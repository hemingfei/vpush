#!/usr/bin/env bash
# Lab-only CICC → ARM staging wrapper for vpush-cicc-lab-sync.service.
# Not production. Never print or commit cookie contents.
#
# Calls scripts/cicc_arm_lab_sync.py with --enable --limit N.
# Default DRY_RUN=1 → --dry-run. Set DRY_RUN=0 in the systemd unit to --apply.
# LIMIT: $CACHE_ROOT/ops-lab-settings.json cicc_limit when present,
# else CICC_LAB_LIMIT (default 3). Cookie stays in VPUSH_CICC_COOKIE_FILE.
set -euo pipefail

CACHE_ROOT="${CACHE_ROOT:-/data/vpush-ima-cache}"
SETTINGS="${OPS_LAB_SETTINGS:-$CACHE_ROOT/ops-lab-settings.json}"
SRC_ROOT="${VPUSH_SRC_ROOT:-/opt/vpush-ima-lab/src}"
SCRIPT="${CICC_LAB_SYNC_PY:-${SRC_ROOT}/scripts/cicc_arm_lab_sync.py}"
PYTHON="${VPUSH_PYTHON:-/opt/vpush-ima-lab/venv/bin/python}"
# Host path. Ops container sees the same file as /secrets/cicc-cookies.txt.
COOKIE="${VPUSH_CICC_COOKIE_FILE:-/opt/vpush-ima-lab/secrets/cicc-cookies.txt}"
LIMIT="${CICC_LAB_LIMIT:-3}"
LOG_DIR="${CACHE_ROOT}/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="${LOG_DIR}/cicc-lab-sync-${STAMP}.log"

umask 077
mkdir -p "${LOG_DIR}"

if [[ ! -x "${PYTHON}" && ! -f "${PYTHON}" ]]; then
  echo "VPUSH_PYTHON missing: ${PYTHON}" >&2
  exit 1
fi
if [[ ! -f "${SCRIPT}" ]]; then
  echo "cicc_arm_lab_sync.py missing under ${SRC_ROOT}/scripts" >&2
  exit 1
fi
if [[ ! -f "${COOKIE}" ]]; then
  echo "CICC cookie file missing; set VPUSH_CICC_COOKIE_FILE to host secrets/cicc-cookies.txt" >&2
  exit 1
fi

if [[ -f "${SETTINGS}" ]]; then
  parsed="$("${PYTHON}" - "${SETTINGS}" <<'PY'
import json, sys
path = sys.argv[1]
try:
    data = json.loads(open(path, encoding="utf-8").read())
except Exception:
    raise SystemExit(0)
limit = data.get("cicc_limit", "")
if limit in (None, ""):
    raise SystemExit(0)
try:
    print(max(1, min(int(limit), 20)))
except (TypeError, ValueError):
    raise SystemExit(0)
PY
)" || true
  if [[ -n "${parsed:-}" ]]; then
    LIMIT="${parsed}"
  fi
fi

if [[ "${DRY_RUN:-1}" == "0" ]]; then
  MODE="--apply"
else
  MODE="--dry-run"
fi

export CACHE_ROOT
export VPUSH_CICC_COOKIE_FILE="${COOKIE}"
export VPUSH_ARM_STAGING_ROOT="${VPUSH_ARM_STAGING_ROOT:-${CACHE_ROOT}/staging}"
# --enable turns middleware on for this process only. Do not export
# VPUSH_ARM_MIDDLEWARE into the systemd environment.

{
  echo "start $(date -Iseconds) mode=${MODE} limit=${LIMIT}"
  set +e
  "${PYTHON}" "${SCRIPT}" --enable "${MODE}" --limit "${LIMIT}"
  rc=$?
  set -e
  echo "done rc=${rc} $(date -Iseconds)"
  exit "${rc}"
} >>"${LOG}" 2>&1
