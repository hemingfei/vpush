"""Phase-2 lab actions: failed requeue and limited confirmed sync triggers.

Never puts cookies / tokens on argv or in audit / last-job JSON.
Does not toggle production middleware. Does not implement IMA QR.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ops_settings import (
    AUDIT_LOG_NAME,
    IMA_GROUP_ALLOWLIST,
    LAST_JOB_NAME,
    REQUEUE_CAP,
    RETRY_SUFFIX,
    SYNC_LIMIT_DEFAULT,
    SYNC_LIMIT_MAX,
    SYNC_OUTPUT_CHARS,
    cache_root,
    cicc_cookie_path,
    ima_secrets_path,
    python_bin,
    scripts_root,
    src_root,
    sync_timeout_seconds,
)
from ops_status import list_failed_files, redact, skip_cache_file

log = logging.getLogger("arm_lab_ops.actions")

_JOB_LOCK = threading.Lock()


class ActionError(RuntimeError):
    """Safe user-facing action error. Message must never include secrets."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def require_confirm(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict) or body.get("confirm") is not True:
        raise ActionError("confirm required", 400)


def clamp_sync_limit(raw: Any, *, default: int = SYNC_LIMIT_DEFAULT) -> int:
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ActionError("limit must be an integer") from exc
    return min(max(value, 1), SYNC_LIMIT_MAX)


def normalize_ima_group(raw: Any) -> str:
    value = str(raw or "legacy").strip() or "legacy"
    if value.startswith("legacy"):
        value = "legacy"
    if value not in IMA_GROUP_ALLOWLIST:
        raise ActionError(f"group not allowed: {value}")
    return value


def safe_relpath(raw: str) -> Path:
    """Relative path that cannot escape a root. Rejects abs / ~ / .. / NUL."""
    if not isinstance(raw, str) or not raw.strip():
        raise ActionError("path required")
    if "\x00" in raw:
        raise ActionError("invalid path")
    text = raw.strip().replace("\\", "/")
    if text.startswith(("/", "~")):
        raise ActionError("path must be relative")
    parts: list[str] = []
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ActionError("path escapes root")
        parts.append(part)
    if not parts:
        raise ActionError("path required")
    return Path(*parts)


def resolve_under(root: Path, rel: str | Path) -> Path:
    rel_path = rel if isinstance(rel, Path) else safe_relpath(rel)
    root_res = root.resolve()
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root_res)
    except ValueError as exc:
        raise ActionError("path escapes root") from exc
    return candidate


