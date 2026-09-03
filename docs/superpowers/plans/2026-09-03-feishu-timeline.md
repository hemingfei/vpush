# 飞书时间线阅读体验重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让研报库飞书时间线首屏只加载最新 7 个自然日，用稳定游标继续加载历史，并以 B 方案修复错位、移除无用媒体提示且保持正文完整。

**Architecture:** 在 `app/api.py` 为现有完整时间线接口增加可选的服务端窗口、来源过滤和不透明游标；不传窗口参数时维持旧行为。`app/static/app.js` 将当前页状态、游标和加载状态集中在现有 `_feishuTimelineState`，时间线分页而文档模式继续完整原始顺序。`app/static/style.css` 用共享 CSS 轨道变量让日期、节点、时间和正文共用同一套几何尺寸。

**Tech Stack:** FastAPI/Python 标准库、SQLite 现有读取模型、原生 JavaScript、CSS、pytest/TestClient。

---

## 文件映射

- Modify: `app/api.py`：游标编码/解码、窗口切页、`GET /api/ima-documents/timeline/all` 可选 query 参数。
- Modify: `app/static/app.js`：分页状态、来源/排序重载、加载更多、作者轨道、提示/媒体占位清理。
- Modify: `app/static/style.css`：时间轨道变量、B 布局、前置正文、加载更多和响应式规则。
- Modify: `tests/test_feishu_documents.py`：服务端窗口、游标和来源过滤契约。
- Modify: `tests/test_frontend_interactions.py`：前端分页、媒体清理、结构和 CSS 契约。
- Create: `docs/superpowers/plans/2026-09-03-feishu-timeline.md`：本实施计划。

## 约定的实现接口

后端在 `app/api.py` 增加三个私有函数，避免把游标细节散落在路由中：

```python
def _feishu_timeline_cursor(entry: dict[str, Any]) -> str: ...
def _feishu_timeline_cursor_key(cursor: str) -> tuple[str, str]: ...
def _feishu_timeline_page(
    entries: list[dict[str, Any]],
    order: Literal["latest", "original"],
    window_days: int | None,
    before: str,
) -> tuple[list[dict[str, Any]], bool, str]: ...
```

时间线请求使用：

```text
GET /api/ima-documents/timeline/all?order=latest&window_days=7
GET /api/ima-documents/timeline/all?order=latest&group=<id>&window_days=7&before=<cursor>
```

响应在旧字段之外增加 `has_more` 和 `next_cursor`。`window_days` 未传时返回完整 `entries`、`has_more=false`、`next_cursor=""`；文档模式不传窗口参数。

---

### Task 1: Add server-side timeline paging

**Files:**
- Modify: `tests/test_feishu_documents.py` near the existing timeline API tests.
- Modify: `app/api.py` near the existing timeline route and datetime imports.

- [ ] **Step 1: Write the failing helper tests**

Add the import and focused tests below. They exercise the required public behavior through the planned private helper; no HTTP fixture is needed for pure ordering/window boundaries.

