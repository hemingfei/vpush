# IMA 多群组文档中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有单群组采集、历史归档和权限边界的前提下，为 IMA 文档中心增加多群组注册、自动发现加手动兜底，以及以群组切换为核心的 B+ 浏览体验。

**Architecture:** 保留 `ImaDocumentService` 作为全局调度器，把账号凭证/间隔与每个群组的知识库和根目录拆开。每次同步按启用群组隔离 manifest 更新和下载错误；文档 API 返回群组摘要并支持群组过滤。前端在现有 SPA 文档页上增加群组上下文、URL 状态恢复和移动端原生选择器，不引入新页面或前端依赖。

**Tech Stack:** Python 3.14、FastAPI、Pydantic、SQLite settings、pytest、原生 JavaScript、原生 CSS、现有 `api()`/`apiBlob()`/SPA router。

---

## 文件地图

- Modify: `app/ima_documents.py` — 群组配置、发现、manifest 元数据、逐群同步和公开状态。
- Modify: `app/api.py` — 群组配置请求模型、管理员保存、文档列表过滤和群组摘要。
- Modify: `app/static/app.js` — 管理员群组行、文档群组选择器、URL 上下文和来源标签。
- Modify: `app/static/style.css` — B+ 选择器、群组状态、移动端布局和文档来源标签。
- Modify: `app/static/index.html` — 递增 `app.js` 静态资源版本。
- Modify: `app/static/sw.js` — 递增 shell cache 版本。
- Modify: `tests/test_ima_documents.py` — 配置、发现、兼容迁移、逐群同步和 store/API 测试。
- Modify: `tests/test_frontend_interactions.py` — 管理员渲染、文档选择器、来源显示、URL 状态和响应式样式静态回归。

所有测试先写入对应测试文件并确认失败，再修改生产代码。每个任务完成后只提交该任务涉及的文件；不触碰现有研究文件和真实 token 配置。

## Task 1: 建立群组配置模型和旧配置兼容

**Files:**
- Modify: `app/ima_documents.py:36-165`
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_ima_documents.py` 中加入以下行为测试。测试使用 `FakeDB`，不读取真实数据库：

```python
def test_config_migrates_legacy_single_group():
    db = FakeDB({
        "ima_pure_uid": "uid",
        "ima_pure_refresh_token": "refresh",
        "ima_pure_knowledge_base_id": "kb-old",
        "ima_pure_root_folder_id": "folder-old",
    })
    cfg = ImaDocumentConfig.from_db(db)
    assert len(cfg.groups) == 1
    assert cfg.groups[0].name == "IMA 文档"
    assert cfg.groups[0].knowledge_base_id == "kb-old"
    assert cfg.groups[0].root_folder_id == "folder-old"
    assert cfg.groups[0].source == "manual"


def test_config_reads_group_registry_without_exposing_token():
    db = FakeDB({
        "ima_pure_refresh_token": "refresh-secret",
        "ima_pure_groups": json.dumps([
            {
                "id": "banking",
                "name": "投行研报",
                "knowledge_base_id": "kb-1",
                "root_folder_id": "folder-1",
                "enabled": True,
                "source": "discovered",
            }
        ], ensure_ascii=False),
    })
    public = ImaDocumentConfig.from_db(db).public()
    assert public["groups"] == [{
        "id": "banking",
        "name": "投行研报",
        "knowledge_base_id": "kb-1",
        "root_folder_id": "folder-1",
        "enabled": True,
        "source": "discovered",
    }]
    assert "refresh-secret" not in json.dumps(public)


def test_config_ignores_malformed_group_registry_and_uses_legacy_group():
    db = FakeDB({
        "ima_pure_groups": "not-json",
        "ima_pure_knowledge_base_id": "kb-old",
        "ima_pure_root_folder_id": "folder-old",
    })
    cfg = ImaDocumentConfig.from_db(db)
    assert [group.knowledge_base_id for group in cfg.groups] == ["kb-old"]
```

Add `import json` at the top of the test file.

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'migrates_legacy_single_group or reads_group_registry or malformed_group_registry'
```

Expected: FAIL because `ImaDocumentConfig` has no `groups` field and `ima_pure_groups` is not parsed.

