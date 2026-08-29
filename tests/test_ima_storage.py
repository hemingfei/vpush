import json
import time
from pathlib import Path

from app.ima_storage import ImaStorageStatus

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_MARKERS = (
    "IMA_ARCHIVE_ROOT=${IMA_ARCHIVE_ROOT:-}",
    "IMA_STORAGE_STATUS_PATH=${IMA_STORAGE_STATUS_PATH:-}",
    "${IMA_ARCHIVE_HOST_PATH:-./data/ima}:/data/ima-archive",
)


PUBLIC_KEYS = {
    "status",
    "available",
    "writable",
    "checked_at",
    "used_percent",
    "inode_percent",
    "monthly_tx_bytes",
    "reason",
    "restic_last_success",
    "restic_last_check_at",
    "restic_last_check_ok",
}


def _write_status(path, **overrides):
    payload = {
        "checked_at": int(time.time()),
        "available": True,
        "writable": True,
        "used_percent": 10,
        "inode_percent": 1,
        "monthly_tx_bytes": 10,
        "capacity_blocked": False,
        "reason": "",
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload))
    return path


def test_local_mode_is_available_without_status_file():
    status = ImaStorageStatus(None, remote=False)
    assert status.public()["status"] == "local"
    assert status.can_read() is True
    assert status.can_write() is True


def test_remote_status_is_stale_after_180_seconds(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({
        "checked_at": int(time.time()) - 181,
        "available": True,
        "writable": True,
        "used_percent": 10,
        "inode_percent": 1,
        "monthly_tx_bytes": 10,
        "capacity_blocked": False,
        "reason": "",
    }))
    status = ImaStorageStatus(path, remote=True)
    assert status.can_read() is False
    assert status.can_write() is False
    assert status.public()["status"] == "stale"


def test_remote_status_blocks_writes_but_allows_reads(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({
        "checked_at": int(time.time()),
        "available": True,
        "writable": True,
        "used_percent": 81,
        "inode_percent": 2,
        "monthly_tx_bytes": 100,
        "capacity_blocked": True,
        "reason": "capacity",
    }))
    status = ImaStorageStatus(path, remote=True)
    assert status.can_read() is True
    assert status.can_write() is False
    assert status.public()["status"] == "capacity_blocked"


def test_remote_missing_status_file(tmp_path):
    path = tmp_path / "missing.json"
    status = ImaStorageStatus(path, remote=True)
    public = status.public()
    assert status.can_read() is False
    assert status.can_write() is False
    assert public["status"] == "missing"
    assert public["reason"] == "missing"
    assert public["available"] is False
    assert public["writable"] is False


def test_remote_invalid_json(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("{not-json")
    status = ImaStorageStatus(path, remote=True)
    public = status.public()
    assert status.can_read() is False
    assert status.can_write() is False
    assert public["status"] == "invalid"
    assert public["reason"] == "invalid"


def test_remote_rejects_string_booleans(tmp_path):
    path = _write_status(
        tmp_path / "status.json",
        available="true",
        writable="true",
        capacity_blocked="false",
    )
    status = ImaStorageStatus(path, remote=True)
    public = status.public()
    assert status.can_read() is False
    assert status.can_write() is False
    assert public["status"] == "invalid"
    assert public["reason"] == "invalid"


def test_remote_clamps_negative_percentages_and_bytes(tmp_path):
    path = _write_status(
        tmp_path / "status.json",
        used_percent=-5,
        inode_percent=-1,
        monthly_tx_bytes=-99,
    )
    status = ImaStorageStatus(path, remote=True)
    public = status.public()
    assert status.can_read() is True
    assert status.can_write() is True
    assert public["used_percent"] == 0
    assert public["inode_percent"] == 0
    assert public["monthly_tx_bytes"] == 0
    assert public["status"] == "available"


def test_remote_future_timestamp_over_five_minutes_is_invalid(tmp_path):
    path = _write_status(
        tmp_path / "status.json",
        checked_at=int(time.time()) + 301,
    )
    status = ImaStorageStatus(path, remote=True)
    public = status.public()
    assert status.can_read() is False
    assert status.can_write() is False
    assert public["status"] == "invalid"
    assert public["reason"] == "invalid"


def test_public_never_includes_sensitive_fields(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({
        "checked_at": int(time.time()),
        "available": True,
        "writable": True,
        "used_percent": 10,
        "inode_percent": 1,
        "monthly_tx_bytes": 10,
        "capacity_blocked": False,
        "reason": "",
        "path": "/mnt/vpush-ima",
        "nfs_host": "10.80.0.2",
        "password": "secret",
        "endpoint": "https://s3.example/restic",
        "wireguard_key": "abc",
    }))
    status = ImaStorageStatus(path, remote=True)
    public = status.public()
    assert set(public) == PUBLIC_KEYS
    blob = json.dumps(public)
    assert "/mnt/" not in blob
    assert "10.80.0.2" not in blob
    assert "secret" not in blob
    assert "s3.example" not in blob
    assert "wireguard" not in blob
    assert "password" not in blob
    assert "endpoint" not in blob


def test_compose_files_expose_optional_ima_archive_mount():
    for name in ("docker-compose.yml", "docker-compose.prod.yml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for marker in COMPOSE_MARKERS:
            assert marker in text, f"{name} missing {marker}"


def test_public_includes_restic_allowlist(tmp_path):
    path = _write_status(
        tmp_path / "status.json",
        restic_last_success=100,
        restic_last_check_at=90,
        restic_last_check_ok=True,
    )
    public = ImaStorageStatus(path, remote=True).public()
    assert public["restic_last_success"] == 100
    assert public["restic_last_check_at"] == 90
    assert public["restic_last_check_ok"] is True


def test_write_request_file_and_pending(tmp_path):
    from app.ima_storage import request_pending, write_request_file

    path = tmp_path / ".vpush-backup-request"
    write_request_file(path)
    assert path.is_file()
    assert request_pending(path, 0) is True
    assert request_pending(path, int(time.time()) + 10) is False
