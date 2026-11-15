"""单实例锁与看门狗的事故修复回归（2026-11-15 疯狂开窗事故）。

锁：agent 启动抢锁（抢不到自退）、guard 判定读锁、死进程残留可接管；
看门狗：新 Chrome「转发给既有实例即退」时端口仍通 → 必须按可用返回
（旧语义「进程退=失败」正是每 30s 重试开窗的根因）。
"""
from __future__ import annotations

from agent.executor import wait_cdp_port_open
from agent.single_instance import acquire_lock, lock_is_taken, release_lock

# ---- 单实例锁 ----

def test_acquire_lock_first_wins_second_rejected(tmp_path):
    lock = tmp_path / "agent.lock"
    first = acquire_lock(lock)
    assert first.held
    second = acquire_lock(lock)
    assert not second.held
    assert second.taken_by_alive  # 持有者是本进程：活的


def test_release_unlocks_for_next(tmp_path):
    lock = tmp_path / "agent.lock"
    first = acquire_lock(lock)
    release_lock(first)
    assert not lock_is_taken(lock)
    second = acquire_lock(lock)
    assert second.held
    release_lock(second)


def test_lock_is_taken_false_without_file(tmp_path):
    assert not lock_is_taken(tmp_path / "absent.lock")


def test_dead_holder_takeover(tmp_path):
    """崩溃残留（pid 不存在）→ 后来者接管，不被死锁困住。"""
    lock = tmp_path / "agent.lock"
    lock.write_text("99999999", encoding="utf-8")  # 不可能存活的 pid
    state = acquire_lock(lock)
    assert state.held
    release_lock(state)


# ---- 看门狗：转发退出场景 ----

class _FakeConn:
    """connect 回调桩：live=False 时端口始终不通；live=True 一连即通。"""

    def __init__(self, *, live: bool):
        self.live = live
        self.calls = 0

    def __call__(self, port):
        self.calls += 1
        if self.live:
            return
        raise OSError("refused")


def test_watchdog_process_exit_with_live_port_returns_true():
    """新 Chrome 转发给既有实例即退，但端口有活 Chrome → True（事故根因）。"""
    conn = _FakeConn(live=True)
    assert wait_cdp_port_open(
        port=9333, timeout_seconds=5, sleep=lambda s: None,
        connect=conn, process_poll=lambda: 1,  # 进程已退出（码 1）
    )


def test_watchdog_dead_process_dead_port_returns_false():
    """进程退 + 端口也不通 → 启动即退判失败。"""
    conn = _FakeConn(live=False)
    assert not wait_cdp_port_open(
        port=9333, timeout_seconds=2, sleep=lambda s: None,
        connect=conn, process_poll=lambda: 1,
    )


def test_watchdog_live_process_live_port_returns_true():
    conn = _FakeConn(live=True)
    assert wait_cdp_port_open(
        port=9333, timeout_seconds=5, sleep=lambda s: None,
        connect=conn, process_poll=lambda: None,
    )


def test_watchdog_timeout_returns_false():
    conn = _FakeConn(live=False)
    assert not wait_cdp_port_open(
        port=9333, timeout_seconds=2, sleep=lambda s: None,
        connect=conn, process_poll=lambda: None,
    )
