"""MX 观点用户端 API 测试。"""
from test_api import auth_headers, make_client

from app import mx_view_analysis as mva


def _seed_snapshot(db):
    kol = db.add_kol("mx", "王哥", "room1")
    db.insert_post(platform="mx", kol_id=kol, external_id="m1", title="", url="",
                   content="固态电池订单爆了", published_at="2026-09-04 09:16:00")
    bid = db.upsert_mx_view_batch("2026-09-04", "09:20", "live")
    db.replace_mx_opinions(bid, [{
        "trading_day": "2026-09-04", "snapshot_at": "09:20", "kol_id": kol,
        "target_type": "topic", "target_name": "固态电池", "direction": "bull",
        "action": "", "confidence": "high", "summary": "订单爆了",
        "evidence_post_ids": [db._rows("SELECT id FROM posts")[0]["id"]],
        "occurred_at": "2026-09-04 09:16:00",
    }])
    payload = mva.aggregate_day_state("2026-09-04", "09:20", db.list_mx_opinions("2026-09-04"), None)
    payload["summary"] = {"text": "看多固态电池", "items": []}
    payload["message_count"] = 1
    db.upsert_mx_view_snapshot("2026-09-04", "09:20", 1, "live", payload, bid)
    mva.bump_view_version(db)
    return kol


def test_mx_views_days_day_snapshot_roundtrip():
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    _seed_snapshot(db)

    days = client.get("/api/mx-views/days", headers=headers).json()
    assert days["days"] == [{"trading_day": "2026-09-04", "snapshots": 1}]

    day = client.get("/api/mx-views/day?day=2026-09-04", headers=headers).json()
    assert day["latest_at"] == "09:20"
    assert day["snapshots"] == [{"snapshot_at": "09:20", "seq": 1, "kind": "live", "message_count": 1}]

    snap = client.get("/api/mx-views/snapshot?day=2026-09-04&at=09:20", headers=headers).json()
    assert snap["version"] >= 1
    assert snap["payload"]["topics"][0]["name"] == "固态电池"
    assert client.get("/api/mx-views/snapshot?day=2026-09-04&at=10:00",
                      headers=headers).status_code == 404
    # 未登录 401
    assert client.get("/api/mx-views/days").status_code == 401


def test_mx_views_stream_pushes_initial_version(monkeypatch):
    # TestClient 会等整个 ASGI 应用跑完才返回响应，故把 SSE 轮询上限/间隔调小让流尽快收尾。
    from app import api as api_module

    monkeypatch.setattr(api_module, "_MX_SSE_MAX_TICKS", 2)
    monkeypatch.setattr(api_module, "_MX_SSE_TICK_SECONDS", 0.01)
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    _seed_snapshot(db)  # version >= 1
    token = headers["Authorization"].split(" ", 1)[1]
    with client.stream("GET", f"/api/mx-views/stream?token={token}", headers=headers) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = resp.iter_lines()
        first = next(lines)
        assert first == "event: version"
        second = next(lines)
        assert second.startswith("data: {")
        assert '"version"' in second


def test_mx_views_target_detail_with_evidence():
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    _seed_snapshot(db)
    data = client.get(
        "/api/mx-views/target?type=topic&name=固态电池&day=2026-09-04&at=09:20",
        headers=headers,
    ).json()
    assert data["bull"]["count"] == 1 and data["bear"]["count"] == 0
    op = data["timeline"][0]
    assert op["kol_name"] == "王哥" and op["direction"] == "bull"
    assert op["evidence"][0]["content"] == "固态电池订单爆了"

    kol = client.get(
        f"/api/mx-views/kol/{db._rows('SELECT id FROM kols')[0]['id']}"
        "?day=2026-09-04&at=09:20",
        headers=headers,
    ).json()
    # 大V下钻时间线也要带作者名/头像字段（抽屉里渲染头像与名字）
    assert kol["kol"]["name"] == "王哥" and len(kol["timeline"]) == 1
    assert kol["timeline"][0]["kol_name"] == "王哥" and "avatar" in kol["timeline"][0]


