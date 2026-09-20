"""MX 大V消息操作标注：生效规则纯函数 + API 集成 + 回放集成测试。

核心场景（用户需求）：
- 管理员标注某消息为「清仓」→ 立即生效，持仓/盈亏立刻反映；
- 授权用户（后台白名单）两人标一致 → 生效；分歧不生效；
- 'none' 标注压制误判的自动信号；
- 一条消息含多笔操作（如同时清仓两只票）→ 逐标的独立标注、独立生效；
- 回放端点 /api/kols/{id}/mx-holdings 时间线出现 source=manual 事件。
"""
from datetime import datetime, timedelta

from test_api import auth_headers, make_client, user_headers

from app import mx_action_marks as mam
from app import mx_kol_holdings as mkh


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _mk(row, post_id=1, username="u", is_admin=False, updated_at="2026-01-01 00:00:00"):
    return {
        "post_id": post_id, "user_id": abs(hash(username)) % 100000,
        "username": username, "is_admin": is_admin,
        "target_name": row[0], "action": row[1], "updated_at": updated_at, "id": 1,
    }


CFG = {"usernames": ["alice", "bob"], "agree_n": 2}


# ---------- 纯函数：生效规则 ----------

def test_resolve_admin_mark_takes_effect_immediately():
    """管理员独裁：单个管理员标注即生效（无视一致人数）。"""
    marks = [_mk(("赛力斯", "清仓"), username="admin1", is_admin=True)]
    eff = mam.resolve_effective_marks(marks, CFG)
    assert eff[1] == [{"target_name": "赛力斯", "action": "清仓", "by_admin": True, "voters": ["admin1"]}]


def test_resolve_latest_admin_wins():
    """多管理员不一致：最近更新者优先（updated_at 最大）。"""
    marks = [
        _mk(("赛力斯", "清仓"), username="a1", is_admin=True, updated_at="2026-01-01 10:00:00"),
        _mk(("赛力斯", "减仓"), username="a2", is_admin=True, updated_at="2026-01-02 10:00:00"),
    ]
    eff = mam.resolve_effective_marks(marks, CFG)
    assert eff[1][0]["action"] == "减仓"
    assert eff[1][0]["by_admin"] is True


def test_resolve_agree_n_users_effective():
    """授权用户两人同标 → 生效；一人不生效。"""
    one = [_mk(("赛力斯", "清仓"), username="alice")]
    assert 1 not in mam.resolve_effective_marks(one, CFG)
    two = one + [_mk(("赛力斯", "清仓"), username="bob")]
    eff = mam.resolve_effective_marks(two, CFG)
    assert eff[1][0]["action"] == "清仓"
    assert eff[1][0]["by_admin"] is False
    assert sorted(eff[1][0]["voters"]) == ["alice", "bob"]


def test_resolve_multi_target_marks_independent():
    """一帖多标：同一帖不同标的各自独立生效（清仓两只票互不影响）。"""
    marks = [
        _mk(("赛力斯", "清仓"), username="alice"),
        _mk(("赛力斯", "清仓"), username="bob"),
        _mk(("比亚迪", "清仓"), username="alice"),
        # 比亚的第二票未达标
    ]
    eff = mam.resolve_effective_marks(marks, CFG)
    assert eff[1] == [{"target_name": "赛力斯", "action": "清仓", "by_admin": False,
                       "voters": ["alice", "bob"]}]
    # 两票都达标 → 两条各自生效
    marks.append(_mk(("比亚迪", "清仓"), username="bob"))
    eff = mam.resolve_effective_marks(marks, CFG)
    assert {e["target_name"] for e in eff[1]} == {"赛力斯", "比亚迪"}


def test_resolve_one_target_conflict_other_target_unaffected():
    """一帖多标：某标的存在分歧只压制该标的，另一标的的生效不受牵连。"""
    marks = [
        _mk(("赛力斯", "清仓"), username="alice"),
        _mk(("赛力斯", "清仓"), username="bob"),
        _mk(("比亚迪", "减仓"), username="alice"),
        _mk(("比亚迪", "减仓"), username="bob"),
        _mk(("比亚迪", "清仓"), username="carol"),
        _mk(("比亚迪", "清仓"), username="dave"),
    ]
    cfg = {"usernames": ["alice", "bob", "carol", "dave"], "agree_n": 2}
    eff = mam.resolve_effective_marks(marks, cfg)
    # 赛力斯一致生效；比亚迪分歧（减仓 vs 清仓两组都达标）不生效
    assert [e["target_name"] for e in eff[1]] == ["赛力斯"]


