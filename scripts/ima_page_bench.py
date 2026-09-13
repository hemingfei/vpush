#!/usr/bin/env python3
"""研报列表首载基准：冷/热查询耗时 + 响应体体积 + EXPLAIN QUERY PLAN（可复跑）。

用法：
  python3 scripts/ima_page_bench.py --db data/dav.db                # 热态，本地
  python3 scripts/ima_page_bench.py --db /tmp/snap_dav.db --cold --runs 3   # 冷页缓存

在 VPS 上对着冻结快照跑（比在生产打真实请求安全）：
  docker cp /tmp/measure/dav.db vpush:/tmp/snap_dav.db
  docker exec -u 0 vpush sh -lc 'chmod 666 /tmp/snap_dav.db'
  docker cp app vpush:/tmp/newapp/app
  docker cp scripts/ima_page_bench.py vpush:/tmp/ima_page_bench.py
  docker exec -u 0 -e PYTHONPATH=/tmp/newapp vpush python3 /tmp/ima_page_bench.py --db /tmp/snap_dav.db --cold --runs 3

`--cold` 用 posix_fadvise(DONTNEED) 丢页缓存（仅 Linux）。测的是首屏真实形态：
先只取列表（facets=False），分面（计数/日期/标签）随后单独一次请求。
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def drop_page_cache(path: str) -> None:
    """丢页缓存，模拟冷启动。需要 Linux；失败时静默跳过。"""
    import os

    advise = getattr(os, "posix_fadvise", None)  # 仅 Linux 有
    if advise is None:
        return
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            advise(fd, 0, 0, getattr(os, "POSIX_FADV_DONTNEED", 0))
        finally:
            os.close(fd)
    except OSError:
        pass


def int_or_zero(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def endpoint_payload(page: dict) -> dict:
    """按 app/api.py 的返回形状组装响应体。"""
    return {
        "groups": page.get("groups") if page.get("groups") is not None else [],
        "items": page["items"],
        "days": page["days"],
        "tags": page["tags"],
        "tag_counts": page.get("tag_counts") or {},
        "document_count": int_or_zero(page.get("document_count")),
        "day": page.get("day") or "",
        "has_more": bool(page.get("has_more")),
        "offset": int_or_zero(page.get("offset")),
    }


def json_bytes(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def field_bytes(items: list[dict]) -> list[tuple[str, int]]:
    totals: dict[str, int] = {}
    for item in items:
        for key, value in item.items():
            totals[key] = totals.get(key, 0) + json_bytes(value)
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


def spy_reads(db) -> list[tuple[str, tuple]]:
    """记录 db 这一轮实际发出的 SQL（用来 EXPLAIN 真实语句，而不是复制一份）。"""
    calls: list[tuple[str, tuple]] = []
    original = db._read_only_rows

    def spy(sql, params=()):
        calls.append((sql, tuple(params)))
        return original(sql, params)

    db._read_only_rows = spy  # type: ignore[method-assign]
    return calls


def explain(db, calls: list[tuple[str, tuple]]) -> None:
    print("\n--- EXPLAIN QUERY PLAN（首屏列表那条 SQL）---")
    for sql, params in calls[:1]:
        for row in db._read_only_rows(f"EXPLAIN QUERY PLAN {sql}", params):
            print(f"  {row['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "dav.db"))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--cold", action="store_true", help="每次跑前丢页缓存")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--groups", default="", help="逗号分隔；默认取库里全部 group_id")
    args = parser.parse_args()

    from app.db import DB

    db = DB(args.db)
    if args.groups:
        groups = [item.strip() for item in args.groups.split(",") if item.strip()]
    else:
        rows = db._read_only_rows(
            "SELECT group_id, COUNT(*) AS n FROM ima_document_index"  # noqa: S608 - 无外部输入
            " GROUP BY group_id ORDER BY n DESC",
        )
        groups = [str(row["group_id"]) for row in rows]
    print(f"db={args.db} groups={len(groups)} limit={args.limit} offset={args.offset}")

    page: dict = {}
    calls: list[tuple[str, tuple]] = []
    for run in range(1, max(args.runs, 1) + 1):
        if args.cold:
            drop_page_cache(args.db)
        started = time.perf_counter()
        calls = spy_reads(db)
        page = db.ima_document_page(
            groups,
            limit=args.limit,
            offset=args.offset,
            facets=False,
        )
        del calls[1:]  # 只留首屏列表那条 SELECT
        list_ms = (time.perf_counter() - started) * 1000
        if args.cold:
            drop_page_cache(args.db)
        started = time.perf_counter()
        db.ima_document_page(groups, limit=1, offset=0)
        facets_ms = (time.perf_counter() - started) * 1000
        print(f"run{run}: 列表(facets=False) {list_ms:8.1f} ms | 分面 {facets_ms:8.1f} ms")

    payload = endpoint_payload(page)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    print(
        f"\n首屏列表响应体: {len(raw) / 1024:.1f} KB raw / "
        f"{len(gzip.compress(raw)) / 1024:.1f} KB gzip, "
        f"items={len(payload['items'])}, document_count={payload['document_count']}",
    )

    print("\n--- 响应体字段占比 ---")
    for key, value in sorted(
        payload.items(),
        key=lambda kv: json_bytes(kv[1]),
        reverse=True,
    ):
        size = json_bytes(value)
        extra = f" (len={len(value)})" if isinstance(value, (list, dict)) else ""
        print(f"{size:9d} B  {100 * size / max(len(raw), 1):5.1f}%  {key}{extra}")

    if payload["items"]:
        print("\n--- items 字段占比（0 表示可去）---")
        for key, size in field_bytes(payload["items"]):
            print(f"{size:9d} B  {key}")

    explain(db, calls)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
