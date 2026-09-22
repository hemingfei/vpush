"""Keep vpush up when a remote archive host dies.

Hard NFS on the production host is what dragged DMIT down with the
storage box: any ``stat`` / ``open`` / ``resolve`` on a hung mount
goes D-state and cannot be killed. ARM is the collection + HTTP
front; production must never kernel-mount ARM or storage.

This module only reads ``/proc/mounts`` (or a test string). It never
touches the archive path.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_NFS_TYPES = frozenset({"nfs", "nfs3", "nfs4"})
_DEFAULT_PULL_TIMEOUT = 20
_DEFAULT_FETCH_TIMEOUT = 5
_DEFAULT_FAILS = 2
_DEFAULT_COOLDOWN = 60.0


def path_without_stat(path: Path | str) -> Path:
    """Absolute path with expanduser only. No ``stat`` / ``resolve``."""
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _mount_entries(mounts_text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mountpoint = parts[1].replace("\\040", " ").replace("\\011", "\t")
        mountpoint = mountpoint.rstrip("/") or "/"
        entries.append((mountpoint, parts[2]))
    return entries


def is_remote_nfs(path: Path | str, mounts_text: str | None = None) -> bool:
    """True when ``path`` is on nfs/nfs4 according to mount table.

    Uses the longest matching mountpoint. Missing ``/proc/mounts``
    (macOS tests) is treated as not NFS.
    """
    raw = os.path.abspath(os.path.expanduser(str(path)))
    text = mounts_text
    if text is None:
        try:
            text = Path("/proc/mounts").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
    best = ""
    fstype = ""
    for mountpoint, kind in _mount_entries(text):
        if raw == mountpoint or raw.startswith(mountpoint.rstrip("/") + "/"):
            if len(mountpoint) >= len(best):
                best = mountpoint
                fstype = kind
        elif mountpoint == "/" and raw.startswith("/"):
            if len(mountpoint) >= len(best):
                best = mountpoint
                fstype = kind
    return fstype in _NFS_TYPES


class CircuitBreaker:
    """Fail-open after consecutive errors so a dead ARM cannot pile workers."""

    def __init__(
        self,
        *,
        failures: int = _DEFAULT_FAILS,
        cooldown: float = _DEFAULT_COOLDOWN,
    ) -> None:
        self.failures_needed = max(1, int(failures))
        self.cooldown = max(1.0, float(cooldown))
        self._fail = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at:
                if time.monotonic() - self._opened_at < self.cooldown:
                    return False
                self._opened_at = 0.0
                self._fail = 0
            return True

    def is_open(self) -> bool:
        with self._lock:
            if not self._opened_at:
                return False
            return time.monotonic() - self._opened_at < self.cooldown

    def success(self) -> None:
        with self._lock:
            self._fail = 0
            self._opened_at = 0.0

    def failure(self) -> None:
        with self._lock:
            self._fail += 1
            if self._fail >= self.failures_needed:
                self._opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._fail = 0
            self._opened_at = 0.0


_arm_circuit = CircuitBreaker()


def arm_circuit() -> CircuitBreaker:
    return _arm_circuit


def reset_arm_circuit() -> None:
    _arm_circuit.reset()


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(lo, min(hi, value))


def pull_timeout_seconds() -> int:
    return _env_int("IMA_PULL_TIMEOUT", _DEFAULT_PULL_TIMEOUT, lo=2, hi=120)


def fetch_timeout_seconds() -> int:
    return _env_int("IMA_FETCH_TIMEOUT", _DEFAULT_FETCH_TIMEOUT, lo=1, hi=30)


def _pull_sibling(suffix: str) -> str:
    pull = os.environ.get("IMA_PULL_URL", "").strip()
    if pull.endswith("/pull"):
        return pull[: -len("/pull")] + suffix
    return ""


def archive_fetch_url() -> str:
    explicit = os.environ.get("IMA_FETCH_URL", "").strip()
    if explicit:
        return explicit
    return _pull_sibling("/file")


def archive_list_url() -> str:
    explicit = os.environ.get("IMA_LIST_URL", "").strip()
    if explicit:
        return explicit
    return _pull_sibling("/list")


def _allowed_fetch_dest(dest: str) -> bool:
    lower = dest.lower()
    if lower.endswith(".pdf") or lower.endswith(".txt"):
        return True
    return dest.startswith("local/") and lower.endswith(".json")


def list_archive_prefix(prefix: str) -> list[dict[str, object]]:
    """List incremental local-library files on ARM. Empty on failure."""
    url = archive_list_url()
    token = os.environ.get("IMA_PULL_TOKEN", "").strip()
    text = str(prefix or "").replace("\\", "/").strip("/")
    if not url or not token or not text.startswith("local/") or ".." in Path(text).parts:
        return []
    if not _arm_circuit.allow():
        return []
    query = urllib.parse.urlencode({"prefix": text})
    request = urllib.request.Request(
        f"{url}?{query}",
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=fetch_timeout_seconds()) as response:
            payload = json.loads(response.read().decode())
        _arm_circuit.success()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        _arm_circuit.failure()
        return []
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        return []
    out: list[dict[str, object]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        dest = str(item.get("dest") or "").replace("\\", "/").lstrip("/")
        if not dest or dest.startswith("/") or ".." in Path(dest).parts:
            continue
        if not dest.startswith(text + "/") and dest != text:
            continue
        if not _allowed_fetch_dest(dest):
            continue
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        out.append({"dest": dest, "size": size})
    return out


def fetch_missing_archive_file(root: Path, relative: str) -> Path | None:
    """GET a missing local file from ARM over HTTP. Never used on NFS."""
    if is_remote_nfs(root):
        return None
    url = archive_fetch_url()
    token = os.environ.get("IMA_PULL_TOKEN", "").strip()
    if not url or not token:
        return None
    dest = str(relative or "").replace("\\", "/").lstrip("/")
    if not dest or dest.startswith("/") or ".." in Path(dest).parts:
        return None
    if not _allowed_fetch_dest(dest):
        return None
    if not _arm_circuit.allow():
        return None
    query = urllib.parse.urlencode({"dest": dest})
    request = urllib.request.Request(
        f"{url}?{query}",
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    target = path_without_stat(root) / dest
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".vpush-fetch-", suffix=".part", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with urllib.request.urlopen(request, timeout=fetch_timeout_seconds()) as response:
            data = response.read()
        if not data:
            raise RuntimeError("empty fetch")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        _arm_circuit.success()
        return target
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, RuntimeError):
        _arm_circuit.failure()
        tmp.unlink(missing_ok=True)
        return None


def arm_pull_status(*, timeout: float = 2.0) -> dict[str, object]:
    """Probe ARM ima-pull /healthz. Short timeout. Never touches NFS."""
    raw = os.environ.get("IMA_PULL_URL", "").strip()
    if not raw:
        return {"configured": False, "ok": False, "status": "unconfigured", "circuit_open": _arm_circuit.is_open()}
    health = raw[:-5] + "/healthz" if raw.endswith("/pull") else raw.rstrip("/") + "/healthz"
    try:
        request = urllib.request.Request(health, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(32).decode("utf-8", "replace").strip()
        ok = response.status == 200 and body.startswith("ok")
        if ok:
            _arm_circuit.success()
        return {
            "configured": True,
            "ok": ok,
            "status": body or str(response.status),
            "circuit_open": _arm_circuit.is_open(),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {
            "configured": True,
            "ok": False,
            "status": type(exc).__name__,
            "circuit_open": _arm_circuit.is_open(),
        }
