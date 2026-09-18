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


def _seed_tag_posts(db, kol_id, rows):
    """rows: [(day, hhmm, tags, content)]——直接落带标签的 MX 消息。

    标签配对要求个股在常用股票名单内（黑话/名单外不判仓），把用到的
    测试股名一并写入名单。
    """
    extra = {t for _, _, tags, _ in rows for t in tags
             if t not in db.get_action_tag_vocabulary()}
    names = list(dict.fromkeys([*db.get_stock_names(), *extra]))
    db.set_stock_names(names)
    for i, (day, hhmm, tags, content) in enumerate(rows):
        db.insert_post(platform="mx", kol_id=kol_id, external_id=f"tagp{i}",
                       title="", url="", content=content,
                       published_at=f"{day} {hhmm}:00", tags=tags)


def test_tag_events_fill_when_opinion_missing():
    """标签补位：消息带操作标签但观点研判没覆盖该标的时，按标签推仓。

    - 观点只研判了 贵州茅台（建仓），标签帖覆盖 中科曙光（加仓）→ 后者经标签入持仓；
    - 标签行 source=tag；同标同操作多帖去重只记一条。
    """
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "标签大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
    ])
    _seed_tag_posts(db, kol, [
        (t, "10:00", ["中科曙光", "加仓"], "中科曙光又加了一笔"),
        (t, "10:30", ["中科曙光", "加仓"], "继续加仓中科曙光（同操作去重）"),
        (t, "11:00", ["宁德时代", "清仓"], "宁德时代全部出了"),
    ])
    out = mkh.build_kol_holdings(db, kol)
    names = {h["target_name"]: h for h in out["holdings"]}
    assert set(names) == {"贵州茅台", "中科曙光"}  # 清仓不入持仓
    tag_rows = [e for e in out["timeline"] if e["source"] == "tag"]
    assert len(tag_rows) == 2  # 中科曙光两条加仓去重成一条 + 宁德清仓
    assert tag_rows[0]["kind"] == "clear" and tag_rows[0]["target_name"] == "宁德时代"
    # 无先前头寸的首条加仓：记持仓态（kind=hold）、按加仓力度 2 分入仓
    assert tag_rows[1]["kind"] == "hold" and tag_rows[1]["target_name"] == "中科曙光"
    assert names["中科曙光"]["score"] == 2.0


def test_tag_events_yield_to_same_day_opinion_actions():
    """同标当日观点已给操作词：标签让位不重复加减仓。"""
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "让位大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "中科曙光", "bull", "建仓"),
        (t, "14:20", "14:15", "stock", "中科曙光", "bull", "加仓"),
    ])
    _seed_tag_posts(db, kol, [
        (t, "10:00", ["中科曙光", "加仓"], "上午聊过加仓（被观点让位）"),
        (t, "15:00", ["中科曙光", "减仓"], "尾盘减仓（观点当日已有操作，也让位）"),
    ])
    out = mkh.build_kol_holdings(db, kol)
    # 仅观点两条事件：建仓 3 + 加仓 2 = 5；标签减仓被同日观点操作顶掉
    assert [h["score"] for h in out["holdings"] if h["target_name"] == "中科曙光"] == [5.0]
    assert all(e["source"] == "opinion" for e in out["timeline"])


def test_semanticless_opinion_action_does_not_suppress_tag():
    """词表外操作（观察/做T）不参与打分，也不参与压制——回归：
    旧实现把所有非空 action 都登记进让位日，「观察」观点会吞掉同日标签的
    真实建仓信号，该股从持仓里凭空消失。
    """
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "观察大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "中科曙光", "bull", "观察"),  # 无仓位语义
    ])
    _seed_tag_posts(db, kol, [
        (t, "10:00", ["中科曙光", "建仓"], "标签识别出真实建仓"),
    ])
    out = mkh.build_kol_holdings(db, kol)
    # 标签建仓不被「观察」压制：看多表态 1 分（观察性轻仓）+ 标签建仓 3 分 = 4
    assert [h["score"] for h in out["holdings"] if h["target_name"] == "中科曙光"] == [4.0]
    # 标签事件在场（未被观点让位丢弃）：已有头寸后的建仓按加仓力度计
    tag_rows = [e for e in out["timeline"] if e["source"] == "tag"]
    assert len(tag_rows) == 1 and tag_rows[0]["kind"] == "add"


def test_tag_only_kol_without_opinions():
    """纯标签大V：没有任何观点数据，仅靠操作标签也能推出演练仓位。"""
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "纯标签大V", "room1")
    _seed_tag_posts(db, kol, [
        (_today(), "09:16", ["老白干酒", "建仓"], "老白干酒建仓了"),
        (_today(), "10:16", ["老白干酒", "高抛"], "老白干酒高抛部分"),
    ])
    out = mkh.build_kol_holdings(db, kol)
    assert out is not None
    assert [h["target_name"] for h in out["holdings"]] == ["老白干酒"]
    kinds = {e["kind"]: e["source"] for e in out["timeline"]}
    assert kinds == {"open": "tag", "trim": "tag"}


def test_tag_events_skip_ambiguous_multi_stock_posts():
    """一帖命中超过 3 只个股时操作归属含糊：整帖跳过不配对。"""
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "歧义大V", "room1")
    _seed_tag_posts(db, kol, [
        (_today(), "09:16", ["贵州茅台", "宁德时代", "中科曙光", "中际旭创", "建仓"],
         "一帖聊了四只票"),
    ])
    out = mkh.build_kol_holdings(db, kol)
    assert out is None  # 无有效事件：返回 None（API 层转空态）


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


def test_tag_vocab_cache_invalidates_on_content_change():
    """词表缓存以 settings 原文为版本键：内容不变命中缓存，改名单即刻生效。"""
    client = make_client()
    db = client.app.state.db
    db.set_stock_names(["贵州茅台"])
    a1 = mkh._load_tag_vocab(db)
    # 同内容再次加载：命中缓存（同一对象身份），零重建
    assert mkh._load_tag_vocab(db) is a1
    # 名单变化：缓存失效重建，新股名可见
    db.set_stock_names(["贵州茅台", "五粮液"])
    a2 = mkh._load_tag_vocab(db)
    assert a2 is not a1 and "五粮液" in a2[1]
    # 操作词表变化同样失效
    db.set_setting("action_tag_vocabulary", '["建仓", "加仓", "自定义词"]')
    a3 = mkh._load_tag_vocab(db)
    assert a3 is not a2 and "自定义词" in a3[0]
