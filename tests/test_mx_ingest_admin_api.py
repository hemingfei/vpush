"""MX 本地采集设备管理面（登录态端点 /api/admin/mx-ingest/*）测试。

覆盖（spec #14 管理面前端接线）：
- 非管理员 403 / 未登录 401；
- overview：设备清单（含 revoked/online 字段）+ 生命周期事件；
- 登录态签发的配对码可真配对（走 build_gateway_app 同库）；
- 吊销：DB 置 revoked + app.state.mx_ingest_notify_revoked 被调用；
- events：list_mx_ingest_events 通路。
"""
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from app.config import Config
from app.main import create_app


def make_client(name="mx-ingest.db"):
    config = Config()
    tmp = tempfile.mkdtemp()
    app = create_app(config=config, db_path=Path(tmp) / name)
    return TestClient(app)


def admin_headers(client, username="ingestadmin", password="secret1234"):
    code = "INGEST01"
    client.app.state.db.add_register_code(code)
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "code": code},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 测试辅助：注册后通过 DB 提升为管理员（生产环境只能由管理员指定）
    client.app.state.db.update_user(data["user"]["id"], is_admin=True)
    return {"Authorization": f"Bearer {data['token']}"}


def test_admin_required_for_mx_ingest_admin_api():
    """未登录 401、非管理员 403（require_admin 同款口径）。"""
    client = make_client()
    # 未登录
    assert client.get("/api/admin/sources/mx/ingest/overview").status_code == 401
    # 普通用户
    client.app.state.db.add_register_code("PLAIN001")
    client.post("/api/auth/register",
                json={"username": "plainuser", "password": "pass123456", "code": "PLAIN001"})
    login = client.post("/api/auth/login",
                        json={"username": "plainuser", "password": "pass123456"})
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    assert client.get("/api/admin/sources/mx/ingest/overview", headers=headers).status_code == 403
    assert client.post("/api/admin/sources/mx/ingest/pairing-code", headers=headers).status_code == 403


def test_overview_lists_devices_and_events():
    """overview 返回设备清单（online/revoked 字段齐）+ 最近事件。"""
    client = make_client()
    headers = admin_headers(client)
    db = client.app.state.db
    device_id = db.add_mx_device("k" * 64, name="采集器")
    db.record_mx_ingest_event(device_id, "hemingfei", "attached", "tab=1 url=https://x")

    r = client.get("/api/admin/sources/mx/ingest/overview", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [d["id"] for d in body["devices"]] == [device_id]
    dev = body["devices"][0]
    assert dev["name"] == "采集器" and dev["revoked"] == 0
    assert dev["online"] is False  # 纯 API 测试无 WS 连接，注册表缺席=离线
    assert "created_at" in dev and "last_seen_at" in dev
    assert any(e["event"] == "attached" for e in body["events"])


def test_pairing_code_minted_via_admin_api_pairs_for_real():
    """登录态签发的配对码与 Bearer 管理面同一账目：真配对可成功。"""
    client = make_client()
    headers = admin_headers(client)

    r = client.post("/api/admin/sources/mx/ingest/pairing-code", headers=headers)
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert len(code) == 8 and code.isdigit()
    # 同库直接消费（网关 handle_pair 同款方法）：一次性码有效
    assert client.app.state.db.consume_mx_pairing_code(code) is True
    # 二次消费作废
    assert client.app.state.db.consume_mx_pairing_code(code) is False


def test_revoke_marks_device_and_notifies_gateway():
    """吊销：DB revoked=1 + notify 回调被调用（掐断存量连接）。"""
    client = make_client()
    headers = admin_headers(client)
    db = client.app.state.db
    device_id = db.add_mx_device("k" * 64, name="采集器")

    revoked_calls = []
    client.app.state.mx_ingest_notify_revoked = lambda did: revoked_calls.append(did)

    r = client.post(f"/api/admin/sources/mx/ingest/devices/{device_id}/revoke", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "device_id": device_id}
    assert revoked_calls == [device_id]
    row = db._rows("SELECT revoked FROM mx_devices WHERE id = ?", (device_id,))[0]
    assert int(row["revoked"]) == 1
    # 已吊销设备密钥认证被拒（find_mx_device_by_key 只认 revoked=0）
    assert db.find_mx_device_by_key("k" * 64) is None


def test_revoke_unknown_device_404():
    """吊销不存在的设备 404（不静默成功）。"""
    client = make_client()
    headers = admin_headers(client)
    r = client.post("/api/admin/sources/mx/ingest/devices/999/revoke", headers=headers)
    assert r.status_code == 404


def test_events_endpoint_returns_recent_first():
    """events 端点按 id 倒序（最近优先），limit 生效。"""
    client = make_client()
    headers = admin_headers(client)
    db = client.app.state.db
    device_id = db.add_mx_device("k" * 64, name="采集器")
    for i in range(5):
        db.record_mx_ingest_event(device_id, "", f"ev{i}", f"d{i}")

    r = client.get("/api/admin/sources/mx/ingest/events?limit=3", headers=headers)
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 3
    assert [e["event"] for e in events] == ["ev4", "ev3", "ev2"]
