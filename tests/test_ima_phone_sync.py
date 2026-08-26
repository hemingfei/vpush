import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.ima_documents import ImaDocumentConfig
from scripts.ima_phone_sync import (
    _REMOTE_UPDATE_SCRIPT,
    ImaCredentials,
    ImaPhoneSyncError,
    SyncOptions,
    _prompt_sync_options,
    build_adb_command,
    build_ssh_command,
    load_sync_config,
    main,
    parse_login_preferences,
    read_phone_preferences,
    resolve_sync_options,
    save_sync_config,
    update_remote_settings,
    validate_ima_credentials,
)

ROOT = Path(__file__).resolve().parents[1]

PREFS_XML = b"""\
<map>
  <string name="pref_login_response">{&quot;data&quot;:{&quot;userId&quot;:&quot;001aa361168019ef&quot;,&quot;refreshToken&quot;:&quot;refresh-secret&quot;,&quot;token&quot;:&quot;short-lived&quot;}}</string>
</map>
"""


def test_parse_login_preferences_extracts_only_ima_credentials():
    credentials = parse_login_preferences(PREFS_XML)

    assert credentials == ImaCredentials(
        uid="001aa361168019ef",
        refresh_token="refresh-secret",
    )


def test_parse_login_preferences_rejects_missing_login_response():
    with pytest.raises(ImaPhoneSyncError, match="pref_login_response"):
        parse_login_preferences(b"<map><string name=\"other\">x</string></map>")


def test_parse_login_preferences_rejects_missing_refresh_token():
    xml = b'<map><string name="pref_login_response">{"userId":"uid_123"}</string></map>'

    with pytest.raises(ImaPhoneSyncError, match="Refresh Token"):
        parse_login_preferences(xml)


def test_parse_login_preferences_rejects_unsafe_uid():
    xml = b'<map><string name="pref_login_response">{"userId":"../../db","refreshToken":"secret"}</string></map>'

    with pytest.raises(ImaPhoneSyncError, match="UID"):
        parse_login_preferences(xml)


def test_parse_login_preferences_enforces_expected_uid():
    with pytest.raises(ImaPhoneSyncError, match="UID 不匹配"):
        parse_login_preferences(PREFS_XML, expected_uid="another-account")


def test_adb_reader_keeps_xml_out_of_command_arguments():
    captured = {}

    def runner(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout=PREFS_XML, stderr=b"")

    assert read_phone_preferences("381a2bca", runner=runner) == PREFS_XML
    assert captured["command"] == build_adb_command("381a2bca")
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["input"] is None
    assert "refresh-secret" not in captured["command"]


def test_ima_refresh_validation_does_not_store_short_lived_token():
    seen = {}

    class FakeClient:
        def __init__(self, config):
            seen["config"] = config

        def refresh(self):
            seen["refresh_called"] = True
            return "short-lived-token"

    credentials = ImaCredentials("uid_123", "refresh-secret")

    assert validate_ima_credentials(credentials, client_factory=FakeClient) == credentials
    assert seen["config"] == ImaDocumentConfig(uid="uid_123", refresh_token="refresh-secret")
    assert seen["refresh_called"] is True


def test_ima_refresh_validation_redacts_upstream_error():
    class FailingClient:
        def __init__(self, config):
            pass

        def refresh(self):
            raise RuntimeError("IMA refresh failed token=refresh-secret")

    with pytest.raises(ImaPhoneSyncError, match="Refresh Token 校验失败") as exc_info:
        validate_ima_credentials(
            ImaCredentials("uid_123", "refresh-secret"),
            client_factory=FailingClient,
        )
    assert "refresh-secret" not in str(exc_info.value)


def test_ssh_update_transfers_token_on_stdin_only(tmp_path):
    captured = {}

    def runner(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout=b'{"updated":true}', stderr=b"")

    credentials = ImaCredentials("uid_123", "refresh-secret")
    update_remote_settings(
        credentials,
        host="179.255.150.134",
        user="root",
        ssh_key=tmp_path / "id_rsa.pem",
        remote_db="/opt/vpush/data/dav.db",
        runner=runner,
    )

    assert "refresh-secret" not in captured["command"]
    payload = json.loads(captured["kwargs"]["input"])
    assert payload == {"uid": "uid_123", "refresh_token": "refresh-secret"}
    assert captured["kwargs"]["check"] is False
    assert captured["kwargs"]["capture_output"] is True
    assert build_ssh_command(
        host="179.255.150.134",
        user="root",
        ssh_key=tmp_path / "id_rsa.pem",
        remote_db="/opt/vpush/data/dav.db",
    ) == captured["command"]


def test_ssh_update_rejects_uid_mismatch_before_transport(tmp_path):
    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("SSH must not run")

    with pytest.raises(ImaPhoneSyncError, match="UID 不匹配"):
        update_remote_settings(
            ImaCredentials("phone-uid", "refresh-secret"),
            host="example.test",
            user="root",
            ssh_key=tmp_path / "id_rsa.pem",
            remote_db="/opt/vpush/data/dav.db",
            expected_uid="remote-uid",
            runner=runner,
        )
    assert called is False



