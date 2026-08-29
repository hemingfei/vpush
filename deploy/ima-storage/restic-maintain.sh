#!/usr/bin/env bash
# Shared Restic check/prune for archive or main-control repositories.
set -eu

usage() {
  echo "usage: $0 check|prune /etc/vpush/ima-storage.env|/etc/vpush/ima-main-backup.env" >&2
  exit 2
}

[ "$#" -eq 2 ] || usage
ACTION="$1"
ENV_FILE="$2"

case "$ACTION" in
  check|prune) ;;
  *) usage ;;
esac

case "$ENV_FILE" in
  /etc/vpush/ima-storage.env|/etc/vpush/ima-main-backup.env) ;;
  *) usage ;;
esac

if [ ! -f "$ENV_FILE" ]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$ENV_FILE"

write_check_json() {
  local ok_value="$1"
  local checked_at
  checked_at="$(date +%s)"
  : "${RESTIC_CHECK_FILE:?RESTIC_CHECK_FILE required}"
  mkdir -p "$(dirname "$RESTIC_CHECK_FILE")"
  local tmp="${RESTIC_CHECK_FILE}.tmp.$$"
  python3 -c 'import json,sys
ok=sys.argv[1]=="true"
out={"checked_at": int(sys.argv[2]), "ok": ok}
with open(sys.argv[3],"w",encoding="utf-8") as fh:
 json.dump(out, fh, separators=(",",":"))
' "$ok_value" "$checked_at" "$tmp"
  mv -f "$tmp" "$RESTIC_CHECK_FILE"
}

is_first_sunday() {
  # Weekly timer + date guard: only first Sunday of the month runs prune.
  local dom dow_sun
  dom="$(date +%d)"
  dow_sun="$(date +%w)" # 0 = Sunday
  [ "$dow_sun" = "0" ] || return 1
  [ "$dom" -le 7 ]
}

case "$ACTION" in
  check)
    set +e
    restic check --read-data-subset=5%
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then
      write_check_json true
    else
      write_check_json false
    fi
    exit "$rc"
    ;;
  prune)
    if [ "${FORCE_PRUNE:-0}" != "1" ] && ! is_first_sunday; then
      echo "skip prune: not first Sunday (set FORCE_PRUNE=1 to override)"
      exit 0
    fi
    # Archive retention. Main-control prune is not scheduled by the monthly timer.
    restic forget --tag ima-archive --keep-daily 30 --prune
    ;;
esac