- [ ] **Step 3: Implement the smallest configuration model**

In `app/ima_documents.py`, add the setting key and immutable group type:

```python
IMA_PURE_GROUPS_KEY = "ima_pure_groups"

@dataclass(frozen=True)
class ImaGroupConfig:
    id: str
    name: str
    knowledge_base_id: str
    root_folder_id: str
    enabled: bool = True
    source: str = "manual"

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "knowledge_base_id": self.knowledge_base_id,
            "root_folder_id": self.root_folder_id,
            "enabled": self.enabled,
            "source": self.source,
        }
```

Extend `ImaDocumentConfig` with `groups: tuple[ImaGroupConfig, ...] = ()`. Add these helpers before the dataclass:

```python
def _legacy_group(kb: str, root: str) -> ImaGroupConfig:
    return ImaGroupConfig(
        id=f"legacy:{kb}:{root}",
        name="IMA 文档",
        knowledge_base_id=kb,
        root_folder_id=root,
    )


def _read_groups(db: Any, kb: str, root: str) -> tuple[ImaGroupConfig, ...]:
    raw = db.get_setting(IMA_PURE_GROUPS_KEY) if db is not None else None
    if raw:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            payload = []
        groups = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            group_id = str(item.get("id") or "").strip()
            group_kb = str(item.get("knowledge_base_id") or "").strip()
            group_root = str(item.get("root_folder_id") or "").strip()
            if not group_id or not group_kb or not group_root:
                continue
            groups.append(ImaGroupConfig(
                id=group_id,
                name=str(item.get("name") or group_id).strip()[:100],
                knowledge_base_id=group_kb,
                root_folder_id=group_root,
                enabled=bool(item.get("enabled", True)),
                source="discovered" if item.get("source") == "discovered" else "manual",
            ))
        if groups:
            return tuple(groups)
    return (_legacy_group(kb, root),)
```

`from_db()` must read legacy KB/root first, then call `_read_groups(db, kb, root)`. `configured` must require the UID, refresh token, and at least one enabled group with both IDs; it must not require the legacy scalar KB/root when a valid group registry exists. `public()` must include `groups: [group.public() for group in self.groups]` while keeping `refresh_token` represented only by `_secret_status`.

- [ ] **Step 4: Run the tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'migrates_legacy_single_group or reads_group_registry or malformed_group_registry'
```

Expected: 3 passed.

- [ ] **Step 5: Run the existing IMA tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py
```

Expected: all existing IMA tests pass; existing scalar fields remain available.

- [ ] **Step 6: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: add IMA multi-group configuration model"
```

## Task 2: Add discovery normalization and isolate multi-group synchronization

**Files:**
- Modify: `app/ima_documents.py:165-315, 600-760`
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write failing discovery and manifest tests**

Add sanitized fixture tests for the discovery parser and group metadata:

```python
def test_discover_groups_normalizes_knowledge_base_payload():
    payload = {
        "data": {
            "knowledge_base_list": [
                {"knowledge_base_id": "kb-1", "name": "投行研报", "root_folder_id": "folder-1"},
                {"id": "kb-2", "kb_name": "宏观策略", "folder_id": "folder-2"},
            ]
        }
    }
    groups = normalize_discovered_groups(payload)
    assert [(g.id, g.name, g.knowledge_base_id, g.root_folder_id) for g in groups] == [
        ("kb-1", "投行研报", "kb-1", "folder-1"),
        ("kb-2", "宏观策略", "kb-2", "folder-2"),
    ]
    assert all(group.source == "discovered" for group in groups)


def test_merge_groups_updates_discovered_without_deleting_manual():
    existing = (
        ImaGroupConfig("manual-1", "手动群", "kb-manual", "folder-manual", source="manual"),
        ImaGroupConfig("kb-1", "旧名称", "kb-1", "folder-old", source="discovered"),
    )
    discovered = (
        ImaGroupConfig("kb-1", "新名称", "kb-1", "folder-new", source="discovered"),
    )
    merged = merge_groups(existing, discovered)
    assert [(g.id, g.name, g.root_folder_id) for g in merged] == [
        ("manual-1", "手动群", "folder-manual"),
        ("kb-1", "新名称", "folder-new"),
    ]


