#!/usr/bin/env python3
"""MX 行为器（Agent）本地验证脚本（票 #17 验收：可复现本地验证，循 spike Phase B 先例）。

验证边界（票裁定）：真实浏览器链路不入 CI、本脚本也不真连 MX——只到
导入/语法/纯逻辑层：全部 agent 模块可导入、窗口/接力/节奏/注册表/日志
纯逻辑在本地真实数据目录上跑一轮离线冒烟。

用法（仓库根目录）：
    .venv/Scripts/python.exe scripts/mx_agent_validate.py [--data-dir <dir>]

真浏览器/真 MX 验收走 48h 挂机（scripts/mx_agent.py 常驻运行）。
"""
from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.services.mx_window import CN_TZ, build_daily_plan  # noqa: E402


def check_modules() -> list[str]:
    """全部 agent 模块导入（语法/依赖面冒烟）。"""
    names = ["agent", "agent.accounts", "agent.config", "agent.cadence",
             "agent.daily_plan", "agent.executor", "agent.lifecycle",
             "agent.login", "agent.relay", "agent.window_runner",
             "agent.browser", "agent.runner"]
    for name in names:
        importlib.import_module(name)
    return names


def check_plan_store(data_dir: Path) -> None:
    """当日计划持久化冒烟：同日两读同一份、跨日重建。"""
    from agent.daily_plan import get_today_plan

    now = datetime.now(CN_TZ)
    plan = get_today_plan(store_dir=data_dir / "plans", now=now,
                          builder=build_daily_plan)
    again = get_today_plan(store_dir=data_dir / "plans", now=now,
                           builder=build_daily_plan)
    assert again == plan, "同日两读必须同一份计划（重启不漂移）"
    tomorrow = get_today_plan(store_dir=data_dir / "plans",
                              now=now + timedelta(days=1),
                              builder=build_daily_plan)
    assert tomorrow.day != plan.day, "跨日必须重建计划"
    print(f"✓ 当日计划持久化：{len(plan.windows)} 段窗口，同日稳定/跨日重建")


def check_relay(data_dir: Path) -> None:
    """接力状态机冒烟：主失败→备用顶上→主恢复→备用下线。"""
    from agent.accounts import parse_accounts
    from agent.relay import RelayStateMachine

    accounts = parse_accounts("primary-demo,backup-demo")
    events: list[tuple[str, str]] = []
    machine = RelayStateMachine(
        accounts, on_switch=lambda kind, acc: events.append((kind, acc.user)))
    machine.report_login("primary-demo", ok=False)
    assert machine.active.user == "backup-demo"
    machine.report_login("backup-demo", ok=True)
    machine.report_login("primary-demo", ok=True)
    assert machine.active.user == "primary-demo"
    assert [k for k, _ in events] == ["switch_to_backup", "primary_recovered"]
    print("✓ 接力状态机：主失败备用顶上、主恢复备用下线、全程单活跃账号")


def check_cadence() -> None:
    """切房节奏冒烟：5-10 分钟区间 + 排除上一个。"""
    import random

    from agent.cadence import pick_room
    from app.services.mx_activity import ACTIVITY_INTERVAL_RANGE

    lo, hi = ACTIVITY_INTERVAL_RANGE
    assert (lo, hi) == (300.0, 600.0), "间隔区间必须是 5-10 分钟（搬运红线）"
    rooms = ["房A", "房B", "房C"]
    for _ in range(50):
        assert pick_room(rooms, last_room="房A", rng=random.Random()) != "房A"
    print(f"✓ 切房节奏：间隔 {lo:.0f}-{hi:.0f}s（5-10 分钟），排除上一个房间")


def check_registry(data_dir: Path) -> None:
    """账号注册表冒烟：profile 目录、token 持久化、无密码。"""
    from agent.accounts import AccountRegistry

    reg = AccountRegistry(data_dir / "accounts.json")
    p1 = reg.profile_dir("primary-demo")
    p2 = reg.profile_dir("backup-demo")
    assert p1 != p2 and p1.exists()
    reg.set_token("primary-demo", "tok-demo", updated_at=1.0)
    again = AccountRegistry(data_dir / "accounts.json")
    assert again.token("primary-demo") == "tok-demo"
    assert "password" not in (data_dir / "accounts.json").read_text(encoding="utf-8")
    print("✓ 账号注册表：每账号独立 profile、token 持久化、密码绝不入文件")


def check_lifecycle(data_dir: Path) -> None:
    """生命周期日志冒烟：写入→按 kind 查询。"""
    from agent.lifecycle import LifecycleLog, query_events

    log = LifecycleLog(data_dir / "lifecycle.jsonl")
    log.record("agent_start", account=None, detail="验证脚本")
    log.record("relay_switch", account="primary-demo", detail="switch_to_backup")
    switches = query_events(data_dir / "lifecycle.jsonl", kind="relay_switch")
    assert len(switches) == 1
    print("✓ 生命周期日志：JSONL 写入/按 kind 查询")


def check_executor_args() -> None:
    """执行器参数冒烟：干净启动、零自动化痕迹。"""
    from agent.executor import chrome_launch_args

    args = chrome_launch_args(exe="chrome", user_data_dir=Path("p/x"),
                              cdp_port=9333, origin="https://mx.example.com")
    joined = " ".join(args)
    assert "--enable-automation" not in joined and "--headless" not in joined
    assert "--remote-debugging-port=9333" in joined
    print("✓ CDPExecutor 启动参数：专用 profile + CDP 端口，零自动化痕迹")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=None,
                        help="验证数据目录（默认临时目录，跑完即弃）")
    args = parser.parse_args()

    names = check_modules()
    print(f"✓ 模块导入：{len(names)} 个（agent 全模块 + runner/browser）")

    if args.data_dir:
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
    else:
        data_dir = Path(tempfile.mkdtemp(prefix="mx_agent_validate_"))

    check_plan_store(data_dir)
    check_relay(data_dir)
    check_cadence()
    check_registry(data_dir)
    check_lifecycle(data_dir)
    check_executor_args()
    print(f"\n全部通过（数据目录：{data_dir}）。真实浏览器/真 MX 链路由 48h 挂机验收覆盖。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
