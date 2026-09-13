"""智囊团观点回流打标：apply_view_tags 分流/幂等/防清理/防回填覆盖测试。"""
import json
from pathlib import Path

from app import mx_view_tagging
from app.db import DB
from app.mx_view_analysis import run_snapshot_batch
from app.tagging import backfill_post_tags, run_tag_maintenance


def make_db() -> DB:
    import tempfile

    return DB(str(Path(tempfile.mkdtemp()) / "test.db"))


def _op(kol_id, name, ttype="stock", direction="bull", action="", confidence="high", evidence=None):
    return {
        "kol_id": kol_id, "target_type": ttype, "target_name": name,
        "direction": direction, "action": action, "confidence": confidence,
        "summary": "s", "evidence_post_ids": evidence or [1], "occurred_at": "2026-09-06 09:40:00",
    }


def _setup(db, *, stock="宁德时代", content="宁德时代订单爆了，准备建仓"):
    kol = db.add_kol("mx", "李四", "room0")
    pid = db.insert_post(
        platform="mx", kol_id=kol, external_id="m1", title="", url="",
        content=content, published_at="2026-09-06 09:38:00",
    )
    if stock:
        db.set_stock_names([stock])
    return kol, pid


def test_known_stock_high_writes_and_registers_direction():
    db = make_db()
    kol, pid = _setup(db)
    summary = mx_view_tagging.apply_view_tags(
        db, [_op(kol, "宁德时代", action="建仓", evidence=[pid])], topic_hints=["固态电池"],
    )
    assert summary["posts"] == 1 and summary["applied"] == 2  # 股票 + 操作
    tags = db.get_post_tags(pid)
    assert "宁德时代" in tags and "建仓" in tags
    # 不置 llm_tagged：不偷 LLM 打标游标的帖子
    row = db._rows("SELECT llm_tagged FROM posts WHERE id = ?", (pid,))[0]
    assert not row["llm_tagged"]
    assert db.count_mx_pending_total() == 1  # LLM 打标队列仍视其为待打标
    rows = db._rows("SELECT tag, kind, status, source, direction FROM post_tag_reviews")
    by_tag = {r["tag"]: r for r in rows}
    assert by_tag["宁德时代"]["source"] == "mx_view"
    assert by_tag["宁德时代"]["direction"] == "bull"
    assert by_tag["宁德时代"]["status"] == "applied"
    assert by_tag["建仓"]["kind"] == "action"
    assert by_tag["建仓"]["direction"] == "bull"


def test_unknown_stock_goes_to_review_not_direct_write():
    db = make_db()
    kol, pid = _setup(db, stock="")  # 名单为空
    summary = mx_view_tagging.apply_view_tags(
        db, [_op(kol, "赛博努巴", evidence=[pid])], topic_hints=[],
    )
    assert summary["applied"] == 0 and summary["reviews"] == 1
    assert "赛博努巴" not in db.get_post_tags(pid)
    row = db.list_tag_reviews(status="pending")[0]
    assert row["tag"] == "赛博努巴" and row["kind"] == "stock" and row["source"] == "mx_view"
    assert row["direction"] == "bull"  # 待审行也带观点方向，审核时可见看多/看空


def test_low_confidence_never_direct_writes():
    db = make_db()
    kol, pid = _setup(db)
    summary = mx_view_tagging.apply_view_tags(
        db, [_op(kol, "宁德时代", confidence="low", evidence=[pid])], topic_hints=[],
    )
    assert summary["applied"] == 0 and summary["reviews"] == 1
    assert "宁德时代" not in db.get_post_tags(pid)


def test_topic_hint_gate():
    db = make_db()
    kol, pid = _setup(db, stock="")
    hints = ["固态电池"]
    mx_view_tagging.apply_view_tags(db, [_op(kol, "固态电池", ttype="topic", evidence=[pid])], topic_hints=hints)
    assert "固态电池" in db.get_post_tags(pid)
    # 新题材：跳过（题材候选审核流负责），不直写也不进标签审核
    summary = mx_view_tagging.apply_view_tags(
        db, [_op(kol, "商业航天", ttype="topic", evidence=[pid])], topic_hints=hints,
    )
    assert summary == {"posts": 0, "applied": 0, "reviews": 0}
    assert "商业航天" not in db.get_post_tags(pid)
    assert db.list_tag_reviews() == []


