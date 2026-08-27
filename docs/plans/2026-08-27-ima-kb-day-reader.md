# 知识库按日瘦行 + 阅读页摘要 / PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打开知识库默认只加载最新有文档的一天，列表瘦行；点开后只显示中文摘要和 PDF 预览，不再铺整份 TXT。

**Architecture:** `ImaDocumentStore` 用一次廉价 manifest/state 扫描提供列表、日期/标签和目录统计，列表不再 `stat` 文件、不返回摘要。`GET /api/ima-documents` 按日或按 `limit`/`offset` 分页。阅读页用详情里的 `abstract`/`abstract_zh`，需要时 `POST .../translate` 走现有 X Cookie 的 Grok 翻译（正文，不传 tweet id），写入 state 缓存。

**Tech Stack:** FastAPI、`ImaDocumentStore`（`app/ima_documents.py`）、现有 `translate_text`（`app/scheduler.py`）、静态 `app/static/app.js` + `style.css`。Python 用 `.venv/bin/python`。

**Spec:** `docs/specs/2026-08-27-ima-kb-day-reader-design.md`

---

## File map

| File | Responsibility |
|---|---|
| `app/ima_documents.py` | 廉价扫描、`include_body`、`catalog_entries`、译文读写 |
| `app/api.py` | 列表默认最新一天 / 分页；详情翻译字段；`POST /translate`；目录改走廉价扫描 |
| `app/scheduler.py` | `translate_text`：无 tweet id 时用同一 X 接口尝试正文 |
| `app/static/app.js` | 瘦行、日期导航、搜索出日、无限滚动、阅读页 |
| `app/static/style.css` | 瘦行网格、阅读页 PDF 占满、去掉收起按钮样式依赖 |
| `app/version.py` `app/static/index.html` `app/static/sw.js` | 缓存版本 |
| `tests/test_ima_kb.py` | store / API |
| `tests/test_scheduler.py` | X 正文翻译 |
| `tests/test_frontend_interactions.py` | 前端契约 |
| `tests/test_ima_documents.py` | 只在现有断言被默认按日行为打到时改 |

不做：采集预译、付费 xAI、手机阅读页、改目录订阅/授权、动 Unraid。

---

### Task 1: Store 廉价扫描（facets / 目录 / 列表不 stat）

**Files:**
- Modify: `app/ima_documents.py`（`document_facets`、`group_summary`、`documents`、`_file_size`；新增 `catalog_entries`）
- Modify: `app/api.py`（catalog 改走 `catalog_entries`）
- Test: `tests/test_ima_kb.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ima_kb.py`:

```python
def test_catalog_entries_and_facets_do_not_need_files(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima-cheap")
    banking = ImaGroupConfig("banking", "投行", "kb", "root")
    older = {
        "media_id": "file_old",
        "name": "旧稿.pdf",
        "day": "0810",
        "abstract": "旧摘要很长" * 20,
        "cover_url": "https://example.com/old.jpg",
        "group_id": "banking",
    }
    newer = {
        "media_id": "file_new",
        "name": "新稿.pdf",
        "day": "0826",
        "abstract": "新摘要",
        "cover_url": "https://example.com/new.jpg",
        "group_id": "banking",
    }
    store.save_manifest([older, newer])
    store.save_state({
        store.state_key(older): {"tags": ["宏观"], "pdf": "missing/old.pdf", "size": 12},
        store.state_key(newer): {"tags": ["新能源"], "txt": "missing/new.txt"},
    })
    entries = store.catalog_entries(groups=(banking,))
    assert {(item["media_id"], item["day"], item["name"]) for item in entries} == {
        ("file_old", "0810", "旧稿.pdf"),
        ("file_new", "0826", "新稿.pdf"),
    }
    facets = store.document_facets(group_id="banking", groups=(banking,))
    assert facets["days"] == ["0826", "0810"]
    assert set(facets["tags"]) == {"宏观", "新能源"}
    listed = store.documents(groups=(banking,), include_body=False)
    assert listed[0]["media_id"] == "file_new"
    assert listed[0]["has_pdf"] is False
    assert listed[0]["has_txt"] is True
    assert listed[0]["size"] == 0
    assert "abstract" not in listed[0]
    assert "cover_url" not in listed[0]
    missing_pdf = store.documents(day="0810", groups=(banking,), include_body=False)
    assert missing_pdf[0]["has_pdf"] is True
    assert missing_pdf[0]["size"] == 12
    summary = store.group_summary((banking,))
    assert summary == [{"id": "banking", "name": "投行", "count": 2}]


def test_documents_page_slices_search_hits(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima-page")
    banking = ImaGroupConfig("banking", "投行", "kb", "root")
    records = [
        {"media_id": f"file_{idx}", "name": f"研报{idx}.pdf", "day": "0826", "abstract": "锂电", "group_id": "banking"}
        for idx in range(3)
    ]
    store.save_manifest(records)
    store.save_state({store.state_key(record): {"tags": ["新能源"]} for record in records})
    page = store.documents(query="研报", groups=(banking,), include_body=False, limit=2, offset=0)
    assert [item["media_id"] for item in page] == ["file_2", "file_1"]
    assert store.documents(query="研报", groups=(banking,), include_body=False, limit=2, offset=2)[0]["media_id"] == "file_0"
```

