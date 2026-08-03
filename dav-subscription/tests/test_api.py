import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_kol_crud_api():
    tmp = tempfile.mkdtemp()
    app = create_app(db_path=Path(tmp) / "api.db")
    client = TestClient(app)

    resp = client.get("/api/kols")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = client.post("/api/kols", json={"platform": "xueqiu", "name": "大V", "external_id": "123"})
    assert resp.status_code == 200
    kid = resp.json()["id"]

    resp = client.post("/api/kols", json={"platform": "facebook", "name": "x", "external_id": "1"})
    assert resp.status_code == 400

    resp = client.put(f"/api/kols/{kid}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] == 0

    resp = client.delete(f"/api/kols/{kid}")
    assert resp.status_code == 200
    assert client.get("/api/kols").json() == []


def test_posts_and_push_logs_api():
    tmp = tempfile.mkdtemp()
    app = create_app(db_path=Path(tmp) / "api2.db")
    client = TestClient(app)
    kid = client.post("/api/kols", json={"platform": "xueqiu", "name": "A", "external_id": "1"}).json()["id"]
    app.state.db.insert_post("xueqiu", kid, "p1", "t", "c", "u", "")
    assert client.get("/api/posts").json()[0]["title"] == "t"
    assert client.get("/api/push-logs").json() == []


def test_healthz():
    tmp = tempfile.mkdtemp()
    app = create_app(db_path=Path(tmp) / "api3.db")
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
