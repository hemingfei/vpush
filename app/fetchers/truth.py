"""Truth Social（特朗普）抓取：直连 truthsocial.com 的 Mastodon 公开 API。

匿名即可读取公开账号的 statuses（无需账号/token），Cloudflare 靠 curl_cffi
chrome 指纹伪装通过（生产容器内实测：普通 httpx 403、指纹伪装 200）；单页
条数服务端封顶 20。CNN 维护的全量存档 JSON（文件 ~17MB、约 30 秒更新，新帖
插在数组头部）保留作兜底：首次 30 天基线（API 单页盖不满）、增量超窗整档
回补、直连失败时降级——常态只 Range 拉头部 512KB 纯文本，必须禁 gzip，否则
Range 切在压缩流上无法解码。两源帖子 id 同为 status id，水位线与去重无缝衔接。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

import httpx
from curl_cffi import requests as cffi

from .base import CN_TZ, Fetcher, Post, strip_html

logger = logging.getLogger(__name__)

TRUTH_API_BASE = "https://truthsocial.com"
STATUS_LIMIT = 20  # 服务端对 limit 的实际封顶，传再大也只回 20 条
ARCHIVE_URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"
HEAD_RANGE_BYTES = 524288  # 常态窗口：约可覆盖上千条新帖
BASELINE_DAYS = 30
TRUMP_X_AVATAR = (
    "https://pbs.twimg.com/profile_images/874276197357596672/kUuht00m_400x400.jpg"
)
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
_PARA_RE = re.compile(r"</p>\s*<p[^>]*>")


def parse_archive_head(raw: bytes) -> list[dict]:
    """解析头部 Range 字节：在最后一个完整对象边界截断后补右括号。"""
    text = raw.decode("utf-8", "replace")
    cut = text.rfind("},\n  {")
    if cut < 0:
        raise ValueError("存档窗口内没有完整条目")
    return json.loads(text[: cut + 1] + "\n]")


def status_to_entry(status: dict) -> dict | None:
    """Mastodon status → CNN 存档条目同构 dict，复用既有的过滤/入库链路。"""
    external_id = str(status.get("id") or "").strip()
    if not external_id:
        return None
    inner = status.get("reblog") or status  # 转发取原帖内容，id/时间用转发层
    raw = str(inner.get("content") or "")
    return {
        "id": external_id,
        "created_at": status.get("created_at"),
        "content": strip_html(_PARA_RE.sub("\n", raw)),
        "media": [
            m["url"]
            for m in (inner.get("media_attachments") or [])
            if m.get("type") == "image" and m.get("url")
        ],
        "url": status.get("url") or inner.get("url") or "",
    }


def entry_dt(entry: dict) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(entry.get("created_at") or ""))
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
        self._account_ids: dict[str, str] = {}

    def fetch(self, kol: dict) -> list[Post]:
        last_id = self.db.max_external_id_num(self.platform) if self.db else 0
        if last_id <= 0:
            # 首次基线：仍整档拉 CNN 存档（API 单页 20 条盖不满 30 天），
            # baseline_ready 会拦住历史帖推送
            entries = self._request(full=True)
            cutoff = datetime.now(CN_TZ) - timedelta(days=BASELINE_DAYS)
            entries = [e for e in entries if (entry_dt(e) or cutoff) >= cutoff]
        else:
            try:
                entries = self._request_api(kol)
            except Exception as exc:  # noqa: BLE001 - 直连失败降级存档
                logger.warning("Truth 直连 API 失败，降级 CNN 存档：%s", exc)
                entries = self._request(full=False)
            if entries and min(int(e["id"]) for e in entries) > last_id:
                # 窗口没盖住上次位置（停机积压超约 3 小时）：整档回补
                logger.warning("Truth 增量窗口未覆盖上次位置，整档回补")
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

    def _request_api(self, kol: dict) -> list[dict]:
        acct = (kol.get("external_id") or "").strip() or "realDonaldTrump"
        account_id = self._account_ids.get(acct)
        if not account_id:
            account = self._api_get(f"/api/v1/accounts/lookup?acct={acct}")
            account_id = str(account.get("id") or "")
            if not account_id:
                raise RuntimeError(f"Truth lookup 未返回 id acct={acct}")
            self._account_ids[acct] = account_id
        statuses = self._api_get(
            f"/api/v1/accounts/{account_id}/statuses?limit={STATUS_LIMIT}"
        )
        return [e for e in map(status_to_entry, statuses) if e]

    def _api_get(self, path: str):
        # CF 只放行很新的指纹（chrome124/131 实测 403），优先各环境 curl_cffi
        # 支持的最新 chrome；403 时换 safari 再试一轮，仍失败由上层降级存档。
        last_error = "not tried"
        for impersonate in ("chrome", "safari"):
            with cffi.Session(impersonate=impersonate, timeout=25) as client:
                resp = client.get(
                    TRUTH_API_BASE + path, headers={"Accept": "application/json"}
                )
            if resp.status_code == 200:
                return resp.json()
            last_error = f"HTTP {resp.status_code} ({impersonate})"
            if resp.status_code != 403:
                break  # 5xx/重定向换指纹没意义，直接降级存档
        raise RuntimeError(f"Truth API 拉取失败 {last_error}")

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
