"""行为器切房间节奏：间隔/抖动/目标选择（票 #17 交付物 ③）。

语义搬运源（mx-behavior-logic.md §2，红线「不重写」）：
- 间隔 5-10 分钟：app/services/mx_activity.py:36 ACTIVITY_INTERVAL_RANGE =
  (300.0, 600.0)（用户口径）；采样方式 random.uniform（mx_activity.py:69-70）；
- 会话开启即武装：首次点击落在一个随机间隔后（mx_activity.py:62——启动
  序列本身已是官方冷启动足迹，紧跟着就点房间反而不像「打开页面先看一眼」）；
- 排除上一个房间（mx_activity.py:72-83 _pick_room 的 fresh or kols 语义）；
- 点击后记录最后打开的房间（settings 键 mx_last_room 的本地等价——由
  AccountRegistry.set_last_room 承接，每账号互不串号）。

本地 agent 与云端 mx_activity 的差异只有执行面：云端 fetcher.fetch 发
HTTP 三连，本地 CDP 真点击（浏览器自己发请求）——节奏决策在此，动作执行
在 executor。
"""
from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence

from app.services.mx_activity import ACTIVITY_INTERVAL_RANGE


class RoomCadence:
    """切房间节奏状态机：到点（maybe_due/advance）由调用方 tick 驱动。

    与云端 MXRoomActivity 相比去掉了 session_active/ws_connected 闸门——
    本地 agent 的窗口循环天然保证「只在窗口内且登录在线时 tick」，
    闸门重复属于云端调度器的历史包袱（那里会话与窗口分属两个子系统）。
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """clock 注入测试锚点；生产用 time.monotonic（与 mx_activity 同源）。"""
        self._clock = clock
        # 会话开启即武装：首次点击落在一个随机间隔之后
        self._armed_at = self._clock() + self.next_interval_seconds()

    @staticmethod
    def interval_range() -> tuple[float, float]:
        """间隔区间——直接引用 mx_activity 常量，数值语义单一来源。"""
        return ACTIVITY_INTERVAL_RANGE

    @staticmethod
    def next_interval_seconds() -> float:
        """下一次切房间间隔（random.uniform 采样，与 mx_activity._interval 同式）。"""
        return random.uniform(*ACTIVITY_INTERVAL_RANGE)

    def due(self) -> bool:
        """是否已到下一次切房间时刻。"""
        return self._clock() >= self._armed_at

    def advance(self) -> None:
        """消费一次到期：重新武装到下一个随机间隔后。"""
        self._armed_at = self._clock() + self.next_interval_seconds()

    def next_fire_in(self) -> float:
        """距下次切房还剩多少秒（日志/观测用）。"""
        return max(0.0, self._armed_at - self._clock())


def pick_room(
    rooms: Sequence[str],
    *,
    last_room: str | None,
    rng: random.Random,
) -> str | None:
    """随机挑一个房间，排除上一个（mx_activity._pick_room 语义照搬）。

    fresh（排除上一个）空时回卷全部候选：单人房间池也能持续工作；
    rooms 空返回 None（调用方顺延节奏不硬点，mx_activity.py:121 同语义）。
    """
    if not rooms:
        return None
    fresh = [r for r in rooms if r != last_room]
    return rng.choice(fresh or list(rooms))
