"""行为器登录重试节奏（票 #17 交付物 ④）。

登录链路本身复用 mx_login（run_login_flow 验证码重试循环 + AI 视觉识码，
不重写）；本模块只管**轮与轮之间**的节奏与触发判定：

- 登录后仍失败（短暂风控波动）→ 按递增退避重试重登：user story 3
  「短暂风控波动不升级为整日断采」——既不断采，也不硬轰（mx_login 文件头
  红线：连续失败登录本身就是风控信号）；
- 致命错误（密码错/锁定/封禁——mx_login._FATAL_LOGIN_MSG_MARKERS 已熔断
  单轮循环）不再触发重登：等人工处置；接力侧表现为切备用账号。

run_login_flow 的执行调用在 agent.browser 运行时（真浏览器链路，不进 CI）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.fetchers.mx.client import MXTokenExpiredError
from app.fetchers.mx.login import MXLoginError

# 致命登录错误特征（搬运 scripts/mx_login.py:55 _FATAL_LOGIN_MSG_MARKERS：
# 换验证码重试毫无意义的错误——命中即不重登，等人工处置）
FATAL_LOGIN_MARKERS = ("密码", "账号", "锁定", "冻结", "封禁", "禁止", "不存在")


@dataclass
class LoginRetryPacer:
    """轮间重登退避：基数随连续失败递增（指数）、带 ±20% 抖动、封顶。

    抖动与原云端行为模拟（mx_activity）的「固定节拍可被统计」教训同源：重登
    节奏也不做机器固定间隔。
    """

    initial_seconds: float = 60.0     # 首轮失败后 1 分钟量级再试
    factor: float = 2.0               # 指数递增
    max_seconds: float = 30 * 60.0    # 封顶 30 分钟（窗口关前必须还有机会）

    def base_delay(self, consecutive_failures: int) -> timedelta:
        """无抖动的基准延迟：initial * factor^(failures-1)，封顶 max。"""
        n = max(1, consecutive_failures)
        seconds = min(self.initial_seconds * (self.factor ** (n - 1)),
                      self.max_seconds)
        return timedelta(seconds=seconds)

    def max_delay(self) -> timedelta:
        return timedelta(seconds=self.max_seconds)

    def next_retry_delay(self, *, now: datetime,
                         consecutive_failures: int) -> timedelta:
        """下一轮重登的等待时长（now 参数只做节奏锚点记录，不参与计算）。"""
        if consecutive_failures <= 0:
            return timedelta(0)
        base = self.base_delay(consecutive_failures).total_seconds()
        jittered = base * random.uniform(0.8, 1.2)
        return timedelta(seconds=min(jittered, self.max_seconds))


@dataclass
class _ProbeResult:
    """登录态探针结果（运行时由 browser 会话侧产出）。"""

    token: str
    alive: bool
    error: BaseException | None


def _is_fatal(exc: BaseException) -> bool:
    if not isinstance(exc, MXLoginError):
        return False
    return any(marker in str(exc) for marker in FATAL_LOGIN_MARKERS)


def relogin_needed(probe: Any) -> bool:
    """探针结果 → 是否需要重登。

    - 会话活着 → 不重登；
    - token 失效 / 普通登录错误 → 重登（按节奏）；
    - 致命登录错误 → 不重登（人工处置；接力切备用账号由 relay 状态机决策）。
    """
    if probe.get("alive"):
        return False
    error = probe.get("error")
    if isinstance(error, MXTokenExpiredError):
        return True
    if isinstance(error, MXLoginError):
        return not _is_fatal(error)
    # 无 token 且无异常信息（如 profile 冷启动首探）：按需重登
    return True