def test_manifest_records_include_group_context(tmp_path):
    group = ImaGroupConfig("banking", "投行研报", "kb-1", "folder-1")
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client.list_items = lambda folder_id: [
        {"media_type": 99, "folder_info": {"name": "0825", "folder_id": "day-1"}}
    ] if folder_id == "folder-1" else [
        {"media_id": "pdf_1", "name": "report.pdf", "file_size": 4}
    ]
    records = client.manifest()
    assert records[0]["group_id"] == "banking"
    assert records[0]["group_name"] == "投行研报"
```

Add tests for `ImaDocumentStore.save_group_manifest()` replacing only one group's records, including removal of legacy records without `group_id` when the compatibility group is written, and for a sync where the first group raises `RuntimeError` while the second group still calls `manifest()` and returns `failed_groups == ["first"]`.

- [ ] **Step 2: Run the new tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'discover_groups or merge_groups or manifest_records_include_group_context or group_manifest or failed_groups'
```

Expected: FAIL because discovery normalization, grouped manifest persistence, and the `group` argument do not exist.

- [ ] **Step 3: Implement discovery and merge functions**

Add these pure functions in `app/ima_documents.py`:

```python
def normalize_discovered_groups(payload: dict[str, Any]) -> tuple[ImaGroupConfig, ...]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    raw = data.get("knowledge_base_list") or data.get("knowledge_list") or data.get("info_list") or []
    groups = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        group_id = str(item.get("id") or item.get("knowledge_base_id") or "").strip()
        root = str(item.get("root_folder_id") or item.get("folder_id") or "").strip()
        if not group_id or not root:
            continue
        groups.append(ImaGroupConfig(
            id=group_id,
            name=str(item.get("name") or item.get("kb_name") or group_id).strip()[:100],
            knowledge_base_id=group_id,
            root_folder_id=root,
            source="discovered",
        ))
    return tuple(groups)


def merge_groups(
    existing: tuple[ImaGroupConfig, ...],
    discovered: tuple[ImaGroupConfig, ...],
) -> tuple[ImaGroupConfig, ...]:
    by_id = {group.id: group for group in existing}
    for group in discovered:
        previous = by_id.get(group.id)
        by_id[group.id] = ImaGroupConfig(
            id=group.id,
            name=previous.name if previous and previous.source == "manual" else group.name,
            knowledge_base_id=group.knowledge_base_id,
            root_folder_id=group.root_folder_id,
            enabled=previous.enabled if previous else True,
            source=previous.source if previous and previous.source == "manual" else "discovered",
        )
    return tuple(by_id.values())
```

Add `ImaPureClient.discover_groups()` using the existing refresh-token headers and the read-only CGI endpoint already used by the repository probe (`/knowledge_tab_reader/list_knowledge_bases`). It must paginate `cursor`/`next_cursor`, pass the response through `normalize_discovered_groups`, and raise a redacted `RuntimeError` on a non-zero response code. If a discovered item has a knowledge-base ID but no root folder ID, call the existing root `list_items(knowledge_base_id)` once and use the first folder entry's `folder_info.folder_id`; skip the item only when no root folder can be resolved. The service will catch discovery errors; the client must not log token-bearing headers.

Change `ImaPureClient.__init__(config, group=None)` and add `knowledge_base_id` and `root_folder_id` properties that return the group's IDs when `group` is present and the legacy config IDs otherwise. Replace the direct `self.config.knowledge_base_id`/`root_folder_id` reads in `list_items()` and `get_media()` with those properties. `manifest()` must include `group_id` and `group_name` when a group is supplied. Existing calls without `group` keep their current behavior and tests.

- [ ] **Step 4: Implement grouped manifest persistence and service isolation**

Add `ImaDocumentStore.save_group_manifest(group_id, records)` that loads the current manifest, normalizes records without `group_id` to the legacy group ID, removes only records belonging to `group_id`, appends the new records, and saves the combined manifest. When `group_id` is the legacy compatibility group, also replace old records that had no `group_id`; records from other groups remain untouched. `documents()` and `document()` must return normalized `group_id`/`group_name` fields using the configured group metadata.

