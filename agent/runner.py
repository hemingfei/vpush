"""行为器主循环：把全部纯逻辑组件粘成常驻进程（票 #17 交付物 ⑧）。

组件分工（本模块零新决策——决策全在已测组件里）：
- WindowRunner（窗口 tick 决策）：开窗/关窗/日切；
- DailyPlanStore（当日计划）：同日重启不漂移；
- RelayStateMachine（接力）：活跃账号唯一，失效切换；
- LoginRetryPacer（轮间退避）：短暂风控波动不升级为整日断采；
- BrowserRuntime（真浏览器链路，agent/browser.py，不进 CI）；
- RoomCadence + pick_room（切房节奏与目标选择）；
- LifecycleLog（生命周期结构化日志）。

循环骨架搬运云端 _mx_window_loop 的形态：30 秒一次 tick，所有异常兜底
记日志继续循环（挂死比异常循环更糟——48h 挂机验收的先决条件）。
"""
from __future__ import annotations

import asyncio
import glob
import logging
import os
import random
import time
from datetime import datetime

from app.services.mx_window import CN_TZ, build_daily_plan, restart_login_allowed

from .accounts import Account, AccountRegistry
from .browser import BrowserRuntime
from .cadence import RoomCadence, pick_room
from .config import AgentConfig
from .daily_plan import get_today_plan
from .executor import CDPExecutor
from .lifecycle import LifecycleLog
from .login import LoginRetryPacer, relogin_needed
from .relay import RelayStateMachine
from .window_runner import WindowRunner

logger = logging.getLogger(__name__)

# 循环节奏与云端 _mx_window_loop 同频（30s tick）
TICK_SECONDS = 30.0


