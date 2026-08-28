# IMA Remote HDD Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move IMA PDF/TXT archives to a WireGuard-protected NFSv4 HDD VPS while keeping SQLite and IMA indexes local, degrading only knowledge-base file access when remote storage is unavailable, and backing the archive up to encrypted object storage.

**Architecture:** `ImaDocumentStore` keeps `manifest.json` and `state.json` under its existing local root and accepts an optional archive root for PDF/TXT paths. A small `ImaStorageStatus` reader consumes a host-generated local JSON status file before any archive I/O. Host systemd jobs probe WireGuard/NFS/capacity, storage-host jobs publish HDD/traffic/backup health, and Restic sends encrypted snapshots directly from the storage VPS to an independent S3-compatible bucket.

**Tech Stack:** Python 3.11, FastAPI, pytest, Docker Compose, WireGuard, NFSv4, systemd, Bash, Restic, vnstat, fio, rsync, ext4.

---

## File Map

**Application**

- Create `app/ima_storage.py`: parse and validate host-generated storage status, expose read/write availability decisions.
- Modify `app/ima_documents.py`: separate local index root from optional archive root and gate archive operations.
- Modify `app/main.py`: construct storage status/archive roots and expose the non-core storage health endpoint.
- Modify `app/api.py`: return 503 for unavailable PDF/TXT, include storage status in admin collector responses, and skip manual sync while blocked.
- Modify `app/static/app.js`: show concise IMA storage state in the existing collector status line.
- Modify `docker-compose.yml`: pass optional archive/status environment and bind mount for local deployments.
- Modify `docker-compose.prod.yml`: pass optional archive/status environment and bind mount production archive.
- Modify `.env.example`: document archive root and status path without secrets.

**Tests**

- Create `tests/test_ima_storage.py`: status parsing, staleness, marker and write/capacity decisions.
- Modify `tests/test_ima_documents.py`: separate roots, relative path compatibility, unavailable archive, failed partial writes, recovery.
- Modify `tests/test_ima_kb.py`: PDF/TXT 503 behavior and admin storage status.
- Modify `tests/test_api.py`: independent `/healthz/ima-storage` contract and unchanged `/healthz`.
- Modify `tests/test_frontend_interactions.py`: collector storage status rendering contract.

**Operations**

- Create `deploy/ima-storage/README.md`: exact provisioning, secret-file ownership, migration and rollback runbook.
- Create `deploy/ima-storage/storage-health.sh`: storage VPS health JSON generator.
- Create `deploy/ima-storage/main-health.sh`: main VPS WireGuard/NFS/status aggregator.
- Create `deploy/ima-storage/restic-backup.sh`: low-priority archive backup and success marker.
- Create `deploy/ima-storage/restic-main-backup.sh`: main VPS SQLite online snapshot plus encrypted control-data backup.
- Create `deploy/ima-storage/restic-maintain.sh`: weekly check or monthly retention/prune by argument.
- Create `deploy/ima-storage/vpush-ima-storage-health.service` and `.timer`: storage VPS 5-minute health job.
- Create `deploy/ima-storage/vpush-ima-main-health.service` and `.timer`: main VPS 1-minute aggregate health job.
- Create `deploy/ima-storage/vpush-ima-restic-backup.service` and `.timer`: daily archive backup.
- Create `deploy/ima-storage/vpush-ima-main-backup.service` and `.timer`: daily main VPS SQLite/index/config backup.
- Create `deploy/ima-storage/vpush-ima-restic-check.service` and `.timer`: weekly archive subset check.
- Create `deploy/ima-storage/vpush-ima-main-restic-check.service` and `.timer`: weekly main-control subset check.
- Create `deploy/ima-storage/vpush-ima-restic-prune.service` and `.timer`: monthly retention/prune.

## Task 1: Add Storage Status Model

**Files:**
- Create: `app/ima_storage.py`
- Create: `tests/test_ima_storage.py`

- [ ] **Step 1: Write failing status parser tests**

Cover these exact cases in `tests/test_ima_storage.py`:

```python
import json
import time

from app.ima_storage import ImaStorageStatus


def test_local_mode_is_available_without_status_file():
    status = ImaStorageStatus(None, remote=False)
    assert status.public()["status"] == "local"
    assert status.can_read() is True
    assert status.can_write() is True


def test_remote_status_is_stale_after_180_seconds(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({
        "checked_at": int(time.time()) - 181,
        "available": True,
        "writable": True,
        "used_percent": 10,
        "inode_percent": 1,
        "monthly_tx_bytes": 10,
        "capacity_blocked": False,
        "reason": "",
    }))
    status = ImaStorageStatus(path, remote=True)
    assert status.can_read() is False
    assert status.can_write() is False
    assert status.public()["status"] == "stale"


def test_remote_status_blocks_writes_but_allows_reads(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({
        "checked_at": int(time.time()),
        "available": True,
        "writable": True,
        "used_percent": 81,
        "inode_percent": 2,
        "monthly_tx_bytes": 100,
        "capacity_blocked": True,
        "reason": "capacity",
    }))
    status = ImaStorageStatus(path, remote=True)
    assert status.can_read() is True
    assert status.can_write() is False
    assert status.public()["status"] == "capacity_blocked"
```

Also test missing file, invalid JSON, booleans supplied as strings, negative percentages, future timestamps over five minutes, and that `public()` never includes paths, IPs, or credentials.

- [ ] **Step 2: Run the tests and verify the module is missing**

Run:

