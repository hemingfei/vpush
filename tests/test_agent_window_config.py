"""窗口配置三态测试：always_on / 自定义窗口 / 默认计划（2026-11-15 用户需求）。

需求：软件里不能把窗口时间写死（要可配），主动打开软件也要能监听
（不受窗口限制）。落点 = MX_AGENT_ALWAYS_ON + MX_AGENT_WINDOWS 两个 env，
默认语义零改动（云端 scheduler 共用 mx_window.py 不动）。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from agent.config import load_agent_config, _parse_custom_windows
from agent.runner import AgentRunner, _combine_hm
from agent.lifecycle import LifecycleLog

CN_TZ = timezone(timedelta(hours=8))


# ---- config 解析 ----


def test_always_on_flag_parsed(monkeypatch, tmp_path):
    monkeypatch.setenv("MX_AGENT_ACCOUNTS", "u1")
    monkeypatch.setenv("MX_AGENT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("MX_AGENT_ALWAYS_ON", "1")
    config = load_agent_config()
    assert config.always_on is True
    assert config.windows is None


def test_custom_windows_parsed_and_validated(monkeypatch, tmp_path):
    monkeypatch.setenv("MX_AGENT_ACCOUNTS", "u1")
    monkeypatch.setenv("MX_AGENT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("MX_AGENT_WINDOWS", '[["07:00","11:30"],["13:00","17:00"]]')
    config = load_agent_config()
    assert config.windows == [("07:00", "11:30"), ("13:00", "17:00")]
    assert config.always_on is False


@pytest.mark.parametrize("bad", [
    'not-json', '["07:00"]', '[["7:00","11:30"]]', '[["25:00","26:00"]]',
    '[["07:00"]]', '[]',
])
def test_bad_windows_fall_back_to_none(monkeypatch, tmp_path, bad):
    monkeypatch.setenv("MX_AGENT_ACCOUNTS", "u1")
    monkeypatch.setenv("MX_AGENT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("MX_AGENT_WINDOWS", bad)
    assert load_agent_config().windows is None
    # 直接解析器同口径
    assert _parse_custom_windows(bad) is None


# ---- runner 窗口三态 ----


def _runner_with(config, tmp_path):
    return AgentRunner(
        config,
        log=LifecycleLog(tmp_path / "lc.jsonl"),
        registry=config.registry(),
    )


def test_always_on_full_day_window_armed_any_time(monkeypatch, tmp_path):
    """always_on：全天单窗；任何时刻（含深夜/周末重启）都武装开窗。"""
    monkeypatch.setenv("MX_AGENT_ACCOUNTS", "u1")
    monkeypatch.setenv("MX_AGENT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("MX_AGENT_ALWAYS_ON", "1")
    config = load_agent_config()
    runner = _runner_with(config, tmp_path)
    # 周日深夜 23:59 —— 默认语义下必不武装，always_on 必开
    now = datetime(2026, 11, 15, 23, 59, tzinfo=CN_TZ)  # 周日
    windows = runner._plan_windows(now)
    assert len(windows) == 1
    start, stop = windows[0]
    assert (start.hour, start.minute) == (0, 0)
    assert (stop - start).total_seconds() == 24 * 3600
    # runner 决策层：重启后首个 tick 即开窗（restart_login 重武装全天窗）
    assert runner._restart_login is True
    runner.runner.tick(now=now, windows=windows)
    assert runner.runner.window_open is True


def test_custom_windows_resolved_to_datetimes(monkeypatch, tmp_path):
    monkeypatch.setenv("MX_AGENT_ACCOUNTS", "u1")
    monkeypatch.setenv("MX_AGENT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("MX_AGENT_WINDOWS", '[["07:00","11:30"]]')
    config = load_agent_config()
    runner = _runner_with(config, tmp_path)
    now = datetime(2026, 11, 15, 8, 0, tzinfo=CN_TZ)
    windows = runner._plan_windows(now)
    assert windows == [(datetime(2026, 11, 15, 7, 0, tzinfo=CN_TZ),
                        datetime(2026, 11, 15, 11, 30, tzinfo=CN_TZ))]
    # 窗内 tick → 开窗决策（计划文件完全未读：data_dir 下无 plans/）
    runner.runner.tick(now=now, windows=windows)
    assert runner.runner.window_open is True
    assert not (tmp_path / "d" / "plans").exists()


def test_default_plan_unchanged_without_env(monkeypatch, tmp_path):
    """未设两个 env：走默认计划文件语义（三段随机窗），行为零改动。"""
    monkeypatch.setenv("MX_AGENT_ACCOUNTS", "u1")
    monkeypatch.setenv("MX_AGENT_DATA_DIR", str(tmp_path / "d"))
    config = load_agent_config()
    assert config.always_on is False and config.windows is None
    runner = _runner_with(config, tmp_path)
    now = datetime.now(CN_TZ)
    windows = runner._plan_windows(now)
    assert len(windows) == 3
    assert (tmp_path / "d" / "plans").exists()  # 计划文件照常持久化


def test_combine_hm_helpers():
    day = datetime(2026, 11, 15).date()
    assert _combine_hm(day, "07:30", CN_TZ) == datetime(2026, 11, 15, 7, 30, tzinfo=CN_TZ)
    assert _combine_hm(day, "xx", CN_TZ) is None
