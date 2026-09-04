"""Truth Social（特朗普）抓取：CNN 维护的全量存档 JSON。

文件 ~17MB、约 30 秒更新，新帖插在数组头部（id 单调递增字符串）。常态只
Range 拉头部 512KB 纯文本——必须禁 gzip，否则 Range 切在压缩流上无法解码；
新帖爆发超出窗口或首次基线时才整档拉取，基线只入库近 30 天。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import httpx

from .base import CN_TZ, Fetcher, Post

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"
HEAD_RANGE_BYTES = 524288  # 常态窗口：约可覆盖上千条新帖
BASELINE_DAYS = 30
TRUMP_X_AVATAR = (
    "https://pbs.twimg.com/profile_images/874276197357596672/kUuht00m_400x400.jpg"
)
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def parse_archive_head(raw: bytes) -> list[dict]:
    """解析头部 Range 字节：在最后一个完整对象边界截断后补右括号。"""
    text = raw.decode("utf-8", "replace")
    cut = text.rfind("},\n  {")
    if cut < 0:
        raise ValueError("存档窗口内没有完整条目")
    return json.loads(text[: cut + 1] + "\n]")


def entry_dt(entry: dict) -> datetime | None:
    try:
        dt = datetime.fromisoformat(
            str(entry.get("created_at") or "").replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(CN_TZ)


def entry_published_at(entry: dict) -> str:
    dt = entry_dt(entry)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else str(entry.get("created_at") or "")


def entry_images(entry: dict) -> list[str]:
    return [
        u for u in (entry.get("media") or [])
        if str(u).lower().split("?", 1)[0].endswith(_IMAGE_EXTS)
    ]


class TruthFetcher(Fetcher):
    platform = "truth"

    def __init__(self, source_config=None, db=None):
        super().__init__(source_config)
        self.db = db

    def fetch(self, kol: dict) -> list[Post]:
        last_id = self.db.max_external_id_num(self.platform) if self.db else 0
        if last_id <= 0:
            # 首次基线：整档拉取，只入库近 30 天（baseline_ready 会拦住历史帖推送）
            entries = self._request(full=True)
            cutoff = datetime.now(CN_TZ) - timedelta(days=BASELINE_DAYS)
            entries = [e for e in entries if (entry_dt(e) or cutoff) >= cutoff]
        else:
            entries = self._request(full=False)
            if entries and min(int(e["id"]) for e in entries) > last_id:
                # 窗口没盖住上次位置（爆发超窗/停机积压）：整档回补
                logger.warning("Truth 存档头部窗口未覆盖上次位置，整档回补")
                entries = self._request(full=True)
        posts = []
        for entry in entries:
            try:
                if int(str(entry.get("id") or 0)) <= last_id:
                    continue
            except (TypeError, ValueError):
                continue
            post = self._to_post(kol, entry)
            if post:
                posts.append(post)
        self._bootstrap_avatar(kol)
        return posts

    def _request(self, full: bool) -> list[dict]:
        # Range 字节必须在纯文本上切：显式 identity 禁掉 httpx 默认的 gzip
        headers = {"Accept-Encoding": "identity"}
        if not full:
            headers["Range"] = f"bytes=0-{HEAD_RANGE_BYTES - 1}"
        with httpx.Client(timeout=60, headers=headers) as client:
            resp = client.get(ARCHIVE_URL)
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"Truth 存档拉取失败 HTTP {resp.status_code}")
        if full:
            return resp.json()
        return parse_archive_head(resp.content)

    def _to_post(self, kol: dict, entry: dict) -> Post | None:
        external_id = str(entry.get("id") or "").strip()
        content = str(entry.get("content") or "").strip()
        images = entry_images(entry)
        if not external_id or (not content and not images):
            return None
        url = str(entry.get("url") or "")
        if not url:
            url = f"https://truthsocial.com/@realDonaldTrump/{external_id}"
        title = content.splitlines()[0][:80] if content else "图片"
        return Post(
            platform=self.platform,
            kol_id=kol["id"],
            kol_name=kol["name"],
            external_id=external_id,
            title=title,
            content=content or "图片",
            url=url,
            published_at=entry_published_at(entry),
            images=images,
        )

    def _bootstrap_avatar(self, kol: dict) -> None:
        """头像取川普 X 账号头像；只在头像为空时下载一次，失败下轮再试。"""
        if self.db is None or kol.get("avatar_url"):
            return
        try:
            from ..avatar_cache import cache_avatar

            avatar = cache_avatar(self.db, kol["id"], TRUMP_X_AVATAR)
            if avatar != TRUMP_X_AVATAR:
                logger.info("Truth 头像已缓存 kol=%s", kol["name"])
        except Exception:  # noqa: BLE001 - 头像失败不影响抓取
            logger.warning("Truth 头像下载失败 kol=%s", kol["name"])
