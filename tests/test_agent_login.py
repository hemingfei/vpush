"""行为器登录重试节奏的纯逻辑测试（票 #17 交付物 ④，user story 3）。

语义：登录链路复用 mx_login——run_login_flow 内部已有验证码重试循环；
本模块管的是**轮与轮之间**的节奏：登录后仍失败（如短暂风控波动）→
按节奏重试重登，而不是整日断采或无退避硬轰（mx_login 文件头红线：
「连续失败登录本身就是风控信号」→ 轮间必须有递增间隔）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from agent.login import LoginRetryPacer, relogin_needed
from app.fetchers.mx.client import MXTokenExpiredError
from app.fetchers.mx.login import MXLoginError
from app.services.mx_window import CN_TZ

# ---- 轮间节奏：递增退避 ----

def test_first_attempt_immediate():
    pacer = LoginRetryPacer()
    t = datetime(2026, 11, 16, 8, 0, tzinfo=CN_TZ)
    assert pacer.next_retry_delay(now=t, consecutive_failures=0) == timedelta(0)


def test_delays_grow_with_consecutive_failures():
    """连续失败越多，下一轮重登间隔越长（指数式，封顶）：对冲「连续失败
    登录本身就是风控信号」。"""
    pacer = LoginRetryPacer()
    t = datetime(2026, 11, 16, 8, 0, tzinfo=CN_TZ)
    # 抖动下单次抽样不保证单调，这里用基准延迟断言单调、实际延迟断言有界
    assert pacer.base_delay(1) < pacer.base_delay(2) < pacer.base_delay(3) < pacer.base_delay(5)
    # 封顶：失败再多间隔也不再无限增长（窗口关之前必须还有机会重登）
    assert pacer.base_delay(10) == pacer.max_delay()
    for _ in range(50):
        d1 = pacer.next_retry_delay(now=t, consecutive_failures=1)
        d100 = pacer.next_retry_delay(now=t, consecutive_failures=100)
        assert d1 > timedelta(0)
        assert d100 <= pacer.max_delay()  # 抖动 ±20% 后仍不越过封顶


def test_delays_jittered_but_within_bounds():
    pacer = LoginRetryPacer()
    t = datetime(2026, 11, 16, 8, 0, tzinfo=CN_TZ)
    for failures in (1, 2, 5):
        base = pacer.base_delay(failures)
        for _ in range(50):
            delay = pacer.next_retry_delay(now=t, consecutive_failures=failures)
            # 抖动 ±20%：不是固定间隔的机器节奏
            assert timedelta(seconds=base.total_seconds() * 0.8) <= delay
            assert delay <= timedelta(seconds=base.total_seconds() * 1.2)


def test_success_resets_failures():
    """登录成功 → 连续失败计数清零（下一轮再失败从头退避）。"""
    pacer = LoginRetryPacer()
    t = datetime(2026, 11, 16, 8, 0, tzinfo=CN_TZ)
    assert pacer.next_retry_delay(now=t, consecutive_failures=3) > timedelta(0)
    assert pacer.next_retry_delay(now=t, consecutive_failures=0) == timedelta(0)


# ---- 重登触发判定 ----

def test_relogin_needed_on_token_expired():
    """掉登录态（token 失效特征异常）→ 需要重登。"""
    probe = {"token": "t", "alive": False, "error": MXTokenExpiredError("token失效")}
    assert relogin_needed(probe) is True


def test_relogin_needed_on_login_error():
    probe = {"token": "t", "alive": False, "error": MXLoginError("登录失败：验证码错误")}
    assert relogin_needed(probe) is True


def test_relogin_not_needed_when_session_alive():
    probe = {"token": "t", "alive": True, "error": None}
    assert relogin_needed(probe) is False


def test_relogin_not_needed_for_fatal_login_error():
    """致命错误（密码错/账号锁定）不重试重登——run_login_flow 已熔断剩余
    次数，这里按节奏重试毫无意义，等人工处置（mx_login._FATAL 登录 msg
    markers 语义）。接力侧表现为切换备用账号，不是同账号硬轰。"""
    probe = {"token": "", "alive": False,
             "error": MXLoginError("密码错误（致命错误，熔断本轮重试）")}
    assert relogin_needed(probe) is False
