"""持股研判用户端 API 测试：CRUD 校验、用户隔离、相关观点窗口/聚合/增量。"""
import json
from datetime import datetime, timedelta

from test_api import auth_headers, make_client, user_headers

from app.mx_view_analysis import CN_TZ


def _ts(**delta) -> str:
    return (datetime.now(CN_TZ) + timedelta(**delta)).strftime("%Y-%m-%d %H:%M:%S")


_batch_seq = 0


def _add_opinion(db, kol_id, ttype, name, direction, occurred, summary="摘要",
                 evidence=None, action=""):
    """直插一条研判观点（批次号自增避让 (batch_id, kol_id, type, name) 唯一约束）。"""
    global _batch_seq
    _batch_seq += 1
    return db._execute(
        "INSERT INTO mx_opinions (batch_id, trading_day, snapshot_at, kol_id, target_type, "
        "target_name, direction, action, confidence, summary, evidence_post_ids, occurred_at) "
        "VALUES (?, ?, '09:20', ?, ?, ?, ?, ?, 'high', ?, ?, ?)",
        (_batch_seq, occurred[:10], kol_id, ttype, name, direction, action, summary,
         json.dumps(evidence or []), occurred),
    )


def _mk_post(db, kol_id, external_id, content, published_at):
    db.insert_post(platform="mx", kol_id=kol_id, external_id=external_id, title="", url="",
                   content=content, published_at=published_at)
    return db._rows("SELECT id FROM posts WHERE external_id = ?", (external_id,))[0]["id"]


def test_holdings_crud_validation_and_isolation():
    client = make_client()
    admin = auth_headers(client)
    other = user_headers(client, "holdings_other")

    r = client.post("/api/my/holdings", headers=admin,
                    json={"target_type": "stock", "target_name": " 贵 州 茅 台 ", "note": " 白酒 "})
    assert r.status_code == 201
    row = r.json()
    # 个股名按全市场名单口径归一后落库，备注 trim
    assert row["target_name"] == "贵州茅台" and row["note"] == "白酒"

    # 重复（归一后撞唯一约束）409；同名不同类型可并存
    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "stock", "target_name": "贵州茅台"}).status_code == 409
    topic_row = client.post("/api/my/holdings", headers=admin,
                            json={"target_type": "topic", "target_name": "贵州茅台"}).json()

    # 校验：名单外个股 / 空题材 / 非法类型 / 超长名
    assert "未收录" in client.post(
        "/api/my/holdings", headers=admin,
        json={"target_type": "stock", "target_name": "不存在的股票"}).json()["detail"]
    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "topic", "target_name": "   "}).status_code == 400
    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "weird", "target_name": "x"}).status_code == 400
    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "topic", "target_name": "x" * 41}).status_code == 400

    # 改名 = 换标的：整体重新校验；note 部分更新
    r = client.patch(f"/api/my/holdings/{row['id']}", headers=admin,
                     json={"target_name": "宁德时代", "note": "改备注"})
    assert r.status_code == 200 and r.json()["target_name"] == "宁德时代"
    # 类型+名称整体校验后与已有持股撞唯一约束 → 409
    r = client.patch(f"/api/my/holdings/{topic_row['id']}", headers=admin,
                     json={"target_type": "stock", "target_name": "宁德时代"})
    assert r.status_code == 409
    # 空体 PATCH 返回现值
    r = client.patch(f"/api/my/holdings/{row['id']}", headers=admin, json={})
    assert r.status_code == 200 and r.json()["note"] == "改备注"
    # 不存在的持股 404
    assert client.patch("/api/my/holdings/99999", headers=admin,
                        json={"note": "x"}).status_code == 404

    # 隔离：他人 PATCH/DELETE 一律 404；未登录 401
    assert client.patch(f"/api/my/holdings/{row['id']}", headers=other,
                        json={"note": "x"}).status_code == 404
    assert client.delete(f"/api/my/holdings/{row['id']}", headers=other).status_code == 404
    assert client.get("/api/my/holdings").status_code == 401
    assert client.post("/api/my/holdings",
                       json={"target_type": "topic", "target_name": "x"}).status_code == 401

    # 删除 204，再删 404；列表只剩 topic 那条
    assert client.delete(f"/api/my/holdings/{row['id']}", headers=admin).status_code == 204
    assert client.delete(f"/api/my/holdings/{row['id']}", headers=admin).status_code == 404
    rest = [(h["target_type"], h["target_name"])
            for h in client.get("/api/my/holdings", headers=admin).json()]
    assert rest == [("topic", "贵州茅台")]


