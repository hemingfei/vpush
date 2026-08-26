"""IMA 知识库产品层：授权、订阅、可读集合。不负责采集或文件。"""
from __future__ import annotations

from typing import Any, Iterable


def is_admin(user: dict[str, Any]) -> bool:
    return bool(user.get("is_admin"))


def readable_group_ids(db: Any, user: dict[str, Any], groups: Iterable[Any]) -> set[str]:
    ids = {str(group.id) for group in groups}
    if is_admin(user):
        return ids
    return {group_id for group_id in ids if db.ima_kb_can_read(int(user["id"]), group_id)}


def catalog(db: Any, user: dict[str, Any], groups: Iterable[Any]) -> dict[str, list[dict[str, Any]]]:
    items = [
        {"id": group.id, "name": group.name, "enabled": bool(group.enabled)}
        for group in groups
    ]
    if is_admin(user):
        return {"subscribed": items, "available": []}
    uid = int(user["id"])
    subscribed: list[dict[str, Any]] = []
    available: list[dict[str, Any]] = []
    for item in items:
        group_id = item["id"]
        if db.ima_kb_can_read(uid, group_id):
            subscribed.append(item)
        elif db.ima_kb_can_subscribe(uid, group_id):
            available.append(item)
    return {"subscribed": subscribed, "available": available}
