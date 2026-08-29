# Knowledge Report-First Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current two-pane knowledge desk with a report-first list and a dedicated PDF reader while preserving search context, subscriptions, permissions, and the existing IMA/PDF APIs.

**Architecture:** Keep `/knowledge` as the report list and `/knowledge/:mediaId` as the reader. Reuse `/api/ima-documents`, catalog, detail, translate, and PDF endpoints; add only deterministic search ranking inside `ImaDocumentStore.documents()`. The frontend keeps one in-memory list snapshot so returning from the reader restores loaded pages, filters, selection, and scroll without fetching page one again.

**Tech Stack:** FastAPI, Python standard library, vanilla JavaScript SPA, existing V Push CSS tokens, browser-native PDF iframe, pytest static/runtime tests.

**Approved spec:** `docs/superpowers/specs/2026-08-29-knowledge-report-first-redesign.md`

**Working-tree constraint:** The repository already contains uncommitted knowledge UI work. Preserve it, do not reset it, and stage only the files named by each task.

---

## File Map

- `app/ima_documents.py`: broaden existing search fields and rank title matches before metadata/body matches.
- `app/static/app.js`: replace the two-pane shell, render the report-first list, debounce search, preserve list snapshots, and render the dedicated reader.
- `app/static/style.css`: remove obsolete `.kb-desk` two-pane rules and add report-list/reader layouts and states.
- `app/static/index.html`: bump CSS/JS cache versions after the final frontend diff.
- `app/static/sw.js`: bump the service-worker shell cache after the final frontend diff.
- `tests/test_ima_kb.py`: executable backend search/ranking regression.
- `tests/test_frontend_interactions.py`: static contract tests for shell, routes, list, restore behavior, reader controls, errors, and cache versions.

No new runtime dependency or frontend framework is introduced.

---

### Task 1: Make Existing Search Match Report Metadata

**Files:**
- Modify: `app/ima_documents.py:1695-1764` (`ImaDocumentStore.documents`)
- Test: `tests/test_ima_kb.py:735-785`

- [ ] **Step 1: Write the failing metadata/ranking test**

Add beside `test_list_ima_documents_defaults_to_latest_stream_and_pages_search`:

```python
def test_documents_searches_tags_and_group_name_and_ranks_title_hits_first(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima-report-search")
    semi = ImaGroupConfig("semi", "SemiAnalysis", "kb-semi", "root")
    records = [
        {
            "media_id": "body-hit",
            "name": "数据中心周报.pdf",
            "day": "0829",
            "abstract": "AI 算力需求继续增长",
            "group_id": "semi",
        },
        {
            "media_id": "title-hit",
            "name": "全球 AI 资本开支展望.pdf",
            "day": "0828",
            "abstract": "云厂商资本开支",
            "group_id": "semi",
        },
        {
            "media_id": "tag-hit",
            "name": "电力基础设施框架.pdf",
            "day": "0827",
            "abstract": "公用事业",
            "group_id": "semi",
        },
    ]
    store.save_manifest(records)
    store.save_state({
        store.state_key(records[0]): {},
        store.state_key(records[1]): {},
        store.state_key(records[2]): {"tags": ["AI"]},
    })

    matches = store.documents(query="ai", groups=(semi,), include_body=False)

    assert [item["media_id"] for item in matches] == [
        "title-hit",
        "tag-hit",
        "body-hit",
    ]
    assert all("_match_rank" not in item for item in matches)
    assert store.documents(query="semianalysis", groups=(semi,), include_body=False)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_ima_kb.py::test_documents_searches_tags_and_group_name_and_ranks_title_hits_first
```

Expected: FAIL because tags and group names are not in the search haystack, and the newer abstract hit sorts before the title hit.

- [ ] **Step 3: Expand the existing search without changing the API shape**

In `ImaDocumentStore.documents()`, compute tags/group metadata before filtering and use a transient rank:

```python
name = str(record.get("name") or media_id)
abstract = str(record.get("abstract") or "")
tags = self._tags(state_item)
actual_group_id = str(
    record.get("group_id")
    or state_item.get("group_id")
    or self._legacy_group_id
    or IMA_LEGACY_GROUP_ID
)
metadata_name = str(
    group_name
    or record.get("group_name")
    or state_item.get("group_name")
    or self._group_metadata.get(actual_group_id, ("", actual_group_id))[0]
)
name_folded = name.casefold()
tag_text = " ".join(tags).casefold()
metadata_folded = metadata_name.casefold()
abstract_folded = abstract.casefold()
haystack = " ".join((name_folded, str(record.get("day") or ""), tag_text, metadata_folded, abstract_folded))
if query and query not in haystack:
    continue
match_rank = 0
if query:
    if query in name_folded:
        match_rank = 3
    elif query in tag_text or query in metadata_folded:
        match_rank = 2
    else:
        match_rank = 1
```

Use `name`, `tags`, `actual_group_id`, and `metadata_name` when building the existing item. Add `"_match_rank": match_rank` temporarily, then replace the current sort/return tail with:

```python
output.sort(
    key=lambda item: (
        int(item.get("_match_rank") or 0),
        item["day"] != "unknown",
        item["day"],
        item["name"],
    ),
    reverse=True,
)
for item in output:
    item.pop("_match_rank", None)
if limit is not None:
    return output[offset:offset + limit]
return output
```

Do not add a new response field or endpoint.

- [ ] **Step 4: Run focused backend regressions**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_ima_kb.py::test_documents_searches_tags_and_group_name_and_ranks_title_hits_first \
  tests/test_ima_kb.py::test_list_ima_documents_defaults_to_latest_stream_and_pages_search \
  tests/test_ima_kb.py::test_documents_page_slices_search_hits
```

Expected: `3 passed`.

- [ ] **Step 5: Commit the search contract**

```bash
git add app/ima_documents.py tests/test_ima_kb.py
git commit -m "feat(ima): rank report search matches"
```

---

### Task 2: Replace the Two-Pane Shell with Route-Owned Surfaces

**Files:**
- Modify: `app/static/app.js:515-632, 901-1307`
- Test: `tests/test_frontend_interactions.py:2256-2310, 3020-3115`

- [ ] **Step 1: Replace obsolete two-pane contract tests**

Replace `test_knowledge_single_subscribed_library_skips_catalog` and `test_knowledge_catalog_shell_contract` with:

```python
def test_knowledge_report_first_shell_uses_one_surface_per_route():
    src = APP_JS.read_text()
    list_shell = _fn_body("mountKnowledgeListShell")
    reader_shell = _fn_body("mountKnowledgeReaderShell")
    render = _fn_body("renderKnowledge")

    assert 'id="ima-report-page"' in list_shell
    assert 'id="kb-list"' in list_shell
    assert 'id="kb-reader"' not in list_shell
    assert 'id="ima-reader-page"' in reader_shell
    assert 'id="kb-reader"' in reader_shell
    assert 'id="kb-list"' not in reader_shell
    assert "mediaId" in render
    assert "mountKnowledgeReaderShell()" in render
    assert "mountKnowledgeListShell()" in render