def test_holdings_limit_30():
    client = make_client()
    admin = auth_headers(client)
    for i in range(30):
        r = client.post("/api/my/holdings", headers=admin,
                        json={"target_type": "topic", "target_name": f"题材{i:02d}"})
        assert r.status_code == 201, r.text
    r = client.post("/api/my/holdings", headers=admin,
                    json={"target_type": "topic", "target_name": "第31条"})
    assert r.status_code == 400 and "30" in r.json()["detail"]


def test_holdings_suggestions():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "王哥", "room1")
    _add_opinion(db, kol, "topic", "可控核聚变", "bull", _ts(days=-1))

    stocks = client.get("/api/my/holdings/suggestions?type=stock&q=茅",
                        headers=admin).json()["items"]
    assert stocks[0] == {"name": "贵州茅台", "extra": "600519"}  # 常用名在前并带代码
    assert len(stocks) <= 20

    recent = client.get("/api/my/holdings/suggestions?type=topic&q=聚变",
                        headers=admin).json()["items"]
    assert {"name": "可控核聚变"} in recent  # 近 90 天研判产出过的题材
    hints = client.get("/api/my/holdings/suggestions?type=topic&q=AI",
                       headers=admin).json()["items"]
    assert {"name": "AI算力"} in hints  # 内置词表兜底

    assert client.get("/api/my/holdings/suggestions?type=bad",
                      headers=admin).status_code == 422
    assert client.get("/api/my/holdings/suggestions?type=stock").status_code == 401


def test_holdings_views_window_summary_holder_and_evidence_cap():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "王哥", "room1")
    ev_ids = [_mk_post(db, kol, f"p{i}", f"原帖{i}", _ts(hours=-2)) for i in range(1, 5)]

    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "stock", "target_name": "贵州茅台"}).status_code == 201
    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "topic", "target_name": "AI算力"}).status_code == 201

    _add_opinion(db, kol, "stock", "贵州茅台", "bull", _ts(hours=-1), "批价回暖", ev_ids)
    _add_opinion(db, kol, "stock", "贵州茅台", "bear", _ts(days=-2), "批价松动")
    _add_opinion(db, kol, "topic", "AI算力", "neutral", _ts(hours=-3), "中性观察")
    _add_opinion(db, kol, "stock", "贵州茅台", "bull", _ts(days=-40), "一个月窗口外")
    _add_opinion(db, kol, "stock", "中际旭创", "bull", _ts(hours=-1), "未持有标的")

    data = client.get("/api/my/holdings/views", headers=admin).json()
    assert data["window_days"] == 30
    # occurred_at 倒序；40 天前与未持有标的都不出现
    assert [(it["target_type"], it["target_name"], it["direction"]) for it in data["items"]] == [
        ("stock", "贵州茅台", "bull"),
        ("topic", "AI算力", "neutral"),
        ("stock", "贵州茅台", "bear"),
    ]
    targets = {(t["target_type"], t["target_name"]): t for t in data["summary"]["targets"]}
    assert targets[("stock", "贵州茅台")]["bull"] == 1
    assert targets[("stock", "贵州茅台")]["bear"] == 1
    assert targets[("stock", "贵州茅台")]["total"] == 2
    assert targets[("topic", "AI算力")]["neutral"] == 1
    assert set(targets) == {("stock", "贵州茅台"), ("topic", "AI算力")}
    assert data["max_id"] == db.max_mx_opinion_id_any()
    # 证据原帖内联且封顶 3 条（种了 4 条）
    newest = data["items"][0]
    assert len(newest["evidence"]) == 3
    assert newest["evidence"][0]["content"] == "原帖1" and newest["evidence"][0]["author"] == "王哥"
    assert newest["kol_name"] == "王哥"

    # holder 只过滤 items，summary 恒为全窗口口径；非法 holder 422
    held = client.get("/api/my/holdings/views?holder=stock:贵州茅台", headers=admin).json()
    assert {it["target_name"] for it in held["items"]} == {"贵州茅台"}
    assert held["summary"] == data["summary"]
    assert client.get("/api/my/holdings/views?holder=junk", headers=admin).status_code == 422
    # 无持股用户空态
    other = user_headers(client, "views_other")
    empty = client.get("/api/my/holdings/views", headers=other).json()
    assert empty["items"] == [] and empty["summary"]["targets"] == []
    assert client.get("/api/my/holdings/views").status_code == 401


