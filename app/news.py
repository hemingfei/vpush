"""Financial news Feed parsing, sanitization and shared refresh service."""
from __future__ import annotations

import hashlib
import html
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import struct_time
from urllib.parse import SplitResult, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import bleach
import feedparser
import httpx
from bleach.html5lib_shim import Filter

from .db import DB
from .url_safety import safe_get_limited

MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_ARTICLES = 100
MAX_IMAGES = 30
MAX_TITLE_CHARS = 500
MAX_AUTHOR_CHARS = 200
MAX_SUMMARY_CHARS = 2000
MAX_BODY_BYTES = 512 * 1024
DEFAULT_RETENTION_DAYS = 30
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_TRACKING_QUERY_KEYS = {"fbclid", "gclid"}
_ALLOWED_TAGS = {
    "p", "br", "h2", "h3", "hr", "ul", "ol", "li", "blockquote",
    "strong", "b", "em", "i", "a", "img", "figure", "figcaption",
    "pre", "code", "table", "thead", "tbody", "tr", "th", "td",
}
_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title", "width", "height", "data-news-image-index"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedArticle:
    external_id: str
    title: str
    url: str
    author: str
    summary: str
    content_html: str
    images: list[str]
    published_at: str
    fetched_at: str
    content_hash: str


@dataclass(frozen=True)
class ParsedFeed:
    title: str
    format: str
    articles: list[ParsedArticle]


class NewsInputError(ValueError):
    """Administrator or Feed input is invalid or unsafe."""


class NewsNotFound(LookupError):
    """Requested article, image index, source or Feed is inaccessible."""


class NewsUpstreamError(RuntimeError):
    """A validated public upstream failed or returned unusable content."""


