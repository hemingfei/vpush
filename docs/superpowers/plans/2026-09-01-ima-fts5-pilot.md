# IMA FTS5 全文检索试点实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用独立 SQLite FTS5 索引，让指定知识库的 TXT 正文参与检索，同时保持现有 ACL、短词搜索和故障降级行为。

**Architecture:** 新增 `ImaSearchIndex`，索引文件与 `dav.db` 分离，只有 `IMA_SEARCH_GROUP_IDS` 明确列出的知识库参与同步。应用启动后在后台做增量同步；用户查询三字以上关键词时，将现有元数据结果与 FTS 正文结果合并。索引不可用、同步中或查询失败时继续使用原有 SQLite 元数据搜索。

**Tech Stack:** Python 标准库、SQLite FTS5 trigram、FastAPI、pytest。

---

### Task 1: 独立全文索引

**Files:**
- Create: `app/ima_search.py`
- Create: `tests/test_ima_search.py`

- [ ] **Step 1: 写失败测试**

覆盖：未配置 group 时不创建文件；配置 group 后只索引该组；不可读 TXT 被跳过；相同 source hash 不重复读取；移除文档会删除索引行；两字查询返回空并交给上层降级；查询只能返回授权 group；英文正文命中并返回清理后的短片段。

- [ ] **Step 2: 验证测试失败**

Run: `../../.venv/bin/python -m pytest -q tests/test_ima_search.py`
Expected: FAIL because `app.ima_search` does not exist.

- [ ] **Step 3: 最小实现**

实现：

```python
class ImaSearchIndex:
    def __init__(self, path: Path, archive_root: Path, group_ids: tuple[str, ...]): ...
    @property
    def enabled(self) -> bool: ...
    def sync(self, rows: list[dict]) -> dict[str, int]: ...
    def search(self, query: str, readable_group_ids: list[str], limit: int) -> list[dict]: ...
    def status(self) -> dict: ...
```

数据库使用 WAL、`busy_timeout=5000`、FTS5 `tokenize='trigram'`。文档表保存 `group_id/media_id/source_hash/name/metadata/body`，FTS 外部内容表与触发器维护索引。`sync()` 只读取 source hash 改变的 TXT，并删除配置组内已消失记录。

- [ ] **Step 4: 验证通过**

Run: `../../.venv/bin/python -m pytest -q tests/test_ima_search.py`
Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add app/ima_search.py tests/test_ima_search.py
git commit -m "feat: add isolated IMA full-text index"
```

### Task 2: 后台增量同步

**Files:**
- Modify: `app/main.py`
- Modify: `app/ima_documents.py`
- Modify: `tests/test_ima_kb.py`

- [ ] **Step 1: 写失败测试**

覆盖：`IMA_SEARCH_GROUP_IDS` 为空时禁用；配置后索引路径为 `db_path` 同目录的 `ima-search.db`；`start()` 的远程维护线程在读模型可用后调用一次同步；同步异常只记录状态，不阻塞 `/healthz`；`status()` 暴露全文索引状态。

- [ ] **Step 2: 验证测试失败**

Run: `../../.venv/bin/python -m pytest -q tests/test_ima_kb.py -k 'full_text_index'`
Expected: FAIL because service has no full-text index.

- [ ] **Step 3: 最小实现**

`main.create_app()` 从 `IMA_SEARCH_GROUP_IDS` 解析逗号分隔 group ID，构造 `ImaSearchIndex` 并注入 `ImaDocumentService`。维护线程从 `ima_document_index` 读取配置组的 `group_id/media_id/name/group_name/metadata_folded/abstract/tags_json/txt_path/downloaded_at/chars`，调用 `sync()`。不在请求线程读取 NFS 正文。

- [ ] **Step 4: 验证通过并提交**

```bash
../../.venv/bin/python -m pytest -q tests/test_ima_kb.py -k 'full_text_index'
git add app/main.py app/ima_documents.py tests/test_ima_kb.py
git commit -m "feat: sync IMA full-text index in background"
```

### Task 3: 混合查询与命中片段

**Files:**
- Modify: `app/ima_documents.py`
- Modify: `app/db.py`
- Modify: `app/api.py`
- Modify: `app/static/app.js`
- Modify: `tests/test_ima_kb.py`
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: 写失败测试**

覆盖：正文独有关键词可以命中；标题/标签/摘要原有命中排在正文补充结果之前；重复文档只返回一次；ACL 不允许的 group 不会因 FTS 泄露；两字查询仍走原查询；分页稳定；API 只返回纯文本 `search_snippet`；前端仅在字段存在时显示片段。

- [ ] **Step 2: 验证测试失败**

Run: `../../.venv/bin/python -m pytest -q tests/test_ima_kb.py -k 'full_text_search' tests/test_frontend_interactions.py -k 'full_text_search'`
Expected: FAIL because list results do not include body-only hits.

- [ ] **Step 3: 最小实现**

`list_documents()` 先取得 `offset + limit + 1` 个现有元数据结果，再请求 FTS 补充结果；按“原有结果、FTS-only 结果”合并去重并分页。新增 DB 批量按 `(group_id, media_id)` 读取公共元数据，避免 N+1。`search_snippet` 由 FTS `snippet()` 返回后去除标记之外的控制字符，最大 240 字符。

- [ ] **Step 4: 验证通过并提交**

```bash
../../.venv/bin/python -m pytest -q tests/test_ima_kb.py -k 'full_text_search' tests/test_frontend_interactions.py -k 'full_text_search'
git add app/ima_documents.py app/db.py app/api.py app/static/app.js tests/test_ima_kb.py tests/test_frontend_interactions.py
git commit -m "feat: supplement knowledge search with full text"
```

### Task 4: 性能、版本和试点验收

**Files:**
- Modify: `app/version.py`
- Modify: `app/static/app.js`
- Modify: `app/static/index.html`
- Modify: `app/static/sw.js`
- Modify: `tests/test_frontend_pwa.py`
- Modify: `docs/用户指南.md`

- [ ] **Step 1: 版本和文档**

版本从 `1.12.127` 增加一个 patch；`app.js` 和 shell cache 各增加 1。用户指南注明：全文检索仅覆盖管理员配置的试点库，两字查询沿用标题/摘要搜索。

- [ ] **Step 2: 专项和完整测试**

```bash
node --check app/static/app.js
../../.venv/bin/python -m pytest -q tests/test_ima_search.py tests/test_ima_kb.py tests/test_frontend_interactions.py tests/test_frontend_pwa.py
../../.venv/bin/python -m pytest -q
```

Expected: all pass.

- [ ] **Step 3: 真实样本验收**

在独立临时文件上索引 SemiAnalysis，确认：索引文档数大于 1,500、索引体积小于 250 MB、常见英文查询中位延迟小于 100 ms、当前元数据结果顺序不回退、索引文件删除后自动降级。

- [ ] **Step 4: 提交**

```bash
git add app/version.py app/static/app.js app/static/index.html app/static/sw.js tests/test_frontend_pwa.py docs/用户指南.md
git commit -m "chore: release IMA full-text search pilot"
```
