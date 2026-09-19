"""ARM lab ops panel: status redaction, auth gate, mocked 115 QR."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

OPS_DIR = Path(__file__).resolve().parent.parent / "arm-lab-ops"
sys.path.insert(0, str(OPS_DIR))

from ops_app import create_app  # noqa: E402
from ops_qr115 import QRError, QRManager, write_cookies  # noqa: E402
from ops_settings import (  # noqa: E402
    DEFAULT_CICC_COOKIES,
    DEFAULT_PYTHON,
    bind_host,
    bind_spec,
    binds_all_interfaces,
    cicc_cookie_path,
    python_bin,
    tailscale_ipv4,
)
from ops_status import (  # noqa: E402
    collect_status,
    cookie_meta,
    ima_cred_status,
    redact,
    sanitize_health,
)


@pytest.fixture
def lab_env(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    secrets = tmp_path / "secrets"
    cache.mkdir()
    (cache / "staging").mkdir()
    (cache / "hot").mkdir()
    (cache / "failed").mkdir()
    (cache / "logs").mkdir()
    secrets.mkdir()
    monkeypatch.setenv("ARM_OPS_PASSWORD", "lab-secret")
    monkeypatch.setenv("CACHE_ROOT", str(cache))
    monkeypatch.setenv("P115_COOKIES_FILE", str(secrets / "115-cookies.txt"))
    monkeypatch.setenv("IMA_PURE_SECRETS_FILE", str(secrets / "ima-pure.json"))
    monkeypatch.setenv("OPENLIST_PUBLIC_URL", "http://127.0.0.1:5244/lab-hot")
    monkeypatch.delenv("PULLER_HEALTH_URL", raising=False)
    monkeypatch.setenv("PULLER_HEALTH_FILE", str(cache / "logs" / "health.json"))
    return cache, secrets


@pytest.fixture
def client(lab_env):
    return TestClient(create_app())


def _login(client: TestClient, password: str = "lab-secret"):
    return client.post("/login", data={"password": password}, follow_redirects=False)


def test_status_redacts_ima_refresh_token_and_cookie_body(lab_env):
    cache, secrets = lab_env
    secrets.joinpath("ima-pure.json").write_text(
        json.dumps({"uid": "user-123456", "refresh_token": "super-secret-refresh"}),
        encoding="utf-8",
    )
    secrets.joinpath("115-cookies.txt").write_text(
        "UID=cookie-secret; CID=cid-secret; SEID=seid-secret",
        encoding="utf-8",
    )
    (cache / "logs" / "puller.log").write_text(
        "upload ok UID=cookie-secret refresh_token=super-secret-refresh\n",
        encoding="utf-8",
    )
    (cache / "logs" / "health.json").write_text(
        json.dumps(
            {
                "ok": True,
                "status": "up",
                "refresh_token": "must-not-leak",
                "cookie": "UID=cookie-secret",
                "updated_at": "2026-09-19T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (cache / "staging" / "a.pdf").write_bytes(b"%PDF")

    payload = collect_status()
    dumped = json.dumps(payload)
    assert "super-secret-refresh" not in dumped
    assert "cookie-secret" not in dumped
    assert "must-not-leak" not in dumped
    assert "seid-secret" not in dumped
    assert payload["ima"] == {
        "present": True,
        "mtime": payload["ima"]["mtime"],
        "uid_len": len("user-123456"),
        "note": payload["ima"]["note"],
    }
    assert "refresh_token" not in payload["ima"]
    assert payload["p115"]["present"] is True
    assert payload["p115"]["length"] == len("UID=cookie-secret; CID=cid-secret; SEID=seid-secret")
    assert "cookie" not in payload["p115"]
    assert "UID=<redacted>" in dumped
    assert payload["cache"]["staging"]["files"] == 1
    assert payload["openlist"]["url"].endswith("/lab-hot")
    health = payload["puller"]["health"]
    assert health["ok"] is True
    assert "refresh_token" not in health
    assert "cookie" not in health


def test_ima_and_cookie_helpers_omit_bodies(tmp_path):
    ima = tmp_path / "ima-pure.json"
    ima.write_text(json.dumps({"uid": "abcde", "refresh_token": "tok"}), encoding="utf-8")
    meta = ima_cred_status(ima)
    assert meta == {"present": True, "mtime": meta["mtime"], "uid_len": 5}
    cookie = tmp_path / "115-cookies.txt"
    cookie.write_text("UID=hidden", encoding="utf-8")
    info = cookie_meta(cookie)
    assert info["present"] is True and info["length"] == 10
    assert "hidden" not in json.dumps(info)
    assert "tok" not in json.dumps(meta)


def test_redact_and_sanitize_health():
    assert "secret" not in redact("UID=secret refresh_token=also-secret")
    cleaned = sanitize_health(
        {"ok": True, "cookie": "UID=x", "nested": {"refresh_token": "y", "status": "up"}}
    )
    assert cleaned["ok"] is True
    assert "cookie" not in cleaned
    assert "refresh_token" not in json.dumps(cleaned)


def test_auth_required_for_status_and_qr(client):
    login_html = client.get("/login").text
    assert "Tailscale" in login_html
    assert "0.0.0.0:8055" in login_html
    assert client.get("/api/status").status_code == 401
    assert client.post("/api/115/qr/start", json={"device_type": "harmony"}).status_code == 401
    assert client.get("/api/115/qr/status", params={"session_id": "x"}).status_code == 401
    assert client.post("/api/failed/requeue", json={"confirm": True, "all": True}).status_code == 401
    assert client.post("/api/sync/ima/dry-run", json={"limit": 1}).status_code == 401
    assert client.post("/api/sync/ima/apply", json={"confirm": True, "limit": 1}).status_code == 401
    assert client.post("/api/sync/cicc/apply", json={"confirm": True, "limit": 1}).status_code == 401
    home = client.get("/", follow_redirects=False)
    assert home.status_code in {303, 307}
    assert home.headers["location"].endswith("/login")


def test_login_sets_httponly_cookie(client):
    bad = _login(client, "nope")
    assert bad.status_code == 401
    ok = _login(client)
    assert ok.status_code == 303
    assert ok.cookies.get("arm_ops")
    header = ok.headers.get("set-cookie", "")
    assert "HttpOnly" in header or "httponly" in header.lower()
    status = client.get("/api/status")
    assert status.status_code == 200
    body = status.json()
    assert body["ok"] is True
    assert "refresh_token" not in json.dumps(body)


def test_login_reads_password_file(tmp_path, monkeypatch):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    pw = secrets / "arm-ops-password.txt"
    pw.write_text("file-password\n", encoding="utf-8")
    monkeypatch.delenv("ARM_OPS_PASSWORD", raising=False)
    monkeypatch.setenv("ARM_OPS_PASSWORD_FILE", str(pw))
    monkeypatch.setenv("CACHE_ROOT", str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    client = TestClient(create_app())
    assert _login(client, "file-password").status_code == 303


class FakeP115:
    token = {"data": {"uid": "qr-uid-1", "time": 11, "sign": "sig"}}
    scan_status = 0
    result = {"data": {"cookie": {"UID": "real-cookie-value", "CID": "c", "SEID": "s"}}}

    @staticmethod
    def login_qrcode_token():
        return FakeP115.token

    @staticmethod
    def login_qrcode(uid):
        assert uid == "qr-uid-1"
        return b"\x89PNG\r\n\x1a\n" + b"fake-png"

    @staticmethod
    def login_qrcode_scan_status(payload):
        assert payload["uid"] == "qr-uid-1"
        return {"data": {"status": FakeP115.scan_status}}

    @staticmethod
    def login_qrcode_scan_result(payload):
        assert payload["app"] == "harmony"
        assert payload["account"] == "qr-uid-1"
        return FakeP115.result


def test_qr_fails_closed_without_p115client(monkeypatch, lab_env):
    def boom():
        raise QRError("p115client is not installed; QR login is unavailable")

    monkeypatch.setattr("ops_qr115.load_p115_client", boom)
    mgr = QRManager()
    with pytest.raises(QRError, match="p115client"):
        mgr.start("harmony")


def test_qr_success_writes_0600_and_omits_cookie(monkeypatch, lab_env, client):
    _cache, secrets = lab_env
    FakeP115.scan_status = 2
    monkeypatch.setattr("ops_qr115.load_p115_client", lambda: FakeP115)
    assert _login(client).status_code == 303
    client.app.state.qr = QRManager()

    start = client.post("/api/115/qr/start", json={"device_type": "harmony"})
    assert start.status_code == 200
    body = start.json()
    assert body["ok"] is True
    assert body["qr_png"].startswith("data:image/png;base64,")
    assert "real-cookie-value" not in json.dumps(body)
    sid = body["session_id"]

    FakeP115.scan_status = 0
    pending = client.get("/api/115/qr/status", params={"session_id": sid})
    assert pending.json()["status"] == "pending"

    FakeP115.scan_status = 2
    done = client.get("/api/115/qr/status", params={"session_id": sid})
    payload = done.json()
    assert payload == {"ok": True, "status": "ok", "cookie_len": payload["cookie_len"]}
    assert "real-cookie-value" not in json.dumps(payload)
    written = secrets / "115-cookies.txt"
    text = written.read_text(encoding="utf-8")
    assert "UID=real-cookie-value" in text
    mode = stat.S_IMODE(written.stat().st_mode)
    assert mode == 0o600


def test_write_cookies_mode(tmp_path):
    path = tmp_path / "115-cookies.txt"
    n = write_cookies(path, "UID=abc; CID=def")
    assert n == len("UID=abc; CID=def")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_qr_start_rate_limit(monkeypatch, lab_env):
    monkeypatch.setattr("ops_qr115.load_p115_client", lambda: FakeP115)
    mgr = QRManager()
    for _ in range(5):
        mgr.start("web")
    with pytest.raises(QRError, match="rate limit"):
        mgr.start("web")


def test_compose_snippet_matches_live_lab_contract():
    text = (OPS_DIR / "docker-compose.snippet.yml").read_text(encoding="utf-8")
    assert "VPUSH_PYTHON: /opt/vpush-ima-lab/venv/bin/python" in text
    assert "VPUSH_SCRIPTS_ROOT: /opt/vpush-ima-lab/src/scripts" in text
    assert "VPUSH_CICC_COOKIE_FILE: /secrets/cicc-cookies.txt" in text
    assert "IMA_PURE_SECRETS_FILE: /secrets/ima-pure.json" in text
    assert "/opt/vpush-ima-lab/src:/opt/vpush-ima-lab/src:ro" in text
    assert "/opt/vpush-ima-lab/venv:/opt/vpush-ima-lab/venv:ro" in text
    assert "/opt/vpush-ima-lab/secrets:/secrets" in text
    cache_mount = next(line for line in text.splitlines() if "/data/vpush-ima-cache:" in line)
    assert ":ro" not in cache_mount
    assert "docker-compose.prod" not in text.lower()


def test_python_bin_env_and_fallback(monkeypatch):
    monkeypatch.delenv("VPUSH_PYTHON", raising=False)
    assert python_bin() == sys.executable
    monkeypatch.setenv("VPUSH_PYTHON", "/opt/vpush-ima-lab/venv/bin/python")
    assert python_bin() == "/opt/vpush-ima-lab/venv/bin/python"
    assert DEFAULT_PYTHON == "/opt/vpush-ima-lab/venv/bin/python"


def test_cicc_cookie_default_is_secrets(monkeypatch):
    monkeypatch.delenv("VPUSH_CICC_COOKIE_FILE", raising=False)
    assert DEFAULT_CICC_COOKIES == "/secrets/cicc-cookies.txt"
    assert cicc_cookie_path().as_posix() == "/secrets/cicc-cookies.txt"


def test_bind_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("ARM_OPS_BIND", raising=False)
    monkeypatch.delenv("ARM_OPS_HOST", raising=False)
    assert bind_spec() == "127.0.0.1"
    assert bind_host() == "127.0.0.1"
    assert binds_all_interfaces("0.0.0.0") is True
    assert binds_all_interfaces("127.0.0.1") is False


def test_bind_prefers_arm_ops_bind_over_host(monkeypatch):
    monkeypatch.setenv("ARM_OPS_HOST", "127.0.0.1")
    monkeypatch.setenv("ARM_OPS_BIND", "100.64.1.20")
    assert bind_spec() == "100.64.1.20"
    assert bind_host() == "100.64.1.20"


def test_bind_tailscale_token_uses_cli_then_iface(monkeypatch):
    monkeypatch.setenv("ARM_OPS_BIND", "tailscale")

    def cli_only(cmd, **_kwargs):
        class Proc:
            returncode = 0
            stdout = "100.64.8.8\n"
            stderr = ""

        if cmd[:3] == ["tailscale", "ip", "-4"]:
            return Proc()
        raise AssertionError(cmd)

    assert tailscale_ipv4(runner=cli_only) == "100.64.8.8"
    assert bind_host(runner=cli_only) == "100.64.8.8"

    def iface_only(cmd, **_kwargs):
        class Proc:
            returncode = 1
            stdout = ""
            stderr = "missing"

        if cmd[:3] == ["tailscale", "ip", "-4"]:
            return Proc()

        class Iface:
            returncode = 0
            stdout = "4: tailscale0    inet 100.64.9.9/32 scope global\n"
            stderr = ""

        return Iface()

    monkeypatch.setenv("ARM_OPS_BIND", "tailscale0")
    assert bind_host(runner=iface_only) == "100.64.9.9"


def test_bind_tailscale_missing_falls_back_to_loopback(monkeypatch):
    monkeypatch.setenv("ARM_OPS_BIND", "tailscale")

    def boom(cmd, **_kwargs):
        raise FileNotFoundError(cmd[0])

    assert bind_host(runner=boom) == "127.0.0.1"


def test_dashboard_phase2_has_confirmed_apply(client):
    assert _login(client).status_code == 303
    html = client.get("/").text
    assert "ima_phone_sync" in html
    assert "开始扫码" in html
    assert "IMA apply" in html
    assert "CICC apply" in html
    assert 'id="apply-confirm"' in html
    assert 'id="requeue-confirm"' in html
    assert "/api/115/qr/ima" not in html
    assert "本面板不做 IMA 扫码" in html
    assert 'id="ima-qr"' not in html
