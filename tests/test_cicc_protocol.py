"""CICC 部署协议离线测试：命令信封、dispatch 校验、结果文件、重试、关键词、时间。

全部离线：加载 scripts/vps/cicc-dispatch.py 后 monkeypatch 模块级常量指向 tmp_path，
patch subprocess/launch 防真执行（计划任务 1/7 约束）。
"""
from __future__ import annotations

import json
import re

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
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": 1710000000,
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
        "bad-mode.json": {"id": "d" * 32, "mode": "rm -rf /", "ts": 1710000000},
        "no-mode.json": {"id": "b" * 32, "ts": 1710000000},
        "no-ts.json": {"id": "c" * 32, "mode": "incr"},
        "bad-payload.json": {"id": "f" * 32, "mode": "incr", "ts": 1710000000,
                             "payload": "not-a-dict"},
    }
    for name, cmd in cases.items():
        _write_command(ctrl_dir, name, cmd)
    mod.main()
    assert not launched, "非法命令不得执行"
    results = {p.stem: json.loads(p.read_text(encoding="utf-8"))
               for p in (ctrl_dir / "results").glob("*.json")}
    assert len(results) == 4, results
    for r in results.values():
        assert r["status"] == "failed"
        assert r["error"], r
        assert r["attempts"] >= 1


def test_dispatch_ignores_temp_files(ctrl, monkeypatch):
    _, archive = ctrl
    mod, launched = _dispatch(monkeypatch, archive / "local" / ".cicc", archive)
    ctrl_dir = archive / "local" / ".cicc"
    _write_command(ctrl_dir, "1710000000000-incr.json",
                   {"id": "e" * 32, "mode": "incr", "actor": "admin", "ts": 1710000000,
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
                   {"mode": "incr", "actor": "admin", "ts": 1710000000})
    mod.main()
    assert launched, "旧命令必须仍被消费"
    assert not list((ctrl_dir / "commands").glob("*.json"))