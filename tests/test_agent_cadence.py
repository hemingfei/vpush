"""行为器切房间节奏的纯逻辑测试（票 #17 交付物 ③）。

语义红线（票 #17 交付物 3）：间隔与抖动自原 app/services/mx_activity
搬运，不重写——ACTIVITY_INTERVAL_RANGE = (300.0, 600.0)「用户口径 5-10 分钟」
（原云端模块已随 ADR-0001 分层删除退役，常量现落地 agent.cadence）、
「排除上一个房间」、「会话开启即武装、首次点击落在随机间隔后」；房间点击后
记录「最后打开的房间」（本地等价云端 settings 键 mx_last_room）。

本地 agent 与原云端行为模拟的差异只有执行面：云端发 HTTP 三连，本地
CDP 真点击（浏览器自己发请求）——选择目标/间隔/排除上一个/最后房间记录
语义照搬（原 mx_activity.py:72-83 的 _pick_room、:62 的武装语义）。
"""
from __future__ import annotations

import random

from agent.cadence import ACTIVITY_INTERVAL_RANGE, RoomCadence, pick_room

ROOMS = ["格兰投研888", "妖股刺客", "姆爷的守护", "老樊"]


# ---- 间隔与抖动 ----

def test_interval_range_is_5_to_10_minutes():
    """间隔常量为 300-600 秒（用户口径 5-10 分钟，搬运红线锁定数值）。"""
    assert ACTIVITY_INTERVAL_RANGE == (300.0, 600.0)
    assert RoomCadence.interval_range() == ACTIVITY_INTERVAL_RANGE


def test_next_fire_sampled_within_range():
    """每次取的间隔落在 [300, 600) 内——分布搬运，不重新发明数值。"""
    cadence = RoomCadence()
    for _ in range(200):
        lo, hi = RoomCadence.interval_range()
        assert lo <= cadence.next_interval_seconds() < hi


def test_arms_first_click_after_random_interval():
    """会话开启即武装：首次点击落在一个随机间隔之后（原 mx_activity.py:62
    「启动序列本身已是官方冷启动足迹，紧跟着就点房间反而不像」）。"""
    lo, hi = RoomCadence.interval_range()
    for _ in range(50):
        # 假时钟恒为 100.0：武装时刻 = 100 + 随机间隔 ∈ [100+300, 100+600)
        cadence = RoomCadence(clock=lambda: 100.0)
        assert cadence.next_fire_in() >= lo
        assert cadence.next_fire_in() < hi
        assert not cadence.due()  # 间隔未到


def test_due_and_advance():
    """到期 → due()=True；advance() 消费后重新武装随机间隔。"""
    tick = {"t": 100.0}
    cadence = RoomCadence(clock=lambda: tick["t"])
    assert not cadence.due()  # 武装时刻之后必然先有间隔
    _lo, hi = RoomCadence.interval_range()
    tick["t"] = 100.0 + hi + 1.0  # 越过区间上界：任意采样必然已到期
    assert cadence.due()
    cadence.advance()  # 消费这次到期：新的随机间隔重新武装
    assert not cadence.due()
    tick["t"] += hi + 1.0
    assert cadence.due()


# ---- 目标选择：排除上一个 ----

def test_pick_room_excludes_last_room():
    """随机挑房间但排除上一个（fresh 空时回卷全部——单人房间池的兜底）。"""
    for _ in range(50):
        room = pick_room(ROOMS, last_room="妖股刺客", rng=random.Random())
        assert room != "妖股刺客"


def test_pick_room_falls_back_when_all_excluded():
    """只有一个房间（排除后为空）：回卷到它（原 mx_activity.fresh or kols 同语义）。"""
    assert pick_room(["唯一房"], last_room="唯一房", rng=random.Random()) == "唯一房"


def test_pick_room_empty_returns_none():
    assert pick_room([], last_room=None, rng=random.Random()) is None


def test_pick_room_covers_all_rooms_when_repeated():
    """多次选择能覆盖全部房间（随机性存在而非恒定首位）。"""
    seen: set[str] = set()
    rng = random.Random(20261114)
    for _ in range(200):
        seen.add(pick_room(ROOMS, last_room=None, rng=rng))
    assert seen == set(ROOMS)
