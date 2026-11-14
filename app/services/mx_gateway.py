"""MX 云网关：本地采集器（扩展）上行帧的 WebSocket 接入端（spec #14 票 #15）。

架构位置（ADR-0001）：采集与行为全部下沉到本地真实浏览器；云端只保留解析
入库。本模块是云端接入面——FastAPI websocket route ``/api/mx-ingest``，接收
扩展按 spike 信封形态上行的帧，喂进现有解析层与入库链路（零改动复用）：

    上行信封 {seq, ts, account, type: ws_in|ws_out|http|lifecycle, payload}

- ``ws_in``/``ws_out``：浏览器看到的 SIO 帧原文（如 42/msg,["room_msg",…]），
  经 ``MxWsClient._dispatch_sio_event`` 帧解析（解密在 ``MxWsClient._parse_message``，
  帖子化在 ``MxFetcher._parse_message_to_post``），入库走 ``on_external_post``
  （生产 = Scheduler.ingest_external_post，与V平台 KOL webhook 同链路）。
- ``lifecycle``：记录生命周期事件（启动/attach/断连/重登），可查询。
- 引擎帧（"2"/"3"/"0"/"40"/"41"）：扩展侧已过滤，网关收到也防御性丢弃。

认证协议（本票定稿，成为扩展票的实现契约）：浏览器 WebSocket API 不能自定义
header，故采用「连接后首帧认证」——

    {"op": "pair", "code": "8位配对码"}   → 一次性绑定：下发设备密钥，码作废
    {"op": "auth", "key": "设备密钥"}     → 设备密钥认证；吊销设备立即断开

配对码生成入口 = DB.create_mx_pairing_code（管理端调用；本票只交付 DB 侧，
后台 UI 接线随扩展票一起做）。设备密钥只存哈希（同 bind_codes 取舍）。

边界（票 #15 硬约束）：不 import/调用 ws.py 连接层（connect/重连额度/退避/
风暴标记——那是后续删除票的领域），只用解析层资产
``_dispatch_sio_event``/``_parse_message``；无云端兜底拉取（Q4 裁定）。
"""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect

from ..db import DB
from ..fetchers.base import Post

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))

# 引擎帧（Engine.IO 心跳/开闭/命名空间连接确认）：扩展侧已过滤不上行，
# 网关收到也防御性丢弃——协议契约的网关侧落点（spec user story 21）。
# 全部是纯类型字节或 "40"+ns 形态（41 带 ns 时如 "41/msg"，用前缀匹配兜住）。
ENGINE_FRAME_RE = re.compile(r"^(?:[023]|4[01])")

# 跨账号模糊去重参数（spec 决策：仅接力重叠期启用）：
# 同房间 + published_at 相邻 10 分钟 + 内容相似度 ≥90% 判同一条；
# 同账号重复不适用（如实入库，大V真连发两条不能误吞）。
FUZZY_DEDUP_WINDOW_MINUTES = 10
FUZZY_DEDUP_SIMILARITY = 0.90

# 断连告警阈值（秒）：设备断开后同设备阈值窗内不重复告警（网络抖动秒级
# 重连不打扰）；超过阈值仍在断开状态即告警。MX_INGEST_DISCONNECT_ALERT_SECONDS
# 环境变量可调，0=关闭断连告警（本地测试建议关闭）。
DISCONNECT_ALERT_SECONDS = 300


def _disconnect_alert_seconds_from_env(default: int = DISCONNECT_ALERT_SECONDS) -> int:
    raw = os.environ.get("MX_INGEST_DISCONNECT_ALERT_SECONDS", "").strip()
    if not raw:
        return default
    try:
        return max(int(float(raw)), 0)
    except ValueError:
        return default

# 上行信封合法 type 集；lifecycle 单列（只记录不进解析链）
FRAME_TYPES = frozenset({"ws_in", "ws_out", "http", "lifecycle"})


