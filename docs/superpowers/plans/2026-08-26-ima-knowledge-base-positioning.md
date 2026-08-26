# IMA 知识库定位 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 IMA 文档中心改成「知识库」：按库授权+订阅、元数据优先阅读、复用现有词表/股票名自动打标，采集和 PDF 落盘不动，不进时间线。

**Architecture:** 采集、群组注册表、PDF/TXT 仍走 `app/ima_documents.py`。新建 `app/ima_kb.py` 只管「谁能订 / 谁订了 / 谁能读」。条目多出来的 `abstract`、`cover_url`、`tags` 写进现有 manifest/state。API 路径保持 `/api/ima-documents*`，前端路由改成 `knowledge`。

**Tech Stack:** FastAPI、SQLite、现有 `app/tagging.py` 规则打标、`app/static/app.js` SPA。

**Spec:** `docs/superpowers/specs/2026-08-26-ima-knowledge-base-positioning-design.md`

**Depends on (already on main):** 多群组文档中心。不要改按群间隔调度，除非回归时发现被误伤。

---

## File map

| File | Responsibility |
|---|---|
| Create: `app/ima_kb.py` | 管理员旁路、可读库、目录（已订阅/可订阅）、订阅校验 |
| Create: `tests/test_ima_kb.py` | 权限、目录、订阅、API 过滤 |
| Modify: `app/tagging.py` | 增加 `tag_text(title, content, ...)`，复用现有规则 |
| Modify: `app/db.py` | `ima_kb_acl` / `ima_kb_subscriptions` 表与方法；删用户时级联 |
| Modify: `app/ima_documents.py` | manifest 写摘要/封面；state 写 tags；`documents()` 支持 `tag`、无文件也可列元数据 |
| Modify: `app/api.py` | 列表/详情按权限过滤；`catalog` / subscribe / admin ACL；`tag` 查询 |
| Modify: `app/main.py` | SPA 前缀加 `knowledge` |
| Modify: `app/static/app.js` | 入口改名、页签、库卡片、标签筛选、阅读页、后台授权 |
| Modify: `app/static/style.css` | 页签/库卡片/标签条，沿用现有 IMA 样式 |
| Modify: `app/static/index.html` | `app.js` / 如有 CSS 改动则升 `?v=` |
| Modify: `tests/test_ima_documents.py` | 全员可读 → 管理员或授权+订阅 |
| Modify: `tests/test_spa_routes.py` | `/knowledge` |
| Modify: `tests/test_frontend_interactions.py` | 导航与时间线入口文案 |
| Modify: `README.md` | 用户可见名称改为知识库（采集说明保留） |

不要新建第三套 ima 抓取，不要把库写入 `kols` / `posts`。

---

### Task 1: `tag_text` 复用现有打标规则

**Files:**
- Modify: `app/tagging.py`（在 `stock_tag_posts` 之后）
- Test: `tests/test_ima_kb.py`（本文件本任务创建）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ima_kb.py
from app.tagging import tag_text


def test_tag_text_uses_vocab_and_stock_names():
    tags = tag_text(
        "宁德时代产业链点评",
        "新能源车需求回暖，宁德时代排产上修。",
        tag_rules=[{"tag": "新能源", "keywords": ["新能源车", "排产"]}],
        stock_names=["宁德时代", "贵州茅台"],
        aliases=[{"alias": "宁王", "stock": "宁德时代"}],
    )
    assert "新能源" in tags
    assert "宁德时代" in tags
    assert tags.count("宁德时代") == 1


