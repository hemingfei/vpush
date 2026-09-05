"""抓取器基础：Post 数据类与公共文本清理。"""
from __future__ import annotations

import email.utils
import html
import logging
import re
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# 项目面向中文社交平台，发布时间统一按北京时间展示，避免依赖服务器时区
CN_TZ = timezone(timedelta(hours=8))
PLATFORM_LABELS = {
    "xueqiu": "雪球",
    "combination": "雪球组合",
    "weibo": "微博",
    "twitter": "X",
    "ima": "ima",
    "zsxq": "知识星球",
    "truth": "Truth Social",
}


def show_original(platform: str, url: str | None) -> bool:
    """星球原文需登录且无稳定外链，广场/推送都不放「查看原文」。"""
    return bool(url) and platform != "zsxq"


@dataclass
class Post:
    platform: str
    kol_id: int
    kol_name: str
    external_id: str
    title: str
    content: str
    url: str
    published_at: str
    category: str = ""
    post_type: str = ""
    detail: dict | None = None
    images: list[str] = field(default_factory=list)
    favorite: bool = False
    # None = 尚未执行规则打标（pending）；空列表 = 已执行但零命中；非空 = 已打标
    tags: list[str] | None = None
    title_src: str = ""
    content_src: str = ""


_COLLAPSED_TRANSLATION_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)


def is_collapsed_translation(translated: str, source: str) -> bool:
    """X 转帖/带链接帖的官方翻译常收成省略号或单个标点，这种译文不能覆盖原文。"""
    text = (translated or "").strip()
    original = (source or "").strip()
    if not original or text == original:
        return False
    if not text:
        return True
    if _COLLAPSED_TRANSLATION_RE.fullmatch(text) and len(original) > 3:
        return True
    return len(text) <= 4 and len(original) >= 20


def twitter_translate_enabled(user: dict | None) -> bool:
    """默认看中文译文；显式关掉才回原文。"""
    if not user or user.get("translate_twitter") is None:
        return True
    return bool(user.get("translate_twitter"))


_TRANSLATE_PLATFORMS = frozenset({"twitter", "truth"})


def has_stored_translation(post: Post | dict) -> bool:
    if isinstance(post, dict):
        src = (post.get("content_src") or "").strip()
        content = (post.get("content") or "").strip()
    else:
        src = (post.content_src or "").strip()
        content = (post.content or "").strip()
    return bool(src) and src != content


def with_twitter_display(post: Post, translate: bool) -> Post:
    if post.platform not in _TRANSLATE_PLATFORMS:
        return post
    if translate:
        if post.content_src and is_collapsed_translation(post.content, post.content_src):
            return replace(
                post,
                title=post.title_src or post.title,
                content=post.content_src,
            )
        return post
    title = post.title_src or post.title
    content = post.content_src or post.content
    if title == post.title and content == post.content:
        return post
    return replace(post, title=title, content=content)


def with_twitter_display_row(row: dict, translate: bool) -> dict:
    if (row.get("platform") or "") not in _TRANSLATE_PLATFORMS:
        return row
    src_t = row.get("title_src") or ""
    src_c = row.get("content_src") or ""
    if translate:
        if src_c and is_collapsed_translation(row.get("content") or "", src_c):
            out = dict(row)
            out["content"] = src_c
            if src_t:
                out["title"] = src_t
            return out
        return row
    if not src_t and not src_c:
        return row
    out = dict(row)
    if src_t:
        out["title"] = src_t
    if src_c:
        out["content"] = src_c
    return out


def apply_twitter_feed(rows: list[dict], user: dict | None) -> list[dict]:
    translate = twitter_translate_enabled(user)
    return [with_twitter_display_row(row, translate) for row in rows]


def strip_html(text: str) -> str:
    """去掉 HTML 标签、还原实体（含 &#34; 等数字实体），<br> 转成换行。"""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).replace("\xa0", " ").strip()


