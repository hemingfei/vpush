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
