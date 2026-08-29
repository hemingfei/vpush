# 知识库设置页签与分库采集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Knowledge settings uses Collect / Zsxq / Storage tabs; each library has a 1h/6h/24h interval; live sync progress shows in the footer; unused IMA cookie/OpenAPI/UID/token fields leave this page.

**Architecture:** Persist `interval_seconds` on existing `ima_pure_groups`. Track per-group last start in settings key `ima_pure_group_runtime`. Scheduled sync only runs due mounted libraries. Manual sync from this page POSTs `{group_id}`. Progress is an in-memory snapshot on `GET /admin/ima-collector`; the page polls it every 2s without redrawing the mount tree.

**Tech Stack:** Python 3, FastAPI, pytest source contracts, static SPA (`app.js` / `style.css`).

**Spec:** `docs/superpowers/specs/2026-08-29-knowledge-settings-tabs-design.md`

**Mock:** `work/ui-validation/knowledge-settings-mock-desktop.png` (do not commit `work/`)

---

## File Map

- Modify `app/ima_documents.py`: clamp interval, `ImaGroupConfig.interval_seconds`, runtime JSON, due filter, `trigger(group_id=)`, progress snapshot, `status()["progress"]`.
- Modify `app/api.py`: `POST /admin/ima-collector/sync` JSON body `{group_id?}`; 409 if unmounted.
- Modify `app/static/app.js`: tabs, remove cookie/UID/token/global interval markup, interval chips, `triggerImaCollector(group_id)`, 2s progress poll.
- Modify `app/static/style.css`: tabs, chips, progress bar, mobile chip wrap.
- Modify `app/static/index.html` + `app/static/sw.js`: cache/resource version.
- Modify `tests/test_ima_documents.py`: interval clamp, due groups, group_id sync, progress.
- Modify `tests/test_api.py` if collector PUT/sync contracts mention global interval.
- Modify `tests/test_frontend_interactions.py`: replace `ima-cookie` assertions; add tabs/chips/progress.

Do not add tables, WebSockets, or delete `ImaFetcher` / `/api/admin/ima-credentials`.

---

### Task 1: Per-library interval on `ImaGroupConfig`

**Files:**
- Modify: `app/ima_documents.py`
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write failing tests**

```python
from app.ima_documents import ImaGroupConfig, _clamp_group_interval, merge_groups


def test_clamp_group_interval_to_three_buckets():
    assert _clamp_group_interval(None) == 3600
    assert _clamp_group_interval(100) == 3600
    assert _clamp_group_interval(10799) == 3600
    assert _clamp_group_interval(10800) == 21600
    assert _clamp_group_interval(43199) == 21600
    assert _clamp_group_interval(43200) == 86400


def test_group_public_includes_interval(tmp_path):
    group = ImaGroupConfig("g", "库", "kb", "root", True, "discovered", (), 21600)
    assert group.public()["interval_seconds"] == 21600


def test_merge_groups_keeps_interval():
    existing = (ImaGroupConfig("g", "旧", "kb", "root", True, "discovered", ("f",), 86400),)
    discovered = (ImaGroupConfig("g", "新", "kb", "root", False, "discovered", ()),)
    merged = merge_groups(existing, discovered)
    assert merged[0].interval_seconds == 86400
    assert merged[0].name == "新"
```

If `ImaGroupConfig` construction in existing tests uses positional args, add `interval_seconds` as the last field with default `3600` so old calls still work.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py::test_clamp_group_interval_to_three_buckets tests/test_ima_documents.py::test_group_public_includes_interval tests/test_ima_documents.py::test_merge_groups_keeps_interval -q --tb=line`

Expected: FAIL (`_clamp_group_interval` missing)

- [ ] **Step 3: Implement**

In `app/ima_documents.py` next to `_interval`:

```python
IMA_GROUP_INTERVALS = (3600, 21600, 86400)