```python
from app.api import _feishu_timeline_cursor, _feishu_timeline_page


def _timeline_entry(entry_id, day, time="12:00"):
    return {
        "id": entry_id,
        "timestamp": f"{day}T{time}:00+08:00",
        "day": day,
        "time": time,
        "blocks": [{"type": "text", "text": entry_id}],
    }


def test_feishu_timeline_page_returns_latest_seven_days_and_cursor():
    entries = [
        _timeline_entry("d10", "2026-09-10"),
        _timeline_entry("d09", "2026-09-09"),
        _timeline_entry("d08", "2026-09-08"),
        _timeline_entry("d07", "2026-09-07"),
        _timeline_entry("d06", "2026-09-06"),
        _timeline_entry("d05", "2026-09-05"),
        _timeline_entry("d04", "2026-09-04"),
        _timeline_entry("d03", "2026-09-03"),
    ]

    page, has_more, cursor = _feishu_timeline_page(entries, "latest", 7, "")

    assert [item["id"] for item in page] == ["d10", "d09", "d08", "d07", "d06", "d05", "d04"]
    assert has_more is True
    assert cursor == _feishu_timeline_cursor(page[-1])


def test_feishu_timeline_page_uses_strict_timestamp_and_id_cursor():
    entries = [
        _timeline_entry("same-b", "2026-09-04", "12:00"),
        _timeline_entry("same-a", "2026-09-04", "12:00"),
        _timeline_entry("older", "2026-09-03"),
    ]
    before = _feishu_timeline_cursor(entries[0])

    page, _has_more, _cursor = _feishu_timeline_page(entries, "latest", 7, before)

    assert [item["id"] for item in page] == ["same-a", "older"]


def test_feishu_timeline_page_without_window_preserves_full_order():
    entries = [_timeline_entry("a", "2026-09-01"), _timeline_entry("b", "2026-09-02")]

    page, has_more, cursor = _feishu_timeline_page(entries, "latest", None, "")

    assert [item["id"] for item in page] == ["b", "a"]
    assert has_more is False
    assert cursor == ""
```

- [ ] **Step 2: Run the new tests and verify the correct failure**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_feishu_documents.py -k 'timeline_page'
```

Expected: collection fails with `ImportError: cannot import name '_feishu_timeline_cursor' from 'app.api'` because the paging helpers do not exist yet.

- [ ] **Step 3: Implement the minimal cursor and page helpers**

Add `base64` to the standard-library imports and change the typing import to `from typing import Any, Literal`. Add these helpers before `create_router`/the route factory in `app/api.py`:

```python
import base64


def _feishu_timeline_entry_key(entry: dict[str, Any]) -> tuple[str, str]:
    return (str(entry.get("timestamp") or ""), str(entry.get("id") or ""))


