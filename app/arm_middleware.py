"""ARM staging path helpers for IMA / CICC collectors.

Default-off. Activate only with ``VPUSH_ARM_MIDDLEWARE=1`` (or
``--arm-middleware`` on a CLI). Does not read IMA cookies or refresh tokens.
Does not write NFS / 115 / OpenList.
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ_BJ = timezone(timedelta(hours=8))
DEFAULT_ARM_STAGING_ROOT = "/data/vpush-ima-cache/staging"
DAY_DIR_RE = re.compile(r"^\d{4}$")
_SAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z_\-\u4e00-\u9fff().]+")


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def middleware_enabled(cli_flag: bool = False) -> bool:
    """中间层默认关；``--arm-middleware`` 或 ``VPUSH_ARM_MIDDLEWARE=1`` 才打开。"""
    return bool(cli_flag) or env_flag("VPUSH_ARM_MIDDLEWARE")


def resolve_staging_root(cli_value: str | None = None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    env = os.environ.get("VPUSH_ARM_STAGING_ROOT", "").strip()
    return Path(env or DEFAULT_ARM_STAGING_ROOT).expanduser()


def _safe_component(value: str, fallback: str = "unknown") -> str:
    cleaned = _SAFE_COMPONENT_RE.sub("_", str(value or "")).strip("._")
    return cleaned or fallback


def ima_group_slug(group_id: Any) -> str:
    """Staging group folder: ``legacy`` for empty/legacy ids, else sanitized id."""
    value = str(group_id or "").strip()
    if not value or value == "legacy" or value.startswith("legacy:"):
        return "legacy"
    return _safe_component(value, "legacy")


def _ts_datetime(ts_ms: Any) -> datetime | None:
    try:
        value = int(str(ts_ms).strip() or 0)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, TZ_BJ)
    except (OSError, OverflowError, ValueError):
        return None


def ima_date_parts(
    day: Any,
    ts_ms: Any = 0,
    *,
    now: datetime | None = None,
) -> tuple[str, str, str]:
    """IMA sort date / MMDD day folder → (YYYY, MM, DD); else Beijing ts/now.

    Prefer the IMA day folder (MMDD) plus year from media ``ts_ms`` (Beijing)
    or the current Beijing year. When MMDD is missing, use Beijing mtime/now
    (``ts_ms`` if valid, otherwise ``now``).
    """
    day_text = str(day or "").strip()
    if DAY_DIR_RE.fullmatch(day_text):
        created = _ts_datetime(ts_ms)
        year = created.strftime("%Y") if created else (now or datetime.now(TZ_BJ)).strftime("%Y")
        return year, day_text[:2], day_text[2:]
    created = _ts_datetime(ts_ms)
    stamp = created or now or datetime.now(TZ_BJ)
    return stamp.strftime("%Y"), stamp.strftime("%m"), stamp.strftime("%d")


def ima_staging_relpath(
    group_id: Any,
    filename: str,
    day: Any = "",
    ts_ms: Any = 0,
    *,
    now: datetime | None = None,
) -> Path:
    """``local/ima/<group>/YYYY/MM/DD/<filename>`` (relative to staging root)."""
    year, month, day_part = ima_date_parts(day, ts_ms, now=now)
    return Path("local") / "ima" / ima_group_slug(group_id) / year / month / day_part / filename


def ima_live_destination(
    record: dict[str, Any],
    *,
    staging_root: Path | None = None,
    filename: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Absolute live-write destination under ARM staging (no network, no secrets)."""
    root = staging_root if staging_root is not None else resolve_staging_root()
    name = filename if filename is not None else str(record.get("name") or "document.pdf")
    if not str(name).lower().endswith(".pdf"):
        name = f"{name}.pdf"
    relative = ima_staging_relpath(
        record.get("group_id"),
        name,
        record.get("day"),
        record.get("ts"),
        now=now,
    )
    return Path(root) / relative


def main(argv: list[str] | None = None) -> int:
    """Offline path printer. Does not download and does not read IMA credentials."""
    ap = argparse.ArgumentParser(
        description="Print IMA ARM staging destination (default-off; no download, no credentials)",
    )
    ap.add_argument(
        "--arm-middleware",
        action="store_true",
        help="启用中间层路径（或设 VPUSH_ARM_MIDDLEWARE=1）；默认关",
    )
    ap.add_argument(
        "--print-dest",
        action="store_true",
        help="打印 live 落盘路径（不写盘、不访问网络）",
    )
    ap.add_argument("--group", default="legacy", help="IMA group_id（默认 legacy）")
    ap.add_argument("--day", default="", help="IMA 日目录 MMDD；缺省则用北京时间 now")
    ap.add_argument("--name", default="document.pdf", help="安全文件名（调用方应已 sanitize）")
    ap.add_argument("--ts", default="", help="媒体创建时间毫秒（可选，用于补年份）")
    ap.add_argument(
        "--staging-root",
        default=None,
        help="ARM staging 根，默认 VPUSH_ARM_STAGING_ROOT 或 "
        f"{DEFAULT_ARM_STAGING_ROOT}",
    )
    args = ap.parse_args(argv)

    if not middleware_enabled(args.arm_middleware):
        print(
            "ARM middleware 未启用（需要 --arm-middleware 或 VPUSH_ARM_MIDDLEWARE=1）。"
            "未解析 live 落盘路径。"
        )
        return 0
    if not args.print_dest:
        print("已启用 ARM middleware。加 --print-dest 可打印 IMA live 落盘路径（不写盘）。")
        return 0

    dest = ima_live_destination(
        {"group_id": args.group, "day": args.day, "ts": args.ts, "name": args.name},
        staging_root=resolve_staging_root(args.staging_root),
    )
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