Refactor the current single-group body of `ImaDocumentService.sync_once()` into a helper with this complete result shape:

```python
def _sync_group(
    self,
    cfg: ImaDocumentConfig,
    group: ImaGroupConfig,
    state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    client = ImaPureClient(cfg, group=group)
    records = client.manifest()
    self.store.save_group_manifest(group.id, records)
    pending = [record for record in records if not self.store.is_complete(record, state)]
    downloaded = 0
    failures = 0
    last_error = ""
    # Move the existing per-record PDF validation, download, TXT conversion,
    # state save, cancellation, and _safe_error logic here, using this client.
    for record in pending:
        if self._cancel_requested:
            break
        media_id = str(record["media_id"])
        pdf = self.store.pdf_path(record)
        txt = self.store.txt_path(record)
        try:
            pdf.parent.mkdir(parents=True, exist_ok=True)
            if pdf.parent.is_symlink():
                raise ValueError("archive directory must not be a symlink")
            if pdf.is_file():
                size, md5 = client._pdf_info(pdf)
                if record.get("size") and size != int(record["size"]):
                    pdf.unlink(missing_ok=True)
            if not pdf.is_file():
                media = client.get_media(media_id)
                result = client.download(media, pdf, int(record.get("size") or 0))
                size, md5 = result["size"], result["md5"]
            else:
                size, md5 = client._pdf_info(pdf)
            chars = convert_pdf(pdf, txt)
            state[media_id] = {
                "group_id": group.id,
                "group_name": group.name,
                "day": record.get("day") or "unknown",
                "name": record.get("name") or media_id,
                "pdf": str(pdf.relative_to(self.store.root)),
                "txt": str(txt.relative_to(self.store.root)),
                "size": size,
                "md5": md5,
                "chars": chars,
                "downloaded_at": datetime.now(UTC).isoformat(),
            }
            self.store.save_state(state)
            downloaded += 1
        except Exception as exc:  # noqa: BLE001 - isolate one bad file
            failures += 1
            last_error = _safe_error(exc)
            logger.warning("IMA document failed media=%s error=%s", media_id[:32], last_error)
    return {
        "group_id": group.id,
        "group_name": group.name,
        "total": len(records),
        "pending": len(pending),
        "downloaded": downloaded,
        "failed": failures,
        "last_error": last_error,
    }
```

The helper keeps the current per-record behavior byte-for-byte except for adding `group_id` and `group_name` to the state entry.

`sync_once()` must call discovery once, merge and persist the registry without clearing manual groups, then loop over the resulting `merged_groups` where `enabled` is true. Persist the merged list as JSON under `IMA_PURE_GROUPS_KEY` before syncing. Catch exceptions around each group, append a redacted `last_error`, and continue. Save `IMA_PURE_LAST_RESULT_KEY` as:

```python
{
  "groups": 2,
  "succeeded_groups": 1,
  "failed_groups": ["投行研报"],
  "downloaded": 3,
  "failed": 1,
  "last_error": "redacted group error"
}
```

The existing top-level `status` values (`not_configured`, `already_running`, `finished`) remain unchanged. `status()` must expose public groups and the aggregate result only.

- [ ] **Step 5: Run focused tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'discover_groups or merge_groups or manifest_records_include_group_context or group_manifest or failed_groups'
.venv/bin/python -m pytest -q tests/test_ima_documents.py
```

Expected: all focused and existing IMA tests pass. The test output must contain no token, signed URL, or absolute archive path.

- [ ] **Step 6: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: sync IMA documents per group"
```

## Task 3: Extend the API without breaking legacy clients

**Files:**
- Modify: `app/api.py:500-530, 2360-2470`
- Modify: `app/ima_documents.py` only if a public group-summary helper is needed.
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write failing API tests**

Use the existing `test_document_api_auth_file_access_and_admin_config(tmp_path, monkeypatch)` test's locally-created `client`, `user_headers`, and `admin_headers` setup pattern. Add two seeded group records to the service store, then add these tests with the same local setup:

```python
def test_document_api_filters_by_group_and_returns_group_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    user_headers = _headers(client, "ima_reader", "IMA001")
    # Seed enabled banking and macro groups, two complete local records, and matching state.
    response = client.get("/api/ima-documents?group=banking", headers=user_headers)
    assert response.status_code == 200
    body = response.json()
    assert {group["id"] for group in body["groups"]} == {"banking", "macro"}
    assert all(item["group_id"] == "banking" for item in body["items"])
    assert body["items"][0]["group_name"] == "投行研报"


def test_document_api_rejects_unknown_group(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    user_headers = _headers(client, "ima_reader", "IMA001")
    response = client.get("/api/ima-documents?group=missing", headers=user_headers)
    assert response.status_code == 400


def test_admin_ima_group_update_preserves_refresh_token(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    admin_headers = _headers(client, "ima_admin", "IMA002", admin=True)
    client.app.state.db.set_setting("ima_pure_refresh_token", "refresh")
    response = client.put(
        "/api/admin/ima-collector",
        headers=admin_headers,
        json={"groups": [{
            "id": "banking",
            "name": "投行研报",
            "knowledge_base_id": "kb-1",
            "root_folder_id": "folder-1",
            "enabled": True,
        }]},
    )
    assert response.status_code == 200
    assert response.json()["config"]["groups"][0]["id"] == "banking"
    assert client.app.state.db.get_setting("ima_pure_refresh_token") == "refresh"
```

Use the existing `_headers()` helper and `TestClient` import; do not invent pytest fixtures.

- [ ] **Step 2: Run the new tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'filters_by_group or rejects_unknown_group or group_update_preserves_refresh_token'
```

Expected: FAIL because the endpoint returns only `items`, does not accept `group`, and `ImaCollectorIn` has no `groups` field.

- [ ] **Step 3: Add request models and strict group validation**

In `app/api.py`, add:

```python
class ImaGroupIn(BaseModel):
    id: str | None = None
    name: str
    knowledge_base_id: str
    root_folder_id: str
    enabled: bool = True


class ImaCollectorIn(BaseModel):
    uid: str | None = None
    refresh_token: str | None = None
    knowledge_base_id: str | None = None
    root_folder_id: str | None = None
    interval_seconds: int | None = None
    groups: list[ImaGroupIn] | None = None
```

Add a local validator in `set_ima_collector()` that trims the name to 100 characters, validates `knowledge_base_id` with `[A-Za-z0-9_-]{1,64}`, validates `root_folder_id` with `[A-Za-z0-9_-]{1,128}`, rejects duplicate IDs, and assigns a deterministic ID `manual-<sha256(kb + "\0" + root)[:16]>` when `id` is omitted. Load the existing group registry before saving so an existing discovered group's `source` is retained when its row is edited manually. Save the resulting JSON with `json.dumps([group.public() for group in groups], ensure_ascii=False)` under `IMA_PURE_GROUPS_KEY`; the endpoint must continue writing the legacy scalar fields when those fields are present. Do not include refresh tokens in audit detail or exception messages.

- [ ] **Step 4: Add group-aware document listing**

Change the endpoint signature to:

```python
@router.get("/ima-documents")
def list_ima_documents(
    q: str = Query("", max_length=200),
    day: str = Query("", max_length=64),
    group: str = Query("", max_length=128),
    user: dict = Depends(get_current_user),
):
```

Use these store contracts so existing `status()` and tests that call `documents()` continue to receive a list:

```python
def documents(
    self,
    query: str = "",
    day: str = "",
    group: str = "",
    groups: tuple[ImaGroupConfig, ...] = (),
) -> list[dict[str, Any]]:
    # Return filtered items; preserve the existing list return type.


def group_summary(
    self,
    groups: tuple[ImaGroupConfig, ...],
) -> list[dict[str, Any]]:
    # Return enabled group IDs, names, and archive counts.
