"""MX Socket.IO WebSocket client."""
from __future__ import annotations

import json
import logging
import random
import time
import asyncio
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

from .crypto import decrypt_ws_data

logger = logging.getLogger(__name__)

# python-socketio 会用传入 logger 为收到的每个事件打一条 INFO
# （Received event "room_msg" [/msg]），消息高峰期直接刷屏。给它单独一个
# 子 logger 调到 WARNING：库的逐事件/连接过程噪音静音，真正的告警与错误仍保留；
# 本模块自身的 INFO（连接/断开等）走上面 logger，不受影响。
sio_logger = logging.getLogger(__name__ + ".socketio")
sio_logger.setLevel(logging.WARNING)

# MX 对外人格常量：HTTP（curl_cffi impersonate）、WS 握手与收帧（curl_cffi
# AsyncWebSocket）、图片下载（curl_cffi Session）三处必须同形，否则「同一个
# token 多个客户端人格」就是风控的现成特征。
# UA / sec-ch-ua 取自 curl_cffi chrome146 模板实测值（2026-09 当前版本），
# 改动任何一项都要同步三处并跑 tests/test_mx.py 的人格契约测试。
IMPERSONATE_TARGET = "chrome146"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"'
SEC_CH_UA_MOBILE = "?0"
SEC_CH_UA_PLATFORM = '"macOS"'
ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9"

# ---- 原生 Engine.IO v4 / Socket.IO v5 传输（默认实现）----
# 2026-10-12 前 WS 走 python-socketio → aiohttp：请求头是 Chrome 形态、TLS
# 指纹却是 Python/OpenSSL——同一个 token，API 是 Chrome 指纹、WS 是 aiohttp
# 指纹，可被关联。现在默认走 curl_cffi AsyncSession.ws_connect(impersonate)，
# 握手 TLS（JA3/JA4）与 HTTP 完全同形；协议栈为最小 EIO4+SIO5 手写实现
# （帧语义移植自 scripts/mx_ws_probe.py 的实测 A/B 探针）。
# 回退开关：配置 ws_impl=socketio 走旧 python-socketio 路径（兜底回滚用）。
EIO_QUERY = "EIO=4&transport=websocket"
# EIO/SIO 握手单帧超时：open 帧 / ns 连接确认都应在数秒内到达
HANDSHAKE_FRAME_TIMEOUT = 20.0
# 收帧空闲上限兜底值（open 帧缺失 pingInterval 时使用）：服务端 ping 周期
# 25s + 宽限 20s + 5s 余量
DEFAULT_IDLE_LIMIT = 50.0

try:  # curl_cffi 为 MX 硬依赖（client.py 已顶层依赖），此处仅防御性容错
    from curl_cffi.requests import WebSocketTimeout as _CffiWebSocketTimeout
except Exception:  # noqa: BLE001
    _CffiWebSocketTimeout = None


async def _open_native_ws(url: str, headers: dict[str, str]):
    """建立 curl_cffi AsyncWebSocket 连接（Chrome TLS 指纹）。

    独立成模块级函数是测试注入点：单测整体替身，不依赖真实网络与库内部。
    返回 (AsyncSession, AsyncWebSocket)；调用方负责 terminate/close 收尾。
    """
    from curl_cffi.requests import AsyncSession

    session = AsyncSession(impersonate=IMPERSONATE_TARGET)
    try:
        ws = await session.ws_connect(
            url, headers=headers, default_headers=False
        )
    except Exception:
        try:
            await session.close()
        except Exception:  # noqa: BLE001 - 尽力收尾
            pass
        raise
    return session, ws

# 断线后的重连策略分两条路径（2026-10-12 诊断后重构，scripts/mx_ws_probe.py
# 可复现）：
# - 「连接动作本身失败」（网络错误/端点 404 等）：等 16-36 秒（随机）重连一次，
#   再失败永久放弃——高频无上限重连是攻击性特征，固定周期节拍也是机器信号。
# - 「连上后被断」：平台会周期性回收 WS 连接（21:57 实测：两个不同账号的连接
#   在 2.8 秒内先后被掐 TCP、无 41 无 close 帧）——常态回收后服务端立即可重连，
#   第 0 档就用 16-36s 快速重连把数据空窗压到 ~30s；若快速重连也没站住（下午
#   盘风暴期实测：新会话 1ms 即被处决），逐档拉长退避等风暴过去；连接站住
#   （存活 ≥ 宽限期）即归零。同 token 另有单会话互踢（新连接 6ms 内 41 踢旧
#   连接且僵尸静默，A/B 实测），阶梯退避同样适用。
KICK_BACKOFF_LEVELS = (
    (16.0, 36.0),      # 第 0 档：常态回收，服务端已恢复，快速重连
    (120.0, 180.0),
    (300.0, 420.0),
    (600.0, 900.0),
)
RECONNECT_DELAY_RANGE = (16.0, 36.0)

