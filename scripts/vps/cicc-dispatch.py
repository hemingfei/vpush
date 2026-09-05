#!/usr/bin/env python3
"""消费 .cicc/commands/ 下的命令文件（vpush 经 NFS 投递），启动对应采集动作。

由 vpush-cicc-dispatch.path（PathModified=commands 目录）触发；处理完删除命令文件，
结果追加进 commands.json 账本。命令文件须为原子写入（vpush 侧 tmp+rename）。
mode ∈ incr|year|all|stop|compress|schedule|settings|backup|consistency|dedup：
  incr/year/all  启动 cicc_report_collector.py（已有采集进程在跑则拒绝，避免重复翻页）
  stop           结束所有采集进程
  compress       启动 gs 压缩回刷（低优先级，可与采集并存，回刷自身跳过 120s 内新文件）
  schedule       采集时间 HH:mm → cicc-schedule.json
  settings       品类定向 {"categories":[…]}（空数组=全部）→ .cicc/cicc_settings.json
  backup         运行 restic-backup.sh（后台，结果看 .vpush-storage-health.json 与日志）
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import time

CTRL = "/srv/vpush-ima/local/.cicc"
COMMANDS_DIR = os.path.join(CTRL, "commands")
RESULTS_DIR = os.path.join(CTRL, "results")
LEDGER = os.path.join(CTRL, "commands.json")
CICC_DIR = "/root/cicc"
COLLECTOR = os.path.join(CICC_DIR, "cicc_report_collector.py")
COMPRESSOR = os.path.join(CICC_DIR, "pdf_backfill_compress.py")
SCHEDULE_FILE = "/usr/local/lib/vpush-ima/cicc-schedule.json"
BACKUP_SCRIPT = "/usr/local/lib/vpush-ima/restic-backup.sh"
CONSISTENCY_SCRIPT = "/usr/local/lib/vpush-ima/cicc-consistency.py"
DEDUP_SCRIPT = "/root/cicc/pdf_dedup_hardlink.py"
PY = "/usr/bin/python3"

MODE_ARGS = {
    "incr": ["--days", "3"],
    "year": ["--since", "2026-01-01"],
    "all": ["--all"],
}

ALL_MODES = ("stop", "compress", "schedule", "settings",
             "consistency", "dedup", "backup", *MODE_ARGS)

MAX_ATTEMPTS = 3
# ponytail: 暂时性失败（collector 忙/OSError/脚本缺失已有分支）保留命令文件重试；
# 参数类错误（unknown_mode/invalid_*）永久失败不重试。
PERMANENT_ERRORS = {"unknown_mode", "invalid_time", "invalid_categories",
                    "invalid_keywords", "invalid_ts", "invalid_payload",
                    "invalid_json", "backup_script_missing",
                    "consistency_script_missing", "dedup_script_missing"}
RESULT_STALE_SECONDS = 600  # running 结果超时视为上次运行崩溃，恢复重试
MAX_TS_FUTURE = 300  # 命令 ts 允许的最大未来偏差（秒），防伪造/损坏时间戳
_TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")


def valid_time_of_day(value) -> bool:
    """HH:mm 严格校验：00:00..23:59（旧实现会放过 24:99）。"""
    return isinstance(value, str) and bool(_TIME_RE.fullmatch(value))


def validate_command(cmd: dict) -> str | None:
    """返回错误原因（None=合法）。命令信封：{id, mode, actor, ts, payload}。

    id 缺失不拒——旧格式（无 id）短期兼容，main() 以文件名为幂等键。
    """
    if not isinstance(cmd, dict):
        return "invalid_json"
    mode = cmd.get("mode")
    if mode not in ALL_MODES:
        return "unknown_mode"
    ts = cmd.get("ts")
    if not isinstance(ts, int) or isinstance(ts, bool) or ts <= 0:
        return "invalid_ts"
    if ts > int(time.time()) + MAX_TS_FUTURE:
        return "invalid_ts"  # 未来时间超允许偏差
    payload = cmd.get("payload")
    if payload is not None and not isinstance(payload, dict):
        return "invalid_payload"
    return None


def write_result(cmd_id: str, entry: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    write_json(os.path.join(RESULTS_DIR, f"{cmd_id}.json"), entry)


def load_result(cmd_id: str) -> dict | None:
    return read_json(os.path.join(RESULTS_DIR, f"{cmd_id}.json"))


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
        if not name.endswith(".json") or name.startswith("."):
            continue
        path = os.path.join(COMMANDS_DIR, name)
        cmd = read_json(path) or {}
        # 新命令以 envelope.id 为幂等键；旧格式（无 id）以文件名为键短期兼容
        cmd_id = str(cmd.get("id") or name)
        prev = load_result(cmd_id) or {}
        if prev.get("status") == "success":
            # 幂等：已成功（可能上次成功与删除之间崩溃），只清命令不重跑
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        if prev.get("status") == "running" and \
                int(time.time()) - int(prev.get("started_at") or 0) < RESULT_STALE_SECONDS:
            continue  # running 且未超时：上次运行未完成（可能真在跑），跳过本次
        started = int(time.time())
        attempts = int(prev.get("attempts") or 0) + 1
        entry = {"id": cmd_id, "mode": cmd.get("mode"), "status": "running",
                 "started_at": started, "finished_at": 0, "attempts": attempts,
                 "error": None}
        write_result(cmd_id, entry)  # 先落 running：崩溃后 stale 恢复可重试
        error = validate_command(cmd)
        payload = cmd.get("payload") if isinstance(cmd.get("payload"), dict) else {}
        try:
            if error is not None:
                entry["error"] = error
            else:
                mode = cmd["mode"]
                entry["error"] = None
                if mode == "stop":
                    subprocess.run(["pkill", "-f", "cicc_repor[t]_collector"], check=False)
                    entry["ok"] = True
                elif mode == "compress":
                    launch(["nice", "-n", "19", "ionice", "-c2", "-n7",
                            PY, "-u", COMPRESSOR, "--root",
                            "/srv/vpush-ima/local/cicc-research", "--strip-watermark"],
                           "ui_compress.log")
                    entry["ok"] = True
                elif mode == "schedule":
                    sched = payload.get("time")
                    if valid_time_of_day(sched):
                        write_json(SCHEDULE_FILE, {"time": sched})
                        entry["ok"] = True
                    else:
                        entry["error"] = "invalid_time"
                elif mode == "settings":
                    cats = payload.get("categories")
                    kws = payload.get("keywords")
                    valid_cats = isinstance(cats, list) and \
                        all(isinstance(c, str) for c in cats)
                    valid_kws = isinstance(kws, list) and \
                        all(isinstance(k, str) for k in kws)
                    if valid_cats and valid_kws:
                        write_json(os.path.join(CTRL, "cicc_settings.json"),
                                   {"categories": [c for c in cats if c.strip()],
                                    "keywords": [k for k in kws if k.strip()]})
                        entry["ok"] = True
                    elif not valid_cats:
                        entry["error"] = "invalid_categories"
                    else:
                        entry["error"] = "invalid_keywords"
                elif mode == "consistency":
                    if not os.path.exists(CONSISTENCY_SCRIPT):
                        entry["error"] = "consistency_script_missing"
                    else:
                        r = subprocess.run([PY, CONSISTENCY_SCRIPT], capture_output=True,
                                           text=True, timeout=600, check=False)
                        entry["ok"] = r.returncode == 0
                        if r.returncode != 0:
                            entry["error"] = (r.stderr or "")[:200]
                elif mode == "dedup":
                    if not os.path.exists(DEDUP_SCRIPT):
                        entry["error"] = "dedup_script_missing"
                    else:
                        subprocess.Popen(["nice", "-n", "19", PY, "-u", DEDUP_SCRIPT, "--apply"],
                                         stdout=open(os.path.join(CICC_DIR, "ui_dedup.log"), "ab"),  # noqa: SIM115 — fd 归子进程
                                         stderr=subprocess.STDOUT, cwd=CICC_DIR,
                                         start_new_session=True, close_fds=True)
                        entry["ok"] = True
                elif mode == "backup":
                    if not os.path.exists(BACKUP_SCRIPT):
                        entry["error"] = "backup_script_missing"
                    else:
                        launch([BACKUP_SCRIPT], "ui_backup.log")
                        entry["ok"] = True
                elif mode in MODE_ARGS:
                    if collectors_running() > 0:
                        entry["error"] = "collector_already_running"
                    else:
                        argv = [PY, "-u", COLLECTOR, *MODE_ARGS[mode]]
                        cats = [c for c in payload.get("categories") or []
                                if isinstance(c, str) and c.strip()]
                        kws = [k for k in payload.get("keywords") or []
                               if isinstance(k, str) and k.strip()]
                        if cats:
                            argv += ["--categories", ",".join(cats)]
                        if kws:
                            argv += ["--keywords", ",".join(kws)]
                        launch(argv, f"ui_{mode}.log")
                        entry["ok"] = True
            if entry.get("ok"):
                entry["status"] = "success"
                entry["error"] = None
        except OSError as exc:
            entry["error"] = str(exc)[:200]
        entry["finished_at"] = int(time.time())
        write_result(cmd_id, entry)
        keep = False
        if entry.get("ok"):
            entry["status"] = "success"
            entry["error"] = None
            keep = True
        elif entry["error"] in PERMANENT_ERRORS or attempts >= MAX_ATTEMPTS:
            entry["status"] = "failed"  # 永久失败或重试耗尽：终结
            keep = True
        else:
            entry["status"] = "retry"  # 暂时性失败：保留命令文件待下次触发
        write_result(cmd_id, entry)
        kept = {"ts": cmd.get("ts") or started, "mode": cmd.get("mode"),
                "actor": str(cmd.get("actor"))[:40],
                "ok": entry["status"] == "success",
                "error": entry.get("error"), "id": cmd_id,
                "status": entry["status"], "attempts": attempts}
        handled.append(kept)
        if keep:
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
