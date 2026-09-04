"""MX 消息的 LLM 打标（当前为全手动模式）。

手动打标（start_manual_job，管理端「开始 LLM 打标」）：
- 弹窗选 MX 大V（显示各自未打标消息数），一次最多处理 1000 条；
- 后台线程分批调 LLM（批大小取 settings），按 llm_tagged=0 选帖（blocked/hidden
  不算，最旧优先），逐批更新进度，可取消；
- 结果与帖子已有标签**去重合并**（不再整体替换），low 进 post_tag_reviews 人工
  审核（标签已在帖上的不进——通过与否它都已在帖），kind=general 黑话经
  is_acceptable_alias 预过滤后进候选表。

自动触发（mx_llm_tag_loop）暂停：原开盘时段调度保留代码，scheduler 按设置
mx_llm_tag_auto_enabled（默认关）决定是否启动，后续恢复自动模式时重开。

试打（run_tag_test）：取 10 条未打标消息走同源调用与校验，零写入，供调参预览。

连续失败告警逻辑仅自动模式使用；手动模式失败直接体现在任务进度里。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time as time_module
from datetime import date, datetime, time, timedelta, timezone

from .db import (
    MX_LLM_TAG_BATCH_SIZE_KEY,
    MX_LLM_TAG_MAX_CALLS_KEY,
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
# 手动打标一次最多处理的消息条数
MAX_MANUAL_MESSAGES = 1000

# 运行状态（进程内计数，重启归零）：供管理端状态面板展示
_state_lock = threading.Lock()
_state: dict = {
    "consecutive_failures": 0,
    "alert_active": False,
    "last_run": None,
    "calls_today": {"date": "", "count": 0},
    # 正式 tick 进行中的 monotonic 起始时刻（None=空闲），供面板/试打提示展示
    "tick_started_at": None,
}

# 单飞锁：LLM 单批最长 180s，分钟级触发点可能撞上未结束的上一轮
_tick_lock = threading.Lock()
# 试打专用锁：试打零写入（不写标签/审核/候选、不推游标），与正式 tick 并行
# 是安全的——不与 _tick_lock 互斥，否则开盘时段 tick 连续持锁（每批 LLM 最长
# 6 分钟、单 tick 最多 5 批），「试打 10 条」会长时间 409 无法诊断
_test_lock = threading.Lock()

# 手动打标任务：同一时刻只跑一个（单飞），状态供管理端进度轮询
_job_lock = threading.Lock()
_job_state_lock = threading.Lock()
_job_state: dict = {
    "running": False,
    "cancel_requested": False,
    "started_at": None,
    "finished_at": None,
    "kols": [],
    "total": 0,
    "processed": 0,
    "batches": 0,
    "failed_batches": 0,
    "error": "",
    "summary": None,
}


def get_tagger_status() -> dict:
    """管理端状态面板用的运行快照（内存计数）。"""
    with _state_lock:
        started = _state["tick_started_at"]
        return {
            "consecutive_failures": _state["consecutive_failures"],
            "alert_active": _state["alert_active"],
            "last_run": dict(_state["last_run"]) if _state["last_run"] else None,
            "calls_today": dict(_state["calls_today"]),
            "tick_running": started is not None,
            "tick_running_seconds": (
                int(time_module.time() - started) if started is not None else 0
            ),
        }


def _day_ticks(day: date) -> list[datetime]:
    """某天（本地日期）的全部触发时刻，升序。

    工作日：09:00-10:29 每分钟 + 10:30-15:05 每五分钟 + 18:00/23:00 集中点；
    周末：09/12/15/18/20/23 点集中。
    """
    ticks: list[datetime] = []
    if day.weekday() < 5:  # 周一=0 … 周五=4
        tick = datetime.combine(day, time(9, 0), tzinfo=CN_TZ)
        end = datetime.combine(day, time(10, 29), tzinfo=CN_TZ)
        while tick <= end:
            ticks.append(tick)
            tick += timedelta(minutes=1)
        tick = datetime.combine(day, time(10, 30), tzinfo=CN_TZ)
        end = datetime.combine(day, time(15, 5), tzinfo=CN_TZ)
        while tick <= end:
            ticks.append(tick)
            tick += timedelta(minutes=5)
        ticks.append(datetime.combine(day, time(18, 0), tzinfo=CN_TZ))
        ticks.append(datetime.combine(day, time(23, 0), tzinfo=CN_TZ))
    else:
        for hour in (9, 12, 15, 18, 20, 23):
            ticks.append(datetime.combine(day, time(hour, 0), tzinfo=CN_TZ))
    return sorted(ticks)


def next_due_tick(now: datetime) -> datetime:
    """下一个应触发的时刻（严格晚于 now）。naive 输入按北京时间理解。"""
    if now.tzinfo is None:
        now = now.replace(tzinfo=CN_TZ)
    now_local = now.astimezone(CN_TZ)
    day = now_local.date()
    for _ in range(8):  # 全周每天都有触发点，1 天必然命中；8 是防御上限
        for tick in _day_ticks(day):
            if tick > now_local:
                return tick
        day = date.fromordinal(day.toordinal() + 1)
    raise RuntimeError("unreachable: no due tick within a week")


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


def run_tag_tick(db, llm_config, publish_alert=None) -> dict:
    """执行一次打标 tick：从游标处排空积压（最多 max_calls_per_tick 批）。

    返回运行摘要；被跳过时返回 {"skipped": 原因}。
    """
    if not _tick_lock.acquire(blocking=False):
        return {"skipped": "busy"}
    with _state_lock:
        _state["tick_started_at"] = time_module.time()
    try:
        return _run_tag_tick_locked(db, llm_config, publish_alert)
    finally:
        with _state_lock:
            _state["tick_started_at"] = None
        _tick_lock.release()


def _run_tag_tick_locked(db, llm_config, publish_alert) -> dict:
    from .llm import tag_posts_llm
    from .tagging import is_acceptable_alias

    if not db.get_mx_llm_tag_enabled():
        # 开关关闭/未配 LLM 属常态：每个触发点都会走一次，DEBUG 防刷屏
        logger.debug("MX LLM 打标 tick 跳过：开关已关闭")
        return {"skipped": "disabled"}
    if not (llm_config and getattr(llm_config, "api_key", "")):
        logger.debug("MX LLM 打标 tick 跳过：未配置系统 LLM")
        return {"skipped": "no_llm"}

    batch_size = min(
        max(db.get_mx_llm_tag_int_setting(MX_LLM_TAG_BATCH_SIZE_KEY, 300), 1), 1000
    )
    max_calls = min(
        max(db.get_mx_llm_tag_int_setting(MX_LLM_TAG_MAX_CALLS_KEY, 5), 1), 20
    )
    tag_rules, topic_tags, action_tags, names, aliases, valid_stocks = _tag_inputs(db)
    known_aliases = {a["alias"] for a in aliases}

    cursor = db.get_mx_llm_tag_cursor()
    processed = 0
    batches = 0
    failed_batches = 0
    last_error = ""
    rows = db.list_mx_posts_after(cursor, batch_size)
    while rows and batches < max_calls:
        response = tag_posts_llm(
            rows, tag_rules, action_tags, names, aliases, llm_config
        )
        _record_call()
        if response is None:
            failed_batches += 1
            last_error = "LLM 调用失败或输出无效"
            logger.warning(
                "MX LLM 打标批次 #%d 失败：%s（游标保持 %d，下个触发点重试）",
                batches + 1, last_error, cursor,
            )
            break
        missing = len(rows) - len(response)
        if len(rows) and missing / len(rows) > MISSING_RATIO_LIMIT:
            failed_batches += 1
            last_error = f"LLM 响应缺失 {missing}/{len(rows)} 条"
            logger.warning(
                "MX LLM 打标批次 #%d 失败：%s（游标保持 %d，下个触发点重试）",
                batches + 1, last_error, cursor,
            )
            break
        writes, reviews, general_pairs, _applied = validate_batch_response(
            rows, response, topic_tags, action_tags, valid_stocks
        )
        for pid, tags in writes.items():
            db.update_post_tags_llm(pid, tags)
        review_logged = 0
        for pid, tag, kind in reviews:
            # 标签已在帖上（如规则标签）时登记会被跳过，按实际登记计数
            if db.add_pending_tag_review(pid, tag, kind, "low"):
                review_logged += 1
        pairs = [
            (alias, stock, pid)
            for alias, stock, pid in general_pairs
            if alias not in known_aliases
            and is_acceptable_alias(alias, stock, valid_stocks)
        ]
        if pairs:
            db.merge_stock_alias_candidates(pairs)
        cursor = max(int(r["id"]) for r in rows)
        db.set_mx_llm_tag_cursor(cursor)
        processed += len(rows)
        batches += 1
        logger.info(
            "MX LLM 打标批次 #%d 完成 posts=%d 写入标签=%d 进审核=%d 黑话候选=%d 游标→%d",
            batches, len(rows), sum(1 for t in writes.values() if t),
            review_logged, len(pairs), cursor,
        )
        rows = db.list_mx_posts_after(cursor, batch_size)

    recovered = False
    alert_due = False
    failures = 0
    with _state_lock:
        if batches:
            recovered = _state["alert_active"]
            _state["alert_active"] = False
            _state["consecutive_failures"] = 0
        else:
            _state["consecutive_failures"] += failed_batches
            failures = _state["consecutive_failures"]
            # 仅真实失败的 tick 才触发告警判定：空转 tick（无积压）不得凭
            # 历史失败计数误报
            alert_due = bool(failed_batches) and failures >= ALERT_FAIL_THRESHOLD

    # 告警链路含 DB 读写（冷却时间戳）与系统通知入库推送，放在状态锁外：
    # get_tagger_status 供管理端轮询，不能被推送网络 IO 卡住。
    # 同一时刻只有一个 tick 在跑（_tick_lock 单飞），锁外读写的串行性不受影响。
    if recovered:
        _publish_alert(
            publish_alert,
            "MX LLM 打标已恢复",
            f"本次处理 {processed} 条消息，打标已恢复正常。",
        )
    elif alert_due and _alert_cooldown_ok(db):
        _publish_alert(
            publish_alert,
            f"MX LLM 打标连续失败 {failures} 次",
            "⚠️ MX 实时消息 LLM 打标连续失败，暂停重试至下个触发点。\n"
            f"最近错误：{last_error or '未知'}\n"
            "请检查系统 LLM 配置（管理员推送设置里的 API Key/模型）与额度。",
        )
        with _state_lock:
            _state["alert_active"] = True

    _record_run(processed, batches, failed_batches > 0, last_error)
    logger.info(
        "MX LLM 打标 tick 完成 processed=%d batches=%d failed=%d cursor=%d",
        processed, batches, failed_batches, cursor,
    )
    return {
        "processed": processed,
        "batches": batches,
        "failed_batches": failed_batches,
        "error": last_error,
        "cursor": cursor,
    }


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

def get_manual_job_status() -> dict:
    """手动打标任务状态快照（进度轮询用）。"""
    with _job_state_lock:
        return {k: (dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v))
                for k, v in _job_state.items()}


def request_cancel_manual_job() -> bool:
    """请求取消正在跑的手动任务（当前批次完成后停止）。返回是否有任务在跑。"""
    with _job_state_lock:
        if not _job_state["running"]:
            return False
        _job_state["cancel_requested"] = True
    logger.info("MX 手动打标收到取消请求，当前批次完成后停止")
    return True


def start_manual_job(db, llm_config, kol_ids: list[int], max_messages: int) -> dict:
    """启动一次手动打标后台任务；已有任务在跑时返回 started=False。

    消息数按 max_messages（服务端硬顶 MAX_MANUAL_MESSAGES）截取，最旧优先。
    """
    if not _job_lock.acquire(blocking=False):
        return {"started": False, "reason": "busy"}
    if not (llm_config and getattr(llm_config, "api_key", "")):
        _job_lock.release()
        return {"started": False, "reason": "no_llm"}
    kol_ids = [int(kid) for kid in (kol_ids or [])]
    max_messages = max(1, min(int(max_messages or MAX_MANUAL_MESSAGES), MAX_MANUAL_MESSAGES))
    kols = [k["name"] for k in db.list_kols(platform="mx") if k["id"] in set(kol_ids)]
    with _job_state_lock:
        _job_state.update(
            running=True, cancel_requested=False, started_at=datetime.now(CN_TZ).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            finished_at=None, kols=kols, total=0, processed=0, batches=0,
            failed_batches=0, error="", summary=None,
        )
    threading.Thread(
        target=_run_manual_job, args=(db, llm_config, kol_ids, max_messages),
        name="mx-llm-tag-manual", daemon=True,
    ).start()
    logger.info(
        "MX 手动打标任务已启动 kols=%d max_messages=%d", len(kol_ids), max_messages
    )
    return {"started": True}


def _run_manual_job(db, llm_config, kol_ids: list[int], max_messages: int) -> None:
    """手动打标任务主体（后台线程）：分批调 LLM，结果与已有标签去重合并。"""
    from .llm import tag_posts_llm
    from .tagging import is_acceptable_alias

    total = processed = batches = failed = tagged_posts = review_count = 0
    candidate_count = 0
    error = ""
    cancelled = False
    try:
        rows = db.list_mx_pending_posts(kol_ids, max_messages)
        total = len(rows)
        with _job_state_lock:
            _job_state["total"] = total
        if not total:
            logger.info("MX 手动打标任务：所选大V暂无未打标消息")
            return
        batch_size = min(
            max(db.get_mx_llm_tag_int_setting(MX_LLM_TAG_BATCH_SIZE_KEY, 300), 1), 1000
        )
        tag_rules, topic_tags, action_tags, names, aliases, valid_stocks = _tag_inputs(db)
        known_aliases = {a["alias"] for a in aliases}
        logger.info(
            "MX 手动打标任务开始 kols=%s 未打标消息 %d 条（id %d..%d）",
            _job_state["kols"], total, int(rows[0]["id"]), int(rows[-1]["id"]),
        )
        for start in range(0, total, batch_size):
            with _job_state_lock:
                cancelled = _job_state["cancel_requested"]
            if cancelled:
                logger.info("MX 手动打标任务：已取消（已处理 %d/%d）", processed, total)
                break
            chunk = rows[start:start + batch_size]
            response = tag_posts_llm(
                chunk, tag_rules, action_tags, names, aliases, llm_config
            )
            _record_call()
            if response is None:
                failed += 1
                error = "LLM 调用失败或输出无效"
                logger.warning(
                    "MX 手动打标批次 #%d 失败：%s（剩余消息保持未打标，可直接重试）",
                    batches + 1, error,
                )
                break
            missing = len(chunk) - len(response)
            if chunk and missing / len(chunk) > MISSING_RATIO_LIMIT:
                failed += 1
                error = f"LLM 响应缺失 {missing}/{len(chunk)} 条"
                logger.warning(
                    "MX 手动打标批次 #%d 失败：%s（剩余消息保持未打标，可直接重试）",
                    batches + 1, error,
                )
                break
            writes, reviews, general_pairs, applied = validate_batch_response(
                chunk, response, topic_tags, action_tags, valid_stocks
            )
            for pid, tags in writes.items():
                # 与已有标签去重合并（不再是整体替换）：本地规则打的标签保留
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
                    review_count += 1
            pairs = [
                (alias, stock, pid)
                for alias, stock, pid in general_pairs
                if alias not in known_aliases
                and is_acceptable_alias(alias, stock, valid_stocks)
            ]
            if pairs:
                db.merge_stock_alias_candidates(pairs)
            tagged_posts += sum(1 for t in writes.values() if t)
            candidate_count += len(pairs)
            processed += len(chunk)
            batches += 1
            with _job_state_lock:
                _job_state.update(processed=processed, batches=batches,
                                  failed_batches=failed)
            logger.info(
                "MX 手动打标批次 #%d 完成 posts=%d 合并标签=%d 进审核=%d 黑话候选=%d 进度 %d/%d",
                batches, len(chunk), sum(1 for t in writes.values() if t),
                review_logged, len(pairs), processed, total,
            )
    except Exception as exc:  # noqa: BLE001 - 任务异常体现在进度里，不影响服务
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("MX 手动打标任务异常")
    finally:
        summary = {
            "total": total,
            "processed": processed,
            "tagged_posts": tagged_posts,
            "reviews": review_count,
            "candidates": candidate_count,
            "failed_batches": failed,
            "cancelled": cancelled,
            "error": error,
        }
        with _job_state_lock:
            _job_state.update(
                running=False,
                finished_at=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                processed=processed, batches=batches, failed_batches=failed,
                error=error, summary=summary,
            )
        _job_lock.release()
        logger.info(
            "MX 手动打标任务结束 processed=%d/%d 合并标签帖=%d 审核=%d 候选=%d 失败批=%d 取消=%s",
            processed, total, tagged_posts, review_count, candidate_count, failed, cancelled,
        )


async def mx_llm_tag_loop(db, llm_config_provider, publish_alert=None) -> None:
    """常驻打标循环：睡到 next_due_tick 醒来跑一次 tick。

    llm_config_provider: 每次触发时现取系统 LLM 配置（管理员改配置无需重启）；
    publish_alert: (title, content) -> None，走系统通知 KOL 链路。
    """
    logger.info("MX LLM 打标循环已启动")
    while True:
        try:
            now = datetime.now(CN_TZ)
            due = next_due_tick(now)
            delay = (due - now).total_seconds() + 1.0  # +1s 保证严格过点
            logger.info("MX LLM 打标下次触发 %s（%.0f 秒后）", due.strftime("%H:%M:%S"), delay)
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 调度异常不终止循环
            logger.exception("MX LLM 打标调度异常，60 秒后重试")
            await asyncio.sleep(60)
            continue
        try:
            # provider 取配置含同步 DB 查询/解密，与 run_tag_tick 一起放进线程执行，
            # 不阻塞共享给 API 的事件循环
            await asyncio.to_thread(
                lambda: run_tag_tick(db, llm_config_provider(), publish_alert)
            )
        except Exception:  # noqa: BLE001 - tick 异常不终止循环
            logger.exception("MX LLM 打标 tick 异常")