def test_knowledge_defaults_to_all_readable_sources():
    render = _fn_body("renderKnowledge")
    controls = _fn_body("knowledgeSourceControlsHtml")

    assert "subscribed.length === 1" not in render
    assert "rememberedKnowledgeGroup" not in APP_JS.read_text()
    assert 'id="ima-doc-source"' in controls
    assert '>全部研报<' in controls
    assert "state.imaCatalogSubscribed" in controls
    assert "available" in controls
    assert "subscribeKnowledge" in controls
```

Update `test_ima_documents_group_switching_contract` so it expects `ima-doc-source` instead of `kb-desk-lib`, while retaining URL group, escaping, local rerender, and ACL assertions. Replace `test_ima_documents_group_switcher_is_responsive_and_touch_friendly` with:

```python
def test_ima_source_filter_is_compact_and_subscription_management_survives():
    src = APP_JS.read_text()
    controls = _fn_body("knowledgeSourceControlsHtml")

    assert 'id="ima-doc-source"' in controls
    assert 'aria-label="资料源"' in controls
    assert "selectImaDocumentGroup(this.value)" in controls
    assert "ima-source-manage" in controls
    assert "knowledgeLibRowHtml" in controls
    assert "subscribeKnowledge" in src
    assert "unsubscribeKnowledge" in src
```

Replace `test_knowledge_desk_auto_opens_first_and_hides_empty_libs` with:

```python
def test_knowledge_report_list_does_not_auto_open_a_reader():
    render = _fn_body("renderImaDocuments")
    assert "ensureKnowledgeReaderOpen" not in APP_JS.read_text()
    assert "openImaDocument(items[0]" not in render
    assert "mountKnowledgeReaderShell" not in render
```

- [ ] **Step 2: Run the shell tests and verify they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_knowledge_report_first_shell_uses_one_surface_per_route \
  tests/test_frontend_interactions.py::test_knowledge_defaults_to_all_readable_sources \
  tests/test_frontend_interactions.py::test_ima_documents_group_switching_contract
```

Expected: FAIL because the current DOM always mounts `.kb-desk` with list and reader.

- [ ] **Step 3: Add route-owned list and reader shells**

Delete `knowledgeReaderEmptyHtml`, `knowledgeCanPickDocument`, `showKnowledgeReaderEmpty`, `syncKnowledgeReaderEmpty`, `syncKnowledgeDocSelection`, `ensureKnowledgeReaderOpen`, and `mountKnowledgeShell`. Add:

```javascript
function mountKnowledgeListShell() {
  ensureKnowledgeKeys();
  if ($("#ima-report-page")) return;
  clearImaPdfUrl();
  $("#main").innerHTML = `
    <section class="section-panel ima-report-page" id="ima-report-page">
      <div id="kb-list" tabindex="-1"></div>
    </section>`;
}

function mountKnowledgeReaderShell() {
  ensureKnowledgeKeys();
  if ($("#ima-reader-page")) return;
  $("#main").innerHTML = `
    <section class="section-panel ima-reader-page" id="ima-reader-page">
      <div id="kb-reader"><div class="admin-skeleton" aria-hidden="true"></div></div>
    </section>`;
}
```

- [ ] **Step 4: Make source selection a filter, not the page identity**

Delete `KB_LAST_GROUP_KEY`, `rememberKnowledgeGroup`, `rememberedKnowledgeGroup`, `imaKnowledgeCatalogRoute`, `imaKnowledgeStayOnCatalog`, `knowledgeDeskGroups`, `knowledgeDeskLibHtml`, and `renderKnowledgeLibs`.

Add:

```javascript
function knowledgeSourceControlsHtml(selectedGroup = "") {
  const selected = String(selectedGroup || "");
  const subscribed = state.imaCatalogSubscribed || [];
  const available = state.imaCatalogAvailable || [];
  const options = [{ id: "", name: "全部研报" }, ...subscribed.map((group) => ({
    id: String(group.id || ""),
    name: group.name || group.id,
  }))];
  const availableHtml = available.length
    ? `<details class="ima-source-manage"><summary>管理订阅</summary><div class="ima-source-menu">${available.map((group) => knowledgeLibRowHtml(group, selected, "available")).join("")}</div></details>`
    : "";
  return `<label class="ima-report-source"><span class="sr-only">资料源</span><select id="ima-doc-source" aria-label="资料源" onchange="selectImaDocumentGroup(this.value)">${options.map((group) => `<option value="${escapeHtml(group.id)}"${group.id === selected ? " selected" : ""}>${escapeHtml(group.name)}</option>`).join("")}</select></label>${availableHtml}`;
}
```

Keep `knowledgeLibRowHtml`, `subscribeKnowledge`, and `unsubscribeKnowledge` because subscription capability is still required. Remove their `rememberKnowledgeGroup(...)` calls. Add compact popover styles for `.ima-source-manage` and `.ima-source-menu` in Task 6; retain the `.kb-lib-row`, `.kb-lib-copy`, `.kb-lib-name`, and `.kb-lib-meta` rules used inside that popover.

Simplify `selectImaDocumentGroup(value)` to set the source filter, clear date/tag, replace the local URL, increment `routeRenderSeq`, and call `renderImaDocuments(seq)`. Do not route to `catalog=1`.

- [ ] **Step 5: Route list and reader separately in `renderKnowledge`**

Keep catalog loading, subscribed/available assignment, no-subscription states, ACL checks, and phone blocking. Remove automatic single/remembered group selection. After validating `selectedGroup`, use:

```javascript
state.imaDocumentsGroup = selectedGroup;
if (mediaId) {
  mountKnowledgeReaderShell();
  await renderImaDocument(seq, mediaId);
  return;
}
mountKnowledgeListShell();
await renderImaDocuments(seq);
```

For a non-admin with subscriptions and no `group` query, leave `selectedGroup === ""`; `/api/ima-documents` already resolves all readable groups.

- [ ] **Step 6: Run the shell and existing ACL tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_knowledge_report_first_shell_uses_one_surface_per_route \
  tests/test_frontend_interactions.py::test_knowledge_defaults_to_all_readable_sources \
  tests/test_frontend_interactions.py::test_ima_documents_group_switching_contract \
  tests/test_frontend_interactions.py::test_ima_knowledge_subscription_callbacks_require_current_session_owner \
  tests/test_frontend_interactions.py::test_ima_documents_follow_latest_dynamic_navigation
```

Expected: `5 passed`.

- [ ] **Step 7: Commit the route-owned shell**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git commit -m "refactor(ima): split report list and reader routes"
```

---

### Task 3: Build the Report-First List, Filters, and Explicit Pagination

**Files:**
- Modify: `app/static/app.js:753-1079, 1310-1585`
- Test: `tests/test_frontend_interactions.py:2904-2995, 3116-3188`

- [ ] **Step 1: Write the report-list contract tests**

Replace the old ticker-first row assertions with:

```python
def test_ima_report_row_is_document_first_and_keeps_optional_metadata():
    row = _fn_body("imaDocumentRow")
    meta = _fn_body("imaReportMetaHtml")

    assert "ima-report-date" in row
    assert "ima-report-title" in row
    assert "ima-report-meta" in row
    assert "ima-report-source" in row
    assert 'fmtImaDayShort(item.day) || "—"' in row
    assert "imaListTitle(item.name)" in row
    assert "imaDocTicker(item.name)" in meta
    assert "imaDistinctiveTags" in meta
    assert "fmtDocSize" in meta
    assert "item.group_name" in row
    assert "unknown" not in row


def test_ima_report_search_is_debounced_and_explicitly_pages():
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    queued = _fn_body("queueImaDocumentsSearch")
    more = _fn_body("loadImaDocumentsMore")

    assert "250" in queued
    assert "clearTimeout(_imaSearchTimer)" in queued
    assert "submitImaDocumentsSearch()" in queued
    assert 'oninput="queueImaDocumentsSearch()"' in render
    assert 'id="ima-docs-more"' in render
    assert 'onclick="loadImaDocumentsMore()"' in render
    assert "IntersectionObserver" not in src[src.index("const _imaItems"):src.index("async function renderImaDocument")]
    assert "正在加载更多" in more
    assert "加载失败，重试" in more
```

Replace `test_ima_document_list_hides_tag_rail_but_keeps_tag_filtering` with a test that expects a real `#ima-doc-tag` select that is hidden only when no reliable tags exist.

Replace the old header/day tests with these route-independent contracts:

```python
def test_ima_report_header_owns_search_date_and_filters():
    render = _fn_body("renderImaDocuments")
    head_start = render.index('<header class="ima-report-head">')
    head_end = render.index("</header>", head_start)
    head = render[head_start:head_end]

    assert 'id="ima-doc-q"' in head
    assert 'id="ima-doc-day-nav-slot"' in head
    assert 'id="ima-doc-source"' in _fn_body("knowledgeSourceControlsHtml")
    assert 'id="ima-doc-tag"' in head
    assert head.index('id="ima-doc-q"') < head.index('id="ima-doc-day-nav-slot"')


def test_ima_report_metadata_contract_keeps_existing_capabilities():
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    reader = _fn_body("renderImaDocument")

    assert 'placeholder="搜标题、公司、代码、行业或资料源"' in render
    assert 'params.set("tag"' in render
    assert "data.days" in render
    assert "loadImaDocumentsMore" in src
    assert "loadImaPdf(mediaId, readerSeq)" in reader
    assert "needs_translation" in reader
    assert "renderImaDocuments" in _fn_body("selectImaDocumentGroup")
    assert ".ima-report-page" in STYLE_CSS.read_text()
```

Delete or replace the obsolete `test_ima_document_day_nav_lives_in_title_header_and_stays_compact`, `test_kb_desk_head_search_and_picker_alignment`, and `test_ima_kb_metadata_list_tag_filter_and_reader_contracts`; do not leave assertions for `.kb-desk-head`, the 320px column, or automatic reader opening.

- [ ] **Step 2: Run the list tests and verify they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_ima_report_row_is_document_first_and_keeps_optional_metadata \
  tests/test_frontend_interactions.py::test_ima_report_search_is_debounced_and_explicitly_pages
```

Expected: FAIL because the current row is ticker/title/date and pagination uses an intersection observer.

- [ ] **Step 3: Replace the row renderer**

Add:

```javascript
function imaReportMetaHtml(item) {
  const parts = [];
  const ticker = imaDocTicker(item?.name);
  if (ticker) parts.push(ticker);
  parts.push(...imaDistinctiveTags(item?.tags));
  const size = fmtDocSize(item?.size);
  if (size) parts.push(size);
  return parts.length
    ? `<span class="ima-report-meta">${parts.map((part) => `<span>${escapeHtml(part)}</span>`).join("")}</span>`
    : "";
}

function imaDocumentRow(item) {
  const day = fmtImaDayShort(item.day) || "—";
  const source = String(item.group_name || "");
  return `
    <article class="ima-doc-row" role="button" tabindex="0" data-media-id="${escapeHtml(item.media_id)}" data-group-id="${escapeHtml(item.group_id || "")}" onclick="openImaDocument(this.dataset.mediaId, this.dataset.groupId)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openImaDocument(this.dataset.mediaId, this.dataset.groupId)}">
      <time class="ima-report-date">${escapeHtml(day)}</time>
      <span class="ima-report-copy"><strong class="ima-report-title">${escapeHtml(imaListTitle(item.name))}</strong>${imaReportMetaHtml(item)}</span>
      <span class="ima-report-source">${escapeHtml(source)}</span>
    </article>`;
}
```

Do not synthesize a report type or company name.

- [ ] **Step 4: Render a report-first header and reliable filters**

In `renderImaDocuments`, replace `.kb-desk-head` markup with:

```javascript
const sourceControls = knowledgeSourceControlsHtml(selectedGroup);
listRoot.innerHTML = `
  <header class="ima-report-head">
    <div class="ima-report-heading"><div><h2 id="ima-doc-title">最新研报</h2><p id="ima-doc-meta" class="section-meta"></p></div><button type="button" class="icon-btn" aria-label="刷新研报" title="刷新研报" onclick="refreshImaDocuments()">${REFRESH_ICON}</button></div>
    <form class="ima-report-search" onsubmit="event.preventDefault();submitImaDocumentsSearch()">
      <label class="ima-report-searchbox">${SEARCH_ICON}<input id="ima-doc-q" type="search" value="${escapeHtml(query)}" placeholder="搜标题、公司、代码、行业或资料源" aria-label="搜索研报" oninput="queueImaDocumentsSearch()"><span id="ima-doc-day-nav-slot"></span></label>
      <div class="ima-report-filters">${sourceControls}<label class="ima-report-tag"><span class="sr-only">标签</span><select id="ima-doc-tag" aria-label="标签" onchange="selectImaDocumentsTag(this.value)" hidden><option value="">全部标签</option></select></label></div>
    </form>
    <div id="ima-doc-filter-chips" class="ima-doc-filter-chips"></div>
    <div class="ima-report-columns" aria-hidden="true"><span>日期</span><span>标题</span><span>资料源</span></div>
  </header>
  <div id="ima-docs-body" class="ima-report-body">${imaReportSkeletonHtml()}</div>`;
```

Add `imaReportSkeletonHtml()` returning six `.ima-report-skeleton-row` elements with the same three columns as a real row.

Populate `#ima-doc-tag` from existing `data.tags`/`tag_counts`; unhide the label only when tags exist or a tag is selected.

- [ ] **Step 5: Debounce search and replace auto-loading with one button**

At module scope add:

```javascript
let _imaSearchTimer = null;
```

Add:

```javascript
function queueImaDocumentsSearch() {
  clearTimeout(_imaSearchTimer);
  _imaSearchTimer = setTimeout(() => submitImaDocumentsSearch(), 250);
}
```

Clear the timer at the start of `submitImaDocumentsSearch()`.

