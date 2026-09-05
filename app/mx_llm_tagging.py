"""MX 消息的 LLM 打标。

手动打标（start_manual_run，管理端「开始 LLM 打标」）：
- 弹窗选 MX 大V（显示各自未打标消息数），一次最多处理 1000 条；启动时取好
  待打标消息并切成每批 ≤100 条的批次入队，同时最多 3 个批次在打标（即 3 次
  LLM 调用），其余排队；按 llm_tagged=0 选帖（blocked/hidden 不算，最旧优先）；
- 已有任务在跑时新任务照常入队排队，不再拒绝；进行中任务已认领的消息不会被
  新任务重复处理；可按任务取消（当前批次完成后停止，排队批次直接跳过）；
  单批失败只收场所在任务，剩余批次跳过（消息保持未打标，可直接重试）；
- 结果与帖子已有标签**去重合并**（不再整体替换），low 进 post_tag_reviews 人工
  审核（标签已在帖上的不进——通过与否它都已在帖），kind=general 黑话经
  is_acceptable_alias 预过滤后进候选表。

自动打标（mx_llm_tag_auto_loop，管理端「MX LLM 打标（自动）」）：
- 配置存 settings（get/set_mx_llm_tag_auto_config）：开关 + 必填的常规时间段
  + 可增减的特殊时间段；每个时间段两个触发参数——新消息累计达到 threshold
  条立即触发、距上次触发超过 interval_minutes 分钟也触发（需有待打标消息）；
- 任一触发后，条数累计与间隔计时都重新计算：条数按水位（上次触发时新消息的
  最大 id）之后的新增消息计，间隔按上次触发时刻算，因此间隔之内条数先到会
  把下一个间隔触发点推向后；
- 特殊时间段优先于常规时间段（按配置顺序取第一个命中的），时段都不命中不触
  发；触发的自动任务与手动任务共用同一队列（每批 ≤100 条、并发 ≤3），且同一
  时刻最多一个自动任务在队列/执行，防止处理不及积压连环入队；
- 自动任务连续失败达到阈值发系统告警（带冷却窗口），恢复成功后发恢复通知。

试打（run_tag_test）：取 10 条未打标消息走同源调用与校验，零写入，供调参预览。
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time as time_module
from collections import deque
from datetime import datetime, timedelta, timezone

from .db import (
    MX_LLM_TAG_BATCH_SIZE_KEY,
    POST_STOCK_TAGS_MAX,
    POST_TAGS_MAX,
)

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))

# 连续失败告警：跨过阈值即发，之后每过冷却窗口再提醒一次（仍在失败时）
ALERT_FAIL_THRESHOLD = 3
ALERT_COOLDOWN_SECONDS = 1800
_ALERT_COOLDOWN_KEY = "mx_llm_tag_alert_at"
# 防偷懒：LLM 响应缺失的消息占比超过该值，整批视为失败（游标不动，下轮重试）
MISSING_RATIO_LIMIT = 0.3
# 管理端「试打」按钮每次取的未处理消息条数
TEST_BATCH_SIZE = 10
# 手动打标单批（一次 LLM 调用）最多处理的消息条数：一次带太多消息易超时/输出
# 截断导致整批失败
MANUAL_BATCH_SIZE_LIMIT = 100
# 同时进行的打标批次（LLM 调用）上限，更多批次排队
MANUAL_MAX_WORKERS = 3
# 进度接口保留的已完成 run 数上限
_FINISHED_RUNS_KEEP = 10
# 自动打标轮询间隔（秒）：触发判定粒度，远小于最小的触发间隔（分钟）
AUTO_POLL_SECONDS = 15
# 自动打标单次触发最多处理的未打标消息条数（切批后进同一队列）
AUTO_RUN_MAX_MESSAGES = 1000
# 特殊时间段数量上限与触发参数边界
AUTO_MAX_SPECIALS = 20
AUTO_INTERVAL_MIN, AUTO_INTERVAL_MAX = 1, 1440
AUTO_THRESHOLD_MAX = 100000

# 运行状态（进程内计数，重启归零）：供管理端状态面板展示
_state_lock = threading.Lock()
_state: dict = {
    "consecutive_failures": 0,
    "alert_active": False,
    "last_run": None,
    "calls_today": {"date": "", "count": 0},
}

# 试打专用锁：试打零写入（不写标签/审核/候选），与手动/自动打标并行是安全的
# ——不互斥，否则打标任务连续持锁（每批 LLM 最长 6 分钟），「试打 10 条」会
# 长时间 409 无法诊断
_test_lock = threading.Lock()

# 自动打标触发布防（进程内，重启后重新布防：水位推到当前、计时清零）。
# 条数维度看水位之后的新增消息，间隔维度看 last_trigger_ts。
_auto_state_lock = threading.Lock()
_auto_state: dict = {
    "armed": False,           # 已初始化水位与计时（开启后首个检查周期完成）
    "watermark": 0,           # 上次布防/触发时的新消息最大 id
    "last_trigger_ts": None,  # 上次触发时刻（epoch 秒；None=等待首轮触发评估）
}
# 已核对过完成状态的自动任务 id：告警统计只算新结束的任务，不重复计数
_auto_alert_seen: set[int] = set()

# 手动打标任务队列：一次「开始打标」是一个 run，待打标消息在启动时取好并切成
# 每批 ≤MANUAL_BATCH_SIZE_LIMIT 条入 _queue；工作线程（≤MANUAL_MAX_WORKERS，队列
# 空即退出、入队时按需重建）消费——同时最多 3 个批次在打标，其余排队。
# 状态全在进程内（重启归零）。
_runs_lock = threading.Lock()
_runs: dict[int, dict] = {}  # run_id -> run 状态（含最近完成的，供进度展示）
_queue: deque = deque()      # 待处理批次 item（见 start_manual_run）
_workers = 0                 # 活跃工作线程数
_run_seq = 0
_claimed_ids: set[int] = set()  # 进行中 run 已认领的消息 id（防重复打标）
# 进度接口暴露的 run 字段（claimed_ids 等内部字段不外露）
_RUN_PUBLIC_FIELDS = (
    "run_id", "source", "kols", "status", "cancel_requested", "total", "processed",
    "batch_total", "batches_done", "batches_failed", "batches_skipped",
    "batches_running", "error", "started_at", "finished_at", "summary",
)


def get_tagger_status() -> dict:
    """管理端状态面板用的运行快照（内存计数）。"""
    with _state_lock:
        return {
            "consecutive_failures": _state["consecutive_failures"],
            "alert_active": _state["alert_active"],
            "last_run": dict(_state["last_run"]) if _state["last_run"] else None,
            "calls_today": dict(_state["calls_today"]),
        }


def _alert_cooldown_ok(db, now_ts: int | None = None) -> bool:
    """告警节流：距上次告警不足冷却窗口则跳过（判定通过即写入时间戳）。"""
    ts = int(now_ts if now_ts is not None else time_module.time())
    try:
        last_ts = int(str(db.get_setting(_ALERT_COOLDOWN_KEY) or "0"))
    except ValueError:
        last_ts = 0
    if ts - last_ts < ALERT_COOLDOWN_SECONDS:
        return False
    db.set_setting(_ALERT_COOLDOWN_KEY, str(ts))
    return True


def _publish_alert(publish_alert, title: str, content: str) -> None:
    if publish_alert is None:
        return
    try:
        publish_alert(title, content)
    except Exception:  # noqa: BLE001 - 告警失败不影响打标主流程
        logger.exception("MX LLM 打标告警发布失败")


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def validate_batch_response(batch_rows, response, topic_tags, action_tags, valid_stocks):
    """把 tag_posts_llm 的归一结果校验为可写数据。

    返回 (writes, reviews, general_pairs, applied)：
    - writes: {post_id: [最终标签]}——仅收 high 且过词表/名单校验的标签，按
      股票>操作>话题 拼接后截到 POST_TAGS_MAX；LLM 缺失的帖子写空（是否整批
      作废由调用方按 MISSING_RATIO_LIMIT 决定）；
    - reviews: [(post_id, tag, kind)]——low 标签进人工审核（幻觉股票既不写也不审）；
    - general_pairs: [(alias, stock, post_id)]——kind=general 的黑话映射（context/
      typo 在 llm 归一层已保守处理，这里只认 general 且正式名在名单内）；
    - applied: [(post_id, tag, kind)]——与 writes 同口径的 high 直写明细（带类型，
      供写库后登记标签来源）。
    """
    topic_set = {str(t) for t in topic_tags or []}
    action_set = {str(t) for t in action_tags or []}
    writes: dict[int, list[str]] = {}
    reviews: list[tuple[int, str, str]] = []
    general_pairs: list[tuple[str, str, int]] = []
    applied: list[tuple[int, str, str]] = []
    for row in batch_rows:
        pid = int(row["id"])
        result = (response or {}).get(pid)
        if result is None:
            writes[pid] = []
            continue
        stocks = [
            s
            for s in result.get("stocks", [])
            if s.get("official") in valid_stocks
        ]
        stocks_high = _dedupe(
            [s["official"] for s in stocks if s.get("confidence") == "high"]
        )[:POST_STOCK_TAGS_MAX]
        actions_high = _dedupe(
            [
                a["name"]
                for a in result.get("actions", [])
                if a.get("name") in action_set and a.get("confidence") == "high"
            ]
        )[:2]
        topics_high = _dedupe(
            [
                t["name"]
                for t in result.get("topics", [])
                if t.get("name") in topic_set and t.get("confidence") == "high"
            ]
        )[:3]
        high_with_kind = (
            [(t, "stock") for t in stocks_high]
            + [(t, "action") for t in actions_high]
            + [(t, "topic") for t in topics_high]
        )
        writes[pid] = _dedupe([t for t, _ in high_with_kind])[:POST_TAGS_MAX]
        kind_by_tag: dict[str, str] = {}
        for t, kind in high_with_kind:
            kind_by_tag.setdefault(t, kind)
        applied.extend((pid, t, kind_by_tag[t]) for t in writes[pid])
        for stock in stocks:
            if stock.get("confidence") != "high":
                reviews.append((pid, stock["official"], "stock"))
        for action in result.get("actions", []):
            if action.get("name") in action_set and action.get("confidence") != "high":
                reviews.append((pid, action["name"], "action"))
        for topic in result.get("topics", []):
            if topic.get("name") in topic_set and topic.get("confidence") != "high":
                reviews.append((pid, topic["name"], "topic"))
        for jargon in result.get("jargon", []):
            raw = str(jargon.get("raw") or "").strip()
            official = str(jargon.get("official") or "").strip()
            if (
                jargon.get("kind") == "general"
                and raw
                and official in valid_stocks
                and raw != official
            ):
                general_pairs.append((raw, official, pid))
    return writes, reviews, general_pairs, applied


def _record_call(count: int = 1) -> None:
    with _state_lock:
        today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
        if _state["calls_today"].get("date") != today:
            _state["calls_today"] = {"date": today, "count": 0}
        _state["calls_today"]["count"] += count


def _record_run(processed: int, batches: int, failed: bool, error: str = "") -> None:
    with _state_lock:
        _state["last_run"] = {
            "at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "processed": processed,
            "batches": batches,
            "failed": failed,
            "error": error,
        }


def _tag_inputs(db):
    """一次 tick 的词表与名单（每 tick 现取，管理员改词表下一 tick 生效）。"""
    from .stock_universe import aliases_for_tagging, names_for_plain_text_tagging

    tag_rules = db.get_tag_vocabulary()
    topic_tags = [r["tag"] for r in tag_rules]
    action_tags = db.get_action_tag_vocabulary()
    excluded = db.get_stock_name_exclusions()
    names = names_for_plain_text_tagging(db.get_stock_names(), excluded)
    aliases = aliases_for_tagging(db.get_stock_aliases(), excluded)
    valid_stocks = set(names) | {a["stock"] for a in aliases}
    return tag_rules, topic_tags, action_tags, names, aliases, valid_stocks


def run_tag_test(db, llm_config) -> dict:
    """试打标：取最多 10 条未 LLM 打标的 MX 消息（最旧优先），走一遍与手动打标
    完全同源的 LLM 调用与校验，只返回预览结果——不写标签、不进审核/候选表。

    管理端「试打 10 条」按钮用。零写入，与手动任务并行安全（独立 _test_lock，
    只防管理员连点造成并发试打）。
    """
    from .llm import tag_posts_llm
    from .tagging import is_acceptable_alias

    if not _test_lock.acquire(blocking=False):
        logger.info("MX LLM 打标试打跳过：上一次试打仍在进行")
        return {"skipped": "busy"}
    try:
        if not (llm_config and getattr(llm_config, "api_key", "")):
            logger.warning("MX LLM 打标试打跳过：未配置系统 LLM")
            return {"skipped": "no_llm"}
        tag_rules, topic_tags, action_tags, names, aliases, valid_stocks = _tag_inputs(db)
        known_aliases = {a["alias"] for a in aliases}
        rows = db.list_mx_pending_posts(None, TEST_BATCH_SIZE)
        if not rows:
            logger.info("MX LLM 打标试打跳过：暂无未打标消息")
            return {"skipped": "no_posts"}
        logger.info(
            "MX LLM 打标试打开始 取未打标消息 %d 条（id %d..%d）",
            len(rows), int(rows[0]["id"]), int(rows[-1]["id"]),
        )
        response = tag_posts_llm(
            rows, tag_rules, action_tags, names, aliases, llm_config
        )
        _record_call()
        if response is None:
            logger.warning(
                "MX LLM 打标试打失败：LLM 调用失败或输出无效（详见上方 LLM 请求日志）",
            )
            return {"skipped": "llm_failed"}
        writes, reviews, general_pairs, _applied = validate_batch_response(
            rows, response, topic_tags, action_tags, valid_stocks
        )
        pairs = [
            (alias, stock, pid)
            for alias, stock, pid in general_pairs
            if alias not in known_aliases
            and is_acceptable_alias(alias, stock, valid_stocks)
        ]
        items = []
        for row in rows:
            pid = int(row["id"])
            excerpt = " ".join(
                (str(row.get("title") or ""), str(row.get("content") or ""))
            ).strip()[:100]
            existing = set(db.get_post_tags(pid))  # 已在帖上的 low 标签不会进审核
            items.append(
                {
                    "post_id": pid,
                    "kol_name": str(row.get("kol_name") or ""),
                    "excerpt": excerpt,
                    "tags": list(writes.get(pid) or []),
                    "review_tags": [
                        {"tag": tag, "kind": kind}
                        for rp, tag, kind in reviews
                        if rp == pid and tag not in existing
                    ],
                    "jargon": [
                        {"alias": alias, "stock": stock}
                        for alias, stock, rp in pairs
                        if rp == pid
                    ],
                }
            )
        summary = {
            "would_tag": sum(1 for item in items if item["tags"]),
            "would_review": sum(len(item["review_tags"]) for item in items),
            "would_candidates": len({(j["alias"], j["stock"]) for j in (
                j for item in items for j in item["jargon"]
            )}),
        }
        logger.info(
            "MX LLM 打标试打完成 tested=%d 将合并=%d 条 将进审核=%d 个 将入候选=%d 对"
            "（未写库）",
            len(rows), summary["would_tag"],
            summary["would_review"], summary["would_candidates"],
        )
        for item in items:
            logger.info(
                "MX LLM 打标试打 post=%s author=%s 合并=[%s] 审核=[%s] 黑话=[%s] 原文=%.80s",
                item["post_id"],
                item["kol_name"],
                "、".join(item["tags"]) or "无",
                "、".join(t["tag"] for t in item["review_tags"]) or "无",
                "、".join(f"{j['alias']}={j['stock']}" for j in item["jargon"]) or "无",
                item["excerpt"],
            )
        return {
            "tested": len(rows),
            "items": items,
            "summary": summary,
        }
    finally:
        _test_lock.release()


# ---- 手动打标任务（管理端「开始 LLM 打标」：选大V、上限 1000 条、可取消） ----

def _run_snapshot(run: dict) -> dict:
    snap = {k: run[k] for k in _RUN_PUBLIC_FIELDS}
    snap["summary"] = dict(run["summary"]) if run["summary"] else None
    return snap


def get_manual_job_status() -> dict:
    """手动打标进度快照：活跃 run 在前、最近完成的 run 在后（进度轮询用）。

    running = 有 run 处于 running 状态；unfinished = 任一 run 尚未收场
    （全部批次有着落才 finalize）。某批失败会立刻把 run 置 failed，但兄弟批
    可能还在跑——前端轮询应以 unfinished 为准，否则会提前停轮。
    """
    with _runs_lock:
        active = [r for r in _runs.values() if r["status"] == "running"]
        finished = sorted(
            (r for r in _runs.values() if r["status"] != "running"),
            key=lambda r: r["finished_at"] or "",
            reverse=True,
        )
        runs = [_run_snapshot(r) for r in active + finished]
        unfinished = any(r["summary"] is None for r in _runs.values())
    return {
        "running": bool(active),
        "unfinished": unfinished,
        "max_concurrent": MANUAL_MAX_WORKERS,
        "batch_size": MANUAL_BATCH_SIZE_LIMIT,
        "runs": runs,
    }


def request_cancel_manual_run(run_id: int | None = None) -> int:
    """请求取消手动打标 run（run_id=None 取消全部）：当前批次完成后停止，
    排队批次直接跳过。返回被取消的 run 数。"""
    with _runs_lock:
        targets = [
            r for r in _runs.values()
            if r["status"] == "running" and (run_id is None or r["run_id"] == run_id)
        ]
        for r in targets:
            r["cancel_requested"] = True
    if targets:
        logger.info(
            "MX 手动打标收到取消请求 runs=%s，当前批次完成后停止",
            [r["run_id"] for r in targets],
        )
    return len(targets)


def start_manual_run(db, llm_config, kol_ids: list[int], max_messages: int) -> dict:
    """创建一次手动打标 run：取待打标消息切成每批 ≤100 条入队后立即返回。

    max_messages ≤ 0 表示不限量（打完所选大V的全部待打标消息）。
    """
    return start_run(db, llm_config, kol_ids, max_messages, source="manual")


def start_run(
    db, llm_config, kol_ids: list[int] | None, max_messages: int, source: str = "manual"
) -> dict:
    """创建一次打标 run：取待打标消息切成每批 ≤100 条入队后立即返回。

    kol_ids=None 不限大V（自动打标）；否则只取指定大V（手动打标）。消息数按
    max_messages 截取（≤0 不限量），最旧优先；进行中 run
    已认领的消息不重复认领（两次选择的大V有重叠时后者顺延取剩余）。已有 run
    在跑时新 run 照常入队排队，不再拒绝。返回 started=False 时带原因。
    """
    global _run_seq
    if not (llm_config and getattr(llm_config, "api_key", "")):
        return {"started": False, "reason": "no_llm"}
    if kol_ids is not None:
        kol_ids = [int(kid) for kid in kol_ids]
    max_messages = max(0, int(max_messages or 0))
    batch_size = min(
        max(db.get_mx_llm_tag_int_setting(MX_LLM_TAG_BATCH_SIZE_KEY, MANUAL_BATCH_SIZE_LIMIT), 1),
        MANUAL_BATCH_SIZE_LIMIT,
    )
    with _runs_lock:
        # 多取 len(_claimed_ids) 条兜底：其中可能混有已被进行中 run 认领的消息，
        # 过滤后仍够 max_messages 条（不限量时无此顾虑，直接全取再过滤）
        fetch_limit = (max_messages + len(_claimed_ids)) if max_messages else 0
        rows = db.list_mx_pending_posts(kol_ids, fetch_limit)
        rows = [r for r in rows if int(r["id"]) not in _claimed_ids]
        if max_messages:
            rows = rows[:max_messages]
        if not rows:
            return {"started": False, "reason": "no_posts"}
        kol_set = set(kol_ids or [])
        kols = [k["name"] for k in db.list_kols(platform="mx") if k["id"] in kol_set]
        tag_rules, topic_tags, action_tags, names, aliases, valid_stocks = _tag_inputs(db)
        known_aliases = {a["alias"] for a in aliases}
        _run_seq += 1
        rid = _run_seq
        chunks = [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]
        _runs[rid] = {
            "run_id": rid,
            "source": source,  # manual=管理端手动触发 auto=时间段自动触发
            "kols": kols,
            "status": "running",  # running | done | cancelled | failed
            "cancel_requested": False,
            "total": len(rows),
            "processed": 0,
            "batch_total": len(chunks),
            "batches_done": 0,
            "batches_failed": 0,
            "batches_skipped": 0,
            "batches_running": 0,
            "error": "",
            "tagged_posts": 0,
            "reviews": 0,
            "candidates": 0,
            "claimed_ids": {int(r["id"]) for r in rows},
            "started_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": None,
            "summary": None,
        }
        _claimed_ids.update(int(r["id"]) for r in rows)
        for chunk in chunks:
            _queue.append({
                "run_id": rid, "rows": chunk, "db": db, "llm_config": llm_config,
                "tag_rules": tag_rules, "topic_tags": topic_tags,
                "action_tags": action_tags, "names": names, "aliases": aliases,
                "valid_stocks": valid_stocks, "known_aliases": known_aliases,
            })
        _ensure_workers_locked()
    logger.info(
        "MX 手动打标任务已入队 run=%d kols=%s 消息 %d 条分 %d 批（每批≤%d，同时打标≤%d）",
        rid, kols, len(rows), len(chunks), batch_size, MANUAL_MAX_WORKERS,
    )
    return {
        "started": True, "run_id": rid, "total": len(rows),
        "batches": len(chunks), "batch_size": batch_size,
    }


def _ensure_workers_locked() -> None:
    """补足工作线程到 MANUAL_MAX_WORKERS（须持有 _runs_lock；测试替换为空操作）。"""
    global _workers
    while _workers < MANUAL_MAX_WORKERS:
        _workers += 1
        threading.Thread(
            target=_worker_loop, name=f"mx-llm-tag-worker-{_workers}", daemon=True,
        ).start()


def _worker_loop() -> None:
    global _workers
    while True:
        with _runs_lock:
            if not _queue:
                _workers -= 1
                return
            item = _queue.popleft()
        _run_batch_item(item)


def _drain_manual_queue() -> None:
    """同步排空队列（测试用；线上由 _worker_loop 消费）。"""
    while True:
        with _runs_lock:
            if not _queue:
                return
            item = _queue.popleft()
        _run_batch_item(item)


def _run_batch_item(item: dict) -> None:
    """处理一个批次：调 LLM、校验、与已有标签去重合并写库，更新 run 进度。

    run 已取消/已提前收场时本批直接记为跳过；LLM 失败或批次异常则收场所在
    run，剩余排队批次随出队逐个跳过（未处理消息保持未打标，可直接重试）。
    """
    from .llm import tag_posts_llm
    from .tagging import is_acceptable_alias

    chunk = item["rows"]
    db = item["db"]
    with _runs_lock:
        run = _runs[item["run_id"]]
        if run["status"] != "running" or run["cancel_requested"]:
            run["batches_skipped"] += 1
            _maybe_finalize_run_locked(run)
            logger.info(
                "MX 手动打标 run=%s 批次跳过（%s）",
                run["run_id"], "已取消" if run["cancel_requested"] else "任务已提前收场",
            )
            return
        run["batches_running"] += 1
    try:
        response = tag_posts_llm(
            chunk, item["tag_rules"], item["action_tags"], item["names"],
            item["aliases"], item["llm_config"],
        )
        _record_call()
        error = ""
        if response is None:
            error = "LLM 调用失败或输出无效"
        else:
            missing = len(chunk) - len(response)
            if chunk and missing / len(chunk) > MISSING_RATIO_LIMIT:
                error = f"LLM 响应缺失 {missing}/{len(chunk)} 条"
        if error:
            with _runs_lock:
                run["batches_failed"] += 1
                run["error"] = error
                run["status"] = "failed"
                run["batches_running"] -= 1
                _maybe_finalize_run_locked(run)
            logger.warning(
                "MX 手动打标 run=%s 批次失败：%s（剩余批次跳过，未处理消息保持未打标）",
                run["run_id"], error,
            )
            return
        writes, reviews, general_pairs, applied = validate_batch_response(
            chunk, response, item["topic_tags"], item["action_tags"], item["valid_stocks"],
        )
        for pid, tags in writes.items():
            # 与已有标签去重合并：本地规则打的标签保留
            known = set(db.get_post_tags(pid))
            db.merge_post_tags_llm(pid, tags)
            # LLM 实际新写入的标签登记来源（applied），供查看弹窗区分
            applied_kinds = {t: k for p2, t, k in applied if p2 == pid}
            for tag in tags:
                if tag not in known:
                    db.record_llm_applied_tag(pid, tag, applied_kinds.get(tag, ""))
        review_logged = 0
        for pid, tag, kind in reviews:
            # 标签已在帖上（本地规则标签保留在合并结果里）时不登记，按实际登记计数
            if db.add_pending_tag_review(pid, tag, kind, "low"):
                review_logged += 1
        pairs = [
            (alias, stock, pid)
            for alias, stock, pid in general_pairs
            if alias not in item["known_aliases"]
            and is_acceptable_alias(alias, stock, item["valid_stocks"])
        ]
        if pairs:
            db.merge_stock_alias_candidates(pairs)
        tagged = sum(1 for t in writes.values() if t)
        with _runs_lock:
            run["batches_done"] += 1
            run["processed"] += len(chunk)
            run["tagged_posts"] += tagged
            run["reviews"] += review_logged
            run["candidates"] += len(pairs)
            run["batches_running"] -= 1
            _maybe_finalize_run_locked(run)
        logger.info(
            "MX 手动打标 run=%s 批次完成 posts=%d 合并标签=%d 进审核=%d 黑话候选=%d 进度 %d/%d",
            run["run_id"], len(chunk), tagged, review_logged, len(pairs),
            run["processed"], run["total"],
        )
    except Exception as exc:  # noqa: BLE001 - 批次异常收场所在 run，不影响服务
        with _runs_lock:
            run["batches_failed"] += 1
            run["error"] = f"{type(exc).__name__}: {exc}"
            run["status"] = "failed"
            run["batches_running"] -= 1
            _maybe_finalize_run_locked(run)
        logger.exception("MX 手动打标 run=%s 批次异常", run["run_id"])


def _maybe_finalize_run_locked(run: dict) -> None:
    """run 的全部批次都有着落（完成/失败/跳过）时收场（须持有 _runs_lock）。"""
    settled = run["batches_done"] + run["batches_failed"] + run["batches_skipped"]
    if settled < run["batch_total"] or run["summary"]:
        return
    if run["status"] == "running":
        run["status"] = "cancelled" if run["cancel_requested"] else "done"
    run["finished_at"] = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    run["summary"] = {
        "total": run["total"],
        "processed": run["processed"],
        "tagged_posts": run["tagged_posts"],
        "reviews": run["reviews"],
        "candidates": run["candidates"],
        "failed_batches": run["batches_failed"],
        "cancelled": run["status"] == "cancelled",
        "error": run["error"],
    }
    _claimed_ids.difference_update(run["claimed_ids"])
    _record_run(run["processed"], run["batches_done"], run["status"] == "failed", run["error"])
    # 只保留最近若干个已完成 run，防状态表与认领集合无限增长
    finished = sorted(
        (r for r in _runs.values() if r["status"] != "running"),
        key=lambda r: r["finished_at"] or "",
        reverse=True,
    )
    for old in finished[_FINISHED_RUNS_KEEP:]:
        _runs.pop(old["run_id"], None)
    logger.info(
        "MX 手动打标 run=%s 结束 status=%s processed=%d/%d 合并标签帖=%d 审核=%d "
        "候选=%d 失败批=%d 跳过批=%d",
        run["run_id"], run["status"], run["processed"], run["total"],
        run["tagged_posts"], run["reviews"], run["candidates"],
        run["batches_failed"], run["batches_skipped"],
    )


# ---- 自动打标（时间段触发：常规 + 特殊时段，条数/间隔双维度） ----

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _hm_to_minutes(value) -> int | None:
    """HH:MM → 当日分钟数；格式非法返回 None。"""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not _TIME_RE.match(value):
        return None
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _normalize_period(raw) -> tuple[dict | None, str]:
    """校验单个时间段配置，返回 (规范化配置, 错误信息)。"""
    if not isinstance(raw, dict):
        return None, "时间段配置格式错误"
    start = _hm_to_minutes(raw.get("start"))
    end = _hm_to_minutes(raw.get("end"))
    if start is None or end is None:
        return None, "时间格式需为 HH:MM（如 09:15）"
    if start >= end:
        return None, "开始时间必须早于结束时间"
    try:
        threshold = int(raw.get("threshold"))
        interval = int(raw.get("interval_minutes"))
    except (TypeError, ValueError):
        return None, "触发条数与间隔分钟需为整数"
    if not 1 <= threshold <= AUTO_THRESHOLD_MAX:
        return None, f"触发条数需在 1-{AUTO_THRESHOLD_MAX} 之间"
    if not AUTO_INTERVAL_MIN <= interval <= AUTO_INTERVAL_MAX:
        return None, f"间隔分钟需在 {AUTO_INTERVAL_MIN}-{AUTO_INTERVAL_MAX} 之间"
    return {
        "name": str(raw.get("name") or "").strip()[:30],
        "start": str(raw.get("start")).strip(),
        "end": str(raw.get("end")).strip(),
        "threshold": threshold,
        "interval_minutes": interval,
    }, ""


def normalize_auto_config(raw) -> tuple[dict | None, str]:
    """校验并规范化自动打标配置，返回 (配置, 错误信息)；错误时配置为 None。

    常规时间段必填；特殊时间段可选、最多 AUTO_MAX_SPECIALS 个。
    """
    raw = raw if isinstance(raw, dict) else {}
    regular, err = _normalize_period(raw.get("regular"))
    if err:
        return None, f"常规时间段：{err}"
    raw_specials = raw.get("specials")
    raw_specials = raw_specials if isinstance(raw_specials, list) else []
    if len(raw_specials) > AUTO_MAX_SPECIALS:
        return None, f"特殊时间段最多 {AUTO_MAX_SPECIALS} 个"
    specials: list[dict] = []
    for idx, sp in enumerate(raw_specials):
        period, err = _normalize_period(sp)
        if err:
            return None, f"特殊时间段第 {idx + 1} 个：{err}"
        specials.append(period)
    return {"enabled": bool(raw.get("enabled")), "regular": regular, "specials": specials}, ""


def resolve_auto_period(cfg: dict, now: datetime) -> dict | None:
    """当前时刻命中的时间段配置：特殊优先（按配置顺序），其余用常规。

    时段含端点（按分钟判等，23:59 即覆盖到当日 23:59:59）；都不命中返回 None。
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=CN_TZ)
    now = now.astimezone(CN_TZ)
    minutes = now.hour * 60 + now.minute
    candidates = [("special", p) for p in cfg.get("specials") or []]
    if cfg.get("regular"):
        candidates.append(("regular", cfg["regular"]))
    for kind, period in candidates:
        if _hm_to_minutes(period["start"]) <= minutes <= _hm_to_minutes(period["end"]):
            resolved = dict(period)
            resolved["kind"] = kind
            return resolved
    return None


