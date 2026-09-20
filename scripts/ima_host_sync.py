#!/usr/bin/env python3
"""ARM host IMA sync: call the production collector, nothing else.

This is the same ``ImaDocumentService.sync_once()`` path production has used
for a long time. The process only sets ARM staging env and loads host secrets.
Do not put ``VPUSH_ARM_MIDDLEWARE=1`` in production compose.

  python3 scripts/ima_host_sync.py
  python3 scripts/ima_host_sync.py --enable
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.arm_middleware import middleware_enabled
from app.ima_documents import (
    IMA_PURE_GROUPS_KEY,
    IMA_PURE_KB_ID_KEY,
    IMA_PURE_REFRESH_TOKEN_KEY,
    IMA_PURE_ROOT_FOLDER_KEY,
    IMA_PURE_UID_KEY,
    ImaDocumentService,
    _safe_error,
)
from app.ima_storage import ImaStorageStatus
from scripts.ima_arm_lab_sync import LabSyncError, arm_middleware_env, load_secrets

_DISABLED_HINT = (
    "IMA host sync 未启用（需要 --enable / --arm-middleware 或 "
    "VPUSH_ARM_MIDDLEWARE=1）。未列出、未下载。不要在生产 compose 里设置 "
    "VPUSH_ARM_MIDDLEWARE=1。"
)
_RESULT_KEYS = (
    "status",
    "groups",
    "skipped_groups",
    "succeeded_groups",
    "failed_groups",
    "total",
    "pending",
    "downloaded",
    "failed",
    "last_error",
    "discovery_error",
)


class SettingsDB:
    """Minimal settings store. ImaDocumentService only needs get/set_setting."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else str(row[0])

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self._conn.commit()

    def set_settings_atomic(self, values: dict[str, str]) -> None:
        self._conn.executemany(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [(key, str(value)) for key, value in values.items()],
        )
        self._conn.commit()


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    public = {key: result.get(key) for key in _RESULT_KEYS if key in result}
    if public.get("last_error"):
        public["last_error"] = _safe_error(public["last_error"])
    if public.get("discovery_error"):
        public["discovery_error"] = _safe_error(public["discovery_error"])
    errors = result.get("group_errors")
    if isinstance(errors, dict):
        public["group_errors"] = {
            str(group)[:64]: _safe_error(err) for group, err in errors.items()
        }
    return public


def _seed_groups(db: SettingsDB, groups_file: str) -> None:
    path = Path(groups_file).expanduser()
    if not path.is_file():
        raise LabSyncError("IMA 组配置文件不存在")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LabSyncError("IMA 组配置不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise LabSyncError("IMA 组配置必须是数组")
    db.set_setting(IMA_PURE_GROUPS_KEY, json.dumps(payload, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--arm-middleware", dest="enable", action="store_true")
    ap.add_argument("--secrets", default=None)
    ap.add_argument(
        "--groups-file",
        default=os.environ.get("IMA_PURE_GROUPS_FILE", ""),
        help="生产导出的 ima_pure_groups JSON（仅在本地库还没有组时写入）",
    )
    ap.add_argument(
        "--db",
        default=os.environ.get("IMA_HOST_DB", "/data/vpush-ima-cache/ima-host.sqlite"),
    )
    ap.add_argument(
        "--index-root",
        default=os.environ.get("IMA_HOST_INDEX", "/data/vpush-ima-cache/ima-index"),
    )
    ap.add_argument("--staging-root", default=None)
    args = ap.parse_args(argv)

    if not middleware_enabled(args.enable):
        print(_DISABLED_HINT)
        return 0

    try:
        with arm_middleware_env(
            Path(args.staging_root).expanduser() if args.staging_root else None
        ) as staging:
            credentials = load_secrets(args.secrets)
            db = SettingsDB(Path(args.db).expanduser())
            db.set_setting(IMA_PURE_UID_KEY, credentials.uid)
            db.set_setting(IMA_PURE_REFRESH_TOKEN_KEY, credentials.refresh_token)
            if os.environ.get("IMA_KB_ID", "").strip():
                db.set_setting(IMA_PURE_KB_ID_KEY, os.environ["IMA_KB_ID"].strip())
            if os.environ.get("IMA_ROOT_FOLDER_ID", "").strip():
                db.set_setting(IMA_PURE_ROOT_FOLDER_KEY, os.environ["IMA_ROOT_FOLDER_ID"].strip())
            groups_file = str(args.groups_file or "").strip()
            if groups_file:
                _seed_groups(db, groups_file)
            service = ImaDocumentService(
                db,
                Path(args.index_root).expanduser(),
                archive_root=staging,
                storage_status=ImaStorageStatus(None, remote=False),
                # Seeded production state marks already-collected media complete
                # without the 118G archive on ARM. New listing hits still download.
                trust_index_state=True,
            )
            result = service.sync_once()
            print(json.dumps(_public_result(result), ensure_ascii=False))
            status = str(result.get("status") or "")
            if status in {"already_running", "not_configured"}:
                return 2
            if status != "finished":
                return 1
            return 1 if int(result.get("failed") or 0) else 0
    except LabSyncError as exc:
        print(exc)
        return 2
    except Exception as exc:
        print(f"IMA host sync 失败: {_safe_error(exc)}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
