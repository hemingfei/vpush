#!/usr/bin/env python3
"""Push the ARM classic tree onto the storage box (cold backup).

Storage outranks 115: this only adds files the archive does not already
have. It never deletes, and it refuses any destination other than
``/srv/vpush-ima``. Default is off until ``--apply`` or ``--dry-run``.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

DEST_ROOT = "/srv/vpush-ima"
_REMOTE_RE = re.compile(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+")
_EXCLUDES = (".cicc/", ".vpush-storage-health.json")


def remote_ok(remote: str) -> bool:
    return bool(_REMOTE_RE.fullmatch(remote))


def dest_ok(path: str) -> bool:
    return path.rstrip("/") == DEST_ROOT


def build_rsync_argv(
    *,
    source: Path,
    remote: str,
    dest_path: str,
    key: Path,
    dry_run: bool,
) -> list[str]:
    if not remote_ok(remote):
        raise ValueError(f"bad storage host: {remote!r}")
    if not dest_ok(dest_path):
        raise ValueError(f"refusing dest outside {DEST_ROOT}: {dest_path!r}")
    ssh = " ".join(
        [
            "ssh",
            "-i",
            shlex.quote(str(key)),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
    )
    argv = [
        "rsync",
        "-a",
        "--ignore-existing",
        "--chown=99:100",
        "--timeout=120",
    ]
    if dry_run:
        argv.extend(["--dry-run", "--stats"])
    for pattern in _EXCLUDES:
        argv.append(f"--exclude={pattern}")
    argv.extend(
        [
            "-e",
            ssh,
            f"{str(source).rstrip('/')}/",
            f"{remote}:{dest_path.rstrip('/')}/",
        ]
    )
    if any(arg == "--delete" or arg.startswith("--delete-") for arg in argv):
        raise RuntimeError("refusing rsync --delete")
    return argv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="copy new files")
    parser.add_argument("--dry-run", action="store_true", help="list what would copy")
    parser.add_argument("--source", default=DEST_ROOT)
    parser.add_argument("--remote", required=False, default="")
    parser.add_argument("--dest", default=DEST_ROOT)
    parser.add_argument("--key", default="")
    args = parser.parse_args(argv)

    if not args.apply and not args.dry_run:
        print("storage backup off（需要 --apply 或 --dry-run）。不会 rsync，不会删除。")
        return 0
    if not args.remote or not args.key:
        print("缺少 --remote 或 --key。未写入。", file=sys.stderr)
        return 2
    key = Path(args.key)
    if not key.is_file():
        print(f"没有备份密钥: {key}", file=sys.stderr)
        return 2
    source = Path(args.source)
    if not source.is_dir():
        print(f"源目录不存在: {source}", file=sys.stderr)
        return 2
    try:
        command = build_rsync_argv(
            source=source,
            remote=args.remote,
            dest_path=args.dest,
            key=key,
            dry_run=bool(args.dry_run and not args.apply),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(" ".join(shlex.quote(part) for part in command))
    completed = subprocess.run(command)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
