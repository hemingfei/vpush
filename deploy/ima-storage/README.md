# IMA Remote HDD Storage Runbook

Host-side WireGuard, NFSv4, health probes, and Restic jobs for the IMA archive.
Application code reads only the local status JSON; secrets never enter Git, Compose, or chat logs.

## Packages

Debian/Ubuntu storage VPS:

```bash
apt-get update
apt-get install -y wireguard nfs-kernel-server restic vnstat fio rsync jq smartmontools
```

Debian/Ubuntu main VPS:

```bash
apt-get update
apt-get install -y wireguard-tools nfs-common netcat-openbsd fio rsync jq
```

## Install paths

| Path | Mode / owner | Purpose |
|------|--------------|---------|
| `/usr/local/lib/vpush-ima/*.sh` | `0755` root:root | Health and Restic scripts |
| `/etc/systemd/system/vpush-ima-*.service` | `0644` root:root | Oneshoot services (`UMask=0077`, `NoNewPrivileges=true`) |
| `/etc/systemd/system/vpush-ima-*.timer` | `0644` root:root | Timers (`Persistent=true`, randomized delay) |
| `/etc/vpush/ima-storage.env` | `0600` root:root | Archive/storage credentials and paths |
| `/etc/vpush/ima-main-backup.env` | `0600` root:root | Main-control Restic credentials (distinct repo/prefix) |
| `/srv/vpush-ima` | `0750` `99:100` | Archive export root |
| `/srv/vpush-ima/.vpush-ima-root` | `0640` `99:100` | Archive identity marker (never auto-create on main) |
| `/srv/vpush-ima/.vpush-storage-health.json` | `0640` `99:100` | Storage health JSON |
| `/opt/vpush/data/ima_storage_status.json` | `0640` `99:100` | Main aggregate status for UID 99 container |
| `/opt/vpush/.env` | `0600` root:root | Mandatory; main backup fails closed on drift |
| `/var/lib/vpush-ima/` | `0750` root:root | Success/check markers and transition state |

Copy scripts and units:

```bash
install -d -m 755 /usr/local/lib/vpush-ima /etc/vpush /var/lib/vpush-ima
install -m 755 deploy/ima-storage/*.sh /usr/local/lib/vpush-ima/
install -m 644 deploy/ima-storage/*.service deploy/ima-storage/*.timer /etc/systemd/system/
```

## Secret files (interactive only)

Create empty root-only env files, then edit as root (values never on the shell command line):

```bash
install -m 600 /dev/null /etc/vpush/ima-storage.env
install -m 600 /dev/null /etc/vpush/ima-main-backup.env
${EDITOR:-nano} /etc/vpush/ima-storage.env
${EDITOR:-nano} /etc/vpush/ima-main-backup.env
```

`ima-storage.env` keys (examples, fill live values interactively):

```text
ARCHIVE_ROOT=/srv/vpush-ima
RESTIC_SUCCESS_FILE=/var/lib/vpush-ima/restic-last-success
RESTIC_CHECK_FILE=/var/lib/vpush-ima/restic-last-check
WG_INTERFACE=wg-vpush-ima
STORAGE_WG_IP=<storage-wg-ip>
ARCHIVE_MOUNT=/mnt/vpush-ima
STATUS_OUTPUT=/opt/vpush/data/ima_storage_status.json
COMPOSE_DIR=/opt/vpush
RESTIC_REPOSITORY=<archive-repo>
RESTIC_PASSWORD=<archive-repo-password>
AWS_ACCESS_KEY_ID=<s3-key>
AWS_SECRET_ACCESS_KEY=<s3-secret>
```

`ima-main-backup.env` must use a **distinct** Restic repository URL or bucket prefix from the archive repo, plus:

```text
RESTIC_CHECK_FILE=/var/lib/vpush-ima/main-restic-last-check
MAIN_RESTIC_SUCCESS_FILE=/var/lib/vpush-ima/main-restic-last-success
RESTIC_REPOSITORY=<main-control-repo>
RESTIC_PASSWORD=<main-control-password>
```

## NFS export identity

Storage export must squash to the container archive identity:

```text
/srv/vpush-ima <main-wg-ip>(rw,sync,all_squash,anonuid=99,anongid=100,no_subtree_check,fsid=10)
```

Validate with a temporary container `--user 99:100` bind of the mount: create, rename, read, delete. Root/all-squashed NFS tests and migration commands work through `all_squash,anonuid=99,anongid=100` (no `chmod 777`, no `no_root_squash`).

## Enable

```bash
systemctl daemon-reload
systemctl enable --now vpush-ima-storage-health.timer   # storage VPS
systemctl enable --now vpush-ima-restic-backup.timer
systemctl enable --now vpush-ima-restic-check.timer
systemctl enable --now vpush-ima-restic-prune.timer     # weekly; script keeps first-Sunday-only

systemctl enable --now vpush-ima-main-health.timer      # main VPS
systemctl enable --now vpush-ima-main-backup.timer
systemctl enable --now vpush-ima-main-restic-check.timer
```

Manual once:

```bash
systemctl start vpush-ima-storage-health.service
systemctl start vpush-ima-main-health.service
systemctl start vpush-ima-restic-backup.service
systemctl start vpush-ima-main-backup.service
systemctl start vpush-ima-restic-check.service
systemctl start vpush-ima-main-restic-check.service
FORCE_PRUNE=1 systemctl start vpush-ima-restic-prune.service
```

## Schedules

| Timer | Cadence |
|-------|---------|
| storage health | every 5 minutes |
| main health | every minute |
| archive backup | daily 04:30 local, `RandomizedDelaySec=1200` |
| main backup | daily 03:45 local, `RandomizedDelaySec=900` |
| archive check | Sunday 05:30 |
| main check | Sunday 06:00 |
| prune | Sunday 06:30 weekly + script first-Sunday guard |

Services use `UMask=0077` (scripts still force health JSON to `99:100` / `0640`), `NoNewPrivileges=true`, and bounded `TimeoutStartSec`.

## Logs

```bash
journalctl -u vpush-ima-storage-health.service -u vpush-ima-main-health.service -f
journalctl -u vpush-ima-restic-backup.service -u vpush-ima-main-backup.service
journalctl -t vpush-ima-main-health
```

Main health emits one `logger -p daemon.warning` journal event per state transition (including traffic warn/high bands), not once per minute.

## External monitor

Require an external HTTPS monitor for `https://vpush.net/healthz/ima-storage`. Alert on non-200. The monitor must not receive storage IPs or credentials.

## Restore checks

Archive: restore random PDF/TXT samples and confirm hashes.

Main control: restore into a temp dir, verify `/opt/vpush/.env` mode `0600`, confirm `FEISHU_CREDENTIAL_KEY` is present/non-empty **without printing its value**.

## Uninstall / rollback

```bash
systemctl disable --now vpush-ima-storage-health.timer vpush-ima-restic-backup.timer \
  vpush-ima-restic-check.timer vpush-ima-restic-prune.timer \
  vpush-ima-main-health.timer vpush-ima-main-backup.timer \
  vpush-ima-main-restic-check.timer || true
rm -f /etc/systemd/system/vpush-ima-*.service /etc/systemd/system/vpush-ima-*.timer
rm -rf /usr/local/lib/vpush-ima
systemctl daemon-reload
# Keep env files until credentials are rotated; then: shred -u /etc/vpush/ima-storage.env /etc/vpush/ima-main-backup.env
# Application rollback: unset IMA_ARCHIVE_ROOT and remount local archive data.
```
