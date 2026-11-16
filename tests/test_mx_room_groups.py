"""MX 房间分组：表/CRUD/观点过滤/推送分组映射 + 管理/观看端 API（spec 2026-11-16）。"""
import tempfile
from pathlib import Path

import pytest

from app.db import DB


def make_db() -> DB:
    return DB(str(Path(tempfile.mkdtemp()) / "test.db"))


def _op(kol_id=1, ttype="topic", name="固态电池", **kw):
    base = {
        "kol_id": kol_id, "target_type": ttype, "target_name": name,
        "direction": "bull", "action": "", "confidence": "high",
        "summary": "订单爆了", "evidence_post_ids": [11], "occurred_at": "2026-09-04 09:20:30",
    }
    base.update(kw)
    return base


def test_group_crud_roundtrip():
    db = make_db()
    a = db.add_kol("mx", "甲", "100")
    b = db.add_kol("mx", "乙", "101")

    gid = db.create_mx_room_group("游资组", [a, b, a])  # 重复成员自动去重
    assert db.mx_room_group_member_ids(gid) == sorted({a, b})

    g = db.get_mx_room_group(gid)
    assert g["name"] == "游资组" and g["push_mode"] == "merged" and g["enabled"] == 1

    # 改名/启停/推送模式
    assert db.update_mx_room_group(gid, name="游资组2", enabled=False, push_mode="per_room")
    g = db.get_mx_room_group(gid)
    assert g["name"] == "游资组2" and g["push_mode"] == "per_room" and g["enabled"] == 0
    assert not db.update_mx_room_group(999, name="不存在")  # 不存在的组返回 False

    # 成员全量替换（单事务语义）
    assert db.replace_mx_room_group_members(gid, [a])
    assert db.mx_room_group_member_ids(gid) == [a]
    assert not db.replace_mx_room_group_members(999, [a])  # 组不存在返回 False

    # 列表：enabled_only 过滤
    assert len(db.list_mx_room_groups()) == 1
    assert len(db.list_mx_room_groups(enabled_only=True)) == 0  # 已停用

    # 删除级联清成员
    assert db.delete_mx_room_group(gid)
    assert db.list_mx_room_groups() == []
    assert not db.get_mx_room_group(gid)


def test_group_name_unique_conflict():
    db = make_db()
    db.create_mx_room_group("同组", [])
    with pytest.raises(Exception):
        db.create_mx_room_group("同组", [])


def test_list_mx_opinions_group_filter():
    """组成员观点可见、非成员不可见；无过滤参数行为不变。"""
    db = make_db()
    day = "2026-09-04"
    a = db.add_kol("mx", "甲", "100")
    b = db.add_kol("mx", "乙", "101")
    bid = db.upsert_mx_view_batch(day, "09:20", "live")
    db.replace_mx_opinions(bid, [_op(kol_id=a), _op(kol_id=b, name="算力")])

    gid = db.create_mx_room_group("只看甲", [a])
    members = db.mx_room_group_member_ids(gid)

    ops = db.list_mx_opinions(day, kol_ids=members)
    assert len(ops) == 1 and ops[0]["kol_id"] == a

    # 空集合=组无成员：语义上无观点（不出全量）
    empty_gid = db.create_mx_room_group("空组", [])
    assert db.list_mx_opinions(day, kol_ids=db.mx_room_group_member_ids(empty_gid)) == []

    # 不传 kol_ids：不过滤（既有调用零改动）
    assert len(db.list_mx_opinions(day)) == 2


def test_target_detail_group_filter():
    db = make_db()
    day = "2026-09-04"
    a = db.add_kol("mx", "甲", "100")
    b = db.add_kol("mx", "乙", "101")
    bid = db.upsert_mx_view_batch(day, "09:20", "live")
    db.replace_mx_opinions(bid, [_op(kol_id=a), _op(kol_id=b)])

    gid = db.create_mx_room_group("只看甲", [a])
    detail = db.get_mx_view_target_detail(day, "topic", "固态电池",
                                          kol_ids=db.mx_room_group_member_ids(gid))
    assert detail is not None
    # 下钻里的看多列表只有组内大V（bull 是 {count, kols} 结构）
    bull_ids = {k["kol_id"] for k in detail["bull"]["kols"]}
    assert bull_ids == {a}
    # 时间线同样只含组内大V
    assert {t["kol_id"] for t in detail["timeline"]} == {a}

    # 空组短路：不查直接 None
    empty_gid = db.create_mx_room_group("空组", [])
    assert db.get_mx_view_target_detail(day, "topic", "固态电池",
                                        kol_ids=db.mx_room_group_member_ids(empty_gid)) is None


def test_mx_merged_group_of_post():
    """推送分组映射：merged 组命中、per_room 组不命中、非组成员不命中。"""
    from app import scheduler

    scheduler._MX_GROUP_CACHE.clear()
    db = make_db()
    a = db.add_kol("mx", "甲", "100")
    b = db.add_kol("mx", "乙", "101")
    c = db.add_kol("mx", "丙", "102")  # 不进组

    merged_gid = db.create_mx_room_group("合并组", [a], push_mode="merged")
    db.create_mx_room_group("逐房组", [b], push_mode="per_room")

    assert scheduler.mx_merged_group_of_post(db, a)["id"] == merged_gid
    assert scheduler.mx_merged_group_of_post(db, b) is None  # per_room 不参与合并推送
    assert scheduler.mx_merged_group_of_post(db, c) is None

    # 停用组即刻不命中（缓存 TTL 30s 内也要失效——先清缓存再验，管理端改组走同款清法）
    db.update_mx_room_group(merged_gid, enabled=False)
    scheduler._MX_GROUP_CACHE.clear()
    assert scheduler.mx_merged_group_of_post(db, a) is None


