"""行为器窗口循环决策层（票 #17 交付物 ② 的粘合层，纯逻辑可单测）。

本地 agent 对应云端调度器窗口循环的「开窗→开 Chrome→登录→保持；
关窗→关 Chrome」（票 #17 + ADR-0001：本地架构里 WS 会话管理由本地浏览器
承接，云端 _mx_window_loop 的窗口决策语义搬运自 app/services/mx_window.py）。

决策规则搬运自 app.services.mx_window（红线：不重写语义）：
- 错过的窗口不武装（arm_windows 默认口径）——重启后不自动续连；
- 例外：工作日 08:00-22:00 重启（restart_login_allowed）重新武装正处的
  窗口，下个 tick 补开；
- 到点开窗一次、出窗关窗一次（对应 scheduler._mx_window_tick 的
  _mx_window_open 状态翻转 + 一次性日志）；
- 日切（看到新日期的首 tick）：发 new_day（调用方重建当日计划 + 接力
  回卷主账号），然后按新窗口重新决策。

真浏览器动作（开关 Chrome/登录/切房）经 on_window_open/on_window_close
回调上抛——回调抛错由调用方兜底，决策层保持纯函数性。
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

from app.services.mx_window import arm_windows


class WindowRunner:
    """窗口 tick 决策器：windows 当日计划 + now → 该开/该关/该日切。

    restart_login 由调用方按「本次进程是否处于重启补登场景」给定一次
    （进程启动时判 restart_login_allowed(now)，与云端 _mx_windows_today
    在装载时一次性判定的口径一致）。
    """

    def __init__(
        self,
        *,
        on_window_open: Callable[[datetime], None],
        on_window_close: Callable[[datetime], None],
        on_new_day: Callable[[date], None],
        restart_login: bool = False,
    ):
        self._on_open = on_window_open
        self._on_close = on_window_close
        self._on_new_day = on_new_day
        self._restart_login = restart_login
        self._day: date | None = None
        self._open = False
        # 武装状态按日缓存（云端 scheduler._mx_armed 同款）：计划装载时刻算一次，
        # 到点 tick 查缓存——每 tick 重算会让「start>=now」与「start<=now」互相
        # 矛盾（开窗点错秒即永远错过；云端语义是装载时判错过，到点必开）
        self._armed: list[bool] | None = None

    def tick(self, *, now: datetime, windows, restart_login: bool | None = None) -> None:
        """单次 tick（调用方按 30s 节奏驱动，与云端 _mx_window_loop 同频）。

        restart_login 默认取构造时注入值（进程启动判一次）；tick 显式传参
        仅供测试驱动特定重启场景。
        """
        today = now.date()
        if self._day != today:
            self._day = today
            self._open = False  # 跨天关窗态复位（夜间关窗兜底，防跨天悬挂）
            self._armed = None  # 武装状态随当日计划重建（云端 _mx_windows_today 同款）
            self._on_new_day(today)

        if self._armed is None or len(self._armed) != len(windows):
            self._armed = arm_windows(list(windows), now,
                                      restart_login=self._restart_login
                                      if restart_login is None else restart_login)
        armed = self._armed
        idx = next((i for i, (start, stop) in enumerate(windows)
                    if start <= now < stop), None)
        if idx is not None:
            # 窗内：武装且未开 → 开（到点开窗；错过开窗点的窗口 arm_windows
            # 已置 False，自然不补开；重启例外重新武装后这里补开）
            if armed[idx] and not self._open:
                self._open = True
                self._on_open(now)
        elif self._open:
            self._open = False
            self._on_close(now)

    @property
    def window_open(self) -> bool:
        """当前是否处于「窗口已开」决策态（runner 异步层据此决定是否保持登录）。"""
        return self._open
