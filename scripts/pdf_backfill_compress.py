#!/usr/bin/env python3
"""全站 PDF 存量条件压缩回刷（gs /prepress 最高品质，存储 VPS 上运行）。

用法：
  python3 pdf_backfill_compress.py --limit 20      # 试跑最大的 20 个，看替换率
  nohup python3 -u pdf_backfill_compress.py > /root/cicc/compress.log 2>&1 &
  python3 pdf_backfill_compress.py --dry-run       # 只跑不改

规则（与采集脚本 compress_pdf 一致）：新体积 < 原件 90% 且页数+文本层一致才原子替换；
已优化的 PDF 压不动自动跳过，幂等可中断重跑（断点见 compress_state.json）。
替换保留原属主/权限/mtime 并 fsync；120 秒内新写入的文件跳过（避开采集进程）。
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cicc_report_collector import compress_pdf

ROOT = "/srv/vpush-ima"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "compress_state.json")
FRESH_SEC = 120
EXCLUDE = ("/srv/vpush-ima/local/",)  # 中金目录归采集会话管辖；--root 指到 local 时例外（回刷中金库）


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="跑压缩但不替换文件")
    ap.add_argument("--limit", type=int, default=0, help="本次最多处理多少个（试跑用）")
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()

    files = []
    exclude = () if os.path.abspath(args.root).startswith("/srv/vpush-ima/local") else EXCLUDE
    for dp, _, fs in os.walk(args.root):
        for f in fs:
            if f.lower().endswith(".pdf"):
                p = os.path.join(dp, f)
                if not p.startswith(exclude):
                    files.append(p)
    files.sort(key=lambda p: -os.path.getsize(p))  # 大文件优先，尽早兑现体积收益
    done = set(json.load(open(STATE))) if os.path.exists(STATE) else set()
    print(f"共 {len(files)} 个 PDF，已完成断点 {len(done)}，本次处理 "
          f"{len([p for p in files if p not in done]) if not args.limit else min(args.limit, len(files))} 个",
          flush=True)

    stats = {"n": 0, "replaced": 0, "kept": 0, "before": 0, "after": 0}
    for p in files:
        if args.limit and stats["n"] >= args.limit:
            break
        if p in done:
            continue
        st = os.stat(p)
        if time.time() - st.st_mtime < FRESH_SEC:
            continue
        stats["n"] += 1
        with open(p, "rb") as f:
            data = f.read()
        new = compress_pdf(data)
        if new is data:
            stats["kept"] += 1
        else:
            stats["replaced"] += 1
            stats["before"] += len(data)
            stats["after"] += len(new)
            print(f"  -{100 - len(new) * 100 // len(data)}%  "
                  f"{len(data) // 1048576}->{len(new) // 1048576}MB  {p}", flush=True)
            if not args.dry_run:
                tmp = p + ".gs-tmp"
                with open(tmp, "wb") as f:
                    f.write(new)
                fd = os.open(tmp, os.O_RDONLY)
                os.fsync(fd)
                os.close(fd)
                os.chmod(tmp, st.st_mode & 0o7777)
                os.chown(tmp, st.st_uid, st.st_gid)
                os.utime(tmp, (st.st_atime, st.st_mtime))
                os.replace(tmp, p)
        done.add(p)
        if stats["n"] % 50 == 0:
            json.dump(sorted(done), open(STATE, "w"))
            saved = (stats["before"] - stats["after"]) / 1048576
            print(f"... 处理 {stats['n']}，替换 {stats['replaced']}，累计省 {saved:.0f}MB", flush=True)
    if not args.dry_run:
        json.dump(sorted(done), open(STATE, "w"))
    saved = (stats["before"] - stats["after"]) / 1048576
    print(f"完成：处理 {stats['n']}，替换 {stats['replaced']}，保持原样 {stats['kept']}，"
          f"被替换文件 {stats['before'] / 1048576:.0f}MB -> {stats['after'] / 1048576:.0f}MB（省 {saved:.0f}MB）",
          flush=True)


if __name__ == "__main__":
    main()