# 复活额度（2026-10-12 起）：退避/快速重连耗尽不再立即永久放弃——风暴期
# （下午盘实测新会话 1ms 即被处决）可能持续一小时以上，一次耗尽就放弃会让
# 整段运行时段空转到关窗。改为「耗尽 → 等 20-30 分钟随机 → 从第 0 档重来」，
# 有界复活 REVIVAL_BUDGET 次，仍然全败才真正放弃告警；「用户过半小时回来看
# 一眼」正是真人会有的行为。连接站住（≥ 宽限期）即全额恢复复活额度。
REVIVAL_DELAY_RANGE = (1200.0, 1800.0)
REVIVAL_BUDGET = 2

# 连接存活宽限期：连上后存活不足此时长即断开，视为连接「没站住」，不恢复
# 重连额度。服务端踢连是毫秒级（实测 1-24ms），正常断线间隔在分钟级以上，
# 60s 足以干净区分两者。
CONNECTION_GRACE_SECONDS = 60.0


def _reconnect_delay() -> float:
    """断线重连等待秒数：16-36 秒之间随机。"""
    return random.uniform(*RECONNECT_DELAY_RANGE)


def _kick_backoff_delay(level: int) -> float:
    """被单会话策略踢后的第 level 档（0 起）退避秒数：档位区间内随机。"""
    level = min(level, len(KICK_BACKOFF_LEVELS) - 1)
    return random.uniform(*KICK_BACKOFF_LEVELS[level])


def _revival_delay() -> float:
    """复活等待秒数：20-30 分钟之间随机。"""
    return random.uniform(*REVIVAL_DELAY_RANGE)

# 连接阶段被拒时，判定「确定是鉴权失败」的精确信号：
# - 握手状态码 401/403（aiohttp 报错形如 "Unexpected status code 401 in server response"）
# - 明确的鉴权失败短语（token 失效/未登录/请重新登录等，匹配前转小写、去空格）
# 弱关键词（仅出现「认证」「过期」「token」）不再单独触发：WAF 拦截页、代理错误
# 文本可能碰巧含这些词，误放弃会停掉 WS 且只能手动接入（后台「登录」可半开重探）
_WS_AUTH_STATUS_CODES = ("401", "403")
_WS_AUTH_MSG_MARKERS = (
    "unauthorized", "forbidden", "invalidtoken", "tokenexpired",
    "token失效", "token过期", "token无效", "token错误",
    "令牌失效", "令牌过期",
    "未登录", "请重新登录", "请先登录", "重新登录",
    "登录失效", "登录过期", "登录已过期", "登录已失效",
    "鉴权失败", "认证失败",
)


def _looks_like_auth_failure(reason: str) -> bool:
    """连接阶段的报错是否「确定」为 TOKEN 过期/无效（精确信号才放弃自动重连）。"""
    text = (reason or "").lower().replace(" ", "").replace("\u3000", "")
    if any(code in text for code in _WS_AUTH_STATUS_CODES):
        return True
    return any(marker in text for marker in _WS_AUTH_MSG_MARKERS)


def _browser_handshake_headers(config) -> dict:
    """按配置的 ws 地址派生 Origin，返回握手请求头（与网页端 Chrome 形态一致）。

    Chrome 的 WebSocket 握手带 Pragma/Cache-Control、Accept-Encoding/Language、
    sec-ch-ua 客户端提示和 sec-fetch-* fetch 元数据（fetch spec：WS 的 mode 为
    "websocket"、dest 为空串；同域连接 site 为 same-origin）；UA 必须显式覆盖，
    否则 aiohttp 会发出自己的「Python aiohttp/x」默认 UA，单条握手就是机器人实锤。
    """
    host = urlparse(str(getattr(config, "ws_url", ""))).netloc
    headers = {
        "User-Agent": BROWSER_UA,
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": ACCEPT_LANGUAGE,
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": SEC_CH_UA_MOBILE,
        "sec-ch-ua-platform": SEC_CH_UA_PLATFORM,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "websocket",
        "sec-fetch-dest": "empty",
    }
    if host:
        headers["Origin"] = f"https://{host}"
    return headers


