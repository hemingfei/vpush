#!/usr/bin/env python3
"""全站 PDF 增量条件压缩（IMA-flat 字体子集化 + gs /prepress）。

用法：
  python3 pdf_backfill_compress.py --limit 20
  python3 pdf_backfill_compress.py --dry-run

规则：IMA-flat 先无损子集化完整字体，其他文件使用 gs /prepress；新体积低于原件
90%、至少节省 256 KiB 且页数/页面几何/逐页文本一致才原子替换。状态按文件指纹
和策略版本记录，文件被重新下载或算法升级后会自动重检。
"""

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import time
from collections import Counter
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cicc_report_collector import (
    IMA_FLAT_MARKER,
    IMA_FLAT_MIN_BYTES,
    compress_pdf_result,
)

ROOT = "/srv/vpush-ima"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "compress_state.json")
STRATEGY_VERSION = 3
FRESH_SEC = 120
EXCLUDE = ("/srv/vpush-ima/local/",)


def default_state_path(root: str) -> str:
    absolute = os.path.abspath(root)
    if absolute == os.path.abspath(ROOT):
        return STATE
    suffix = hashlib.sha256(absolute.encode()).hexdigest()[:12]
    return os.path.join(HERE, f"compress_state_{suffix}.json")


@contextmanager
def path_lock(path: str):
    fd = os.open(os.path.dirname(path), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def fingerprint(st: os.stat_result) -> dict[str, int]:
    return {
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "inode": st.st_ino,
    }


def state_record(st: os.stat_result, result: str) -> dict[str, int | str]:
    return {
        **fingerprint(st),
        "strategy_version": STRATEGY_VERSION,
        "result": result,
    }


def record_matches(record: object, st: os.stat_result) -> bool:
    return bool(
        isinstance(record, dict)
        and record.get("strategy_version") == STRATEGY_VERSION
        and record.get("size") == st.st_size
        and record.get("mtime_ns") == st.st_mtime_ns
        and record.get("inode") == st.st_ino
    )


def source_unchanged(path: str, original: os.stat_result) -> bool:
    try:
        return fingerprint(os.stat(path)) == fingerprint(original)
    except FileNotFoundError:
        return False


def is_ima_flat_path(path: str, size: int) -> bool:
    if size < IMA_FLAT_MIN_BYTES:
        return False
    try:
        with open(path, "rb") as f:
            if IMA_FLAT_MARKER not in f.read():
                return False
        import fitz
        with fitz.open(path) as doc:
            return doc.metadata.get("subject") == IMA_FLAT_MARKER.decode()
    except Exception:
        return False


def atomic_write_json(path: str, data: object) -> None:
    directory = os.path.dirname(path) or "."
    fd, temp = tempfile.mkstemp(prefix=".compress-state-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def load_state(
    path: str, root: str, files: dict[str, os.stat_result]
) -> tuple[dict, bool]:
    absolute_root = os.path.abspath(root)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}, False

    if isinstance(raw, dict) and raw.get("version") in {2, STRATEGY_VERSION}:
        records = raw.get("files")
        state_root = raw.get("root")
        if not isinstance(records, dict):
            return {}, True
        if state_root and state_root != absolute_root:
            return {}, True
        current = {p: record for p, record in records.items() if p in files}
        migrated = raw.get("version") != STRATEGY_VERSION or state_root != absolute_root
        if migrated:
            for record in current.values():
                if isinstance(record, dict):
                    record["strategy_version"] = STRATEGY_VERSION
        return current, migrated or len(current) != len(records)

    if not isinstance(raw, list):
        return {}, True

    records = {}
    for file_path in raw:
        st = files.get(file_path)
        if st is None or is_ima_flat_path(file_path, st.st_size):
            continue
        records[file_path] = state_record(st, "legacy_v1")
    return records, True


def state_payload(root: str, records: dict) -> dict:
    return {
        "version": STRATEGY_VERSION,
        "root": os.path.abspath(root),
        "files": records,
    }