def append_audit(row: dict[str, Any], root: Path | None = None) -> None:
    """Append one JSON line. Caller must not put secrets in row."""
    path = (root or cache_root()) / "logs" / AUDIT_LOG_NAME
    payload = {"ts": _now(), **row}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_last_job(row: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    path = (root or cache_root()) / "logs" / LAST_JOB_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = dict(row)
    for key in ("stdout", "stderr", "error"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = redact(cleaned[key])
    if isinstance(cleaned.get("argv"), list):
        cleaned["argv"] = [redact(str(item)) for item in cleaned["argv"]]
    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cleaned


def _sidecar_path(file_path: Path) -> Path:
    return file_path.with_name(file_path.name + RETRY_SUFFIX)


def _unlink_sidecar(file_path: Path) -> bool:
    sidecar = _sidecar_path(file_path)
    try:
        if sidecar.is_file() or sidecar.is_symlink():
            sidecar.unlink()
            return True
    except OSError:
        return False
    return False


def requeue_failed(body: dict[str, Any] | None, root: Path | None = None) -> dict[str, Any]:
    """Move selected failed/ files back to staging/. Requires confirm: true."""
    require_confirm(body)
    payload = body if isinstance(body, dict) else {}
    cache = root or cache_root()
    failed_root = cache / "failed"
    staging_root = cache / "staging"
    if not failed_root.is_dir():
        raise ActionError("failed directory is missing")
    staging_root.mkdir(parents=True, exist_ok=True)

    if payload.get("all") is True:
        listed = list_failed_files(cache, cap=REQUEUE_CAP)
        rels = [str(item.get("path") or "") for item in listed.get("items") or []]
    else:
        raw_paths = payload.get("paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ActionError("paths required (or all: true)")
        rels = [str(item) for item in raw_paths[:REQUEUE_CAP]]

    moved: list[str] = []
    skipped: list[dict[str, str]] = []
    for raw in rels:
        try:
            rel = safe_relpath(raw)
        except ActionError as exc:
            skipped.append({"path": redact(str(raw)[:120]), "reason": str(exc)})
            continue
        if skip_cache_file(Path(rel.name)):
            skipped.append({"path": rel.as_posix(), "reason": "sidecar or skip suffix"})
            continue
        try:
            src = resolve_under(failed_root, rel)
        except ActionError as exc:
            skipped.append({"path": rel.as_posix(), "reason": str(exc)})
            continue
        if src.is_symlink() or not src.is_file():
            skipped.append({"path": rel.as_posix(), "reason": "not a regular file"})
            continue
        dest = resolve_under(staging_root, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            skipped.append({"path": rel.as_posix(), "reason": "staging dest exists"})
            continue
        try:
            shutil.move(str(src), str(dest))
        except OSError:
            try:
                shutil.copy2(src, dest)
                src.unlink()
            except OSError as exc:
                skipped.append({"path": rel.as_posix(), "reason": type(exc).__name__})
                continue
        _unlink_sidecar(src)
        leftover = failed_root / rel
        _unlink_sidecar(leftover)
        moved.append(rel.as_posix())

    append_audit(
        {
            "action": "requeue",
            "count": len(moved),
            "skipped": len(skipped),
            "all": payload.get("all") is True,
        },
        root=cache,
    )
    log.info("requeue moved=%s skipped=%s", len(moved), len(skipped))
    return {
        "ok": True,
        "action": "requeue",
        "moved": moved,
        "skipped": skipped,
        "count": len(moved),
    }


def _script_path(name: str) -> Path:
    path = scripts_root() / name
    if not path.is_file():
        raise ActionError(f"script missing: {name}")
    return path


def _job_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VPUSH_ARM_MIDDLEWARE", None)
    src = src_root()
    pythonpath = str(src)
    existing = env.get("PYTHONPATH", "")
    if existing and pythonpath not in existing.split(os.pathsep):
        pythonpath = pythonpath + os.pathsep + existing
    env["PYTHONPATH"] = pythonpath
    env["CACHE_ROOT"] = str(cache_root())
    env["VPUSH_ARM_STAGING_ROOT"] = str(cache_root() / "staging")
    secrets = ima_secrets_path()
    env["IMA_PURE_SECRETS_FILE"] = str(secrets)
    env["VPUSH_CICC_COOKIE_FILE"] = str(cicc_cookie_path())
    return env


def _clip_output(text: str) -> str:
    cleaned = redact(text or "")
    if len(cleaned) > SYNC_OUTPUT_CHARS:
        return cleaned[:SYNC_OUTPUT_CHARS] + "..."
    return cleaned


def run_subprocess_job(
    action: str,
    argv: list[str],
    *,
    extra_env: dict[str, str] | None = None,
    timeout: int | None = None,
    root: Path | None = None,
    runner=None,
) -> dict[str, Any]:
    """Run a lab script. Never put secrets on argv. Captures redacted output."""
    if not _JOB_LOCK.acquire(blocking=False):
        raise ActionError("a sync job is already running", 409)
    cache = root or cache_root()
    env = _job_env()
    if extra_env:
        env.update(extra_env)
    timeout_s = timeout if timeout is not None else sync_timeout_seconds()
    run = runner or subprocess.run
    public_argv = [Path(argv[1]).name if len(argv) > 1 else action, *argv[2:]]
    started = _now()
    try:
        try:
            proc = run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
                env=env,
                cwd=str(src_root()),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _clip_output(exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
            stderr = _clip_output(exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
            row = {
                "ok": False,
                "action": action,
                "ts": started,
                "argv": public_argv,
                "returncode": None,
                "timeout": True,
                "stdout": stdout,
                "stderr": stderr or "timed out",
                "error": f"timed out after {timeout_s}s",
            }
            write_last_job(row, root=cache)
            append_audit({"action": action, "count": 1, "timeout": True}, root=cache)
            return row
        except OSError as exc:
            row = {
                "ok": False,
                "action": action,
                "ts": started,
                "argv": public_argv,
                "returncode": None,
                "timeout": False,
                "stdout": "",
                "stderr": "",
                "error": type(exc).__name__,
            }
            write_last_job(row, root=cache)
            append_audit({"action": action, "count": 1, "error": type(exc).__name__}, root=cache)
            return row

        row = {
            "ok": proc.returncode == 0,
            "action": action,
            "ts": started,
            "argv": public_argv,
            "returncode": proc.returncode,
            "timeout": False,
            "stdout": _clip_output(proc.stdout or ""),
            "stderr": _clip_output(proc.stderr or ""),
            "error": None if proc.returncode == 0 else "script exited non-zero",
        }
        write_last_job(row, root=cache)
        append_audit(
            {"action": action, "count": 1, "returncode": proc.returncode},
            root=cache,
        )
        return row
    finally:
        _JOB_LOCK.release()


def ima_sync(body: dict[str, Any] | None, *, dry_run: bool) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
    if not dry_run:
        require_confirm(payload)
    limit = clamp_sync_limit(payload.get("limit"))
    group = normalize_ima_group(payload.get("group"))
    secrets = ima_secrets_path()
    if not secrets.is_file():
        raise ActionError("IMA secrets file missing")
    script = _script_path("ima_arm_lab_sync.py")
    mode = "--dry-run" if dry_run else "--apply"
    argv = [
        python_bin(),
        str(script),
        "--enable",
        mode,
        "--limit",
        str(limit),
        "--group",
        group,
    ]
    action = "ima-dry-run" if dry_run else "ima-apply"
    result = run_subprocess_job(action, argv)
    result["limit"] = limit
    result["group"] = group
    return result


def cicc_sync(body: dict[str, Any] | None, *, dry_run: bool) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
    if not dry_run:
        require_confirm(payload)
    limit = clamp_sync_limit(payload.get("limit"))
    cookie = cicc_cookie_path()
    if not cookie.is_file():
        raise ActionError(
            f"CICC cookie file missing ({cookie.name}); set VPUSH_CICC_COOKIE_FILE"
        )
    script = _script_path("cicc_arm_lab_sync.py")
    mode = "--dry-run" if dry_run else "--apply"
    argv = [
        python_bin(),
        str(script),
        "--enable",
        mode,
        "--limit",
        str(limit),
    ]
    days = payload.get("days")
    if days not in (None, ""):
        try:
            days_n = max(0, min(int(days), 30))
        except (TypeError, ValueError) as exc:
            raise ActionError("days must be an integer") from exc
        argv.extend(["--days", str(days_n)])
    action = "cicc-dry-run" if dry_run else "cicc-apply"
    result = run_subprocess_job(action, argv)
    result["limit"] = limit
    return result

