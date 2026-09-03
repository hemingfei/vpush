"""MX 实时消息的开盘时段 LLM 打标。

调度（mx_llm_tag_loop，常驻 asyncio 任务）：
- 工作日 09:00-10:29 每分钟、10:30-15:05 每五分钟，另加 18:00/23:00 集中点；
- 周末 09/12/15/18/20/23 点集中；
- 法定节假日无日历，按工作日表跑——无新帖则零 LLM 调用，自然空转。

进度（settings 键 mx_llm_tag_cursor = 已处理的最大 post id）重启安全；每个触发
点循环排空积压（单 tick 最多 N 批），单批失败游标不动、下个触发点整体重试
（重复打标是幂等覆盖，无害）。

打标（llm.tag_posts_llm）：话题+股票+操作三类标签，每个标签带 confidence；
high 直接整体替换写入 posts.tags（总上限 POST_TAGS_MAX，超出按 股票>操作>话题
截断），low 进 post_tag_reviews 人工审核；LLM 报告的 kind=general 黑话经
is_acceptable_alias 预过滤后进 stock_alias_candidates 候选表，人工审核通过后
并入 stock_aliases 供规则打标免费命中（context/typo 一律不入候选）。

连续失败 >=3 次通过系统通知 KOL 告警（30 分钟冷却），恢复后发恢复通知。
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

# 运行状态（进程内计数，重启归零）：供管理端状态面板展示
_state_lock = threading.Lock()
_state: dict = {
    "consecutive_failures": 0,
    "alert_active": False,
    "last_run": None,
    "calls_today": {"date": "", "count": 0},
}

# 单飞锁：LLM 单批最长 180s，分钟级触发点可能撞上未结束的上一轮
_tick_lock = threading.Lock()


def get_tagger_status() -> dict:
    """管理端状态面板用的运行快照（内存计数）。"""
    with _state_lock:
        return {
            "consecutive_failures": _state["consecutive_failures"],
            "alert_active": _state["alert_active"],
            "last_run": dict(_state["last_run"]) if _state["last_run"] else None,
            "calls_today": dict(_state["calls_today"]),
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

    返回 (writes, reviews, general_pairs)：
    - writes: {post_id: [最终标签]}——仅收 high 且过词表/名单校验的标签，按
      股票>操作>话题 拼接后截到 POST_TAGS_MAX；LLM 缺失的帖子写空（是否整批
      作废由调用方按 MISSING_RATIO_LIMIT 决定）；
    - reviews: [(post_id, tag, kind)]——low 标签进人工审核（幻觉股票既不写也不审）；
    - general_pairs: [(alias, stock, post_id)]——kind=general 的黑话映射（context/
      typo 在 llm 归一层已保守处理，这里只认 general 且正式名在名单内）。
    """
    topic_set = {str(t) for t in topic_tags or []}
    action_set = {str(t) for t in action_tags or []}
    writes: dict[int, list[str]] = {}
    reviews: list[tuple[int, str, str]] = []
    general_pairs: list[tuple[str, str, int]] = []
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
        )[:2]
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
        writes[pid] = _dedupe(stocks_high + actions_high + topics_high)[:POST_TAGS_MAX]
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
    return writes, reviews, general_pairs


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
    try:
        return _run_tag_tick_locked(db, llm_config, publish_alert)
    finally:
        _tick_lock.release()


def _run_tag_tick_locked(db, llm_config, publish_alert) -> dict:
    from .llm import tag_posts_llm
    from .tagging import is_acceptable_alias

    if not db.get_mx_llm_tag_enabled():
        return {"skipped": "disabled"}
    if not (llm_config and getattr(llm_config, "api_key", "")):
        return {"skipped": "no_llm"}

    batch_size = min(
        max(db.get_mx_llm_tag_int_setting(MX_LLM_TAG_BATCH_SIZE_KEY, 40), 1), 100
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
            break
        missing = len(rows) - len(response)
        if len(rows) and missing / len(rows) > MISSING_RATIO_LIMIT:
            failed_batches += 1
            last_error = f"LLM 响应缺失 {missing}/{len(rows)} 条"
            break
        writes, reviews, general_pairs = validate_batch_response(
            rows, response, topic_tags, action_tags, valid_stocks
        )
        for pid, tags in writes.items():
            db.update_post_tags_llm(pid, tags)
        for pid, tag, kind in reviews:
            db.add_pending_tag_review(pid, tag, kind, "low")
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
    """试打标：取游标之后最多 10 条未处理 MX 帖，走一遍与正式 tick 完全同源的
    LLM 调用与校验，只返回预览结果——不写标签、不进审核/候选表、不推进游标。

    管理端「试打 10 条」按钮用；拿不到单飞锁（正式 tick 在跑）返回 busy。
    """
    from .llm import tag_posts_llm
    from .tagging import is_acceptable_alias

    if not _tick_lock.acquire(blocking=False):
        return {"skipped": "busy"}
    try:
        if not (llm_config and getattr(llm_config, "api_key", "")):
            return {"skipped": "no_llm"}
        tag_rules, topic_tags, action_tags, names, aliases, valid_stocks = _tag_inputs(db)
        known_aliases = {a["alias"] for a in aliases}
        cursor = db.get_mx_llm_tag_cursor()
        rows = db.list_mx_posts_after(cursor, TEST_BATCH_SIZE)
        if not rows:
            return {"skipped": "no_posts", "cursor": cursor}
        response = tag_posts_llm(
            rows, tag_rules, action_tags, names, aliases, llm_config
        )
        _record_call()
        if response is None:
            return {"skipped": "llm_failed"}
        writes, reviews, general_pairs = validate_batch_response(
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
            items.append(
                {
                    "post_id": pid,
                    "kol_name": str(row.get("kol_name") or ""),
                    "excerpt": excerpt,
                    "tags": list(writes.get(pid) or []),
                    "review_tags": [
                        {"tag": tag, "kind": kind}
                        for rp, tag, kind in reviews
                        if rp == pid
                    ],
                    "jargon": [
                        {"alias": alias, "stock": stock}
                        for alias, stock, rp in pairs
                        if rp == pid
                    ],
                }
            )
        return {
            "cursor": cursor,
            "tested": len(rows),
            "items": items,
            "summary": {
                "would_tag": sum(1 for item in items if item["tags"]),
                "would_review": sum(len(item["review_tags"]) for item in items),
                "would_candidates": len({(j["alias"], j["stock"]) for j in (
                    j for item in items for j in item["jargon"]
                )}),
            },
        }
    finally:
        _tick_lock.release()


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