```bash
.venv/bin/python -m pytest tests/test_ima_storage.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.ima_storage'`.

- [ ] **Step 3: Implement the minimal status reader**

Create `app/ima_storage.py` with:

```python
class ImaStorageStatus:
    STALE_SECONDS = 180

    def __init__(self, path: str | Path | None, *, remote: bool): ...
    def load(self) -> dict[str, object]: ...
    def can_read(self) -> bool: ...
    def can_write(self) -> bool: ...
    def public(self) -> dict[str, object]: ...
```

Rules:

- Local mode always reads/writes and returns `status=local`.
- Remote mode requires a valid, fresh JSON object.
- Read requires `available is True`.
- Write additionally requires `writable is True` and `capacity_blocked is False`.
- Accept only actual JSON booleans; never use Python truthiness for external values.
- Clamp public percentages to 0-100 and bytes to non-negative integers.
- Public fields are exactly `status`, `available`, `writable`, `checked_at`, `used_percent`, `inode_percent`, `monthly_tx_bytes`, and `reason`.
- Return bounded reasons from a fixed allowlist: `missing`, `invalid`, `stale`, `unavailable`, `readonly`, `capacity`, or empty.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_ima_storage.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/ima_storage.py tests/test_ima_storage.py
git commit -m "feat: add IMA archive storage status"
```

## Task 2: Split Local Index and Remote Archive Roots

**Files:**
- Modify: `app/ima_documents.py:999-1358`
- Modify: `app/ima_documents.py:1617-1623`
- Modify: `app/ima_documents.py:1674-2000`
- Modify: `tests/test_ima_documents.py`

- [ ] **Step 1: Write failing separate-root tests**

Add tests that construct:

```python
index_root = tmp_path / "index"
archive_root = tmp_path / "archive"
marker = archive_root / ".vpush-ima-root"
archive_root.mkdir()
marker.touch()
status_path = tmp_path / "status.json"
```

Write a fresh available status and instantiate:

```python
status = ImaStorageStatus(status_path, remote=True)
store = ImaDocumentStore(index_root, archive_root=archive_root, storage_status=status)
```

Assert:

- `manifest.json` and `state.json` are created only under `index_root`.
- `pdf_path()` and `txt_path()` are under `archive_root`.
- state still stores existing relative names such as `0827/Report.pdf` or `7476629605476515__da8b115652fbc75e/unknown/Report.pdf`, never absolute paths.
- `_state_path()` resolves state paths against `archive_root`.
- a symlink archive root raises `ValueError`.
- a missing marker makes archive reads/writes unavailable without creating directories.
- local single-root construction keeps every current test path unchanged.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_ima_documents.py -k 'archive_root or separate_root or legacy_manifest' -q
```

Expected: failure because `ImaDocumentStore` does not accept `archive_root` or `storage_status`.

- [ ] **Step 3: Implement separate roots**

Change the constructor to:

```python
def __init__(
    self,
    root: str | Path,
    *,
    archive_root: str | Path | None = None,
    storage_status: ImaStorageStatus | None = None,
):
```

Implementation boundaries:

- `self.root` remains index root.
- `self.archive_root` defaults to `self.root`.
- `manifest_path`, `state_path`, `_load`, `_save`, `save_manifest`, and `save_state` remain local.
- `_safe_path`, `_archive_path`, `pdf_path`, `txt_path`, `_state_path`, PDF conversion, filename restoration, and file existence checks use `archive_root`.
- Split document metadata lookup from archive materialization: `document()` derives `has_pdf`/`has_txt` only from non-empty local state paths and must not resolve or `stat` the remote archive. Add a dedicated authorized archive-path method used only by PDF/TXT routes after the local storage status gate.
- Add `archive_readable()` and `archive_writable()` methods that combine `storage_status` and `.vpush-ima-root` checks only in remote mode.
- Never call `mkdir` under an unavailable remote archive.
- Use `path.relative_to(self.archive_root)` whenever storing PDF/TXT paths.
- Preserve current behavior when no separate root/status is passed.

- [ ] **Step 4: Gate sync and maintenance paths**

Change `ImaDocumentService.__init__` to accept and pass through the same keyword-only archive parameters:

```python
def __init__(
    self,
    db: Any,
    index_root: str | Path,
    *,
    archive_root: str | Path | None = None,
    storage_status: ImaStorageStatus | None = None,
):
```

In `ImaDocumentService`:

- Expose `self.storage_status: ImaStorageStatus` on `ImaDocumentService` and pass the same object to the store.
- Before starting manual or scheduled sync, return the bounded public status string: `storage_unavailable`, `storage_stale`, `storage_readonly`, or `capacity_blocked` when `archive_writable()` is false.
- During an active sync, recheck before each file so an outage does not begin another download.
- Skip startup filename restoration, manifest rebuilding that needs files, and retag file reads when archive is unavailable.
- Keep discovery and local manifest/state intact.
- Never clear a group manifest because storage was unavailable.

- [ ] **Step 5: Test partial-write failure and recovery**

Use a fake downloader that writes part of a file and raises `OSError`. Assert:

- final PDF does not exist;
- `.part` is removed;
- state does not mark the document complete;
- after status becomes available, a second sync succeeds using the same relative path.

