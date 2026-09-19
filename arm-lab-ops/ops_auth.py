"""HttpOnly session cookie + lab password. Never logs the password."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from pathlib import Path

from ops_settings import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    env_str,
    password_file,
)

COOKIE_KWARGS = {
    "key": SESSION_COOKIE,
    "httponly": True,
    "samesite": "lax",
    "path": "/",
}


def load_password() -> str:
    """Password from ARM_OPS_PASSWORD or the secrets file. Empty if unset."""
    env = os.environ.get("ARM_OPS_PASSWORD")
    if env:
        return env.rstrip("\n")
    path = password_file()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not text:
        return ""
    return text.splitlines()[0]


def password_configured() -> bool:
    return bool(load_password())


def verify_password(provided: str) -> bool:
    expected = load_password()
    if not expected:
        return False
    left = hashlib.sha256(provided.encode("utf-8")).digest()
    right = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(left, right)


def _session_secret() -> bytes:
    """Derive HMAC key from password + optional ARM_OPS_SESSION_SECRET."""
    extra = env_str("ARM_OPS_SESSION_SECRET", "")
    material = f"{load_password()}\0{extra}".encode("utf-8")
    return hashlib.sha256(material).digest()


def issue_session(now: int | None = None) -> str:
    exp = int(now if now is not None else time.time()) + SESSION_TTL_SECONDS
    body = str(exp)
    sig = hmac.new(_session_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"v1.{body}.{sig}"


def session_ok(token: str | None) -> bool:
    if not token or not password_configured():
        return False
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        return False
    _ver, body, sig = parts
    if not body.isdigit():
        return False
    expected = hmac.new(_session_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False
    return int(body) >= int(time.time())


def cookie_path_hint() -> Path:
    return password_file()
