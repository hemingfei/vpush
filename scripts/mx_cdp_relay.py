"""MX CDP relay：扩展 SW ↔ page devtools ws 的本地桥（票 #23 追加）。

为什么存在（2026-11-17 16:23 起采集断流根因链）：
- chrome.debugger 的 target attach 是单名额——agent 的 Playwright
  （connect_over_cdp，flat session attach）先挂时扩展永远被拒
  （"Another debugger already attached"）。
- page 的 devtools ws 端点（ws://127.0.0.1:9223/devtools/page/<id>）
  与 flat session attach 是不同机制，天然多客户端并存——但浏览器内
  WebSocket（扩展 SW）发起的升级请求带 Origin: chrome-extension://…，
  Chrome DevTools 服务端拒非 DevTools 前端的 origin（CSRF 防御），
  SW 直连被拒（实测 ERR）。
- 本进程：**无 Origin 概念的 python websockets 客户端**（与 Playwright/
  排障脚本同性质），连 page ws + Network.enable，把 Network.webSocket
  Frame* 事件原样转发到本地 ws://127.0.0.1:9333——扩展 SW 连这个
  端点收帧（自己的服务器，无 Origin 约束）。

契约（与 extension/src/cdp_fallback.js 的 cdpMessageToEvent 对齐）：
- SW 连接后 relay 推送 {"role":"page","pageId":...} 一帧（SW 记账/观测用）
- 之后原样转发 CDP 帧事件 JSON（{"id":..,"method":"Network.webSocket
  FrameReceived/Sent","params":{...}}）；非该两事件的报文不下发。
- 页面目标死了 → relay 主动关 SW 连接（SW onclose 走 alarm 重试路径）。

运行面：pythonw 常驻（MXCollectorGuard 可一并拉起——本脚本自带
单实例锁与目标自动重选，重复启动幂等退出）；依赖 venv 的 websockets。

用法：
    .venv/Scripts/pythonw.exe scripts/mx_cdp_relay.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # agent.single_instance 同款引导

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("mx_cdp_relay")

CDP_HTTP = "http://127.0.0.1:9223"
RELAY_PORT = 9333
# 转发白名单：只推这两类事件（与 cdp_fallback.cdpMessageToEvent 同口径）
FRAME_METHODS = frozenset(
    {"Network.webSocketFrameReceived", "Network.webSocketFrameSent"}
)


def find_page_ws_url() -> str | None:
    """/json/list 里选 MX 页面的 webSocketDebuggerUrl（同步 urllib）。"""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{CDP_HTTP}/json/list", timeout=2) as resp:
            targets = json.loads(resp.read().decode("utf-8", "replace"))
    except OSError as e:
        log.warning("CDP HTTP 不可达: %s", e)
        return None
    prefix = os.environ.get("MX_SITE_PREFIX", "https://mx.2026.foodtop1.com/")
    for t in targets:
        if (
            t.get("type") == "page"
            and str(t.get("url", "")).startswith(prefix)
            and t.get("webSocketDebuggerUrl")
        ):
            return t["webSocketDebuggerUrl"]
    return None


async def bridge(client_ws) -> None:
    """一条 SW 连接的完整生命周期：连 page ws → 双向转发。"""
    import websockets

    page_url = find_page_ws_url()
    if page_url is None:
        log.warning("找不到 MX page target，本连接关闭（SW 侧重试）")
        await client_ws.close()
        return
    async with websockets.connect(page_url, max_size=8 * 1024 * 1024) as page_ws:
        await page_ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
        await client_ws.send(json.dumps({"role": "page", "pageUrl": page_url}))
        async def pump_page_to_client():
            async for raw in page_ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if msg.get("method") in FRAME_METHODS:
                    await client_ws.send(raw)

        async def pump_client_to_page():
            # SW→page 方向：当前无业务（Network.enable 由本进程做）；
            # 保留转发以备将来（如 SW 主动要 getResponseBody）
            async for raw in client_ws:
                try:
                    await page_ws.send(raw)
                except Exception:  # noqa: BLE001 - page 侧死了即止
                    return

        await asyncio.gather(
            pump_page_to_client(),
            pump_client_to_page(),
            return_exceptions=True,
        )


async def serve() -> None:
    import websockets

    async def handler(client_ws):
        try:
            await bridge(client_ws)
        except Exception:  # noqa: BLE001 - 单连接失败不影响服务
            log.warning("bridge 异常", exc_info=True)
            try:
                await client_ws.close()
            except Exception:  # noqa: BLE001
                pass

    async with websockets.serve(handler, "127.0.0.1", RELAY_PORT):
        log.info("relay 监听 ws://127.0.0.1:%d", RELAY_PORT)
        await asyncio.Future()  # 常驻


def main() -> None:
    from agent.single_instance import acquire_lock

    lock = acquire_lock(REPO / "data" / "cdp_relay.lock")
    if lock is None:
        log.info("已有 relay 实例（锁被持），退出")
        return
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