def save_auto_config(db, raw) -> tuple[dict | None, str]:
    """校验并保存自动打标配置，按开关变化重置触发布防。

    刚开启：条数从当前消息起算、计时清零（下一轮检查即评估首轮触发）；
    已开启改配置：保留间隔计时连续性，仅把条数水位推进到当前消息。
    """
    clean, err = normalize_auto_config(raw)
    if err:
        return None, err
    prev = db.get_mx_llm_tag_auto_config()
    was_enabled = bool(isinstance(prev, dict) and prev.get("enabled"))
    db.set_mx_llm_tag_auto_config(clean)
    fresh_enable = clean["enabled"] and not was_enabled
    with _auto_state_lock:
        keep_ts = _auto_state["last_trigger_ts"] if clean["enabled"] and not fresh_enable else None
        _auto_state.update(
            armed=clean["enabled"],
            watermark=db.max_mx_post_id(),
            last_trigger_ts=keep_ts,
        )
    logger.info(
        "MX 自动打标配置已保存 enabled=%s 常规=%s-%s 特殊=%d 个",
        clean["enabled"], clean["regular"]["start"], clean["regular"]["end"],
        len(clean["specials"]),
    )
    return clean, ""


def get_auto_status(db) -> dict:
    """自动打标配置与触发状态快照（管理端状态面板用）。"""
    cfg, _err = normalize_auto_config(db.get_mx_llm_tag_auto_config())
    if cfg is None:  # 存量数据损坏时兜底为关闭态，避免面板崩掉
        cfg = {"enabled": False, "regular": None, "specials": []}
    now = datetime.now(CN_TZ)
    period = resolve_auto_period(cfg, now) if cfg["enabled"] else None
    with _auto_state_lock:
        armed = _auto_state["armed"]
        watermark = _auto_state["watermark"]
        last_ts = _auto_state["last_trigger_ts"]
    new_since = db.count_mx_new_since(watermark)[0] if cfg["enabled"] else 0
    interval_due_at = None
    if period and last_ts:
        due = datetime.fromtimestamp(last_ts, CN_TZ) + timedelta(
            minutes=period["interval_minutes"]
        )
        interval_due_at = due.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "enabled": cfg["enabled"],
        "regular": cfg["regular"],
        "specials": cfg["specials"],
        "active_period": period,
        "armed": armed and cfg["enabled"],
        "last_trigger_at": (
            datetime.fromtimestamp(last_ts, CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
            if last_ts
            else None
        ),
        "new_since_trigger": new_since,
        "interval_due_at": interval_due_at,
    }


