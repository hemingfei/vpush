#!/usr/bin/env bash
# Storage VPS: low-priority encrypted archive backup.
set -eu

ENV_FILE=/etc/vpush/ima-storage.env
if [ ! -f "$ENV_FILE" ]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$ENV_FILE"

: "${ARCHIVE_ROOT:?ARCHIVE_ROOT required}"
: "${RESTIC_SUCCESS_FILE:?RESTIC_SUCCESS_FILE required}"

# Credentials come only from the root-only env file; never echo them.
nice -n 10 ionice -c2 -n7 restic backup "$ARCHIVE_ROOT" \
  --tag ima-archive --limit-upload 20480

TMP="${RESTIC_SUCCESS_FILE}.tmp.$$"
mkdir -p "$(dirname "$RESTIC_SUCCESS_FILE")"
date +%s >"$TMP"
mv -f "$TMP" "$RESTIC_SUCCESS_FILE"
