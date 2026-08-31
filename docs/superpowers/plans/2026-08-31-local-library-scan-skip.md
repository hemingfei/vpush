# Local Library Scan Skip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the periodic IMA cycle from walking and rewriting unchanged `local/<slug>/` trees on NFS, while keeping admin「扫描本地库」as a forced full scan.

**Architecture:** Local libraries, ACL, sidecar abstracts, and the SQLite read model already exist. Do not add OpenList, Meilisearch, WebDAV, or a second file-manager UI. Copy only OpenList/IMA listing-cache behavior: cheap mtime fingerprint per slug; skip walk and manifest/state/index writes when the fingerprint matches the last successful scan.

**Tech Stack:** Python 3.12, stdlib `os`/`json`/`pathlib`, existing `ImaDocumentService`, pytest.

**Design:** `docs/superpowers/specs/2026-08-29-local-storage-library-mount-design.md` §6（周期扫描）+ OpenList `database` 索引增量更新习惯。挂载/ACL/sidecar 已落地，本计划只补扫描跳过。

---

## Evaluation (do not re-implement)

Already shipped — do not rebuild:

- `archive_root/local/<slug>/` + `.vpush-local-library.json` + `.vpush-local-meta.jsonl`
- `scan_local_libraries` / create / enable / rename / ACL
- `group_id = local-<slug>`, IMA `local-` 前缀拒绝
- `sync_once` 开头附带本地扫描，失败不挡 IMA
- 阅读走 `authorized_archive_file`；IMA 重命名跳过本地路径
- SQLite `ima_document_page` 已服务 `/knowledge`

Rejected (OpenList):

- 部署 OpenList / WebDAV 写库 / Bleve / Meilisearch / 签名直链分享 / 主进程反代 PDF

Remaining gap:

- `_scan_local_libraries_locked` 每次 `os.walk` 全树，并把所有 PDF 的 `downloaded_at` 写成 now，再 `save_group_manifest` + `save_state` + `_replace_group_index`。中金本地库变大后，这会在 NFS 上重复打满 IMA 周期。

---

## File Map

- Modify `app/ima_documents.py`: fingerprint helper; skip unchanged libraries on periodic scan; keep admin scan forced.
- Modify `tests/test_local_libraries.py`: skip, sidecar bust, new-file bust, forced scan.

Do not touch `app/api.py` routes except if `scan_local_libraries()` needs a `force` argument with default `True` (admin POST stays forced). Do not change frontend copy. Do not add dependencies.

---

## Task 1: Fingerprint unchanged libraries and skip apply

**Files:**
- Modify: `app/ima_documents.py` (`ImaDocumentStore.scan_local_libraries`, `_scan_local_library`, `ImaDocumentService._scan_local_libraries_locked`, `scan_local_libraries`)
- Test: `tests/test_local_libraries.py`

- [ ] **Step 1: Write failing skip tests**

Add next to the existing scan tests. Use a spy around `save_group_manifest` (or count writes) so skip is observable:

```python
def test_periodic_scan_skips_unchanged_library(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, pdfs=["0830/纪要.pdf"])
    first = service.scan_local_libraries()
    assert first["status"] == "finished"
    writes = {"n": 0}
    original = service.store.save_group_manifest

    def wrapped(group_id, records):
        writes["n"] += 1
        return original(group_id, records)

    service.store.save_group_manifest = wrapped
    second = service._scan_local_libraries_locked(force=False)
    assert second["status"] == "finished"
    assert writes["n"] == 0
    demo = [item for item in second["libraries"] if item["slug"] == "demo"][0]
    assert demo["pdf_count"] == 1
    assert demo.get("skipped") is True


def test_sidecar_or_new_pdf_busts_skip(tmp_path):
    service, archive = _service(tmp_path)
    lib = _make_library(archive, pdfs=["a_101.pdf"])
    service.scan_local_libraries()
    (lib / SIDECAR).write_text(
        json.dumps({"id": "101", "summary": "新摘要", "tags": ["宏观"], "publish": "2026-08-30"})
        + "\n",
        encoding="utf-8",
    )
    result = service._scan_local_libraries_locked(force=False)
    assert result["libraries"][0].get("skipped") is not True
    assert service.store.load_manifest()[0]["abstract"] == "新摘要"

    (lib / "b.pdf").write_bytes(b"%PDF-1.7 fake")
    result = service._scan_local_libraries_locked(force=False)
    assert result["libraries"][0]["pdf_count"] == 2


def test_admin_scan_force_walks_even_if_fingerprint_matches(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, pdfs=["a.pdf"])
    service.scan_local_libraries()
    writes = {"n": 0}
    original = service.store.save_group_manifest

    def wrapped(group_id, records):
        writes["n"] += 1
        return original(group_id, records)

    service.store.save_group_manifest = wrapped
    result = service.scan_local_libraries()  # admin POST: force=True
    assert result["status"] == "finished"
    assert writes["n"] == 1
```

- [ ] **Step 2: Run tests and confirm skip is absent**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_local_libraries.py -k 'skips_unchanged or busts_skip or force_walks'
```

Expected: FAIL (`_scan_local_libraries_locked() got an unexpected keyword argument 'force'` or `skipped` missing).

- [ ] **Step 3: Add a cheap fingerprint helper on the store**

```python
def local_library_fingerprint(self, lib_dir: Path) -> str:
    parts = []
    for rel in (LOCAL_LIBRARY_MARKER, LOCAL_LIBRARY_SIDECAR, "."):
        path = lib_dir if rel == "." else lib_dir / rel
        try:
            stat = path.stat()
            parts.append((rel, stat.st_mtime_ns, stat.st_size))
        except OSError:
            parts.append((rel, 0, 0))
    return json.dumps(parts, separators=(",", ":"))