def _feishu_timeline_cursor(entry: dict[str, Any]) -> str:
    raw = json.dumps(
        {"timestamp": _feishu_timeline_entry_key(entry)[0], "id": _feishu_timeline_entry_key(entry)[1]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _feishu_timeline_cursor_key(cursor: str) -> tuple[str, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode((cursor + padding).encode("ascii")).decode("utf-8"))
        timestamp = str(payload["timestamp"])
        entry_id = str(payload["id"])
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("时间线游标无效") from exc
    if not timestamp or not entry_id:
        raise ValueError("时间线游标无效")
    return timestamp, entry_id


def _feishu_timeline_page(
    entries: list[dict[str, Any]],
    order: Literal["latest", "original"],
    window_days: int | None,
    before: str,
) -> tuple[list[dict[str, Any]], bool, str]:
    ordered = sorted(entries, key=_feishu_timeline_entry_key, reverse=order == "latest")
    if not window_days:
        return ordered, False, ""
    cursor_key = _feishu_timeline_cursor_key(before) if before else None
    candidates = [
        item for item in ordered
        if cursor_key is None
        or (_feishu_timeline_entry_key(item) < cursor_key if order == "latest" else _feishu_timeline_entry_key(item) > cursor_key)
    ]
    if not candidates:
        return [], False, ""
    anchor = datetime.fromisoformat(str(candidates[0].get("day") or candidates[0]["timestamp"][:10])).date()
    if order == "latest":
        lower = anchor - timedelta(days=window_days - 1)
        page = [
            item for item in candidates
            if lower <= datetime.fromisoformat(str(item.get("day") or item["timestamp"][:10])).date() <= anchor
        ]
    else:
        upper = anchor + timedelta(days=window_days - 1)
        page = [
            item for item in candidates
            if anchor <= datetime.fromisoformat(str(item.get("day") or item["timestamp"][:10])).date() <= upper
        ]
    if not page:
        return [], bool(candidates), ""
    has_more = len(page) < len(candidates)
    return page, has_more, _feishu_timeline_cursor(page[-1]) if has_more else ""
```

- [ ] **Step 4: Run the helper tests and the existing Feishu tests**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_feishu_documents.py -k 'timeline_page'
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_feishu_documents.py
```

Expected: the three new tests and all existing Feishu tests pass.

- [ ] **Step 5: Add the route contract test before wiring the route**

Extend `test_feishu_timeline_is_open_to_all_users` after the existing legacy request with:

```python
    windowed = client.get(
        f"/api/ima-documents/timeline/all?window_days=7&group={group_id}",
        headers=user,
    )
    assert windowed.status_code == 200, windowed.text
    assert windowed.json()["has_more"] is False
    assert windowed.json()["next_cursor"] == ""
```

Add an invalid-cursor assertion in the same test:

```python
    invalid = client.get(
        "/api/ima-documents/timeline/all?window_days=7&before=bad-cursor",
        headers=user,
    )
    assert invalid.status_code == 400
```

- [ ] **Step 6: Run the route test to verify the correct failure**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_feishu_documents.py::test_feishu_timeline_is_open_to_all_users
```

Expected: the `windowed` response assertion fails because the existing route does not accept/use `window_days` or return paging metadata; the invalid cursor request does not yet return 400.

- [ ] **Step 7: Wire optional window, group, and cursor handling into the existing route**

Change `get_all_feishu_document_timelines` in `app/api.py` to accept:

```python
        order: Literal["latest", "original"] = "latest",
        group: str = Query("", max_length=128),
        window_days: int | None = Query(None, ge=1, le=31),
        before: str = Query("", max_length=512),
        user: dict = Depends(get_current_user),
```

Inside the route, retain the existing readable-group calculation and source metadata shape, but build all authorized source metadata before filtering entries. Read timeline files only for the requested `group` when `group` is supplied:

```python
        if before and not window_days:
            raise HTTPException(status_code=400, detail="时间线游标需要窗口参数")
        readable = {group.id for group in _readable_groups(user)}
        sources = [
            item for item in db.list_feishu_document_sources(active_only=True)
            if item.get("timeline_path") and item.get("group_id") in readable
        ]
        if group and not any(item.get("group_id") == group for item in sources):
            raise HTTPException(status_code=404, detail="文档不存在")
        public_sources = [
            {
                "id": source["id"],
                "group_id": source["group_id"],
                "media_id": source["media_id"],
                "title": source.get("title") or "飞书文档",
                "revision_id": source.get("revision_id") or "",
                "last_success_at": source.get("last_success_at") or "",
            }
            for source in sources
        ]
        source_by_group = {item["group_id"]: item for item in public_sources}
        entries = []
        notices = []
        for source in sources:
            if group and source.get("group_id") != group:
                continue
            try:
                timeline = feishu_documents.timeline(source)
            except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
                continue
            public_source = source_by_group[source["group_id"]]
            notices.extend({**item, "source": public_source} for item in timeline.get("notices") or [])
            entries.extend({**item, "source": public_source} for item in timeline.get("entries") or [])
        entries, has_more, next_cursor = _feishu_timeline_page(entries, order, window_days, before)
        return {
            "sources": public_sources,
            "notices": notices,
            "entries": entries,
            "order": order,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }
```

The legacy no-window path still returns every entry, just with the two metadata fields added. Wrap the helper call so malformed client cursors are a bounded 400 response:

```python
        try:
            entries, has_more, next_cursor = _feishu_timeline_page(entries, order, window_days, before)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="时间线游标无效") from exc
```

Then return the response shown above.

- [ ] **Step 8: Run the API regression suite**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_feishu_documents.py
```

Expected: all Feishu document/API tests pass, including the new windowed and invalid-cursor assertions.

- [ ] **Step 9: Commit the server change**

```bash
git add app/api.py tests/test_feishu_documents.py
git commit -m "feat: page Feishu timeline responses"
```

---

### Task 2: Add failing frontend contracts for paging and content cleanup

**Files:**
- Modify: `tests/test_frontend_interactions.py` after `test_feishu_timeline_ui_fixes`.

- [ ] **Step 1: Add the failing static contracts**

```python
def test_feishu_timeline_uses_windowed_pages_and_load_more_state():
    src = APP_JS.read_text()
    load = _fn_body("loadFeishuTimeline")
    view = _fn_body("renderFeishuTimelineView")

    assert "feishuTimelineRequestPath" in load
    assert 'params.set("window_days", "7")' in src
    assert "next_cursor" in src
    assert "has_more" in src
    assert "loadMoreFeishuTimeline" in src
    assert "feishuTimelineMoreHtml" in view


def test_feishu_timeline_removes_unavailable_media_and_failed_image_shells():
    src = APP_JS.read_text()
    asset = _fn_body("feishuTimelineAssetHtml")
    images = _fn_body("loadFeishuTimelineImages")
    view = _fn_body("renderFeishuTimelineView")

    assert "asset.unavailable" not in asset
    assert 'closest(".post-img-link")' in images
    assert 'class="feishu-timeline-notice"' not in view


def test_feishu_timeline_b_layout_shares_one_track_geometry():
    src = STYLE_CSS.read_text()
    entries = _fn_body("feishuTimelineEntriesHtml")

    assert "feishuEntryAuthor" in entries
    assert "--feishu-time-rail" in src
    assert "--feishu-track-gap" in src
    assert "grid-template-columns: var(--feishu-time-rail)" in src
    assert ".feishu-entry-author" in src
```

- [ ] **Step 2: Run the contracts and verify they fail for the missing behavior**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_frontend_interactions.py -k 'windowed_pages or unavailable_media or b_layout'
```

Expected: failures identify the absent `window_days=7`/load-more state, the existing `asset.unavailable` placeholder branch and notice output, and the absent shared layout variables.

---

### Task 3: Implement frontend paging and preserve all document content

**Files:**
- Modify: `app/static/app.js` in `feishuTimelineAssetHtml` through `loadFeishuTimeline`.

- [ ] **Step 1: Remove only unavailable-media UI and empty failed-image shells**

Make `feishuTimelineAssetHtml` return an empty string when no usable asset id exists, while keeping the current image and attachment branches:

```javascript
function feishuTimelineAssetHtml(asset, mediaId, groupId) {
  if (!asset?.id) return "";
  const name = asset.name || (asset.kind === "image" ? "文档图片" : "文档附件");
  if (String(asset.mime || "").startsWith("image/") || asset.kind === "image") {
    return `<a class="post-img-link" href="#" onclick="event.preventDefault();openLightbox(this.querySelector('img'))" aria-label="查看${escapeHtml(name)}"><img src="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=" data-feishu-asset="${escapeHtml(asset.id)}" data-media-id="${escapeHtml(mediaId)}" data-group-id="${escapeHtml(groupId)}" alt="${escapeHtml(name)}" loading="lazy"></a>`;
  }
  return `<button type="button" class="feishu-attachment" data-asset-id="${escapeHtml(asset.id)}" data-media-id="${escapeHtml(mediaId)}" data-group-id="${escapeHtml(groupId)}" data-name="${escapeHtml(name)}" onclick="downloadFeishuTimelineAsset(this)">${escapeHtml(name)}</button>`;
}
```

In `loadFeishuTimelineImages`, mark each image before awaiting its request and remove the complete link on failure:

```javascript
const images = [...document.querySelectorAll("img[data-feishu-asset]:not([data-feishu-loading])")];
await Promise.all(images.map(async (img) => {
  img.dataset.feishuLoading = "1";
  const query = img.dataset.groupId ? `?group=${encodeURIComponent(img.dataset.groupId)}` : "";
  try {
    const blob = await apiBlob(`/api/ima-documents/${encodeURIComponent(img.dataset.mediaId)}/assets/${encodeURIComponent(img.dataset.feishuAsset)}${query}`);
    if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq || !img.isConnected) return;
    const url = URL.createObjectURL(blob);
    _feishuTimelineMediaUrls.push(url);
    img.src = url;
  } catch {
    const link = img.closest(".post-img-link");
    if (link) link.remove();
    else if (img.isConnected) img.remove();
  }
}));
```

This keeps table text and attachment metadata intact; it only suppresses media that cannot be displayed.

- [ ] **Step 2: Add the B-layout author summary and unlabelled preamble rendering**

Add this helper before `feishuTimelineEntriesHtml`:

```javascript
function feishuEntryAuthor(entry) {
  const blocks = Array.isArray(entry?.blocks) ? entry.blocks : [];
  const speakers = [...new Set(blocks.map((block) => String(block?.speaker || "").trim()).filter(Boolean))];
  if (speakers.length !== 1 || blocks.some((block) => String(block?.reply_to || "").trim())) return "";
  return speakers[0];
}
```

Change `feishuTimelineBlockHtml` to accept `showSpeaker = true` and only emit the existing speaker header when it is true:

```javascript
function feishuTimelineBlockHtml(block, mediaId, groupId, showSpeaker = true) {
  if (block.type === "table") {
    const rows = (block.rows || []).map((row, rowIndex) => {
      const tag = rowIndex === 0 ? "th" : "td";
      return `<tr>${(row || []).map((cell) => `<${tag}>${escapeHtml(cell?.text || "").replace(/\n/g, "<br>")}${(cell?.assets || []).map((asset) => feishuTimelineAssetHtml(asset, mediaId, groupId)).join("")}</${tag}>`).join("")}</tr>`;
    }).join("");
    return rows ? `<div class="feishu-entry-table" role="region" aria-label="文档表格" tabindex="0"><table><tbody>${rows}</tbody></table></div>` : "";
  }
  const speaker = String(block.speaker || "");
  const reply = String(block.reply_to || "");
  const text = String(block.text || "");
  const identity = speaker && showSpeaker
    ? `<div class="feishu-entry-speaker"><strong>${escapeHtml(speaker)}</strong>${reply ? `<span>回复 ${escapeHtml(reply)}</span>` : ""}</div>`
    : "";
  const assets = (block.assets || []).filter((asset) => asset && asset.id);
  const assetHtml = assets.length ? `<div class="post-images feishu-entry-assets">${assets.map((asset) => feishuTimelineAssetHtml(asset, mediaId, groupId)).join("")}</div>` : "";
  return `<div class="feishu-entry-block${speaker ? " has-speaker" : ""}">${identity}${text ? `<p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>` : ""}${assetHtml}</div>`;
}
```

In `feishuTimelineEntriesHtml`, put the single author in the time rail and suppress only the duplicated speaker heading for that unambiguous entry. Wrap pre-timestamp notices without a card or title:

```javascript
function feishuTimelineEntriesHtml(entries, showSource) {
  if (!entries.length) return emptyState("这个范围内还没有时间线记录");
  let lastDay = "";
  return entries.map((entry) => {
    const source = entry.source || {};
    const day = String(entry.day || String(entry.timestamp || "").slice(0, 10));
    const dayHead = day !== lastDay
      ? `<h3 class="feishu-day-heading" id="feishu-day-${escapeHtml(day)}"><span>${escapeHtml(fmtImaDay(day) || day)}</span></h3>`
      : "";
    lastDay = day;
    const author = feishuEntryAuthor(entry);
    const sourceLabel = showSource && source.title ? `<span class="feishu-entry-source">${escapeHtml(source.title)}</span>` : "";
    const authorLabel = author ? `<span class="feishu-entry-author">${escapeHtml(author)}</span>` : "";
    const blocks = (entry.blocks || []).map((block) => feishuTimelineBlockHtml(block, source.media_id || "", source.group_id || "", !author)).join("");
    return `${dayHead}<article class="feishu-entry" data-entry-id="${escapeHtml(entry.id || "")}">
      <div class="feishu-entry-time"><time datetime="${escapeHtml(entry.timestamp || "")}">${escapeHtml(entry.time || "")}</time>${authorLabel}${sourceLabel}</div>
      <div class="feishu-entry-content">${blocks || '<p class="muted">空记录</p>'}</div>
    </article>`;
  }).join("");
}
```

In `renderFeishuTimelineView`, keep the existing notice filtering but render the filtered notices without `<aside>`, `<strong>文档提示</strong>`, or a card. A table notice must still use `feishuTimelineBlockHtml`; text notices use an unlabelled `feishu-entry-block`. The final body must be assembled as:

```javascript
const preambleHtml = notices.map((notice) => notice.type === "table"
  ? feishuTimelineBlockHtml(notice, notice.source?.media_id || "", notice.source?.group_id || "")
  : `<div class="feishu-entry-block feishu-timeline-preamble-block"><p>${escapeHtml(notice.text || "").replace(/\n/g, "<br>")}</p></div>`
).join("");
host.innerHTML = `${preambleHtml}${docMode ? feishuDocumentEntriesHtml(entries) : feishuTimelineEntriesHtml(entries, showSourceLabels)}${docMode ? "" : feishuTimelineMoreHtml()}`;
```

- [ ] **Step 3: Add request path and page state helpers**

Add these helpers before `selectFeishuTimelineSource`:

```javascript
function feishuTimelineRequestPath(state, before = "") {
  const params = new URLSearchParams({ order: state.order });
  if (state.mode !== "document") params.set("window_days", "7");
  if (state.selectedGroup) params.set("group", state.selectedGroup);
  if (before) params.set("before", before);
  return `/api/ima-documents/timeline/all?${params.toString()}`;
}

