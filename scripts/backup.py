#!/usr/bin/env python3
"""SQLite 在线备份（WAL 安全）：python scripts/backup.py [db] [backup_dir] [keep]"""
from __future__ import annotations

import pathlib
import sqlite3
import sys
import time


def snapshot_files(folder: pathlib.Path) -> list[pathlib.Path]:
    """应用 dav-<ts>.db + 部署 dav.db.<ts>；按 mtime，不含 shm/wal。"""
    files: list[pathlib.Path] = []
    if not folder.is_dir():
        return files
    for path in folder.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name.endswith(("-shm", "-wal")):
            continue
        if (name.startswith("dav-") and name.endswith(".db")) or name.startswith("dav.db."):
            files.append(path)
    files.sort(key=lambda item: (item.stat().st_mtime, item.name))
    return files


def prune(folder: pathlib.Path, keep: int) -> None:
    files = snapshot_files(folder)
    for old in files[:-keep]:
        old.unlink(missing_ok=True)
        pathlib.Path(str(old) + "-shm").unlink(missing_ok=True)
        pathlib.Path(str(old) + "-wal").unlink(missing_ok=True)


def main() -> int:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/dav.db"
    backup_dir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "backups")
    keep = int(sys.argv[3]) if len(sys.argv) > 3 else 14

    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_dir.chmod(0o700)
    target = backup_dir / f"dav-{time.strftime('%Y%m%d-%H%M%S')}.db"

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(target)
    try:
        result = check.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        target.unlink(missing_ok=True)
        raise RuntimeError(f"备份校验失败: {result}")
    target.chmod(0o600)

    prune(backup_dir, keep)
    print(f"备份完成: {target}（保留最近 {keep} 份）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
