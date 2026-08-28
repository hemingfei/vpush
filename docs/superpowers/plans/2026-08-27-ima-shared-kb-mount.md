# IMA 共享知识库文件夹挂载实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏旧 IMA 配置和本地归档的前提下，自动发现共享知识库、按需选择文件夹，并递归同步所选目录。

**Architecture:** 扩展现有 `ima_pure_groups` JSON，在 `ImaGroupConfig` 中增加可区分旧回退与显式空挂载的 `folder_ids`。服务端提供管理员发现和一层文件夹目录 API；同步器只从所选根目录递归遍历，使用 visited 集合保护循环和父子重复。静态管理页在现有抓取设置内改成桌面两栏、手机单列，目录选择留在前端 draft，保存时一次原子提交。

**Tech Stack:** FastAPI/Pydantic、现有 `ImaPureClient` 和 `ImaDocumentService`、SQLite settings、静态 `app.js`/`style.css`、pytest `TestClient`、现有设计 token。Python 使用 `.venv/bin/python`。

---

## 文件范围

| 文件 | 职责 |
|---|---|
| `app/ima_documents.py` | 配置兼容、发现状态、文件夹归一化、递归 manifest、同步状态 |
| `app/api.py` | `folder_ids` 请求模型、管理员发现/目录接口、保存校验 |
| `app/static/app.js` | IMA 挂载 draft、知识库列表、懒加载目录树、父子选择、状态与焦点 |
| `app/static/style.css` | 两栏/单列布局、稳定行高、滚动、焦点和长文本布局 |
| `app/static/sw.js`、`app/static/index.html`、`app/version.py` | 实现完成后的静态资源缓存版本递增 |
| `tests/test_ima_documents.py` | 模型、发现合并、目录归一化、递归同步和失败保留 |
| `tests/test_ima_kb.py` | 管理 API、保存校验和端到端配置行为 |
| `tests/test_frontend_interactions.py` | 静态前端契约和 CSS 响应式约束 |
| `docs/superpowers/specs/2026-08-27-ima-shared-kb-mount-design.md` | 已确认的行为基线，不再修改需求 |

不要修改 `docs/research/`、`.cursor/`、`work/` 或用户已有未跟踪文件。

---

### Task 1: 扩展配置模型并保留旧回退

**Files:**
- Modify: `app/ima_documents.py` (`ImaGroupConfig`、`_read_groups`、`merge_groups`、`configured`)
- Modify: `app/api.py`（先加入 `ImaGroupIn.folder_ids` 类型）
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_ima_documents.py` 增加以下测试，验证旧字段、显式空数组和发现默认值不能混淆：

```python
def test_group_folder_ids_distinguish_legacy_fallback_from_explicit_empty():
    legacy_db = FakeDB({
        IMA_PURE_GROUPS_KEY: json.dumps([{
            "id": "legacy", "name": "旧库", "knowledge_base_id": "kb",
            "root_folder_id": "root", "enabled": True,
        }])
    })
    legacy = ImaDocumentConfig.from_db(legacy_db).groups[0]
    assert legacy.folder_ids is None
    assert legacy.mount_folder_ids == ("root",)
    assert legacy.public()["folder_ids"] == ["root"]

    empty_db = FakeDB({
        IMA_PURE_GROUPS_KEY: json.dumps([{
            "id": "new", "name": "新库", "knowledge_base_id": "kb",
            "root_folder_id": "root", "folder_ids": [], "enabled": False,
        }])
    })
    empty = ImaDocumentConfig.from_db(empty_db).groups[0]
    assert empty.folder_ids == ()
    assert empty.mount_folder_ids == ()
    assert empty.public()["folder_ids"] == []
    assert empty.public()["mounted_folder_count"] == 0


