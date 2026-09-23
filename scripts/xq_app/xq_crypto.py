#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""国密原语：实现已迁入 app 包（镜像只挂载 app/，运行时需要它）。

此处仅做转发，保持 `python scripts/xq_app/*.py` 的老入口不变。
权威实现：app/xq_crypto.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 仓库根，便于 import app.*

from app.xq_crypto import *  # noqa: E402,F401,F403
