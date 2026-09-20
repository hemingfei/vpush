#!/usr/bin/env bash
# Host: map ARM hot (date-shard) → /srv/vpush-ima classic POSIX tree.
# Incremental only. Do not point --source at a full storage archive.
set -euo pipefail
CACHE_ROOT="${CACHE_ROOT:-/data/vpush-ima-cache}"
SOURCE="${VPUSH_NFS_SYNC_SOURCE:-$CACHE_ROOT/hot}"
DEST="${VPUSH_NFS_SYNC_DEST:-/srv/vpush-ima}"
PYTHON="${VPUSH_PYTHON:-/opt/vpush-ima-lab/venv/bin/python}"
SCRIPT="${VPUSH_NFS_SYNC_PY:-/opt/vpush-ima-lab/src/scripts/arm_nfs_sync.py}"
if [[ ! -f "$SCRIPT" ]]; then
  SCRIPT=/opt/vpush-ima-lab/scripts/arm_nfs_sync.py
fi
exec "$PYTHON" "$SCRIPT" --enable --apply --source "$SOURCE" --dest "$DEST"
