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
from datetime import date, datetime, timedelta, timezone

from . import llm

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


def remove_topic_candidate(db, name: str) -> None:
    """审核落定（采纳/忽略）后从候选表删除指定题材名；名字不存在则忽略。"""
    name = str(name or "").strip()
    cands = get_topic_candidates(db)
    if not name or name not in cands:
        return
    cands.remove(name)
    db.set_setting(MX_VIEW_TOPIC_CANDIDATES_KEY, json.dumps(cands, ensure_ascii=False))


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


# ---- 批次全流程（研判 → 校验落库 → 聚合 → 总结 → 版本推进） ----

_batch_lock = threading.Lock()
_fail_lock = threading.Lock()
_fail_count = 0


def get_fail_count(db) -> int:
    with _fail_lock:
        return _fail_count


def _reset_fail_count() -> None:
    global _fail_count
    with _fail_lock:
        _fail_count = 0


def _bump_fail_count() -> int:
    global _fail_count
    with _fail_lock:
        _fail_count += 1
        return _fail_count


_backfill_state_lock = threading.Lock()
_backfill_state: dict = {
    "running": False, "cancel": False, "day_from": "", "day_to": "",
    "current_day": "", "done_windows": 0, "total_windows": 0, "error": "",
}


def backfill_running() -> bool:
    with _backfill_state_lock:
        return bool(_backfill_state["running"])


SUMMARY_SYSTEM_PROMPT = (
    "你是A股操作建议总结助手。输入某交易日某快照时刻的群体大V观点聚合数据（JSON）。"
    '输出 JSON：{"text":"不超过3句话的今日操作建议","items":[{"type":"topic|stock","name":"标的",'
    '"direction":"bull|bear","action":"建仓|加仓|减仓|清仓|做T|观察（可空）"}]}。'
    "items 最多 6 条，只选最有共识的方向与重点个股；text 用最简洁的中文讲清：主攻什么、回避什么、重点个股怎么操作。"
)


def _agg_digest(payload: dict, prev_summary: str) -> str:
    slim = {
        "snapshot_at": payload["snapshot_at"],
        "topics": payload["topics"][:8],
        "stocks": payload["stocks"][:8],
        "kol_count": len(payload.get("kols") or []),
        "prev_summary": prev_summary,
    }
    return json.dumps(slim, ensure_ascii=False)


def generate_summary(db, llm_config, payload) -> dict:
    """每快照一版总结；LLM 失败/未配置不拖垮批次，回退占位文案。

    未配置时交由 llm._chat 自行返回 None → 回退，与配置了坏 key 的失败同路。
    """
    fallback = {"text": "（本次总结生成失败，以上一版为准）", "items": []}
    prev = ""
    try:
        snaps = db.list_mx_view_snapshots(payload["trading_day"])
        earlier = [s for s in snaps if s["snapshot_at"] < payload["snapshot_at"] and s["payload"].get("summary")]
        if earlier:
            prev = earlier[-1]["payload"]["summary"].get("text") or ""
    except Exception:  # noqa: BLE001
        pass
    try:
        text = llm._chat(
            llm_config,
            [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": _agg_digest(payload, prev)},
            ],
            4000,
            temperature=0,
            attempts=2,
            response_format={"type": "json_object"},
            timeout=120,
        )
        if not text:
            return fallback
        parsed = json.loads(re.search(r"\{.*\}", text, re.DOTALL).group(0))
        items = [
            {
                "type": str(i.get("type") or "topic"),
                "name": str(i.get("name") or "")[:30],
                "direction": i.get("direction") if i.get("direction") in ("bull", "bear") else "neutral",
                "action": str(i.get("action") or ""),
            }
            for i in (parsed.get("items") or []) if isinstance(i, dict) and str(i.get("name") or "").strip()
        ][:6]
        return {"text": str(parsed.get("text") or "").strip()[:500] or fallback["text"], "items": items}
    except Exception:  # noqa: BLE001
        logger.exception("MX 观点总结生成失败")
        return fallback


