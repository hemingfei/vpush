"""MX 大V实时观点：DB 层与研判管线测试。"""
import json
from pathlib import Path

from app.db import DB


def make_db() -> DB:
    import tempfile

    return DB(str(Path(tempfile.mkdtemp()) / "test.db"))


def _op(kol_id=1, ttype="topic", name="固态电池", **kw):
    base = {
        "kol_id": kol_id, "target_type": ttype, "target_name": name,
        "direction": "bull", "action": "", "confidence": "high",
        "summary": "订单爆了", "evidence_post_ids": [11], "occurred_at": "2026-09-04 09:20:30",
    }
    base.update(kw)
    return base


def test_mx_view_tables_and_snapshot_upsert():
    db = make_db()
    day = "2026-09-04"
    kol = db.add_kol("mx", "李四", "room0")
    bid = db.upsert_mx_view_batch(day, "09:20", "live")
    n = db.replace_mx_opinions(bid, [_op(kol_id=kol), _op(kol_id=kol, ttype="stock", name="XX股份", action="建仓")])
    assert n == 2
    ops = db.list_mx_opinions(day)
    assert len(ops) == 2 and ops[0]["kol_name"]  # JOIN kols 带出名字

    db.upsert_mx_view_snapshot(day, "09:20", 1, "live", {"seq": 1, "snapshot_at": "09:20"}, bid)
    db.upsert_mx_view_snapshot(day, "09:26", 2, "live", {"seq": 2, "snapshot_at": "09:26"}, bid)
    # 同刻重跑覆盖，seq 不新增行
    db.upsert_mx_view_snapshot(day, "09:20", 1, "backfill", {"seq": 1, "snapshot_at": "09:20", "v": 2}, bid)
    snaps = db.list_mx_view_snapshots(day)
    assert [s["snapshot_at"] for s in snaps] == ["09:20", "09:26"]
    assert snaps[0]["payload"]["v"] == 2
    assert db.get_mx_view_snapshot(day, "09:26")["payload"]["seq"] == 2
    assert db.mx_view_days() == [{"trading_day": day, "snapshots": 2}]


def test_list_mx_opinions_up_to_at_and_window_query():
    db = make_db()
    day = "2026-09-04"
    kol = db.add_kol("mx", "王哥", "room1")
    db.insert_post(platform="mx", kol_id=kol, external_id="m1", title="", url="",
                   content="固态电池订单爆了", published_at=f"{day} 09:18:00")
    db.insert_post(platform="mx", kol_id=kol, external_id="m2", title="", url="",
                   content="午后消息", published_at=f"{day} 09:30:00")
    posts = db.list_mx_posts_in_window(day, "09:15", "09:20", after_id=0)
    assert [p["external_id"] for p in posts] == ["m1"]
    assert db.list_mx_posts_in_window(day, "09:20", "09:26", after_id=posts[0]["id"]) == []

    bid = db.upsert_mx_view_batch(day, "09:20", "live")
    db.replace_mx_opinions(bid, [_op(kol_id=kol)])
    bid2 = db.upsert_mx_view_batch(day, "09:26", "live")
    db.replace_mx_opinions(bid2, [_op(kol_id=kol, name="房地产", direction="bear")])
    assert len(db.list_mx_opinions(day, up_to_at="09:20")) == 1
    assert len(db.list_mx_opinions(day, up_to_at="09:26")) == 2


def test_mx_view_cursor_roundtrip():
    db = make_db()
    assert db.get_mx_view_cursor() == 0
    db.set_mx_view_cursor(42)
    assert db.get_mx_view_cursor() == 42


from app.mx_view_analysis import (
    DEFAULT_MX_VIEW_SCHEDULE,
    MX_VIEW_FIRST_WINDOW_START,
    resolve_schedule,
    snapshot_windows,
)


def test_resolve_schedule_default_has_38_snapshots():
    times = resolve_schedule(DEFAULT_MX_VIEW_SCHEDULE)
    assert times[0] == "09:20" and times[1] == "09:26"
    assert "09:30" in times and "10:30" in times and "11:30" in times
    assert "12:00" in times and "13:20" in times and "15:00" in times and times[-1] == "16:00"
    assert len(times) == 38
    assert times == sorted(set(times))


