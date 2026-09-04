# 飞书时间线来源头像 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 飞书时间线顶部用来源头像胶囊切换杨康平 / 失业期神；研报库列表和混看来源名用同一套显示名。条目本身不加头像。

**Architecture:** 前端一张对照表 `FEISHU_SOURCE_DISPLAY` + `feishuSourceDisplay(title)`。`group_id` 和接口不变。头像是 `app/static/` 里的小 PNG，URL 带 `?v=1`。

**Tech Stack:** 现有原生 JS / CSS / pytest 静态源码测试。图片用已安装的 Pillow 压成 128×128。

**规格:** `docs/superpowers/specs/2026-09-03-feishu-timeline-source-avatars-design.md`

---

## 文件映射

- Create: `app/static/feishu-yang.png`（杨康平 / `K神-2026`）
- Create: `app/static/feishu-shiye.png`（失业期神 / `Q神-档案库`）
- Modify: `app/static/app.js`：对照表、胶囊、来源名、回滚不再找 `<select>`
- Modify: `app/static/style.css`：胶囊里头像圆
- Modify: `app/static/index.html`：`app.js?v=398`、`style.css?v=280`
- Modify: `tests/test_frontend_interactions.py`
- Modify: `tests/test_frontend_pwa.py`：同步缓存键
- Create: `docs/superpowers/plans/2026-09-03-feishu-timeline-source-avatars.md`

## 对照表

| 现有来源名 | 显示名 | 文件 |
| --- | --- | --- |
| `K神-2026`、`杨康平` | 杨康平 | `/feishu-yang.png?v=1` |
| `Q神-档案库`、`Q神`、`失业期神` | 失业期神 | `/feishu-shiye.png?v=1` |

原图：`.superpowers/brainstorm/33151-1788424712/content/yang.png`、`shiye.png`

---

### Task 1: 对照表和压缩头像

**Files:**
- Create: `app/static/feishu-yang.png`
- Create: `app/static/feishu-shiye.png`
- Modify: `app/static/app.js`（`feishuLiveItemHtml` 上方）
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: 写会失败的测试**

在 `tests/test_frontend_interactions.py` 里 `test_feishu_timeline_uses_windowed_pages_and_load_more_state` 之前加上：

```python
def test_feishu_source_display_maps_known_libraries():
    src = APP_JS.read_text()
    helper = _fn_body("feishuSourceDisplay")
    assert 'function feishuSourceDisplay' in src
    assert '"K神-2026"' in src and '"Q神-档案库"' in src
    assert '"Q神"' in src
    assert "杨康平" in src and "失业期神" in src
    assert "/feishu-yang.png?v=1" in src
    assert "/feishu-shiye.png?v=1" in src
    assert "FEISHU_SOURCE_DISPLAY[raw]" in helper
    assert 'label: raw' in helper


def test_feishu_source_avatar_files_are_small_static_pngs():
    yang = APP_JS.with_name("feishu-yang.png")
    shiye = APP_JS.with_name("feishu-shiye.png")
    assert yang.is_file() and shiye.is_file()
    assert yang.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert shiye.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert yang.stat().st_size < 80_000
    assert shiye.stat().st_size < 80_000
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest tests/test_frontend_interactions.py::test_feishu_source_display_maps_known_libraries tests/test_frontend_interactions.py::test_feishu_source_avatar_files_are_small_static_pngs -q`

Expected: FAIL，`feishuSourceDisplay` 不存在，PNG 不存在。

- [ ] **Step 3: 压图并加上对照表**

```bash
python3 - <<'PY'
from pathlib import Path
from PIL import Image

root = Path("/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription")
src_dir = root / ".superpowers/brainstorm/33151-1788424712/content"
out = root / "app/static"

def square(src, dest):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    im = im.resize((128, 128), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG", optimize=True)

square(src_dir / "yang.png", out / "feishu-yang.png")
square(src_dir / "shiye.png", out / "feishu-shiye.png")
print((out / "feishu-yang.png").stat().st_size, (out / "feishu-shiye.png").stat().st_size)
PY
```

在 `app/static/app.js` 的 `function feishuLiveItemHtml` 正上方插入：

```javascript
const FEISHU_SOURCE_DISPLAY = {
  "K神-2026": { label: "杨康平", avatar: "/feishu-yang.png?v=1" },
  "杨康平": { label: "杨康平", avatar: "/feishu-yang.png?v=1" },
  "Q神-档案库": { label: "失业期神", avatar: "/feishu-shiye.png?v=1" },
  "Q神": { label: "失业期神", avatar: "/feishu-shiye.png?v=1" },
  "失业期神": { label: "失业期神", avatar: "/feishu-shiye.png?v=1" },
};

function feishuSourceDisplay(title) {
  const raw = String(title || "").trim();
  return FEISHU_SOURCE_DISPLAY[raw] || { label: raw, avatar: "" };
}
```