def _maybe_summary(db, llm_config, payload) -> dict:
    """按 mx_view_summary_min_interval_min 间隔复用上一版总结（默认 0=每快照必出）。"""
    interval = get_summary_min_interval(db)
    if interval > 0:
        snaps = [s for s in db.list_mx_view_snapshots(payload["trading_day"])
                 if s["payload"].get("summary") and s["snapshot_at"] < payload["snapshot_at"]]
        if snaps:
            last = snaps[-1]
            last_min = _hhmm_to_min(last["snapshot_at"])
            cur_min = _hhmm_to_min(payload["snapshot_at"])
            if cur_min - last_min < interval:
                return last["payload"]["summary"]
    return generate_summary(db, llm_config, payload)


def run_snapshot_batch(db, day, snapshot_at, window, kind="live", llm_config=None,
                       advance_cursor: bool = True) -> dict:
    """跑一个快照批次：取窗口消息 → LLM 研判 → 校验落库 → 聚合存快照。

    失败抛异常（批次落 failed、游标不动）；0 条新消息直接返回 {"ran": False}。
    回填（advance_cursor=False）时不推进消息游标，避免抢走 live 批次的未读窗口。
    """
    with _batch_lock:
        batch_id = db.upsert_mx_view_batch(day, snapshot_at, kind)
        cursor = db.get_mx_view_cursor()
        kol_ids = get_kol_ids(db)
        posts = db.list_mx_posts_in_window(
            day, window[0], window[1], after_id=cursor,
            kol_ids=kol_ids or None, limit=get_batch_size(db),
        )
        if not posts:
            db.finish_mx_view_batch(batch_id, "done", 0)
            return {"ran": False, "opinions": 0, "message_count": 0}
        try:
            raw = llm.research_viewpoints(
                posts, get_topic_hints(db), db.get_action_tag_vocabulary(), llm_config=llm_config
            )
            if raw is None:
                raise RuntimeError("LLM 研判失败（无有效响应）")
            valid, new_topics = validate_opinions(
                raw, posts, db.get_stock_aliases(), day, snapshot_at
            )
            db.replace_mx_opinions(batch_id, valid)
            if advance_cursor:
                db.set_mx_view_cursor(max(int(p["id"]) for p in posts))
            if new_topics:
                add_topic_candidates(db, new_topics)

            opinions = db.list_mx_opinions(day)
            snaps = db.list_mx_view_snapshots(day)
            earlier = [s for s in snaps if s["snapshot_at"] < snapshot_at]
            prev_payload = earlier[-1]["payload"] if earlier else None
            payload = aggregate_day_state(day, snapshot_at, opinions, prev_payload, new_opinions=valid)
            payload["message_count"] = len(posts)
            payload["summary"] = _maybe_summary(db, llm_config, payload)
            seq = len([s for s in snaps if s["snapshot_at"] < snapshot_at]) + 1
            db.upsert_mx_view_snapshot(day, snapshot_at, seq, kind, payload, batch_id)
            db.finish_mx_view_batch(batch_id, "done", len(posts))
            if kind == "live":
                bump_view_version(db)
            _reset_fail_count()
            logger.info("MX 观点快照 %s %s messages=%d opinions=%d", day, snapshot_at, len(posts), len(valid))
            return {"ran": True, "opinions": len(valid), "message_count": len(posts)}
        except Exception as e:  # noqa: BLE001
            db.finish_mx_view_batch(batch_id, "failed", len(posts), str(e)[:500])
            count = _bump_fail_count()
            logger.error("MX 观点快照失败 %s %s（连续第 %d 次）: %s", day, snapshot_at, count, e)
            raise


