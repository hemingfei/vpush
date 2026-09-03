"""MX 开盘时段 LLM 打标：时刻表、结果校验、tick 执行与告警。"""
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app import mx_llm_tagging as m
from app.fetchers.base import CN_TZ
from app.db import DB


def make_db() -> DB:
    return DB(Path(tempfile.mkdtemp()) / "test.db")


def make_config(api_key="sk-test"):
    return SimpleNamespace(api_key=api_key, api_base="https://x", model="m")


def ts(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=CN_TZ)


def _reset_state():
    with m._state_lock:
        m._state.update(
            consecutive_failures=0, alert_active=False, last_run=None,
            calls_today={"date": "", "count": 0}, tick_started_at=None,
        )


# ---- next_due_tick：时刻表边界 ----

def test_next_due_tick_weekday_minute_window():
    assert m.next_due_tick(ts(2026, 9, 3, 8, 0)) == ts(2026, 9, 3, 9, 0)  # 周四
    assert m.next_due_tick(ts(2026, 9, 3, 9, 0)) == ts(2026, 9, 3, 9, 1)  # 严格晚于
    assert m.next_due_tick(ts(2026, 9, 3, 9, 30, 5)) == ts(2026, 9, 3, 9, 31)


def test_next_due_tick_switch_to_five_minutes():
    assert m.next_due_tick(ts(2026, 9, 3, 10, 29, 30)) == ts(2026, 9, 3, 10, 30)
    assert m.next_due_tick(ts(2026, 9, 3, 10, 30, 10)) == ts(2026, 9, 3, 10, 35)


def test_next_due_tick_afternoon_and_evening():
    # 15:05 是分钟档最后一跳，15:10 不含；之后到 18:00 集中点
    assert m.next_due_tick(ts(2026, 9, 3, 15, 5)) == ts(2026, 9, 3, 18, 0)
    assert m.next_due_tick(ts(2026, 9, 3, 15, 6)) == ts(2026, 9, 3, 18, 0)
    assert m.next_due_tick(ts(2026, 9, 3, 18, 0, 1)) == ts(2026, 9, 3, 23, 0)
    assert m.next_due_tick(ts(2026, 9, 3, 23, 0, 1)) == ts(2026, 9, 4, 9, 0)


def test_next_due_tick_weekend_fixed_points():
    # 周六 2026-09-05
    assert m.next_due_tick(ts(2026, 9, 5, 0, 0)) == ts(2026, 9, 5, 9, 0)
    assert m.next_due_tick(ts(2026, 9, 5, 9, 0, 1)) == ts(2026, 9, 5, 12, 0)
    assert m.next_due_tick(ts(2026, 9, 5, 20, 0, 1)) == ts(2026, 9, 5, 23, 0)
    assert m.next_due_tick(ts(2026, 9, 6, 23, 0, 1)) == ts(2026, 9, 7, 9, 0)  # 周一


def test_next_due_tick_accepts_naive_as_cn():
    assert m.next_due_tick(datetime(2026, 9, 3, 8, 0)) == ts(2026, 9, 3, 9, 0)


# ---- validate_batch_response：校验与分流 ----

def _result(topics=None, stocks=None, actions=None, jargon=None):
    return {
        "topics": topics or [],
        "stocks": stocks or [],
        "actions": actions or [],
        "jargon": jargon or [],
    }


VALID = {"贵州茅台", "宁德时代", "申菱环境"}
TOPICS = ["宏观", "大盘", "个股", "科技"]
ACTIONS = ["建仓", "加仓", "减仓", "清仓", "做T", "观察"]