- [ ] **Step 4: 再跑测试，确认通过**

Run: `python3 -m pytest tests/test_frontend_interactions.py::test_feishu_source_display_maps_known_libraries tests/test_frontend_interactions.py::test_feishu_source_avatar_files_are_small_static_pngs -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/static/feishu-yang.png app/static/feishu-shiye.png app/static/app.js tests/test_frontend_interactions.py
git commit -m "feat: 飞书来源显示名和静态头像"
```

---

### Task 2: 顶部下来源改成胶囊

**Files:**
- Modify: `app/static/app.js`（`feishuTimelineToolbarHtml`、`selectFeishuTimelineSource`）
- Modify: `app/static/style.css`（`.feishu-timeline-toolbar` 附近）
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: 写会失败的测试**

同一测试文件加上：

```python
def test_feishu_timeline_toolbar_uses_source_avatar_pills():
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    toolbar = _fn_body("feishuTimelineToolbarHtml")
    pills = _fn_body("feishuSourcePillsHtml")
    select_src = _fn_body("selectFeishuTimelineSource")
    item = _fn_body("feishuLiveItemHtml")
    assert "function feishuSourcePillsHtml" in src
    assert "feishuSourcePillsHtml(" in toolbar
    assert 'aria-label="来源"' in pills
    assert "feishu-source-avatar" in pills
    assert "selectFeishuTimelineSource(this.dataset.group)" in pills
    assert "全部来源" not in toolbar
    assert "<select" not in toolbar
    assert "select[aria-label=" not in select_src
    assert "class=\"live-item\"" in item
    assert "feishu-source-avatar" not in item
    assert ".feishu-source-avatar" in css
    assert "border-radius: 50%" in css
```

并把 `test_feishu_timeline_reader_interaction_batch` 里的：

```python
    assert "showSourceSelect = sources.length > 1" in toolbar
```

改成：

```python
    assert "feishuSourcePillsHtml(" in toolbar
    assert "<select" not in toolbar
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest tests/test_frontend_interactions.py::test_feishu_timeline_toolbar_uses_source_avatar_pills tests/test_frontend_interactions.py::test_feishu_timeline_reader_interaction_batch -q`

Expected: FAIL，toolbar 仍是 `<select>`。

- [ ] **Step 3: 改 toolbar 和回滚**

把 `feishuTimelineToolbarHtml` 里来源 `<select>` 整段换成：

```javascript
function feishuSourcePillsHtml(sources, selectedGroup) {
  const selected = String(selectedGroup || "");
  const items = sources.length > 1 ? [{ group_id: "", title: "全部" }, ...sources] : sources;
  if (!items.length) return "";
  return `<div class="tl-pills feishu-source-pills" role="radiogroup" aria-label="来源">${items.map((source) => {
    const id = String(source.group_id || "");
    const display = feishuSourceDisplay(source.title);
    const on = id === selected;
    const img = display.avatar ? `<img class="feishu-source-avatar" src="${escapeHtml(display.avatar)}" alt="">` : "";
    return `<button type="button" class="tl-pill${on ? " selected" : ""}" role="radio" aria-checked="${on}" data-group="${escapeHtml(id)}" aria-label="${escapeHtml(display.label)}" onclick="selectFeishuTimelineSource(this.dataset.group)">${img}<span>${escapeHtml(display.label)}</span></button>`;
  }).join("")}</div>`;
}
```

`feishuTimelineToolbarHtml` 删除 `sourceOptions` / `showSourceSelect` / `<select aria-label="来源">`，在日期选择器旁输出 `feishuSourcePillsHtml(sources, selectedGroup)`。

`selectFeishuTimelineSource` 失败回滚里删掉：

```javascript
    const select = document.querySelector('.feishu-timeline-toolbar select[aria-label="来源"]');
    if (select?.isConnected) select.value = current.selectedGroup;
```

`renderFeishuTimelineView()` 已经会按恢复后的 state 重画胶囊。

在 `.feishu-timeline-toolbar` 规则后加：

```css
.feishu-source-pills { flex-wrap: wrap; }
.feishu-source-avatar {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
```

- [ ] **Step 4: 再跑测试，确认通过**

Run: `python3 -m pytest tests/test_frontend_interactions.py::test_feishu_timeline_toolbar_uses_source_avatar_pills tests/test_frontend_interactions.py::test_feishu_timeline_reader_interaction_batch -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/static/app.js app/static/style.css tests/test_frontend_interactions.py
git commit -m "feat: 飞书时间线用来源头像胶囊切换"
```

