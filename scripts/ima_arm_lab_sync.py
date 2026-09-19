#!/usr/bin/env python3
"""Lab-only IMA → ARM staging incremental sync (default-off).

Oracle-SJ-ARM 限量采集入口。默认什么都不做。须 ``--enable`` /
``--arm-middleware`` 或 ``VPUSH_ARM_MIDDLEWARE=1`` 才列出或下载。

启用后默认 dry-run：只列 media_id / title / dest，不下载。
``--apply`` 才 get_media + download。落盘走 ``ImaDocumentStore.pdf_path``
（中间层打开后为 ``$VPUSH_ARM_STAGING_ROOT/local/ima/<group>/YYYY/MM/DD/``）。

凭据：``IMA_UID`` + ``IMA_REFRESH_TOKEN``，或 ``--secrets`` /
``IMA_PURE_SECRETS_FILE``（``{"uid","refresh_token"}``，权限 0600）。
从不打印 token。上传 115 仍由 puller_loop 负责；不要把
``VPUSH_ARM_MIDDLEWARE=1`` 写进生产 compose。

用法：
  python3 scripts/ima_arm_lab_sync.py
  python3 scripts/ima_arm_lab_sync.py --enable --dry-run --group legacy --limit 3
  python3 scripts/ima_arm_lab_sync.py --arm-middleware --apply --group legacy --secrets /root/ima-secrets.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.arm_middleware import middleware_enabled, resolve_staging_root
from app.fetchers.base import CN_TZ
from app.ima_documents import (
    IMA_LEGACY_GROUP_ID,
    IMA_LEGACY_GROUP_NAME,
    IMA_PURE_KB_ID_DEFAULT,
    IMA_PURE_ROOT_FOLDER_DEFAULT,
    ImaDocumentConfig,
    ImaDocumentStore,
    ImaGroupConfig,
    ImaPureClient,
    _optional_int,
    _safe_error,
    ima_folder_id,
    ima_folder_name,
    ima_month_folder_key,
    is_ima_folder_item,
    item_display_name,
)

DEFAULT_LIMIT = 3
MAX_LIMIT = 20
DAY_DIR_RE = re.compile(r"^\d{4}$")
_UID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_MAX_REFRESH_TOKEN_LENGTH = 4096
_DISABLED_HINT = (
    "IMA → ARM lab sync 未启用（需要 --enable / --arm-middleware 或 "
    "VPUSH_ARM_MIDDLEWARE=1）。未列出、未下载。实验室用法见 "
    "scripts/ima_arm_lab_sync.md。不要在生产 compose 里设置 VPUSH_ARM_MIDDLEWARE=1。"
)


class LabSyncError(RuntimeError):
    """User-facing lab sync error; never include token values."""


@dataclass(frozen=True)
class ImaLabCredentials:
    uid: str
    refresh_token: str


@dataclass(frozen=True)
class FolderRef:
    folder_id: str
    name: str


@dataclass(frozen=True)
class PlannedItem:
    media_id: str
    title: str
    dest: Path
    day: str
    group_id: str
    size: int
    ts: str


def activate_arm_middleware(staging_root: Path | None = None) -> Path:
    """Force live staging write so pdf_path / download use the ARM layout."""
    os.environ["VPUSH_ARM_MIDDLEWARE"] = "1"
    if staging_root is not None:
        os.environ["VPUSH_ARM_STAGING_ROOT"] = str(Path(staging_root).expanduser())
    return resolve_staging_root()


@contextmanager
def arm_middleware_env(staging_root: Path | None = None) -> Iterator[Path]:
    """Set middleware env for the call, then restore so lab runs do not leak flags."""
    old_flag = os.environ.get("VPUSH_ARM_MIDDLEWARE")
    old_root = os.environ.get("VPUSH_ARM_STAGING_ROOT")
    touched_root = staging_root is not None
    try:
        yield activate_arm_middleware(staging_root)
    finally:
        if old_flag is None:
            os.environ.pop("VPUSH_ARM_MIDDLEWARE", None)
        else:
            os.environ["VPUSH_ARM_MIDDLEWARE"] = old_flag
        if touched_root:
            if old_root is None:
                os.environ.pop("VPUSH_ARM_STAGING_ROOT", None)
            else:
                os.environ["VPUSH_ARM_STAGING_ROOT"] = old_root


def _validate_uid(value: Any) -> str:
    uid = str(value or "").strip()
    if not _UID_RE.fullmatch(uid):
        raise LabSyncError("IMA UID 格式无效")
    return uid


def _validate_refresh_token(value: Any) -> str:
    token = str(value or "")
    if not token or len(token) > _MAX_REFRESH_TOKEN_LENGTH:
        raise LabSyncError("IMA Refresh Token 无效")
    if any(ord(char) < 32 or ord(char) == 127 for char in token):
        raise LabSyncError("IMA Refresh Token 无效")
    return token


def load_secrets(secrets_path: str | Path | None = None) -> ImaLabCredentials:
    """Read uid + refresh_token from env and/or a 0600 JSON file. Never log values."""
    env_uid = os.environ.get("IMA_UID", "").strip()
    env_token = os.environ.get("IMA_REFRESH_TOKEN", "").strip()
    path_text = str(secrets_path or "").strip() or os.environ.get("IMA_PURE_SECRETS_FILE", "").strip()
    file_uid = ""
    file_token = ""
    if path_text:
        target = Path(path_text).expanduser()
        try:
            mode = target.stat().st_mode & 0o777
        except OSError as exc:
            raise LabSyncError("secrets 文件无法读取") from exc
        if mode & 0o077:
            raise LabSyncError("secrets 文件权限必须为 0600")
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LabSyncError("secrets 文件不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise LabSyncError("secrets 文件必须是 {\"uid\",\"refresh_token\"} 对象")
        file_uid = str(payload.get("uid") or "").strip()
        file_token = str(payload.get("refresh_token") or "")
    uid = env_uid or file_uid
    token = env_token or file_token
    if not uid or not token:
        raise LabSyncError(
            "缺少 IMA 凭据（IMA_UID+IMA_REFRESH_TOKEN 或 --secrets / IMA_PURE_SECRETS_FILE）"
        )
    return ImaLabCredentials(uid=_validate_uid(uid), refresh_token=_validate_refresh_token(token))


def build_group_and_config(
    credentials: ImaLabCredentials,
    group_id: str,
    *,
    knowledge_base_id: str = "",
    root_folder_id: str = "",
) -> tuple[ImaDocumentConfig, ImaGroupConfig]:
    raw_group = str(group_id or "").strip() or IMA_LEGACY_GROUP_ID
    kb = str(knowledge_base_id or os.environ.get("IMA_KB_ID", "") or "").strip()
    root = str(root_folder_id or os.environ.get("IMA_ROOT_FOLDER_ID", "") or "").strip()
    if raw_group == IMA_LEGACY_GROUP_ID or raw_group.startswith("legacy:"):
        gid = IMA_LEGACY_GROUP_ID
        name = IMA_LEGACY_GROUP_NAME
        kb = kb or IMA_PURE_KB_ID_DEFAULT
        root = root or IMA_PURE_ROOT_FOLDER_DEFAULT
    else:
        gid = raw_group
        name = raw_group
        kb = kb or raw_group
        root = root or kb
    group = ImaGroupConfig(
        id=gid,
        name=name,
        knowledge_base_id=kb,
        root_folder_id=root,
    )
    config = ImaDocumentConfig(
        uid=credentials.uid,
        refresh_token=credentials.refresh_token,
        knowledge_base_id=kb,
        root_folder_id=root,
        groups=(group,),
    )
    return config, group


def folder_refs(items: list[dict[str, Any]]) -> list[FolderRef]:
    refs: list[FolderRef] = []
    for item in items:
        if not is_ima_folder_item(item):
            continue
        folder_id = ima_folder_id(item)
        if not folder_id:
            continue
        refs.append(FolderRef(folder_id, ima_folder_name(item, folder_id)))
    return refs


def pick_newest_month(folders: list[FolderRef]) -> FolderRef | None:
    keyed = [(ima_month_folder_key(folder.name), folder) for folder in folders]
    ranked = [(key, folder) for key, folder in keyed if key is not None]
    if not ranked:
        return None
    return max(ranked, key=lambda item: item[0])[1]


def pick_day_folder(folders: list[FolderRef], day: str = "") -> FolderRef | None:
    matches = [
        folder
        for folder in folders
        if DAY_DIR_RE.fullmatch(folder.name) and (not day or folder.name == day)
    ]
    if not matches:
        return None
    return max(matches, key=lambda folder: folder.name)


def pick_month_for_day(folders: list[FolderRef], day: str) -> FolderRef | None:
    """Prefer the newest year-month folder whose MM matches ``day`` (MMDD)."""
    if not DAY_DIR_RE.fullmatch(day):
        return None
    month = int(day[:2])
    ranked: list[tuple[tuple[int, int], FolderRef]] = []
    for folder in folders:
        key = ima_month_folder_key(folder.name)
        if key is not None and key[1] == month:
            ranked.append((key, folder))
    if not ranked:
        return None
    return max(ranked, key=lambda item: item[0])[1]


def select_descend_folders(folders: list[FolderRef], *, day: str = "") -> list[FolderRef]:
    """Newest-month then newest/matching MMDD, same signals as ImaPureClient listing."""
    month = pick_newest_month(folders)
    day_folder = pick_day_folder(folders, day)
    if day:
        if day_folder:
            return [day_folder]
        month_for_day = pick_month_for_day(folders, day)
        if month_for_day:
            return [month_for_day]
        return [month] if month else []
    if month:
        return [month]
    return [day_folder] if day_folder else []


def record_from_list_item(
    item: dict[str, Any],
    *,
    group: ImaGroupConfig,
    folder_path: list[str],
) -> dict[str, Any] | None:
    """Mirror ImaPureClient.manifest PDF filtering / day extraction (no extra layout)."""
    if is_ima_folder_item(item):
        return None
    media_type = item.get("media_type")
    if media_type is not None and (isinstance(media_type, bool) or not isinstance(media_type, int)):
        return None
    if media_type == 99:
        return None
    media_id_value = item.get("media_id")
    if not isinstance(media_id_value, str) or not media_id_value.strip():
        return None
    try:
        media_id = ImaDocumentStore.validate_media_id(media_id_value.strip())
    except ValueError:
        return None
    file_size = _optional_int(item.get("file_size"))
    if file_size is None:
        return None
    ts_value = item.get("create_time")
    try:
        ts_ms = int(ts_value) if not isinstance(ts_value, bool) else 0
    except (TypeError, ValueError, OverflowError):
        ts_ms = 0
    name = item_display_name(item, media_id)
    if not (name.lower().endswith(".pdf") or media_id.lower().startswith("pdf_")):
        return None
    day = next((value for value in reversed(folder_path) if DAY_DIR_RE.fullmatch(value)), "")
    if not day and ts_ms > 0:
        try:
            day = datetime.fromtimestamp(ts_ms / 1000, CN_TZ).strftime("%m%d")
        except (OSError, OverflowError, ValueError):
            day = ""
    return {
        "media_id": media_id,
        "name": name,
        "day": day or "unknown",
        "size": file_size or 0,
        "ts": str(ts_ms) if ts_ms > 0 else "",
        "group_id": group.id,
        "group_name": group.name,
        "folder_path": list(folder_path),
    }


def _records_from_items(
    items: list[dict[str, Any]],
    *,
    group: ImaGroupConfig,
    folder_path: list[str],
    day: str = "",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in items:
        record = record_from_list_item(item, group=group, folder_path=folder_path)
        if record is None:
            continue
        if day and record.get("day") != day:
            continue
        records.append(record)
    return records


def _list_items(client: Any, folder_id: str, *, folders_only: bool = False) -> list[dict[str, Any]]:
    return list(client.list_items(folder_id, folders_only=folders_only) or [])


def collect_lab_records(
    client: Any,
    group: ImaGroupConfig,
    *,
    day: str = "",
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Limited listing: newest month/day folders (or ``--day`` MMDD), then first N PDFs."""
    day = str(day or "").strip()
    if day and not DAY_DIR_RE.fullmatch(day):
        raise LabSyncError("--day 必须是 MMDD（四位数字）")
    limit = max(0, min(int(limit), MAX_LIMIT))
    if limit == 0:
        return []

    mount_ids = [folder_id for folder_id in group.mount_folder_ids if folder_id]
    kb = (group.knowledge_base_id or "").strip()
    start_id = mount_ids[0] if mount_ids else kb
    if not start_id:
        return []

    start_path: list[str] = []
    items = _list_items(client, start_id)
    folders = folder_refs(items)

    if kb and start_id != kb:
        try:
            siblings = _list_items(client, kb, folders_only=True)
        except Exception:
            siblings = []
        sibling_folders = folder_refs(siblings)
        target_month = pick_month_for_day(sibling_folders, day) if day else pick_newest_month(sibling_folders)
        if target_month is not None:
            start_id = target_month.folder_id
            start_path = [target_month.name]
            items = _list_items(client, start_id)
            folders = folder_refs(items)

    records = _records_from_items(items, group=group, folder_path=start_path, day=day)
    if len(records) >= limit and not select_descend_folders(folders, day=day):
        return records[:limit]

    for target in select_descend_folders(folders, day=day):
        child_path = start_path + [target.name]
        child_items = _list_items(client, target.folder_id)
        records.extend(_records_from_items(child_items, group=group, folder_path=child_path, day=day))
        child_folders = folder_refs(child_items)
        for nested in select_descend_folders(child_folders, day=day):
            if ima_month_folder_key(nested.name) and ima_month_folder_key(target.name):
                continue
            nested_path = child_path + [nested.name]
            nested_items = _list_items(client, nested.folder_id)
            records.extend(
                _records_from_items(nested_items, group=group, folder_path=nested_path, day=day)
            )
        if len(records) >= limit:
            break
    return records[:limit]


