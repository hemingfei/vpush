"""Lab-only schedule / concurrency knobs for the ARM ops panel.

Persists $CACHE_ROOT/ops-lab-settings.json (never secrets). Host wrappers
read LIMIT / parallel from that file. Puller reads puller_batch_size from
the same JSON (or $CACHE_ROOT/ops-puller.env).
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from ops_actions import ActionError, append_audit, require_confirm
from ops_settings import (
    CICC_INCR_DAYS_DEFAULT,
    CICC_INCR_DAYS_MAX,
    CICC_INCR_DAYS_MIN,
    DEFAULT_CICC_TIMER_UNIT,
    DEFAULT_DAILY_SYNC_CLOCK,
    DEFAULT_IMA_GROUPS_PARALLEL,
    DEFAULT_SYNC_TIMEZONE,
    DEFAULT_TIMER_HELPER,
    DEFAULT_TIMER_UNIT,
    LAB_SYNC_LIMIT_DEFAULT,
    LAB_SYNC_LIMIT_MAX,
    PULLER_BATCH_DEFAULT,
    PULLER_BATCH_MAX,
    PULLER_BATCH_MIN,
    cicc_timer_unit,
    lab_settings_path,
    puller_env_path,
    timer_helper_path,
    timer_unit,
)
from ops_status import timer_status

log = logging.getLogger("arm_lab_ops.knobs")

_CLOCK_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")
_TZ_RE = re.compile(r"^[A-Za-z0-9_+\-/]+$")
SETTINGS_FILE_MODE = 0o664
PULLER_ENV_MODE = 0o664

DEFAULTS: dict[str, Any] = {
    "daily_sync_clock": DEFAULT_DAILY_SYNC_CLOCK,
    "timezone": DEFAULT_SYNC_TIMEZONE,
    "ima_limit_per_group": LAB_SYNC_LIMIT_DEFAULT,
    "cicc_limit": LAB_SYNC_LIMIT_DEFAULT,
    "cicc_incr_days": CICC_INCR_DAYS_DEFAULT,
    "ima_groups_parallel": DEFAULT_IMA_GROUPS_PARALLEL,
    "puller_batch_size": PULLER_BATCH_DEFAULT,
}


def parse_clock(raw: Any) -> str:
    """Parse HH:MM (optional :SS) and normalize to HH:MM."""
    if raw is None or str(raw).strip() == "":
        return DEFAULT_DAILY_SYNC_CLOCK
    text = str(raw).strip()
    match = _CLOCK_RE.fullmatch(text)
    if not match:
        raise ActionError("daily_sync_clock must be HH:MM (24h, Asia/Shanghai)")
    hour = int(match.group(1))
    minute = int(match.group(2))
    return f"{hour:02d}:{minute:02d}"


def parse_timezone(raw: Any) -> str:
    if raw is None or str(raw).strip() == "":
        return DEFAULT_SYNC_TIMEZONE
    text = str(raw).strip()
    if not _TZ_RE.fullmatch(text) or ".." in text:
        raise ActionError("timezone is invalid")
    return text


def parse_limit(raw: Any, *, field: str, default: int = LAB_SYNC_LIMIT_DEFAULT) -> int:
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ActionError(f"{field} must be an integer") from exc
    if value < 1 or value > LAB_SYNC_LIMIT_MAX:
        raise ActionError(f"{field} must be between 1 and {LAB_SYNC_LIMIT_MAX}")
    return value


def parse_batch(raw: Any, *, default: int = PULLER_BATCH_DEFAULT) -> int:
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ActionError("puller_batch_size must be an integer") from exc
    if value < PULLER_BATCH_MIN or value > PULLER_BATCH_MAX:
        raise ActionError(
            f"puller_batch_size must be between {PULLER_BATCH_MIN} and {PULLER_BATCH_MAX}"
        )
    return value


def parse_days(raw: Any, *, default: int = CICC_INCR_DAYS_DEFAULT) -> int:
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ActionError("cicc_incr_days must be an integer") from exc
    if value < CICC_INCR_DAYS_MIN or value > CICC_INCR_DAYS_MAX:
        raise ActionError(
            f"cicc_incr_days must be between {CICC_INCR_DAYS_MIN} and {CICC_INCR_DAYS_MAX}"
        )
    return value


def parse_bool(raw: Any, *, default: bool = DEFAULT_IMA_GROUPS_PARALLEL) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ActionError("ima_groups_parallel must be a boolean")


def validate_settings(body: dict[str, Any] | None, *, base: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
    current = dict(DEFAULTS)
    if isinstance(base, dict):
        current.update({key: base[key] for key in DEFAULTS if key in base})
    return {
        "daily_sync_clock": parse_clock(payload.get("daily_sync_clock", current["daily_sync_clock"])),
        "timezone": parse_timezone(payload.get("timezone", current["timezone"])),
        "ima_limit_per_group": parse_limit(
            payload.get("ima_limit_per_group", current["ima_limit_per_group"]),
            field="ima_limit_per_group",
        ),
        "cicc_limit": parse_limit(
            payload.get("cicc_limit", current["cicc_limit"]),
            field="cicc_limit",
        ),
        "ima_groups_parallel": parse_bool(
            payload.get("ima_groups_parallel", current["ima_groups_parallel"])
        ),
        "cicc_incr_days": parse_days(
            payload.get("cicc_incr_days", current.get("cicc_incr_days", CICC_INCR_DAYS_DEFAULT))
        ),
        "puller_batch_size": parse_batch(
            payload.get("puller_batch_size", current["puller_batch_size"])
        ),
    }


def load_settings(path: Path | None = None) -> dict[str, Any]:
    target = path or lab_settings_path()
    if not target.is_file():
        return dict(DEFAULTS)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    try:
        return validate_settings(data, base=DEFAULTS)
    except ActionError:
        merged = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in data:
                try:
                    merged.update(validate_settings({key: data[key]}, base=merged))
                except ActionError:
                    continue
        return merged


def write_settings_file(settings: dict[str, Any], path: Path | None = None) -> Path:
    target = path or lab_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {**settings, "timezone": settings.get("timezone") or DEFAULT_SYNC_TIMEZONE}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, SETTINGS_FILE_MODE)
    tmp.replace(target)
    try:
        os.chmod(target, SETTINGS_FILE_MODE)
    except OSError:
        pass
    return target


def write_puller_env(settings: dict[str, Any], path: Path | None = None) -> Path:
    """Write PULLER_BATCH_SIZE for systemd EnvironmentFile=-$CACHE_ROOT/ops-puller.env."""
    target = path or puller_env_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    batch = int(settings["puller_batch_size"])
    text = (
        "# Generated by ARM lab ops. Not secrets. Sourced by puller systemd if configured.\n"
        f"PULLER_BATCH_SIZE={batch}\n"
    )
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, PULLER_ENV_MODE)
    tmp.replace(target)
    try:
        os.chmod(target, PULLER_ENV_MODE)
    except OSError:
        pass
    return target


def host_apply_command(settings: dict[str, Any]) -> str:
    clock = settings["daily_sync_clock"]
    tz = settings.get("timezone") or DEFAULT_SYNC_TIMEZONE
    helper = timer_helper_path()
    if not helper.is_file():
        helper = Path(DEFAULT_TIMER_HELPER)
    return f"sudo {helper} {clock} {tz}"


def oncalendar_line(clock: str, tz: str = DEFAULT_SYNC_TIMEZONE) -> str:
    return f"*-*-* {clock}:00 {tz}"


def dropin_text(clock: str, tz: str = DEFAULT_SYNC_TIMEZONE) -> str:
    return (
        "# Generated by ARM lab ops. Clears inherited OnCalendar then sets both timers.\n"
        "[Timer]\n"
        "OnCalendar=\n"
        f"OnCalendar={oncalendar_line(clock, tz)}\n"
    )


def _write_timer_dropin(unit: str, clock: str, tz: str) -> Path:
    if not unit.endswith(".timer") or "/" in unit or ".." in unit:
        raise ActionError("invalid timer unit")
    directory = Path("/etc/systemd/system") / f"{unit}.d"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "ops-schedule.conf"
    path.write_text(dropin_text(clock, tz), encoding="utf-8")
    return path


def _systemctl_available(runner=subprocess.run) -> bool:
    try:
        proc = runner(
            ["systemctl", "show", timer_unit(), "--property=Id"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def apply_sync_timers(
    settings: dict[str, Any],
    *,
    runner=None,
) -> dict[str, Any]:
    """Rewrite CICC timer OnCalendar only. Never restart the IMA lab timer."""
    clock = settings["daily_sync_clock"]
    tz = settings.get("timezone") or DEFAULT_SYNC_TIMEZONE
    ima = timer_unit()
    cicc = cicc_timer_unit()
    host_cmd = host_apply_command(settings)
    run = runner or subprocess.run
    helper = timer_helper_path()
    units = [cicc]
    skipped = [ima]

    if helper.is_file() and os.access(helper, os.X_OK):
        try:
            proc = run(
                [str(helper), clock, tz],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "applied": False,
                "method": "helper",
                "detail": type(exc).__name__,
                "host_command": host_cmd,
                "units": units,
                "skipped": skipped,
            }
        if proc.returncode == 0:
            return {
                "applied": True,
                "method": "helper",
                "detail": None,
                "host_command": host_cmd,
                "units": units,
                "skipped": skipped,
            }
        err = (proc.stderr or proc.stdout or "helper failed").splitlines()
        return {
            "applied": False,
            "method": "helper",
            "detail": (err[0] if err else "helper failed")[:160],
            "host_command": host_cmd,
            "units": units,
            "skipped": skipped,
        }

    if not _systemctl_available(runner=run):
        return {
            "applied": False,
            "method": "host-command",
            "detail": "systemctl not available from this process (typical in docker)",
            "host_command": host_cmd,
            "units": units,
            "skipped": skipped,
        }

    written: list[str] = []
    try:
        written.append(str(_write_timer_dropin(cicc, clock, tz)))
        reload = run(
            ["systemctl", "daemon-reload"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if reload.returncode != 0:
            raise OSError((reload.stderr or "daemon-reload failed").strip()[:160])
        restart = run(
            ["systemctl", "restart", cicc],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if restart.returncode != 0:
            raise OSError((restart.stderr or "timer restart failed").strip()[:160])
    except OSError as exc:
        return {
            "applied": False,
            "method": "dropin",
            "detail": f"{type(exc).__name__}: {exc}"[:160],
            "host_command": host_cmd,
            "units": units,
            "skipped": skipped,
            "dropins": written,
        }
    return {
        "applied": True,
        "method": "dropin",
        "detail": None,
        "host_command": host_cmd,
        "units": units,
        "skipped": skipped,
        "dropins": written,
    }


def timer_snapshot() -> dict[str, Any]:
    ima = timer_status(timer_unit())
    cicc = timer_status(cicc_timer_unit())
    return {
        "ima": ima,
        "cicc": cicc,
        "next": ima.get("next") or cicc.get("next"),
    }


def settings_public(settings: dict[str, Any], apply_info: dict[str, Any] | None = None) -> dict[str, Any]:
    path = lab_settings_path()
    apply_row = apply_info or {
        "applied": False,
        "method": None,
        "detail": None,
        "host_command": host_apply_command(settings),
        "units": [cicc_timer_unit()],
        "skipped": [timer_unit()],
    }
    return {
        "ok": True,
        "settings": settings,
        "path": str(path),
        "exists": path.is_file(),
        "timers": timer_snapshot(),
        "apply": apply_row,
        "defaults": dict(DEFAULTS),
    }


def get_settings() -> dict[str, Any]:
    return settings_public(load_settings())


def save_settings(body: dict[str, Any] | None, *, runner=None) -> dict[str, Any]:
    require_confirm(body)
    payload = body if isinstance(body, dict) else {}
    current = load_settings()
    settings = validate_settings(payload, base=current)
    write_settings_file(settings)
    write_puller_env(settings)
    apply_info = apply_sync_timers(settings, runner=runner)
    append_audit(
        {
            "action": "settings-save",
            "clock": settings["daily_sync_clock"],
            "timezone": settings["timezone"],
            "ima_limit": settings["ima_limit_per_group"],
            "cicc_limit": settings["cicc_limit"],
            "cicc_incr_days": settings["cicc_incr_days"],
            "parallel": settings["ima_groups_parallel"],
            "batch": settings["puller_batch_size"],
            "timers_applied": apply_info.get("applied") is True,
            "apply_method": apply_info.get("method"),
        }
    )
    log.info(
        "settings saved clock=%s ima_limit=%s cicc_limit=%s batch=%s timers=%s",
        settings["daily_sync_clock"],
        settings["ima_limit_per_group"],
        settings["cicc_limit"],
        settings["puller_batch_size"],
        apply_info.get("applied"),
    )
    return settings_public(settings, apply_info)


# Re-export for tests / docs.
__all__ = [
    "DEFAULTS",
    "DEFAULT_CICC_TIMER_UNIT",
    "DEFAULT_TIMER_UNIT",
    "apply_sync_timers",
    "dropin_text",
    "get_settings",
    "host_apply_command",
    "load_settings",
    "oncalendar_line",
    "parse_batch",
    "parse_bool",
    "parse_clock",
    "parse_days",
    "parse_limit",
    "save_settings",
    "settings_public",
    "validate_settings",
    "write_puller_env",
    "write_settings_file",
]
