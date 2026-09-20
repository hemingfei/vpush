#!/usr/bin/env bash
# Host: run the production IMA collector (ImaDocumentService.sync_once).
# Lab-only process env. Do not export VPUSH_ARM_MIDDLEWARE into systemd.
set -euo pipefail

CACHE_ROOT="${CACHE_ROOT:-/data/vpush-ima-cache}"
SRC_ROOT="${VPUSH_SRC_ROOT:-/opt/vpush-ima-lab/src}"
PYTHON="${VPUSH_PYTHON:-/opt/vpush-ima-lab/venv/bin/python}"
SCRIPT="${IMA_HOST_SYNC_PY:-$SRC_ROOT/scripts/ima_host_sync.py}"
SECRETS="${IMA_PURE_SECRETS_FILE:-/opt/vpush-ima-lab/secrets/ima-pure.json}"
GROUPS_FILE="${IMA_PURE_GROUPS_FILE:-/opt/vpush-ima-lab/secrets/ima-pure-groups.json}"

if [[ ! -f "$SCRIPT" ]]; then
  echo "ima_host_sync.py missing at $SCRIPT" >&2
  exit 2
fi

export CACHE_ROOT
export IMA_PURE_SECRETS_FILE="$SECRETS"
export IMA_PURE_GROUPS_FILE="$GROUPS_FILE"
export IMA_HOST_DB="${IMA_HOST_DB:-$CACHE_ROOT/ima-host.sqlite}"
export IMA_HOST_INDEX="${IMA_HOST_INDEX:-$CACHE_ROOT/ima-index}"
export VPUSH_ARM_STAGING_ROOT="${VPUSH_ARM_STAGING_ROOT:-$CACHE_ROOT/staging}"
export PYTHONPATH="${PYTHONPATH:-$SRC_ROOT}"

# Production owns IMA incremental (sync_once → IMA_PULL). Do not dual-collect
# from this host timer unless Kale explicitly sets IMA_LAB_DUAL_COLLECT=1.
if [[ "${IMA_LAB_DUAL_COLLECT:-0}" != "1" ]]; then
  echo "IMA lab collect refused: production owns incremental via IMA_PULL. Timer must stay disabled." >&2
  exit 3
fi

exec "$PYTHON" "$SCRIPT" --enable --secrets "$SECRETS" --groups-file "$GROUPS_FILE"