- [ ] **Step 6: Run IMA document tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_ima_documents.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: separate IMA indexes from archive files"
```

## Task 3: Wire Storage Status Into the Application and API

**Files:**
- Modify: `app/main.py:80-86`
- Modify: `app/main.py:261-264`
- Modify: `app/api.py:2473-2898`
- Modify: `tests/test_api.py`
- Modify: `tests/test_ima_kb.py`

- [ ] **Step 1: Write failing application/API tests**

Add tests using `monkeypatch.setenv` before `create_app`:

```python
monkeypatch.setenv("IMA_ARCHIVE_ROOT", str(archive_root))
monkeypatch.setenv("IMA_STORAGE_STATUS_PATH", str(status_path))
```

Test contracts:

- `/healthz` remains `200 {"status":"ok"}` when archive status is missing.
- `/healthz/ima-storage` returns 503 with only non-sensitive public fields when unavailable.
- `/healthz/ima-storage` returns 200 when available.
- `GET /api/admin/ima-collector` includes `storage`.
- list/catalog/document-detail endpoints remain 200 during outage and document detail performs no remote path resolution or `stat`;
- PDF and TXT endpoints return 503, not 404, during outage;
- authenticated `Range: bytes=0-1023` against an available PDF returns 206, correct `Content-Range`, and exactly 1,024 response bytes;
- `POST /api/admin/ima-collector/sync` returns 503 with `知识库存储暂不可用` while blocked.

- [ ] **Step 2: Run tests and verify missing endpoint/status**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_api.py::test_healthz \
  tests/test_ima_kb.py -k 'storage or unavailable' -q
```

Expected: new assertions fail because storage status is not integrated.

- [ ] **Step 3: Construct the roots in `create_app`**

Use:

```python
index_root = Path(config.db_path).parent / "ima"
archive_env = os.environ.get("IMA_ARCHIVE_ROOT", "").strip()
archive_root = Path(archive_env) if archive_env else index_root
status_env = os.environ.get("IMA_STORAGE_STATUS_PATH", "").strip()
storage_status = ImaStorageStatus(status_env or None, remote=bool(archive_env))
ima_documents = ImaDocumentService(
    db,
    index_root,
    archive_root=archive_root,
    storage_status=storage_status,
)
```

Do not derive remote mode from whether the path currently exists.

- [ ] **Step 4: Add the independent health endpoint**

Add before the static catch-all:

```python
@app.get("/healthz/ima-storage")
def ima_storage_health(response: Response):
    payload = ima_documents.storage_status.public()
    if not ima_documents.store.archive_readable():
        response.status_code = 503
    return payload
```

Do not add archive status to `/healthz`.

- [ ] **Step 5: Add API gates**

- Add `storage` to `_ima_collector_status()`.
- In PDF/TXT endpoints, distinguish archive unavailable from an absent indexed file and return 503 first.
- In manual sync endpoint, translate all four blocked statuses (`storage_unavailable`, `storage_stale`, `storage_readonly`, `capacity_blocked`) into HTTP 503 with bounded Chinese messages, and parameterize tests across all four.
- Keep authentication and ACL checks before revealing whether a specific document exists.

- [ ] **Step 6: Run focused API tests**

```bash
.venv/bin/python -m pytest tests/test_api.py tests/test_ima_kb.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/api.py tests/test_api.py tests/test_ima_kb.py
git commit -m "feat: degrade IMA access when archive is offline"
```

## Task 4: Show Storage State in Existing Admin UI

**Files:**
- Modify: `app/static/app.js:6530-6548`
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write failing frontend contract tests**

Assert that `imaCollectorStatusText` handles:

- `storage.status === "unavailable"` as `知识库存储暂不可用`.
- `storage.status === "stale"` as `知识库存储状态过期`.
- `storage.status === "readonly"` as `知识库存储当前只读`.
- `storage.status === "capacity_blocked"` as `知识库存储空间已达限制`.
- available storage appends a compact percentage such as `存储 23%`.
- no storage field preserves old text exactly.

- [ ] **Step 2: Run the contract test and verify failure**

```bash
.venv/bin/python -m pytest \
  tests/test_frontend_interactions.py -k ima_collector_storage -q
```

Expected: failure because the function does not inspect `status.storage`.

- [ ] **Step 3: Implement the smallest UI change**

Update only `imaCollectorStatusText`; do not add a new panel, chart, dependency, CSS class, or polling loop. Existing `/api/admin/ima-collector` refreshes provide the status.

- [ ] **Step 4: Run frontend tests and syntax check**

```bash
.venv/bin/python -m pytest tests/test_frontend_interactions.py -q
node --check app/static/app.js
```

Expected: all tests and syntax check pass.

- [ ] **Step 5: Commit**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git commit -m "feat: show IMA archive health in admin status"
```

## Task 5: Add Compose and Environment Configuration

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/test_frontend_interactions.py` or a new narrow text-contract test in `tests/test_ima_storage.py`

- [ ] **Step 1: Add a failing compose contract test**

Read both compose files as text and assert they include:

```text
IMA_ARCHIVE_ROOT=${IMA_ARCHIVE_ROOT:-}
IMA_STORAGE_STATUS_PATH=${IMA_STORAGE_STATUS_PATH:-}
${IMA_ARCHIVE_HOST_PATH:-./data/ima}:/data/ima-archive
```

The empty default must preserve local development without requiring NFS.

- [ ] **Step 2: Run the contract test and verify failure**

```bash
.venv/bin/python -m pytest tests/test_ima_storage.py -k compose -q
```

Expected: failure because compose configuration is absent.

- [ ] **Step 3: Update compose files**

Add the two environment entries and one bind mount to `vpush` only. Do not mount the archive into `waf-bot` or Caddy.

Production `.env` values used later:

```text
IMA_ARCHIVE_ROOT=/data/ima-archive
IMA_STORAGE_STATUS_PATH=/data/ima_storage_status.json
IMA_ARCHIVE_HOST_PATH=/mnt/vpush-ima
```

Do not commit these production values into `.env.example`; document them as examples.

- [ ] **Step 4: Document operator behavior**

In README, state:

- separate archive root is optional;
- SQLite and indexes stay under `/data`;
- external archive must contain `.vpush-ima-root`;
- remote storage requires a fresh local status JSON;
- remote secrets do not belong in Compose or Git.

- [ ] **Step 5: Validate compose**

Run:

```bash
docker compose -f docker-compose.yml config >/tmp/vpush-compose.yml
docker compose -f docker-compose.prod.yml config >/tmp/vpush-compose-prod.yml
.venv/bin/python -m pytest tests/test_ima_storage.py -k compose -q
```

Expected: both compose commands exit 0 and tests pass.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml docker-compose.prod.yml .env.example README.md tests/test_ima_storage.py
git commit -m "chore: configure external IMA archive mount"
```

## Task 6: Add Host Health and Restic Operations

**Files:**
- Create: `deploy/ima-storage/storage-health.sh`
- Create: `deploy/ima-storage/main-health.sh`
- Create: `deploy/ima-storage/restic-backup.sh`
- Create: `deploy/ima-storage/restic-main-backup.sh`
- Create: `deploy/ima-storage/restic-maintain.sh`
- Create: `deploy/ima-storage/vpush-ima-storage-health.service`
- Create: `deploy/ima-storage/vpush-ima-storage-health.timer`
- Create: `deploy/ima-storage/vpush-ima-main-health.service`
- Create: `deploy/ima-storage/vpush-ima-main-health.timer`
- Create: `deploy/ima-storage/vpush-ima-restic-backup.service`
- Create: `deploy/ima-storage/vpush-ima-restic-backup.timer`
- Create: `deploy/ima-storage/vpush-ima-main-backup.service`
- Create: `deploy/ima-storage/vpush-ima-main-backup.timer`
- Create: `deploy/ima-storage/vpush-ima-restic-check.service`
- Create: `deploy/ima-storage/vpush-ima-restic-check.timer`
- Create: `deploy/ima-storage/vpush-ima-main-restic-check.service`
- Create: `deploy/ima-storage/vpush-ima-main-restic-check.timer`
- Create: `deploy/ima-storage/vpush-ima-restic-prune.service`
- Create: `deploy/ima-storage/vpush-ima-restic-prune.timer`
- Create: `deploy/ima-storage/README.md`
- Create: `tests/test_ima_storage_ops.py`

- [ ] **Step 1: Write failing static operation tests**

Test that:

- every shell script begins with `#!/bin/sh` or `#!/usr/bin/env bash` and `set -eu`;
- no script contains an IP address, private key, password, S3 key, or repository URL;
- each script declares one exact allowed root-only environment file: archive/storage scripts use `/etc/vpush/ima-storage.env`, while main control backup/check uses `/etc/vpush/ima-main-backup.env`;
- every health JSON final file is owner `99:100`, mode `0640`, even though the systemd service has `UMask=0077`;
- root/all-squashed NFS tests and migration commands work through `all_squash,anonuid=99,anongid=100`;
- backup invokes `nice`, `ionice`, and Restic upload limit;
- main backup runs `scripts/backup.py` before Restic and never copies an open SQLite file directly;
- main backup fails closed unless `/opt/vpush/.env` is owned by `root:root` with mode `0600`;
- archive and main backups use distinct repository prefixes or credentials;
- timers use `Persistent=true` and randomized delay;
- health scripts use fixed exit semantics: probe failures still write status JSON, configuration errors exit nonzero;
- main health logs one journal event per state transition instead of once per minute;
- systemd services use `UMask=0077`, `NoNewPrivileges=true`, and bounded `TimeoutStartSec`.

- [ ] **Step 2: Run tests and verify files are missing**

```bash
.venv/bin/python -m pytest tests/test_ima_storage_ops.py -q
```

Expected: failures for missing deployment artifacts.

- [ ] **Step 3: Implement `storage-health.sh`**

Inputs from `/etc/vpush/ima-storage.env`:

```text
ARCHIVE_ROOT=/srv/vpush-ima
RESTIC_SUCCESS_FILE=/var/lib/vpush-ima/restic-last-success
RESTIC_CHECK_FILE=/var/lib/vpush-ima/restic-last-check
```

Produce `.vpush-storage-health.json` containing checked time, writable state, filesystem percentages, vnstat monthly transmit bytes, backup timestamps, and bounded reason. Use only standard tools plus `vnstat --json` parsed by `python3 -c`; do not parse human-formatted units. Before atomic rename, set temp and final files to owner `99:100`, mode `0640`.

- [ ] **Step 4: Implement `main-health.sh`**

Inputs:

```text
WG_INTERFACE=wg-vpush-ima
STORAGE_WG_IP=10.80.0.2
ARCHIVE_MOUNT=/mnt/vpush-ima
STATUS_OUTPUT=/opt/vpush/data/ima_storage_status.json
COMPOSE_DIR=/opt/vpush
```

Checks:

- latest WireGuard handshake is no older than 180 seconds when traffic is expected;
- `timeout 5 nc -z 10.80.0.2 2049` succeeds;
- mountpoint and both remote marker/health JSON exist;
- remote health is no older than 10 minutes;
- capacity block is true at filesystem or inode 80% and above;
- monthly traffic produces warnings at 1.2 TB and 1.6 TB but blocks no reads/writes;
- missing archive never creates `.vpush-ima-root` locally;
- aggregate status is written atomically to `/opt/vpush/data` with owner `99:100`, mode `0640` so the UID 99 container can read it;
- when the archive is reachable but not mounted, run `mount /mnt/vpush-ima` before declaring recovery;
- compare the new bounded status/reason with `/var/lib/vpush-ima/main-health-last`; on change, write exactly one `logger -p daemon.warning` transition event, and write one recovery event when healthy again.

For failed-mount boot recovery, use `/run/vpush-ima-placeholder`. If the container is running while `/mnt/vpush-ima` is not a mountpoint, create the marker. When NFS becomes reachable, explicitly mount it, then run `docker compose up -d --no-deps --force-recreate vpush`; remove the marker only after the recreated container reports healthy and `/healthz/ima-storage` succeeds.

- [ ] **Step 5: Implement Restic scripts**

`restic-backup.sh`:

```bash
nice -n 10 ionice -c2 -n7 restic backup "$ARCHIVE_ROOT" \
  --tag ima-archive --limit-upload 20480
```

On success write the epoch to `RESTIC_SUCCESS_FILE` atomically.

`restic-maintain.sh` accepts only an action (`check` or `prune`) and one of the two exact environment file paths. `check` runs Restic and always atomically writes JSON containing `checked_at` and `ok` before returning the original Restic exit code:

```bash
restic check --read-data-subset=5%
```

`restic-maintain.sh prune` runs:

```bash
restic forget --tag ima-archive --keep-daily 30 --prune
```

On every check attempt write the success/failure JSON to `RESTIC_CHECK_FILE`; never leave an old success looking current after failure. Never echo repository credentials.

`restic-main-backup.sh` runs the existing online SQLite backup helper first:

```bash
python3 /opt/vpush/src/scripts/backup.py \
  /opt/vpush/data/dav.db /opt/vpush/data/backups 30
```

It verifies the helper exited successfully, then runs Restic with tag `ima-control` over these explicit paths:

```text
/opt/vpush/data/backups
/opt/vpush/data/ima/manifest.json
/opt/vpush/data/ima/state.json
/opt/vpush/docker-compose.yml
/opt/vpush/.env
/opt/vpush/config.yaml
/etc/systemd/system/vpush-ima-*.service
/etc/systemd/system/vpush-ima-*.timer
/etc/wireguard/wg-vpush-ima.conf
/etc/fstab
```

The main backup uses `/etc/vpush/ima-main-backup.env`, a repository prefix separate from the archive repository, and records its own success epoch under `/var/lib/vpush-ima/main-restic-last-success`. Before SQLite backup it verifies `/opt/vpush/.env` exists, is owned by `root:root`, and has mode `0600`; any drift aborts the job. Missing optional index/config files are logged and skipped; `/opt/vpush/.env` is mandatory and a failed SQLite online backup aborts Restic. Restore tests verify `.env` mode `0600` and `FEISHU_CREDENTIAL_KEY` is present without printing its value.

- [ ] **Step 6: Add systemd units and runbook**

Timers:

- storage health: every 5 minutes;
- main health: every minute;
- archive backup: daily at 04:30 local with 20-minute randomized delay;
- main control-data backup: daily at 03:45 local with 15-minute randomized delay;
- archive check: Sunday 05:30;
- main control-data check: Sunday 06:00;
- prune: first Sunday of month at 06:30, documented manual enable because `OnCalendar` month/week expression varies across systemd versions; use a weekly timer plus script date guard.

README must include exact package names, install paths, file owners/modes, enable commands, log commands, and uninstall/rollback commands. It must also require an external HTTPS monitor for `https://vpush.net/healthz/ima-storage`; the monitor alerts on non-200 without receiving storage IPs or credentials. Secret values are gathered interactively during execution and written using `install -m 600 /dev/null /etc/vpush/ima-storage.env` plus a root editor; do not show them in shell history.

- [ ] **Step 7: Validate operations artifacts**

```bash
shellcheck deploy/ima-storage/*.sh
.venv/bin/python -m pytest tests/test_ima_storage_ops.py -q
```

Expected: shellcheck and tests pass. If shellcheck is not installed locally, install it before this validation rather than skipping.

- [ ] **Step 8: Commit**

```bash
git add deploy/ima-storage tests/test_ima_storage_ops.py
git commit -m "ops: add IMA remote storage services"
```

## Task 7: Run Complete Local Verification

**Files:** all modified implementation files

- [ ] **Step 1: Run focused storage and IMA tests**

```bash
.venv/bin/python -m pytest \
  tests/test_ima_storage.py \
  tests/test_ima_storage_ops.py \
  tests/test_ima_documents.py \
  tests/test_ima_kb.py \
  tests/test_api.py -q
```

Expected: all pass.

- [ ] **Step 2: Run frontend and static checks**

```bash
.venv/bin/python -m pytest tests/test_frontend_interactions.py -q
node --check app/static/app.js
node --check app/static/sw.js
git diff --check
```

Expected: all pass with no output from syntax/diff checks.

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Request independent code review**

Review priorities:

- no archive path can escape `archive_root`;
- outage paths cannot clear local indexes;
- ACL checks occur before document existence/storage disclosure;
- no remote secret enters repository or logs;
- default local deployment is unchanged;
- no synchronous NFS probe occurs in normal list/API paths.

