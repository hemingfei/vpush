"""A 股正式简称词库：给纯文字打标用，不占用管理员手改的常用股票名表。

两字名误伤高，全市场名只收 3 字及以上；茅台/理想等两字名仍只认常用表。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

UNIVERSE_MIN_LEN = 3
_RESOURCE = Path(__file__).resolve().parent / "resources" / "a_share_names.json"


def _normalize_name(name: str) -> str:
    cleaned = str(name or "").replace(" ", "").replace("\u3000", "")
    return cleaned.replace("Ａ", "A").replace("Ｂ", "B").strip()


def _load_payload() -> dict:
    if not _RESOURCE.is_file():
        return {}
    try:
        parsed = json.loads(_RESOURCE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@lru_cache(maxsize=1)
def universe_meta() -> dict:
    payload = _load_payload()
    names = bundled_plain_names()
    return {
        "updated": str(payload.get("updated") or ""),
        "source": str(payload.get("source") or ""),
        "count": len(names),
    }


@lru_cache(maxsize=1)
def bundled_plain_names() -> tuple[str, ...]:
    from .tagging import is_equity_name

    payload = _load_payload()
    seen: set[str] = set()
    out: list[str] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = _normalize_name(item.get("name") or "")
        if (
            len(name) < UNIVERSE_MIN_LEN
            or name in seen
            or not is_equity_name(name)
        ):
            continue
        seen.add(name)
        out.append(name)
    return tuple(out)


def names_for_plain_text_tagging(curated=None, excluded=None, universe=None) -> list[str]:
    """常用表（含两字名）+ 全市场 3 字及以上正式简称，去掉管理员排除项。"""
    from .tagging import is_equity_name

    curated_list = [str(n).strip() for n in (curated or []) if str(n).strip()]
    curated_set = set(curated_list)
    excluded_set = {str(n).strip() for n in (excluded or []) if str(n).strip()}
    extra = list(universe) if universe is not None else list(bundled_plain_names())
    seen: set[str] = set()
    out: list[str] = []
    for name in curated_list + extra:
        if name in seen or name in excluded_set:
            continue
        if name not in curated_set and len(name) < UNIVERSE_MIN_LEN:
            continue
        if not is_equity_name(name):
            continue
        seen.add(name)
        out.append(name)
    return out


def aliases_for_tagging(aliases, excluded=None) -> list[dict]:
    """去掉指向管理员排除正式名的别名，避免删名后仍被黑话打上。"""
    excluded_set = {str(n).strip() for n in (excluded or []) if str(n).strip()}
    out = []
    for item in aliases or []:
        if not isinstance(item, dict):
            continue
        stock = str(item.get("stock") or "").strip()
        if stock and stock not in excluded_set:
            out.append(item)
    return out
