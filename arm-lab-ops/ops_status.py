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
    CICC_INCR_DAYS_DEFAULT,
    CICC_SYNC_LOG_GLOB,
    FAILED_LIST_CAP,
    IMA_HOST_SYNC_LOG_GLOB,
    IMA_SYNC_LOG_GLOB,
    JOURNAL_LINES,
    LAST_JOB_NAME,
    LOG_FILE_CAP,
    LOG_TAIL_LINES,
    SKIP_SUFFIXES,
    WALK_FILE_CAP,
    WALK_SECONDS_CAP,
    cache_force_bytes,
    cache_force_gb,
    cache_root,
    cache_warn_bytes,
    cache_warn_gb,
    cicc_cookie_path,
    cicc_timer_unit,
    cookies_path,
    docker_sock,
    export_root,
    ima_secrets_path,
    openlist_public_url,
    pull_health_url,
    puller_container_name,
    puller_health_file,
    puller_health_url,
    puller_unit,
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
    "uploaded_count",
    "failed_count",
    "skipped_count",
    "tick_ok",
    "tick_fail",
    "tick_skip",
    "keep_hot",
    "batch_size",
    "admitted",
    "action",
    "argv",
    "returncode",
    "timeout",
    "stdout",
    "stderr",
    "limit",
    "group",
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
    name = puller_container_name()
    if not name:
        return {"available": False, "source": None, "containers": []}
    sock = docker_sock()
    via_cli = _docker_via_cli(name)
    if via_cli is not None:
        return via_cli
    via_sock = _docker_via_sock(sock, name)
    if via_sock is not None:
        return via_sock
    return {"available": sock.exists(), "source": None, "containers": []}


