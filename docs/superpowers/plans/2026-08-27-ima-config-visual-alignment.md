# IMA 配置区块视觉统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让“抓取设置 → IMA 文档采集”和“Cookie 管理 → IMA 凭证”复用现有配置区块的布局、字体、间距、控件和响应式规范，同时保持所有行为不变。

**Architecture:** 继续使用现有静态 `app.js` 字符串渲染和 `style.css` token；不引入组件库或新的抽象。采集配置整理为“连接与同步 / 群组列表 / 状态操作”的现有配置层级，凭证表单整理为作用域网格并移除行内布局样式；字段 ID、事件处理器和 API 调用全部保留。

**Tech Stack:** 原生 JavaScript、CSS、项目 `vendor/design-tokens.css`、pytest 前端源码契约测试、Playwright 截图与 Impeccable detector。

---

## File Map

- Modify `app/static/app.js:4914-4960`: IMA 群组行结构；保留 `data-group-*`、字段 ID 和删除行为。
- Modify `app/static/app.js:5212-5284`: 两个 IMA 区块表单层级；去除凭证区块行内布局样式，保留全部事件和输入 ID。
- Modify `app/static/style.css:2723-2750`: IMA 专属网格、代码字体、状态栏和移动端规则，全部复用现有 token。
- Modify `app/static/index.html:36,135`: 递增静态 CSS/JS query 版本。
- Modify `app/static/sw.js:2`: 递增 shell cache 名称。
- Modify `tests/test_frontend_interactions.py` near the existing IMA/Cookie tests: 锁定布局结构、字段、无行内样式和缓存版本。
- Create `docs/superpowers/plans/2026-08-27-ima-config-visual-alignment.md`: 本实施计划。

## Task 1: Write the failing frontend contract tests

**Files:**
- Modify: `tests/test_frontend_interactions.py` near `test_ima_document_collector_lives_in_fetch_settings`
- Modify: `tests/test_frontend_interactions.py:1804-1811` cache-version assertions

- [ ] **Step 1: Add the structural contract test**

Append this test, using the module’s existing `APP_JS`, `STYLE_CSS` and `_fn_body()` helpers:

```python
def test_ima_config_blocks_use_shared_layout_and_no_inline_spacing():
    stats = _fn_body("loadAdminStats")
    row = _fn_body("imaGroupRowHtml")
    config_start = stats.index('<div id="st-config"')
    cookies_start = stats.index('<div id="st-cookies"')
    config = stats[config_start:cookies_start]
    cookies = stats[cookies_start:]
    ima_start = cookies.index("<h2 class=\"section-title\">ima 凭证</h2>")
    ima_end = cookies.index("<h2 class=\"section-title\">知识星球 Cookie</h2>")
    ima_credentials = cookies[ima_start:ima_end]
    css = STYLE_CSS.read_text()

    assert 'class="cfg-group ima-group-row"' in row
    assert 'class="ima-group-fields cfg-fields"' in row
    assert 'class="ima-collector-fields cfg-fields"' in config
    assert 'class="ima-credential-fields"' in ima_credentials
    assert 'class="ima-credential-actions toolbar"' in ima_credentials
    assert 'style="margin-top:' not in ima_credentials
    assert 'style="margin:6px' not in ima_credentials
    assert ".ima-code-field .form-control" in css
    assert ".ima-credential-fields" in css
```

- [ ] **Step 2: Update the existing cache-busting expectations**

Change the existing assertions from the current versions to the next versions:

```python
assert 'href="/style.css?v=195"' in html
assert 'src="/app.js?v=275"' in html
assert 'dav-shell-v144' in sw
```

