# Subscription And Push Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the standalone web “组合订阅 / 我的订阅 / 推送设置” entries with one “订阅与推送” entry whose default tab manages all existing subscriptions.

**Architecture:** Keep the existing backend and `subscriptions` data model unchanged. Reuse the current my-subscription filter/list functions inside a new settings tab, redirect the two legacy SPA paths at the router boundary, and delete the now-dead standalone renderers. Keep settings sub-load failures local so channel, AI, and account tabs remain usable.

**Tech Stack:** Vanilla JavaScript SPA, CSS, FastAPI static hosting, Python `pytest` source-contract tests, Playwright/Chrome for bounded visual validation.

---

## File Map

**Modify:**

- `app/static/app.js`: navigation, legacy redirects, settings tabs, reused subscription panel/loader, mutation refresh behavior, dead renderer removal, related UI copy.
- `tests/test_frontend_interactions.py`: failing contracts for the merged navigation, redirects, settings subscription panel, local failure handling, and updated static asset versions.
- `app/static/index.html`: increment the `app.js` cache-busting query once.
- `app/static/sw.js`: increment the shell cache key once.
- `README.md`: replace obsolete standalone-page screenshots/copy with the merged web workflow.
- `DOCKERHUB.md`: update the web feature list and FAQ entry names.
- `docs/用户指南.md`: document the web “订阅与推送” path without changing the mini-program instructions.

**Do not modify:**

- `app/api.py`, `app/db.py`, `app/scheduler.py`, notifier/fetcher modules, or database migrations.
- `miniprogram/`.
- `app/static/style.css` unless the bounded browser pass proves a real overflow or alignment defect; existing settings-tab scrolling, mobile platform badges, and bottom-nav flex already cover the design.
- `app/version.py` or `APP_VERSION`; release versioning is separate from this information-architecture change.

**Workspace note:** At plan creation, several target files have concurrent local edits. Implement in an isolated worktree based on the branch that contains those edits, or wait until they are committed. Never restore, overwrite, or broadly stage unrelated changes.

### Task 1: Lock And Implement The Single Navigation Entry

**Files:**
- Modify: `tests/test_frontend_interactions.py:1-145`
- Modify: `app/static/app.js:53-54,504-512,664-670,11691-11810`

- [ ] **Step 1: Add a failing navigation and legacy-route contract**

Update the opening module comment so it names the surviving card surfaces: subscription plaza, subscription management, search, and KOL detail.

Add these explicit contracts:

```python
def test_subscription_push_is_the_only_subscription_management_navigation_entry():
    src = APP_JS.read_text()
    nav = src[src.index("const NAV ="):src.index("const SIDEBAR_SLIM_KEY")]
    mobile = src[src.index("const MOBILE_NAV ="):src.index("function renderBottomNav")]

    for block in (nav, mobile):
        assert 'route: "settings"' in block
        assert 'label: "订阅与推送"' in block
        assert 'route: "mysubs"' not in block
        assert 'route: "combinations"' not in block
    assert "TRENDING_ICON" not in src
    assert "BOOKMARK_ICON" not in src


def test_legacy_subscription_pages_redirect_at_the_router_boundary():
    src = APP_JS.read_text()
    router = _fn_body("router")
    prefixes = src[src.index("const SPA_PREFIXES"):src.index("function routeStillActive")]

    assert '"mysubs"' in prefixes and '"combinations"' in prefixes
    assert 'page === "mysubs"' in router
    assert 'state.settingsTab = "subs"' in router
    assert 'replaceRoute("settings")' in router
    assert 'page === "combinations"' in router
    assert 'state.platform = "combination"' in router
    assert 'replaceRoute("home")' in router
    assert "renderMySubs(renderSeq)" not in router
    assert "renderCombinations(renderSeq)" not in router
```

