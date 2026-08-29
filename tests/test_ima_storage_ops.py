"""Static contract tests for IMA remote storage host operations."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "deploy" / "ima-storage"

SCRIPTS = [
    "storage-health.sh",
    "main-health.sh",
    "restic-backup.sh",
    "restic-main-backup.sh",
    "restic-maintain.sh",
]

ARCHIVE_ENV = "/etc/vpush/ima-storage.env"
MAIN_ENV = "/etc/vpush/ima-main-backup.env"

SERVICES = [
    "vpush-ima-storage-health.service",
    "vpush-ima-main-health.service",
    "vpush-ima-restic-backup.service",
    "vpush-ima-main-backup.service",
    "vpush-ima-restic-check.service",
    "vpush-ima-main-restic-check.service",
    "vpush-ima-restic-prune.service",
]

PATH_UNITS = [
    "vpush-ima-refresh-request.path",
    "vpush-ima-backup-request.path",
]

TIMERS = [
    "vpush-ima-storage-health.timer",
    "vpush-ima-main-health.timer",
    "vpush-ima-restic-backup.timer",
    "vpush-ima-main-backup.timer",
    "vpush-ima-restic-check.timer",
    "vpush-ima-main-restic-check.timer",
    "vpush-ima-restic-prune.timer",
]

SECRET_PATTERNS = [
    # Allow loopback used by in-container health probes; still catch real endpoints.
    re.compile(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    re.compile(r"(?i)password\s*="),
    re.compile(r"(?i)secret[_-]?access[_-]?key\s*="),
    re.compile(r"(?i)aws_secret_access_key\s*="),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)s3:https?://"),
    re.compile(r"(?i)rest:https?://"),
    re.compile(r"(?i)RESTIC_REPOSITORY\s*=\s*\S+"),
]


def _read(name: str) -> str:
    path = OPS / name
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_required_ops_files_exist():
    required = SCRIPTS + SERVICES + TIMERS + PATH_UNITS + ["README.md"]
    missing = [name for name in required if not (OPS / name).is_file()]
    assert missing == [], f"missing deploy artifacts: {missing}"


def test_shell_scripts_use_strict_mode():
    for name in SCRIPTS:
        text = _read(name)
        first = text.splitlines()[0].strip()
        assert first in {"#!/bin/sh", "#!/usr/bin/env bash"}, name
        assert re.search(r"(?m)^set -eu\b", text) or re.search(
            r"(?m)^set -euo\b", text
        ), name


def test_scripts_contain_no_secrets_or_endpoints():
    for name in SCRIPTS:
        text = _read(name)
        for pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            assert match is None, f"{name} matched {pattern.pattern}: {match.group(0)!r}"


def test_scripts_declare_exact_root_env_files():
    mapping = {
        "storage-health.sh": {ARCHIVE_ENV},
        "main-health.sh": {ARCHIVE_ENV},
        "restic-backup.sh": {ARCHIVE_ENV},
        "restic-main-backup.sh": {MAIN_ENV},
        "restic-maintain.sh": {ARCHIVE_ENV, MAIN_ENV},
    }
    for name, allowed in mapping.items():
        text = _read(name)
        for env_path in allowed:
            assert env_path in text, f"{name} must declare {env_path}"
        # archive/main scripts must not hard-require the other env
        if name == "restic-main-backup.sh":
            assert ARCHIVE_ENV not in text
        if name in {"storage-health.sh", "main-health.sh", "restic-backup.sh"}:
            assert MAIN_ENV not in text
        if name == "restic-maintain.sh":
            assert "check" in text and "prune" in text
            assert ARCHIVE_ENV in text and MAIN_ENV in text


def test_health_json_forced_to_container_readable_mode():
    for name in ("storage-health.sh", "main-health.sh"):
        text = _read(name)
        assert "99:100" in text or "99:100" in text.replace(" ", ""), name
        assert re.search(r"chown\s+99:100\b", text), name
        assert re.search(r"chmod\s+0640\b", text) or re.search(r"chmod\s+640\b", text), name
        assert ".vpush-storage-health.json" in text or "STATUS_OUTPUT" in text or "ima_storage_status.json" in text, name


def test_readme_documents_all_squash_nfs_identity():
    text = _read("README.md")
    assert "all_squash" in text
    assert "anonuid=99" in text
    assert "anongid=100" in text


def test_archive_backup_uses_low_priority_and_upload_limit():
    text = _read("restic-backup.sh")
    assert "nice" in text
    assert "ionice" in text
    assert "--limit-upload" in text
    assert "20480" in text
    assert "--tag ima-archive" in text
    assert "RESTIC_SUCCESS_FILE" in text


def test_main_backup_uses_online_sqlite_helper_and_fails_closed_on_env_mode():
    text = _read("restic-main-backup.sh")
    assert "scripts/backup.py" in text
    assert "BACKUP_PY" in text
    assert "/opt/vpush/scripts/backup.py" in text
    assert "/opt/vpush/src/scripts/backup.py" in text
    assert "backup.py not found" in text
    assert "/opt/vpush/data/dav.db" in text
    assert "--tag ima-control" in text
    assert MAIN_ENV in text
    assert "main-restic-last-success" in text
    assert re.search(r"root:root", text)
    assert re.search(r"0600|600", text)
    assert "/opt/vpush/.env" in text
    # never copy the live db file directly
    assert not re.search(r"\bcp\b.*dav\.db", text)
    assert "FEISHU_CREDENTIAL_KEY" in text or "FEISHU_CREDENTIAL_KEY" in _read("README.md")


def test_archive_and_main_backups_are_distinct():
    archive = _read("restic-backup.sh")
    main = _read("restic-main-backup.sh")
    assert ARCHIVE_ENV in archive and MAIN_ENV in main
    assert "--tag ima-archive" in archive
    assert "--tag ima-control" in main
    assert ARCHIVE_ENV not in main
    assert MAIN_ENV not in archive


def test_timers_are_persistent_with_randomized_delay():
    for name in TIMERS:
        text = _read(name)
        assert re.search(r"(?m)^Persistent=true\s*$", text), name
        assert re.search(r"(?m)^RandomizedDelaySec=\d+\s*$", text), name


def test_timer_schedules_match_runbook():
    schedules = {
        "vpush-ima-storage-health.timer": r"OnCalendar=.*:0/5",
        "vpush-ima-main-health.timer": r"OnCalendar=.*\*",
        "vpush-ima-restic-backup.timer": r"OnCalendar=.*04:30",
        "vpush-ima-main-backup.timer": r"OnCalendar=.*03:45",
        "vpush-ima-restic-check.timer": r"OnCalendar=.*Sun.*05:30",
        "vpush-ima-main-restic-check.timer": r"OnCalendar=.*Sun.*06:00",
        "vpush-ima-restic-prune.timer": r"OnCalendar=.*Sun.*06:30",
    }
    delays = {
        "vpush-ima-restic-backup.timer": "1200",
        "vpush-ima-main-backup.timer": "900",
    }
    for name, pattern in schedules.items():
        text = _read(name)
        assert re.search(pattern, text), name
    for name, delay in delays.items():
        text = _read(name)
        assert f"RandomizedDelaySec={delay}" in text, name


def test_health_scripts_have_fixed_exit_semantics():
    storage = _read("storage-health.sh")
    main = _read("main-health.sh")
    for text, name in ((storage, "storage-health.sh"), (main, "main-health.sh")):
        assert "exit 1" in text or "exit 2" in text, name
        assert "mv" in text, f"{name} must atomically publish JSON"
        # probe path still publishes status
        assert "checked_at" in text, name


def test_main_health_logs_one_transition_event():
    text = _read("main-health.sh")
    assert "logger -p daemon.warning" in text
    assert "main-health-last" in text
    assert "/run/vpush-ima-placeholder" in text
    assert "docker compose -f \"$COMPOSE_FILE\" up -d --no-deps --force-recreate vpush" in text
    assert "COMPOSE_FILE" in text
    assert "/opt/vpush/docker-compose.prod.yml" in text
    assert "/opt/vpush/docker-compose.yml" in text
    assert "urllib.request" in text
    assert "127.0.0.1:8000/healthz/ima-storage" in text
    assert "wget" not in text
    assert "mount " in text
    assert ".vpush-ima-root" in text
    assert "nc -z" in text or "nc -z" in text.replace('"', "")


def test_systemd_services_harden_runtime():
    for name in SERVICES:
        text = _read(name)
        assert re.search(r"(?m)^UMask=0077\s*$", text), name
        assert re.search(r"(?m)^NoNewPrivileges=true\s*$", text), name
        match = re.search(r"(?m)^TimeoutStartSec=(\d+)\s*$", text)
        assert match, name
        assert 1 <= int(match.group(1)) <= 14400, name


def test_restic_maintain_contract():
    text = _read("restic-maintain.sh")
    assert "--read-data-subset=5%" in text
    assert "forget --tag ima-archive --keep-daily 30 --prune" in text
    assert "RESTIC_CHECK_FILE" in text
    assert '"ok"' in text or '"ok":' in text or "ok" in text
    assert "checked_at" in text
    # date guard for monthly prune via weekly timer
    assert "first" in text.lower() or re.search(r"\b(day|date|DOM)\b", text)
    assert ARCHIVE_ENV in text and MAIN_ENV in text


def test_readme_is_ops_runbook():
    text = _read("README.md")
    for needle in (
        "wireguard",
        "nfs",
        "restic",
        "vnstat",
        "systemctl enable",
        "journalctl",
        "ima-storage.env",
        "ima-main-backup.env",
        "install -m 600",
        "https://vpush.net/healthz/ima-storage",
        "99:100",
        "0640",
        "0600",
        "UMask=0077",
        "all_squash",
    ):
        assert needle.lower() in text.lower(), needle
