#!/usr/bin/env python3
"""IMA 归档 → ARM staging 日期分片（remap only，默认关）。

本脚本只把已有归档树拷到 staging，不从 IMA 下载。
live 采集写 staging 走 ``app/ima_documents.py``（``VPUSH_ARM_MIDDLEWARE=1``
或 ``python3 -m app.arm_middleware --arm-middleware --print-dest``）。

ima_phone_sync 只换 Refresh Token，不落 PDF。旧 puller / 文档中心仍写：
  /srv/vpush-ima/<group>/<MMDD|unknown>/<title>__<token>.pdf
remap 到：
  $VPUSH_ARM_STAGING_ROOT/local/ima/<group>/YYYY/MM/DD/<filename>

默认什么都不做。须 --enable / --arm-middleware 或 VPUSH_ARM_MIDDLEWARE=1 才规划路径。
启用后默认 --dry-run，只打印将要复制的 src → dest，不写盘。
不读取 IMA Cookie / Refresh Token / ima_phone_sync.env。

用法：
  python3 ima_to_arm_staging.py
  python3 ima_to_arm_staging.py --enable --dry-run --source /path/to/ima-archive
  python3 ima_to_arm_staging.py --arm-middleware --dry-run --source /path/to/ima-archive
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ_BJ = timezone(timedelta(hours=8))
DEFAULT_SOURCE = "/srv/vpush-ima"
DEFAULT_STAGING_ROOT = "/data/vpush-ima-cache/staging"
DAY_DIR_RE = re.compile(r"^\d{4}$")
SKIP_DIR_NAMES = {"local", "failed", "hot", "manifest", "staging"}


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def middleware_enabled(cli_enable: bool = False) -> bool:
    return bool(cli_enable) or env_flag("VPUSH_ARM_MIDDLEWARE")


def resolve_staging_root(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value)
    env = os.environ.get("VPUSH_ARM_STAGING_ROOT", "").strip()
    return Path(env or DEFAULT_STAGING_ROOT)


def year_for(path: Path, year_override: str | None = None) -> str:
    if year_override:
        return year_override
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return datetime.now(TZ_BJ).strftime("%Y")
    return datetime.fromtimestamp(mtime, TZ_BJ).strftime("%Y")


def map_day_dir(name: str) -> tuple[str, str] | None:
    """MMDD → (MM, DD)；unknown → ('unknown', 'unknown')；其它跳过。"""
    if name == "unknown":
        return "unknown", "unknown"
    if DAY_DIR_RE.fullmatch(name):
        return name[:2], name[2:]
    return None


def staging_dest(staging_root: Path, group: str, year: str, month: str, day: str,
                 filename: str) -> Path:
    return staging_root / "local" / "ima" / group / year / month / day / filename


def plan_copies(source: Path, staging_root: Path, *, year: str | None = None) -> list[tuple[Path, Path]]:
    """扫描 IMA 归档，列出将 remap 到 staging 日期分片的 (src, dest)。不读凭据。"""
    planned: list[tuple[Path, Path]] = []
    if not source.is_dir():
        return planned
    for group_dir in sorted(source.iterdir()):
        if not group_dir.is_dir():
            continue
        if group_dir.name.startswith(".") or group_dir.name in SKIP_DIR_NAMES:
            continue
        for day_dir in sorted(group_dir.iterdir()):
            if not day_dir.is_dir() or day_dir.name.startswith("."):
                continue
            mapped = map_day_dir(day_dir.name)
            if mapped is None:
                continue
            month, day = mapped
            for pdf in sorted(day_dir.glob("*.pdf")):
                if pdf.name.startswith("."):
                    continue
                yyyy = year_for(pdf, year)
                dest = staging_dest(staging_root, group_dir.name, yyyy, month, day, pdf.name)
                planned.append((pdf, dest))
    return planned


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
    ap.add_argument("--enable", action="store_true",
                    help="启用 remap（或设 VPUSH_ARM_MIDDLEWARE=1）；默认关")
    ap.add_argument("--arm-middleware", dest="enable", action="store_true",
                    help="同 --enable（与中金 / IMA live 开关名对齐）；仍只 remap，不下载")
    ap.add_argument("--dry-run", action="store_true", default=None,
                    help="只列路径不复制（启用后的默认）")
    ap.add_argument("--apply", action="store_true",
                    help="真正复制/硬链；须同时 --enable")
    ap.add_argument("--source", default=None, help=f"IMA 归档根，默认 {DEFAULT_SOURCE}")
    ap.add_argument("--staging-root", default=None,
                    help="ARM staging 根，默认 VPUSH_ARM_STAGING_ROOT 或 "
                         f"{DEFAULT_STAGING_ROOT}")
    ap.add_argument("--year", default=None, help="固定年份（否则用文件 mtime 北京年）")
    args = ap.parse_args(argv)

    if not middleware_enabled(args.enable):
        print("ARM middleware 未启用（需要 --enable 或 VPUSH_ARM_MIDDLEWARE=1）。未复制任何文件。")
        return 0

    source = Path(args.source or DEFAULT_SOURCE)
    staging_root = resolve_staging_root(args.staging_root)
    dry_run = True if args.dry_run is None else args.dry_run
    if args.apply:
        dry_run = False

    planned = plan_copies(source, staging_root, year=args.year)
    if not planned:
        print(f"无待映射 PDF（source={source}）")
        return 0

    for src, dest in planned:
        if dry_run:
            print(f"WOULD COPY {src} → {dest}")
        else:
            action = apply_copy(src, dest)
            print(f"{action.upper()} {src} → {dest}")
    print(f"{'dry-run' if dry_run else 'apply'} {len(planned)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
