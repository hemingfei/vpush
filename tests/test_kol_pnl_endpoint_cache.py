"""单大V预估盈亏端点读小时级缓存测试：命中不重算、兜底现算回填、窗口分键。"""
import json
from datetime import datetime

from test_api import auth_headers, make_client

from app import mx_kol_pnl as mp
from app.scheduler import Scheduler


def _seed_today_opinion(db, kol_id, name="贵州茅台"):
    t = datetime.now().strftime("%Y-%m-%d")
    db.insert_post(platform="mx", kol_id=kol_id, external_id=f"ep{kol_id}",
                   title="", url="", content="x", published_at=f"{t} 09:20:00")
    pid = db._rows("SELECT id FROM posts ORDER BY id DESC")[0]["id"]
    bid = db.upsert_mx_view_batch(t, "09:20", "live")
    db.replace_mx_opinions(bid, [{
        "trading_day": t, "snapshot_at": "09:20", "kol_id": kol_id,
        "target_type": "stock", "target_name": name, "direction": "bull",
        "action": "建仓", "confidence": "high", "summary": "s",
        "evidence_post_ids": [pid], "occurred_at": f"{t} 09:20:00",
    }])


def test_kol_pnl_endpoint_serves_fresh_cache(monkeypatch):
    """缓存新鲜：端点直接返回缓存内容，不触发回放。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "缓存命中大V", "kc1")
    _seed_today_opinion(db, kol)

    cached = {"kol": {"kol_id": kol, "name": "缓存命中大V", "avatar": "", "platform": "mx"},
              "window_days": 30, "stale_days": 10, "available": True,
              "stocks": [{"target_name": "贵州茅台", "realized_pnl_pct": -3.2}],
              "event_prices": {}, "summary": {}, "generated_at": "2026-09-21 10:00"}
    db.upsert_kol_pnl_cache(kol, 30, cached)

    real_pnl = mp.build_kol_pnl
    calls = {"n": 0}

    def counting_pnl(*a, **k):
        calls["n"] += 1
        return real_pnl(*a, **k)

    monkeypatch.setattr(mp, "build_kol_pnl", counting_pnl)
    # 缓存新鲜度由 scheduler 小时任务保证（上一小时刚算过）；端点只看有无
    r = client.get(f"/api/kols/{kol}/mx-pnl", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["stocks"][0]["realized_pnl_pct"] == -3.2
    assert calls["n"] == 0  # 未现算


def test_kol_pnl_endpoint_falls_back_and_backfills(monkeypatch):
    """缓存缺失：兜底现算并回填缓存，下次命中。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "兜底大V", "kc2")
    _seed_today_opinion(db, kol)

    def stub_pnl(database, kol_id, days=30, price_lookup=None):
        return {"kol": {"kol_id": kol_id, "name": "兜底大V", "avatar": "", "platform": "mx"},
                "window_days": days, "stale_days": 10, "available": False,
                "stocks": [], "event_prices": {}, "summary": {},
                "generated_at": "2026-09-21 11:00"}

    monkeypatch.setattr(mp, "build_kol_pnl", stub_pnl)
    r = client.get(f"/api/kols/{kol}/mx-pnl?days=60", headers=headers)
    assert r.status_code == 200 and r.json()["available"] is False
    # 回填：之后缓存可读（60 窗口键）
    hit = db.get_kol_pnl_cache(kol, 60)
    assert hit is not None and hit["payload"]["available"] is False


def test_kol_pnl_endpoint_no_signal_not_cached(monkeypatch):
    """回放无信号（None）：不缓存（空结果不是数据，缓存会挡住后续真实重算）。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "无信号大V", "kc3")

    monkeypatch.setattr(mp, "build_kol_pnl", lambda *a, **k: None)
    r = client.get(f"/api/kols/{kol}/mx-pnl", headers=headers)
    assert r.status_code == 200
    assert db.get_kol_pnl_cache(kol, 30) is None


def test_kol_pnl_endpoint_non_refresh_window_never_cached(monkeypatch):
    """days=45 等无重算任务的窗口：现算直返、不读写缓存（否则快照永久陈旧）。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "非标窗口大V", "kc4")
    _seed_today_opinion(db, kol)

    # 预埋一份 45 天的旧缓存（模拟历史脏数据）：也不允许被读出
    db.upsert_kol_pnl_cache(kol, 45, {"stocks": [{"target_name": "旧", "realized_pnl_pct": 1.0}]})

    calls = {"n": 0}

    def stub_pnl(database, kol_id, days=30, price_lookup=None):
        calls["n"] += 1
        return {"kol": {"kol_id": kol_id}, "window_days": days, "stale_days": 10,
                "available": True, "stocks": [], "event_prices": {}, "summary": {},
                "generated_at": "2026-09-21 11:00"}

    monkeypatch.setattr(mp, "build_kol_pnl", stub_pnl)
    r = client.get(f"/api/kols/{kol}/mx-pnl?days=45", headers=headers)
    assert r.status_code == 200 and r.json()["window_days"] == 45
    assert calls["n"] == 1  # 现算，不读旧缓存
    # 请求后仍只有那份旧缓存（新结果未被回填）
    assert db.get_kol_pnl_cache(kol, 45)["payload"]["stocks"][0]["target_name"] == "旧"
