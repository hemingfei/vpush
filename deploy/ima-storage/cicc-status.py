#!/usr/bin/env python3
"""把中金采集状态写进 .cicc/status.json（vpush 经 NFS 读取），每 60 秒由 timer 触发。"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import time

CTRL = "/srv/vpush-ima/local/.cicc"
CICC_DIR = "/root/cicc"
LIB_ROOT = "/srv/vpush-ima/local"


def collectors_running() -> int:
    r = subprocess.run(["pgrep", "-fc", "^python3 -u .*cicc_repor[t]_collector"],
                       capture_output=True, text=True, check=False)
    try:
        return int(r.stdout.strip() or 0)
    except ValueError:
        return 0


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: str, obj, *, mode: int = 0o640) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.chmod(tmp, mode)
    try:
        os.chown(tmp, 99, 100)
    except PermissionError:
        pass
    os.replace(tmp, path)


def log_tails() -> dict[str, str]:
    tails = {}
    for path in sorted(glob.glob(os.path.join(CICC_DIR, "*.log"))):
        try:
            with open(path, errors="replace") as f:
                tail = f.read()[-4096:].splitlines()
            tails[os.path.basename(path)[:-4]] = tail[-1][:200] if tail else ""
        except OSError:
            continue
    return tails


def count_pdfs() -> int:
    total = 0
    for dp, _, fs in os.walk(LIB_ROOT):
        if dp.startswith(os.path.join(LIB_ROOT, ".cicc")):
            continue
        total += sum(1 for name in fs if name.lower().endswith(".pdf"))
    return total


def main() -> None:
    running = subprocess.run(["pgrep", "-fc", "^python3 -u .*pdf_backfill_compres[s]"],
                             capture_output=True, text=True, check=False)
    try:
        compress = int(running.stdout.strip() or 0)
    except ValueError:
        compress = 0
    status = {
        "ts": int(time.time()),
        "running": collectors_running(),
        "compress_running": compress,
        "files_total": count_pdfs(),
        "schedule_enabled": os.path.exists(os.path.join(CTRL, "incremental.enabled")),
        "last_incremental": read_json(os.path.join(CTRL, "incremental.last")),
        "logs": log_tails(),
        "commands": (read_json(os.path.join(CTRL, "commands.json"), []) or [])[-20:],
    }
    os.makedirs(CTRL, exist_ok=True)
    write_json(os.path.join(CTRL, "status.json"), status)


if __name__ == "__main__":
    main()