```

`documents()` must normalize legacy records to the compatibility group's ID/name, filter by `group` after validating it against enabled groups, apply the existing query/day filters, and return each item with `group_id`/`group_name` but no paths. `group_summary()` returns all enabled configured groups, including groups with zero documents. The API handler must call `cfg = ima_documents.config()`, validate `group` against `tuple(item for item in cfg.groups if item.enabled)`, then return `{"groups": ima_documents.store.group_summary(cfg.groups), "items": ima_documents.store.documents(q, day, group, cfg.groups)}`. When `group` is non-empty and unknown, the API raises HTTP 400 before calling the store. The public response remains `{"groups": [{"id": "group-id", "name": "群组名称", "count": 0}], "items": []}` and contains no file paths, Refresh Token, Cookie, or signed URL.

Update `get_ima_document()` to include `group_id` and `group_name` so the reader can render context. Leave text/PDF routes and auth unchanged.

- [ ] **Step 5: Run API and security tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'filters_by_group or rejects_unknown_group or group_update_preserves_refresh_token'
.venv/bin/python -m pytest -q tests/test_ima_documents.py
```

Expected: focused tests pass and all existing auth, path, PDF, TXT, and token-redaction tests remain green.

- [ ] **Step 6: Commit**

```bash
git add app/api.py app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: expose IMA group-aware document API"
```

## Task 4: Add minimal administrator group configuration UI

**Files:**
- Modify: `app/static/app.js:4220-4475, 5180-5220`
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write failing static UI tests**

Add tests that read `app/static/app.js` and assert:

```python
def test_ima_admin_config_renders_group_rows_and_save_payload():
    src = APP_JS.read_text()
    config = src[src.index('IMA 文档采集'):src.index('st-cookies')]
    assert 'id="ima-groups"' in config
    assert "addImaGroupRow()" in config
    save = _fn_body("saveImaCollector")
    assert "ima-groups" in save
    assert "groups" in save
    assert "refresh_token" in save
```

Also assert that the admin render has an automatic discovery status element, an enabled checkbox per row, and a remove action with an `aria-label`.

- [ ] **Step 2: Run the new tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k 'ima_admin_config_renders_group_rows'
```

Expected: FAIL because the current admin view has only one KB/root input and `saveImaCollector()` sends scalar fields.

- [ ] **Step 3: Implement the minimal group-row renderer and parser**

Each row must use stable `data-group-index` and contain exactly these elements: a text input with `data-field="name"`, a text input with `data-field="knowledge_base_id"`, a text input with `data-field="root_folder_id"`, a checkbox with `data-field="enabled"`, and a remove button with `aria-label="移除 IMA 群组"`.

Implement:

```javascript
function addImaGroupRow(group = {}) {
  const container = $("#ima-groups");
  if (!container) return;
  container.insertAdjacentHTML("beforeend", imaGroupRowHtml(group, container.children.length));
}

function readImaGroupRows() {
  return [...document.querySelectorAll("#ima-groups [data-group-row]")].map((row) => ({
    id: row.dataset.groupId || null,
    name: row.querySelector('[data-field="name"]')?.value.trim() || "",
    knowledge_base_id: row.querySelector('[data-field="knowledge_base_id"]')?.value.trim() || "",
    root_folder_id: row.querySelector('[data-field="root_folder_id"]')?.value.trim() || "",
    enabled: Boolean(row.querySelector('[data-field="enabled"]')?.checked),
  }));
}
```

The remove button removes only its row. Keep the UI usable when no rows are present by showing the manual fallback empty state.

- [ ] **Step 4: Change admin loading and saving**

Use `imaCollector.config.groups` when rendering rows. Show `imaCollector.last_result` group discovery/sync status without exposing errors that contain URLs or credentials. Update `saveImaCollector()` to send both legacy scalar fields and `groups: readImaGroupRows()` so old server versions fail predictably and current servers persist the registry. After saving, clear only the token input and reload the admin status as today.

- [ ] **Step 5: Run focused frontend tests and syntax checks**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k 'ima_admin_config'
node --check app/static/app.js
```

Expected: focused tests pass and Node reports no syntax errors.

- [ ] **Step 6: Commit**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git commit -m "feat: add IMA group fallback configuration UI"
```

## Task 5: Implement the B+ document list and URL-preserved group switching

**Files:**
- Modify: `app/static/app.js:95-110, 490-560`
- Modify: `app/static/style.css:2575-2620`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write failing list interaction tests**

Add static tests:

```python
def test_ima_document_list_has_group_switcher_and_all_group_source_label():
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    assert 'id="ima-doc-group"' in render
    assert "全部群组" in render
    assert "group" in render
    assert "group_name" in src
    assert "ima-doc-group-label" in src