In `test_router_emits_route_token`, keep `renderHome`, `renderTimeline`, `renderKolPage`, `renderSearch`, and `renderSettings`; remove the two legacy renderer calls. Leave the refresh-helper and renderer-guard tests for Task 2, where the replacement loader is introduced.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_subscription_push_is_the_only_subscription_management_navigation_entry \
  tests/test_frontend_interactions.py::test_legacy_subscription_pages_redirect_at_the_router_boundary \
  tests/test_frontend_interactions.py::test_router_emits_route_token
```

Expected: failures showing the legacy navigation entries and render calls still exist.

- [ ] **Step 3: Implement the minimal navigation and router boundary**

Delete the now-unused `TRENDING_ICON` and `BOOKMARK_ICON` constants. In the existing first `NAV` group, replace only its `items` array with:

```javascript
items: [
  { route: "timeline", icon: LIST_ICON, label: "最新动态" },
  { route: "knowledge", icon: BOOK_ICON, label: "研报库" },
  { route: "home", icon: GRID_ICON, label: "订阅广场" },
  { route: "settings", icon: GEAR_ICON, label: "订阅与推送" },
]
```

Replace `MOBILE_NAV` with:

```javascript
const MOBILE_NAV = [
  { route: "timeline", icon: LIST_ICON, label: "动态" },
  { route: "home", icon: GRID_ICON, label: "广场" },
  { route: "settings", icon: GEAR_ICON, label: "订阅与推送" },
];
```

Keep `mysubs` and `combinations` in `SPA_PREFIXES` so old same-origin links are intercepted. Add `settingsTab: "subs"` next to the existing my-subscription state. In `router()`, reset the default only when the destination is outside settings, then replace the legacy branches:

```javascript
const path = routePath();
const [page, rawParam] = path.split("/");
if (page !== "settings") state.settingsTab = "subs";
```

```javascript
if (page === "home") await renderHome(renderSeq);
else if (page === "combinations") {
  state.platform = "combination";
  replaceRoute("home");
  return;
}
else if (page === "mysubs") {
  state.settingsTab = "subs";
  replaceRoute("settings");
  return;
}
else if (page === "timeline") await renderTimeline(renderSeq);
else if (page === "settings") await renderSettings(renderSeq);
```

Do not change the existing `zsxq`, knowledge, admin, auth, or popstate branches.

- [ ] **Step 4: Run the Task 1 contracts and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_subscription_push_is_the_only_subscription_management_navigation_entry \
  tests/test_frontend_interactions.py::test_legacy_subscription_pages_redirect_at_the_router_boundary \
  tests/test_frontend_interactions.py::test_router_emits_route_token
```

Expected: all three pass. The existing standalone renderer functions are temporarily dead but still present; Task 2 deletes them when the replacement panel lands.

- [ ] **Step 5: Commit the navigation boundary**

```bash
git add app/static/app.js tests/test_frontend_interactions.py
git diff --cached --check
git commit -m "refactor: 合并订阅导航入口"
```

Expected: one passing commit containing only navigation, router, state-default, and contract changes.

### Task 2: Move Existing Subscription Management Into Settings

**Files:**
- Modify: `tests/test_frontend_interactions.py:490-620,705-750,2290-2320,2970-3010`
- Modify: `app/static/app.js:2170-2385,4100-4788`
- Modify: `app/static/index.html:135`
- Modify: `app/static/sw.js:2`

- [ ] **Step 1: Add failing settings-panel and local-error contracts**

Add the route-refresh replacement contract:

```python
def test_refresh_kols_view_covers_all_card_routes():
    body = _fn_body("refreshKolsView")
    for route_call in ('isRoute("home")', 'isRoute("settings")',
                       'isRoute("kol/")', 'isRoute("search")'):
        assert route_call in body
    assert "loadHomeKols" in body
    assert "loadSettingsSubscriptions" in body
    assert "renderKolPage" in body
    assert "doSearch" in body
    assert 'isRoute("mysubs")' not in body
    assert 'isRoute("combinations")' not in body
```