- [ ] **Step 3: Run only the new/updated tests and verify the failure is meaningful**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py::test_ima_config_blocks_use_shared_layout_and_no_inline_spacing tests/test_frontend_interactions.py::test_frontend_asset_urls_bust_browser_cache
```

Expected: `FAIL` because the current group row has no `cfg-group ima-group-row`, the collector has no `ima-collector-fields`, the credential block still has inline margins, and the asset versions are still `194 / 274 / v143`.

## Task 2: Normalize IMA markup

**Files:**
- Modify: `app/static/app.js:4917-4925`
- Modify: `app/static/app.js:5213-5231`
- Modify: `app/static/app.js:5270-5284`

- [ ] **Step 1: Make each group row a bounded shared config group**

Replace the return template in `imaGroupRowHtml()` with this exact structure. Keep every interpolation, data attribute, field name, value, max length, checkbox condition and handler shown here:

```javascript
  return `
    <div class="cfg-group ima-group-row" data-group-row data-group-index="${index}" data-group-id="${escapeHtml(groupId)}">
      <div class="ima-group-row-head">
        <p class="cfg-group-title">IMA 群组</p>
        <button type="button" class="btn-ghost danger" onclick="removeImaGroupRow(this)" aria-label="移除 IMA 群组">移除</button>
      </div>
      <div class="ima-group-fields cfg-fields">
        <label class="cfg-field"><span>群组名称</span><input type="text" class="form-control" data-field="name" value="${escapeHtml(group.name || "")}" maxlength="100"></label>
        <label class="cfg-field ima-code-field"><span>知识库 ID</span><input type="text" class="form-control" data-field="knowledge_base_id" value="${escapeHtml(group.knowledge_base_id || "")}" maxlength="64"></label>
        <label class="cfg-field ima-code-field"><span>根文件夹 ID</span><input type="text" class="form-control" data-field="root_folder_id" value="${escapeHtml(group.root_folder_id || "")}" maxlength="128"></label>
        <label class="cfg-field cfg-check ima-group-enabled"><input type="checkbox" data-field="enabled" ${group.enabled !== false ? "checked" : ""}><span class="cfg-check-desc">启用</span></label>
      </div>
    </div>`;
```

- [ ] **Step 2: Group collector fields without changing any control**

Replace the current collector fields and group toolbar area with this exact hierarchy; the five labels retain the current values and IDs:

```html
<div class="cfg-stack ima-collector-stack">
  <div class="cfg-group ima-collector-connection">
    <p class="cfg-group-title">连接与同步</p>
    <div class="ima-collector-fields cfg-fields">
      <label class="cfg-field ima-code-field"><span>IMA UID</span><input id="ima-pure-uid" type="text" class="form-control" value="${escapeHtml(pure.uid || "001aa361168019ef")}" maxlength="64"></label>
      <label class="cfg-field ima-code-field"><span>知识库 ID</span><input id="ima-pure-kb" type="text" class="form-control" value="${escapeHtml(pure.knowledge_base_id || "7464369361259867")}" maxlength="64"></label>
      <label class="cfg-field ima-code-field"><span>根文件夹 ID</span><input id="ima-pure-root" type="text" class="form-control" value="${escapeHtml(pure.root_folder_id || "folder_7489327974078249")}" maxlength="128"></label>
      <label class="cfg-field"><span>检查间隔<span class="cfg-unit">分钟</span></span><input id="ima-pure-interval" type="number" class="form-control" min="30" max="10080" value="${Math.round(Number(pure.interval_seconds || 3600) / 60)}"></label>
      <label class="cfg-field ima-code-field ima-field--wide"><span>Refresh Token</span><input id="ima-pure-token" class="form-control" type="password" autocomplete="off" placeholder="${pure.refresh_token?.set ? "已保存，留空保持不变" : "重新登录 IMA 后粘贴"}"></label>
    </div>
  </div>
  <div class="cfg-group ima-groups-block">
    <div class="ima-groups-head">
      <p class="cfg-group-title">知识库群组</p>
      <div class="toolbar ima-groups-toolbar">
        <span id="ima-group-discovery-status" class="muted">${imaGroupDiscoveryStatusText(imaCollector)}</span>
        <button type="button" class="btn-ghost" onclick="addImaGroupRow()">添加 IMA 群组</button>
      </div>
    </div>
    <div id="ima-groups" class="ima-groups-list">${renderImaGroupRows(imaCollector.config && imaCollector.config.groups)}</div>
  </div>
</div>
<div class="cfg-foot ima-collector-foot">
  <span id="ima-collector-status" class="muted">${imaCollectorStatusText(imaCollector)}</span>
  <div class="toolbar"><button type="button" class="btn-normal" onclick="saveImaCollector()">保存采集配置</button><button type="button" class="btn-ghost" onclick="triggerImaCollector()">${REFRESH_ICON}<span>立即同步</span></button></div>
