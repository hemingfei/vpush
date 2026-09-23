#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隐式账号注册：实现已迁入 app 包（生产链路由 app/fetchers/* 直接调用）。

此处仅做转发，保持 `python scripts/xq_app/*.py` 的老入口不变。
权威实现：app/xq_identity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 仓库根，便于 import app.*

from app.xq_identity import (  # noqa: E402,F401
    API,
    APP_UA,
    APP_VERSION,
    DEFAULT_DEVICE_ID,
    device_id,
    device_id_from_android_id,
    empty_sign,
    identity,
    new_device_id,
    rotate_identity,
    sm4_decrypt_hex,
    sm4_encrypt_hex,
)
from app.xq_identity import register as _register  # noqa: E402


def register(device: str, verbose: bool = False) -> dict:
    """旧脚本会传 verbose=，进度输出改由 logging 控制，这里忽略该参数。"""
    return _register(device)


if __name__ == "__main__":
    device = sys.argv[1] if len(sys.argv) > 1 else device_id()
    out = register(device)
    print(f"device       : {device}")
    print(f"uid          : {out['uid']}")
    print(f"is_new       : {out.get('is_new')}")
    print(f"access_token : {out['access_token']}")
    print(f"cookie       : {out['cookie'][:100]}…")
