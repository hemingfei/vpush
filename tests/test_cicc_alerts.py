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
    (tmp_path / "schedule.json").write_text('{"time":"00:00"}')

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


def test_collector_keywords_filter():
    """标题关键词白名单：命中任一保留，空白名单全保留。"""
    spec = importlib.util.spec_from_file_location(
        "cicc_collector_kw", ROOT / "scripts/cicc_report_collector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    items = [{"title": "宁德时代：Q3 业绩点评"}, {"title": "贵州茅台：渠道跟踪"}]
    assert len(mod.filter_by_keywords(items, [])) == 2
    assert len(mod.filter_by_keywords(items, ["宁德时代"])) == 1
    assert len(mod.filter_by_keywords(items, ["宁德时代", "白酒"])) == 1  # 「白酒」不在标题中
    assert mod.filter_by_keywords(items, ["不存在的词"]) == []


def _collector():
    spec = importlib.util.spec_from_file_location(
        "cicc_collector_sidecar", ROOT / "scripts/cicc_report_collector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_collector_sidecar_row_uses_beijing_date_and_caps_tags():
    mod = _collector()
    row = mod.sidecar_row({
        "id": 99,
        "title": "宁德时代深度",
        "summary": "x" * 3000,
        "reportType": "深度报告",
        "documentLabels": ["新能源", "电力设备"],
        "portalCategoryIds": ["7", 8],
        "publishTime": "2026-08-29T17:43:03Z",
        "analysts": [{"name": "张三"}, "李四"],
    }, {7: "公司研究", "8": "汽车"}, "公司研究")
    assert row["id"] == "99"
    assert row["publish"] == "2026-08-30"
    assert row["day"] == "0830"
    assert len(row["summary"]) == 2000
    assert row["tags"] == ["深度报告", "公司研究", "新能源", "电力设备", "汽车"]
    assert row["authors"] == "张三 李四"


def test_collector_merge_sidecar_upserts_and_keeps_existing(tmp_path):
    mod = _collector()
    path = tmp_path / ".vpush-local-meta.jsonl"
    path.write_text(
        json.dumps({"id": "1", "title": "旧", "summary": "a", "tags": [], "day": "0801", "publish": "2026-08-01", "authors": ""}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    n = mod.merge_sidecar(path, {
        "1": {"id": "1", "title": "新", "summary": "b", "tags": ["宏观"], "day": "0802", "publish": "2026-08-02", "authors": "甲"},
        "2": {"id": "2", "title": "增量", "summary": "c", "tags": ["宁德时代"], "day": "0830", "publish": "2026-08-30", "authors": ""},
    })
    assert n == 2
    rows = mod.load_sidecar(path)
    assert rows["1"]["title"] == "新"
    assert rows["2"]["summary"] == "c"
    assert "宁德时代" in rows["2"]["tags"]