</div>
```

Keep the surrounding `<section>` title and description unchanged. `saveImaCollector()` and `triggerImaCollector()` remain byte-for-byte unchanged; `#ima-groups [data-group-row]` continues to match the new markup.

- [ ] **Step 3: Give the IMA credentials block a scoped form layout**

Replace only the current three independent labels, their inline-styled inputs, and the inline-styled toolbar with this exact structure. Keep the original `ima`, `cid`, `key` data expressions and conditional clear button:

```html
<div class="ima-credential-fields">
  <label class="ima-credential-field ima-credential-field--wide" for="ima-cookie">
    <span>网页 Cookie（x-ima-cookie）</span>
    <textarea id="ima-cookie" class="form-control cookie-paste" rows="3" placeholder="IMA-TOKEN=...; IMA-UID=..."></textarea>
  </label>
  <label class="ima-credential-field ima-code-field" for="ima-cid">
    <span>OpenAPI Client ID</span>
    <input id="ima-cid" class="form-control" placeholder="Client ID">
  </label>
  <label class="ima-credential-field ima-code-field" for="ima-key">
    <span>OpenAPI API Key</span>
    <input id="ima-key" class="form-control" placeholder="API Key" type="password">
  </label>
</div>
<div class="ima-credential-actions toolbar">
  <button type="button" class="btn-normal" onclick="saveImaCredentials()">保存 ima 凭证</button>
  <button type="button" class="btn-ghost" onclick="pasteCookieField('ima-cookie')">从剪贴板填入 Cookie</button>
  ${ima.cookie?.set && !ima.cookie.from_env ? `<button type="button" class="btn-ghost danger" onclick="clearSavedCookie('ima','ima')" aria-label="清除 ima Cookie">清除 Cookie</button>` : ""}
</div>
```

Remove the old `style="margin-top:8px;display:block"`, `style="margin-top:6px"` and `style="margin-top:12px"` attributes in this section only. Do not change `saveImaCredentials()` or credential API payloads.

## Task 3: Add the minimum scoped CSS

**Files:**
- Modify: `app/static/style.css` around the existing IMA rules at `2723-2750`

- [ ] **Step 1: Add desktop rules using existing design tokens**

Replace the obsolete `.ima-collector-grid` rule and the duplicate base `.ima-collector-foot` layout rule with:

```css
.ima-collector-stack { display: grid; gap: var(--space-4); }
.ima-collector-connection,
.ima-groups-block,
.ima-group-row { min-width: 0; }
.ima-collector-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3) var(--space-4);
  margin-top: var(--space-3);
}
.ima-collector-fields .cfg-field { min-width: 0; }
.ima-collector-fields .ima-field--wide { grid-column: 1 / -1; }
.ima-groups-head,
.ima-group-row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.ima-groups-head .cfg-group-title,
.ima-group-row-head .cfg-group-title { margin: 0; }
.ima-groups-toolbar { margin: 0; }
.ima-groups-list { display: grid; gap: var(--space-3); margin-top: var(--space-3); }
.ima-group-row { padding: 14px 16px 16px; }
.ima-group-fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3) var(--space-4);
  margin-top: var(--space-3);
}
.ima-group-fields .cfg-field { min-width: 0; }
.ima-group-enabled { grid-column: 1 / -1; }
.ima-code-field .form-control {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.ima-credential-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}
.ima-credential-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  color: var(--color-text-strong);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
}
.ima-credential-field--wide { grid-column: 1 / -1; }
.ima-credential-field .form-control { margin: 0; }
.ima-credential-actions { margin-top: var(--space-4); }
.ima-collector-foot .toolbar { margin-top: 0; }
```

- [ ] **Step 2: Add narrow-layout rules after the existing IMA rules**

Add:

```css
@media (max-width: 800px) {
  .ima-collector-fields,
  .ima-group-fields,
  .ima-credential-fields { grid-template-columns: 1fr; }
  .ima-collector-fields .ima-field--wide,
  .ima-group-enabled,
  .ima-credential-field--wide { grid-column: auto; }
}

@media (max-width: 768px) {
  .ima-collector-foot { align-items: stretch; }
  .ima-collector-foot .toolbar,
  .ima-credential-actions { width: 100%; }
  .ima-collector-foot .toolbar button,
  .ima-credential-actions button { flex: 1 1 160px; min-height: 44px; }
  .ima-groups-head { align-items: flex-start; flex-direction: column; }
  .ima-groups-toolbar { width: 100%; }
  .ima-groups-toolbar button { width: 100%; }
}
```

Retain `.cookie-paste` and the existing mobile 16px form-control rule. Do not add colors, shadows, radii, font families, or arbitrary negative spacing.

- [ ] **Step 3: Bust browser and service-worker caches**

Change only these current literals:

```text
app/static/index.html: /style.css?v=194 -> /style.css?v=195
app/static/index.html: /app.js?v=274 -> /app.js?v=275
app/static/sw.js: const CACHE = "dav-shell-v143" -> const CACHE = "dav-shell-v144"
```

## Task 4: Run tests and inspect the diff

**Files:**
- Test: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k 'ima or cookie_tab'
```

Expected: all selected tests pass, including the new shared-layout contract and updated asset-version test.

- [ ] **Step 2: Run the full frontend interaction suite**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py
```

Expected: PASS with no new failures.

- [ ] **Step 3: Check diff and touched files**

Run:

```bash
git diff --check -- app/static/app.js app/static/style.css app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
git status --short -- app/static/app.js app/static/style.css app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
```

Expected: no whitespace errors; the status output reflects only these intended files, alongside the repository’s pre-existing unrelated changes.

## Task 5: Verify the rendered layout and detector output

**Files:**
- Verify: `app/static/app.js`, `app/static/style.css`, `app/static/index.html`, `app/static/sw.js`
- Output: `work/ui-validation/ima-config-desktop.png`, `work/ui-validation/ima-config-mobile.png`, `work/ui-validation/ima-credentials-desktop.png`, `work/ui-validation/ima-credentials-mobile.png`

- [ ] **Step 1: Start a UI-only server against a temporary database**

Run from the repository root in a separate terminal:

```bash
tmpdir=$(mktemp -d)
DAV_UI_ONLY=1 ALERTS_ENABLED=false WEB_ADMIN_PASSWORD=ima-ui-test DB_PATH="$tmpdir/ima-ui.db" .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Use the generated temporary database only for the visual check; do not point the server at `data/dav.db`.

- [ ] **Step 2: Capture the two tabs at desktop and mobile widths**

After logging in at `http://127.0.0.1:8765` as `admin` / `ima-ui-test`, run:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from playwright.sync_api import sync_playwright

base = "http://127.0.0.1:8765"
out = Path("work/ui-validation")
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for width, suffix in ((1440, "desktop"), (390, "mobile")):
        page = browser.new_page(viewport={"width": width, "height": 1200}, device_scale_factor=1)
        page.goto(base, wait_until="networkidle")
        page.get_by_label("用户名").fill("admin")
        page.get_by_label("密码").fill("ima-ui-test")
        page.get_by_role("button", name="登录").click()
        page.wait_for_load_state("networkidle")
        page.goto(base + "/admin/stats?tab=config", wait_until="networkidle")
        page.screenshot(path=str(out / f"ima-config-{suffix}.png"), full_page=True)
        page.goto(base + "/admin/stats?tab=cookies", wait_until="networkidle")
        page.screenshot(path=str(out / f"ima-credentials-{suffix}.png"), full_page=True)
        page.close()
    browser.close()
PY
```

Check the screenshots for shared title/meta hierarchy, label/body font scale, 1px borders, 42/44px controls, no overflow for long IDs, and mobile single-column reflow. Stop the temporary server after inspection.

- [ ] **Step 3: Run the required mechanical scan once after the UI is finished**

Run:

```bash
node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json app/static/app.js app/static/style.css
```

Expected: no unexplained layout/type findings caused by the IMA additions.

- [ ] **Step 4: Run the final focused regression set**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py tests/test_ima_documents.py tests/test_ima_kb.py
```

Expected: PASS; backend and IMA behavior tests remain unchanged because this plan modifies only frontend rendering, styling, and cache version literals.
