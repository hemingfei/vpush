#!/usr/bin/env python3
"""本地库一致性体检（只报告不删改）：写入 .cicc/consistency.json。

检查项（磁盘侧自洽性）：
  corrupt      非 %PDF 头/零字节文件
  dup_id       同一报告 id 出现在多个文件（尾缀 _<id> 撞车）
  bad_name     缺少「_数字」尾缀的 pdf（无法与 sidecar 关联）
  empty_dirs   空目录（品类/MMDD 层级残留）
  sidecar_miss 无 sidecar 行的文件数（信息项）
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time

LIB = "/srv/vpush-ima/local/cicc-research"
CTRL = "/srv/vpush-ima/local/.cicc"
ID_TAIL = re.compile(r"_([0-9]+)$")


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
    files = glob.glob(LIB + "/*/*/*.pdf")
    corrupt, bad_name = [], []
    ids, dup_ids = {}, set()
    sidecar_rows = {}
    meta_path = os.path.join(LIB, ".vpush-local-meta.jsonl")
    try:
        with open(meta_path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    sidecar_rows[str(row.get("id") or "")] = row
                except ValueError:
                    continue
    except OSError:
        pass
    no_sidecar = 0
    for f in files:
        rel = os.path.relpath(f, LIB)
        try:
            with open(f, "rb") as fh:
                if fh.read(5) != b"%PDF-":
                    corrupt.append(rel)
        except OSError:
            corrupt.append(rel)
        stem = os.path.basename(f)[:-4]
        m = ID_TAIL.search(stem)
        if not m:
            bad_name.append(rel)
            continue
        rid = m.group(1)
        if rid in ids:
            dup_ids.add(rid)
        ids.setdefault(rid, rel)
        if rid not in sidecar_rows:
            no_sidecar += 1
    empty_dirs = [dp for dp, _, fs in os.walk(LIB, topdown=False)
                  if not fs and not any(os.listdir(dp))]
    report = {
        "generated_at": int(time.time()),
        "files": len(files),
        "corrupt": sorted(corrupt)[:20],
        "corrupt_count": len(corrupt),
        "dup_ids": sorted(dup_ids)[:20],
        "dup_id_count": len(dup_ids),
        "bad_name": sorted(bad_name)[:20],
        "bad_name_count": len(bad_name),
        "no_sidecar_count": no_sidecar,
        "empty_dirs": [d.replace(LIB + "/", "") for d in empty_dirs][:20],
        "empty_dir_count": len(empty_dirs),
    }
    write_json(os.path.join(CTRL, "consistency.json"), report)
    print(json.dumps({k: v for k, v in report.items() if k != "corrupt"}, ensure_ascii=False)[:400])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"consistency failed: {exc}", file=sys.stderr)
        sys.exit(1)