# ---- 管理/观看端 API（TestClient 走真实 FastAPI 路由）----


def _client():
    from fastapi.testclient import TestClient

    from app.config import Config
    from app.main import create_app

    tmp = tempfile.mkdtemp()
    app = create_app(config=Config(), db_path=Path(tmp) / "groups.db")
    return TestClient(app)


def _admin_headers(client, username="groupsadmin"):
    code = "GROUPS01"
    client.app.state.db.add_register_code(code)
    resp = client.post("/api/auth/register",
                       json={"username": username, "password": "secret1234", "code": code})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    client.app.state.db.update_user(data["user"]["id"], is_admin=True)
    return {"Authorization": f"Bearer {data['token']}"}


def test_admin_group_api_crud_and_authz():
    client = _client()
    # 未登录 401 / 非管理员（未登录同口径）401
    assert client.get("/api/admin/mx-room-groups").status_code == 401

    headers = _admin_headers(client)
    db = client.app.state.db
    kid = db.add_kol("mx", "甲", "100")

    # 建组
    resp = client.post("/api/admin/mx-room-groups", headers=headers,
                       json={"name": "游资组", "member_ids": [kid], "push_mode": "merged"})
    assert resp.status_code == 200, resp.text
    gid = resp.json()["id"]

    # 重名 409
    resp = client.post("/api/admin/mx-room-groups", headers=headers,
                       json={"name": "游资组", "member_ids": []})
    assert resp.status_code == 409

    # 空名 422
    assert client.post("/api/admin/mx-room-groups", headers=headers,
                       json={"name": "  ", "member_ids": []}).status_code == 422

    # 列表带成员名明细
    resp = client.get("/api/admin/mx-room-groups", headers=headers)
    groups = resp.json()["groups"]
    assert len(groups) == 1
    assert groups[0]["name"] == "游资组"
    assert groups[0]["members"] == [{"kol_id": kid, "name": "甲", "enabled": True}]

    # 改名 + 成员替换 + 删除
    assert client.put(f"/api/admin/mx-room-groups/{gid}", headers=headers,
                      json={"name": "新名", "push_mode": "per_room"}).status_code == 200
    assert client.put(f"/api/admin/mx-room-groups/{gid}/members", headers=headers,
                      json={"member_ids": [kid]}).status_code == 200
    assert client.put("/api/admin/mx-room-groups/999", headers=headers,
                      json={"enabled": False}).status_code == 404
    assert client.delete(f"/api/admin/mx-room-groups/{gid}", headers=headers).status_code == 200
    assert client.delete(f"/api/admin/mx-room-groups/{gid}", headers=headers).status_code == 404


def test_viewer_endpoints_group_filter_and_errors():
    client = _client()
    headers = _admin_headers(client, "vieweradmin")
    db = client.app.state.db
    # 注册用户 token（观看端 get_current_user）
    code = "VIEWER01"
    db.add_register_code(code)
    r = client.post("/api/auth/register",
                    json={"username": "viewer", "password": "secret1234", "code": code})
    user_headers = {"Authorization": f"Bearer {r.json()['token']}"}

    a = db.add_kol("mx", "甲", "100")
    b = db.add_kol("mx", "乙", "101")
    day = "2026-11-16"
    bid = db.upsert_mx_view_batch(day, "09:20", "live")
    db.replace_mx_opinions(bid, [_op(kol_id=a), _op(kol_id=b, name="算力")])
    # feed 按快照 meta 拼回 seq：无 meta 的批次整批跳过，补一条快照
    db.upsert_mx_view_snapshot(day, "09:20", 1, "live",
                                {"seq": 1, "snapshot_at": "09:20"}, bid)

    gid = db.create_mx_room_group("只看甲", [a])

    # groups 列表（观看端）
    resp = client.get("/api/mx-views/groups", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json()["groups"] == [{"id": gid, "name": "只看甲", "member_count": 1}]

    # feed：无 group_id 全量；有 group_id 只下发组内；不存在的组 404
    full = client.get(f"/api/mx-views/feed?day={day}", headers=user_headers).json()
    assert sum(len(b["opinions"]) for b in full["batches"]) == 2
    scoped = client.get(f"/api/mx-views/feed?day={day}&group_id={gid}",
                        headers=user_headers).json()
    sent = [o for b in scoped["batches"] for o in b["opinions"]]
    assert len(sent) == 1 and sent[0]["kol_id"] == a
    assert client.get(f"/api/mx-views/feed?day={day}&group_id=999",
                      headers=user_headers).status_code == 404

    # target 下钻：组过滤生效
    detail = client.get(
        f"/api/mx-views/target?type=topic&name={_quote('固态电池')}&day={day}&group_id={gid}",
        headers=user_headers).json()
    assert [k["kol_id"] for k in detail["bull"]["kols"]] == [a]

    # 停用组 → 观看端 422
    db.update_mx_room_group(gid, enabled=False)
    assert client.get(f"/api/mx-views/feed?day={day}&group_id={gid}",
                      headers=user_headers).status_code == 422


def _quote(s):
    from urllib.parse import quote

    return quote(s)