def _clamp_group_interval(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 3600
    if number < 10800:
        return 3600
    if number < 43200:
        return 21600
    return 86400
```

Add field `interval_seconds: int = 3600` on `ImaGroupConfig`. Include it in `public()`.

In `_read_groups` constructor and the legacy rewrite, pass `interval_seconds=_clamp_group_interval(item.get("interval_seconds"))`.

In `merge_groups`, copy `interval_seconds=previous.interval_seconds if previous else 3600`.

Every other `ImaGroupConfig(...)` in this file that lists fields explicitly must still compile (default covers them).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py -q --tb=line`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: store 1h/6h/24h interval on each IMA group"
```

---

### Task 2: Due groups and optional `group_id` sync

**Files:**
- Modify: `app/ima_documents.py` (`IMA_PURE_GROUP_RUNTIME_KEY`, `trigger`, `sync_once`)
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write failing tests**

Use the existing `FakeDB` + `ImaDocumentService` pattern from `test_sync_retries_get_media_after_pdf_http_403`.

```python
def test_scheduled_sync_skips_group_that_is_not_due(tmp_path, monkeypatch):
    # two mounted groups: a=3600 due, b=86400 started 1 hour ago
    # FakeClient.manifest records which group ids were listed
    # service.trigger(scheduled=True) then wait for worker
    # assert only group a was synced


def test_manual_sync_one_group_ignores_due_window(tmp_path, monkeypatch):
    # both groups started 1 minute ago
    # trigger(group_id="b") syncs only b
```

Helper: write `ima_pure_groups` with two enabled mounted groups; `ima_pure_group_runtime` `{"b": {"last_started_at": now-60}}`. Monkeypatch `ImaPureClient` like other sync tests.

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py::test_scheduled_sync_skips_group_that_is_not_due tests/test_ima_documents.py::test_manual_sync_one_group_ignores_due_window -q --tb=short`

Expected: FAIL (`trigger()` has no `group_id`)

- [ ] **Step 3: Implement**

```python
IMA_PURE_GROUP_RUNTIME_KEY = "ima_pure_group_runtime"
```

Add helpers on `ImaDocumentService`:

```python
def _group_runtime(self) -> dict[str, Any]:
    raw = self.db.get_setting(IMA_PURE_GROUP_RUNTIME_KEY) or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}

def _mark_group_runtime(self, group_id: str, *, started: bool) -> None:
    data = self._group_runtime()
    item = dict(data.get(group_id) or {})
    now = int(time.time())
    if started:
        item["last_started_at"] = now
    else:
        item["last_finished_at"] = now
    data[group_id] = item
    self.db.set_setting(IMA_PURE_GROUP_RUNTIME_KEY, json.dumps(data, ensure_ascii=False))

def _group_due(self, group: ImaGroupConfig, now: float) -> bool:
    item = self._group_runtime().get(group.id) or {}
    try:
        last = float(item.get("last_started_at") or 0)
    except (TypeError, ValueError):
        last = 0.0
    return (now - last) >= _clamp_group_interval(group.interval_seconds)
```

`trigger(self, scheduled: bool = False, group_id: str = "")`:

- Store `self._sync_group_id = group_id` under `_state_lock` before starting the worker.
- If `group_id`: skip the global `too_soon` check.
- If `scheduled`: `_next_run_at = now + max(1800, min((g.interval_seconds for g in mounted), default=3600))`.
- Manual full sync (no group_id) keeps current `too_soon` using `cfg.interval_seconds`.

`sync_once`: after `enabled_groups = [...]`:

```python
        requested = ""
        with self._state_lock:
            requested = self._sync_group_id
            self._sync_group_id = ""
        if requested:
            enabled_groups = [g for g in enabled_groups if g.id == requested]
        elif scheduled_flag:
            now = time.time()
            enabled_groups = [g for g in enabled_groups if self._group_due(g, now)]
```

Pass `scheduled` into `sync_once` via `self._sync_scheduled` set in `trigger`, or add an argument `_worker` already calls `sync_once()` — set `self._sync_scheduled` in `trigger`.

Before `_sync_group`, `_mark_group_runtime(group.id, started=True)`; after, `started=False` (finished).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py -q --tb=line`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: sync only due IMA libraries or one requested group"
```

---

### Task 3: Sync API accepts `group_id`

**Files:**
- Modify: `app/api.py` (`trigger_ima_collector`)
- Test: `tests/test_ima_kb.py` or `tests/test_api.py` (whichever already hits `/api/admin/ima-collector/sync`)

- [ ] **Step 1: Find the existing sync test and add**

```python
def test_ima_collector_sync_unknown_group_404(client, admin_headers):
    response = client.post("/api/admin/ima-collector/sync", json={"group_id": "missing"})
    assert response.status_code in (404, 409, 400)

def test_ima_collector_sync_unmounted_group_409(...):
    # group exists with folder_ids=[]
    assert response.status_code == 409
```

If the test client fixture name differs, copy from the nearest collector test.

- [ ] **Step 2: Run to fail**

Expected: current handler ignores JSON body, so unmounted group still returns 200/`started` or 429.

- [ ] **Step 3: Implement**

```python
class ImaCollectorSyncIn(BaseModel):
    group_id: str = ""

@router.post("/admin/ima-collector/sync", ...)
def trigger_ima_collector(body: ImaCollectorSyncIn | None = None, admin: dict = Depends(require_admin)):
    group_id = (body.group_id if body else "").strip()
    if group_id:
        group = next((item for item in _configured_groups() if item.id == group_id), None)
        if group is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        if not group.mount_folder_ids:
            raise HTTPException(status_code=409, detail="请先挂载该知识库")
    result = ima_documents.trigger(group_id=group_id)
    ...
```

FastAPI: optional body on POST can be `body: ImaCollectorSyncIn = Body(default_factory=ImaCollectorSyncIn)` so empty POST still works.

- [ ] **Step 4: Run related API tests**

Run: `.venv/bin/python -m pytest tests/test_ima_kb.py tests/test_api.py -q --tb=line -k ima`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api.py tests/test_ima_kb.py tests/test_api.py
git commit -m "feat: POST ima-collector/sync can target one library"
```

---

### Task 4: In-memory sync progress

**Files:**
- Modify: `app/ima_documents.py` (`status`, `_sync_group`)
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write failing test**

```python
def test_status_exposes_download_progress_while_running(tmp_path, monkeypatch):
    # FakeClient.download blocks until an Event is set
    # start sync, wait until status()["progress"]["phase"] == "download"
    # assert downloaded counts move; progress is None after finish
```

Keep it deterministic: FakeClient.manifest returns two PDFs; first download waits on `gate`. Assert `progress["pending"]==2` and `phase=="download"` before releasing.

- [ ] **Step 2: Run to fail**

Expected: `status()` has no `progress`

- [ ] **Step 3: Implement**

On the service:

```python
        self._progress: dict[str, Any] | None = None
```

```python
    def _set_progress(self, **fields: Any) -> None:
        with self._state_lock:
            current = dict(self._progress or {})
            current.update(fields)
            self._progress = current

    def status(self) -> dict[str, Any]:
        ...
        with self._state_lock:
            progress = None if not running else dict(self._progress or {})
        ...
        return {..., "progress": progress}
```

In `_sync_group` after listing, before downloads:

```python
        self._set_progress(
            group_id=group.id,
            group_name=group.name,
            phase="listing",
            listed=len(records),
            pending=0,
            downloaded=0,
            failed=0,
        )
```

After `pending = [...]`:

```python
        self._set_progress(phase="download", pending=len(pending), downloaded=0, failed=0)
```

Increment `downloaded`/`failed` in the `as_completed` loop via `_set_progress`. Clear `_progress = None` in `_worker` `finally` after setting `_running = False`.

Do not write progress to SQLite.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py -q --tb=line`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: expose live IMA sync progress on collector status"
```

---

### Task 5: Frontend source contracts

**Files:**
- Test: `tests/test_frontend_interactions.py`

Existing tests **will fail** once markup moves. Update them in this task **before** changing `app.js`, using the new contracts so TDD still holds.

- [ ] **Step 1: Change assertions that require the old form**

In `test_frontend_interactions.py`:

- `assert 'for="ima-cookie"' in knowledge` → **must not** appear in `loadAdminKnowledge`
- same for `ima-cid`, `ima-key`, `id="ima-pure-token"`, `id="ima-pure-interval"`, `id="ima-pure-uid"`
- `focusCookieField` may keep `ima-cookie` only if some other page still uses it; knowledge page must not call `saveImaCredentials`
- Add:

```python
def test_knowledge_settings_uses_collect_tabs_and_interval_chips():
    knowledge = _fn_body("loadAdminKnowledge")
    assert 'data-tab="collect"' in knowledge
    assert 'data-tab="zsxq"' in knowledge
    assert 'data-tab="storage"' in knowledge
    assert "ima-interval-seg" in knowledge
    assert "imaCollectorProgressHtml" in knowledge or "ima-sync-progress" in knowledge
    assert "saveImaCredentials()" not in knowledge
    save = _fn_body("saveImaCollector")
    assert "ima-pure-interval" not in save
    trigger = _fn_body("triggerImaCollector")
    assert "group_id" in trigger
```

Grep `ima-cookie` / `ima-pure-interval` / `saveImaCredentials` in this test file and update every knowledge-page assertion.

- [ ] **Step 2: Run to fail (old markup still present)**

Run: `.venv/bin/python -m pytest tests/test_frontend_interactions.py::test_knowledge_settings_uses_collect_tabs_and_interval_chips -q --tb=short`

Expected: FAIL

- [ ] **Step 3: No production code in this step if the new test is the only failure. If updating old tests made the suite fail on current `app.js`, that is intended — Task 6 makes them pass.**

- [ ] **Step 4: Commit tests first if the new test is additive; otherwise commit with Task 6.** Prefer one commit with Task 6 if many old assertions must flip.

---

### Task 6: Knowledge page markup and progress poll

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/style.css`
- Modify: `app/static/index.html`, `app/static/sw.js` (bump `?v=` and cache name)

- [ ] **Step 1: Confirm Task 5 tests fail against current JS**

- [ ] **Step 2: Implement UI**

`loadAdminKnowledge` root:

```html
<div class="knowledge-settings">
  <div class="ks-tabs" role="tablist">
    <button type="button" class="ks-tab is-on" data-tab="collect">采集</button>
    <button type="button" class="ks-tab" data-tab="zsxq">星球</button>
    <button type="button" class="ks-tab" data-tab="storage">存储</button>
  </div>
  <section class="section-panel ks-panel is-on" data-panel="collect"> ... mount ... footer ... </section>
  <section class="section-panel ks-panel" data-panel="zsxq"> ... existing zsxq blocks ... </section>
  <section class="section-panel ks-panel" data-panel="storage">${imaStoragePanelHtml(...)}</section>
</div>
```

Library row: keep `ima-mount-kb-row`; add

```html
<span class="ima-interval-seg" data-group-id="${id}">
  <button type="button" data-sec="3600">1h</button>
  <button type="button" data-sec="21600">6h</button>
  <button type="button" data-sec="86400">24h</button>
</span>
```

Selected chip gets `is-on`. Click must `stopPropagation` so it does not change the selected library. Store interval on the draft group object; `readImaMountGroups()` includes `interval_seconds`.

`saveImaCollector`: drop minutes validation and `uid` / `interval_seconds` / `refresh_token` from the PUT body. Still send `groups` (with `interval_seconds`) plus hidden kb/root if the API requires them — send current `pure.uid` / kb / root from status, not from inputs.

`triggerImaCollector`:

```javascript
const groupId = imaMountState.selectedId;
if (!groupId) { flash("请先选择知识库", "error"); return; }
await api("/api/admin/ima-collector/sync", { method: "POST", body: JSON.stringify({ group_id: groupId }) });
startImaProgressPoll();
```

Progress footer `#ima-collector-status` plus `#ima-sync-progress`:

```javascript
function imaCollectorProgressHtml(status) {
  const p = status.progress;
  if (!status.running || !p) return "";
  if (p.phase === "listing") {
    return `<div class="ima-progress"><div class="ima-progress-label">${escapeHtml(p.group_name || "")} · 列目录 ${Number(p.listed||0)}</div><div class="ima-progress-bar"><span style="width:15%"></span></div></div>`;
  }
  const total = Math.max(1, Number(p.pending || 0));
  const done = Number(p.downloaded || 0);
  const pct = Math.max(0, Math.min(100, Math.round(done * 100 / total)));
  return `<div class="ima-progress"><div class="ima-progress-label">${escapeHtml(p.group_name || "")} · 下载 ${done} / ${Number(p.pending||0)}</div><div class="ima-progress-bar"><span style="width:${pct}%"></span></div></div>`;
}
```

`startImaProgressPoll`: `setInterval` 2000ms, `GET /api/admin/ima-collector`, update `#ima-sync-progress` and disable `#ima-sync-btn` while `running`. **Do not** call `loadAdminKnowledge`. Clear interval when `running` is false and restore `imaCollectorStatusText`.

Tab click: toggle `.is-on` on `.ks-tab` / `.ks-panel`. Persist selected tab in `sessionStorage` key `ks-tab` so a stats refresh does not jump away if you later redraw; default `collect`.

Remove the IMA 凭证 block and the connection fields from this page only. Leave `saveImaCredentials` function in `app.js` for now (unused).

CSS: match mock — `.ks-tabs` flex gap 6px; `.ks-tab.is-on` accent fill; `.ima-interval-seg` pill; `@media (max-width: 800px)` library row stacks chips under the name (`grid-template-columns: 1fr`). Progress bar 8px, accent fill.

Bump `app.js?v=` and `style.css?v=` in `index.html`, and the SW cache name in `sw.js`.

- [ ] **Step 3: Run frontend + collector tests**

Run: `.venv/bin/python -m pytest tests/test_frontend_interactions.py tests/test_ima_documents.py tests/test_ima_kb.py -q --tb=line`

Expected: PASS

Run: `node --check app/static/app.js && node --check app/static/sw.js`

Expected: silent success

- [ ] **Step 4: Commit**

```bash
git add app/static/app.js app/static/style.css app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
git commit -m "feat: knowledge settings tabs, per-library interval, live sync progress"
```

---

### Task 7: Desktop/mobile check

**Files:** none committed from `work/`

- [ ] **Step 1:** `DAV_UI_ONLY=1` local server, Chrome 1440 and 390 screenshots of `/admin/knowledge`. Compare to `work/ui-validation/knowledge-settings-mock-desktop.png`. Cookie/OpenAPI/UID must be absent. Interval chips fully visible on 390.

- [ ] **Step 2:** Click 立即同步 on a mounted library; footer must show progress without resetting folder checkboxes.

- [ ] **Step 3:** If CSS spacing is off, fix in `style.css` and bump versions. Do not recommit screenshots.

---

## Spec coverage

| Spec | Task |
|------|------|
| Collect/Zsxq/Storage tabs | 6 |
| Remove cookie/OpenAPI/UID/token/global interval | 5, 6 |
| 1h/6h/24h on each library | 1, 6 |
| Save interval on `ima_pure_groups` | 1, 6 |
| Scheduled due-only sync | 2 |
| Manual sync current library | 2, 3, 6 |
| Live progress, 2s poll, no tree redraw | 4, 6 |
| No new tables / no WebSocket | all |
| Keep ima-credentials API | 6 (leave function) |

## Placeholder scan

No TBD. 403/NFS/storage-direct are out of scope.