def test_tag_text_empty_when_no_hit():
    assert tag_text("无标题", "无关正文", tag_rules=[], stock_names=[], aliases=[]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ima_kb.py::test_tag_text_uses_vocab_and_stock_names -v`

Expected: FAIL with `ImportError` or `tag_text` is not defined

- [ ] **Step 3: Write minimal implementation**

在 `app/tagging.py` 的 `stock_tag_posts` 之后加入：

```python
def tag_text(
    title: str,
    content: str,
    tag_rules,
    stock_names,
    aliases=None,
) -> list[str]:
    """对任意标题+正文跑现有规则，返回话题标签+股票标签（总上限 5）。"""

    class _Doc:
        def __init__(self, title: str, content: str):
            self.title = title
            self.content = content

    docs = [_Doc(title or "", content or "")]
    topic = list((rule_tag_posts(docs, tag_rules).get(0) or [])[:TAG_PER_POST_MAX])
    stocks = list((stock_tag_posts(docs, stock_names, aliases).get(0) or [])[:STOCK_PER_POST_MAX])
    merged: list[str] = []
    for tag in topic + stocks:
        if tag and tag not in merged:
            merged.append(tag)
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ima_kb.py::test_tag_text_uses_vocab_and_stock_names tests/test_ima_kb.py::test_tag_text_empty_when_no_hit -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ima_kb.py app/tagging.py
git commit -m "feat: add tag_text helper for knowledge-base documents"
```

---

### Task 2: ACL 与订阅表

**Files:**
- Modify: `app/db.py`（`SCHEMA` 末尾索引前、`_migrate`、`delete_user`、KOL ACL 方法附近）
- Test: `tests/test_ima_kb.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_ima_kb.py
from app.db import DB


def test_ima_kb_acl_and_subscribe_roundtrip(tmp_path):
    db = DB(tmp_path / "kb.sqlite")
    admin_id = db.add_user("kb_admin", "hash", is_admin=True)
    user_id = db.add_user("kb_user", "hash", is_admin=False)
    db.set_ima_kb_acl("banking", [user_id])
    assert db.ima_kb_acl_usernames("banking") == ["kb_user"]
    assert db.ima_kb_can_subscribe(user_id, "banking") is True
    assert db.ima_kb_can_subscribe(admin_id, "banking") is False
    assert db.ima_kb_can_read(user_id, "banking") is False
    db.ima_kb_subscribe(user_id, "banking")
    assert db.ima_kb_can_read(user_id, "banking") is True
    db.set_ima_kb_acl("banking", [])
    assert db.ima_kb_can_read(user_id, "banking") is False
    assert db.ima_kb_is_subscribed(user_id, "banking") is False


def test_delete_user_clears_ima_kb_rows(tmp_path):
    db = DB(tmp_path / "kb-del.sqlite")
    user_id = db.add_user("gone", "hash", is_admin=False)
    db.set_ima_kb_acl("kb1", [user_id])
    db.ima_kb_subscribe(user_id, "kb1")
    db.delete_user(user_id)
    assert db.ima_kb_acl_usernames("kb1") == []
    assert db.ima_kb_is_subscribed(user_id, "kb1") is False
```

用户创建一律用 `DB.add_user(username, password_hash, is_admin=...)`。

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ima_kb.py::test_ima_kb_acl_and_subscribe_roundtrip -v`

Expected: FAIL with `AttributeError: set_ima_kb_acl`

- [ ] **Step 3: Add schema, migrate, and methods**

在 `SCHEMA` 的 `CREATE INDEX IF NOT EXISTS idx_kol_acl_user` 附近加入：

```sql
CREATE TABLE IF NOT EXISTS ima_kb_acl (
    group_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (group_id, user_id)
);
CREATE TABLE IF NOT EXISTS ima_kb_subscriptions (
    user_id INTEGER NOT NULL,
    group_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_ima_kb_acl_user ON ima_kb_acl(user_id);
CREATE INDEX IF NOT EXISTS idx_ima_kb_sub_group ON ima_kb_subscriptions(group_id);
```

在 `_migrate` 里对现有库再执行同样的 `CREATE TABLE IF NOT EXISTS` / index（与 `webpush_subscriptions` 那段相同模式）。

在 `set_kol_acl` 附近加入（`created_at` 用 `int(time.time())`）：

```python
def set_ima_kb_acl(self, group_id: str, user_ids: list[int]) -> None:
    group_id = str(group_id or "").strip()
    allowed = {int(uid) for uid in user_ids}
    with self._lock:
        try:
            self._conn.execute("BEGIN")
            self._conn.execute("DELETE FROM ima_kb_acl WHERE group_id = ?", (group_id,))
            for uid in allowed:
                self._conn.execute(
                    "INSERT OR IGNORE INTO ima_kb_acl (group_id, user_id) VALUES (?, ?)",
                    (group_id, uid),
                )
            self._conn.execute(
                "DELETE FROM ima_kb_subscriptions WHERE group_id = ? AND user_id NOT IN (%s)"
                % (",".join("?" * len(allowed)) if allowed else "NULL"),
                (group_id, *allowed) if allowed else (group_id,),
            )
            if not allowed:
                self._conn.execute(
                    "DELETE FROM ima_kb_subscriptions WHERE group_id = ?", (group_id,)
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
```

空授权时第二条 DELETE 用「删该 group 全部订阅」，不要生成非法 SQL。更干净的写法：先删订阅里不在 `allowed` 的用户：

```python
rows = self._conn.execute(
    "SELECT user_id FROM ima_kb_subscriptions WHERE group_id = ?", (group_id,)
).fetchall()
for row in rows:
    if int(row["user_id"]) not in allowed:
        self._conn.execute(
            "DELETE FROM ima_kb_subscriptions WHERE group_id = ? AND user_id = ?",
            (group_id, row["user_id"]),
        )
```

其余方法：

```python
def ima_kb_acl_usernames(self, group_id: str) -> list[str]:
    return [
        r["username"]
        for r in self._rows(
            "SELECT u.username FROM ima_kb_acl a JOIN users u ON u.id = a.user_id "
            "WHERE a.group_id = ? ORDER BY u.username",
            (group_id,),
        )
    ]

def ima_kb_acl_user_ids(self, group_id: str) -> list[int]:
    return [r["user_id"] for r in self._rows(
        "SELECT user_id FROM ima_kb_acl WHERE group_id = ?", (group_id,)
    )]

def ima_kb_can_subscribe(self, user_id: int, group_id: str) -> bool:
    row = self._rows(
        "SELECT 1 FROM ima_kb_acl WHERE group_id = ? AND user_id = ?",
        (group_id, user_id),
    )
    return bool(row)

def ima_kb_subscribe(self, user_id: int, group_id: str) -> None:
    self._conn.execute(
        "INSERT OR IGNORE INTO ima_kb_subscriptions (user_id, group_id, created_at) VALUES (?, ?, ?)",
        (user_id, group_id, int(time.time())),
    )
    self._conn.commit()

def ima_kb_unsubscribe(self, user_id: int, group_id: str) -> None:
    self._conn.execute(
        "DELETE FROM ima_kb_subscriptions WHERE user_id = ? AND group_id = ?",
        (user_id, group_id),
    )
    self._conn.commit()

def ima_kb_is_subscribed(self, user_id: int, group_id: str) -> bool:
    return bool(self._rows(
        "SELECT 1 FROM ima_kb_subscriptions WHERE user_id = ? AND group_id = ?",
        (user_id, group_id),
    ))

def ima_kb_can_read(self, user_id: int, group_id: str) -> bool:
    return self.ima_kb_can_subscribe(user_id, group_id) and self.ima_kb_is_subscribed(user_id, group_id)
```

`ima_kb_subscribe` / `unsubscribe` 必须和别的写方法一样加 `_lock`。

`delete_user` 在删 `kol_acl` 旁增加：

```python
self._conn.execute("DELETE FROM ima_kb_acl WHERE user_id = ?", (user_id,))
self._conn.execute("DELETE FROM ima_kb_subscriptions WHERE user_id = ?", (user_id,))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ima_kb.py -v`

Expected: PASS（含 Task 1）

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_ima_kb.py
git commit -m "feat: add knowledge-base ACL and subscription tables"
```

---

### Task 3: `ima_kb` 目录与可读集合

**Files:**
- Create: `app/ima_kb.py`
- Test: `tests/test_ima_kb.py`

- [ ] **Step 1: Write the failing tests**

```python
from app.ima_documents import ImaGroupConfig
from app.ima_kb import catalog, readable_group_ids


def _groups():
    return (
        ImaGroupConfig("banking", "投行研报", "kb1", "root1"),
        ImaGroupConfig("macro", "宏观", "kb2", "root2"),
    )


def test_catalog_hides_ungranted_groups_from_users(tmp_path):
    db = DB(tmp_path / "cat.sqlite")
    user_id = db.add_user("reader", "hash", is_admin=False)
    admin_id = db.add_user("owner", "hash", is_admin=True)
    db.set_ima_kb_acl("banking", [user_id])
    user = {"id": user_id, "is_admin": 0}
    admin = {"id": admin_id, "is_admin": 1}
    listed = catalog(db, user, _groups())
    assert [g["id"] for g in listed["available"]] == ["banking"]
    assert listed["subscribed"] == []
    db.ima_kb_subscribe(user_id, "banking")
    listed = catalog(db, user, _groups())
    assert [g["id"] for g in listed["subscribed"]] == ["banking"]
    assert listed["available"] == []
    assert {g["id"] for g in catalog(db, admin, _groups())["subscribed"] + catalog(db, admin, _groups())["available"]} >= {"banking", "macro"}
    assert readable_group_ids(db, user, _groups()) == {"banking"}
    assert readable_group_ids(db, admin, _groups()) == {"banking", "macro"}
```

管理员目录：全部已注册库放进 `subscribed`（管理预览不依赖自己是否订阅），`available` 为空。普通用户严格按 ACL + 订阅拆两个列表。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ima_kb.py::test_catalog_hides_ungranted_groups_from_users -v`

Expected: FAIL with `ImportError: app.ima_kb`

- [ ] **Step 3: Implement `app/ima_kb.py`**

```python
"""IMA 知识库产品层：授权、订阅、可读集合。不负责采集或文件。"""
from __future__ import annotations

from typing import Any, Iterable


def is_admin(user: dict[str, Any]) -> bool:
    return bool(user.get("is_admin"))


def readable_group_ids(db: Any, user: dict[str, Any], groups: Iterable[Any]) -> set[str]:
    ids = {str(group.id) for group in groups}
    if is_admin(user):
        return ids
    return {group_id for group_id in ids if db.ima_kb_can_read(int(user["id"]), group_id)}


def catalog(db: Any, user: dict[str, Any], groups: Iterable[Any]) -> dict[str, list[dict[str, Any]]]:
    items = [
        {"id": group.id, "name": group.name, "enabled": bool(group.enabled)}
        for group in groups
    ]
    if is_admin(user):
        return {"subscribed": items, "available": []}
    uid = int(user["id"])
    subscribed: list[dict[str, Any]] = []
    available: list[dict[str, Any]] = []
    for item in items:
        group_id = item["id"]
        if db.ima_kb_can_read(uid, group_id):
            subscribed.append(item)
        elif db.ima_kb_can_subscribe(uid, group_id):
            available.append(item)
    return {"subscribed": subscribed, "available": available}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ima_kb.py::test_catalog_hides_ungranted_groups_from_users -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_kb.py tests/test_ima_kb.py
git commit -m "feat: add knowledge-base catalog visibility helpers"
```

---

### Task 4: 锁文档 API，加上目录 / 订阅 / 授权

**Files:**
- Modify: `app/api.py`（`list_ima_documents` 一段，`ImaCollectorIn` 附近）
- Modify: `tests/test_ima_documents.py`（现有全员可读断言）
- Test: `tests/test_ima_kb.py`

现网 `GET /api/ima-documents` 对任意登录用户返回全部启用库。本任务改成：默认仅管理员；普通用户必须 ACL+订阅。未知/未授权 `group` 从 400 改为 404。

- [ ] **Step 1: Update existing tests so they express the new contract, then add API tests**

把 `tests/test_ima_documents.py` 里这些用例的读者改成管理员，或先授权再订阅：

- `test_document_api_auth_file_access_and_admin_config`：`user_headers` 读列表应变空/`404`；用 `admin_headers` 断言现有文件访问。另加：给 `ima_reader` 授权+订阅后，用户又能读 `file_abc`。
- `test_group_aware_document_api_returns_summary_and_filters_items` 及后续 group 过滤用例：`headers` 改为 `_headers(..., admin=True)`，因为它们测的是群组筛选而不是 ACL。未知 group 的期望从 `400` 改成 `404`。

在 `tests/test_ima_kb.py` 增加（复用 `tests/test_ima_documents.py` 的 `_headers` 和落盘方式）：

```python
def test_user_cannot_see_kb_until_granted_and_subscribed(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "acl.sqlite"))
    user_headers = _headers(client, "reader", "KBUSER1")
    admin_headers = _headers(client, "owner", "KBADM1", admin=True)
    # 写入一条完整文档到 store（复制 test_document_api_auth 的落盘 10 行）
    listed = client.get("/api/ima-documents", headers=user_headers)
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert client.get("/api/ima-documents/file_abc", headers=user_headers).status_code == 404
    catalog = client.get("/api/ima-documents/catalog", headers=user_headers).json()
    assert catalog["subscribed"] == []
    assert catalog["available"] == []

    client.put(
        "/api/admin/ima-collector/groups/legacy/acl",
        headers=admin_headers,
        json={"usernames": ["reader"]},
    )
    catalog = client.get("/api/ima-documents/catalog", headers=user_headers).json()
    assert [g["id"] for g in catalog["available"]]  # 至少有一个可订库
    assert client.get("/api/ima-documents/file_abc", headers=user_headers).status_code == 404
    group_id = catalog["available"][0]["id"]
    assert client.post(
        f"/api/ima-documents/groups/{group_id}/subscribe", headers=user_headers
    ).status_code == 200
    assert client.get("/api/ima-documents/file_abc", headers=user_headers).status_code == 200
```

`legacy` 是否存在取决于当前注册表：测试里应先 `GET /api/admin/ima-collector` 取 `config.groups[0].id`，用真实 id 授权，不要写死 `legacy`。

再测：未授权用户 `POST subscribe` → 404；撤权后读条目 404。

- [ ] **Step 2: Run the new API test to verify it fails**

Run: `python -m pytest tests/test_ima_kb.py::test_user_cannot_see_kb_until_granted_and_subscribed -v`

Expected: FAIL with 404 on `/catalog` or user still sees items

- [ ] **Step 3: Implement API**

在 `app/api.py` 增加：

```python
from .ima_kb import catalog as ima_kb_catalog, readable_group_ids

class ImaKbAclIn(BaseModel):
    usernames: list[str]
```

**必须把** `GET /ima-documents/catalog`、`POST/DELETE /ima-documents/groups/{group_id}/subscribe` 注册在 `GET /ima-documents/{media_id}` **之前**。

辅助函数（放在 ima-documents 路由闭包里）：

```python
def _configured_groups():
    return ima_documents.config().groups

def _readable_groups(user: dict):
    groups = _configured_groups()
    allowed = readable_group_ids(db, user, groups)
    return tuple(group for group in groups if group.id in allowed)

def _require_readable_group(user: dict, group_id: str):
    readable = _readable_groups(user)
    if group_id and group_id not in {group.id for group in readable}:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return readable
```

改 `list_ima_documents`：

- `groups = _readable_groups(user)`
- 指定 `group` 且不在可读集合 → 404（不再 400）
- `items` / `groups` 摘要都只用 `readable` 集合
- 增加 `tag: str = Query("", max_length=64)`，传给 `store.documents(..., tag=tag)`（Task 5 才会真正过滤；本任务可先把参数接上）

改 `_ima_document`：同样只用 `_readable_groups(user)`。

新路由：

```python
@router.get("/ima-documents/catalog")
def ima_documents_catalog(user: dict = Depends(get_current_user)):
    return ima_kb_catalog(db, user, _configured_groups())

@router.post("/ima-documents/groups/{group_id}/subscribe")
def subscribe_ima_kb(group_id: str, user: dict = Depends(get_current_user)):
    if ima_documents is None:
        raise HTTPException(status_code=503, detail="IMA 文档服务未启用")
    if not re.fullmatch(r"[A-Za-z0-9_:-]{1,128}", group_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if group_id not in {g.id for g in _configured_groups()}:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if user.get("is_admin"):
        db.ima_kb_subscribe(user["id"], group_id)
        return {"ok": True}
    if not db.ima_kb_can_subscribe(user["id"], group_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    db.ima_kb_subscribe(user["id"], group_id)
    _audit(user, "subscribe_ima_kb", group_id)
    return {"ok": True}

@router.delete("/ima-documents/groups/{group_id}/subscribe")
def unsubscribe_ima_kb(group_id: str, user: dict = Depends(get_current_user)):
    db.ima_kb_unsubscribe(user["id"], group_id)
    _audit(user, "unsubscribe_ima_kb", group_id)
    return {"ok": True}

@router.put("/admin/ima-collector/groups/{group_id}/acl", dependencies=[Depends(require_admin)])
def set_ima_kb_acl(group_id: str, body: ImaKbAclIn, admin: dict = Depends(require_admin)):
    if group_id not in {g.id for g in _configured_groups()}:
        raise HTTPException(status_code=404, detail="知识库不存在")
    user_ids = []
    for username in body.usernames:
        target = db.get_user_by_username_ci(username.strip())
        if target is None:
            raise HTTPException(status_code=400, detail=f"用户不存在: {username}")
        user_ids.append(target["id"])
    db.set_ima_kb_acl(group_id, user_ids)
    _audit(admin, "set_ima_kb_acl", group_id, ",".join(body.usernames))
    return {"ok": True, "acl_usernames": db.ima_kb_acl_usernames(group_id)}
```

`GET /api/admin/ima-collector` 的每个 `config.groups[]` 增加 `acl_usernames`（在 `status()` 之后补，或改 `ImaGroupConfig.public()` 不合适——ACL 不在 group JSON 里）。在 API 层：

```python
payload = ima_documents.status()
for group in payload.get("config", {}).get("groups", []):
    group["acl_usernames"] = db.ima_kb_acl_usernames(group["id"])
return payload
```

- [ ] **Step 4: Run API tests**

Run:

```
python -m pytest tests/test_ima_kb.py tests/test_ima_documents.py -v
```

Expected: PASS。若旧测试仍假设普通用户能读，按 Step 1 改完再跑。

- [ ] **Step 5: Commit**

```bash
git add app/api.py tests/test_ima_kb.py tests/test_ima_documents.py
git commit -m "feat: gate IMA documents behind knowledge-base ACL"
```

---

### Task 5: 条目元数据与标签过滤

**Files:**
- Modify: `app/ima_documents.py`（`ImaDocumentStore.documents` / `document`，约 1073–1175 行；`ImaPureClient.manifest` 约 571–582 行）
- Test: `tests/test_ima_documents.py` 或 `tests/test_ima_kb.py`

- [ ] **Step 1: Write the failing store tests**

```python
def test_documents_include_metadata_and_tag_filter(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {
        "media_id": "file_meta",
        "name": "宁德时代纪要.pdf",
        "day": "0826",
        "abstract": "排产上修",
        "cover_url": "https://example.com/c.jpg",
        "group_id": "banking",
    }
    pdf = store.pdf_path(record)
    txt = store.txt_path(record)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.7")
    txt.write_text("正文", encoding="utf-8")
    store.save_manifest([record])
    store.save_state({
        store.state_key(record): {
            "pdf": str(pdf.relative_to(store.root)),
            "txt": str(txt.relative_to(store.root)),
            "tags": ["新能源", "宁德时代"],
            "has_pdf": True,
            "has_txt": True,
        }
    })
    banking = ImaGroupConfig("banking", "投行", "kb", "root")
    items = store.documents(groups=(banking,))
    assert items[0]["abstract"] == "排产上修"
    assert items[0]["cover_url"] == "https://example.com/c.jpg"
    assert items[0]["tags"] == ["新能源", "宁德时代"]
    assert items[0]["has_pdf"] is True
    assert store.documents(tag="新能源", groups=(banking,))[0]["media_id"] == "file_meta"
    assert store.documents(tag="宏观", groups=(banking,)) == []
    assert store.documents(query="排产", groups=(banking,))[0]["media_id"] == "file_meta"


def test_documents_can_list_metadata_without_files(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima2")
    record = {"media_id": "file_bare", "name": "只有摘要.pdf", "day": "0826", "abstract": "摘要", "group_id": "banking"}
    store.save_manifest([record])
    store.save_state({store.state_key(record): {"tags": []}})
    banking = ImaGroupConfig("banking", "投行", "kb", "root")
    items = store.documents(groups=(banking,))
    assert items[0]["media_id"] == "file_bare"
    assert items[0]["has_pdf"] is False
    assert items[0]["has_txt"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ima_kb.py::test_documents_include_metadata_and_tag_filter -v`

Expected: FAIL（缺字段或无文件被跳过）

- [ ] **Step 3: Implement store + manifest fields**

`documents()`：

- 增加参数 `tag: str = ""`。
- 不再要求 pdf/txt 都在才入列。`has_pdf` / `has_txt` 由路径是否为文件决定。
- 输出增加 `abstract`、`cover_url`、`tags`、`has_pdf`、`has_txt`。`tags` 必须是 list[str]，非法值当 `[]`。
- 搜索串改成 `name + day + abstract`。
- `tag` 非空时，条目 `tags` 必须包含该字符串。

`document()`：同样带出这些字段；没有文件时仍返回元数据（`pdf`/`txt` 可以是 `None`）。API 的 text/pdf 在文件缺失时保持 404。

`ImaPureClient.manifest()` 写记录时：

```python
from .fetchers.ima_inspect import item_cover, item_text

record = {
    "media_id": media_id,
    "name": name,
    "day": day,
    "size": file_size or 0,
    "md5": md5_value or "",
    "ts": str(ts_value or ""),
    "abstract": item_text(item)[:2000],
    "cover_url": item_cover(item)[:2000],
}
```

`cover_url` 只接受 `item_cover` 返回的 `http` URL，不要把本地路径写进去。

- [ ] **Step 4: Run store tests**

Run: `python -m pytest tests/test_ima_kb.py::test_documents_include_metadata_and_tag_filter tests/test_ima_kb.py::test_documents_can_list_metadata_without_files tests/test_ima_documents.py -k "document or group_aware or manifest" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_kb.py
git commit -m "feat: persist knowledge-base abstracts covers and tags"
```

---

### Task 6: 采集后打标与存量回填

**Files:**
- Modify: `app/ima_documents.py`（`_sync_group` 写 state 处；`ImaDocumentService.start` / 新方法 `retag_all`）
- Test: `tests/test_ima_kb.py`

- [ ] **Step 1: Write the failing test**

用 FakeDB 配好 `tag_vocabulary` / `stock_names`，构造一个已有 TXT 的完整 record，调用 `ImaDocumentService.retag_all()`，断言 state 里出现标签。

```python
def test_retag_all_writes_tags_from_title_and_txt(tmp_path):
    db = FakeDB({
        "tag_vocabulary": json.dumps([{"tag": "新能源", "keywords": ["排产"]}], ensure_ascii=False),
        "stock_names": json.dumps(["宁德时代"], ensure_ascii=False),
    })
    # FakeDB 若没有 get_tag_vocabulary，给 ImaDocumentService.retag_all 注入真实 DB
```

更稳：用真实 `DB`：

```python
def test_retag_all_writes_tags_from_title_and_txt(tmp_path):
    db = DB(tmp_path / "tag.sqlite")
    db.set_tag_vocabulary([{"tag": "新能源", "keywords": ["排产"]}])
    db.set_stock_names(["宁德时代"])
    service = ImaDocumentService(db, tmp_path / "ima")
    record = {"media_id": "file_tag", "name": "宁德时代纪要.pdf", "day": "0826", "abstract": "排产上修"}
    pdf = service.store.pdf_path(record)
    txt = service.store.txt_path(record)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.7")
    txt.write_text("排产上修，宁德时代", encoding="utf-8")
    service.store.save_manifest([record])
    service.store.save_state({
        service.store.state_key(record): {
            "pdf": str(pdf.relative_to(service.store.root)),
            "txt": str(txt.relative_to(service.store.root)),
        }
    })
    result = service.retag_all()
    assert result["tagged"] >= 1
    state = service.store.load_state()
    tags = state[service.store.state_key(record)]["tags"]
    assert "新能源" in tags
    assert "宁德时代" in tags
```

另写 `test_sync_group_tags_new_download` 只在容易 stub `ImaPureClient` 时做；否则本任务只测 `retag_all`，`_sync_group` 成功写入 state 后调用同一个 `_tag_record(db, store, record, state_item)`。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ima_kb.py::test_retag_all_writes_tags_from_title_and_txt -v`

Expected: FAIL with `AttributeError: retag_all`

- [ ] **Step 3: Implement tagging hook**

在 `app/ima_documents.py`：

```python
def _tag_document(db: Any, record: dict[str, Any], txt: Path | None) -> list[str]:
    from .stock_universe import aliases_for_tagging, names_for_plain_text_tagging
    from .tagging import tag_text

    body = str(record.get("abstract") or "")
    if txt is not None and txt.is_file():
        try:
            body = body + "\n" + txt.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    return tag_text(
        str(record.get("name") or ""),
        body,
        db.get_tag_vocabulary(),
        names_for_plain_text_tagging(db.get_stock_names(), db.get_stock_name_exclusions()),
        aliases_for_tagging(db.get_stock_aliases(), db.get_stock_name_exclusions()),
    )
```

`ImaDocumentService.retag_all(self) -> dict`：遍历 manifest+state，重算 `tags` 写回 state，返回 `{"processed": n, "tagged": m}`。

`_sync_group` 在成功写完一条 state 后：

```python
state[key]["tags"] = _tag_document(self.db, record, txt)
```

`start()` 在 `restore_original_filenames` 之后调用一次 `retag_all()`（只填 `tags` 缺失或空且现在能打出标签的条目也可以；实现选「缺 tags 字段才打」以免每次启动全量扫 TXT。测试里 state 没有 `tags` 键即可被回填）。

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_ima_kb.py::test_retag_all_writes_tags_from_title_and_txt tests/test_ima_documents.py -k "sync or trigger or group" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_kb.py
git commit -m "feat: auto-tag knowledge-base documents on sync"
```

---

### Task 7: 词表维护时清知识库过期标签

**Files:**
- Modify: `app/tagging.py`（`run_tag_maintenance` 末尾，约 585–600 行）或 `app/api.py` 里触发维护的接口
- Modify: `app/main.py` 仅当维护入口拿得到 `ima_documents` 时调用 `retag`/`purge`
- Test: `tests/test_ima_kb.py`

规格：不新开每日任务；挂在现有标签维护之后。

- [ ] **Step 1: Write the failing test**

构造 store 条目 `tags=["过期标签", "新能源"]`，`valid` 只有 `新能源`，调用将要写的 `purge_ima_document_tags(store, {"新能源"})`，断言只剩 `新能源`。

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL, function missing

- [ ] **Step 3: Implement `purge_ima_document_tags` in `app/ima_documents.py`**

```python
def purge_ima_document_tags(store: ImaDocumentStore, valid_tags: set[str]) -> int:
    state = store.load_state()
    changed = 0
    for item in state.values():
        if not isinstance(item, dict):
            continue
        tags = [t for t in (item.get("tags") or []) if isinstance(t, str)]
        kept = [t for t in tags if t in valid_tags]
        if kept != tags:
            item["tags"] = kept
            changed += 1
    if changed:
        store.save_state(state)
    return changed
```

在 `run_tag_maintenance` 不要硬依赖 store。在 `app/api.py` 触发标签维护成功后：

```python
if ima_documents is not None:
    valid = {r["tag"] for r in db.get_tag_vocabulary()} | set(db.get_stock_names())
    for alias in db.get_stock_aliases():
        if isinstance(alias, dict) and alias.get("stock"):
            valid.add(str(alias["stock"]))
    purged = purge_ima_document_tags(ima_documents.store, valid)
```

把 `purged` 写进该接口响应或审计 detail。找不到维护接口就搜 `run_tag_maintenance` / `try_run_tag_maintenance` 的 API 调用点。

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_ima_kb.py -k "purge or tag" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py app/api.py tests/test_ima_kb.py
git commit -m "feat: purge stale knowledge-base tags with vocab maintenance"
```

---

### Task 8: 前端入口、页签、库卡片

**Files:**
- Modify: `app/main.py`（`SPA_PREFIXES` 加 `knowledge`，保留 `ima-documents`）
- Modify: `app/static/app.js`（NAV、路由表、`renderImaDocuments`、时间线入口）
- Modify: `app/static/style.css`（页签，沿用 `.settings-tab` / `.ima-docs-shell`）
- Test: `tests/test_spa_routes.py`、`tests/test_frontend_interactions.py`

- [ ] **Step 1: Write / update failing frontend tests**

`tests/test_spa_routes.py` 的路径列表加上 `"/knowledge"`。

`tests/test_frontend_interactions.py` 里：

- 导航断言改为 `route: "knowledge"`、`label: "知识库"`
- 时间线入口 `go('knowledge')`，文案含「知识库」
- `ima-documents` 仍可出现在重定向逻辑里，但侧栏 label 不能再是「IMA 文档」

后台标题「IMA 文档采集」可以保留（管理员配置区），不要改那条「采集不进 Cookie 管理」的测试，除非你同时改了标题。

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_spa_routes.py tests/test_frontend_interactions.py -k "ima or knowledge or nav" -v`

Expected: FAIL on old strings / routes

- [ ] **Step 3: Implement frontend shell**

`app/main.py`：

```python
SPA_PREFIXES = frozenset({
    "timeline", "home", "combinations", "mysubs", "settings",
    "search", "kol", "more", "admin", "zsxq", "ima-documents", "knowledge",
})
```

`app/static/app.js`：

- `NAV`：`{ route: "knowledge", icon: BOOK_ICON, label: "知识库" }`
- 路由白名单数组加上 `"knowledge"`，保留 `"ima-documents"`
- 进入 `page === "ima-documents"` 时 `history.replaceState` 到同等 query 的 `knowledge`（`group`/`q`/`day` 保留），再 `renderKnowledge`
- `renderKnowledge`：先 `GET /api/ima-documents/catalog`
  - 两个页签：已订阅 / 可订阅
  - 已订阅：库卡片，点击进入该库条目列表（沿用现有 `group` 查询）
  - 可订阅：卡片 +「订阅」按钮 → `POST /api/ima-documents/groups/{id}/subscribe`
  - 已订阅卡片提供「退订」
  - 管理员 catalog 的 `subscribed` 即全部库，直接显示卡片
- 普通用户打开 `?group=` 但不在已订阅 → 空态「没有这个知识库」，不要列出别人的库名
- 时间线按钮：`go('knowledge')`，文案「知识库」/「查看已订阅知识库」
- 空态：未授权「暂无可订阅的知识库」；已订阅空「还没有订阅知识库」

库内列表先仍复用现有日期分组和搜索，下一任务再加标签和元数据。

CSS：`.kb-tabs`、`.kb-card`，桌面紧凑、移动端控件 ≥44px。

- [ ] **Step 4: Run frontend/spa tests**

Run: `python -m pytest tests/test_spa_routes.py tests/test_frontend_interactions.py -k "ima or knowledge or nav or timeline" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/static/app.js app/static/style.css tests/test_spa_routes.py tests/test_frontend_interactions.py
git commit -m "feat: rename IMA documents entry to knowledge bases"
```

---

### Task 9: 库内元数据列表、标签筛选、阅读页

**Files:**
- Modify: `app/static/app.js`（`imaDocumentRow`、`renderImaDocuments`、`renderImaDocument`）
- Modify: `app/static/style.css`
- Modify: `app/api.py`（列表/详情 JSON 带 `abstract`/`cover_url`/`tags`/`has_pdf`/`has_txt`；`tag` 已在 Task 4 接上）
- Test: `tests/test_frontend_interactions.py`、`tests/test_ima_kb.py`

- [ ] **Step 1: Write API + frontend assertions**

API：管理员读详情，响应含 `abstract`、`tags`、`has_pdf`。`?tag=新能源` 只返回带该标签的条目。

前端：`app.js` 含 `placeholder="搜索标题或摘要"`、`ima-doc-tag` 或等价 id、阅读页在没有 `has_pdf` 时不渲染「查看 PDF」按钮。

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL missing fields / missing DOM ids

- [ ] **Step 3: Implement**

详情 JSON 补：

```python
"abstract": document.get("abstract") or "",
"cover_url": document.get("cover_url") or "",
"tags": document.get("tags") or [],
"has_pdf": bool(document.get("has_pdf")),
"has_txt": bool(document.get("has_txt")),
```

列表 `items` 已由 store 带出。`cover_url` 不得是本地绝对路径。

前端库内：

- 行/卡片：封面（失败隐藏）、标题、摘要截断、标签 chip、日期、大小
- 标签筛选：`select` 或 chip，选项 = 当前列表里出现过的 tags 去重；`params.set("tag", ...)`
- 阅读页：标题/摘要/封面/标签在最上。`has_txt` 才拉 `/text`；`has_pdf` 才显示查看/下载。两者都无：只显示元数据
- 搜索 placeholder 改为「搜索标题或摘要」
- 去掉普通用户的「全部群组」通看（Task 8 已先选库；库内不要再给普通用户「全部群组」）

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_ima_kb.py tests/test_ima_documents.py tests/test_frontend_interactions.py -k "tag or knowledge or ima-doc or abstract" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api.py app/static/app.js app/static/style.css tests/test_ima_kb.py tests/test_frontend_interactions.py
git commit -m "feat: show knowledge-base metadata and tag filters"
```

---

### Task 10: 后台授权用户 + 缓存版本 + 文档

**Files:**
- Modify: `app/static/app.js`（IMA 采集群组行）
- Modify: `app/static/index.html`（`app.js?v=260` → `261`；若改了 CSS 则 `style.css?v=185` → `186`）
- Modify: `README.md`（「IMA 文档中心」用户入口改为知识库；采集段落可仍写管理员配置）
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write the failing frontend test**

断言采集群组行模板含「授权用户」和 `ima-kb-acl`（或稳定 id）。保存采集时不要误把 ACL 当 groups JSON 的未知字段丢掉——ACL 走独立 `PUT /api/admin/ima-collector/groups/{id}/acl`。

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL, string missing

- [ ] **Step 3: Implement admin field and bump assets**

每行群组：在启用/间隔之后加

```html
<label class="cfg-field cfg-field--wide"><span>授权用户</span>
<input class="form-control ima-kb-acl" data-group="${escapeHtml(group.id)}"
  value="${escapeHtml((group.acl_usernames || []).join(", "))}"
  placeholder="逗号分隔用户名，空则仅管理员"></label>
```

单独「保存授权」可并进现有「保存采集配置」：保存 groups 之后，对每个 `.ima-kb-acl` 再 `PUT` ACL。空字符串 = 清空授权。

`index.html` 升高 `app.js?v=`（当前 260）。改了 CSS 就升高 `style.css?v=`。

README：用户侧栏改为「知识库」；写明需管理员授权后自行订阅；PDF 采集后台仍在。

- [ ] **Step 4: Run a focused regression**

Run:

```
python -m pytest tests/test_ima_kb.py tests/test_ima_documents.py tests/test_spa_routes.py tests/test_frontend_interactions.py tests/test_tagging.py -q
```

Expected: PASS。`tests/test_tagging.py` 若不存在就去掉。

- [ ] **Step 5: Commit**

```bash
git add app/static/app.js app/static/index.html README.md tests/test_frontend_interactions.py
git commit -m "feat: let admins grant knowledge-base subscribers"
```

---

## Self-review (spec coverage)

| Spec requirement | Task |
|---|---|
| 入口改名、旧路由重定向 | 8 |
| 已订阅 / 可订阅 | 3, 4, 8 |
| 默认仅管理员，再授权，再订阅 | 2, 3, 4 |
| 撤权立刻 404、级联删订阅 | 2, 4 |
| 不进 posts / 时间线 | 全程不写 posts；8 只改入口文案 |
| 采集/PDF 格式不动 | 5–6 只加字段和打标调用 |
| 摘要/封面 | 5 |
| 无 PDF 仍可看元数据 | 5, 9 |
| 自动打标股票/行业 | 1, 6 |
| 库内按标签筛选 | 5, 9 |
| 复用后台词表，不另建 | 1, 6, 7 |
| 维护时清过期标签 | 7 |
| API 仍用 `/api/ima-documents*` | 4 |
| 后台授权用户 | 4, 10 |
| 未知库 404 不 403 | 4 |

无 TBD。函数名前后一致：`tag_text`、`catalog`、`readable_group_ids`、`set_ima_kb_acl`、`retag_all`、`purge_ima_document_tags`。