Keep `test_documents_include_metadata_and_tag_filter` passing: `documents()` 默认 `include_body=True`，仍返回 `abstract`/`cover_url`。

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_ima_kb.py::test_catalog_entries_and_facets_do_not_need_files tests/test_ima_kb.py::test_documents_page_slices_search_hits`

Expected: FAIL (`catalog_entries` missing and/or `include_body` unexpected).

- [ ] **Step 3: Implement store changes**

In `app/ima_documents.py`:

1. `_file_size` 不再 `pdf.stat()`：

```python
    @staticmethod
    def _file_size(state_item: dict[str, Any], record: dict[str, Any], pdf: Path | None) -> int:
        del pdf
        return int(state_item.get("size") or record.get("size") or 0)
```

2. 新增 `catalog_entries`：只扫 manifest，过滤 `groups` / `group_id`，返回 `{media_id, name, day, group_id}`。不要 `is_file()`。

3. `document_facets`：不要再调用 `self.documents()`。按 `catalog_entries` 同样的库过滤扫 manifest，`days` 去重后 **倒序**，`tags` 从 state 收集。保留 `query` 参数以免打坏现有调用，但 **忽略** `query`（搜索不收窄日期/标签）。

4. `group_summary`：用 `catalog_entries(groups=groups)` 计数，不要 `self.documents()`。

5. `documents(...)` 增加 `include_body: bool = True`、`limit: int | None = None`、`offset: int = 0`：
   - 仍用 manifest 过滤 `day` / `query`（haystack 继续含 `abstract`）/ `tag` / 库。
   - `has_pdf = bool(state_item.get("pdf"))`，`has_txt = bool(state_item.get("txt"))`。不要 `pdf.is_file()` / `txt.is_file()`。
   - `include_body is False` 时不要写入 `abstract`、`cover_url`。
   - 排序仍是 `(day, name)` 倒序。
   - `limit is not None` 时返回 `output[offset:offset + limit]`。

6. `app/api.py` 的 `ima_documents_catalog`：把 `store.documents(groups=_configured_groups())` 换成 `store.catalog_entries(groups=_configured_groups())`。`attach_catalog_stats` 签名不变。

详情 `document()` **继续** `is_file()`，阅读页要认真实文件。

- [ ] **Step 4: Run store tests**

Run: `.venv/bin/python -m pytest -q tests/test_ima_kb.py tests/test_ima_documents.py`

Expected: PASS。若有旧测试断言列表 `has_pdf` 必须 `is_file()`，以「state 有路径即 True」为准，改断言而不是改回 stat。

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py app/api.py tests/test_ima_kb.py
git commit -m "$(cat <<'EOF'
perf: scan IMA knowledge lists without per-file stats

EOF
)"
```

---

### Task 2: 列表 API 默认最新一天 + 分页 + 不回摘要

**Files:**
- Modify: `app/api.py`（`list_ima_documents`）
- Test: `tests/test_ima_kb.py`

- [ ] **Step 1: Write the failing API tests**

Append to `tests/test_ima_kb.py`（沿用 `test_document_detail_exposes_metadata_and_list_filters_by_tag` 的建库方式：`DAV_UI_ONLY=1`、admin、往 `client.app.state.ima_documents.store` 写两天的文档）：

