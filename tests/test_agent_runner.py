"""AgentRunner 离线冒烟测试：tick 驱动全链路决策，浏览器动作用桩替换。

票 #17 交付物 ⑧（运行入口）的可测面：常驻循环骨架把窗口决策/当日计划/
接力/登录节奏/切房节奏粘合——桩掉 BrowserRuntime 后全链路离线可驱动
（真浏览器链路不入 CI，spec 裁定；这里验证的是「粘合正确」）。
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime

import pytest

from agent.config import AgentConfig
from agent.lifecycle import LifecycleLog, query_events
from agent.runner import AgentRunner
from app.services.mx_window import CN_TZ


class _FakeRuntime:
    """BrowserRuntime 桩：记录动作，零浏览器。"""

    def __init__(self):
        self.started = False
        self.stopped = False
        self.logins: list[str] = []
        self.rooms: list[str] = []
        self.token = "tok-fake"

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def ensure_logged_in(self, *, account: str, password: str) -> bool:
        self.logins.append(account)
        return True

    async def switch_room(self, room_name: str) -> None:
        self.rooms.append(room_name)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """单账号配置 + 固定窗口 + 离线数据目录。"""
    monkeypatch.setenv("MX_AGENT_ACCOUNTS", "solo-user")
    monkeypatch.setenv("MX_AGENT_PASSWORD_SOLO_USER", "pw")
    monkeypatch.setenv("MX_AGENT_DATA_DIR", str(tmp_path / "agentdata"))
    cfg = AgentConfig(accounts=__import__("agent.accounts", fromlist=["parse_accounts"]).parse_accounts("solo-user"),
                      data_dir=tmp_path / "agentdata")
    cfg.rooms = ["房A", "房B"]
    return cfg, tmp_path


def _windows_for(day: date):
    return (
        (datetime(day.year, day.month, day.day, 7, 0, tzinfo=CN_TZ),
         datetime(day.year, day.month, day.day, 11, 50, tzinfo=CN_TZ)),
    )


def _seed_plan(cfg: AgentConfig, day: date) -> None:
    """往计划存档写固定窗口（绕过 build_daily_plan 的随机性）。

    _plan_windows 走 get_today_plan → 当天文件命中即复用——与生产重启
    复用同一路径，同时让 tick 测试可控。
    """
    from agent.daily_plan import DailyPlanStore

    DailyPlanStore(cfg.data_dir / "plans").load_or_build(
        day, builder=lambda _d: __import__("app.services.mx_window",
                                           fromlist=["MXDailyPlan"]).MXDailyPlan(
            day=day,
            windows=_windows_for(day),
            # loads_plan 要求 fallback_slots 非空（坏数据防护）——固定一个即可
            fallback_slots=(datetime(day.year, day.month, day.day,
                                     8, 0, tzinfo=CN_TZ),),
            force_close_at=datetime(day.year, day.month, day.day,
                                    23, 40, tzinfo=CN_TZ),
        ))


def test_tick_open_window_starts_runtime_and_logs(monkeypatch, tmp_path, env):
    """进窗 tick：起桩运行时 + 登录成功 + 生命周期 browser_open/login_ok。"""
    cfg, tmp_path = env
    log = LifecycleLog(tmp_path / "agentdata" / "lifecycle.jsonl")
    runner = AgentRunner(cfg, log=log)
    fake = _FakeRuntime()
    runner.runtime = fake
    runner._open_window_done = False

    async def _fake_open(account, *, now):
        await fake.start()
        ok = await fake.ensure_logged_in(account=account.user, password="pw")
        assert ok
        runner.log.record("browser_open", account=account.user, detail="窗口开启")
        runner.log.record("login_ok", account=account.user, detail="窗口开启登录成功")
        runner.cadence = __import__("agent.cadence", fromlist=["RoomCadence"]).RoomCadence()

    monkeypatch.setattr(runner, "_open_window", _fake_open)
    day = date(2026, 11, 16)
    _seed_plan(cfg, day)
    asyncio.run(runner._tick(now=datetime(day.year, day.month, day.day, 7, 0, tzinfo=CN_TZ)))
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    kinds = [e["kind"] for e in events]
    assert "new_day_reset" in kinds and "browser_open" in kinds and "login_ok" in kinds
    assert fake.started


def test_window_close_stops_runtime(monkeypatch, tmp_path, env):
    """出窗 tick：运行时 stop + browser_close 生命周期。"""
    cfg, tmp_path = env
    log = LifecycleLog(tmp_path / "agentdata" / "lifecycle.jsonl")
    runner = AgentRunner(cfg, log=log)
    fake = _FakeRuntime()
    runner.runtime = fake
    # 先制造「窗口已开」决策态
    day = date(2026, 11, 16)
    _seed_plan(cfg, day)  # 固定计划：build_daily_plan 随机关窗时刻可能让 11:50 仍在窗内
    wins = _windows_for(day)
    runner.runner.tick(now=datetime(day.year, day.month, day.day, 7, 0, tzinfo=CN_TZ),
                       windows=wins)
    assert runner.runner.window_open

    async def scenario():
        await runner._tick(now=datetime(day.year, day.month, day.day, 11, 50, tzinfo=CN_TZ))

    asyncio.run(scenario())
    assert fake.stopped
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    assert any(e["kind"] == "browser_close" for e in events)


def test_room_switch_flow_records_last_room(monkeypatch, tmp_path, env):
    """切房链路：节奏到期 → 挑目标（排除上一个）→ 真点击桩 → 记录最后房间。"""
    import random

    from agent.cadence import RoomCadence

    cfg, tmp_path = env
    runner = AgentRunner(cfg, log=LifecycleLog(tmp_path / "agentdata" / "lifecycle.jsonl"))
    fake = _FakeRuntime()
    runner.runtime = fake
    runner.cadence = RoomCadence()
    # 强制到期：把武装时刻拨到过去
    runner.cadence._armed_at = 0.0
    runner.registry.set_last_room("solo-user", "房B")
    monkeypatch.setattr(random.Random, "choice",
                        lambda self, seq: next(r for r in seq if r != "房B"))

    async def scenario():
        await runner._maybe_switch_room()

    asyncio.run(scenario())
    assert fake.rooms == ["房A"]  # 排除上一个「房B」
    assert runner.registry.last_room("solo-user") == "房A"
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    assert any(e["kind"] == "room_switch" and "房A" in e["detail"] for e in events)


def test_room_click_failure_postpones_only(monkeypatch, tmp_path, env):
    """单次点击失败只顺延节奏，不炸循环（mx_activity 单次失败顺延语义）。"""
    from agent.cadence import RoomCadence

    cfg, tmp_path = env
    runner = AgentRunner(cfg, log=LifecycleLog(tmp_path / "agentdata" / "lifecycle.jsonl"))
    fake = _FakeRuntime()
    runner.runtime = fake
    runner.cadence = RoomCadence()
    runner.cadence._armed_at = 0.0

    async def boom(room_name: str) -> None:
        raise RuntimeError("点击超时")

    fake.switch_room = boom

    async def scenario():
        await runner._maybe_switch_room()

    asyncio.run(scenario())
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    assert any("失败" in e["detail"] and e["kind"] == "room_switch" for e in events)
    # 节奏已重新武装（advance 被调用）
    assert runner.cadence.next_fire_in() > 0


def test_login_failure_after_open_triggers_relay_and_backoff(monkeypatch, tmp_path, env):
    """开窗登录失败：接力切换评估 + 轮间退避计时（不硬轰不断采）。"""
    cfg, tmp_path = env
    # 双账号配置
    from agent.accounts import parse_accounts

    cfg.accounts = parse_accounts("solo-user,backup-user")
    runner = AgentRunner(cfg, log=LifecycleLog(tmp_path / "agentdata" / "lifecycle.jsonl"))
    fake = _FakeRuntime()
    fake.ensure_logged_in_calls: list[str] = []

    async def fail_login(*, account: str, password: str) -> bool:
        fake.ensure_logged_in_calls.append(account)
        return False

    fake.ensure_logged_in = fail_login

    async def _fake_open(account, *, now):
        await fake.start()
        ok = await fake.ensure_logged_in(account=account.user, password="pw")
        assert not ok
        runner._login_failures += 1
        runner.relay.report_login(account.user, ok=False)
        runner.log.record("login_fail", account=account.user,
                          detail=f"连续失败 {runner._login_failures} 次，接力切换评估")

    monkeypatch.setattr(runner, "_open_window", _fake_open)
    day = date(2026, 11, 16)
    _seed_plan(cfg, day)
    asyncio.run(runner._tick(now=datetime(day.year, day.month, day.day, 7, 0, tzinfo=CN_TZ)))
    # 主账号失败 → 接力切到备用
    assert runner.relay.active.user == "backup-user"
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    kinds = [e["kind"] for e in events]
    assert "relay_switch" in kinds and "login_fail" in kinds
