# ARM lab sync systemd samples

Lab-only units for Oracle-SJ-ARM. **Not** production compose. Copy onto the host; do not enable these on the public vpush VPS.

| Unit | Calendar | ExecStart |
|---|---|---|
| `vpush-ima-lab-sync.{service,timer}` | 10:30 Asia/Shanghai | host `bin/ima-lab-sync-all.sh` (already installed) |
| `vpush-cicc-lab-sync.{service,timer}` | 11:00 Asia/Shanghai | [`../bin/cicc-lab-sync.sh`](../bin/cicc-lab-sync.sh) |

CICC wrapper runs `scripts/cicc_arm_lab_sync.py --enable --limit 3`. `DRY_RUN=1` (unit default) uses `--dry-run`; `DRY_RUN=0` uses `--apply`. Logs: `$CACHE_ROOT/logs/cicc-lab-sync-*.log`. Cookie path is host `secrets/cicc-cookies.txt` — never commit.

See [../README.md](../README.md) for install commands.
