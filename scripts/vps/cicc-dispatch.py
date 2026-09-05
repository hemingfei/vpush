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
import hashlib
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
                    "invalid_json", "invalid_id", "stale_command", "permission_denied",
                    "collector_auth", "collector_quota", "collector_stopped",
                    "backup_script_missing",
                    "consistency_script_missing", "dedup_script_missing"}
RESULT_STALE_SECONDS = 600  # running 结果超时视为上次运行崩溃，恢复重试
MAX_TS_FUTURE = 300  # 命令 ts 允许的最大未来偏差（秒），防伪造/损坏时间戳
MAX_TS_AGE = 24 * 3600  # 控制命令只在 24 小时内有效，避免挂载恢复后重放旧操作
COLLECTOR_TIMEOUT = 12 * 3600
_TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def valid_time_of_day(value) -> bool:
    """HH:mm 严格校验：00:00..23:59（旧实现会放过 24:99）。"""
    return isinstance(value, str) and bool(_TIME_RE.fullmatch(value))


def validate_command(cmd: dict) -> str | None:
    """返回错误原因（None=合法）。命令信封：{id, mode, actor, ts, payload}。

    旧格式的缺失 id 在调用前被转换为基于文件名的安全摘要。
    """
    if not isinstance(cmd, dict):
        return "invalid_json"
    if not isinstance(cmd.get("id"), str) or not _ID_RE.fullmatch(cmd["id"]):
        return "invalid_id"
    mode = cmd.get("mode")
    if mode not in ALL_MODES:
        return "unknown_mode"
    ts = cmd.get("ts")
    if not isinstance(ts, int) or isinstance(ts, bool) or ts <= 0:
        return "invalid_ts"
    if ts > int(time.time()) + MAX_TS_FUTURE:
        return "invalid_ts"  # 未来时间超允许偏差
    if ts < int(time.time()) - MAX_TS_AGE:
        return "stale_command"
    payload = cmd.get("payload")
    if not isinstance(payload, dict):
        return "invalid_payload"
    if mode in MODE_ARGS:
        for key, error in (("categories", "invalid_categories"),
                           ("keywords", "invalid_keywords")):
            values = payload.get(key, [])
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                return error
    return None


def safe_command_id(cmd: dict, name: str) -> tuple[str, str | None]:
    """返回仅能作为单个结果文件名使用的 ID；旧命令使用文件名摘要。"""
    value = cmd.get("id")
    if value is None:
        digest = hashlib.sha256(name.encode("utf-8", "replace")).hexdigest()[:24]
        return f"legacy-{digest}", None
    if isinstance(value, str) and _ID_RE.fullmatch(value):
        return value, None
    digest = hashlib.sha256(name.encode("utf-8", "replace")).hexdigest()[:24]
    return f"invalid-{digest}", "invalid_id"


def normalize_legacy_command(cmd: dict, cmd_id: str) -> dict:
    """将短期兼容的顶层扩展字段转成统一 payload。"""
    normalized = dict(cmd)
    normalized["id"] = cmd_id
    if "payload" not in normalized:
        normalized["payload"] = {
            key: normalized[key] for key in ("time", "categories", "keywords")
            if key in normalized
        }
    return normalized


def normalize_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def write_result(cmd_id: str, entry: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    write_json(os.path.join(RESULTS_DIR, f"{cmd_id}.json"), entry)


def load_result(cmd_id: str) -> dict | None:
    return read_json(os.path.join(RESULTS_DIR, f"{cmd_id}.json"))


def completion_path(cmd_id: str) -> str:
    return os.path.join(CTRL, f"completed-{cmd_id}.json")


def command_completed(cmd_id: str) -> bool:
    marker = read_json(completion_path(cmd_id), {}) or {}
    return marker.get("id") == cmd_id


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


def stop_requested() -> bool:
    """采集等待期间仅识别通过完整协议校验的 stop 命令。"""
    try:
        names = os.listdir(COMMANDS_DIR)
    except OSError:
        return False
    for name in names:
        if not name.endswith(".json") or name.startswith("."):
            continue
        raw = read_json(os.path.join(COMMANDS_DIR, name))
        if not isinstance(raw, dict):
            continue
        cmd_id, id_error = safe_command_id(raw, name)
        cmd = normalize_legacy_command(raw, cmd_id)
        if id_error is None and validate_command(cmd) is None and cmd.get("mode") == "stop":
            return True
    return False


def classify_collector_error(returncode: int, paused: dict, started_at: int) -> str:
    try:
        marker_ts = int(paused.get("ts") or 0)
    except (TypeError, ValueError):
        marker_ts = 0
    if marker_ts >= started_at and paused.get("reason") == "auth":
        return "collector_auth"
    if marker_ts >= started_at and paused.get("reason") == "quota":
        return "collector_quota"
    return f"collector_exit_{returncode}"


def run_collector(argv: list[str]) -> tuple[bool, str | None]:
    """等待采集器真实退出；等待期间仍响应新投递的 stop 命令。"""
    os.makedirs(CICC_DIR, exist_ok=True)
    started_at = int(time.time())
    with open(os.path.join(CICC_DIR, "ui_collector.log"), "ab") as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                   cwd=CICC_DIR, close_fds=True)
        deadline = time.monotonic() + COLLECTOR_TIMEOUT
        while process.poll() is None:
            if stop_requested():
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                return False, "collector_stopped"
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                return False, "collector_timeout"
            time.sleep(1)
    if process.returncode == 0:
        return True, None
    paused = read_json(os.path.join(CTRL, "paused.json"), {}) or {}
    return False, classify_collector_error(process.returncode, paused, started_at)