def _auto_update_alerts(db, publish_alert) -> None:
    """核对新结束的自动任务，维护连续失败告警（任一成功且无失败即恢复）。"""
    runs = get_manual_job_status()["runs"]
    finished = [
        r for r in runs
        if r["source"] == "auto" and r["status"] != "running"
        and r["run_id"] not in _auto_alert_seen
    ]
    if not finished:
        return
    failed_runs = 0
    succeeded = False
    last_error = ""
    for run in finished:
        _auto_alert_seen.add(run["run_id"])
        summary = run["summary"] or {}
        if run["status"] == "failed" or summary.get("failed_batches"):
            failed_runs += 1
            last_error = summary.get("error") or "打标任务失败"
        elif summary.get("processed"):
            succeeded = True
    recovered = False
    with _state_lock:
        if failed_runs:
            _state["consecutive_failures"] += failed_runs
        elif succeeded:
            recovered = _state["alert_active"] or _state["consecutive_failures"] > 0
            _state["alert_active"] = False
            _state["consecutive_failures"] = 0
        failures = _state["consecutive_failures"]
        alert_due = bool(failed_runs) and failures >= ALERT_FAIL_THRESHOLD
    # 告警链路含 DB 读写与系统通知推送，放在状态锁外：get_tagger_status 供
    # 管理端轮询，不能被推送网络 IO 卡住。
    if recovered:
        _publish_alert(publish_alert, "MX LLM 打标已恢复", "自动打标已恢复正常。")
    elif alert_due and _alert_cooldown_ok(db):
        _publish_alert(
            publish_alert,
            f"MX LLM 打标连续失败 {failures} 次",
            "⚠️ MX 实时消息自动 LLM 打标连续失败。\n"
            f"最近错误：{last_error or '未知'}\n"
            "请检查系统 LLM 配置（管理员推送设置里的 API Key/模型）与额度。",
        )
        with _state_lock:
            _state["alert_active"] = True


