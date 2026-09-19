"""Read-only lab status. Never returns cookie / refresh_token bodies."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ops_settings import (
    LOG_FILE_CAP,
    LOG_TAIL_LINES,
    WALK_FILE_CAP,
    WALK_SECONDS_CAP,
    cache_root,
    cookies_path,
    docker_sock,
    ima_secrets_path,
    openlist_public_url,
    puller_container_name,
    puller_health_file,
    puller_health_url,
    timer_unit,
)

_COOKIE_RE = re.compile(
    r"(UID|CID|KID|SEID|SID|USERID|PHPSESSID|access_token|refresh_token)=[^\s;]+",
    re.IGNORECASE,
)
_SECRET_KEY_RE = re.compile(
    r"(cookie|token|password|secret|authorization|seid|refresh)",
    re.IGNORECASE,
)
_SAFE_HEALTH_KEYS = {
    "ok",
    "status",
    "state",
    "active",
    "healthy",
    "uptime",
    "updated_at",
    "ts",
    "timestamp",
    "container",
    "name",
    "error",
    "code",
    "files",
    "bytes",
    "staging",
    "hot",
    "failed",
    "last_ok",
    "last_error",
    "pid",
}


def iso_mtime(path: Path) -> str | None:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact(text: str) -> str:
    text = _COOKIE_RE.sub(r"\1=<redacted>", text)
    text = re.sub(
        r"(refresh_token|access_token|cookie)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    if len(text) > 400:
        return text[:400] + "..."
    return text


def _json_from_path(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None


def ima_cred_status(path: Path | None = None) -> dict[str, Any]:
    """Return {present, mtime, uid_len} only. Never include refresh_token."""
    target = path or ima_secrets_path()
    if not target.is_file():
        return {"present": False, "mtime": None, "uid_len": 0}
    uid_len = 0
    data = _json_from_path(target)
    if isinstance(data, dict):
        uid = data.get("uid")
        if isinstance(uid, str):
            uid_len = len(uid)
    return {"present": True, "mtime": iso_mtime(target), "uid_len": uid_len}


def cookie_meta(path: Path | None = None) -> dict[str, Any]:
    """Return {present, mtime, length} only. Never include cookie body."""
    target = path or cookies_path()
    if not target.is_file():
        return {"present": False, "mtime": None, "length": 0}
    try:
        length = target.stat().st_size
    except OSError:
        length = 0
    return {"present": True, "mtime": iso_mtime(target), "length": int(length)}


def disk_usage(root: Path) -> dict[str, Any] | None:
    try:
        usage = shutil.disk_usage(root if root.exists() else root.parent)
    except OSError:
        return None
    pct = round((usage.used / usage.total) * 100, 1) if usage.total else 0.0
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_pct": pct,
    }


def _du_bytes(path: Path) -> int | None:
    try:
        proc = subprocess.run(
            ["du", "-sb", str(path)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    first = proc.stdout.split()[0]
    if not first.isdigit():
        return None
    return int(first)


def walk_usage(
    path: Path,
    file_cap: int = WALK_FILE_CAP,
    seconds_cap: float = WALK_SECONDS_CAP,
) -> dict[str, Any]:
    """Count files and bytes under path. Caps work; may set truncated."""
    if not path.exists():
        return {"exists": False, "files": 0, "bytes": 0, "truncated": False}
    if not path.is_dir():
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        return {"exists": True, "files": 1, "bytes": size, "truncated": False}

    files = 0
    total = 0
    truncated = False
    deadline = time.monotonic() + seconds_cap
    stack = [path]
    while stack:
        if files >= file_cap or time.monotonic() >= deadline:
            truncated = True
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if files >= file_cap or time.monotonic() >= deadline:
                        truncated = True
                        break
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                            continue
                        if entry.is_file(follow_symlinks=False):
                            files += 1
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue

    if truncated:
        du = _du_bytes(path)
        if du is not None:
            total = du
    return {"exists": True, "files": files, "bytes": total, "truncated": truncated}


def sanitize_health(value: Any, depth: int = 0) -> Any:
    """Drop secret keys and redact leftover strings. Keep a small safe subset."""
    if depth > 4:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or _SECRET_KEY_RE.search(key):
                continue
            if key not in _SAFE_HEALTH_KEYS and not isinstance(item, (int, float, bool)):
                cleaned = sanitize_health(item, depth + 1)
                if cleaned is None or cleaned == {} or cleaned == []:
                    continue
                out[key] = cleaned
                continue
            out[key] = sanitize_health(item, depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize_health(item, depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return None


def _http_json(url: str, timeout: float = 2.0) -> Any:
    import httpx

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def health_from_url(url: str) -> dict[str, Any] | None:
    if not url:
        return None
    try:
        payload = _http_json(url)
    except Exception:
        return None
    cleaned = sanitize_health(payload)
    return cleaned if isinstance(cleaned, dict) else None


def health_from_file(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = _json_from_path(path)
    cleaned = sanitize_health(payload)
    return cleaned if isinstance(cleaned, dict) else None


def _docker_via_cli(name: str) -> dict[str, Any] | None:
    fmt = "{{.Names}}\t{{.Status}}\t{{.State}}"
    cmd = ["docker", "ps", "-a", "--format", fmt]
    if name:
        cmd.extend(["--filter", f"name={name}"])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        cname, status, state = parts[0], parts[1], parts[2]
        if name and name not in cname:
            continue
        if not name and not any(token in cname.lower() for token in ("puller", "ima-lab", "vpush-ima")):
            continue
        rows.append({"name": cname, "status": status, "state": state})
    if not rows:
        return {"available": True, "source": "docker-cli", "containers": []}
    return {"available": True, "source": "docker-cli", "containers": rows[:8]}


def _docker_via_sock(sock: Path, name: str) -> dict[str, Any] | None:
    if not sock.exists():
        return None
    try:
        import httpx

        transport = httpx.HTTPTransport(uds=str(sock))
        with httpx.Client(transport=transport, timeout=2.0) as client:
            resp = client.get("http://localhost/containers/json", params={"all": "true"})
            resp.raise_for_status()
            items = resp.json()
    except Exception:
        return None
    if not isinstance(items, list):
        return None
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        names = item.get("Names") or []
        joined = " ".join(str(n) for n in names)
        if name and name not in joined:
            continue
        if not name and not any(token in joined.lower() for token in ("puller", "ima-lab", "vpush-ima")):
            continue
        rows.append(
            {
                "name": joined.strip(),
                "status": str(item.get("Status") or ""),
                "state": str(item.get("State") or ""),
            }
        )
    return {"available": True, "source": "docker.sock", "containers": rows[:8]}


def docker_status() -> dict[str, Any]:
    sock = docker_sock()
    name = puller_container_name()
    via_cli = _docker_via_cli(name)
    if via_cli is not None:
        return via_cli
    via_sock = _docker_via_sock(sock, name)
    if via_sock is not None:
        return via_sock
    return {"available": sock.exists(), "source": None, "containers": []}


def timer_status(unit: str | None = None) -> dict[str, Any]:
    name = unit or timer_unit()
    known = {"active", "inactive", "failed", "activating", "deactivating"}
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"unit": name, "active": "unknown", "detail": type(exc).__name__}
    active = (proc.stdout or "").strip()
    if active in known:
        return {"unit": name, "active": active, "detail": None}
    err = redact((proc.stderr or active or "unavailable").splitlines()[0])
    return {"unit": name, "active": "unavailable", "detail": err[:80]}


def log_tails(root: Path, limit: int = LOG_TAIL_LINES) -> list[dict[str, Any]]:
    log_dir = root / "logs"
    if not log_dir.is_dir():
        return []
    files = sorted(
        [p for p in log_dir.iterdir() if p.is_file() and p.suffix in {".log", ".txt", ".jsonl"}],
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for path in files[:LOG_FILE_CAP]:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        tail = [redact(line) for line in lines[-limit:]]
        out.append({"name": path.name, "mtime": iso_mtime(path), "tail": tail})
    return out


def collect_status() -> dict[str, Any]:
    root = cache_root()
    health_url = puller_health_url()
    file_health = health_from_file(puller_health_file())
    url_health = health_from_url(health_url) if health_url else None
    docker = docker_status()
    source = "none"
    if url_health is not None:
        source = "health_url"
    elif file_health is not None:
        source = "health_file"
    elif docker.get("containers"):
        source = "docker"
    elif (root / "logs").is_dir():
        source = "logs"
    timer = timer_status()
    if source == "none" and timer.get("active") not in {None, "unknown"}:
        source = "systemd"

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cache": {
            "root": str(root),
            "exists": root.exists(),
            "disk": disk_usage(root) if root.exists() or root.parent.exists() else None,
            "staging": walk_usage(root / "staging"),
            "hot": walk_usage(root / "hot"),
            "failed": walk_usage(root / "failed"),
        },
        "puller": {
            "source": source,
            "docker": docker,
            "health": url_health or file_health,
            "timer": timer,
            "logs": log_tails(root),
        },
        "ima": {
            **ima_cred_status(),
            "note": "IMA QR is not on this panel. Use Mac ima_phone_sync.",
        },
        "p115": cookie_meta(),
        "openlist": {"url": openlist_public_url()},
    }