function mergeFeishuTimelineEntries(current, incoming) {
  const seen = new Set(current.map((entry) => String(entry.id || "")));
  return [...current, ...incoming.filter((entry) => {
    const id = String(entry.id || "");
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  })];
}

function feishuTimelineMoreHtml() {
  const state = _feishuTimelineState;
  if (!state || (!state.hasMore && !state.error)) return "";
  const label = state.loading ? "正在加载…" : state.error ? "重试" : "加载更早";
  const error = state.error ? `<p class="feishu-timeline-load-error" role="alert">${escapeHtml(state.error)}</p>` : "";
  return `<div class="feishu-timeline-more"><button type="button" class="btn-normal" onclick="loadMoreFeishuTimeline()"${state.loading ? " disabled" : ""}>${label}</button>${error}</div>`;
}
```

- [ ] **Step 4: Implement one reset/append page loader**

Add `loadFeishuTimelinePage(reset = false)` and `loadMoreFeishuTimeline` after the request helpers. The loader must capture the current state object and ignore a response if the route/readers changed or `_feishuTimelineState` no longer references that request state:

```javascript
async function loadFeishuTimelinePage(reset = false) {
  const current = _feishuTimelineState;
  if (!current || current.loading) return false;
  const before = reset ? "" : current.nextCursor;
  const requestState = {
    ...current,
    loading: true,
    error: "",
    data: reset ? { ...current.data, entries: [], notices: [] } : current.data,
  };
  _feishuTimelineState = requestState;
  renderFeishuTimelineView();
  try {
    const data = await api(feishuTimelineRequestPath(requestState, before));
    if (!routeStillActive(requestState.seq) || requestState.readerSeq !== _imaReaderSeq || _feishuTimelineState !== requestState) return false;
    _feishuTimelineState = {
      ...requestState,
      data: {
        ...data,
        entries: reset ? (data.entries || []) : mergeFeishuTimelineEntries(requestState.data.entries || [], data.entries || []),
        notices: reset ? (data.notices || []) : (requestState.data.notices || []),
      },
      nextCursor: String(data.next_cursor || ""),
      hasMore: !!data.has_more,
      loading: false,
      error: "",
    };
    renderFeishuTimelineView();
    return true;
  } catch (err) {
    if (!routeStillActive(requestState.seq) || requestState.readerSeq !== _imaReaderSeq || _feishuTimelineState !== requestState) return false;
    _feishuTimelineState = { ...requestState, loading: false, error: err.message || "时间线加载失败" };
    renderFeishuTimelineView();
    return false;
  }
}

