#!/usr/bin/env python3
"""全站 PDF 去重：同内容文件用硬链接合并（存储 VPS 上运行）。

用法：
  python3 pdf_dedup_hardlink.py                # dry-run：只统计，不改任何文件
  python3 pdf_dedup_hardlink.py --apply        # 实际合并

原理：按体积分组 → 不同 inode 才计算 sha256 → 同 hash 即同内容。把重复 inode
下的路径换成指向「mtime 最老」正本的硬链接。路径均保留，存储只占一份；已共享
inode 的路径直接跳过。任务与 PDF 压缩共用全局锁，替换时再锁双方父目录。
"""

import argparse
import collections
import fcntl
import hashlib
import os
import re
import secrets
import stat
import sys
import time
from contextlib import contextmanager

ROOT = "/srv/vpush-ima"
EXCLUDE = ("/srv/vpush-ima/local/",)
HERE = os.path.dirname(os.path.abspath(__file__))
GLOBAL_LOCK = os.path.join(HERE, "compress_global.lock")
ARCHIVE_LOCK_NAME = ".vpush-pdf.lock"
FRESH_SEC = 120
OLD_TEMP_SUFFIX = ".pdf.dedup-tmp"
NEW_TEMP_RE = re.compile(r"^\.dedup-\d+-[0-9a-f]{16}$")


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(st: os.stat_result) -> tuple[int, int, int, int]:
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns


