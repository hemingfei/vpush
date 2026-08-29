# Knowledge Library Performance Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace repeated 35 MiB JSON scans on `/knowledge` with a rebuildable SQLite read model, batch collection-state writes, and parallel catalog/list loading while preserving JSON recovery and existing search behavior.

**Architecture:** `manifest.json` and `state.json` remain authoritative. `dav.db` gains document, tag, and index-meta tables that are rebuilt or incrementally updated by `ImaDocumentService`; API methods read SQLite whenever the read model is available and use the current store path only when no usable index exists. The browser keeps `/api/me` validation, then starts catalog and first-page requests together.

**Tech Stack:** Python 3.12, stdlib `sqlite3`/`json`/`threading`, FastAPI, vanilla JavaScript, pytest, Chrome, Docker Compose.

**Design:** `docs/superpowers/specs/2026-08-29-knowledge-performance-index-design.md`

---

## File Map

- Modify `app/db.py`: schema, transactional index writes, indexed list/catalog/detail queries, index metadata.
- Modify `app/ima_documents.py`: record-to-index projection, rebuild/fingerprint/fallback, batched state flush, status.
- Modify `app/api.py`: route list/catalog/detail/PDF/TXT through service read methods.
- Modify `app/ima_kb.py`: merge precomputed SQLite catalog statistics without expanding one row per document.
- Modify `app/static/app.js`: start catalog and first-page requests together; show index fallback status to administrators.
- Modify `app/static/index.html`: bump `app.js` asset version.
- Modify `app/static/sw.js`: bump shell cache version.
- Modify `tests/test_db.py`: migration, transactions, search, ordering, pagination, and literal wildcard tests.
- Modify `tests/test_ima_documents.py`: rebuild, fingerprint, fallback, batch flush, cancellation, and status tests.
- Modify `tests/test_ima_kb.py`: indexed API parity, ACL, reader path, and JSON fallback tests.
- Modify `tests/test_frontend_interactions.py`: parallel request and status-copy contracts.
- Create `scripts/benchmark_ima_knowledge.py`: authenticated 20-run latency report without printing credentials.

## Task 1: Create the SQLite read-model schema and atomic writers

**Files:**
- Modify: `app/db.py:502-514`
- Modify: `app/db.py:755-773`
- Modify: `app/db.py:1260-1440`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing migration and replacement tests**

Add tests that create a real `DB`, inspect table/index names, replace one group twice, and prove another group survives:

```python
def test_ima_document_index_schema_and_group_replace(tmp_path):
    db = DB(tmp_path / "index.sqlite")
    tables = {row["name"] for row in db._rows("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row["name"] for row in db._rows("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"ima_document_index", "ima_document_tags", "ima_document_index_meta"} <= tables
    assert {"idx_ima_doc_latest", "idx_ima_doc_group_latest", "idx_ima_doc_tag_group"} <= indexes

    db.replace_ima_document_group("g1", [_index_row("g1", "a", "0829")])
    db.replace_ima_document_group("g2", [_index_row("g2", "b", "0828")])
    db.replace_ima_document_group("g1", [_index_row("g1", "c", "0830")])

    assert {(row["group_id"], row["media_id"]) for row in db._rows(
        "SELECT group_id, media_id FROM ima_document_index"
    )} == {("g1", "c"), ("g2", "b")}
```

Define `_index_row()` in the test with every required field so no production defaults are hidden:

```python
def _index_row(group_id, media_id, day, *, name="研报.pdf", tags=None, abstract=""):
    tags = tags or []
    return {
        "group_id": group_id,
        "media_id": media_id,
        "day": day,
        "valid_day": int(day.isdigit() and len(day) == 4),
        "name": name,
        "group_name": group_id,
        "name_folded": name.casefold(),
        "metadata_folded": f"{group_id} {' '.join(tags)}".casefold(),
        "abstract": abstract,
        "abstract_folded": abstract.casefold(),
        "abstract_zh": "",
        "abstract_src_hash": "",
        "cover_url": "",
        "tags": tags,
        "size": 0,
        "chars": 0,
        "has_pdf": 0,
        "has_txt": 0,
        "pdf_path": "",
        "txt_path": "",
        "downloaded_at": "",
    }
```

