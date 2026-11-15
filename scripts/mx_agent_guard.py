#!/usr/bin/env python3
r"""MX agent guard: keep scripts/mx_agent.py alive (Windows schtasks, every minute).

Idempotent: reads the single-instance lock (data/agent/agent.lock) — lock held
by a live process = agent alive, spawn only when the lock is absent/dead-holder.
Silent on the healthy path; spawns/append-only log at data/agent_guard.log.

2026-11-15 事故修复：旧版靠 WMI 进程枚举判存活，spawn 后 5s 复查太早，
每分钟误判「不在」再拉一个——8 组实例并存共抢 CDP 9223。改用锁文件这一
硬前提（agent 启动即抢锁，抢不到自退），枚举彻底退场。

Task registration (one-time):
    schtasks /Create /TN "MXAgentGuard" /SC MINUTE /MO 1 ^
        /TR "wscript.exe \"C:\Users\hemin\Documents\vpush\scripts\mx_agent_guard.vbs\"" /F
Boot-startup is covered by the 1-minute cadence itself (first tick <= 60s
after logon). The .vbs wrapper keeps the console hidden (pythonw).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = REPO / ".venv" / "Scripts" / "pythonw.exe"
PYTHON_GUI = REPO / ".venv" / "Scripts" / "python.exe"
ENTRY = REPO / "scripts" / "mx_agent.py"
LOG = REPO / "data" / "agent_guard.log"
STDOUT_LOG = REPO / "data" / "agent_stdout.log"
AGENT_LOCK = REPO / "data" / "agent" / "agent.lock"


def agent_running() -> bool:
    """锁被活进程持有 = agent 在运行。

    无锁文件 = 不在（快路径，零 subprocess）；锁文件在 → 起子进程跑
    agent.single_instance.lock_is_taken（与 agent 抢锁同一套生死判定，
    永不双开）；子进程调用异常按「在运行」处理——双开抢 9223 比漏拉
    一次 tick 有害得多（漏拉由每分钟 cadence 自兜底）。
    """
    import subprocess as sp

    if not AGENT_LOCK.exists():
        return False
    try:
        code = sp.run(
            [str(PYTHON_GUI), "-c",
             (f"import sys; sys.path.insert(0, r'{REPO}'); "
              f"from agent.single_instance import lock_is_taken; "
              f"sys.exit(0 if lock_is_taken(r'{AGENT_LOCK}') else 1)")],
            capture_output=True, timeout=30, check=False,
            creationflags=sp.CREATE_NO_WINDOW,
        )
        return code.returncode == 0
    except Exception:
        return True


def spawn() -> None:
    """Start agent detached: cwd=repo root, output appended to agent_stdout.log."""
    exe = PYTHON if PYTHON.exists() else PYTHON_GUI
    if not (exe.exists() and ENTRY.exists()):
        _log(f"FATAL: missing exe/entry: {exe} / {ENTRY}")
        return
    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: outlives the guard process
    DETACHED = 0x00000008 | 0x00000200
    log_h = open(STDOUT_LOG, "ab")  # noqa: SIM115 - 句柄归 DETACHED 子进程持有
    subprocess.Popen(
        [str(exe), str(ENTRY)],
        cwd=str(REPO),
        stdout=log_h,
        stderr=subprocess.STDOUT,
        creationflags=DETACHED,
    )
    _log("spawned")


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def main() -> int:
    if agent_running():
        return 0
    spawn()
    return 0


if __name__ == "__main__":
    sys.exit(main())
