"""行为器周期页面刷新节奏测试（票 #23 防线一）。

语义契约：间隔随机 50-90 分钟（用户口径）、会话开启即武装、due/advance
消费语义与 RoomCadence 同构；AgentRunner 开窗重置节奏（新窗口首次刷新
落在随机间隔后）、到点调用 runtime.reload_page 并记 lifecycle 事件。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent.reload_cadence import RELOAD_INTERVAL_RANGE, ReloadCadence
from agent.runner import AgentRunner


# ---- 间隔与抖动 ----

def test_interval_range_is_50_to_90_minutes():
    """间隔常量为 3000-5400 秒（用户口径 50-90 分钟，常量锁定）。"""
    assert RELOAD_INTERVAL_RANGE == (3000.0, 5400.0)
    assert ReloadCadence.interval_range() == RELOAD_INTERVAL_RANGE


def test_next_fire_sampled_within_range():
    """每次取的间隔落在 [3000, 5400) 内——分布锁定，不重新发明数值。"""
    cadence = ReloadCadence()
    for _ in range(200):
        lo, hi = ReloadCadence.interval_range()
        assert lo <= cadence.next_interval_seconds() < hi


def test_arms_first_reload_after_random_interval():
    """会话开启即武装：首次刷新落在一个随机间隔之后（不开窗即到点）。"""
    lo, hi = ReloadCadence.interval_range()
    for _ in range(50):
        cadence = ReloadCadence(clock=lambda: 100.0)
        assert cadence.next_fire_in() >= lo
        assert cadence.next_fire_in() < hi
        assert not cadence.due()


def test_due_and_advance():
    """到期 → due()=True；advance() 消费后重新武装随机间隔。"""
    tick = {"t": 100.0}
    cadence = ReloadCadence(clock=lambda: tick["t"])
    assert not cadence.due()
    _lo, hi = ReloadCadence.interval_range()
    tick["t"] = 100.0 + hi + 1.0  # 越过区间上界：任意采样必然已到期
    assert cadence.due()
    cadence.advance()
    assert not cadence.due()
    tick["t"] += hi + 1.0
    assert cadence.due()


# ---- runner 接线 ----

def _make_runner(tmp_path: Path) -> AgentRunner:
    """最小可用 runner：写盘日志 + 单账号。"""
    from agent.config import AgentConfig
    from agent.lifecycle import LifecycleLog

    cfg = AgentConfig(
        accounts=[type("Acc", (), {"user": "u1", "password": "p", "role": "primary"})()],
        always_on=True,
    )
    cfg.data_dir = tmp_path
    return AgentRunner(cfg, log=LifecycleLog(tmp_path / "lifecycle.jsonl"))


def test_tick_calls_reload_when_due(tmp_path, monkeypatch):
    """开窗期到点：runtime.reload_page 被调用 + lifecycle 记 page_reload。"""
    runner = _make_runner(tmp_path)

    class FakeRuntime:
        reloaded = 0

        async def reload_page(self):
            FakeRuntime.reloaded += 1

    runner.runtime = FakeRuntime()
    runner.runner._open = True
    # 越过区间上界：任意采样必然已到期
    runner.reload_cadence._armed_at = runner.reload_cadence._clock() - 1.0

    asyncio.run(runner._maybe_reload_page())
    assert FakeRuntime.reloaded == 1
    events = [
        json.loads(line)
        for line in (tmp_path / "lifecycle.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert events[-1]["kind"] == "page_reload"
    assert "周期刷新完成" in events[-1]["detail"]
    # 消费后重新武装：未到点不重复刷
    assert not runner.reload_cadence.due()


def test_tick_skips_reload_when_not_due(tmp_path):
    """未到点：不调用 reload（随机间隔内零开销）。"""
    runner = _make_runner(tmp_path)

    class FakeRuntime:
        reloaded = 0

        async def reload_page(self):
            FakeRuntime.reloaded += 1

    runner.runtime = FakeRuntime()
    runner.runner._open = True
    asyncio.run(runner._maybe_reload_page())
    assert FakeRuntime.reloaded == 0


def test_reload_failure_defers_not_raises(tmp_path):
    """reload 抛异常：记失败事件顺延节奏，不炸 tick 主循环。"""
    runner = _make_runner(tmp_path)

    class FakeRuntime:
        async def reload_page(self):
            raise RuntimeError("page gone")

    runner.runtime = FakeRuntime()
    runner.reload_cadence._armed_at = runner.reload_cadence._clock() - 1.0
    asyncio.run(runner._maybe_reload_page())  # 不抛
    events = [
        json.loads(line)
        for line in (tmp_path / "lifecycle.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert events[-1]["kind"] == "page_reload"
    assert "刷新失败" in events[-1]["detail"]
    assert not runner.reload_cadence.due()  # 已消费：失败也顺延
