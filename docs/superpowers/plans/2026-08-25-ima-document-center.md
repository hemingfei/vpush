# IMA Document Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a VPS-backed IMA PDF/TXT document center to VPUSH without putting PDF content into the normal push timeline.

**Architecture:** Keep the existing `ImaFetcher` unchanged for Cookie/OpenAPI timeline compatibility. Add an `ImaDocumentService` that owns the pure VPS protocol client, manifest/state archive, lock, and interval loop. FastAPI exposes authenticated document/file endpoints and admin-only collector controls; the SPA adds a user-facing document route and extends the existing IMA admin credential panel.

**Tech Stack:** Python 3.11, FastAPI, SQLite settings, `cryptography` AES-GCM/RSA-OAEP, `pypdf`, vanilla JavaScript SPA, pytest/TestClient.

---

## File map

- Create: `app/ima_documents.py` — pure client, archive store, config defaults, incremental sync service.
- Create: `tests/test_ima_documents.py` — protocol, archive, locking, and service tests.
- Modify: `app/api.py` — document endpoints and pure collector configuration/status endpoints.
- Modify: `app/main.py` — construct the document service, pass it to API, start/stop its interval worker.
- Modify: `app/static/app.js` — IMA document navigation, list/detail reader, PDF Blob loading, admin settings controls.
- Modify: `app/static/style.css` — document list, reader, and compact admin status styles.
- Modify: `README.md` and `.env.example` — explain the simple setup and runtime-only secret handling.
- Create: `docs/superpowers/plans/2026-08-25-ima-document-center.md` — this plan.

## Task 1: Write failing pure-client and archive tests

**Files:**
- Create: `tests/test_ima_documents.py`

- [ ] **Step 1: Add tests for stable defaults and secret masking.**

```python
def test_default_config_targets_august_folder():
    cfg = ImaDocumentConfig.from_db(FakeDB())
    assert cfg.uid == "001aa361168019ef"
    assert cfg.knowledge_base_id == "7464369361259867"
    assert cfg.root_folder_id == "folder_7489327974078249"
    assert cfg.interval_seconds == 3600


def test_public_config_never_returns_refresh_token():
    cfg = ImaDocumentConfig(refresh_token="secret-token")
    public = cfg.public()
    assert public["refresh_token"]["set"] is True
    assert "secret-token" not in str(public)
```

- [ ] **Step 2: Add tests for safe filenames and manifest path validation.**

```python
def test_archive_paths_are_relative_and_confined(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "file_abc", "name": "../report.pdf", "day": "0825"}
    path = store.pdf_path(record)
    assert path.parent == (tmp_path / "ima" / "0825").resolve()
    assert path.is_relative_to((tmp_path / "ima").resolve())
    assert ".." not in path.name
```

- [ ] **Step 3: Add tests for incremental completion and recovery.**

```python
def test_completed_media_is_skipped_but_missing_txt_is_pending(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "file_abc", "name": "report.pdf", "day": "0825", "size": 4}
    pdf, txt = store.pdf_path(record), store.txt_path(record)
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7")
    store.save_state({"file_abc": {"pdf": "0825/report.pdf", "txt": "0825/report.txt"}})
    assert store.is_complete(record) is False
    txt.write_text("text", encoding="utf-8")
    assert store.is_complete(record) is True
```

- [ ] **Step 4: Add tests for encrypted request shape using the existing known algorithm.**

```python
def test_encrypt_body_uses_aes_128_gcm_and_rsa_oaep():
    key, body, wrapped = encrypt_body(b'{"media_id":"file_abc"}')
    assert len(key) == 16
    assert len(base64.b64decode(body)) > 12 + 16
    assert len(base64.b64decode(wrapped)) == 256
    assert decrypt_body(body, key) == b'{"media_id":"file_abc"}'
```