def truncate_text(text: str, limit: int) -> str:
    """截断长文本：优先在换行/句号处断，避免拦腰切断一句话，末尾补省略号。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("\n", "。", "！", "？", "；"):
        idx = cut.rfind(sep)
        if idx > limit * 0.6:
            return cut[: idx + 1].rstrip() + "…"
    return cut.rstrip() + "…"


def digest_body(post: Post, full: bool, max_chars: int = 120, full_limit: int = 2000) -> str:
    """合并摘要正文：单条摘要显示完整正文（保留换行）；多条截断到 max_chars 并补省略号。"""
    raw = post.content or post.title or "（无正文）"
    if full:
        return truncate_text(raw, full_limit)
    flat = raw.replace("\n", " ")
    if len(flat) <= max_chars:
        return flat
    return flat[:max_chars].rstrip() + "…"


def parse_published_at(raw: str) -> datetime | None:
    """时间戳 / RFC2822 / 常见日期串 → 北京时间；解析失败返回 None。"""
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        ts = int(raw)
        ts = ts / 1000 if ts > 1e12 else ts
        try:
            return datetime.fromtimestamp(ts, tz=CN_TZ)
        except (ValueError, OSError, OverflowError):
            return None
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt is not None:
            return dt.astimezone(CN_TZ)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=CN_TZ)
        except ValueError:
            continue
    return None


def attachment_lines(post: Post, note: str = "（链接可能过期）") -> list[str]:
    """从 post.detail["files"] 生成附件行：📎 文件名 + 下载链接。无附件返回空列表。"""
    files = ((post.detail or {}).get("files") or []) if post.detail else []
    lines = []
    for f in files:
        name = str(f.get("name") or "附件") if isinstance(f, dict) else "附件"
        url = str(f.get("url") or "") if isinstance(f, dict) else ""
        if url.startswith(("http://", "https://")):
            lines.append(f"📎 {name}\n   {url} {note}")
    return lines


def format_published_at(raw: str) -> str:
    """把时间戳（毫秒/秒）或 RFC2822（X/微博）格式化为可读时间，其他格式原样返回。"""
    raw = (raw or "").strip()
    dt = parse_published_at(raw)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else raw


class ThreadLocalClient:
    """httpx.Client 非线程安全：poll_once 同平台最多 8 并发，每线程懒建一个。"""

    def __init__(self, factory, injected=None):
        self._factory = factory
        self._injected = injected
        self._local = threading.local()

    def get(self):
        if self._injected is not None:
            return self._injected
        client = getattr(self._local, "client", None)
        if client is None:
            client = self._factory()
            self._local.client = client
        return client

    def set(self, client) -> None:
        self._injected = client

    def reset(self) -> None:
        if self._injected is not None:
            return
        self._local.client = None


class Fetcher:
    platform = ""

    def __init__(self, source_config):
        self.source_config = source_config

    def fetch(self, kol: dict) -> list[Post]:
        raise NotImplementedError


# ---- 追平翻页：防「大V爆发发帖 / 停机积压时帖子滚出首页被静默漏抓」 ----
# 常态（首页尾部已是旧帖）零额外请求；只有检测到缺口才向后翻页
BACKFILL_PAGES = 3
GAP_WARN_INTERVAL = 6 * 3600
_gap_warned_at: dict[str, float] = {}


def tail_is_unseen(db, posts: list[Post]) -> bool:
    """时间线（新→旧序）最末一帖是否从未入库。真则首页之后可能还有漏掉的帖。"""
    if db is None or not posts:
        return False
    tail = posts[-1]
    return not db.existing_post_keys([(tail.platform, tail.external_id)])


def warn_timeline_gap(platform: str) -> None:
    """追平页数用尽仍未撞见旧帖：WARNING 进 error_logs，把漏帖从静默变可感知。"""
    now = time.monotonic()
    last_warned = _gap_warned_at.get(platform)
    if last_warned is not None and now - last_warned < GAP_WARN_INTERVAL:
        return
    _gap_warned_at[platform] = now
    logger.warning(
        "%s 时间线在第 %d 页仍未见已入库的旧帖，更早的发帖可能没被抓全"
        "（大V爆发发帖或服务停机积压）；可临时调低轮询间隔观察",
        PLATFORM_LABELS.get(platform, platform),
        BACKFILL_PAGES,
    )


def catchup_pages(db, fetch_page, first: list[Post]) -> list[Post]:
    """首页最末一帖是新的 → 继续向后翻页，直到撞见已知帖或页数封顶。

    fetch_page(page:int)->list[Post] 由各平台提供指定页内容（新→旧）。
    返回按 external_id 去重合并的完整列表；仅统计已推送类型的帖子，
    纯转发等被平台过滤的尾巴检测不到（设计取舍）。
    """
    if not first or db is None or not tail_is_unseen(db, first):
        return first
    platform = first[0].platform
    merged = {p.external_id for p in first}
    all_posts = list(first)
    caught_up = False
    for page in range(2, BACKFILL_PAGES + 2):
        try:
            batch = fetch_page(page) or []
        except Exception as exc:  # noqa: BLE001 - 追平失败不影响本轮已有结果
            logger.warning("%s 第 %d 页追平失败 err=%s", platform, page, exc)
            break
        if not batch:
            break
        seen = db.existing_post_keys([(p.platform, p.external_id) for p in batch])
        for p in batch:
            if p.external_id not in merged:
                merged.add(p.external_id)
                all_posts.append(p)
        if (batch[-1].platform, batch[-1].external_id) in seen:
            caught_up = True
            break
    if not caught_up:
        warn_timeline_gap(platform)
    return all_posts
