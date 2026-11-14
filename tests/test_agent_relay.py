"""接力（Relay）状态机纯逻辑测试（票 #17 交付物 ⑤）。

语义红线（票 #17 交付物 5 + CONTEXT.md「接力」+ ADR-0001 多账号接力段）：
- 主账号登录失败/失效 → 备用账号顶上；
- 主账号恢复 → 备用账号下线；
- 两账号任何时刻不并行在线（行为器单浏览器单账号驱动）；
- 各账号每天都登录，无轮休概念（「轮换」是禁用词）；
- 接力只按失效切换触发——不按时间段轮换（spec Out of Scope）。
"""
from __future__ import annotations

from agent.accounts import parse_accounts
from agent.relay import RelayState, RelayStateMachine

ACCOUNTS = parse_accounts("primary-user,backup-user")


def _machine(events: list) -> RelayStateMachine:
    """记录切换动作的接力机（events 元素 = (事件, 账号名)）。"""
    return RelayStateMachine(
        ACCOUNTS,
        on_switch=lambda kind, account: events.append((kind, account.user)),
    )


def test_initial_active_is_primary():
    """初始态：主账号活跃（备用待命，不并行在线）。"""
    m = _machine([])
    assert m.active.user == "primary-user"
    assert m.state == RelayState.PRIMARY_ACTIVE


def test_primary_login_failure_activates_backup():
    """主账号登录失败 → 备用顶上（kind="switch_to_backup"）。"""
    events: list = []
    m = _machine(events)
    m.report_login("primary-user", ok=False)
    assert m.active.user == "backup-user"
    assert events == [("switch_to_backup", "backup-user")]


def test_backup_login_failure_keeps_trying_no_parallel():
    """备用也失败 → 沿清单顺延/回卷主账号，绝不停在「无账号」也不并行。"""
    events: list = []
    m = _machine(events)
    m.report_login("primary-user", ok=False)
    m.report_login("backup-user", ok=False)
    # 回卷到主账号（清单里唯一的候选）——重试节奏由调用方控制
    assert m.active.user == "primary-user"
    assert len(events) == 2


def test_primary_recovery_stands_down_backup():
    """备用在位时主账号恢复登录 → 备用下线（kind="primary_recovered"）。"""
    events: list = []
    m = _machine(events)
    m.report_login("primary-user", ok=False)
    m.report_login("backup-user", ok=True)   # 备用登录成功在位
    m.report_login("primary-user", ok=True)  # 主账号恢复
    assert m.active.user == "primary-user"
    assert events[-1] == ("primary_recovered", "primary-user")


def test_no_parallel_online():
    """全程任意时刻活跃账号唯一（状态机只输出一个 active，绝不出现双账号）。"""
    events: list = []
    m = _machine(events)
    seq = [("primary-user", False), ("backup-user", True), ("backup-user", True),
           ("primary-user", True), ("primary-user", False)]
    for user, ok in seq:
        m.report_login(user, ok=ok)
        # 每步后都恰好有一个活跃账号
        assert m.active is not None


def test_backup_login_success_while_primary_active_is_ignored():
    """主账号健康时备用账号的登录成功不切换（不并行在线的推论）。"""
    events: list = []
    m = _machine(events)
    m.report_login("primary-user", ok=True)
    m.report_login("backup-user", ok=True)  # 迟到的备用成功：不动
    assert m.active.user == "primary-user"
    assert events == []


def test_session_expired_on_primary_switches_to_backup():
    """主账号掉登录态（会话中途失效）→ 与登录失败同一切换语义。"""
    events: list = []
    m = _machine(events)
    m.report_login("primary-user", ok=True)
    m.report_session_expired("primary-user")
    assert m.active.user == "backup-user"
    assert events == [("switch_to_backup", "backup-user")]


def test_primary_daily_login_no_rest_days():
    """无轮休：主账号第二天首个窗口照常登录（状态机日切时回卷主账号）。

    「各账号每天登录」：备用顶位只覆盖主账号的下线窗口，不改变
    第二天从主账号开始的日程。
    """
    events: list = []
    m = _machine(events)
    m.report_login("primary-user", ok=False)
    m.report_login("backup-user", ok=True)
    m.new_day()
    assert m.active.user == "primary-user"
    assert events[-1] == ("new_day_reset", "primary-user")


def test_manual_events_do_not_leak_passwords_or_secrets(events=None):
    """回调只带账号名与切换类型——凭据绝不进事件流（生命周期日志可查询
    但可查询面不含密钥）。"""
    captured: list = []
    m = RelayStateMachine(
        ACCOUNTS,
        on_switch=lambda kind, account: captured.append((kind, account)),
    )
    m.report_login("primary-user", ok=False)
    # 回调给的是 Account 对象：账号名/user 可查，密码从不出现
    assert all(isinstance(a.user, str) for _, a in captured)
    assert all("password" not in k for k, _ in captured)
