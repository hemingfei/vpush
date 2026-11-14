"""行为器浏览器运行时：真浏览器链路（开/关 Chrome、connect、seed、点击、登录）。

**不进 CI**（spec 裁定：真实浏览器链路由 48h 挂机验收覆盖）——本模块把
可单测的纯逻辑（executor 参数构造/cadence/relay/login pacer）接到
Playwright connect-over-CDP 的真实执行上：

- 进程启动协议复用 spike Phase B 先例（spike_dual_debugger.py:281-316）：
  subprocess 干净启动 → 看门狗轮询调试端口 → connect_over_cdp 附着；
- seed 免登：localStorage 五键 + reload + 等首页（mx_room_switch_capture
  .py:88-100 实测键集）；
- 登录：mx_login.run_login_flow（AI 视觉识码 ocr_fn 走 ai_ocr 无人值守）；
- 点击切房：点房间名 strong、回落头像区（isTrusted=true，spike Phase A
  实证；Playwright click 即 CDP Input 域派发）。

agent 是行为决策者，本模块零决策——决策全部来自 runner（窗口/接力/节奏）。
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from pathlib import Path

from .executor import CDPExecutor, wait_cdp_port_open

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent


class BrowserRuntime:
    """一个活跃账号一个运行时实例：Chrome 进程 + CDP 会话 + 页面动作。

    生命周期由 agent.runner 驱动：start()（开窗）/ stop()（关窗）；
    ensure_logged_in() 幂等——seed 已登录直接过，掉登录态走重登链路。
    """

    def __init__(self, *, executor: CDPExecutor, account_user: str,
                 token: str | None):
        self.executor = executor
        self.account_user = account_user
        self._token = token
        self._proc: subprocess.Popen | None = None
        self._pw = None
        self._browser = None
        self._page = None

    # ---- 进程与会话 ----

    def _spawn_chrome(self, err_path: Path) -> subprocess.Popen:
        """干净启动专用 Chrome（阻塞调用，经 to_thread 执行）。

        stderr 落盘 profile 目录：启动即退时看门狗能报死因（spike 先例）。
        句柄交给子进程后由本对象生命周期管理，stop() 里 terminate 收口。
        """
        return subprocess.Popen(
            self.executor.launch_args(),
            stderr=open(err_path, "wb"),  # noqa: SIM115 - 句柄归子进程持有
            stdout=open(err_path, "wb"),   # noqa: SIM115 - 同上
        )

    async def start(self) -> None:
        """干净启动专用 Chrome + connect_over_cdp 附着（spike 先例全链路）。"""
        if self._proc is not None:
            return
        self.executor.user_data_dir.mkdir(parents=True, exist_ok=True)
        err_path = self.executor.user_data_dir / "chrome_stderr.log"
        # Popen + stderr 落盘都是阻塞调用，移出事件循环（spike 脚本无此约束，
        # agent 是常驻 async 进程——启动期 0.5s 量级阻塞不该卡掉切房节奏）
        self._proc = await asyncio.to_thread(self._spawn_chrome, err_path)

        import socket

        def _connect(port: int) -> None:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return

        ok = await asyncio.to_thread(
            wait_cdp_port_open,
            port=self.executor.cdp_port,
            timeout_seconds=15.0,
            sleep=time.sleep,
            connect=_connect,
            process_poll=lambda: self._proc.poll() if self._proc else -1,
        )
        if not ok:
            await self.stop()
            tail = ""
            try:
                tail = err_path.read_bytes()[-2000:].decode("utf-8", "replace")
            except OSError:
                pass
            raise RuntimeError(f"Chrome 启动失败（CDP 端口未监听）stderr 尾部：{tail}")

        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.connect_over_cdp(
            self.executor.endpoint_url()
        )
        ctx = self._browser.contexts[0]
        self._page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    async def stop(self) -> None:
        """关浏览器（窗口结束/接力下线）；进程与 CDP 会话一并收。"""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:  # noqa: BLE001 - 关闭尽力而为
                logger.warning("CDP 会话关闭失败", exc_info=True)
            self._browser = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:  # noqa: BLE001 - 关闭尽力而为
                logger.debug("playwright 驱动关闭失败", exc_info=True)
            self._pw = None
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None
        self._page = None

    # ---- 登录链路 ----

    async def ensure_logged_in(self, *, account: str, password: str) -> bool:
        """seed 免登 → 失败走 mx_login 全自动重登（AI 视觉识码）。

        返回 True=会话可用。密码只经内存传递，异常/日志不得带出。
        """
        page = self._page
        if page is None:
            return False
        await page.goto(self.executor.origin, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        # profile seed 免登（已有 token 时首选路径）
        if self._token:
            from .executor import seed_storage_script

            await page.evaluate(seed_storage_script(), [self._token, account])
            await page.reload(wait_until="domcontentloaded")
            try:
                await page.wait_for_selector("text=直播间", timeout=30000)
                return True
            except Exception:  # noqa: BLE001 - seed 失效走重登
                logger.info("MX profile seed 免登失败，走重登链路 account=%s", account)
        return await self._login_with_ai(account, password)

    async def _login_with_ai(self, account: str, password: str) -> bool:
        """mx_login 全自动重登：run_login_flow 重试循环 + AI 视觉识码。

        ocr_fn 直调 vision_read_text 走普通 httpx（spike Phase B 先例：
        本机 Ark 域名 IPv4 直连被 user_supplied 安全体 400，关掉 IP 固定体）。
        """
        from app.fetchers.mx.client import MXClient
        from scripts.mx_login import (
            ai_ocr,
            api_base_of,
            run_login_flow,
            vision_configured,
        )

        if not (account and password):
            logger.error("MX 登录缺凭据 account=%s", account)
            return False
        if not vision_configured():
            logger.error("视觉识码未配置（MX_VISION_* 或 LLM_* 缺失）")
            return False
        client = MXClient(api_base_of(self.executor.origin), "")
        try:
            result = await asyncio.to_thread(
                run_login_flow, client, account, password,
                attempts=5, no_prompt=True, ocr_fn=ai_ocr,
            )
        finally:
            client.close()
        self._token = result.get("token") or ""
        return bool(self._token)

    @property
    def token(self) -> str | None:
        """当前会话 token（runner 在登录成功后回写注册表）。"""
        return self._token

    # ---- 行为动作 ----

    async def switch_room(self, room_name: str) -> None:
        """真点击切房间：点房间名 strong，回落头像区（选择器先例
        scripts/mx_room_switch_capture.py:126-143 open_room）。"""
        import re

        page = self._page
        if page is None:
            raise RuntimeError("浏览器会话未建立")
        item = page.get_by_role("button", name=re.compile(f"^{re.escape(room_name)}")).first
        if await item.count() == 0:
            raise RuntimeError(f"房间列表里没找到：{room_name}")
        try:
            await item.locator(CDPExecutor.ROOM_STRONG_SELECTOR).first.click(timeout=3000)
        except Exception:  # noqa: BLE001 - 无 strong 点头像区
            await item.click(position=CDPExecutor.FALLBACK_CLICK_OFFSET)
