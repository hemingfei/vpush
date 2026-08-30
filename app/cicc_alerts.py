"""中金采集与存储的阈值告警和增量结果通知。

挂在调度周期（Scheduler tick）里调用 maybe_check_cicc：读 .cicc/status.json →
评估阈值（磁盘/stale）与增量完成事件 → 冷却去重后经管理员现有渠道推送。
纯函数 evaluate_alerts/should_notify 便于单测；状态存 DB settings。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from .cicc_collector import from_env
from .logging_setup import redact_secrets

logger = logging.getLogger(__name__)

ALERT_SETTINGS_KEY = "cicc_alert_settings"
ALERT_STATE_KEY = "cicc_alert_state"
CHECK_INTERVAL_SECONDS = 300
ALERT_COOLDOWN_SECONDS = 86400
DEFAULT_SETTINGS = {"disk_warn": 80, "disk_crit": 90,
                    "stale_minutes": 30, "notify_enabled": True}


def load_alert_settings(db) -> dict:
    raw = db.get_setting(ALERT_SETTINGS_KEY)
    settings = dict(DEFAULT_SETTINGS)
    if raw:
        try:
            settings.update(json.loads(raw))
        except (ValueError, TypeError):
            pass
    return settings


def save_alert_settings(db, settings: dict) -> None:
    clean = {"disk_warn": int(settings.get("disk_warn") or 80),
             "disk_crit": int(settings.get("disk_crit") or 90),
             "stale_minutes": int(settings.get("stale_minutes") or 30),
             "notify_enabled": bool(settings.get("notify_enabled", True))}
    db.set_setting(ALERT_SETTINGS_KEY, json.dumps(clean))
    return clean


def evaluate_alerts(status: dict, settings: dict,
                    now: int | None = None) -> list[tuple[str, str]]:
    """纯函数：status + 告警设置 → 待发告警 [(冷却键, 文案)]。"""
    now = int(now or time.time())
    out: list[tuple[str, str]] = []
    storage = status.get("storage") or {}
    disk = storage.get("disk") or {}
    pct = float(disk.get("pct") or 0)
    crit = int(settings.get("disk_crit") or 90)
    warn = int(settings.get("disk_warn") or 80)
    if pct >= crit:
        out.append(("disk_crit", f"🔴 存储机磁盘使用率 {pct}%（≥{crit}%），请尽快清理归档。"))
    elif pct >= warn:
        out.append(("disk_warn", f"🟡 存储机磁盘使用率 {pct}%（≥{warn}%）。"))
    ts = int(status.get("ts") or 0)
    stale_min = max(int(settings.get("stale_minutes") or 30), 1)
    if ts and now - ts > stale_min * 60:
        out.append(("stale", f"⚠️ 存储机状态已超过 {stale_min} 分钟未刷新，采集/状态服务可能异常。"))
    return out


def should_notify(state: dict, key: str, now: int,
                  window: int = ALERT_COOLDOWN_SECONDS) -> bool:
    last = int((state.get("alerts") or {}).get(key) or 0)
    return now - last >= window


def paused_alert(status: dict, state: dict) -> tuple[str, str] | None:
    """纯函数：paused.json 出现且 ts 前进（新一次熔断）→ 告警文案；冷却由 should_notify 统一管。"""
    paused = status.get("paused")
    if not paused:
        return None
    ts = int(paused.get("ts") or 0)
    if not ts or ts <= int(state.get("paused_notified_ts") or 0):
        return None
    reason = str(paused.get("reason") or "")
    if reason == "quota":
        return ("paused", "🔴 中金采集暂停：本月研报配额已满，等月初重置（每日增量会自动重试）。")
    if reason == "auth":
        return ("paused", "🔴 中金采集暂停：登录态失效，请在存储机更新 Cookie 文件。")
    return ("paused", f"🔴 中金采集暂停：{paused.get('detail') or reason or '未知原因'}。")


def _load_state(db) -> dict:
    raw = db.get_setting(ALERT_STATE_KEY)
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def maybe_check_cicc(db, notifiers: list, notifiers_config=None, *, now: int | None = None) -> None:
    """调度周期入口：内部 60s 节流；发告警与增量完成通知（各带冷却）。"""
    from .channels import build_channel_notifier, iter_user_channels

    now = int(now or time.time())
    state = _load_state(db)
    if now - int(state.get("last_check") or 0) < CHECK_INTERVAL_SECONDS:
        return
    state["last_check"] = now
    settings = load_alert_settings(db)

    ctl = from_env()
    status = ctl.status() if ctl else {}
    pending: list[tuple[str, str]] = []
    if settings.get("notify_enabled", True) and status and not status.get("stale"):
        pending += evaluate_alerts(status, settings, now)
        pa = paused_alert(status, state)
        if pa:
            pending.append(pa)
            state["paused_notified_ts"] = int((status.get("paused") or {}).get("ts") or 0)
        summary = (status.get("storage") or {}).get("last_incr_summary") or {}
        s_ts = int(summary.get("ts") or 0)
        if s_ts > int(state.get("incr_notified_ts") or 0):
            pending.append(("__incr__",
                            f"📥 中金增量完成：新增 {summary.get('added', 0)} 篇，"
                            f"失败 {summary.get('failed', 0)} 篇。"))
            state["incr_notified_ts"] = s_ts

    sendable = [(key, msg) for key, msg in pending
                if key == "__incr__" or should_notify(state, key, now)]
    if sendable:
        client = __import__("httpx").Client(timeout=15)
        try:
            for user in db.list_users():
                if not user.get("is_admin"):
                    continue
                for channel in iter_user_channels(user, notifiers_config, db):
                    try:
                        notifier = build_channel_notifier(
                            channel, user, notifiers_config, client=client, db=db)
                        for _, msg in sendable:
                            notifier.send_text(redact_secrets(msg))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("中金告警发送失败 user=%s channel=%s err=%s",
                                       user.get("username"), channel, exc)
        finally:
            client.close()
        for key, _ in sendable:
            if key != "__incr__":
                state.setdefault("alerts", {})[key] = now
    db.set_setting(ALERT_STATE_KEY, json.dumps(state))