def test_merge_groups_preserves_mounts_and_new_discovered_group_is_unmounted():
    existing = (
        ImaGroupConfig(
            "old", "旧名称", "kb-old", "root-old", True, "discovered",
            ("folder-kept",),
        ),
    )
    discovered = (
        ImaGroupConfig("old", "新名称", "kb-old", "root-new"),
        ImaGroupConfig("new", "新库", "kb-new", "root-new"),
    )
    merged = merge_groups(existing, discovered, discovery_complete=True)
    assert [(g.id, g.name, g.root_folder_id, g.mount_folder_ids) for g in merged] == [
        ("old", "新名称", "root-new", ("folder-kept",)),
        ("new", "新库", "root-new", ()),
    ]
    assert merged[1].enabled is False


def test_merge_groups_failed_discovery_keeps_stale_discovered_groups():
    existing = (ImaGroupConfig("gone", "旧库", "kb-gone", "root", True, "discovered", ("f",)),)
    assert merge_groups(existing, (), discovery_complete=False) == existing
```

保留已有旧 `ImaGroupConfig` 四参数调用，新增字段必须放在 `enabled` 和 `source` 之后，避免位置参数错位。

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'folder_ids or merge_groups'
```

Expected: FAIL，现有 dataclass 没有 `folder_ids`、`mount_folder_ids` 或 `mounted_folder_count`。

- [ ] **Step 3: Implement the minimal model change**

在 `ImaGroupConfig` 末尾增加 `folder_ids: tuple[str, ...] | None = None`，并实现：

```python
@property
def mount_folder_ids(self) -> tuple[str, ...]:
    if self.folder_ids is None:
        return (self.root_folder_id,) if self.enabled and self.root_folder_id else ()
    return self.folder_ids
```

`public()` 输出 `folder_ids=list(self.mount_folder_ids())` 和 `mounted_folder_count=len(self.mount_folder_ids())`。`_read_groups()` 对 JSON 中存在的 `folder_ids` 只接受字符串列表，去空白、精确去重；字段缺失保留 `None`。若旧 `enabled=false` 且字段缺失，保持 `None`，`mount_folder_ids` 自然为空。

`merge_groups(existing, discovered, discovery_complete=False)`：

- 保留已有组的 `folder_ids`、enabled 和手工字段。
- 新 discovered 组使用 `folder_ids=()`、`enabled=False`。
- 只有 `discovery_complete=True` 时才删除未出现在本次结果中的 discovered 组。

`ImaDocumentConfig.configured` 改为检查 `group.enabled and group.mount_folder_ids`。`ImaPureClient.effective_*` 仍保留旧逻辑供现有调用使用。

在 `ImaGroupIn` 增加：

```python
folder_ids: list[str] | None = None
```

- [ ] **Step 4: Run focused tests and existing IMA tests**

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'folder_ids or merge_groups'
.venv/bin/python -m pytest -q tests/test_ima_documents.py tests/test_ima_kb.py
```

Expected: 新测试和已有旧配置/发现/群组测试全部 PASS；若旧发现测试依赖新库 `enabled=True`，只调整其预期为新库未挂载，不改变旧群组行为。

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py app/api.py tests/test_ima_documents.py
git commit -m "feat: model IMA folder mounts compatibly"
```

---

### Task 2: 实现目录归一化与递归 manifest

**Files:**
- Modify: `app/ima_documents.py` (`ImaPureClient.manifest` 及辅助函数)
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write the failing tests**

增加以下测试，覆盖直接文件、任意深度、重复根、循环、路径和日期：