In `test_renderers_check_route_token_after_await`, remove `renderMySubs` and `renderCombinations`, then add `loadSettingsSubscriptions` to the guarded local loaders.

Replace the old `renderMySubs`-based mobile test with:

```python
def test_settings_subscription_panel_reuses_mobile_badges_and_desktop_toolbar():
    panel = _fn_body("settingsSubscriptionsPanelHtml")
    tabs = _fn_body("renderMySubsTabs")
    mobile_html = _fn_body("mysubsMobileFiltersHtml")

    assert "isMobileTimelineFilter()" in panel
    assert 'id="mysubs-tabs"' in panel
    assert 'id="mysubs-list"' in panel
    assert 'id="mysubs-fav-toggle"' in panel
    assert '"platform-tabs"' in panel
    assert "platformShortLabel(p)" in mobile_html
    assert "switchMySubsPlatform('${p}')" in mobile_html
    assert "toggleMySubsFav()" in mobile_html
    assert "STAR_SVG" in mobile_html
    assert "mysubsMobileFiltersHtml()" in tabs
    assert 'platformTabHTML(p, state.mysubsPlatform' in tabs


def test_settings_subscription_loader_is_route_guarded_local_and_retryable():
    load = _fn_body("loadSettingsSubscriptions")

    assert 'api("/api/my/subscriptions")' in load
    assert load.count("routeStillActive(seq)") >= 2
    assert '$("#main").innerHTML' not in load
    assert '$("#mysubs-list")' in load
    assert "renderMySubsTabs()" in load
    assert "renderMySubsList()" in load
    assert "加载失败:" in load
    assert "重试" in load
    assert "loadSettingsSubscriptions(routeRenderSeq)" in load
```

Add a settings-tab contract:

```python
def test_subscription_management_is_the_default_settings_tab():
    src = APP_JS.read_text()
    render = _fn_body("renderSettings")
    switch = _fn_body("switchSettingsTab")

    assert 'const SETTINGS_TABS = ["subs", "push", "bind", "llm", "account"]' in src
    assert 'data-tab="subs"' in render
    assert 'id="st-subs"' in render
    assert "settingsSubscriptionsPanelHtml()" in render
    assert 'switchSettingsTab(state.settingsTab || "subs")' in render
    assert 'setPageTitle("订阅与推送")' in render
    assert 'name = "subs"' in switch
```

Update existing contracts:

- `test_plaza_source_visibility_admin_and_pills`: check `ensurePlazaPlatformSelection()` in `renderSettings`, not deleted `renderMySubs`.
- `test_kol_image_settings_is_fourth_push_section_and_loads_independently`: expect `switchSettingsTab(state.settingsTab || "subs")`; require `loadSettingsSubscriptions(seq);` before `loadKolImageSettings(seq);` and neither call to be awaited.
- `test_kol_card_name_wraps_full_combination_title`: remove the `renderCombinations`/`hidePlatform` assertion; keep the wrapping assertions and assert `PLATFORM_LABELS[kol.platform]` remains in `kolCard`.
- `test_settings_tabs_use_tab_aria`: additionally assert all five `aria-controls`/tabpanel pairs exist.

- [ ] **Step 2: Run the focused panel tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_refresh_kols_view_covers_all_card_routes \
  tests/test_frontend_interactions.py::test_renderers_check_route_token_after_await \
  tests/test_frontend_interactions.py::test_settings_subscription_panel_reuses_mobile_badges_and_desktop_toolbar \
  tests/test_frontend_interactions.py::test_settings_subscription_loader_is_route_guarded_local_and_retryable \
  tests/test_frontend_interactions.py::test_subscription_management_is_the_default_settings_tab \
  tests/test_frontend_interactions.py::test_kol_image_settings_is_fourth_push_section_and_loads_independently \
  tests/test_frontend_interactions.py::test_settings_tabs_use_tab_aria
