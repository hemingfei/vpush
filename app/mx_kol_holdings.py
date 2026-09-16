"""MX 大V预估持仓：按历史多空观点回放推演当前仓位。

数据源是观点研判管线产出的 mx_opinions（LLM 已从消息提取方向 + 操作词），
本模块只做纯计算回放，不落库、不调 LLM——历史观点不可变，结果可随时重算。
窗口默认近 30 个自然日，越窗的持仓视为已了结，不再计入。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))

WINDOW_DAYS = 30
# 窗口内无新表态的标的，持仓保留天数（观点沉默 ≠ 卖出，但太久没提按了结处理）
STALE_DAYS = 10

# 操作词 → 仓位分变更（相对分，最后归一化为 0-100% 占比）。
# 分值只表达操作的相对力度：建仓是新头寸所以最重，加仓/低吸按半仓力度，
# 减仓/高抛对冲回撤，清仓直接了结。词表外操作（管理员自定义词）不参与。
ACTION_POINTS = {"建仓": 3.0, "加仓": 2.0, "低吸": 2.0, "减仓": -2.0, "高抛": -2.0, "清仓": None}
# 无操作词观点的隐含仓位分：方向强表态但无明确操作，按观察性轻仓计
STANCE_POINTS = {"bull": 1.0, "bear": 0.0, "neutral": 0.0}
# 同标的方向翻空（bull→bear）：观点变脸视作减仓信号（力度同减仓）
FLIP_TO_BEAR_POINTS = -2.0
# 仓位分下限：跌破视为清仓（连续减仓/翻空的自然终点）
EXIT_THRESHOLD = 0.5

# 有效建仓操作：时间线上首条记录的「买入建仓」判定依据
OPEN_ACTIONS = ("建仓", "低吸")


def _now_date() -> str:
    return datetime.now(CN_TZ).strftime("%Y-%m-%d")


def _days_ago(day: str, n: int) -> bool:
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return False
    return d < (datetime.now(CN_TZ).date() - timedelta(days=n))


def build_kol_holdings(db, kol_id, days: int = WINDOW_DAYS) -> dict | None:
    """回放单大V近 N 天观点，推演当前预估持仓。

    返回 {kol, window, timeline, holdings, generated_at}；大V无任何观点返回 None。
    timeline 为逐条操作事件（买入建仓/买入加仓/卖出减仓/卖出清仓/翻空减仓/持仓），
    holdings 为按仓位分归一化的当前持仓（stock 只有个股，topic 为关注板块单列）。
    """
    kol = db.get_kol(int(kol_id))
    if not kol:
        return None
    rows = db.list_mx_opinions_for_kol(kol_id, days=days)
    if not rows:
        return None

    timeline: list[dict] = []
    scores: dict[tuple, dict] = {}  # (ttype, name) -> {score, opened, last_day, ...}
    for r in rows:  # 升序：早 → 晚
        ttype = str(r.get("target_type") or "")
        name = str(r.get("target_name") or "").strip()
        if ttype not in ("stock", "topic") or not name:
            continue
        day = str(r.get("trading_day") or "")
        direction = str(r.get("direction") or "")
        action = str(r.get("action") or "").strip()
        occurred = str(r.get("occurred_at") or "") or f"{day} {r.get('snapshot_at') or ''}"
        key = (ttype, name)
        prev = scores.get(key)
        prev_dir = prev["direction"] if prev else ""

        delta = 0.0
        kind = "hold"  # 无明确操作的观点：只记表态不动仓
        if action in ACTION_POINTS:
            pts = ACTION_POINTS[action]
            if pts is None:  # 清仓
                kind = "clear"
            else:
                if prev is None and action in OPEN_ACTIONS:
                    kind = "open"  # 买入建仓：首条且为开仓操作
                elif prev is None:
                    kind = "hold"  # 首条即加仓/减仓：无先前头寸可加，记持仓
                else:
                    kind = "add" if pts > 0 else "trim"
                delta = pts
        elif prev is not None and prev_dir == "bull" and direction == "bear":
            kind, delta = "flip", FLIP_TO_BEAR_POINTS  # 翻空减仓
        elif prev is None and direction == "bull":
            # 看多首提：观察性建仓（个股入持仓，题材计 1 分入关注板块）
            kind, delta = "open", STANCE_POINTS["bull"]

        if kind == "clear":
            new_score = 0.0
        else:
            new_score = max(0.0, (prev["score"] if prev else 0.0) + delta)

        scores[key] = {
            "score": new_score, "direction": direction or prev_dir, "last_day": day,
            "last_at": occurred, "opened": (prev and prev.get("opened")) or occurred,
        }
        timeline.append({
            "trading_day": day, "occurred_at": occurred,
            "snapshot_at": str(r.get("snapshot_at") or ""),
            "target_type": ttype, "target_name": name,
            "direction": direction, "action": action,
            "kind": kind,
            "summary": str(r.get("summary") or "")[:200],
            "evidence": json.loads(r.get("evidence_post_ids") or "[]"),
        })

    # 当前持仓：清仓/跌破阈值的剔除；沉默超 STALE_DAYS 天的按了结剔除
    live: dict[tuple, dict] = {}
    for key, st in scores.items():
        if st["score"] < EXIT_THRESHOLD:
            continue
        if _days_ago(st["last_day"], STALE_DAYS):
            continue
        live[key] = st

    def _finalize(bucket_keys, label):
        rows_out = []
        total = sum(max(0.0, live[k]["score"]) for k in bucket_keys if k in live) or 1.0
        for key in bucket_keys:
            if key not in live:
                continue
            st = live[key]
            rows_out.append({
                "target_type": key[0], "target_name": key[1],
                "weight": round(100.0 * st["score"] / total, 1),
                "score": round(st["score"], 2),
                "direction": st["direction"],
                "since": st["opened"], "last_at": st["last_at"],
                "last_day": st["last_day"],
            })
        rows_out.sort(key=lambda x: -x["weight"])
        return rows_out

    stock_keys = [k for k in live if k[0] == "stock"]
    topic_keys = [k for k in live if k[0] == "topic"]
    timeline.sort(key=lambda e: (e["trading_day"], e["occurred_at"]), reverse=True)  # 最新在前
    return {
        "kol": {"kol_id": int(kol_id), "name": kol.get("name") or "",
                "avatar": kol.get("avatar_url") or "", "platform": kol.get("platform") or ""},
        "window_days": days,
        "timeline": timeline,
        "holdings": _finalize(stock_keys, "stock"),
        "topics": _finalize(topic_keys, "topic"),
        "opinion_count": len(timeline),
        "generated_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    }