def test_replay_is_idempotent_and_direction_refreshes():
    db = make_db()
    kol, pid = _setup(db)
    first = mx_view_tagging.apply_view_tags(
        db, [_op(kol, "宁德时代", evidence=[pid])], topic_hints=[],
    )
    assert first["applied"] == 1
    # 回填重放同批观点：标签不重复，登记行不新增
    mx_view_tagging.apply_view_tags(db, [_op(kol, "宁德时代", evidence=[pid])], topic_hints=[])
    assert db.get_post_tags(pid).count("宁德时代") == 1
    assert len(db._rows("SELECT id FROM post_tag_reviews")) == 1
    # 立场翻转后的新观点覆盖同帖同标签：方向刷成最新
    mx_view_tagging.apply_view_tags(
        db, [_op(kol, "宁德时代", direction="bear", evidence=[pid])], topic_hints=[],
    )
    row = db._rows("SELECT direction FROM post_tag_reviews")[0]
    assert row["direction"] == "bear"


def test_multi_evidence_and_dedupe_across_opinions():
    db = make_db()
    kol = db.add_kol("mx", "王哥", "room1")
    p1 = db.insert_post(platform="mx", kol_id=kol, external_id="m1", title="", url="",
                        content="利好宁德时代", published_at="2026-09-06 09:38:00")
    p2 = db.insert_post(platform="mx", kol_id=kol, external_id="m2", title="", url="",
                        content="宁王又爆单", published_at="2026-09-06 09:39:00")
    db.set_stock_names(["宁德时代"])
    mx_view_tagging.apply_view_tags(
        db,
        [_op(kol, "宁德时代", evidence=[p1, p2]), _op(kol, "宁德时代", action="加仓", evidence=[p1])],
        topic_hints=[],
    )
    for pid, want in ((p1, ["宁德时代", "加仓"]), (p2, ["宁德时代"])):
        assert db.get_post_tags(pid) == want
    # 两条观点同引 p1 且同打宁德时代：同帖同标签只留一条登记
    assert len(db._rows("SELECT id FROM post_tag_reviews WHERE post_id = ? AND tag = '宁德时代'", (p1,))) == 1
    assert len(db._rows("SELECT id FROM post_tag_reviews WHERE tag = '加仓'")) == 1


def test_disabled_by_default_and_switch_roundtrip():
    db = make_db()
    assert mx_view_tagging.get_view_tagging_enabled(db) is False
    mx_view_tagging.set_view_tagging_enabled(db, True)
    assert mx_view_tagging.get_view_tagging_enabled(db) is True
    mx_view_tagging.set_view_tagging_enabled(db, False)
    assert mx_view_tagging.get_view_tagging_enabled(db) is False


def test_cleanup_stale_tags_keeps_topic_hints():
    """每日维护不得清掉回流打上的题材标签（题材参考表不在打标词表里）。"""
    db = make_db()
    kol = db.add_kol("mx", "李四", "room0")
    pid = db.insert_post(platform="mx", kol_id=kol, external_id="m1", title="", url="",
                         content="固态电池线爆发", published_at="2026-09-06 09:38:00")
    db.update_post_tags(pid, ["固态电池", "过期的标签"])
    run_tag_maintenance(db, llm_config=None)
    assert db.get_post_tags(pid) == ["固态电池"]


def test_cleanup_stale_tags_keeps_action_tags():
    """每日维护不得清掉操作标签：LLM 打标与观点回流都会把建仓/减仓写上帖。"""
    db = make_db()
    kol = db.add_kol("mx", "李四", "room0")
    pid = db.insert_post(platform="mx", kol_id=kol, external_id="m1", title="", url="",
                         content="宁德时代建仓", published_at="2026-09-06 09:38:00")
    db.update_post_tags(pid, ["建仓", "做T", "过期的标签"])
    run_tag_maintenance(db, llm_config=None)
    assert db.get_post_tags(pid) == ["建仓", "做T"]


def test_backfill_all_protects_view_tagged_posts():
    db = make_db()
    kol = db.add_kol("mx", "李四", "room0")
    protected = db.insert_post(platform="mx", kol_id=kol, external_id="m1", title="", url="",
                               content="宁德时代订单爆了", published_at="2026-09-06 09:38:00")
    plain = db.insert_post(platform="mx", kol_id=kol, external_id="m2", title="", url="",
                           content="聊聊宏观", published_at="2026-09-06 09:39:00")
    db.set_stock_names(["宁德时代"])
    db.set_setting("tag_vocabulary", json.dumps([{"tag": "宏观", "keywords": ["宏观"]}], ensure_ascii=False))
    mx_view_tagging.apply_view_tags(db, [_op(kol, "宁德时代", evidence=[protected])], topic_hints=[])
    backfill_post_tags(db, "all")
    # 有回流标签的帖原样保留；无回流标签的帖按当前规则重算
    assert db.get_post_tags(protected) == ["宁德时代"]
    assert db.get_post_tags(plain) == ["宏观"]


