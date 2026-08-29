"""MX room sync service."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from ..avatar_cache import cache_avatar
from ..config import MxConfig
from ..fetchers.mx.client import MXClient

logger = logging.getLogger(__name__)


class MXRoomSyncService:
    def __init__(self, config: MxConfig, db=None):
        self.config = config
        self.db = db
        self._last_sync: datetime | None = None
        self._sync_task: asyncio.Task | None = None
        self._initial_sync_task: asyncio.Task | None = None
        self._stopped = False

    async def sync_rooms(self):
        """Sync all MX rooms to KOLs（同步 HTTP/DB 走线程池，不阻塞事件循环）。"""
        await asyncio.to_thread(self._sync_rooms_blocking)

    def _sync_rooms_blocking(self):
        if not self.config.token:
            logger.warning("MX token not configured, skipping room sync")
            return

        logger.info("Starting MX room sync")
        client = MXClient(self.config.api_base, self.config.token)
        try:
            rooms = client.get_rooms()
            logger.info(f"Fetched {len(rooms)} MX rooms")

            for room in rooms:
                self._sync_room(room)

            self._last_sync = datetime.now()
            logger.info(f"MX room sync completed, processed {len(rooms)} rooms")
        except Exception as e:
            logger.error(f"MX room sync failed: {e}", exc_info=True)
            raise
        finally:
            client.close()

    def _sync_room(self, room: dict):
        """Sync a single room to KOL."""
        room_id = str(room.get("id", ""))
        if not room_id:
            return

        # Get extra data
        extra_data = {
            "teaname": room.get("teaname", ""),
            "introduce": room.get("introduce", ""),
            "message_today": room.get("message_today", 0),
            "msgtime": room.get("msgtime", ""),
            "createtime": room.get("createtime", ""),
            "star": room.get("star", 0) == 1,
            "enabled": True,
            "show_in_plaza": True,
        }

        if self.db:
            # Check if KOL exists
            existing = self.db.get_kol_by_external("mx", room_id)
            if existing:
                # Update existing KOL
                self._update_kol(existing["id"], room, extra_data)
            else:
                # Create new KOL
                self._create_kol(room, extra_data)

    def _create_kol(self, room: dict, extra_data: dict):
        """Create a new KOL from MX room."""
        if not self.db:
            return
        try:
            room_id = str(room.get("id", ""))
            name = room.get("title") or f"MX Room {room_id}"
            avatar = room.get("avatar", "")

            kol_id = self.db.add_kol(
                platform="mx",
                name=name,
                external_id=room_id,
                priority=False,
                secondary=False,
            )

            # 下载头像到本地缓存，避免第三方图床过期后头像挂掉
            if avatar:
                cache_avatar(self.db, kol_id, avatar)

            self._update_kol_extra(kol_id, extra_data)
            logger.info(f"Created MX KOL: {name} (id: {kol_id})")
        except Exception as e:
            logger.error(f"Failed to create MX KOL: {e}", exc_info=True)

    def _update_kol(self, kol_id: int, room: dict, extra_data: dict):
        """Update an existing KOL with MX room data."""
        if not self.db:
            return
        try:
            name = room.get("title")
            avatar = room.get("avatar", "")

            updates = {}
            if name:
                updates["name"] = name
            if updates:
                self.db.update_kol(kol_id, **updates)

            if avatar:
                cache_avatar(self.db, kol_id, avatar)

            self._update_kol_extra(kol_id, extra_data)
            logger.debug(f"Updated MX KOL id: {kol_id}")
        except Exception as e:
            logger.error(f"Failed to update MX KOL id: {kol_id}: {e}", exc_info=True)

    def _update_kol_extra(self, kol_id: int, extra_data: dict):
        """Update KOL's extra_data field."""
        if not self.db:
            return
        try:
            # Get current extra data
            rows = self.db._rows("SELECT extra_data FROM kols WHERE id = ?", (kol_id,))
            if not rows:
                return
            current = rows[0]["extra_data"] or ""
            try:
                current_dict = json.loads(current) if current else {}
            except (json.JSONDecodeError, ValueError):
                current_dict = {}

            # Preserve existing enabled and show_in_plaza settings
            preserved_enabled = current_dict.get("enabled")
            preserved_show_in_plaza = current_dict.get("show_in_plaza")

            # Merge
            current_dict.update(extra_data)

            # Restore preserved settings
            if preserved_enabled is not None:
                current_dict["enabled"] = preserved_enabled
            if preserved_show_in_plaza is not None:
                current_dict["show_in_plaza"] = preserved_show_in_plaza

            new_extra = json.dumps(current_dict, ensure_ascii=False)

            # Update
            self.db._execute(
                "UPDATE kols SET extra_data = ? WHERE id = ?",
                (new_extra, kol_id),
            )
        except Exception as e:
            logger.error(f"Failed to update MX KOL extra_data id: {kol_id}: {e}", exc_info=True)

    async def start_periodic_sync(self):
        """Start periodic room sync.

        初始同步放在后台任务执行：146 个房间逐个处理（含最多 15s 超时的头像
        下载）可能耗时数分钟，await 它会阻塞 WS 与调度启动——历史上表现为
        「后端启动后好几分钟连不上 WebSocket」。
        """
        if self._sync_task is not None and not self._sync_task.done():
            return
        self._stopped = False

        async def run_initial_sync():
            try:
                await self.sync_rooms()
            except Exception as e:  # noqa: BLE001 - 后台任务自行吞错记日志
                logger.error(f"MX initial room sync error: {e}", exc_info=True)

        if self._initial_sync_task is None or self._initial_sync_task.done():
            # 持有任务引用：事件循环只持弱引用，不保存可能被 GC 中途取消
            self._initial_sync_task = asyncio.create_task(run_initial_sync())

        interval_hours = self.config.sync_interval_hours or 1
        interval = interval_hours * 3600

        async def sync_loop():
            while not self._stopped:
                try:
                    await asyncio.sleep(interval)
                    if self.config.enabled and not self._stopped:
                        await self.sync_rooms()
                except Exception as e:
                    logger.error(f"MX periodic sync error: {e}", exc_info=True)

        # 持有任务引用：事件循环只持弱引用，不保存可能被 GC 中途取消
        self._sync_task = asyncio.create_task(sync_loop())
        logger.info(f"MX periodic sync started, interval: {interval_hours}h")

    def stop(self):
        """停止定时同步任务（同步方法，可在非事件循环上下文调用）。"""
        self._stopped = True
        for task in (self._sync_task, self._initial_sync_task):
            if task is not None and not task.done():
                task.cancel()
        self._sync_task = None
        self._initial_sync_task = None