---

### Task 3: 研报库列表和混看名字

**Files:**
- Modify: `app/static/app.js`（`knowledgeLibRowHtml`、`knowledgeSourceControlsHtml`、`feishuLiveItemHtml`、`setPageTitle(selectedGroupName)`）
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: 写会失败的测试**

```python
def test_knowledge_and_timeline_use_feishu_source_display_names():
    row = _fn_body("knowledgeLibRowHtml")
    controls = _fn_body("knowledgeSourceControlsHtml")
    item = _fn_body("feishuLiveItemHtml")
    render = _fn_body("renderImaDocuments")
    assert "feishuSourceDisplay(" in row
    assert "feishuSourceDisplay(" in controls
    assert "feishuSourceDisplay(source.title).label" in item
    assert "feishuSourceDisplay(selectedGroupName).label" in render
    assert 'id="ima-doc-source"' in controls
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest tests/test_frontend_interactions.py::test_knowledge_and_timeline_use_feishu_source_display_names -q`

Expected: FAIL

- [ ] **Step 3: 接到同一张表**

`knowledgeLibRowHtml`：

```javascript
  const name = feishuSourceDisplay(group.name || id).label;
```

`knowledgeSourceControlsHtml` 的 map：

```javascript
    name: feishuSourceDisplay(group.name || group.id).label,
```

`feishuLiveItemHtml` 的来源名：

```javascript
  const sourceLabel = showSource && source.title ? `<div class="feishu-live-source">${escapeHtml(feishuSourceDisplay(source.title).label)}</div>` : "";
```

`renderImaDocuments` 里：

```javascript
    if (!knowledgeMediaIdFromPath()) setPageTitle(feishuSourceDisplay(selectedGroupName).label);
```

不要改 `ima-progress` 管理文案。

- [ ] **Step 4: 再跑测试，确认通过**

Run: `python3 -m pytest tests/test_frontend_interactions.py::test_knowledge_and_timeline_use_feishu_source_display_names tests/test_frontend_interactions.py::test_feishu_timeline_toolbar_uses_source_avatar_pills -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git commit -m "feat: 研报库列表用飞书来源显示名"
```

---

### Task 4: 缓存键

**Files:**
- Modify: `app/static/index.html`：`style.css?v=279` → `280`，`app.js?v=397` → `398`
- Modify: `tests/test_frontend_interactions.py` 里对应 assert
- Modify: `tests/test_frontend_pwa.py` 里对应 assert

当前值：`href="/style.css?v=279"`、`src="/app.js?v=397"`。

- [ ] **Step 1: 写会失败的测试**

改这两个测试里的键：
- `tests/test_frontend_interactions.py::test_static_asset_cache_bust_versions`
- `tests/test_frontend_pwa.py::test_frontend_assets_match_financial_news_release_revision`

```python
    assert 'href="/style.css?v=280"' in html
    assert 'src="/app.js?v=398"' in html
```

不动 `sw.js` 的 `dav-shell-v263`，不动 `APP_VERSION`。

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest tests/test_frontend_interactions.py::test_static_asset_cache_bust_versions tests/test_frontend_pwa.py::test_frontend_assets_match_financial_news_release_revision -q`

Expected: FAIL，index.html 仍是 `v=279` / `v=397`。

- [ ] **Step 3: 改 `app/static/index.html`**

```html
  <link rel="stylesheet" href="/style.css?v=280">
```

```html
  <script src="/app.js?v=398"></script>
```

- [ ] **Step 4: 跑相关测试**

Run: `python3 -m pytest tests/test_frontend_interactions.py tests/test_frontend_pwa.py -q`

Expected: PASS（若全文件过慢，至少跑本计划新增的 4 个测试 + 缓存键那两条）。

- [ ] **Step 5: Commit**

```bash
git add app/static/index.html tests/test_frontend_interactions.py tests/test_frontend_pwa.py
git commit -m "chore: 刷新飞书头像相关静态缓存键"
```

---

## 自检

- 规格里的胶囊、对照表、研报库改名、条目不叠头像、静态 `?v=` 都有步骤
- 没有 404 产品逻辑，没有 `/timeline` 迁移，没有动态卡片
- 每步先测试后实现，命令可复制

## 执行

计划写好了。两种执行方式：

1. **Subagent-driven（推荐）** — 每个 task 一个新子代理，独立过测再回来
2. **Inline** — 本会话按 task 执行，每个 task 停下来检查

哪种？