Delete `_imaLoadObserver`, `_imaLoadFallback`, `startImaDocumentsAutoLoad`, and the observer/fallback body of `stopImaDocumentsAutoLoad`; keep `stopImaDocumentsAutoLoad()` as a small compatibility cleanup that only resets `_imaLoadingMore` if callers still need it, or remove its calls together.

Render pagination with:

```javascript
const more = state.imaDocumentsHasMore
  ? `<div class="ima-docs-more"><button id="ima-docs-more" type="button" class="btn-ghost" onclick="loadImaDocumentsMore()">加载更多</button></div>`
  : "";
body.innerHTML = `<div class="ima-doc-list">${items.map((item) => imaDocumentRow(item)).join("")}</div>${more}`;
```

For the header count, use the total document count only for the unfiltered latest stream. For search/tag results, show the loaded result count plus `+` while `has_more` is true:

```javascript
const resultCount = query || tag
  ? `${items.length}${data.has_more ? "+" : ""} 条结果`
  : `${Number(data.document_count) || items.length} 份`;
if (meta) meta.textContent = resultCount;
```

In `loadImaDocumentsMore()`, disable `#ima-docs-more`, set its text to `正在加载更多…`, append rows with `imaDocumentRow(item)`, then either restore `加载更多`, remove the wrapper when exhausted, or set `加载失败，重试` on failure.

- [ ] **Step 6: Update empty-state copy**

Replace `imaDocumentsEmptyHtml` with:

```javascript
function imaDocumentsEmptyHtml(hasFilter) {
  if (hasFilter) {
    return emptyState(
      "没有找到相关研报",
      `<div><p class="section-meta">换个公司、代码或主题试试</p><button type="button" class="btn-normal" onclick="clearImaDocumentsFilters()">清除筛选</button></div>`
    );
  }
  return emptyState("这里还没有研报");
}
```

Date filtering remains available through the compact date control, but the page no longer groups rows by date.

- [ ] **Step 7: Run report-list regressions**

Run:

```bash
node --check app/static/app.js
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_ima_report_row_is_document_first_and_keeps_optional_metadata \
  tests/test_frontend_interactions.py::test_ima_report_search_is_debounced_and_explicitly_pages \
  tests/test_frontend_interactions.py::test_knowledge_desk_defaults_to_latest_stream \
  tests/test_frontend_interactions.py::test_ima_day_picker_restricts_to_available_days \
  tests/test_frontend_interactions.py::test_ima_documents_search_leaves_day_view
```

Expected: JavaScript syntax check succeeds and `5 passed`.

- [ ] **Step 8: Commit the report list**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git commit -m "feat(ima): add report-first knowledge list"
```

---

### Task 4: Preserve List Context and Build the Dedicated Reader

**Files:**
- Modify: `app/static/app.js:334-383, 515-626, 1588-1745`
- Test: `tests/test_frontend_interactions.py:1248-1295, 2757-2899`

- [ ] **Step 1: Write failing snapshot and reader-navigation tests**

Add:

```python
def test_ima_reader_captures_and_restores_the_loaded_result_set():
    src = APP_JS.read_text()
    capture = _fn_body("captureImaListSnapshot")
    current = _fn_body("currentImaListSnapshot")
    restore = _fn_body("restoreImaListSnapshot")
    opener = _fn_body("openImaDocument")

    assert "_imaItems.map" in capture
    assert "scrollTop" in capture
    assert "state.imaDocumentsHasMore" in capture
    assert "location.pathname + location.search" in capture
    assert "captureImaListSnapshot" in opener
    assert "snapshot.route" in current
    assert "location.pathname + location.search" in current
    assert "requestAnimationFrame" in restore
    assert "scrollTop" in restore
    assert "api(" not in restore


def test_ima_reader_has_one_app_download_and_result_neighbors():
    reader = _fn_body("renderImaDocument")
    nav = _fn_body("imaReaderNavHtml")
    back = _fn_body("backFromImaReader")

    assert "ima-reader-toolbar" in reader
    assert "backFromImaReader" in reader
    assert "btn-normal ima-reader-download" in reader
    assert "<details open" in reader
    assert "imaReaderNavHtml" in reader
    assert "openImaDocument" in nav
    assert ", true)" in nav
    assert "history.back()" in back
    assert "go(fallbackRoute)" in back
    assert "downloadImaPdf" not in _fn_body("showImaPdfFail")


def test_ima_reader_separates_document_group_from_list_source_filter():
    route = _fn_body("imaDocumentReaderRoute")
    reader = _fn_body("renderImaDocument")
    group = _fn_body("imaReaderDocumentGroup")

    assert 'params.set("doc_group", groupId)' in route
    assert 'currentQuery.get("group")' in reader
    assert 'currentQuery.get("doc_group")' in reader
    assert "imaDocumentsRoute(listGroup, query, day, tag)" in reader
    assert 'routeQuery().get("doc_group")' in group
    assert "imaReaderDocumentGroup()" in _fn_body("loadImaPdf")
    assert "imaReaderDocumentGroup()" in _fn_body("downloadImaPdf")
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_ima_reader_captures_and_restores_the_loaded_result_set \
  tests/test_frontend_interactions.py::test_ima_reader_has_one_app_download_and_result_neighbors \
  tests/test_frontend_interactions.py::test_ima_reader_separates_document_group_from_list_source_filter
```

Expected: FAIL because there is no list snapshot, the reader is still part of the shared desk, and the current `group` parameter incorrectly serves both list filtering and document identity.

- [ ] **Step 3: Separate the list source from the exact document group**

Use `group` only for the report-list source filter and add `doc_group` only on reader URLs. Replace `imaDocumentReaderRoute` with:

```javascript
function imaDocumentReaderRoute(mediaId, groupId = "") {
  const listGroup = routeQuery().get("group") || state.imaDocumentsGroup || "";
  const listRoute = normalizeRoute(imaDocumentsRoute(
    listGroup,
    state.imaDocumentsQuery,
    state.imaDocumentsDay,
    state.imaDocumentsTag
  ));
  const params = new URLSearchParams(listRoute.split("?")[1] || "");
  if (groupId) params.set("doc_group", groupId);
  const query = params.toString();
  return `${_imaDocumentRoute(mediaId)}${query ? `?${query}` : ""}`;
}

function imaReaderDocumentGroup() {
  return routeQuery().get("doc_group")
    || routeQuery().get("group")
    || state.imaDocumentsGroup
    || "";
}
```

In `renderImaDocument`, use:

```javascript
const listGroup = currentQuery.get("group") || state.imaDocumentsGroup || "";
const documentGroup = currentQuery.get("doc_group") || listGroup;
const groupQuery = documentGroup ? `?group=${encodeURIComponent(documentGroup)}` : "";
let backRoute = imaDocumentsRoute(listGroup, query, day, tag);
```

Use `imaReaderDocumentGroup()` in `loadImaPdf` and `downloadImaPdf`. Update the existing group-context tests to assert this helper rather than requiring every function to read `routeQuery().get("group")` directly. This prevents opening a row from the all-source list from changing the Back destination to one source.

- [ ] **Step 4: Add a bounded in-memory list snapshot**

At module scope add:

```javascript
let _imaListSnapshot = null;
```

Add helpers:

```javascript
function imaDocumentKey(mediaId, groupId = "") {
  return `${String(groupId || "")}\u0000${String(mediaId || "")}`;
}