def _auto_check(db, llm_config_provider, publish_alert=None) -> dict:
    """自动打标单次检查：命中时段且有待打标消息，且条数达阈值或间隔已到，
    且当前没有排队/打标中的自动任务时，入队一个自动打标任务。

    触发后水位推进到当前新消息、间隔计时重新起算——两个维度因此互相重置。
    """
    _auto_update_alerts(db, publish_alert)
    cfg, _err = normalize_auto_config(db.get_mx_llm_tag_auto_config())
    if cfg is None or not cfg["enabled"]:
        with _auto_state_lock:
            _auto_state["armed"] = False
        return {"skipped": "disabled"}
    period = resolve_auto_period(cfg, datetime.now(CN_TZ))
    if period is None:
        return {"skipped": "out_of_period"}
    llm_config = llm_config_provider()
    if not (llm_config and getattr(llm_config, "api_key", "")):
        return {"skipped": "no_llm"}
    with _auto_state_lock:
        if not _auto_state["armed"]:
            # 布防：条数从当前消息起算；last_trigger_ts=None 让首轮触发
            # （有待打标消息时）立即评估通过
            _auto_state.update(armed=True, watermark=db.max_mx_post_id(), last_trigger_ts=None)
    if any(
        r["source"] == "auto" and r["status"] == "running"
        for r in get_manual_job_status()["runs"]
    ):
        return {"skipped": "auto_run_active"}
    if db.count_mx_pending_total() == 0:
        with _auto_state_lock:
            _auto_state["watermark"] = db.max_mx_post_id()
        return {"skipped": "no_pending"}
    now_ts = time_module.time()
    with _auto_state_lock:
        watermark = _auto_state["watermark"]
        last_ts = _auto_state["last_trigger_ts"]
    new_count, max_id = db.count_mx_new_since(watermark)
    interval_due = last_ts is None or now_ts - last_ts >= period["interval_minutes"] * 60
    if new_count < period["threshold"] and not interval_due:
        return {"skipped": "not_due"}
    reason = (
        f"新消息达 {new_count}/{period['threshold']} 条" if new_count >= period["threshold"]
        else "到达间隔触发点"
    )
    result = start_run(db, llm_config, None, AUTO_RUN_MAX_MESSAGES, source="auto")
    if not result["started"]:
        logger.info("MX 自动打标触发未成任务：%s（%s）", reason, result["reason"])
        return {"skipped": result["reason"]}
    with _auto_state_lock:
        _auto_state.update(watermark=max_id, last_trigger_ts=now_ts)
    logger.info(
        "MX 自动打标已触发（%s，%s 时段）run=%d 消息 %d 条分 %d 批",
        reason, "特殊" if period["kind"] == "special" else "常规",
        result["run_id"], result["total"], result["batches"],
    )
    return {"triggered": True, "reason": reason, "run_id": result["run_id"]}


async def mx_llm_tag_auto_loop(db, llm_config_provider, publish_alert=None) -> None:
    """自动打标常驻循环：每 AUTO_POLL_SECONDS 秒检查一次是否触发。

    开关与时段配置每轮现读，改配置无需重启。provider 取配置含同步 DB 查询/
    解密，与检查一起放进线程执行，不阻塞共享给 API 的事件循环。
    """
    logger.info("MX LLM 打标自动循环已启动（每 %d 秒检查一次）", AUTO_POLL_SECONDS)
    while True:
        try:
            await asyncio.sleep(AUTO_POLL_SECONDS)
            await asyncio.to_thread(_auto_check, db, llm_config_provider, publish_alert)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 单轮检查异常不终止循环
            logger.exception("MX LLM 打标自动检查异常")
