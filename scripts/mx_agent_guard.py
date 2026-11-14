#!/usr/bin/env python3
r"""MX agent guard: keep scripts/mx_agent.py alive (Windows schtasks, every minute).

Idempotent: matches python.exe processes whose command line contains
"mx_agent.py"; spawns a detached instance only when none is running.
Silent on the healthy path; spawns/append-only log at data/agent_guard.log.

Task registration (one-time):
    schtasks /Create /TN "MXAgentGuard" /SC MINUTE /MO 1 ^
        /TR "wscript.exe \"C:\Users\hemin\Documents\vpush\scripts\mx_agent_guard.vbs\"" /F
Boot-startup is covered by the 1-minute cadence itself (first tick <= 60s
after logon). The .vbs wrapper keeps the console hidden (pythonw).
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = REPO / ".venv" / "Scripts" / "pythonw.exe"
PYTHON_GUI = REPO / ".venv" / "Scripts" / "python.exe"
ENTRY = REPO / "scripts" / "mx_agent.py"
LOG = REPO / "data" / "agent_guard.log"
STDOUT_LOG = REPO / "data" / "agent_stdout.log"


def agent_running() -> bool:
    """True when a python.exe process runs mx_agent.py.

    Query failure counts as "running": double-spawn would fight over the
    CDP port (9223); missing one guard tick is harmless.
    """
    ps = (
        "if ((Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*' -and "
        "$_.CommandLine -like '*mx_agent.py*' } | "
        "Measure-Object).Count -gt 0) { 'YES' } else { 'NO' }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return "YES" in out.stdout
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
    log_h = open(STDOUT_LOG, "ab")
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
    time.sleep(5)  # record-only confirmation; next tick retries if still absent
    if not agent_running():
        _log("WARN: not detected 5s after spawn (retry on next tick)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