```python
def test_manifest_recurses_selected_folders_and_keeps_folder_metadata():
    group = ImaGroupConfig(
        "research", "研究", "kb", "root", True, "discovered", ("mount-a", "child-a")
    )
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    responses = {
        "mount-a": [
            {"media_id": "pdf_direct", "name": "直接.pdf", "file_size": 8},
            {"media_type": 99, "folder_info": {"folder_id": "child-a", "name": "0826"}},
        ],
        "child-a": [
            {"media_type": 99, "folder_info": {"folder_id": "child-b", "name": "研报"}},
        ],
        "child-b": [
            {"media_id": "pdf_nested", "name": "嵌套.pdf", "file_size": "9"},
        ],
    }
    calls = []
    def list_items(folder_id):
        calls.append(folder_id)
        return responses[folder_id]
    client.list_items = list_items

    records = client.manifest()
    assert {r["media_id"] for r in records} == {"pdf_direct", "pdf_nested"}
    direct = next(r for r in records if r["media_id"] == "pdf_direct")
    nested = next(r for r in records if r["media_id"] == "pdf_nested")
    assert direct["source_folder_id"] == "mount-a"
    assert nested["source_folder_id"] == "child-b"
    assert nested["source_root_folder_id"] == "mount-a"
    assert nested["folder_path"] == ["0826", "研报"]
    assert nested["day"] == "0826"
    assert calls.count("child-a") == 1
    assert calls.count("mount-a") == 1


def test_manifest_deduplicates_overlapping_roots_and_stops_folder_cycles():
    group = ImaGroupConfig(
        "research", "研究", "kb", "root", True, "discovered", ("root-a", "root-b")
    )
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    responses = {
        "root-a": [
            {"media_type": 99, "folder_info": {"folder_id": "root-b", "name": "A"}},
            {"media_id": "pdf_same", "name": "同一份.pdf", "file_size": 8},
        ],
        "root-b": [
            {"media_type": 99, "folder_info": {"folder_id": "root-a", "name": "B"}},
            {"media_id": "pdf_same", "name": "同一份.pdf", "file_size": 8},
        ],
    }
    calls = []
    client.list_items = lambda folder_id: calls.append(folder_id) or responses[folder_id]
    records = client.manifest()
    assert [r["media_id"] for r in records] == ["pdf_same"]
    assert calls.count("root-a") == 1
    assert calls.count("root-b") == 1


def test_manifest_uses_unknown_day_for_non_date_folder_path():
    group = ImaGroupConfig("research", "研究", "kb", "root", True, "discovered", ("mount",))
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client.list_items = lambda folder_id: [{"media_id": "pdf_x", "name": "x.pdf", "file_size": 8}]
    record = client.manifest()[0]
    assert record["day"] == "unknown"
    assert record["folder_path"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'recurses_selected or overlapping_roots or unknown_day'
```

Expected: FAIL，当前 manifest 只读取 `effective_root_folder_id` 的日期子目录，忽略直接文件和 `folder_ids`。

- [ ] **Step 3: Implement directory helpers and traversal**

在 `app/ima_documents.py` 添加局部辅助函数：

- `_folder_id(item) -> str`：按 `folder_info.folder_id`、`folder_id`、`folder_* media_id` 顺序读取并校验格式。
- `_folder_name(item, folder_id) -> str`：按 `folder_info.name`、`name`、`title`、ID 回退。
- `_is_folder_item(item) -> bool`：复用 `classify_item` 的字段语义，同时支持现有 `media_type=99`。
- `_folder_children_hint(item) -> bool | None`：读取 `folder_number`、`sub_folder_count`、`children_count`。

`manifest()` 以 `self.group.mount_folder_ids` 为根；当 `group is None` 时用现有 `effective_root_folder_id`，保证旧调用仍有效。队列元素为 `(folder_id, root_id, path, depth)`，每个群组维护：

```python
visited_folder_ids: set[str]
seen_media_ids: set[str]
```

对每个目录只调用一次 `list_items`。目录条目加入队列，非目录条目走现有 PDF 校验和摘要/封面提取。每条记录添加 `source_folder_id`、`source_root_folder_id` 和 `folder_path`。路径中最后一个匹配 `^\d{4}$` 的名称作为 `day`，否则 `unknown`。

设置常量 `IMA_MAX_FOLDER_DEPTH = 32`、`IMA_MAX_FOLDER_NODES = 10000`。到达上限抛出 RuntimeError，让服务层保留旧 manifest。用短注释说明这是单群组保护上限，不做全局目录扫描。

- [ ] **Step 4: Run focused and regression tests**

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'manifest or group'
.venv/bin/python -m pytest -q tests/test_ima_documents.py tests/test_ima_kb.py
```

Expected: 递归新测试 PASS，原有日期目录、PDF 过滤、摘要、同媒体 ID 分组和增量同步测试 PASS。

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: recursively scan selected IMA folders"
```

