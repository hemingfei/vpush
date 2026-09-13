#!/usr/bin/env python3
"""研报首屏 DB 冷测：列表/分面查询耗时与 EXPLAIN QUERY PLAN（可复跑）。

这里只测 DB 查询，不含 FastAPI 授权、服务层附加或 JSON 序列化；HTTP
耗时与响应体 raw/gzip 字节数由 scripts/ima_first_load_probe.py 实测。

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
import statistics
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
        return


def spy_reads(db) -> list[tuple[str, tuple]]:
    """记录 db 这一轮实际发出的 SQL（用来 EXPLAIN 真实语句，而不是复制一份）。"""
    calls: list[tuple[str, tuple]] = []
    original = db._read_only_rows

    def spy(sql, params=()):
        calls.append((sql, tuple(params)))
        return original(sql, params)

    db._read_only_rows = spy  # type: ignore[method-assign]
    return calls


def open_benchmark_db(path: str, *, cold: bool):
    from app.db import DB

    if cold:
        drop_page_cache(path)
    return DB(path)


def benchmark_once(
    path: str,
    groups: list[str],
    *,
    cold: bool,
    limit: int,
    offset: int,
) -> tuple[list[tuple[str, tuple]], float, float]:
    list_db = open_benchmark_db(path, cold=cold)
    try:
        calls = spy_reads(list_db)
        started = time.perf_counter()
        list_db.ima_document_page(groups, limit=limit, offset=offset, facets=False)
        list_ms = (time.perf_counter() - started) * 1000
        del calls[1:]
    finally:
        list_db.close()

    facets_db = open_benchmark_db(path, cold=cold)
    try:
        started = time.perf_counter()
        facets_db.ima_document_page(groups, limit=1, offset=0)
        facets_ms = (time.perf_counter() - started) * 1000
    finally:
        facets_db.close()
    return calls, list_ms, facets_ms


def run_benchmarks(
    path: str,
    groups: list[str],
    *,
    cold: bool,
    limit: int,
    offset: int,
    runs: int,
) -> list[tuple[list[tuple[str, tuple]], float, float]]:
    return [
        benchmark_once(path, groups, cold=cold, limit=limit, offset=offset)
        for _ in range(max(runs, 1))
    ]


def explain(path: str, calls: list[tuple[str, tuple]]) -> None:
    db = open_benchmark_db(path, cold=False)
    try:
        print("\n--- EXPLAIN QUERY PLAN（首屏列表那条 SQL）---")
        for sql, params in calls[:1]:
            for row in db._read_only_rows(f"EXPLAIN QUERY PLAN {sql}", params):
                print(f"  {row['detail']}")
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "dav.db"))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--cold", action="store_true", help="每次跑前丢页缓存")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--groups", default="", help="逗号分隔；默认取库里全部 group_id")
    args = parser.parse_args()

    groups = [item.strip() for item in args.groups.split(",") if item.strip()]
    if not groups:
        db = open_benchmark_db(args.db, cold=False)
        try:
            rows = db._read_only_rows(
                "SELECT group_id, COUNT(*) AS n FROM ima_document_index"  # noqa: S608 - 无外部输入
                " GROUP BY group_id ORDER BY n DESC",
            )
            groups = [str(row["group_id"]) for row in rows]
        finally:
            db.close()
    print(f"db={args.db} groups={len(groups)} limit={args.limit} offset={args.offset}")

    samples = run_benchmarks(
        args.db,
        groups,
        cold=args.cold,
        limit=args.limit,
        offset=args.offset,
        runs=args.runs,
    )
    for run, (_calls, list_ms, facets_ms) in enumerate(samples, 1):
        print(f"run{run}: DB 列表 {list_ms:8.1f} ms | DB 分面 {facets_ms:8.1f} ms")

    print(
        f"\n{len(samples)} 次 fresh DB: "
        f"list p50={statistics.median(sample[1] for sample in samples):.1f} ms | "
        f"facets p50={statistics.median(sample[2] for sample in samples):.1f} ms",
    )
    explain(args.db, samples[-1][0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
