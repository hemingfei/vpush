#!/usr/bin/env python3
"""把中金采集状态写进 .cicc/status.json（vpush 经 NFS 读取），每 60 秒由 timer 触发。"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import time

CTRL = "/srv/vpush-ima/local/.cicc"
CICC_DIR = "/root/cicc"
LIB_ROOT = "/srv/vpush-ima/local"
SCHEDULE_FILE = "/usr/local/lib/vpush-ima/cicc-schedule.json"
HEALTH_FILE = "/srv/vpush-ima/local/.vpush-storage-health.json"
BACKUP_ENV = "/etc/vpush/ima-storage.env"


def collectors_running() -> int:
    r = subprocess.run(["pgrep", "-fc", "^python3 -u .*cicc_repor[t]_collector"],
                       capture_output=True, text=True)
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


def storage_section() -> dict:
    """磁盘/WG/NFS/归档统计与采集计划（60s 轻量；贵的统计由 cicc-stats.py 每小时供）。"""
    st = os.statvfs("/srv")
    total = st.f_blocks * st.f_frsize
    free = st.f_bfree * st.f_frsize
    used = total - free
    disk = {"total_gb": round(total / 2**30, 1), "used_gb": round(used / 2**30, 1),
            "free_gb": round(free / 2**30, 1),
            "pct": round(used / total * 100, 1) if total else 0.0}
    wg = {"ok": False, "rtt_ms": None}
    r = subprocess.run(["ping", "-c", "1", "-W", "2", "10.80.0.1"],
                       capture_output=True, text=True, check=False)
    m = re.search(r"time=([\d.]+) ms", r.stdout or "")
    if r.returncode == 0:
        wg["ok"] = True
        wg["rtt_ms"] = float(m.group(1)) if m else None
    lib_root = "/srv/vpush-ima/local"
    nfs = {"mounted": os.path.isdir(lib_root),
           "marker_ok": os.path.exists("/srv/vpush-ima/.vpush-ima-root")}
    return {"disk": disk, "wg": wg, "nfs": nfs,
            "archive": read_json(os.path.join(CTRL, "stats.json"), {}),
            "schedule": read_json(SCHEDULE_FILE, {"time": "03:00"}),
            "last_incr_summary": read_json(os.path.join(CTRL, "last_incr_summary.json"), {}) or {}}


def load_env_file(path: str) -> dict[str, str]:
    """解析 KEY=VALUE 行（去引号），等价 shell source 的变量来源；缺失/异常返回空。"""
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def parse_snapshots(text: str) -> list[dict]:
    """restic snapshots --json → [{id 前 8 位, time, size}]。"""
    try:
        snaps = json.loads(text or "[]")
    except ValueError:
        return []
    if not isinstance(snaps, list):
        return []
    return [{"id": str(s.get("short_id") or s.get("id") or "")[:8],
             "time": str(s.get("time") or ""),
             "size": int((s.get("summary") or {}).get("total_bytes_processed") or 0)}
            for s in snaps if isinstance(s, dict)]


def backup_section() -> dict:
    """备份节：诚实呈现——env 没配 RESTIC_REPOSITORY 就直说未生效；配了再试 snapshots。"""
    health = read_json(HEALTH_FILE, {}) or {}
    section = {"configured": False,
               "restic_last_success": int(health.get("restic_last_success") or 0),
               "restic_last_check_ok": health.get("restic_last_check_ok") is True}
    env = load_env_file(BACKUP_ENV)
    if not env.get("RESTIC_REPOSITORY"):
        section["reason"] = "env 缺 RESTIC_REPOSITORY，需要配置备份目标"
        return section
    section["configured"] = True
    run_env = dict(os.environ)
    run_env.update(env)
    try:
        r = subprocess.run(["restic", "snapshots", "--latest", "5", "--json"],
                           capture_output=True, text=True, timeout=120,
                           check=False, env=run_env)
    except (OSError, subprocess.SubprocessError) as exc:
        section["reason"] = str(exc)[:200]
        return section
    if r.returncode != 0:
        section["reason"] = ((r.stderr or r.stdout or "restic snapshots 失败").strip())[-200:]
        return section
    section["snapshots"] = parse_snapshots(r.stdout)
    return section


def count_pdfs() -> int:
    total = 0
    for dp, _, fs in os.walk(LIB_ROOT):
        if dp.startswith(os.path.join(LIB_ROOT, ".cicc")):
            continue
        total += sum(1 for name in fs if name.lower().endswith(".pdf"))
    return total


def main() -> None:
    running = subprocess.run(["pgrep", "-fc", "^python3 -u .*pdf_backfill_compres[s]"],
                             capture_output=True, text=True)
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
        "paused": read_json(os.path.join(CTRL, "paused.json")),
        "cicc_settings": read_json(os.path.join(CTRL, "cicc_settings.json"), {}) or {},
        "logs": log_tails(),
        "commands": (read_json(os.path.join(CTRL, "commands.json"), []) or [])[-20:],
        "storage": storage_section(),
        "backup": backup_section(),
    }
    os.makedirs(CTRL, exist_ok=True)
    write_json(os.path.join(CTRL, "status.json"), status)


if __name__ == "__main__":
    main()
