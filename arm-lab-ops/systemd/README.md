# ARM lab sync systemd samples

Lab-only units for Oracle-SJ-ARM. **Not** production compose. Copy onto the host; do not enable these on the public vpush VPS.

| Unit | Calendar | ExecStart |
|---|---|---|
| `vpush-ima-lab-sync.{service,timer}` | 10:30 Asia/Shanghai | host `bin/ima-lab-sync-all.sh` (already installed) |
| `vpush-cicc-lab-sync.{service,timer}` | 11:00 Asia/Shanghai | [`../bin/cicc-lab-sync.sh`](../bin/cicc-lab-sync.sh) |

Both wrappers default to `DRY_RUN=1` (`--dry-run`). Set `DRY_RUN=0` in the systemd unit for a real daily apply. IMA runs `scripts/ima_arm_lab_sync.py --enable` per allowlisted group; CICC runs `scripts/cicc_arm_lab_sync.py --enable --limit N`. `N` comes from `$CACHE_ROOT/ops-lab-settings.json` (`ima_limit_per_group` / `cicc_limit`) when present. CICC logs: `$CACHE_ROOT/logs/cicc-lab-sync-*.log`. Cookie path is host `secrets/cicc-cookies.txt` — never commit.

The ops panel can rewrite both timers' `OnCalendar` via [`../bin/apply-lab-sync-timers.sh`](../bin/apply-lab-sync-timers.sh) (drop-in). Sample calendars below are the pre-settings live values (10:30 / 11:00).

See [../README.md](../README.md) for install commands.