- [ ] **Step 5: Run the new tests and confirm they fail because the module is absent.**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py -q`
Expected: collection failure naming the missing `app.ima_documents` symbols.

## Task 2: Implement the pure VPS client and archive service

**Files:**
- Create: `app/ima_documents.py`

- [ ] **Step 1: Implement constants and DB-backed configuration.**

Use these exact settings keys and defaults:

```python
IMA_PURE_UID_KEY = "ima_pure_uid"
IMA_PURE_REFRESH_TOKEN_KEY = "ima_pure_refresh_token"
IMA_PURE_KB_ID_KEY = "ima_pure_knowledge_base_id"
IMA_PURE_ROOT_FOLDER_KEY = "ima_pure_root_folder_id"
IMA_PURE_INTERVAL_KEY = "ima_pure_interval_seconds"
IMA_PURE_UID_DEFAULT = "001aa361168019ef"
IMA_PURE_KB_ID_DEFAULT = "7464369361259867"
IMA_PURE_ROOT_FOLDER_DEFAULT = "folder_7489327974078249"
IMA_PURE_INTERVAL_DEFAULT = 3600
IMA_PURE_INTERVAL_MIN = 1800
```

`ImaDocumentConfig.from_db(db)` reads DB settings first, then `IMA_UID`, `IMA_REFRESH_TOKEN`, `IMA_KB_ID`, and `IMA_ROOT_FOLDER_ID` environment fallbacks. It clamps interval values to at least 1800 seconds. `public()` exposes `set`, `preview`, IDs, and interval only; it never includes the refresh token.

- [ ] **Step 2: Implement the protocol functions copied from the verified case, parameterized by config.**

Implement `bkn`, `encrypt_body`, `decrypt_body`, `ImaPureClient.refresh`, `ImaPureClient.list_items`, `ImaPureClient.get_media`, and `ImaPureClient.download` with these invariants:

- AES key is exactly 16 random bytes.
- GCM nonce is 12 bytes and prefixes the ciphertext/tag.
- RSA wrapping is OAEP with SHA-256 for both digest and MGF1.
- `get_media` body contains only `media_id` and `source_knowledge_base_id`.
- List calls use `limit=50`, `next_cursor`, and `is_end`.
- Download writes to a temporary sibling file, verifies `%PDF-1.`, checks expected size, then atomically renames.
- No exception or log message includes refresh token, cookies, or signed URLs.

- [ ] **Step 3: Implement manifest/state storage.**

`ImaDocumentStore(root)` owns `manifest.json`, `state.json`, and `<day>/...` files. It must use `safe_filename`, resolve paths under `root`, store only relative paths in state, write JSON through a sibling `.tmp` followed by `os.replace`, and expose `documents(q="", day="")` using only records whose PDF and TXT both exist.

- [ ] **Step 4: Implement tree enumeration and one incremental sync.**

`ImaDocumentService.sync_once()` loads the configured root folder, lists each child date folder with pagination, creates manifest records, skips complete media IDs, downloads pending PDFs, extracts text with `pypdf`, writes state after every successful file, and returns `{total, pending, downloaded, failed, last_error}`. It must preserve per-file failure isolation and never enqueue posts or notifications.

- [ ] **Step 5: Implement locking, minimum manual interval, and lifecycle.**

The service exposes:

```python
service.start()
service.stop()
service.status()
service.trigger()  # returns started/already_running/too_soon/not_configured
```

Use one `threading.Lock`; scheduled runs wait one configured interval between starts, default one hour. `trigger()` starts a daemon worker only when credentials are configured, no worker is running, and the minimum interval has elapsed. The service stores status in memory plus DB timestamp/error settings for API display.

- [ ] **Step 6: Run the focused tests and confirm green.**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py -q`
Expected: all focused tests pass.

## Task 3: Add authenticated APIs and app lifecycle wiring

**Files:**
- Modify: `app/api.py`
- Modify: `app/main.py`
- Modify: `app/static/index.html`
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Add failing TestClient coverage for user and admin boundaries.**

Add tests that create an app with a temporary DB and temporary archive, obtain a normal-user token and admin token, seed one valid manifest/state/PDF/TXT, and assert:

```python
assert client.get("/api/ima-documents").status_code == 401
assert user_client.get("/api/ima-documents").status_code == 200
assert user_client.get("/api/ima-documents/file_abc/text").text == "text"
assert user_client.get("/api/ima-documents/file_abc/pdf").headers["content-type"].startswith("application/pdf")
assert user_client.get("/api/admin/ima-collector").status_code == 403
assert admin_client.get("/api/admin/ima-collector").status_code == 200
```

- [ ] **Step 2: Extend `create_api_router` with an optional `ima_documents` service.**

Add authenticated routes:

```text
GET  /api/ima-documents?q=&day=
GET  /api/ima-documents/{media_id}/text
GET  /api/ima-documents/{media_id}/pdf?download=0|1
GET  /api/admin/ima-collector
PUT  /api/admin/ima-collector
POST /api/admin/ima-collector/sync
```

