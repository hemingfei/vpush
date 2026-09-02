"""IMA 知识库产品层：授权、订阅、可读集合。不负责采集或文件。"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_DAY_KEY = re.compile(r"^\d{4}$")


def is_admin(user: dict[str, Any]) -> bool:
    return bool(user.get("is_admin"))


def readable_group_ids(db: Any, user: dict[str, Any], groups: Iterable[Any]) -> set[str]:
    ids = {str(group.id) for group in groups}
    if is_admin(user):
        return ids
    uid = int(user["id"])
    acl = {str(group_id) for group_id in db.ima_kb_group_ids_for_user(uid)}
    subscribed = {
        str(group_id) for group_id in db.ima_kb_subscribed_group_ids_for_user(uid)
    }
    return ids & acl & subscribed


def catalog(db: Any, user: dict[str, Any], groups: Iterable[Any]) -> dict[str, list[dict[str, Any]]]:
    items = [
        {"id": group.id, "name": group.name, "enabled": bool(group.enabled)}
        for group in groups
    ]
    if is_admin(user):
        return {"subscribed": items, "available": []}
    uid = int(user["id"])
    acl = {str(group_id) for group_id in db.ima_kb_group_ids_for_user(uid)}
    subscriptions = {
        str(group_id) for group_id in db.ima_kb_subscribed_group_ids_for_user(uid)
    }
    subscribed_ids = acl & subscriptions
    available_ids = acl - subscriptions
    return {
        "subscribed": [item for item in items if str(item["id"]) in subscribed_ids],
        "available": [item for item in items if str(item["id"]) in available_ids],
    }


def attach_catalog_summary(
    listed: dict[str, list[dict[str, Any]]],
    stats_by_group: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    for key in ("subscribed", "available"):
        for group in listed.get(key, []):
            extra = stats_by_group.get(str(group.get("id") or ""), {}) or {}
            group["document_count"] = int(extra.get("document_count") or 0)
            group["latest_day"] = str(extra.get("latest_day") or "")
            group["latest_title"] = str(extra.get("latest_title") or "")
            group["latest_media_id"] = str(extra.get("latest_media_id") or "")
    return listed


def attach_catalog_stats(
    listed: dict[str, list[dict[str, Any]]],
    documents: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    stats: dict[str, dict[str, Any]] = {}
    for item in documents:
        group_id = str(item.get("group_id") or "")
        if not group_id:
            continue
        bucket = stats.setdefault(
            group_id,
            {"document_count": 0, "latest_day": "", "latest_title": "", "latest_media_id": ""},
        )
        bucket["document_count"] += 1
        day = str(item.get("day") or "")
        if _DAY_KEY.fullmatch(day) and day >= str(bucket["latest_day"] or ""):
            bucket["latest_day"] = day
            bucket["latest_title"] = str(item.get("name") or "")
            bucket["latest_media_id"] = str(item.get("media_id") or "")
    return attach_catalog_summary(listed, stats)


def attach_catalog_acl(listed: dict[str, list[dict[str, Any]]], db: Any, user: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if not is_admin(user):
        return listed
    for key in ("subscribed", "available"):
        for group in listed.get(key, []):
            group["acl_usernames"] = db.ima_kb_acl_usernames(str(group.get("id") or ""))
    return listed