- [ ] **Step 2: Run the tests and confirm the schema is absent**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_db.py -k ima_document_index_schema
```

Expected: FAIL because `ima_document_index` does not exist.

- [ ] **Step 3: Add schema and migration statements**

Add the same `CREATE TABLE/INDEX IF NOT EXISTS` definitions to `SCHEMA` and `_migrate()`:

```sql
CREATE TABLE IF NOT EXISTS ima_document_index (
    group_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    day TEXT NOT NULL DEFAULT 'unknown',
    valid_day INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL DEFAULT '',
    group_name TEXT NOT NULL DEFAULT '',
    name_folded TEXT NOT NULL DEFAULT '',
    metadata_folded TEXT NOT NULL DEFAULT '',
    abstract TEXT NOT NULL DEFAULT '',
    abstract_folded TEXT NOT NULL DEFAULT '',
    abstract_zh TEXT NOT NULL DEFAULT '',
    abstract_src_hash TEXT NOT NULL DEFAULT '',
    cover_url TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    size INTEGER NOT NULL DEFAULT 0,
    chars INTEGER NOT NULL DEFAULT 0,
    has_pdf INTEGER NOT NULL DEFAULT 0,
    has_txt INTEGER NOT NULL DEFAULT 0,
    pdf_path TEXT NOT NULL DEFAULT '',
    txt_path TEXT NOT NULL DEFAULT '',
    downloaded_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (group_id, media_id)
);
CREATE TABLE IF NOT EXISTS ima_document_tags (
    group_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (group_id, media_id, tag)
);
CREATE TABLE IF NOT EXISTS ima_document_index_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'fallback',
    fingerprint TEXT NOT NULL DEFAULT '',
    rebuilt_at TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    document_count INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ima_doc_latest
    ON ima_document_index(valid_day DESC, day DESC, name DESC);
CREATE INDEX IF NOT EXISTS idx_ima_doc_group_latest
    ON ima_document_index(group_id, valid_day DESC, day DESC, name DESC);
CREATE INDEX IF NOT EXISTS idx_ima_doc_tag_group
    ON ima_document_tags(tag, group_id);
CREATE INDEX IF NOT EXISTS idx_ima_doc_group_tag
    ON ima_document_tags(group_id, tag);
```

- [ ] **Step 4: Implement one transaction helper and the two write APIs**

Add `_insert_ima_document_rows()`, `replace_ima_document_group()`, and `replace_ima_document_index()` near the existing IMA ACL methods. Both public methods must hold `self._lock`, call `BEGIN`, delete/insert documents and tags, validate the final count, commit, and rollback on every exception.

Use one ordered column tuple and one SQL statement so group and full rebuild cannot drift:

```python
_IMA_INDEX_COLUMNS = (
    "group_id", "media_id", "day", "valid_day", "name", "group_name",
    "name_folded", "metadata_folded", "abstract", "abstract_folded",
    "abstract_zh", "abstract_src_hash", "cover_url", "tags_json", "size",
    "chars", "has_pdf", "has_txt", "pdf_path", "txt_path", "downloaded_at",
)
```

`replace_ima_document_group(group_id, rows)` deletes only that group's tag and document rows. `replace_ima_document_index(rows, fingerprint, duration_ms)` replaces all rows and updates meta to `ready` only after `SELECT COUNT(*)` equals `len(rows)`.

- [ ] **Step 5: Implement incremental batch updates and meta status**

Add `update_ima_document_batch(self, rows: list[dict], fingerprint: str) -> int`, `ima_document_index_meta(self) -> dict`, and `mark_ima_document_index(self, status: str, *, error: str = "") -> None`.

Use this exact status validation at the start of `mark_ima_document_index()`:

```python
allowed = {"ready", "rebuilding", "fallback", "failed"}
if status not in allowed:
    raise ValueError("invalid IMA document index status")