def test_holdings_views_after_id_increment_and_pagination():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "王哥", "room1")
    client.post("/api/my/holdings", headers=admin,
                json={"target_type": "topic", "target_name": "固态电池"})
    first = _add_opinion(db, kol, "topic", "固态电池", "bull", _ts(hours=-2), "旧观点")
    second = _add_opinion(db, kol, "topic", "固态电池", "bear", _ts(hours=-1), "新观点")

    full = client.get("/api/my/holdings/views", headers=admin).json()
    assert [it["id"] for it in full["items"]] == [second, first]
    assert full["max_id"] == second

    # after_id 增量：只回游标之后的相关观点，并带当前全局 max_id
    inc = client.get(f"/api/my/holdings/views?after_id={first}", headers=admin).json()
    assert [it["id"] for it in inc["items"]] == [second]
    assert inc["max_id"] == second
    none = client.get(f"/api/my/holdings/views?after_id={second}", headers=admin).json()
    assert none["items"] == [] and none["max_id"] == second

    # before_id 翻旧页：按 id 游标取更旧一页
    page1 = client.get("/api/my/holdings/views?limit=1", headers=admin).json()
    assert [it["id"] for it in page1["items"]] == [second]
    page2 = client.get(f"/api/my/holdings/views?limit=1&before_id={second}",
                       headers=admin).json()
    assert [it["id"] for it in page2["items"]] == [first]


def test_holdings_tag_posts_window_direction_holder_and_pagination():
    """标签快讯流：窗口过滤、方向角标、holder 下钻、翻页与增量、参数校验。"""
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "王哥", "room1")

    def _mk_tagged(external_id, tags, published_at, direction_tag=""):
        pid = _mk_post(db, kol, external_id, f"正文{external_id}", published_at)
        db.update_post_tags(pid, tags)
        if direction_tag:
            db.record_applied_tag(pid, direction_tag, "stock", source="mx_view",
                                  direction="bull")
        return pid

    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "stock", "target_name": "贵州茅台"}).status_code == 201
    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "topic", "target_name": "AI算力"}).status_code == 201

    # 按时间旧→新入库（posts.id 随发帖递增，与线上到达序一致）
    p_both = _mk_tagged("t3", ["贵州茅台", "AI算力"], _ts(hours=-3))
    p_topic = _mk_tagged("t2", ["AI算力"], _ts(hours=-2))
    p_bull = _mk_tagged("t1", ["贵州茅台", "白酒"], _ts(hours=-1), direction_tag="贵州茅台")
    _mk_tagged("t4", ["中际旭创"], _ts(hours=-1))  # 未持有标的：不命中
    _mk_tagged("t5", ["贵州茅台"], _ts(days=-40))  # 窗口外

    data = client.get("/api/my/holdings/tag-posts", headers=admin).json()
    assert data["window_days"] == 30
    # published_at 倒序；窗口外与未持有标的都不出现；一帖多标的按持股清单序全列（新添加在前）
    assert [(it["id"], it["target_names"]) for it in data["items"]] == [
        (p_bull, ["贵州茅台"]),
        (p_topic, ["AI算力"]),
        (p_both, ["AI算力", "贵州茅台"]),
    ]
    # 方向取观点回流登记（首个命中标的的登记）；无登记为空
    assert data["items"][0]["direction"] == "bull"
    assert data["items"][1]["direction"] == ""
    assert data["items"][0]["kol_name"] == "王哥"
    assert data["items"][0]["content"].startswith("正文t1")
    assert data["max_id"] == db.max_post_id_any()
    # 聚合：恒全量口径；同名股票/题材计数各自成立
    targets = {(t["target_type"], t["target_name"]): t["tag_count"]
               for t in data["summary"]["targets"]}
    assert targets[("stock", "贵州茅台")] == 2
    assert targets[("topic", "AI算力")] == 2

    # holder 只过滤 items，summary 恒为全窗口口径；非法 holder 422
    held = client.get("/api/my/holdings/tag-posts?holder=stock:贵州茅台",
                      headers=admin).json()
    assert {it["target_names"][0] for it in held["items"]} == {"贵州茅台"}
    assert held["summary"] == data["summary"]
    assert client.get("/api/my/holdings/tag-posts?holder=junk",
                      headers=admin).status_code == 422

    # before_id 翻旧页 / after_id 增量（posts.id 游标；水位含未命中标的的全局帖）
    page1 = client.get("/api/my/holdings/tag-posts?limit=1", headers=admin).json()
    assert [it["id"] for it in page1["items"]] == [p_bull]
    page2 = client.get(f"/api/my/holdings/tag-posts?limit=2&before_id={p_bull}",
                       headers=admin).json()
    assert [it["id"] for it in page2["items"]] == [p_topic, p_both]
    inc = client.get(f"/api/my/holdings/tag-posts?after_id={p_topic}",
                     headers=admin).json()
    assert [it["id"] for it in inc["items"]] == [p_bull]
    # 游标推到最新已命中帖后：未命中的 t4/t5 不出现，但水位照全局帖推进
    none = client.get(f"/api/my/holdings/tag-posts?after_id={p_bull}",
                      headers=admin).json()
    assert none["items"] == []
    assert none["max_id"] == db.max_post_id_any() > p_bull

    # 无持股用户空态；未登录 401
    other = user_headers(client, "tag_posts_other")
    empty = client.get("/api/my/holdings/tag-posts", headers=other).json()
    assert empty["items"] == [] and empty["summary"]["targets"] == []
    assert client.get("/api/my/holdings/tag-posts").status_code == 401


