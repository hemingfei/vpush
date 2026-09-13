#!/usr/bin/env python3
"""Measure and gate the IMA document first-load database queries."""
from __future__ import annotations

import argparse
import logging
import math
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import DB  # noqa: E402


class ProbeError(RuntimeError):
    """A validation or performance gate failed."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gate IMA first-load list and facets DB query performance."
    )
    parser.add_argument("--db", required=True, metavar="PATH", help="SQLite database path")
    parser.add_argument(
        "--groups",
        nargs="+",
        metavar="GROUP",
        help="Authorized group IDs; defaults to every non-empty indexed group",
    )
    parser.add_argument("--runs", type=int, default=3, help="Measured runs per query (default: 3)")
    parser.add_argument(
        "--list-budget-ms",
        type=float,
        default=150.0,
        metavar="MS",
        help="Maximum list median in milliseconds (default: 150)",
    )
    parser.add_argument(
        "--facets-budget-ms",
        type=float,
        default=200.0,
        metavar="MS",
        help="Maximum facets median in milliseconds (default: 200)",
    )
    parser.add_argument(
        "--hard-request-ceiling-ms",
        type=float,
        default=500.0,
        metavar="MS",
        help="Maximum individual measured request in milliseconds (default: 500)",
    )
    return parser


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    for name in ("list_budget_ms", "facets_budget_ms", "hard_request_ceiling_ms"):
        value = getattr(args, name)
        if not math.isfinite(value) or value < 0:
            parser.error(f"--{name.replace('_', '-')} must be a finite non-negative number")


def _readonly_backup(source: Path, target: Path) -> None:
    """Take a consistent read-only snapshot without opening the source through DB."""
    uri = source.resolve().as_uri() + "?mode=ro"
    source_conn = sqlite3.connect(uri, uri=True)
    target_conn = sqlite3.connect(str(target))
    try:
        source_conn.backup(target_conn)
        target_conn.commit()
    finally:
        target_conn.close()
        source_conn.close()


def _group_ids(db: DB) -> list[str]:
    rows = db._read_only_rows(
        "SELECT DISTINCT group_id FROM ima_document_index "
        "WHERE TRIM(COALESCE(group_id, '')) <> '' ORDER BY group_id"
    )
    return [str(row["group_id"]) for row in rows]


def _requested_groups(db: DB, requested: list[str] | None) -> tuple[list[str], list[str]]:
    available = _group_ids(db)
    if not available:
        raise ProbeError("no group data found in ima_document_index")
    if requested is None:
        return available, available
    groups = list(dict.fromkeys(str(group).strip() for group in requested))
    if any(not group for group in groups):
        raise ProbeError("--groups cannot contain an empty group ID")
    unknown = [group for group in groups if group not in set(available)]
    if unknown:
        raise ProbeError("requested group data not found: " + ", ".join(unknown))
    return available, groups


def _time_call(call) -> float:
    started = time.perf_counter_ns()
    call()
    return (time.perf_counter_ns() - started) / 1_000_000.0


def _measure(db: DB, groups: list[str], runs: int) -> tuple[list[float], list[float]]:
    db.ima_document_page(groups, limit=50, offset=0, facets=False)
    db.ima_document_page(groups, limit=50, offset=0, facets=True)
    list_times = [
        _time_call(
            lambda: db.ima_document_page(
                groups, limit=50, offset=0, facets=False
            )
        )
        for _ in range(runs)
    ]
    facets_times = [
        _time_call(
            lambda: db.ima_document_page(groups, limit=50, offset=0, facets=True)
        )
        for _ in range(runs)
    ]
    return list_times, facets_times


def _capture_default_plan(db: DB, groups: list[str]) -> list[str]:
    captured: list[tuple[str, tuple[object, ...]]] = []
    original = db._read_only_rows

    def capture(sql, params=()):
        if "FROM ima_document_index d" in sql and "LIMIT ? OFFSET ?" in sql:
            captured.append((sql, tuple(params)))
        return original(sql, params)

    db._read_only_rows = capture
    try:
        db.ima_document_page(groups, limit=50, offset=0, facets=False)
    finally:
        db._read_only_rows = original
    if len(captured) != 1:
        raise ProbeError(
            f"could not capture actual default list SQL for {len(groups)} group(s)"
        )
    sql, params = captured[0]
    return [row["detail"] for row in original("EXPLAIN QUERY PLAN " + sql, params)]


def _validate_plan(db: DB, groups: list[str], expected_index: str) -> list[str]:
    details = _capture_default_plan(db, groups)
    joined = "\n".join(details).upper()
    if expected_index.upper() not in joined:
        raise ProbeError(
            f"plan for {len(groups)} group(s) does not use {expected_index}: "
            + "; ".join(details)
        )
    if "TEMP B-TREE FOR ORDER BY" in joined:
        raise ProbeError(
            f"plan for {len(groups)} group(s) contains TEMP B-TREE FOR ORDER BY: "
            + "; ".join(details)
        )
    return details


def _warmup_safety() -> tuple[int, int]:
    warnings: list[str] = []

    class WarningCapture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            warnings.append(record.getMessage())

    logger = logging.getLogger("app.db")
    handler = WarningCapture()
    logger.addHandler(handler)
    with tempfile.TemporaryDirectory(prefix="ima-first-load-warmup-") as directory:
        empty_path = Path(directory) / "empty.sqlite"
        populated_path = Path(directory) / "populated.sqlite"
        empty = DB(empty_path)
        populated = DB(populated_path)
        try:
            empty_result = empty.warm_ima_document_page(limit=50)

            row = {
                "group_id": "warmup-group",
                "media_id": "warmup-document",
                "day": "0901",
                "valid_day": 1,
                "name": "warmup-document.pdf",
                "group_name": "warmup-group",
                "name_folded": "warmup-document.pdf",
                "metadata_folded": "warmup-group",
                "abstract": "",
                "abstract_folded": "",
                "abstract_zh": "",
                "abstract_src_hash": "",
                "cover_url": "",
                "tags": [],
                "size": 0,
                "chars": 0,
                "has_pdf": 0,
                "has_txt": 0,
                "pdf_path": "",
                "txt_path": "",
                "downloaded_at": "",
            }
            populated.replace_ima_document_index([row], "stale-like", 0)
            populated_result = populated.warm_ima_document_page(limit=50)
        finally:
            logger.removeHandler(handler)
            empty.close()
            populated.close()
    warmup_warnings = [
        warning for warning in warnings if warning.startswith("[ima-page-warmup]")
    ]
    if warmup_warnings:
        raise ProbeError("warmup safety warning: " + "; ".join(warmup_warnings))
    if empty_result != 0:
        raise ProbeError(f"empty-index warmup returned {empty_result}, expected 0")
    if populated_result != 1:
        raise ProbeError(
            f"populated/stale-like-index warmup returned {populated_result}, expected 1"
        )
    return empty_result, populated_result


def _report(
    *,
    db_path: Path,
    document_count: int,
    group_count: int,
    groups: list[str],
    list_times: list[float],
    facets_times: list[float],
    plans: list[tuple[str, list[str]]],
    budgets: tuple[float, float, float],
    warmup: tuple[int, int],
    passed: bool,
) -> str:
    list_median = median(list_times)
    facets_median = median(facets_times)
    list_budget, facets_budget, ceiling = budgets
    lines = [
        f"db path: {db_path}",
        f"document count: {document_count}",
        f"group count: {group_count}",
        f"requested group count: {len(groups)}",
        "list runs (ms): " + ", ".join(f"{value:.3f}" for value in list_times),
        "facets runs (ms): " + ", ".join(f"{value:.3f}" for value in facets_times),
        f"list median (ms): {list_median:.3f}",
        f"facets median (ms): {facets_median:.3f}",
        f"thresholds: list median < {list_budget:.3f} ms; facets median < {facets_budget:.3f} ms; hard request < {ceiling:.3f} ms",
    ]
    for label, details in plans:
        lines.append(f"EXPLAIN {label}:")
        lines.extend(f"  {detail}" for detail in details)
        lines.append("  checks: expected index present; no TEMP B-TREE FOR ORDER BY")
    lines.extend(
        [
            "warmup safety:",
            f"  empty index: {warmup[0]} (no exception)",
            f"  populated/stale-like index: {warmup[1]} (no exception)",
            "overall: PASS" if passed else "overall: FAIL",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    source = Path(args.db).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="ima-first-load-probe-") as directory:
        snapshot = Path(directory) / "snapshot.sqlite"
        _readonly_backup(source, snapshot)
        db = DB(snapshot)
        try:
            all_groups, groups = _requested_groups(db, args.groups)
            document_count = db.ima_document_index_count()
            group_count = len(all_groups)
            plans: list[tuple[str, list[str]]] = []
            if len(groups) > 1:
                plans.append(
                    (
                        "multi-group",
                        _validate_plan(db, groups, "idx_ima_doc_latest"),
                    )
                )
                plans.append(
                    (
                        "one-group",
                        _validate_plan(db, [groups[0]], "idx_ima_doc_group_latest"),
                    )
                )
            else:
                plans.append(
                    (
                        "one-group",
                        _validate_plan(db, groups, "idx_ima_doc_group_latest"),
                    )
                )
            list_times, facets_times = _measure(db, groups, args.runs)
        finally:
            db.close()

    warmup = _warmup_safety()
    list_median = median(list_times)
    facets_median = median(facets_times)
    ceiling = args.hard_request_ceiling_ms
    over_ceiling = [
        ("list", index + 1, value)
        for index, value in enumerate(list_times)
        if value >= ceiling
    ] + [
        ("facets", index + 1, value)
        for index, value in enumerate(facets_times)
        if value >= ceiling
    ]
    passed = list_median < args.list_budget_ms and facets_median < args.facets_budget_ms
    passed = passed and not over_ceiling
    report = _report(
        db_path=source,
        document_count=document_count,
        group_count=group_count,
        groups=groups,
        list_times=list_times,
        facets_times=facets_times,
        plans=plans,
        budgets=(args.list_budget_ms, args.facets_budget_ms, ceiling),
        warmup=warmup,
        passed=passed,
    )
    print(report)
    if over_ceiling:
        print(
            "hard-ceiling failures: "
            + ", ".join(
                f"{kind} run {index}={value:.3f} ms"
                for kind, index, value in over_ceiling
            ),
            file=sys.stderr,
        )
    if list_median >= args.list_budget_ms:
        print("list median failed its threshold", file=sys.stderr)
    if facets_median >= args.facets_budget_ms:
        print("facets median failed its threshold", file=sys.stderr)
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    _validate_args(args, parser)
    try:
        return run(args)
    except (OSError, ProbeError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