```

Expected: failures because the `subs` tab and loader do not exist.

- [ ] **Step 3: Extract the existing panel markup without changing its behavior**

Delete `renderMySubs(seq)` and replace it with a pure panel template:

```javascript
function settingsSubscriptionsPanelHtml() {
  const mobileFilter = isMobileTimelineFilter();
  return `
    <section class="section-panel${mobileFilter ? " home-panel" : ""}">
      <header class="section-head home-head">
        <div><h2 class="section-title">已订阅</h2></div>
      </header>
      <div class="toolbar" style="margin:12px 0 16px">
        <div class="${mobileFilter ? "icon-badge-bar mysubs-mobile-filters" : "platform-tabs"}" id="mysubs-tabs"></div>
        ${mobileFilter ? "" : `<button id="mysubs-fav-toggle" class="fav-toggle ${state.mysubsFavorite ? "fav-on" : ""}" onclick="toggleMySubsFav()">${STAR_SVG} 特别关注</button>`}
      </div>
      <div id="mysubs-list" class="kol-grid">${emptyState("加载中…")}</div>
    </section>`;
}
```

Keep `mysubsMobileFiltersHtml`, `renderMySubsTabs`, `switchMySubsPlatform`, `renderMySubsList`, and `toggleMySubsFav` as the single implementation used by the new tab.

- [ ] **Step 4: Add the route-owned local loader**

Add immediately before the existing filter helpers:

```javascript
async function loadSettingsSubscriptions(seq) {
  const target = $("#mysubs-list");
  if (!target) return;
  target.innerHTML = emptyState("加载中…");
  try {
    const subs = await api("/api/my/subscriptions");
    if (!routeStillActive(seq)) return;
    state.catalog = subs.map((k) => ({ ...k, subscribed: true }));
    renderMySubsTabs();
    renderMySubsList();
  } catch (err) {
    if (!routeStillActive(seq)) return;
    const current = $("#mysubs-list");
    if (!current) return;
    current.innerHTML = emptyState(
      "加载失败: " + err.message,
      `<div><button type="button" class="btn-ghost" onclick="loadSettingsSubscriptions(routeRenderSeq)">重试</button></div>`
    );
  }
}
```

Do not write `#main` from this loader. This is what keeps channel binding, AI, and account settings usable when subscriptions fail.

- [ ] **Step 5: Add the fifth settings tab and make it the default**

Change the tab list and title:

```javascript
const SETTINGS_TABS = ["subs", "push", "bind", "llm", "account"];
```

```javascript
setPageTitle("订阅与推送");
ensurePlazaPlatformSelection();
```

Insert the first tab/button and panel before the existing push tab/panel:

```javascript
<button type="button" class="settings-tab active" role="tab" id="tab-subs"
  aria-selected="true" aria-controls="st-subs" data-tab="subs"
  onclick="switchSettingsTab('subs')">订阅管理</button>
```

```javascript
<div id="st-subs" class="settings-tab-panel" role="tabpanel" aria-labelledby="tab-subs">
  ${settingsSubscriptionsPanelHtml()}
</div>
```

Remove the hardcoded active state from the push button, set its initial `aria-selected` to `false`, and preserve the existing push/bind/llm/account panel bodies unchanged. At the end of `renderSettings` use:

```javascript
switchSettingsTab(state.settingsTab || "subs");
toggleDnd();
loadSettingsSubscriptions(seq);
loadKolImageSettings(seq);
```

In `switchSettingsTab`, change only the invalid-name fallback:

```javascript
if (!SETTINGS_TABS.includes(name)) name = "subs";
```

Keep `state.settingsTab = name`; internal bind/unbind reloads must preserve the current settings tab.

- [ ] **Step 6: Make existing subscription mutations refresh the new surface**

Replace the obsolete branches in `refreshKolsView()`:

```javascript
async function refreshKolsView() {
  const seq = routeRenderSeq;
  if (isRoute("home")) await loadHomeKols(seq);
  else if (isRoute("settings")) await loadSettingsSubscriptions(seq);
  else if (isRoute("kol/")) await renderKolPage(Number(routePath().split("/")[1] || 0), seq);
  else if (isRoute("search")) doSearch(seq);
}
```

In `toggleFavorite` and `toggleSecondary`, replace the obsolete mysubs branch with:

```javascript
else if (isRoute("settings") && state.settingsTab === "subs") renderMySubsList();
```

The settings branch handles unsubscribe and failed subscription-type rollback by calling `loadSettingsSubscriptions(seq)`.

Delete `renderCombinations(seq)` entirely. Its removal also makes `kolCard(kol, opts)` speculative: simplify it to `kolCard(kol)`, always add the platform tag, and remove `opts`, `hidePlatform`, and their old test assertions. Do not delete combination detail rendering, fetchers, labels, platform icons, quote tags, or `/api/catalog?platform=combination`; only the standalone directory renderer and its one-use display option are dead.

Update user-visible admin copy from `推送设置 → AI 摘要` to `订阅与推送 → AI 摘要`. Leave the inner tab name “推送设置” unchanged.

- [ ] **Step 7: Increment static cache keys once and update the source contract**

At plan creation the current values are:

```html
<script src="/app.js?v=370"></script>
```

```javascript
const CACHE = "dav-shell-v239";
```

Advance them once to `app.js?v=371` and `dav-shell-v240`, and update `test_frontend_asset_urls_bust_browser_cache` to expect those exact values. Do not bump `style.css?v=261` because CSS is unchanged. If concurrent work has already advanced either integer before implementation starts, increment that then-current integer once and make the test match the resulting exact value.

- [ ] **Step 8: Run focused and full frontend tests**

Run:

```bash
node --check app/static/app.js
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py
```

Expected: JavaScript syntax check exits 0; all frontend interaction tests pass.

- [ ] **Step 9: Commit the working SPA merge**

Review staged paths before committing because these files may contain concurrent edits:

```bash
git diff -- app/static/app.js app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
git add app/static/app.js app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
git diff --cached --check
git commit -m "feat: 合并订阅与推送入口"
```

Expected: one commit containing only the reviewed SPA/test changes; no backend or mini-program file staged.

### Task 3: Update User-Facing Web Documentation

**Files:**
- Modify: `README.md:20-25,90-95,215-245,278-283`
- Modify: `DOCKERHUB.md:88-96,148-156`
- Modify: `docs/用户指南.md:27-64`

- [ ] **Step 1: Update README without rewriting bot or mini-program terminology**

Make these exact content changes:

- Rename the settings screenshot caption to `订阅与推送 · 订阅管理与推送配置`.
- Remove the stale standalone `mysubs.png` and `combinations.png` screenshot row; do not invent replacement screenshots.
- Where text directs web users to the former top-level page, write `订阅与推送` and include the inner tab where useful, for example `订阅与推送 → 渠道绑定`.
- Keep `/mysubs` bot-command descriptions as “我的订阅”; that command is not a web route.
- Do not change mini-program wording.

The resulting product workflow near the feature introduction must state:

```markdown
- **订阅广场**：发现并订阅大V、雪球组合及其他平台内容
- **订阅与推送**：在“订阅管理”维护已订项目，并配置推送规则、接收渠道、AI 摘要和账号
```

- [ ] **Step 2: Update Docker Hub usage and FAQ copy**

Replace the separate web bullets with one:

```markdown
- **订阅与推送**：管理已订阅的大V和雪球组合，标星特别关注，并配置 Telegram / 飞书 / 企业微信 / Bark / 浏览器通知
```

Change FAQ directions to `订阅与推送 → 渠道绑定` or `订阅与推送 → 推送设置` as appropriate. Keep the `/mysubs` command row unchanged.

- [ ] **Step 3: Split web and mini-program directions in the user guide**

