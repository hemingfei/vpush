# 研报库 Phase 1 前端交互与美观性优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构研报库（`/knowledge`）的列表卡片流、顶部搜索/筛选工具栏、移动端来源下拉切换及阅读器高光摘要卡片，提升投研阅读质感与移动端使用体验。

**Architecture:** 后端 `_public_list_item` 轻量透出 140 字摘要；前端通过 CSS + 语义化 DOM 将单行表格升级为带 2 行折行标题、机构徽章和摘要透出的微卡片流；顶部搜索框与次级工具栏解耦，并通过媒体查询实现桌面端横排 Pills 与移动端原生 Select 的无缝响应式切换；阅读器顶部摘要升级为投研 Callout 高光卡片并支持一键复制。

**Tech Stack:** Python 3.14 (FastAPI / `app/ima_documents.py`), Vanilla JavaScript (`app/static/app.js`), CSS Design Tokens (`app/static/style.css`), pytest.

---

### Task 1: 后端 `_public_list_item` 扩充 `abstract` 字段与截断

**Files:**
- Modify: `app/ima_documents.py:3090-3120`
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_ima_documents.py`, add `test_public_list_item_includes_truncated_abstract`:

```python
def test_public_list_item_includes_truncated_abstract():
    from app.ima_documents import ImaDocumentsService

    # Case 1: abstract_zh takes precedence and is truncated to 140 chars
    long_zh = "这是一段很长的中文研报摘要。" * 20
    item1 = {
        "media_id": "doc1",
        "name": "测试研报1.pdf",
        "abstract_zh": long_zh,
        "abstract": "English abstract",
    }
    public1 = ImaDocumentsService._public_list_item(item1)
    assert "abstract" in public1
    assert public1["abstract"] == long_zh[:140]
    assert len(public1["abstract"]) == 140

    # Case 2: abstract fallback when abstract_zh missing
    item2 = {
        "media_id": "doc2",
        "name": "测试研报2.pdf",
        "abstract": "   Fallback abstract content with spaces   ",
    }
    public2 = ImaDocumentsService._public_list_item(item2)
    assert public2["abstract"] == "Fallback abstract content with spaces"

    # Case 3: no abstract present -> key omitted or empty
    item3 = {
        "media_id": "doc3",
        "name": "测试研报3.pdf",
    }
    public3 = ImaDocumentsService._public_list_item(item3)
    assert "abstract" not in public3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ima_documents.py -k "test_public_list_item_includes_truncated_abstract"`
Expected: FAIL with `AssertionError: assert 'abstract' in public1`

- [ ] **Step 3: Write minimal implementation**

In `app/ima_documents.py`, update `_public_list_item`:

```python
    @staticmethod
    def _public_list_item(item: dict[str, Any]) -> dict[str, Any]:
        public = {
            "media_id": item.get("media_id") or "",
            "name": item.get("name") or "",
            "day": item.get("day") or "unknown",
            "sort_date": str(item.get("_sort_date") or item.get("sort_date") or ""),
            "size": item.get("size") or 0,
            "chars": item.get("chars") or 0,
            "downloaded_at": item.get("downloaded_at") or "",
            "tags": list(item.get("tags") or []),
            "has_pdf": bool(item.get("has_pdf")),
            "has_txt": bool(item.get("has_txt")),
        }
        if item.get("group_id"):
            public["group_id"] = item["group_id"]
        if item.get("group_name"):
            public["group_name"] = item["group_name"]
        if item.get("search_snippet"):
            public["search_snippet"] = str(item["search_snippet"])[:240]
        abstract_text = str(item.get("abstract_zh") or item.get("abstract") or "").strip()
        if abstract_text:
            public["abstract"] = abstract_text[:140]
        return public
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ima_documents.py -k "test_public_list_item_includes_truncated_abstract"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat(knowledge): include truncated abstract in public list item"
```

---

### Task 2: 前端 JS：顶部搜索框独立、清空按钮与移动端来源下拉菜单

**Files:**
- Modify: `app/static/app.js:1342-1355, 1520-1560`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_frontend_interactions.py`, add `test_ima_report_header_responsive_source_and_search_clear`:

