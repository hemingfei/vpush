"""大V持股汇总 API 测试：聚合端点四榜口径、范围隔离、窗口参数、鉴权。

口径与术语见 CONTEXT.md「大V持股/共同进攻/割肉清仓」。
"""
import json
from datetime import datetime, timedelta

from test_api import auth_headers, make_client

from app import kol_holdings_summary as khs
from app.mx_view_analysis import CN_TZ, holdings_kol_ids


def _ts(**delta) -> str:
    return (datetime.now(CN_TZ) + timedelta(**delta)).strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now(CN_TZ).strftime("%Y-%m-%d")


def _seed_opinions(db, kol_id, rows):
    """rows: [(day, hhmm, ttype, name, direction, action)]。

    批次号带 kol_id 序号错开：replace_mx_opinions 是整批替换，两大V共用同一
    (trading_day, snapshot_at) 批次时后写的会清掉先写的观点（生产一批本就含
    多大V，插桩必须按大V分批才贴近真实批次结构）。
    """
    post_id = None
    for day, hhmm, ttype, name, direction, action in rows:
        if post_id is None:
            db.insert_post(platform="mx", kol_id=kol_id, external_id=f"kp{kol_id}",
                           title="", url="", content=f"消息 {name}", published_at=f"{day} {hhmm}:00")
            post_id = db._rows("SELECT id FROM posts ORDER BY id DESC")[0]["id"]
        bid = db.upsert_mx_view_batch(day, f"{hhmm}x{kol_id}", "live")
        db.replace_mx_opinions(bid, [{
            "trading_day": day, "snapshot_at": hhmm, "kol_id": kol_id,
            "target_type": ttype, "target_name": name, "direction": direction,
            "action": action, "confidence": "high", "summary": f"{name} {action or direction}",
            "evidence_post_ids": [post_id], "occurred_at": f"{day} {hhmm}:00",
        }])


