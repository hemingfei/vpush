"""行为器窗口循环决策的纯逻辑测试（票 #17 交付物 ②③ 的粘合层）。

本地 agent 对应「开窗→开 Chrome→登录→保持；关窗→关 Chrome」（mx-behavior
avior-logic.md §1 云端调度器消费侧的本地对应物；WS 会话管理不再需要）。

决策规则搬运（mx_window.py + scheduler _mx_window_tick）：
- 错过的窗口不武装（arm_windows）；工作日 08:00-22:00 重启例外重新武装
  正处的窗口（restart_login_allowed）；
- 到点开窗一次、窗口结束关窗一次；开关窗动作经回调上抛（真浏览器动作
  由 runner 的异步层承接，纯决策在此可单测）；
- 日切：new_day → 计划重建 + 接力回卷主账号。
"""
from __future__ import annotations

from datetime import date, datetime

from agent.window_runner import WindowRunner
from app.services.mx_window import CN_TZ


def _at(h: int, m: int = 0, day: date = date(2026, 11, 16)) -> datetime:
    """2026-11-16 是周一（工作日）。"""
    return datetime(day.year, day.month, day.day, h, m, tzinfo=CN_TZ)


def _windows_for(day: date):
    """固定三窗（避开随机）：7:00-11:50 / 12:30-16:00 / 19:00-23:30。"""
    return (
        (datetime(day.year, day.month, day.day, 7, 0, tzinfo=CN_TZ),
         datetime(day.year, day.month, day.day, 11, 50, tzinfo=CN_TZ)),
        (datetime(day.year, day.month, day.day, 12, 30, tzinfo=CN_TZ),
         datetime(day.year, day.month, day.day, 16, 0, tzinfo=CN_TZ)),
        (datetime(day.year, day.month, day.day, 19, 0, tzinfo=CN_TZ),
         datetime(day.year, day.month, day.day, 23, 30, tzinfo=CN_TZ)),
    )


def _runner(monkey_days=None, restart_login: bool = False) -> tuple[WindowRunner, list]:
    actions: list = []
    runner = WindowRunner(
        on_window_open=lambda now: actions.append(("open", now)),
        on_window_close=lambda now: actions.append(("close", now)),
        on_new_day=lambda day: actions.append(("new_day", day)),
        restart_login=restart_login,
    )
    return runner, actions


def test_window_opens_once_at_start_and_closes_once_at_end():
    runner, actions = _runner()
    wins = _windows_for(date(2026, 11, 16))
    # 7:00 前不开（首 tick 顺带 new_day——见 test_new_day_reset_between_days）
    runner.tick(now=_at(6, 59), windows=wins)
    assert actions == [("new_day", date(2026, 11, 16))]
    # 7:00 进窗 → 开一次
    runner.tick(now=_at(7, 0), windows=wins)
    assert actions[-1] == ("open", _at(7, 0))
    # 窗内持续 tick 不重复开
    runner.tick(now=_at(9, 30), windows=wins)
    assert len(actions) == 2
    # 出窗 → 关一次
    runner.tick(now=_at(11, 50), windows=wins)
    assert actions[-1][0] == "close"
    # 窗外持续 tick 不重复关
    runner.tick(now=_at(12, 29), windows=wins)
    assert len(actions) == 3
    # 第二段窗口照常
    runner.tick(now=_at(12, 30), windows=wins)
    assert actions[-1][0] == "open"


def test_missed_window_not_automatically_opened():
    """重启前已错过开窗点的窗口不再自动开（arm_windows「错过不续连」语义）。"""
    runner, actions = _runner()
    wins = _windows_for(date(2026, 11, 16))
    # 8:00 tick：处在第一窗内（7:00 已过）——不补开（默认非重启补登场景）
    runner.tick(now=_at(8, 0), windows=wins)
    assert [a[0] for a in actions] == ["new_day"]  # 只有 new_day，无 open
    # 12:45 tick：处在第二窗内——第二窗开窗点 12:30 也已过，同样不补开
    runner.tick(now=_at(12, 45), windows=wins)
    assert [a[0] for a in actions] == ["new_day"]


def test_restart_login_allowed_rearms_current_window():
    """工作日 08:00-22:00 重启例外：正处的窗口重新武装（下个 tick 补开）。"""
    runner, actions = _runner(restart_login=True)
    wins = _windows_for(date(2026, 11, 16))
    runner.tick(now=_at(8, 0), windows=wins)
    assert actions[-1] == ("open", _at(8, 0))
    # 补开后窗口行为照常：出窗即关
    runner.tick(now=_at(11, 50), windows=wins)
    assert actions[-1][0] == "close"


def test_restart_login_outside_work_hours_does_not_rearm():
    """夜间/周末重启不补（restart_login_allowed 的时间窗语义）。"""
    # 2026-11-15 是周日
    runner, actions = _runner(restart_login=True)
    wins = _windows_for(date(2026, 11, 15))
    runner.tick(now=_at(19, 10), windows=wins)  # 周日 19:10 已在晚间窗内
    assert [a[0] for a in actions] == ["new_day"]  # 不补开


def test_new_day_reset_between_days():
    runner, actions = _runner()
    day1 = _windows_for(date(2026, 11, 16))
    day2 = _windows_for(date(2026, 11, 17))
    runner.tick(now=_at(7, 0), windows=day1)   # new_day + open
    runner.tick(now=_at(23, 30), windows=day1)  # close（23:30 出窗）
    # 次日首 tick：先发 new_day；7:05 已过 7:00，新窗口开窗点也已错过 → 不补开
    runner.tick(now=_at(7, 5, day=date(2026, 11, 17)), windows=day2)
    kinds = [a[0] for a in actions]
    assert kinds == ["new_day", "open", "close", "new_day"]
    assert actions[3][1] == date(2026, 11, 17)