def test_ima_document_list_preserves_group_in_route_and_reader_back_link():
    src = APP_JS.read_text()
    assert "routeQuery()" in src[src.index("async function renderImaDocuments"):src.index("async function loadImaPdf")]
    reader = _fn_body("renderImaDocument")
    assert "ima-documents?group=" in reader or "group=" in reader
```

Add CSS assertions for `#ima-doc-group` and mobile `min-height: 44px`.

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k 'ima_document_list_has_group_switcher or preserves_group_in_route'
```

Expected: FAIL because the current render has only search/date controls and never sends a group query.

- [ ] **Step 3: Add state and query helpers**

Add `imaDocumentsGroup` to the existing state near `imaDocumentsQuery` and `imaDocumentsDay`. Use the URL as the source of truth when entering the route:

```javascript
function imaDocumentsGroupFromRoute() {
  return routeQuery().get("group") || "";
}

function imaDocumentsRoute(group) {
  const query = new URLSearchParams();
  if (group) query.set("group", group);
  const suffix = query.toString();
  return `ima-documents${suffix ? `?${suffix}` : ""}`;
}
```

On document-page render, set `state.imaDocumentsGroup = imaDocumentsGroupFromRoute()` before building the request. The selection handler must `replaceRoute(imaDocumentsRoute(value))` and render with the current route sequence.

- [ ] **Step 4: Render the B+ controls and group-aware list**

Change the list request to include `group` when selected:

```javascript
if (group) params.set("group", group);
```

Use the API `groups` array to render two synchronized controls: `.ima-doc-group-tabs` is visible on desktop for up to five groups, and `.ima-doc-group-select` is visible on desktop when there are more than five groups and on every mobile width. Both controls call `selectImaDocumentGroup(value)`, which updates `state.imaDocumentsGroup`, clears the day, calls `replaceRoute(imaDocumentsRoute(value))`, and re-renders. The controls use the same option values with `全部群组` first.

Update `imaDocumentRow(item, showGroup)` so `showGroup` controls a `.ima-doc-group-label` line. Call `imaDocumentGroups(items, !state.imaDocumentsGroup)`. The all-group view shows the group label; a specific group view does not. The group header displays the selected group name and count from the response.

Keep the existing search and date controls. Switching group preserves `state.imaDocumentsQuery` and calls `renderImaDocuments(routeRenderSeq)` without a full route transition.

- [ ] **Step 5: Add responsive styles without new visual language**

Add styles beside the existing IMA rules:

```css
.ima-doc-group-switcher { display: flex; align-items: center; gap: 8px; min-width: 180px; }
.ima-doc-group-tabs { display: flex; gap: 4px; min-width: 0; }
.ima-doc-group-tab { min-height: 44px; }
.ima-doc-group-select { display: none; min-height: 44px; }
.ima-doc-group-switcher .form-control { min-height: 44px; }
.ima-doc-group-label { color: var(--color-text-faint); font-size: var(--text-xs); }
.ima-doc-row:focus-visible { outline: 2px solid var(--color-accent); outline-offset: -2px; }

@media (min-width: 769px) {
  .ima-doc-group-switcher.has-many .ima-doc-group-tabs { display: none; }
  .ima-doc-group-switcher.has-many .ima-doc-group-select { display: block; }
}

@media (max-width: 768px) {
  .ima-doc-group-switcher { width: 100%; }
  .ima-doc-group-tabs { display: none; }
  .ima-doc-group-select { display: block; width: 100%; }
  .ima-doc-group-switcher .form-control { width: 100%; min-height: 44px; }
}
```

Do not add shadows, gradients, decorative cards, or a second accent color. Keep long group names clipped inside the selector and allowed to wrap in result metadata.

- [ ] **Step 6: Run focused frontend tests and syntax checks**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k 'ima_document_list or ima_documents_follow_latest_dynamic_navigation'
node --check app/static/app.js
```

