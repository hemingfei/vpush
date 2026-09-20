"""财经新闻关键词提醒：入库后按人合并成一条推送。

与研报关键词提醒（knowledge_notify）同构：60s 节流扫描、按人去重合并、
免打扰时段跳过且不打已通知标记。订阅关系只决定默认信息流，推送看本开关。
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from .channels import build_channel_notifier, iter_user_channels
from .logging_setup import redact_secrets

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60
DIGEST_SHOW_MAX = 8
RECENT_LIMIT = 400
TITLE_MAX = 80

SETTINGS_LAST_CHECK = "news_keyword_last_check"
# 财经新闻入口：推送里给纯文本 URL，Telegram 客户端会自己转成可点链接
NEWS_URL = "https://vpush.net/news"


def article_keyword_hit(keywords: list[str], article: dict) -> list[str]:
    """返回命中的关键词（保序去重）。大小写不敏感子串，对齐动态/研报关键词。"""
    cleaned = [kw.strip() for kw in keywords if (kw or "").strip()]
    if not cleaned:
        return []
    text = "\n".join(
        part
        for part in (
            article.get("title"),
            article.get("summary"),
            article.get("author"),
            article.get("source_name"),
        )
        if part
    ).lower()
    hits: list[str] = []
    seen: set[str] = set()
    for kw in cleaned:
        key = kw.lower()
        if key in seen:
            continue
        if key in text:
            seen.add(key)
            hits.append(kw)
    return hits


def _display_title(article: dict) -> str:
    title = str(article.get("title") or "").strip() or "财经新闻"
    if len(title) > TITLE_MAX:
        return title[: TITLE_MAX - 1] + "…"
    return title


def format_digest(articles: list[dict], *, extra: int = 0) -> str:
    n = len(articles) + extra
    lines = [f"财经新闻 {n} 条命中关键词", ""]
    for article in articles:
        title = _display_title(article)
        source = str(article.get("source_name") or "").strip()
        suffix = f"（{source}）" if source else ""
        lines.append(f"· {title}{suffix}")
    if extra:
        lines.append(f"· 还有 {extra} 条")
    lines.append("")
    lines.append(f"打开财经新闻查看 {NEWS_URL}")
    return "\n".join(lines)


def maybe_notify_news_keywords(db, notifiers_config=None, *, now: int | None = None) -> int:
    """调度入口：找出开关打开的用户，把未通知的命中新闻合并推一条。

    免打扰时段跳过且不打已通知标记，下轮再试。返回成功投递的用户数。
    """
    from .scheduler import _in_dnd_window

    now = int(now or time.time())
    last = db.get_setting(SETTINGS_LAST_CHECK)
    if last:
        try:
            if now - int(last) < CHECK_INTERVAL_SECONDS:
                return 0
        except (TypeError, ValueError):
            pass
    db.set_setting(SETTINGS_LAST_CHECK, str(now))
    if notifiers_config is None:
        return 0

    users = db.list_news_keyword_users()
    if not users:
        return 0
    keywords_map = db.get_users_keywords([int(u["id"]) for u in users])
    delivered = 0
    client = __import__("httpx").Client(timeout=15)
    try:
        for user in users:
            kws = keywords_map.get(int(user["id"])) or []
            if not kws:
                continue
            if _in_dnd_window(user):
                continue
            since = str(user.get("keywords_match_news_since") or "").strip()
            if not since:
                since = datetime.now(UTC).isoformat()
            recent = db.list_recent_news_articles(since, limit=RECENT_LIMIT)
            if not recent:
                continue
            pending = db.filter_unnotified_news_articles(int(user["id"]), recent)
            matched = [
                article
                for article in pending
                if article_keyword_hit(kws, article)
            ]
            if not matched:
                continue
            shown = matched[:DIGEST_SHOW_MAX]
            extra = max(0, len(matched) - len(shown))
            text = redact_secrets(format_digest(shown, extra=extra))
            channels = list(iter_user_channels(user, notifiers_config, db))
            if not channels:
                continue
            sent_ok = False
            for channel in channels:
                try:
                    notifier = build_channel_notifier(
                        channel, user, notifiers_config, client=client, db=db
                    )
                    notifier.send_text(text)
                    sent_ok = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "财经新闻关键词推送失败 user=%s channel=%s err=%s",
                        user.get("username"),
                        channel,
                        exc,
                    )
            if sent_ok:
                db.mark_news_keyword_notified(int(user["id"]), matched)
                delivered += 1
    finally:
        client.close()
    return delivered