```

`update_ima_document_batch()` uses `INSERT ... ON CONFLICT(group_id, media_id) DO UPDATE`, replaces tags only for touched keys, updates the fingerprint after rows succeed, and returns the touched count. `ima_document_index_meta()` returns the single meta row with typed integer count/duration fields and fallback defaults when no row exists.

- [ ] **Step 6: Run focused and DB regression tests**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_db.py -k 'ima_document_index or ima_document_group'
PYTHONPATH=. .venv/bin/pytest -q tests/test_db.py
```

Expected: all selected tests, then the complete DB file, PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: add IMA document read model"
```

## Task 2: Add indexed list, catalog, detail, and search queries

**Files:**
- Modify: `app/db.py:1260-1440`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing query-parity tests**

Create rows covering title, tag/source, abstract, unknown date, duplicate media IDs in different groups, and literal wildcard characters. Assert:

```python
def test_ima_document_index_search_ranking_and_literal_wildcards(tmp_path):
    db = DB(tmp_path / "search.sqlite")
    db.replace_ima_document_index([
        _index_row("semi", "title", "0828", name="全球 AI 展望.pdf"),
        _index_row("semi", "tag", "0829", tags=["AI"]),
        _index_row("semi", "body", "0830", abstract="AI 算力继续增长"),
        _index_row("semi", "literal", "0827", name="100%_覆盖.pdf"),
        _index_row("semi", "unknown", "unknown", name="无日期.pdf"),
    ], "fp", 1)

    page = db.ima_document_page(["semi"], query="ai", limit=50, offset=0)
    assert [item["media_id"] for item in page["items"][:3]] == ["title", "tag", "body"]
    assert db.ima_document_page(["semi"], query="100%_", limit=50, offset=0)["items"][0]["media_id"] == "literal"
    assert db.ima_document_page(["semi"], query="AI", limit=50, offset=0)["document_count"] == 3
    assert db.ima_document_page(["semi"], limit=50, offset=0)["items"][-1]["media_id"] == "unknown"
```

Add separate assertions for tag counts, `has_more`, offsets, group filtering, and `(group_id, media_id)` detail ambiguity.

- [ ] **Step 2: Run tests and confirm query methods are missing**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_db.py -k ima_document_index_search
```

Expected: FAIL with `AttributeError: 'DB' object has no attribute 'ima_document_page'`.

- [ ] **Step 3: Add literal LIKE escaping and page query**

Add a module helper:

```python
def _like_pattern(value: str) -> str:
    folded = str(value or "").strip().casefold()
    escaped = folded.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
```

Implement `ima_document_page(self, readable_group_ids: list[str], *, group: str = "", query: str = "", day: str = "", tag: str = "", limit: int = 50, offset: int = 0) -> dict`.

Build the `IN (?, ...)` clause only from server-authorized group IDs. Use `EXISTS` for tag filtering. Search rank is `CASE` over `name_folded`, `metadata_folded`, and `abstract_folded`; every `LIKE` uses `ESCAPE '\\'`. Query one extra row (`limit + 1`) to compute `has_more`, strip the extra row, and issue separate indexed aggregate queries for days, tag counts, total count, and group counts. Return exact existing API keys: `items`, `days`, `tags`, `tag_counts`, `document_count`, `day`, `has_more`, `offset`, and `group_counts`.

- [ ] **Step 4: Add catalog and detail queries**

Implement `ima_document_catalog_stats(self, group_ids: list[str]) -> dict[str, dict]`, `ima_document_from_index(self, media_id: str, readable_group_ids: list[str], group: str = "") -> dict | None`, and `ima_document_index_count(self) -> int`.

Catalog selects counts and the first row ordered by valid day/day/name per group. Detail returns `None` when an unqualified media ID exists in more than one readable group, preserving current ambiguity behavior. Every returned document decodes `tags_json` to `tags` and derives public booleans from the stored integer fields.

