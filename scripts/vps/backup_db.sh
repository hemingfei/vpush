#!/usr/bin/env bash
# 生产库一致性备份：走 sqlite3 backup API，替代 cp（journal 模式下 cp 可能拷到撕裂事务）。
# 用法（在 VPS 上）：DB=/opt/vpush/data/dav.db bash backup_db.sh
# 依次尝试宿主机 sqlite3 CLI → 宿主机 python3 → docker 一次性容器。
set -euo pipefail

DB="${DB:-/opt/vpush/data/dav.db}"
DEST_DIR="${DEST_DIR:-/opt/vpush/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$DEST_DIR/dav-$STAMP.db"

mkdir -p "$DEST_DIR"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB" ".backup '$DEST'"
elif command -v python3 >/dev/null 2>&1; then
  python3 - "$DB" "$DEST" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
try:
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
finally:
    source.close()
PY
else
  docker run --rm -v "/opt/vpush/data:/data:ro" -v "$DEST_DIR:/backups" \
    python:3.12-slim python -c "
import sqlite3
source = sqlite3.connect('file:/data/$(basename "$DB")?mode=ro', uri=True)
target = sqlite3.connect('/backups/$(basename "$DEST")')
source.backup(target)
target.close()
"
fi

chmod 600 "$DEST" 2>/dev/null || true

if command -v sqlite3 >/dev/null 2>&1; then
  test "$(sqlite3 "file:$DEST?mode=ro" 'PRAGMA quick_check')" = "ok"
elif command -v python3 >/dev/null 2>&1; then
  python3 - "$DEST" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
finally:
    conn.close()
PY
fi

echo "$DEST"
