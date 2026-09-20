"""115 QR login via p115client. Fail closed if the library is missing.

Never puts cookie bodies in JSON responses or logs. On success the cookie is
written to P115_COOKIES_FILE (mode 0600) and only cookie_len is returned.
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ops_settings import (
    P115_DEVICE_TYPES,
    QR_SESSION_TTL_SECONDS,
    QR_START_LIMIT,
    QR_START_WINDOW_SECONDS,
    cookies_path,
    default_device_type,
)

log = logging.getLogger("arm_lab_ops.qr115")


class QRError(RuntimeError):
    """Safe, user-facing QR error. Message must never include cookies."""


def load_p115_client():
    try:
        from p115client import P115Client
    except ImportError as exc:
        raise QRError("p115client is not installed; QR login is unavailable") from exc
    return P115Client


def normalize_device_type(raw: str | None) -> str:
    value = (raw or default_device_type()).strip().lower()
    if value not in P115_DEVICE_TYPES:
        raise QRError(f"unsupported device type: {value}")
    return value


def _token_data(resp: Any) -> dict[str, Any]:
    if not isinstance(resp, dict):
        raise QRError("QR token response was not a JSON object")
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    uid = data.get("uid")
    if not uid:
        raise QRError("QR token missing uid")
    return {
        "uid": str(uid),
        "time": data.get("time"),
        "sign": data.get("sign"),
    }


def _png_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _qr_png(client_cls, uid: str) -> bytes:
    png = client_cls.login_qrcode(uid)
    if isinstance(png, (bytes, bytearray)) and png:
        return bytes(png)
    raise QRError("QR image was empty")


def _cookie_from_result(resp: Any) -> str:
    if not isinstance(resp, dict):
        raise QRError("QR login result was not a JSON object")
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    cookie = data.get("cookie") if isinstance(data, dict) else None
    if isinstance(cookie, dict):
        parts = [f"{key}={value}" for key, value in cookie.items() if value is not None]
        text = "; ".join(parts).strip()
        if text:
            return text
    if isinstance(cookie, str) and cookie.strip():
        return cookie.strip()
    raise QRError("QR login result had no cookie")


def write_cookies(path: Path, cookie: str) -> int:
    """Atomically write cookie file as 0600. Returns byte length. Never logs body."""
    if not cookie.strip():
        raise QRError("refusing to write empty cookie")
    parent = path.parent
    if not parent.is_dir():
        raise QRError("secrets directory is missing")
    data = cookie.strip().encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=".115-cookies.", dir=str(parent))
    tmp_path = Path(tmp_name)
    try:
        os.write(fd, data)
        os.fchmod(fd, 0o600)
        os.close(fd)
        fd = -1
        os.replace(tmp_path, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise QRError("failed to write cookie file") from exc
    log.info("115 cookie written (%s bytes, mode 0600)", len(data))
    return len(data)


def _status_code(resp: Any) -> int | None:
    if not isinstance(resp, dict):
        return None
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    raw = data.get("status") if isinstance(data, dict) else None
    if raw is None:
        raw = resp.get("status")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@dataclass
class QRManager:
    starts: list[float] = field(default_factory=list)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def _prune(self, now: float) -> None:
        self.starts = [ts for ts in self.starts if now - ts < QR_START_WINDOW_SECONDS]
        expired = [
            sid
            for sid, row in self.sessions.items()
            if now - float(row.get("created", 0)) > QR_SESSION_TTL_SECONDS
        ]
        for sid in expired:
            self.sessions.pop(sid, None)

    def check_rate(self, now: float | None = None) -> None:
        ts = time.time() if now is None else now
        self._prune(ts)
        if len(self.starts) >= QR_START_LIMIT:
            raise QRError("QR start rate limit; wait a minute")

    def start(self, device_type: str | None = None) -> dict[str, Any]:
        now = time.time()
        self.check_rate(now)
        app = normalize_device_type(device_type)
        client_cls = load_p115_client()
        token_resp = client_cls.login_qrcode_token()
        token = _token_data(token_resp)
        png = _qr_png(client_cls, token["uid"])
        sid = secrets.token_urlsafe(16)
        self.starts.append(now)
        self.sessions[sid] = {
            "uid": token["uid"],
            "time": token["time"],
            "sign": token["sign"],
            "app": app,
            "created": now,
            "status": "pending",
            "cookie_len": None,
        }
        log.info("115 QR started session=%s app=%s", sid, app)
        return {
            "ok": True,
            "session_id": sid,
            "device_type": app,
            "qr_png": _png_data_url(png),
            "status": "pending",
        }

    def poll(self, session_id: str) -> dict[str, Any]:
        row = self.sessions.get(session_id)
        if row is None:
            raise QRError("unknown or expired QR session")
        if row.get("status") == "ok":
            return {"ok": True, "status": "ok", "cookie_len": row.get("cookie_len")}

        client_cls = load_p115_client()
        payload = {"uid": row["uid"], "time": row["time"], "sign": row["sign"]}
        status_resp = client_cls.login_qrcode_scan_status(payload)
        code = _status_code(status_resp)
        if code in (None, 0):
            row["status"] = "pending"
            return {"ok": True, "status": "pending"}
        if code == 1:
            row["status"] = "scanned"
            return {"ok": True, "status": "scanned"}
        if code in (-1,):
            row["status"] = "cancelled"
            return {"ok": False, "status": "cancelled"}
        if code in (-2,):
            row["status"] = "expired"
            return {"ok": False, "status": "expired"}
        if code != 2:
            row["status"] = "error"
            return {"ok": False, "status": "error"}

        result = client_cls.login_qrcode_scan_result({"account": row["uid"], "app": row["app"]})
        cookie = _cookie_from_result(result)
        length = write_cookies(cookies_path(), cookie)
        del cookie
        row["status"] = "ok"
        row["cookie_len"] = length
        row.pop("uid", None)
        row.pop("time", None)
        row.pop("sign", None)
        log.info("115 QR success session=%s cookie_len=%s", session_id, length)
        return {"ok": True, "status": "ok", "cookie_len": length}
