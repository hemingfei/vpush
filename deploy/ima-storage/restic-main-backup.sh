#!/usr/bin/env bash
# Main VPS: online SQLite snapshot then encrypted control-data backup.
set -eu

ENV_FILE=/etc/vpush/ima-main-backup.env
if [ ! -f "$ENV_FILE" ]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$ENV_FILE"

SUCCESS_FILE="${MAIN_RESTIC_SUCCESS_FILE:-/var/lib/vpush-ima/main-restic-last-success}"
ENV_PATH=/opt/vpush/.env

# Fail closed unless production env is root:root 0600.
if [ ! -f "$ENV_PATH" ]; then
  echo "missing $ENV_PATH" >&2
  exit 1
fi
OWNER_GROUP="$(stat -c '%U:%G' "$ENV_PATH" 2>/dev/null || stat -f '%Su:%Sg' "$ENV_PATH")"
MODE="$(stat -c '%a' "$ENV_PATH" 2>/dev/null || stat -f '%OLp' "$ENV_PATH")"
if [ "$OWNER_GROUP" != "root:root" ] || { [ "$MODE" != "600" ] && [ "$MODE" != "0600" ]; }; then
  echo "$ENV_PATH must be root:root mode 0600 (got ${OWNER_GROUP} ${MODE})" >&2
  exit 1
fi

# Online SQLite backup first; never copy an open dav.db directly.
BACKUP_SCRIPT=""
if [ -n "${BACKUP_PY:-}" ] && [ -f "$BACKUP_PY" ]; then
  BACKUP_SCRIPT="$BACKUP_PY"
elif [ -f /opt/vpush/scripts/backup.py ]; then
  BACKUP_SCRIPT=/opt/vpush/scripts/backup.py
elif [ -f /opt/vpush/src/scripts/backup.py ]; then
  BACKUP_SCRIPT=/opt/vpush/src/scripts/backup.py
else
  echo "backup.py not found (set BACKUP_PY or install under /opt/vpush)" >&2
  exit 1
fi

python3 "$BACKUP_SCRIPT" \
  /opt/vpush/data/dav.db /opt/vpush/data/backups 30

PATHS=(
  /opt/vpush/data/backups
  /opt/vpush/data/ima/manifest.json
  /opt/vpush/data/ima/state.json
  /opt/vpush/docker-compose.yml
  /opt/vpush/.env
  /opt/vpush/config.yaml
)
OPTIONAL=(
  /etc/systemd/system/vpush-ima-*.service
  /etc/systemd/system/vpush-ima-*.timer
  /etc/wireguard/wg-vpush-ima.conf
  /etc/fstab
)

BACKUP_ARGS=()
for path in "${PATHS[@]}"; do
  if [ -e "$path" ]; then
    BACKUP_ARGS+=("$path")
  else
    case "$path" in
      /opt/vpush/.env)
        echo "mandatory path missing: $path" >&2
        exit 1
        ;;
      *)
        logger -p daemon.warning -- "vpush-ima-main-backup: skip missing $path"
        ;;
    esac
  fi
done

# shellcheck disable=SC2086
for pattern in "${OPTIONAL[@]}"; do
  # intentional glob for unit/timer paths
  for path in $pattern; do
    if [ -e "$path" ]; then
      BACKUP_ARGS+=("$path")
    fi
  done
done

nice -n 10 ionice -c2 -n7 restic backup "${BACKUP_ARGS[@]}" \
  --tag ima-control --limit-upload 20480

# Restore-test contract helper notes (runbook): verify restored .env mode 0600
# and that FEISHU_CREDENTIAL_KEY is present without printing its value.

TMP="${SUCCESS_FILE}.tmp.$$"
mkdir -p "$(dirname "$SUCCESS_FILE")"
date +%s >"$TMP"
mv -f "$TMP" "$SUCCESS_FILE"