```

ponytail: 只 stat 库根、标记、sidecar。嵌套文件原地改内容且父目录 mtime 不变时会漏检；管理员「扫描本地库」强制全量。若以后原地覆盖 PDF 成为常态，再改成逐文件 mtime。

- [ ] **Step 4: Skip walk inside `_scan_local_library` when fingerprint matches**

Change `_scan_local_library(self, path, known_groups, previous=None, force=False)`.

If `not force` and `previous` has the same fingerprint, no `error`, and a stored `pdf_count`/`name`/`enabled`/`tags`, return an entry with `records is None` (or `"skipped": True` and empty records) **without** `os.walk`.

If marker JSON is unreadable, keep current error/transient behavior (do not skip).

Always compute and return the new fingerprint on both skip and full walk.

- [ ] **Step 5: Apply skip in `_scan_local_libraries_locked`**

```python
def scan_local_libraries(self, force: bool = True) -> dict[str, Any]:
    ...
    return self._scan_local_libraries_locked(force=force)

def _scan_local_libraries_locked(self, force: bool = False) -> dict[str, Any]:
```

- Admin `POST /api/admin/ima-local-libraries/scan` keeps calling `scan_local_libraries()` → `force=True`.
- `sync_once` keeps calling `_scan_local_libraries_locked()` → default `force=False`.
- `create_local_library` can keep `scan_local_libraries()` (forced once after mkdir).

When an entry is skipped:

- Do not call `save_group_manifest`, `save_state`, or `_replace_group_index`.
- Copy `pdf_count` / `name` / `enabled` / `tags` from previous status.
- Set `"skipped": True` on the summary.
- Still write the new fingerprint into `IMA_LOCAL_LIBRARIES_KEY` so the next cycle can skip again.

When not skipped, persist `"fingerprint"` on the summary.

Broken-marker / walk-error libraries must not store a matching fingerprint that would skip a later repair.

- [ ] **Step 6: Run local-library tests**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_local_libraries.py
```

Expected: all PASS. Existing broken-marker / prune / ACL tests remain green.

- [ ] **Step 7: Commit Task 1**

```bash
git add app/ima_documents.py tests/test_local_libraries.py
git commit -m "perf: skip unchanged local library scans"
```

---

## Task 2: Keep IMA isolation and sidecar bust coverage

**Files:**
- Test: `tests/test_local_libraries.py`
- Modify: `app/ima_documents.py` only if a test proves IMA still walks `local/`

- [ ] **Step 1: Add a regression that IMA sync does not rewrite local PDFs**

```python
def test_ima_sync_does_not_move_or_delete_local_pdfs(tmp_path, monkeypatch):
    service, archive = _service(tmp_path)
    lib = _make_library(archive, slug="cicc", enabled=True, pdfs=["0830/a_1.pdf"])
    service.scan_local_libraries()
    pdf = lib / "0830" / "a_1.pdf"
    before = pdf.read_bytes()
    service.sync_once()
    assert pdf.is_file()
    assert pdf.read_bytes() == before
    assert all(
        str(item.get("pdf") or "").startswith("local/")
        for item in service.store.load_state().values()
        if item.get("group_id") == "local-cicc"
    )
```

If this already passes, keep it as a lock. Do not add OpenList or extra scanners.

- [ ] **Step 2: Run focused plus IMA skip tests**

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_local_libraries.py tests/test_ima_documents.py -k 'local_library or local-'
.venv/bin/ruff check app/ima_documents.py tests/test_local_libraries.py
git diff --check
```

Expected: PASS.

- [ ] **Step 3: Commit only if Step 1 added a test or a real IMA skip fix**

```bash
git add tests/test_local_libraries.py app/ima_documents.py
git commit -m "test: keep IMA sync off local library files"
```

Skip the commit if the tree is unchanged.

---

## Task 3: Verify periodic path and document the ceiling

**Files:**
- Modify: `docs/superpowers/specs/2026-08-29-local-storage-library-mount-design.md` §6 only if the skip rule is not already there.

- [ ] **Step 1: Confirm `sync_once` calls `_scan_local_libraries_locked()` without force**

Grep:

```bash
rg -n "_scan_local_libraries_locked|scan_local_libraries\(" app/ima_documents.py app/api.py
```

Expected: API scan → `scan_local_libraries()`; `sync_once` → `_scan_local_libraries_locked()`.

- [ ] **Step 2: One-line spec note under §6**

周期扫描：若 `local/<slug>/` 目录、标记文件、sidecar 的 mtime/size 与上次成功扫描一致，则跳过 walk 与索引写入。管理员「扫描本地库」始终全量。

- [ ] **Step 3: Commit spec note**

```bash
git add -f docs/superpowers/specs/2026-08-29-local-storage-library-mount-design.md
git commit -m "docs: skip unchanged local library scans"
```

---

## Completion Gate

Done when:

- Unchanged local libraries are not walked or rewritten on the IMA interval.
- Sidecar or new PDF changes are picked up on the next periodic scan.
- Admin scan still walks every library.
- IMA sync still does not download, rename, or delete `local/` files.
- `tests/test_local_libraries.py` and ruff pass.
- OpenList, Meilisearch, WebDAV, and extra search services are still absent.

Do not deploy OpenList. Do not tune TCP. Do not put storage private keys in code.
