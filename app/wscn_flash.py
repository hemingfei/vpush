"""快讯（wallstreetcn live）播报的共用 Post 构造逻辑。

自动播报（scheduler.check_and_broadcast_wscn）与管理端手动播报
（api._broadcast_wscn_item）共用同一份口径：标题前缀（score≥2 为
「【重要快讯】」，否则「【快讯】」）、ISO 时间转北京时间裸字符串、
external_id=wscn_flash_{id} 天然去重——抽成单一实现防止两处漂移。
"""
from __future__ import annotations

from datetime import datetime

from .fetchers.base import CN_TZ, Post


def wscn_flash_title(item: dict) -> str:
    """快讯标题：score 决定前缀，高亮标题拼在前缀之后（无高亮仅前缀）。"""
    highlight = (item.get("highlight_title") or "").strip()
    prefix = "【重要快讯】" if int(item.get("score") or 1) >= 2 else "【快讯】"
    return f"{prefix}{highlight}" if highlight else prefix


def build_wscn_post(item: dict, kol_id: int, kol_name: str) -> Post | None:
    """快讯 item → 播报到 V 平台 KOL 的 Post；id 无效时返回 None。"""
    item_id = int(item.get("id") or 0)
    if item_id <= 0:
        return None
    # published_at 是 ISO 格式（含时区），转为北京时间裸字符串与现有帖子一致
    raw_ts = item.get("published_at") or ""
    try:
        dt = datetime.fromisoformat(raw_ts) if raw_ts else datetime.now(CN_TZ)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=CN_TZ)
        published_at = dt.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:  # noqa: BLE001 - 时间解析失败按当前时间兜底
        published_at = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return Post(
        platform="system",
        kol_id=kol_id,
        kol_name=kol_name,
        external_id=f"wscn_flash_{item_id}",
        title=wscn_flash_title(item),
        content=item.get("body") or "",
        url=(item.get("url") or "").strip(),
        published_at=published_at,
        post_type="wscn_flash",
    )