def test_resolve_conflict_groups_not_effective():
    """分歧：同标的两操作组都达标 → 该标的生效，等管理员定夺。"""
    marks = [
        _mk(("赛力斯", "清仓"), username="alice"),
        _mk(("赛力斯", "清仓"), username="bob"),
        _mk(("赛力斯", "减仓"), username="carol"),
        _mk(("赛力斯", "减仓"), username="dave"),
    ]
    cfg = {"usernames": ["alice", "bob", "carol", "dave"], "agree_n": 2}
    assert 1 not in mam.resolve_effective_marks(marks, cfg)


def test_resolve_only_one_reached_group_effective():
    """一组达标另一组未达 → 达标组生效（多数意见优先）。"""
    marks = [
        _mk(("赛力斯", "清仓"), username="alice"),
        _mk(("赛力斯", "清仓"), username="bob"),
        _mk(("赛力斯", "减仓"), username="carol"),
    ]
    eff = mam.resolve_effective_marks(marks, CFG)
    assert eff[1][0]["action"] == "清仓"


def test_resolve_revoked_user_not_counted():
    """被移出白名单的旧标注不再计数（悬置而非删除）。"""
    marks = [
        _mk(("赛力斯", "清仓"), username="alice"),
        _mk(("赛力斯", "清仓"), username="bob"),
        _mk(("赛力斯", "减仓"), username="eve"),
    ]
    # bob 被移出白名单 → 只剩 alice 一票不达标
    cfg = {"usernames": ["alice"], "agree_n": 2}
    assert 1 not in mam.resolve_effective_marks(marks, cfg)
    # eve 不在白名单，其减仓票从不计数
    cfg2 = {"usernames": ["alice", "bob", "eve"], "agree_n": 2}
    eff = mam.resolve_effective_marks(marks, cfg2)
    assert eff[1][0]["action"] == "清仓"


def test_resolve_none_action_can_be_effective():
    """'none'（非操作）标注同样走一致生效，供回放压制自动信号。"""
    marks = [
        _mk(("赛力斯", "none"), username="alice"),
        _mk(("赛力斯", "none"), username="bob"),
    ]
    eff = mam.resolve_effective_marks(marks, CFG)
    assert eff[1][0]["action"] == "none"


def test_config_validation_and_roundtrip():
    """配置校验：人数区间 2~10、用户不存在拒绝；保存后读回一致。"""
    client = make_client()
    db = client.app.state.db
    # 默认配置
    cfg = mam.get_mark_config(db)
    assert cfg == {"usernames": [], "agree_n": 2}
    # 用户不存在
    clean, err = mam.save_mark_config(db, ["幽灵用户"], 3)
    assert clean is None and "用户不存在" in err
    # 人数越界
    _, err = mam.save_mark_config(db, [], 1)
    assert "之间" in err
    _, err = mam.save_mark_config(db, [], 11)
    assert "之间" in err
    # 合法保存（先造真实用户）
    db._execute(
        "INSERT INTO users (username, password_hash, is_admin, created_at) "
        "VALUES ('marker1', 'x', 0, datetime('now'))"
    )
    clean, err = mam.save_mark_config(db, ["marker1", "marker1"], 3)
    assert err is None
    assert clean == {"usernames": ["marker1"], "agree_n": 3}
    assert mam.get_mark_config(db) == clean


# ---------- API + 回放集成 ----------

def _setup_mark_env(client):
    """造 1 管理员 + 3 普通用户，白名单放 alice/bob，返回各 headers。"""
    admin = auth_headers(client)
    alice = user_headers(client, "mark_alice")
    bob = user_headers(client, "mark_bob")
    nobody = user_headers(client, "mark_nobody")
    resp = client.put("/api/admin/mx-action-marks/config", headers=admin,
                      json={"usernames": ["mark_alice", "mark_bob"], "agree_n": 2})
    assert resp.status_code == 200, resp.text
    return admin, alice, bob, nobody


def _seed_post(db, kol_id, content, published_at):
    db.insert_post(platform="mx", kol_id=kol_id, external_id=f"p{kol_id}_{published_at}",
                   title="", url="", content=content, published_at=published_at)
    return db._rows("SELECT id FROM posts ORDER BY id DESC")[0]["id"]