Apply confirmed findings, stage the explicit files shown by `git status --short`, review `git diff --cached`, and rerun Steps 1-3 before committing:

```bash
git diff --cached --check
git commit -m "fix: harden IMA remote storage failure handling"
```

Expected: no commit when review finds no changes.

## Task 8: Release Backward-Compatible Application Changes

**Files:**
- Modify release version files only according to `.cursor/skills/vpush-release-deploy/SKILL.md` (`name: vpush-release-deploy`).

- [ ] **Step 1: Confirm defaults are inert**

On the current main VPS, confirm production `.env` does not yet define `IMA_ARCHIVE_ROOT`. Deploying this release must continue using `/data/ima` locally.

- [ ] **Step 2: Publish the next patch release**

Follow the repository release process exactly:

- increment `app/version.py` and `app/static/app.js` together;
- increment `app.js?v=` and service worker cache because JS changed;
- run required tests and checks;
- push `main`, create the next tag and GitHub Release;
- deploy the next patch using the repo-local `vpush-release-deploy` skill while archive environment remains unset;
- verify container healthy and existing IMA files readable.

- [ ] **Step 3: Record release evidence**

Save release URL, CI run URL, deployed version, container health, public health, and a random PDF/TXT read result in the deployment log. Do not enable remote storage yet.

## Task 9: Provision the Storage VPS

**Files:** remote host only; no repository secrets

- [ ] **Step 1: Collect live values interactively**

At execution time ask the operator for:

- storage VPS public IP;
- storage VPS SSH key path;
- main VPS and storage VPS WireGuard private/public keys;
- archive Restic repository URL/password;
- main control-data Restic repository URL/password using a distinct bucket prefix or repository;
- S3 endpoint, access key and secret key;

Do not place these values in chat logs, command arguments, Git, Compose, screenshots, or task output. Transfer secret files over SSH stdin and chmod 600.

- [ ] **Step 2: Inspect the storage host before formatting anything**

Run read-only:

```bash
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,MODEL
findmnt --real
df -hT
free -h
uname -a
```

Expected: identify the 1 TB data device unambiguously. If the OS and data share one partition, do not format; create `/srv/vpush-ima` on the existing ext4 filesystem. Format only an empty dedicated data device explicitly confirmed by the operator.

- [ ] **Step 3: Install packages and base controls**

For Debian/Ubuntu:

```bash
apt-get update
apt-get install -y wireguard nfs-kernel-server restic vnstat fio rsync jq smartmontools
fallocate -l 1G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
sysctl -w vm.swappiness=10
```

Persist swap and swappiness once, avoiding duplicate lines. Expected: services installed and swap active.

- [ ] **Step 4: Configure data directory and permissions**

Create `/srv/vpush-ima`, set owner `99:100`, mode `0750`, create `.vpush-ima-root` explicitly as owner `99:100` and mode `0640`, and confirm the path is on the intended HDD using `findmnt -T /srv/vpush-ima`.

- [ ] **Step 5: Configure WireGuard and firewall**

Use `10.80.0.2/30` on storage and `10.80.0.1/30` on main. Allow NFS only from `10.80.0.1`; block public TCP/UDP 2049. Validate:

```bash
wg show
ping -c 3 10.80.0.1
ss -lntup | grep ':2049'
```

Expected: fresh handshake, private ping succeeds, and NFS is unreachable from an unrelated public host.

- [ ] **Step 6: Configure NFS export**

Add exactly one export:

```text
/srv/vpush-ima 10.80.0.1(rw,sync,all_squash,anonuid=99,anongid=100,no_subtree_check,fsid=10)
```

Run:

```bash
exportfs -rav
exportfs -v
```

Expected: only the WireGuard client is authorized for this export.

- [ ] **Step 7: Install storage health and Restic units**

Copy reviewed artifacts to `/usr/local/lib/vpush-ima` and `/etc/systemd/system`, create `/etc/vpush/ima-storage.env` mode 0600, initialize Restic, enable storage health/backup/check/prune timers, and run each service manually once.

Expected:

- `.vpush-storage-health.json` is valid JSON;
- first Restic backup succeeds;
- Restic snapshots include tag `ima-archive`;
- random empty test directory restores successfully.

## Task 10: Provision the Main VPS Mount and Status Probe

**Files:** main production host only

- [ ] **Step 1: Install main-host client tools**

For Debian/Ubuntu:

```bash
apt-get update
apt-get install -y wireguard-tools nfs-common netcat-openbsd fio rsync jq
```

Expected: `wg`, `mount.nfs4`, `nc`, `fio`, `rsync`, and `jq` are available.

- [ ] **Step 2: Create mountpoint without hiding data**

Create `/mnt/vpush-ima` as root mode `0750`. Do not mount over `/opt/vpush/data/ima`.

- [ ] **Step 3: Add the NFS mount**

Add to `/etc/fstab`:

```text
10.80.0.2:/srv/vpush-ima /mnt/vpush-ima nfs4 nfsvers=4.2,proto=tcp,soft,timeo=50,retrans=2,rsize=1048576,wsize=1048576,noatime,_netdev,nofail,x-systemd.device-timeout=10s 0 0
```

Run:

```bash
systemctl daemon-reload
mount /mnt/vpush-ima
mountpoint -q /mnt/vpush-ima
test -f /mnt/vpush-ima/.vpush-ima-root
```

Expected: all commands succeed. Confirm there is no `x-systemd.automount` or idle unmount; the health watcher owns explicit recovery mounts.