```python
def test_ima_report_header_responsive_source_and_search_clear():
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    source_fn = _fn_body("knowledgeSourceControlsHtml")

    # Clear button in searchbox when query is non-empty
    assert "clearImaDocumentsFilter('q')" in render or "clearImaDocumentsFilter(&#39;q&#39;)" in render or "clearImaDocumentsFilter" in render
    assert "ima-search-clear" in render

    # Responsive source controls: contains both pills and mobile select
    assert "feishuSourcePillsHtml(" in source_fn
    assert "kb-source-select-mobile" in source_fn
    assert "selectImaDocumentGroup(this.value)" in source_fn

    # Date slot moved out of search label into toolbar/filters
    head_start = render.index('<header class="ima-report-head">')
    head_end = render.index("</header>", head_start)
    head = render[head_start:head_end]
    assert head.index("</form>") < head.index('id="ima-doc-day-nav-slot"')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_report_header_responsive_source_and_search_clear"`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

In `app/static/app.js`:

1. Update `knowledgeSourceControlsHtml(selectedGroup = "")`:
```javascript
function knowledgeSourceControlsHtml(selectedGroup = "") {
  const subscribed = state.imaCatalogSubscribed || [];
  const sources = subscribed.map((group) => ({
    group_id: String(group.id || ""),
    title: group.name || group.id,
  }));
  const pillsHtml = `<div class="kb-source-pills-desk">${feishuSourcePillsHtml(sources, selectedGroup, "selectImaDocumentGroup")}</div>`;
  const mobileOptions = [
    `<option value="" ${!selectedGroup ? "selected" : ""}>📚 全部研报库</option>`,
    ...sources.map((s) => `<option value="${escapeHtml(s.group_id)}" ${s.group_id === selectedGroup ? "selected" : ""}>📚 ${escapeHtml(s.title)}</option>`)
  ].join("");
  const mobileSelectHtml = `<div class="kb-source-select-wrap"><select class="kb-source-select-mobile" aria-label="切换研报库" onchange="selectImaDocumentGroup(this.value)">${mobileOptions}</select></div>`;
  return `<div class="ima-report-source">${pillsHtml}${mobileSelectHtml}</div>`;
}
```

2. Update `renderImaDocuments`:
Move `#ima-doc-day-nav-slot` into `.ima-report-filters`, add search clear button:
```javascript
    const clearBtn = query
      ? `<button type="button" class="ima-search-clear" onclick="clearImaDocumentsFilter('q')" aria-label="清除搜索">${X_ICON}</button>`
      : "";
    listRoot.innerHTML = `
  <header class="ima-report-head">
    <div class="ima-report-heading"><div><h2 id="ima-doc-title">最新研报</h2><p id="ima-doc-meta" class="section-meta"></p></div><button type="button" class="icon-btn" aria-label="刷新研报" title="刷新研报" onclick="refreshImaDocuments()">${REFRESH_ICON}</button></div>
    <form class="ima-report-search" onsubmit="event.preventDefault();submitImaDocumentsSearch()">
      <label class="ima-report-searchbox">${SEARCH_ICON}<input id="ima-doc-q" type="search" value="${escapeHtml(query)}" placeholder="搜标题、公司、代码、行业或资料源" aria-label="搜索研报" oninput="queueImaDocumentsSearch()" oncompositionstart="_imaSearchComposing=true" oncompositionend="_imaSearchComposing=false;queueImaDocumentsSearch()">${clearBtn}</label>
    </form>
    <div class="ima-report-filters">${sourceControls}<span id="ima-doc-day-nav-slot"></span><label class="ima-report-tag"><span class="sr-only">标签</span><select id="ima-doc-tag" aria-label="标签" onchange="selectImaDocumentsTag(this.value)" hidden><option value="">全部标签</option></select></label></div>
    <div id="ima-doc-filter-chips" class="ima-doc-filter-chips"></div>
  </header>
  <div id="ima-docs-body" class="ima-report-body">${keepOld && oldHtml ? oldHtml : imaReportSkeletonHtml()}</div>`;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_report_header_responsive_source_and_search_clear"`
Expected: PASS

- [ ] **Step 5: Run existing header tests to ensure no regressions**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_report_header_owns_search_date_and_filters"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git commit -m "feat(knowledge): decouple searchbox and add mobile source dropdown"
```

---

### Task 3: 前端 CSS：顶部搜索与筛选响应式排版样式

**Files:**
- Modify: `app/static/style.css:3120-3180, 4050-4100`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_frontend_interactions.py`, add `test_ima_report_responsive_controls_css`:

```python
def test_ima_report_responsive_controls_css():
    css = STYLE_CSS.read_text()
    assert ".kb-source-pills-desk" in css
    assert ".kb-source-select-mobile" in css
    assert ".ima-search-clear" in css
    # Desktop hides mobile select
    assert re.search(r"\.kb-source-select-mobile\s*\{[^}]*display:\s*none", css)
    # Mobile breakpoint switches pills to none and shows select
    mobile_part = css[css.rfind("@media (max-width: 768px)"):]
    assert ".kb-source-pills-desk" in mobile_part
    assert "display: none" in mobile_part
    assert ".kb-source-select-mobile" in mobile_part
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_report_responsive_controls_css"`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

In `app/static/style.css`:
Add styles for `.kb-source-select-mobile`, `.kb-source-select-wrap`, `.ima-search-clear`, and media queries:

```css
.kb-source-select-wrap { display: none; }
.kb-source-select-mobile {
  height: 34px;
  padding: 0 12px;
  border: var(--border-default);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  color: var(--color-text-strong);
  font: inherit;
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
}
.ima-search-clear {
  position: absolute;
  right: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-pill);
  background: var(--color-surface-soft);
  color: var(--color-text-muted);
  cursor: pointer;
}
.ima-search-clear:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-strong);
}

@media (max-width: 768px) {
  .kb-source-pills-desk { display: none !important; }
  .kb-source-select-wrap { display: inline-flex; }
  .kb-source-select-mobile { display: inline-flex; width: 100%; max-width: 180px; }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_report_responsive_controls_css"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/static/style.css tests/test_frontend_interactions.py
git commit -m "style(knowledge): add responsive controls css for search clear and mobile select"
```

---

### Task 4: 前端：研报列表微卡片流与摘要透出 (Card Flow)

**Files:**
- Modify: `app/static/app.js:985-1010`, `app/static/style.css:3130-3180`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_frontend_interactions.py`, add `test_ima_doc_row_renders_abstract_when_present`:

```python
def test_ima_doc_row_renders_abstract_when_present():
    row = _fn_body("imaDocumentRow")
    css = STYLE_CSS.read_text()

    # Preserves search snippet logic while adding abstract snippet fallback
    assert "item.search_snippet" in row
    assert "escapeHtml(item.search_snippet)" in row
    assert "item.abstract" in row
    assert "escapeHtml(item.abstract)" in row

    # Title clamp 2 lines in CSS
    assert ".ima-report-title" in css
    assert "-webkit-line-clamp: 2" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_doc_row_renders_abstract_when_present"`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

1. In `app/static/app.js`, update `imaDocumentRow(item)`:
```javascript
function imaDocumentRow(item) {
  const day = fmtImaDayShort(item.sort_date || item.day) || "—";
  const source = String(item.group_name || "");
  const meta = imaReportMetaHtml(item);
  const snippet = item.search_snippet
    ? `<span class="ima-report-snippet">${escapeHtml(item.search_snippet)}</span>`
    : (item.abstract ? `<span class="ima-report-snippet">${escapeHtml(item.abstract)}</span>` : "");
  return `
    <article class="ima-doc-row" role="button" tabindex="0" data-media-id="${escapeHtml(item.media_id)}" data-group-id="${escapeHtml(item.group_id || "")}" onclick="openImaDocument(this.dataset.mediaId, this.dataset.groupId)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openImaDocument(this.dataset.mediaId, this.dataset.groupId)}">
      <time class="ima-report-date">${escapeHtml(day)}</time>
      <span class="ima-report-copy"><strong class="ima-report-title">${escapeHtml(imaListTitle(item.name))}</strong>${snippet}${meta}</span>
      <span class="ima-report-source">${escapeHtml(source)}</span>
    </article>`;
}
```

2. In `app/static/style.css`, update `.ima-report-title`:
Change single line ellipsis to 2-line clamp with line-height 1.42:
```css
.ima-report-title {
  display: -webkit-box;
  overflow: hidden;
  color: var(--color-text-strong);
  font-size: var(--text-body);
  font-weight: var(--font-weight-medium);
  line-height: 1.42;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow-wrap: break-word;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_doc_row_renders_abstract_when_present"`
Expected: PASS

- [ ] **Step 5: Run all existing row tests**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_report_row"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/static/app.js app/static/style.css tests/test_frontend_interactions.py
git commit -m "feat(knowledge): render abstract snippet and enable 2-line clamped title in doc card"
```

---

### Task 5: 前端：阅读器详情页高光摘要卡片与复制操作 (Reader Callout Card & Copy)

**Files:**
- Modify: `app/static/app.js:2310-2325`, `app/static/style.css:2975-3000`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_frontend_interactions.py`, add `test_ima_reader_abstract_callout_and_copy`:

```python
def test_ima_reader_abstract_callout_and_copy():
    src = APP_JS.read_text()
    reader = _fn_body("renderImaDocument")
    css = STYLE_CSS.read_text()

    # Abstract copy function exists with fallback and flash feedback
    assert "function copyImaAbstract(" in src
    assert "已复制研报摘要" in src
    assert "copyImaAbstract()" in reader or "copyImaAbstract(this)" in reader or "copyImaAbstract" in reader

    # Reader callout styling and visual accent
    assert ".ima-reader-abstract" in css
    assert "border-left:" in css[css.index(".ima-reader-abstract"):]
    assert "var(--color-accent)" in css[css.index(".ima-reader-abstract"):]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_reader_abstract_callout_and_copy"`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

1. In `app/static/app.js`:
Add `copyImaAbstract(btn)`:
```javascript
function copyImaAbstract(btn) {
  const text = $("#ima-reader-abstract")?.textContent?.trim() || "";
  if (!text) return;
  const doFlash = () => flash("已复制研报摘要");
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(doFlash).catch(() => copyImaAbstractFallback(text, doFlash));
  } else {
    copyImaAbstractFallback(text, doFlash);
  }
}

function copyImaAbstractFallback(text, onSuccess) {
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    if (onSuccess) onSuccess();
  } catch (err) {
    flash("复制失败，请手动选择复制", "error");
  }
}
```

In `renderImaDocument(item, mediaId, groupId)`:
Update `abstractHtml`:
```javascript
    const copyBtn = `<button type="button" class="ima-abstract-copy-btn" onclick="event.stopPropagation();copyImaAbstract(this)" aria-label="复制摘要" title="复制摘要"><span aria-hidden="true">📋</span> 复制摘要</button>`;
    const abstractHtml = abstractText
      ? `<details open class="ima-reader-abstract${abstractLong ? " is-clamped" : ""}"><summary><span>💡 研报核心摘要</span>${copyBtn}</summary><p id="ima-reader-abstract">${escapeHtml(abstractText)}</p>${abstractMore}</details>`
      : "";
```

2. In `app/static/style.css`:
Enhance `.ima-reader-abstract` to callout card:
```css
.ima-reader-abstract {
  margin: 12px 0 0;
  padding: 12px 16px;
  border: 1px solid var(--border-soft);
  border-left: 4px solid var(--color-accent);
  border-radius: var(--radius-control);
  background: var(--color-surface-soft);
  color: var(--color-text);
  font-size: var(--text-sm);
}
.ima-reader-abstract summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-strong);
  list-style: none;
}
.ima-reader-abstract summary::-webkit-details-marker { display: none; }
.ima-abstract-copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: var(--border-default);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all 0.15s ease;
}
.ima-abstract-copy-btn:hover {
  background: var(--color-surface-hover);
  color: var(--color-accent-text);
  border-color: var(--color-accent);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_reader_abstract_callout_and_copy"`
Expected: PASS

- [ ] **Step 5: Run existing reader abstract clamp tests**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "test_ima_reader_clamps_long_abstract_and_keeps_preview_floor"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/static/app.js app/static/style.css tests/test_frontend_interactions.py
git commit -m "feat(knowledge): enhance reader abstract as callout card with one-click copy"
```

---

### Task 6: 全量回归与多视口视觉走查

**Files:**
- Test: All tests across backend and frontend

- [ ] **Step 1: Run all IMA and knowledge related tests**

Run: `.venv/bin/pytest tests/test_frontend_interactions.py -k "ima_"`
Expected: 100% PASS

Run: `.venv/bin/pytest tests/test_ima_documents.py`
Expected: 100% PASS

- [ ] **Step 2: Run the full test suite**

Run: `.venv/bin/pytest`
Expected: All 1750+ tests pass without errors

- [ ] **Step 3: Visual inspection on companion server**

Inspect `http://localhost:61376` to verify:
- Desktop view (1280px): 2-line titles, abstract snippets, pills, search clear button, callout card.
- Mobile view (375px): mobile select dropdown replaces pills, no horizontal overflow.
- Dark theme switch: check contrast of callout card and badges.

- [ ] **Step 4: Final commit / documentation updates**

```bash
git add docs/superpowers/plans/2026-09-03-knowledge-base-phase1.md
git commit -m "docs(plans): complete implementation plan for knowledge base phase 1"
```
