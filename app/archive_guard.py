"""Keep vpush up when a remote archive host dies.

Hard NFS on the production host is what dragged DMIT down with the
storage box: any ``stat`` / ``open`` / ``resolve`` on a hung mount
goes D-state and cannot be killed. ARM is the collection + HTTP
front; production must never kernel-mount ARM or storage.

This module only reads ``/proc/mounts`` (or a test string). It never
touches the archive path.
"""

from __future__ import annotations

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


def archive_fetch_url() -> str:
    explicit = os.environ.get("IMA_FETCH_URL", "").strip()
    if explicit:
        return explicit
    pull = os.environ.get("IMA_PULL_URL", "").strip()
    if pull.endswith("/pull"):
        return pull[: -len("/pull")] + "/file"
    return ""


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
    lower = dest.lower()
    if not (lower.endswith(".pdf") or lower.endswith(".txt")):
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
