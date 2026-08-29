"""MX Socket.IO WebSocket client."""
from __future__ import annotations

import json
import logging
import time
import asyncio
from datetime import datetime
from typing import Any, Callable

from .crypto import decrypt_ws_data

logger = logging.getLogger(__name__)


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

    async def connect(self):
        """Connect to MX WebSocket server."""
        try:
            import socketio

            # 使用配置的 namespace
            namespace = getattr(self.config, "ws_namespace", self.NAMESPACE)

            # 使用与 chat-monitor 一致的配置，但关闭底层 Engine.IO 的详细日志
            self._sio = socketio.AsyncClient(
                logger=logger,
                engineio_logger=False,  # 关闭 Engine.IO 底层详细日志，避免刷屏
                reconnection=True,
                reconnection_delay=3000,  # 增加重连延迟到 3 秒，避免立即重连
                reconnection_delay_max=10000  # 最大延迟 10 秒
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

            auth = {
                "tt": int(time.time() * 1000),
                "token": self.config.token,
                "version": "web",
            }

            logger.info(
                f"Connecting to MX WebSocket at {self.config.ws_url}, "
                f"path={self.config.ws_path}, namespace={namespace}"
            )
            await self._sio.connect(
                self.config.ws_url,
                socketio_path=self.config.ws_path,
                transports=["websocket"],  # 与 chat-monitor 一致，仅使用 websocket
                auth=auth,
                wait_timeout=60,
                namespaces=[namespace]
            )

        except Exception as e:
            logger.error(f"Failed to connect to MX WebSocket: {e}", exc_info=True)
            raise

    async def disconnect(self):
        """Disconnect from MX WebSocket server."""
        if self._sio and self.connected:
            await self._sio.disconnect()
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
            except Exception as e:
                logger.error(f"MX WebSocket error: {e}, reconnecting in 5 seconds...", exc_info=True)
                self.connected = False

                if not self._should_stop:
                    await asyncio.sleep(5)

    async def stop(self):
        """Stop the WebSocket client."""
        self._should_stop = True
        await self.disconnect()
