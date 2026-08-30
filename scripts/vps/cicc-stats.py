#!/usr/bin/env python3
"""归档体量统计（每小时，贵操作）：归档总字节 + 各品类文件数/字节 → .cicc/stats.json。

cicc-status.py 每分钟把它合并进 status.json 的 storage.archive 节；
本地库按 cicc-research/<品类> 分桶，其余归档目录聚合为 legacy/其他。
"""
from __future__ import annotations

import json
import os
import time

LIB_ROOT = "/srv/vpush-ima/local"
CTRL = "/srv/vpush-ima/local/.cicc"


def write_json(path: str, obj) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.chmod(tmp, 0o640)
    try:
        os.chown(tmp, 99, 100)
    except PermissionError:
        pass
    os.replace(tmp, path)


def main() -> None:
    cats: dict[str, dict] = {}
    total_files = total_bytes = 0
    for dp, _, fs in os.walk(LIB_ROOT):
        if "/.cicc" in dp:
            continue
        rel = os.path.relpath(dp, LIB_ROOT)
        parts = rel.split(os.sep)
        bucket = "其他归档"
        if parts[0] == "cicc-research":
            if len(parts) >= 2:
                bucket = f"中金·{parts[1]}"
        elif parts[0] != ".":
            bucket = parts[0]
        entry = cats.setdefault(bucket, {"files": 0, "bytes": 0})
        for name in fs:
            if not name.lower().endswith(".pdf"):
                continue
            try:
                size = os.stat(os.path.join(dp, name)).st_size
            except OSError:
                continue
            entry["files"] += 1
            entry["bytes"] += size
            total_files += 1
            total_bytes += size
    cats_list = [{"name": k, "files": v["files"], "bytes": v["bytes"]}
                 for k, v in sorted(cats.items(), key=lambda kv: -kv[1]["bytes"])]
    write_json(os.path.join(CTRL, "stats.json"),
               {"generated_at": int(time.time()),
                "archive": {"files": total_files, "bytes": total_bytes},
                "categories": cats_list})


if __name__ == "__main__":
    main()
