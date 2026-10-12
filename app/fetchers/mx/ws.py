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

# MX 对外人格常量：HTTP（curl_cffi impersonate）、WS 握手（aiohttp）、图片下载
# 三处必须同形，否则「同一个 token 多个客户端人格」就是风控的现成特征。
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

# 断线后的重连策略分两条路径（2026-10-12 诊断后重构，scripts/mx_ws_probe.py
# 可复现）：平台对同账号实施单 WS 会话互踢——新连接接入后服务端毫秒级给旧
# 连接发 Socket.IO DISCONNECT(41) 且不再发心跳/close（僵尸静默，engine.io 读
# 超时 ~45s 后才判定断开）。因此：
# - 「连接动作本身失败」（网络错误/端点 404 等）：等 16-36 秒（随机）重连一次，
#   再失败永久放弃——高频无上限重连是攻击性特征，固定周期节拍也是机器信号。
# - 「连上后被断」（含被 41 踢、僵尸静默超时、网络中断）：立即抢回会话只会
#   与对手（同 token 的另一客户端——2026-10-12 晚间勘误：非本人网页，真凶
#   待定位，见 docs/mx-单会话互踢诊断-2026-10-12.md）互踢，按阶梯退避等待
#   对方结束会话再接入；连接站住（存活 ≥ 宽限期）即归零。
KICK_BACKOFF_LEVELS = ((120.0, 180.0), (300.0, 420.0), (600.0, 900.0))
RECONNECT_DELAY_RANGE = (16.0, 36.0)

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
        """Connect to MX WebSocket server."""
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
        """连接并监听 MX WebSocket，断线后按双路径策略自恢复。

        连接动作本身失败（非鉴权）：等待 16-36 秒随机延时后重连一次，再失败
        永久放弃（旧语义不变）。连上后被断：走单会话互踢的阶梯退避——立即重连
        会踢掉对方（同 token 的另一客户端，2026-10-12 勘误：非本人网页、幻影
        客户端待定位），对方自动重连又会踢回来，旧策略
        在这种互踢里一轮就耗尽额度永久放弃；阶梯退避（约 2-3 / 5-7 / 10-15 分钟
        随机）给对方留出结束会话的时间，连接站住即归零，三档耗尽才放弃告警。
        连接阶段若被判定为 TOKEN 过期/无效，则不等待不重试，立即放弃。
        """
        self._should_stop = False
        self.running = True
        self.gave_up = False
        # 连接动作失败路径的「唯一一次快速重连」额度：连接站住后恢复
        reconnect_pending = False
        # 互踢退避档位（0 起）：连接站住后归零
        kick_level = 0
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
                    # 站住的连接：两条路径的额度/档位都恢复
                    reconnect_pending = False
                    kick_level = 0
                if connect_attempt and uptime is None:
                    # 连接动作本身失败（网络错误/端点 404 等）：唯一一次快速重连
                    if reconnect_pending:
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
                        "MX WebSocket 连接失败（%s），%.0f 秒后重连一次；再失败将停止自动重连",
                        reason or "connection closed",
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                # 「连上后被断」：单会话互踢的阶梯退避（详见类注释/KICK_BACKOFF_LEVELS）
                if kick_level >= len(KICK_BACKOFF_LEVELS):
                    self.gave_up = True
                    detail = reason or (
                        f"存活 {uptime:.1f}s 后被断开" if uptime is not None else "connection closed"
                    )
                    logger.error(
                        "MX WebSocket 退避重连仍未站住（%s）——疑似同账号单会话互踢"
                        "（疑似另一客户端占用同 token），已停止自动重连；请排查"
                        "同 token 的其他客户端后在管理后台手动接入",
                        detail,
                    )
                    self._fire_give_up(
                        reason or "single-session kick backoff exhausted", False
                    )
                    break
                delay = _kick_backoff_delay(kick_level)
                kick_level += 1
                logger.error(
                    "MX WebSocket 断开（%s，存活 %.0f 秒）——平台同账号单会话互踢，"
                    "%.0f 秒后第 %d 档退避重连",
                    reason or "connection closed",
                    uptime or 0,
                    delay,
                    kick_level,
                )
                await asyncio.sleep(delay)
        finally:
            self.running = False

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
        关闭握手，直接关闭底层 aiohttp 会话掐断连接；sio.disconnect() 会发送
        优雅关闭包，绝不能用在「退出/关窗」语义上。

        reason 记录触发者（管理员手动 / 系统窗口自动），供状态页如实展示。
        """
        self._should_stop = True
        self.manually_stopped = True
        self.stop_reason = reason
        self.connected = False
        eio = getattr(self._sio, "eio", None)
        http = getattr(eio, "http", None)
        if http is not None and not getattr(http, "closed", True):
            try:
                await http.close()
            except Exception:  # noqa: BLE001 - 尽力掐断即可，失败仅记日志
                logger.debug("MX WS 底层连接掐断失败（忽略）", exc_info=True)
        self._sio = None