def _parse_systemctl_show(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _systemctl_show_timer(name: str) -> dict[str, Any] | None:
    try:
        proc = subprocess.run(
            [
                "systemctl",
                "show",
                name,
                "--property=ActiveState,UnitFileState,NextElapseUSecRealtime,LastTriggerUSec",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    props = _parse_systemctl_show(proc.stdout)
    if not props:
        return None

    def _clean(raw: str | None) -> str | None:
        value = (raw or "").strip()
        if not value or value.lower() in {"n/a", "0", "none"}:
            return None
        return value

    known = {"active", "inactive", "failed", "activating", "deactivating"}
    active = (props.get("ActiveState") or "").strip()
    return {
        "unit": name,
        "active": active if active in known else (active or "unknown"),
        "detail": None,
        "enabled": _clean(props.get("UnitFileState")),
        "next": _clean(props.get("NextElapseUSecRealtime")),
        "last_trigger": _clean(props.get("LastTriggerUSec")),
    }


def timer_status(unit: str | None = None) -> dict[str, Any]:
    name = unit or timer_unit()
    shown = _systemctl_show_timer(name)
    if shown is not None:
        return shown
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
        return {
            "unit": name,
            "active": "unknown",
            "detail": type(exc).__name__,
            "next": None,
            "last_trigger": None,
        }
    active = (proc.stdout or "").strip()
    if active in known:
        return {"unit": name, "active": active, "detail": None, "next": None, "last_trigger": None}
    err = redact((proc.stderr or active or "unavailable").splitlines()[0])
    return {
        "unit": name,
        "active": "unavailable",
        "detail": err[:80],
        "next": None,
        "last_trigger": None,
    }


def service_status(unit: str | None = None) -> dict[str, Any]:
    """Best-effort `systemctl show` for a long-running unit (lab puller)."""
    name = unit or puller_unit()
    try:
        proc = subprocess.run(
            [
                "systemctl",
                "show",
                name,
                "--property=ActiveState,UnitFileState,SubState,MainPID",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "unit": name,
            "active": "unknown",
            "detail": type(exc).__name__,
            "enabled": None,
            "sub": None,
            "pid": None,
        }
    if proc.returncode != 0:
        raw = (proc.stderr or proc.stdout or "unavailable").splitlines()
        err = redact(raw[0] if raw else "unavailable")
        return {
            "unit": name,
            "active": "unavailable",
            "detail": err[:80],
            "enabled": None,
            "sub": None,
            "pid": None,
        }
    props = _parse_systemctl_show(proc.stdout)
    known = {"active", "inactive", "failed", "activating", "deactivating"}
    active = (props.get("ActiveState") or "").strip()
    pid_raw = (props.get("MainPID") or "").strip()
    pid = int(pid_raw) if pid_raw.isdigit() and int(pid_raw) > 0 else None
    enabled = (props.get("UnitFileState") or "").strip() or None
    if enabled and enabled.lower() in {"n/a", "0", "none"}:
        enabled = None
    return {
        "unit": name,
        "active": active if active in known else (active or "unknown"),
        "detail": None,
        "enabled": enabled,
        "sub": (props.get("SubState") or "").strip() or None,
        "pid": pid,
    }


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


_SYNC_GROUP_RE = re.compile(r"\bgroup=([A-Za-z0-9:_-]+)")
_SYNC_COUNTS_RE = re.compile(
    r"downloaded=(\d+)\s+skipped=(\d+)\s+failed=(\d+)",
    re.IGNORECASE,
)
_SYNC_ERROR_RE = re.compile(r"\b(FAIL|ERROR|失败|Traceback)\b", re.IGNORECASE)


def skip_cache_file(path: Path) -> bool:
    name = path.name
    if name.startswith((".", "#")):
        return True
    lowered = name.lower()
    return any(lowered.endswith(suf) for suf in SKIP_SUFFIXES)


def _latest_log(root: Path, *globs: str) -> Path | None:
    log_dir = root / "logs"
    if not log_dir.is_dir():
        return None
    matches: list[Path] = []
    for pattern in globs:
        matches.extend(p for p in log_dir.glob(pattern) if p.is_file())
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return matches[0]


def latest_ima_sync_log(root: Path | None = None) -> Path | None:
    return _latest_log(root or cache_root(), IMA_HOST_SYNC_LOG_GLOB, IMA_SYNC_LOG_GLOB)


def latest_cicc_sync_log(root: Path | None = None) -> Path | None:
    return _latest_log(root or cache_root(), CICC_SYNC_LOG_GLOB, "cicc-lab-sync-*.log")


def parse_ima_sync_log(path: Path) -> dict[str, Any]:
    """Redacted summary of an ima-lab-sync-*.log (last run + per-group counts)."""
    empty = {
        "log": path.name if path else None,
        "mtime": iso_mtime(path) if path and path.is_file() else None,
        "last_run": None,
        "groups": {},
        "totals": {"downloaded": 0, "skipped": 0, "failed": 0},
        "last_error": None,
    }
    if not path.is_file():
        return empty
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return empty
    if len(text) > 400_000:
        text = text[-400_000:]
    lines = text.splitlines()
    groups: dict[str, dict[str, int]] = {}
    group_has_summary: set[str] = set()
    current = "unknown"
    last_error = None
    last_run = iso_mtime(path)

    def bucket(name: str) -> dict[str, int]:
        if name not in groups:
            groups[name] = {"downloaded": 0, "skipped": 0, "failed": 0}
        return groups[name]

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        gmatch = _SYNC_GROUP_RE.search(line)
        if gmatch:
            current = gmatch.group(1)
        cmatch = _SYNC_COUNTS_RE.search(line)
        if cmatch:
            row = bucket(current)
            row["downloaded"] = int(cmatch.group(1))
            row["skipped"] = int(cmatch.group(2))
            row["failed"] = int(cmatch.group(3))
            group_has_summary.add(current)
            continue
        kind = line.split(None, 1)[0].upper() if line.split() else ""
        if current not in group_has_summary:
            if kind in {"SYNC", "DOWNLOADED"}:
                bucket(current)["downloaded"] += 1
            elif kind in {"SKIP", "SKIPPED"}:
                bucket(current)["skipped"] += 1
            elif kind == "FAIL":
                bucket(current)["failed"] += 1
        if _SYNC_ERROR_RE.search(line):
            last_error = redact(line)

    totals = {"downloaded": 0, "skipped": 0, "failed": 0}
    for row in groups.values():
        for key in totals:
            totals[key] += row[key]
    return {
        "log": path.name,
        "mtime": iso_mtime(path),
        "last_run": last_run,
        "groups": groups,
        "totals": totals,
        "last_error": last_error,
    }


def journal_snippet(unit: str | None = None) -> dict[str, Any]:
    """Best-effort redacted journal tail for the lab sync service."""
    timer = unit or timer_unit()
    service = timer[:-6] + ".service" if timer.endswith(".timer") else timer
    try:
        proc = subprocess.run(
            ["journalctl", "-u", service, "-n", str(JOURNAL_LINES), "--no-pager", "-o", "cat"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "unit": service, "tail": [], "detail": type(exc).__name__}
    if proc.returncode != 0:
        err = redact((proc.stderr or "unavailable").splitlines()[0]) if proc.stderr else "unavailable"
        return {"available": False, "unit": service, "tail": [], "detail": err[:80]}
    tail = [redact(line) for line in (proc.stdout or "").splitlines() if line.strip()]
    return {"available": True, "unit": service, "tail": tail[-20:], "detail": None}


def parse_cicc_sync_log(path: Path) -> dict[str, Any]:
    empty = {
        "log": path.name if path else None,
        "mtime": iso_mtime(path) if path and path.is_file() else None,
        "last_run": None,
        "days": None,
        "dry_run": None,
        "returncode": None,
        "last_error": None,
    }
    if not path.is_file():
        return empty
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return empty
    if len(text) > 200_000:
        text = text[-200_000:]
    days = None
    dry_run = None
    returncode = None
    last_error = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("start "):
            match = re.search(r"days=(\d+)", line)
            if match:
                days = int(match.group(1))
            dry_match = re.search(r"dry_run=(\d+)", line)
            if dry_match:
                dry_run = dry_match.group(1) == "1"
        if line.startswith("done "):
            rc = re.search(r"rc=(-?\d+)", line)
            if rc:
                returncode = int(rc.group(1))
        if _SYNC_ERROR_RE.search(line):
            last_error = redact(line)
    return {
        "log": path.name,
        "mtime": iso_mtime(path),
        "last_run": iso_mtime(path),
        "days": days,
        "dry_run": dry_run,
        "returncode": returncode,
        "last_error": last_error,
    }


def cicc_sync_summary(root: Path | None = None) -> dict[str, Any]:
    target = latest_cicc_sync_log(root)
    if target is None:
        summary: dict[str, Any] = {
            "log": None,
            "mtime": None,
            "last_run": None,
            "days": None,
            "dry_run": None,
            "returncode": None,
            "last_error": None,
        }
    else:
        summary = parse_cicc_sync_log(target)
    journal = journal_snippet(cicc_timer_unit())
    summary["journal"] = journal
    return summary


def export_status() -> dict[str, Any]:
    root = export_root()
    cicc = walk_usage(root / "local" / "cicc-research")
    return {
        "root": str(root),
        "exists": root.exists(),
        "cicc_research": cicc,
    }


def pull_listener_status() -> dict[str, Any]:
    url = pull_health_url()
    if not url:
        return {"ok": False, "status": "unconfigured", "url": ""}
    try:
        import httpx

        with httpx.Client(timeout=2.0, follow_redirects=True) as client:
            resp = client.get(url)
        text = (resp.text or "").strip()[:32]
        return {
            "ok": resp.status_code == 200,
            "status": text or str(resp.status_code),
            "url": url,
        }
    except Exception as exc:
        return {"ok": False, "status": type(exc).__name__, "url": url}


def settings_incr_days(root: Path | None = None) -> int:
    path = (root or cache_root()) / "ops-lab-settings.json"
    payload = _json_from_path(path)
    if not isinstance(payload, dict):
        return CICC_INCR_DAYS_DEFAULT
    try:
        value = int(payload.get("cicc_incr_days") or CICC_INCR_DAYS_DEFAULT)
    except (TypeError, ValueError):
        return CICC_INCR_DAYS_DEFAULT
    return value if 1 <= value <= 14 else CICC_INCR_DAYS_DEFAULT


def puller_policy(root: Path | None = None) -> dict[str, Any]:
    target = root or cache_root()
    payload = _json_from_path(target / "manifest" / "puller-heartbeat.json")
    if not isinstance(payload, dict):
        return {"keep_hot": True, "batch_size": None, "source": "default"}
    keep = payload.get("keep_hot")
    batch = payload.get("batch_size")
    return {
        "keep_hot": True if keep is None else bool(keep),
        "batch_size": batch if isinstance(batch, int) else None,
        "source": "heartbeat",
    }


def sync_summary(root: Path | None = None) -> dict[str, Any]:
    target = latest_ima_sync_log(root)
    if target is None:
        summary: dict[str, Any] = {
            "log": None,
            "mtime": None,
            "last_run": None,
            "groups": {},
            "totals": {"downloaded": 0, "skipped": 0, "failed": 0},
            "last_error": None,
        }
    else:
        summary = parse_ima_sync_log(target)
    journal = journal_snippet()
    summary["journal"] = journal
    return summary


def list_failed_files(root: Path | None = None, cap: int = FAILED_LIST_CAP) -> dict[str, Any]:
    failed = (root or cache_root()) / "failed"
    if not failed.exists():
        return {"exists": False, "items": [], "count": 0, "truncated": False, "cap": cap}
    items: list[dict[str, Any]] = []
    truncated = False
    seen = 0
    stack = [failed]
    deadline = time.monotonic() + WALK_SECONDS_CAP
    while stack:
        if time.monotonic() >= deadline:
            truncated = True
            break
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                path = Path(entry.path)
                if skip_cache_file(path):
                    continue
                seen += 1
                try:
                    rel = path.resolve().relative_to(failed.resolve()).as_posix()
                except ValueError:
                    continue
                if ".." in Path(rel).parts:
                    continue
                stat = entry.stat(follow_symlinks=False)
                items.append(
                    {
                        "path": rel,
                        "size": int(stat.st_size),
                        "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    }
                )
            except OSError:
                continue
    items.sort(key=lambda row: row.get("mtime") or "", reverse=True)
    if len(items) > cap:
        truncated = True
        items = items[:cap]
    return {
        "exists": True,
        "items": items,
        "count": seen,
        "truncated": truncated,
        "cap": cap,
    }


def cache_waterline(root: Path | None = None) -> dict[str, Any]:
    target = root or cache_root()
    staging = walk_usage(target / "staging")
    hot = walk_usage(target / "hot")
    failed = walk_usage(target / "failed")
    used = int(staging.get("bytes") or 0) + int(hot.get("bytes") or 0) + int(failed.get("bytes") or 0)
    warn = cache_warn_bytes()
    force = cache_force_bytes()
    level = "ok"
    if used >= force:
        level = "force"
    elif used >= warn:
        level = "warn"
    pct = round((used / force) * 100, 1) if force else 0.0
    return {
        "used_bytes": used,
        "warn_bytes": warn,
        "force_bytes": force,
        "warn_gb": cache_warn_gb(),
        "force_gb": cache_force_gb(),
        "used_pct_of_force": pct,
        "level": level,
        "truncated": bool(
            staging.get("truncated") or hot.get("truncated") or failed.get("truncated")
        ),
    }


def _count_uploads_jsonl(path: Path, line_cap: int = 200) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    ok = fail = 0
    for line in lines[-line_cap:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("ok") is True:
            ok += 1
        elif row.get("ok") is False:
            fail += 1
    return {"ok": ok, "fail": fail, "source": "uploads.jsonl", "window": f"last_{min(len(lines), line_cap)}"}


def _count_uploads_sqlite(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        import sqlite3

        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            row = conn.execute(
                "SELECT "
                "SUM(CASE WHEN status IN ('uploaded','hot') THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) "
                "FROM files"
            ).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    if not row:
        return None
    return {
        "ok": int(row[0] or 0),
        "fail": int(row[1] or 0),
        "source": "lab.sqlite",
        "window": "all",
    }


def puller_upload_counts(root: Path | None = None) -> dict[str, Any]:
    target = root or cache_root()
    jsonl = _count_uploads_jsonl(target / "manifest" / "uploads.jsonl")
    if jsonl is not None:
        return jsonl
    heartbeat = target / "manifest" / "puller-heartbeat.json"
    payload = _json_from_path(heartbeat)
    if isinstance(payload, dict):
        tick_ok = payload.get("tick_ok")
        tick_fail = payload.get("tick_fail")
        if isinstance(tick_ok, int) or isinstance(tick_fail, int):
            return {
                "ok": int(tick_ok or 0),
                "fail": int(tick_fail or 0),
                "source": "heartbeat",
                "window": "last_tick",
            }
        uploaded = payload.get("uploaded_count")
        failed = payload.get("failed_count")
        if isinstance(uploaded, int) or isinstance(failed, int):
            return {
                "ok": int(uploaded or 0),
                "fail": int(failed or 0),
                "source": "heartbeat",
                "window": "lifetime",
            }
    sqlite = _count_uploads_sqlite(target / "manifest" / "lab.sqlite")
    if sqlite is not None:
        return sqlite
    return {"ok": 0, "fail": 0, "source": "none", "window": None}


def read_last_job(root: Path | None = None) -> dict[str, Any] | None:
    path = (root or cache_root()) / "logs" / LAST_JOB_NAME
    payload = _json_from_path(path)
    if not isinstance(payload, dict):
        return None
    cleaned = sanitize_health(payload)
    if not isinstance(cleaned, dict):
        return None
    for key in ("stdout", "stderr", "error"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = redact(cleaned[key])
    return cleaned


def collect_status() -> dict[str, Any]:
    root = cache_root()
    health_url = puller_health_url()
    file_health = health_from_file(puller_health_file())
    url_health = health_from_url(health_url) if health_url else None
    unit = service_status()
    docker = docker_status()
    source = "none"
    if url_health is not None:
        source = "health_url"
    elif file_health is not None:
        source = "health_file"
    elif unit.get("active") == "active":
        source = "systemd"
    elif docker.get("containers"):
        source = "docker"
    elif (root / "logs").is_dir():
        source = "logs"
    timer = timer_status()
    cicc_timer = timer_status(cicc_timer_unit())
    if source == "none" and timer.get("active") not in {None, "unknown"}:
        source = "systemd"
    policy = puller_policy(root)
    export = export_status()
    pull = pull_listener_status()
    ima_timer_live = timer.get("enabled") not in {None, "disabled", "masked"} and timer.get("active") == "active"

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roles": {
            "ima_collect": "vpush_pull",
            "cicc_collect": "arm_incr",
            "storage": "hot_then_115",
            "vpush_link": "http_pull",
            "ima_dual_collect": ima_timer_live,
        },
        "cache": {
            "root": str(root),
            "exists": root.exists(),
            "disk": disk_usage(root) if root.exists() or root.parent.exists() else None,
            "waterline": cache_waterline(root),
            "staging": walk_usage(root / "staging"),
            "hot": walk_usage(root / "hot"),
            "failed": walk_usage(root / "failed"),
        },
        "export": export,
        "pull": pull,
        "failed_queue": list_failed_files(root),
        "sync": sync_summary(root),
        "cicc_sync": cicc_sync_summary(root),
        "last_job": read_last_job(root),
        "puller": {
            "source": source,
            "unit": unit,
            "docker": docker,
            "health": url_health or file_health,
            "timer": timer,
            "cicc_timer": cicc_timer,
            "uploads": puller_upload_counts(root),
            "policy": policy,
            "logs": log_tails(root),
        },
        "ima": {
            **ima_cred_status(),
            "timer": timer,
            "note": "IMA QR is not on this panel. Use Mac ima_phone_sync.",
        },
        "p115": cookie_meta(),
        "cicc": {
            **cookie_meta(cicc_cookie_path()),
            "timer": cicc_timer,
            "incr_days": settings_incr_days(root),
        },
        "openlist": {"url": openlist_public_url()},
    }