async function loadMoreFeishuTimeline() {
  const state = _feishuTimelineState;
  if (!state || state.loading || (!state.hasMore && !state.error)) return;
  await loadFeishuTimelinePage(false);
}
```

Update `loadFeishuTimeline` so the first request includes `window_days=7` for timeline mode and initializes `nextCursor`, `hasMore`, `loading`, and `error` from the response. Use `feishuTimelineRequestPath` for the initial request after constructing the state shell; document mode leaves `window_days` unset.

- [ ] **Step 5: Reload pages on source and order changes**

Replace the synchronous source filter with a state reset and page request:

```javascript
async function selectFeishuTimelineSource(groupId) {
  if (!_feishuTimelineState) return;
  const current = _feishuTimelineState;
  const selectedGroup = String(groupId || "");
  if (selectedGroup === current.selectedGroup) return;
  _feishuTimelineState = {
    ...current,
    selectedGroup,
    data: { ...current.data, entries: [], notices: [] },
    nextCursor: "",
    hasMore: false,
    error: "",
  };
  await loadFeishuTimelinePage(true);
}
```

Change `changeFeishuTimelineOrder` to set a new state with `order`, clear entries/cursor/error, await `loadFeishuTimelinePage(true)`, and restore the previous order/select value when that request returns an error. Keep the existing document-mode early return.

- [ ] **Step 6: Run the frontend contracts and existing frontend tests**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_frontend_interactions.py -k 'windowed_pages or unavailable_media or b_layout'
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_frontend_interactions.py
```