def content_similarity(a: str, b: str) -> float:
    """跨账号模糊去重的内容相似度：归一化后按最长公共序列比例。

    归一化沿 _squeeze 先例（去空白/标点/链接）——两账号转发同一条消息，
    平台侧 msg 序列化可能有细微差别（空格/转义），裸文本直比会漏。
    """
    def _norm(text: str) -> str:
        squeezed = re.sub(r"[\s\W_]+", "", re.sub(r"https?://\S+", "", text or ""), flags=re.UNICODE)
        return squeezed.lower()

    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


class MxIngestGateway:
    """云网关会话处理器：认证状态机 + 帧路由 + 幂等 + 跨账号去重。

    一个实例服务一条 websocket 连接；共享状态（已入库帖子的模糊去重
    查询）经 DB 完成。
    """

    def __init__(
        self,
        db: DB,
        on_external_post=None,
        alert_publisher=None,
        disconnect_alert_seconds: int | None = DISCONNECT_ALERT_SECONDS,
    ):
        self.db = db
        # 生产 = Scheduler.ingest_external_post（入库+推送+屏蔽词+缓冲）；
        # 纯 UI 调试模式/测试可置 None（只入库）或自定义桩
        self.on_external_post = on_external_post
        # 断连告警发布器：callable(title, content)；生产传调度器的系统通知
        # KOL 发布闭包，测试置 None 关闭
        self.alert_publisher = alert_publisher
        self.disconnect_alert_seconds = disconnect_alert_seconds
        # MxFetcher 惰性实例（解析链帖子化用，与生产同库同缓存）
        self._fetcher = None

    # ---- 认证状态机 ----

    async def handle_pair(self, ws: WebSocket, message: dict) -> None:
        """一次性配对：8 位码 → 校验 → 下发设备密钥 → 码作废。"""
        code = str(message.get("code") or "").strip()
        if not self.db.consume_mx_pairing_code(code):
            await ws.send_json({"ok": False, "error": "配对码无效或已使用"})
            return
        # 设备密钥：secrets.token_hex(32)（64 hex 字符）；库里只存哈希
        device_key = secrets.token_hex(32)
        device_id = self.db.add_mx_device(device_key, name="采集器")
        logger.info("MX 云网关：配对成功 device_id=%s", device_id)
        await ws.send_json({"ok": True, "device_key": device_key})

    async def authenticate(self, ws: WebSocket, message: dict) -> dict | None:
        """设备密钥认证：返回设备行；吊销/未知拒绝并断开。

        吊销后现存连接即断、新连接拒绝——「现存连接即断」由网关连接层
        维护 (device_id -> set[WebSocket]) 注册表，吊销时反向通知实现
        （revoke_mx_device 的调用方为管理端，走 notify_revoked_devices）。
        """
        key = str(message.get("key") or "").strip()
        device = self.db.find_mx_device_by_key(key)
        if device is None:
            await ws.send_json({"ok": False, "error": "设备密钥无效或已吊销"})
            await ws.close(code=4003)
            return None
        self.db.touch_mx_device(device["id"])
        await ws.send_json({"ok": True})
        return device

    # ---- 帧处理 ----

    async def handle_envelope(self, ws: WebSocket, device: dict, envelope: dict) -> None:
        """处理一条上行信封帧（已过认证）。"""
        etype = str(envelope.get("type") or "")
        account = str(envelope.get("account") or "")
        seq = envelope.get("seq")

        if etype == "lifecycle":
            # 生命周期事件（启动/attach/断连/重登）：只记录，不进解析链
            event = str(envelope.get("event") or "") or "lifecycle"
            detail = str(envelope.get("detail") or "")
            self.db.record_mx_ingest_event(device["id"], account, event, detail)
            return

        if etype not in ("ws_in", "ws_out", "http"):
            logger.debug("MX 云网关：忽略未知 type=%s 帧", etype)
            return

        payload = envelope.get("payload")
        if not isinstance(payload, str) or not payload:
            return

        # 引擎帧防御性丢弃：扩展侧已过滤，网关收到也不进解析链
        if ENGINE_FRAME_RE.match(payload):
            logger.debug("MX 云网关：丢弃引擎帧 seq=%s type=%s", seq, etype)
            return

        # (account, seq) 24h 幂等窗：扩展断线重连补传的重复帧直接丢
        if seq is None or self.db.seen_mx_ingest_seq(account, seq):
            logger.debug("MX 云网关：幂等命中丢弃 account=%s seq=%s", account, seq)
            return

        if etype == "http":
            # HTTP 请求/响应帧：当前解析链只消费 WS 消息帧，记录事件供排障，
            # 不进 _dispatch_sio_event（形态不同，硬喂会产生噪音日志）
            self.db.record_mx_ingest_event(
                device["id"], account, "http_frame", f"len={len(payload)}"
            )
            return

        # ws_in/ws_out：帧原文 → 现有解析链（零改动复用）
        await self._dispatch_frame(ws, device, account, payload)

    async def _dispatch_frame(self, ws: WebSocket, device: dict, account: str, frame: str) -> None:
        """把 SIO 帧原文喂进 MxWsClient 的解析层（无传输实例）。

        用 MxWsClient(config, on_message=…) 实例化一个「无传输」客户端：
        - _native_ws 保持 None → _send_sio_ack 对 ws is None 早退（ws.py
          「ACK 副作用」在网关路径安全短路），连接层零接触；
        - on_message 同步回调收解析出的原始消息 dict，本网关再走
          fetcher._parse_message_to_post 帖子化 + ingest 入库。
        解析含同步 IO（房间查库、图片下载），与生产先例一致丢线程池。
        """
        from ..fetchers.mx.ws import MxWsClient

        raw_messages: list[dict] = []

        client = MxWsClient(self._parse_config(), raw_messages.append)
        await client._dispatch_sio_event(frame)

        for raw in raw_messages:
            if not isinstance(raw, dict):
                continue
            post = await asyncio.to_thread(self._parse_to_post, raw)
            if post is None:
                continue
            # 账号标签注入 detail（下划线前缀运行时字段，与 _receivedAt 同口径，
            # 不参与 _fallback_external_id 摘要）：跨账号模糊去重按它跳过同账号
            if post.detail is None:
                post.detail = {}
            post.detail["_ingest_account"] = account
            if self._is_cross_account_duplicate(account, post):
                logger.info(
                    "MX 云网关：跨账号去重命中丢弃 account=%s external_id=%s room=%s",
                    account, post.external_id, post.detail.get("rid") or "",
                )
                continue
            await asyncio.to_thread(self._ingest, post)

    def _parse_config(self):
        """解析链所需的最小 config（MxWsClient._dispatch_sio_event 只读命名空间）。"""
        from types import SimpleNamespace

        return SimpleNamespace(ws_namespace="/msg", token="", ws_url="", ws_path="")

    def _parse_to_post(self, raw_msg: dict) -> Post | None:
        """原始消息 dict → Post（复用 fetcher._parse_message_to_post，零改动）。

        MxFetcher 按需实例化（构造依赖 config.db_path 的 DB 实例即可）：
        这里持有共享 self.db，房间→KOL 查询与图片缓存与生产同库。
        """
        if self._fetcher is None:
            from types import SimpleNamespace

            config = SimpleNamespace(
                api_base="https://mx.2026.foodtop1.com/business-api/4",
                token="",
                page_size=30,
                max_history_pages=100,
                ws_enabled=False,
            )
            from ..fetchers.mx.fetcher import MxFetcher

            self._fetcher = MxFetcher(config, self.db)
        try:
            return self._fetcher._parse_message_to_post(raw_msg)
        except Exception:
            logger.exception("MX 云网关：消息帖子化失败 raw=%s", str(raw_msg)[:200])
            return None

    def _ingest(self, post: Post) -> int | None:
        """入库（生产走 ingest_external_post：去重/屏蔽词/推送一体）。"""
        try:
            if self.on_external_post is not None:
                return self.on_external_post(post)
            return self.db.save_post(post)
        except Exception:
            logger.exception("MX 云网关：入库失败 external_id=%s", post.external_id)
            return None

    def _is_cross_account_duplicate(self, account: str, post: Post) -> bool:
        """跨账号模糊去重：同房间 + published_at 相邻 + 内容相似 ≥90%。

        仅对不同账号启用（接力重叠期形态）；同账号重复如实入库。
        判定基于「最近窗口内已入库的 MX 帖」——查 posts 而非内存缓存，
        多实例/重启不失效。先到者按其 external_id 入库（已发生，不动），
        后到者丢弃。
        """
        rid = ""
        if post.detail:
            rid = str(post.detail.get("rid") or post.detail.get("room_id") or "")
        if not rid or not post.content:
            return False
        cutoff = (
            datetime.now(CN_TZ) - timedelta(minutes=FUZZY_DEDUP_WINDOW_MINUTES)
        ).strftime("%Y-%m-%d %H:%M:%S")
        # 窗口内同房间候选：rid 在 detail JSON 里（int 或 str 两种序列化），
        # LIKE 双形态粗筛 + Python 精筛；候选来自 posts 而非内存缓存，
        # 多实例/重启不失效。先到者已按自身 external_id 入库（不动），
        # 后到者命中即丢弃。
        candidates = self.db._rows(
            "SELECT platform, external_id, content, detail, published_at FROM posts "
            "WHERE platform = 'mx' AND published_at >= ? "
            "AND (detail LIKE ? OR detail LIKE ?) LIMIT 50",
            (
                cutoff,
                f'%"rid": "{rid}"%',
                f'%"rid": {rid}%',
            ),
        )
        for row in candidates:
            try:
                detail = json.loads(row.get("detail") or "")
            except (TypeError, ValueError):
                continue
            if not isinstance(detail, dict) or str(detail.get("rid") or "") != rid:
                continue
            # 同账号不模糊去重：接力重叠期两账号 rid 相同是常态，单账号自己
            # 重复发的相同内容必须如实入库（user story 15）
            src_account = str(detail.get("_ingest_account") or "")
            if src_account == account:
                continue
            if content_similarity(row.get("content") or "", post.content) >= FUZZY_DEDUP_SIMILARITY:
                return True
        return False