def test_resolve_schedule_ignores_bad_segments_and_dedupes():
    cfg = {
        "segments": [
            {"start": "09:00", "end": "09:10", "interval_min": 5},
            {"start": "bad", "end": "10:00", "interval_min": 5},
            {"start": "10:00", "end": "10:20", "interval_min": 0},
        ],
        "extra_times": ["09:10", "xx:00", "09:10"],
    }
    assert resolve_schedule(cfg) == ["09:00", "09:05", "09:10"]


def test_snapshot_windows_first_window_starts_at_0915():
    times = resolve_schedule(DEFAULT_MX_VIEW_SCHEDULE)
    wins = snapshot_windows(times)
    assert wins[0] == (MX_VIEW_FIRST_WINDOW_START, "09:20")
    assert wins[1] == ("09:20", "09:26")
    assert wins[2] == ("09:26", "09:30")
    # 12:00 的上一快照是 11:30；16:00 的上一快照是 15:00
    assert wins[times.index("12:00")] == ("11:30", "12:00")
    assert wins[times.index("16:00")] == ("15:00", "16:00")


from app import llm as llm_mod


def test_research_viewpoints_parses_and_normalizes(monkeypatch):
    posts = [
        {"id": 11, "kol_name": "王哥", "title": "", "content": "固态电池订单爆了", "published_at": "2026-09-04 09:18:00"},
        {"id": 12, "kol_name": "李姐", "title": "", "content": "地产别碰", "published_at": "2026-09-04 09:19:00"},
    ]
    captured = {}

    def fake_chat(llm_config, messages, max_tokens, **kw):
        captured["messages"] = messages
        return (
            '{"opinions": ['
            '{"author":"王哥","target_type":"topic","target_name":"固态电池","direction":"bull",'
            '"action":"","confidence":"high","summary":"订单排到Q2","evidence":[11,99]},'
            '{"author":"李姐","target_type":"stock","target_name":"中X锂业","direction":"bear",'
            '"action":"减仓","confidence":"low","summary":"高位减一点","evidence":[12]}'
            "]}"
        )

    monkeypatch.setattr(llm_mod, "_chat", fake_chat)
    out = llm_mod.research_viewpoints(posts, ["固态电池"], ["建仓", "减仓"])
    assert out is not None and len(out) == 2
    assert out[0]["evidence"] == [11]  # 幻觉 id 99 在解析层丢弃
    assert out[1]["direction"] == "bear" and out[1]["action"] == "减仓"
    user_text = captured["messages"][1]["content"]
    assert '"id": 11' in user_text and "固态电池" in captured["messages"][0]["content"]


def test_research_viewpoints_failure_returns_none(monkeypatch):
    monkeypatch.setattr(llm_mod, "_chat", lambda *a, **k: None)
    assert llm_mod.research_viewpoints(
        [{"id": 1, "kol_name": "A", "title": "", "content": "x", "published_at": "2026-09-04 09:00:00"}],
        [], [],
    ) is None
    assert llm_mod.research_viewpoints([], [], []) == []


from app.mx_view_analysis import aggregate_day_state, validate_opinions


def _posts():
    return [
        {"id": 11, "kol_id": 1, "kol_name": "王哥", "title": "", "content": "固态电池订单爆了",
         "published_at": "2026-09-04 09:18:00"},
        {"id": 12, "kol_id": 2, "kol_name": "李姐", "title": "", "content": "中锂减持",
         "published_at": "2026-09-04 09:19:00"},
    ]