- [ ] **Step 5: Run query and full DB tests**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_db.py -k 'ima_document_index_search or ima_document_catalog or ima_document_detail'
PYTHONPATH=. .venv/bin/pytest -q tests/test_db.py
```

Expected: all PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: query IMA documents from SQLite"
```

## Task 3: Build, fingerprint, rebuild, and fall back in the service

**Files:**
- Modify: `app/ima_documents.py:1289-2000`
- Modify: `app/ima_documents.py:2060-2300`
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write failing projection and rebuild tests**

Use a real `DB` and a service with manifest/state records. Verify index fields, duplicate group/media support, fingerprint stability, stale index rebuild, and rollback on an injected DB exception:

```python
def test_service_rebuilds_ima_read_model_from_manifest_and_state(tmp_path):
    db = DB(tmp_path / "dav.sqlite")
    service = ImaDocumentService(db, tmp_path / "ima")
    group = ImaGroupConfig("semi", "SemiAnalysis", "kb", "root")
    record = {
        "group_id": "semi", "group_name": "SemiAnalysis", "media_id": "file_a",
        "name": "AI 展望.pdf", "day": "0829", "abstract": "算力需求", "cover_url": "https://img.invalid/a",
    }
    service.store.save_manifest([record])
    service.store.save_state({service.store.state_key(record): {
        "tags": ["AI"], "pdf": "semi/a.pdf", "size": 8, "downloaded_at": "2026-08-29T00:00:00+00:00",
    }})

    result = service.rebuild_read_index((group,))

    assert result["status"] == "ready"
    indexed = db.ima_document_from_index("file_a", ["semi"], "semi")
    assert indexed["abstract"] == "算力需求"
    assert indexed["tags"] == ["AI"]
    assert indexed["has_pdf"] is True
```

- [ ] **Step 2: Run tests and confirm rebuild methods are missing**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_ima_documents.py -k 'rebuilds_ima_read_model or index_fingerprint or index_fallback'
```

Expected: FAIL because `rebuild_read_index()` is absent.

- [ ] **Step 3: Add projection and fingerprint helpers**

Add constants `IMA_INDEX_VERSION = 1` and helpers on `ImaDocumentService`:

```python
def _source_fingerprint(self) -> str:
    parts = []
    for path in (self.store.manifest_path, self.store.state_path):
        try:
            stat = path.stat()
            parts.append((stat.st_mtime_ns, stat.st_size))
        except OSError:
            parts.append((0, 0))
    return json.dumps({"version": IMA_INDEX_VERSION, "files": parts}, separators=(",", ":"))
```

`_index_row(record, state)` must use `store._state_item()`, preserve `abstract_zh`/`abstract_src_hash`, set `valid_day` only for four digits, serialize paths as relative strings, and compute folded fields with `casefold()`.

- [ ] **Step 4: Implement transactional rebuild and status**

Add `rebuild_read_index(self, groups: tuple[ImaGroupConfig, ...] | None = None) -> dict[str, object]`, `read_index_status(self) -> dict[str, object]`, and `_rebuild_index_if_needed(self) -> None`.

Build rows before opening the DB transaction. Mark `rebuilding`, call `replace_ima_document_index`, then report `ready`, count, duration, and empty error. On failure mark `failed`, retain old rows, log a safe message, and return the error without raising into app startup.

Call `_rebuild_index_if_needed()` at the end of the existing `_archive_maintenance()` function. Remote installations already run that maintenance function in a daemon thread; local installations complete it before the scheduler starts. Do not start a second rebuild thread that can race retag/state maintenance.

- [ ] **Step 5: Add service read wrappers with one fallback boundary**

Implement `list_documents()`, `catalog_stats()`, and `document()` on the service. Use DB methods when meta status is `ready`, or when status is `rebuilding`/`failed` and an older index has rows. Use the JSON store only when meta status is `fallback` or no indexed rows exist. A valid empty source may be `ready` with zero rows when its fingerprint matches, so row count alone must not decide readiness. Do not add fallback branches in individual API routes.

- [ ] **Step 6: Make status cheap on the indexed path**

Change `status()` so `documents` comes from `ima_document_index_count()` when nonzero and include:

```python
"index": {
    "status": "ready",
    "documents": 16394,
    "rebuilt_at": "2026-08-29T00:00:00+00:00",
    "duration_ms": 912,
    "error": "",
}
```

Only the empty-index fallback may call `load_manifest()` and `load_state()`.

- [ ] **Step 7: Run service and storage regression tests**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_ima_documents.py -k 'read_model or index or status_counts'
PYTHONPATH=. .venv/bin/pytest -q tests/test_ima_documents.py tests/test_ima_storage.py tests/test_ima_storage_ops.py
```

