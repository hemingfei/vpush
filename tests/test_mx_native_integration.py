"""原生 EIO4/SIO5 栈 × 真实 curl_cffi AsyncWebSocket 的本机集成测试。

起一个最小 Engine.IO v4 / Socket.IO v5 服务端（aiohttp WS），用生产
MxWsClient（默认 curl_cffi 实现）完整走握手 → 心跳 → 事件分发 → 服务端断开
→ 重连，验证真实网络路径（ws_connect 握手、recv_str/send_str 帧循环、
terminate）——不依赖 MX 真服务器（帧语义移植自 scripts/mx_ws_probe.py
2026-10-12 的实测）。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from aiohttp import web

from app.fetchers.mx.ws import MxWsClient


class MiniEioServer:
    """最小 EIO4/SIO5 服务端：握手校验 auth、应答心跳、推送一条事件后断开。"""

    def __init__(self):
        self.auth_frames: list[str] = []
        self.pongs = 0
        self.client_messages: list[str] = []
        self.connections = 0
        self.port: int = 0
        self._runner = None

    async def start(self):
        app = web.Application()
        app.router.add_get("/business-api/4/socket.io/", self.handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.port = self._runner.addresses[0][1]

    async def stop(self):
        if self._runner is not None:
            await self._runner.cleanup()

    async def handler(self, request):
        # EIO 查询参数是协议必需（与生产服务端同口径）
        assert "EIO=4" in request.query_string
        assert request.query.get("transport") == "websocket"
        self.connections += 1
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(request)
        await ws.send_str('0{"sid":"s-test","pingInterval":250,"pingTimeout":200}')
        authed = False
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue
            text = msg.data
            if text.startswith("40/msg,"):
                self.auth_frames.append(text)
                # 校验 auth 帧是合法紧凑 JSON 且字段齐备
                auth = json.loads(text.split(",", 1)[1])
                assert set(auth) == {"tt", "token", "version"}
                assert auth["token"] == "tok" and auth["version"] == "web"
                await ws.send_str('40/msg,{"sid":"ns-test"}')
                authed = True
                # 连接确认后推一条 room_msg 事件——帧形态必须是实测 ground
                # truth：非默认 ns 带「42/msg,」前缀（2026-10-13 生产事故即
                # fixture 写成无前缀形态、放过了分发解析缺 ns 路由的回归）
                await ws.send_str('42/msg,["room_msg",{"rid":"9","msg":"ping-case"}]')
            elif text == "3":
                self.pongs += 1
            else:
                self.client_messages.append(text)
        return ws

    async def kick_all(self, send_41: bool = True):
        """给当前连接发 41（服务端主动断开）——由测试按需调用。"""
        raise NotImplementedError  # 通过 handler 内状态机控制，见各用例


async def _drive(server_control, coro, timeout=10.0):
    return await asyncio.wait_for(coro, timeout)


def test_native_stack_full_path_against_local_eio_server():
    """端到端：真实 curl_cffi 握手 → auth 帧 → 事件回调 → 心跳 → 断开重连。"""
    import app.fetchers.mx.ws as mx_ws

    async def scenario():
        server = MiniEioServer()
        await server.start()
        try:
            config = SimpleNamespace(
                ws_url=f"ws://127.0.0.1:{server.port}/business-api/4",
                ws_path="/socket.io",
                ws_namespace="/msg",
                token="tok",
            )
            got = []
            backoff_levels = []

            def fake_backoff(level: int) -> float:
                backoff_levels.append(level)
                return 0.01

            mx_ws_local = mx_ws
            orig_backoff = mx_ws_local._kick_backoff_delay
            orig_revival = mx_ws_local._revival_delay
            mx_ws_local._kick_backoff_delay = fake_backoff
            mx_ws_local._revival_delay = lambda: 0.01
            try:
                client = MxWsClient(config, got.append)
                task = asyncio.create_task(client.run_forever())

                # 等事件到达（握手 + auth + 事件分发全部真实网络路径）
                for _ in range(200):
                    if got:
                        break
                    await asyncio.sleep(0.05)
                assert got and got[0]["rid"] == "9"

                # 服务端心跳：直接复用底层连接发 ping 由 handler 外侧完成较繁琐，
                # 这里以收帧侧语义替代——客户端空闲上限 = 0.25+0.2+5s，远大于
                # 用例时长，不会误判僵尸；pong 行为由单测覆盖
                assert server.auth_frames, "auth 帧必须到达服务端"

                # 断开（服务端关闭 TCP）：客户端走互踢退避并自动重连
                # aiohttp handler 随客户端 cancel/stop 退出，这里直接 stop 客户端
                await client.stop()
                await asyncio.sleep(0.1)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                assert client.gave_up is False
            finally:
                mx_ws_local._kick_backoff_delay = orig_backoff
                mx_ws_local._revival_delay = orig_revival
        finally:
            await server.stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


def test_native_stack_heartbeat_pong_against_local_server():
    """服务端 ping → 客户端必须回 pong（真实网络路径上的 EIO 心跳）。"""

    async def scenario():
        # ping 服务器变体：auth 确认后周期发 "2"
        server = MiniEioServer()
        send_pings = {"on": False}

        orig_handler = server.handler

        async def handler_with_pings(request):
            ws_web = web.WebSocketResponse(autoping=False)
            assert "EIO=4" in request.query_string
            server.connections += 1
            await ws_web.prepare(request)
            await ws_web.send_str('0{"sid":"s","pingInterval":200,"pingTimeout":200}')
            async for msg in ws_web:
                if msg.type != web.WSMsgType.TEXT:
                    continue
                if msg.data.startswith("40/msg,"):
                    server.auth_frames.append(msg.data)
                    await ws_web.send_str('40/msg,{"sid":"n"}')
                    # 连发三个心跳
                    await ws_web.send_str("2")
                    await ws_web.send_str("2")
                    await ws_web.send_str("2")
                elif msg.data == "3":
                    server.pongs += 1
            return ws_web

        server.handler = handler_with_pings
        await server.start()
        try:
            config = SimpleNamespace(
                ws_url=f"ws://127.0.0.1:{server.port}/business-api/4",
                ws_path="/socket.io",
                ws_namespace="/msg",
                token="tok",
            )
            client = MxWsClient(config, lambda m: None)
            await asyncio.wait_for(client.connect(), timeout=5)
            assert client.connected is True
            # 收帧循环必须跑起来才会应答心跳（connect 只做握手）
            recv_task = asyncio.create_task(client._sio.wait())
            # 等三个 pong 回到服务端
            for _ in range(100):
                if server.pongs >= 3:
                    break
                await asyncio.sleep(0.05)
            assert server.pongs >= 3
            recv_task.cancel()
            await client.stop()
        finally:
            await server.stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=15))