def replace_pdf(
    path: str, data: bytes, original: os.stat_result
) -> tuple[bool, str, os.stat_result | None]:
    directory = os.path.dirname(path)
    fd, temp = tempfile.mkstemp(prefix=".compress-", suffix=".pdf", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, original.st_mode & 0o7777)
        os.chown(temp, original.st_uid, original.st_gid)
        os.utime(temp, ns=(original.st_atime_ns, original.st_mtime_ns))
        with path_lock(path):
            if not source_unchanged(path, original):
                return False, "source_changed", None
            os.replace(temp, path)
            temp = ""
            replaced_stat = os.stat(path)
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return True, "", replaced_stat
    finally:
        if temp:
            try:
                os.unlink(temp)
            except OSError:
                pass


def scan_files(root: str) -> dict[str, os.stat_result]:
    files = {}
    exclude = () if os.path.abspath(root).startswith("/srv/vpush-ima/local") else EXCLUDE
    for directory, _, names in os.walk(root):
        for name in names:
            if not name.lower().endswith(".pdf"):
                continue
            path = os.path.join(directory, name)
            if path.startswith(exclude):
                continue
            try:
                files[path] = os.stat(path)
            except FileNotFoundError:
                pass
    return files


def run(args: argparse.Namespace) -> None:
    files = scan_files(args.root)
    records, migrated = load_state(args.state, args.root, files)
    now = time.time()
    pending = []
    fresh = 0
    for path, st in files.items():
        if record_matches(records.get(path), st):
            continue
        if now - st.st_mtime < FRESH_SEC:
            fresh += 1
            continue
        ima_flat = is_ima_flat_path(path, st.st_size)
        pending.append((not ima_flat, -st.st_mtime_ns, path, st))
    pending.sort()
    if args.limit:
        pending = pending[:args.limit]

    print(f"共 {len(files)} 个 PDF，状态 {len(records)}，待处理 {len(pending)}，"
          f"新写入跳过 {fresh}", flush=True)
    stats = Counter()
    before = after = 0

    for index, (_, _, path, original) in enumerate(pending, 1):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except (FileNotFoundError, OSError):
            stats["source_changed"] += 1
            continue

        new, result = compress_pdf_result(data)
        processed_stat = original
        if result.startswith("compressed_"):
            if args.dry_run:
                replaced = True
            else:
                replaced, failure, replaced_stat = replace_pdf(path, new, original)
                if replaced:
                    processed_stat = replaced_stat
                else:
                    result = failure
            if replaced:
                stats[result] += 1
                before += len(data)
                after += len(new)
                print(f"  -{100 - len(new) * 100 // len(data)}%  "
                      f"{len(data) / 1048576:.1f}->{len(new) / 1048576:.1f}MB  "
                      f"{result}  {path}", flush=True)
            else:
                stats[result] += 1
        else:
            stats[result] += 1

        if not args.dry_run and result not in {
                "source_changed", "subset_error", "subset_unavailable",
                "gs_error", "gs_unavailable", "verify_error", "verify_unavailable"}:
            if processed_stat is None:
                records.pop(path, None)
            else:
                records[path] = state_record(processed_stat, result)
        if not args.dry_run and index % 25 == 0:
            atomic_write_json(args.state, state_payload(args.root, records))
            saved = (before - after) / 1048576
            print(f"... 处理 {index}/{len(pending)}，替换 "
                  f"{stats['compressed_subset'] + stats['compressed_gs']}，"
                  f"累计省 {saved:.0f}MB", flush=True)

    if not args.dry_run and (pending or migrated):
        atomic_write_json(args.state, state_payload(args.root, records))
    saved = (before - after) / 1048576
    reasons = ", ".join(f"{key}={value}" for key, value in sorted(stats.items())) or "无"
    print(f"完成：处理 {sum(stats.values())}，替换 "
          f"{stats['compressed_subset'] + stats['compressed_gs']}，"
          f"{before / 1048576:.0f}MB -> {after / 1048576:.0f}MB（省 {saved:.0f}MB）；"
          f"{reasons}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="跑压缩但不替换文件或状态")
    parser.add_argument("--limit", type=int, default=0, help="本次最多处理多少个")
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--state", default=None)
    args = parser.parse_args()
    args.state = args.state or default_state_path(args.root)

    os.makedirs(os.path.dirname(args.state) or ".", exist_ok=True)
    with open(args.state + ".lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("已有压缩任务在运行，本次跳过", flush=True)
            return
        run(args)


if __name__ == "__main__":
    main()
