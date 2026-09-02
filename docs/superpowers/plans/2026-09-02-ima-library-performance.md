# IMA Library Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and implement tasks serially in this worktree.

**Goal:** Remove avoidable report-library request stalls and startup NFS work while preserving ACL and fallback behavior.

**Architecture:** Keep SQLite and the existing read model. Add one stdlib read-only query helper for request paths, one persisted remote-maintenance completion fingerprint, early list-shell mounting, and indexed per-group catalog lookups.

**Tech Stack:** Python stdlib `sqlite3`, FastAPI service code, vanilla JavaScript, pytest.

---

### Task 1: Isolate Request Reads

**Files:** `app/db.py`, `tests/test_db.py`, `tests/test_ima_kb.py`

- [ ] Add a failing concurrency test that holds `DB._lock` while a file-backed IMA page/catalog read runs in another thread; assert completion and correct ACL-scoped data. Add a memory-database regression assertion.
- [ ] Run the focused tests and confirm the file-backed test times out on current `_rows`.
- [ ] Add the smallest `_readonly_rows(sql, params)` helper using `Path(...).resolve().as_uri() + "?mode=ro"`, `uri=True`, `sqlite3.Row`, `busy_timeout=5000`, and `finally: close()`. Fall back to `_rows` for `:memory:`.
- [ ] Route request-time user, IMA config/ACL, and IMA read-model methods through the helper; do not change write transactions or general `_rows`.
- [ ] Run DB and IMA ACL tests; commit.

### Task 2: Skip Completed Remote Maintenance

**Files:** `app/ima_documents.py`, `tests/test_ima_documents.py`

- [ ] Add failing tests for matching checkpoint skip, stale/missing checkpoint execution, successful checkpoint update, and no update after any maintenance failure.
- [ ] Run tests and confirm current maintenance invokes NFS work despite a matching checkpoint.
- [ ] Add one setting key and compare it with `_source_fingerprint()` only when `storage_status.remote` is true. Preserve first index validation and final FTS sync. Update checkpoint only when restore, manifest rebuild, and retag complete without exception.
- [ ] Run maintenance and service tests; commit.

### Task 3: Render the List Surface Immediately

**Files:** `app/static/app.js`, `tests/test_frontend_interactions.py`

- [ ] Update the static contract test to require `mountKnowledgeListShell()` before catalog request creation and first `await`, guarded by the list route.
- [ ] Run the test and confirm ordering failure.
- [ ] Mount the list shell immediately for non-reader routes and include the existing skeleton inside `#kb-list`; keep parallel requests and settled fallback unchanged.
- [ ] Run frontend interaction tests and the Impeccable detector; commit.

### Task 4: Use Indexed Catalog Lookups

**Files:** `app/db.py`, `tests/test_db.py`

- [ ] Extend catalog tests with empty sort dates, name ties, multiple groups, and an empty group. Add a query-plan assertion proving no window coroutine/temp ORDER BY and use of `idx_ima_doc_group_latest`.
- [ ] Run the focused test and confirm the current window query fails the plan expectation.
- [ ] Replace the window query with grouped counts plus one `ORDER BY sort_date DESC, name DESC LIMIT 1` lookup per group through the read-only helper.
- [ ] Benchmark against a production database copy or production read-only probe; run DB tests; commit.

### Task 5: Verify and Review

**Files:** all changed files

- [ ] Run the four focused test files, then `../../.venv/bin/python -m pytest -q`.
- [ ] Run syntax/static checks and inspect the final diff.
- [ ] Run fresh-context correctness, test, simplicity, and performance reviews; apply only concrete in-scope fixes through one writer and rerun affected tests.
- [ ] Report measured before/after behavior and residual SQLite file-lock risk. Do not push or deploy without explicit approval.
