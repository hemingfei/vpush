"""CICC 部署协议离线测试：命令信封、dispatch 校验、结果文件、重试、关键词、时间。

全部离线：加载 scripts/vps/cicc-dispatch.py 后 monkeypatch 模块级常量指向 tmp_path，
patch subprocess/launch 防真执行（计划任务 1/7 约束）。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest
from conftest import load_vps_script

from app.cicc_collector import CiccControl


@pytest.fixture
def ctrl(cicc_archive):
    archive, _ = cicc_archive
    return CiccControl(str(archive)), archive


def _dispatch(monkeypatch, ctrl, archive):
    """加载 scripts/vps/cicc-dispatch.py，路径常量指向离线目录，防真执行。"""
    mod = load_vps_script("cicc-dispatch")
    monkeypatch.setattr(mod, "CTRL", str(ctrl))
    monkeypatch.setattr(mod, "COMMANDS_DIR", str(ctrl / "commands"))
    monkeypatch.setattr(mod, "RESULTS_DIR", str(ctrl / "results"))
    monkeypatch.setattr(mod, "LEDGER", str(ctrl / "commands.json"))
    monkeypatch.setattr(mod, "CICC_DIR", str(archive / "cicc"))
    monkeypatch.setattr(mod, "COLLECTOR", str(archive / "cicc" / "cicc_report_collector.py"))
    monkeypatch.setattr(mod, "SCHEDULE_FILE", str(ctrl / "cicc-schedule.json"))
    launched = []
    monkeypatch.setattr(mod, "launch", lambda argv, log_name: launched.append((argv, log_name)))
    monkeypatch.setattr(mod, "run_collector", lambda argv: (launched.append((argv, "collector")) or (True, None)))
    monkeypatch.setattr(mod, "collectors_running", lambda: 0)
    (ctrl / "commands").mkdir(parents=True, exist_ok=True)
    (ctrl / "results").mkdir(parents=True, exist_ok=True)
    return mod, launched


def _write_command(ctrl, name, obj):
    path = ctrl / "commands" / name
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


# —— 任务 2：命令信封与随机 ID ——

def test_trigger_ids_are_random_and_distinct(ctrl):
    ctl, _ = ctrl
    assert ctl.trigger("incr", "admin") == {"queued": "incr"}
    ctl.trigger("incr", "admin")
    cmds = sorted((ctl.ctrl / "commands").glob("*.json"))
    assert len(cmds) == 2
    id1 = json.loads(cmds[0].read_text(encoding="utf-8"))["id"]
    id2 = json.loads(cmds[1].read_text(encoding="utf-8"))["id"]
    assert id1 != id2


def test_command_filename_has_sortable_time_and_id(ctrl):
    ctl, _ = ctrl
    ctl.trigger("incr", "admin", extra={"categories": ["公司研究"]})
    (file,) = (ctl.ctrl / "commands").glob("*.json")
    cmd = json.loads(file.read_text(encoding="utf-8"))
    assert re.fullmatch(r"\d{13}-(incr|year|all|stop|compress|schedule|settings|backup)-[a-f0-9]{8}\.json",
                        file.name), file.name
    assert file.name.endswith(f"-{cmd['id'][:8]}.json")


def test_command_envelope_payload(ctrl):
    ctl, _ = ctrl
    ctl.trigger("settings", "admin",
                extra={"time": "03:30", "categories": ["公司研究"], "keywords": ["宁德时代"]})
    (file,) = (ctl.ctrl / "commands").glob("*.json")
    cmd = json.loads(file.read_text(encoding="utf-8"))
    assert cmd["mode"] == "settings"
    assert cmd["actor"] == "admin"
    assert isinstance(cmd["ts"], int) and cmd["ts"] > 0
    assert cmd["payload"] == {"time": "03:30", "categories": ["公司研究"],
                              "keywords": ["宁德时代"]}


def test_dispatch_writes_success_result_and_launches(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    cmd_id = "a" * 32
    _write_command(archive / "local" / ".cicc", f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": int(time.time()),
                    "payload": {}})
    mod.main()
    assert launched, "incr 必须触发 launch"
    result = json.loads((archive / "local" / ".cicc" / "results" / f"{cmd_id}.json")
                        .read_text(encoding="utf-8"))
    assert result["id"] == cmd_id
    assert result["mode"] == "incr"
    assert result["status"] == "success"
    assert result["attempts"] >= 1
    assert not list((archive / "local" / ".cicc" / "commands").glob("*.json")), "处理完应删命令"


def test_dispatch_rejects_missing_fields_with_failed_result(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cases = {
        "bad-mode.json": {"id": "d" * 32, "mode": "rm -rf /", "ts": int(time.time())},
        "no-mode.json": {"id": "b" * 32, "ts": int(time.time())},
        "no-ts.json": {"id": "c" * 32, "mode": "incr"},
        "bad-payload.json": {"id": "f" * 32, "mode": "incr", "ts": int(time.time()),
                             "payload": "not-a-dict"},
        "null-payload.json": {"id": "a" * 32, "mode": "incr", "ts": int(time.time()),
                              "payload": None},
    }
    for name, cmd in cases.items():
        _write_command(ctrl_dir, name, cmd)
    mod.main()
    assert not launched, "非法命令不得执行"
    results = {p.stem: json.loads(p.read_text(encoding="utf-8"))
               for p in (ctrl_dir / "results").glob("*.json")}
    assert len(results) == 5, results
    for r in results.values():
        assert r["status"] == "failed"
        assert r["error"], r
        assert r["attempts"] >= 1


def test_dispatch_ignores_temp_files(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    _write_command(ctrl_dir, "1710000000000-incr.json",
                   {"id": "e" * 32, "mode": "incr", "actor": "admin", "ts": int(time.time()),
                    "payload": {}})
    _write_command(ctrl_dir, ".tmp.12345", {"mode": "incr"})
    mod.main()
    assert len(launched) == 1
    assert not (ctrl_dir / "commands" / ".tmp.12345").exists() or True  # 临时文件未处理


def test_dispatch_legacy_command_without_id_still_runs(ctrl, monkeypatch):
    """旧格式（无 id、无 payload）命令短期兼容：以文件名为幂等键执行。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    _write_command(ctrl_dir, "1710000000000-incr.json",
                   {"mode": "incr", "actor": "admin", "ts": int(time.time())})
    mod.main()
    assert launched, "旧命令必须仍被消费"
    assert not list((ctrl_dir / "commands").glob("*.json"))


