"""行为器切房间节奏：间隔/抖动/目标选择（票 #17 交付物 ③）。

语义搬运源（票 #17「不重写」红线；原数值出处见下述历史，常量现落地本模块）：
- 间隔 5-10 分钟：ACTIVITY_INTERVAL_RANGE = (300.0, 600.0)（用户口径），
  采样方式 random.uniform——数值原出处 app/services/mx_activity.py:36
  （云端行为模拟已随 ADR-0001 分层删除退役，常量随语义搬运至此，
  数值单一来源随迁移）；
- 会话开启即武装：首次点击落在一个随机间隔后（原 mx_activity.py:62——启动
  序列本身已是官方冷启动足迹，紧跟着就点房间反而不像「打开页面先看一眼」）；
- 排除上一个房间（原 mx_activity.py:72-83 _pick_room 的 fresh or kols 语义）；
- 点击后记录最后打开的房间（settings 键 mx_last_room 的本地等价——由
  AccountRegistry.set_last_room 承接，每账号互不串号）。

本地 agent 与原云端行为模拟的差异只有执行面：云端 fetcher.fetch 发
HTTP 三连，本地 CDP 真点击（浏览器自己发请求）——节奏决策在此，动作执行
在 executor。
"""
from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence

# 点房间的间隔秒数（随机区间）：用户口径 5-10 分钟。真人盯盘时每几分钟切
# 一次房间是常态，量级为每小时个位数请求，远低于任何攻击性频率。
# （历史：原为 app/services/mx_activity.py:36，随 ADR-0001 分层删除搬迁至此，
#  tests/test_agent_cadence.py 与 scripts/mx_agent_validate.py 锁定该数值。）
ACTIVITY_INTERVAL_RANGE = (300.0, 600.0)


class RoomCadence:
    """切房间节奏状态机：到点（maybe_due/advance）由调用方 tick 驱动。

    与原云端 MXRoomActivity 相比去掉了 session_active/ws_connected 闸门——
    本地 agent 的窗口循环天然保证「只在窗口内且登录在线时 tick」，
    闸门重复属于云端调度器的历史包袱（那里会话与窗口分属两个子系统）。
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """clock 注入测试锚点；生产用 time.monotonic（与原 mx_activity 同源）。"""
        self._clock = clock
        # 会话开启即武装：首次点击落在一个随机间隔之后
        self._armed_at = self._clock() + self.next_interval_seconds()

    @staticmethod
    def interval_range() -> tuple[float, float]:
        """间隔区间——本模块常量，数值语义单一来源。"""
        return ACTIVITY_INTERVAL_RANGE

    @staticmethod
    def next_interval_seconds() -> float:
        """下一次切房间间隔（random.uniform 采样，与原 mx_activity._interval 同式）。"""
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
    """随机挑一个房间，排除上一个（原 mx_activity._pick_room 语义照搬）。

    fresh（排除上一个）空时回卷全部候选：单人房间池也能持续工作；
    rooms 空返回 None（调用方顺延节奏不硬点，原 mx_activity.py:121 同语义）。
    """
    if not rooms:
        return None
    fresh = [r for r in rooms if r != last_room]
    return rng.choice(fresh or list(rooms))
