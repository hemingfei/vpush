#!/usr/bin/env python3
"""每日增量（03:00 北京时间，vpush-cicc-incremental.timer 触发）。

incremental.enabled 标志存在才跑；已有采集进程在跑则跳过（等下一轮，断点续传兜底）。
"""
from __future__ import annotations

import json
import os
import subprocess
import time

CTRL = "/srv/vpush-ima/local/.cicc"
CICC_DIR = "/root/cicc"
COLLECTOR = os.path.join(CICC_DIR, "cicc_report_collector.py")
PY = "/usr/bin/python3"


def collectors_running() -> int:
    r = subprocess.run(["pgrep", "-fc", "^python3 -u .*cicc_repor[t]_collector"],
                       capture_output=True, text=True, check=False)
    try:
        return int(r.stdout.strip() or 0)
    except ValueError:
        return 0


def write_last(path: str, note: str) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"ts": int(time.time()), "note": note}, f)
    os.chmod(tmp, 0o640)
    try:
        os.chown(tmp, 99, 100)
    except PermissionError:
        pass
    os.replace(tmp, path)


def main() -> None:
    if not os.path.exists(os.path.join(CTRL, "incremental.enabled")):
        return
    if collectors_running() > 0:
        write_last(os.path.join(CTRL, "incremental.last"), "skipped_collector_running")
        return
    os.makedirs(CICC_DIR, exist_ok=True)
    log = open(os.path.join(CICC_DIR, "auto_incr.log"), "ab")  # noqa: SIM115 — fd 归子进程
    subprocess.Popen([PY, "-u", COLLECTOR, "--days", "3"],
                     stdout=log, stderr=log, cwd=CICC_DIR,
                     start_new_session=True, close_fds=True)
    write_last(os.path.join(CTRL, "incremental.last"), "launched")


if __name__ == "__main__":
    main()