def test_validate_high_writes_low_reviews():
    rows = [{"id": 1}, {"id": 2}]
    response = {
        1: _result(
            topics=[{"name": "个股", "confidence": "high"}],
            stocks=[{"official": "贵州茅台", "raw": "茅台", "confidence": "high"}],
            actions=[{"name": "做T", "confidence": "high"}],
            jargon=[{"raw": "茅台", "official": "贵州茅台", "kind": "general"}],
        ),
        2: _result(
            topics=[{"name": "科技", "confidence": "low"}],
            stocks=[{"official": "宁德时代", "raw": "宁王", "confidence": "low"}],
        ),
    }
    writes, reviews, pairs = m.validate_batch_response(
        rows, response, TOPICS, ACTIONS, VALID
    )
    assert writes[1] == ["贵州茅台", "做T", "个股"]
    assert writes[2] == []
    assert (2, "宁德时代", "stock") in reviews
    assert (2, "科技", "topic") in reviews
    assert pairs == [("茅台", "贵州茅台", 1)]


def test_validate_drops_vocab_miss_and_hallucination():
    rows = [{"id": 1}]
    response = {
        1: _result(
            topics=[{"name": "不存在的", "confidence": "high"}],
            stocks=[{"official": "不存在的股票", "raw": "x", "confidence": "high"}],
            actions=[{"name": "加仓", "confidence": "low"}],
        ),
    }
    writes, reviews, pairs = m.validate_batch_response(
        rows, response, TOPICS, ACTIONS, VALID
    )
    assert writes[1] == []
    assert reviews == [(1, "加仓", "action")]  # 幻觉股票既不写也不审
    assert pairs == []


def test_validate_total_cap_priority_stock_first():
    rows = [{"id": 1}]
    response = {
        1: _result(
            topics=[{"name": t, "confidence": "high"} for t in ("宏观", "大盘", "个股")],
            stocks=[{"official": "贵州茅台", "confidence": "high"},
                    {"official": "宁德时代", "confidence": "high"}],
            actions=[{"name": a, "confidence": "high"} for a in ("建仓", "做T")],
        ),
    }
    writes, _reviews, _pairs = m.validate_batch_response(
        rows, response, TOPICS, ACTIONS, VALID
    )
    # 2 股票 + 2 操作 + 3 话题，共 7 个未触顶（总上限 10）
    assert writes[1] == ["贵州茅台", "宁德时代", "建仓", "做T", "宏观", "大盘", "个股"]

    # 股票上限 6：7 只合法股票截到前 6；其余维度全保留（6+2+3=11 < 总上限 15）
    big_topics = [f"话{i}" for i in range(1, 4)]
    big_actions = [f"操{i}" for i in range(1, 3)]
    big_valid = {f"股{i}" for i in range(1, 8)}
    response = {
        1: _result(
            topics=[{"name": t, "confidence": "high"} for t in big_topics],
            stocks=[{"official": s, "confidence": "high"} for s in sorted(big_valid)],
            actions=[{"name": a, "confidence": "high"} for a in big_actions],
        ),
    }
    writes, _reviews, _pairs = m.validate_batch_response(
        rows, response, big_topics, big_actions, big_valid
    )
    assert writes[1] == [
        f"股{i}" for i in range(1, 7)
    ] + ["操1", "操2", "话1", "话2", "话3"]


def test_validate_general_jargon_only():
    rows = [{"id": 1}, {"id": 2}]
    response = {
        1: _result(jargon=[
            {"raw": "茅哥", "official": "贵州茅台", "kind": "general"},
            {"raw": "芒果", "official": "宁德时代", "kind": "context"},
            {"raw": "申领环境", "official": "申菱环境", "kind": "typo"},
            {"raw": "贵州茅台", "official": "贵州茅台", "kind": "general"},  # 同名剔除
            {"raw": "编的", "official": "不存在的股票", "kind": "general"},  # 非法正式名
        ]),
        2: _result(jargon=[{"raw": "茅哥", "official": "贵州茅台", "kind": "general"}]),
    }
    _w, _r, pairs = m.validate_batch_response(rows, response, TOPICS, ACTIONS, VALID)
    assert pairs == [("茅哥", "贵州茅台", 1), ("茅哥", "贵州茅台", 2)]


# ---- run_tag_tick：游标、告警、跳过 ----