User routes use `get_current_user`; admin routes use `require_admin`. PDF/TXT lookup accepts only a manifest `media_id`, resolves through the store, and returns 404 for unknown/incomplete records. PDF responses use `application/pdf` with `inline` unless `download=1`.

- [ ] **Step 3: Extend the existing `ImaCredentialsIn` model or add a separate `ImaCollectorIn` model.**

Keep old fields backward-compatible. New collector PUT fields are optional so blank refresh token means “keep existing token”, not “erase it”. Validate UID/IDs as non-empty bounded strings and interval as 1800–604800 seconds. Audit only that the fields were changed, never their values.

- [ ] **Step 4: Wire the service in `create_app`.**

Construct the service after `DB` with `Path(config.db_path).parent / "ima"`; pass it to `create_api_router`. In the normal lifespan call `start()` before `yield`, then `stop()` before `db.close()`. Keep `DAV_UI_ONLY=1` from starting background sync. Add `ima-documents` to `SPA_PREFIXES`.

- [ ] **Step 5: Run focused API tests.**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py -q`
Expected: all document service and API tests pass.

## Task 4: Add the SPA document center and simple admin configuration

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/style.css`
- Test: `tests/test_spa_routes.py` or an existing static route test

- [ ] **Step 1: Add the failing route assertion.**

Assert that `/ima-documents` returns the SPA shell and that the route is included in the server fallback allowlist.

- [ ] **Step 2: Add the navigation item and route.**

Add a user-visible `IMA 文档` item to `NAV` and the mobile navigation. Add `renderImaDocuments()` to the router. Use the existing `BOOK_ICON`/`FILE_TEXT_ICON` vocabulary rather than introducing a new icon dependency.

- [ ] **Step 3: Implement list and reader behavior.**

`renderImaDocuments()` calls `/api/ima-documents`, renders a search box, day filter, grouped rows, and an empty/error state. Selecting a row updates the route to `ima-documents/{media_id}` and renders TXT first. `loadImaPdf()` calls the authenticated `apiBlob()` helper, creates a Blob URL, assigns it to a PDF object/embed, and revokes the previous URL when leaving the reader. Download uses the same authenticated Blob fetch and an anchor with the original filename.

- [ ] **Step 4: Extend the existing IMA admin card.**

Add fields for UID, refresh token, KB ID, root folder ID, and interval. Pre-fill UID/KB/root defaults; leave the refresh token blank and show “已保存” status when present. Add save, refresh status, and “立即同步” actions. Never put the token into `value`, HTML, status text, or error messages after save.

- [ ] **Step 5: Add focused styles and run frontend syntax checks.**

Add document list/reader styles that reuse existing tokens and preserve mobile layout. Run:

```bash
node --check app/static/app.js
.venv/bin/python -m pytest tests/test_spa_routes.py -q
```

Expected: JavaScript syntax check and SPA route tests pass.

## Task 5: Documentation, integration verification, and cleanup

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Test: full existing suite

- [ ] **Step 1: Document the shortest setup path.**

Explain: open admin data source settings, leave the prefilled UID/KB/root values, paste a newly issued refresh token once, save, click “立即同步”, and use the new sidebar IMA 文档 page. Document the one-hour default, 30-minute minimum, archive path under `/data/ima`, and that PDFs are never pushed.

- [ ] **Step 2: Add safe environment fallbacks without secret values.**

Document `IMA_UID`, `IMA_REFRESH_TOKEN`, `IMA_KB_ID`, and `IMA_ROOT_FOLDER_ID` as optional deployment variables with empty/example placeholders only. Do not alter `.env` with a real token.

- [ ] **Step 3: Run the complete verification set.**

```bash
node --check app/static/app.js
.venv/bin/python -m pytest tests/test_ima_documents.py tests/test_ima_fetcher.py tests/test_spa_routes.py -q
.venv/bin/python -m pytest -q
rg -n "refresh_token|IMA_REFRESH_TOKEN|IMA-TOKEN|x-ima-ctk" app tests README.md .env.example
```

Expected: tests pass; the final search contains only variable names, placeholders, or masking code, never a token value.

- [ ] **Step 4: Inspect the final diff and preserve unrelated worktree changes.**

Run `git status --short` and `git diff --check`; do not stage or revert the existing unrelated modified/untracked files. Commit only the implementation files for this feature after verification.