def test_validate_opinions_drops_hallucinations_and_normalizes():
    raw = [
        {"author": "王哥", "target_type": "topic", "target_name": "固态电池", "direction": "bull",
         "action": "", "confidence": "high", "summary": "订单爆了", "evidence": [11]},
        {"author": "李姐", "target_type": "stock", "target_name": "中锂", "direction": "bear",
         "action": "减仓", "confidence": "high", "summary": "高位", "evidence": [12]},
        {"author": "王哥", "target_type": "stock", "target_name": "不存在股", "direction": "bull",
         "action": "", "confidence": "high", "summary": "", "evidence": [999]},  # 幻觉 evidence
        {"author": "张三", "target_type": "topic", "target_name": "机器人", "direction": "bull",
         "action": "", "confidence": "high", "summary": "", "evidence": [11]},  # 作者不一致
        {"author": "李姐", "target_type": "stock", "target_name": "中锂", "direction": "bear",
         "action": "减仓", "confidence": "high", "summary": "重复", "evidence": [12]},  # 批内去重
    ]
    valid, new_topics = validate_opinions(
        raw, _posts(), [{"alias": "中锂", "stock": "中X锂业"}], "2026-09-04", "09:20"
    )
    assert len(valid) == 2
    assert valid[1]["target_name"] == "中X锂业"  # 黑话归一
    assert valid[0]["kol_id"] == 1 and valid[0]["evidence_post_ids"] == [11]
    assert valid[0]["snapshot_at"] == "09:20" and valid[0]["trading_day"] == "2026-09-04"
    assert new_topics == ["固态电池"]


def test_aggregate_day_state_strength_momentum_kols():
    day, at = "2026-09-04", "09:26"

    def op(snap, kol, ttype, name, direction, action="", at_occ="09:18:00", prio=0):
        return {
            "snapshot_at": snap, "kol_id": kol, "kol_name": f"大V{kol}",
            "avatar_url": "", "kol_priority": prio,
            "target_type": ttype, "target_name": name, "direction": direction,
            "action": action, "summary": "s", "occurred_at": f"2026-09-04 {at_occ}",
        }

    prev = {"topics": [{"name": "固态电池", "net": 5}], "stocks": []}
    opinions = [
        op("09:20", 1, "topic", "固态电池", "bull"),
        op("09:20", 2, "topic", "固态电池", "bull"),
        op("09:26", 1, "topic", "固态电池", "bull"),  # 同大V最新仍 bull
        op("09:20", 3, "topic", "固态电池", "bear"),
        op("09:20", 4, "stock", "XX股份", "bull", "建仓", prio=1),  # priority 加权 1.5*1.2
        op("09:20", 5, "topic", "房地产", "bear"),
        op("09:26", 5, "topic", "房地产", "bear"),  # 当前立场口径：仍 bear
        op("09:20", 6, "topic", "房地产", "bull"),  # 但 6 翻多 → net 0
    ]
    payload = aggregate_day_state(day, at, opinions, prev)
    topics = {t["name"]: t for t in payload["topics"]}
    # 当前立场口径：大V1 的两条 bull 去重为一条 → bull=2（与大V5 的 bear 去重同理）
    assert topics["固态电池"]["bull"] == 2 and topics["固态电池"]["bear"] == 1
    assert topics["固态电池"]["net"] == 1
    assert topics["固态电池"]["momentum"] == -4  # 上一快照 net=5
    stocks = {s["name"]: s for s in payload["stocks"]}
    # XX股份: w = 1 * 1.5 * 1.2 = 1.8 → strength = 50+45 = 95
    assert stocks["XX股份"]["strength"] == 95
    assert stocks["XX股份"]["actions"] == {"建仓": 1}
    assert topics["房地产"]["net"] == 0
    assert payload["trading_day"] == day and payload["snapshot_at"] == at
    assert any(k["kol_id"] == 1 for k in payload["kols"])


# ---- Task 5：批次全流程 ----

from app import mx_view_analysis as mva


def _seed_posts(db, day):
    kol = db.add_kol("mx", "王哥", "room1")
    db.insert_post(platform="mx", kol_id=kol, external_id="m1", title="", url="",
                   content="固态电池订单爆了", published_at=f"{day} 09:16:00")
    db.insert_post(platform="mx", kol_id=kol, external_id="m2", title="", url="",
                   content="看好算力", published_at=f"{day} 09:21:00")
    return kol


_VIEW_JSON = (
    '{"opinions":[{"author":"王哥","target_type":"topic","target_name":"固态电池",'
    '"direction":"bull","action":"","confidence":"high","summary":"订单爆了","evidence":[%d]}]}'
)
_SUMMARY_JSON = (
    '{"text":"早盘王哥看多固态电池。","items":[{"type":"topic","name":"固态电池",'
    '"direction":"bull"}]}'
)


