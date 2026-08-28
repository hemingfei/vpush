"""MX platform fetcher."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable

from ...avatar_cache import cache_avatar, cache_image_file
from ..base import Fetcher, Post, catchup_pages, format_published_at
from .client import MXClient
from .crypto import decrypt_content
from .ws import MxWsClient

logger = logging.getLogger(__name__)


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
        self.page_size = getattr(source_config, "page_size", 50)
        self.ws_client = None
        self._room_cache = {}
        self._ws_enabled = getattr(source_config, "ws_enabled", True)

    def fetch(self, kol):
        room_id = int(kol["external_id"])
        posts = []

        try:
            # 直接获取最新消息
            messages = self.mx_client.get_room_history(room_id, limit=self.page_size)
            posts = self._build_posts(kol, messages)
        except Exception as e:
            logger.error("Failed to fetch MX room history: %s", e, exc_info=True)
            raise

        # 更新头像
        if posts and self.db:
            extra = {}
            try:
                if kol.get("extra_data"):
                    extra = json.loads(kol["extra_data"]) if isinstance(kol["extra_data"], str) else kol["extra_data"]
            except Exception:
                pass
            avatar = extra.get("avatar", "")
            if avatar and avatar != (self.db.get_kol(kol["id"]) or {}).get("avatar_url"):
                self.db.update_kol_avatar(kol["id"], cache_avatar(self.db, kol["id"], avatar))
        
        return posts

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

    async def start_ws(self, on_message):
        """
        启动 WebSocket 连接并监听实时消息。
        
        Args:
            on_message: 回调函数，当收到新消息时调用（可以是异步函数）
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
            # 在新的任务中运行异步回调，避免阻塞事件循环
            asyncio.create_task(on_raw_message(raw_msg))

        self.ws_client = MxWsClient(self.config, _on_raw_message)
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
            content, images = self._parse_msg_content(msg_field)
            
            # 如果没有内容，尝试从其他字段获取
            if not content and not images:
                # 尝试直接解密内容
                content = decrypt_content(raw_msg) or ""
                if not content and not images:
                    # 还是没内容，尝试把整个消息的 JSON 作为内容
                    content = json.dumps(raw_msg, ensure_ascii=False)

            # 尝试多种方式获取消息 ID
            msg_id = raw_msg.get("id") or raw_msg.get("msgid") or raw_msg.get("msg_id")
            # 尝试多种方式获取创建时间
            createtime = raw_msg.get("createtime") or raw_msg.get("created_at") or raw_msg.get("ts")

            return Post(
                platform=self.platform,
                kol_id=kol["id"],
                kol_name=kol["name"],
                external_id=str(msg_id) if msg_id else "",
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

    def _get_room_info(self, room_id):
        """
        获取房间信息（优先从缓存获取）。
        
        Args:
            room_id: 房间 ID
            
        Returns:
            KOL 信息字典或 None
        """
        if room_id in self._room_cache:
            return self._room_cache[room_id]

        # 从数据库查询
        if self.db:
            kol = self.db.get_kol_by_external("mx", str(room_id))
            if kol:
                self._room_cache[room_id] = kol
                return kol

        return None

    def _parse_msg_content(self, msg_str):
        """
        解析 msg 字段，返回 (content, images)。
        
        Args:
            msg_str: msg 字段的 JSON 字符串
            
        Returns:
            (content, images) 元组
        """
        if not msg_str:
            return "", []

        content_parts = []
        images = []

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
                                if self.db:
                                    cached_url = cache_image_file(self.db, url, "mx_images", "/mx-images")
                                    images.append(cached_url)
                                else:
                                    images.append(url)
        except json.JSONDecodeError:
            # 如果不是 JSON，直接作为文本
            content_parts.append(msg_str)

        content = "\n".join(content_parts)
        return content, images[:4]

    def get_ws_status(self):
        """
        获取 WebSocket 连接状态。
        
        Returns:
            状态字典
        """
        if self.ws_client:
            return {
                "connected": self.ws_client.connected,
                "last_message_at": self.ws_client.last_message_at,
            }
        return {"connected": False, "last_message_at": None}