def _normalized_parts(url: str) -> tuple[SplitResult, str]:
    parsed = urlsplit((url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("文章地址必须是 HTTP(S)")
    if parsed.username or parsed.password:
        raise ValueError("文章地址不能包含认证信息")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    host_label = f"[{host}]" if ":" in host else host
    port = parsed.port
    default_port = 443 if scheme == "https" else 80
    netloc = host_label if port in (None, default_port) else f"{host_label}:{port}"
    return parsed, urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def normalize_feed_url(url: str) -> str:
    return _normalized_parts(url)[1]


def normalize_article_url(url: str) -> str:
    parsed, normalized = _normalized_parts(url)
    base = urlsplit(normalized)
    query = urlencode([
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ])
    return urlunsplit((base.scheme, base.netloc, base.path, query, ""))


def _plain_text(value: object, limit: int) -> str:
    text = html.unescape(str(value or ""))
    text = bleach.clean(text, tags=[], attributes={}, strip=True)
    return " ".join(text.split())[:limit]


def _safe_content_url(value: str, base_url: str) -> str | None:
    try:
        return normalize_article_url(urljoin(base_url, (value or "").strip()))
    except (TypeError, ValueError):
        return None


def clean_article_html(raw_html: str, base_url: str) -> tuple[str, list[str]]:
    """Sanitize article HTML and replace images with authenticated image indexes."""
    images: list[str] = []

    class ArticleFilter(Filter):
        def __iter__(self):
            for token in self.source:
                if token["type"] in {"StartTag", "EmptyTag"} and token["name"] == "a":
                    href_key = (None, "href")
                    href = token["data"].get(href_key)
                    if href:
                        resolved = _safe_content_url(href, base_url)
                        if resolved:
                            token["data"][href_key] = resolved
                            token["data"][(None, "target")] = "_blank"
                            token["data"][(None, "rel")] = "noopener noreferrer nofollow"
                        else:
                            token["data"].pop(href_key, None)
                elif token["type"] in {"StartTag", "EmptyTag"} and token["name"] == "img":
                    src_key = (None, "src")
                    src = token["data"].pop(src_key, None)
                    if src and len(images) < MAX_IMAGES:
                        resolved = _safe_content_url(src, base_url)
                        if resolved:
                            index = len(images)
                            images.append(resolved)
                            token["data"][(None, "data-news-image-index")] = str(index)
                yield token

    cleaner = bleach.Cleaner(
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols={"http", "https"},
        strip=True,
        filters=[ArticleFilter],
    )
    cleaned = cleaner.clean(raw_html or "")
    if len(cleaned.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("正文过大")
    return cleaned, images


def _entry_link(entry: dict, feed_url: str) -> str:
    links = entry.get("links") or []
    for link in links:
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return normalize_article_url(urljoin(feed_url, link["href"]))
    raw_link = entry.get("link") or ""
    return normalize_article_url(urljoin(feed_url, raw_link)) if raw_link else ""


def _entry_content(entry: dict) -> str:
    content = entry.get("content") or []
    if content and content[0].get("value"):
        return str(content[0]["value"])
    return str(entry.get("summary") or entry.get("description") or "")


def _entry_date(entry: dict, fetched_at: datetime) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if isinstance(parsed, struct_time):
        value = datetime(*parsed[:6], tzinfo=UTC)
    else:
        value = fetched_at
    return min(value, fetched_at)


def parse_feed(payload: bytes, feed_url: str, fetched_at: datetime) -> ParsedFeed:
    parsed = feedparser.parse(payload)
    version = str(parsed.version or "")
    if not version.startswith(("rss", "atom")):
        raise ValueError("不是有效的 RSS/Atom Feed")
    fetched_at = fetched_at.astimezone(UTC) if fetched_at.tzinfo else fetched_at.replace(tzinfo=UTC)
    feed_title = _plain_text(parsed.feed.get("title", ""), MAX_TITLE_CHARS)
    candidates: list[tuple[datetime, int, dict]] = []
    for position, entry in enumerate(parsed.entries):
        try:
            url = _entry_link(entry, feed_url)
            title = _plain_text(entry.get("title"), MAX_TITLE_CHARS)
            if not title or not url:
                continue
            content_raw = _entry_content(entry)
            content_html, images = clean_article_html(content_raw, url)
            author = _plain_text(entry.get("author"), MAX_AUTHOR_CHARS)
            summary = _plain_text(entry.get("summary") or entry.get("description"), MAX_SUMMARY_CHARS)
            published = _entry_date(entry, fetched_at)
            external_id = _plain_text(entry.get("id") or entry.get("guid"), 2048) or url
            article = ParsedArticle(
                external_id=external_id,
                title=title,
                url=url,
                author=author,
                summary=summary,
                content_html=content_html,
                images=images,
                published_at=published.isoformat(),
                fetched_at=fetched_at.isoformat(),
                content_hash=hashlib.sha256(
                    "\n".join((title, summary, content_html)).encode("utf-8")
                ).hexdigest(),
            )
            candidates.append((published, position, article))
        except (TypeError, ValueError):
            continue
    candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return ParsedFeed(
        title=feed_title,
        format=version,
        articles=[item[2] for item in candidates[:MAX_ARTICLES]],
    )


class NewsService:
    def __init__(self, db: DB, client: httpx.Client | None = None):
        self.db = db
        self.client = client or httpx.Client(trust_env=False)
        self._owns_client = client is None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="news-feed")
        self._locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._closed = False

    def _feed_lock(self, feed_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(int(feed_id), threading.Lock())

    def submit_feed(self, feed_id: int) -> bool:
        if self._closed:
            return False
        lock = self._feed_lock(feed_id)
        if not lock.acquire(blocking=False):
            return False
        self._executor.submit(self._run_submitted, int(feed_id), lock)
        return True

    def _run_submitted(self, feed_id: int, lock: threading.Lock) -> None:
        try:
            self.refresh_feed(feed_id)
        except Exception:  # noqa: BLE001 - worker 异常也必须落库并释放锁
            logger.exception("财经新闻后台刷新异常 feed_id=%s", feed_id)
            try:
                self.db.mark_news_feed_failure(
                    feed_id, "network_error", "后台刷新异常", datetime.now(UTC).isoformat()
                )
            except Exception:  # noqa: BLE001 - DB 故障只能记录日志
                logger.exception("财经新闻后台刷新错误状态写入失败 feed_id=%s", feed_id)
        finally:
            lock.release()

    def close(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=False)
        if self._owns_client:
            self.client.close()

    def _fetch_feed(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        timeout = httpx.Timeout(connect=5, read=15, write=5, pool=5)
        return safe_get_limited(
            self.client,
            url,
            max_bytes=MAX_FEED_BYTES,
            headers=headers,
            default_ports_only=True,
            timeout=timeout,
        )

    def validate_feed(self, url: str) -> dict:
        try:
            normalized = normalize_feed_url(url)
            response = self._fetch_feed(normalized)
            if not 200 <= response.status_code < 300:
                raise NewsUpstreamError("Feed 返回 HTTP 错误")
            parsed = parse_feed(response.content, normalized, datetime.now(UTC))
        except NewsUpstreamError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise NewsInputError("Feed 地址无法验证") from exc
        return {
            "format": parsed.format,
            "title": parsed.title,
            "entries": [
                {
                    "title": article.title,
                    "published_at": article.published_at,
                    "text": article.summary,
                }
                for article in parsed.articles[:3]
            ],
        }

    def _retention_days(self) -> int | None:
        raw = self.db.get_setting("stats_posts_retention_days")
        if raw is None:
            return DEFAULT_RETENTION_DAYS
        try:
            days = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_RETENTION_DAYS
        return days if days > 0 else None

    @staticmethod
    def _error_detail(exc: BaseException) -> str:
        request = getattr(exc, "request", None)
        if request is not None:
            try:
                parsed = urlsplit(str(request.url))
                safe_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
                return f"{type(exc).__name__}: {safe_url}"[:300]
            except ValueError:
                pass
        text = " ".join(str(exc or "").split())
        return text[:300] or "上游请求失败"

    def refresh_feed(self, feed_id: int) -> dict:
        feed = self.db.get_news_feed(feed_id)
        if not feed:
            raise NewsNotFound("Feed 不存在")
        source = self.db.get_news_source(feed["source_id"])
        if not source or not source["enabled"] or source["archived_at"] or not feed["enabled"] or feed["archived_at"]:
            raise NewsInputError("Feed 已停用或归档")
        attempted_at = datetime.now(UTC).isoformat()
        self.db.mark_news_feed_attempt(feed_id, attempted_at)
        headers = {}
        if feed["etag"]:
            headers["If-None-Match"] = feed["etag"]
        if feed["last_modified"]:
            headers["If-Modified-Since"] = feed["last_modified"]
        try:
            response = self._fetch_feed(feed["url"], headers)
            if response.status_code == 304:
                self.db.mark_news_feed_success(
                    feed_id,
                    etag=response.headers.get("etag", feed["etag"]),
                    last_modified=response.headers.get("last-modified", feed["last_modified"]),
                    succeeded_at=attempted_at,
                )
                return {"status": "not_modified", "feed_id": feed_id}
            if not 200 <= response.status_code < 300:
                raise NewsUpstreamError("Feed 返回 HTTP 错误")
            parsed = parse_feed(response.content, feed["url"], datetime.now(UTC))
            retention_days = self._retention_days()
            cutoff = (
                datetime.now(UTC) - timedelta(days=retention_days)
                if retention_days is not None else None
            )
            stored = 0
            for article in parsed.articles:
                if cutoff is not None and datetime.fromisoformat(article.published_at) < cutoff:
                    continue
                self.db.upsert_news_article({
                    "source_id": feed["source_id"],
                    "feed_id": feed_id,
                    "external_id": article.external_id,
                    "title": article.title,
                    "url": article.url,
                    "author": article.author,
                    "summary": article.summary,
                    "content_html": article.content_html,
                    "images": article.images,
                    "published_at": article.published_at,
                    "fetched_at": article.fetched_at,
                    "content_hash": article.content_hash,
                })
                stored += 1
            self.db.mark_news_feed_success(
                feed_id,
                etag=response.headers.get("etag", ""),
                last_modified=response.headers.get("last-modified", ""),
                succeeded_at=attempted_at,
            )
            return {"status": "updated", "feed_id": feed_id, "articles": stored}
        except ValueError as exc:
            code = "unsafe_url" if "安全" in str(exc) or "地址" in str(exc) else "invalid_feed"
            self.db.mark_news_feed_failure(feed_id, code, self._error_detail(exc), attempted_at)
            return {"status": "failed", "feed_id": feed_id, "error_code": code}
        except httpx.HTTPError as exc:
            self.db.mark_news_feed_failure(feed_id, "network_error", self._error_detail(exc), attempted_at)
            return {"status": "failed", "feed_id": feed_id, "error_code": "network_error"}
        except NewsUpstreamError as exc:
            self.db.mark_news_feed_failure(feed_id, "http_error", self._error_detail(exc), attempted_at)
            return {"status": "failed", "feed_id": feed_id, "error_code": "http_error"}

    def submit_due(self) -> list[int]:
        if self.db.get_setting("news_enabled") != "1":
            return []
        try:
            interval = int(self.db.get_setting("news_refresh_interval_seconds") or 600)
        except ValueError:
            interval = 600
        before = (datetime.now(UTC) - timedelta(seconds=max(1, interval))).isoformat()
        accepted = []
        for feed in self.db.list_due_news_feeds(before):
            if self.submit_feed(feed["id"]):
                accepted.append(feed["id"])
        return accepted

    def fetch_image(self, article_id: int, index: int, user_id: int) -> tuple[bytes, str]:
        article = self.db.get_news_article(article_id, user_id=user_id)
        if not article:
            raise NewsNotFound("文章不存在")
        try:
            image_index = int(index)
            if image_index < 0:
                raise IndexError
            target = article["images"][image_index]
        except (IndexError, TypeError, ValueError):
            raise NewsNotFound("图片不存在") from None
        try:
            response = safe_get_limited(
                self.client,
                target,
                max_bytes=MAX_IMAGE_BYTES,
                default_ports_only=True,
                timeout=httpx.Timeout(connect=5, read=15, write=5, pool=5),
            )
        except ValueError as exc:
            raise NewsInputError("图片地址不安全") from exc
        except httpx.HTTPError as exc:
            raise NewsUpstreamError("图片暂时无法加载") from exc
        if not 200 <= response.status_code < 300:
            raise NewsUpstreamError("图片暂时无法加载")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise NewsInputError("上游不是允许的图片类型")
        return response.content, content_type