- [ ] **Step 4: Validate UID/GID and POSIX operations as container user**

Run in a temporary container with `--user 99:100` and the mount bound at `/archive`:

- create a directory;
- write a PDF-like test file;
- rename it in place;
- read it;
- delete it.

Expected: every operation succeeds without `chmod 777` or `no_root_squash`.

- [ ] **Step 5: Run baseline performance tests**

Run:

```bash
fio --name=seqwrite --filename=/mnt/vpush-ima/.fio-test \
  --size=1G --rw=write --bs=1M --direct=1 --iodepth=4
fio --name=seqread --filename=/mnt/vpush-ima/.fio-test \
  --size=1G --rw=read --bs=1M --direct=1 --iodepth=4
fio --name=parallel-read --filename=/mnt/vpush-ima/.fio-test \
  --size=1G --rw=read --bs=1M --numjobs=10 --iodepth=2
rm -f /mnt/vpush-ima/.fio-test
```

Record bandwidth, latency and errors. Acceptance is no I/O errors and aggregate read throughput sufficient for ten concurrent expected PDFs; if aggregate throughput is below 40 MB/s or p95 1 MB read latency exceeds 250 ms, investigate network/HDD before migration.

- [ ] **Step 6: Install and enable main health and backup units**

Install main health, main Restic backup and main Restic check units. Before the first backup run:

```bash
chown root:root /opt/vpush/.env
chmod 600 /opt/vpush/.env
test "$(stat -c '%U:%G:%a' /opt/vpush/.env)" = root:root:600
```

Create `/etc/vpush/ima-main-backup.env` as root mode `0600`, initialize its distinct Restic repository, run one online SQLite/control backup and one subset check, then run main health once and validate `/opt/vpush/data/ima_storage_status.json` with `jq`.

Expected: `available=true`, `writable=true`, accurate capacity/traffic values, a tagged `ima-control` Restic snapshot, and a successful main repository subset check. Configure an external HTTPS monitor against `/healthz/ima-storage` after the application switch; until then verify journal transition events with `journalctl -u vpush-ima-main-health.service`.

## Task 11: Two-Phase Archive Migration

**Files:** production data only

- [ ] **Step 1: Capture pre-migration inventory**

On main VPS record:

```bash
find /opt/vpush/data/ima -type f -print0 | sort -z | xargs -0 sha256sum > /root/ima-before.sha256
du -sb /opt/vpush/data/ima
find /opt/vpush/data/ima -type f -iname '*.pdf' | wc -l
find /opt/vpush/data/ima -type f -iname '*.txt' | wc -l
```

Store the inventory root-only. Do not output document names into public logs.

- [ ] **Step 2: Run online first pass**

Use rsync from main to mounted storage, excluding only local indexes and markers:

```bash
rsync -rltH --info=progress2 \
  --exclude=/manifest.json --exclude=/state.json \
  --exclude=/.vpush-ima-root --exclude=/.vpush-storage-health.json \
  /opt/vpush/data/ima/ /mnt/vpush-ima/
```

Expected: current archive directories copy while V Push remains online.

- [ ] **Step 3: Enter maintenance window and back up control data**

- stop new IMA sync;
- stop `vpush` cleanly;
- use `scripts/backup.py` or `DB.online_backup` to create a quick-checked SQLite backup;
- copy manifest/state to `/opt/vpush/data/backups` with timestamp and mode 0600.

Expected: container stopped and verified backups exist.

- [ ] **Step 4: Run guarded final rsync and checksum dry-run**

While V Push is stopped, validate the target before allowing deletion:

```bash
test "$(findmnt -n -o FSTYPE --target /mnt/vpush-ima)" = nfs4
test "$(findmnt -n -o TARGET --target /mnt/vpush-ima)" = /mnt/vpush-ima
test -f /mnt/vpush-ima/.vpush-ima-root
test "$(stat -c '%u:%g:%a' /mnt/vpush-ima/.vpush-ima-root)" = 99:100:640
```

Then reconcile destination-only names left by the online pass:

```bash
rsync -rltHc --delete \
  --exclude=/manifest.json --exclude=/state.json \
  --exclude=/.vpush-ima-root --exclude=/.vpush-storage-health.json \
  /opt/vpush/data/ima/ /mnt/vpush-ima/
rsync -rltHnc --delete \
  --exclude=/manifest.json --exclude=/state.json \
  --exclude=/.vpush-ima-root --exclude=/.vpush-storage-health.json \
  /opt/vpush/data/ima/ /mnt/vpush-ima/
```

Expected: the second command has no file differences. Never run the deleting transfer unless all four target guards pass.

- [ ] **Step 5: Preserve local rollback copy and local indexes**

Set `stamp=$(date +%Y%m%d-%H%M%S)` and rename local `/opt/vpush/data/ima` to `/opt/vpush/data/ima-local-rollback-$stamp`. Write that exact path to `/root/vpush-ima-rollback-path`, create a new `/opt/vpush/data/ima`, copy only manifest/state into it, set ownership/modes to match the container, and retain the rollback path for seven days.

- [ ] **Step 6: Enable remote archive environment and mount**

Add production `.env` values from Task 5, ensure the NFS mount and status JSON are healthy, then recreate only `vpush` with Compose.

Expected: container `running healthy`, `/healthz` 200, `/healthz/ima-storage` 200.

## Task 12: Production Acceptance and Fault Exercise

**Files:** production only

- [ ] **Step 1: Verify indexes and random documents**