def main() -> None:
    os.makedirs(COMMANDS_DIR, exist_ok=True)
    handled = []
    for name in sorted(os.listdir(COMMANDS_DIR)):
        if not name.endswith(".json") or name.startswith("."):
            continue
        path = os.path.join(COMMANDS_DIR, name)
        raw_cmd = read_json(path)
        source_cmd = raw_cmd if isinstance(raw_cmd, dict) else {}
        cmd_id, id_error = safe_command_id(source_cmd, name)
        cmd = normalize_legacy_command(source_cmd, cmd_id)
        prev = load_result(cmd_id) or {}
        if prev.get("status") == "success":
            # 幂等：已成功（可能上次成功与删除之间崩溃），只清命令不重跑
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        if command_completed(cmd_id):
            prev.update({"id": cmd_id, "mode": cmd.get("mode"), "status": "success",
                         "finished_at": int(time.time()), "error": None})
            write_result(cmd_id, prev)
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        if prev.get("status") == "running" and \
                int(time.time()) - int(prev.get("started_at") or 0) < RESULT_STALE_SECONDS:
            continue  # running 且未超时：上次运行未完成（可能真在跑），跳过本次
        if int(prev.get("attempts") or 0) >= MAX_ATTEMPTS:
            prev.update({"status": "failed", "finished_at": int(time.time()),
                         "error": prev.get("error") or "retry_exhausted"})
            write_result(cmd_id, prev)
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        started = int(time.time())
        attempts = int(prev.get("attempts") or 0) + 1
        entry = {"id": cmd_id, "mode": cmd.get("mode"), "status": "running",
                 "started_at": started, "finished_at": 0, "attempts": attempts,
                 "error": None}
        write_result(cmd_id, entry)  # 先落 running：崩溃后 stale 恢复可重试
        error = id_error or validate_command(cmd)
        if raw_cmd is None:  # 非法 JSON：空 dict 会误报 unknown_mode
            error = "invalid_json"
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
                                   {"categories": normalize_strings(cats),
                                    "keywords": normalize_strings(kws)})
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
                        filters_path = os.path.join(CTRL, f"filters-{cmd_id}.json")
                        if attempts == 1 or not os.path.exists(filters_path):
                            filters = payload
                            if "categories" not in payload and "keywords" not in payload:
                                saved = read_json(os.path.join(CTRL, "cicc_settings.json"), {}) or {}
                                filters = saved if isinstance(saved, dict) else {}
                            categories = filters.get("categories", [])
                            keywords = filters.get("keywords", [])
                            if not isinstance(categories, list) or not all(
                                    isinstance(value, str) for value in categories):
                                categories = []
                            if not isinstance(keywords, list) or not all(
                                    isinstance(value, str) for value in keywords):
                                keywords = []
                            write_json(filters_path, {
                                "categories": normalize_strings(categories),
                                "keywords": normalize_strings(keywords),
                            })
                        argv += ["--filters-file", filters_path]
                        marker_path = completion_path(cmd_id)
                        if attempts == 1:
                            try:
                                os.remove(marker_path)
                            except FileNotFoundError:
                                pass
                        argv += ["--completion-file", marker_path]
                        entry["ok"], entry["error"] = run_collector(argv)
            if entry.get("ok"):
                entry["status"] = "success"
                entry["error"] = None
        except PermissionError:
            entry["error"] = "permission_denied"
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
