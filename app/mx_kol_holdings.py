"""MX 大V预估持仓：按历史多空观点回放推演当前仓位。

双信号源合流回放，观点研判优先、标签补位：
- 主源：观点研判管线产出的 mx_opinions（LLM 已从消息提取方向 + 操作词）；
- 补源：消息标签 posts.tags 里的操作词（独立打标管线，覆盖比研判窗口全，
  研判漏提操作时补位）——仅当同标的当日观点未给出操作词时采纳。
本模块只做纯计算回放，不落库、不调 LLM——历史数据不可变，结果可随时重算。
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
# 标签操作词的方向语义（标签不带方向，按操作语义反推）
TAG_BUY_ACTIONS = ("建仓", "加仓", "低吸")
# 标签事件的单帖个股配对上限：一帖命中超过 3 只个股时操作归属太含糊，
# 配对全配会批量虚增头寸，宁缺勿滥整帖跳过
TAG_PAIR_STOCK_MAX = 3


def _days_ago(day: str, n: int) -> bool:
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return False
    return d < (datetime.now(CN_TZ).date() - timedelta(days=n))


# 词表进程内缓存：三份词表都在 settings 单键里、变更频率极低，而预估持仓每次
# 请求都要全量构建（操作词/全市场个股名/别名映射）。以三键原文为版本键——
# 内容不变直接命中，管理员改词表即刻生效。
_vocab_cache: dict = {"key": None, "data": (set(), set(), {})}


def _load_tag_vocab(db) -> tuple[set, set, dict]:
    """标签分类用的词表：操作词表 / 个股正式名集合 / 黑话→正式名映射。"""
    from .db import (
        ACTION_TAG_VOCABULARY_KEY,
        STOCK_ALIASES_KEY,
        STOCK_NAMES_EXCLUDED_KEY,
        STOCK_NAMES_KEY,
    )

    key = (
        db.get_setting(ACTION_TAG_VOCABULARY_KEY) or "",
        db.get_setting(STOCK_NAMES_KEY) or "",
        db.get_setting(STOCK_NAMES_EXCLUDED_KEY) or "",
        db.get_setting(STOCK_ALIASES_KEY) or "",
    )
    if _vocab_cache["key"] == key:
        return _vocab_cache["data"]
    action_set = {str(t).strip() for t in db.get_action_tag_vocabulary() if str(t).strip()}
    stock_set = {str(n).strip() for n in db.get_stock_names() if str(n).strip()}
    alias_map = {str(a.get("alias") or "").strip(): str(a.get("stock") or "").strip()
                 for a in db.get_stock_aliases()}
    data = (action_set, stock_set, alias_map)
    _vocab_cache["key"] = key
    _vocab_cache["data"] = data
    return data


def _build_tag_events(db, kol_id, since_day, action_set, stock_set, alias_map) -> list[dict]:
    """标签含操作词的帖子 → 候选操作事件（个股配对，题材不判仓）。

    同帖操作词 × 个股标签做笛卡尔配对：标签体系不记录操作归属，个股名与
    操作词同帖即视为相关（LLM 打标时同帖标的与操作本就来自同一段话）。
    since_day 由调用方统一按北京时间算好传入（与观点源同一天窗）。
    """
    events: list[dict] = []
    for r in db.list_mx_action_tag_posts_for_kol(kol_id, since_day, sorted(action_set)):
        tags = [str(t).strip() for t in (r.get("tags") or []) if str(t).strip()]
        actions = [t for t in tags if t in action_set][:2]
        stocks: list[str] = []
        for t in tags:
            if t in action_set:
                continue
            official = alias_map.get(t, t)
            if official in stock_set and official not in stocks:
                stocks.append(official)
        if not actions or not stocks or len(stocks) > TAG_PAIR_STOCK_MAX:
            continue
        day = str(r.get("trading_day") or "")
        occurred = str(r.get("published_at") or "") or f"{day} 00:00:00"
        for name in stocks:
            for action in actions:
                events.append({
                    "trading_day": day, "occurred_at": occurred, "snapshot_at": "",
                    "target_type": "stock", "target_name": name,
                    "direction": "bull" if action in TAG_BUY_ACTIONS else "bear",
                    "action": action, "source": "tag",
                    "summary": str(r.get("content") or "").strip()[:160],
                    "evidence_post_ids": [int(r["id"])] if r.get("id") else [],
                })
    return events


def build_kol_holdings(db, kol_id, days: int = WINDOW_DAYS) -> dict | None:
    """回放单大V近 N 天观点+标签，推演当前预估持仓。

    返回 {kol, window, timeline, holdings, generated_at}；大V无任何信号返回 None。
    timeline 为逐条操作事件（买入建仓/买入加仓/卖出减仓/卖出清仓/翻空减仓/持仓表态，
    source 区分 opinion=观点研判 / tag=标签补位），holdings 为按仓位分归一化的
    当前持仓（stock 只有个股，topic 为关注板块单列）。
    """
    kol = db.get_kol(int(kol_id))
    if not kol:
        return None
    # 窗口下界统一北京时间算（观点源与标签源同一天，不能一边 CN 一边 UTC）
    since = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = db.list_mx_opinions_for_kol(kol_id, since_day=since)

    # 事件流：观点为主、标签补位。同标的当日观点已给出**有仓位语义的**操作词时
    # 该日标签事件整体让位（观点管线对证据/作者有强校验，可信度更高）；观察/做T
    # 等词表外操作不参与打分，也不参与压制——否则「观察」会吞掉同日标签的
    # 真实建仓信号。同标的同日同操作的多条标签帖只取最早一条，不重复加减仓。
    events: list[dict] = []
    opinion_action_days: dict[tuple, set] = {}
    for r in rows:  # 升序：早 → 晚
        ttype = str(r.get("target_type") or "")
        name = str(r.get("target_name") or "").strip()
        if ttype not in ("stock", "topic") or not name:
            continue
        day = str(r.get("trading_day") or "")
        direction = str(r.get("direction") or "")
        action = str(r.get("action") or "").strip()
        occurred = str(r.get("occurred_at") or "") or f"{day} {r.get('snapshot_at') or ''}"
        if action in ACTION_POINTS:
            opinion_action_days.setdefault((ttype, name), set()).add(day)
        events.append({
            "trading_day": day, "occurred_at": occurred,
            "snapshot_at": str(r.get("snapshot_at") or ""),
            "target_type": ttype, "target_name": name,
            "direction": direction, "action": action, "source": "opinion",
            "summary": str(r.get("summary") or "")[:200],
            "evidence_post_ids": json.loads(r.get("evidence_post_ids") or "[]"),
        })
    # 标签补位与观点是否为空无关：大V没被研判过但消息打了操作标签时，纯标签也能推仓
    action_set, stock_set, alias_map = _load_tag_vocab(db)
    seen_tag: set[tuple] = set()
    for ev in _build_tag_events(db, kol_id, since, action_set, stock_set, alias_map):
        if ev["trading_day"] in opinion_action_days.get(("stock", ev["target_name"]), set()):
            continue
        dedup = (ev["target_name"], ev["action"], ev["trading_day"])
        if dedup in seen_tag:
            continue
        seen_tag.add(dedup)
        events.append(ev)
    if not events:
        return None
    events.sort(key=lambda e: (e["trading_day"], e["occurred_at"]))  # 早 → 晚

    timeline: list[dict] = []
    scores: dict[tuple, dict] = {}  # (ttype, name) -> {score, opened, last_day, ...}
    for ev in events:
        ttype = ev["target_type"]
        name = ev["target_name"]
        day = ev["trading_day"]
        direction = ev["direction"]
        action = ev["action"]
        occurred = ev["occurred_at"]
        key = (ttype, name)
        prev = scores.get(key)
        prev_dir = prev["direction"] if prev else ""

        delta = 0.0
        kind = "hold"  # 无明确操作的观点：只记表态不动仓
        if action in ACTION_POINTS:
            pts = ACTION_POINTS[action]
            if pts is None:  # 清仓
                kind = "clear"
            elif prev is None:
                if action in OPEN_ACTIONS:
                    kind = "open"  # 买入建仓：首条且为开仓操作
                    delta = pts
                elif pts > 0:
                    # 首条即加仓/低吸：无先前头寸可加，记持仓态；
                    # 买入意图明确，按开仓力度给分
                    delta = pts
                # 首条即减仓/高抛：无仓可减，记持仓态不动分
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
            "snapshot_at": ev["snapshot_at"],
            "target_type": ttype, "target_name": name,
            "direction": direction, "action": action,
            "kind": kind, "source": ev["source"],
            "summary": ev["summary"],
            "evidence": ev["evidence_post_ids"],
        })

    # 当前持仓：清仓/跌破阈值的剔除；沉默超 STALE_DAYS 天的按了结剔除
    live: dict[tuple, dict] = {}
    for key, st in scores.items():
        if st["score"] < EXIT_THRESHOLD:
            continue
        if _days_ago(st["last_day"], STALE_DAYS):
            continue
        live[key] = st

    def _finalize(bucket_keys):
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
        "stale_days": STALE_DAYS,  # 前端空态文案同口径，避免常量双写漂移
        "timeline": timeline,
        "holdings": _finalize(stock_keys),
        "topics": _finalize(topic_keys),
        "opinion_count": len(timeline),
        "generated_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    }
