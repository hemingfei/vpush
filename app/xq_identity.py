#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雪球 App 隐式账号身份通道：用 App 域名路径 + App token 取代网页 cookie/WAF 解算。

为什么需要（详见 docs/handoff/2026-09-23-xueqiu-app-identity-channel.md）：
    · WAF 按「域名+路径」分级：xueqiu.com/statuses/* 触发阿里云挑战，
      api.xueqiu.com/v4/statuses/* 不触发（同 IP 同期实测 40 QPS 全挑战 vs 201 QPS 全通）
    · App 首启自动注册隐式账号（JWT uid ≠ -1），其 token 能访问网页匿名访问不了的数据
    · token 与 UA 强绑定：必须成对使用 "Xueqiu Android <版本>"，混用必被拒
      （表现为 403 Seek IP Blacklisted / error_code 10022 / 400016）

注册链路（逆向自 com.xueqiu.user.account.SNBAccountClient / com.xueqiu.enc）：
    ① POST /ee2e/public_key.json  上送本地 SM2 公钥（明文 JSON）→ 服务端返回公钥
    ② sm4Key = SM3(ECDH(本地私钥, 服务端公钥).X 大写hex)[前16字节]
    ③ SM4/CBC/PKCS7 加密注册表单（key 同时作 IV），请求体为**大写 hex**（不是 Base64）
    ④ POST /uc_passport/provider/oauth/app_anonymous_id（头 isenc: 1）→ SM4 密文解密得 token

注册幂等：同一 deviceId 反复注册返回同一 uid 与同一 access_token。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from typing import Any

from curl_cffi import requests as cffi
from gmssl import sm4

from .xq_crypto import (
    decode_public_key,
    derive_sm4_key,
    ecdh_shared_hex,
    encode_public_key,
    generate_keypair,
)

logger = logging.getLogger(__name__)

APP_UA = "Xueqiu Android 14.96.3"
# 网页路径用的 UA：必须与实际指纹（curl_cffi impersonate="chrome124"）一致
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
API = "https://api.xueqiu.com"
APP_VERSION = "14.96.3"
APP_CLIENT_ID = "JtXbaMn7eP"  # com.xueqiu.android.base.Constants
APP_CLIENT_SECRET = "txsDfr9FphRSPov5oQou74"  # 逆向自 APK 客户端内置常量，非本服务凭据
SIGN_SECRET = "2ee0b0d606aa1e845fb9537251db0785"  # gj/a.java，同上（客户端内置签名盐）

# 身份开关：默认走 App 通道；设 0 退回旧的网页 cookie 路径（部署级回滚开关）
ENABLED_ENV = "XUEQIU_APP_IDENTITY"
# 设备指纹覆盖：需要强制换新隐式账号时设置（否则用固定常量，长期复用同一账号）
DEVICE_ID_ENV = "XUEQIU_DEVICE_ID"
# 隐式账号身份失效时的换新节流：避免在持续失败下不断注册新账号
ROTATE_COOLDOWN = 600

DEFAULT_DEVICE_ID = "1ONEPLUS" + hashlib.md5(b"vpush-xueqiu-app").hexdigest()

_lock = threading.Lock()
_identity: dict | None = None
_last_rotate = 0.0


def enabled() -> bool:
    """App 身份通道是否启用（env 覆盖，默认启用）。"""
    return (os.environ.get(ENABLED_ENV) or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def device_id_from_android_id(manufacturer: str, android_id: str) -> str:
    """按 SharedIdCacheStorage 的公式构造设备指纹（1 + 厂商 + md5(androidId)）。"""
    return "1" + manufacturer.upper().replace(".", "") + hashlib.md5(
        android_id.encode()
    ).hexdigest()


def device_id() -> str:
    """当前使用的设备指纹：env 覆盖优先，否则固定常量（同 deviceId 幂等复用同一账号）。"""
    return (os.environ.get(DEVICE_ID_ENV) or "").strip() or DEFAULT_DEVICE_ID


def new_device_id() -> str:
    """换新设备指纹 → 换新隐式账号（仅旧身份被服务端拒绝时使用）。"""
    return device_id_from_android_id("OnePlus", uuid.uuid4().hex)


def empty_sign() -> str:
    """空参数的 _s（真机注册请求里也是 9667ca）。"""
    return hashlib.sha1(f"_secretkey={SIGN_SECRET}".encode()).hexdigest()[-6:]


def sm4_encrypt_hex(key_hex: str, data: bytes) -> str:
    key = bytes.fromhex(key_hex)
    cipher = sm4.CryptSM4()
    cipher.set_key(key, sm4.SM4_ENCRYPT)
    return cipher.crypt_cbc(key, data).hex().upper()


def sm4_decrypt_hex(key_hex: str, cipher_hex: str) -> bytes:
    key = bytes.fromhex(key_hex)
    cipher = sm4.CryptSM4()
    cipher.set_key(key, sm4.SM4_DECRYPT)
    return cipher.crypt_cbc(key, bytes.fromhex(cipher_hex))


def _headers(device: str) -> dict:
    return {
        "User-Agent": APP_UA,
        "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.6,zh;q=0.4",
        "X-Device-ID": device,
        "X-Device-Model-Name": "OnePlus_PJD110",
        "X-Device-OS": "Android 16",
        "Cookie": "xq_a_token=;xq_id_token=;u=0;session_id=;xid=0",
    }


def _negotiate(session: cffi.Session, device: str) -> str:
    """步骤 ① ②：密钥协商 → sm4Key。"""
    d, q = generate_keypair()
    params = {"_t": f"{device}.0.0.{int(time.time() * 1000)}", "_s": empty_sign()}
    resp = session.post(
        f"{API}/ee2e/public_key.json",
        params=params,
        json={"public_key": encode_public_key(q)},
        headers={**_headers(device), "Content-Type": "application/json;charset=UTF-8"},
        timeout=25,
    )
    payload: Any = resp.json()
    data = payload.get("data") or {}
    if not data.get("public_key"):
        raise RuntimeError(f"雪球密钥协商失败: {payload}")
    return derive_sm4_key(ecdh_shared_hex(d, decode_public_key(data["public_key"])))


def register(device: str) -> dict:
    """注册隐式账号，返回 {access_token, refresh_token, uid, id_token, cookie, device_id}。"""
    session = cffi.Session(impersonate="chrome")
    sm4_key = _negotiate(session, device)
    form = {
        "client_id": APP_CLIENT_ID,
        "client_secret": APP_CLIENT_SECRET,
        "sid": device,
        "timestamp": str(int(time.time() * 1000)),
        "type": "1",
        "version": APP_VERSION,
        "nonce_str": str(uuid.uuid4()),
    }
    body = "&".join(f"{k}={v}" for k, v in form.items())
    cipher_hex = sm4_encrypt_hex(sm4_key, body.encode())

    params = {"_t": f"{device}.0.0.{int(time.time() * 1000)}", "_s": empty_sign()}
    resp = session.post(
        f"{API}/uc_passport/provider/oauth/app_anonymous_id",
        params=params,
        data=cipher_hex,
        headers={
            **_headers(device),
            "isenc": "1",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
        timeout=25,
    )
    payload = resp.json()
    if payload.get("result_code") != 0:
        raise RuntimeError(f"雪球隐式账号注册失败: {payload}")

    result = json.loads(sm4_decrypt_hex(sm4_key, payload["data"]))
    result["cookie"] = (
        f"xq_a_token={result['access_token']};"
        f"xq_id_token={result['id_token']};u={result['uid']}"
    )
    result["device_id"] = device
    return result


def identity() -> dict:
    """当前 App 身份（进程内缓存）。首次调用会注册隐式账号，失败时抛异常由调用方降级。"""
    global _identity
    with _lock:
        if _identity is None:
            _identity = register(device_id())
            logger.info(
                "雪球 App 隐式账号就绪: uid=%s device=%s",
                _identity.get("uid"),
                _identity.get("device_id"),
            )
        return _identity


def rotate_identity() -> dict:
    """身份被服务端拒绝时换新设备指纹重新注册（ROTATE_COOLDOWN 内不重复换，避免刷账号）。"""
    global _identity, _last_rotate
    with _lock:
        now = time.time()
        if now - _last_rotate < ROTATE_COOLDOWN:
            raise RuntimeError("雪球 App 身份刚轮换过，暂不重复注册")
        _identity = register(new_device_id())
        _last_rotate = now
        logger.warning(
            "雪球 App 身份已轮换: uid=%s device=%s",
            _identity.get("uid"),
            _identity.get("device_id"),
        )
        return _identity


if __name__ == "__main__":
    # 冒烟：注册/复用隐式账号并打印身份（容器内可直接 python -m app.xq_identity）
    me = identity()
    print(f"uid={me['uid']} device={me['device_id']}")
    print(f"cookie={me['cookie'][:80]}…")
