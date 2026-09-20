"""ARM host IMA sync: production collector only, default-off, no secret leak."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import ima_host_sync as host


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    monkeypatch.delenv("VPUSH_ARM_STAGING_ROOT", raising=False)
    monkeypatch.delenv("IMA_ARCHIVE_ROOT", raising=False)
    monkeypatch.delenv("IMA_PULL_URL", raising=False)
    monkeypatch.delenv("IMA_UID", raising=False)
    monkeypatch.delenv("IMA_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("IMA_PURE_SECRETS_FILE", raising=False)


def _secrets(path: Path) -> Path:
    path.write_text(json.dumps({"uid": "lab-uid", "refresh_token": "lab-token"}), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_disabled_does_nothing(capsys):
    assert host.main([]) == 0
    assert "未启用" in capsys.readouterr().out


def test_enable_calls_production_sync_once(tmp_path, monkeypatch, capsys):
    secrets = _secrets(tmp_path / "ima-pure.json")
    groups = [{"id": "legacy", "name": "默认知识库", "knowledge_base_id": "kb",
               "root_folder_id": "root", "enabled": True}]
    groups_file = tmp_path / "groups.json"
    groups_file.write_text(json.dumps(groups), encoding="utf-8")
    captured = {}

    class FakeService:
        def __init__(self, db, index_root, **kwargs):
            captured["groups"] = db.get_setting("ima_pure_groups")
            captured["uid"] = db.get_setting("ima_pure_uid")
            captured["archive"] = str(kwargs.get("archive_root") or "")
            captured["trust_index_state"] = bool(kwargs.get("trust_index_state"))

        def sync_once(self):
            return {
                "status": "finished",
                "groups": 1,
                "downloaded": 2,
                "failed": 0,
                "last_error": "",
            }

    monkeypatch.setattr(host, "ImaDocumentService", FakeService)
    rc = host.main([
        "--enable",
        "--secrets", str(secrets),
        "--groups-file", str(groups_file),
        "--db", str(tmp_path / "ima-host.sqlite"),
        "--index-root", str(tmp_path / "index"),
        "--staging-root", str(tmp_path / "staging"),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out)["downloaded"] == 2
    assert "lab-token" not in out
    assert captured["uid"] == "lab-uid"
    assert "legacy" in (captured["groups"] or "")
    assert captured["archive"].endswith("staging")
    assert captured["trust_index_state"] is True
    assert "VPUSH_ARM_MIDDLEWARE" not in __import__("os").environ
    assert "VPUSH_ARM_STAGING_ROOT" not in __import__("os").environ


def test_failed_downloads_exit_1(tmp_path, monkeypatch):
    secrets = _secrets(tmp_path / "ima-pure.json")

    class FakeService:
        def __init__(self, *args, **kwargs):
            pass

        def sync_once(self):
            return {"status": "finished", "downloaded": 0, "failed": 3}

    monkeypatch.setattr(host, "ImaDocumentService", FakeService)
    rc = host.main([
        "--enable",
        "--secrets", str(secrets),
        "--db", str(tmp_path / "ima-host.sqlite"),
        "--index-root", str(tmp_path / "index"),
        "--staging-root", str(tmp_path / "staging"),
    ])
    assert rc == 1
