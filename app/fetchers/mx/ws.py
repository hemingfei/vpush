"""MX Socket.IO 解析层（云端已无连接层，ADR-0001）。

云端直连（原生 EIO4/SIO5 栈、TLS 拟人指纹、重连/退避/风暴标记、HTTP 三连）
已随本地双组件上线整体退役。保留本模块是因为它是唯一成熟的帧解析资产：

- 采集器（MV3 扩展）把浏览器看到的 WS 帧原文上行到 /api/mx-ingest；
- 云网关（app/services/mx_gateway.py）用 ``MxWsClient._dispatch_sio_event``
  分发事件、``_parse_message`` 解密/解压/解码，再交给 fetcher 帖子化入库。

因此这里只留纯解析与分发，不含任何传输、重连或鉴权代码：没有连接层就没有
可被平台识别的客户端人格，也就没有需要防的踢线战线。
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .crypto import decrypt_ws_data

logger = logging.getLogger(__name__)

# 图片下载与 HTTP 侧仍复用浏览器人格常量（三处同形是历史约定，保留单一来源）。
IMPERSONATE_TARGET = "chrome146"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)
# UA / sec-ch-ua 取自 curl_cffi chrome146 模板实测值（2026-09 当前版本），
# 改动任何一项都要同步三处并跑人格契约测试（tests/test_mx_parse.py）。
SEC_CH_UA = '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"'
SEC_CH_UA_MOBILE = "?0"
SEC_CH_UA_PLATFORM = '"macOS"'
ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9"

# 平台非消息事件：request=客户端环境探测（如 cz88 IP 查询）、va 等，
# 不进消息管道（旧 catch-all 会把 va 的裸数字当消息产生噪音日志）
NON_MESSAGE_EVENTS = frozenset({"request", "va"})


class MxWsClient:
    """无传输的帧解析器：只把 SIO 事件帧变成消息 dict。"""

    NAMESPACE = "/msg"

    def __init__(self, config: Any, on_message_callback: Callable[[dict], None]):
        self.config = config
        self.on_message = on_message_callback
        self.connected = False
        self.last_message_at: datetime | None = None

    async def _dispatch_sio_event(self, frame: str):
        """解析 SIO EVENT 帧并分发（对齐旧实现 room_msg + catch-all 语义）。

        实测服务端事件帧为带命名空间前缀的 ``42/msg,["room_msg",...]``
        （2026-10-12 mx_ws_probe 抓包 ground truth，非默认 ns 必带前缀）；
        同时容错 42[...]（默认 ns）、2[...]（无 EIO 包裹的历史形态）与
        ack 序号形态 ``42/msg,<ack>["request",...]``（2026-10-13 实测：
        平台环境探测事件 request/va 均带序号，浏览器会回 43 ACK，本客户端
        回空载荷 ACK 对齐协议，但不猜业务契约）。
        """
        body = None
        ns_part = ""  # 命名空间段（含尾逗号，如 "/msg,"），回 ACK 时复用
        ack_id: int | None = None
        if frame.startswith("2["):
            body = frame[1:]  # 剥掉类型数字，保留 '['：剩余即 JSON 数组
        elif frame.startswith("42"):
            rest = frame[2:]
            if rest.startswith("/"):
                # 42/msg,[...]：剥掉命名空间前缀，取逗号后的载荷
                comma = rest.find(",")
                if comma == -1:
                    logger.warning("MX WS 事件帧缺载荷分隔逗号：%s", frame[:120])
                    return
                ns_part = rest[: comma + 1]
                rest = rest[comma + 1:]
            if not rest.startswith("["):
                # 42/msg,<ack>[...]：服务端期待确认的事件帧
                bracket = rest.find("[")
                if bracket == -1:
                    logger.warning("MX WS 事件帧缺载荷数组：%s", frame[:120])
                    return
                ack_part = rest[:bracket]
                if not ack_part.isdigit():
                    logger.warning("MX WS 事件帧形态未识别：%s", frame[:120])
                    return
                ack_id = int(ack_part)
                rest = rest[bracket:]
            body = rest
        if body is None:
            return
        try:
            args = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("MX WS 事件载荷非 JSON：%s", frame[:120])
            if ack_id is not None:
                await self._send_sio_ack(ns_part, ack_id)
            return
        if ack_id is not None:
            await self._send_sio_ack(ns_part, ack_id)
        if not isinstance(args, list) or not args:
            return
        event = args[0] if isinstance(args[0], str) else ""
        if event in NON_MESSAGE_EVENTS:
            # 平台非消息事件（request=客户端环境探测如 cz88 IP 查询、va 等）：
            # 不进消息管道（旧 catch-all 会把 va 的裸数字当消息产生噪音日志）
            logger.debug("MX WS 平台事件已忽略并回 ACK（event=%s）：%s", event, frame[:100])
            return
        payloads = args[1:]
        if not payloads:
            return
        # 单载荷直接透传（room_msg 形态）；多参事件归一成列表（同旧 catch-all）
        await self._handle_message(payloads[0] if len(payloads) == 1 else payloads)

    async def _send_sio_ack(self, ns_part: str, ack_id: int):
        """云端无传输连接，ACK 不再发送（网关路径的协议占位）。

        扩展侧看到浏览器自己回 ACK，云端不重复回；保留方法是为了让
        ``_dispatch_sio_event`` 的调用路径与浏览器抓包形态一致。
        """
        return

    async def _handle_message(self, data):
        """
        Handle incoming WebSocket message.

        Args:
            data: Message data (could be encrypted or plain JSON)
        """
        try:
            self.last_message_at = datetime.now()
            logger.debug(f"Received MX WebSocket message: {data}")

            # 解析含 lzstring 解压 + AES 解密 + JSON 解码（大消息高峰 CPU 密集），
            # 与 fetcher 的帖子解析同池：直接在 loop 上跑会拖垮 socket.io 心跳
            # 导致服务端断连，必须丢线程池执行（逐条 await，保持消息顺序）
            message = await asyncio.to_thread(self._parse_message, data)
            if isinstance(message, list):
                # 事件一次送达一批消息：逐条分发给回调
                for item in message:
                    if isinstance(item, dict):
                        item["_receivedAt"] = datetime.now().isoformat()
                        self.on_message(item)
            elif message is not None:
                self.on_message(message)
        except Exception:
            logger.exception("Failed to handle MX WebSocket message")

    def _parse_message(self, data) -> dict | list | None:
        """
        Parse incoming WebSocket message, following chat-monitor's logic.

        Args:
            data: Raw message data

        Returns:
            Parsed message object（list 表示一批消息）or None if parsing failed
        """
        parsed = None

        if isinstance(data, list):
            # socket.io 原生数组载荷（多参事件归一成列表）：原样返回，交给
            # _handle_message 的 list 分发路径逐条处理，绝不能落进 {"raw": ...}
            # 被静默丢弃
            return data

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
