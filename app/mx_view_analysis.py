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
