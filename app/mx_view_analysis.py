"""MX 平台大V实时观点：快照研判管线（periodic batch research）。

与 posts.tags 打标链路完全独立：每个快照时刻把窗口内新消息交给 LLM 研判出
结构化多空观点（mx_opinions），再纯 SQL/Python 聚合成整页状态存快照
（mx_view_snapshots.payload）。LLM 只做「消息→观点」，排名/强度/动量都是计算。
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))

# ---- settings 键 ----
MX_VIEW_ENABLED_KEY = "mx_view_enabled"
MX_VIEW_SCHEDULE_KEY = "mx_view_schedule"
MX_VIEW_BATCH_SIZE_KEY = "mx_view_batch_size"
MX_VIEW_KOL_IDS_KEY = "mx_view_kol_ids"
MX_VIEW_TOPIC_HINTS_KEY = "mx_view_topic_hints"
MX_VIEW_TOPIC_CANDIDATES_KEY = "mx_view_topic_candidates"
MX_VIEW_VERSION_KEY = "mx_view_version"
MX_VIEW_SUMMARY_MIN_INTERVAL_KEY = "mx_view_summary_min_interval_min"

# 当日首个快照（09:20）的消息窗口起点固定为 09:15（集合竞价开始），不可配
MX_VIEW_FIRST_WINDOW_START = "09:15"

DEFAULT_MX_VIEW_SCHEDULE = {
    "segments": [
        {"start": "09:30", "end": "10:30", "interval_min": 5},
        {"start": "10:30", "end": "11:30", "interval_min": 10},
        {"start": "13:00", "end": "13:20", "interval_min": 5},
        {"start": "13:20", "end": "15:00", "interval_min": 10},
    ],
    "extra_times": ["09:20", "09:26", "12:00", "16:00"],
}

DEFAULT_TOPIC_HINTS = [
    "固态电池", "算力租赁", "AI算力", "人工智能", "机器人", "低空经济", "房地产", "白酒",
    "半导体", "芯片", "光伏", "锂电池", "储能", "新能源车", "军工", "医药", "创新药",
    "中药", "银行", "券商", "保险", "煤炭", "钢铁", "有色金属", "黄金", "石油", "化工",
    "电力", "传媒", "游戏", "跨境电商", "消费电子", "消费", "卫星互联网", "数据要素",
    "信创", "网络安全", "预制菜", "旅游", "免税", "养殖", "种业",
]

# 强度分权重：方向定符号（bull +1 / bear -1，neutral 不参与），操作放大绝对值
ACTION_BOOST = {"建仓": 1.5, "加仓": 1.5, "减仓": 1.5, "清仓": 1.5, "做T": 0.7, "观察": 0.7, "": 1.0}

_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")


def _hhmm_to_min(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def resolve_schedule(config: dict | None) -> list[str]:
    """解析快照配置为全天显式时刻列表（升序去重；段起点与终点都生成）。"""
    cfg = config if isinstance(config, dict) else DEFAULT_MX_VIEW_SCHEDULE
    times: set[str] = set()
    for seg in cfg.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        start, end = str(seg.get("start") or ""), str(seg.get("end") or "")
        try:
            interval = int(seg.get("interval_min") or 0)
        except (TypeError, ValueError):
            interval = 0
        if not (_HHMM_RE.match(start) and _HHMM_RE.match(end) and interval > 0):
            continue
        cur, stop = _hhmm_to_min(start), _hhmm_to_min(end)
        while cur <= stop:
            times.add(f"{cur // 60:02d}:{cur % 60:02d}")
            cur += interval
    for t in cfg.get("extra_times") or []:
        t = str(t)
        if _HHMM_RE.match(t):
            times.add(t)
    return sorted(times)


def snapshot_windows(times: list[str]) -> list[tuple[str, str]]:
    """每快照的消息窗口 (上一快照, 本快照]；首窗起点固定 09:15。"""
    starts = [MX_VIEW_FIRST_WINDOW_START] + list(times[:-1])
    return list(zip(starts, times))


# ---- settings 读取（容错：坏值回默认） ----

def _load_json_setting(db, key, default):
    raw = db.get_setting(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def load_schedule_config_raw(db) -> dict:
    cfg = _load_json_setting(db, MX_VIEW_SCHEDULE_KEY, DEFAULT_MX_VIEW_SCHEDULE)
    return cfg if isinstance(cfg, dict) else dict(DEFAULT_MX_VIEW_SCHEDULE)


def get_schedule_config(db) -> dict:
    """管理端展示用：原始配置 + 解析结果。"""
    cfg = load_schedule_config_raw(db)
    return {"config": cfg, "resolved_times": resolve_schedule(cfg)}


def get_enabled(db) -> bool:
    return str(db.get_setting(MX_VIEW_ENABLED_KEY) or "0") == "1"


def get_batch_size(db) -> int:
    try:
        return max(1, int(db.get_setting(MX_VIEW_BATCH_SIZE_KEY) or 600))
    except (TypeError, ValueError):
        return 600


def get_kol_ids(db) -> list[int]:
    raw = _load_json_setting(db, MX_VIEW_KOL_IDS_KEY, [])
    return [int(i) for i in raw] if isinstance(raw, list) else []


def get_topic_hints(db) -> list[str]:
    raw = _load_json_setting(db, MX_VIEW_TOPIC_HINTS_KEY, None)
    if raw is None:
        return list(DEFAULT_TOPIC_HINTS)
    return [str(x) for x in raw if str(x).strip()] if isinstance(raw, list) else []


def get_topic_candidates(db) -> list[str]:
    raw = _load_json_setting(db, MX_VIEW_TOPIC_CANDIDATES_KEY, [])
    return [str(x) for x in raw] if isinstance(raw, list) else []


def add_topic_candidates(db, names: list[str]) -> None:
    """新题材并入候选表（去重、不含参考表已有词），上限 200。"""
    hints = set(get_topic_hints(db))
    cands = get_topic_candidates(db)
    for name in names:
        if name and name not in hints and name not in cands:
            cands.append(name)
    db.set_setting(MX_VIEW_TOPIC_CANDIDATES_KEY, json.dumps(cands[:200], ensure_ascii=False))


def get_summary_min_interval(db) -> int:
    try:
        return max(0, int(db.get_setting(MX_VIEW_SUMMARY_MIN_INTERVAL_KEY) or 0))
    except (TypeError, ValueError):
        return 0


# ---- 版本号（SSE 推送依据，settings 持久化 + 进程内无状态） ----

def get_view_version(db) -> int:
    try:
        return int(db.get_setting(MX_VIEW_VERSION_KEY) or 0)
    except (TypeError, ValueError):
        return 0


def bump_view_version(db) -> int:
    v = get_view_version(db) + 1
    db.set_setting(MX_VIEW_VERSION_KEY, str(v))
    return v


def resolve_system_llm_config(db):
    """API 手动跑批/回填用的站点 LLM 配置（settings 优先，退环境配置）。"""
    from .config import load_config

    config = load_config()
    cfg = type("LlmConfig", (), {})()
    cfg.api_key = db.get_setting("llm_api_key") or config.llm.api_key or ""
    cfg.api_base = db.get_setting("llm_api_base") or config.llm.api_base or "https://api.openai.com/v1"
    cfg.model = db.get_setting("llm_model") or config.llm.model or "gpt-4o-mini"
    cfg.user_supplied = False
    return cfg


# ---- 观点校验与聚合 ----

VALID_DIRECTIONS = ("bull", "bear", "neutral")
VALID_TARGET_TYPES = ("topic", "stock")
VALID_ACTIONS = tuple(a for a in ACTION_BOOST if a)


def validate_opinions(raw, posts, aliases, day, snapshot_at):
    """校验 LLM 研判结果：证据核对/作者核对/枚举/黑话归一/批内去重。

    返回 (可落库 opinions, 参考表之外的新题材名)。任何一项不满足即丢弃该条。
    """
    posts_by_id = {}
    for p in posts or []:
        posts_by_id[int(p["id"])] = p
    alias_map = {str(a.get("alias") or ""): str(a.get("stock") or "") for a in aliases or []}
    valid: list[dict] = []
    new_topics: list[str] = []
    seen: set[tuple] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        evidence = []
        for ev in item.get("evidence") or []:
            try:
                ev_id = int(ev)
            except (TypeError, ValueError):
                continue
            if ev_id in posts_by_id and ev_id not in evidence:
                evidence.append(ev_id)
        if not evidence:
            continue
        ev_posts = [posts_by_id[i] for i in evidence]
        authors = {str(p.get("kol_name") or "") for p in ev_posts}
        author = str(item.get("author") or "")
        if author and author not in authors:
            continue  # 作者与证据不符：丢弃
        kol_id = int(ev_posts[0]["kol_id"])
        ttype = str(item.get("target_type") or "")
        direction = str(item.get("direction") or "")
        if ttype not in VALID_TARGET_TYPES or direction not in VALID_DIRECTIONS:
            continue
        name = str(item.get("target_name") or "").strip()
        if not name:
            continue
        if ttype == "stock":
            name = alias_map.get(name, name)
        action = str(item.get("action") or "").strip()
        if action and action not in VALID_ACTIONS:
            action = ""
        key = (kol_id, ttype, name)
        if key in seen:
            continue
        seen.add(key)
        occurred = max(str(p.get("published_at") or "") for p in ev_posts)
        valid.append(
            {
                "trading_day": day,
                "snapshot_at": snapshot_at,
                "kol_id": kol_id,
                "target_type": ttype,
                "target_name": name,
                "direction": direction,
                "action": action,
                "confidence": str(item.get("confidence") or "high"),
                "summary": str(item.get("summary") or "").strip()[:200],
                "evidence_post_ids": evidence,
                "occurred_at": occurred,
            }
        )
        if ttype == "topic":
            new_topics.append(name)
    return valid, sorted(set(new_topics))


def _opinion_weight(op: dict) -> float:
    """方向定符号 × 操作放大 × 大V权重。"""
    if op["direction"] == "bull":
        sign = 1.0
    elif op["direction"] == "bear":
        sign = -1.0
    else:
        return 0.0
    boost = ACTION_BOOST.get(str(op.get("action") or ""), 1.0)
    kol_w = 1.2 if int(op.get("kol_priority") or 0) > 0 else 1.0
    return sign * boost * kol_w


def aggregate_day_state(day, snapshot_at, opinions, prev_payload=None, new_opinions=None):
    """按「当前立场」口径聚合整页状态：每大V每标的取 ≤snapshot_at 的最新一条。

    opinions 须已按 (snapshot_at, occurred_at, id) 升序（list_mx_opinions 的序）。
    """
    stance: dict[tuple, dict] = {}
    for op in opinions or []:
        if str(op.get("snapshot_at") or "") > snapshot_at:
            continue
        stance[(int(op["kol_id"]), str(op["target_type"]), str(op["target_name"]))] = op

    def _blank(kind, name):
        return (
            {"name": name, "bull": 0, "bear": 0, "net": 0, "s_bull": 0.0, "s_bear": 0.0,
             "strength": 50, "momentum": 0, "latest_at": "", "actions": {}}
            if kind == "stock"
            else {"name": name, "bull": 0, "bear": 0, "net": 0, "s_bull": 0.0, "s_bear": 0.0,
                  "strength": 50, "momentum": 0, "latest_at": ""}
        )

    topics: dict[str, dict] = {}
    stocks: dict[str, dict] = {}
    kol_state: dict[int, dict] = {}
    for (kol_id, ttype, name), op in stance.items():
        w = _opinion_weight(op)
        bucket = stocks if ttype == "stock" else topics
        agg = bucket.setdefault(name, _blank(ttype, name))
        if w > 0:
            agg["bull"] += 1
            agg["s_bull"] += w
        elif w < 0:
            agg["bear"] += 1
            agg["s_bear"] += abs(w)
        occurred = str(op.get("occurred_at") or "")
        if occurred > agg["latest_at"]:
            agg["latest_at"] = occurred
        if ttype == "stock" and op.get("action"):
            agg["actions"][op["action"]] = agg["actions"].get(op["action"], 0) + 1
        # 大V总览
        ks = kol_state.setdefault(
            kol_id,
            {"kol_id": kol_id, "name": op.get("kol_name") or "", "avatar": op.get("avatar_url") or "",
             "opinion_count": 0, "bull_names": [], "bear_names": [], "last_at": ""},
        )
        ks["opinion_count"] += 1
        target = f"{name}" if ttype == "topic" else name
        if w > 0 and len(ks["bull_names"]) < 8:
            ks["bull_names"].append(target)
        if w < 0 and len(ks["bear_names"]) < 8:
            ks["bear_names"].append(target)
        if occurred > ks["last_at"]:
            ks["last_at"] = occurred

    def _finalize(bucket, prev_list):
        prev_net = {str(x.get("name")): int(x.get("net") or 0) for x in (prev_list or [])}
        out = []
        for agg in bucket.values():
            total = agg["s_bull"] + agg["s_bear"]
            agg["net"] = agg["bull"] - agg["bear"]
            agg["strength"] = round(50 + 45 * (agg["s_bull"] - agg["s_bear"]) / max(total, 1.0))
            agg["momentum"] = agg["net"] - prev_net.get(agg["name"], agg["net"])
            for drop in ("s_bull", "s_bear"):
                agg.pop(drop)
            out.append(agg)
        return out

    topic_rows = sorted(_finalize(topics, (prev_payload or {}).get("topics")),
                        key=lambda x: (-x["net"], -(x["bull"] + x["bear"])))
    stock_rows = sorted(_finalize(stocks, (prev_payload or {}).get("stocks")),
                        key=lambda x: (-x["strength"], -x["net"]))
    kol_rows = sorted(kol_state.values(), key=lambda x: (-x["opinion_count"], x["name"]))
    return {
        "trading_day": day,
        "snapshot_at": snapshot_at,
        "summary": None,  # Task 5 填充 {"text","items"}
        "topics": topic_rows,
        "stocks": stock_rows,
        "kols": kol_rows,
        "new_opinions": [
            {
                "kol_id": int(o["kol_id"]), "kol_name": o.get("kol_name") or "",
                "target_type": o["target_type"], "target_name": o["target_name"],
                "direction": o["direction"], "action": o.get("action") or "",
                "summary": o.get("summary") or "", "occurred_at": o.get("occurred_at") or "",
            }
            for o in (new_opinions or [])
        ][:50],
    }