---

### Task 3: 服务层发现状态、组隔离与解除挂载

**Files:**
- Modify: `app/ima_documents.py` (`ImaDocumentService`)
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write the failing tests**

增加：

```python
def test_service_discover_success_persists_new_unmounted_groups_and_failure_keeps_config(tmp_path, monkeypatch):
    from app import ima_documents
    db = FakeDB({
        IMA_PURE_UID_KEY: "uid",
        IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
        IMA_PURE_KB_ID_KEY: "kb-old",
        IMA_PURE_ROOT_FOLDER_KEY: "root-old",
        IMA_PURE_GROUPS_KEY: json.dumps([{
            "id": "old", "name": "旧库", "knowledge_base_id": "kb-old",
            "root_folder_id": "root-old", "folder_ids": ["keep"],
            "enabled": True, "source": "discovered",
        }]),
    })
    class FakeClient:
        def __init__(self, config, group=None):
            self.config = config
        def discover_groups(self):
            return (ImaGroupConfig("new", "新库", "kb-new", "root-new"),)
    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    result = service.discover()
    assert result["status"] == "finished"
    saved = json.loads(db.get_setting(IMA_PURE_GROUPS_KEY))
    assert [row["id"] for row in saved] == ["new"]
    assert saved[0]["folder_ids"] == []
    assert saved[0]["enabled"] is False

    class BrokenClient(FakeClient):
        def discover_groups(self):
            raise RuntimeError("https://ima.invalid/?token=secret")
    monkeypatch.setattr(ima_documents, "ImaPureClient", BrokenClient)
    before = db.get_setting(IMA_PURE_GROUPS_KEY)
    failed = service.discover()
    assert failed["status"] == "failed"
    assert db.get_setting(IMA_PURE_GROUPS_KEY) == before
    assert "secret" not in json.dumps(failed)


def test_service_skips_unmounted_group_and_keeps_local_files(tmp_path, monkeypatch):
    from app import ima_documents
    db = FakeDB({
        IMA_PURE_UID_KEY: "uid", IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
        IMA_PURE_KB_ID_KEY: "kb", IMA_PURE_ROOT_FOLDER_KEY: "root",
        IMA_PURE_GROUPS_KEY: json.dumps([{
            "id": "empty", "name": "空库", "knowledge_base_id": "kb",
            "root_folder_id": "root", "folder_ids": [], "enabled": False,
        }]),
    })
    class NeverClient:
        def __init__(self, config, group=None):
            raise AssertionError("unmounted group must not create a sync client")
    monkeypatch.setattr(ima_documents, "ImaPureClient", NeverClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    service.store.save_manifest([{"media_id": "old", "group_id": "empty", "name": "old.pdf"}])
    assert service.sync_once()["groups"] == 0
    assert service.store.load_manifest()[0]["media_id"] == "old"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py -k 'discover_success or unmounted_group'
```

Expected: FAIL，服务没有 `discover()`，且同步当前按 enabled/root 处理。

- [ ] **Step 3: Implement service methods and status**

增加 discovery settings key 和 `ImaDocumentService.discover()`：

- 未配置返回 `status=not_configured`，不写组清单。
- 成功调用 `ImaPureClient.discover_groups()`，再读取最新 `self.config()` 合并，调用 `merge_groups(..., discovery_complete=True)`，一次 settings 写入组清单和 discovery 成功状态。
- 异常调用 `_safe_error()`，只写 discovery 状态，不写 `IMA_PURE_GROUPS_KEY`，返回当前 config 与 `status=failed`。
- 用独立 `_discovery_lock` 避免两个管理员请求同时发现；保存前重新读取配置，避免覆盖并行保存的 folder draft。

更新 `status()` 返回 discovery 状态和每组挂载计数。更新 `sync_once()` 复用同一发现辅助逻辑；发现失败传 `discovery_complete=False`。组循环只处理 `group.enabled and group.mount_folder_ids`，空挂载列入 `skipped_groups`，不清理旧文件。

