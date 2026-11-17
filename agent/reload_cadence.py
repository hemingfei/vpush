"""行为器周期页面刷新节奏（票 #23 防线一）。

背景（2026-11-17 断流 4.3h 实锤）：页面自己的 WS 死亡且页面 JS 无自愈
重连——token 全程有效，reload 即重建会话（平台官方「关窗重开自动登录」
同机制）。本节奏让 agent 每隔随机 50-90 分钟 reload 一次页面，作为
扩展侧静默看门狗（ws_watchdog，3-10 分钟阈值）之外的第二道防线：
看门狗精准快（分钟级）但依赖扩展存活；周期 reload 慢而确定——两道
防线独立失效。

结构照搬 RoomCadence（agent/cadence.py 同惯用法）：到点（due/advance）
由调用方 30s tick 驱动，random.uniform 采样。刷新后页面回大厅态，
当前房间采集断，下次切房点击（RoomCadence ≤6min）自动恢复轮转——
代价可接受（用户口径拍板）。

拟人化：人盯盘时 50-90 分钟刷新一次页面是常态行为，与切房节奏
（5-10min）同哲学；reload 的自愈节奏本身不可预测。
"""
from __future__ import annotations

import random
import time
from collections.abc import Callable

# 周期刷新间隔秒数（随机区间）：用户口径 50-90 分钟。
RELOAD_INTERVAL_RANGE = (3000.0, 5400.0)


class ReloadCadence:
    """页面刷新节奏状态机：到点由调用方 tick 驱动（RoomCadence 同构）。

    窗口关闭（runtime 收尸）时调用方重置（构造新实例或 reset）——
    新窗口的首次刷新落在一个随机间隔后，不开窗即到点的假到期。
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """clock 注入测试锚点；生产用 time.monotonic（与 RoomCadence 同源）。"""
        self._clock = clock
        self._armed_at = self._clock() + self.next_interval_seconds()

    @staticmethod
    def interval_range() -> tuple[float, float]:
        """间隔区间——本模块常量，数值语义单一来源。"""
        return RELOAD_INTERVAL_RANGE

    @staticmethod
    def next_interval_seconds() -> float:
        """下一次刷新间隔（random.uniform 采样，与 RoomCadence 同式）。"""
        return random.uniform(*RELOAD_INTERVAL_RANGE)

    def due(self) -> bool:
        """是否已到下一次刷新时刻。"""
        return self._clock() >= self._armed_at

    def advance(self) -> None:
        """消费一次到期：重新武装到下一个随机间隔后。"""
        self._armed_at = self._clock() + self.next_interval_seconds()

    def next_fire_in(self) -> float:
        """距下次刷新还剩多少秒（日志/观测用）。"""
        return max(0.0, self._armed_at - self._clock())
