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
from datetime import datetime, time as dt_time, timedelta

from app.services.mx_window import CN_TZ, build_daily_plan, restart_login_allowed

from .accounts import Account, AccountRegistry
from .browser import BrowserRuntime
from .cadence import RoomCadence, pick_room
from .config import AgentConfig
from .daily_plan import get_today_plan
from .executor import CDPExecutor
from .lifecycle import LifecycleLog
from .login import FATAL_LOGIN_MARKERS, LoginRetryPacer, _is_fatal, relogin_needed
from .relay import RelayStateMachine
from .reload_cadence import ReloadCadence
from .window_runner import WindowRunner

logger = logging.getLogger(__name__)

# 循环节奏与云端 _mx_window_loop 同频（30s tick）
TICK_SECONDS = 30.0


def _fatal_mark(exc: BaseException) -> str:
    """致命错误特征标记（日志用；只取命中词，不带异常原文以外的信息）。"""
    text = str(exc)
    return next((m for m in FATAL_LOGIN_MARKERS if m in text), "fatal")


def _combine_hm(day, hhmm: str, tzinfo):
    """当日 "HH:MM" → aware datetime（自定义窗口解析；坏值返回 None）。"""
    try:
        hour, minute = (int(p) for p in hhmm.split(":"))
        return datetime.combine(day, dt_time(hour, minute), tzinfo=tzinfo)
    except ValueError:
        return None