class AgentRunner:
    """常驻行为器：一个循环驱动窗口/登录/接力/切房全生命周期。"""

    def __init__(self, config: AgentConfig, *, log: LifecycleLog,
                 registry: AccountRegistry | None = None):
        self.config = config
        self.log = log
        self.registry = registry or config.registry()
        self.relay = RelayStateMachine(
            config.accounts,
            on_switch=self._on_relay_switch,
        )
        self._restart_login = restart_login_allowed(datetime.now(CN_TZ))
        self.runner = WindowRunner(
            on_window_open=lambda now: None,   # 异步动作在 _tick 里由 decision 驱动
            on_window_close=lambda now: None,
            on_new_day=self._on_new_day,
            restart_login=self._restart_login,
        )
        self.cadence = RoomCadence()
        self.pacer = LoginRetryPacer()
        self.runtime: BrowserRuntime | None = None
        self._login_failures = 0
        self._next_relogin_at: float | None = None

    # ---- 日志回调（生命周期事件统一落点） ----

    def _on_relay_switch(self, kind: str, account: Account) -> None:
        self.log.record("relay_switch", account=account.user,
                        detail=f"{kind} → 活跃账号 {account.user}")

    def _on_new_day(self, day) -> None:
        # 日切：接力回卷主账号 + 计划重建（WindowRunner 的下一 tick 读新窗口）
        self.relay.new_day()
        self.log.record("new_day_reset", account=self.relay.active.user,
                        detail=f"{day} 计划重建，回卷主账号")

    # ---- 窗口动作（tick 决策驱动的异步执行） ----

    def _plan_windows(self, now: datetime):
        plan = get_today_plan(
            store_dir=self.config.data_dir / "plans",
            now=now,
            builder=build_daily_plan,
        )
        return plan.windows

    async def _open_window(self, account: Account, *, now: datetime) -> None:
        """开窗：起浏览器 → 登录（seed 免登 → 重登链路）→ 节奏重武装。"""
        self.log.record("browser_open", account=account.user,
                        detail=f"窗口开启 {now:%H:%M:%S}")
        executor = CDPExecutor(
            exe=self._chrome_exe(),
            user_data_dir=self.registry.profile_dir(account.user),
            cdp_port=self.config.cdp_port,
            origin=self.config.origin,
        )
        rt = BrowserRuntime(executor=executor, account_user=account.user,
                            token=self.registry.token(account.user))
        await rt.start()
        ok = await rt.ensure_logged_in(
            account=account.user,
            password=self.config.password_of(account),
        )
        if ok and rt.token:
            self.registry.set_token(account.user, rt.token, updated_at=time.time())
            self._login_failures = 0
            self._next_relogin_at = None
            self.relay.report_login(account.user, ok=True)
            self.log.record("login_ok", account=account.user, detail="窗口开启登录成功")
        else:
            self._login_failures += 1
            self.relay.report_login(account.user, ok=False)
            self.log.record("login_fail", account=account.user,
                            detail=f"连续失败 {self._login_failures} 次，接力切换评估")
        self.runtime = rt
        self.cadence = RoomCadence()  # 会话开启即武装：首次点击落在一个随机间隔后

    async def _close_window(self, *, now: datetime) -> None:
        """关窗：关浏览器（采集器随浏览器一起退出；agent 不感知采集器）。"""
        account = self.relay.active
        self.log.record("browser_close", account=account.user,
                        detail=f"窗口结束 {now:%H:%M:%S}")
        if self.runtime is not None:
            await self.runtime.stop()
            self.runtime = None

    # ---- 登录保持与重登 ----

    async def _ensure_session(self) -> None:
        """窗口开着但会话掉登录态 → 按 pacer 节奏重登（不硬轰不断采）。"""
        if self.runtime is None:
            return
        account = self.relay.active
        token = self.runtime.token
        probe = {"token": token, "alive": bool(token), "error": None}
        if token:
            # 只读探针语义（mx_login.probe_token 的 user/info）：token 在即可用
            probe["alive"] = True
        if not relogin_needed(probe):
            return
        now_mono = time.monotonic()
        if self._next_relogin_at is not None and now_mono < self._next_relogin_at:
            return  # 退避窗口未到
        ok = await self.runtime.ensure_logged_in(
            account=account.user, password=self.config.password_of(account))
        if ok and self.runtime.token:
            self.registry.set_token(account.user, self.runtime.token,
                                    updated_at=time.time())
            self._login_failures = 0
            self._next_relogin_at = None
            self.log.record("login_ok", account=account.user, detail="重登成功")
        else:
            self._login_failures += 1
            delay = self.pacer.next_retry_delay(
                now=datetime.now(CN_TZ), consecutive_failures=self._login_failures)
            self._next_relogin_at = now_mono + delay.total_seconds()
            self.relay.report_login(account.user, ok=False)
            self.log.record("login_fail", account=account.user,
                            detail=f"重登失败 {self._login_failures} 次，"
                                   f"{delay.total_seconds():.0f}s 后再试")

    # ---- 切房 ----

    async def _maybe_switch_room(self) -> None:
        if self.runtime is None or not self.cadence.due():
            return
        account = self.relay.active
        last = self.registry.last_room(account.user)
        room = pick_room(self.config.rooms, last_room=last, rng=random.Random())
        if room is None:
            self.cadence.advance()
            return
        try:
            await self.runtime.switch_room(room)
        except Exception:  # noqa: BLE001 - 单次点击失败只顺延节奏（mx_activity 同语义）
            self.log.record("room_switch", account=account.user,
                            detail=f"点击 {room} 失败，顺延节奏")
        else:
            self.registry.set_last_room(account.user, room)
            self.log.record("room_switch", account=account.user, detail=f"点开 {room}")
        self.cadence.advance()

    # ---- 主循环 ----

    async def _tick(self, *, now: datetime) -> None:
        windows = self._plan_windows(now)
        was_open = self.runner.window_open
        self.runner.tick(now=now, windows=windows)
        now_open = self.runner.window_open
        if now_open and not was_open:
            await self._open_window(self.relay.active, now=now)
        elif not now_open and was_open:
            await self._close_window(now=now)
        if now_open:
            await self._ensure_session()
            await self._maybe_switch_room()

    async def run(self) -> None:
        """常驻循环：30s tick，异常兜底记日志继续（不退出）。"""
        self.log.record("agent_start", account=None,
                        detail=f"行为器启动 账号数={len(self.config.accounts)}")
        while True:
            try:
                await self._tick(now=datetime.now(CN_TZ))
            except asyncio.CancelledError:
                if self.runtime is not None:
                    await self.runtime.stop()
                raise
            except Exception:  # noqa: BLE001 - 挂死比异常循环更糟
                logger.exception("行为器 tick 异常")
            await asyncio.sleep(TICK_SECONDS)

    # ---- 工具 ----

    @staticmethod
    def _chrome_exe() -> str:
        """专用 Chrome 可执行文件：环境变量 > Playwright Chromium > 系统 Chrome。

        前提（ADR-0001）：干净启动的 branded Chrome；Playwright 自带
        Chromium 是开发/验收用回落（branded Chrome 137+ 不认 --load-extension
        只影响扩展安装，不影响 agent 的行为面）。
        """
        override = (os.environ.get("MX_AGENT_CHROME_EXE") or "").strip()
        if override:
            return override
        cands = sorted(glob.glob(os.path.expanduser(
            "~/AppData/Local/ms-playwright/chromium-*/chrome-win64/chrome.exe")),
            reverse=True)
        if cands:
            return cands[0]
        return "chrome"  # PATH 兜底（POSIX 形态；Windows 一般走前两者）