def _make_settings_db(path, uid="uid_123", token="old-secret"):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        [("ima_pure_uid", uid), ("ima_pure_refresh_token", token)],
    )
    conn.commit()
    conn.close()


def test_remote_update_script_commits_both_settings_atomically(tmp_path):
    db_path = tmp_path / "dav.db"
    _make_settings_db(db_path)
    payload = json.dumps({"uid": "uid_123", "refresh_token": "new-secret"}).encode()

    result = subprocess.run(
        [sys.executable, "-c", _REMOTE_UPDATE_SCRIPT, str(db_path)],
        input=payload,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode()
    conn = sqlite3.connect(db_path)
    values = dict(conn.execute("SELECT key, value FROM settings"))
    conn.close()
    assert values["ima_pure_uid"] == "uid_123"
    assert values["ima_pure_refresh_token"] == "new-secret"


def test_remote_update_script_rejects_uid_change_without_writing(tmp_path):
    db_path = tmp_path / "dav.db"
    _make_settings_db(db_path)
    payload = json.dumps({"uid": "other_uid", "refresh_token": "new-secret"}).encode()

    result = subprocess.run(
        [sys.executable, "-c", _REMOTE_UPDATE_SCRIPT, str(db_path)],
        input=payload,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    conn = sqlite3.connect(db_path)
    values = dict(conn.execute("SELECT key, value FROM settings"))
    conn.close()
    assert values["ima_pure_uid"] == "uid_123"
    assert values["ima_pure_refresh_token"] == "old-secret"


def test_sync_config_round_trip_is_allowlisted_and_mode_600(tmp_path):
    path = tmp_path / "ima_phone_sync.env"
    options = SyncOptions(
        device="381a2bca",
        host="179.255.150.134",
        user="root",
        ssh_key="/tmp/dmit-ssh/id_rsa.pem",
        remote_db="/opt/vpush/data/dav.db",
        expected_uid="001aa361168019ef",
    )

    save_sync_config(path, options)

    assert load_sync_config(path) == options
    assert path.stat().st_mode & 0o777 == 0o600
    assert "refresh_token" not in path.read_text().lower()


def test_sync_config_rejects_unknown_fields(tmp_path):
    path = tmp_path / "ima_phone_sync.env"
    path.write_text("IMA_SYNC_HOST=example.test\nIMA_REFRESH_TOKEN=secret\n")
    path.chmod(0o600)

    with pytest.raises(ImaPhoneSyncError, match="配置项无效"):
        load_sync_config(path)


def test_resolve_sync_options_prefers_cli_values(tmp_path):
    path = tmp_path / "ima_phone_sync.env"
    save_sync_config(
        path,
        SyncOptions("phone", "old.example", "root", "old-key", "/old.db", "uid"),
    )

    resolved = resolve_sync_options(
        config_path=path,
        cli_values={"host": "new.example", "ssh_key": "/new-key"},
    )

    assert resolved.host == "new.example"
    assert resolved.ssh_key == "/new-key"
    assert resolved.device == "phone"
    assert resolved.remote_db == "/old.db"


def test_first_run_prompt_saves_non_secret_config(tmp_path, monkeypatch):
    answers = iter(
        [
            "381a2bca",
            "example.test",
            "root",
            "/tmp/id_rsa",
            "/opt/vpush/data/dav.db",
            "uid_123",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    path = tmp_path / "ima_phone_sync.env"

    options = _prompt_sync_options(path)

    assert options == SyncOptions(
        "381a2bca",
        "example.test",
        "root",
        "/tmp/id_rsa",
        "/opt/vpush/data/dav.db",
        "uid_123",
    )
    assert path.stat().st_mode & 0o777 == 0o600
    assert "refresh" not in path.read_text().lower()


def test_one_click_returns_error_for_missing_host(tmp_path, monkeypatch):
    answers = iter(["381a2bca", "", "root", "", "/opt/vpush/data/dav.db", "uid_123"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    assert main(["--one-click", "--config-file", str(tmp_path / "missing.env")]) == 1


def test_one_click_launcher_uses_repo_root_and_virtualenv():
    launcher = (ROOT / "scripts" / "ima_phone_sync.command").read_text()

    assert "dirname" in launcher
    assert ".venv/bin/python" in launcher
    assert "--one-click" in launcher
    assert "source " not in launcher


def test_ssh_update_rejects_remote_path_injection(tmp_path):
    with pytest.raises(ImaPhoneSyncError, match="数据库路径"):
        build_ssh_command(
            host="example.test",
            user="root",
            ssh_key=tmp_path / "id_rsa.pem",
            remote_db="/tmp/db; touch /tmp/pwned",
        )