def test_mx_views_feed_all_batches_latest_first():
    """全天观点流直读 mx_opinions：最新批次在前、批内时间倒序、seq 由快照元数据拼回、
    无观点批次不出现；未登录 401。"""
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "王哥", "room1")
    db.insert_post(platform="mx", kol_id=kol, external_id="m1", title="", url="",
                   content="固态电池订单爆了", published_at="2026-09-04 09:16:00")
    post_id = db._rows("SELECT id FROM posts")[0]["id"]

    def seed(at, seq, summary, occurred):
        bid = db.upsert_mx_view_batch("2026-09-04", at, "live")
        db.replace_mx_opinions(bid, [{
            "trading_day": "2026-09-04", "snapshot_at": at, "kol_id": kol,
            "target_type": "topic", "target_name": "固态电池", "direction": "bull",
            "action": "", "confidence": "high", "summary": summary,
            "evidence_post_ids": [post_id], "occurred_at": occurred,
        }])
        db.upsert_mx_view_snapshot("2026-09-04", at, seq, "live", {"message_count": 1}, bid)

    seed("09:20", 1, "王哥 看多", "2026-09-04 09:16:00")
    seed("09:40", 2, "王哥 看多(后批)", "2026-09-04 09:35:00")
    empty = db.upsert_mx_view_batch("2026-09-04", "10:00", "live")  # 无观点批次
    db.finish_mx_view_batch(empty, "done", 0)
    db.upsert_mx_view_snapshot("2026-09-04", "10:00", 3, "live", {"message_count": 0}, empty)

    data = client.get("/api/mx-views/feed?day=2026-09-04", headers=headers).json()
    batches = data["batches"]
    assert [b["snapshot_at"] for b in batches] == ["09:40", "09:20"]  # 最新批次在前，无观点批次跳过
    assert [b["seq"] for b in batches] == [2, 1]
    assert all(o["snapshot_at"] == b["snapshot_at"] for b in batches for o in b["opinions"])
    assert batches[0]["opinions"][0]["summary"] == "王哥 看多(后批)"
    assert client.get("/api/mx-views/feed?day=2026-09-04").status_code == 401


def test_mx_views_admin_config_and_status():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    cfg = client.get("/api/admin/mx-views/config", headers=admin).json()
    assert cfg["enabled"] is False and cfg["batch_size"] == 600
    assert len(cfg["schedule"]["resolved_times"]) == 38
    assert "固态电池" in cfg["topic_hints"]

    put = client.put("/api/admin/mx-views/config", headers=admin,
                     json={"enabled": True, "batch_size": 300,
                           "schedule": {"segments": [{"start": "09:30", "end": "09:40", "interval_min": 5}],
                                        "extra_times": []}})
    assert put.status_code == 200
    cfg2 = client.get("/api/admin/mx-views/config", headers=admin).json()
    assert cfg2["enabled"] is True and cfg2["batch_size"] == 300
    assert cfg2["schedule"]["resolved_times"] == ["09:30", "09:35", "09:40"]
    # 非法 schedule 422
    bad = client.put("/api/admin/mx-views/config", headers=admin,
                     json={"schedule": {"segments": "oops", "extra_times": []}})
    assert bad.status_code == 422
    # 超界时刻（24:00）422：落库回填后 last_done 永远压住当天 live 快照
    bad2 = client.put("/api/admin/mx-views/config", headers=admin,
                      json={"schedule": {"segments": [], "extra_times": ["24:00"]}})
    assert bad2.status_code == 422 and "extra_times" in bad2.json()["detail"]
    # 普通用户 403
    from test_api import user_headers

    uh = user_headers(client, "plainmxv")
    assert client.get("/api/admin/mx-views/config", headers=uh).status_code == 403

    status = client.get("/api/admin/mx-views/status", headers=admin).json()
    assert status["cursor"] == 0 and status["backfill"]["running"] is False


def test_mx_views_admin_candidates_adopt_and_dismiss():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    mva.add_topic_candidates(db, ["可控核聚变", "固态电池"])  # 参考表已有的不入候选
    lst = client.get("/api/admin/mx-views/topic-candidates", headers=admin).json()
    assert lst["candidates"] == ["可控核聚变"]
    r = client.post("/api/admin/mx-views/topic-candidates/adopt", headers=admin,
                    json={"name": "可控核聚变"})
    assert r.status_code == 200
    assert "可控核聚变" in client.get("/api/admin/mx-views/config", headers=admin).json()["topic_hints"]
    assert client.get("/api/admin/mx-views/topic-candidates", headers=admin).json()["candidates"] == []
    client.post("/api/admin/mx-views/topic-candidates/dismiss", headers=admin, json={"name": "x"})