function captureImaListSnapshot(selectedMediaId = "", selectedGroupId = "") {
  const body = $("#ima-docs-body");
  if (!body) return;
  _imaListSnapshot = {
    route: location.pathname + location.search,
    items: _imaItems.map((item) => ({ ...item, tags: [...(item.tags || [])] })),
    hasMore: !!state.imaDocumentsHasMore,
    days: [...(state.imaDocumentsDays || [])],
    tagCounts: { ..._imaTagCounts },
    documentCount: _imaDocumentCount,
    scrollTop: body.scrollTop,
    selectedKey: imaDocumentKey(selectedMediaId, selectedGroupId),
  };
}

function currentImaListSnapshot() {
  const snapshot = _imaListSnapshot;
  return snapshot && snapshot.route === location.pathname + location.search
    ? snapshot
    : null;
}

function restoreImaListSnapshot(snapshot, body) {
  if (!snapshot || !body) return false;
  _imaItems.length = 0;
  _imaItems.push(...snapshot.items.map((item) => ({ ...item, tags: [...(item.tags || [])] })));
  state.imaDocumentsHasMore = snapshot.hasMore;
  state.imaDocumentsDays = [...snapshot.days];
  _imaTagCounts = { ...snapshot.tagCounts };
  _imaDocumentCount = snapshot.documentCount;
  const more = snapshot.hasMore
    ? `<div class="ima-docs-more"><button id="ima-docs-more" type="button" class="btn-ghost" onclick="loadImaDocumentsMore()">加载更多</button></div>`
    : "";
  body.innerHTML = `<div class="ima-doc-list">${snapshot.items.map((item) => imaDocumentRow(item)).join("")}</div>${more}`;
  requestAnimationFrame(() => {
    body.scrollTop = snapshot.scrollTop;
    const row = [...body.querySelectorAll(".ima-doc-row")].find((item) => imaDocumentKey(item.dataset.mediaId, item.dataset.groupId) === snapshot.selectedKey);
    if (row) {
      row.classList.add("is-selected");
      row.setAttribute("aria-current", "true");
    }
    if (snapshot.focusSearch) {
      snapshot.focusSearch = false;
      $("#ima-doc-q")?.focus();
    }
  });
  return true;
}
```

After the list header is mounted in `renderImaDocuments`, call `currentImaListSnapshot()`. If present, call `restoreImaListSnapshot(snapshot, body)`, restore the tag/date controls from the snapshot, and return without calling `/api/ima-documents`.

Do not store blobs or PDF URLs in the snapshot.

- [ ] **Step 5: Open the reader without reloading the list or catalog**

Replace the local shared-desk branch in `openImaDocument` with:

```javascript
const listWasOpen = !!$("#ima-report-page");
if (listWasOpen) captureImaListSnapshot(id, groupId);
const url = normalizeRoute(imaDocumentReaderRoute(id, groupId));
if (location.pathname + location.search !== url) {
  if (replace) history.replaceState(null, "", url);
  else history.pushState(null, "", url);
}
mountKnowledgeReaderShell();
const seq = ++routeRenderSeq;
renderImaDocument(seq, id);
```

When previous/next navigation calls this function from the reader, `listWasOpen` is false, so the original snapshot remains unchanged. Use `replace=true` for previous/next so browser Back returns to the list rather than every intermediate report.

- [ ] **Step 6: Add reliable Back and previous/next helpers**

Add:

```javascript
function backFromImaReader(fallbackRoute, focusSearch = false) {
  const snapshot = _imaListSnapshot;
  if (snapshot && snapshot.route === normalizeRoute(fallbackRoute)) {
    if (focusSearch) snapshot.focusSearch = true;
    history.back();
    return;
  }
  go(fallbackRoute);
}

function imaReaderNavHtml(mediaId, groupId = "") {
  const snapshot = _imaListSnapshot;
  if (!snapshot || snapshot.items.length < 2) return "";
  const current = imaDocumentKey(mediaId, groupId);
  const index = snapshot.items.findIndex((item) => imaDocumentKey(item.media_id, item.group_id) === current);
  if (index < 0) return "";
  const prev = snapshot.items[index - 1];
  const next = snapshot.items[index + 1];
  const button = (item, className, label) => item
    ? `<button type="button" class="${className}" onclick="openImaDocument('${escapeHtml(item.media_id)}', '${escapeHtml(item.group_id || "")}', true)">${label} <span>${escapeHtml(imaListTitle(item.name))}</span></button>`
    : "";
  return `<nav class="ima-reader-nav" aria-label="同一结果集">${button(prev, "ima-reader-prev", "上一份")}${button(next, "ima-reader-next", "下一份")}</nav>`;
}
```

During restoration, if `snapshot.focusSearch` is true, clear it and focus `#ima-doc-q` after painting.

- [ ] **Step 7: Render the dedicated reader**

In `renderImaDocument`, keep group scoping, translation ownership, PDF validation, and session guards. Replace the reader HTML with:

```javascript
const backLabel = _imaListSnapshot ? `返回${_imaListSnapshot.items.length}${_imaListSnapshot.hasMore ? "+" : ""}条结果` : "返回研报列表";
const download = item.has_pdf
  ? `<button type="button" class="btn-normal ima-reader-download" onclick="downloadImaPdf('${escapeHtml(mediaId)}')">${DOWNLOAD_ICON}<span>下载 PDF</span></button>`
  : "";
$("#kb-reader").innerHTML = `
  <article class="ima-reader">
    <header class="ima-reader-toolbar">
      <button type="button" class="btn-ghost ima-reader-back" data-back="${escapeHtml(backRoute)}" onclick="backFromImaReader(this.dataset.back)">返回 <span>${escapeHtml(backLabel)}</span></button>
      <div class="ima-reader-actions"><button type="button" class="icon-btn" aria-label="返回搜索" data-back="${escapeHtml(backRoute)}" onclick="backFromImaReader(this.dataset.back, true)">${SEARCH_ICON}</button>${download}</div>
    </header>
    <section class="ima-reader-info">
      <h2 class="ima-reader-title">${escapeHtml(imaDisplayTitle(item.name))}</h2>
      ${fileMetaHtml}
      ${abstractHtml}
    </section>
    ${pdfPanel}
    ${imaReaderNavHtml(mediaId, item.group_id || documentGroup)}
  </article>`;
```

Keep `<details open class="ima-reader-abstract">`. Keep `frame.src = window._imaPdfUrl` without toolbar-suppression fragments or clipping.

- [ ] **Step 8: Run reader ownership and navigation regressions**

Run:

```bash
node --check app/static/app.js
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_ima_reader_captures_and_restores_the_loaded_result_set \
  tests/test_frontend_interactions.py::test_ima_reader_has_one_app_download_and_result_neighbors \
  tests/test_frontend_interactions.py::test_ima_reader_separates_document_group_from_list_source_filter \
  tests/test_frontend_interactions.py::test_ima_document_reader_requests_keep_current_group_for_all_endpoints \
  tests/test_frontend_interactions.py::test_ima_pdf_load_is_owned_by_route_and_reader_generation_before_load_or_fail_side_effects \
  tests/test_frontend_interactions.py::test_ima_pdf_download_checks_session_owner_before_every_side_effect
```

Expected: syntax check succeeds and `6 passed`.

- [ ] **Step 9: Commit the dedicated reader**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git commit -m "feat(ima): add dedicated report reader"
```

---

### Task 5: Preserve Old Content During Refresh and Harden States

**Files:**
- Modify: `app/static/app.js` (`refreshImaDocuments`, `renderImaDocuments`, `showImaPdfFail`)
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write failing refresh/error-state tests**

Add:

```python
def test_ima_refresh_keeps_old_reports_and_uses_inline_retry():
    refresh = _fn_body("refreshImaDocuments")
    render = _fn_body("renderImaDocuments")
    error = _fn_body("imaReportRefreshErrorHtml")

    assert "keepOld: true" in refresh
    assert "const oldHtml" in render
    assert "ima-report-refresh-error" in error
    assert "最新研报暂时无法更新" in error
    assert "refreshImaDocuments()" in error
    assert "body.innerHTML = oldHtml" in render


def test_ima_report_states_do_not_drop_incomplete_documents():
    empty = _fn_body("imaDocumentsEmptyHtml")
    row = _fn_body("imaDocumentRow")
    fail = _fn_body("showImaPdfFail")

    assert "没有找到相关研报" in empty
    assert "换个公司、代码或主题试试" in empty
    assert 'fmtImaDayShort(item.day) || "—"' in row
    assert "预览打不开" in fail
    assert "downloadImaPdf" not in fail
    assert "btn-normal" not in fail
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_ima_refresh_keeps_old_reports_and_uses_inline_retry \
  tests/test_frontend_interactions.py::test_ima_report_states_do_not_drop_incomplete_documents
```

Expected: FAIL because refresh currently replaces the list with a skeleton and uses a whole-body error.

- [ ] **Step 3: Add explicit refresh ownership and inline failure**

Change:

```javascript
function refreshImaDocuments() {
  const seq = ++routeRenderSeq;
  renderImaDocuments(seq, { keepOld: true });
}
```

Add:

```javascript
function imaReportRefreshErrorHtml(message) {
  return `<div class="ima-report-refresh-error" role="alert"><span>最新研报暂时无法更新：${escapeHtml(message)}</span><button type="button" class="btn-ghost" onclick="refreshImaDocuments()">重试</button></div>`;
}
```

Change the signature to:

```javascript
async function renderImaDocuments(seq, { keepOld = false } = {})
```

Before replacing list content, capture:

```javascript
const previousBody = $("#ima-docs-body");
const oldHtml = keepOld ? previousBody?.innerHTML || "" : "";
```

Keep old rows mounted while the request runs and set `aria-busy="true"` on `#ima-report-page`. On success, remove it and paint the response. On failure:

```javascript
const body = $("#ima-docs-body");
$("#ima-report-page")?.removeAttribute("aria-busy");
if (keepOld && oldHtml && body) {
  body.innerHTML = oldHtml;
  body.insertAdjacentHTML("afterbegin", imaReportRefreshErrorHtml(err.message || "请求失败"));
  return;
}
body.innerHTML = emptyState(`加载失败：${err.message}`, `<div><button type="button" class="btn-normal" onclick="refreshImaDocuments()">重试</button></div>`);
```

Do not mutate the list snapshot on a failed refresh.

- [ ] **Step 4: Keep the PDF failure state single-action**

Keep the application-level download only in `.ima-reader-toolbar`. `showImaPdfFail` must render only:

```javascript
panel.innerHTML = `<div class="ima-reader-empty" role="status"><p>预览打不开，请使用上方下载 PDF</p></div>`;
```

- [ ] **Step 5: Run state regressions**

Run:

```bash
node --check app/static/app.js
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_ima_refresh_keeps_old_reports_and_uses_inline_retry \
  tests/test_frontend_interactions.py::test_ima_report_states_do_not_drop_incomplete_documents \
  tests/test_frontend_interactions.py::test_knowledge_reader_pdf_fail_uses_header_download_only \
  tests/test_frontend_interactions.py::test_ima_documents_refresh_and_retry_advance_local_route_seq
```

Expected: syntax check succeeds and `4 passed`.

- [ ] **Step 6: Commit hardened states**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git commit -m "fix(ima): preserve reports during refresh failures"
```

---

### Task 6: Replace the Two-Pane CSS with Report and Reader Layouts

**Files:**
- Modify: `app/static/style.css:486-493, 2717-3184`
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write failing layout/token tests**

Add:

```python
def test_ima_report_first_layout_is_flat_dense_and_full_width():
    css = STYLE_CSS.read_text()

    assert ".ima-report-page" in css
    assert ".ima-report-head" in css
    assert ".ima-report-columns" in css
    assert ".ima-report-body" in css
    assert ".ima-report-title" in css
    assert ".ima-report-source" in css
    assert "grid-template-columns: 64px minmax(0, 1fr) 132px" in css
    assert re.search(r"\.ima-doc-row\s*\{[^}]*min-height:\s*50px", css)
    assert "box-shadow: none" in css
    assert ".kb-desk" not in css
    assert ".kb-reader" not in css


def test_ima_dedicated_reader_fills_the_desktop_surface():
    css = STYLE_CSS.read_text()

    assert ".ima-reader-page" in css
    assert ".ima-reader-toolbar" in css
    assert ".ima-reader-info" in css
    assert ".ima-reader-nav" in css
    assert re.search(r"\.ima-reader-page \.ima-pdf-panel\s*\{[^}]*flex:\s*1", css)
    assert "clip-path" not in css[css.index(".ima-reader-page"):]
    assert "color-scheme: light" not in css[css.index(".ima-reader-page"):]
```

Delete or replace `test_ima_document_headers_have_desktop_flex_alignment` and every remaining knowledge assertion for `.kb-desk`, `.kb-list`, `.kb-reader`, `.kb-desk-search`, or `grid-template-columns: 320px`. The two tests above become the layout authority; generic mobile, PDF ownership, route, and accessibility tests remain.

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_ima_report_first_layout_is_flat_dense_and_full_width \
  tests/test_frontend_interactions.py::test_ima_dedicated_reader_fills_the_desktop_surface
```

Expected: FAIL because `.kb-desk` still owns a 300/320px list column.

- [ ] **Step 3: Remove dead two-pane styles**

Delete the `.page-main:has(.kb-desk)` block and the knowledge-specific `.kb-desk`, `.kb-list`, `.kb-reader`, `.kb-libs`, `.kb-desk-*`, and `@media (max-width: 1439px) { .kb-desk ... }` rules. Keep reusable `.ima-doc-*`, `.ima-reader-*`, date-menu, and generic button rules only when still referenced by the new markup.