def test_kol_summary_requires_login_and_validates_window():
    client = make_client()
    assert client.get("/api/my/holdings/kol-summary").status_code == 401
    headers = auth_headers(client)
    assert client.get("/api/my/holdings/kol-summary?days=15", headers=headers).status_code == 422
    r = client.get("/api/my/holdings/kol-summary", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["window_days"] == 30
    for key in ("heavy", "attack", "topics", "clears", "generated_at"):
        assert key in body


def test_kol_summary_heavy_ranking_and_kol_list():
    """重仓票按持有大V人数降序（同数按名称稳定序），行内带大V摘要名单。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    t = _today()
    k1 = db.add_kol("mx", "共振大V", "r1")
    k2 = db.add_kol("mx", "重仓大V", "r2")
    k3 = db.add_kol("mx", "独票大V", "r3")
    _seed_opinions(db, k1, [(t, "09:20", "stock", "贵州茅台", "bull", "建仓")])
    _seed_opinions(db, k2, [(t, "09:30", "stock", "贵州茅台", "bull", "建仓")])
    _seed_opinions(db, k3, [(t, "09:40", "stock", "中科曙光", "bull", "建仓")])

    body = client.get("/api/my/holdings/kol-summary", headers=headers).json()
    heavy = body["heavy"]
    assert [row["target_name"] for row in heavy][:2] == ["贵州茅台", "中科曙光"]
    assert heavy[0]["kol_count"] == 2
    kols = {k["kol_id"]: k for k in heavy[0]["kols"]}
    assert set(kols) == {k1, k2}
    assert kols[k1]["name"] == "共振大V"
    assert heavy[1]["kol_count"] == 1


def test_kol_summary_attack_requires_two_kols():
    """共同进攻：≥2 位大V对同一票建仓/加仓才上榜，单人动作不上榜。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    t = _today()
    k1 = db.add_kol("mx", "进攻大V一", "a1")
    k2 = db.add_kol("mx", "进攻大V二", "a2")
    _seed_opinions(db, k1, [
        (t, "09:20", "stock", "五粮液", "bull", "建仓"),
        (t, "09:30", "stock", "中科曙光", "bull", "建仓"),
    ])
    _seed_opinions(db, k2, [(t, "10:00", "stock", "五粮液", "bull", "加仓")])
    _seed_opinions(db, db.add_kol("mx", "减仓大V", "a3"),
                   [(t, "10:30", "stock", "中科曙光", "bear", "减仓")])

    body = client.get("/api/my/holdings/kol-summary", headers=headers).json()
    attack = body["attack"]
    names = [row["target_name"] for row in attack]
    assert names == ["五粮液"]  # 中科曙光是一买一减：非共振，不上榜
    assert attack[0]["kol_count"] == 2
    assert attack[0]["last_at"] and attack[0]["last_at"].startswith(t)


def test_kol_summary_topics_aggregate():
    """题材方向：各大V题材关注按人数聚合，按人数降序。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    t = _today()
    k1 = db.add_kol("mx", "题材大V一", "tp1")
    k2 = db.add_kol("mx", "题材大V二", "tp2")
    _seed_opinions(db, k1, [
        (t, "09:20", "topic", "AI算力", "bull", ""),
        (t, "09:21", "topic", "可控核聚变", "bull", ""),
    ])
    _seed_opinions(db, k2, [(t, "09:30", "topic", "AI算力", "bull", "")])

    body = client.get("/api/my/holdings/kol-summary", headers=headers).json()
    topics = body["topics"]
    assert [row["target_name"] for row in topics] == ["AI算力", "可控核聚变"]
    assert topics[0]["kol_count"] == 2 and topics[1]["kol_count"] == 1


def test_kol_summary_clears_from_replay_events():
    """清仓榜：窗口内清仓事件按标的聚合；盈亏挂接在 T3 落地，本票为 null 占位。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    t = _today()
    k1 = db.add_kol("mx", "清仓大V一", "c1")
    k2 = db.add_kol("mx", "清仓大V二", "c2")
    _seed_opinions(db, k1, [
        (t, "09:20", "stock", "贵州茅台", "bull", "建仓"),
        (t, "14:30", "stock", "贵州茅台", "bear", "清仓"),
        (t, "09:25", "stock", "中科曙光", "bull", "建仓"),
    ])
    _seed_opinions(db, k2, [
        (t, "09:30", "stock", "贵州茅台", "bull", "建仓"),
        (t, "15:00", "stock", "贵州茅台", "bear", "清仓"),
    ])

    body = client.get("/api/my/holdings/kol-summary", headers=headers).json()
    clears = body["clears"]
    assert [row["target_name"] for row in clears] == ["贵州茅台"]
    assert clears[0]["kol_count"] == 2
    entries = clears[0]["entries"]
    assert len(entries) == 2  # 两位大V各一笔清仓
    assert all(e["realized_pnl_pct"] is None for e in entries)  # T3 前占位
    assert all(e["at"].startswith(t) for e in entries)


def test_kol_summary_clears_attach_cached_pnl():
    """清仓榜盈亏挂接：按（大V, 窗口）读小时级缓存，浮亏=割肉、盈利=止盈、无价=占位。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    t = _today()
    k1 = db.add_kol("mx", "割肉大V", "cp1")
    k2 = db.add_kol("mx", "止盈大V", "cp2")
    k3 = db.add_kol("mx", "缺价大V", "cp3")
    _seed_opinions(db, k1, [
        (t, "09:20", "stock", "贵州茅台", "bull", "建仓"),
        (t, "14:30", "stock", "贵州茅台", "bear", "清仓"),
    ])
    _seed_opinions(db, k2, [
        (t, "09:30", "stock", "五粮液", "bull", "建仓"),
        (t, "15:00", "stock", "五粮液", "bear", "清仓"),
    ])
    _seed_opinions(db, k3, [
        (t, "09:40", "stock", "中科曙光", "bull", "建仓"),
        (t, "15:10", "stock", "中科曙光", "bear", "清仓"),
    ])

    def _cached_pnl(kol_id, pct):
        return {"stocks": [{"target_name": "贵州茅台" if kol_id == k1 else
                            ("五粮液" if kol_id == k2 else "中科曙光"),
                            "realized_pnl_pct": pct}]}

    db.upsert_kol_pnl_cache(k1, 30, _cached_pnl(k1, -12.5))  # 浮亏 → 割肉
    db.upsert_kol_pnl_cache(k2, 30, _cached_pnl(k2, 8.3))    # 盈利 → 止盈
    # k3 不写缓存 → 无价占位

    body = client.get("/api/my/holdings/kol-summary", headers=headers).json()
    by_name = {row["target_name"]: row for row in body["clears"]}
    maotai, wly,曙光 = by_name["贵州茅台"], by_name["五粮液"], by_name["中科曙光"]
    assert maotai["entries"][0]["realized_pnl_pct"] == -12.5
    assert maotai["entries"][0]["signal"] == "cut"   # 割肉
    assert wly["entries"][0]["realized_pnl_pct"] == 8.3
    assert wly["entries"][0]["signal"] == "profit"   # 止盈
    assert 曙光["entries"][0]["realized_pnl_pct"] is None
    assert 曙光["entries"][0]["signal"] == ""        # 无价占位
    # 榜行汇总徽计数（前端展示「2 割肉 1 止盈」用）
    assert body["clears"]  # 排序稳定即可


def test_kol_summary_clears_cache_miss_matches_window():
    """缓存按窗口取：90 天榜只挂 (kol,90) 的缓存，缺 90 缓存时占位不串用 30 的。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    old_day = (datetime.now(CN_TZ) - timedelta(days=45)).strftime("%Y-%m-%d")
    kol = db.add_kol("mx", "老仓割肉大V", "cw1")
    _seed_opinions(db, kol, [
        (old_day, "09:20", "stock", "五粮液", "bull", "建仓"),
        (old_day, "14:30", "stock", "五粮液", "bear", "清仓"),
    ])
    db.upsert_kol_pnl_cache(kol, 30, {"stocks": [{"target_name": "五粮液",
                                                  "realized_pnl_pct": -5.0}]})

    b90 = client.get("/api/my/holdings/kol-summary?days=90", headers=headers).json()
    entry = b90["clears"][0]["entries"][0]
    assert entry["realized_pnl_pct"] is None  # 90 缓存缺失：占位，不串 30 的数
    assert entry["signal"] == ""


def test_kol_summary_respects_holdings_scope():
    """范围口径：不在 holdings_kol_ids 的大V持仓不进榜（与单大V页同口径）。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    t = _today()
    k_in = db.add_kol("mx", "名单内大V", "s1")
    k_out = db.add_kol("mx", "名单外大V", "s2")
    db.set_setting("mx_view_kol_ids", json.dumps([k_in]))
    _seed_opinions(db, k_in, [(t, "09:20", "stock", "贵州茅台", "bull", "建仓")])
    _seed_opinions(db, k_out, [(t, "09:20", "stock", "贵州茅台", "bull", "建仓")])

    body = client.get("/api/my/holdings/kol-summary", headers=headers).json()
    heavy = {row["target_name"]: row for row in body["heavy"]}
    assert heavy["贵州茅台"]["kol_count"] == 1
    assert heavy["贵州茅台"]["kols"][0]["name"] == "名单内大V"


def test_kol_summary_window_days_changes_scope():
    """窗口参数：30 天窗口外、90 天窗口内的清仓事件只在 90 天榜出现。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    old_day = (datetime.now(CN_TZ) - timedelta(days=45)).strftime("%Y-%m-%d")
    t = _today()
    kol = db.add_kol("mx", "老仓大V", "w1")
    _seed_opinions(db, kol, [
        (old_day, "09:20", "stock", "五粮液", "bull", "建仓"),
        (old_day, "14:30", "stock", "五粮液", "bear", "清仓"),
        (t, "09:20", "stock", "贵州茅台", "bull", "建仓"),
    ])

    b30 = client.get("/api/my/holdings/kol-summary?days=30", headers=headers).json()
    assert [r["target_name"] for r in b30["heavy"]] == ["贵州茅台"]
    assert b30["clears"] == []
    b90 = client.get("/api/my/holdings/kol-summary?days=90", headers=headers).json()
    assert {r["target_name"] for r in b90["heavy"]} == {"贵州茅台"}
    assert [r["target_name"] for r in b90["clears"]] == ["五粮液"]


def test_kol_summary_empty_state():
    """空态：无任何大V/观点时四榜空数组、不报错。"""
    client = make_client()
    headers = auth_headers(client)
    body = client.get("/api/my/holdings/kol-summary", headers=headers).json()
    assert body["heavy"] == [] and body["attack"] == []
    assert body["topics"] == [] and body["clears"] == []


def test_kol_summary_ttl_cache_hits_within_window():
    """进程内 TTL 缓存：同窗口二次请求命中缓存不重跑回放（计数器验证）。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    t = _today()
    kol = db.add_kol("mx", "缓存大V", "cc1")
    _seed_opinions(db, kol, [(t, "09:20", "stock", "贵州茅台", "bull", "建仓")])

    calls = {"n": 0}
    real_build = khs.build_kol_holdings

    def counting_build(*args, **kwargs):
        calls["n"] += 1
        return real_build(*args, **kwargs)

    khs.build_kol_holdings = counting_build
    try:
        client.get("/api/my/holdings/kol-summary", headers=headers)
        client.get("/api/my/holdings/kol-summary", headers=headers)
        assert calls["n"] == 1  # 二次命中缓存
        client.get("/api/my/holdings/kol-summary?days=90", headers=headers)
        assert calls["n"] == 2  # 窗口不同缓存键不同
    finally:
        khs.build_kol_holdings = real_build
