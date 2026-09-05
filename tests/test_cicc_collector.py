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
from scripts import cicc_report_collector


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


def test_read_schedule_rejects_out_of_range_stored_time(ctrl):
    ctl, archive = ctrl
    status_path = archive / "local" / ".cicc" / "status.json"
    status_path.write_text(json.dumps({
        "ts": time.time(), "storage": {"schedule": {"time": "24:99"}},
    }), encoding="utf-8")

    assert ctl.read_schedule()["time"] == "03:00"


def test_from_env_none_without_archive(monkeypatch):
    monkeypatch.delenv("IMA_ARCHIVE_ROOT", raising=False)
    assert from_env() is None


def _admin_client():
    tmp = tempfile.mkdtemp()
    os.environ["DAV_UI_ONLY"] = "1"
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


def test_prepare_target_dir_repairs_category_parent(monkeypatch, tmp_path):
    target = tmp_path / "local" / "cicc-research" / "金融工程" / "0903"
    target.parent.mkdir(parents=True)
    target.parent.chmod(0o700)
    chowns = []
    monkeypatch.setattr(
        cicc_report_collector.os,
        "chown",
        lambda path, uid, gid: chowns.append((Path(path), uid, gid)),
    )

    cicc_report_collector.prepare_target_dir(target, fix_owner=True)

    assert target.is_dir()
    assert chowns == [
        (target.parent, cicc_report_collector.CHOWN_UID, cicc_report_collector.CHOWN_GID),
        (target, cicc_report_collector.CHOWN_UID, cicc_report_collector.CHOWN_GID),
    ]
    assert target.parent.stat().st_mode & 0o777 == 0o750
    assert target.stat().st_mode & 0o777 == 0o750


def test_load_filters_file_preserves_commas_and_rejects_invalid_values(tmp_path):
    path = tmp_path / "filters.json"
    path.write_text(json.dumps({
        "categories": ["公司研究"],
        "keywords": ["alpha,beta", "半导体"],
    }, ensure_ascii=False), encoding="utf-8")

    assert cicc_report_collector.load_filters_file(path) == (
        ["公司研究"], ["alpha,beta", "半导体"],
    )

    path.write_text(json.dumps({"categories": [], "keywords": [123]}), encoding="utf-8")
    with pytest.raises(ValueError, match="keywords"):
        cicc_report_collector.load_filters_file(path)


def test_write_completion_marker_is_atomic(tmp_path):
    path = tmp_path / "completed.json"
    cicc_report_collector.write_completion_marker(path, "command-id")

    assert json.loads(path.read_text(encoding="utf-8")) == {"id": "command-id"}
    assert not list(tmp_path.glob(".completed.*"))



def test_admin_cicc_api(tmp_path, monkeypatch):
    monkeypatch.delenv("IMA_PULL_URL", raising=False)
    monkeypatch.setenv("IMA_ARCHIVE_ROOT", str(tmp_path / "archive"))
    (tmp_path / "archive" / "local" / ".cicc" / "commands").mkdir(parents=True)
    os.environ["DAV_UI_ONLY"] = "1"
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
