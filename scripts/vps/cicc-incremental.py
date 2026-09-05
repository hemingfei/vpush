#!/usr/bin/env python3
"""中金每日增量（时间可配）：timer 每小时 :05 触发本脚本，门控决定是否真正执行。

门控（北京时间）：
  1) incremental.enabled 不存在 → 总开关关
  2) 已有采集进程在跑 → skip（下一 tick 重试）
  3) 未到当日计划时间（cicc-schedule.json 的 time，缺省 03:00）→ skip
  4) 今日已成功跑过（last_incr_summary.date == 今天）→ skip
  5) paused.json reason=auth 且 48h 内 → skip（等管理员换 Cookie）；
     reason=quota 不跳——每日一次的重试正是配额重置后的恢复手段
通过后同步执行 collector --days 3（品类定向见 cicc_settings.json），
解析「完成：下载 N，已存在跳过 M，失败 K」写入 .cicc/last_incr_summary.json 供通知与展示。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

CTRL = "/srv/vpush-ima/local/.cicc"
CICC_DIR = "/root/cicc"
COLLECTOR = os.path.join(CICC_DIR, "cicc_report_collector.py")
SCHEDULE_FILE = "/usr/local/lib/vpush-ima/cicc-schedule.json"
PY = "/usr/bin/python3"
BJ = timezone(timedelta(hours=8))
DONE_RE = re.compile(r"完成：下载 (\d+)，已存在跳过 (\d+)，失败 (\d+)")
_TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
PAUSED_AUTH_WINDOW = 48 * 3600  # Cookie 失效后自动重试多久放弃（等管理员介入）


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


def read_schedule() -> str:
    data = read_json(SCHEDULE_FILE, {}) or {}
    t = str(data.get("time") or "03:00")
    return t if _TIME_RE.fullmatch(t) else "03:00"


def should_run(now: datetime, schedule_hhmm: str,
               last_summary: dict | None) -> tuple[bool, str]:
    """门控纯函数：未到计划时间/今日已跑 → False。"""
    try:
        hh, mm = (int(x) for x in schedule_hhmm.split(":", 1))
        hh, mm = hh % 24, mm % 60
    except ValueError:
        hh, mm = 3, 0
    sched = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < sched:
        return False, "before_schedule_time"
    if str((last_summary or {}).get("date") or "") == now.strftime("%Y-%m-%d"):
        return False, "already_ran_today"
    return True, "due"


def paused_skip(paused: dict | None, now_ts: int) -> tuple[bool, str]:
    """熔断门控纯函数：Cookie 失效（auth）48h 内跳过等管理员换 Cookie；
    配额满（quota）不跳——每日重试就是月初重置后的恢复手段。"""
    if not paused:
        return False, ""
    if paused.get("reason") != "auth":
        return False, ""
    ts = int(paused.get("ts") or 0)
    if ts and 0 <= now_ts - ts < PAUSED_AUTH_WINDOW:
        return True, "paused_auth"
    return False, ""


def write_json(path: str, obj) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.chmod(tmp, 0o640)
    try:
        os.chown(tmp, 99, 100)
    except PermissionError:
        pass
    os.replace(tmp, path)


def main() -> None:
    if not os.path.exists(os.path.join(CTRL, "incremental.enabled")):
        return
    now = datetime.now(BJ)
    schedule = read_schedule()
    last = read_json(os.path.join(CTRL, "last_incr_summary.json"), {}) or {}
    run, reason = should_run(now, schedule, last)
    if not run:
        write_json(os.path.join(CTRL, "incremental.last"),
                   {"ts": int(time.time()), "note": reason})
        return
    if collectors_running() > 0:
        write_json(os.path.join(CTRL, "incremental.last"),
                   {"ts": int(time.time()), "note": "skipped_collector_running"})
        return
    skip, note = paused_skip(read_json(os.path.join(CTRL, "paused.json")), int(now.timestamp()))
    if skip:
        write_json(os.path.join(CTRL, "incremental.last"),
                   {"ts": int(time.time()), "note": note})
        return
    # 品类定向：cicc_settings.json 非空则只采勾选品类（空数组/缺文件=全部）
    settings = read_json(os.path.join(CTRL, "cicc_settings.json"), {}) or {}
    cats = [str(c) for c in (settings.get("categories") or []) if str(c).strip()]
    keywords = [str(k) for k in (settings.get("keywords") or []) if str(k).strip()]
    argv = [PY, "-u", COLLECTOR, "--days", "3"]
    if cats:
        argv += ["--categories", ",".join(cats)]
    if keywords:
        argv += ["--keywords", ",".join(keywords)]
    os.makedirs(CICC_DIR, exist_ok=True)
    r = subprocess.run(argv,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800, check=False)
    with open(os.path.join(CICC_DIR, "auto_incr.log"), "ab") as log:
        log.write((r.stdout or "").encode("utf-8", "replace"))
    tail = (r.stdout or "")[-2000:]
    m = DONE_RE.search(tail)
    added, skipped, failed = (int(m.group(i)) for i in (1, 2, 3)) if m else (0, 0, 1)
    summary = {"ts": int(time.time()), "date": now.strftime("%Y-%m-%d"),
               "added": added, "skipped": skipped, "failed": failed,
               "ok": r.returncode == 0}
    write_json(os.path.join(CTRL, "last_incr_summary.json"), summary)
    write_json(os.path.join(CTRL, "incremental.last"),
               {"ts": int(time.time()), "note": f"done added={added} failed={failed}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # 任何异常不得让 timer 反复重启拖垮机器
        print(f"incremental failed: {exc}", file=sys.stderr)
        sys.exit(0)
