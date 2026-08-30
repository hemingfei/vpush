"""MX Socket.IO WebSocket client."""
from __future__ import annotations

import json
import logging
import time
import asyncio
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

from .crypto import decrypt_ws_data

logger = logging.getLogger(__name__)

# 与 MX 网页端一致的浏览器形态请求头：服务端/网关会校验 Origin、UA，
# 缺失时可能拒绝握手或静默不推送
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# 断线后由 run_forever 循环负责重连的间隔（秒）
RECONNECT_INTERVAL_SECONDS = 5


def _browser_handshake_headers(config) -> dict:
    """按配置的 ws 地址派生 Origin，返回握手请求头（与网页端形态一致）。"""
    host = urlparse(str(getattr(config, "ws_url", ""))).netloc
    headers = {"User-Agent": BROWSER_UA}
    if host:
        headers["Origin"] = f"https://{host}"
    return headers


class MxWsClient:
    """MX Socket.IO WebSocket client."""

    NAMESPACE = "/msg"

    def __init__(self, config: Any, on_message_callback: Callable[[dict], None]):
        """
        Initialize MX WebSocket client.

        Args:
            config: MX configuration object
            on_message_callback: Callback function when a new message is received
        """
        self.config = config
        self.on_message = on_message_callback
        self.connected = False
        self.last_message_at: datetime | None = None
        self._sio: Any = None
        self._task: Any = None
        self._should_stop = False
        # 管理员主动断开标记：与掉线区分开，供状态接口展示原因
        self.manually_stopped = False

    async def connect(self):
        """Connect to MX WebSocket server."""
        try:
            import socketio

            # 使用配置的 namespace
            namespace = getattr(self.config, "ws_namespace", self.NAMESPACE)

            # 内部重连必须关闭：python-socketio 的内部重连延迟单位是秒，且
            # run_forever 的 wait() 会阻塞在内部重连任务上（断线后要等满退避
            # 时间才能恢复）。统一由 run_forever 以固定间隔自管理重连。
            self._sio = socketio.AsyncClient(
                logger=logger,
                engineio_logger=False,  # 关闭 Engine.IO 底层详细日志，避免刷屏
                reconnection=False,
            )

            @self._sio.event(namespace=namespace)
            async def connect():
                logger.info("MX WebSocket connected")
                self.connected = True

            @self._sio.event(namespace=namespace)
            async def disconnect():
                logger.info("MX WebSocket disconnected")
                self.connected = False

            @self._sio.event(namespace=namespace)
            async def connect_error(data):
                logger.error(f"MX WebSocket connect_error: {data}")

            @self._sio.on('room_msg', namespace=namespace)
            async def on_room_msg(data):
                await self._handle_message(data)

            # 添加兜底捕获所有事件
            @self._sio.on('*', namespace=namespace)
            async def catch_all(event, *args):
                if event not in ['connect', 'disconnect', 'connect_error', 'room_msg']:
                    logger.debug(f"Received MX WebSocket event {namespace}: {event}")
                    # 部分事件不带 payload：单参透传，多参/无参归一成列表再走解析
                    if len(args) == 1:
                        await self._handle_message(args[0])
                    else:
                        await self._handle_message(list(args))

            # auth 用 callable：python-socketio 每次建立连接时求值，tt 始终新鲜
            def _auth():
                return {
                    "tt": int(time.time() * 1000),
                    "token": self.config.token,
                    "version": "web",
                }

            headers = _browser_handshake_headers(self.config)

            logger.info(
                f"Connecting to MX WebSocket at {self.config.ws_url}, "
                f"path={self.config.ws_path}, namespace={namespace}"
            )
            await self._sio.connect(
                self.config.ws_url,
                headers=headers,
                socketio_path=self.config.ws_path,
                transports=["websocket"],  # 仅使用 websocket，与网页端一致
                auth=_auth,
                wait_timeout=60,
                namespaces=[namespace]
            )

        except Exception as e:
            logger.error(f"Failed to connect to MX WebSocket: {e}", exc_info=True)
            raise

    async def disconnect(self):
        """Disconnect from MX WebSocket server."""
        if self._sio is not None:
            try:
                await self._sio.disconnect()
            except Exception:  # noqa: BLE001 - 尽力断开即可
                logger.warning("MX WebSocket disconnect failed", exc_info=True)
        self.connected = False

    async def _handle_message(self, data):
        """
        Handle incoming WebSocket message.

        Args:
            data: Message data (could be encrypted or plain JSON)
        """
        try:
            self.last_message_at = datetime.now()
            logger.debug(f"Received MX WebSocket message: {data}")

            message = self._parse_message(data)
            if isinstance(message, list):
                # 事件一次送达一批消息：逐条分发给回调
                for item in message:
                    if isinstance(item, dict):
                        item["_receivedAt"] = datetime.now().isoformat()
                        self.on_message(item)
            elif message is not None:
                self.on_message(message)
        except Exception as e:
            logger.error(f"Failed to handle MX WebSocket message: {e}", exc_info=True)

    def _parse_message(self, data) -> dict | None:
        """
        Parse incoming WebSocket message, following chat-monitor's logic.

        Args:
            data: Raw message data

        Returns:
            Parsed message object or None if parsing failed
        """
        parsed = None

        def _use_decrypted(decrypted):
            """解密结果可能是已解析的 dict/list，也可能是字符串；统一安全处理。"""
            nonlocal parsed
            if isinstance(decrypted, (dict, list)):
                parsed = decrypted
                return
            try:
                parsed = json.loads(decrypted)
            except (json.JSONDecodeError, TypeError, ValueError):
                # 保留原始字段（dict 时），绝不能把 rid/msg 埋进 raw 键导致消息被丢弃
                parsed = dict(data) if isinstance(data, dict) else {"raw": data}
                parsed["decrypted"] = decrypted

        if isinstance(data, str):
            # Try to parse directly as JSON first
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                # If that fails, try to decrypt with WebSocket key
                decrypted = decrypt_ws_data(data)
                if decrypted:
                    _use_decrypted(decrypted)
                else:
                    logger.warning(f"Failed to parse or decrypt MX string message: {data[:100]}")

        elif isinstance(data, dict):
            # Check for encrypted content or data field
            if "content" in data and isinstance(data["content"], str) and len(data["content"]) > 50:
                decrypted = decrypt_ws_data(data["content"])
                if decrypted:
                    _use_decrypted(decrypted)
                else:
                    # 解密失败（可能是明文长文本）：保留原始字段，绝不能包成
                    # {"raw": data} 把 rid/msg 埋进去导致消息被下游丢弃
                    parsed = data
            elif "data" in data and isinstance(data["data"], str):
                decrypted = decrypt_ws_data(data["data"])
                if decrypted:
                    _use_decrypted(decrypted)
                else:
                    parsed = data
            else:
                parsed = data

        if parsed is None:
            parsed = {"raw": data}

        # Add received timestamp（list 表示一批消息，时间戳在 _handle_message 里逐条补）
        if isinstance(parsed, dict):
            parsed["_receivedAt"] = datetime.now().isoformat()
        return parsed

    async def run_forever(self):
        """
        Run the WebSocket client forever, with automatic reconnection.
        """
        self._should_stop = False

        while not self._should_stop:
            try:
                if not self.connected:
                    await self.connect()

                # Sleep and let the Socket.IO client handle events
                await self._sio.wait()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"MX WebSocket error: {e}, reconnecting in {RECONNECT_INTERVAL_SECONDS} seconds...", exc_info=True)
                self.connected = False

            if self._should_stop:
                break
            await asyncio.sleep(RECONNECT_INTERVAL_SECONDS)

    async def stop(self):
        """Stop the WebSocket client."""
        self._should_stop = True
        self.manually_stopped = True
        await self.disconnect()
