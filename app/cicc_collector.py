"""中金研报采集控制：经 NFS 归档上的 .cicc 控制目录与存储机 systemd 交互。

通道（复用 .vpush-storage-health.json 同款"归档内文件"模式，无新网络服务）：
  命令  写 local/.cicc/commands/<epoch_ms>-<mode>.json，
        存储机 vpush-cicc-dispatch.path 消费（mode ∈ MODES）
  状态  读 local/.cicc/status.json（存储机每 60s 刷新，超时视为 stale）
  开关  写/删 local/.cicc/incremental.enabled（每日 03:00 增量的总开关）
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

MODES = ("incr", "year", "all", "stop", "compress", "schedule")
STATUS_STALE_SECONDS = 300


class CiccControl:
    def __init__(self, archive_root: str):
        self.ctrl = Path(archive_root) / "local" / ".cicc"

    def status(self) -> dict:
        path = self.ctrl / "status.json"
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            stale = int(time.time()) - int(data.get("ts", 0)) > STATUS_STALE_SECONDS
        except Exception:
            return {"available": True, "stale": True}
        return {"available": True, "stale": stale, **data}

    def trigger(self, mode: str, actor: str, extra: dict | None = None) -> dict:
        if mode not in MODES:
            raise ValueError(f"未知操作：{mode}")
        cmds = self.ctrl / "commands"
        cmds.mkdir(parents=True, exist_ok=True)
        name = f"{int(time.time() * 1000)}-{mode}.json"
        tmp = cmds / f".tmp.{os.getpid()}"
        payload = {"mode": mode, "actor": actor, "ts": int(time.time())}
        if extra:
            payload.update(extra)
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, cmds / name)  # 原子落名，dispatch 的 inotify 不会读到半截文件
        return {"queued": mode}

    def schedule_enabled(self) -> bool:
        return (self.ctrl / "incremental.enabled").exists()

    def read_schedule(self) -> dict:
        """当前采集时间计划（存储机 cicc-schedule.json，经 status 透传时缺省 03:00）。"""
        data = json.loads((self.ctrl / "status.json").read_text(encoding="utf-8")) \
            if (self.ctrl / "status.json").exists() else {}
        storage = data.get("storage") or {}
        schedule = storage.get("schedule") or {}
        t = str(schedule.get("time") or "03:00")
        return {"time": t if re.fullmatch(r"\d{2}:\d{2}", t) else "03:00",
                "schedule_enabled": self.schedule_enabled()}

    def set_schedule_time(self, time_of_day: str, actor: str) -> dict:
        """下发采集时间（HH:mm），存储机 dispatch 写 cicc-schedule.json。"""
        return self.trigger("schedule", actor, extra={"time": time_of_day})

    def set_schedule(self, enabled: bool) -> dict:
        self.ctrl.mkdir(parents=True, exist_ok=True)
        flag = self.ctrl / "incremental.enabled"
        if enabled:
            tmp = self.ctrl / ".enabled.tmp"
            tmp.write_text("1", encoding="utf-8")
            os.replace(tmp, flag)
        else:
            flag.unlink(missing_ok=True)
        return {"schedule_enabled": enabled}


def from_env() -> CiccControl | None:
    archive = os.environ.get("IMA_ARCHIVE_ROOT", "").strip()
    if not archive:
        return None
    return CiccControl(archive)