def _add_mx_posts(db, n=2, external_prefix="m"):
    ids = []
    for i in range(n):
        kid = db.add_kol("mx", "修心见道", f"{external_prefix}{i}")
        pid = db.insert_post(
            "mx", kid, f"{external_prefix}{i}", "",
            "申领环境，又红5以上减的，均线低吃回来，做了个T", "u", ""
        )
        ids.append(pid)
    return ids


def test_run_tag_tick_success_writes_and_advances_cursor():
    db = make_db()
    ids = _add_mx_posts(db, 2)
    response = {
        ids[0]: _result(
            topics=[{"name": "个股", "confidence": "high"}],
            stocks=[{"official": "申菱环境", "raw": "申领环境", "confidence": "high"}],
            actions=[{"name": "做T", "confidence": "high"}],
            jargon=[{"raw": "申领环境", "official": "申菱环境", "kind": "typo"}],
        ),
        ids[1]: _result(
            stocks=[{"official": "贵州茅台", "raw": "茅哥", "confidence": "high"}],
            jargon=[{"raw": "茅哥", "official": "贵州茅台", "kind": "general"}],
        ),
    }
    import app.llm as llm
    orig = llm.tag_posts_llm
    llm.tag_posts_llm = lambda rows, *a, **kw: dict(response)
    _reset_state()
    try:
        result = m.run_tag_tick(db, make_config())
    finally:
        llm.tag_posts_llm = orig

    assert result["processed"] == 2 and result["batches"] == 1
    assert result["cursor"] == max(ids)
    assert db.get_mx_llm_tag_cursor() == max(ids)
    tags0 = db.list_posts(platform="mx", include_hidden=True)
    by_id = {p["id"]: p for p in tags0}
    assert by_id[ids[0]]["tags"] == ["申菱环境", "做T", "个股"]
    assert by_id[ids[1]]["tags"] == ["贵州茅台"]
    assert all(p["llm_tagged"] == 1 for p in by_id.values())  # LLM 写回打标记
    # typo 不进候选；general 进候选
    candidates = db.get_stock_alias_candidates()
    assert [c["alias"] for c in candidates] == ["茅哥"]
    reviews = db.list_tag_reviews()
    assert reviews == []
    db.close()


def test_run_tag_tick_replaces_local_rule_tags():
    """实时链路先打的本地规则标签，LLM 打标完成后被整体替换（含零命中写空）。"""
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    # 模拟实时/兜底入库时已先走过本地规则打标
    db.update_post_tags(pid, ["宏观"])
    import app.llm as llm
    orig = llm.tag_posts_llm
    _reset_state()
    try:
        llm.tag_posts_llm = lambda rows, *a, **kw: {
            pid: _result(
                topics=[{"name": "个股", "confidence": "high"}],
                stocks=[{"official": "申菱环境", "raw": "申领环境", "confidence": "high"}],
            )
        }
        result = m.run_tag_tick(db, make_config())
    finally:
        llm.tag_posts_llm = orig

    assert result["processed"] == 1
    posts = {p["id"]: p for p in db.list_posts(platform="mx", include_hidden=True)}
    assert posts[pid]["tags"] == ["申菱环境", "个股"]  # 规则标签被 LLM 标签替换
    assert posts[pid]["llm_tagged"] == 1
    db.close()


def test_run_tag_tick_low_tags_go_to_review():
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    response = {
        pid: _result(
            topics=[{"name": "科技", "confidence": "low"}],
            stocks=[{"official": "宁德时代", "raw": "宁王", "confidence": "low"}],
        ),
    }
    import app.llm as llm
    orig = llm.tag_posts_llm
    llm.tag_posts_llm = lambda rows, *a, **kw: dict(response)
    _reset_state()
    try:
        result = m.run_tag_tick(db, make_config())
    finally:
        llm.tag_posts_llm = orig

    assert result["processed"] == 1
    posts = {p["id"]: p for p in db.list_posts(platform="mx", include_hidden=True)}
    assert posts[pid]["tags"] == []  # low 标签不直接写
    reviews = db.list_tag_reviews()
    assert {(r["tag"], r["kind"]) for r in reviews} == {("科技", "topic"), ("宁德时代", "stock")}
    db.close()


