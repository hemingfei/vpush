"""MX 大V预估持仓：回放推演逻辑 + 用户端 API 测试。"""
from datetime import datetime, timedelta

from test_api import auth_headers, make_client

from app import mx_kol_holdings as mkh


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def _seed_opinions(db, kol_id, rows):
    """rows: [(day, at, occurred_hhmm, ttype, name, direction, action)]"""
    post_id = None
    for day, at, hhmm, ttype, name, direction, action in rows:
        if post_id is None:
            db.insert_post(platform="mx", kol_id=kol_id, external_id=f"p{kol_id}",
                           title="", url="", content=f"消息 {name}", published_at=f"{day} {hhmm}:00")
            post_id = db._rows("SELECT id FROM posts ORDER BY id DESC")[0]["id"]
        bid = db.upsert_mx_view_batch(day, at, "live")
        db.replace_mx_opinions(bid, [{
            "trading_day": day, "snapshot_at": at, "kol_id": kol_id,
            "target_type": ttype, "target_name": name, "direction": direction,
            "action": action, "confidence": "high", "summary": f"{name} {action or direction}",
            "evidence_post_ids": [post_id], "occurred_at": f"{day} {hhmm}:00",
        }])


def test_replay_open_add_trim_clear():
    """建仓→加仓→减仓→清仓全流程：时间线 kind 判定 + 清仓后不入持仓。"""
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "测试大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "贵州茅台", "bull", "加仓"),
        (t, "13:30", "13:26", "stock", "贵州茅台", "bull", "减仓"),
        (t, "14:30", "14:26", "stock", "贵州茅台", "bear", "清仓"),
    ])
    out = mkh.build_kol_holdings(db, kol)
    kinds = [e["kind"] for e in out["timeline"]]
    assert kinds == ["clear", "trim", "add", "open"]  # 最新在前
    assert all(h["target_name"] != "贵州茅台" for h in out["holdings"])  # 清仓剔除


def test_replay_flip_to_bear_trims():
    """同标的多→空且无操作词：翻空减仓，跌破阈值后出持仓。"""
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "测试大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "中科曙光", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "中科曙光", "bear", ""),  # 翻空无操作
    ])
    out = mkh.build_kol_holdings(db, kol)
    assert out["timeline"][0]["kind"] == "flip"
    # 建仓 3.0 - 翻空 2.0 = 1.0 ≥ 阈值：仍在持仓（减仓而非清仓）
    assert [h["target_name"] for h in out["holdings"]] == ["中科曙光"]


def test_replay_stale_position_exits():
    """沉默超 STALE_DAYS 天：按了结剔除。"""
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "test-stale", "room1")
    _seed_opinions(db, kol, [
        (_days_ago(mkh.STALE_DAYS + 3), "09:20", "09:16", "stock", "老股票", "bull", "建仓"),
        (_today(), "09:20", "09:16", "stock", "新股票", "bull", "建仓"),
    ])
    out = mkh.build_kol_holdings(db, kol)
    names = [h["target_name"] for h in out["holdings"]]
    assert names == ["新股票"]


def test_replay_topics_separate_from_stocks():
    """题材观点不入个股持仓，走 topics 单列；权重归一化合计 100%。"""
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "测试大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "宁德时代", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "中际旭创", "bull", "建仓"),
        (t, "11:20", "11:15", "topic", "AI算力", "bull", ""),
    ])
    out = mkh.build_kol_holdings(db, kol)
    assert [h["target_name"] for h in out["holdings"]] == ["宁德时代", "中际旭创"]
    assert out["holdings"][0]["weight"] == out["holdings"][1]["weight"] == 50.0
    assert [x["target_name"] for x in out["topics"]] == ["AI算力"]


def test_api_returns_holdings_and_empty_state():
    """端点：正常返回结构 + 无观点大V回空结构 + 非 MX 平台 400 + 未登录 401。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "API大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
    ])
    resp = client.get(f"/api/kols/{kol}/mx-holdings", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["kol"]["name"] == "API大V"
    assert data["timeline"][0]["kind"] == "open"
    assert data["holdings"][0]["target_name"] == "贵州茅台"
    assert data["holdings"][0]["weight"] == 100.0
    assert data["window_days"] == 30

    # 无观点：空结构不是 404
    kol2 = db.add_kol("mx", "空大V", "room2")
    empty = client.get(f"/api/kols/{kol2}/mx-holdings", headers=headers).json()
    assert empty["holdings"] == [] and empty["timeline"] == [] and empty["opinion_count"] == 0

    # 非平台大V 400；不存在 404；days 钳位
    kol3 = db.add_kol("weibo", "微博大V", "w1")
    assert client.get(f"/api/kols/{kol3}/mx-holdings", headers=headers).status_code == 400
    assert client.get("/api/kols/99999/mx-holdings", headers=headers).status_code == 404
    clamped = client.get(f"/api/kols/{kol}/mx-holdings?days=365", headers=headers).json()
    assert clamped["window_days"] == 90
    assert client.get(f"/api/kols/{kol}/mx-holdings").status_code == 401
