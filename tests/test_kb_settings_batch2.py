"""知识库设置增强第二批：熔断门控/告警文案/品类定向命令/备份节 解析测试。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_vps(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/vps/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# —— 功能1：paused 熔断门控（cicc-incremental）——

def test_paused_skip_auth_within_48h():
    m = _load_vps("cicc-incremental")
    now = 1_000_000_000
    assert m.paused_skip({"reason": "auth", "ts": now - 3600}, now) == (True, "paused_auth")


def test_paused_skip_auth_expired_after_48h():
    m = _load_vps("cicc-incremental")
    now = 1_000_000_000
    assert m.paused_skip({"reason": "auth", "ts": now - 49 * 3600}, now) == (False, "")


def test_paused_skip_quota_never_blocks():
    m = _load_vps("cicc-incremental")
    now = 1_000_000_000
    assert m.paused_skip({"reason": "quota", "ts": now - 60}, now) == (False, "")


def test_paused_skip_no_file_or_garbage():
    m = _load_vps("cicc-incremental")
    now = 1_000_000_000
    assert m.paused_skip(None, now) == (False, "")
    assert m.paused_skip({}, now) == (False, "")
    assert m.paused_skip({"reason": "auth", "ts": 0}, now) == (False, "")


# —— 功能1：熔断告警文案（cicc_alerts）——

def test_paused_alert_quota_text():
    from app.cicc_alerts import paused_alert

    now = 5_000_000
    status = {"paused": {"reason": "quota", "ts": now, "detail": "code 400013 本月配额已满"}}
    key, msg = paused_alert(status, {}) or ("", "")
    assert key == "paused" and "配额" in msg and "月初" in msg


def test_paused_alert_auth_text():
    from app.cicc_alerts import paused_alert

    now = 5_000_000
    status = {"paused": {"reason": "auth", "ts": now, "detail": "HTTP 401 登录态失效"}}
    _, msg = paused_alert(status, {}) or ("", "")
    assert "登录态" in msg and "Cookie" in msg


def test_paused_alert_only_when_ts_advances():
    from app.cicc_alerts import paused_alert

    now = 5_000_000
    state = {"paused_notified_ts": now}
    assert paused_alert({}, state) is None
    assert paused_alert({"paused": {"reason": "quota", "ts": now}}, state) is None  # ts 未前进
    assert paused_alert({"paused": {"reason": "quota", "ts": now + 1}}, state) is not None


# —— 功能2：settings 命令 payload（CiccControl → dispatch 消费）——

def test_settings_command_payload(tmp_path):
    from app.cicc_collector import CiccControl

    ctl = CiccControl(str(tmp_path))
    ctl.set_cicc_settings(["宏观经济", "固定收益"], "tester")
    cmds = list((tmp_path / "local" / ".cicc" / "commands").glob("*.json"))
    assert len(cmds) == 1
    body = json.loads(cmds[0].read_text(encoding="utf-8"))
    assert body["mode"] == "settings"
    assert body["categories"] == ["宏观经济", "固定收益"]
    assert body["actor"] == "tester"


def test_settings_empty_means_all(tmp_path):
    from app.cicc_collector import CiccControl

    ctl = CiccControl(str(tmp_path))
    ctl.set_cicc_settings([], "tester")
    (cmd,) = (tmp_path / "local" / ".cicc" / "commands").glob("*.json")
    assert json.loads(cmd.read_text(encoding="utf-8"))["categories"] == []


# —— 功能2：品类名单一致性（前端硬编码 vs 后端校验）——

def test_category_list_matches_frontend():
    from app.cicc_collector import CICC_CATEGORIES

    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    for cat in CICC_CATEGORIES:
        assert f'"{cat}"' in js, f"前端 CICC_CATEGORIES 缺少 {cat}"


# —— 功能3：备份节解析（mock restic 输出）——

def test_parse_snapshots_fields():
    m = _load_vps("cicc-status")
    raw = json.dumps([
        {"id": "a" * 64, "short_id": "abcdef1234", "time": "2026-08-30T03:00:00+08:00",
         "summary": {"total_bytes_processed": 123456789}},
        {"id": "b" * 64, "time": "2026-08-29T03:00:00+08:00"},  # 无 summary → size 0
    ])
    snaps = m.parse_snapshots(raw)
    assert snaps[0] == {"id": "abcdef12", "time": "2026-08-30T03:00:00+08:00", "size": 123456789}
    assert snaps[1]["size"] == 0 and len(snaps[1]["id"]) == 8


def test_parse_snapshots_bad_output():
    m = _load_vps("cicc-status")
    assert m.parse_snapshots("") == []
    assert m.parse_snapshots("not json") == []
    assert m.parse_snapshots('{"x":1}') == []


def test_backup_section_unconfigured(tmp_path, monkeypatch):
    m = _load_vps("cicc-status")
    monkeypatch.setattr(m, "HEALTH_FILE", str(tmp_path / "health.json"))
    monkeypatch.setattr(m, "BACKUP_ENV", str(tmp_path / "env"))
    (tmp_path / "health.json").write_text(json.dumps({"restic_last_success": 123,
                                                      "restic_last_check_ok": True}))
    section = m.backup_section()
    assert section["configured"] is False
    assert section["restic_last_success"] == 123
    assert section["restic_last_check_ok"] is True
    assert "RESTIC_REPOSITORY" in section["reason"]


def test_backup_section_runs_restic(tmp_path, monkeypatch):
    m = _load_vps("cicc-status")
    monkeypatch.setattr(m, "HEALTH_FILE", str(tmp_path / "health.json"))
    env_file = tmp_path / "ima-storage.env"
    env_file.write_text('# comment\nRESTIC_REPOSITORY="/srv/backup/repo"\nRESTIC_PASSWORD=secret\n')
    monkeypatch.setattr(m, "BACKUP_ENV", str(env_file))
    snaps = [{"id": "c" * 64, "short_id": "deadbeef", "time": "2026-08-30T03:00:00+08:00",
              "summary": {"total_bytes_processed": 1}}]
    calls = {}

    class R:
        returncode = 0
        stdout = json.dumps(snaps)
        stderr = ""

    def fake_run(argv, **kwargs):
        calls["argv"], calls["env"] = argv, kwargs["env"]
        return R()

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    section = m.backup_section()
    assert section["configured"] is True
    assert section["snapshots"][0]["id"] == "deadbeef"
    assert calls["argv"][:3] == ["restic", "snapshots", "--latest"]
    assert calls["env"]["RESTIC_REPOSITORY"] == "/srv/backup/repo"  # env 文件已 source
    assert "secret" not in json.dumps(section)  # 敏感 env 不落 status


def test_backup_section_restic_failure_reports_reason(tmp_path, monkeypatch):
    m = _load_vps("cicc-status")
    monkeypatch.setattr(m, "HEALTH_FILE", str(tmp_path / "health.json"))
    monkeypatch.setattr(m, "BACKUP_ENV", str(tmp_path / "env"))
    (tmp_path / "env").write_text("RESTIC_REPOSITORY=/srv/backup/repo\n")

    class R:
        returncode = 1
        stdout = ""
        stderr = "Fatal: wrong password"

    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: R())
    section = m.backup_section()
    assert section["configured"] is True and "snapshots" not in section
    assert "wrong password" in section["reason"]
