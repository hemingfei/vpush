#!/usr/bin/env bash
# Host wrapper: /opt/vpush-ima-lab/bin/ima-lab-sync-all.sh
# Lab-only IMA → ARM staging. Not production.
# Reads LIMIT + ima_groups_parallel from $CACHE_ROOT/ops-lab-settings.json
# when present (ARM lab ops panel). Does not put secrets on argv.
#
# Default DRY_RUN=1 → --dry-run (same as cicc-lab-sync.sh).
# Set DRY_RUN=0 in the systemd unit for a real daily apply.
set -euo pipefail

CACHE_ROOT="${CACHE_ROOT:-/data/vpush-ima-cache}"
SETTINGS="${OPS_LAB_SETTINGS:-$CACHE_ROOT/ops-lab-settings.json}"
SCRIPTS_ROOT="${VPUSH_SCRIPTS_ROOT:-/opt/vpush-ima-lab/src/scripts}"
PYTHON="${VPUSH_PYTHON:-/opt/vpush-ima-lab/venv/bin/python}"
SCRIPT="${IMA_LAB_SYNC_PY:-$SCRIPTS_ROOT/ima_arm_lab_sync.py}"

LIMIT="${IMA_LIMIT:-10}"
PARALLEL="${IMA_GROUPS_PARALLEL:-0}"

if [[ -f "$SETTINGS" ]]; then
  parsed="$("$PYTHON" - "$SETTINGS" <<'PY'
import json, sys
path = sys.argv[1]
try:
    data = json.loads(open(path, encoding="utf-8").read())
except Exception:
    raise SystemExit(0)
limit = data.get("ima_limit_per_group", data.get("ima_limit", 10))
parallel = data.get("ima_groups_parallel", data.get("ima_parallel", False))
try:
    limit = max(1, min(int(limit), 20))
except (TypeError, ValueError):
    limit = 10
print(limit)
print("1" if parallel in (True, 1, "1", "true", "yes", "on") else "0")
PY
)" || true
  if [[ -n "${parsed:-}" ]]; then
    LIMIT="$(printf '%s\n' "$parsed" | sed -n '1p')"
    PARALLEL="$(printf '%s\n' "$parsed" | sed -n '2p')"
  fi
fi

GROUPS=(legacy 7479082602225992 7476629605476515 7437050366161003)
if [[ ! -f "$SCRIPT" ]]; then
  echo "ima_arm_lab_sync.py missing at $SCRIPT" >&2
  exit 2
fi

if [[ "${DRY_RUN:-1}" == "0" ]]; then
  MODE="--apply"
else
  MODE="--dry-run"
fi

run_group() {
  local group="$1"
  "$PYTHON" "$SCRIPT" --enable "$MODE" --limit "$LIMIT" --group "$group"
}

if [[ "$PARALLEL" == "1" ]]; then
  pids=()
  for group in "${GROUPS[@]}"; do
    run_group "$group" &
    pids+=("$!")
  done
  status=0
  for pid in "${pids[@]}"; do
    wait "$pid" || status=1
  done
  exit "$status"
fi

status=0
for group in "${GROUPS[@]}"; do
  run_group "$group" || status=1
  sleep 2
done
exit "$status"
