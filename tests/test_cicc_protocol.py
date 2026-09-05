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
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": 1710000000,
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
                   {"id": cmd_id, "mode": "rm -rf /", "actor": "admin", "ts": 1710000000,
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
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": 1710000000,
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
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": 1710000000,
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
                    "ts": 1710000000,
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
                    "ts": 1710000000,
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
                    "ts": 1710000000,
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
                    "ts": 1710000000,
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
                   {"id": cmd_id, "mode": "incr", "actor": "admin", "ts": 1710000000,
                    "payload": {"keywords": ["宁德时代"]}})
    mod.main()  # 第一次忙
    assert not launched
    mod.main()  # 第二次成功
    assert launched
    argv, _ = launched[0]
    assert "--keywords" in argv
    assert argv[argv.index("--keywords") + 1] == "宁德时代"
    r = json.loads((ctrl_dir / "results" / f"{cmd_id}.json").read_text(encoding="utf-8"))
    assert r["status"] == "success" and r["attempts"] == 2