Expected: all PASS.

- [ ] **Step 8: Commit Task 3**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: rebuild IMA query index"
```

## Task 4: Batch state persistence and incremental index updates

**Files:**
- Modify: `app/ima_documents.py:2430-2640`
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write failing count, timer, final-flush, and crash-order tests**

Add tests with 21 successful fake downloads and a spy around `store.save_state()`: expect one flush at 20 and one final flush. Add a timeout test by monkeypatching `IMA_STATE_FLUSH_SECONDS = 0`; one completion must flush immediately. Add cancellation and raised-future tests proving dirty state flushes in `finally`.

Also assert operation order:

```python
assert events == ["state", "index"]
```

when the flush spy records `save_state()` before `update_ima_document_batch()`.

- [ ] **Step 2: Run tests and confirm state is still saved per document**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_ima_documents.py -k 'batches_state or flushes_state or state_before_index'
```

Expected: FAIL because current `_sync_group()` calls `save_state(state)` after every success.

- [ ] **Step 3: Replace `as_completed()` with a bounded wait loop**

Import `FIRST_COMPLETED` and `wait`; add:

```python
IMA_STATE_FLUSH_COUNT = 20
IMA_STATE_FLUSH_SECONDS = 2.0
```

Maintain `dirty_records`, `last_flush`, and a local `flush()`:

```python
def flush() -> None:
    nonlocal last_flush
    if not dirty_records:
        return
    self.store.save_state(state)
    rows = [self._index_row(record, state) for record in dirty_records.values()]
    updater = getattr(self.db, "update_ima_document_batch", None)
    if callable(updater):
        try:
            updater(rows, self._source_fingerprint())
        except Exception as exc:  # noqa: BLE001
            self.db.mark_ima_document_index("failed", error=_safe_error(exc))
            logger.warning("IMA index batch update failed error=%s", _safe_error(exc))
    dirty_records.clear()
    last_flush = time.monotonic()
```

Drive futures with `wait(pending_futures, timeout=remaining, return_when=FIRST_COMPLETED)`. Flush when 20 records are dirty, two seconds elapse, or no futures remain. Put a final `flush()` in `finally` so cancellation, group failure, and service stop do not lose completed records.

- [ ] **Step 4: Replace the group index only after a successful listing**

After state is loaded and before downloads begin, project the group's records and call `replace_ima_document_group()`. If listing fails, never call replacement, preserving the last good group rows.

- [ ] **Step 5: Keep translation/tag writes coherent**

After `write_abstract_zh()` and tag purge/retag paths persist state, call `update_ima_document_batch()` for the changed records. JSON remains first in every path.

- [ ] **Step 6: Run focused, full IMA, and puller tests**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_ima_documents.py -k 'batch or flush or listing_empty or group_failed'
PYTHONPATH=. .venv/bin/pytest -q tests/test_ima_documents.py tests/test_ima_puller.py tests/test_ima_storage.py tests/test_ima_storage_ops.py
```

Expected: all PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "perf: batch IMA state persistence"
```

## Task 5: Switch knowledge APIs to the indexed service boundary

**Files:**
- Modify: `app/api.py:2480-2670`
- Modify: `app/ima_kb.py:40-90`
- Test: `tests/test_ima_kb.py`
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write failing API parity and no-JSON-read tests**