def test_run_tag_tick_failure_keeps_cursor_and_alerts():
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    import app.llm as llm
    orig = llm.tag_posts_llm
    alerts = []
    llm.tag_posts_llm = lambda rows, *a, **kw: None
    _reset_state()
    try:
        r1 = m.run_tag_tick(db, make_config(), publish_alert=lambda t, c: alerts.append(t))
        r2 = m.run_tag_tick(db, make_config(), publish_alert=lambda t, c: alerts.append(t))
        r3 = m.run_tag_tick(db, make_config(), publish_alert=lambda t, c: alerts.append(t))
    finally:
        llm.tag_posts_llm = orig

    assert r1["failed_batches"] == r2["failed_batches"] == r3["failed_batches"] == 1
    assert db.get_mx_llm_tag_cursor() == 0  # 游标不动
    posts = {p["id"]: p for p in db.list_posts(platform="mx", include_hidden=True)}
    assert posts[pid]["tags"] == []  # 游标不动，标签未被写（list_posts 归一化为空数组）
    assert len(alerts) == 1  # 第 3 次失败才告警（冷却期内不重复）
    assert "连续失败 3 次" in alerts[0]
    db.close()


def test_run_tag_tick_recovery_notice_after_success():
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    import app.llm as llm
    orig = llm.tag_posts_llm
    alerts = []
    _reset_state()
    try:
        llm.tag_posts_llm = lambda rows, *a, **kw: None
        for _ in range(3):
            m.run_tag_tick(db, make_config(), publish_alert=lambda t, c: alerts.append(t))
        llm.tag_posts_llm = lambda rows, *a, **kw: {
            pid: _result(stocks=[{"official": "贵州茅台", "confidence": "high"}])
        }
        result = m.run_tag_tick(db, make_config(), publish_alert=lambda t, c: alerts.append(t))
    finally:
        llm.tag_posts_llm = orig

    assert result["batches"] == 1
    assert alerts[-1] == "MX LLM 打标已恢复"
    assert db.get_mx_llm_tag_cursor() == pid
    db.close()


def test_run_tag_tick_idle_no_false_alert_after_failures():
    """积压消失（如帖子被隐藏）后的空转 tick 不得凭历史失败计数再次告警。"""
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    import app.llm as llm
    orig = llm.tag_posts_llm
    alerts = []
    _reset_state()
    try:
        llm.tag_posts_llm = lambda rows, *a, **kw: None
        for _ in range(3):
            m.run_tag_tick(db, make_config(), publish_alert=lambda t, c: alerts.append(t))
        assert len(alerts) == 1
        # 积压清空 + 冷却窗口已过：空转 tick（failed_batches=0）不应再告警
        db._execute("UPDATE posts SET hidden = 1 WHERE id = ?", (pid,))
        db.set_setting(m._ALERT_COOLDOWN_KEY, "0")
        r = m.run_tag_tick(db, make_config(), publish_alert=lambda t, c: alerts.append(t))
        assert r["batches"] == 0 and r["failed_batches"] == 0
        assert len(alerts) == 1
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_run_tag_tick_skips_blocked_and_disabled():
    db = make_db()
    ids = _add_mx_posts(db, 2)
    db._execute("UPDATE posts SET blocked = 1 WHERE id = ?", (ids[0],))
    import app.llm as llm
    orig = llm.tag_posts_llm
    seen_rows = []

    def fake(rows, *a, **kw):
        seen_rows.extend(r["id"] for r in rows)
        return {r["id"]: _result() for r in rows}

    _reset_state()
    try:
        llm.tag_posts_llm = fake
        result = m.run_tag_tick(db, make_config())
        assert seen_rows == [ids[1]]  # blocked 帖不送 LLM
        assert result["cursor"] == ids[1]  # 游标跳过 blocked
        llm.tag_posts_llm = orig
        assert m.run_tag_tick(db, make_config(None)) == {"skipped": "no_llm"}
        db.set_mx_llm_tag_enabled(False)
        assert m.run_tag_tick(db, make_config()) == {"skipped": "disabled"}
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_run_tag_tick_busy_lock_skipped():
    db = make_db()
    _reset_state()
    with m._tick_lock:
        assert m.run_tag_tick(db, make_config()) == {"skipped": "busy"}
    db.close()