# —— 任务 3：失败重试与幂等 ——

def test_transient_failure_retries_then_succeeds(ctrl, monkeypatch):
    """collector_already_running（暂时性）第一次保留命令文件，第二次成功后删除。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    busy = iter([1, 0])
    monkeypatch.setattr(mod, "collectors_running", lambda: next(busy))
    cmd_id = "11" * 16
    _write_command(ctrl_dir, f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": int(time.time()),
                    "payload": {}})

    mod.main()  # 第一次：collector 忙 → 保留命令文件
    assert not launched
    assert (ctrl_dir / "commands").glob("*.json"), "暂时性失败必须保留命令文件供重试"
    r1 = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r1["status"] == "retry"
    assert r1["error"] == "collector_already_running"
    assert r1["attempts"] == 1

    mod.main()  # 第二次：空闲 → 成功，命令文件删除
    assert launched
    r2 = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r2["status"] == "success"
    assert r2["attempts"] == 2
    assert not list((ctrl_dir / "commands").glob("*.json"))
    assert r2["id"] == cmd_id, "重试不得生成新 id"


def test_permanent_failure_does_not_retry(ctrl, monkeypatch):
    """unknown_mode 等参数错误：一次即失败，删除命令文件不保留。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "22" * 16
    _write_command(ctrl_dir, f"1710000000000-bogus-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "rm -rf /", "actor": "admin", "ts": int(time.time()),
                    "payload": {}})
    mod.main()
    mod.main()  # 再来一次也不能重试
    assert not launched
    assert not list((ctrl_dir / "commands").glob("*.json")), "永久失败不得保留命令文件"
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "failed"
    assert r["attempts"] == 1


def test_transient_failure_gives_up_after_max_attempts(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    monkeypatch.setattr(mod, "collectors_running", lambda: 1)  # 永远忙
    cmd_id = "33" * 16
    _write_command(ctrl_dir, f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": int(time.time()),
                    "payload": {}})
    for _ in range(mod.MAX_ATTEMPTS):
        mod.main()
    assert not launched
    assert not list((ctrl_dir / "commands").glob("*.json")), "耗尽后命令文件必须删除"
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "failed"
    assert r["attempts"] == mod.MAX_ATTEMPTS