`_sync_group()` 改用新的 `client.manifest()`；目录遍历异常不调用 `save_group_manifest`。正常组仍替换该组 manifest。取消全部挂载由保存 API调用 `store.save_group_manifest(group_id, [])`，只改索引，不删文件/state。

- [ ] **Step 4: Run service regression tests**

```bash
.venv/bin/python -m pytest -q tests/test_ima_documents.py
```

Expected: PASS；同步旧配置仍下载，网络空响应仍保留 manifest，新增组不下载。

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: persist IMA discovery and isolate mounts"
```

---

### Task 4: 管理 API、字段校验和后端端到端测试

**Files:**
- Modify: `app/api.py`
- Test: `tests/test_ima_kb.py`

- [ ] **Step 1: Write the failing API tests**

增加测试辅助 fake client，并覆盖发现、目录、保存：

```python
def test_admin_ima_discover_and_folder_listing(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-api.sqlite"))
    headers = _headers(client, "mount_admin", "MOUNT01", admin=True)
    service = client.app.state.ima_documents
    class FakeClient:
        def __init__(self, config, group=None):
            self.group = group
        def discover_groups(self):
            return (ImaGroupConfig("kb-new", "新知识库", "kb-new", "root-new"),)
        def list_items(self, folder_id):
            assert self.group.knowledge_base_id == "kb-new"
            return [{
                "media_type": 99,
                "folder_info": {"folder_id": "folder-a", "name": "周报"},
                "folder_number": 2,
            }]
    monkeypatch.setattr("app.ima_documents.ImaPureClient", FakeClient)
    discovered = client.post("/api/admin/ima-collector/discover", headers=headers)
    assert discovered.status_code == 200
    group = discovered.json()["config"]["groups"][0]
    assert group["id"] == "kb-new"
    assert group["folder_ids"] == []
    listed = client.get(
        "/api/admin/ima-collector/groups/kb-new/folders",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()["items"] == [{
        "id": "folder-a", "name": "周报", "parent_id": "root-new",
        "has_children": True, "folder_count": 2,
    }]
    assert client.get(
        "/api/admin/ima-collector/groups/kb-new/folders?parent_id=bad/id",
        headers=headers,
    ).status_code == 400


def test_admin_ima_put_folder_ids_validates_and_keeps_old_client_compat(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-put.sqlite"))
    headers = _headers(client, "mount_put_admin", "MOUNTPUT", admin=True)
    body = {
        "groups": [{
            "id": "group-a", "name": "资料", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "folder_ids": ["f1", "f1", "f2"],
            "enabled": True,
        }]
    }
    response = client.put("/api/admin/ima-collector", headers=headers, json=body)
    assert response.status_code == 200
    saved = client.app.state.db.get_setting(IMA_PURE_GROUPS_KEY)
    assert json.loads(saved)[0]["folder_ids"] == ["f1", "f2"]
    assert json.loads(saved)[0]["enabled"] is True

    old = client.put("/api/admin/ima-collector", headers=headers, json={
        "groups": [{
            "id": "group-a", "name": "资料", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "enabled": True,
        }]
    })
    assert old.status_code == 200
    assert json.loads(client.app.state.db.get_setting(IMA_PURE_GROUPS_KEY))[0]["folder_ids"] == ["f1", "f2"]


@pytest.mark.parametrize("folder_ids", [
    ["bad/id"], [""], [123], ["f"] * 257,
])
def test_admin_ima_put_rejects_invalid_folder_ids(tmp_path, monkeypatch, folder_ids):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-invalid.sqlite"))
    headers = _headers(client, "mount_invalid_admin", "MOUNTINV", admin=True)
    response = client.put("/api/admin/ima-collector", headers=headers, json={
        "groups": [{
            "id": "group-a", "name": "资料", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "folder_ids": folder_ids,
        }]
    })
    assert response.status_code == 400, response.text
```

也增加非管理员访问发现和目录接口必须返回 401/403 的断言，以及发现失败响应不得包含 `token=secret`。

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest -q tests/test_ima_kb.py -k 'admin_ima_discover or folder_ids'
```

Expected: FAIL，路由不存在或保存响应没有 `folder_ids`。

- [ ] **Step 3: Implement API routes and validation**

在 `ImaGroupIn` 保持旧字段必填，加入可省略 `folder_ids`。在保存循环中：

1. `folder_ids is None` 时取已有 group 的有效数组；若没有已有数组按 `enabled/root_folder_id` 回退。
2. 显式数组逐项检查 `isinstance(value, str)`、strip 后正则 `[A-Za-z0-9_:-]{1,128}`，最多 256 个，精确去重。
3. `enabled=false` 时数组归一化为空；非空数组的新请求将 enabled 设为 true。
4. source 只取数据库已有值，不读客户端字段。
5. 通过 `db.set_settings_atomic` 一次保存。
6. 保存成功后对显式空数组组调用 `save_group_manifest(group_id, [])`，保留本地文件。

增加 `POST /admin/ima-collector/discover`：调用 service `discover()`；`not_configured` 返回 400，网络/IMA 失败返回 200 的 `ok=false` 当前状态。

增加 `GET /admin/ima-collector/groups/{group_id}/folders`：验证 group ID、parent ID，创建 `ImaPureClient(cfg, group=group)`，读取根目录或 parent 一层。只归一化文件夹项并返回 `group_id/parent_id/items`。错误使用 `_safe_error` 后返回 502。

注意路由不能放到带 `{group_id}/acl` 之后造成误匹配；两个路径后缀不同，显式写完整路径并保留 `acl` 路由测试。

- [ ] **Step 4: Run API and full backend tests**

```bash
.venv/bin/python -m pytest -q tests/test_ima_kb.py tests/test_ima_documents.py
```

Expected: PASS，原有管理员群组保存、ACL、订阅、文档 API 和原子写入测试不回归。

- [ ] **Step 5: Commit**

```bash
git add app/api.py tests/test_ima_kb.py
 git commit -m "feat: expose IMA discovery and folder mount APIs"
```

---

### Task 5: 实现两栏挂载设置 UI

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/style.css`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write the failing frontend contract tests**

在 `tests/test_frontend_interactions.py` 增加断言：

```python
def test_ima_mount_settings_use_two_panes_and_lazy_folder_api():
    src = APP_JS.read_text()
    stats = _fn_body("loadAdminStats")
    assert 'class="ima-mount-layout"' in stats
    assert 'id="ima-kb-list"' in stats
    assert 'id="ima-folder-tree"' in stats
    assert "loadImaFolderChildren" in src
    assert "/api/admin/ima-collector/groups/" in src
    assert "/folders?parent_id=" in src
    assert "folder_ids" in _fn_body("saveImaCollector")
    assert "addImaGroupRow" not in stats
    assert "root_folder_id" not in _fn_body("imaGroupRowHtml")


def test_ima_mount_ui_preserves_draft_and_uses_safe_dynamic_text():
    src = APP_JS.read_text()
    for name in (
        "imaMountState", "renderImaMountGroups", "renderImaFolderTree",
        "toggleImaFolder", "imaSafeError", "focusId",
    ):
        assert name in src
    for fn in ("imaMountGroupRowHtml", "imaFolderRowHtml", "imaGroupDiscoveryStatusText"):
        body = _fn_body(fn)
        assert "escapeHtml" in body
    render = _fn_body("renderStatsData")
    assert "renderImaMountGroups" not in render


def test_ima_mount_css_stacks_at_800px_and_keeps_touch_targets():
    css = STYLE_CSS.read_text()
    assert ".ima-mount-layout" in css
    assert ".ima-folder-tree" in css
    narrow = _media_block(css, "@media (max-width: 800px)")
    assert re.search(r"\.ima-mount-layout\s*\{[^}]*grid-template-columns:\s*1fr", narrow)
    assert re.search(r"\.ima-mount-kb-row[^}]*min-height:\s*44px", css)
    assert re.search(r"\.ima-folder-row[^}]*min-height:\s*44px", css)
```

- [ ] **Step 2: Run frontend tests to verify they fail**

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k 'mount_settings or mount_ui or mount_css'
```

Expected: FAIL，当前仍渲染 `imaGroupRowHtml` 手工表单。

- [ ] **Step 3: Implement state and rendering**

在 `app.js` 增加单一 draft 状态：

```javascript
const imaMountState = {
  groups: [], selectedGroupId: "", drafts: new Map(), children: new Map(),
  loading: new Set(), errors: new Map(), discoveryBusy: false,
  dirty: false, discoveryEntered: false, requestSeq: 0,
};
```

实现以下函数：

- `initImaMountState(groups)`：以 group ID 建立 draft set，保留每组 `folder_ids`。
- `renderImaMountGroups()`：左栏按钮显示名称、source 和挂载数量，动态文本全部 `escapeHtml`。
- `selectImaMountGroup(id)`：保存当前选中 ID，按缓存优先加载根目录；用 request sequence 丢弃过期响应。
- `loadImaFolderChildren(groupId, parentId, force=false)`：调用目录 API，成功按 `${groupId}:${parentId}` 缓存；失败只写当前节点错误并提供 retry 按钮。
- `renderImaFolderTree(groupId)`：渲染已加载节点和 orphan selection；每个展开按钮设置 `aria-expanded`，每个 checkbox 使用稳定 ID/label。
- `toggleImaFolder(groupId, folderId, checked)`：父选中时移除已知后代；父取消移除父选择；重新计算 `checked/indeterminate/disabled`，不发送请求。
- `discoverImaGroups()`：禁用按钮期间只更新 discovery 状态；成功合并服务端组到 draft，失败保留整个 mount state。
- `readImaMountGroups()`：发送完整旧字段加显式 `folder_ids`，`enabled = folder_ids.length > 0`。

替换旧 `renderImaGroupRows/addImaGroupRow/removeImaGroupRow/readImaGroupRows` 在 IMA 文档采集区域的使用；可以保留无调用的旧函数一段时间，但测试必须确认新区域不渲染手工输入和添加按钮。知识库 ID、根目录 ID使用 hidden input 只提交兼容值。

进入 `config` tab 时只触发一次自动发现。状态轮询的 `renderStatsData` 只能更新状态元素，不能调用 mount renderer。保存前记录 `document.activeElement.id`，保存成功整页刷新后恢复该 ID；发现、目录加载不整页刷新。

- [ ] **Step 4: Implement CSS with existing tokens**

在 IMA settings 样式附近增加：

```css
.ima-mount-layout {
  display: grid;
  grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
  gap: var(--space-4);
  min-width: 0;
}
.ima-mount-pane {
  min-width: 0;
  border: var(--border-default);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  overflow: hidden;
}
.ima-mount-pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: 52px;
  padding: 8px 12px;
  border-bottom: var(--border-default);
}
.ima-mount-pane-head > * { min-width: 0; }
.ima-mount-pane-head .section-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ima-kb-list, .ima-folder-tree {
  max-height: 460px;
  overflow: auto;
  min-width: 0;
}
.ima-mount-kb-row, .ima-folder-row {
  min-height: 44px;
  width: 100%;
  min-width: 0;
  border: 0;
  border-top: var(--border-default);
  background: transparent;
}
```

实际实现中使用现有 token 替代硬编码颜色/间距；行内名称允许 `overflow-wrap:anywhere`，计数区域 `flex-shrink:0`；按钮 focus 使用全局 `:focus-visible`。目录树内部仅目录列表滚动。`@media (max-width: 800px)` 将 `.ima-mount-layout` 设为单列、两栏顺序保持知识库再文件夹，保存按钮宽度 100%，所有按钮/checkbox 外围可点击区域至少 44px。不要添加渐变、装饰 blob、额外阴影或新圆角体系。

- [ ] **Step 5: Run static frontend tests and syntax check**

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py
node --check app/static/app.js
git diff --check
```

Expected: PASS；旧 IMA 交互契约按新布局更新，其他设置页测试不变。

- [ ] **Step 6: Commit**

```bash
git add app/static/app.js app/static/style.css tests/test_frontend_interactions.py
git commit -m "feat: add IMA folder mount settings UI"
```

---

### Task 6: 缓存版本、完整自动化验收和真实浏览器检查

**Files:**
- Modify: `app/static/sw.js`、`app/static/index.html`、`app/version.py`（只在静态资源版本机制需要时）
- Test: all existing test files touched by the feature

- [ ] **Step 1: Run the complete automated suite before browser work**

```bash
.venv/bin/python -m pytest -q
node --check app/static/app.js
git diff --check
```

先修复真实失败，不通过时不进行完成声明或实测挂载。

- [ ] **Step 2: Start a local server on an unused port**

检查默认开发端口是否占用；若已占用选择另一个端口。使用项目现有启动命令启动服务，并记录实际 URL。不要覆盖用户已有运行进程。

- [ ] **Step 3: Verify desktop UI at 1440px**

使用真实浏览器打开管理员后台的抓取设置：

1. 检查 IMA 连接区、发现状态和两栏布局不横向溢出。
2. 发现多个库，确认左栏每行名称和挂载数，点击不同库只加载对应根目录。
3. 展开至少两层，选中父目录，确认子目录继承 checked/disabled；刷新状态期间草稿不丢。
4. 选中长名称库/长名称目录，确认没有遮挡、重叠和布局跳动。
5. 取消父目录、选择另一个目录，保存后确认请求 payload 含正确 `folder_ids`，保存后焦点回到保存按钮或原控件。
6. 模拟目录失败、发现失败，确认错误只出现在当前区域且有重试，旧列表和 draft 保留。

- [ ] **Step 4: Verify mobile UI at 390px**

1. 使用 390px 宽打开同一设置页，确认顺序是知识库列表在前、文件夹列表在后。
2. 检查行、展开按钮、复选框、发现和保存按钮均可触控，最小高度 44px。
3. 用超长中文名称、空目录、加载中、失败态检查换行/省略和无水平滚动。
4. 切换库后返回，确认每个库的 draft 仍在；保存后不出现遮挡或页面跳到错误位置。

- [ ] **Step 5: Real IMA account discovery and mount test**

只在自动化、静态检查和浏览器验收全部通过后执行：

1. 读取本机已有 `data/ima_web.env` 或服务端环境中的 IMA 凭证，不在终端命令参数、日志或回复中打印 Token。
2. 用正式发现接口 `POST /api/admin/ima-collector/discover` 获取当前账号清单，核对新增的两个知识库名称/ID；若发现结果仍只含旧库，停止挂载并报告 IMA 权限/账号可见性证据。
3. 对两个新库分别调用 folder API 根目录，选择可确认的目标文件夹。默认只选择最小、可验证的目录，不勾选整个库，避免未授权的大量下载；若根目录只有一个明确业务目录，选择该目录。
4. 通过设置页保存，确认新组 `folder_ids` 非空、`enabled=true`，新库保存前没有产生下载。
5. 触发一次同步，观察每组 `folder_count/total/downloaded/failed` 和 manifest；确认只出现所选目录的 PDF，直接文件与嵌套文件都能处理。
6. 二次同步确认已下载文件不重复下载；对已存在同名/重复媒体 ID检查 state key 和本地路径不冲突。
7. 记录实际测试结果：两个知识库的脱敏名称、所选文件夹名称、发现时间、同步统计、失败项和是否保留旧 manifest。凭证值、签名 URL 和完整请求头不得记录。

- [ ] **Step 6: Final completion audit**

确认每一项都具备证据：

- `folder_ids` 配置和旧回退测试通过。
- 发现成功/失败、目录 API、字段校验和同步隔离测试通过。
- 递归、父子重复、循环、上限和本地文件保留测试通过。
- 桌面/手机真实浏览器无溢出、遮挡、焦点和 draft 丢失。
- 本机新两个知识库实际发现并完成一次小范围挂载同步，或明确记录阻塞原因。
- `pytest`、`node --check`、`git diff --check` 全部通过。

在以上证据齐全前不标记本任务完成。
