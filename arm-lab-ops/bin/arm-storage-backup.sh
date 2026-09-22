#!/usr/bin/env bash
# ARM classic tree → storage /srv/vpush-ima. Incremental add only.
# Never --delete. Storage is the cold archive; 115 is the later copy.
set -euo pipefail

CACHE_ROOT="${CACHE_ROOT:-/data/vpush-ima-cache}"
SRC="${STORAGE_BACKUP_SRC:-/srv/vpush-ima}"
HOT="${VPUSH_NFS_SYNC_SOURCE:-$CACHE_ROOT/hot}"
DEST="${STORAGE_BACKUP_DEST:-/srv/vpush-ima}"
HOST="${STORAGE_BACKUP_HOST:-root@198.12.125.212}"
KEY="${STORAGE_BACKUP_KEY:-/opt/vpush-ima-lab/secrets/storage-backup}"
PYTHON="${VPUSH_PYTHON:-/opt/vpush-ima-lab/venv/bin/python}"
SRC_ROOT="${VPUSH_SRC_ROOT:-/opt/vpush-ima-lab/src}"
NFS_SYNC="${VPUSH_NFS_SYNC_PY:-$SRC_ROOT/scripts/arm_nfs_sync.py}"
BACKUP="${VPUSH_STORAGE_BACKUP_PY:-$SRC_ROOT/scripts/arm_storage_backup.py}"
LOCK="${CACHE_ROOT}/manifest/storage-backup.lock"

MODE=(--apply)
if [[ "${1:-}" == "--dry-run" ]]; then
  MODE=(--dry-run)
fi

mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
if ! flock -w 90 9; then
  echo "storage backup busy; skip" >&2
  exit 0
fi

if [[ "${MODE[0]}" == "--apply" && -f "$NFS_SYNC" ]]; then
  "$PYTHON" "$NFS_SYNC" --enable --apply --source "$HOT" --dest "$SRC" \
    || echo "nfs-sync failed; rsync existing export anyway" >&2
fi

exec "$PYTHON" "$BACKUP" "${MODE[@]}" \
  --source "$SRC" \
  --remote "$HOST" \
  --dest "$DEST" \
  --key "$KEY"
