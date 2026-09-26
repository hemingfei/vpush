"""心裁阅读器（xincai reader）webhook 接收端：把对端已抓好的正文写进新闻库。

与 RSS 通道的唯一区别是「谁出网」：RSS 由本服务出网拉取，地址必须过
``url_safety`` 的 SSRF 校验（拒私网、拒非标端口）；这里是阅读器主动 POST 过来，
本服务只提供入口，不去够对端的内网，所以不需要 Feed 可解析、也不需要地址可达。

落库复用 ``news_articles`` 与既有的清洗/打标函数，因此站内阅读、已读状态、
主题筛选全部沿用现成实现。源标记 ``internal=1``：一次性回填完成前
普通用户看不到，完成后默认勾选并可读。

推送端（阅读器）每轮重推最近 N 篇，靠 ``(source_id, external_id)`` 唯一约束去重，
所以「推送失败」不是事故，下一轮会自动补上。
"""
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from .db import DB
from .news import (
    MAX_BODY_BYTES,
    MAX_SUMMARY_CHARS,
    MAX_TITLE_CHARS,
    _plain_text,
    classify_news_topics,
    clean_article_html,
    normalize_article_url,
)

logger = logging.getLogger(__name__)

MAX_BATCH_ARTICLES = 200
MAX_EXTERNAL_ID = 200
MAX_SOURCE_NAME = 60


def publication_kind(name: str, hinted: str = "") -> str:
    hint = (hinted or "").strip().lower()
    if hint in {"weekly", "magazine"} or "周刊" in (name or ""):
        return "magazine"
    return "feed"


def _issue_meta(item: dict) -> dict:
    issue = item.get("issue") if isinstance(item.get("issue"), dict) else {}
    try:
        order = int(item.get("tocOrder") if item.get("tocOrder") is not None else issue.get("order") or 0)
    except (TypeError, ValueError):
        order = 0
    return {
        "issue_key": str(item.get("issueKey") or issue.get("issueKey") or issue.get("key") or "").strip()[:40],
        "issue_label": str(item.get("issueLabel") or issue.get("label") or "").strip()[:80],
        "issue_title": str(item.get("issueTitle") or issue.get("title") or "").strip()[:200],
        "issue_cover": str(item.get("issueCover") or issue.get("cover") or "").strip()[:500],
        "section": str(item.get("section") or item.get("category") or "").strip()[:40],
        "toc_order": order,
    }


class XincaiIngestError(ValueError):
    """请求体不合法（对端会收到 400）。"""


def _normalize_ts(raw: object, fallback: str) -> str:
    """ISO8601 → 与 feedparser 路径一致的 UTC isoformat。

    对端（JS）发的是 ``...Z``，Python 3.11 以前 ``fromisoformat`` 不吃这个后缀，
    所以先替换掉再解析，避免版本差异。
    """
    text = str(raw or "").strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    if not text:
        return fallback
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return fallback
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _build_article(item: dict, source_id: int, feed_id: int, now: str) -> dict | None:
    """把一条推送记录转成 news_articles 的行；缺关键字段返回 None（整批跳过它）。"""
    external_id = str(item.get("externalId") or "").strip()[:MAX_EXTERNAL_ID]
    if not external_id:
        return None

    raw_url = str(item.get("url") or "").strip()
    try:
        url = normalize_article_url(raw_url) if raw_url else ""
    except ValueError:
        url = ""

    raw_html = str(item.get("html") or "")
    if len(raw_html.encode("utf-8", "ignore")) > MAX_BODY_BYTES:
        # 超长正文按字节截断（对端不该发这么大的，但别让它撑爆表）
        raw_html = raw_html.encode("utf-8", "ignore")[:MAX_BODY_BYTES].decode("utf-8", "ignore")

    # base_url 用来把相对图片地址补全；拿不到文章地址时给它一个不可解析的占位，
    # clean_article_html 内部会把补全失败（非 http(s)）的图整个丢掉
    content_html, images = clean_article_html(raw_html, url or "https://xincai.invalid/")

    title = _plain_text(item.get("title"), MAX_TITLE_CHARS) or "(无标题)"
    summary = _plain_text(item.get("text") or content_html, MAX_SUMMARY_CHARS)

    digest = str(item.get("contentHash") or "").strip()
    if not digest:
        digest = hashlib.sha256(raw_html.encode("utf-8", "ignore")).hexdigest()
    digest = digest[:64]

    return {
        "source_id": source_id,
        "feed_id": feed_id,
        "external_id": external_id,
        "title": title,
        "url": url,
        "author": _plain_text(item.get("author"), 200),
        "summary": summary,
        "content_html": content_html,
        "images": images,
        "topics": classify_news_topics(title, summary),
        "published_at": _normalize_ts(item.get("publishedAt"), now),
        "fetched_at": _normalize_ts(item.get("fetchedAt"), now),
        "content_hash": digest,
        **_issue_meta(item),
    }