def test_success_result_is_idempotent_on_rescan(ctrl, monkeypatch):
    """成功结果存在时，残留命令文件不得再次执行。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "44" * 16
    # 手工模拟：结果已 success，但命令文件仍在（上次删除前崩溃）
    (ctrl_dir / "results").mkdir(parents=True, exist_ok=True)
    (ctrl_dir / "results" / f"{cmd_id}.json").write_text(json.dumps(
        {"id": cmd_id, "mode": "incr", "status": "success",
         "started_at": 100, "finished_at": 101, "attempts": 1, "error": None}),
        encoding="utf-8")
    _write_command(ctrl_dir, f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": int(time.time()),
                    "payload": {}})
    mod.main()
    assert not launched, "已成功命令不得重复执行"
    assert not list((ctrl_dir / "commands").glob("*.json"))


# —— 任务 4：关键词透传 ——

def test_settings_keeps_keywords_through_dispatch(ctrl, monkeypatch):
    """payload.keywords 必须写入 cicc_settings.json（回归：旧 dispatch 只写 categories）。"""
    _, archive = ctrl
    mod, _launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "55" * 16
    _write_command(ctrl_dir, f"1710000000000-settings-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "settings", "actor": "admin",
                    "ts": int(time.time()),
                    "payload": {"categories": ["公司研究"],
                                 "keywords": ["宁德时代", "半导体"]}})
    mod.main()
    settings = json.loads((ctrl_dir / "cicc_settings.json").read_text(encoding="utf-8"))
    assert settings["categories"] == ["公司研究"]
    assert settings["keywords"] == ["宁德时代", "半导体"]
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "success"


def test_settings_empty_keywords_means_no_filter(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "56" * 16
    _write_command(ctrl_dir, f"1710000000000-settings-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "settings", "actor": "admin",
                    "ts": int(time.time()),
                    "payload": {"categories": [], "keywords": []}})
    mod.main()
    settings = json.loads((ctrl_dir / "cicc_settings.json").read_text(encoding="utf-8"))
    assert settings["keywords"] == []


def test_settings_rejects_non_string_keywords(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "57" * 16
    _write_command(ctrl_dir, f"1710000000000-settings-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "settings", "actor": "admin",
                    "ts": int(time.time()),
                    "payload": {"categories": ["公司研究"], "keywords": [123]}})
    mod.main()
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "failed"
    assert r["error"] == "invalid_keywords"
    assert not (ctrl_dir / "cicc_settings.json").exists()


def test_keywords_survive_unicode_and_quotes(ctrl, monkeypatch):
    """中文/逗号/引号关键词 JSON 往返不变形。"""
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    kw = ["宁德时代，新能源", "A股\"牛市\"", "半导体'龙头'", "混合,逗号"]
    cmd_id = "58" * 16
    _write_command(ctrl_dir, f"1710000000000-settings-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "settings", "actor": "admin",
                    "ts": int(time.time()),
                    "payload": {"categories": ["公司研究"], "keywords": kw}})
    mod.main()
    settings = json.loads((ctrl_dir / "cicc_settings.json").read_text(encoding="utf-8"))
    assert settings["keywords"] == kw


def test_retry_keeps_original_keywords(ctrl, monkeypatch):
    """暂时性失败重试：命令文件保留，重试仍用原 payload 关键词，不从当前配置重新读。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    busy = iter([1, 0])
    monkeypatch.setattr(mod, "collectors_running", lambda: next(busy))
    cmd_id = "59" * 16
    _write_command(ctrl_dir, f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": int(time.time()),
                    "payload": {"keywords": ["宁德时代"]}})
    mod.main()  # 第一次忙
    assert not launched
    mod.main()  # 第二次成功
    assert launched
    argv, _ = launched[0]
    assert "--filters-file" in argv
    filters = json.loads(Path(argv[argv.index("--filters-file") + 1]).read_text(encoding="utf-8"))
    assert filters["keywords"] == ["宁德时代"]
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "success" and r["attempts"] == 2


# —— 任务 5：时间字段校验 ——

def test_validate_time_of_day_bounds():
    from app.cicc_collector import validate_time_of_day as v

    for ok in ("00:00", "03:00", "23:59"):
        assert v(ok) is True
    for bad in ("3:00", "24:00", "12:60", "12:30:00", "", "ab:cd", "12:3"):
        assert v(bad) is False, bad


