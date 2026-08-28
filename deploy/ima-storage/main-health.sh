#!/usr/bin/env bash
# Main VPS: aggregate WireGuard/NFS/remote health into local status JSON.
set -eu

ENV_FILE=/etc/vpush/ima-storage.env
if [ ! -f "$ENV_FILE" ]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$ENV_FILE"

: "${WG_INTERFACE:?WG_INTERFACE required}"
: "${STORAGE_WG_IP:?STORAGE_WG_IP required}"
: "${ARCHIVE_MOUNT:?ARCHIVE_MOUNT required}"
: "${STATUS_OUTPUT:?STATUS_OUTPUT required}"
: "${COMPOSE_DIR:?COMPOSE_DIR required}"

if [ -z "${COMPOSE_FILE:-}" ]; then
  if [ -f /opt/vpush/docker-compose.prod.yml ]; then
    COMPOSE_FILE=/opt/vpush/docker-compose.prod.yml
  elif [ -f /opt/vpush/docker-compose.yml ]; then
    COMPOSE_FILE=/opt/vpush/docker-compose.yml
  else
    echo "no docker compose file found under /opt/vpush (set COMPOSE_FILE)" >&2
    exit 1
  fi
fi

STATE_FILE=/var/lib/vpush-ima/main-health-last
PLACEHOLDER=/run/vpush-ima-placeholder
REMOTE_MARKER="${ARCHIVE_MOUNT}/.vpush-ima-root"
REMOTE_HEALTH="${ARCHIVE_MOUNT}/.vpush-storage-health.json"
TMP_FILE="${STATUS_OUTPUT}.tmp.$$"
CHECKED_AT="$(date +%s)"
mkdir -p "$(dirname "$STATUS_OUTPUT")" /var/lib/vpush-ima

AVAILABLE=false
WRITABLE=false
CAPACITY_BLOCKED=false
USED_PERCENT=0
INODE_PERCENT=0
MONTHLY_TX_BYTES=0
REASON="unavailable"

trap 'rm -f "$TMP_FILE"' EXIT

log_transition() {
  logger -p daemon.warning -- "vpush-ima-main-health: $1"
}

wg_handshake_ok() {
  # When no recent handshake exists, treat as down. Skip age check if no transfer expected.
  local latest
  latest="$(wg show "$WG_INTERFACE" latest-handshakes 2>/dev/null | awk 'NR==1 {print $2}')" || return 1
  [ -n "$latest" ] || return 1
  [ "$latest" != "0" ] || return 1
  local now age
  now="$(date +%s)"
  age=$((now - latest))
  [ "$age" -le 180 ]
}

nfs_port_ok() {
  timeout 5 nc -z "$STORAGE_WG_IP" 2049 >/dev/null 2>&1
}

container_running() {
  docker compose -f "$COMPOSE_FILE" ps --status running vpush 2>/dev/null | grep -q vpush
}

healthz_ok() {
  # python:3.12-slim image probe; mirror Dockerfile HEALTHCHECK style.
  docker compose -f "$COMPOSE_FILE" exec -T vpush \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/ima-storage')" \
    >/dev/null 2>&1
}

maybe_recover_mount() {
  if mountpoint -q "$ARCHIVE_MOUNT"; then
    return 0
  fi
  if container_running; then
    : >"$PLACEHOLDER"
  fi
  if nfs_port_ok; then
    mount "$ARCHIVE_MOUNT" || return 1
    if [ -f "$PLACEHOLDER" ]; then
      (
        cd "$COMPOSE_DIR"
        docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate vpush
      ) || return 1
      if healthz_ok; then
        rm -f "$PLACEHOLDER"
      fi
    fi
  fi
  mountpoint -q "$ARCHIVE_MOUNT"
}

# Probe path: always continue to publish JSON.
if ! wg_handshake_ok; then
  REASON="unavailable"
elif ! nfs_port_ok; then
  REASON="unavailable"
else
  maybe_recover_mount || true
  if ! mountpoint -q "$ARCHIVE_MOUNT"; then
    REASON="unavailable"
  elif [ ! -f "$REMOTE_MARKER" ]; then
    # Never create .vpush-ima-root locally on a missing archive.
    REASON="unavailable"
  elif [ ! -f "$REMOTE_HEALTH" ]; then
    REASON="unavailable"
  else
    PARSE="$(python3 -c 'import json,sys,time
path=sys.argv[1]
now=int(time.time())
try:
 d=json.load(open(path,encoding="utf-8"))
except Exception:
 print("invalid 0 0 0 0 false false"); raise SystemExit