@contextmanager
def archive_lock(root: str):
    fd = os.open(os.path.join(root, ARCHIVE_LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o660)
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def scan_files(root: str) -> list[tuple[str, os.stat_result]]:
    entries = []
    now = time.time()
    for directory, _, names in os.walk(root):
        for name in names:
            if not name.lower().endswith(".pdf"):
                continue
            path = os.path.join(directory, name)
            if path.startswith(EXCLUDE):
                continue
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or now - st.st_mtime < FRESH_SEC:
                continue
            entries.append((path, st))
    return entries


def stale_temp_links(root: str, pdf_entries: list[tuple[str, os.stat_result]]):
    by_inode = collections.defaultdict(list)
    for path, st in pdf_entries:
        by_inode[(st.st_dev, st.st_ino)].append(path)
    stale = []
    for directory, _, names in os.walk(root):
        for name in names:
            if not (name.endswith(OLD_TEMP_SUFFIX) or NEW_TEMP_RE.fullmatch(name)):
                continue
            path = os.path.join(directory, name)
            try:
                st = os.lstat(path)
            except OSError:
                continue
            witnesses = by_inode.get((st.st_dev, st.st_ino))
            if stat.S_ISREG(st.st_mode) and witnesses:
                stale.append((path, witnesses[0], st))
    return stale


def clean_stale_temp_links(
    root: str, pdf_entries: list[tuple[str, os.stat_result]], apply: bool
) -> tuple[int, int]:
    cleaned = bytes_freed = 0
    for temp_path, pdf_path, original in stale_temp_links(root, pdf_entries):
        if apply:
            try:
                with archive_lock(root):
                    temp_st = os.lstat(temp_path)
                    pdf_st = os.lstat(pdf_path)
                    if ((temp_st.st_dev, temp_st.st_ino) !=
                            (pdf_st.st_dev, pdf_st.st_ino)):
                        continue
                    os.unlink(temp_path)
                    if temp_st.st_nlink == 1:
                        bytes_freed += temp_st.st_size
            except OSError:
                continue
        cleaned += 1
    return cleaned, bytes_freed


def file_xattrs(path: str) -> dict[str, bytes] | None:
    listxattr = getattr(os, "listxattr", None)
    getxattr = getattr(os, "getxattr", None)
    if listxattr is None or getxattr is None:
        return None
    try:
        return {
            name: getxattr(path, name, follow_symlinks=False)
            for name in listxattr(path, follow_symlinks=False)
        }
    except OSError:
        return None


def metadata_matches(
    a_path: str, a: os.stat_result, b_path: str, b: os.stat_result
) -> bool:
    return bool(
        a.st_dev == b.st_dev
        and a.st_uid == b.st_uid
        and a.st_gid == b.st_gid
        and (a.st_mode & 0o7777) == (b.st_mode & 0o7777)
        and file_xattrs(a_path) is not None
        and file_xattrs(a_path) == file_xattrs(b_path)
    )


def link_path(source: str, destination: str) -> bool:
    directory = os.path.dirname(destination)
    temp = os.path.join(
        directory, f".dedup-{os.getpid()}-{secrets.token_hex(8)}")
    try:
        os.link(source, temp)
        os.replace(temp, destination)
        temp = ""
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            try:
                os.fsync(directory_fd)
                return True
            except OSError:
                return False
        finally:
            os.close(directory_fd)
    finally:
        if temp:
            try:
                os.unlink(temp)
            except OSError:
                pass


def run(root: str, apply: bool) -> dict[str, int]:
    entries = scan_files(root)
    cleaned, cleaned_bytes = clean_stale_temp_links(root, entries, apply)
    if apply and cleaned:
        entries = scan_files(root)
    by_size = collections.defaultdict(list)
    for path, st in entries:
        by_size[st.st_size].append((path, st))
    duplicate_sizes = {
        size: group
        for size, group in by_size.items()
        if len({(st.st_dev, st.st_ino) for _, st in group}) > 1
    }
    print(
        f"扫描 {len(entries)} 个 PDF，不同 inode 同体积候选组 {len(duplicate_sizes)}；"
        f"{'清理' if apply else '可清理'}旧临时链接 {cleaned}",
        flush=True,
    )

    stats = {
        "groups": 0,
        "linked": 0,
        "already_linked": 0,
        "skip_meta": 0,
        "race": 0,
        "durability_error": 0,
        "bytes": cleaned_bytes,
        "cleaned": cleaned,
    }
    for size, same_size in sorted(
        duplicate_sizes.items(), key=lambda item: -item[0]
    ):
        inode_groups = collections.defaultdict(list)
        for path, st in same_size:
            inode_groups[(st.st_dev, st.st_ino)].append((path, st))

        by_hash = collections.defaultdict(list)
        for inode_entries in inode_groups.values():
            path, _ = min(inode_entries, key=lambda item: len(item[0]))
            try:
                by_hash[sha256_of(path)].append(inode_entries)
            except OSError:
                stats["race"] += 1

        for same_content in by_hash.values():
            if len(same_content) < 2:
                continue
            stats["groups"] += 1
            same_content.sort(
                key=lambda group: (
                    min(st.st_mtime_ns for _, st in group),
                    min(len(path) for path, _ in group),
                )
            )
            keep_group = same_content[0]
            keep_path, keep_st = min(keep_group, key=lambda item: len(item[0]))
            stats["already_linked"] += len(keep_group) - 1

            for duplicate_group in same_content[1:]:
                duplicate_path, duplicate_st = duplicate_group[0]
                paths = [path for path, _ in duplicate_group]
                originals = {
                    path: fingerprint(st) for path, st in duplicate_group
                }
                try:
                    with archive_lock(root):
                        if fingerprint(os.lstat(keep_path)) != fingerprint(keep_st):
                            stats["race"] += len(paths)
                            continue
                        if any(
                            fingerprint(os.lstat(path)) != originals[path]
                            for path in paths
                        ):
                            stats["race"] += len(paths)
                            continue
                        if not metadata_matches(
                            keep_path, keep_st, duplicate_path, duplicate_st
                        ):
                            stats["skip_meta"] += len(paths)
                            continue
                        if not apply:
                            stats["linked"] += len(paths)
                            if duplicate_st.st_nlink == len(paths):
                                stats["bytes"] += size
                            continue

                        old_fd = os.open(duplicate_path, os.O_RDONLY)
                        try:
                            for path in paths:
                                try:
                                    if not link_path(keep_path, path):
                                        stats["durability_error"] += 1
                                    stats["linked"] += 1
                                except OSError as error:
                                    print(f"  ERR {path}: {error}", file=sys.stderr)
                                    stats["race"] += 1
                            if os.fstat(old_fd).st_nlink == 0:
                                stats["bytes"] += size
                        finally:
                            os.close(old_fd)
                except OSError as error:
                    print(f"  ERR {duplicate_path}: {error}", file=sys.stderr)
                    stats["race"] += len(paths)
                    continue
                print(
                    f"  {'链接' if apply else '将链接'} "
                    f"{size / 1048576:.1f}MB  {duplicate_path}",
                    flush=True,
                )

    action = "合并" if apply else "可合并(dry-run)"
    print(
        f"完成：重复内容组 {stats['groups']}，{action} {stats['linked']} 个路径，"
        f"已有硬链接 {stats['already_linked']} 个路径，"
        f"元数据不一致跳过 {stats['skip_meta']}，并发变更跳过 {stats['race']}，"
        f"目录落盘告警 {stats['durability_error']}，"
        f"{'释放' if apply else '可释放'} {stats['bytes'] / 1048576:.0f}MB",
        flush=True,
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply", action="store_true", help="实际执行合并（默认只统计）"
    )
    parser.add_argument("--root", default=ROOT)
    args = parser.parse_args()

    if not args.apply:
        run(args.root, False)
        return

    os.makedirs(HERE, exist_ok=True)
    with open(GLOBAL_LOCK, "a") as global_lock:
        fcntl.flock(global_lock, fcntl.LOCK_EX)
        run(args.root, True)


if __name__ == "__main__":
    main()
