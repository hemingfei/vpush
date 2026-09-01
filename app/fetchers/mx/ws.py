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

# 断线后的重连策略：只等 12 秒重连一次；这次重连再失败就永久放弃自动重连
# （高频无上限重连会加重平台风控处罚），恢复只能靠管理员在后台手动接入
RECONNECT_DELAY_SECONDS = 12

# 连接阶段被拒时，判定为 TOKEN 过期/无效的关键词（命中则不重试，直接放弃告警）
_AUTH_FAIL_KEYWORDS = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "auth",
    "token",
    "登录",
    "认证",
    "过期",
    "无效",
)


def _looks_like_auth_failure(reason: str) -> bool:
    """连接阶段的报错是否像 TOKEN 过期/无效（握手 401/403 或鉴权类文案）。"""
    text = (reason or "").lower()
    return any(kw in text for kw in _AUTH_FAIL_KEYWORDS)


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

    def __init__(
        self,
        config: Any,
        on_message_callback: Callable[[dict], None],
        on_give_up: Callable[[str], Any] | None = None,
    ):
        """
        Initialize MX WebSocket client.

        Args:
            config: MX configuration object
            on_message_callback: Callback function when a new message is received
            on_give_up: 永久放弃自动重连时的回调（参数为失败原因），用于发布系统告警
        """
        self.config = config
        self.on_message = on_message_callback
        self.on_give_up = on_give_up
        self.connected = False
        self.last_message_at: datetime | None = None
        self._sio: Any = None
        self._task: Any = None
        self._should_stop = False
        # run_forever 存活期间为 True：供状态接口区分「连接中」与「已断线」
        self.running = False
        # 12 秒后的那次重连也失败后置 True：已永久放弃自动重连，需管理员手动接入
        self.gave_up = False
        # 管理员主动断开标记：与掉线区分开，供状态接口展示原因
        self.manually_stopped = False

    async def connect(self):
        """Connect to MX WebSocket server."""
        try:
            import socketio

            # 使用配置的 namespace
            namespace = getattr(self.config, "ws_namespace", self.NAMESPACE)

            # 库内部重连必须关闭：断线后由管理员在后台手动重连（重新走 start_ws
            # 建新客户端），绝不能让 python-socketio 自己悄悄重连。
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
        """连接并监听 MX WebSocket，断线后按「只重连一次」策略自恢复。

        首次连接失败或断线：等待 RECONNECT_DELAY_SECONDS 秒后重连一次；
        重连成功则恢复额度（下次断线仍可重连一次），重连再失败就永久放弃
        自动重连：置 gave_up 并触发 on_give_up 回调（用于系统账号发布告警）。
        连接阶段若被判定为 TOKEN 过期/无效，则不等待不重试，立即放弃。
        恢复只能由管理员在后台手动接入（start_ws 会创建新客户端，状态自动复位）。
        """
        self._should_stop = False
        self.running = True
        self.gave_up = False
        # 本次连接是否还欠一次「12 秒后重连」机会：连接成功后恢复
        reconnect_pending = False
        try:
            while not self._should_stop:
                reason = ""
                connect_attempt = False
                try:
                    if not self.connected:
                        connect_attempt = True
                        await self.connect()
                    reconnect_pending = False
                    # Sleep and let the Socket.IO client handle events
                    await self._sio.wait()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"MX WebSocket error: {e}", exc_info=True)
                    reason = str(e) or e.__class__.__name__
                finally:
                    self.connected = False
                if self._should_stop or self.manually_stopped:
                    break
                # TOKEN 过期/无效（连接阶段被拒）：不等待不重试，直接永久放弃并告警；
                # 更换 TOKEN 后由管理员手动接入或次日窗口自动恢复
                if connect_attempt and _looks_like_auth_failure(reason):
                    self.gave_up = True
                    logger.error("MX WebSocket 连接被拒（TOKEN 过期/无效），已停止重试")
                    self._fire_give_up(reason, True)
                    break
                if reconnect_pending:
                    # 12 秒后的那次重连也失败（或重连后立即再断）：永久放弃
                    self.gave_up = True
                    logger.error("MX WebSocket 重连失败，已停止自动重连；请在管理后台手动接入")
                    self._fire_give_up(reason, False)
                    break
                reconnect_pending = True
                logger.error(
                    "MX WebSocket 断开（%s），%d 秒后重连一次；再失败将停止自动重连",
                    reason or "connection closed",
                    RECONNECT_DELAY_SECONDS,
                )
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)
        finally:
            self.running = False

    def _fire_give_up(self, reason: str, token_expired: bool):
        """永久放弃自动重连时回调外部（发布系统告警等）；回调异常只记日志。"""
        if self.on_give_up is None:
            return
        try:
            result = self.on_give_up(reason, token_expired)
            if asyncio.iscoroutine(result):
                asyncio.create_task(self._await_give_up(result))
        except Exception:
            logger.error("MX WebSocket 重连失败回调执行异常", exc_info=True)

    async def _await_give_up(self, coro):
        try:
            await coro
        except Exception:
            logger.error("MX WebSocket 重连失败回调执行异常", exc_info=True)

    async def stop(self):
        """Stop the WebSocket client."""
        self._should_stop = True
        self.manually_stopped = True
        await self.disconnect()