checked=int(d.get("checked_at") or 0)
if checked<=0 or now-checked>600:
 print("stale", int(d.get("used_percent") or 0), int(d.get("inode_percent") or 0), int(d.get("monthly_tx_bytes") or 0), "false", "false")
 raise SystemExit
used=int(d.get("used_percent") or 0)
inode=int(d.get("inode_percent") or 0)
tx=int(d.get("monthly_tx_bytes") or 0)
writable="true" if d.get("writable") else "false"
avail="true" if d.get("available", True) else "false"
print("ok", used, inode, tx, writable, avail)
' "$REMOTE_HEALTH")"
    R_STATUS="$(printf '%s\n' "$PARSE" | awk '{print $1}')"
    USED_PERCENT="$(printf '%s\n' "$PARSE" | awk '{print $2}')"
    INODE_PERCENT="$(printf '%s\n' "$PARSE" | awk '{print $3}')"
    MONTHLY_TX_BYTES="$(printf '%s\n' "$PARSE" | awk '{print $4}')"
    R_WRITABLE="$(printf '%s\n' "$PARSE" | awk '{print $5}')"
    R_AVAIL="$(printf '%s\n' "$PARSE" | awk '{print $6}')"

    if [ "$R_STATUS" != "ok" ]; then
      REASON="unavailable"
    else
      AVAILABLE=true
      if [ "$R_WRITABLE" = "true" ] && [ "$R_AVAIL" = "true" ]; then
        WRITABLE=true
        REASON=""
      else
        WRITABLE=false
        REASON="readonly"
      fi
      if [ "$USED_PERCENT" -ge 80 ] || [ "$INODE_PERCENT" -ge 80 ]; then
        CAPACITY_BLOCKED=true
        WRITABLE=false
        REASON="capacity"
      fi
    fi
  fi
fi

# Traffic warnings only (1.2 TB / 1.6 TB); never block reads/writes.
TX_BAND=ok
if [ "$MONTHLY_TX_BYTES" -ge 1600000000000 ]; then
  TX_BAND=high
elif [ "$MONTHLY_TX_BYTES" -ge 1200000000000 ]; then
  TX_BAND=warn
fi

BOUNDED_REASON="$REASON"
case "$BOUNDED_REASON" in
  ""|unavailable|readonly|capacity|stale|missing|invalid) ;;
  *) BOUNDED_REASON="unavailable" ;;
esac

STATUS_KEY="${AVAILABLE}:${WRITABLE}:${CAPACITY_BLOCKED}:${BOUNDED_REASON}:${TX_BAND}"
PREV_KEY=""
if [ -f "$STATE_FILE" ]; then
  PREV_KEY="$(tr -d '\n' <"$STATE_FILE" || true)"
fi

python3 -c 'import json,sys
out={
 "checked_at": int(sys.argv[1]),
 "available": sys.argv[2]=="true",
 "writable": sys.argv[3]=="true",
 "used_percent": int(float(sys.argv[4] or 0)),
 "inode_percent": int(float(sys.argv[5] or 0)),
 "monthly_tx_bytes": int(float(sys.argv[6] or 0)),
 "capacity_blocked": sys.argv[7]=="true",
 "reason": sys.argv[8],
}
with open(sys.argv[9],"w",encoding="utf-8") as fh:
 json.dump(out, fh, separators=(",",":"))
' "$CHECKED_AT" "$AVAILABLE" "$WRITABLE" "$USED_PERCENT" "$INODE_PERCENT" \
  "$MONTHLY_TX_BYTES" "$CAPACITY_BLOCKED" "$BOUNDED_REASON" "$TMP_FILE"

chown 99:100 "$TMP_FILE"
chmod 0640 "$TMP_FILE"
mv -f "$TMP_FILE" "$STATUS_OUTPUT"
chown 99:100 "$STATUS_OUTPUT"
chmod 0640 "$STATUS_OUTPUT"
trap - EXIT

if [ "$STATUS_KEY" != "$PREV_KEY" ]; then
  if [ "$AVAILABLE" = "true" ] && [ "$CAPACITY_BLOCKED" = "false" ] && [ "$WRITABLE" = "true" ] && [ "$TX_BAND" = "ok" ]; then
    log_transition "recovered available writable"
  else
    log_transition "transition available=$AVAILABLE writable=$WRITABLE capacity_blocked=$CAPACITY_BLOCKED reason=$BOUNDED_REASON tx=$TX_BAND"
  fi
  printf '%s\n' "$STATUS_KEY" >"$STATE_FILE"
fi

exit 0