class AgentRunner:
    """常驻行为器：一个循环驱动窗口/登录/接力/切房全生命周期。"""

    def __init__(self, config: AgentConfig, *, log: LifecycleLog,
                 registry: AccountRegistry | None = None,
                 runtime_factory=None):
        self.config = config
        self.log = log
        self.registry = registry or config.registry()
        self.relay = RelayStateMachine(
            config.accounts,
            on_switch=self._on_relay_switch,
        )
        # always_on 全天窗起点 00:00 必然 start<now：arm_windows 会判「错过」，
        # 必须借 restart_login 的重武装语义让全天窗任何时刻重启都开窗
        # （用户主动打开软件=要监听，这是 always_on 的存在理由）。
        # 自定义窗口同理：打开软件时正处自定义窗内 → 立即在线（否则重启
        # 后整段窗口报废，违背「主动打开也要能监听」的需求原点）。
        # 默认窗口维持云端口径：仅工作日 08-22 重启才补登。
        self._restart_login = (self.config.always_on
                               or self.config.windows is not None
                               or restart_login_allowed(datetime.now(CN_TZ)))
        self.runner = WindowRunner(
            on_window_open=lambda now: None,   # 异步动作在 _tick 里由 decision 驱动
            on_window_close=lambda now: None,
            on_new_day=self._on_new_day,
            restart_login=self._restart_login,
        )
        self.cadence = RoomCadence()
        # 周期页面刷新（票 #23 防线一）：随机 50-90min reload 重建页面 WS，
        # 扩展侧静默看门狗（3-10min 阈值）之外的第二道防线。开窗时重新
        # 构造=新窗口首次刷新落在随机间隔后（不开窗即到点的假到期）。
        self.reload_cadence = ReloadCadence()
        self.pacer = LoginRetryPacer()
        self.runtime: BrowserRuntime | None = None
        # BrowserRuntime 工厂（S2 接力换 profile 用）：签名 (account_user, token)
        # → BrowserRuntime。缺省 = 生产实现（CDPExecutor + 专属 profile），
        # 测试注入桩以离线驱动换 profile 顺序断言。
        self._runtime_factory = runtime_factory or self._make_runtime
        self._login_failures = 0
        self._next_relogin_at: float | None = None
        self._last_login_error: BaseException | None = None

    def _make_runtime(self, account_user: str, token: str | None) -> BrowserRuntime:
        """生产运行时构造：一个账号一个 CDPExecutor（专属 profile，ADR-0001）。"""
        executor = CDPExecutor(
            exe=self._chrome_exe(),
            user_data_dir=self.registry.profile_dir(account_user),
            cdp_port=self.config.cdp_port,
            origin=self.config.origin,
        )
        return BrowserRuntime(executor=executor, account_user=account_user,
                              token=token)

    # ---- 日志回调（生命周期事件统一落点） ----

    def _on_relay_switch(self, kind: str, account: Account) -> None:
        """接力切换：换 profile 重开会话（S2——切换不再只记日志）。

        中途换 profile 序列（两账号不并行在线的结构保证，ADR-0001）：
        1. 关当前浏览器（在线的旧账号随浏览器退出，先下线）；
        2. 用新活跃账号的专属 profile 起新浏览器；
        3. 对新账号跑登录链路（seed 免登 → 失效重登）；
        4. 续窗：切房节奏重新武装（会话开启即武装的口径同 _open_window）。

        窗口没开时（如开窗登录失败引发的切换）只做 1-2 的「清场」——
        下次 tick 的开窗动作自然用新活跃账号。swap 中途失败降级：
        运行时清空 + relay_swap_error 记档，状态机活跃位不动（决策一致性
        由状态机保证），下次开窗按活跃账号重试。
        """
        self.log.record("relay_switch", account=account.user,
                        detail=f"{kind} → 活跃账号 {account.user}")
        asyncio.get_event_loop().create_task(self._swap_runtime(account))

    async def _swap_runtime(self, account: Account) -> None:
        """执行一次换 profile（_on_relay_switch 的异步体；异常全兜底）。"""
        try:
            if self.runtime is not None:
                old = self.runtime
                self.runtime = None
                await old.stop()  # 先关旧：旧账号先下线，绝不并行在线
            if not self.runner.window_open:
                # 窗口未开（开窗失败引发的切换）：无会话可续，清场即完成
                return
            rt = self._runtime_factory(account.user, self.registry.token(account.user))
            await rt.start()
            ok = await rt.ensure_logged_in(
                account=account.user,
                password=self.config.password_of(account),
            )
            if ok and rt.token:
                self.registry.set_token(account.user, rt.token, updated_at=time.time())
                self.log.record("login_ok", account=account.user,
                                detail="接力换 profile 后登录成功")
            else:
                self._login_failures += 1
                self.relay.report_login(account.user, ok=False)
                self.log.record("login_fail", account=account.user,
                                detail=f"换 profile 后登录失败 "
                                       f"{self._login_failures} 次，接力切换评估")
            self.runtime = rt
            self.cadence = RoomCadence()  # 新会话开启即武装
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - swap 失败降级：清空运行时等下次开窗
            self.runtime = None
            logger.exception("接力换 profile 失败 account=%s", account.user)
            self.log.record("relay_swap_error", account=account.user,
                            detail="换 profile 中途失败，运行时已清空待下次开窗")

    def _on_new_day(self, day) -> None:
        # 日切：接力回卷主账号 + 计划重建（WindowRunner 的下一 tick 读新窗口）
        self.relay.new_day()
        self.log.record("new_day_reset", account=self.relay.active.user,
                        detail=f"{day} 计划重建，回卷主账号")

    # ---- 窗口动作（tick 决策驱动的异步执行） ----

    def _plan_windows(self, now: datetime):
        """当日窗口：三态（优先级 always_on > 自定义窗口 > 默认三段随机窗）。

        - always_on（MX_AGENT_ALWAYS_ON=1）：全天单窗——用户主动打开软件
          就要能监听，窗口调度整体旁路（开窗即登录在线，关进程才下线）；
        - 自定义窗口（MX_AGENT_WINDOWS）：确定性解析成当日 datetime 对，
          不走计划文件（env 即事实源，当日形状天然不漂移）；
        - 默认：当日计划（计划文件持久化，重启不漂移，既有语义零改动）。
        """
        if self.config.always_on:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            return [(day_start, day_end)]
        if self.config.windows:
            day = now.date()
            windows = []
            for start_hm, stop_hm in self.config.windows:
                start = _combine_hm(day, start_hm, now.tzinfo)
                stop = _combine_hm(day, stop_hm, now.tzinfo)
                if start is not None and stop is not None:
                    windows.append((start, stop))
            if windows:
                return windows
            # 全部解析失败不该发生（config 层已词法校验）：落回默认计划
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
        rt = self._runtime_factory(account.user, self.registry.token(account.user))
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
        self.reload_cadence = ReloadCadence()  # 新窗口首次刷新落在随机间隔后

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
        """窗口开着但会话掉登录态 → 按 pacer 节奏重登（不硬轰不断采）。

        探针（S6）：CDP Runtime.evaluate 读 seed 的 localStorage 登录键
        （BrowserRuntime.probe_session——presence + 非空）。token 在但页面
        已被登出（互踢/会话过期）时键被清，探针判死触发中段重登；CDP
        报错视同失效（保守侧在重登链路，relogin_needed 的 error 分支）。
        """
        if self.runtime is None:
            return
        account = self.relay.active
        probe = await self._probe_session()
        if not relogin_needed(probe):
            return
        now_mono = time.monotonic()
        if self._next_relogin_at is not None and now_mono < self._next_relogin_at:
            return  # 退避窗口未到
        # CDP 会话已死（浏览器进程被杀/崩溃）时，在死页面上重试登录只会
        # 永远失败——浏览器进程必须重建。旧 runtime 收尸置 None，下一 tick
        # 走「窗内无运行时补开」路径拉起新 Chrome（_tick 的补开分支）。
        if probe.get("error") is not None:
            dead = self.runtime
            self.runtime = None
            await dead.stop()
            self._next_relogin_at = None  # 补开即全新登录链路，清掉退避
            self.log.record("browser_rebuild", account=account.user,
                            detail="CDP 会话失效，重建浏览器")
            return
        try:
            ok = await self.runtime.ensure_logged_in(
                account=account.user, password=self.config.password_of(account))
        except Exception as exc:  # noqa: BLE001 - 登录链路异常也要走失败分支
            ok = False
            self._last_login_error = exc
        else:
            self._last_login_error = probe.get("error")
        if ok and self.runtime.token:
            self.registry.set_token(account.user, self.runtime.token,
                                    updated_at=time.time())
            self._login_failures = 0
            self._next_relogin_at = None
            self.log.record("login_ok", account=account.user, detail="重登成功")
        else:
            self._login_failures += 1
            # 致命登录错误（密码错/锁定/封禁——login._is_fatal）不硬轰：
            # 不排退避、直接报给接力状态机切备用账号（等人工处置的是
            # 备用也致命时——状态机沿清单顺延，不会停在无账号）
            err = self._last_login_error
            if err is not None and _is_fatal(err):
                self.relay.report_login(account.user, ok=False)
                self.log.record("login_fail", account=account.user,
                                detail=f"致命登录错误（{_fatal_mark(err)}），"
                                       "跳过重试节奏，接力切换评估")
                return
            delay = self.pacer.next_retry_delay(
                now=datetime.now(CN_TZ), consecutive_failures=self._login_failures)
            self._next_relogin_at = now_mono + delay.total_seconds()
            self.relay.report_login(account.user, ok=False)
            self.log.record("login_fail", account=account.user,
                            detail=f"重登失败 {self._login_failures} 次，"
                                   f"{delay.total_seconds():.0f}s 后再试")

    async def _probe_session(self) -> dict:
        """探针收敛点：runtime 有 CDP 探针用它；异常视同失效（alive=False
        + error），交给 relogin_needed 的既有 error 分支。"""
        if self.runtime is None:
            return {"alive": False, "error": None}
        try:
            return await self.runtime.probe_session()
        except Exception as exc:  # noqa: BLE001 - CDP 探针报错按失效处理
            return {"alive": False, "error": exc}

    # ---- 切房 ----

    async def _maybe_reload_page(self) -> None:
        """到点刷新页面（票 #23 防线一）：随机 50-90min reload 重建页面 WS。

        单次失败只顺延节奏（与切房同语义）——reload 失败大概率是 CDP/
        页面状态问题，_ensure_session 的探针/重登链路会另行处理。
        """
        if self.runtime is None or not self.reload_cadence.due():
            return
        account = self.relay.active
        try:
            await self.runtime.reload_page()
        except Exception:  # noqa: BLE001 - 失败顺延，下周期再试
            self.log.record("page_reload", account=account.user,
                            detail="刷新失败，顺延节奏")
        else:
            self.log.record("page_reload", account=account.user,
                            detail=f"周期刷新完成（下轮 {self.reload_cadence.next_fire_in():.0f}s 后）")
        self.reload_cadence.advance()

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
        except Exception:  # noqa: BLE001 - 单次点击失败只顺延节奏（原 mx_activity 同语义）
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
            # 开窗动作中途失败（如 Chrome 启动异常）时 runtime 为 None 而
            # window_open 已翻转 True——只靠 _ensure_session 会永久短路
            # （runtime None 直接 return），会话卡死到出窗。此处补开：
            # 「上一 tick 就已开窗但至今无运行时」（was_open=True）= 开窗
            # 失败后的恢复路径；刚翻转的 tick（was_open=False）不补，由
            # _open_window 自身的结果处理负责。
            if self.runtime is None and was_open:
                await self._open_window(self.relay.active, now=now)
            await self._ensure_session()
            await self._maybe_reload_page()
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