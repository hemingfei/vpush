#!/usr/bin/env python3
"""消费 .cicc/commands/ 下的命令文件（vpush 经 NFS 投递），启动对应采集动作。

由 vpush-cicc-dispatch.path（PathModified=commands 目录）触发；处理完删除命令文件，
结果追加进 commands.json 账本。命令文件须为原子写入（vpush 侧 tmp+rename）。
mode ∈ incr|year|all|stop|compress：
  incr/year/all  启动 cicc_report_collector.py（已有采集进程在跑则拒绝，避免重复翻页）
  stop           结束所有采集进程
  compress       启动 gs 压缩回刷（低优先级，可与采集并存，回刷自身跳过 120s 内新文件）
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time

CTRL = "/srv/vpush-ima/local/.cicc"
COMMANDS_DIR = os.path.join(CTRL, "commands")
LEDGER = os.path.join(CTRL, "commands.json")
CICC_DIR = "/root/cicc"
COLLECTOR = os.path.join(CICC_DIR, "cicc_report_collector.py")
COMPRESSOR = os.path.join(CICC_DIR, "pdf_backfill_compress.py")
PY = "/usr/bin/python3"

MODE_ARGS = {
    "incr": ["--days", "3"],
    "year": ["--since", "2026-01-01"],
    "all": ["--all"],
}


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


def launch(argv: list[str], log_name: str) -> None:
    os.makedirs(CICC_DIR, exist_ok=True)
    fh = open(os.path.join(CICC_DIR, log_name), "ab")  # noqa: SIM115 — fd 归子进程，不可提前关闭
    subprocess.Popen(argv, stdout=fh, stderr=fh, cwd=CICC_DIR,
                     start_new_session=True, close_fds=True)


def main() -> None:
    os.makedirs(COMMANDS_DIR, exist_ok=True)
    handled = []
    for name in sorted(os.listdir(COMMANDS_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(COMMANDS_DIR, name)
        cmd = read_json(path) or {}
        mode = cmd.get("mode")
        entry = {"ts": int(time.time()), "mode": mode,
                 "actor": str(cmd.get("actor", ""))[:40], "ok": False}
        try:
            if mode == "stop":
                subprocess.run(["pkill", "-f", "cicc_repor[t]_collector"], check=False)
                entry["ok"] = True
            elif mode == "compress":
                launch(["nice", "-n", "19", "ionice", "-c2", "-n7",
                        PY, "-u", COMPRESSOR, "--root",
                        "/srv/vpush-ima/local/cicc-research", "--strip-watermark"],
                       "ui_compress.log")
                entry["ok"] = True
            elif mode in MODE_ARGS:
                if collectors_running() > 0:
                    entry["error"] = "collector_already_running"
                else:
                    launch([PY, "-u", COLLECTOR, *MODE_ARGS[mode]], f"ui_{mode}.log")
                    entry["ok"] = True
            else:
                entry["error"] = "unknown_mode"
        except OSError as exc:
            entry["error"] = str(exc)[:200]
        handled.append(entry)
        try:
            os.remove(path)
        except OSError:
            pass

    if handled:
        lock = open(os.path.join(CTRL, ".ledger.lock"), "w")  # noqa: SIM115 — 锁文件生命周期即本块
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            ledger = (read_json(LEDGER, []) or []) + handled
            write_json(LEDGER, ledger[-20:])
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()


if __name__ == "__main__":
    main()
