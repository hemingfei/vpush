"""ARM lab ops settings: validation, confirm gate, persistence, no secrets."""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

OPS_DIR = Path(__file__).resolve().parent.parent / "arm-lab-ops"
sys.path.insert(0, str(OPS_DIR))

from ops_actions import ActionError  # noqa: E402
from ops_app import create_app  # noqa: E402
from ops_lab_knobs import (  # noqa: E402
    DEFAULTS,
    apply_sync_timers,
    dropin_text,
    get_settings,
    load_settings,
    parse_batch,
    parse_clock,
    parse_limit,
    save_settings,
    validate_settings,
    write_puller_env,
)


@pytest.fixture
def lab_env(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    secrets = tmp_path / "secrets"
    cache.mkdir()
    (cache / "logs").mkdir()
    secrets.mkdir()
    monkeypatch.setenv("ARM_OPS_PASSWORD", "lab-secret")
    monkeypatch.setenv("CACHE_ROOT", str(cache))
    monkeypatch.setenv("P115_COOKIES_FILE", str(secrets / "115-cookies.txt"))
    monkeypatch.setenv("IMA_PURE_SECRETS_FILE", str(secrets / "ima-pure.json"))
    monkeypatch.delenv("ARM_OPS_TIMER_HELPER", raising=False)
    return cache, secrets


@pytest.fixture
def client(lab_env):
    return TestClient(create_app())


def _login(client: TestClient, password: str = "lab-secret"):
    return client.post("/login", data={"password": password}, follow_redirects=False)


def test_clock_and_limit_validation():
    assert parse_clock("03:00") == "03:00"
    assert parse_clock("3:05") == "03:05"
    assert parse_clock("23:59:00") == "23:59"
    assert parse_clock("") == "03:00"
    with pytest.raises(ActionError, match="HH:MM"):
        parse_clock("25:00")
    with pytest.raises(ActionError, match="HH:MM"):
        parse_clock("not-a-time")
    with pytest.raises(ActionError, match="HH:MM"):
        parse_clock("03:00; rm -rf /")
    assert parse_limit(10, field="ima_limit_per_group") == 10
    assert parse_limit(1, field="cicc_limit") == 1
    assert parse_limit(20, field="cicc_limit") == 20
    with pytest.raises(ActionError, match="between 1 and 20"):
        parse_limit(0, field="ima_limit_per_group")
    with pytest.raises(ActionError, match="between 1 and 20"):
        parse_limit(21, field="ima_limit_per_group")
    with pytest.raises(ActionError, match="integer"):
        parse_limit("nope", field="cicc_limit")
    from ops_lab_knobs import parse_days
    assert parse_days(3) == 3
    assert parse_days(14) == 14
    with pytest.raises(ActionError, match="between 1 and 14"):
        parse_days(0)
    assert parse_batch(40) == 40
    assert parse_batch(1) == 1
    assert parse_batch(200) == 200
    with pytest.raises(ActionError, match="between 1 and 200"):
        parse_batch(0)
    with pytest.raises(ActionError, match="between 1 and 200"):
        parse_batch(201)
    with pytest.raises(ActionError, match="integer"):
        parse_batch("big")


def test_validate_settings_defaults_and_merge():
    assert validate_settings({}) == DEFAULTS
    row = validate_settings(
        {
            "daily_sync_clock": "4:30",
            "ima_limit_per_group": 8,
            "cicc_limit": 12,
            "ima_groups_parallel": False,
            "puller_batch_size": 60,
        }
    )
    assert row["daily_sync_clock"] == "04:30"
    assert row["ima_groups_parallel"] is False
    assert row["puller_batch_size"] == 60
    merged = validate_settings({"ima_limit_per_group": 7}, base=row)
    assert merged["daily_sync_clock"] == "04:30"
    assert merged["ima_limit_per_group"] == 7


def test_save_requires_confirm_and_writes_json(lab_env, monkeypatch):
    cache, _secrets = lab_env
    with pytest.raises(ActionError, match="confirm required"):
        save_settings({"daily_sync_clock": "05:00", "ima_limit_per_group": 4})
    with pytest.raises(ActionError, match="confirm required"):
        save_settings({"confirm": "true", "ima_limit_per_group": 4})

    def boom(*_a, **_k):
        raise FileNotFoundError("systemctl")

    monkeypatch.setattr("ops_lab_knobs.subprocess.run", boom)
    result = save_settings(
        {
            "confirm": True,
            "daily_sync_clock": "04:15",
            "ima_limit_per_group": 9,
            "cicc_limit": 6,
            "ima_groups_parallel": False,
            "puller_batch_size": 55,
        }
    )
    assert result["ok"] is True
    assert result["settings"]["daily_sync_clock"] == "04:15"
    path = cache / "ops-lab-settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["ima_limit_per_group"] == 9
    assert data["cicc_limit"] == 6
    assert data["ima_groups_parallel"] is False
    assert data["puller_batch_size"] == 55
    assert stat.S_IMODE(path.stat().st_mode) == 0o664
    env_path = cache / "ops-puller.env"
    env_text = env_path.read_text(encoding="utf-8")
    assert "PULLER_BATCH_SIZE=55" in env_text
    assert "password" not in env_text.lower()
    assert "cookie" not in env_text.lower()
    audit = (cache / "logs" / "ops-audit.jsonl").read_text(encoding="utf-8")
    assert "settings-save" in audit
    assert "cookie" not in audit
    assert "password" not in audit
    assert result["apply"]["host_command"]
    assert "apply-lab-sync-timers.sh" in result["apply"]["host_command"]
    assert "04:15" in result["apply"]["host_command"]


def test_get_settings_defaults_when_missing(lab_env):
    payload = get_settings()
    assert payload["ok"] is True
    assert payload["settings"] == DEFAULTS
    assert payload["exists"] is False
    assert "refresh_token" not in json.dumps(payload)
    assert payload["timers"]["ima"]["unit"].endswith(".timer")


def test_load_settings_skips_corrupt_fields(lab_env):
    cache, _secrets = lab_env
    (cache / "ops-lab-settings.json").write_text(
        json.dumps({"ima_limit_per_group": 99, "puller_batch_size": 40, "daily_sync_clock": "07:10"}),
        encoding="utf-8",
    )
    loaded = load_settings()
    assert loaded["ima_limit_per_group"] == 10
    assert loaded["puller_batch_size"] == 40
    assert loaded["daily_sync_clock"] == "07:10"


def test_api_settings_auth_and_confirm(client, lab_env, monkeypatch):
    cache, _secrets = lab_env
    assert client.get("/api/settings").status_code == 401
    assert client.post("/api/settings", json={"confirm": True}).status_code == 401
    assert _login(client).status_code == 303
    got = client.get("/api/settings")
    assert got.status_code == 200
    assert got.json()["settings"]["puller_batch_size"] == 40
    denied = client.post(
        "/api/settings",
        json={"ima_limit_per_group": 8, "daily_sync_clock": "06:00"},
    )
    assert denied.status_code == 400
    assert denied.json()["error"] == "confirm required"
    bad = client.post(
        "/api/settings",
        json={"confirm": True, "ima_limit_per_group": 99},
    )
    assert bad.status_code == 400
    monkeypatch.setattr(
        "ops_lab_knobs.subprocess.run",
        lambda *_a, **_k: (_ for _ in ()).throw(FileNotFoundError("systemctl")),
    )
    ok = client.post(
        "/api/settings",
        json={
            "confirm": True,
            "daily_sync_clock": "02:45",
            "ima_limit_per_group": 11,
            "cicc_limit": 12,
            "ima_groups_parallel": True,
            "puller_batch_size": 40,
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["settings"]["daily_sync_clock"] == "02:45"
    dumped = json.dumps(body)
    assert "lab-secret" not in dumped
    assert "refresh_token" not in dumped
    assert (cache / "ops-lab-settings.json").is_file()


def test_apply_timers_prefers_helper(tmp_path, monkeypatch, lab_env):
    helper = tmp_path / "apply-lab-sync-timers.sh"
    helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    helper.chmod(0o755)
    monkeypatch.setenv("ARM_OPS_TIMER_HELPER", str(helper))
    seen = {}

    class Proc:
        returncode = 0
        stdout = "applied"
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return Proc()

    result = apply_sync_timers(
        {"daily_sync_clock": "03:00", "timezone": "Asia/Shanghai"},
        runner=fake_run,
    )
    assert result["applied"] is True
    assert result["method"] == "helper"
    assert seen["argv"][0] == str(helper)
    assert seen["argv"][1] == "03:00"


def test_dropin_text_resets_oncalendar():
    text = dropin_text("03:00", "Asia/Shanghai")
    assert "OnCalendar=\n" in text
    assert "OnCalendar=*-*-* 03:00:00 Asia/Shanghai" in text


def test_write_puller_env_mode(lab_env):
    cache, _secrets = lab_env
    path = write_puller_env({"puller_batch_size": 40})
    assert path == cache / "ops-puller.env"
    assert "PULLER_BATCH_SIZE=40" in path.read_text(encoding="utf-8")
    assert stat.S_IMODE(path.stat().st_mode) == 0o664


def test_dashboard_has_settings_section(client):
    assert _login(client).status_code == 303
    html = client.get("/").text
    js = (OPS_DIR / "static" / "ops.js").read_text(encoding="utf-8")
    assert 'id="settings-card"' in html
    assert 'id="settings-confirm"' in html
    assert "/api/settings" in html or "/api/settings" in js
    assert "PULLER_BATCH_SIZE" in html
    assert "每日同步时钟" in html
    assert "cicc_incr_days" in html or "中金增量天数" in html


def test_wrappers_read_settings_file():
    root = Path(__file__).resolve().parent.parent / "arm-lab-ops" / "bin"
    ima = (root / "ima-lab-sync-all.sh").read_text(encoding="utf-8")
    cicc = (root / "cicc-lab-sync.sh").read_text(encoding="utf-8")
    helper = (root / "apply-lab-sync-timers.sh").read_text(encoding="utf-8")
    assert "ima_host_sync.py" in ima
    assert "IMA_LAB_DUAL_COLLECT" in ima
    assert "IMA_PURE_GROUPS_FILE" in ima
    assert "cicc_report_collector.py" in cicc
    assert "--arm-middleware" in cicc
    assert "--days" in cicc
    assert "CICC_INCR_DAYS" in cicc
    assert 'DRY_RUN:-1' in cicc
    assert "OnCalendar=" in helper
    assert "vpush-ima-lab-sync.timer" in helper
    assert "vpush-cicc-lab-sync.timer" in helper
    nfsd = (root.parent / "systemd" / "nfsd-tailscale.conf").read_text(encoding="utf-8")
    assert "host=100.112.25.21" in nfsd
    assert nfsd.strip().endswith("host=100.112.25.21")
    assert "cookie" not in ima.lower()
    assert "password" not in ima.lower()


def test_host_units_prefer_systemd_not_compose():
    systemd = Path(__file__).resolve().parent.parent / "arm-lab-ops" / "systemd"
    puller = (systemd / "vpush-ima-lab-puller.service").read_text(encoding="utf-8")
    ops = (systemd / "vpush-arm-lab-ops.service").read_text(encoding="utf-8")
    snippet = (systemd.parent / "docker-compose.snippet.yml").read_text(encoding="utf-8")
    readme = (systemd.parent / "README.md").read_text(encoding="utf-8")
    assert "puller_loop.py" in puller
    assert "CACHE_ROOT=/data/vpush-ima-cache" in puller
    assert "P115_COOKIES_FILE=/opt/vpush-ima-lab/secrets/115-cookies.txt" in puller
    assert "EnvironmentFile=-/data/vpush-ima-cache/ops-puller.env" in puller
    assert "docker.sock" not in puller
    assert "ops_app.py" in ops
    assert "ARM_OPS_BIND=tailscale" in ops
    assert "ARM_OPS_PASSWORD_FILE=/opt/vpush-ima-lab/secrets/arm-ops-password.txt" in ops
    assert not any(
        line.startswith("Environment=PULLER_CONTAINER_NAME") for line in ops.splitlines()
    )
    assert "docker.sock" not in ops
    assert "0.0.0.0" not in ops
    assert "UID=" not in puller and "UID=" not in ops
    assert "refresh_token" not in puller and "refresh_token" not in ops
    assert "Leftover" in snippet
    assert "vpush-arm-lab-ops.service" in snippet
    assert "vpush-ima-lab-puller.service" in readme
    assert "只留 OpenList" in readme
