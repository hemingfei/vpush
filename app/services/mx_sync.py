"""MX room sync service."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from ..config import MxConfig
from ..fetchers.mx.client import MXClient

logger = logging.getLogger(__name__)


class MXRoomSyncService:
    def __init__(self, config: MxConfig, db=None):
        self.config = config
        self.db = db
        self._last_sync: datetime | None = None

    async def sync_rooms(self):
        """Sync all MX rooms to KOLs."""
        if not self.config.token:
            logger.warning("MX token not configured, skipping room sync")
            return

        logger.info("Starting MX room sync")
        try:
            client = MXClient(self.config.api_base, self.config.token)
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
            name = room.get("title", f"MX Room {room_id}")
            avatar = room.get("avatar", "")
            intro = room.get("introduce", "")

            kol_id = self.db.add_kol(
                platform="mx",
                name=name,
                external_id=room_id,
                priority=False,
                secondary=False,
            )

            # Update avatar and extra data
            if avatar:
                self.db.update_kol_avatar(kol_id, avatar)
            
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
                self.db.update_kol_avatar(kol_id, avatar)
            
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
            
            # Merge
            current_dict.update(extra_data)
            new_extra = json.dumps(current_dict, ensure_ascii=False)
            
            # Update
            self.db._execute(
                "UPDATE kols SET extra_data = ? WHERE id = ?",
                (new_extra, kol_id),
            )
        except Exception as e:
            logger.error(f"Failed to update MX KOL extra_data id: {kol_id}: {e}", exc_info=True)

    async def start_periodic_sync(self):
        """Start periodic room sync."""
        interval_hours = self.config.sync_interval_hours or 1
        interval = interval_hours * 3600

        async def sync_loop():
            while True:
                try:
                    await asyncio.sleep(interval)
                    if self.config.enabled:
                        await self.sync_rooms()
                except Exception as e:
                    logger.error(f"MX periodic sync error: {e}", exc_info=True)

        asyncio.create_task(sync_loop())
        logger.info(f"MX periodic sync started, interval: {interval_hours}h")