Expected: the new contracts and all existing frontend interaction tests pass. If a static assertion conflicts with an existing compatibility test, preserve the test’s behavior contract and adjust only the new assertion’s scope.

- [ ] **Step 7: Commit the frontend behavior change**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git commit -m "feat: paginate and simplify Feishu timeline"
```

---

### Task 4: Implement shared B-layout geometry and states

**Files:**
- Modify: `app/static/style.css` in the existing `.feishu-*` block and its mobile media query.

- [ ] **Step 1: Add shared geometry and state styles**

Replace the independent timeline offsets with shared variables and matching grid geometry:

```css
.feishu-timeline-panel {
  --feishu-time-rail: 68px;
  --feishu-track-gap: 16px;
  --feishu-rail-center: calc(var(--feishu-time-rail) + (var(--feishu-track-gap) / 2));
}
.feishu-day-heading {
  display: grid;
  grid-template-columns: var(--feishu-time-rail) minmax(0, 1fr);
  column-gap: var(--feishu-track-gap);
  margin: 28px 0 0;
  padding: 0 0 10px;
  border-bottom: var(--border-default);
  color: var(--color-text-strong);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
  scroll-margin-top: 12px;
}
.feishu-day-heading::before { content: ""; }
.feishu-entry {
  position: relative;
  display: grid;
  grid-template-columns: var(--feishu-time-rail) minmax(0, 1fr);
  gap: var(--feishu-track-gap);
  padding: 18px 0;
}
.feishu-entry::before {
  content: "";
  position: absolute;
  left: var(--feishu-rail-center);
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--color-line);
}
.feishu-entry::after {
  content: "";
  position: absolute;
  left: var(--feishu-rail-center);
  top: 23px;
  width: 9px;
  height: 9px;
  transform: translateX(-50%);
  border: 2px solid var(--color-accent);
  border-radius: 50%;
  background: var(--color-surface);
}
.feishu-entry-time { min-width: 0; padding-right: 4px; text-align: right; }
.feishu-entry-time > span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.feishu-entry-author { color: var(--color-text); font-size: var(--text-xs); line-height: 1.4; }
.feishu-entry-source { color: var(--color-text-muted); font-size: var(--text-xs); }
.feishu-entry-content { min-width: 0; display: grid; gap: 12px; padding-left: 0; }
.feishu-timeline-preamble-block { margin: 16px 0 4px; }
.feishu-timeline-more { display: grid; justify-items: center; gap: 8px; padding: 18px 0 8px; }
.feishu-timeline-more button { min-height: 44px; }
.feishu-timeline-load-error { margin: 0; color: var(--color-danger); font-size: var(--text-sm); }
```

Delete the now-unused `.feishu-timeline-notice` rules and the `.feishu-asset-missing` rule. Keep existing table, attachment, available-image, date-nav and document-mode styles.

- [ ] **Step 2: Keep mobile geometry on the same variables**

Update the existing `@media (max-width: 768px)` timeline rules as follows:

```css
  .feishu-timeline-panel {
    --feishu-time-rail: 48px;
    --feishu-track-gap: 12px;
  }
  .feishu-timeline-body { padding: 0 14px 32px 12px; }
  .feishu-day-heading { margin-top: 20px; }
  .feishu-entry { padding: 14px 0; }
  .feishu-entry::after { top: 19px; }
  .feishu-entry-time { padding-right: 2px; }
  .feishu-entry-time span { display: none; }