```python
def test_list_ima_documents_defaults_to_latest_day_and_pages_search(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "kb-day.sqlite"))
    admin_headers = _headers(client, "kb_day_admin", "KBDAY01", admin=True)
    store = client.app.state.ima_documents.store
    records = [
        {"media_id": "file_old", "name": "旧稿.pdf", "day": "0810", "abstract": "旧摘要"},
        {"media_id": "file_new", "name": "新稿.pdf", "day": "0826", "abstract": "新摘要"},
        {"media_id": "file_hit", "name": "锂电跟踪.pdf", "day": "0810", "abstract": "新摘要也在旧日"},
    ]
    store.save_manifest(records)
    store.save_state({store.state_key(record): {"tags": ["新能源"]} for record in records})

    latest = client.get("/api/ima-documents", headers=admin_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["day"] == "0826"
    assert [item["media_id"] for item in body["items"]] == ["file_new"]
    assert "abstract" not in body["items"][0]
    assert "cover_url" not in body["items"][0]
    assert body["has_more"] is False
    assert body["days"] == ["0826", "0810"]

    missing = client.get("/api/ima-documents?day=0101", headers=admin_headers)
    assert missing.json()["items"] == []
    assert missing.json()["day"] == "0101"
    assert missing.json()["days"] == ["0826", "0810"]

    search = client.get("/api/ima-documents?q=摘要&limit=1&offset=0", headers=admin_headers)
    assert search.status_code == 200
    search_body = search.json()
    assert search_body["day"] == ""
    assert search_body["has_more"] is True
    assert len(search_body["items"]) == 1
    page2 = client.get("/api/ima-documents?q=摘要&limit=1&offset=1", headers=admin_headers).json()
    assert page2["has_more"] is True
    ids = {search_body["items"][0]["media_id"], page2["items"][0]["media_id"]}
    assert "file_new" in ids
```

不写 `group_id`：和 `test_document_detail_exposes_metadata_and_list_filters_by_tag` 一样，admin 能读默认库里的 legacy 记录。

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_ima_kb.py::test_list_ima_documents_defaults_to_latest_day_and_pages_search`

Expected: FAIL（响应没有 `day`/`has_more`，或无参列表返回两天）。

- [ ] **Step 3: Implement list endpoint**

In `app/api.py` `list_ima_documents` 增加 `limit: int = 50`、`offset: int = 0`。逻辑：

```python
        facets = ima_documents.store.document_facets(group_id=group, groups=groups)
        query = q.strip()
        tag = tag.strip()
        search_mode = bool(query or tag)
        if search_mode:
            effective_day = ""
            matched = ima_documents.store.documents(
                query, "", group_id=group, groups=groups, tag=tag, include_body=False
            )
            limit = bounded_limit(limit, default=50)
            offset = max(offset, 0)
            has_more = offset + limit < len(matched)
            items = matched[offset:offset + limit]
        else:
            effective_day = day.strip() or next(iter(facets["days"]), "")
            items = (
                ima_documents.store.documents(
                    "", effective_day, group_id=group, groups=groups, include_body=False
                )
                if effective_day
                else []
            )
            has_more = False
            offset = 0
        return {
            "groups": ima_documents.store.group_summary(groups),
            "items": items,
            "days": facets["days"],
            "tags": facets["tags"],
            "day": effective_day,
            "has_more": has_more,
            "offset": offset,
        }
```

`?day=0101`（不在 `days` 里）仍把 `day` 回成 `0101`，`items=[]`。

- [ ] **Step 4: Run related API tests**

Run: `.venv/bin/python -m pytest -q tests/test_ima_kb.py tests/test_ima_documents.py`

Expected: PASS。`test_group_aware_document_api_returns_summary_and_filters_items` 里无参 `GET /api/ima-documents` 只有一天，行为应不变。若某测试假定无参返回多天，改成显式 `?q=` 或按日断言。

- [ ] **Step 5: Commit**

```bash
git add app/api.py tests/test_ima_kb.py tests/test_ima_documents.py
git commit -m "$(cat <<'EOF'
feat: page IMA knowledge lists by latest day

