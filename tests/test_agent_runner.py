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
    """单次点击失败只顺延节奏，不炸循环（原 mx_activity 单次失败顺延语义）。"""
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


# ---- S2: 接力中途换 profile（接力切换的浏览器面）----


class _RecordingFactory:
    """记录 start/stop 顺序的 BrowserRuntime 工厂桩（构造顺序=换 profile 顺序）。"""

    def __init__(self):
        self.events: list[str] = []
        self.fail_on: str | None = None
        self.runtimes: list[_FakeRuntime] = []

    def make(self, account: str, token: str | None) -> _FakeRuntime:
        rt = _FakeRuntime()
        rt.account = account
        rt.token = token

        async def start():
            self.events.append(f"start:{account}")
            if self.fail_on == f"start:{account}":
                raise RuntimeError("Chrome 启动失败")

        async def stop():
            self.events.append(f"stop:{account}")

        rt.start = start
        rt.stop = stop
        self.runtimes.append(rt)
        return rt


def _two_account_runner(env, tmp_path, factory):
    from agent.accounts import parse_accounts

    cfg, _ = env
    cfg.accounts = parse_accounts("main-user,backup-user")
    runner = AgentRunner(cfg, log=LifecycleLog(tmp_path / "agentdata" / "lifecycle.jsonl"))
    runner._runtime_factory = factory.make
    return runner


def _open_window_state(runner, day=None):
    """把 WindowRunner 拨到「窗口已开」决策态（mid-session 场景前提）。"""
    day = day or date(2026, 11, 16)
    wins = _windows_for(day)
    # 先武装：起点设为未来一毫秒的等价手法——直接用 restart_login=True 补武装
    runner.runner.tick(
        now=datetime(day.year, day.month, day.day, 8, 0, tzinfo=CN_TZ),
        windows=wins, restart_login=True)
    assert runner.runner.window_open


def test_relay_switch_swaps_profile_mid_session(env, tmp_path):
    """接力切换（switch_to_backup）：旧运行时先关，新 profile 启动+登录续窗。"""
    factory = _RecordingFactory()
    runner = _two_account_runner(env, tmp_path, factory)
    _open_window_state(runner)
    old_rt = factory.make("main-user", "tok-m")
    runner.runtime = old_rt
    runner.registry.set_token("main-user", "tok-m", updated_at=1.0)
    runner.registry.set_token("backup-user", "tok-b", updated_at=1.0)

    async def scenario():
        runner.relay.report_login("main-user", ok=False)
        await asyncio.sleep(0.1)  # 等换 profile 的 create_task 执行完

    asyncio.run(scenario())
    # 切换后活跃账号是备用，且完成了「先关旧、再起新、再登录」的动作序列
    assert runner.relay.active.user == "backup-user"
    assert factory.events[:2] == ["stop:main-user", "start:backup-user"], factory.events
    assert runner.runtime is factory.runtimes[-1], "运行时必须换成备用 profile 的实例"
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    kinds = [e["kind"] for e in events]
    assert "relay_switch" in kinds and "login_ok" in kinds, kinds


def test_relay_swap_failure_degrades_gracefully(env, tmp_path):
    """换 profile 中途失败：降级不炸——接力状态保持一致，下次开窗走新活跃账号。"""
    factory = _RecordingFactory()
    runner = _two_account_runner(env, tmp_path, factory)
    _open_window_state(runner)
    old_rt = factory.make("main-user", "tok-m")
    runner.runtime = old_rt
    runner.registry.set_token("main-user", "tok-m", updated_at=1.0)
    factory.fail_on = "start:backup-user"  # 新 profile 启动即失败

    async def scenario():
        runner.relay.report_login("main-user", ok=False)
        await asyncio.sleep(0.1)  # 等 swap 任务跑完（含失败分支）

    asyncio.run(scenario())
    # 状态机活跃位已切到备用（决策一致性），运行时被清空（旧浏览器已关、
    # 新浏览器没起来——下次 tick 开窗动作按活跃账号重开）
    assert runner.relay.active.user == "backup-user"
    assert runner.runtime is None
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    assert any(e["kind"] == "relay_swap_error" for e in events), events


def test_primary_recovered_swaps_back(env, tmp_path):
    """主账号恢复（primary_recovered）：备用浏览器关停，主 profile 换回。"""
    factory = _RecordingFactory()
    runner = _two_account_runner(env, tmp_path, factory)
    _open_window_state(runner)
    backup_rt = factory.make("backup-user", "tok-b")
    runner.runtime = backup_rt
    runner.registry.set_token("main-user", "tok-m", updated_at=1.0)
    runner.registry.set_token("backup-user", "tok-b", updated_at=1.0)
    # 把状态机拨到备用在位（manual，绕过 report_login 的失败切换含义）
    runner.relay._active_index = 1

    async def scenario():
        runner.relay.report_login("main-user", ok=True)
        await asyncio.sleep(0.1)  # 等 swap-back 任务跑完

    asyncio.run(scenario())
    assert runner.relay.active.user == "main-user"
    assert factory.events[:2] == ["stop:backup-user", "start:main-user"], factory.events
    assert runner.runtime is factory.runtimes[-1], "运行时必须换回主账号 profile 实例"
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    kinds = [e["kind"] for e in events]
    assert "relay_switch" in kinds


