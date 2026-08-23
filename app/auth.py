"""认证：PBKDF2 密码哈希 + HMAC 签名 token（无第三方依赖）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time

TOKEN_TTL_SECONDS = 30 * 24 * 3600
USERNAME_MIN_LEN = 6
USERNAME_MAX_LEN = 30
# 登录名不是展示名：禁止空格、引号、符号和 emoji。机器人自动建号不走这条。
_USERNAME_RE = re.compile(r"^[A-Za-z\u4e00-\u9fff][A-Za-z0-9_\-\u4e00-\u9fff]{5,29}$")
USERNAME_CHARSET_MSG = "用户名仅限中文、字母、数字、下划线和连字符，须以中文或字母开头"


def validate_username(username: str) -> str:
    """规范化并校验网页注册 / 管理员改名用的用户名。非法则 ValueError。"""
    name = (username or "").strip()
    if len(name) < USERNAME_MIN_LEN:
        raise ValueError("用户名至少6位")
    if len(name) > USERNAME_MAX_LEN:
        raise ValueError("用户名最长30位")
    if not _USERNAME_RE.fullmatch(name):
        raise ValueError(USERNAME_CHARSET_MSG)
    return name


def is_valid_username(username: str) -> bool:
    try:
        validate_username(username)
        return True
    except ValueError:
        return False

def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 200_000
    ).hex()
    return f"{salt}${digest}"


# 用户不存在时也执行一次同样的哈希校验，避免通过响应时间探测用户名是否存在
DUMMY_HASH = hash_password("__dummy__")


def verify_password(password: str, stored: str) -> bool:
    try:
        salt = stored.split("$", 1)[0]
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(user_id: int, username: str, secret: str, token_version: int = 0) -> str:
    payload = {
        "uid": user_id,
        "name": username,
        "ver": int(token_version),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str, secret: str) -> dict | None:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


def get_or_create_secret(db, configured: str = "") -> str:
    """token 密钥：优先用配置，否则在 DB 里持久化一个随机密钥。"""
    if configured:
        return configured
    key = "token_secret"
    secret = db.get_setting(key)
    if not secret:
        secret = os.urandom(32).hex()
        db.set_setting(key, secret)
    return secret