def ingest_articles(db: DB, payload: dict) -> dict:
    """按 sourceName 分组入库；返回每组建到的媒体源 id 与入库篇数。"""
    if not isinstance(payload, dict):
        raise XincaiIngestError("请求体必须是 JSON 对象")

    raw_articles = payload.get("articles")
    if not isinstance(raw_articles, list) or not raw_articles:
        raise XincaiIngestError("articles 不能为空")
    if len(raw_articles) > MAX_BATCH_ARTICLES:
        raise XincaiIngestError(f"单批最多 {MAX_BATCH_ARTICLES} 篇，收到 {len(raw_articles)}")

    default_group = str(payload.get("group") or "").strip()[:40]
    default_source = str(payload.get("sourceName") or "").strip()[:MAX_SOURCE_NAME]
    now = datetime.now(UTC).isoformat()

    grouped: dict[str, list[dict]] = {}
    # group key -> (显示名, 对端来源 id)。按 sourceId 分组而不是按名字：
    # 名字允许两边各自改，身份得跟着对端的稳定 id 走。
    labels: dict[str, tuple[str, str]] = {}
    skipped = 0
    for item in raw_articles:
        if not isinstance(item, dict):
            skipped += 1
            continue
        name = str(item.get("sourceName") or default_source or "心裁").strip()[:MAX_SOURCE_NAME]
        if not name:
            name = "心裁"
        sid = str(item.get("sourceId") or "").strip()[:80]
        key = sid or name
        grouped.setdefault(key, []).append(item)
        labels.setdefault(key, (name, sid))

    saved = 0
    sources: dict[str, int] = {}
    for key, items in grouped.items():
        name, sid = labels[key]
        external_key = f"xincai-{sid}" if sid else ""
        hinted = str(payload.get("sourceKind") or items[0].get("sourceKind") or "")
        platform = next(
            (p for p in (str(it.get("platform") or "").strip().lower() for it in items) if p in ("caixin", "ft")),
            "",
        )
        try:
            source_id = db.get_or_create_internal_news_source(
                name, default_group, external_key=external_key,
                kind=publication_kind(name, hinted), platform=platform,
            )
        except ValueError as exc:
            raise XincaiIngestError(str(exc)) from None
        feed_id = db.get_or_create_internal_news_feed(source_id)
        rows = [row for row in (_build_article(it, source_id, feed_id, now) for it in items) if row]
        skipped += len(items) - len(rows)
        if rows:
            db.upsert_news_articles_batch(rows)
            saved += len(rows)
            # 占位 feed 的 last_success_at 记「推送到达时间」：源状态的新鲜度判定读它，
            # 比看文章发布时间准——栏目当天没更新不等于推送链路断了
            db.mark_news_feed_success(feed_id, etag="", last_modified="", succeeded_at=now)
        sources[name] = source_id

    logger.info("xincai 接收：入库 %d 篇，跳过 %d 条，媒体源 %s", saved, skipped, sources)
    return {"ok": True, "accepted": saved, "skipped": skipped, "sources": sources}
