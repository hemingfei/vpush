"""MX 人形时间抖动：把「请求足迹对齐」补成「到达时间也对齐」。

官方网页端的启动请求被页面渲染/JS 初始化天然拉开几百毫秒到一两秒，vpush
的启动序列此前是零间隔背靠背连发——请求集合与官方一致、时间纹理却是机器
的。这里给低频请求链补上同量级的随机间隔。

只用于启动序列/房间同步/进房拉取等低频路径，绝不加在 WS 消息链路上。
测试环境由 tests/conftest.py 统一置 VPUSH_MX_JITTER=0 关闭，避免拖慢全量
回归；抖动行为本身由专门的用例显式开启验证。
"""
from __future__ import annotations

import os
import random
import time

# kind → (下限秒, 上限秒)
JITTER_RANGES: dict[str, tuple[float, float]] = {
    # 冷启动序列相邻只读请求之间（页面 JS 初始化天然拉开的量级）
    "boot_step": (0.15, 1.2),
    # 启动序列 → 房间列表 → 连 WS 三个阶段之间（页面加载/应用初始化）
    "phase": (0.4, 1.6),
    # 进房上报 → 拉历史消息之间（房间页挂载时两个 XHR 近乎同时，间隔很小）
    "room_open": (0.05, 0.45),
}


def jitter_enabled() -> bool:
    return os.environ.get("VPUSH_MX_JITTER", "1").strip().lower() not in (
        "0", "false", "no", "",
    )


def human_delay(kind: str) -> float:
    """返回 kind 的人形随机间隔秒数；抖动关闭时恒 0。"""
    lo, hi = JITTER_RANGES[kind]
    return random.uniform(lo, hi) if jitter_enabled() else 0.0


def human_pause(kind: str) -> None:
    """阻塞一个 kind 的随机间隔（供已在线程池里跑的调用方使用）。"""
    delay = human_delay(kind)
    if delay > 0:
        time.sleep(delay)
