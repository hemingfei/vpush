"""MX room sync service."""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Any

from ..avatar_cache import cache_avatar
from ..config import MxConfig
from ..fetchers.mx.client import MXClient

logger = logging.getLogger(__name__)

# 房间列表同步间隔：每轮在 2-6 小时之间随机取值。
# 精确的固定周期（每小时/每 24 小时整）是风控日志里最直白的机器信号，
# 随机化后相邻两次同步的间隔不可预测。
SYNC_MIN_INTERVAL_SECONDS = 2 * 3600
SYNC_MAX_INTERVAL_SECONDS = 6 * 3600


class MXRoomSyncService:
    def __init__(self, config: MxConfig, db=None, on_error=None, should_run=None):
        self.config = config
        self.db = db
        # on_error(str)：房间同步失败时回调（调度器用它走系统 KOL「系统通知」告警）
        self.on_error = on_error
        # should_run()：同步执行前的门控（每日运行窗口 / TOKEN 状态）
        self.should_run = should_run
        self._last_sync: datetime | None = None
        self._sync_task: asyncio.Task | None = None
        self._initial_sync_task: asyncio.Task | None = None
        self._stopped = False
        # 复用同一客户端：每次同步都新建连接会产生一串「新 TLS 握手」事件，
        # 同指纹的连接在风控日志里可被聚合计数
        self._client: MXClient | None = None

    def _get_client(self) -> MXClient:
        if self._client is None:
            self._client = MXClient(self.config.api_base, self.config.token)
        return self._client

    def _notify_error(self, message: str):
        if self.on_error is None:
            return
        try:
            self.on_error(message)
        except Exception:  # noqa: BLE001 - 告警失败不影响同步任务
            logger.error("MX sync on_error 回调失败", exc_info=True)

    async def sync_rooms(self):
        """Sync all MX rooms to KOLs（同步 HTTP/DB 走线程池，不阻塞事件循环）。"""
        await asyncio.to_thread(self._sync_rooms_blocking)

    def _sync_rooms_blocking(self):
        if not self.config.token:
            logger.warning("MX token not configured, skipping room sync")
            return

        logger.info("Starting MX room sync")
        client = self._get_client()
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
            # 初始同步同样受窗口门控：窗口外启动服务时不产生 MX 请求
            if self.should_run is not None and not self.should_run():
                logger.info("MX 初始同步跳过：不在运行窗口内")
                return
            try:
                await self.sync_rooms()
            except Exception as e:  # noqa: BLE001 - 后台任务自行吞错记日志
                logger.error(f"MX initial room sync error: {e}", exc_info=True)
                self._notify_error(f"房间同步失败：{e}")

        if self._initial_sync_task is None or self._initial_sync_task.done():
            # 持有任务引用：事件循环只持弱引用，不保存可能被 GC 中途取消
            self._initial_sync_task = asyncio.create_task(run_initial_sync())

        async def sync_loop():
            # 每轮随机睡 2-6 小时再尝试一次：窗口外/TOKEN 失效时只跳过本次，
            # 不产生任何 MX 请求，下一次尝试仍是随机 2-6 小时之后
            while not self._stopped:
                try:
                    await asyncio.sleep(
                        random.uniform(SYNC_MIN_INTERVAL_SECONDS, SYNC_MAX_INTERVAL_SECONDS)
                    )
                    if self._stopped:
                        break
                    if not self.config.enabled:
                        continue
                    if self.should_run is not None and not self.should_run():
                        continue
                    await self.sync_rooms()
                except Exception as e:
                    logger.error(f"MX periodic sync error: {e}", exc_info=True)
                    self._notify_error(f"房间同步失败：{e}")

        # 持有任务引用：事件循环只持弱引用，不保存可能被 GC 中途取消
        self._sync_task = asyncio.create_task(sync_loop())
        logger.info(
            f"MX periodic sync started, interval: random "
            f"{SYNC_MIN_INTERVAL_SECONDS // 3600}-{SYNC_MAX_INTERVAL_SECONDS // 3600}h"
        )

    def stop(self):
        """停止定时同步任务（同步方法，可在非事件循环上下文调用）。"""
        self._stopped = True
        for task in (self._sync_task, self._initial_sync_task):
            if task is not None and not task.done():
                task.cancel()
        self._sync_task = None
        self._initial_sync_task = None
        if self._client is not None:
            self._client.close()
            self._client = None