Seed manifest/state, call `service.rebuild_read_index()`, then monkeypatch `store.load_manifest` and `store.load_state` to raise. Assert list, catalog, detail, PDF, and TXT endpoints still succeed from SQLite. Cover admin, subscribed user, outsider, duplicate media IDs, tag/date/search pagination, unknown day, and literal `%`/`_` queries.

- [ ] **Step 2: Run tests and confirm routes still call store methods**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_ima_kb.py -k 'indexed_api or indexed_pdf or no_json_read'
```

Expected: FAIL from the monkeypatched JSON readers.

- [ ] **Step 3: Route list and catalog through service wrappers**

Replace direct calls to `store.document_facets()`, `store.documents()`, `store.group_summary()`, and `store.catalog_entries()` with:

```python
payload = ima_documents.list_documents(
    groups=groups,
    query=q.strip(),
    day=day.strip(),
    group=group.strip(),
    tag=tag.strip(),
    limit=bounded_limit(limit, default=50),
    offset=max(offset, 0),
)
```

Catalog keeps existing `ima_kb_catalog()` and ACL attachment. Add `attach_catalog_summary(listed, stats_by_group)` in `app/ima_kb.py`; it copies `document_count`, `latest_day`, `latest_title`, and `latest_media_id` from the precomputed mapping into subscribed/available groups. Keep `attach_catalog_stats(listed, documents)` for the JSON fallback and existing callers. The API uses `attach_catalog_summary(listed, ima_documents.catalog_stats(groups))` on the indexed path.

- [ ] **Step 4: Route detail and archive paths through the indexed result**

Change `_ima_document()` to call `ima_documents.document()`. Change `_ima_archive_file()` to read `pdf_path` or `txt_path` from that document and pass it to `authorized_archive_file()`; remove the extra `load_state()` call. Keep `archive_readable()` and `Path.is_file()` checks exactly where they are.

- [ ] **Step 5: Expose index status through admin payload**

`_ima_collector_status()` already returns `ima_documents.status()`; assert its `index` object is present and contains no document names, abstracts, paths, tokens, or URLs.

- [ ] **Step 6: Run API and IMA regression tests**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_ima_kb.py
PYTHONPATH=. .venv/bin/pytest -q tests/test_ima_documents.py tests/test_api.py
```

Expected: all PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add app/api.py app/ima_kb.py tests/test_ima_kb.py tests/test_ima_documents.py
git commit -m "perf: serve knowledge APIs from SQLite"
```

## Task 6: Load catalog and first page in parallel

**Files:**
- Modify: `app/static/app.js:1209-1460`
- Modify: `app/static/app.js:7477-7515`
- Modify: `app/static/index.html:36,135`
- Modify: `app/static/sw.js:2`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write failing frontend contracts**

Add assertions that `renderKnowledge()` creates both promises before its first await after the skeleton, uses `Promise.allSettled`, passes prefetched list data into `renderImaDocuments()`, preserves list success when catalog fails, and appends an index fallback message only in the admin status function.

- [ ] **Step 2: Run the contracts and confirm sequential loading**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_frontend_interactions.py -k 'knowledge_parallel or knowledge_index_status'
```

Expected: FAIL because catalog is awaited before `renderImaDocuments()` starts.

- [ ] **Step 3: Extract one request builder and allow prefetched data**

Add:

```javascript
function imaDocumentsRequestPath() {
  const params = new URLSearchParams();
  const query = routeQuery().get("q") || "";
  const day = routeQuery().get("day") || "";
  const tag = routeQuery().get("tag") || "";
  const group = imaDocumentsGroupFromRoute() || "";
  if (query) params.set("q", query);
  if (tag) params.set("tag", tag);
  if (group) params.set("group", group);
  if (query || tag || !day) {
    params.set("limit", "50");
    params.set("offset", "0");
  } else {
    params.set("day", day);
  }
  return `/api/ima-documents?${params.toString()}`;
}
```

Change the signature to:

```javascript
async function renderImaDocuments(seq, { keepOld = false, prefetched = null } = {})
```