# ---- run_tag_test：试打预览，零写入 ----

def test_run_tag_test_preview_and_no_writes():
    db = make_db()
    ids = _add_mx_posts(db, 3)
    response = {
        ids[0]: _result(
            stocks=[{"official": "贵州茅台", "raw": "茅哥", "confidence": "high"}],
            jargon=[{"raw": "茅哥", "official": "贵州茅台", "kind": "general"}],
        ),
        ids[1]: _result(
            topics=[{"name": "科技", "confidence": "low"}],
            jargon=[{"raw": "芒果", "official": "贵州茅台", "kind": "context"}],
        ),
        ids[2]: _result(),
    }
    import app.llm as llm
    orig = llm.tag_posts_llm
    llm.tag_posts_llm = lambda rows, *a, **kw: dict(response)
    _reset_state()
    try:
        result = m.run_tag_test(db, make_config())
    finally:
        llm.tag_posts_llm = orig

    assert result["tested"] == 3
    items = {it["post_id"]: it for it in result["items"]}
    assert items[ids[0]]["tags"] == ["贵州茅台"]
    assert items[ids[0]]["jargon"] == [{"alias": "茅哥", "stock": "贵州茅台"}]
    assert items[ids[1]]["review_tags"] == [{"tag": "科技", "kind": "topic"}]
    assert items[ids[1]]["jargon"] == []  # context 黑话不进候选
    assert items[ids[2]]["tags"] == []
    assert result["summary"] == {"would_tag": 1, "would_review": 1, "would_candidates": 1}
    # 零写入：游标、标签、审核队列、候选表全部不动
    assert db.get_mx_llm_tag_cursor() == 0
    posts = {p["id"]: p for p in db.list_posts(platform="mx", include_hidden=True)}
    assert all(p["tags"] == [] for p in posts.values())
    assert db.list_tag_reviews() == []
    assert db.get_stock_alias_candidates() == []
    db.close()


def test_run_tag_test_skips():
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    _reset_state()
    with m._test_lock:  # 只有另一个试打在跑才 busy
        assert m.run_tag_test(db, make_config()) == {"skipped": "busy"}
    assert m.run_tag_test(db, make_config(None)) == {"skipped": "no_llm"}
    db.update_post_tags_llm(pid, [])  # 标记已打标 → 无未打标消息
    result = m.run_tag_test(db, make_config())
    assert result == {"skipped": "no_posts"}
    db.close()


def test_run_tag_test_runs_alongside_formal_tick():
    """正式 tick 持锁期间试打照常可用：试打零写入，与打标并行是安全的。"""
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    import app.llm as llm
    orig = llm.tag_posts_llm
    llm.tag_posts_llm = lambda rows, *a, **kw: {
        pid: _result(stocks=[{"official": "贵州茅台", "confidence": "high"}])
    }
    _reset_state()
    try:
        with m._tick_lock:  # 模拟正式 tick 正在跑（开盘时段可能连持数十分钟）
            result = m.run_tag_test(db, make_config())
        assert result["tested"] == 1
        assert result["items"][0]["tags"] == ["贵州茅台"]
        assert db.get_mx_llm_tag_cursor() == 0  # 试打不推游标
        db.close()
        db = make_db()
        (pid2,) = _add_mx_posts(db, 1)
        # 正式 tick 自身不受影响
        llm.tag_posts_llm = lambda rows, *a, **kw: {int(r["id"]): _result() for r in rows}
        assert m.run_tag_tick(db, make_config())["processed"] == 1
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_tick_running_flag_visible_in_status():
    db = make_db()
    _reset_state()
    observed = {}
    orig = m._run_tag_tick_locked

    def spy(db_, cfg, alert=None):
        status = m.get_tagger_status()
        observed["running"] = status["tick_running"]
        observed["seconds"] = status["tick_running_seconds"]
        return {"processed": 0, "batches": 0, "failed_batches": 0, "error": "", "cursor": 0}

    m._run_tag_tick_locked = spy
    try:
        m.run_tag_tick(db, make_config())
    finally:
        m._run_tag_tick_locked = orig

    assert observed["running"] is True and observed["seconds"] >= 0
    assert m.get_tagger_status()["tick_running"] is False  # 结束后复位
    db.close()


