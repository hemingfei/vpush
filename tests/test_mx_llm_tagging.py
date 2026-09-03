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
            calls_today={"date": "", "count": 0},
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
    # 2 股票 + 2 操作 + 1 话题（截到 5，话题优先级最低）
    assert writes[1] == ["贵州茅台", "宁德时代", "建仓", "做T", "宏观"]


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

    assert result["tested"] == 3 and result["cursor"] == 0
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
    with m._tick_lock:
        assert m.run_tag_test(db, make_config()) == {"skipped": "busy"}
    assert m.run_tag_test(db, make_config(None)) == {"skipped": "no_llm"}
    db.set_mx_llm_tag_cursor(pid)  # 游标推到末尾 → 无未处理消息
    result = m.run_tag_test(db, make_config())
    assert result["skipped"] == "no_posts" and result["cursor"] == pid
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
    for tag in ("宁德时代", "宏观", "大盘", "个股"):
        db.append_post_tag(pid, tag)
    assert db.append_post_tag(pid, "科技") is False  # 已满 5 个
    posts = {p["id"]: p for p in db.list_posts(platform="mx", include_hidden=True)}
    assert posts[pid]["tags"] == ["贵州茅台", "宁德时代", "宏观", "大盘", "个股"]
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
