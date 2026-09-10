from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def _register(client: TestClient, username: str) -> dict:
    code = f"ANDROID-{username}"
    client.app.state.db.add_register_code(code)
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "pass123456", "code": code},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_android_device_register_update_transfer_and_delete(tmp_path: Path):
    client = TestClient(create_app(db_path=tmp_path / "android-devices.db"))
    first = _register(client, "android_first")
    second = _register(client, "android_second")
    first_headers = {"Authorization": f"Bearer {first['token']}"}
    second_headers = {"Authorization": f"Bearer {second['token']}"}

    payload = {
        "token": "token-a",
        "provider": "fcm",
        "device_model": "Pixel 9",
        "app_version": "0.1.0+1",
    }
    created = client.put(
        "/api/me/android-devices/install-a", headers=first_headers, json=payload
    )
    assert created.status_code == 200, created.text
    assert created.json() == {
        "ok": True,
        "installation_id": "install-a",
        "provider": "fcm",
        "device_count": 1,
    }
    assert client.get("/api/me", headers=first_headers).json()["android_device_count"] == 1

    updated = client.put(
        "/api/me/android-devices/install-a",
        headers=first_headers,
        json={**payload, "token": "token-b"},
    )
    assert updated.status_code == 200
    assert updated.json()["device_count"] == 1
    saved = client.app.state.db.list_android_devices(
        client.app.state.db.get_user_by_username("android_first")["id"]
    )
    assert saved[0]["token"] == "token-b"
    assert saved[0]["device_model"] == "Pixel 9"

    transferred = client.put(
        "/api/me/android-devices/install-a",
        headers=second_headers,
        json={"token": "token-c", "provider": "huawei"},
    )
    assert transferred.status_code == 200
    assert client.app.state.db.count_android_devices(
        client.app.state.db.get_user_by_username("android_first")["id"]
    ) == 0
    assert client.app.state.db.count_android_devices(
        client.app.state.db.get_user_by_username("android_second")["id"]
    ) == 1

    deleted = client.delete(
        "/api/me/android-devices/install-a", headers=second_headers
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "device_count": 0}


def test_android_device_validation_and_authentication(tmp_path: Path):
    client = TestClient(create_app(db_path=tmp_path / "android-devices-validation.db"))
    user = _register(client, "android_validation")
    headers = {"Authorization": f"Bearer {user['token']}"}

    assert client.put(
        "/api/me/android-devices/short",
        headers=headers,
        json={"token": "token", "provider": "fcm"},
    ).status_code == 400
    assert client.put(
        "/api/me/android-devices/install_ok",
        headers=headers,
        json={"token": "", "provider": "fcm"},
    ).status_code == 422
    assert client.put(
        "/api/me/android-devices/install-ok",
        headers=headers,
        json={"token": "token", "provider": "unknown"},
    ).status_code == 422
    assert client.put(
        "/api/me/android-devices/install-ok",
        json={"token": "token", "provider": "fcm"},
    ).status_code == 401
    assert client.delete(
        "/api/me/android-devices/install-ok", headers=headers
    ).json() == {"ok": True, "device_count": 0}