def build_ingest_router(
    db: DB,
    on_external_post=None,
    alert_publisher=None,
    disconnect_alert_seconds: int | None = None,
) -> APIRouter:
    """构造云网关 router（挂 /api/mx-ingest，APIRouter prefix=/api）。

    生产在 main.create_app 里调用并 include；on_external_post 传调度器的
    ingest_external_post（与V平台 KOL webhook 同链路），纯 UI 调试模式传 None。
    disconnect_alert_seconds 缺省读 MX_INGEST_DISCONNECT_ALERT_SECONDS 环境变量
    （默认 300 秒；0=关闭断连告警）。
    """
    if disconnect_alert_seconds is None:
        disconnect_alert_seconds = _disconnect_alert_seconds_from_env()
    router = APIRouter(prefix="/api")
    gateway = MxIngestGateway(
        db,
        on_external_post=on_external_post,
        alert_publisher=alert_publisher,
        disconnect_alert_seconds=disconnect_alert_seconds,
    )
    # 吊销反向通知注册表：device_id -> set[WebSocket]；管理端吊销时现存连接即断。
    # 注册表挂在 gateway 实例上（build_ingest_router 每次调用新建一个 gateway，
    # 不用模块级全局——多 app 共存（测试/多实例）时不串线）
    gateway.live_connections = {}
    # 断连告警去重窗（monotonic 时刻）：同设备阈值窗内只告警一次
    _disconnect_alert_at: dict[int, float] = {}

    def notify_revoked_devices(device_id: int) -> None:
        """吊销设备：已认证的存量连接立即断开（spec user story 11）。"""
        conns = gateway.live_connections.pop(int(device_id), None)
        if not conns:
            return
        for ws in list(conns):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(ws.close(code=4003))
                else:
                    loop.run_until_complete(ws.close(code=4003))
            except Exception:
                logger.debug("MX 云网关：吊销断开失败（忽略）", exc_info=True)

    # 管理端接线点（后台 UI 随扩展票接；吊销管理端点调用本回调）
    gateway.notify_revoked_devices = notify_revoked_devices  # type: ignore[attr-defined]
    # include_router 复制路由、自定义属性不随行：挂 router 属性供
    # build_gateway_app/main.create_app 取出来挂 app.state
    router.mx_ingest_notify_revoked = notify_revoked_devices  # type: ignore[attr-defined]

    async def _connection_session(ws: WebSocket, device: dict) -> None:
        device_id = int(device["id"])
        gateway.live_connections.setdefault(device_id, set()).add(ws)
        disconnected = False
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    envelope = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("MX 云网关：信封非 JSON（丢弃）：%s", str(raw)[:120])
                    continue
                if not isinstance(envelope, dict):
                    continue
                if envelope.get("op") == "auth":
                    # 连接中途重新认证（吊销后被断开的扩展按新密钥重连；
                    # 正常路径认证发生在首帧，见 websocket 端点）
                    device = await gateway.authenticate(ws, envelope) or device
                    continue
                await gateway.handle_envelope(ws, device, envelope)
        except WebSocketDisconnect:
            disconnected = True
        finally:
            conns = gateway.live_connections.get(device_id)
            if conns is not None:
                conns.discard(ws)
                if not conns:
                    gateway.live_connections.pop(device_id, None)
            if disconnected:
                _on_disconnect(device)

    def _on_disconnect(device: dict) -> None:
        """断连记录 + 超阈值告警（循系统通知 KOL 机制，阈值可配置）。

        「断连超过阈值才告警」：阈值窗内同设备重复断连不重复告警；网络
        抖动秒级重连不打扰。真断（行为器/采集器挂了）在阈值后才见告警。
        """
        device_id = int(device["id"])
        try:
            db.record_mx_ingest_event(device_id, "", "disconnect", "连接断开")
        except Exception:
            logger.debug("MX 云网关：断连事件记录失败（忽略）", exc_info=True)
        if gateway.alert_publisher is None or not gateway.disconnect_alert_seconds:
            return
        now = time.monotonic()
        last = _disconnect_alert_at.get(device_id, 0.0)
        if now - last < gateway.disconnect_alert_seconds:
            return
        _disconnect_alert_at[device_id] = now
        try:
            gateway.alert_publisher(
                "MX 采集器断连",
                f"设备 {device.get('name') or device_id} 的采集连接已断开，"
                "如非计划内请检查本地行为器/采集器状态。",
            )
        except Exception:
            logger.debug("MX 云网关：断连告警发布失败（忽略）", exc_info=True)

    @router.websocket("/mx-ingest")
    async def mx_ingest(ws: WebSocket) -> None:
        """云网关入口：首帧认证（pair/auth 二选一），认证通过后收信封帧。

        浏览器 WebSocket API 不能自定义 header（spec 约束），认证机制 =
        连接后首帧 {"op": ...}；认证失败 close 4001/4003，扩展侧据此提示
        重新配对/报告吊销。
        """
        await ws.accept()
        try:
            first = await ws.receive_text()
            message = json.loads(first) if first else {}
        except (WebSocketDisconnect, json.JSONDecodeError):
            return
        if not isinstance(message, dict):
            await ws.close(code=4001)
            return
        op = str(message.get("op") or "")
        if op == "pair":
            await gateway.handle_pair(ws, message)
            return
        if op != "auth":
            await ws.send_json({"ok": False, "error": "首帧必须为 pair 或 auth"})
            await ws.close(code=4001)
            return
        device = await gateway.authenticate(ws, message)
        if device is None:
            return
        await _connection_session(ws, device)

    return router


def build_gateway_app(
    db: DB,
    on_external_post=None,
    alert_publisher=None,
    disconnect_alert_seconds: int | None = None,
) -> FastAPI:
    """独立小 app（测试/内嵌用）：只含云网关路由。"""
    if disconnect_alert_seconds is None:
        disconnect_alert_seconds = _disconnect_alert_seconds_from_env()
    app = FastAPI()
    router = build_ingest_router(
        db,
        on_external_post=on_external_post,
        alert_publisher=alert_publisher,
        disconnect_alert_seconds=disconnect_alert_seconds,
    )
    app.include_router(router)
    # 吊销回调挂 app.state：include_router 会复制路由、自定义属性不随行，
    # 管理端经 app.state 拿（生产 main.create_app 同样透传）
    app.state.mx_ingest_notify_revoked = router.mx_ingest_notify_revoked  # type: ignore[attr-defined]
    return app