Under “网页/小程序使用”, make the platform difference explicit:

```markdown
3. 网页打开“订阅与推送”：
   - “订阅管理”维护已订阅的大V和雪球组合；发现新内容仍去“订阅广场”；
   - “渠道绑定”查看 Telegram / 飞书等渠道状态并完成绑定；
   - “推送设置”配置总开关、免打扰、关键词和动态图片。
4. 小程序继续使用现有“我的订阅”和“推送设置”页面，本次网页合并不改变小程序操作。
```

Update the web browser notification path to `订阅与推送 → 渠道绑定`. Keep bot command names and mini-program page names unchanged.

- [ ] **Step 4: Verify terminology**

Run:

```bash
rg -n "组合订阅|我的订阅|推送设置|订阅与推送" \
  README.md DOCKERHUB.md docs/用户指南.md
```

Expected:

- No text presents “组合订阅” or “我的订阅” as standalone web navigation.
- `/mysubs` remains documented as a bot command.
- “推送设置” remains only as an inner tab or mini-program page.
- Web directions consistently start at “订阅与推送”.

- [ ] **Step 5: Commit documentation separately**

```bash
git add README.md DOCKERHUB.md docs/用户指南.md
git diff --cached --check
git commit -m "docs: 更新订阅与推送入口说明"
```

Expected: one documentation-only commit.

### Task 4: Bounded Browser And Full Regression Verification

**Files:**
- Verify: `app/static/app.js`
- Verify: `app/static/style.css`
- Verify: `app/static/index.html`
- Verify: `tests/test_frontend_interactions.py`
- Create temporarily, do not commit: `work/ui-validation/subscription-push/`

- [ ] **Step 1: Start an isolated local UI server**

Use a temporary database and a dedicated port:

```bash
tmpdir=$(mktemp -d)
DAV_UI_ONLY=1 ALERTS_ENABLED=false WEB_ADMIN_PASSWORD=ui-test \
  DB_PATH="$tmpdir/vpush.db" \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Run it in a managed background terminal. Expected: `http://127.0.0.1:8765/healthz` returns 200. Stop the server and remove `$tmpdir` after validation.

- [ ] **Step 2: Run one Playwright pass for navigation, legacy routes, desktop/mobile, and themes**

Create `work/ui-validation/subscription-push/check.py` with:

```python
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = Path("work/ui-validation/subscription-push")
OUT.mkdir(parents=True, exist_ok=True)
SUBS = [
    {"id": 1, "name": "唐朝", "platform": "xueqiu", "external_id": "123",
     "enabled": 1, "category_name": "价值投资", "subscribe_type": "both",
     "favorite": 1, "secondary": 0, "hide_images": 0, "avatar_url": ""},
    {"id": 2, "name": "伯言-A股", "platform": "combination", "external_id": "ZH3623878",
     "enabled": 1, "category_name": "组合", "subscribe_type": "post",
     "favorite": 0, "secondary": 0, "hide_images": 0, "avatar_url": ""},
]

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    token = context.request.post(
        f"{BASE}/api/auth/login",
        data={"username": "admin", "password": "ui-test"},
    ).json()["token"]
    context.add_init_script(
        f"localStorage.setItem('dav_token', {json.dumps(token)});"
    )
    page = context.new_page()
    page.route("**/api/my/subscriptions", lambda route: route.fulfill(json=SUBS))
    page.goto(BASE)

    for theme in ("light", "dark"):
        page.evaluate("theme => localStorage.setItem('theme', theme)", theme)
        page.goto(f"{BASE}/settings")
        page.get_by_role("tab", name="订阅管理").wait_for()
        page.get_by_text("唐朝", exact=True).first.wait_for()
        assert page.get_by_role("tab", name="订阅管理").get_attribute("aria-selected") == "true"
        assert page.locator('.nav-item[data-route="settings"] .nav-label').inner_text() == "订阅与推送"
        assert page.locator('.nav-item[data-route="mysubs"]').count() == 0
        assert page.locator('.nav-item[data-route="combinations"]').count() == 0
        assert page.get_by_text("唐朝", exact=True).count() >= 1
        assert page.get_by_text("伯言-A股", exact=True).count() >= 1
        assert page.evaluate("document.documentElement.scrollWidth === document.documentElement.clientWidth")
        page.screenshot(path=OUT / f"desktop-{theme}.png", full_page=True)

    page.set_viewport_size({"width": 390, "height": 844})
    for theme in ("light", "dark"):
        page.evaluate("theme => localStorage.setItem('theme', theme)", theme)
        page.goto(f"{BASE}/settings")
        page.get_by_text("唐朝", exact=True).first.wait_for()
        assert page.locator(".bnav-item").count() == 4  # admin adds “更多” to the three user tabs
        assert page.locator('.bnav-item[data-route="settings"] .bnav-label').inner_text() == "订阅与推送"
        assert page.locator("#mysubs-tabs.icon-badge-bar").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth === document.documentElement.clientWidth")
        page.screenshot(path=OUT / f"mobile-{theme}.png", full_page=True)

    page.goto(f"{BASE}/mysubs")
    page.wait_for_url(f"{BASE}/settings")
    assert page.get_by_role("tab", name="订阅管理").get_attribute("aria-selected") == "true"

    page.goto(f"{BASE}/combinations")
    page.wait_for_url(f"{BASE}/home")
    assert page.locator('[data-platform="combination"].selected').count() >= 1
    browser.close()
```