class _NativeTransport:
    """原生传输对 run_forever 的 _sio 替身：wait() 即收帧循环，直到连接断开。

    保持 ``await self._sio.wait()`` 这一等待点不变，run_forever 的断线/退避/
    复活策略与传输实现完全解耦（单测也因此能整体替身 connect 与 wait）。
    """

    __slots__ = ("_client",)

    def __init__(self, client: "MxWsClient"):
        self._client = client

    async def wait(self):
        await self._client._native_recv_loop()


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
        # 原生传输（默认）：底层 AsyncWebSocket/AsyncSession 与收帧空闲上限
        self._native_ws: Any = None
        self._native_session: Any = None
        self._native_idle_limit: float = DEFAULT_IDLE_LIMIT
        # give-up 回调的 fire-and-forget 任务持引用：事件循环只持弱引用，
        # 不持有可能被 GC 中途取消（照搬 fetcher._ws_tasks 的防御）
        self._giveup_tasks: set = set()
        self._should_stop = False
        # run_forever 存活期间为 True：供状态接口区分「连接中」与「已断线」
        self.running = False
        # 唯一一次自动重连也失败后置 True：已永久放弃自动重连，需管理员手动接入
        self.gave_up = False
        # 管理员主动断开标记：与掉线区分开，供状态接口展示原因
        self.manually_stopped = False
        # 断开原因（管理员手动 / 系统窗口自动），stop() 时写入，供状态接口如实展示
        self.stop_reason = ""

    async def connect(self):
        """按配置选传输实现：curl_cffi（默认，Chrome TLS 指纹）/ socketio（回退）。"""
        impl = str(getattr(self.config, "ws_impl", "") or "curl_cffi").strip().lower()
        if impl == "socketio":
            await self._connect_socketio()
        else:
            await self._connect_native()

    # ---- 原生 EIO4/SIO5 over curl_cffi ----

    def _native_url(self) -> str:
        base = str(getattr(self.config, "ws_url", "")).rstrip("/")
        path = str(getattr(self.config, "ws_path", "") or "/socket.io")
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}/?{EIO_QUERY}"

    async def _connect_native(self):
        """原生握手：WS 建立 → EIO open → SIO ns CONNECT（带 auth）→ 确认。"""
        # 防御：上一连接的残留句柄先掐掉（正常路径由收帧循环退出时清理）
        await self._close_native()
        namespace = str(
            getattr(self.config, "ws_namespace", self.NAMESPACE) or self.NAMESPACE
        )
        url = self._native_url()
        session, ws = await _open_native_ws(url, _browser_handshake_headers(self.config))
        self._native_session = session
        self._native_ws = ws
        try:
            frame = await ws.recv_str(timeout=HANDSHAKE_FRAME_TIMEOUT)
            if not frame.startswith("0"):
                raise RuntimeError(f"EIO 握手异常首帧：{frame[:80]}")
            meta = {}
            try:
                meta = json.loads(frame[1:]) if frame[1:].strip() else {}
            except json.JSONDecodeError:
                logger.warning("MX WS open 帧解析失败（按默认心跳参数续用）：%s", frame[:120])
            ping_interval = float(meta.get("pingInterval") or 25000) / 1000
            ping_timeout = float(meta.get("pingTimeout") or 20000) / 1000
            self._native_idle_limit = ping_interval + ping_timeout + 5.0

            # SIO ns CONNECT：40<ns>,<紧凑 JSON auth>（单帧，与官方网页端一致）
            auth = {
                "tt": int(time.time() * 1000),
                "token": self.config.token,
                "version": "web",
            }
            await ws.send_str(
                f"40{namespace}," + json.dumps(auth, separators=(",", ":"))
            )
            while True:
                frame = await ws.recv_str(timeout=HANDSHAKE_FRAME_TIMEOUT)
                if frame.startswith("2"):
                    if frame == "2":
                        await ws.send_str("3")
                        continue
                    # 2[...]：握手期间即有事件推送，直接分发
                    await self._dispatch_sio_event(frame)
                    continue
                if frame.startswith("44"):
                    raise RuntimeError(f"Socket.IO 连接被拒：{frame[:200]}")
                if frame.startswith("41"):
                    raise RuntimeError(f"握手期间被服务端断开：{frame[:120]}")
                if frame.startswith("40"):
                    break  # ns 连接确认（40<ns>,{"sid":...}）
                if frame == "1":
                    raise RuntimeError("握手期间服务端关闭连接（EIO CLOSE）")
                logger.debug("MX WS 握手期忽略帧：%s", frame[:100])
            self.connected = True
            logger.info(
                "MX WebSocket connected（curl_cffi 原生栈，ns=%s）", namespace
            )
            self._sio = _NativeTransport(self)
        except Exception:
            await self._close_native()
            raise

    async def _native_recv_loop(self):
        """收帧循环（_NativeTransport.wait 的实体）：心跳应答 + 事件分发。

        任何导致连接不可用的情况都抛异常交给 run_forever 的断线策略：
        服务端断开（41/1）、传输错误、以及「pingInterval+pingTimeout 内无任何
        帧」的心跳超时——后者正是 2026-10-09 事故里僵尸假死的兜底。
        """
        ws = self._native_ws
        if ws is None:
            raise RuntimeError("MX WS 原生传输未初始化")
        while True:
            try:
                frame = await ws.recv_str(timeout=self._native_idle_limit)
            except Exception as exc:
                if _CffiWebSocketTimeout is not None and isinstance(
                    exc, _CffiWebSocketTimeout
                ):
                    raise RuntimeError(
                        f"WS 心跳超时（{self._native_idle_limit:.0f}s 无任何帧，"
                        "疑似僵尸连接）"
                    ) from exc
                raise
            if frame == "2":
                await ws.send_str("3")
                continue
            if not frame:
                continue
            head = frame[0]
            if head == "2":  # SIO EVENT：2["event",payload,...]
                await self._dispatch_sio_event(frame)
            elif head == "4":
                sub = frame[1:2]
                if sub == "4":
                    raise RuntimeError(f"Socket.IO 连接错误帧：{frame[:200]}")
                if sub == "1":
                    raise RuntimeError("服务端发送 Socket.IO DISCONNECT（41）")
                if sub == "5":
                    logger.warning(
                        "MX WS 二进制附件事件暂不支持，已跳过：%s", frame[:120]
                    )
                # 40 确认重放及其他子类型：忽略
            elif head == "1":
                raise RuntimeError("服务端发送 Engine.IO CLOSE（1）")
            elif head == "3":
                continue  # ACK：本客户端不发起需确认的请求
            elif head == "0":
                continue  # 重复 open 帧（不应出现）
            else:
                logger.debug("MX WS 未识别帧：%s", frame[:100])

    async def _dispatch_sio_event(self, frame: str):
        """解析 SIO EVENT 帧并分发（对齐旧实现 room_msg + catch-all 语义）。"""
        body = None
        if frame.startswith("2["):
            body = frame[1:]  # 剥掉类型数字，保留 '['：剩余即 JSON 数组
        elif frame.startswith("42["):  # Socket.IO v2 形态容错
            body = frame[2:]
        if body is None:
            return
        try:
            args = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("MX WS 事件载荷非 JSON：%s", frame[:120])
            return
        if not isinstance(args, list) or len(args) < 2:
            return
        payloads = args[1:]
        # 单载荷直接透传（room_msg 形态）；多参事件归一成列表（同旧 catch-all）
        await self._handle_message(payloads[0] if len(payloads) == 1 else payloads)

    async def _close_native(self):
        """掐断原生传输：terminate 不发任何关闭帧（关标签页语义），与 stop 同口径。"""
        ws, self._native_ws = self._native_ws, None
        session, self._native_session = self._native_session, None
        if ws is not None:
            try:
                ws.terminate()
            except Exception:  # noqa: BLE001 - 尽力掐断
                logger.debug("MX WS 原生句柄 terminate 失败（忽略）", exc_info=True)
        if session is not None:
            try:
                await session.close()
            except Exception:  # noqa: BLE001
                logger.debug("MX WS 原生会话关闭失败（忽略）", exc_info=True)

    # ---- python-socketio 传输（ws_impl=socketio 回退）----

    async def _connect_socketio(self):
        """python-socketio/aiohttp 传输（ws_impl=socketio 回退实现）。"""
        try:
            import socketio

            # 使用配置的 namespace
            namespace = getattr(self.config, "ws_namespace", self.NAMESPACE)

            # 库内部重连必须关闭：断线后由管理员在后台手动重连（重新走 start_ws
            # 建新客户端），绝不能让 python-socketio 自己悄悄重连。
            self._sio = socketio.AsyncClient(
                logger=sio_logger,
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
        except Exception as e:
            logger.error(f"Failed to handle MX WebSocket message: {e}", exc_info=True)

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

    async def run_forever(self):
        """连接并监听 MX WebSocket，断线后按双路径策略 + 有界复活自恢复。

        连接动作本身失败（非鉴权）：等待 16-36 秒随机延时后重连一次；再失败
        不是立即放弃，而是进入复活等待（见 REVIVAL_BUDGET）。连上后被断：走
        阶梯退避——平台会周期性回收 WS 连接（2026-10-12 21:57 实测：两个不同
        账号 2.8s 内先后被掐 TCP），常态回收后服务端立即可重连，第 0 档 16-36s
        快速恢复把空窗压到 ~30s；若快速重连也没站住（风暴期新会话 1ms 即被
        处决），逐档拉长退避等风暴过去。退避耗尽进入复活等待（20-30 分钟随机
        × REVIVAL_BUDGET 次）再从第 0 档重来——风暴可持续一小时以上，一次
        耗尽就放弃会让整段运行时段空转；复活额度也耗尽才真正放弃告警。
        连接站住（存活 ≥ 宽限期）即归零档位、恢复全部额度（两条路径通用）。
        连接阶段若被判定为 TOKEN 过期/无效，则不等待不重试，立即放弃。
        """
        self._should_stop = False
        self.running = True
        self.gave_up = False
        # 连接动作失败路径的「唯一一次快速重连」额度：连接站住后恢复
        reconnect_pending = False
        # 互踢退避档位（0 起）：连接站住后归零
        kick_level = 0
        # 复活额度：退避/快速重连耗尽后消耗一次进入长等待；站住即全额恢复
        revivals_left = REVIVAL_BUDGET
        try:
            while not self._should_stop:
                reason = ""
                connect_attempt = False
                connected_at: float | None = None
                try:
                    if not self.connected:
                        connect_attempt = True
                        await self.connect()
                    connected_at = time.monotonic()
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
                uptime = (
                    time.monotonic() - connected_at
                    if connected_at is not None
                    else None
                )
                stood = uptime is not None and uptime >= CONNECTION_GRACE_SECONDS
                if stood:
                    # 站住的连接：两条路径的额度/档位、复活额度全部恢复
                    reconnect_pending = False
                    kick_level = 0
                    revivals_left = REVIVAL_BUDGET
                if connect_attempt and uptime is None:
                    # 连接动作本身失败（网络错误/端点 404 等）：快速重连一次；
                    # 再失败不再立即放弃，而是消耗复活额度等风暴过去
                    if reconnect_pending:
                        if revivals_left > 0:
                            revivals_left -= 1
                            delay = _revival_delay()
                            logger.error(
                                "MX WebSocket 快速重连仍失败（%s），%.0f 分钟后复活"
                                "重连（剩余 %d 次）",
                                reason or "connection closed",
                                delay / 60,
                                revivals_left,
                            )
                            if await self._interruptible_sleep(delay):
                                break  # 复活等待期间被 stop/窗口关闭
                            reconnect_pending = False
                            continue
                        self.gave_up = True
                        logger.error(
                            "MX WebSocket 重连失败（%s），已停止自动重连；请在管理后台手动接入",
                            reason,
                        )
                        self._fire_give_up(reason, False)
                        break
                    reconnect_pending = True
                    delay = _reconnect_delay()
                    logger.error(
                        "MX WebSocket 连接失败（%s），%.0f 秒后重连一次；再失败将进入长间隔复活重试",
                        reason or "connection closed",
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                # 「连上后被断」：阶梯退避（详见类注释/KICK_BACKOFF_LEVELS）
                if kick_level >= len(KICK_BACKOFF_LEVELS):
                    if revivals_left > 0:
                        revivals_left -= 1
                        delay = _revival_delay()
                        logger.error(
                            "MX WebSocket 退避重连仍未站住（%s）——疑似平台侧连接"
                            "回收风暴或同 token 单会话互踢，%.0f 分钟后从第 0 档"
                            "复活重连（剩余 %d 次）",
                            reason or (
                                f"存活 {uptime:.1f}s 后被断开" if uptime is not None else "connection closed"
                            ),
                            delay / 60,
                            revivals_left,
                        )
                        if await self._interruptible_sleep(delay):
                            break  # 复活等待期间被 stop/窗口关闭
                        kick_level = 0
                        reconnect_pending = False
                        continue
                    self.gave_up = True
                    detail = reason or (
                        f"存活 {uptime:.1f}s 后被断开" if uptime is not None else "connection closed"
                    )
                    logger.error(
                        "MX WebSocket 复活重连仍未站住（%s），已停止自动重连；请稍后"
                        "在管理后台手动接入",
                        detail,
                    )
                    self._fire_give_up(
                        reason or "single-session kick backoff exhausted", False
                    )
                    break
                delay = _kick_backoff_delay(kick_level)
                kick_level += 1
                logger.error(
                    "MX WebSocket 断开（%s，存活 %.0f 秒）——平台回收连接/互踢，"
                    "%.0f 秒后第 %d 档退避重连",
                    reason or "connection closed",
                    uptime or 0,
                    delay,
                    kick_level,
                )
                await asyncio.sleep(delay)
        finally:
            self.running = False

    async def _interruptible_sleep(self, seconds: float) -> bool:
        """分片睡眠（复活等待用）：期间被 stop 置位即提前醒来并返回 True。

        20-30 分钟的复活等待不能裸睡：窗口关窗靠 task.cancel 能打断裸睡，但
        stop()（关标签页语义）只置标志——分片睡眠保证两种退出路径都在秒级
        响应，复活等待不会拖住会话收口。
        """
        deadline = time.monotonic() + seconds
        while not self._should_stop:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(1.0, remaining))
        return True

    def _fire_give_up(self, reason: str, token_expired: bool):
        """永久放弃自动重连时回调外部（发布系统告警等）；回调异常只记日志。"""
        if self.on_give_up is None:
            return
        try:
            result = self.on_give_up(reason, token_expired)
            if asyncio.iscoroutine(result):
                task = asyncio.create_task(self._await_give_up(result))
                self._giveup_tasks.add(task)
                task.add_done_callback(self._giveup_tasks.discard)
        except Exception:
            logger.error("MX WebSocket 重连失败回调执行异常", exc_info=True)

    async def _await_give_up(self, coro):
        try:
            await coro
        except Exception:
            logger.error("MX WebSocket 重连失败回调执行异常", exc_info=True)

    async def stop(self, reason: str = "已手动断开"):
        """停止 WS 客户端：模拟用户直接关闭标签页/浏览器退出。

        真实用户的退出不会发 socket.io `41`、engine.io CLOSE 包或 WS Close 帧
        ——服务端只会看到 TCP 连接消失（transport close）。因此这里不做任何
        关闭握手：原生栈直接 terminate 底层连接（同样不发关闭帧），socketio
        回退栈直接关闭底层 aiohttp 会话掐断连接；sio.disconnect() 会发送
        优雅关闭包，绝不能用在「退出/关窗」语义上。

        reason 记录触发者（管理员手动 / 系统窗口自动），供状态页如实展示。
        """
        self._should_stop = True
        self.manually_stopped = True
        self.stop_reason = reason
        self.connected = False
        await self._close_native()
        eio = getattr(self._sio, "eio", None)
        http = getattr(eio, "http", None)
        if http is not None and not getattr(http, "closed", True):
            try:
                await http.close()
            except Exception:  # noqa: BLE001 - 尽力掐断即可，失败仅记日志
                logger.debug("MX WS 底层连接掐断失败（忽略）", exc_info=True)
        self._sio = None