def run_due_view_batch(db, llm_config=None):
    """调度器入口：启用且工作日且无回填时，跑最近一个到期的计划快照。

    错过多个快照（停机）时只跑一批、以实际时刻命名（时间轴不补空档）。
    返回 {"ran":..., "failed":..., "consecutive":...} 或 None（无动作）。
    """
    if not get_enabled(db) or backfill_running():
        return None
    now = datetime.now(CN_TZ)
    if now.weekday() >= 5:
        return None
    day = now.strftime("%Y-%m-%d")
    now_hhmm = now.strftime("%H:%M")
    times = resolve_schedule(load_schedule_config_raw(db))
    done = {s["snapshot_at"] for s in db.list_mx_view_snapshots(day)}
    last_done = max(done, default="")
    pending = [t for t in times if t > last_done and t <= now_hhmm]
    if not pending:
        return None
    if _batch_lock.locked():
        return None
    idx = times.index(pending[0])
    win_start = MX_VIEW_FIRST_WINDOW_START if idx == 0 else times[idx - 1]
    # 错过多个快照：快照名与窗口终点都用当前时刻，覆盖到最后一条消息
    snapshot_at = pending[0] if len(pending) == 1 else now_hhmm
    win_end = snapshot_at
    try:
        result = run_snapshot_batch(
            db, day=day, snapshot_at=snapshot_at, window=(win_start, win_end),
            kind="live", llm_config=llm_config,
        )
        return {"ran": result["ran"], "failed": False, "consecutive": get_fail_count(db)}
    except Exception as e:  # noqa: BLE001
        return {"ran": False, "failed": True, "error": str(e), "consecutive": get_fail_count(db)}


# ---- 回填 job：按快照表重放整天（仅工作日），不推游标不推版本 ----

def _iter_weekdays(day_from: str, day_to: str) -> list[str]:
    d0 = date.fromisoformat(day_from)
    d1 = date.fromisoformat(day_to)
    out = []
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d = date.fromordinal(d.toordinal() + 1)
    return out


def backfill_status() -> dict:
    with _backfill_state_lock:
        return dict(_backfill_state)


def request_backfill_cancel() -> None:
    with _backfill_state_lock:
        _backfill_state["cancel"] = True


def start_backfill_job(db, day_from, day_to, llm_config=None) -> bool:
    """回填 = 按快照表重放整天（仅工作日）。已在跑或日期区间非法/超 30 天返回 False。"""
    with _backfill_state_lock:
        if _backfill_state["running"]:
            return False
    try:
        days = _iter_weekdays(day_from, day_to)
    except ValueError:
        return False
    if not days or (date.fromisoformat(day_to) - date.fromisoformat(day_from)).days > 30:
        return False
    with _backfill_state_lock:
        _backfill_state.update(
            running=True, cancel=False, day_from=day_from, day_to=day_to,
            current_day="", done_windows=0, total_windows=0, error="",
        )

    def worker():
        try:
            windows = snapshot_windows(resolve_schedule(load_schedule_config_raw(db)))
            with _backfill_state_lock:
                _backfill_state["total_windows"] = len(days) * len(windows)
            for day in days:
                with _backfill_state_lock:
                    if _backfill_state["cancel"]:
                        break
                    _backfill_state["current_day"] = day
                for start, end in windows:
                    with _backfill_state_lock:
                        if _backfill_state["cancel"]:
                            break
                    try:
                        run_snapshot_batch(
                            db, day=day, snapshot_at=end, window=(start, end),
                            kind="backfill", llm_config=llm_config, advance_cursor=False,
                        )
                    except Exception as e:  # noqa: BLE001 - 单窗失败继续，错误留批次表
                        logger.error("回填单窗失败 %s %s: %s", day, end, e)
                    with _backfill_state_lock:
                        _backfill_state["done_windows"] += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("MX 观点回填任务异常")
            with _backfill_state_lock:
                _backfill_state["error"] = str(e)[:300]
        finally:
            with _backfill_state_lock:
                _backfill_state["running"] = False
                _backfill_state["current_day"] = ""

    threading.Thread(target=worker, name="mx-view-backfill", daemon=True).start()
    return True