# ---- S6: 会话中段失效检测（CDP liveness 探针）----


def test_mid_session_logout_triggers_relogin(env, tmp_path, monkeypatch):
    """localStorage 掉登录态（键被清）→ 探针判死 → 中段重登成功。"""
    cfg, _ = env
    runner = AgentRunner(cfg, log=LifecycleLog(tmp_path / "agentdata" / "lifecycle.jsonl"))
    fake = _FakeRuntime()
    fake.token = None  # token 兜底无效——探针才说话

    async def ensure_logged_in(*, account: str, password: str) -> bool:
        fake.logins.append(account)
        fake.token = "tok-new"  # 真实运行时契约：登录成功回写 token
        return True

    async def probe():
        return {"alive": False, "error": None}

    fake.ensure_logged_in = ensure_logged_in
    fake.probe_session = probe
    runner.runtime = fake

    async def scenario():
        await runner._ensure_session()

    asyncio.run(scenario())
    assert fake.logins == ["solo-user"], "探针判死应走中段重登"
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    assert any(e["kind"] == "login_ok" for e in events)


def test_mid_session_alive_skips_relogin(env, tmp_path):
    """localStorage 认证键健在 → alive → 不重登（pacer 不空转）。"""
    cfg, _ = env
    runner = AgentRunner(cfg, log=LifecycleLog(tmp_path / "agentdata" / "lifecycle.jsonl"))
    fake = _FakeRuntime()

    async def probe():
        return {"alive": True, "error": None}

    fake.probe_session = probe
    runner.runtime = fake

    async def scenario():
        await runner._ensure_session()

    asyncio.run(scenario())
    assert fake.logins == [], "会话健在不应重登"


def test_mid_session_probe_error_treated_as_dead(env, tmp_path):
    """CDP 探针报错（Runtime.evaluate 失败）= 浏览器进程已死：收尸重建。

    死页面上的 ensure_logged_in 只会永远失败——正确语义是收尸旧 runtime
    （置 None + browser_rebuild 事件），重登发生在下一 tick 补开的新浏览器上。
    """
    cfg, tmp_path = env
    log_path = tmp_path / "agentdata" / "lifecycle.jsonl"
    runner = AgentRunner(cfg, log=LifecycleLog(log_path))
    fake = _FakeRuntime()

    async def probe():
        raise RuntimeError("CDP 会话丢失")

    async def ensure_logged_in(*, account: str, password: str) -> bool:
        fake.logins.append(account)
        fake.token = "tok-new"
        return True

    fake.ensure_logged_in = ensure_logged_in
    fake.probe_session = probe
    runner.runtime = fake

    async def scenario():
        await runner._ensure_session()

    asyncio.run(scenario())
    assert runner.runtime is None, "旧 runtime 已收尸"
    assert fake.logins == [], "不在死页面上重登"
    events = query_events(log_path)
    assert any(e["kind"] == "browser_rebuild" for e in events), "重建事件入档"


def test_mid_session_fatal_error_triggers_relay_switch(env, tmp_path):
    """中段重登致命错误（密码错/锁定）：不硬轰——报给接力状态机切备用。"""
    from agent.accounts import parse_accounts

    cfg, _ = env
    cfg.accounts = parse_accounts("main-user,backup-user")
    runner = AgentRunner(cfg, log=LifecycleLog(tmp_path / "agentdata" / "lifecycle.jsonl"))
    runner.relay = __import__("agent.relay", fromlist=["RelayStateMachine"]).RelayStateMachine(
        cfg.accounts, on_switch=runner._on_relay_switch)
    fake = _FakeRuntime()
    fake.token = None

    async def probe():
        return {"alive": False, "error": None}

    fake.probe_session = probe

    async def fail_login(*, account: str, password: str) -> bool:
        from app.fetchers.mx.login import MXLoginError

        raise MXLoginError("密码错误，请重新输入")

    fake.probe_session = probe
    fake.ensure_logged_in = fail_login
    runner.runtime = fake

    async def scenario():
        await runner._ensure_session()

    asyncio.run(scenario())
    assert runner.relay.active.user == "backup-user", "致命错误应触发接力切换"
    events = query_events(tmp_path / "agentdata" / "lifecycle.jsonl")
    kinds = [e["kind"] for e in events]
    assert any(k in ("login_fail", "relay_switch") for k in kinds), kinds