def test_run_tag_test_logs_details(caplog):
    """试打全程有日志：开始/汇总/逐帖明细，管理员可从服务端日志核对打标依据。"""
    import logging

    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    import app.llm as llm
    orig = llm.tag_posts_llm
    llm.tag_posts_llm = lambda rows, *a, **kw: {
        pid: _result(
            stocks=[{"official": "贵州茅台", "raw": "茅哥", "confidence": "high"}],
            jargon=[{"raw": "茅哥", "official": "贵州茅台", "kind": "general"}],
        )
    }
    _reset_state()
    try:
        with caplog.at_level(logging.INFO, logger="app.mx_llm_tagging"):
            result = m.run_tag_test(db, make_config())
    finally:
        llm.tag_posts_llm = orig

    assert result["tested"] == 1
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "试打开始" in text and "取未打标消息 1 条" in text
    assert "试打完成" in text and "将合并=1" in text
    assert f"post={pid}" in text
    assert "合并=[贵州茅台]" in text
    assert "黑话=[茅哥=贵州茅台]" in text
    db.close()


# ---- llm_tagged 标记位：只有 LLM 写回才打 ----

def test_llm_tagged_marker_only_set_by_llm_write():
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    # 规则回填（update_post_tags）与人工追加不打 LLM 标记
    db.update_post_tags(pid, ["宏观"])
    row = db.list_posts(platform="mx", include_hidden=True)[0]
    assert row["llm_tagged"] == 0 and row["tags"] == ["宏观"]
    # LLM 写回：替换标签并标记（新库迁移后列存在、默认 0）
    db.update_post_tags_llm(pid, ["贵州茅台"])
    row = db.list_posts(platform="mx", include_hidden=True)[0]
    assert row["llm_tagged"] == 1 and row["tags"] == ["贵州茅台"]
    db.close()


# ---- db 辅助：审核队列与候选表 ----

def test_append_post_tag_cap_and_dedupe():
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    assert db.append_post_tag(pid, "贵州茅台") is True
    assert db.append_post_tag(pid, "贵州茅台") is False  # 判重
    # 补满到 15 个后追加失败
    for tag in ("宁德时代", "申菱环境", "宏观", "大盘", "个股", "科技", "财报",
                "政策", "资讯", "美股", "港股", "黄金", "大宗", "医药"):
        assert db.append_post_tag(pid, tag) is True
    assert db.append_post_tag(pid, "加密") is False  # 已满 15 个
    posts = {p["id"]: p for p in db.list_posts(platform="mx", include_hidden=True)}
    assert posts[pid]["tags"] == [
        "贵州茅台", "宁德时代", "申菱环境", "宏观", "大盘", "个股", "科技", "财报",
        "政策", "资讯", "美股", "港股", "黄金", "大宗", "医药",
    ]
    db.close()


def test_tag_review_unique_and_status_flow():
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    db.add_pending_tag_review(pid, "科技", "topic", "low")
    db.add_pending_tag_review(pid, "科技", "topic", "low")  # 去重
    assert len(db.list_tag_reviews()) == 1
    review = db.list_tag_reviews()[0]
    updated = db.set_tag_review_status(review["id"], "approved")
    assert updated["post_id"] == pid and updated["tag"] == "科技"
    assert db.list_tag_reviews() == []
    assert len(db.list_tag_reviews(status="approved")) == 1
    assert db.set_tag_review_status(999, "approved") is None
    db.close()


