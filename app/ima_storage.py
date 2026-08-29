"""Host-generated IMA archive storage status reader."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

_REASON_ALLOWLIST = frozenset({
    "",
    "missing",
    "invalid",
    "stale",
    "unavailable",
    "readonly",
    "capacity",
})
_FUTURE_SKEW_SECONDS = 300
BACKUP_REQUEST_WINDOW = 3600


def write_request_file(path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(int(time.time())), encoding="utf-8")
    try:
        os.chmod(target, 0o640)
    except OSError:
        pass


def request_pending(path: str | Path, last_success: object, *, window: int = BACKUP_REQUEST_WINDOW) -> bool:
    target = Path(path)
    if not target.is_file():
        return False
    requested = int(target.stat().st_mtime)
    return requested > int(last_success or 0) and (int(time.time()) - requested) < window


def _clamp_percent(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def _clamp_bytes(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(0, number)


class ImaStorageStatus:
    STALE_SECONDS = 180

    def __init__(self, path: str | Path | None, *, remote: bool):
        self.path = Path(path) if path else None
        self.remote = remote

    def load(self) -> dict[str, object]:
        if not self.remote:
            return {
                "status": "local",
                "available": True,
                "writable": True,
                "checked_at": 0,
                "used_percent": 0,
                "inode_percent": 0,
                "monthly_tx_bytes": 0,
                "reason": "",
                "capacity_blocked": False,
            }

        if self.path is None or not self.path.is_file():
            return self._unavailable("missing")

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return self._unavailable("invalid")

        if not isinstance(raw, dict):
            return self._unavailable("invalid")

        checked_at = raw.get("checked_at")
        if isinstance(checked_at, bool) or not isinstance(checked_at, (int, float)):
            return self._unavailable("invalid")
        checked_at = int(checked_at)

        available = raw.get("available")
        writable = raw.get("writable")
        capacity_blocked = raw.get("capacity_blocked")
        if not isinstance(available, bool) or not isinstance(writable, bool) or not isinstance(capacity_blocked, bool):
            return self._unavailable("invalid")

        now = int(time.time())
        if checked_at > now + _FUTURE_SKEW_SECONDS:
            return self._unavailable("invalid", checked_at=checked_at)
        if now - checked_at > self.STALE_SECONDS:
            return self._unavailable(
                "stale",
                checked_at=checked_at,
                used_percent=raw.get("used_percent"),
                inode_percent=raw.get("inode_percent"),
                monthly_tx_bytes=raw.get("monthly_tx_bytes"),
            )

        used_percent = _clamp_percent(raw.get("used_percent"))
        inode_percent = _clamp_percent(raw.get("inode_percent"))
        monthly_tx_bytes = _clamp_bytes(raw.get("monthly_tx_bytes"))

        if not available:
            return {
                "status": "unavailable",
                "available": False,
                "writable": writable,
                "checked_at": checked_at,
                "used_percent": used_percent,
                "inode_percent": inode_percent,
                "monthly_tx_bytes": monthly_tx_bytes,
                "reason": "unavailable",
                "capacity_blocked": capacity_blocked,
            }

        if capacity_blocked:
            return {
                "status": "capacity_blocked",
                "available": True,
                "writable": writable,
                "checked_at": checked_at,
                "used_percent": used_percent,
                "inode_percent": inode_percent,
                "monthly_tx_bytes": monthly_tx_bytes,
                "reason": "capacity",
                "capacity_blocked": True,
            }

        if not writable:
            return {
                "status": "readonly",
                "available": True,
                "writable": False,
                "checked_at": checked_at,
                "used_percent": used_percent,
                "inode_percent": inode_percent,
                "monthly_tx_bytes": monthly_tx_bytes,
                "reason": "readonly",
                "capacity_blocked": False,
            }

        reason = raw.get("reason", "")
        if not isinstance(reason, str) or reason not in _REASON_ALLOWLIST:
            reason = ""

        return {
            "status": "available",
            "available": True,
            "writable": True,
            "checked_at": checked_at,
            "used_percent": used_percent,
            "inode_percent": inode_percent,
            "monthly_tx_bytes": monthly_tx_bytes,
            "reason": reason,
            "capacity_blocked": False,
            "restic_last_success": _clamp_bytes(raw.get("restic_last_success", 0)),
            "restic_last_check_at": _clamp_bytes(raw.get("restic_last_check_at", 0)),
            "restic_last_check_ok": raw.get("restic_last_check_ok") is True,
        }

    def can_read(self) -> bool:
        data = self.load()
        return data.get("available") is True

    def can_write(self) -> bool:
        data = self.load()
        return (
            data.get("available") is True
            and data.get("writable") is True
            and data.get("capacity_blocked") is False
        )

    def public(self) -> dict[str, object]:
        data = self.load()
        return {
            "status": data["status"],
            "available": data["available"],
            "writable": data["writable"],
            "checked_at": data["checked_at"],
            "used_percent": data["used_percent"],
            "inode_percent": data["inode_percent"],
            "monthly_tx_bytes": data["monthly_tx_bytes"],
            "reason": data["reason"],
            "restic_last_success": _clamp_bytes(data.get("restic_last_success", 0)),
            "restic_last_check_at": _clamp_bytes(data.get("restic_last_check_at", 0)),
            "restic_last_check_ok": data.get("restic_last_check_ok") is True,
        }

    def _unavailable(
        self,
        reason: str,
        *,
        checked_at: int = 0,
        used_percent: object = 0,
        inode_percent: object = 0,
        monthly_tx_bytes: object = 0,
    ) -> dict[str, object]:
        status = reason if reason in {"missing", "invalid", "stale"} else "unavailable"
        return {
            "status": status,
            "available": False,
            "writable": False,
            "checked_at": checked_at,
            "used_percent": _clamp_percent(used_percent),
            "inode_percent": _clamp_percent(inode_percent),
            "monthly_tx_bytes": _clamp_bytes(monthly_tx_bytes),
            "reason": reason if reason in _REASON_ALLOWLIST else "invalid",
            "capacity_blocked": False,
        }