EOF
)"
```

---

### Task 3: 翻译——X 正文尝试 + 详情字段 + POST

**Files:**
- Modify: `app/scheduler.py`（`translate_text`）
- Modify: `app/ima_documents.py`（`abstract_src_hash`、`translation_fields`、`write_abstract_zh`）
- Modify: `app/api.py`（详情字段、`POST /ima-documents/{media_id}/translate`）
- Test: `tests/test_scheduler.py`、`tests/test_ima_kb.py`

- [ ] **Step 1: Write failing translation tests**

In `tests/test_scheduler.py`，仿 `test_translate_text_uses_x_official_translation`：

```python
def test_translate_text_uses_x_text_body_without_tweet_id():
    calls = []

    def handler(request):
        calls.append(request)
        assert "api.x.com/2/grok/translation.json" in str(request.url)
        body = json.loads(request.content)
        assert body["content_type"] == "TEXT"
        assert "id" not in body
        assert body["text"] == "CATL solid-state timeline"
        assert body["dst_lang"] == "zh-cn"
        return httpx.Response(200, json={"result": {"text": "宁德时代固态时间表"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = translate_text(
        "CATL solid-state timeline",
        client=client,
        twitter_cookie="auth_token=my-auth-token; ct0=ct0-token",
    )
    assert result == "宁德时代固态时间表"
    assert len(calls) == 1
```

```python
def test_translate_text_skips_mymemory_when_long_text_and_x_fails():
    def handler(request):
        if "grok/translation.json" in str(request.url):
            return httpx.Response(400, text="no")
        raise AssertionError("MyMemory should not be called")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    src = "word " * 200  # >500 chars, English
    assert translate_text(src, client=client, twitter_cookie="auth_token=a; ct0=b") == src.strip()
```

短英文 + X 失败仍走现有 MyMemory（`test_translate_text_mymemory` 不传 cookie，行为不变）。

In `tests/test_ima_kb.py`：

```python
def test_document_detail_and_translate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "kb-tr.sqlite"))
    admin_headers = _headers(client, "kb_tr_admin", "KBTR001", admin=True)
    store = client.app.state.ima_documents.store
    zh = {"media_id": "file_zh", "name": "中文.pdf", "day": "0826", "abstract": "宁德时代排产上修，产业链需求回暖。"}
    en = {"media_id": "file_en", "name": "English.pdf", "day": "0826", "abstract": "CATL solid-state timeline"}
    store.save_manifest([zh, en])
    store.save_state({store.state_key(zh): {}, store.state_key(en): {}})

    zh_detail = client.get("/api/ima-documents/file_zh", headers=admin_headers).json()
    assert zh_detail["needs_translation"] is False
    assert zh_detail["abstract_zh"] == ""

    en_detail = client.get("/api/ima-documents/file_en", headers=admin_headers).json()
    assert en_detail["needs_translation"] is True
    assert en_detail["abstract"] == "CATL solid-state timeline"

    monkeypatch.setattr(
        "app.scheduler.translate_text",
        lambda text, **kwargs: "宁德时代固态时间表",
    )
    translated = client.post("/api/ima-documents/file_en/translate", headers=admin_headers)
    assert translated.status_code == 200
    assert translated.json()["abstract_zh"] == "宁德时代固态时间表"
    again = client.get("/api/ima-documents/file_en", headers=admin_headers).json()
    assert again["needs_translation"] is False
    assert again["abstract_zh"] == "宁德时代固态时间表"
    state = store.load_state()[store.state_key(en)]
    assert state["abstract_zh"] == "宁德时代固态时间表"
    assert state["abstract_src_hash"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_scheduler.py::test_translate_text_uses_x_text_body_without_tweet_id tests/test_scheduler.py::test_translate_text_skips_mymemory_when_long_text_and_x_fails tests/test_ima_kb.py::test_document_detail_and_translate_cache`

Expected: FAIL。

- [ ] **Step 3: Extend `translate_text`**

In `app/scheduler.py` `translate_text`，X Cookie 齐全时：

- 有 `tweet_id`：保持现有 `content_type=POST` + `id`。
- 无 `tweet_id`：同一 URL / 同一 header，body 为 `{"content_type": "TEXT", "text": text[:2000], "dst_lang": "zh-cn"}`，**不要** `id`。解析仍用 `_parse_x_translation_body`。
- X 失败后：`len(text) > 500` 则返回原文（不要打 MyMemory，不要因为只有 x_translate 错误而 `raise`）。`<=500` 才走现有 MyMemory。
- `_already_chinese` 仍在请求前短路。

- [ ] **Step 4: Store + API translation fields**

In `app/ima_documents.py`：

```python
def abstract_src_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def translation_fields(abstract: str, state_item: dict[str, Any]) -> dict[str, Any]:
    from .scheduler import _already_chinese

    text = str(abstract or "")
    cached = str(state_item.get("abstract_zh") or "")
    src_hash = str(state_item.get("abstract_src_hash") or "")
    fresh = bool(cached) and src_hash == abstract_src_hash(text)
    already = _already_chinese(text)
    return {
        "abstract": text,
        "abstract_zh": cached if fresh else "",
        "needs_translation": bool(text) and (not already) and (not fresh),
    }
```

`write_abstract_zh(self, media_id, group_id, groups, text_zh)`：找到对应 state key，写入 `abstract_zh` 与当前原文的 `abstract_src_hash`，`save_state`。找不到文档则 `ValueError`。

让 `store.document()` 直接带上 `abstract_zh`、`needs_translation`（内部读 state 后走 `translation_fields`）。详情 JSON 原样返回这两字段。

新增 `POST /ima-documents/{media_id}/translate`（放在 `/{media_id}/text` **之前**）：

```python
    @router.post("/ima-documents/{media_id}/translate")
    def translate_ima_document(
        media_id: str,
        group: str = Query("", max_length=128),
        user: dict = Depends(get_current_user),
    ):
        document = _ima_document(user, media_id, group)
        if not document.get("needs_translation"):
            return {"abstract_zh": document.get("abstract_zh") or document.get("abstract") or ""}
        from .scheduler import translate_text
        source = document.get("abstract") or ""
        try:
            zh = translate_text(source)
        except Exception:
            zh = source
        if zh and zh != source:
            ima_documents.store.write_abstract_zh(
                media_id,
                group,
                groups=_require_readable_group(user, group),
                text_zh=zh,
            )
        return {"abstract_zh": zh}
```

`write_abstract_zh` 找不到文档则 `ValueError`，API 转 404。翻译失败或译文等于原文：不写 state，返回原文。不要 500。

- [ ] **Step 5: Run translation tests**

Run: `.venv/bin/python -m pytest -q tests/test_scheduler.py tests/test_ima_kb.py`

Expected: PASS。`test_translate_text_mymemory` / `test_translate_text_uses_x_official_translation` 必须仍绿。

- [ ] **Step 6: Commit**

```bash
git add app/scheduler.py app/ima_documents.py app/api.py tests/test_scheduler.py tests/test_ima_kb.py
git commit -m "$(cat <<'EOF'
feat: translate IMA abstracts via X text endpoint

EOF
)"
```

---

### Task 4: 前端瘦行 + 按日导航 + 搜索出日 + 无限滚动

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/style.css`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Update frontend contract tests first（会红）**

改 `test_ima_kb_metadata_list_tag_filter_and_reader_contracts` 的列表部分（阅读页断言放到 Task 5 一起改也可以；本任务先改列表相关，阅读页旧断言若会红就一并挪到 Task 5 再改）：

列表相关改为：

```python
    assert "ima-doc-abstract" not in row
    assert "item.abstract" not in row
    assert "ima-doc-row-thumb" not in row
    assert "item.cover_url" not in row
    assert "item.tags" not in row
    assert "imaDocKindLabel" in row
    assert "fmtImaDay(item.day)" in row
    assert "stepImaDocumentsDay" in src
    assert "ima-doc-day-nav" in src
    assert "loadImaDocumentsMore" in src
    assert 'params.set("limit"' in render
    assert "data.has_more" in render
```

新增：

```python
def test_ima_documents_search_leaves_day_view():
    src = APP_JS.read_text()
    submit = _fn_body("submitImaDocumentsSearch")
    tag = _fn_body("selectImaDocumentsTag")
    day = _fn_body("selectImaDocumentsDay")
    clear = _fn_body("clearImaDocumentsFilters")
    assert "state.imaDocumentsDay = \"\"" in submit
    assert "state.imaDocumentsDay = \"\"" in tag
    assert "state.imaDocumentsQuery = \"\"" in day
    assert "state.imaDocumentsTag = \"\"" in day
    assert "imaDocumentsLastDay" in clear
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest -q tests/test_frontend_interactions.py::test_ima_kb_metadata_list_tag_filter_and_reader_contracts tests/test_frontend_interactions.py::test_ima_documents_search_leaves_day_view`

Expected: FAIL。

- [ ] **Step 3: Compact rows + CSS**

`imaDocumentRow`：不要封面、摘要、行内标签。保留标题、`fmtImaDay`、`imaDocKindLabel`；管理员看全部库时保留 `group_name`。

```javascript
function imaDocumentRow(item, showGroupLabel = false) {
  const groupLabel = showGroupLabel && item.group_name
    ? `<span class="ima-doc-group-label">${escapeHtml(item.group_name)}</span>` : "";
  return `
    <div class="ima-doc-row" role="button" tabindex="0" data-media-id="${escapeHtml(item.media_id)}" onclick="openImaDocument(this.dataset.mediaId)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openImaDocument(this.dataset.mediaId)}">
      <span class="ima-doc-row-copy">
        <span class="ima-doc-row-name">${escapeHtml(item.name)}</span>
        ${groupLabel}
        <span class="ima-doc-row-meta">${escapeHtml(fmtImaDay(item.day) || "")} · <span class="ima-doc-kind">${escapeHtml(imaDocKindLabel(item))}</span></span>
      </span>
      <span class="ima-doc-row-arrow" aria-hidden="true">›</span>
    </div>`;
}
```

`.ima-doc-row` 改成 `grid-template-columns: minmax(0, 1fr) 20px`。`copy`/`arrow` 的 `grid-column` 改成 1 / 2。按日模式下可以不再套 `imaDocumentGroups` 的日期大标题（整页就是这一天）；搜索模式用扁平列表，日期写在行上。

- [ ] **Step 4: Day nav + search/tag 出日 + 无限滚动**

状态增加 `imaDocumentsLastDay`、`imaDocumentsHasMore`。模块级 `_imaOffset`、`_imaItems`、`_imaLoadingMore`（仿 `_tlOffset`）。

行为：

- `submitImaDocumentsSearch`：读输入，`state.imaDocumentsDay = ""`，写路由后 `renderImaDocuments`。
- `selectImaDocumentsTag`：设 tag，**清空 day**。
- `selectImaDocumentsDay`：设 day，**清空 q 和 tag**（输入框也清）。
- `clearImaDocumentsFilters` / 清掉最后一个搜索或标签：`day = state.imaDocumentsLastDay || ""`。
- `renderImaDocuments` 请求：有 `q`/`tag` 时带 `limit=50`、`offset`；没有则带当前 `day`（可空，让服务端补最新一天）。
- 响应后：若不是搜索模式且 `data.day`，`state.imaDocumentsDay = data.day`，`state.imaDocumentsLastDay = data.day`，`replaceState` 补上 `day`。
- 工具栏在搜索模式隐藏日期导航；按日模式渲染：

```html
<nav class="ima-doc-day-nav" aria-label="日期">
  <button type="button" class="btn-ghost" ${prevDisabled} onclick="stepImaDocumentsDay(-1)" aria-label="前一天">‹</button>
  <span>${escapeHtml(fmtImaDay(data.day) || data.day)}</span>
  <button type="button" class="btn-ghost" ${nextDisabled} onclick="stepImaDocumentsDay(1)" aria-label="后一天">›</button>
</nav>
```

`stepImaDocumentsDay(delta)`：在 `data.days`（或 `state.imaDocumentsDays`）里找当前 day 的下标，`+delta`；越界禁用按钮即可。`days` 已是新→旧，`delta=-1` 走向更旧。

- 搜索/标签：`has_more` 时在列表底放 `#ima-docs-sentinel`，`IntersectionObserver`（`rootMargin: 400px`）或 scroll 回退，调用 `loadImaDocumentsMore`：`offset = _imaItems.length`，`append`，不要整页 skeleton。
- 按日模式不要无限滚动。
- 日期芯片不要清成「全部日期」；筛选里的日期下拉仍可跳日（走 `selectImaDocumentsDay`）。

- [ ] **Step 5: Run frontend list tests + 现有知识库契约**

Run: `.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k ima`

Expected: 列表相关 PASS。阅读页旧断言若仍红，留给 Task 5。

- [ ] **Step 6: Commit**

```bash
git add app/static/app.js app/static/style.css tests/test_frontend_interactions.py
git commit -m "$(cat <<'EOF'
feat: browse knowledge libraries by day in compact rows

EOF
)"
```

---

### Task 5: 阅读页摘要 + PDF；缓存版本

**Files:**
- Modify: `app/static/app.js`（`renderImaDocument`）
- Modify: `app/static/style.css`（PDF 高度、去掉对 TXT/收起的依赖）
- Modify: `app/version.py`、`app/static/index.html`、`app/static/sw.js`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Rewrite reader contract tests**

`test_ima_document_reader_preserves_group_context_and_metadata`：

- 保留 backRoute / group / day / name。
- `"查看 PDF"` 改为不出现；保留 `"下载"`。
- 不要再断言 `item.chars`。
- 断言 `ima-reader-abstract`、`needs_translation`、`/translate`。

`test_ima_document_reader_requests_keep_current_group_for_all_endpoints`：

- 删除 ` /text` 断言。
- 增加 `translate` POST 带 `groupQuery`（若 URL 有 group）。

`test_ima_document_reader_backroute_uses_detail_group_when_url_has_none`：

- 把 `const text = await` 换成 `loadImaPdf` 或 `ima-reader-abstract` 的下标，保证补 `group_id` 发生在渲染摘要/PDF 之前。

`test_ima_kb_metadata_list_tag_filter_and_reader_contracts` 阅读页部分：

- 不要 `/text`、不要 `ima-text-view`、不要「查看 PDF」。
- `loadImaPdf(mediaId)` 仍在 `renderImaDocument` 里。
- 保留 `has_pdf`。
- `closeImaPdf` 可以留着不再从阅读页调用。

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k 'ima_document_reader or ima_kb_metadata'`

Expected: FAIL。

- [ ] **Step 3: Implement reader**

`renderImaDocument`：

1. 不要请求 `/text`，不要 `#ima-text-view`。
2. 摘要：`item.abstract_zh || item.abstract`，放进 `<p class="ima-reader-abstract" id="ima-reader-abstract">`。
3. 有封面仍渲染小图。
4. 有 `has_pdf`：工具栏只留「下载 PDF」；`#ima-pdf-panel` 打开即 `loadImaPdf(mediaId)`。不要「查看 PDF」「收起 PDF」。
5. 没有 PDF：一段说明「还没有 PDF 预览」，不要空 iframe。
6. 若 `item.needs_translation`：`api(\`/api/ima-documents/${id}/translate\`, { method: "POST" })`，成功后替换 `#ima-reader-abstract`。失败保持原文，不要 `flash`。
7. `loadImaPdf` 失败：`flash` 一次，面板可留空；不要把下载按钮藏掉。

`.ima-pdf-panel iframe` 用 `min-height: calc(100vh - 220px)`（或等价，保证摘要下面是主视野）。删阅读页对 `.ima-text-view` 的依赖即可，CSS 规则可留着以免误伤。

- [ ] **Step 4: Bump cache versions**

当前：`APP_VERSION = "1.12.67"`，`style.css?v=192`，`app.js?v=272`，`dav-shell-v141`。

改成：`1.12.68`、`v=193`、`v=273`、`dav-shell-v142`。

同步改 `test_frontend_asset_urls_bust_browser_cache`。

- [ ] **Step 5: Run full related suite**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_ima_kb.py \
  tests/test_ima_documents.py \
  tests/test_scheduler.py \
  tests/test_frontend_interactions.py
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add app/static/app.js app/static/style.css app/version.py app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
git commit -m "$(cat <<'EOF'
feat: show knowledge reader as Chinese abstract plus PDF

EOF
)"
```

---

## Manual check（实现后）

用本地或现有 UI：打开一个库应只有最新一天、行很矮；搜标题离开按日并能继续往下滚；点开英文摘要应先出原文再换成中文（X Cookie 可用时）；PDF 能预览和下载；没有整份 TXT。手机端仍是「请在电脑上打开」。不要把 Unraid 当线上。

---

## Self-review

| Spec | Task |
|---|---|
| 默认最新一天、`‹ ›`、空 day 由服务端补 | 2, 4 |
| 搜索/标签出日；清筛选回上一天 | 4 |
| 搜索无限滚动 50 条 | 2, 4 |
| 瘦行：标题/日期/类型 | 4 |
| 阅读页摘要 + PDF + 下载，无 TXT | 5 |
| 列表不回 abstract、不 stat | 1, 2 |
| facets / catalog / group_summary 廉价扫描 | 1 |
| `needs_translation` + 打开后译 + state 缓存 | 3, 5 |
| X 正文、不传 tweet id；长文本不打 MyMemory | 3 |
| 目录订阅/授权/手机拦截不变 | 未改那些路径 |
