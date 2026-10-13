"""MX 会话中段「真人点房间」活动模拟。

行为假设（2026-10-13）：vpush 的 WS 会话连上后完全静默——只答心跳 pong 与
ACK，会话中段零应用层请求；而真人使用时每次点选房间必发 room/view +
room/notice 两个 HTTP（2026-09-02 抓包场景 S2 实测）。若平台以「会话中段
零用户操作」为画像特征对 token 置「连上即断」标记（下午风暴的候选成因之一，
与周期性连接回收并行存在，见 mx-单会话互踢诊断-2026-10-12），本模拟即为
对冲；对回收本身无效——回收与行为无关，别指望它消除常态踢连。

行为口径：会话存活且 WS 在线期间，每 5-10 分钟（随机）「点开」一个启用的
房间——room/view（进房/已读上报）→ 人形微间隔 → room/notice（房间公告），
与官方点选房间的请求链逐请求同形；绝不发 msg/list（官方 S2 点选不拉历史，
消息渲染自本地缓存，vpush 的等价物是数据库 + WS 全房间实时推送）。

开关：MX_ACTIVITY_SIM=0/false/no 关闭（默认开启）。房间从数据库启用的 MX
KOL 里随机挑（排除上一个，避免背靠背重复点同一房间）；无可点集合则本轮
跳过、只顺延节奏。最后一次点开的房间记入 settings 键 ``mx_last_room``，
供会话启动时「恢复上次打开的房间」复用（官方 localStorage 语义的等价物）。
"""
from __future__ import annotations

import logging
import os
import random
import time

from ..fetchers.mx.client import MXTokenExpiredError
from ..fetchers.mx.human import human_pause

logger = logging.getLogger(__name__)

# 点房间的间隔秒数（随机区间）：用户口径 5-10 分钟。真人盯盘时每几分钟切
# 一次房间是常态，量级为每小时个位数请求，远低于任何攻击性频率
ACTIVITY_INTERVAL_RANGE = (300.0, 600.0)

# 最后点开的房间（settings 键）：会话启动「恢复上次打开的房间」用
LAST_ROOM_SETTING_KEY = "mx_last_room"


def activity_enabled() -> bool:
    return os.environ.get("MX_ACTIVITY_SIM", "1").strip().lower() not in (
        "0", "false", "no",
    )


class MXRoomActivity:
    """会话中段点房间模拟器：节奏状态 + 单次「点开房间」请求链。"""

    def __init__(self, client, db=None):
        self.client = client
        self.db = db
        self._last_rid: str | None = None
        # 会话开启即武装：首次点房间落在一个随机间隔之后（启动序列本身已是
        # 官方冷启动足迹，紧跟着就点房间反而不像「打开页面先看一眼」）
        self._next_fire = time.monotonic() + self._interval()

    @staticmethod
    def enabled() -> bool:
        return activity_enabled()

    @staticmethod
    def _interval() -> float:
        return random.uniform(*ACTIVITY_INTERVAL_RANGE)

    def _pick_room(self) -> dict | None:
        """随机挑一个启用的 MX 房间（排除上一个）；无可挑返回 None。"""
        if self.db is None:
            return None
        kols = [
            k for k in self.db.list_kols(platform="mx")
            if k.get("enabled") and str(k.get("external_id") or "").strip()
        ]
        if not kols:
            return None
        fresh = [k for k in kols if str(k.get("external_id")) != self._last_rid]
        return random.choice(fresh or kols)

    async def maybe_click(self, *, session_active: bool, ws_connected: bool) -> str:
        """到期则点一次房间；返回动作描述（房间名(rid)），未触发返回空串。

        闸门（会话存活 + WS 在线）不满足时保留到期状态——页面半开不点房间，
        但「该点了」这件事不算消失，恢复在线后的下个 tick 立即补上。
        MXTokenExpiredError 向上抛（调用方走统一熔断），其余单次失败只顺延。
        """
        if not self.enabled() or self._next_fire is None:
            return ""
        if not (session_active and ws_connected):
            return ""
        if time.monotonic() < self._next_fire:
            return ""
        kol = self._pick_room()
        if kol is None:
            self._next_fire = time.monotonic() + self._interval()
            return ""
        rid = str(kol["external_id"])
        try:
            self.client.room_view(int(rid))
            human_pause("room_open")
            self.client.room_notice(int(rid))
        except MXTokenExpiredError:
            raise
        except Exception as exc:  # noqa: BLE001 - 单次失败只顺延节奏
            logger.warning("MX 会话活动模拟失败 room=%s: %s", rid, exc, exc_info=True)
            self._next_fire = time.monotonic() + self._interval()
            return ""
        self._last_rid = rid
        self._next_fire = time.monotonic() + self._interval()
        if self.db is not None:
            try:
                self.db.set_setting(LAST_ROOM_SETTING_KEY, rid)
            except Exception:  # noqa: BLE001 - 记录失败不影响模拟本身
                logger.debug("MX 会话活动模拟写 mx_last_room 失败", exc_info=True)
        logger.info(
            "MX 会话活动模拟：点开房间 %s(%s)（view+notice）",
            kol.get("name"), rid,
        )
        return f"{kol.get('name')}({rid})"
