"""研报关键词提醒：每日入库后按人合并成一条推送。

不走帖子 notify_subscribers；不穿透免打扰。授权（ACL）是可见性门槛。
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from .channels import build_channel_notifier, iter_user_channels
from .cicc_collector import CICC_CATEGORIES
from .logging_setup import redact_secrets

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60
DIGEST_SHOW_MAX = 8
RECENT_LIMIT = 400
TITLE_MAX = 80

# 库标 / 中金一级品类：允许匹配（用户手填），但不在研报页提供「加入关键词」入口。
BROAD_REPORT_TAGS = frozenset(("中金研报", *CICC_CATEGORIES))

SETTINGS_LAST_CHECK = "knowledge_keyword_last_check"


def is_watchable_report_tag(tag: str) -> bool:
    name = (tag or "").strip()
    return bool(name) and name not in BROAD_REPORT_TAGS


def document_keyword_hit(keywords: list[str], doc: dict) -> list[str]:
    """返回命中的关键词（保序去重）。大小写不敏感子串，对齐动态关键词。"""
    cleaned = [kw.strip() for kw in keywords if (kw or "").strip()]
    if not cleaned:
        return []
    tags = doc.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    text = "\n".join(
        part
        for part in (
            doc.get("name"),
            doc.get("abstract"),
            doc.get("abstract_zh"),
            doc.get("group_name"),
            "\n".join(str(tag) for tag in tags if tag),
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


def _display_title(doc: dict) -> str:
    name = str(doc.get("name") or "").strip() or str(doc.get("media_id") or "研报")
    if len(name) > TITLE_MAX:
        return name[: TITLE_MAX - 1] + "…"
    return name


def format_digest(docs: list[dict], *, extra: int = 0) -> str:
    n = len(docs) + extra
    lines = [f"今日研报 {n} 篇命中关键词", ""]
    for doc in docs:
        title = _display_title(doc)
        source = str(doc.get("group_name") or "").strip()
        suffix = f"（{source}）" if source else ""
        lines.append(f"· {title}{suffix}")
    if extra:
        lines.append(f"· 还有 {extra} 篇")
    lines.append("")
    lines.append("打开研报库查看")
    return "\n".join(lines)


def _user_since(user: dict) -> str:
    since = str(user.get("keywords_match_reports_since") or "").strip()
    if since:
        return since
    return datetime.now(UTC).isoformat()


def _can_read(db, user: dict, group_id: str) -> bool:
    if user.get("is_admin"):
        return True
    return db.ima_kb_can_read(int(user["id"]), group_id)


def maybe_notify_knowledge_keywords(db, notifiers_config=None, *, now: int | None = None) -> int:
    """调度入口：找出开关打开的用户，把未通知的命中研报合并推一条。

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

    users = db.list_knowledge_keyword_users()
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
            since = _user_since(user)
            recent = db.list_recent_ima_documents(since, limit=RECENT_LIMIT)
            if not recent:
                continue
            pending = db.filter_unnotified_knowledge_docs(int(user["id"]), recent)
            matched: list[dict] = []
            for doc in pending:
                group_id = str(doc.get("group_id") or "")
                if not group_id or not _can_read(db, user, group_id):
                    continue
                if document_keyword_hit(kws, doc):
                    matched.append(doc)
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
                        "研报关键词推送失败 user=%s channel=%s err=%s",
                        user.get("username"),
                        channel,
                        exc,
                    )
            if sent_ok:
                db.mark_knowledge_keyword_notified(int(user["id"]), matched)
                delivered += 1
    finally:
        client.close()
    return delivered