def test_holdings_views_summary_kols_and_actions():
    """总览卡数据：summary 附带去重大V名单（计数不受截断影响）与操作词统计。"""
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    k1 = db.add_kol("mx", "王哥", "room1")
    k2 = db.add_kol("mx", "李哥", "room2")

    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "stock", "target_name": "贵州茅台"}).status_code == 201
    assert client.post("/api/my/holdings", headers=admin,
                       json={"target_type": "topic", "target_name": "AI算力"}).status_code == 201

    # 王哥：茅台 2 看多（1 条带建仓）+ 1 看空；李哥：茅台 1 看多（带加仓）
    _add_opinion(db, k1, "stock", "贵州茅台", "bull", _ts(hours=-1), "批价回暖", action="建仓")
    _add_opinion(db, k1, "stock", "贵州茅台", "bull", _ts(hours=-2), "继续看好")
    _add_opinion(db, k1, "stock", "贵州茅台", "bear", _ts(hours=-3), "批价松动")
    _add_opinion(db, k2, "stock", "贵州茅台", "bull", _ts(hours=-4), "跟随", action="加仓")
    # 王哥 40 天前的看空：窗口外，不进聚合
    _add_opinion(db, k1, "stock", "贵州茅台", "bear", _ts(days=-40), "窗口外")
    # 名单截断：13 位大V看多 AI算力 → 名单截前 12、计数仍 13
    for i in range(13):
        ki = db.add_kol("mx", f"大V{i:02d}", f"airoom{i}")
        _add_opinion(db, ki, "topic", "AI算力", "bull", _ts(hours=-1), f"观点{i}")

    data = client.get("/api/my/holdings/views", headers=admin).json()
    targets = {(t["target_type"], t["target_name"]): t for t in data["summary"]["targets"]}

    mt = targets[("stock", "贵州茅台")]
    assert (mt["bull"], mt["bear"], mt["total"]) == (3, 1, 4)  # 观点口径不含窗口外
    assert mt["kols"]["count"] == 2  # 去重大V（王哥跨方向只计一次）
    assert (mt["kols"]["bull"], mt["kols"]["bear"], mt["kols"]["neutral"]) == (2, 1, 0)
    # 名单按该标的观点数降序：王哥(3) > 李哥(1)
    assert mt["kols"]["bull_names"] == ["王哥", "李哥"]
    assert mt["kols"]["bear_names"] == ["王哥"]
    assert mt["actions"] == {"建仓": 1, "加仓": 1}  # 次数同则按词序稳定

    ai = targets[("topic", "AI算力")]
    assert ai["kols"]["count"] == 13 and ai["kols"]["bull"] == 13
    assert len(ai["kols"]["bull_names"]) == 12  # 截前 12，计数不受影响
    assert ai["actions"] == {}
    # 无观点标的不进 summary（前端自行兜底空结构）
    client.post("/api/my/holdings", headers=admin,
                json={"target_type": "topic", "target_name": "液冷"})
    names = {(t["target_type"], t["target_name"])
             for t in client.get("/api/my/holdings/views", headers=admin).json()["summary"]["targets"]}
    assert ("topic", "液冷") not in names
