"""MX room sync service."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime

from ..avatar_cache import cache_avatar
from ..config import MxConfig
from ..fetchers.mx.client import MXClient, MXTokenExpiredError

logger = logging.getLogger(__name__)


class MXRoomSyncService:
    def __init__(self, config: MxConfig, db=None):
        self.config = config
        self.db = db
        self._last_sync: datetime | None = None
        self._stopped = False
        # 复用同一客户端：每次同步都新建连接会产生一串「新 TLS 握手」事件，
        # 同指纹的连接在风控日志里可被聚合计数
        self._client: MXClient | None = None

    def _get_client(self) -> MXClient:
        if self._client is None:
            self._client = MXClient(self.config.api_base, self.config.token)
        return self._client

    def _notify_error(self, message: str):
        """同步失败的统一出口：当前由调用方（开窗会话）捕获后走系统告警，保留挂点。"""
        logger.error("MX room sync error: %s", message)

    async def sync_rooms(self) -> int:
        """Sync all MX rooms to KOLs（同步 HTTP/DB 走线程池，不阻塞事件循环）。

        Returns:
            本次拉取到的房间数量（供开窗/登录报告展示）。
        """
        return await asyncio.to_thread(self._sync_rooms_blocking)

    def boot_sequence(self) -> list[dict]:
        """官方网页端冷启动的只读启动序列（room/list 除外，由 sync_rooms 负责）。

        顺序与真实打开网页一致：user/info → system/config → msg/tip →
        grouplist → 平台公告，全部走同一个复用客户端（同一连接）。返回逐接口
        报告 [{name, ok, detail, ms}]；TOKEN 过期向上抛出（触发熔断，报告里
        已含失败步骤）；其余单个请求失败记为失败项但不中断——对齐是最佳努力，
        不能反过来影响消息链路。
        """
        client = self._get_client()
        report: list[dict] = []

        def user_info_detail(result):
            info = (result or {}).get("info") or {}
            remote = info.get("token")
            if remote and remote != self.config.token:
                logger.warning(
                    "MX user/info 返回 token 与本地配置不一致（服务端可能已轮换），"
                    "请尽快到后台「数据源 → MX」更换 TOKEN"
                )
            return f"账号 {info.get('user') or '?'}"

        def tip_detail(result):
            data = (result or {}).get("data") or {}
            return f"总未读 {data.get('count', '?')}"

        steps = (
            ("user/info", client.user_info, user_info_detail),
            ("system/config", client.system_config, None),
            ("msg/tip", client.msg_tip, tip_detail),
            ("room/grouplist", client.room_grouplist,
             lambda r: f"{len((r or {}).get('list') or [])} 个分组"),
            ("master-notice", client.master_notice,
             lambda r: f"{len((r or {}).get('list') or [])} 条平台公告"),
        )
        for name, fn, detail_fn in steps:
            started = time.monotonic()
            try:
                result = fn()
                detail = detail_fn(result) if detail_fn else "ok"
                report.append({"name": name, "ok": True, "detail": detail,
                               "ms": int((time.monotonic() - started) * 1000)})
            except MXTokenExpiredError:
                report.append({"name": name, "ok": False, "detail": "TOKEN 已过期/无效",
                               "ms": int((time.monotonic() - started) * 1000)})
                raise
            except Exception as exc:  # noqa: BLE001 - 对齐请求失败不影响消息链路
                logger.warning("MX 启动序列 %s 失败（忽略）: %s", name, exc)
                report.append({"name": name, "ok": False, "detail": str(exc)[:80],
                               "ms": int((time.monotonic() - started) * 1000)})
        return report

    def _sync_rooms_blocking(self) -> int:
        if not self.config.token:
            logger.warning("MX token not configured, skipping room sync")
            return 0
        logger.info("Starting MX room sync")
        client = self._get_client()
        try:
            rooms = client.get_rooms()
            logger.info(f"Fetched {len(rooms)} MX rooms")

            for room in rooms:
                self._sync_room(room)

            self._last_sync = datetime.now()
            logger.info(f"MX room sync completed, processed {len(rooms)} rooms")
            return len(rooms)
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

    def stop(self):
        """停止同步服务：关闭内部缓存的 HTTP 会话（同步由开窗动作触发，无后台任务）。"""
        self._stopped = True
        if self._client is not None:
            self._client.close()
            self._client = None
