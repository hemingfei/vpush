"""大V持股汇总：把分析范围内全部大V的预估持仓聚合成一张总览。

四榜（术语见 CONTEXT.md「大V持股/共同进攻/割肉清仓」）：
- 重仓票（heavy）：当前持有同一标的的大V人数降序——静态共识；
- 共同进攻（attack）：窗口内 ≥2 位大V对同一标的建仓/加仓/低吸的动作共振；
- 题材方向（topics）：各大V预估持仓的题材关注按人数聚合；
- 清仓榜（clears）：窗口内清仓事件按标的聚合，按清仓大V数降序；
  盈亏挂接由小时级盈亏缓存（T2/T3）提供，本模块只留 null 占位。

纯计算不落库（对齐 mx_kol_holdings 哲学）：单大V结果永远可重算；
聚合结果在进程内做短 TTL 缓存防抖（109 个大V全量回放实测约 0.3s，
但页面上多榜共用一次响应，避免每请求都重跑）。名单/词表改动通过
TTL 过期自然生效，不需要显式失效。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from .mx_kol_holdings import TAG_BUY_ACTIONS, build_kol_holdings

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))

WINDOW_CHOICES = (30, 60, 90)
CACHE_TTL = 60.0  # 秒：防抖窗口，非数据新鲜度承诺

_cache: dict = {"data": {}, "lock": threading.Lock()}


def _kol_brief(kol: dict) -> dict:
    """行内大V摘要：只下发展示所需的三个字段。"""
    return {"kol_id": int(kol["kol_id"]), "name": kol["name"], "avatar": kol["avatar"]}


def _ranked(counter: dict) -> list[dict]:
    """{name: [kol_brief...]} → 榜行：人数降序、同数按名称稳定序。"""
    rows = []
    for name in sorted(counter, key=lambda n: (-len(counter[n]), n)):
        kols = counter[name]
        rows.append({"target_name": name, "kol_count": len(kols), "kols": kols})
    return rows


def _ranked_clears(clears: dict) -> list[dict]:
    """清仓榜行：kols 与其他榜同构（复用行展开），entries 带清仓时间+盈亏明细。"""
    rows = []
    for name in sorted(clears, key=lambda n: (-len(clears[n]), n)):
        entries = clears[name]
        rows.append({
            "target_name": name, "kol_count": len(entries),
            "kols": [{k: e[k] for k in ("kol_id", "name", "avatar")} for e in entries],
            "entries": entries,
        })
    return rows


def _pnl_by_name(db, kol_id: int, days: int) -> dict[str, dict]:
    """小时级盈亏缓存 → {标的: 股票行}；缓存缺失/损坏返回空（调用方按缺价占位）。"""
    cached = db.get_kol_pnl_cache(kol_id, days)
    if not cached:
        return {}
    stocks = (cached.get("payload") or {}).get("stocks") or []
    return {str(s.get("target_name") or ""): s
            for s in stocks if isinstance(s, dict) and s.get("target_name")}


def _clear_signal(pnl_row: dict | None) -> tuple[float | None, str]:
    """清仓行的盈亏挂接：返回 (realized_pnl_pct, signal)。

    signal：cut=割肉（浮亏清仓）、profit=止盈、空串=无缓存数据（前端占位）。
    割肉判定零阈值（CONTEXT.md「割肉清仓」）：盈亏为负即割肉。
    """
    if not pnl_row:
        return None, ""
    pct = pnl_row.get("realized_pnl_pct")
    if pct is None:
        return None, ""
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return None, ""
    return pct, ("cut" if pct < 0 else "profit")


def build_summary(db, kol_ids: list[int], days: int = 30) -> dict:
    """对名单内每个大V跑预估持仓回放，聚合四榜。

    kol_ids 由调用方按 holdings_kol_ids 口径传入（名单 ∩ 启用 MX 大V）；
    单个大V回放失败只跳过该大V，不连坐整榜。
    """
    heavy: dict[str, list] = {}
    heavy_last: dict[str, str] = {}
    topics: dict[str, list] = {}
    topics_last: dict[str, str] = {}
    attack: dict[str, list] = {}
    attack_last: dict[str, str] = {}
    clears: dict[str, list] = {}

    for kol_id in kol_ids:
        try:
            out = build_kol_holdings(db, kol_id, days=days)
        except Exception:  # noqa: BLE001 - 单大V脏数据不连坐
            logger.exception("kol holdings replay failed in summary, kol_id=%s", kol_id)
            continue
        if not out:
            continue
        brief = _kol_brief(out["kol"])

        for row in out.get("holdings") or []:
            name = row["target_name"]
            heavy.setdefault(name, []).append(brief)
            if str(row.get("last_at") or "") > heavy_last.get(name, ""):
                heavy_last[name] = str(row.get("last_at") or "")
        for row in out.get("topics") or []:
            name = row["target_name"]
            topics.setdefault(name, []).append(brief)
            if str(row.get("last_at") or "") > topics_last.get(name, ""):
                topics_last[name] = str(row.get("last_at") or "")

        # 共同进攻/清仓走回放时间线的**操作词**而非 kind：首条即「加仓」的事件
        # kind=hold（无先前头寸可加），但那是一笔真实买入（mx_kol_pnl 同样按
        # 此修正）；操作词口径下 opinion/tag/manual 三源一致。
        # 大V→标的去重（一个大V多笔同票买入算一人一票）。
        pnl_map = _pnl_by_name(db, kol_id, days)
        seen_attack: set[str] = set()
        seen_clear: set[str] = set()
        for ev in out.get("timeline") or []:
            if ev.get("target_type") != "stock":
                continue
            name = ev["target_name"]
            at = ev.get("occurred_at") or ev.get("trading_day") or ""
            if ev.get("action") in TAG_BUY_ACTIONS and name not in seen_attack:
                seen_attack.add(name)
                attack.setdefault(name, []).append(brief)
                if at > attack_last.get(name, ""):
                    attack_last[name] = at
            elif ev.get("kind") == "clear" and name not in seen_clear:
                seen_clear.add(name)
                pct, signal = _clear_signal(pnl_map.get(name))
                clears.setdefault(name, []).append({
                    "kol_id": brief["kol_id"], "name": brief["name"],
                    "avatar": brief["avatar"], "at": at,
                    "realized_pnl_pct": pct, "signal": signal,
                })

    def _with_last_at(rows: list[dict], last_map: dict[str, str]) -> list[dict]:
        for row in rows:
            row["last_at"] = last_map.get(row["target_name"], "")
        return rows

    attack_rows = []
    for row in _ranked(attack):
        if row["kol_count"] >= 2:  # 共同进攻 ≥2 人才是共振：单人动作无共识含义
            row["last_at"] = attack_last.get(row["target_name"], "")
            attack_rows.append(row)
    return {
        "window_days": days,
        "heavy": _with_last_at(_ranked(heavy), heavy_last),
        "attack": attack_rows,
        "topics": _with_last_at(_ranked(topics), topics_last),
        "clears": _ranked_clears(clears),
        "generated_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    }


def cached_summary(db, kol_ids_provider, days: int = 30) -> dict:
    """TTL 缓存包裹的聚合：同窗口 60s 内多请求共享一次回放。

    kol_ids_provider 每次现调（名单是 settings 驱动的动态值，不能缓存 id 列表）。
    缓存键用 db.path 而非 id(db)：id 在对象回收后会被复用，跨 DB 世界（测试逐用例
    建临时库）会串数据；同路径=同数据世界，路径键天然隔离。
    """
    key = (str(db.path), int(days))
    now = time.monotonic()
    with _cache["lock"]:
        hit = _cache["data"].get(key)
        if hit and now - hit["at"] <= CACHE_TTL:
            return hit["data"]
    data = build_summary(db, kol_ids_provider(), days=days)
    with _cache["lock"]:
        _cache["data"][key] = {"at": now, "data": data}
    return data
