#!/usr/bin/env python3
r"""MX collector guard: keep the collector host browser alive (#22 宿主守护).

The collector (MV3 extension) lives **inside** a browser: browser dead =
collection dead. This guard mirrors scripts/mx_agent_guard.py (the agent
process guard): schtasks fires it every minute, idempotently ensuring the
dedicated collector host Chromium is up. 手动关浏览器/电脑重启后 <=60s 内
采集自愈（配对态存 chrome.storage.local，持久 profile 复用，无需重新配对）。

会话裁定（#22 待决事项落地时必须记录）：issue #22 曾倾向「自托管 CRX +
组策略 force-install」作长期形态——**被否决**：CRX/组策略 force-install
会把 debugger 扩展装进运营者的**日常浏览器**，违背 ADR-0001 的「专用
实例，不碰日常浏览器」红线。可长期存续的形态是**专用 Playwright
Chromium 宿主**（持久 profile + --load-extension），平台已实证接受——
真实 MX 会话在该宿主上连跑数日（2026-11-15 E2E）。branded Chrome 137+
删了 --load-extension 正好不构成回归理由：本宿主本来就不用 branded
Chrome 的日常 profile。

Manual recovery recipe (proven 2026-11-15; profile checked in as
.scratch/mx-collector-profile — gitignored, local only):
    Playwright Chromium + --load-extension=extension/ + persistent profile
    .scratch/mx-collector-profile + --remote-debugging-port=9223 + open MX
    homepage. Pairing state (device key/seq/buffer) persists in the
    profile's chrome.storage.local — restart reuses it, no re-pairing.

Tick semantics (mirror mx_agent_guard: enumerate nothing, hard facts only):
    ① agent lock held = agent owns 9223 (its OWN branded Chrome or an
       adopted foreign Chrome) → guard exits tick doing NOTHING (agent's
       domain; killing/competing would break the browser_open flow).
    ② agent lock free + CDP probe: port open AND a target
       chrome-extension://*/sw.js exists → collector host healthy, done.
    ③ agent lock free + port closed → spawn collector host (idempotent).
    ④ agent lock free + port open but NO unpacked sw.js target → foreign
       Chrome (pytest residue / daily browser / half-dead stranger):
       log a structured warning, DO NOT kill (never touch foreign
       browsers — the 2026-11-15 incident taught exactly that), exit tick.
    ⑤ healthy browser but no page target matches the origin → log warning
       only (agent's browser_open flow reopens MX pages on its window
       ticks anyway; guard only guarantees the host process, per #22).

Config (env; .env loaded first, mx_agent.py:445 先例):
    MX_COLLECTOR_CHROME_EXE     browser exe override (default: newest
                                Playwright Chromium, agent.runner 先例)
    MX_COLLECTOR_PROFILE_DIR    persistent profile dir
                                (default .scratch/mx-collector-profile)
    MX_COLLECTOR_EXTENSION_DIR unpacked extension dir (default extension/)
    MX_COLLECTOR_ORIGIN         MX homepage opened at spawn
                                (default MX_LOGIN_ORIGIN / agent DEFAULT_ORIGIN)
    MX_COLLECTOR_CDP_PORT       CDP port (default 9223, same as agent —
                                adopt 语义: 切房与采集同一浏览器)

Task registration (one-time, mirrors MXAgentGuard):
    schtasks /Create /TN "MXCollectorGuard" /SC MINUTE /MO 1 ^
        /TR "wscript.exe \"C:\Users\hemin\Documents\vpush\scripts\mx_collector_guard.vbs\"" /F
Boot startup is covered by the 1-minute cadence (first tick <= 60s after
logon); .vbs keeps the console hidden (pythonw).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "data" / "collector_guard.log"
STDOUT_LOG = REPO / "data" / "collector_stdout.log"
AGENT_LOCK = REPO / "data" / "agent" / "agent.lock"

DEFAULT_PROFILE_DIR = REPO / ".scratch" / "mx-collector-profile"
DEFAULT_EXTENSION_DIR = REPO / "extension"
DEFAULT_CDP_PORT = 9223
DEFAULT_ORIGIN = "https://mx.2026.foodtop1.com"  # agent.config 同源默认
PROBE_TIMEOUT_SECONDS = 2.0


@dataclass
class CollectorConfig:
    """Guard 配置（纯环境变量派生，mx_agent.py 先例；默认即手动恢复配方）。"""

    chrome_exe: str
    profile_dir: Path
    extension_dir: Path
    origin: str
    cdp_port: int

    def launch_args(self) -> list[str]:
        """启动参数 = 手动恢复配方原样（关键不变式在 tests 锁定）。

        红线（与 agent.executor.chrome_launch_args 同口径）：绝不加
        --enable-automation/--headless——本宿主对平台呈现的就是一台普通
        桌面 Chromium，配对态又活在 profile 里，自动化痕迹没有存在理由。
        """
        return [
            self.chrome_exe,
            f"--user-data-dir={self.profile_dir}",
            f"--remote-debugging-port={self.cdp_port}",
            f"--load-extension={self.extension_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
            self.origin,
        ]


def load_collector_config() -> CollectorConfig:
    """从环境变量组装配置（.env 由 main 先 load_dotenv）。"""
    return CollectorConfig(
        chrome_exe=(
            os.environ.get("MX_COLLECTOR_CHROME_EXE", "").strip()
            or _default_chrome_exe()
        ),
        profile_dir=Path(
            os.environ.get("MX_COLLECTOR_PROFILE_DIR", "").strip()
            or DEFAULT_PROFILE_DIR
        ),
        extension_dir=Path(
            os.environ.get("MX_COLLECTOR_EXTENSION_DIR", "").strip()
            or DEFAULT_EXTENSION_DIR
        ),
        origin=(
            os.environ.get("MX_COLLECTOR_ORIGIN", "").strip().rstrip("/")
            or os.environ.get("MX_LOGIN_ORIGIN", "").strip().rstrip("/")
            or DEFAULT_ORIGIN
        ),
        cdp_port=_parse_port(os.environ.get("MX_COLLECTOR_CDP_PORT", "")),
    )


def _parse_port(raw: str) -> int:
    try:
        return int(raw.strip()) if raw.strip() else DEFAULT_CDP_PORT
    except ValueError:
        return DEFAULT_CDP_PORT


def _default_chrome_exe() -> str:
    """Playwright Chromium 探测（agent.runner._chrome_exe 先例，无 env 时）。

    会话裁定：宿主用 Playwright Chromium 而非 branded Chrome——
    --load-extension 在 branded 137+ 已删，且 CRX/组策略路线被否决
    （会把 debugger 扩展装进日常浏览器，违 ADR-0001 专用实例红线）。
    """
    cands = sorted(
        glob.glob(
            os.path.expanduser(
                "~/AppData/Local/ms-playwright/chromium-*/chrome-win64/chrome.exe"
            )
        ),
        reverse=True,
    )
    if cands:
        return cands[0]
    return "chrome"  # PATH 兜底（POSIX 形态；Windows 一般走 Playwright）


def _cdp_targets(port: int, fetch) -> list[dict]:
    """/json/list 目标清单（fetch 注入可测；失败=清单空，按端口不通语义处理）。"""
    try:
        text = fetch(
            f"http://127.0.0.1:{port}/json/list", timeout=PROBE_TIMEOUT_SECONDS
        )
        targets = json.loads(text)
        return [t for t in targets if isinstance(t, dict)]
    except (OSError, ValueError, urllib.error.URLError):
        return []


def _is_collector_target(target: dict) -> bool:
    """目标是否我们的采集器 SW：任何 chrome-extension://…/sw.js 即是。

    不硬编码扩展 ID（unpacked 扩展 ID 随机器/路径漂移）；branded 日常
    Chrome 绝不会出现 unpacked sw.js 目标——这是宿主归属的最简可靠判据。
    """
    url = target.get("url", "")
    return url.startswith("chrome-extension://") and url.endswith("/sw.js")


def probe_health(*, config: CollectorConfig, fetch) -> dict:
    """健康分类（纯逻辑，注入 fetch 可离线测试）。

    返回 {"kind": healthy|foreign|port_closed|mx_tab_missing, "targets":…}：
    - healthy         端口通 + 有我们的 sw.js 目标（MX 标签缺失时顺带报
                      mx_tab_missing 提示——不影响 healthy 语义，agent 的
                      browser_open 流自会开页，本守护只保宿主进程，#22）；
    - foreign         端口通但没有 sw.js 目标 = 异种 Chrome（pytest 残留/
                      agent 专属 branded Chrome/日常浏览器）——绝不动它，
                      只记结构化告警（2026-11-15 事故教训：误判动手才是
                      最大风险）；agent 活着时 9223 归它管，同理不动；
    - port_closed     端口不通（fetch 报错）→ 该拉起。
    """
    targets = _cdp_targets(config.cdp_port, fetch)
    if not targets:
        # 空清单可能来自「端口压根不通」——调用方拿到 port_closed。
        return {"kind": "port_closed", "targets": []}
    if not any(_is_collector_target(t) for t in targets):
        return {"kind": "foreign", "targets": targets}
    if not any(str(t.get("url", "")).startswith(config.origin) for t in targets):
        # 宿主健康但 MX 页没了：只告警不代开（保进程是本守护边界；开页
        # 归 agent 窗口流/browser_open，职责不越界，ticket 裁定 keep simple）
        return {"kind": "mx_tab_missing", "targets": targets}
    return {"kind": "healthy", "targets": targets}


def agent_owns_port() -> bool:
    """agent 单实例锁被活进程持有 = 9223 归 agent 管。

    判定复用 agent.single_instance.lock_is_taken（与 agent 抢锁同一套
    生死判定，97bf917 已跨平台）；锁文件在但判定异常按「agent 在」处理
    —— 宁不动勿抢端口（mx_agent_guard 同保守侧）。
    """
    if not AGENT_LOCK.exists():
        return False
    from agent.single_instance import lock_is_taken

    try:
        return lock_is_taken(AGENT_LOCK)
    except Exception:
        return True


def spawn_collector(config: CollectorConfig) -> None:
    """Detached 启动采集宿主（stdout/stderr 追加 collector_stdout.log）。"""
    DETACHED = 0x00000008 | 0x00000200
    log_h = open(STDOUT_LOG, "ab")  # noqa: SIM115 - 句柄归 DETACHED 子进程持有
    try:
        subprocess.Popen(
            config.launch_args(),
            cwd=str(REPO),
            stdout=log_h,
            stderr=subprocess.STDOUT,
            creationflags=DETACHED,
        )
    finally:
        log_h.close()
    _log(f"spawned port={config.cdp_port} profile={config.profile_dir}")


def _fetch(url: str, timeout: float) -> str:
    """生产 fetch：urllib 同步抓取（CDP 本机环回，无需凭据）。"""
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def tick(config: CollectorConfig | None = None, *, fetch=_fetch) -> dict:
    """单次守护决策（幂等；返回决策供 --validate/测试断言）。"""
    config = config or load_collector_config()
    if agent_owns_port():
        _log("agent holds 9223 — collector host not managed this tick")
        return {"kind": "agent_owns_port", "spawned": False}
    health = probe_health(config=config, fetch=fetch)
    kind = health["kind"]
    if kind == "healthy":
        return {"kind": "healthy", "spawned": False}
    if kind == "mx_tab_missing":
        # 宿主进程活着即可：MX 页由 agent browser_open 流维护（#22 裁定）
        _log(
            "WARN: collector host up but no MX tab "
            f"(origin={config.origin}) — agent browser_open will reopen"
        )
        return {"kind": "mx_tab_missing", "spawned": False}
    if kind == "foreign":
        _log(
            f"WARN: port {config.cdp_port} held by a non-collector Chrome "
            "(no unpacked sw.js target) — not touching (agent/foreign "
            "browser domain)"
        )
        return {"kind": "foreign", "spawned": False}
    spawn_collector(config)
    return {"kind": "port_closed", "spawned": True}


def _validate() -> int:
    """本地自检：配置/参数/锁判定干跑，不真起浏览器（mx_agent_validate 精神）。"""
    config = load_collector_config()
    print(f"chrome_exe={config.chrome_exe}")
    print(f"profile_dir={config.profile_dir}")
    print(f"extension_dir={config.extension_dir}")
    print(f"origin={config.origin}")
    print(f"cdp_port={config.cdp_port}")
    args = config.launch_args()
    joined = " ".join(args)
    assert "--load-extension=" in joined, "必须带 --load-extension"
    assert "--enable-automation" not in joined and "--headless" not in joined, (
        "自动化痕迹红线（ADR-0001）"
    )
    print(f"launch_args({len(args)}): {joined}")
    agent_holds = agent_owns_port()
    health = probe_health(config=config, fetch=_fetch)
    print(f"agent_owns_port={agent_holds}")
    print(f"probe={health['kind']}")
    print("validate ok — no browser spawned, no state touched")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate",
        action="store_true",
        help="配置/参数/锁判定干跑自检（不真起浏览器）",
    )
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except ImportError:
        pass
    if args.validate:
        return _validate()
    if REPO.name != "vpush" or not (REPO / "agent").exists():
        return 0  # 安全面：跑错目录直接退出
    tick()
    return 0


if __name__ == "__main__":
    sys.exit(main())