Expected: all matching tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/static/app.js app/static/style.css tests/test_frontend_interactions.py
git commit -m "feat: add B-plus IMA group document browsing"
```

## Task 6: Preserve reader context, bump assets, and verify the complete change

**Files:**
- Modify: `app/static/app.js:560-582`
- Modify: `app/static/index.html:132` — increment both `style.css` and `app.js` versions.
- Modify: `app/static/sw.js:1`
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write failing reader/context and asset tests**

Add tests that assert the reader gets group context from the document API, renders it, and returns to the selected group. Update the existing asset test to the next versions, using the actual current values as the base:

```python
def test_ima_reader_shows_group_context_and_restores_group_route():
    reader = _fn_body("renderImaDocument")
    assert "item.group_name" in reader
    assert "item.day" in reader
    assert "imaDocumentsRoute" in reader


def test_ima_asset_urls_bump_for_multi_group_ui():
    html = (APP_JS.parent / "index.html").read_text()
    sw = (APP_JS.parent / "sw.js").read_text()
    assert 'href="/style.css?v=185"' in html
    assert 'src="/app.js?v=258"' in html
    assert 'dav-shell-v128' in sw
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k 'ima_reader_shows_group_context or ima_asset_urls_bump'
```

Expected: FAIL because the reader currently renders only day/name metadata and the assets are still `257`/`127`.

- [ ] **Step 3: Implement reader context and cache invalidation**

Update the reader header to render `item.group_name` before `item.day`, keep the existing name/size/chars/actions, and compute the fallback route before fetching:

```javascript
const backRoute = imaDocumentsRoute(state.imaDocumentsGroup || imaDocumentsGroupFromRoute());
// Use go(backRoute) in the existing load-error action so a direct reader URL can recover context.
```

When opening a row, do not clear the group query. The existing global topbar back button can continue using browser history; the load-error action must call `go(backRoute)`. Keep PDF URL cleanup and download behavior unchanged.

Change `index.html` from `style.css?v=184` to `style.css?v=185`, from `app.js?v=257` to `app.js?v=258`, and `sw.js` from `dav-shell-v127` to `dav-shell-v128`. Update the existing asset assertion to expect both new HTML versions.

- [ ] **Step 4: Run the final verification set**

Run all commands from the repository root:

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py tests/test_frontend_interactions.py
.venv/bin/python -m pytest -q
node --check app/static/app.js
node --check app/static/sw.js
.venv/bin/ruff check app/ima_documents.py app/api.py
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k 'ima'
git diff --check
```

Expected: full suite passes; Node checks pass; Ruff reports no new issues in touched Python production files; the IMA-focused frontend tests pass.

- [ ] **Step 5: Run the required UI detector once**

Run:

```bash
node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json app/static/app.js app/static/style.css app/static/index.html app/static/sw.js
```

Expected: no new high-severity findings in the changed IMA surface. Existing unrelated advisories may be recorded without changing unrelated UI.

- [ ] **Step 6: Perform the bounded browser check**

Start the existing app on an unused local port, authenticate with a test account, and check both desktop and mobile widths. Verify:

1. `全部群组` and each group appear in the selector.
2. Switching group changes only the list area and keeps the search value.
3. All-group results show source group; single-group results do not repeat it.
4. Empty/error states stay inside the document surface.
5. Opening a document and returning restores the group query.
6. Mobile selector and action buttons remain at least 44px high with no horizontal overflow.

If Playwright is unavailable, record that limitation and rely on the static tests, Node checks, and detector output; do not claim screenshot validation.

- [ ] **Step 7: Commit the final UI/context changes**

```bash
git add app/static/app.js app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
git commit -m "fix: preserve IMA group reading context"
```

## Plan self-review

- Spec goal and B+ interaction: Tasks 4–6.
- Group registry, auto discovery, manual fallback: Tasks 1–2 and Task 4.
- Legacy scalar settings and manifest compatibility: Tasks 1–2.
- Group-aware API and permissions: Task 3.
- Per-group failure isolation: Task 2.
- Empty/loading/error states and mobile constraints: Tasks 5–6.
- Token/path redaction and existing auth behavior: Tasks 1–3 and final verification.
- No placeholders, new dependencies, resident watcher, unread model, favorites, or split reader are introduced.
