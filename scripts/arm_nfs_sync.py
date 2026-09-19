#!/usr/bin/env python3
"""ARM hot/staging → classic NFS layout (default-off, dry-run).

存储恢复后，把 ARM 日期分片映射回生产挂载用的旧 POSIX/NFS 布局：

  CICC: dest/local/cicc-research/<品类>/<MMDD>/...
        以及 .vpush-local-library.json / .vpush-local-meta.jsonl（若源侧有）
  IMA:  dest/<group_id>__<hash>/<MMDD>/...（legacy 则 dest/<MMDD>/）

默认什么都不做。须 ``--enable`` 或 ``VPUSH_ARM_NFS_SYNC=1`` 才规划路径。
本开关独立于 ``VPUSH_ARM_MIDDLEWARE``。启用后默认 dry-run；``--apply``
才硬链/拷贝。不读 IMA / 115 Cookie，不上传 115。

用法：
  python3 scripts/arm_nfs_sync.py
  python3 scripts/arm_nfs_sync.py --enable --dry-run --dest /mnt/vpush-ima
  VPUSH_ARM_NFS_SYNC=1 VPUSH_NFS_SYNC_DEST=/mnt/vpush-ima \\
    python3 scripts/arm_nfs_sync.py --apply --source /data/vpush-ima-cache/hot
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOURCE = "/data/vpush-ima-cache/hot"
CICC_MARKERS = (".vpush-local-library.json", ".vpush-local-meta.jsonl")
IMA_ROOT_MARKER = ".vpush-ima-root"
YEAR_RE = re.compile(r"^\d{4}$")
MONTH_DAY_RE = re.compile(r"^\d{2}$")
PDF_ID_RE = re.compile(r"_(\d+)\.pdf$", re.IGNORECASE)
GROUP_NS_RE = re.compile(r"^.+__[0-9a-f]{16}$")
_SAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z_\-\u4e00-\u9fff().]+")
_DISABLED_HINT = (
    "ARM NFS 兼容同步未启用（需要 --enable 或 VPUSH_ARM_NFS_SYNC=1）。"
    "未读取源目录、未写入。"
    "本开关独立于 VPUSH_ARM_MIDDLEWARE。"
    "不要在生产 compose 里设置 VPUSH_ARM_MIDDLEWARE=1 或 VPUSH_ARM_NFS_SYNC=1。"
    "用法见 scripts/arm_nfs_sync.md。"
)
_MISSING_DEST_HINT = (
    "缺少 --dest 或 VPUSH_NFS_SYNC_DEST（例如未来 NFS 挂载点）。未写入。"
)


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def nfs_sync_enabled(cli_enable: bool = False) -> bool:
    """NFS 同步默认关；独立于 VPUSH_ARM_MIDDLEWARE。"""
    return bool(cli_enable) or env_flag("VPUSH_ARM_NFS_SYNC")


def resolve_source(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    env = os.environ.get("VPUSH_NFS_SYNC_SOURCE", "").strip()
    return Path(env or DEFAULT_SOURCE).expanduser()


def resolve_dest(cli_value: str | None) -> Path | None:
    text = (cli_value or os.environ.get("VPUSH_NFS_SYNC_DEST", "")).strip()
    return Path(text).expanduser() if text else None


def _safe_component(value: str, fallback: str = "unknown") -> str:
    cleaned = _SAFE_COMPONENT_RE.sub("_", str(value or "")).strip("._")
    return cleaned or fallback


def is_legacy_ima_group(group_id: str) -> bool:
    value = str(group_id or "").strip()
    return not value or value == "legacy" or value.startswith("legacy:")


def ima_classic_group_dir(group_id: str) -> str | None:
    """Classic IMA archive folder: None for legacy (files under MMDD).

    Named groups match ``ImaDocumentStore._group_namespace``:
    ``<safe_id>__<sha256[:16]>``. If the ARM folder is already namespaced
    (remap of an old tree), keep it.
    """
    if is_legacy_ima_group(group_id):
        return None
    slug = _safe_component(group_id, "unknown")
    if GROUP_NS_RE.fullmatch(slug):
        return slug
    digest = hashlib.sha256(str(group_id).encode("utf-8")).hexdigest()[:16]
    return f"{slug}__{digest}"


def mmdd_from_parts(month: str, day: str) -> str:
    if MONTH_DAY_RE.fullmatch(month) and MONTH_DAY_RE.fullmatch(day):
        return f"{month}{day}"
    return "unknown"


def extract_cicc_id(filename: str) -> str:
    match = PDF_ID_RE.search(filename)
    return match.group(1) if match else ""


def load_jsonl_rows(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return rows
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "").strip()
        if rid:
            rows[rid] = row
    return rows


def _read_json_object(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def cicc_category_for(pdf: Path, jsonl_rows: dict[str, dict]) -> str:
    sidecar = _read_json_object(pdf.with_suffix(".json"))
    if sidecar:
        category = str(sidecar.get("category") or "").strip()
        if category:
            return category
    rid = extract_cicc_id(pdf.name)
    row = jsonl_rows.get(rid) if rid else None
    if row:
        category = str(row.get("category") or "").strip()
        if category:
            return category
    return ""


@dataclass(frozen=True)
class PlannedCopy:
    src: Path
    dest: Path
    kind: str = "file"  # file | marker


def _iter_date_shard_files(root: Path, pattern: str = "*.pdf") -> list[tuple[Path, str, str, str]]:
    """Yield (file, year, month, day) under ``root/YYYY/MM/DD/`` (unknown allowed)."""
    found: list[tuple[Path, str, str, str]] = []
    if not root.is_dir():
        return found
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or year_dir.name.startswith("."):
            continue
        year = year_dir.name if YEAR_RE.fullmatch(year_dir.name) else ""
        if year_dir.name == "unknown":
            year = "unknown"
        if not year:
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir() or month_dir.name.startswith("."):
                continue
            month = month_dir.name
            if not (MONTH_DAY_RE.fullmatch(month) or month == "unknown"):
                continue
            for day_dir in sorted(month_dir.iterdir()):
                if not day_dir.is_dir() or day_dir.name.startswith("."):
                    continue
                day = day_dir.name
                if not (MONTH_DAY_RE.fullmatch(day) or day == "unknown"):
                    continue
                for item in sorted(day_dir.glob(pattern)):
                    if item.is_file() and not item.name.startswith("."):
                        found.append((item, year, month, day))
    return found


def plan_cicc(source: Path, dest: Path) -> tuple[list[PlannedCopy], list[Path]]:
    planned: list[PlannedCopy] = []
    skipped: list[Path] = []
    cicc_src = source / "local" / "cicc-research"
    cicc_dest = dest / "local" / "cicc-research"
    jsonl_rows = load_jsonl_rows(cicc_src / ".vpush-local-meta.jsonl")
    for marker_name in CICC_MARKERS:
        marker = cicc_src / marker_name
        if marker.is_file():
            planned.append(PlannedCopy(marker, cicc_dest / marker_name, kind="marker"))
    for pdf, _year, month, day in _iter_date_shard_files(cicc_src):
        category = cicc_category_for(pdf, jsonl_rows)
        if not category:
            skipped.append(pdf)
            continue
        mmdd = mmdd_from_parts(month, day)
        dest_pdf = cicc_dest / _safe_component(category, "unknown") / mmdd / pdf.name
        planned.append(PlannedCopy(pdf, dest_pdf))
    return planned, skipped


def plan_ima(source: Path, dest: Path) -> list[PlannedCopy]:
    planned: list[PlannedCopy] = []
    ima_src = source / "local" / "ima"
    marker = source / IMA_ROOT_MARKER
    if marker.is_file():
        planned.append(PlannedCopy(marker, dest / IMA_ROOT_MARKER, kind="marker"))
    if not ima_src.is_dir():
        return planned
    for group_dir in sorted(ima_src.iterdir()):
        if not group_dir.is_dir() or group_dir.name.startswith("."):
            continue
        group_folder = ima_classic_group_dir(group_dir.name)
        for pdf, _year, month, day in _iter_date_shard_files(group_dir):
            mmdd = mmdd_from_parts(month, day)
            relative = Path(mmdd) / pdf.name
            if group_folder:
                relative = Path(group_folder) / relative
            planned.append(PlannedCopy(pdf, dest / relative))
            txt = pdf.with_suffix(".txt")
            if txt.is_file():
                planned.append(PlannedCopy(txt, dest / relative.with_suffix(".txt")))
    return planned


def plan_copies(source: Path, dest: Path) -> tuple[list[PlannedCopy], list[Path]]:
    cicc_planned, skipped = plan_cicc(source, dest)
    ima_planned = plan_ima(source, dest)
    return cicc_planned + ima_planned, skipped


def apply_copy(src: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return "exists"
    try:
        os.link(src, dest)
        return "link"
    except OSError:
        shutil.copy2(src, dest)
        return "copy"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--enable",
        action="store_true",
        help="启用 NFS 兼容同步（或设 VPUSH_ARM_NFS_SYNC=1）；默认关",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只列 src → dest，不写盘（启用后的默认）",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="真正硬链/拷贝；须同时启用",
    )
    ap.add_argument(
        "--source",
        default=None,
        help=f"ARM hot/staging 根，默认 {DEFAULT_SOURCE}",
    )
    ap.add_argument(
        "--dest",
        default=None,
        help="经典 NFS 根（或 VPUSH_NFS_SYNC_DEST）；启用后必填",
    )
    args = ap.parse_args(argv)

    if not nfs_sync_enabled(args.enable):
        print(_DISABLED_HINT)
        return 0

    dest = resolve_dest(args.dest)
    if dest is None:
        print(_MISSING_DEST_HINT)
        return 2

    source = resolve_source(args.source)
    dry_run = True
    if args.apply:
        dry_run = False
    if args.dry_run:
        dry_run = True

    planned, skipped = plan_copies(source, dest)
    for path in skipped:
        print(f"SKIP no-category {path}")
    if not planned:
        print(f"无待同步文件（source={source} dest={dest}）")
        return 0

    for item in planned:
        if dry_run:
            print(f"WOULD COPY {item.src} → {item.dest}")
        else:
            action = apply_copy(item.src, item.dest)
            print(f"{action.upper()} {item.src} → {item.dest}")
    print(f"{'dry-run' if dry_run else 'apply'} {len(planned)} 个文件（不上传 115）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
