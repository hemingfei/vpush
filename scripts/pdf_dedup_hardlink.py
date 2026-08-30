#!/usr/bin/env python3
"""全站 PDF 去重：同内容文件用硬链接合并（存储 VPS 上运行）。

用法：
  python3 pdf_dedup_hardlink.py                # dry-run：只统计，不改任何文件
  python3 pdf_dedup_hardlink.py --apply        # 实际合并

原理：按体积分组 → 同体积才算 sha1 → 同 hash 即同内容。把多余路径换成指向「mtime 最老」
那份的硬链接（os.link 到同目录临时名再 os.replace 原子换入）。两条路径都保留，
ima 索引/访问路径零变化，存储只占一份；ima-puller 覆写其中一条不影响另一条。
仅当同设备且属主/权限一致才合并；120 秒内新写入的文件跳过；排除 local/（中金归采集会话）。
天然幂等：已合并的组重跑只会再次零成本换入同一硬链接。
"""

import argparse
import collections
import hashlib
import os
import sys
import time

ROOT = "/srv/vpush-ima"
EXCLUDE = ("/srv/vpush-ima/local/",)
FRESH_SEC = 120


def sha1_of(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="实际执行合并（默认只统计）")
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()

    by_size = collections.defaultdict(list)
    scanned = 0
    for dp, _, fs in os.walk(args.root):
        for f in fs:
            if not f.lower().endswith(".pdf"):
                continue
            p = os.path.join(dp, f)
            if p.startswith(EXCLUDE):
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            if time.time() - st.st_mtime < FRESH_SEC:
                continue
            by_size[st.st_size].append((p, st))
            scanned += 1
    dup_sizes = {s: v for s, v in by_size.items() if len(v) > 1}
    print(f"扫描 {scanned} 个 PDF，同体积候选组 {len(dup_sizes)}，"
          f"涉及 {sum(len(v) for v in dup_sizes.values())} 个文件", flush=True)

    stats = {"groups": 0, "linked": 0, "skip_meta": 0, "race": 0, "bytes": 0}
    for size, entries in sorted(dup_sizes.items(), key=lambda x: -x[0]):
        by_hash = collections.defaultdict(list)
        for p, st in entries:
            try:
                by_hash[sha1_of(p)].append((p, st))
            except OSError:
                pass
        for same in by_hash.values():
            if len(same) < 2:
                continue
            stats["groups"] += 1
            same.sort(key=lambda x: (x[1].st_mtime, len(x[0])))  # mtime 最老者为正本
            keep_p, keep_st = same[0]
            for dup_p, dup_st in same[1:]:
                if (dup_st.st_dev != keep_st.st_dev or dup_st.st_uid != keep_st.st_uid
                        or dup_st.st_gid != keep_st.st_gid
                        or (dup_st.st_mode & 0o7777) != (keep_st.st_mode & 0o7777)):
                    stats["skip_meta"] += 1
                    continue
                try:
                    # 换入前复核：两边 inode 未被并发替换（压缩回刷/ima-puller 可能 os.replace）
                    if (os.stat(dup_p).st_ino != dup_st.st_ino
                            or os.stat(keep_p).st_ino != keep_st.st_ino):
                        stats["race"] += 1
                        continue
                    if args.apply:
                        tmp = dup_p + ".dedup-tmp"
                        if os.path.exists(tmp):
                            os.unlink(tmp)
                        os.link(keep_p, tmp)
                        os.replace(tmp, dup_p)
                except OSError as e:
                    print(f"  ERR {dup_p}: {e}", file=sys.stderr)
                    stats["race"] += 1
                    continue
                stats["linked"] += 1
                stats["bytes"] += size
                print(f"  {'链接' if args.apply else '将链接'} {size / 1048576:.1f}MB  {dup_p}", flush=True)
    action = "合并" if args.apply else "可合并(dry-run)"
    print(f"完成：重复组 {stats['groups']}，{action} {stats['linked']} 个文件，"
          f"元数据不一致跳过 {stats['skip_meta']}，并发变更跳过 {stats['race']}，"
          f"{'释放' if args.apply else '可释放'} {stats['bytes'] / 1048576:.0f}MB",
          flush=True)


if __name__ == "__main__":
    main()
