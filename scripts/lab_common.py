#!/usr/bin/env python3
"""Shared lab helpers for 115 puller scripts.

Never logs cookie/token values. Defaults: P115_LAB_ROOT=/vpush, device=harmony.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CACHE_SUBDIRS = ("staging", "hot", "failed", "manifest", "logs")
RETRY_SUFFIX = ".retry.json"
SKIP_SUFFIXES = (".retry.json", ".tmp", ".part", ".partial", ".lock", ".swp")
COOKIE_ERRNOS = {99, 401, 911, 40101004, 401990008, 40101017}

_COOKIE_RE = re.compile(
    r"(UID|CID|KID|SEID|SID|USERID|PHPSESSID|access_token|refresh_token)=[^\s;]+",
    re.IGNORECASE,
)
# Align with arm-lab-ops/ops_status.redact: key: value / key=value.
_KV_SECRET_RE = re.compile(
    r"(refresh_token|access_token|cookie)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
# JSON "refresh_token": "..." / "access_token":"..." (ops colon form misses the quotes).
_JSON_SECRET_RE = re.compile(
    r'(["\']?(?:refresh_token|access_token|cookie|UID|CID|SEID|KID)["\']?\s*:\s*)'
    r'(["\'][^"\']*["\']|[^\s,;}"\']+)',
    re.IGNORECASE,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def env_str(name: str, default: str) -> str:
    val = os.environ.get(name, default)
    return default if val is None or val == "" else val


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def cache_root() -> Path:
    return Path(env_str("CACHE_ROOT", "/cache"))


def lab_root() -> str:
    root = env_str("P115_LAB_ROOT", "/vpush").rstrip("/") or "/vpush"
    if not root.startswith("/"):
        root = "/" + root
    return root


def device_type() -> str:
    return env_str("P115_DEVICE_TYPE", "harmony")


def cookies_path() -> Path:
    return Path(env_str("P115_COOKIES_FILE", "/secrets/115-cookies.txt"))


def warn_bytes() -> int:
    return int(env_float("CACHE_WARN_GB", 30.0) * (1024**3))


def force_bytes() -> int:
    return int(env_float("CACHE_FORCE_GB", 35.0) * (1024**3))


def ensure_cache_dirs(root: Path | None = None) -> dict[str, Path]:
    root = root or cache_root()
    paths = {name: root / name for name in CACHE_SUBDIRS}
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    (paths["manifest"] / "inbox").mkdir(parents=True, exist_ok=True)
    return paths


def fail(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def redact(text: str) -> str:
    text = _COOKIE_RE.sub(r"\1=<redacted>", text)
    text = _KV_SECRET_RE.sub(r"\1=<redacted>", text)
    text = _JSON_SECRET_RE.sub(r"\1<redacted>", text)
    if len(text) > 400:
        return text[:400] + "..."
    return text


def safe_exc(exc: BaseException) -> str:
    return redact(f"{type(exc).__name__}: {exc}")


def load_cookies(path: Path | None = None) -> str:
    path = path or cookies_path()
    if not path.is_file():
        fail(f"cookies file missing: {path}", 2)
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        fail(f"cookies file empty: {path}", 2)
    if len(raw) < 10:
        fail("cookies file suspiciously short", 2)
    return raw


def make_client(path: Path | None = None):
    from p115client import P115Client

    cookies = load_cookies(path)
    client = P115Client(cookies, app=device_type(), console_qrcode=False)
    del cookies
    return client


def _cid_from(resp: Any) -> int | None:
    """Parse a directory id from 115 getid/mkdir/upload payloads.

    Current get_path_id shape is ``{"state": true, "data": {"file_id": ..., "is_private": ...}}``.
    Treat 0 as valid (root). Never log the raw response body.
    """
    if not isinstance(resp, dict):
        return None
    candidates: list[Any] = [
        resp.get("id"),
        resp.get("cid"),
        resp.get("file_id"),
        resp.get("fid"),
        resp.get("fileid"),
    ]
    data = resp.get("data")
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("id"),
                data.get("cid"),
                data.get("file_id"),
                data.get("fid"),
                data.get("fileid"),
            ]
        )
    elif data not in (None, "", False):
        candidates.append(data)
    for cid in candidates:
        if cid is None or cid == "":
            continue
        try:
            return int(cid)
        except (TypeError, ValueError):
            continue
    return None


def ensure_remote_dir(client, remote_path: str) -> int:
    """Ensure directory path exists; return cid (int)."""
    path = remote_path if remote_path.startswith("/") else f"/{remote_path}"
    path = path.rstrip("/") or "/"
    if path == "/":
        return 0
    resp = client.fs_dir_getid2({"path": path, "parent_id": 0, "is_create": 1})
    cid = _cid_from(resp)
    if cid is not None:
        return cid
    if isinstance(resp, dict) and not resp.get("state", True) and resp.get("errno"):
        return _ensure_by_walk(client, path)
    return _ensure_by_walk(client, path)


def _item_name(item: dict) -> str | None:
    n = item.get("n") or item.get("fn") or item.get("file_name")
    return str(n) if n else None


def _item_is_dir(item: dict) -> bool:
    if item.get("fc") == "0" or item.get("is_dir"):
        return True
    if item.get("fid") is None and item.get("cid") is not None and "sha" not in item:
        return True
    return False


def _ensure_by_walk(client, path: str) -> int:
    parts = [p for p in path.strip("/").split("/") if p]
    cid = 0
    for i, name in enumerate(parts):
        listing = client.fs_files({"cid": cid, "show_dir": 1, "limit": 1150})
        data = listing.get("data") if isinstance(listing, dict) else None
        found = None
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                if _item_name(item) != name:
                    continue
                if _item_is_dir(item):
                    found = item.get("cid") or item.get("id")
                    if found is not None:
                        break
        if found is not None:
            cid = int(found)
            continue
        mk = client.fs_mkdir({"cname": name, "pid": cid})
        if not isinstance(mk, dict):
            fail(f"fs_mkdir failed for {name} under cid={cid}")
        new_id = mk.get("cid") or mk.get("id")
        if new_id is None and isinstance(mk.get("data"), dict):
            new_id = mk["data"].get("cid") or mk["data"].get("id")
        if new_id is None:
            sub = "/" + "/".join(parts[: i + 1])
            got = client.fs_dir_getid2({"path": sub, "is_create": 0})
            new_id = _cid_from(got)
        if new_id is None:
            fail(f"fs_mkdir could not obtain cid for {name}; resp_keys={list(mk.keys())}")
        cid = int(new_id)
    return cid


def list_dir(client, cid: int, limit: int = 1150) -> list[dict]:
    listing = client.fs_files({"cid": cid, "show_dir": 1, "limit": limit})
    data = listing.get("data") if isinstance(listing, dict) else None
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def list_names(client, cid: int, limit: int = 1150) -> list[str]:
    names: list[str] = []
    for item in list_dir(client, cid, limit=limit):
        n = _item_name(item)
        if n:
            names.append(n)
    return names


def get_path_cid(client, remote_path: str, create: bool = False) -> int | None:
    path = remote_path if remote_path.startswith("/") else f"/{remote_path}"
    path = path.rstrip("/") or "/"
    if path == "/":
        return 0
    resp = client.fs_dir_getid2(
        {"path": path, "parent_id": 0, "is_create": 1 if create else 0}
    )
    return _cid_from(resp)


def _nonzero_errno(up: dict) -> bool:
    errno = up.get("errno")
    if errno in (None, "", False):
        return False
    try:
        return int(errno) != 0
    except (TypeError, ValueError):
        return True


def upload_ok(up: Any) -> bool:
    """True only for a successful 115 upload payload.

    Missing ``state`` or a nonzero ``errno`` is never success. A present
    ``state: false`` can still count if a pickcode / file id is there and
    errno is absent or 0 (same as the previous pickcode fallback).
    """
    if not isinstance(up, dict):
        return False
    if "state" not in up:
        return False
    if _nonzero_errno(up):
        return False
    if up.get("state"):
        return True
    return any(k in up for k in ("pickcode", "file_id", "fid", "fileid"))


def classify_error(exc: BaseException) -> tuple[str, str]:
    """Return (kind, safe_message) where kind is network|cookie|other."""
    msg = safe_exc(exc)
    name = type(exc).__name__
    try:
        from p115client.exception import (
            P115AccessTokenError,
            P115AuthenticationError,
            P115LoginError,
        )
    except Exception:
        P115AuthenticationError = P115LoginError = P115AccessTokenError = tuple()  # type: ignore

    if isinstance(exc, (P115AuthenticationError, P115LoginError, P115AccessTokenError)):
        return "cookie", msg
    if name in {"P115AuthenticationError", "P115LoginError", "P115AccessTokenError"}:
        return "cookie", msg

    errno_val = None
    args = getattr(exc, "args", ())
    for arg in args:
        if isinstance(arg, dict):
            errno_val = arg.get("errno") or arg.get("code") or arg.get("errNo")
            err_txt = str(arg.get("error") or arg.get("message") or arg.get("msg") or "")
            if errno_val in COOKIE_ERRNOS or any(
                tok in err_txt for tok in ("重新登录", "请登录", "未登录", "登录失效")
            ):
                return "cookie", msg
        if isinstance(arg, int) and arg in COOKIE_ERRNOS:
            return "cookie", msg

    net_names = {
        "TimeoutError",
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionAbortedError",
        "ConnectionRefusedError",
        "BrokenPipeError",
        "gaierror",
        "timeout",
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "NewConnectionError",
        "MaxRetryError",
        "SSLError",
        "ProxyError",
        "ProtocolError",
    }
    if name in net_names or isinstance(
        exc, (TimeoutError, ConnectionError, ConnectionResetError, BrokenPipeError)
    ):
        return "network", msg
    if isinstance(exc, OSError):
        import errno as py_errno

        en = getattr(exc, "errno", None)
        # 115 uses errno 99 for "please re-login"; Linux 99 is EADDRNOTAVAIL.
        if "登录" in msg or "login" in msg.lower() or "请重新登录" in msg:
            return "cookie", msg
        net_errnos = {
            py_errno.ECONNREFUSED,
            py_errno.ETIMEDOUT,
            py_errno.EHOSTUNREACH,
            py_errno.ENETUNREACH,
            py_errno.ECONNRESET,
            py_errno.EPIPE,
            getattr(py_errno, "EADDRNOTAVAIL", 99),
        }
        if en in net_errnos:
            return "network", msg
        if "timed out" in msg.lower() or "network" in msg.lower() or "temporarily" in msg.lower():
            return "network", msg
    if "登录" in msg or "cookie" in msg.lower():
        return "cookie", msg
    return "other", msg


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def file_sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_sha1(path: Path) -> str:
    import hashlib

    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def date_shard(when=None) -> str:
    """YYYY/MM/DD using Asia/Shanghai (UTC+8) when when is None."""
    from datetime import timedelta

    if when is None:
        when = datetime.now(timezone(timedelta(hours=8)))
    elif getattr(when, "tzinfo", None) is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.strftime("%Y/%m/%d")


def cicc_research_rel(stable_id: str, *, when=None, ext: str = ".pdf") -> str:
    """local/cicc-research/YYYY/MM/DD/<stable-id>.ext"""
    if not ext.startswith("."):
        ext = "." + ext
    return f"local/cicc-research/{date_shard(when)}/{stable_id}{ext}"


def skip_file(path: Path) -> bool:
    name = path.name
    if name.startswith(".") or name.startswith("#"):
        return True
    lowered = name.lower()
    return any(lowered.endswith(suf) for suf in SKIP_SUFFIXES)


def safe_relpath(raw: str) -> Path:
    """Relative path whitelist matching ops ``safe_relpath``.

    Rejects empty, NUL, absolute, ``~``, and ``..`` segments. Does not
    touch the filesystem.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("path required")
    if "\x00" in raw:
        raise ValueError("invalid path")
    text = raw.strip().replace("\\", "/")
    if text.startswith(("/", "~")):
        raise ValueError("path must be relative")
    parts: list[str] = []
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("path escapes root")
        parts.append(part)
    if not parts:
        raise ValueError("path required")
    return Path(*parts)


def resolve_under(root: Path, rel: str | Path) -> Path:
    """Resolve ``root / rel`` and require the result stay under ``root``."""
    rel_path = rel if isinstance(rel, Path) else safe_relpath(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError("path escapes root")
    root_res = root.resolve()
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root_res)
    except ValueError as exc:
        raise ValueError("path escapes root") from exc
    return candidate


def rel_under(path: Path, root: Path) -> Path:
    rel = path.resolve().relative_to(root.resolve())
    if ".." in rel.parts:
        raise ValueError(f"path escapes root: {path}")
    return rel


def tree_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                if fp.is_file() and not fp.is_symlink():
                    total += fp.stat().st_size
            except OSError:
                continue
    return total


def fs_usage(path: Path) -> dict[str, int]:
    st = os.statvfs(path)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - (st.f_bfree * st.f_frsize)
    return {"total": total, "used": used, "free": free}


def gb(n: int | float) -> float:
    return round(n / (1024**3), 3)