def test_record_applied_tag_upgrades_pending():
    db = make_db()
    kol, pid = _setup(db, stock="")
    db.add_pending_tag_review(pid, "赛博努巴", "stock", "low")
    db.record_applied_tag(pid, "赛博努巴", "stock", source="mx_view", direction="bull")
    row = db._rows("SELECT status, confidence, direction FROM post_tag_reviews")[0]
    assert row["status"] == "applied" and row["confidence"] == "high" and row["direction"] == "bull"


def test_day_stats_and_attach_directions():
    db = make_db()
    kol, pid = _setup(db)
    mx_view_tagging.apply_view_tags(db, [_op(kol, "宁德时代", evidence=[pid])], topic_hints=[])
    from datetime import datetime, timezone, timedelta

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    stats = db.mx_view_tag_day_stats(today)
    assert stats["applied"] >= 1
    posts = db.list_posts(limit=10, with_view_directions=True)
    assert posts[0]["view_directions"].get("宁德时代") == "bull"
    # 不带参数时不附方向（打标回填等内部遍历不受影响）
    assert "view_directions" not in db.list_posts(limit=10)[0]


def test_pending_tags_attached_with_direction_and_dropped_after_reject():
    """待审标签提示性下发：pending 附到帖子行（带方向/来源），拒绝后不再下发。"""
    db = make_db()
    kol, pid = _setup(db)
    mx_view_tagging.apply_view_tags(
        db, [_op(kol, "宁德时代", confidence="low", direction="bear", evidence=[pid])], topic_hints=[],
    )
    # 待审标签附到帖子行：用户侧实时可见，带方向与来源
    rows = db.attach_pending_tags([{"id": pid}])
    pending = rows[0]["pending_tags"]
    assert len(pending) == 1
    assert pending[0]["tag"] == "宁德时代" and pending[0]["direction"] == "bear"
    assert pending[0]["source"] == "mx_view" and pending[0]["confidence"] == "low"
    # 待审方向也进入 view_directions（方向角标在待审标签上同样可用）
    assert db.attach_view_directions([{"id": pid}])[0]["view_directions"].get("宁德时代") == "bear"
    # 审核拒绝：pending 下发与方向都撤掉
    review_id = db.list_tag_reviews(status="pending")[0]["id"]
    db.set_tag_review_status(review_id, "rejected")
    assert db.attach_pending_tags([{"id": pid}])[0]["pending_tags"] == []
    assert "宁德时代" not in db.attach_view_directions([{"id": pid}])[0]["view_directions"]


def test_run_snapshot_batch_applies_tags_when_enabled(monkeypatch):
    """挂钩集成：开关开启时快照批次把研判观点回写证据帖标签，关闭时不写。"""
    db = make_db()
    kol = db.add_kol("mx", "李四", "room0")
    pid1 = db.insert_post(platform="mx", kol_id=kol, external_id="m1", title="", url="",
                          content="宁德时代订单爆了", published_at="2026-09-06 09:38:00")
    pid2 = db.insert_post(platform="mx", kol_id=kol, external_id="m2", title="", url="",
                          content="午后宁德时代继续拉", published_at="2026-09-06 09:44:00")
    db.set_stock_names(["宁德时代"])
    db.set_setting("mx_view_enabled", "1")

    def fake_research(posts, *a, **k):
        return [
            {"author": "李四", "target_type": "stock", "target_name": "宁德时代",
             "direction": "bull", "action": "建仓", "confidence": "high",
             "summary": "订单", "evidence": [p["id"] for p in posts]},
        ]

    monkeypatch.setattr("app.llm.research_viewpoints", fake_research)
    monkeypatch.setattr("app.llm._chat", lambda *a, **k: "")

    day = "2026-09-06"
    run_snapshot_batch(db, day=day, snapshot_at="09:40", window=("09:15", "09:40"))
    assert db.get_mx_view_cursor() == pid1
    assert "宁德时代" not in db.get_post_tags(pid1)  # 默认关：不写

    mx_view_tagging.set_view_tagging_enabled(db, True)
    run_snapshot_batch(db, day=day, snapshot_at="09:45", window=("09:40", "09:45"))
    assert db.get_mx_view_cursor() == pid2
    tags = db.get_post_tags(pid2)
    assert "宁德时代" in tags and "建仓" in tags  # 开启后：研判观点回流上帖
    assert "宁德时代" not in db.get_post_tags(pid1)  # 开关前的历史批次不回溯
    rows = db._rows(
        "SELECT direction FROM post_tag_reviews WHERE post_id = ? AND tag = '宁德时代'",
        (pid2,),
    )
    assert rows and rows[0]["direction"] == "bull"