```

The existing mobile toolbar, date select and hidden date rail remain unchanged. The shared grid keeps the date label and entry content aligned at both breakpoints.

- [ ] **Step 3: Run the CSS/frontend tests**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_frontend_interactions.py -k 'feishu_timeline'
```

Expected: all Feishu timeline static contracts pass, including the pre-existing source/order/document-mode contracts and the new shared-geometry contract.

- [ ] **Step 4: Commit the layout change**

```bash
git add app/static/style.css
git commit -m "style: align Feishu timeline tracks"
```

---

### Task 5: Run complete verification and visual checks

**Files:**
- No new production files. Inspect the three implementation files and their tests.

- [ ] **Step 1: Run focused backend and frontend suites**

```bash
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_feishu_documents.py tests/test_frontend_interactions.py
```

Expected: exit code 0 and zero failed tests.

- [ ] **Step 2: Run repository checks that cover JavaScript syntax and Python compilation**

```bash
node --check app/static/app.js
PYTHONPATH=. ./.venv/bin/python -m compileall -q app
```

Expected: both commands exit 0 without syntax or compilation errors.

- [ ] **Step 3: Run the UI server and capture desktop/mobile renders**

Start the application on a separate local port:

```bash
PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 18000
```

If port `18000` is occupied, repeat with `--port 18001`. Open `http://127.0.0.1:18000/knowledge`, authenticate with the existing local test account, enter a Feishu source, and inspect:

- desktop: date label, time rail, node line and body start on one geometry;
- mobile: date selector, 44px controls, no horizontal overflow;
- bottom loading: load-more, retry and no-more behavior;
- real content: text, table, available image and attachment.

Stop the local server after the visual pass.

- [ ] **Step 4: Run the required Impeccable detector once after UI edits**

```bash
node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json app/static/app.js app/static/style.css
```

Read the JSON, fix only findings caused by this change, then rerun the same command once if fixes were made. Record any detector limitation instead of claiming a clean result without output.

- [ ] **Step 5: Review the complete requirement checklist**

Confirm from code/tests/visual output:

```text
[ ] first timeline request sends window_days=7
[ ] server response supplies has_more/next_cursor
[ ] cursor pages have strict (timestamp,id) boundaries
[ ] group and authorization filtering remain enforced
[ ] legacy no-window response remains complete
[ ] top notice card/title is absent
[ ] unavailable media text and failed image shells are absent
[ ] real preamble text/tables remain
[ ] author/time/content use shared track geometry
[ ] load-more success/error/retry states work
[ ] document mode remains original order
[ ] focused tests, syntax, compile, and detector have fresh output
```

- [ ] **Step 6: Commit any final test-only or compatibility adjustment**

```bash
git status --short
git diff --check
```

Only stage files belonging to this feature. Use a final commit message such as:

```bash
git add app/api.py app/static/app.js app/static/style.css tests/test_feishu_documents.py tests/test_frontend_interactions.py
git commit -m "test: verify Feishu timeline redesign"
```

Do not stage `.cursor/`, `config.demo.yaml`, `docs/ima-self-kb-write-handoff.md`, `docs/plans/2026-08-27-admin-duty-dashboard.md`, `docs/research/`, or `work/`.
