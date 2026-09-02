"""MX platform fetcher."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Callable
from urllib.parse import urlparse

from ...avatar_cache import cache_image_file
from ..base import (
    BACKFILL_PAGES,
    Fetcher,
    Post,
    format_published_at,
    warn_timeline_gap,
)
from .client import MXClient, MXTokenExpiredError
from .ws import MxWsClient

logger = logging.getLogger(__name__)

# 房间信息缓存 TTL：WS 消息按 rid 找 KOL 用的缓存，过期后重查数据库，
# 避免房间改名/禁用后长期使用旧信息
ROOM_CACHE_TTL_SECONDS = 300
ROOM_CACHE_MISS_TTL_SECONDS = 60

# file 消息可能是平台把截图/图片当文件发送（如钉钉转存图），按图片处理的判定：
# URL 带图片扩展名，或 URL 完全没有扩展名（转存图常不带格式后缀，此时参考文件名
# 扩展名兜底）；URL 带其他扩展名（.pdf/.zip 等）视为真实文件，走附件保留
IMAGE_FILE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|bmp|avif)$", re.IGNORECASE)
# 任意文件扩展名（2-5 位，避免把「v1.2」这类版本号尾巴当成扩展名）
ANY_FILE_EXT_RE = re.compile(r"\.[A-Za-z0-9]{2,5}$")
# 音频扩展名：纯语音消息合成「[语音]」占位正文时区分文件类型用
AUDIO_EXT_RE = re.compile(r"\.(mp3|m4a|aac|wav|ogg|oga|opus|amr|flac)$", re.IGNORECASE)


def looks_like_image_url(url: str, name: str = "") -> bool:
    """判断 file 消息是否按图片处理：URL 带图片扩展名，或 URL 没有任何扩展名。"""
    url_path = urlparse(str(url or "")).path
    name_path = urlparse(str(name or "")).path
    if IMAGE_FILE_EXT_RE.search(url_path):
        return True
    if ANY_FILE_EXT_RE.search(url_path):
        # URL 明确带非图片扩展名（.pdf/.zip 等）→ 真实文件
        return False
    # URL 没有后缀：文件名带扩展名时以文件名为准（如「报告.pdf」仍是文件），
    # 否则视为图片
    if ANY_FILE_EXT_RE.search(name_path):
        return bool(IMAGE_FILE_EXT_RE.search(name_path))
    return True


def normalize_mx_text(text: str) -> str:
    """归一化 MX 消息正文的换行：还原转义序列，折叠连续换行（不允许空行）。

    MX 服务端对正文换行做了双重转义：msg 文本 JSON 解码一次后仍会剩字面量
    「反斜杠+n/r」（与真实 CR、CRLF 混杂，如编辑前缀「xx [编辑]\r\n正文」）。
    统一还原成真实换行，再把连续换行压成单个换行；只有空白字符（含全角空格）
    的行按空行处理。
    """
    if not text:
        return ""
    # 先处理字面量转义序列（反斜杠开头），再归并真实 CR/CRLF，顺序不能反
    s = (
        str(text)
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    return "\n".join(line for line in s.split("\n") if line.strip())


class MxFetcher(Fetcher):
    platform = "mx"

    def __init__(self, source_config, db, client=None):
        super().__init__(source_config)
        self.db = db
        self.config = source_config
        self.mx_client = MXClient(
            getattr(source_config, "api_base", "https://mx.2026.naaifu.cn/business-api/5"),
            getattr(source_config, "token", "")
        )
        self.max_history_pages = getattr(source_config, "max_history_pages", 100)
        # 官方 msg/list 的 pagesize 实测为 30（2026-09-02 抓包）
        self.page_size = getattr(source_config, "page_size", 30)
        self.ws_client = None
        # (monotonic, kol) 元组：kol 为 None 也缓存（更短 TTL），未知房间噪音事件不至于打爆数据库
        self._room_cache: dict = {}
        self._ws_tasks: set = set()
        self._ws_enabled = getattr(source_config, "ws_enabled", True)

    def fetch(self, kol):
        room_id = int(kol["external_id"])

        # 官方网页端每次打开房间都先发 room/view 进房上报（2026-09-02 抓包实测）：
        # 拉取前对齐「人打开了这个房间」的请求链。上报失败只记日志不阻断拉取；
        # TOKEN 过期照常抛出，交由上层熔断/告警接管
        try:
            self.mx_client.room_view(room_id)
        except MXTokenExpiredError:
            raise
        except Exception:  # noqa: BLE001 - 上报失败不影响拉取
            logger.warning("MX room/view 上报失败 room=%s", room_id, exc_info=True)

        try:
            # 直接获取最新消息
            messages = self.mx_client.get_room_history(room_id, limit=self.page_size)
            posts = self._build_posts(kol, messages)
        except Exception as e:
            logger.error("Failed to fetch MX room history: %s", e, exc_info=True)
            raise

        # 首页尾部出现了未入库的新帖 → 继续向后翻页追平，防止爆发发帖时漏抓
        return self._backfill_history(kol, room_id, messages, posts)

    def _backfill_history(self, kol, room_id, first_messages, first_posts):
        """首页最末一帖未入库 → 用 msgid 游标向后追平（cursor 版 catchup_pages）。"""
        if self.db is None or not first_posts or not first_messages:
            return first_posts
        # 不足一页说明已返回全部历史，不存在缺口
        if len(first_messages) < self.page_size:
            return first_posts
        platform = self.platform
        known = self.db.existing_post_keys(
            [(platform, p.external_id) for p in first_posts]
        )
        if (platform, first_posts[-1].external_id) in known:
            return first_posts

        merged = {p.external_id for p in first_posts}
        all_posts = list(first_posts)
        caught_up = False
        msg_ids = self._numeric_msg_ids(first_messages)
        if not msg_ids:
            return first_posts
        cursor = min(msg_ids)

        for page in range(2, BACKFILL_PAGES + 2):
            try:
                batch = self.mx_client.get_room_history(room_id, cursor, self.page_size)
            except Exception as exc:  # noqa: BLE001 - 追平失败不影响本轮已有结果
                logger.warning("MX 第 %d 页追平失败 room=%s err=%s", page, room_id, exc)
                break
            if not batch:
                break
            posts = self._build_posts(kol, batch)
            seen = self.db.existing_post_keys([(platform, p.external_id) for p in posts])
            for p in posts:
                if p.external_id not in merged:
                    merged.add(p.external_id)
                    all_posts.append(p)
            if posts and (platform, posts[-1].external_id) in seen:
                caught_up = True
                break
            batch_ids = self._numeric_msg_ids(batch)
            if not batch_ids or min(batch_ids) >= cursor:
                break  # 游标未前移，避免原地死循环
            cursor = min(batch_ids)
            if len(batch) < self.page_size:
                break

        if not caught_up:
            warn_timeline_gap(platform)
        return all_posts

    @staticmethod
    def _numeric_msg_ids(messages) -> list[int]:
        ids = []
        for m in messages:
            mid = m.get("id")
            if isinstance(mid, bool):
                continue
            if isinstance(mid, int):
                ids.append(mid)
            elif isinstance(mid, str) and mid.isdigit():
                ids.append(int(mid))
        return ids

    def _build_posts(self, kol, messages):
        posts = []
        for msg in messages:
            try:
                post = self._parse_message_to_post(msg, kol)
                if post:
                    posts.append(post)
            except Exception as e:
                logger.error("Failed to build post from MX message: %s", e, exc_info=True)
                continue
        return posts

    def _format_published_at(self, createtime):
        """格式化 MX 消息时间。"""
        if not createtime:
            return format_published_at(str(int(time.time())))
        try:
            if isinstance(createtime, int) or str(createtime).isdigit():
                ts = int(createtime)
                ts = ts / 1000 if ts > 1e12 else ts
                return format_published_at(str(int(ts)))
            return format_published_at(str(createtime))
        except Exception:
            return format_published_at(str(int(time.time())))

    async def start_ws(self, on_message, on_ws_give_up=None):
        """
        启动 WebSocket 连接并监听实时消息。

        Args:
            on_message: 回调函数，当收到新消息时调用（可以是异步函数）
            on_ws_give_up: 自动重连永久放弃时的回调（参数为失败原因），用于发布系统告警
        """
        if not self._ws_enabled:
            logger.info("MX WebSocket is disabled")
            return

        async def on_raw_message(raw_msg):
            try:
                post = self._parse_message_to_post(raw_msg)
                if post:
                    if asyncio.iscoroutinefunction(on_message):
                        await on_message(post)
                    else:
                        on_message(post)
            except Exception as e:
                logger.error(f"Failed to process MX WebSocket message: {e}", exc_info=True)

        # 为了让 ws.py 能调用异步回调，我们需要一个包装器
        def _on_raw_message(raw_msg):
            # 在新的任务中运行异步回调，避免阻塞事件循环；
            # 必须持有任务引用，否则事件循环只持弱引用，任务可能被 GC 中途取消
            task = asyncio.create_task(on_raw_message(raw_msg))
            self._ws_tasks.add(task)
            task.add_done_callback(self._ws_tasks.discard)

        self.ws_client = MxWsClient(self.config, _on_raw_message, on_give_up=on_ws_give_up)
        await self.ws_client.run_forever()

    async def stop_ws(self):
        """停止 WebSocket 连接。"""
        if self.ws_client:
            await self.ws_client.stop()

    def _parse_message_to_post(self, raw_msg, kol=None):
        """
        将 MX 消息转换为 Post 对象。
        
        Args:
            raw_msg: 原始 MX 消息
            kol: KOL 信息（如果不提供则从缓存获取）
            
        Returns:
            Post 对象或 None
        """
        try:
            # 尝试多种方式获取 room_id
            room_id = raw_msg.get("rid") or raw_msg.get("room_id")
            if not room_id:
                logger.warning(f"MX message missing room id: {raw_msg}")
                return None

            # 获取 KOL 信息
            if kol is None:
                kol = self._get_room_info(room_id)
            if not kol:
                logger.warning(f"MX room {room_id} not found")
                return None

            # 尝试多种方式获取 msg 字段
            msg_field = raw_msg.get("msg") or raw_msg.get("message") or ""
            content, images, files = self._parse_msg_content(msg_field)

            # 完全解析不出文本/图片/文件的消息才丢弃：把原始 JSON 整包当正文入库
            # 会变成垃圾推送；纯文件消息（语音/PDF 等）已在解析时合成占位正文保留
            if not content and not images and not files:
                logger.debug("MX message without parsable content dropped: %s", str(raw_msg)[:200])
                return None

            # 尝试多种方式获取消息 ID；缺 id 时生成确定性兜底键，
            # 否则所有空 id 消息共用 '' 撞 (platform, external_id) 唯一约束被静默吞掉
            msg_id = raw_msg.get("id") or raw_msg.get("msgid") or raw_msg.get("msg_id")
            if msg_id:
                external_id = str(msg_id)
            else:
                external_id = self._fallback_external_id(room_id, raw_msg, content)
                logger.warning(
                    "MX message missing id, using fallback external_id=%s room=%s",
                    external_id, room_id,
                )
            # 尝试多种方式获取创建时间
            createtime = raw_msg.get("createtime") or raw_msg.get("created_at") or raw_msg.get("ts")

            return Post(
                platform=self.platform,
                kol_id=kol["id"],
                kol_name=kol["name"],
                external_id=external_id,
                title="",
                content=content,
                url="",
                published_at=self._format_published_at(createtime),
                post_type="post",
                images=images,
                detail=raw_msg,
            )
        except Exception as e:
            logger.error(f"Failed to parse MX message to post: {e}", exc_info=True)
            return None

    @staticmethod
    def _fallback_external_id(room_id, raw_msg, content):
        """缺 id 消息的确定性键：同一条消息两次到达（WS/轮询）生成同一键，去重仍有效。"""
        createtime = raw_msg.get("createtime") or raw_msg.get("created_at") or raw_msg.get("ts")
        basis = content or json.dumps(raw_msg, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.md5(basis.encode("utf-8")).hexdigest()[:12]
        if createtime:
            return f"{room_id}-{createtime}-{digest[:8]}"
        return f"{room_id}-{digest}"

    def _get_room_info(self, room_id):
        """
        获取房间信息（带 TTL 缓存，过期重查数据库）。

        Args:
            room_id: 房间 ID

        Returns:
            KOL 信息字典或 None
        """
        now = time.monotonic()
        cached = self._room_cache.get(room_id)
        if cached is not None:
            cached_at, cached_kol = cached
            ttl = ROOM_CACHE_TTL_SECONDS if cached_kol else ROOM_CACHE_MISS_TTL_SECONDS
            if now - cached_at < ttl:
                return cached_kol

        # 从数据库查询
        kol = None
        if self.db:
            kol = self.db.get_kol_by_external("mx", str(room_id))
            self._room_cache[room_id] = (now, kol)
        return kol

    def _parse_msg_content(self, msg_str):
        """
        解析 msg 字段，返回 (content, images, files)。

        Args:
            msg_str: msg 字段的 JSON 字符串

        Returns:
            (content, images, files) 元组。files 是非图片附件（语音/PDF 等）
            的 [{url, name}] 列表，原始 msg 已随 detail 入库，前端从
            detail.msg 自行解析渲染播放按钮/附件链接，这里只负责占位正文
        """
        if not msg_str:
            return "", [], []

        content_parts = []
        images = []
        files = []

        try:
            msg_list = json.loads(msg_str)
            if isinstance(msg_list, list):
                for item in msg_list:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        if item_type == "text":
                            text = item.get("msg", "")
                            if text:
                                content_parts.append(text)
                        elif item_type == "pic":
                            url = item.get("url", "")
                            if url:
                                self._append_image(images, url)
                        elif item_type == "file":
                            url = (item.get("url") or "").strip()
                            if url and looks_like_image_url(url, item.get("name") or ""):
                                self._append_image(images, url)
                            elif url:
                                files.append({"url": url, "name": item.get("name") or ""})
            elif isinstance(msg_list, str):
                # msg 字段是 JSON 编码的纯字符串
                content_parts.append(msg_list)
        except json.JSONDecodeError:
            # 如果不是 JSON，直接作为文本
            content_parts.append(msg_str)

        content = "\n".join(content_parts)
        # 纯文件消息（如语音）没有文字：合成占位正文保住消息不被丢弃，
        # 推送渠道和帖卡也不至于空正文
        if not content and files:
            if all(self._file_is_audio(f) for f in files):
                content = "[语音]"
            else:
                content = "[文件]"
        return normalize_mx_text(content), images[:4], files

    @staticmethod
    def _file_is_audio(file_item) -> bool:
        """按 URL path / 文件名扩展名判断附件是否音频（与前端播放按钮口径一致）。"""
        url_path = urlparse(str(file_item.get("url") or "")).path
        name = str(file_item.get("name") or "")
        return bool(AUDIO_EXT_RE.search(url_path) or AUDIO_EXT_RE.search(name))

    def _append_image(self, images, url):
        """图片统一走本地缓存，下载失败或内存库时保留原 URL。"""
        if self.db:
            images.append(cache_image_file(self.db, url, "mx_images", "/mx-images"))
        else:
            images.append(url)

    def get_ws_status(self):
        """
        获取 WebSocket 连接状态。

        Returns:
            状态字典（detail 用于区分未连接的具体原因）
        """
        if self.ws_client:
            client = self.ws_client
            gave_up = bool(getattr(client, "gave_up", False))
            if getattr(client, "manually_stopped", False):
                detail = "已手动断开"
            elif gave_up:
                # 12 秒后的那次重连也失败了：已永久放弃自动重连
                detail = "自动重连失败已停止，请手动接入"
            elif not client.connected:
                # 断线后等待 12 秒自动重连；任务已退出且未放弃时需管理员接入
                detail = "未连接，等待自动重连" if getattr(client, "running", False) else "已断线，请手动接入"
            else:
                detail = ""
            return {
                "connected": client.connected,
                "last_message_at": client.last_message_at,
                "gave_up": gave_up,
                "detail": detail,
            }
        if not self._ws_enabled:
            return {
                "connected": False,
                "last_message_at": None,
                "detail": "WS 未启用（ws_enabled=false）",
            }
        return {
            "connected": False,
            "last_message_at": None,
            "detail": "WS 尚未启动",
        }
