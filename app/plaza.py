"""动态广场数据源显隐：自动（启用大V 为 0 则藏）/ 显示 / 隐藏。"""
from __future__ import annotations

import json

from .db import DB

# 与前端 PLATFORM_TABS 对齐（不含 ima：广场没有 ima 角标）
PLAZA_PLATFORMS = ("system", "xueqiu", "combination", "weibo", "twitter", "zsxq", "mx", "truth")
PLAZA_MODES = ("auto", "show", "hide")
PLAZA_VISIBILITY_KEY = "plaza_source_visibility"


def parse_plaza_visibility(raw: str | None) -> dict[str, str]:
    """读 settings JSON；坏数据或未知键一律忽略，缺省 auto。"""
    out = {platform: "auto" for platform in PLAZA_PLATFORMS}
    if not raw:
        return out
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    for platform, mode in data.items():
        if platform in out and mode in PLAZA_MODES:
            out[platform] = mode
    return out


def plaza_source_rows(db: DB) -> list[dict]:
    counts = db.count_enabled_kols_by_platform()
    visibility = parse_plaza_visibility(db.get_setting(PLAZA_VISIBILITY_KEY))
    rows = []
    for platform in PLAZA_PLATFORMS:
        mode = visibility[platform]
        enabled = int(counts.get(platform, 0))
        visible = mode == "show" or (mode == "auto" and enabled > 0)
        rows.append(
            {
                "platform": platform,
                "mode": mode,
                "enabled_kols": enabled,
                "visible": visible,
            }
        )
    return rows


def plaza_visible_platforms(db: DB) -> list[str]:
    return [row["platform"] for row in plaza_source_rows(db) if row["visible"]]


def user_timeline_platforms(db: DB, user_id: int, is_admin: bool = False) -> list[str]:
    """动态角标：广场可见 ∩ 当前用户已订阅平台。广场仍用 plaza_visible_platforms。"""
    have = db.subscribed_platforms(user_id, is_admin)
    return [platform for platform in plaza_visible_platforms(db) if platform in have]


def plaza_hidden_platforms(db: DB) -> list[str]:
    return [row["platform"] for row in plaza_source_rows(db) if not row["visible"]]


def is_plaza_hidden(db: DB, platform: str | None) -> bool:
    return bool(platform) and platform in set(plaza_hidden_platforms(db))


def filter_plaza_rows(db: DB, rows: list[dict], key: str = "platform") -> list[dict]:
    hidden = set(plaza_hidden_platforms(db))
    if not hidden:
        return list(rows)
    return [row for row in rows if row.get(key) not in hidden]


def _kol_extra(kol: dict) -> dict:
    raw = kol.get("extra_data") or ""
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw) if raw else {}
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def kol_plaza_hidden(db: DB, kol: dict | None) -> bool:
    """平台整体被隐藏，或（MX）房间被管理员设为不在广场显示。

    MX 房间的 extra_data.show_in_plaza 仅在显式 False 时隐藏（缺省视为显示）。
    """
    if not kol:
        return True
    if is_plaza_hidden(db, kol.get("platform")):
        return True
    if kol.get("platform") == "mx":
        return _kol_extra(kol).get("show_in_plaza") is False
    return False


def filter_plaza_kol_rows(db: DB, rows: list[dict]) -> list[dict]:
    """大V行的广场可见性过滤：平台隐藏 + MX 房间级 show_in_plaza。"""
    return [row for row in rows if not kol_plaza_hidden(db, row)]


def set_plaza_visibility(db: DB, updates: dict[str, str]) -> list[dict]:
    """合并写入部分平台的 mode，返回最新 rows。非法平台/mode 抛 ValueError。"""
    visibility = parse_plaza_visibility(db.get_setting(PLAZA_VISIBILITY_KEY))
    for platform, mode in updates.items():
        if platform not in PLAZA_PLATFORMS:
            raise ValueError(f"不支持的平台: {platform}")
        if mode not in PLAZA_MODES:
            raise ValueError("显示方式须为自动、显示或隐藏")
        visibility[platform] = mode
    db.set_setting(PLAZA_VISIBILITY_KEY, json.dumps(visibility, ensure_ascii=False))
    return plaza_source_rows(db)
