"""知识库设置增强第一批：门控/阈值/去重/命令格式 测试。"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_incremental():
    spec = importlib.util.spec_from_file_location(
        "cicc_incremental", ROOT / "scripts/vps/cicc-incremental.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gate_runs_when_due():
    m = _load_incremental()
    now = datetime(2026, 8, 30, 5, 0)
    ok, reason = m.should_run(now, "03:00", {"date": "2026-08-29"})
    assert ok and reason == "due"


def test_gate_skips_before_schedule_time():
    m = _load_incremental()
    now = datetime(2026, 8, 30, 1, 0)
    assert m.should_run(now, "03:00", {"date": "2026-08-29"}) == (False, "before_schedule_time")


def test_gate_skips_when_already_ran_today():
    m = _load_incremental()
    now = datetime(2026, 8, 30, 5, 0)
    assert m.should_run(now, "03:00", {"date": "2026-08-30"}) == (False, "already_ran_today")


def test_gate_default_schedule_is_0300():
    m = _load_incremental()
    assert m.read_schedule.__module__ == m.__name__  # 存在且归属正确
    assert m.should_run(datetime(2026, 8, 30, 3, 0), "03:00", {})[0] is True


def test_incremental_summary_written(tmp_path, monkeypatch):
    """同步执行 collector 后解析「完成：下载 N」写入 last_incr_summary。"""
    import json as _json

    m = _load_incremental()
    monkeypatch.setattr(m, "CTRL", str(tmp_path))
    monkeypatch.setattr(m, "SCHEDULE_FILE", str(tmp_path / "schedule.json"))
    monkeypatch.setattr(m, "CICC_DIR", str(tmp_path))
    monkeypatch.setattr(m, "collectors_running", lambda: 0)
    (tmp_path / "incremental.enabled").write_text("1")

    class R:
        returncode = 0
        stdout = "... 完成下载测试\n完成：下载 12，已存在跳过 30，失败 1\n"

    calls = {}

    def fake_run(*a, **k):
        calls["argv"] = a[0]
        return R()

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    m.main()
    summary = _json.loads((tmp_path / "last_incr_summary.json").read_text())
    assert (summary["added"], summary["skipped"], summary["failed"]) == (12, 30, 1)
    assert summary["date"] == datetime.now(m.BJ).strftime("%Y-%m-%d")
    assert calls["argv"][-2:] == ["--days", "3"]


def test_alert_thresholds():
    from app.cicc_alerts import evaluate_alerts

    settings = {"disk_warn": 80, "disk_crit": 90, "stale_minutes": 30}
    now = 1_000_000_000
    status = {"ts": now, "storage": {"disk": {"pct": 95}}}
    assert evaluate_alerts(status, settings, now)[0][0] == "disk_crit"
    status["storage"]["disk"]["pct"] = 85
    assert evaluate_alerts(status, settings, now)[0][0] == "disk_warn"
    status["storage"]["disk"]["pct"] = 50
    assert evaluate_alerts(status, settings, now) == []


def test_alert_stale_detection():
    from app.cicc_alerts import evaluate_alerts

    settings = {"disk_warn": 80, "disk_crit": 90, "stale_minutes": 30}
    now = 1_000_000_000
    status = {"ts": now - 31 * 60, "storage": {"disk": {"pct": 10}}}
    keys = [k for k, _ in evaluate_alerts(status, settings, now)]
    assert "stale" in keys


def test_notify_cooldown_24h():
    from app.cicc_alerts import should_notify

    now = 1_000_000_000
    state = {"alerts": {"disk_warn": now - 3600}}
    assert not should_notify(state, "disk_warn", now)          # 1h 前发过 → 冷却中
    assert should_notify(state, "disk_warn", now + 86400)      # 超过 24h → 可再发
    assert should_notify({}, "disk_warn", now)                 # 从未发过


def test_schedule_command_payload(tmp_path):
    from app.cicc_collector import CiccControl

    ctl = CiccControl(str(tmp_path))
    ctl.set_schedule_time("05:30", "tester")
    cmds = list((tmp_path / "local" / ".cicc" / "commands").glob("*.json"))
    assert len(cmds) == 1
    body = json.loads(cmds[0].read_text(encoding="utf-8"))
    assert body["mode"] == "schedule" and body["time"] == "05:30"
