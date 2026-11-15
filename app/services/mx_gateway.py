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
    {"op": "ping"}                       ← 网关→扩展周期下发（Q19 SW 保活），
                                           无 seq/account/type 不是上行信封，
                                           扩展侧 sock.onmessage 对非 pair/auth
                                           帧本就是 no-op，收到即达保活目的

配对码生成入口 = 管理面路由（本模块 build_ingest_router 内 POST
/api/admin/mx-ingest/pairing-code，Bearer MX_INGEST_ADMIN_TOKEN 认证，
mx_shot_token「token 即凭据」同取舍；留空=管理面整体关闭一律 404）；
设备清单 GET /api/admin/mx-ingest/devices、吊销 POST
/api/admin/mx-ingest/devices/{id}/revoke（吊销即断存量连接 close 4003）。
设备密钥只存哈希（同 bind_codes 取舍）。

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

from fastapi import (
    APIRouter,
    FastAPI,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse

from ..db import DB
from ..fetchers.base import Post, _squeeze

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

# 断连告警阈值（秒）：断开后延迟检查的等待时长——超过阈值仍在断开状态
# 即告警（模块头语义 + spec「超过阈值仍在断开状态即告警」）；同时兼作
# 同设备告警去重窗（阈值窗内重复断连不重复告警，网络抖动秒级重连不打扰）。
# threshold=0 = 立即告警（无延迟检查窗口，兼容本地测试/脚本断言快路径）。
# MX_INGEST_DISCONNECT_ALERT_SECONDS 环境变量可调。
DISCONNECT_ALERT_SECONDS = 300

# 云端→扩展 ping 间隔（秒，Q19 决策「云端→扩展 15s ping 兼 SW 保活」）：
# MV3 扩展 Service Worker 空闲约 30s 即被浏览器冻结（spec #14 已知坑），
# 冻结后 chrome.debugger 事件断流=整台机器采集停摆。网关在设备认证在线
# 期间每 15s 下发一帧 {"op":"ping"}，浏览器为处理入站消息会唤醒/续期 SW
# （inbound WS 消息是官方文档明确的 SW 确认项），把 SW 生命周期对齐到
# 连接生命周期。ping 是网关单向下发帧，非上行信封——无 seq/account/type，
# 扩展侧 sock.onmessage 对非 pair/auth 帧本就是 no-op（契约已核实），
# 收到即达成保活目的。MX_INGEST_PING_SECONDS 环境变量可调；0=禁用。
PING_SECONDS = 15


def _disconnect_alert_seconds_from_env(default: int = DISCONNECT_ALERT_SECONDS) -> int:
    raw = os.environ.get("MX_INGEST_DISCONNECT_ALERT_SECONDS", "").strip()
    if not raw:
        return default
    try:
        return max(int(float(raw)), 0)
    except ValueError:
        return default


def _ping_seconds_from_env(default: int = PING_SECONDS) -> int:
    """ping 间隔配置（与断连告警阈值同解析口径：坏值回落默认，0=禁用）。"""
    raw = os.environ.get("MX_INGEST_PING_SECONDS", "").strip()
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

    归一化直接复用 fetchers.base._squeeze（去空白/标点/链接，单一实现
    不另起炉灶）——两账号转发同一条消息，平台侧 msg 序列化可能有细微
    差别（空格/转义），裸文本直比会漏。
    """
    na, nb = _squeeze(a), _squeeze(b)
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
        api_base: str = "",
    ):
        self.db = db
        # 生产 = Scheduler.ingest_external_post（入库+推送+屏蔽词+缓冲）；
        # 纯 UI 调试模式/测试可置 None（只入库）或自定义桩
        self.on_external_post = on_external_post
        # 断连告警发布器：callable(title, content)；生产传调度器的系统通知
        # KOL 发布闭包，测试置 None 关闭
        self.alert_publisher = alert_publisher
        self.disconnect_alert_seconds = disconnect_alert_seconds
        # 解析链帖子化所需 api_base（T5：与 fetcher 同源配置，非硬编码；
        # 缺省回落 MxConfig.api_base 默认值，见 _parse_config）
        self.api_base = (api_base or "").strip()
        # MxFetcher 惰性实例（解析链帖子化用，与生产同库同缓存）
        self._fetcher = None
        # 吊销反向通知注册表（正式声明，T4）：device_id -> set[WebSocket]；
        # 由本类自行维护（连接登记/移除），吊销时 notify_revoked_devices 反查。
        self.live_connections: dict[int, set[WebSocket]] = {}
        # 吊销回调（正式声明，T4）：管理端吊销设备后，把已认证的存量连接
        # 全部 close(4003)。签名 device_id -> None；由 router 注入具体实现
        # （依赖事件循环，构造期不可执行），缺省 no-op（测试/无连接面场景）。
        self.notify_revoked_devices = lambda device_id: None

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

    # ---- 云端→扩展 ping（Q19 决策）----

    async def send_pings(self, ws: WebSocket, interval: float) -> None:
        """周期下发 {"op":"ping"}，直到发送失败/连接关闭自然退出。

        SW 保活原理（模块头 PING_SECONDS 注释）：入站 WS 消息唤醒/续期
        MV3 Service Worker。该协程只做「定时 send + 失败即收」，不做任何
        连接登记/清理——send 抛异常（连接已断/正在关闭）时尽力 close，
        让收帧循环的 receive_text 随即抛 WebSocketDisconnect 走标准断开
        路径（finally 记录事件/告警/清注册表）；close 自身失败（已被
        对端关闭等）也忽略。任务本身由 _connection_session 的 finally
        cancel，绝不反噬收帧循环。
        interval<=0 由调用方拦下，本方法不重复判断。
        """
        while True:
            await asyncio.sleep(interval)
            try:
                await ws.send_json({"op": "ping"})
            except Exception:
                # 发送失败=连接已不可用：close 让标准断开路径跑（receive_text
                # 随即抛 WebSocketDisconnect 记录断连事件/清注册表）
                try:
                    await ws.close()
                except Exception:
                    # close 自身失败（连接已被对端关闭等）按断连处理即可
                    logger.debug(
                        "MX 云网关：ping 失败后 close 失败（忽略）", exc_info=True
                    )
                return

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

    def _api_base(self) -> str:
        """帖子化用 api_base（T5）：网关构造参数优先，回落 MxConfig 默认值。

        与 fetchers 的配置同源（app.config MxConfig.api_base ← MX_API_BASE
        env）；build_ingest_router 从 config 传入，测试可覆盖。不再在函数体
        里硬编码域名——域名漂移时只改配置，不改代码。
        """
        if self.api_base:
            return self.api_base
        from ..config import MxConfig

        return MxConfig().api_base

    def _parse_to_post(self, raw_msg: dict) -> Post | None:
        """原始消息 dict → Post（复用 fetcher._parse_message_to_post，零改动）。

        MxFetcher 按需实例化（构造依赖 config.db_path 的 DB 实例即可）：
        这里持有共享 self.db，房间→KOL 查询与图片缓存与生产同库。
        """
        if self._fetcher is None:
            from types import SimpleNamespace

            config = SimpleNamespace(
                api_base=self._api_base(),
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
    admin_token: str = "",
    api_base: str = "",
    ping_seconds: float | None = None,
) -> APIRouter:
    """构造云网关 router（挂 /api/mx-ingest + 管理面，APIRouter prefix=/api）。

    生产在 main.create_app 里调用并 include；on_external_post 传调度器的
    ingest_external_post（与V平台 KOL webhook 同链路），纯 UI 调试模式传 None。
    disconnect_alert_seconds 缺省读 MX_INGEST_DISCONNECT_ALERT_SECONDS 环境变量
    （默认 300 秒；0=断连立即告警）。
    admin_token：管理面 Bearer 凭据（空=管理面整体关闭，路由一律 404 不暴露
    存在性——mx_shot_token 同取舍：token 即凭据、泄露轮换即可）。
    api_base：帖子化链路用（T5）；缺省回落 MxConfig.api_base（与 fetchers
    同源配置，build_gateway_app 从 config 透传）。
    ping_seconds：云端→扩展 ping 间隔（Q19 决策「15s ping 兼 SW 保活」）；
    缺省读 MX_INGEST_PING_SECONDS 环境变量（默认 15 秒；0=禁用）。
    """
    if disconnect_alert_seconds is None:
        disconnect_alert_seconds = _disconnect_alert_seconds_from_env()
    if ping_seconds is None:
        ping_seconds = _ping_seconds_from_env()
    router = APIRouter(prefix="/api")
    gateway = MxIngestGateway(
        db,
        on_external_post=on_external_post,
        alert_publisher=alert_publisher,
        disconnect_alert_seconds=disconnect_alert_seconds,
        api_base=api_base,
    )
    # ping 间隔（Q19）：router 级配置而非 gateway 实例属性——与 admin_token
    # 同类（连接层行为参数），_connection_session 闭包直接取用。不取整：
    # 测试用亚秒间隔验证 cadence（disconnect_alert_seconds 浮点参数同口径）
    _ping_interval = max(float(ping_seconds or 0), 0.0)
    # ping 任务注册表（leak 观测面）：每条已认证连接恰一个任务，断开的
    # finally 里 cancel+落账；经 router 属性透出（mx_ingest_live_connections
    # 同模式），测试断言「断开后无 ping 任务跨连接泄漏」
    _ping_tasks: set[asyncio.Task] = set()
    # 吊销反向通知（T4 正式接线）：注册表在 gateway 实例上（build 每次调用
    # 新建 gateway，不用模块级全局——多 app 共存（测试/多实例）不串线）
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

    gateway.notify_revoked_devices = notify_revoked_devices
    # include_router 复制路由、自定义属性不随行：挂 router 属性供
    # build_gateway_app/main.create_app 取出来挂 app.state
    router.mx_ingest_notify_revoked = notify_revoked_devices  # type: ignore[attr-defined]
    # 在线连接注册表同样透出（登录态管理面 /admin/mx-ingest/overview 的在线判定用）
    router.mx_ingest_live_connections = gateway.live_connections  # type: ignore[attr-defined]
    router.mx_ingest_ping_tasks = _ping_tasks  # type: ignore[attr-defined]

    # ---- 断连告警：延迟检查 + 去重窗（S4）----

    def _publish_disconnect_alert(device: dict) -> None:
        device_id = int(device["id"])
        try:
            gateway.alert_publisher(
                "MX 采集器断连",
                f"设备 {device.get('name') or device_id} 的采集连接已断开"
                f"超过 {gateway.disconnect_alert_seconds} 秒，如非计划内请检查"
                "本地行为器/采集器状态。",
            )
        except Exception:
            logger.debug("MX 云网关：断连告警发布失败（忽略）", exc_info=True)

    async def _delayed_disconnect_check(device: dict) -> None:
        """延迟检查：阈值秒后仍无该设备的活跃连接 → 告警（一次）。"""
        await asyncio.sleep(gateway.disconnect_alert_seconds)
        device_id = int(device["id"])
        if gateway.live_connections.get(device_id):
            return  # 阈值内重连成功：网络抖动，不告警
        _publish_disconnect_alert(device)

    def _on_disconnect(device: dict) -> None:
        """断连记录 + 延迟告警调度（循系统通知 KOL 机制，阈值可配置）。

        语义（S4 对齐 spec「超过阈值仍在断开状态即告警」）：
        - 断连只记录事件 + 按阈值安排一个延迟检查任务；
        - 延迟检查到期时设备仍无活跃连接才发告警——秒级抖动重连不打扰；
        - 去重窗：同设备阈值窗内不重复安排告警（抖动反复断开不刷屏）；
        - threshold=0 = 立即告警（无延迟窗口；本地测试快路径）。
        """
        device_id = int(device["id"])
        try:
            db.record_mx_ingest_event(device_id, "", "disconnect", "连接断开")
        except Exception:
            logger.debug("MX 云网关：断连事件记录失败（忽略）", exc_info=True)
        if gateway.alert_publisher is None:
            return
        if not gateway.disconnect_alert_seconds:
            # threshold=0：立即告警（去重窗同时为 0 → 每次断连都告，无缓冲）
            _publish_disconnect_alert(device)
            return
        now = time.monotonic()
        last = _disconnect_alert_at.get(device_id, 0.0)
        if now - last < gateway.disconnect_alert_seconds:
            return  # 去重窗内：已有延迟检查在途/已告警，不再安排新告警
        _disconnect_alert_at[device_id] = now
        asyncio.get_event_loop().create_task(_delayed_disconnect_check(device))

    # ---- 管理面（S1）：配对码签发 / 设备清单 / 吊销 ----
    # 认证循 mx_shot_token 先例（token 即凭据、Bearer 头、404 不暴露存在性）；
    # 机器对机器接口，非用户会话。

    def _admin_guard(authorization: str | None) -> None:
        """管理面凭据校验：未配置 token = 功能整体关闭（一律 404）。"""
        expected = (admin_token or "").strip()
        if not expected:
            raise HTTPException(status_code=404, detail="not found")
        got = ""
        if authorization and authorization.startswith("Bearer "):
            got = authorization[7:].strip()
        if not got or not secrets.compare_digest(got, expected):
            raise HTTPException(status_code=404, detail="not found")

    @router.post("/admin/mx-ingest/pairing-code")
    async def admin_mint_pairing_code(
        authorization: str | None = Header(None)
    ) -> JSONResponse:
        """签发 8 位一次性配对码：返回 {code, expires_at}（明文码不出日志）。"""
        _admin_guard(authorization)
        ttl = 15 * 60
        code = db.create_mx_pairing_code(ttl_seconds=ttl)
        row = db._rows(
            "SELECT expires_at FROM mx_pairing_codes ORDER BY id DESC LIMIT 1"
        )
        expires_at = float(row[0]["expires_at"]) if row else time.time() + ttl
        return JSONResponse({"code": code, "expires_at": expires_at})

    @router.get("/admin/mx-ingest/devices")
    async def admin_list_devices(
        authorization: str | None = Header(None)
    ) -> JSONResponse:
        """设备清单（管理面）：id/name/revoked/时间戳 + 是否在线；
        key_hash 绝不回传（哈希是验证面不是展示面）。"""
        _admin_guard(authorization)
        rows = db._rows(
            "SELECT id, name, revoked, created_at, last_seen_at FROM mx_devices "
            "ORDER BY id DESC LIMIT 500"
        )
        devices = [
            {
                "id": int(r["id"]),
                "name": str(r.get("name") or ""),
                "revoked": int(r.get("revoked") or 0),
                "created_at": str(r.get("created_at") or ""),
                "last_seen_at": str(r.get("last_seen_at") or ""),
                "online": bool(gateway.live_connections.get(int(r["id"]))),
            }
            for r in rows
        ]
        return JSONResponse({"devices": devices})

    @router.post("/admin/mx-ingest/devices/{device_id}/revoke")
    async def admin_revoke_device(
        device_id: int, authorization: str | None = Header(None)
    ) -> JSONResponse:
        """吊销设备：置 revoked + 存量连接即断（close 4003，user story 11）。"""
        _admin_guard(authorization)
        db.revoke_mx_device(device_id)
        gateway.notify_revoked_devices(device_id)
        return JSONResponse({"ok": True, "device_id": device_id})

    async def _connection_session(ws: WebSocket, device: dict) -> None:
        device_id = int(device["id"])
        gateway.live_connections.setdefault(device_id, set()).add(ws)
        # 云端→扩展 ping 任务（Q19 决策）：认证在线期间周期下发 {"op":"ping"}
        # 兼 MV3 SW 保活（入站消息唤醒/续期 Service Worker）。ping 失败只在
        # 任务内退出（send_pings 吞异常返回），绝不反噬收帧循环——下面的
        # try/except/finally 收帧语义与 ping 引入前完全一致。
        pinger = None
        if _ping_interval > 0:
            pinger = asyncio.create_task(gateway.send_pings(ws, _ping_interval))
            _ping_tasks.add(pinger)
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
            # 先撤 ping 任务再清注册表：cancel 后等它落地，确保无任务跨连接
            # 泄漏（泄漏的 pinger 会对已关闭 ws 反复 send 失败——无害但脏）。
            # asyncio.wait 不透传子任务异常/取消（gather 会 raise）。
            if pinger is not None:
                pinger.cancel()
                await asyncio.wait({pinger})
                _ping_tasks.discard(pinger)
            conns = gateway.live_connections.get(device_id)
            if conns is not None:
                conns.discard(ws)
                if not conns:
                    gateway.live_connections.pop(device_id, None)
            if disconnected:
                _on_disconnect(device)

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
    admin_token: str = "",
    api_base: str = "",
    ping_seconds: float | None = None,
) -> FastAPI:
    """独立小 app（测试/内嵌用）：只含云网关路由。"""
    if disconnect_alert_seconds is None:
        disconnect_alert_seconds = _disconnect_alert_seconds_from_env()
    if ping_seconds is None:
        ping_seconds = _ping_seconds_from_env()
    app = FastAPI()
    router = build_ingest_router(
        db,
        on_external_post=on_external_post,
        alert_publisher=alert_publisher,
        disconnect_alert_seconds=disconnect_alert_seconds,
        admin_token=admin_token,
        api_base=api_base,
        ping_seconds=ping_seconds,
    )
    app.include_router(router)
    # 吊销回调挂 app.state：include_router 会复制路由、自定义属性不随行，
    # 管理端经 app.state 拿（生产 main.create_app 同样透传）
    app.state.mx_ingest_notify_revoked = router.mx_ingest_notify_revoked  # type: ignore[attr-defined]
    # ping 任务注册表同样透出（观测面）：测试断言断开后无任务跨连接泄漏
    app.state.mx_ingest_ping_tasks = router.mx_ingest_ping_tasks  # type: ignore[attr-defined]
    return app
