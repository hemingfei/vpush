"""快讯播报功能测试：手动播报 / 去重 / 配置校验 / 权限。

覆盖后端 3 个接口（GET/PUT settings + POST broadcast），以及自动播报方法
check_and_broadcast_wscn 的核心逻辑（settings 读取、去重、last_id 推进）。
"""

import json

import httpx

from tests.test_api import auth_headers, make_client, user_headers


def _make_system_kol(db, name="快讯播报", ext_id="wscn_bc_kol"):
    kid = db.add_kol("system", name, ext_id)
    db.update_kol(kid, enabled=True)
    return kid


def _wscn_item(item_id=1001, score=3, title="重要消息", body="测试快讯正文", url="https://wallstreetcn.com/livenews/1001"):
    return {
        "id": item_id,
        "score": score,
        "highlight_title": title,
        "body": body,
        "published_at": "2026-09-08T14:30:00+08:00",
        "url": url,
    }


# ---- 配置接口 ----


def test_broadcast_settings_defaults():
    """GET settings 返回默认值：disabled / kol_id=0 / threshold=2 / last_id=0。"""
    client = make_client("wscn-bc-defaults.db")
    headers = auth_headers(client)
    resp = client.get("/api/admin/wscn-broadcast/settings", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["kol_id"] == 0
    assert data["score_threshold"] == 2
    assert data["last_id"] == 0
    assert isinstance(data["system_kols"], list)


def test_broadcast_settings_roundtrip():
    """PUT settings 保存后 GET 回读一致。"""
    client = make_client("wscn-bc-rt.db")
    db = client.app.state.db
    headers = auth_headers(client)
    kid = _make_system_kol(db)

    resp = client.put(
        "/api/admin/wscn-broadcast/settings",
        headers=headers,
        json={"enabled": True, "kol_id": kid, "score_threshold": 5},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    resp = client.get("/api/admin/wscn-broadcast/settings", headers=headers)
    data = resp.json()
    assert data["enabled"] is True
    assert data["kol_id"] == kid
    assert data["score_threshold"] == 5
    # system_kols 列表包含配置的 KOL
    kol_ids = [k["id"] for k in data["system_kols"]]
    assert kid in kol_ids


def test_broadcast_settings_rejects_non_system_kol():
    """PUT settings：非 system 平台的 KOL 被拒绝。"""
    client = make_client("wscn-bc-sys.db")
    db = client.app.state.db
    headers = auth_headers(client)
    kid_xq = db.add_kol("xueqiu", "雪球大V", "xq001")

    resp = client.put(
        "/api/admin/wscn-broadcast/settings",
        headers=headers,
        json={"enabled": True, "kol_id": kid_xq, "score_threshold": 2},
    )
    assert resp.status_code == 400
    assert "V平台 KOL" in resp.json()["detail"]


def test_broadcast_settings_rejects_unknown_kol():
    """PUT settings：不存在的 KOL id 报 400。"""
    client = make_client("wscn-bc-unknown.db")
    headers = auth_headers(client)
    resp = client.put(
        "/api/admin/wscn-broadcast/settings",
        headers=headers,
        json={"enabled": True, "kol_id": 999999, "score_threshold": 2},
    )
    assert resp.status_code == 400
    assert "不存在" in resp.json()["detail"]


# ---- 手动播报 ----


def test_broadcast_manual_creates_post():
    """POST broadcast：播报一条快讯后 posts 表有对应记录。"""
    client = make_client("wscn-bc-manual.db")
    db = client.app.state.db
    headers = auth_headers(client)
    kid = _make_system_kol(db)
    client.put(
        "/api/admin/wscn-broadcast/settings",
        headers=headers,
        json={"enabled": True, "kol_id": kid, "score_threshold": 2},
    )

    item = _wscn_item()
    resp = client.post("/api/admin/wscn-broadcast", headers=headers, json=item)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["broadcast"] is True
    assert data["post_id"] is not None

    # 验证帖子入库
    rows = db._rows(
        "SELECT * FROM posts WHERE platform = 'system' AND external_id = ?",
        (f"wscn_flash_{item['id']}",),
    )
    assert len(rows) == 1
    post = rows[0]
    assert post["kol_id"] == kid
    assert post["title"] == f"【重要快讯】{item['highlight_title']}"
    assert post["content"] == item["body"]
    assert post["url"] == item["url"]
    assert post["post_type"] == "wscn_flash"
    # published_at 转为北京时间裸字符串
    assert post["published_at"].startswith("2026-09-08")


def test_broadcast_manual_idempotent():
    """POST broadcast：同一条快讯播报两次，第二次返回 broadcast=False。"""
    client = make_client("wscn-bc-idem.db")
    db = client.app.state.db
    headers = auth_headers(client)
    kid = _make_system_kol(db)
    client.put(
        "/api/admin/wscn-broadcast/settings",
        headers=headers,
        json={"enabled": True, "kol_id": kid, "score_threshold": 2},
    )

    item = _wscn_item(item_id=2002)
    resp1 = client.post("/api/admin/wscn-broadcast", headers=headers, json=item)
    assert resp1.status_code == 200
    assert resp1.json()["broadcast"] is True

    resp2 = client.post("/api/admin/wscn-broadcast", headers=headers, json=item)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["broadcast"] is False
    assert data2["post_id"] is None
    assert "已播报过" in data2["message"]

    # posts 表只有一条记录
    rows = db._rows(
        "SELECT id FROM posts WHERE platform = 'system' AND external_id = ?",
        (f"wscn_flash_{item['id']}",),
    )
    assert len(rows) == 1


def test_broadcast_manual_no_config_returns_400():
    """POST broadcast：未配置目标 KOL 时报 400。"""
    client = make_client("wscn-bc-noconfig.db")
    headers = auth_headers(client)
    item = _wscn_item()
    resp = client.post("/api/admin/wscn-broadcast", headers=headers, json=item)
    assert resp.status_code == 400
    assert "V平台 KOL" in resp.json()["detail"]


def test_broadcast_manual_uses_fallback_title():
    """POST broadcast：无 highlight_title 时标题为「【重要快讯】」。"""
    client = make_client("wscn-bc-fallback.db")
    db = client.app.state.db
    headers = auth_headers(client)
    kid = _make_system_kol(db)
    client.put(
        "/api/admin/wscn-broadcast/settings",
        headers=headers,
        json={"enabled": True, "kol_id": kid, "score_threshold": 2},
    )

    item = _wscn_item(item_id=3003, title="")
    resp = client.post("/api/admin/wscn-broadcast", headers=headers, json=item)
    assert resp.status_code == 200
    assert resp.json()["broadcast"] is True

    rows = db._rows(
        "SELECT title FROM posts WHERE platform = 'system' AND external_id = ?",
        (f"wscn_flash_{item['id']}",),
    )
    assert rows[0]["title"] == "【重要快讯】"


# ---- 权限 ----


def test_broadcast_requires_admin():
    """普通用户 403、未登录 401。"""
    client = make_client("wscn-bc-perm.db")
    db = client.app.state.db
    admin_h = auth_headers(client)
    user_h = user_headers(client, "bcuser")
    kid = _make_system_kol(db)
    client.put(
        "/api/admin/wscn-broadcast/settings",
        headers=admin_h,
        json={"enabled": True, "kol_id": kid, "score_threshold": 2},
    )

    item = _wscn_item(item_id=4004)
    # 普通用户 POST -> 403
    assert client.post("/api/admin/wscn-broadcast", headers=user_h, json=item).status_code == 403
    # 未登录 POST -> 401
    assert client.post("/api/admin/wscn-broadcast", json=item).status_code == 401
    # 普通用户 GET settings -> 403
    assert client.get("/api/admin/wscn-broadcast/settings", headers=user_h).status_code == 403
    # 普通用户 PUT settings -> 403
    assert client.put(
        "/api/admin/wscn-broadcast/settings", headers=user_h,
        json={"enabled": True, "kol_id": kid, "score_threshold": 2},
    ).status_code == 403


# ---- 自动播报 ----


def test_auto_broadcast_skips_when_disabled():
    """check_and_broadcast_wscn 在未启用时不做任何事。"""
    client = make_client("wscn-bc-auto-off.db")
    db = client.app.state.db
    kid = _make_system_kol(db)
    # 不启用自动播报
    db.set_setting("wscn_broadcast_enabled", "0")
    db.set_setting("wscn_broadcast_kol_id", str(kid))

    scheduler = client.app.state.scheduler
    # 不应抛异常，也不应创建任何帖子
    scheduler.check_and_broadcast_wscn()
    rows = db._rows("SELECT COUNT(*) as c FROM posts WHERE post_type = 'wscn_flash'")
    assert rows[0]["c"] == 0


def test_auto_broadcast_publishes_important_items(monkeypatch):
    """check_and_broadcast_wscn：启用后对 score>=threshold 的新快讯入库+推进 last_id。"""
    client = make_client("wscn-bc-auto-on.db")
    db = client.app.state.db
    kid = _make_system_kol(db)
    db.set_setting("wscn_broadcast_enabled", "1")
    db.set_setting("wscn_broadcast_kol_id", str(kid))
    db.set_setting("wscn_broadcast_score_threshold", "2")
    db.set_setting("wscn_broadcast_last_id", "0")

    # mock wscn 缓存返回 3 条快讯：score=1（不重要）、score=3（重要）、score=2（重要）
    fake_data = {
        "items": [
            _wscn_item(item_id=5001, score=1, title="普通"),
            _wscn_item(item_id=5002, score=3, title="很重要"),
            _wscn_item(item_id=5003, score=2, title="重要"),
        ],
        "next_cursor": "",
        "polling_cursor": 5003,
    }

    def fake_fetch(*, cursor="", limit=30):
        return fake_data

    monkeypatch.setattr("app.api._fetch_wscn_lives", fake_fetch)

    scheduler = client.app.state.scheduler
    scheduler.check_and_broadcast_wscn()

    # 只有 score>=2 的两条入库
    rows = db._rows(
        "SELECT external_id FROM posts WHERE platform = 'system' AND post_type = 'wscn_flash' ORDER BY external_id"
    )
    ext_ids = [r["external_id"] for r in rows]
    assert "wscn_flash_5002" in ext_ids
    assert "wscn_flash_5003" in ext_ids
    assert "wscn_flash_5001" not in ext_ids

    # last_id 推进到 5003
    assert db.get_setting("wscn_broadcast_last_id") == "5003"


def test_auto_broadcast_idempotent_on_recheck(monkeypatch):
    """check_and_broadcast_wscn：第二次运行时 last_id 已推进，不重复入库。"""
    client = make_client("wscn-bc-auto-idem.db")
    db = client.app.state.db
    kid = _make_system_kol(db)
    db.set_setting("wscn_broadcast_enabled", "1")
    db.set_setting("wscn_broadcast_kol_id", str(kid))
    db.set_setting("wscn_broadcast_score_threshold", "2")
    db.set_setting("wscn_broadcast_last_id", "0")

    fake_data = {
        "items": [_wscn_item(item_id=6001, score=3)],
        "next_cursor": "",
        "polling_cursor": 6001,
    }
    monkeypatch.setattr("app.api._fetch_wscn_lives", lambda **kw: fake_data)

    scheduler = client.app.state.scheduler
    scheduler.check_and_broadcast_wscn()
    assert db.get_setting("wscn_broadcast_last_id") == "6001"

    # 第二次运行：last_id=6001，无候选（item id 6001 <= 6001）
    scheduler.check_and_broadcast_wscn()

    rows = db._rows(
        "SELECT COUNT(*) as c FROM posts WHERE platform = 'system' AND external_id = 'wscn_flash_6001'"
    )
    assert rows[0]["c"] == 1  # 仍然只有一条


# ---- 标题前缀：score>=2 为【重要快讯】，score<2 为【快讯】 ----


def test_broadcast_manual_score1_uses_plain_title():
    """POST broadcast：score<2 的快讯标题用「【快讯】」前缀。"""
    client = make_client("wscn-bc-plain.db")
    db = client.app.state.db
    headers = auth_headers(client)
    kid = _make_system_kol(db)
    client.put(
        "/api/admin/wscn-broadcast/settings",
        headers=headers,
        json={"enabled": True, "kol_id": kid, "score_threshold": 2},
    )

    item = _wscn_item(item_id=3101, score=1, title="普通消息")
    resp = client.post("/api/admin/wscn-broadcast", headers=headers, json=item)
    assert resp.status_code == 200
    assert resp.json()["broadcast"] is True

    rows = db._rows(
        "SELECT title FROM posts WHERE platform = 'system' AND external_id = ?",
        (f"wscn_flash_{item['id']}",),
    )
    assert rows[0]["title"] == "【快讯】普通消息"


def test_auto_broadcast_threshold1_titles(monkeypatch):
    """threshold=1 全量播报：score>=2 标「【重要快讯】」，score<2 标「【快讯】」。"""
    client = make_client("wscn-bc-auto-t1.db")
    db = client.app.state.db
    kid = _make_system_kol(db)
    db.set_setting("wscn_broadcast_enabled", "1")
    db.set_setting("wscn_broadcast_kol_id", str(kid))
    db.set_setting("wscn_broadcast_score_threshold", "1")
    db.set_setting("wscn_broadcast_last_id", "0")

    fake_data = {
        "items": [
            _wscn_item(item_id=7001, score=1, title="普通"),
            _wscn_item(item_id=7002, score=3, title="很重要"),
        ],
        "next_cursor": "",
        "polling_cursor": 7002,
    }
    monkeypatch.setattr("app.api._fetch_wscn_lives", lambda **kw: fake_data)

    scheduler = client.app.state.scheduler
    scheduler.check_and_broadcast_wscn()

    rows = db._rows(
        "SELECT external_id, title FROM posts WHERE platform = 'system' AND post_type = 'wscn_flash' ORDER BY external_id"
    )
    titles = {r["external_id"]: r["title"] for r in rows}
    assert titles["wscn_flash_7001"] == "【快讯】普通"
    assert titles["wscn_flash_7002"] == "【重要快讯】很重要"
