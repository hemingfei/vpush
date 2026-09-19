#!/usr/bin/env python3
"""Lab-only CICC → ARM staging incremental sync (default-off).

Oracle-SJ-ARM 限量采集入口。默认什么都不做。须 ``--enable`` /
``--arm-middleware`` 或 ``VPUSH_ARM_MIDDLEWARE=1`` 才列出或下载。

启用后默认 dry-run：只列 id / title / dest，不下载。
``--apply`` 才取 PDF。落盘走 ``cicc_report_collector.target_path``
（中间层打开后为 ``$VPUSH_ARM_STAGING_ROOT/local/cicc-research/YYYY/MM/DD/``）。

Cookie：``--cookie-file`` 或 ``VPUSH_CICC_COOKIE_FILE``（默认
``/root/cicc/cookies.txt``）。从不打印 Cookie 值。配额/熔断沿用采集器
``Session`` / ``write_paused``（400013 / 40010），不另开旁路。
上传 115 仍由 puller_loop 负责；不要把 ``VPUSH_ARM_MIDDLEWARE=1``
写进生产 compose。

用法：
  python3 scripts/cicc_arm_lab_sync.py
  python3 scripts/cicc_arm_lab_sync.py --enable --dry-run --limit 3 --days 7
  python3 scripts/cicc_arm_lab_sync.py --arm-middleware --apply --limit 3
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.arm_middleware import middleware_enabled, resolve_staging_root
from scripts import cicc_report_collector as cicc

DEFAULT_LIMIT = 3
MAX_LIMIT = 20
DEFAULT_DAYS = 7
_DISABLED_HINT = (
    "CICC → ARM lab sync 未启用（需要 --enable / --arm-middleware 或 "
    "VPUSH_ARM_MIDDLEWARE=1）。未列出、未下载。实验室用法见 "
    "scripts/cicc_arm_lab_sync.md。不要在生产 compose 里设置 VPUSH_ARM_MIDDLEWARE=1。"
)
_COOKIE_LINE_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])(set-cookie|cookie)(\s*[:=]\s*)[^\r\n]*"
)


class LabSyncError(RuntimeError):
    """User-facing lab sync error; never include cookie values."""


@dataclass(frozen=True)
class PlannedItem:
    rid: str
    title: str
    dest: Path
    category: str
    publish_time: str
    item: dict[str, Any]


def activate_arm_middleware(staging_root: Path | None = None) -> Path:
    """Force live staging write so target_path uses the ARM date-shard layout."""
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


def _safe_error(exc: BaseException) -> str:
    text = (str(exc).splitlines() or [""])[0]
    return _COOKIE_LINE_RE.sub(r"\1\2<redacted>", text)


def require_cookie_mode(path: Path) -> None:
    """Reject group/other-readable cookie files (same bar as IMA load_secrets)."""
    try:
        mode = path.stat().st_mode & 0o777
    except OSError as exc:
        raise LabSyncError("Cookie 文件无法读取") from exc
    if mode & 0o077:
        raise LabSyncError("Cookie 文件权限必须为 0600")


def clamp_limit(value: int) -> int:
    return max(0, min(int(value), MAX_LIMIT))


def date_window(days: int, *, today: date | None = None) -> tuple[str | None, str]:
    """Mirror collector ``--days``: inclusive window ending today (Beijing calendar via date.today)."""
    end = (today or date.today()).strftime("%Y-%m-%d")
    span = max(0, int(days))
    if span <= 0:
        return None, end
    start = ((today or date.today()) - timedelta(days=span - 1)).strftime("%Y-%m-%d")
    return start, end


def plan_item(item: dict[str, Any], *, root: Path, category: str) -> PlannedItem | None:
    rid = item.get("id")
    if rid is None or isinstance(rid, bool):
        return None
    title = str(item.get("title") or "")
    publish = str(item.get("publishTime") or "")
    dest = cicc.target_path(root, category, publish, title, rid, middleware=True)
    return PlannedItem(
        rid=str(rid),
        title=title,
        dest=dest,
        category=category,
        publish_time=publish,
        item=item,
    )


def collect_lab_records(
    sess: Any,
    categories: list[dict[str, Any]],
    *,
    days: int = DEFAULT_DAYS,
    limit: int = DEFAULT_LIMIT,
    keywords: list[str] | None = None,
    list_page_fn: Callable[..., dict] | None = None,
    today: date | None = None,
) -> list[PlannedItem]:
    """Limited listing: first N reports in the ``--days`` window, ARM staging dests."""
    limit = clamp_limit(limit)
    if limit == 0:
        return []
    start, end = date_window(days, today=today)
    list_page = list_page_fn or cicc.list_page
    root = cicc.resolve_output_root(None, middleware=True)
    planned: list[PlannedItem] = []
    kw = list(keywords or [])
    for cat in categories:
        name = str(cat.get("name") or "")
        cat_id = cat.get("id")
        page = 1
        while len(planned) < limit:
            data = list_page(sess, cat_id, page, start, end)
            page_items = list((data or {}).get("content") or [])
            items = cicc.filter_by_keywords(page_items, kw)
            for it in items:
                if not isinstance(it, dict):
                    continue
                row = plan_item(it, root=root, category=name)
                if row is None:
                    continue
                planned.append(row)
                if len(planned) >= limit:
                    break
            if not page_items or len(page_items) < cicc.PAGE_SIZE or page >= cicc.MAX_PAGES:
                break
            page += 1
        if len(planned) >= limit:
            break
    return planned[:limit]


def apply_planned(
    sess: Any,
    planned: list[PlannedItem],
    *,
    download_fn: Callable[[Any, int], bytes] | None = None,
    id_name: dict | None = None,
) -> dict[str, int]:
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    fetch = download_fn or cicc.viewer_pdf
    names = id_name or {}
    for item in planned:
        if item.dest.is_file():
            print(f"SKIP exists id={item.rid} dest={item.dest}")
            stats["skipped"] += 1
            continue
        try:
            payload = cicc.strip_watermark(fetch(sess, int(item.rid)))
            cicc.prepare_target_dir(item.dest.parent, fix_owner=False)
            item.dest.write_bytes(payload)
            row = cicc.sidecar_row(item.item, names, item.category)
            if row.get("id"):
                cicc.write_arm_item_sidecar(item.dest, row, item.category)
            print(f"SYNC id={item.rid} title={item.title} dest={item.dest}")
            stats["downloaded"] += 1
        except SystemExit:
            raise
        except Exception as exc:
            print(f"FAIL id={item.rid} error={_safe_error(exc)}")
            stats["failed"] += 1
    return stats


def _print_planned(planned: list[PlannedItem], *, dry_run: bool) -> None:
    prefix = "WOULD SYNC" if dry_run else "PLAN"
    for item in planned:
        print(f"{prefix} id={item.rid} title={item.title} dest={item.dest}")
    kind = "dry-run" if dry_run else "planned"
    print(f"{kind} {len(planned)} 个文件（lab limit；115 仍由 puller_loop 上传）")


def _load_categories(
    sess: Any,
    wanted: list[str],
    *,
    fetch_param_fn: Callable[[Any], dict] | None = None,
) -> tuple[list[dict[str, Any]], dict]:
    param = (fetch_param_fn or cicc.fetch_param)(sess)
    all_cats = list(param.get("treeData") or [])
    id_name = cicc.category_id_names(param)
    if wanted:
        cats = [c for c in all_cats if c.get("name") in wanted]
        missing = set(wanted) - {c.get("name") for c in cats}
        if missing:
            raise LabSyncError(f"未知品类: {sorted(missing)}")
        return cats, id_name
    return all_cats, id_name


def main(
    argv: list[str] | None = None,
    *,
    session_factory: Callable[[], Any] | None = None,
    list_page_fn: Callable[..., dict] | None = None,
    fetch_param_fn: Callable[[Any], dict] | None = None,
    download_fn: Callable[[Any, int], bytes] | None = None,
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
        help="只列 id / title / dest，不下载（启用后的默认）",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="真正取 PDF 落盘 staging；须同时启用",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"最多处理 N 篇（默认 {DEFAULT_LIMIT}，上限 {MAX_LIMIT}）",
    )
    ap.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"最近 N 天（含今天，默认 {DEFAULT_DAYS}）；0=不限",
    )
    ap.add_argument("--categories", default="", help="逗号分隔的一级品类名，默认全部")
    ap.add_argument("--keywords", default="", help="逗号分隔的标题关键词白名单")
    ap.add_argument(
        "--cookie-file",
        default=None,
        help="Cookie 文件（默认 /root/cicc/cookies.txt；可用 VPUSH_CICC_COOKIE_FILE 覆盖）",
    )
    ap.add_argument(
        "--staging-root",
        default=None,
        help="ARM staging 根，默认 VPUSH_ARM_STAGING_ROOT 或 /data/vpush-ima-cache/staging",
    )
    ap.add_argument(
        "--endpoint",
        choices=["viewer", "download"],
        default="viewer",
        help="取 PDF：viewer=fetchPdf（默认，不计月度配额）；download=计 300/月。熔断不绕过",
    )
    args = ap.parse_args(argv)

    if not middleware_enabled(args.enable):
        print(_DISABLED_HINT)
        return 0

    dry_run = True
    if args.apply:
        dry_run = False
    if args.dry_run:
        dry_run = True

    staging_root = Path(args.staging_root).expanduser() if args.staging_root else None
    wanted = [c.strip() for c in (args.categories or "").split(",") if c.strip()]
    keywords = [k.strip() for k in (args.keywords or "").split(",") if k.strip()]

    try:
        with arm_middleware_env(staging_root):
            if session_factory is None:
                cookie_path = cicc.resolve_cookie_file(args.cookie_file)
                if not cookie_path.exists():
                    print(f"Cookie 文件不存在: {cookie_path}")
                    return 2
                require_cookie_mode(cookie_path)
                sess = cicc.Session(cookie_path.read_text(encoding="utf-8"))
            else:
                sess = session_factory()
            cats, id_name = _load_categories(sess, wanted, fetch_param_fn=fetch_param_fn)
            planned = collect_lab_records(
                sess,
                cats,
                days=args.days,
                limit=args.limit,
                keywords=keywords,
                list_page_fn=list_page_fn,
            )
            if not planned:
                print(f"无待同步研报（days={args.days} limit={clamp_limit(args.limit)}）")
                return 0
            if dry_run:
                _print_planned(planned, dry_run=True)
                return 0
            _print_planned(planned, dry_run=False)
            fetch = download_fn
            if fetch is None:
                fetch = cicc.download_pdf if args.endpoint == "download" else cicc.viewer_pdf
            stats = apply_planned(sess, planned, download_fn=fetch, id_name=id_name)
            print(
                f"apply downloaded={stats['downloaded']} skipped={stats['skipped']} "
                f"failed={stats['failed']}（115 仍由 puller_loop 上传）"
            )
            return 1 if stats["failed"] else 0
    except LabSyncError as exc:
        print(_safe_error(exc))
        return 2
    except SystemExit:
        raise
    except Exception as exc:
        print(f"lab sync 失败: {_safe_error(exc)}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
