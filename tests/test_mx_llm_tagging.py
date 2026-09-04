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


def _reset_manual_state():
    """清空手动打标队列模型状态（run 表/队列/认领集/工作线程计数）。"""
    with m._runs_lock:
        m._runs.clear()
        m._queue.clear()
        m._claimed_ids.clear()
        m._run_seq = 0
        m._workers = 0
    _reset_state()


def _reset_auto_state():
    """清空自动打标触发布防与告警核对状态（不影响 run 队列）。"""
    with m._auto_state_lock:
        m._auto_state.update(armed=False, watermark=0, last_trigger_ts=None)
    m._auto_alert_seen.clear()
    _reset_state()


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
    writes, reviews, pairs, applied = m.validate_batch_response(
        rows, response, TOPICS, ACTIONS, VALID
    )
    assert writes[1] == ["贵州茅台", "做T", "个股"]
    assert writes[2] == []
    assert (2, "宁德时代", "stock") in reviews
    assert (2, "科技", "topic") in reviews
    assert pairs == [("茅台", "贵州茅台", 1)]
    # applied 与 writes 同口径，且带类型（供写库后登记标签来源）
    assert applied == [(1, "贵州茅台", "stock"), (1, "做T", "action"), (1, "个股", "topic")]


def test_validate_drops_vocab_miss_and_hallucination():
    rows = [{"id": 1}]
    response = {
        1: _result(
            topics=[{"name": "不存在的", "confidence": "high"}],
            stocks=[{"official": "不存在的股票", "raw": "x", "confidence": "high"}],
            actions=[{"name": "加仓", "confidence": "low"}],
        ),
    }
    writes, reviews, pairs, applied = m.validate_batch_response(
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
    writes, _reviews, _pairs, _applied = m.validate_batch_response(
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
    writes, _reviews, _pairs, _applied = m.validate_batch_response(
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
    _w, _r, pairs, _applied = m.validate_batch_response(rows, response, TOPICS, ACTIONS, VALID)
    assert pairs == [("茅哥", "贵州茅台", 1), ("茅哥", "贵州茅台", 2)]


# ---- 测试数据助手 ----

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
    # 零写入：标签、审核队列、候选表全部不动（也无游标类残留设置）
    assert db.get_setting("mx_llm_tag_cursor") is None
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


def test_tag_review_skips_tag_already_on_post():
    """标签已在帖上（规则标签/上一轮已写入）时不进审核：通过与否它都已在帖。"""
    db = make_db()
    (pid,) = _add_mx_posts(db, 1)
    db.update_post_tags(pid, ["科技"])
    assert db.add_pending_tag_review(pid, "科技", "topic", "low") is False
    assert db.list_tag_reviews() == []
    assert db.add_pending_tag_review(pid, "宏观", "topic", "low") is True
    assert [r["tag"] for r in db.list_tag_reviews()] == ["宏观"]
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


def test_manual_run_merges_and_reports(monkeypatch):
    """手动打标：分批合并写入、low 进审核、进度汇总正确、llm_tagged 置位。"""
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

    _reset_manual_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    llm.tag_posts_llm = fake
    try:
        out = m.start_manual_run(db, make_config(), [kid], 100)
        assert out["started"] is True and out["total"] == 2 and out["batches"] == 1
        m._drain_manual_queue()
        status = m.get_manual_job_status()
        assert status["running"] is False
        run = status["runs"][0]
        assert run["status"] == "done" and run["total"] == 2
        s = run["summary"]
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


def test_manual_run_batches_capped_at_100(monkeypatch):
    """手动打标单批 ≤100 条：250 条切 3 批（100/100/50），逐批入队。"""
    db = make_db()
    kid = db.add_kol("mx", "房间C", "c1")
    for i in range(250):
        db.insert_post("mx", kid, f"c{i}", "", f"消息{i}", "u", "")
    import app.llm as llm
    orig = llm.tag_posts_llm
    sizes = []

    def fake(rows, *a, **kw):
        sizes.append(len(rows))
        return {
            int(r["id"]): _result(topics=[{"name": "科技", "confidence": "high"}])
            for r in rows
        }

    _reset_manual_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    llm.tag_posts_llm = fake
    try:
        out = m.start_manual_run(db, make_config(), [kid], 1000)
        assert out["total"] == 250 and out["batches"] == 3 and out["batch_size"] == 100
        m._drain_manual_queue()
        assert sizes == [100, 100, 50]
        run = m.get_manual_job_status()["runs"][0]
        assert run["status"] == "done"
        assert run["processed"] == 250 and run["batches_done"] == 3
        assert run["batches_failed"] == 0 and run["batches_skipped"] == 0
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_manual_run_second_run_queues_and_claims_remaining(monkeypatch):
    """任务进行中可再启动（入队不拒绝）；重叠大V的已认领消息不重复打标。"""
    db = make_db()
    kid = db.add_kol("mx", "房间Q", "q1")
    for i in range(150):
        db.insert_post("mx", kid, f"q{i}", "", f"消息{i}", "u", "")
    import app.llm as llm
    orig = llm.tag_posts_llm
    seen = []

    def fake(rows, *a, **kw):
        seen.append([int(r["id"]) for r in rows])
        return {
            int(r["id"]): _result(topics=[{"name": "科技", "confidence": "high"}])
            for r in rows
        }

    _reset_manual_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    llm.tag_posts_llm = fake
    try:
        out1 = m.start_manual_run(db, make_config(), [kid], 100)
        assert out1["started"] is True and out1["total"] == 100
        # run1 尚未排空时启动 run2：照常入队，只认领 run1 未认领的剩余 50 条
        out2 = m.start_manual_run(db, make_config(), [kid], 100)
        assert out2["started"] is True and out2["total"] == 50
        m._drain_manual_queue()
        status = m.get_manual_job_status()
        assert status["running"] is False and len(status["runs"]) == 2
        by_id = {r["run_id"]: r for r in status["runs"]}
        assert by_id[out1["run_id"]]["processed"] == 100
        assert by_id[out2["run_id"]]["processed"] == 50
        # 两次打标无重叠，150 条消息各打标一次
        flat = [pid for batch in seen for pid in batch]
        assert len(flat) == 150 and len(set(flat)) == 150
        assert len(db.list_mx_pending_posts(None, 1000)) == 0
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_manual_run_cancel_skips_queued(monkeypatch):
    """取消任务：当前批次完成后停止，排队批次跳过，未处理消息保持未打标。"""
    db = make_db()
    kid = db.add_kol("mx", "房间X", "x1")
    for i in range(250):
        db.insert_post("mx", kid, f"x{i}", "", f"消息{i}", "u", "")
    import app.llm as llm
    orig = llm.tag_posts_llm
    calls = []

    def fake(rows, *a, **kw):
        calls.append(len(rows))
        return {
            int(r["id"]): _result(topics=[{"name": "科技", "confidence": "high"}])
            for r in rows
        }

    _reset_manual_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    llm.tag_posts_llm = fake
    try:
        out = m.start_manual_run(db, make_config(), [kid], 1000)
        assert m.request_cancel_manual_run(out["run_id"]) == 1
        m._drain_manual_queue()
        assert calls == []  # 取消发生在任何批次开跑前
        run = m.get_manual_job_status()["runs"][0]
        assert run["status"] == "cancelled" and run["cancel_requested"] is True
        assert run["processed"] == 0 and run["batches_skipped"] == 3
        s = run["summary"]
        assert s["cancelled"] is True and s["processed"] == 0
        assert len(db.list_mx_pending_posts(None, 1000)) == 250
        assert m.request_cancel_manual_run() == 0  # 已无进行中任务
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_manual_run_low_tag_already_on_post_not_reviewed(monkeypatch):
    """LLM low 建议的标签若已在帖上（如规则标签），不进审核队列也不计数。"""
    db = make_db()
    kid = db.add_kol("mx", "房间N", "n1")
    p1 = db.insert_post("mx", kid, "y1", "", "消息内容", "u", "")
    db.update_post_tags(p1, ["科技"])
    import app.llm as llm
    orig = llm.tag_posts_llm
    llm.tag_posts_llm = lambda rows, *a, **kw: {
        int(r["id"]): _result(topics=[{"name": "科技", "confidence": "low"}]) for r in rows
    }
    _reset_manual_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    try:
        m.start_manual_run(db, make_config(), [kid], 100)
        m._drain_manual_queue()
        s = m.get_manual_job_status()["runs"][0]["summary"]
        assert s["reviews"] == 0 and s["processed"] == 1
        assert db.list_tag_reviews() == []
        assert db.get_post_tags(p1) == ["科技"]  # 合并后规则标签保留
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_manual_run_llm_failure_keeps_pending(monkeypatch):
    """LLM 调用失败：任务报错收场、剩余批次跳过，未处理消息保持未打标。"""
    db = make_db()
    kid = db.add_kol("mx", "房间F", "f1")
    for i in range(150):
        db.insert_post("mx", kid, f"f{i}", "", f"内容{i}", "u", "")
    import app.llm as llm
    orig = llm.tag_posts_llm
    _reset_manual_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    llm.tag_posts_llm = lambda rows, *a, **kw: None
    try:
        m.start_manual_run(db, make_config(), [kid], 1000)
        m._drain_manual_queue()
        status = m.get_manual_job_status()
        run = status["runs"][0]
        assert run["status"] == "failed"
        assert run["summary"]["failed_batches"] == 1
        assert run["batches_skipped"] == 1  # 第二批随收场跳过
        assert "LLM 调用失败" in run["summary"]["error"]
        assert run["summary"]["processed"] == 0
        assert len(db.list_mx_pending_posts(None, 1000)) == 150
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_manual_run_no_posts_rejected(monkeypatch):
    """所选大V没有未打标消息时直接拒绝（不再空跑任务）。"""
    db = make_db()
    kid = db.add_kol("mx", "房间E", "e1")
    _reset_manual_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    out = m.start_manual_run(db, make_config(), [kid], 100)
    assert out["started"] is False and out["reason"] == "no_posts"
    assert m.get_manual_job_status()["runs"] == []
    db.close()


def test_manual_run_real_workers_process_queue():
    """不替换工作线程：入队即由真实线程消费（同时最多 3 批），任务正常收场。"""
    import time as t

    db = make_db()
    kid = db.add_kol("mx", "房间W", "w1")
    for i in range(10):
        db.insert_post("mx", kid, f"w{i}", "", f"消息{i}", "u", "")
    import app.llm as llm
    orig = llm.tag_posts_llm
    llm.tag_posts_llm = lambda rows, *a, **kw: {
        int(r["id"]): _result(topics=[{"name": "科技", "confidence": "high"}]) for r in rows
    }
    _reset_manual_state()
    try:
        out = m.start_manual_run(db, make_config(), [kid], 100)
        assert out["started"] is True
        deadline = t.time() + 10
        while t.time() < deadline and m.get_manual_job_status()["running"]:
            t.sleep(0.05)
        run = m.get_manual_job_status()["runs"][0]
        assert run["status"] == "done" and run["processed"] == 10
        assert len(db.list_mx_pending_posts(None, 100)) == 0
        # 等工作线程随队列排空退出，避免残留线程污染后续测试的工作线程计数
        deadline = t.time() + 5
        while t.time() < deadline and m._workers > 0:
            t.sleep(0.05)
    finally:
        llm.tag_posts_llm = orig
        _reset_manual_state()
    db.close()


# ---- 自动打标：配置校验、时段解析、触发引擎 ----

def _save_auto(db, enabled=True, regular=None, specials=None, threshold=5, interval_minutes=30):
    cfg = {
        "enabled": enabled,
        "regular": regular
        or {"start": "00:00", "end": "23:59", "threshold": threshold, "interval_minutes": interval_minutes},
        "specials": specials or [],
    }
    clean, err = m.save_auto_config(db, cfg)
    assert err == "", err
    return clean


def test_normalize_auto_config_validation():
    # 常规时间段必填且开始<结束
    cfg, err = m.normalize_auto_config(
        {"regular": {"start": "23:00", "end": "09:00", "threshold": 5, "interval_minutes": 30}}
    )
    assert cfg is None and "常规时间段" in err
    # 时间格式必须 HH:MM
    cfg, err = m.normalize_auto_config(
        {"regular": {"start": "9:00", "end": "10:00", "threshold": 5, "interval_minutes": 30}}
    )
    assert cfg is None and "HH:MM" in err
    # 触发条数 / 间隔分钟边界
    cfg, err = m.normalize_auto_config(
        {"regular": {"start": "09:00", "end": "10:00", "threshold": 0, "interval_minutes": 30}}
    )
    assert cfg is None and "触发条数" in err
    cfg, err = m.normalize_auto_config(
        {"regular": {"start": "09:00", "end": "10:00", "threshold": 5, "interval_minutes": 0}}
    )
    assert cfg is None and "间隔分钟" in err
    # 特殊时间段错误带序号
    cfg, err = m.normalize_auto_config({
        "regular": {"start": "00:00", "end": "23:59", "threshold": 50, "interval_minutes": 30},
        "specials": [
            {"start": "09:00", "end": "10:00", "threshold": 5, "interval_minutes": 5},
            {"start": "11:00", "end": "10:00", "threshold": 5, "interval_minutes": 5},
        ],
    })
    assert cfg is None and "第 2 个" in err
    # 合法配置规范化
    cfg, err = m.normalize_auto_config({
        "enabled": True,
        "regular": {"start": "00:00", "end": "23:59", "threshold": 50, "interval_minutes": 30},
        "specials": [
            {"name": "开盘", "start": "09:15", "end": "11:35", "threshold": 20, "interval_minutes": 5}
        ],
    })
    assert err == "" and cfg["enabled"] is True
    assert cfg["regular"]["threshold"] == 50
    assert cfg["specials"][0]["name"] == "开盘"


def test_resolve_auto_period_special_priority_and_boundary():
    cfg = {
        "regular": {"name": "", "start": "00:00", "end": "23:59", "threshold": 50, "interval_minutes": 30},
        "specials": [
            {"name": "开盘", "start": "09:15", "end": "11:35", "threshold": 20, "interval_minutes": 5},
            {"name": "尾盘", "start": "14:30", "end": "15:30", "threshold": 10, "interval_minutes": 3},
        ],
    }
    period = m.resolve_auto_period(cfg, ts(2026, 9, 4, 9, 20))
    assert period["kind"] == "special" and period["name"] == "开盘" and period["threshold"] == 20
    # 特殊时段含端点（15:30 仍属尾盘）
    period = m.resolve_auto_period(cfg, ts(2026, 9, 4, 15, 30))
    assert period["kind"] == "special" and period["name"] == "尾盘"
    # 不命中特殊时段回退常规
    period = m.resolve_auto_period(cfg, ts(2026, 9, 4, 12, 0))
    assert period["kind"] == "regular"
    # 常规时段之外不触发（9:00 含端点命中）
    cfg2 = {
        "regular": {"name": "", "start": "09:00", "end": "15:00", "threshold": 50, "interval_minutes": 30},
        "specials": [],
    }
    assert m.resolve_auto_period(cfg2, ts(2026, 9, 4, 8, 59)) is None
    assert m.resolve_auto_period(cfg2, ts(2026, 9, 4, 9, 0)) is not None


def test_auto_check_count_trigger_and_watermark(monkeypatch):
    """新消息达到阈值触发：入队 source=auto 任务，水位推进、不连环触发。"""
    db = make_db()
    _reset_manual_state()
    _reset_auto_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    import app.llm as llm
    orig = llm.tag_posts_llm
    llm.tag_posts_llm = lambda rows, *a, **kw: {
        int(r["id"]): _result(topics=[{"name": "科技", "confidence": "high"}]) for r in rows
    }
    try:
        _save_auto(db)  # 布防：水位=当前最大 id，间隔计时清零
        ids = _add_mx_posts(db, 6)  # 布防后到达 6 条 ≥ 阈值 5 → 条数触发
        out = m._auto_check(db, lambda: make_config())
        assert out.get("triggered") is True and "达 6" in out["reason"]
        run = m.get_manual_job_status()["runs"][0]
        assert run["source"] == "auto" and run["total"] == 6
        with m._auto_state_lock:
            assert m._auto_state["watermark"] == max(ids)
            assert m._auto_state["last_trigger_ts"] is not None
        # 自动任务还在队列 → 不连环触发
        assert m._auto_check(db, lambda: make_config()) == {"skipped": "auto_run_active"}
        m._drain_manual_queue()
        # 再来 1 条（未达阈值、间隔未到）→ 不触发
        _add_mx_posts(db, 1, external_prefix="n")
        assert m._auto_check(db, lambda: make_config()) == {"skipped": "not_due"}
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_auto_check_interval_trigger(monkeypatch):
    """首轮布防后立即触发；之后仅当距上次触发超过间隔分钟才再触发。"""
    import time as time_module

    db = make_db()
    _add_mx_posts(db, 2)
    _reset_manual_state()
    _reset_auto_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    import app.llm as llm
    orig = llm.tag_posts_llm
    llm.tag_posts_llm = lambda rows, *a, **kw: {
        int(r["id"]): _result(topics=[{"name": "科技", "confidence": "high"}]) for r in rows
    }
    try:
        _save_auto(db, threshold=100, interval_minutes=30)
        # 首轮布防后 last_trigger_ts=None → 立即触发（即使没有新消息）
        out = m._auto_check(db, lambda: make_config())
        assert out.get("triggered") is True and "间隔" in out["reason"]
        m._drain_manual_queue()
        # 未达阈值、间隔未到 → 不触发
        _add_mx_posts(db, 1, external_prefix="i")
        assert m._auto_check(db, lambda: make_config()) == {"skipped": "not_due"}
        # 上次触发拨回 31 分钟前 → 间隔触发，只处理剩余未打标的 1 条
        with m._auto_state_lock:
            m._auto_state["last_trigger_ts"] = time_module.time() - 31 * 60
        out2 = m._auto_check(db, lambda: make_config())
        assert out2.get("triggered") is True and "间隔" in out2["reason"]
        assert m.get_manual_job_status()["runs"][0]["total"] == 1
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_auto_check_skips_disabled_out_of_period_no_llm(monkeypatch):
    db = make_db()
    _add_mx_posts(db, 3)
    _reset_manual_state()
    _reset_auto_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # 固定为 08:00，时段判定可确定性断言
            return ts(2026, 9, 4, 8, 0)

    monkeypatch.setattr(m, "datetime", FixedDatetime)
    # 开关关闭 → 跳过并清布防
    _save_auto(db, enabled=False)
    assert m._auto_check(db, lambda: make_config()) == {"skipped": "disabled"}
    with m._auto_state_lock:
        assert m._auto_state["armed"] is False
    # 8:00 不在 9:00-15:00 → 不在时段
    _save_auto(
        db,
        regular={"start": "09:00", "end": "15:00", "threshold": 1, "interval_minutes": 5},
    )
    assert m._auto_check(db, lambda: make_config()) == {"skipped": "out_of_period"}
    # 命中 7:00-9:00（含端点）但未配系统 LLM → no_llm
    _save_auto(
        db,
        regular={"start": "07:00", "end": "09:00", "threshold": 1, "interval_minutes": 5},
    )
    assert m._auto_check(db, lambda: make_config(None)) == {"skipped": "no_llm"}
    assert m.get_manual_job_status()["runs"] == []


def test_auto_check_no_pending_advances_watermark(monkeypatch):
    """无待打标消息不触发，但把水位推进到当前（历史消息不累计条数）。"""
    db = make_db()
    ids = _add_mx_posts(db, 2)
    db.update_post_tags_llm(ids[0], [])
    db.update_post_tags_llm(ids[1], [])
    _reset_manual_state()
    _reset_auto_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    _save_auto(db)
    assert m._auto_check(db, lambda: make_config()) == {"skipped": "no_pending"}
    with m._auto_state_lock:
        assert m._auto_state["watermark"] == ids[1]
        assert m._auto_state["armed"] is True


def test_auto_alert_on_repeated_failures(monkeypatch):
    """自动任务连续失败达阈值发告警（带冷却），成功后发恢复通知。"""
    db = make_db()
    _add_mx_posts(db, 1)
    _reset_manual_state()
    _reset_auto_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    import app.llm as llm
    orig = llm.tag_posts_llm
    alerts = []
    db.set_setting(m._ALERT_COOLDOWN_KEY, "0")
    try:
        _save_auto(db)
        llm.tag_posts_llm = lambda rows, *a, **kw: None
        for _ in range(3):
            # 复位间隔计时（布防），让每个失败任务都能立即再次触发
            with m._auto_state_lock:
                m._auto_state["last_trigger_ts"] = None
            out = m._auto_check(db, lambda: make_config(), lambda t, c: alerts.append(t))
            assert out.get("triggered")
            m._drain_manual_queue()
        # 3 个失败任务都已完成未核对；再跑一轮检查 → 累计 3 次失败 → 告警
        m._auto_check(db, lambda: make_config(), lambda t, c: alerts.append(t))
        assert any("连续失败 3 次" in a for a in alerts)

        llm.tag_posts_llm = lambda rows, *a, **kw: {
            int(r["id"]): _result(topics=[{"name": "科技", "confidence": "high"}]) for r in rows
        }
        with m._auto_state_lock:
            m._auto_state["last_trigger_ts"] = None
        m._auto_check(db, lambda: make_config(), lambda t, c: alerts.append(t))
        m._drain_manual_queue()
        m._auto_check(db, lambda: make_config(), lambda t, c: alerts.append(t))
        assert any("已恢复" in a for a in alerts)
    finally:
        llm.tag_posts_llm = orig
    db.close()


def test_get_auto_status_roundtrip(monkeypatch):
    db = make_db()
    _add_mx_posts(db, 2)
    _reset_manual_state()
    _reset_auto_state()
    monkeypatch.setattr(m, "_ensure_workers_locked", lambda: None)
    _save_auto(
        db,
        specials=[
            {"name": "开盘", "start": "09:15", "end": "11:35", "threshold": 20, "interval_minutes": 5}
        ],
    )
    # 持久化 + 快照回读
    assert db.get_mx_llm_tag_auto_config()["specials"][0]["name"] == "开盘"
    status = m.get_auto_status(db)
    assert status["enabled"] is True
    assert status["regular"]["start"] == "00:00"
    assert len(status["specials"]) == 1
    # 常规时段为全天 → 当前必然命中常规
    assert status["active_period"]["kind"] == "regular"
    assert status["armed"] is True
    assert status["last_trigger_at"] is None and status["interval_due_at"] is None
    assert status["new_since_trigger"] >= 0
    db.close()


def test_auto_config_api_roundtrip():
    """管理端 API：保存/校验/回读自动打标配置（含状态接口透出）。"""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(db_path=Path(tempfile.mkdtemp()) / "auto-api.db")
    client = TestClient(app)
    client.app.state.db.add_register_code("AUTO0001")
    data = client.post(
        "/api/auth/register",
        json={"username": "autoadmin", "password": "secret123", "code": "AUTO0001"},
    ).json()
    client.app.state.db.update_user(data["user"]["id"], is_admin=True)
    headers = {"Authorization": f"Bearer {data['token']}"}

    # 初始状态：未开启
    body = client.get("/api/admin/mx-llm-tag/status", headers=headers).json()
    assert body["enabled"] is False and "regular" in body and "specials" in body

    # 保存合法配置（含特殊时间段）
    resp = client.post(
        "/api/admin/mx-llm-tag/auto-config",
        headers=headers,
        json={
            "enabled": True,
            "regular": {"start": "00:00", "end": "23:59", "threshold": 50, "interval_minutes": 30},
            "specials": [
                {"name": "开盘", "start": "09:15", "end": "11:35", "threshold": 20, "interval_minutes": 5}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["enabled"] is True

    # 回读
    body = client.get("/api/admin/mx-llm-tag/status", headers=headers).json()
    assert body["enabled"] is True and len(body["specials"]) == 1
    assert body["specials"][0]["threshold"] == 20

    # 非法配置 → 400 带具体原因
    resp = client.post(
        "/api/admin/mx-llm-tag/auto-config",
        headers=headers,
        json={
            "enabled": True,
            "regular": {"start": "10:00", "end": "09:00", "threshold": 5, "interval_minutes": 30},
            "specials": [],
        },
    )
    assert resp.status_code == 400 and "常规时间段" in resp.json()["detail"]