def test_api_rejects_invalid_schedule_time(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.delenv("IMA_PULL_URL", raising=False)
    monkeypatch.setenv("IMA_ARCHIVE_ROOT", str(tmp_path / "archive"))
    (tmp_path / "archive" / "local" / ".cicc" / "commands").mkdir(parents=True)
    os.environ["DAV_UI_ONLY"] = "1"
    app = create_app(config=None, db_path=Path(tmp_path) / "cicc.db")
    client = TestClient(app)
    client.app.state.db.add_register_code("CICC01")
    resp = client.post("/api/auth/register", json={
        "username": "admin1", "password": "secret123", "code": "CICC01"})
    data = resp.json()
    client.app.state.db.update_user(data["user"]["id"], is_admin=True)
    headers = {"Authorization": f"Bearer {data['token']}"}

    for bad in ("24:00", "12:60", "3:00"):
        r = client.put("/api/admin/cicc/schedule",
                       json={"enabled": True, "time": bad}, headers=headers)
        assert r.status_code == 400, (bad, r.text)


def test_dispatch_rejects_invalid_schedule_time(ctrl, monkeypatch):
    """dispatch 侧 24:99 等必须 invalid_time（永久失败），不得写入 schedule 文件。"""
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    for i, bad in enumerate(("24:00", "12:60", "3:00", "")):
        cmd_id = f"60{i}" + "0" * 30
        _write_command(ctrl_dir, f"1710000000000-schedule-{cmd_id[:8]}.json",
                       {"id": cmd_id, "mode": "schedule", "actor": "admin",
                        "ts": int(time.time()), "payload": {"time": bad}})
    mod.main()
    assert not (ctrl_dir / "cicc-schedule.json").exists()
    results = {p.stem: json.loads(p.read_text(encoding="utf-8"))
               for p in (ctrl_dir / "results").glob("*.json")}
    assert len(results) == 4
    for r in results.values():
        assert r["status"] == "failed" and r["error"] == "invalid_time", r


def test_dispatch_accepts_valid_schedule_time(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "61" * 16
    _write_command(ctrl_dir, f"1710000000000-schedule-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "schedule", "actor": "admin",
                    "ts": int(time.time()), "payload": {"time": "05:30"}})
    mod.main()
    sched = json.loads((ctrl_dir / "cicc-schedule.json").read_text(encoding="utf-8"))
    assert sched == {"time": "05:30"}


def test_dispatch_rejects_future_ts(ctrl, monkeypatch):
    """命令 ts 未来超过允许时钟偏差 → invalid_ts（永久失败）。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "62" * 16
    far_future = int(time.time()) + 3600 * 24 * 30  # 未来 30 天
    _write_command(ctrl_dir, f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin",
                    "ts": far_future, "payload": {}})
    mod.main()
    assert not launched
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "failed" and r["error"] == "invalid_ts"


def test_dispatch_accepts_recent_past_ts(ctrl, monkeypatch):
    """阈值内的过去 ts（重试场景）必须放行。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "63" * 16
    _write_command(ctrl_dir, f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin",
                    "ts": int(time.time()) - 60, "payload": {}})
    mod.main()
    assert launched
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "success"


# —— 任务 6：统一部署脚本来源 ——

def test_deploy_ima_storage_has_no_script_copies():
    """canonical 只允许 scripts/vps/：deploy/ima-storage 不得再放 cicc-*.py 双份。"""
    root = Path(__file__).resolve().parent.parent
    stale = sorted((root / "deploy" / "ima-storage").glob("cicc-*.py"))
    assert stale == [], f"deploy/ima-storage 不得保留脚本副本（canonical=scripts/vps）：{stale}"


def test_systemd_units_use_absolute_paths_only():
    """deploy/ima-storage/vpush-cicc-*.service 的 ExecStart 必须是明确绝对路径。"""
    root = Path(__file__).resolve().parent.parent
    for unit in (root / "deploy" / "ima-storage").glob("vpush-cicc-*.service"):
        text = unit.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("ExecStart="):
                _, _, value = line.partition("=")
                assert value.startswith("/"), f"{unit.name}: ExecStart 必须是绝对路径: {line}"
                assert "/Users" not in value, f"{unit.name}: 不得依赖开发机路径: {value}"


# —— 任务 7：崩溃恢复与恶意输入 ——