Run:

```bash
.venv/bin/python work/ui-validation/subscription-push/check.py
```

Expected: exit 0 and four screenshots. If Playwright cannot launch Chrome, record that limitation and perform the same routes manually; do not claim screenshot validation.

- [ ] **Step 3: Review screenshots once and fix only demonstrated defects**

Check all screenshots together for:

- “订阅管理” is the first visible and selected settings tab.
- Desktop tabs remain one row; mobile tabs scroll horizontally without clipping the active tab.
- Mobile bottom navigation contains the three equal-width user items; the admin validation account adds the existing fourth “更多” item, and the full “订阅与推送” label still fits.
- Mobile platform controls remain one equal-width icon badge row with hidden text labels.
- Subscription names, long combination names, buttons, and platform metadata do not overlap.
- Light and dark themes preserve readable borders, text, and Duty Blue selection.

If a real defect appears, make the smallest `app/static/style.css` fix, increment `style.css?v=261` once, update the asset-version test, rerun Task 2 tests, and capture one confirmation pass. Do not add speculative CSS.

- [ ] **Step 4: Run the Impeccable detector once**

```bash
node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json \
  app/static/app.js app/static/index.html app/static/style.css
```

Expected: no unresolved error-level finding relevant to the changed surface. Record warnings that are pre-existing or outside scope; do not refactor unrelated UI.

- [ ] **Step 5: Run final regression commands**

```bash
node --check app/static/app.js
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py
.venv/bin/python -m pytest -q
git diff --check
git status --short
```

Expected: syntax check exits 0, both pytest runs report zero failures, `git diff --check` is silent, no screenshot/temporary database/`.superpowers/` artifact is staged, and any pre-existing unrelated worktree changes are reported rather than altered.

- [ ] **Step 6: Produce the completion audit**

Map the confirmed spec to evidence:

- single “订阅与推送” navigation: source contract + desktop/mobile screenshot;
- default subscription management tab: source contract + screenshot;
- unified big-V/combination list: mocked browser data + existing API tests;
- old route compatibility: Playwright URL assertions;
- local subscription failure boundary: loader source contract;
- unchanged backend/mini-program: final diff path review;
- responsive/light/dark behavior: bounded screenshot pass;
- no regressions: full pytest output.

Do not create another feature commit unless Step 3 required a visual fix. Do not commit screenshots or the temporary Playwright script.
