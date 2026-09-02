"""中金采集控制：NFS 控制目录读写、触发命令、每日增量开关、admin API。"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.cicc_collector import CiccControl, from_env
from app.main import create_app


@pytest.fixture
def ctrl(tmp_path):
    archive = tmp_path / "archive"
    (archive / "local" / ".cicc" / "commands").mkdir(parents=True)
    return CiccControl(str(archive)), archive


def test_status_missing_file_reports_stale(ctrl):
    ctl, _ = ctrl
    data = ctl.status()
    assert data["available"] is True
    assert data["stale"] is True


def test_status_parses_storage_side_file(ctrl):
    ctl, archive = ctrl
    status_path = archive / "local" / ".cicc" / "status.json"
    status_path.write_text(json.dumps({
        "ts": time.time(), "running": 2, "files_total": 100,
        "schedule_enabled": True, "logs": {"y2026_company": "... 20 下载"},
        "commands": [], "compress_running": 0, "last_incremental": None,
    }), encoding="utf-8")
    data = ctl.status()
    assert data["stale"] is False
    assert data["running"] == 2
    assert data["files_total"] == 100


def test_trigger_writes_atomic_command_file(ctrl):
    ctl, archive = ctrl
    result = ctl.trigger("year", "kale")
    assert result == {"queued": "year"}
    files = list((archive / "local" / ".cicc" / "commands").glob("*.json"))
    assert len(files) == 1
    cmd = json.loads(files[0].read_text(encoding="utf-8"))
    assert cmd["mode"] == "year"
    assert cmd["actor"] == "kale"
    assert not list((archive / "local" / ".cicc" / "commands").glob(".tmp*"))


def test_trigger_rejects_unknown_mode(ctrl):
    ctl, _ = ctrl
    with pytest.raises(ValueError):
        ctl.trigger("rm -rf /", "kale")


def test_schedule_toggle(ctrl):
    ctl, archive = ctrl
    flag = archive / "local" / ".cicc" / "incremental.enabled"
    assert ctl.schedule_enabled() is False
    assert ctl.set_schedule(True) == {"schedule_enabled": True}
    assert flag.exists()
    assert ctl.schedule_enabled() is True
    assert ctl.set_schedule(False) == {"schedule_enabled": False}
    assert not flag.exists()


def test_from_env_none_without_archive(monkeypatch):
    monkeypatch.delenv("IMA_ARCHIVE_ROOT", raising=False)
    assert from_env() is None


@pytest.fixture(autouse=True)
def _ui_only_env(monkeypatch):
    """测试实例必须关闭后台任务（避免抢生产 Telegram 机器人）；经 monkeypatch
    设置，测完自动还原——裸 os.environ 会泄漏到同进程后续测试，把
    create_app 的调度器接线（on_mx_config_changed 等）整体关掉。"""
    monkeypatch.setenv("DAV_UI_ONLY", "1")


def _admin_client():
    tmp = tempfile.mkdtemp()
    os.environ["IMA_ARCHIVE_ROOT"] = tempfile.mkdtemp()
    os.environ.pop("IMA_PULL_URL", None)
    cmd_dir = Path(os.environ["IMA_ARCHIVE_ROOT"]) / "local" / ".cicc" / "commands"
    cmd_dir.mkdir(parents=True)
    app = create_app(config=None, db_path=Path(tmp) / "cicc.db")
    return TestClient(app), cmd_dir


def _admin_headers(client):
    client.app.state.db.add_register_code("CICC01")
    resp = client.post("/api/auth/register", json={
        "username": "admin1", "password": "secret123", "code": "CICC01"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    client.app.state.db.update_user(data["user"]["id"], is_admin=True)
    return {"Authorization": f"Bearer {data['token']}"}


def test_admin_cicc_api(tmp_path, monkeypatch):
    monkeypatch.delenv("IMA_PULL_URL", raising=False)
    monkeypatch.setenv("IMA_ARCHIVE_ROOT", str(tmp_path / "archive"))
    (tmp_path / "archive" / "local" / ".cicc" / "commands").mkdir(parents=True)
    app = create_app(config=None, db_path=Path(tmp_path) / "cicc.db")
    client = TestClient(app)
    headers = _admin_headers(client)

    r = client.get("/api/admin/cicc/status", headers=headers)
    assert r.status_code == 200
    assert r.json()["available"] is True
    assert r.json()["stale"] is True

    r = client.post("/api/admin/cicc/trigger", json={"mode": "compress"},
                    headers=headers)
    assert r.status_code == 200
    assert r.json() == {"queued": "compress"}
    cmds = list((tmp_path / "archive" / "local" / ".cicc" / "commands").glob("*.json"))
    assert len(cmds) == 1

    r = client.post("/api/admin/cicc/trigger", json={"mode": "bogus"},
                    headers=headers)
    assert r.status_code == 400

    r = client.put("/api/admin/cicc/schedule", json={"enabled": True},
                   headers=headers)
    assert r.status_code == 200
    assert (tmp_path / "archive" / "local" / ".cicc" / "incremental.enabled").exists()
