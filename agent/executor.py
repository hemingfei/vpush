"""CDPExecutor：行为器的浏览器执行器抽象（票 #17 交付物 ①）。

主路径（spec #14 Implementation Decisions）：connect-over-CDP 连「干净启动」
的专用 Chrome——独立 user-data-dir + 独立调试端口，**不带 --enable-automation**
（ADR-0001 否决纯 CDP agent 方案的理由正是 Playwright/ChromeDriver 的自动化
痕迹常驻；干净启动的 branded Chrome 对平台呈现的就是日常浏览器）。

切房点击用 CDP Input 域（Playwright click 即 CDP Input.dispatchMouseEvent，
isTrusted=true 已由 spike Phase A 实证）。浏览器先起进程、看门狗轮询调试
端口，再 connect_over_cdp 附着——启动协议复用 spike Phase B 先例
（spike_dual_debugger.py:281-316）。

seed 免登：登录 token 写 localStorage 五键 + reload + 等首页（
scripts/mx_room_switch_capture.py:88-100 抓包实测键集）。

本模块只做「可单测的纯部分」（参数/URL/脚本构造）——真浏览器链路不进
CI（48h 挂机验收覆盖），异步运行时挂在 executor.runtime 之外按需导入，
避免纯逻辑测试背上 playwright 导入面。
"""
from __future__ import annotations

from pathlib import Path


def cdp_endpoint_url(port: int) -> str:
    """connect_over_cdp 的端点 URL（本机环回；spike 先例 http://127.0.0.1:<port>）。"""
    return f"http://127.0.0.1:{port}"


def chrome_launch_args(
    *,
    exe: str,
    user_data_dir: Path,
    cdp_port: int,
    origin: str,
) -> list[str]:
    """干净启动参数：专用 profile + CDP 端口 + MX 首页，零自动化痕迹。

    红线（锁在 tests/test_agent_executor.py）：不加 --enable-automation、
    --headless、--remote-allow-origins、--disable-blink-features=AutomationControlled
    ——这些正是「云端伪装成浏览器」时代被风控盯上的指纹（ADR-0001）。
    """
    return [
        exe,
        f"--user-data-dir={user_data_dir}",
        f"--remote-debugging-port={cdp_port}",
        "--no-first-run",
        "--no-default-browser-check",
        origin,
    ]


def seed_storage_script() -> str:
    """profile seed 免登的 page.evaluate 脚本（可单测的字符串构造）。

    键集来自 scripts/mx_room_switch_capture.py:88-100 抓包实测——官方
    「关窗重开自动登录」读取的 localStorage 最小集；写完由调用方 reload
    并等待首页（"text=直播间"）。
    """
    return """([token, user]) => {
      localStorage.setItem('mx_web_token', JSON.stringify(token));
      localStorage.setItem('mx_web_hosturl', JSON.stringify('/business-api/5'));
      localStorage.setItem('mx_web_raw_hosturl', JSON.stringify('/5'));
      localStorage.setItem('mx_web_login_account', JSON.stringify({ user }));
      localStorage.setItem('mx_web_dark_mode', 'false');
    }"""


def wait_cdp_port_open(*, port: int, timeout_seconds: float,
                       sleep, connect, process_poll,
                       host: str = "127.0.0.1") -> bool:
    """启动看门狗：轮询调试端口直至监听（spike_dual_debugger.py:294-316 先例）。

    参数全部注入（sleep/connect/poll），可纯单测/复现脚本复用：
    - sleep(seconds)；connect(port) → 成功返回、失败抛 OSError 的回调；
    - process_poll() → 浏览器进程退出码（None=存活）。
    进程退出立即返回 False（启动即退，不用等满超时）。
    """
    deadline = timeout_seconds
    waited = 0.0
    while waited < deadline:
        sleep(0.5)
        waited += 0.5
        if process_poll() is not None:
            return False  # 浏览器启动即退：不再等
        try:
            connect(port)
            return True
        except OSError:
            continue
    return False


class CDPExecutor:
    """一个账号一个执行器实例：进程 + connect_over_cdp 会话 + 页面动作。

    真浏览器链路（launch/watchdog/connect/seed/click）不进 CI——本类的
    异步方法按需导入 playwright（agent 运行时才引入，纯逻辑测试不触发）。
    """

    # 真点击选择器先例（scripts/mx_room_switch_capture.py:126-143 open_room）：
    # 点房间条目内部的 <strong>（房间名文本），避开列表中部的 AI 按钮；
    # 无 strong 回落点条目左上头像区
    ROOM_STRONG_SELECTOR = "strong"
    FALLBACK_CLICK_OFFSET = {"x": 40, "y": 20}

    def __init__(self, *, exe: str, user_data_dir: Path, cdp_port: int, origin: str):
        self.exe = exe
        self.user_data_dir = Path(user_data_dir)
        self.cdp_port = cdp_port
        self.origin = origin.rstrip("/")
        self._proc = None
        self._browser = None

    # ---- 纯构造面（可单测） ----

    def launch_args(self) -> list[str]:
        return chrome_launch_args(
            exe=self.exe,
            user_data_dir=self.user_data_dir,
            cdp_port=self.cdp_port,
            origin=self.origin,
        )

    def endpoint_url(self) -> str:
        return cdp_endpoint_url(self.cdp_port)