Use `await prefetched` when supplied; otherwise call `api(imaDocumentsRequestPath())`. Remove the duplicate URLSearchParams block from the function.

- [ ] **Step 4: Start both requests together and isolate failures**

In `renderKnowledge()`:

```javascript
const catalogPromise = api("/api/ima-documents/catalog");
const documentsPromise = api(imaDocumentsRequestPath());
const [catalogResult, documentsResult] = await Promise.allSettled([
  catalogPromise,
  documentsPromise,
]);
```

When catalog fails but documents succeed, derive subscribed source controls from `documentsResult.value.groups`, render the list, and insert one inline catalog warning. When documents fail, retain the existing list retry even if catalog succeeded. If both fail, show the current full-page retry state.

Do not cache `/api/me`, change phone blocking, or alter snapshot/read-return behavior.

- [ ] **Step 5: Add administrator index status copy**

In `imaCollectorStatusText()`, append one of:

```javascript
const indexMessages = {
  rebuilding: "索引重建中",
  fallback: "索引回退",
  failed: "索引异常",
};
```

Only append when `status.index.status !== "ready"`; never show it on `/knowledge` for ordinary users.

- [ ] **Step 6: Bump static asset versions**

Change `app.js?v=314` to `app.js?v=315` in `index.html` and `dav-shell-v185` to `dav-shell-v186` in `sw.js`. CSS is unchanged, so do not bump `style.css?v=226`.

- [ ] **Step 7: Run frontend checks**

```bash
node --check app/static/app.js
node --check app/static/sw.js
PYTHONPATH=. .venv/bin/pytest -q tests/test_frontend_interactions.py -k 'knowledge or ima'
```