def test_merge_stock_alias_candidates_dedupe_and_cap():
    from app.db import STOCK_ALIAS_CANDIDATES_MAX

    db = make_db()
    db.merge_stock_alias_candidates([("茅哥", "贵州茅台", 1)])
    db.merge_stock_alias_candidates([("茅哥", "贵州茅台", 2), ("宁叔", "宁德时代", 3)])
    candidates = db.get_stock_alias_candidates()
    by_alias = {c["alias"]: c for c in candidates}
    assert by_alias["茅哥"]["count"] == 2
    assert by_alias["宁叔"]["sample_post_id"] == 3
    db.merge_stock_alias_candidates([(f"别名{i}", "贵州茅台", None) for i in range(300)])
    assert len(db.get_stock_alias_candidates()) == STOCK_ALIAS_CANDIDATES_MAX
    db.close()


# ---- llm.tag_posts_llm：归一化（假 HTTP） ----

def _chat_response(payload_text):
    import httpx

    def handler(request):
        return httpx.Response(
            200, json={"choices": [{"message": {"content": payload_text}}]}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tag_posts_llm_success_normalization():
    from app.llm import tag_posts_llm

    rows = [{"id": 5, "kol_name": "修心见道", "title": "", "content": "芒果都绿了"}]
    text = (
        '{"results":[{"id":5,'
        '"topics":[{"name":"个股","confidence":"high"},{"name":"X","confidence":"high"}],'
        '"stocks":[{"official":"芒果超媒","raw":"芒果","confidence":"high"}],'
        '"actions":[],'
        '"jargon":[{"raw":"芒果","official":"芒果超媒","kind":"weird_kind"}]}]}'
    )
    out = tag_posts_llm(
        rows, [{"tag": "个股", "keywords": ["股价"]}], ["建仓"], ["芒果超媒"],
        llm_config=make_config(), client=_chat_response(text),
    )
    assert out is not None
    # tag_posts_llm 只做结构归一；词表过滤在 validate_batch_response 层
    assert out[5]["topics"] == [
        {"name": "个股", "confidence": "high"},
        {"name": "X", "confidence": "high"},
    ]
    assert out[5]["stocks"][0]["official"] == "芒果超媒"
    assert out[5]["jargon"][0]["kind"] == "context"  # 未知 kind 保守归为 context


def test_tag_posts_llm_bad_output_returns_none():
    from app.llm import tag_posts_llm

    rows = [{"id": 5, "kol_name": "a", "title": "", "content": "x"}]
    for bad in ("抱歉我做不到", "not json at all", '{"results": "nope"}'):
        out = tag_posts_llm(
            rows, [], [], [], llm_config=make_config(), client=_chat_response(bad)
        )
        assert out is None
    assert tag_posts_llm(rows, [], [], [], llm_config=None) is None
    assert tag_posts_llm([], [], [], [], llm_config=make_config()) == {}


# ---- 手动打标：合并写入 / 未打标计数 / 后台任务 ----

def test_merge_post_tags_llm_dedupe_and_cap():
    """LLM 结果与已有标签去重合并（已有在前），总数截到 POST_TAGS_MAX。"""
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    db.update_post_tags(pid, ["宏观", "个股"])  # 本地规则先打的标签
    n = db.merge_post_tags_llm(pid, ["申菱环境", "个股", "做T"])
    assert n == 4
    row = db.list_posts(platform="mx", include_hidden=True)[0]
    assert row["tags"] == ["宏观", "个股", "申菱环境", "做T"]
    assert row["llm_tagged"] == 1
    # 合并后超总数上限：截到前 POST_TAGS_MAX 个
    db.merge_post_tags_llm(pid, [f"标{i}" for i in range(12)])  # 4+12=16 → 15
    row = db.list_posts(platform="mx", include_hidden=True)[0]
    assert len(row["tags"]) == 15
    db.close()


def test_count_and_list_mx_pending():
    db = make_db()
    kid = db.add_kol("mx", "房间A", "p1")
    kid2 = db.add_kol("mx", "房间B", "p2")
    p1 = db.insert_post("mx", kid, "a1", "", "消息一", "u", "")
    p2 = db.insert_post("mx", kid, "a2", "", "消息二", "u", "")
    b1 = db.insert_post("mx", kid2, "b1", "", "消息三", "u", "")
    db._execute("UPDATE posts SET blocked = 1 WHERE id = ?", (p2,))
    done = db.insert_post("mx", kid2, "b2", "", "消息四", "u", "")
    db.update_post_tags_llm(done, [])  # 已打标的不算 pending
    counts = {r["kol_id"]: int(r["pending"]) for r in db.count_mx_pending_by_kol()}
    assert counts[kid] == 1 and counts[kid2] == 1
    assert db.count_mx_pending_total() == 2
    assert [r["id"] for r in db.list_mx_pending_posts([kid], 10)] == [p1]
    assert [r["id"] for r in db.list_mx_pending_posts(None, 10)] == [p1, b1]
    db.close()


def test_run_manual_job_merges_and_reports():
    """手动任务：分批合并写入、low 进审核、进度汇总正确、llm_tagged 置位。"""
    db = make_db()
    kid = db.add_kol("mx", "房间M", "m1")
    p1 = db.insert_post("mx", kid, "x1", "", "申领环境做个T", "u", "")
    p2 = db.insert_post("mx", kid, "x2", "", "宁王可以关注", "u", "")
    db.update_post_tags(p1, ["个股"])  # 本地已有标签，验证合并保留
    import app.llm as llm
    orig = llm.tag_posts_llm

    def fake(rows, *a, **kw):
        out = {}
        for r in rows:
            out[int(r["id"])] = (
                _result(
                    stocks=[{"official": "申菱环境", "confidence": "high"}],
                    actions=[{"name": "做T", "confidence": "high"}],
                ) if "申领" in r["content"]
                else _result(topics=[{"name": "科技", "confidence": "low"}])
            )
        return out

    _reset_state()
    llm.tag_posts_llm = fake
    assert m._job_lock.acquire(blocking=False)
    try:
        m._run_manual_job(db, make_config(), [kid], 100)
        status = m.get_manual_job_status()
        assert status["running"] is False and status["total"] == 2
        s = status["summary"]
        # tagged_posts 只统计拿到 LLM 标签的消息（p2 仅 low，进审核不写标签）
        assert s["processed"] == 2 and s["tagged_posts"] == 1
        assert s["reviews"] == 1 and s["candidates"] == 0 and s["failed_batches"] == 0
        assert s["error"] == "" and s["cancelled"] is False
        posts = {p["id"]: p for p in db.list_posts(platform="mx", include_hidden=True)}
        # 本地标签保留 + LLM 标签去重合并；仅 low 的消息合并结果为空但已算处理
        assert posts[p1]["tags"] == ["个股", "申菱环境", "做T"]
        assert posts[p2]["tags"] == []
        assert all(p["llm_tagged"] == 1 for p in posts.values())
        assert [(r["tag"], r["kind"]) for r in db.list_tag_reviews()] == [("科技", "topic")]
        assert db.list_mx_pending_posts(None, 100) == []
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_run_manual_job_llm_failure_keeps_pending():
    """LLM 调用失败：任务报错收场，未处理消息保持未打标（可直接重试）。"""
    db = make_db()
    kid = db.add_kol("mx", "房间F", "f1")
    p1 = db.insert_post("mx", kid, "y1", "", "内容一", "u", "")
    p2 = db.insert_post("mx", kid, "y2", "", "内容二", "u", "")
    import app.llm as llm
    orig = llm.tag_posts_llm
    _reset_state()
    llm.tag_posts_llm = lambda rows, *a, **kw: None
    assert m._job_lock.acquire(blocking=False)
    try:
        m._run_manual_job(db, make_config(), [kid], 100)
        status = m.get_manual_job_status()
        assert status["summary"]["failed_batches"] == 1
        assert "LLM 调用失败" in status["summary"]["error"]
        assert status["summary"]["processed"] == 0
        pending_ids = {r["id"] for r in db.list_mx_pending_posts(None, 100)}
        assert pending_ids == {p1, p2}
    finally:
        llm.tag_posts_llm = orig
    db.close()