def test_run_snapshot_batch_end_to_end(monkeypatch):
    db = make_db()
    day = "2026-09-04"  # 周五
    kol = _seed_posts(db, day)
    db.set_setting(mva.MX_VIEW_ENABLED_KEY, "1")
    calls = {"n": 0}

    def fake_chat(llm_config, messages, max_tokens, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _VIEW_JSON % db._rows("SELECT id FROM posts")[0]["id"]
        return _SUMMARY_JSON

    monkeypatch.setattr(mva.llm, "_chat", fake_chat)

    result = mva.run_snapshot_batch(db, day=day, snapshot_at="09:20", window=("09:15", "09:20"))
    assert result["ran"] is True and result["opinions"] == 1
    assert result["message_count"] == 1
    assert calls["n"] == 2  # 研判 + 总结
    snap = db.get_mx_view_snapshot(day, "09:20")
    assert snap["payload"]["summary"]["text"].startswith("早盘")
    assert snap["payload"]["topics"][0]["name"] == "固态电池"
    assert snap["payload"]["new_opinions"][0]["kol_id"] == kol
    assert snap["payload"]["message_count"] == 1
    assert mva.get_view_version(db) == 1  # live 批次推版本
    m1_id = db._rows("SELECT id FROM posts WHERE external_id = 'm1'")[0]["id"]
    assert db.get_mx_view_cursor() == m1_id

    # 同窗口重跑：0 条新消息 → 不落空快照、不调 LLM、版本不动
    calls["n"] = 10
    r2 = mva.run_snapshot_batch(db, day=day, snapshot_at="09:20", window=("09:15", "09:20"))
    assert r2["ran"] is False and calls["n"] == 10 and mva.get_view_version(db) == 1


def test_run_due_view_batch_catchup_and_failure(monkeypatch):
    db = make_db()
    day = "2026-09-04"
    _seed_posts(db, day)
    assert mva.run_due_view_batch(db) is None  # 未启用 → 直接短路返回 None
    db.set_setting(mva.MX_VIEW_ENABLED_KEY, "1")

    monkeypatch.setattr(mva.llm, "_chat", lambda *a, **k: None)
    try:
        mva.run_snapshot_batch(db, day=day, snapshot_at="09:20", window=("09:15", "09:20"))
        raise AssertionError("应当抛出 LLM 失败")
    except RuntimeError:
        pass
    assert mva.get_fail_count(db) == 1
    batch = db._rows("SELECT status, error FROM mx_view_batches")[0]
    assert batch["status"] == "failed" and batch["error"]
    assert db.get_mx_view_cursor() == 0  # 失败游标不动
    assert db.get_mx_view_snapshot(day, "09:20") is None  # 失败不落快照


# ---- Task 6：回填 job（按快照表重放整天） ----


def test_backfill_replays_days_without_touching_cursor_or_version(monkeypatch):
    db = make_db()
    calls = []

    def fake_batch(db_, day, snapshot_at, window, kind="live", llm_config=None, advance_cursor=True):
        calls.append((day, snapshot_at, kind, advance_cursor))
        db_.upsert_mx_view_snapshot(day, snapshot_at, 1, kind, {"snapshot_at": snapshot_at}, 0)
        return {"ran": True, "opinions": 0, "message_count": 0}

    monkeypatch.setattr(mva, "run_snapshot_batch", fake_batch)
    assert mva.start_backfill_job(db, "2026-09-03", "2026-09-04") is True
    assert mva.backfill_running() is True
    # 等线程结束（窗口总量 38×2，假函数瞬间完成）
    import time as _t

    for _ in range(100):
        if not mva.backfill_running():
            break
        _t.sleep(0.05)
    assert mva.backfill_running() is False
    days = {c[0] for c in calls}
    assert days == {"2026-09-03", "2026-09-04"}  # 都是工作日
    assert all(c[2] == "backfill" and c[3] is False for c in calls)
    assert any(c[1] == "09:20" for c in calls) and any(c[1] == "16:00" for c in calls)
    assert mva.start_backfill_job(db, "2026-09-03", "2026-09-04") is True  # 可再次启动


def test_backfill_rejects_range_over_30_days():
    db = make_db()
    assert mva.start_backfill_job(db, "2026-01-01", "2026-09-01") is False