- [ ] **Step 4: Add the full-width report surface**

Add:

```css
.page-main:has(.ima-report-page),
.page-main:has(.ima-reader-page) {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px);
  max-height: calc(100vh - 56px);
  padding-top: 16px;
  padding-bottom: 16px;
  overflow: hidden;
}
.ima-report-page,
.ima-reader-page {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
  box-shadow: none;
}
#kb-list { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.ima-report-head { flex: 0 0 auto; border-bottom: var(--border-default); }
.ima-report-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px 10px; }
.ima-report-heading h2 { margin: 0; color: var(--color-text-strong); font-size: var(--text-title); font-weight: var(--font-weight-semibold); }
.ima-report-search { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; padding: 0 16px 12px; }
.ima-report-searchbox { display: flex; align-items: center; gap: 8px; min-height: 42px; padding: 0 12px; border: var(--border-strong); border-radius: var(--radius-control); background: var(--color-surface); }
.ima-report-searchbox:focus-within { border-color: var(--color-accent-text); box-shadow: var(--shadow-focus-ring); }
.ima-report-searchbox input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--color-text); font-size: var(--text-body); }
.ima-report-filters { display: flex; align-items: center; gap: 8px; }
.ima-report-source select,
.ima-report-tag select { min-height: 42px; border: var(--border-strong); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-text); padding: 0 30px 0 10px; }
.ima-source-manage { position: relative; }
.ima-source-manage > summary { display: inline-flex; align-items: center; min-height: 42px; padding: 0 10px; border: var(--border-strong); border-radius: var(--radius-control); cursor: pointer; list-style: none; }
.ima-source-menu { position: absolute; z-index: 20; top: calc(100% + 4px); right: 0; width: 280px; max-height: 320px; overflow: auto; padding: 6px; border: var(--border-default); border-radius: var(--radius-control); background: var(--color-surface); box-shadow: var(--shadow-sm); }
.ima-source-menu .kb-lib-row { min-height: 42px; }
.ima-report-columns,
.ima-doc-row,
.ima-report-skeleton-row { display: grid; grid-template-columns: 64px minmax(0, 1fr) 132px; gap: 12px; align-items: center; padding: 0 16px; }
.ima-report-columns { min-height: 30px; border-top: var(--border-default); background: var(--color-surface-soft); color: var(--color-text-muted); font-size: var(--text-xs); }
.ima-report-body { flex: 1 1 auto; min-height: 0; overflow: auto; }
.ima-doc-row { min-height: 50px; border-bottom: var(--border-default); cursor: pointer; }
.ima-doc-row:hover { background: var(--color-surface-soft); }
.ima-doc-row:focus-visible { outline: 2px solid var(--color-accent); outline-offset: -2px; }
.ima-report-date,
.ima-report-source { overflow: hidden; color: var(--color-text-muted); font-size: var(--text-xs); text-overflow: ellipsis; white-space: nowrap; }
.ima-report-copy { min-width: 0; display: grid; gap: 3px; }
.ima-report-title { overflow: hidden; color: var(--color-text-strong); font-size: var(--text-sm); font-weight: var(--font-weight-semibold); text-overflow: ellipsis; white-space: nowrap; }
.ima-report-meta { display: flex; min-width: 0; gap: 8px; overflow: hidden; color: var(--color-text-muted); font-size: var(--text-xs); white-space: nowrap; }
.ima-report-refresh-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 10px 16px; padding: 8px 10px; border: 1px solid color-mix(in srgb, var(--color-danger) 30%, transparent); border-radius: var(--radius-2xs); color: var(--color-danger); }
.ima-report-skeleton-row { min-height: 50px; border-bottom: var(--border-default); }
```

Use existing skeleton colors/tokens; do not add gradients, cards, or shadows.

- [ ] **Step 5: Add the dedicated reader layout**

Add:

```css
#kb-reader,
.ima-reader { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.ima-reader-toolbar { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 48px; padding: 6px 12px; border-bottom: var(--border-default); }
.ima-reader-actions { display: flex; align-items: center; gap: 8px; }
.ima-reader-back { min-width: 0; max-width: 50%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ima-reader-info { flex: 0 0 auto; padding: 12px 16px; }
.ima-reader-title { margin: 0; color: var(--color-text-strong); font-size: var(--text-title); font-weight: var(--font-weight-semibold); }
.ima-reader-info .ima-reader-filemeta { margin-top: 6px; }
.ima-reader-info .ima-reader-abstract { margin-top: 8px; }
.ima-reader-page .ima-pdf-panel { flex: 1 1 auto; min-height: 0; margin: 0; border: 0; border-top: var(--border-default); border-radius: 0; background: var(--color-surface-soft); overflow: hidden; }
.ima-reader-page .ima-pdf-panel iframe { width: 100%; height: 100%; min-height: 0; border: 0; }
.ima-reader-nav { flex: 0 0 auto; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); border-top: var(--border-default); }
.ima-reader-nav button { min-width: 0; min-height: 40px; padding: 0 12px; overflow: hidden; border: 0; background: var(--color-surface); color: var(--color-text-muted); text-overflow: ellipsis; white-space: nowrap; }
.ima-reader-nav button:hover { background: var(--color-surface-soft); color: var(--color-accent-text); }
.ima-reader-next { text-align: right; }
```

Keep the browser-native PDF black toolbar; do not set `color-scheme` or `clip-path` on the iframe.

- [ ] **Step 6: Run CSS and phone-block regressions**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_ima_report_first_layout_is_flat_dense_and_full_width \
  tests/test_frontend_interactions.py::test_ima_dedicated_reader_fills_the_desktop_surface \
  tests/test_frontend_interactions.py::test_ima_documents_follow_latest_dynamic_navigation \
  tests/test_frontend_interactions.py::test_knowledge_settings_storage_and_phone_sync_blocks
```

Expected: `4 passed`.

- [ ] **Step 7: Run the Impeccable detector once**

Run:

```bash
node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json \
  app/static/app.js app/static/style.css
```

Expected: no blocking findings. Fix only findings inside the knowledge surface; do not refactor unrelated pages.

- [ ] **Step 8: Commit the visual replacement**

```bash
git add app/static/style.css tests/test_frontend_interactions.py
git commit -m "style(ima): replace knowledge desk with report workspace"
```

---

### Task 7: Cache Busting, Browser Validation, and Full Regression

**Files:**
- Modify: `app/static/index.html:36,135`
- Modify: `app/static/sw.js:2`
- Modify: `tests/test_frontend_interactions.py` (`test_frontend_asset_urls_bust_browser_cache`)
- Verify only: `/tmp/kb-reader-shot.py` or a replacement temporary Playwright script

- [ ] **Step 1: Bump frontend asset versions**

Read the current values first. Increment CSS and JS query versions by one and increment the service-worker cache by one. For the current working tree, the expected next values are:

```html
<link rel="stylesheet" href="/style.css?v=229">
<script src="/app.js?v=313"></script>
```

```javascript
const CACHE = "dav-shell-v185";
```

If another approved change has already bumped them before execution, increment from the actual current values instead of reusing these literals.

- [ ] **Step 2: Update the cache-version test**

Update `test_frontend_asset_urls_bust_browser_cache` to assert exactly the versions written in Step 1.

- [ ] **Step 3: Run syntax and focused knowledge tests**

Run:

```bash
node --check app/static/app.js
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_ima_kb.py::test_documents_searches_tags_and_group_name_and_ranks_title_hits_first \
  tests/test_ima_kb.py::test_list_ima_documents_defaults_to_latest_stream_and_pages_search \
  tests/test_frontend_interactions.py -k 'knowledge or ima_document or ima_report or frontend_asset_urls'