def plan_items(
    records: list[dict[str, Any]],
    store: ImaDocumentStore,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[PlannedItem]:
    """Map listed records to ``ImaDocumentStore.pdf_path`` destinations (staging when on)."""
    planned: list[PlannedItem] = []
    occupied: set[str] = set()
    for record in records[: max(0, min(int(limit), MAX_LIMIT))]:
        dest = store.pdf_path(record, occupied=occupied)
        occupied.add(store.archive_relative(dest))
        planned.append(
            PlannedItem(
                media_id=str(record.get("media_id") or ""),
                title=str(record.get("name") or ""),
                dest=dest,
                day=str(record.get("day") or ""),
                group_id=str(record.get("group_id") or IMA_LEGACY_GROUP_ID),
                size=int(record.get("size") or 0),
                ts=str(record.get("ts") or ""),
            )
        )
    return planned


def apply_planned(client: Any, planned: list[PlannedItem]) -> dict[str, int]:
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    for item in planned:
        if item.dest.is_file():
            print(f"SKIP exists media_id={item.media_id} dest={item.dest}")
            stats["skipped"] += 1
            continue
        try:
            media = client.get_media(item.media_id)
            result = client.download(media, item.dest, int(item.size or 0))
            size = int((result or {}).get("size") or item.size or 0)
            print(f"SYNC media_id={item.media_id} title={item.title} dest={item.dest} size={size}")
            stats["downloaded"] += 1
        except Exception as exc:
            print(f"FAIL media_id={item.media_id} error={_safe_error(exc)}")
            stats["failed"] += 1
    return stats


def _print_planned(planned: list[PlannedItem], *, dry_run: bool) -> None:
    prefix = "WOULD SYNC" if dry_run else "PLAN"
    for item in planned:
        print(
            f"{prefix} media_id={item.media_id} title={item.title} dest={item.dest}"
        )
    kind = "dry-run" if dry_run else "planned"
    print(f"{kind} {len(planned)} 个文件（lab limit；115 仍由 puller_loop 上传）")


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[ImaDocumentConfig, ImaGroupConfig], Any] | None = None,
    store_factory: Callable[[Path], ImaDocumentStore] | None = None,
) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--enable",
        action="store_true",
        help="启用实验室同步（或设 VPUSH_ARM_MIDDLEWARE=1）；默认关",
    )
    ap.add_argument(
        "--arm-middleware",
        dest="enable",
        action="store_true",
        help="同 --enable（打开 ARM staging 写入）",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只列 media_id / title / dest，不下载（启用后的默认）",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="真正 get_media + download；须同时启用",
    )
    ap.add_argument("--group", default=IMA_LEGACY_GROUP_ID, help="IMA group id 或 legacy（默认）")
    ap.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"最多处理 N 篇（默认 {DEFAULT_LIMIT}，上限 {MAX_LIMIT}）",
    )
    ap.add_argument("--day", default="", help="只要该 IMA 日目录 MMDD；缺省则取最新月/日文件夹")
    ap.add_argument(
        "--secrets",
        default=None,
        help="JSON 凭据文件 {\"uid\",\"refresh_token\"}（或 IMA_PURE_SECRETS_FILE）；须 0600",
    )
    ap.add_argument(
        "--staging-root",
        default=None,
        help="ARM staging 根，默认 VPUSH_ARM_STAGING_ROOT 或 /data/vpush-ima-cache/staging",
    )
    ap.add_argument(
        "--index-root",
        default=None,
        help="ImaDocumentStore 索引目录（默认临时目录；PDF 仍写 staging）",
    )
    args = ap.parse_args(argv)

    if not middleware_enabled(args.enable):
        print(_DISABLED_HINT)
        return 0

    day = str(args.day or "").strip()
    if day and not DAY_DIR_RE.fullmatch(day):
        print("--day 必须是 MMDD（四位数字）")
        return 2

    dry_run = True
    if args.apply:
        dry_run = False
    if args.dry_run:
        dry_run = True

    staging_root = Path(args.staging_root).expanduser() if args.staging_root else None
    try:
        with arm_middleware_env(staging_root):
            credentials = load_secrets(args.secrets)
            config, group = build_group_and_config(credentials, args.group)
            index_root = (
                Path(args.index_root).expanduser()
                if args.index_root
                else Path(tempfile.mkdtemp(prefix="ima-arm-lab-"))
            )
            store = (store_factory or ImaDocumentStore)(index_root)
            factory = client_factory or (lambda cfg, grp: ImaPureClient(cfg, group=grp))
            client = factory(config, group)
            records = collect_lab_records(client, group, day=day, limit=args.limit)
            planned = plan_items(records, store, limit=args.limit)
            if not planned:
                print(f"无待同步 PDF（group={group.id} day={day or 'newest'}）")
                return 0
            if dry_run:
                _print_planned(planned, dry_run=True)
                return 0
            _print_planned(planned, dry_run=False)
            stats = apply_planned(client, planned)
            print(
                f"apply downloaded={stats['downloaded']} skipped={stats['skipped']} "
                f"failed={stats['failed']}（115 仍由 puller_loop 上传）"
            )
            return 1 if stats["failed"] else 0
    except LabSyncError as exc:
        print(exc)
        return 2
    except Exception as exc:
        print(f"lab sync 失败: {_safe_error(exc)}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