def _seed_opinion(db, kol_id, post_id, day, at, name, direction, action):
    bid = db.upsert_mx_view_batch(day, at, "live")
    db.replace_mx_opinions(bid, [{
        "trading_day": day, "snapshot_at": at, "kol_id": kol_id,
        "target_type": "stock", "target_name": name, "direction": direction,
        "action": action, "confidence": "high", "summary": f"{name} {action or direction}",
        "evidence_post_ids": [post_id], "occurred_at": f"{day} {at}:00",
    }])


def test_api_admin_mark_immediately_effective():
    """管理员标注清仓 → 立即生效：时间线出现 manual 清仓事件，持仓剔除。"""
    client = make_client()
    db = client.app.state.db
    admin, *_ = _setup_mark_env(client)
    kol = db.add_kol("mx", "标注大V", "room1")
    t = _today()
    p1 = _seed_post(db, kol, "赛力斯建仓", f"{t} 09:30:00")
    _seed_opinion(db, kol, p1, t, "09:35", "赛力斯", "bull", "建仓")
    p2 = _seed_post(db, kol, "赛力斯清仓了", f"{t} 14:30:00")
    # 无标注：赛力斯在持仓
    out = mkh.build_kol_holdings(db, kol)
    assert any(h["target_name"] == "赛力斯" for h in out["holdings"])
    # 管理员标注 p2 为清仓
    resp = client.post(f"/api/posts/{p2}/action-mark", headers=admin,
                       json={"target_name": "赛力斯", "action": "清仓"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["effective"] == [
        {"target_name": "赛力斯", "action": "清仓", "by_admin": True, "voters": ["testadmin"]}]
    out = mkh.build_kol_holdings(db, kol)
    assert all(h["target_name"] != "赛力斯" for h in out["holdings"])
    manual = [e for e in out["timeline"] if e["source"] == "manual"]
    assert manual and manual[0]["kind"] == "clear"


def test_api_two_users_agree_effective():
    """授权用户两人同标生效；一人未生效。"""
    client = make_client()
    db = client.app.state.db
    admin, alice, bob, nobody = _setup_mark_env(client)
    kol = db.add_kol("mx", "投票大V", "room1")
    t = _today()
    p = _seed_post(db, kol, "清仓完毕", f"{t} 14:00:00")
    p_open = _seed_post(db, kol, "建仓", f"{t} 09:00:00")
    _seed_opinion(db, kol, p_open, t, "09:05", "贵州茅台", "bull", "建仓")
    # 无权用户 403
    resp = client.post(f"/api/posts/{p}/action-mark", headers=nobody,
                       json={"target_name": "贵州茅台", "action": "清仓"})
    assert resp.status_code == 403
    # alice 一票：生效为空
    resp = client.post(f"/api/posts/{p}/action-mark", headers=alice,
                       json={"target_name": "贵州茅台", "action": "清仓"})
    assert resp.status_code == 200
    assert resp.json()["effective"] == []
    assert mkh.build_kol_holdings(db, kol)["holdings"]
    # bob 同标 → 生效，持仓剔除
    resp = client.post(f"/api/posts/{p}/action-mark", headers=bob,
                       json={"target_name": "贵州茅台", "action": "清仓"})
    assert resp.json()["effective"][0]["action"] == "清仓"
    out = mkh.build_kol_holdings(db, kol)
    assert all(h["target_name"] != "贵州茅台" for h in out["holdings"])


def test_api_none_mark_suppresses_false_positive():
    """'none' 标注压制误判：管理员标非操作 → 误提的建仓观点不再推仓。"""
    client = make_client()
    db = client.app.state.db
    admin, *_ = _setup_mark_env(client)
    kol = db.add_kol("mx", "误判大V", "room1")
    t = _today()
    p = _seed_post(db, kol, "聊聊天", f"{t} 10:00:00")
    p2 = _seed_post(db, kol, "再聊聊", f"{t} 16:00:00")
    _seed_opinion(db, kol, p, t, "10:05", "比亚迪", "bull", "建仓")
    # 无关帖的看多表态兜底，保证压制后 holdings 非空可断言「比亚迪被剔除」
    _seed_opinion(db, kol, p2, t, "16:05", "隆基", "bull", "")
    assert any(h["target_name"] == "比亚迪" for h in mkh.build_kol_holdings(db, kol)["holdings"])
    resp = client.post(f"/api/posts/{p}/action-mark", headers=admin,
                       json={"target_name": "比亚迪", "action": "none"})
    assert resp.status_code == 200
    assert resp.json()["effective"][0]["action"] == "none"
    out = mkh.build_kol_holdings(db, kol)
    assert out is not None  # 隆基表态仍在
    assert all(h["target_name"] != "比亚迪" for h in out["holdings"])


def test_api_validation_and_delete():
    """非法操作词/全市场名单外股票 400；DELETE 撤标回放还原；弹窗数据含权限与词表。

    个股校验口径与打标管线一致（常用表+全市场−排除项）：常用表外的
    全市场正式名（如 工业富联）可标注，不存在/拼错的名字仍 400。
    """
    client = make_client()
    db = client.app.state.db
    admin, alice, *_ = _setup_mark_env(client)
    kol = db.add_kol("mx", "校验大V", "room1")
    t = _today()
    p = _seed_post(db, kol, "随便", f"{t} 10:00:00")
    # 非法操作词
    resp = client.post(f"/api/posts/{p}/action-mark", headers=admin,
                       json={"target_name": "贵州茅台", "action": "梭哈"})
    assert resp.status_code == 400
    # 名单外股票（黑话走别名归一，仍不在全市场正式名内）
    resp = client.post(f"/api/posts/{p}/action-mark", headers=admin,
                       json={"target_name": "不存在的股票", "action": "建仓"})
    assert resp.status_code == 400
    # 非 MX 帖 400
    other_kol = db.add_kol("xueqiu", "雪球大V", "x1")
    pid = _seed_post(db, other_kol, "雪球帖", f"{t} 10:00:00")
    db._execute("UPDATE posts SET platform='xueqiu' WHERE id = ?", (pid,))
    resp = client.post(f"/api/posts/{pid}/action-mark", headers=admin,
                       json={"target_name": "贵州茅台", "action": "建仓"})
    assert resp.status_code == 400
    # 正常标注 → 弹窗数据
    resp = client.post(f"/api/posts/{p}/action-mark", headers=alice,
                       json={"target_name": "贵州茅台", "action": "建仓"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_mark"] is True and data["is_admin"] is False
    assert data["my_marks"] == [{"target_name": "贵州茅台", "action": "建仓"}]
    assert "清仓" in data["actions"] and "none" in data["actions"]
    # DELETE 撤标（不带标的 = 全撤）
    resp = client.delete(f"/api/posts/{p}/action-mark", headers=alice)
    assert resp.status_code == 200
    assert resp.json()["my_marks"] == [] and resp.json()["marks"] == []
    # 再删 404
    assert client.delete(f"/api/posts/{p}/action-mark", headers=alice).status_code == 404
    # 管理员撤他人标注
    resp = client.post(f"/api/posts/{p}/action-mark", headers=alice,
                       json={"target_name": "贵州茅台", "action": "建仓"})
    resp = client.delete(f"/api/posts/{p}/action-mark?user_id="
                         f"{db.get_user_by_username_ci('mark_alice')['id']}", headers=admin)
    assert resp.status_code == 200


def test_api_multi_target_mark_and_delete_one():
    """一帖多标：同帖多标的各自保存/生效；DELETE 带标的只撤一条，其余保留。

    marks 行带 user_id/is_mine（前端逐条撤销按钮的归属判断依据）。
    """
    client = make_client()
    db = client.app.state.db
    admin, alice, *_ = _setup_mark_env(client)
    kol = db.add_kol("mx", "多标大V", "room1")
    t = _today()
    p = _seed_post(db, kol, "赛力斯和比亚迪都清仓了", f"{t} 14:00:00")
    # 同帖两个标的
    resp = client.post(f"/api/posts/{p}/action-mark", headers=admin,
                       json={"target_name": "赛力斯", "action": "清仓"})
    assert resp.status_code == 200
    assert resp.json()["effective"] == [
        {"target_name": "赛力斯", "action": "清仓", "by_admin": True, "voters": ["testadmin"]}]
    resp = client.post(f"/api/posts/{p}/action-mark", headers=admin,
                       json={"target_name": "比亚迪", "action": "清仓"})
    assert resp.status_code == 200
    data = resp.json()
    # 两条都生效（管理员直判各自独立）
    assert {e["target_name"] for e in data["effective"]} == {"赛力斯", "比亚迪"}
    assert len(data["marks"]) == 2
    assert data["my_marks"] == [{"target_name": "赛力斯", "action": "清仓"},
                                {"target_name": "比亚迪", "action": "清仓"}]
    # marks 行的归属标记：管理员视角全 is_mine；alice 视角全不是
    assert all(m["is_mine"] for m in data["marks"])
    other = client.get(f"/api/posts/{p}/action-mark", headers=alice).json()
    assert other["marks"] and all(not m["is_mine"] for m in other["marks"])
    assert all(int(m["user_id"]) == db.get_user_by_username_ci("testadmin")["id"]
               for m in other["marks"])
    # 回放：两条 manual 清仓事件都注入
    _seed_opinion(db, kol, p, t, "14:05", "赛力斯", "bull", "建仓")
    _seed_opinion(db, kol, p, t, "14:05", "比亚迪", "bull", "建仓")
    out = mkh.build_kol_holdings(db, kol)
    manual = [e for e in out["timeline"] if e["source"] == "manual"]
    assert {e["target_name"] for e in manual} == {"赛力斯", "比亚迪"}
    assert all(h["target_name"] not in ("赛力斯", "比亚迪") for h in out["holdings"])
    # 带标的撤销：只撤赛力斯，比亚迪保留
    resp = client.delete(f"/api/posts/{p}/action-mark?target_name=赛力斯", headers=admin)
    assert resp.status_code == 200
    data = resp.json()
    assert data["my_marks"] == [{"target_name": "比亚迪", "action": "清仓"}]
    assert {e["target_name"] for e in data["effective"]} == {"比亚迪"}
    # 撤不存在的标的 404
    resp = client.delete(f"/api/posts/{p}/action-mark?target_name=隆基", headers=admin)
    assert resp.status_code == 404


def test_api_auto_tags_in_modal_payload():
    """弹窗数据带 auto_tags（消息上的自动标签）与 llm_tagged，供人工对照。"""
    client = make_client()
    db = client.app.state.db
    admin, *_ = _setup_mark_env(client)
    kol = db.add_kol("mx", "自动标大V", "room1")
    t = _today()
    p = _seed_post(db, kol, "清仓赛力斯", f"{t} 14:00:00")
    db.update_post_tags(p, ["清仓", "赛力斯"])
    resp = client.get(f"/api/posts/{p}/action-mark", headers=admin)
    assert resp.status_code == 200
    data = resp.json()
    assert data["auto_tags"] == ["清仓", "赛力斯"]
    assert data["llm_tagged"] is False  # update_post_tags 不置 LLM 标记
    # 未打标消息 auto_tags 为空
    p2 = _seed_post(db, kol, "没标签", f"{t} 15:00:00")
    data = client.get(f"/api/posts/{p2}/action-mark", headers=admin).json()
    assert data["auto_tags"] == []


def test_api_universe_stock_name_accepted():
    """常用表外的全市场正式名可标注：校验口径与打标管线一致。

    帖子标签按宽口径（常用表+全市场）打冷门股名，标注弹窗的输入建议
    即来自这些标签；校验若按常用表窄口径会报「不是名单内正式名」。
    """
    client = make_client()
    db = client.app.state.db
    admin, *_ = _setup_mark_env(client)
    kol = db.add_kol("mx", "宽口径大V", "room1")
    t = _today()
    p = _seed_post(db, kol, "工业富联建仓", f"{t} 10:00:00")
    # 前置：工业富联确为全市场正式名且不在常用表（新装库默认名单）
    assert "工业富联" not in set(db.get_stock_names())
    resp = client.post(f"/api/posts/{p}/action-mark", headers=admin,
                       json={"target_name": "工业富联", "action": "建仓"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["my_marks"][0]["target_name"] == "工业富联"
    assert resp.json()["effective"][0]["action"] == "建仓"
    # 管理员排除项仍然拦截：排除后同名校注 400（口径含「−排除项」）
    db.set_stock_names(list(db.get_stock_names()) + ["工业富联"])
    db.set_stock_name_exclusions(["工业富联"])
    resp = client.post(f"/api/posts/{p}/action-mark", headers=admin,
                       json={"target_name": "工业富联", "action": "建仓"})
    assert resp.status_code == 400


def test_api_me_flag_and_feed_attach():
    """/api/me 带 can_mx_action_mark；feed 帖子带 mx_mark 角标数据。"""
    client = make_client()
    db = client.app.state.db
    admin, alice, _, nobody = _setup_mark_env(client)
    me = client.get("/api/me", headers=alice).json()
    assert me["can_mx_action_mark"] is True
    me = client.get("/api/me", headers=nobody).json()
    assert me["can_mx_action_mark"] is False
    me = client.get("/api/me", headers=admin).json()
    assert me["can_mx_action_mark"] is True
    # feed（需订阅可见）：管理员标了 → 帖子带 effective 角标
    kol = db.add_kol("mx", "角标大V", "room1")
    db.add_subscription(db.get_user_by_username_ci("mark_nobody")["id"], kol)
    t = _today()
    p = _seed_post(db, kol, "清仓", f"{t} 15:00:00")
    resp = client.post(f"/api/posts/{p}/action-mark", headers=admin,
                       json={"target_name": "贵州茅台", "action": "清仓"})
    assert resp.status_code == 200
    feed = client.get("/api/my/feed", headers=nobody).json()
    row = next((x for x in feed if int(x["id"]) == int(p)), None)
    assert row is not None, "帖子未出现在 feed（订阅或可见性拦截？）"
    assert row.get("mx_mark") and row["mx_mark"]["effective"][0]["action"] == "清仓"


def test_api_remark_updates_effective():
    """改标即覆盖（upsert）：bob 从减仓改为清仓后与 alice 达成一致。"""
    client = make_client()
    db = client.app.state.db
    _, alice, bob, _ = _setup_mark_env(client)
    kol = db.add_kol("mx", "改标大V", "room1")
    t = _today()
    p = _seed_post(db, kol, "清仓", f"{t} 15:00:00")
    client.post(f"/api/posts/{p}/action-mark", headers=alice,
                json={"target_name": "贵州茅台", "action": "清仓"})
    resp = client.post(f"/api/posts/{p}/action-mark", headers=bob,
                       json={"target_name": "贵州茅台", "action": "减仓"})
    assert resp.json()["effective"] == []  # 分歧
    resp = client.post(f"/api/posts/{p}/action-mark", headers=bob,
                       json={"target_name": "贵州茅台", "action": "清仓"})
    assert resp.json()["effective"][0]["action"] == "清仓"


def test_manual_event_reopens_after_clear():
    """人工清仓后，后续标签建仓正确重开仓（manual 事件不压制他人跨日的信号）。"""
    client = make_client()
    db = client.app.state.db
    admin, *_ = _setup_mark_env(client)
    kol = db.add_kol("mx", "重开大V", "room1")
    t = _today()
    t2 = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    p1 = _seed_post(db, kol, "建仓", f"{t2} 09:00:00")
    _seed_opinion(db, kol, p1, t2, "09:05", "贵州茅台", "bull", "建仓")
    p2 = _seed_post(db, kol, "清仓", f"{t2} 11:00:00")
    resp = client.post(f"/api/posts/{p2}/action-mark", headers=admin,
                       json={"target_name": "贵州茅台", "action": "清仓"})
    assert resp.status_code == 200
    out = mkh.build_kol_holdings(db, kol)
    assert all(h["target_name"] != "贵州茅台" for h in out["holdings"])
    # 次日另一帖的建仓标签（走 tag 源）：manual 清仓不压制，重开仓
    p3 = _seed_post(db, kol, "又建仓了", f"{t} 13:00:00")
    db.update_post_tags(p3, ["建仓", "贵州茅台"])
    out = mkh.build_kol_holdings(db, kol)
    assert any(h["target_name"] == "贵州茅台" for h in out["holdings"])


def test_admin_config_endpoints():
    """admin 配置端点：GET/PUT 往返；非管理员 403；未知用户 400。"""
    client = make_client()
    admin, alice, _, _ = _setup_mark_env(client)
    resp = client.get("/api/admin/mx-action-marks/config", headers=admin)
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["agree_n"] == 2 and "mark_alice" in cfg["usernames"]
    # 普通用户 403
    assert client.get("/api/admin/mx-action-marks/config", headers=alice).status_code == 403
    # 未知用户 400
    resp = client.put("/api/admin/mx-action-marks/config", headers=admin,
                      json={"usernames": ["ghost"], "agree_n": 2})
    assert resp.status_code == 400
    # 保存合法值 + 最近标注列表
    resp = client.put("/api/admin/mx-action-marks/config", headers=admin,
                      json={"usernames": ["mark_alice"], "agree_n": 3})
    assert resp.status_code == 200
    db = client.app.state.db
    kol = db.add_kol("mx", "列表大V", "room1")
    t = _today()
    p = _seed_post(db, kol, "清仓", f"{t} 15:00:00")
    client.post(f"/api/posts/{p}/action-mark", headers=admin,
                json={"target_name": "贵州茅台", "action": "清仓"})
    resp = client.get("/api/admin/mx-action-marks", headers=admin)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items and items[0]["effective"]["action"] == "清仓"
    assert items[0]["kol_name"] == "列表大V"
