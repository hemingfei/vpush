"""接力（Relay）状态机：失效切换的唯一决策点（票 #17 交付物 ⑤）。

语义（spec #14 Implementation Decisions + CONTEXT.md「接力」）：
- 账号注册表顺序即优先级：清单首个是主账号，其后是备用；
- 主账号登录失败/失效 → 备用顶上；备用再失败 → 沿清单顺延/回卷——
  绝不停在「无账号」状态（重试节奏由调用方按 mx_login 的重试口径控制）；
- 主账号恢复登录成功 → 备用下线（kind="primary_recovered"）；
- 两账号不并行在线：状态机任一时刻只输出一个活跃账号——行为器单浏览器
  单 profile 单账号驱动，这是「不并行」的结构保证；
- 无轮休概念（「轮换」是禁用词）：new_day() 把活跃位回卷到主账号——
  备用顶位只覆盖主账号的下线窗口，第二天日程照常从主账号开始；
- 接力只按失效切换触发：没有按时间段轮换的路径（spec Out of Scope）。

跨账号去重是云端网关的职责（同房间+时间相邻+内容相似 ≥90%），本状态机
只负责「当前活跃账号是谁」——该标识随采集器信封 account 字段上行。
"""
from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field

from .accounts import Account


class RelayState(enum.Enum):
    PRIMARY_ACTIVE = "primary_active"
    BACKUP_ACTIVE = "backup_active"


@dataclass(frozen=True)
class RelayEvent:
    """一次切换事件（进结构化日志；只含账号名，绝不含凭据）。"""

    kind: str          # switch_to_backup | primary_recovered | new_day_reset
    account: str


@dataclass
class RelayStateMachine:
    """账号清单驱动的失效切换状态机。

    on_switch(kind, account)：切换发生时的回调——调用方用来发结构化日志
    与触发实际登录动作。回调同步执行、不抛错假设（调用方自行兜底）。
    """

    accounts: list[Account]
    on_switch: Callable[[str, Account], None] = lambda kind, account: None
    _active_index: int = field(default=0, init=False)

    # ---- 观察面 ----

    @property
    def active(self) -> Account:
        """当前活跃账号（唯一在线者）。"""
        return self.accounts[self._active_index]

    @property
    def state(self) -> RelayState:
        return (RelayState.PRIMARY_ACTIVE if self._active_index == 0
                else RelayState.BACKUP_ACTIVE)

    def _emit(self, kind: str, account: Account) -> None:
        self.on_switch(kind, account)

    # ---- 事件入口 ----

    def report_login(self, user: str, *, ok: bool) -> None:
        """某账号登录结果（成功/失败）——接力切换的触发器。

        规则：
        - 失败的是当前活跃账号 → 顺延到下一候选（回卷到头）；失败的不是
          活跃账号 → 无事发生（后台探测失败不打扰在线会话）；
        - 成功的是主账号且活跃位不在主账号 → 主账号恢复，备用下线；
        - 成功的是当前活跃账号 → 无事发生；成功的是非活跃备用 → 不切换
          （不并行在线的推论：备用成功不构成上线理由）。
        """
        idx = next((i for i, a in enumerate(self.accounts) if a.user == user), None)
        if idx is None:
            return
        if ok:
            if idx == 0 and self._active_index != 0:
                self._active_index = 0
                self._emit("primary_recovered", self.active)
            return
        if idx != self._active_index:
            return
        # 当前活跃账号登录失败：沿清单顺延（到尾回卷到头），绝不停在无账号
        self._active_index = (self._active_index + 1) % len(self.accounts)
        self._emit("switch_to_backup", self.active)

    def report_session_expired(self, user: str) -> None:
        """某账号会话中途失效（掉登录态）——与登录失败同一切换语义。"""
        self.report_login(user, ok=False)

    def new_day(self) -> None:
        """日切：活跃位回卷主账号（无轮休——各账号每天登录，从主账号开始）。"""
        if self._active_index != 0:
            self._active_index = 0
            self._emit("new_day_reset", self.active)