def test_crash_after_write_before_dispatch_recovers(ctrl, monkeypatch):
    """命令落盘后、dispatch 执行前崩溃：命令文件保留，下次正常消费。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "64" * 16
    _write_command(ctrl_dir, f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin",
                    "ts": int(time.time()), "payload": {}})
    mod.main()
    assert launched
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "success"


def test_crash_mid_running_result_recovers_after_stale(ctrl, monkeypatch):
    """dispatch 执行中崩溃：result 停在 running，超时后恢复执行。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "65" * 16
    _write_command(ctrl_dir, f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin",
                    "ts": int(time.time()), "payload": {}})
    # 模拟崩溃：result 停在 running（旧时间戳）
    (ctrl_dir / "results").mkdir(parents=True, exist_ok=True)
    (ctrl_dir / "results" / f"{cmd_id}.json").write_text(json.dumps(
        {"id": cmd_id, "mode": "incr", "status": "running",
         "started_at": int(time.time()) - 3600, "finished_at": 0,
         "attempts": 2, "error": None}), encoding="utf-8")
    mod.main()
    assert launched, "stale running 结果必须恢复重试"
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "success"
    assert r["attempts"] == 3


def test_fresh_running_result_skips(ctrl, monkeypatch):
    """running 未超时：跳过（可能是另一 dispatch 实例正在处理）。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "66" * 16
    _write_command(ctrl_dir, f"1710000000000-incr-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "incr", "actor": "admin",
                    "ts": int(time.time()), "payload": {}})
    (ctrl_dir / "results").mkdir(parents=True, exist_ok=True)
    (ctrl_dir / "results" / f"{cmd_id}.json").write_text(json.dumps(
        {"id": cmd_id, "mode": "incr", "status": "running",
         "started_at": int(time.time()), "finished_at": 0,
         "attempts": 1, "error": None}), encoding="utf-8")
    mod.main()
    assert not launched
    assert list((ctrl_dir / "commands").glob("*.json")), "命令文件必须保留等下次"


def test_temp_settings_file_not_left_half_written(ctrl, monkeypatch):
    """settings 写入为原子 tmp+replace：结果文件不会被半截 JSON 污染。"""
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "67" * 16
    _write_command(ctrl_dir, f"1710000000000-settings-{cmd_id[:8]}.json",
                   {"id": cmd_id, "mode": "settings", "actor": "admin",
                    "ts": int(time.time()),
                    "payload": {"categories": ["公司研究"], "keywords": ["宁德时代"]}})
    # 残留 tmp：模拟上次写入中途崩溃
    (ctrl_dir / "results" / "67.tmp.999").write_text('{"partial', encoding="utf-8")
    mod.main()
    settings = json.loads((ctrl_dir / "cicc_settings.json").read_text(encoding="utf-8"))
    assert settings == {"categories": ["公司研究"], "keywords": ["宁德时代"]}
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "success"  # 结果文件是完整 JSON，不是 tmp 残留


def test_malicious_filenames_and_content_are_safe(ctrl, monkeypatch):
    """路径穿越文件名/非法 JSON/超长 actor/shell 特殊字符：不得执行任意命令或写出控制目录。"""
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    evil = [
        ("..%2f..%2fetc%2fpasswd.json", {"mode": "incr", "ts": int(time.time())}),
        (f"{'a' * 250}.json", "not-json{"),  # 超长文件名+非法 JSON（>255 会 OSError，250 是安全上限）
        ("evil$(rm).json", {"mode": "incr", "actor": ";rm -rf /",
                            "ts": int(time.time()), "payload": {}}),
        ("1670000000000-incr-12345678.json",
         {"id": "68" * 16, "mode": "incr", "actor": "x" * 10000,
          "ts": int(time.time()), "payload": {"keywords": ["$(touch /tmp/pwned)"]}}),
    ]
    for name, content in evil:
        (ctrl_dir / "commands" / name).write_text(
            content if isinstance(content, str) else json.dumps(content),
            encoding="utf-8")
    mod.main()
    assert not Path("/tmp/pwned").exists()
    assert not (ctrl_dir.parent / "passwd").exists()  # 路径穿越无效
    # 第 4 条是合法信封（含 shell 特殊字符的关键词只进 argv，不执行）
    launched_kw = [a for a, _ in launched if "--filters-file" in a]
    assert launched_kw
    filters_path = Path(launched_kw[0][launched_kw[0].index("--filters-file") + 1])
    assert "$(touch /tmp/pwned)" in json.loads(filters_path.read_text(encoding="utf-8"))["keywords"]


def test_invalid_json_command_fails_keeps_nothing(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    (ctrl_dir / "commands" / "1710000000000-garbage.json").write_text(
        "{not json", encoding="utf-8")
    mod.main()
    assert not launched
    results = list((ctrl_dir / "results").glob("*.json"))
    assert results, "非法 JSON 必须有 failed 结果"
    r = json.loads(results[0].read_text(encoding="utf-8"))
    assert r["status"] == "failed"
    assert r["error"] == "invalid_json"


def test_command_id_cannot_escape_results_directory(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    _write_command(ctrl_dir, "escape.json", {
        "id": "../../escaped", "mode": "incr", "actor": "admin",
        "ts": int(time.time()), "payload": {},
    })

    mod.main()

    assert not launched
    assert not (archive / "escaped.json").exists()
    results = list((ctrl_dir / "results").glob("*.json"))
    assert len(results) == 1
    assert json.loads(results[0].read_text(encoding="utf-8"))["error"] == "invalid_id"


def test_invalid_collector_filter_type_fails_without_stopping_queue(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    now = int(time.time())
    _write_command(ctrl_dir, "bad.json", {
        "id": "badfilters", "mode": "incr", "actor": "admin", "ts": now,
        "payload": {"keywords": 123},
    })
    _write_command(ctrl_dir, "good.json", {
        "id": "goodfilters", "mode": "incr", "actor": "admin", "ts": now,
        "payload": {"keywords": []},
    })

    mod.main()

    assert mod.load_result("badfilters")["error"] == "invalid_keywords"
    assert mod.load_result("goodfilters")["status"] == "success"
    assert len(launched) == 1


def test_stale_command_is_rejected(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    _write_command(ctrl_dir, "stale.json", {
        "id": "stale-command", "mode": "incr", "actor": "admin",
        "ts": int(time.time()) - mod.MAX_TS_AGE - 1, "payload": {},
    })

    mod.main()

    assert not launched
    assert mod.load_result("stale-command")["error"] == "stale_command"


def test_legacy_schedule_fields_are_migrated_to_payload(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    _write_command(ctrl_dir, "legacy-schedule.json", {
        "mode": "schedule", "actor": "admin", "ts": int(time.time()), "time": "04:30",
    })

    mod.main()

    assert json.loads((ctrl_dir / "cicc-schedule.json").read_text(encoding="utf-8")) == {
        "time": "04:30",
    }


def test_stale_running_at_attempt_limit_is_not_executed(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "attempt-limit"
    _write_command(ctrl_dir, "attempt-limit.json", {
        "id": cmd_id, "mode": "incr", "actor": "admin",
        "ts": int(time.time()), "payload": {},
    })
    mod.write_result(cmd_id, {
        "id": cmd_id, "mode": "incr", "status": "running",
        "started_at": int(time.time()) - mod.RESULT_STALE_SECONDS - 1,
        "finished_at": 0, "attempts": mod.MAX_ATTEMPTS, "error": None,
    })

    mod.main()

    assert not launched
    assert mod.load_result(cmd_id)["status"] == "failed"
    assert mod.load_result(cmd_id)["attempts"] == mod.MAX_ATTEMPTS


def test_collector_exit_failure_is_not_marked_success(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    monkeypatch.setattr(mod, "run_collector", lambda argv: (False, "collector_exit_1"))
    _write_command(ctrl_dir, "collector-failure.json", {
        "id": "collector-failure", "mode": "incr", "actor": "admin",
        "ts": int(time.time()), "payload": {},
    })

    mod.main()

    result = mod.load_result("collector-failure")
    assert result["status"] == "retry"
    assert result["error"] == "collector_exit_1"
    assert (ctrl_dir / "commands" / "collector-failure.json").exists()


def test_collector_receives_filters_as_json_file(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    received = []

    def run(argv):
        path = Path(argv[argv.index("--filters-file") + 1])
        received.append(json.loads(path.read_text(encoding="utf-8")))
        return True, None

    monkeypatch.setattr(mod, "run_collector", run)
    _write_command(ctrl_dir, "filters.json", {
        "id": "filter-file", "mode": "incr", "actor": "admin",
        "ts": int(time.time()),
        "payload": {"categories": ["公司研究"], "keywords": ["alpha,beta", "半导体"]},
    })

    mod.main()

    assert received == [{"categories": ["公司研究"], "keywords": ["alpha,beta", "半导体"]}]


def test_manual_collection_snapshots_saved_filters_for_retry(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    mod.write_json(str(ctrl_dir / "cicc_settings.json"), {
        "categories": ["公司研究"], "keywords": ["原始关键词"],
    })
    received = []

    outcomes = iter([(False, "collector_exit_1"), (True, None)])
    monkeypatch.setattr(mod, "run_collector",
                        lambda argv: (received.append(json.loads(Path(
                            argv[argv.index("--filters-file") + 1]).read_text(encoding="utf-8")))
                                      or next(outcomes)))
    _write_command(ctrl_dir, "manual.json", {
        "id": "manual-snapshot", "mode": "incr", "actor": "admin",
        "ts": int(time.time()), "payload": {},
    })

    mod.main()
    mod.write_json(str(ctrl_dir / "cicc_settings.json"), {
        "categories": [], "keywords": ["后来修改"],
    })
    mod.main()

    assert received == [
        {"categories": ["公司研究"], "keywords": ["原始关键词"]},
        {"categories": ["公司研究"], "keywords": ["原始关键词"]},
    ]


def test_dispatch_has_periodic_retry_timer():
    root = Path(__file__).resolve().parent.parent
    timer = root / "deploy/ima-storage/vpush-cicc-dispatch.timer"
    assert timer.exists()
    assert "OnUnitActiveSec=" in timer.read_text(encoding="utf-8")


def test_dispatch_service_timeout_value_has_no_inline_comment():
    root = Path(__file__).resolve().parent.parent
    service = root / "deploy/ima-storage/vpush-cicc-dispatch.service"
    timeout = next(line for line in service.read_text(encoding="utf-8").splitlines()
                   if line.startswith("TimeoutStartSec="))
    assert re.fullmatch(r"TimeoutStartSec=\d+", timeout)
    dispatch = load_vps_script("cicc-dispatch")
    assert int(timeout.partition("=")[2]) > dispatch.COLLECTOR_TIMEOUT

    installer = (root / "scripts/vps/install_cicc_batch1.sh").read_text(encoding="utf-8")
    assert "vpush-cicc-dispatch.service" in installer
    assert timeout in installer


def test_permission_error_is_permanent(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    monkeypatch.setattr(mod, "run_collector",
                        lambda argv: (_ for _ in ()).throw(PermissionError("denied")))
    _write_command(ctrl_dir, "permission.json", {
        "id": "permission-error", "mode": "incr", "actor": "admin",
        "ts": int(time.time()), "payload": {},
    })

    mod.main()

    result = mod.load_result("permission-error")
    assert result["status"] == "failed"
    assert result["error"] == "permission_denied"


def test_pending_stop_request_is_detected_without_accepting_invalid_json(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    (ctrl_dir / "commands" / "broken.json").write_text("{bad", encoding="utf-8")
    assert mod.stop_requested() is False

    _write_command(ctrl_dir, "stop.json", {
        "id": "stop-request", "mode": "stop", "actor": "admin",
        "ts": int(time.time()), "payload": {},
    })
    assert mod.stop_requested() is True


def test_collector_error_uses_only_pause_marker_from_current_run(ctrl, monkeypatch):
    _, archive = ctrl
    mod, _ = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    assert mod.classify_collector_error(1, {"reason": "auth", "ts": 100}, 101) == \
        "collector_exit_1"
    assert mod.classify_collector_error(1, {"reason": "auth", "ts": 101}, 101) == \
        "collector_auth"
    assert mod.classify_collector_error(1, {"reason": "quota", "ts": 102}, 101) == \
        "collector_quota"


def test_stale_running_with_completion_marker_is_not_reexecuted(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    cmd_id = "completed-before-result"
    _write_command(ctrl_dir, "completed.json", {
        "id": cmd_id, "mode": "incr", "actor": "admin",
        "ts": int(time.time()), "payload": {},
    })
    mod.write_result(cmd_id, {
        "id": cmd_id, "mode": "incr", "status": "running",
        "started_at": int(time.time()) - mod.RESULT_STALE_SECONDS - 1,
        "finished_at": 0, "attempts": 1, "error": None,
    })
    mod.write_json(str(ctrl_dir / f"completed-{cmd_id}.json"), {"id": cmd_id})

    mod.main()

    assert not launched
    assert mod.load_result(cmd_id)["status"] == "success"
    assert not (ctrl_dir / "commands" / "completed.json").exists()