Compare pre/post document counts, groups, dates, tags and ACL-visible catalogs. Randomly select 10 indexed records without printing names publicly; read TXT and PDF, verify PDF header and state MD5/size when present.

- [ ] **Step 2: Verify HTTP Range and ten concurrent readers**

Use authenticated requests for 10 different PDFs where available. Require:

- `Range: bytes=0-1023` returns HTTP 206;
- `Content-Range` identifies bytes 0-1023 and total size;
- response body is exactly 1,024 bytes;
- no 5xx while storage is healthy;
- record time-to-first-byte and complete throughput;
- main VPS CPU remains below 80% over the 10-reader sample;
- storage VPS load average remains below 1.5 and available memory stays above 200 MB;
- HDD `await` stays below 100 ms averaged over the sample;
- capture `nfsstat -c` before and after the sample; retransmissions added during the sample remain below 1% of added RPC calls;
- kernel and application logs contain zero NFS I/O errors.

- [ ] **Step 3: Run a small incremental IMA sync**

Mount one small folder or wait for one new file, trigger sync, and verify:

- PDF/TXT appears only under `/mnt/vpush-ima`;
- manifest/state update only under `/opt/vpush/data/ima`;
- no archive file appears in the new local index root;
- second sync downloads nothing already complete.

- [ ] **Step 4: Exercise storage outage**

During an approved maintenance window, block NFS over WireGuard or stop NFS briefly. Confirm within bounded retry/status windows:

- `/healthz` remains 200;
- `/healthz/ima-storage` returns 503;
- PDF/TXT returns 503 after ACL authorization;
- list/catalog, push scheduler and unrelated APIs remain available;
- IMA sync skips without clearing indexes or creating local archive files.

Restore NFS and confirm health endpoint, document reads and next sync recover.

- [ ] **Step 5: Verify backup and restore**

After first full Restic snapshot:

- restore random 10 PDF/TXT pairs to a temporary directory;
- restore the main VPS index/control snapshot separately;
- verify restored `.env` mode is `0600` and `FEISHU_CREDENTIAL_KEY` is non-empty without displaying its value;
- compare SHA-256 against online files;
- delete the temporary restore only after all matches pass.

- [ ] **Step 6: Exercise rollback and return to remote storage**

Perform one controlled rollback during the approved maintenance window:

1. Stop V Push and back up current SQLite, manifest and state.
2. Set `rollback=$(cat /root/vpush-ima-rollback-path)`; verify it is a real directory under `/opt/vpush/data`, not a symlink or mountpoint.
3. Rsync remote archive additions into that directory with `rsync -rltH --chown=99:100`, excluding both health markers; verify `find "$rollback" \( ! -user 99 -o ! -group 100 \) -print -quit` returns no path before continuing.
4. Copy the current local `manifest.json` and `state.json` into the rollback directory with owner `99:100`; do not reuse the cutover-time copies.
5. Set `stamp=$(date +%Y%m%d-%H%M%S)`, move the current index-only `/opt/vpush/data/ima` to `/opt/vpush/data/ima-remote-index-$stamp`, and record that path in `/root/vpush-ima-remote-index-path`.
6. Move the verified rollback directory to `/opt/vpush/data/ima`, remove archive environment values, force-recreate V Push, and verify at least one record created after cutover has metadata, TXT and PDF.
7. Stop V Push, move `/opt/vpush/data/ima` back to the exact rollback path recorded in `/root/vpush-ima-rollback-path`, then move the exact saved index-only directory back to `/opt/vpush/data/ima`.
8. Restore archive environment values, ensure NFS is mounted, force-recreate V Push, and remove `/root/vpush-ima-remote-index-path` only after success.
9. Reverify core/storage health and the same post-cutover record.

Expected: both rollback and return-to-remote paths pass without losing post-cutover tags, translations, completion state, or files.

- [ ] **Step 7: Start the seven-day observation window**

Record:

- application release and commit;
- mount options;
- archive size/counts;
- storage health;
- first backup/check result;
- performance results;
- rollback directory path and earliest deletion date.

Do not delete local rollback data yet.

## Task 13: Finalize After Seven Stable Days

**Files:** production only

- [ ] **Step 1: Audit observation evidence**

Require all of:

- no unresolved NFS/storage errors;
- no unexpected IMA 5xx while storage was healthy;
- capacity below 70%;
- monthly transfer below 60% threshold or explained;
- at least seven successful daily Restic snapshots;
- successful subset check and random restore;
- incremental IMA sync remains idempotent.

- [ ] **Step 2: Take a final rollback backup**

Create a fresh main SQLite/index backup and verify Restic snapshot before deleting local archive rollback data.

- [ ] **Step 3: Remove only the timestamped rollback archive**

Resolve the exact rollback path, verify it is under `/opt/vpush/data/`, verify it is not a mountpoint or symlink, print its size for operator approval, then remove that exact path. Never glob `ima*` and never touch `/opt/vpush/data/ima`.

- [ ] **Step 4: Verify disk and service health**

Run:

```bash
df -h /opt/vpush/data
curl -fsS https://vpush.net/healthz
curl -fsS https://vpush.net/healthz/ima-storage
```

Expected: main disk space reclaimed, core and storage health return success.

- [ ] **Step 5: Close the implementation record**

Update the deployment record with final disk usage, Restic restore evidence, residual risks, and the explicit trigger for future JuiceFS/S3 reconsideration. Do not save credentials, IP-private topology, or document names.