```

Expected: syntax check succeeds and all selected tests pass.

- [ ] **Step 4: Run the broader static/frontend regression**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py \
  tests/test_frontend_pwa.py \
  tests/test_frontend_xss.py \
  tests/test_ima_kb.py
```

Expected: all tests pass. Do not accept xfails or failures introduced by this change.

- [ ] **Step 5: Start the isolated preview server**

Start the existing preview fixture on an unused fixed port in a separate terminal. Importing the fixture seeds `/tmp/kb-daypicker-preview/dav.sqlite`; it never opens production `dav.db`:

```bash
cd '/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription'
.venv/bin/python - <<'PY'
import importlib.util
from pathlib import Path
import uvicorn

path = Path('/tmp/kb-daypicker-preview.py')
spec = importlib.util.spec_from_file_location('kb_report_preview', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
uvicorn.run(module.app, host='127.0.0.1', port=8779, log_level='warning')
PY
```

Expected URL: `http://127.0.0.1:8779/` with `admin / pass123456`.

- [ ] **Step 6: Capture the bounded desktop screenshot set**

Replace `/tmp/kb-reader-shot.py` with this temporary, uncommitted validator:

```python
from io import BytesIO
from pathlib import Path

from playwright.sync_api import sync_playwright
from pypdf import PdfWriter

BASE = "http://127.0.0.1:8779"
OUT = Path("work/ui-validation/knowledge-report-first")
OUT.mkdir(parents=True, exist_ok=True)

pdf_io = BytesIO()
writer = PdfWriter()
writer.add_blank_page(width=612, height=792)
writer.write(pdf_io)
VALID_PDF = pdf_io.getvalue()


def login(page):
    page.goto(BASE, wait_until="domcontentloaded")
    page.fill("#login-username", "admin")
    page.fill("#login-password", "pass123456")
    page.click("button[type=submit]")
    page.wait_for_selector(".sidebar")


def assert_surface(page):
    assert page.locator(".sidebar").count() == 1
    assert page.locator("#main").count() == 1
    assert page.locator(".ima-report-page, .ima-reader-page").count() == 1


def capture(browser, width, height):
    context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
    page = context.new_page()
    page.route(
        "**/api/ima-documents/*/pdf*",
        lambda route: route.fulfill(status=200, body=VALID_PDF, headers={"Content-Type": "application/pdf"}),
    )
    login(page)

    page.goto(f"{BASE}/knowledge", wait_until="networkidle")
    page.wait_for_selector(".ima-doc-row")
    assert_surface(page)
    page.screenshot(path=OUT / f"latest-{width}.png", full_page=True)

    page.goto(f"{BASE}/knowledge?q=2319.HK", wait_until="networkidle")
    page.wait_for_selector(".ima-doc-row")
    assert_surface(page)
    page.screenshot(path=OUT / f"search-{width}.png", full_page=True)

    page.locator(".ima-doc-row").first.click()
    page.wait_for_selector(".ima-reader-page")
    page.wait_for_selector("#ima-pdf-frame:not([hidden])")
    assert_surface(page)
    page.screenshot(path=OUT / f"reader-{width}.png", full_page=True)

    page.locator(".ima-reader-back").click()
    page.wait_for_selector(".ima-report-page")
    assert page.locator("#ima-doc-q").input_value() == "2319.HK"

    page.goto(f"{BASE}/knowledge?q=definitely-no-match", wait_until="networkidle")
    page.wait_for_selector("text=没有找到相关研报")
    assert_surface(page)
    page.screenshot(path=OUT / f"empty-{width}.png", full_page=True)
    context.close()

    fail_context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
    fail_page = fail_context.new_page()
    fail_page.route(
        "**/api/ima-documents/*/pdf*",
        lambda route: route.fulfill(status=200, body=b"not a pdf", headers={"Content-Type": "application/pdf"}),
    )
    login(fail_page)
    fail_page.goto(f"{BASE}/knowledge?q=2319.HK", wait_until="networkidle")
    fail_page.locator(".ima-doc-row").first.click()
    fail_page.wait_for_selector("text=预览打不开")
    assert_surface(fail_page)
    fail_page.screenshot(path=OUT / f"pdf-fail-{width}.png", full_page=True)
    fail_context.close()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    for viewport in ((1280, 800), (1440, 900)):
        capture(browser, *viewport)
    browser.close()
```

Run:

```bash
.venv/bin/python /tmp/kb-reader-shot.py
```

Expected: ten screenshots under `work/ui-validation/knowledge-report-first/`; do not stage `work/`.

- [ ] **Step 7: Review screenshots in one bounded pass**

Check all screenshots together for:

- no two-pane document sidebar;
- list title remains the dominant column at both widths;
- unknown dates show `—` without shifting columns;
- source/tag controls do not dominate the header;
- reader topbar has one application download button;
- native PDF toolbar and black canvas remain visible;
- Back restores the exact query, loaded rows, selected row, and scroll position;
- no overlap, clipped text, nested cards, or Duty Blue overuse.

Apply one consolidated fix batch if needed, rerun Step 3, and capture one confirmation batch only.

- [ ] **Step 8: Commit cache versions and any final verified fixes**

```bash
git add app/static/app.js app/static/style.css app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
git commit -m "test(ima): validate report-first knowledge flow"
```

Before committing, run `git diff --cached --name-only` and confirm no `.cursor/`, `work/`, `docs/research/`, preview data, or unrelated scripts are staged.

---

## Completion Audit

Before claiming completion, map each approved requirement to evidence:

- report-first list: screenshot + `test_ima_report_row_is_document_first_and_keeps_optional_metadata`;
- company is metadata only: list helper test and absence of company cards;
- no-code reports preserved: unknown/optional metadata test;
- dedicated reader: route-owned shell test + screenshot;
- search state/scroll restore: snapshot test + browser back verification;
- same-result previous/next: reader navigation test + browser verification;
- old content survives refresh failure: inline refresh test;
- PDF failure keeps one download action: existing owner/failure tests + screenshot;
- explicit load-more: pagination test;
- phone remains blocked: dynamic navigation/mobile tests;
- native PDF viewer retained: reader CSS test + screenshot;
- no unsupported type inference: no new client classifier and only existing tags/group metadata rendered.

Residual limitations must be reported, not hidden: dates remain `MMDD`, company-name scoping is ordinary text search unless explicit ticker metadata exists, and multi-company relationships require a future manifest/API extension.
