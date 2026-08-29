#!/usr/bin/env bash
# Storage VPS: publish archive health JSON under ARCHIVE_ROOT.
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
: "${RESTIC_CHECK_FILE:?RESTIC_CHECK_FILE required}"

HEALTH_FILE="${ARCHIVE_ROOT}/.vpush-storage-health.json"
TMP_FILE="${HEALTH_FILE}.tmp.$$"
CHECKED_AT="$(date +%s)"
REASON=""
WRITABLE=false
USED_PERCENT=0
INODE_PERCENT=0
MONTHLY_TX_BYTES=0
LAST_BACKUP=0
LAST_CHECK_OK=false
LAST_CHECK_AT=0

trap 'rm -f "$TMP_FILE"' EXIT

if [ ! -d "$ARCHIVE_ROOT" ]; then
  REASON="unavailable"
else
  if touch "${ARCHIVE_ROOT}/.vpush-health-write-test" 2>/dev/null; then
    rm -f "${ARCHIVE_ROOT}/.vpush-health-write-test"
    WRITABLE=true
  else
    REASON="readonly"
  fi
  USED_PERCENT="$(df -P "$ARCHIVE_ROOT" 2>/dev/null | awk 'NR==2 {gsub(/%/,"",$5); print $5+0}')"
  USED_PERCENT="${USED_PERCENT:-0}"
  INODE_PERCENT="$(df -Pi "$ARCHIVE_ROOT" 2>/dev/null | awk 'NR==2 {gsub(/%/,"",$5); print $5+0}')"
  INODE_PERCENT="${INODE_PERCENT:-0}"
fi

if [ -f "$RESTIC_SUCCESS_FILE" ]; then
  LAST_BACKUP="$(tr -d '[:space:]' <"$RESTIC_SUCCESS_FILE" || true)"
  case "$LAST_BACKUP" in
    ''|*[!0-9]*) LAST_BACKUP=0 ;;
  esac
fi

if [ -f "$RESTIC_CHECK_FILE" ]; then
  PARSE="$(python3 -c 'import json,sys
try:
 d=json.load(open(sys.argv[1],encoding="utf-8"))
 print(int(d.get("checked_at") or 0), "true" if d.get("ok") else "false")
except Exception:
 print(0, "false")
' "$RESTIC_CHECK_FILE")"
  LAST_CHECK_AT="$(printf '%s\n' "$PARSE" | awk '{print $1}')"
  LAST_CHECK_OK="$(printf '%s\n' "$PARSE" | awk '{print $2}')"
fi

# Parse vnstat --json only; never human-formatted units.
MONTHLY_TX_BYTES="$(vnstat --json 2>/dev/null | python3 -c 'import json,sys,time
try:
 j=json.load(sys.stdin)
except Exception:
 print(0); raise SystemExit
now=time.gmtime(); total=0
for iface in j.get("interfaces") or []:
  for month in (iface.get("traffic") or {}).get("month") or []:
    date=month.get("date") or {}
    if int(date.get("year") or 0)==now.tm_year and int(date.get("month") or 0)==now.tm_mon:
      total += int(month.get("tx") or 0)
print(max(0,total))
' 2>/dev/null || echo 0)"

AVAILABLE=true
if [ "$REASON" = "unavailable" ]; then
  AVAILABLE=false
fi

python3 -c 'import json,sys
out={
 "checked_at": int(sys.argv[1]),
 "available": sys.argv[2]=="true",
 "writable": sys.argv[3]=="true",
 "used_percent": int(float(sys.argv[4] or 0)),
 "inode_percent": int(float(sys.argv[5] or 0)),
 "monthly_tx_bytes": int(float(sys.argv[6] or 0)),
 "restic_last_success": int(float(sys.argv[7] or 0)),
 "restic_last_check_at": int(float(sys.argv[8] or 0)),
 "restic_last_check_ok": sys.argv[9]=="true",
 "reason": sys.argv[10],
}
path=sys.argv[11]
with open(path,"w",encoding="utf-8") as fh:
 json.dump(out, fh, separators=(",",":"))
' "$CHECKED_AT" "$AVAILABLE" "$WRITABLE" "$USED_PERCENT" "$INODE_PERCENT" \
  "$MONTHLY_TX_BYTES" "$LAST_BACKUP" "$LAST_CHECK_AT" "$LAST_CHECK_OK" "$REASON" "$TMP_FILE"

chown 99:100 "$TMP_FILE"
chmod 0640 "$TMP_FILE"
mv -f "$TMP_FILE" "$HEALTH_FILE"
chown 99:100 "$HEALTH_FILE"
chmod 0640 "$HEALTH_FILE"
trap - EXIT
exit 0