Expected: syntax checks and selected tests PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add app/static/app.js app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
git commit -m "perf: load knowledge data in parallel"
```

## Task 7: Add a repeatable latency benchmark and complete regression

**Files:**
- Create: `scripts/benchmark_ima_knowledge.py`
- Modify: `tests/test_ima_kb.py`

- [ ] **Step 1: Write the benchmark script**

The script reads `VPUSH_TOKEN` and optional `VPUSH_BASE_URL`, performs 20 authenticated runs per route, consumes every response body, and prints min/median/p95/max without printing headers or token values:

```python
#!/usr/bin/env python3
import json
import os
import statistics
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("VPUSH_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ["VPUSH_TOKEN"]
HEADERS = {"Authorization": "Bearer " + TOKEN}


def fetch_json(route: str):
    request = urllib.request.Request(BASE + route, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


catalog = fetch_json("/api/ima-documents/catalog")
subscribed = catalog.get("subscribed") or []
group_id = str(subscribed[0].get("id") or "") if subscribed else ""
ROUTES = [
    "/api/ima-documents/catalog",
    "/api/ima-documents?limit=50&offset=0",
    "/api/ima-documents?q=新能源&limit=50&offset=0",
    "/api/ima-documents?q=AI&limit=50&offset=0",
]
if group_id:
    ROUTES.append("/api/ima-documents?" + urllib.parse.urlencode({
        "group": group_id, "limit": 50, "offset": 0,
    }))

for route in ROUTES:
    samples = []
    for _ in range(20):
        started = time.perf_counter()
        fetch_json(route)
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    print(f"{route} min={min(samples):.1f} median={statistics.median(samples):.1f} p95={p95:.1f} max={max(samples):.1f} ms")
```

- [ ] **Step 2: Add a no-JSON happy-path performance contract**

In `tests/test_ima_kb.py`, rebuild an index, patch JSON readers to fail, then run catalog/list/search 20 times. Do not assert wall-clock milliseconds in CI; assert every response is 200 and JSON readers remain untouched.

- [ ] **Step 3: Run all relevant tests and static checks**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_db.py tests/test_ima_documents.py tests/test_ima_kb.py tests/test_ima_puller.py tests/test_ima_storage.py tests/test_ima_storage_ops.py tests/test_frontend_interactions.py
.venv/bin/ruff check app/db.py app/ima_documents.py app/api.py scripts/benchmark_ima_knowledge.py
node --check app/static/app.js
node --check app/static/sw.js
git diff --check
```

Expected: all tests and checks PASS. Existing framework deprecation warnings may remain; no new warning is accepted.

- [ ] **Step 4: Run local browser regression**

Start with `DAV_UI_ONLY=1`, then check Chrome at 1440×900 light, 1440×900 dark, and 390×844. Cover initial skeleton, latest list, Chinese search, `AI`, source switch, load more, reader return, catalog failure, list failure, and phone-blocked state. Delete temporary harnesses and screenshots after recording the result.

- [ ] **Step 5: Commit Task 7**

```bash
git add scripts/benchmark_ima_knowledge.py tests/test_ima_kb.py
git commit -m "test: benchmark knowledge query latency"
```

## Task 8: Release and verify production

**Files:**
- Modify: `app/version.py`
- Modify: `app/static/app.js` only where the repository's `APP_VERSION` constant is declared

- [ ] **Step 1: Review the complete branch before release**

```bash
git status -sb
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
```

Expected: only the planned files are tracked; `.cursor/`, `work/`, probes, and unrelated local files are absent.

- [ ] **Step 2: Request an independent code review**

Review schema rollback, SQL parameterization, ACL filtering, wildcard escaping, JSON-first flush ordering, stale-index behavior, archive path authorization, and frontend failure isolation. Resolve every Critical or Important finding and rerun Task 7 checks.

- [ ] **Step 3: Publish using the project deploy procedure**

Read and follow `vpush-vps-deploy`. Increase the next patch version without replacing an existing tag, commit the version change, push `main`, create/push the tag, create the GitHub release, and wait only for the `publish-amd64` job.

- [ ] **Step 4: Back up and deploy the VPS image**

Before container replacement, copy `/opt/vpush/data/dav.db` into `/opt/vpush/data/backups/`. Pull the tagged `icekale/vpush` image, retag it as `dav-subscription-vpush:latest`, and recreate only `vpush` with `docker compose up -d --no-build vpush`.

- [ ] **Step 5: Verify index build and correctness**

Verify:

```text
/healthz = 200
/api/version current = released version
container = running and healthy
index status transitions rebuilding/fallback -> ready
index document count = manifest document count
catalog/list/detail/PDF all return expected data
no new traceback or database locked errors
```

- [ ] **Step 6: Measure production latency**

Generate an administrator token inside the container without printing it, pass it only to a container-local benchmark process, and run `scripts/benchmark_ima_knowledge.py` with `VPUSH_BASE_URL=http://127.0.0.1:8000`. Required loopback API targets:

```text
catalog p95 < 200 ms
latest list p95 < 300 ms
active-sync latest list p95 < 750 ms
cached-static knowledge list usable < 1.5 s
```

Run once while idle and once during a controlled IMA sync. Separately use external Chrome with cached static assets to verify the 1.5-second user-visible target; do not apply loopback millisecond thresholds to Cloudflare/TLS timings. If targets fail, stop release closure, retain the JSON fallback, and profile the slow indexed query before changing scope.

- [ ] **Step 7: Verify one real sync batch and rollback path**

Confirm state mtime changes in batches rather than once per PDF, new PDFs appear in SQLite and `/knowledge`, failed group listing preserves old rows, and stopping/restarting the container rebuilds a deliberately stale fingerprint. Do not delete manifest/state or the pre-deploy DB backup.

---

## Completion Gate

The work is complete only when:

- SQLite is the happy path for catalog/list/detail/PDF/TXT.
- Empty, stale, failed, and rebuilding indexes keep the page available through old rows or JSON fallback.
- Search parity covers title, source, tags, abstract, two-character Chinese, `AI`, stock codes, and literal wildcards.
- State persistence is bounded by 20 documents or two seconds and flushes on every exit path.
- ACL and archive path safety tests pass.
- Production p95 targets pass idle and during active collection.
- Existing manifest/state and backups remain intact.
