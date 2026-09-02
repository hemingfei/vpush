# Plaza Favorite Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the low-frequency “特别关注” scope from the plaza toolbar into the existing filter panel without changing filtering behavior or the mobile seven-badge layout.

**Architecture:** Keep the current `state.homeFavorite` client-side filter and API behavior. Reuse the existing filter panel and native `.switch` control, with one shared renderer used by desktop and mobile; desktop keeps “已订阅” in the toolbar while mobile keeps it inside the panel.

**Tech Stack:** Vanilla JavaScript, existing CSS tokens/components, pytest static frontend contracts, Playwright/browser screenshots.

---

### Task 1: Lock the Plaza Filter Structure

**Files:**
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Replace the current broad plaza-filter assertions with a failing layout contract**

Add assertions to `test_plaza_keeps_subscribed_and_favorite_filters()` that require:

```python
panel = _fn_body("homeFilterPanelHtml")
toggle = _fn_body("homeFilterToggleHtml")
scope = _fn_body("homeScopeTogglesHtml")

assert "homeFilterPanelHtml(true)" in render
assert "homeFilterPanelHtml(false)" in render
assert "homeSubscribedToggleHtml()" in render
assert "homeFilterToggleHtml()" in render
assert "只看特别关注" in scope
assert "type=\"checkbox\"" in scope
assert "includeSubscribed" in scope
assert "homeScopeTogglesHtml(mobile)" in panel
assert 'aria-label="筛选"' in toggle
assert "homePanelHasFilters()" in toggle
assert "特别关注" not in toggle
```

Also require `homePanelHasFilters()` to include desktop panel filters and mobile-only controls:

```python
panel_state = _fn_body("homePanelHasFilters")
assert "state.homeCategory || state.homeFavorite" in panel_state
assert "isMobileTimelineFilter()" in panel_state
assert "state.homeQ || state.homeSubscribed" in panel_state
```

Keep the existing assertions that `homeFilteredKols()` filters by `state.homeSubscribed` and `state.homeFavorite`, and that `homeResetFilters()` clears both.

- [ ] **Step 2: Tighten the mobile seven-badge contract**

In `test_mobile_mysubs_filter_is_seven_equal_44px_targets()`, replace the old `homeScopeTogglesHtml` visibility assertion with:

```python
assert "homeFilterToggleHtml()" in _fn_body("renderHome")
assert "repeat(7, minmax(0, 1fr))" in css
assert ".icon-badge-bar > .home-filter-toggle" in css
```

- [ ] **Step 3: Run the focused tests and confirm RED**

Run:

```bash
../../.venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py::test_plaza_keeps_subscribed_and_favorite_filters \
  tests/test_frontend_interactions.py::test_mobile_mysubs_filter_is_seven_equal_44px_targets
```

Expected: failures because `homeFilterPanelHtml`, `homeFilterToggleHtml`, and `homePanelHasFilters` do not exist yet.

- [ ] **Step 4: Commit the failing contract**

```bash
git add tests/test_frontend_interactions.py
git commit -m "test: 固化订阅广场筛选层级"
```

### Task 2: Move Favorite Into the Existing Filter Panel

**Files:**
- Modify: `app/static/app.js:1956-2096`
- Modify: `app/static/style.css:953-966,2262-2282,2320-2337`

- [ ] **Step 1: Add the minimum shared render helpers**

Replace the combined toolbar pills with four small helpers:

```javascript
function homePanelHasFilters() {
  return !!(state.homeCategory || state.homeFavorite
    || (isMobileTimelineFilter() && (state.homeQ || state.homeSubscribed)));
}

function homeSubscribedToggleHtml() {
  return `<button type="button" id="home-sub-toggle" class="fav-toggle ${state.homeSubscribed ? "fav-on" : ""}" aria-pressed="${state.homeSubscribed}" onclick="toggleHomeSubscribed()">已订阅</button>`;
}

function homeScopeTogglesHtml(includeSubscribed) {
  return `<div class="home-scope-filters">
    ${includeSubscribed ? `<label class="switch home-scope-switch"><input id="home-sub-toggle" type="checkbox" ${state.homeSubscribed ? "checked" : ""} onchange="toggleHomeSubscribed()"><span class="track"></span><span>只看已订阅</span></label>` : ""}
    <label class="switch home-scope-switch"><input id="home-fav-toggle" type="checkbox" ${state.homeFavorite ? "checked" : ""} onchange="toggleHomeFavorite()"><span class="track"></span><span>只看特别关注</span></label>
  </div>`;
}

function homeFilterToggleHtml() {
  return `<button type="button" id="home-filter-toggle" class="fav-toggle home-filter-toggle ${homePanelHasFilters() ? "has-filter" : ""}" aria-label="筛选" title="筛选" aria-expanded="false" aria-controls="home-filter-panel" onclick="homeToggleFilter()">${FILTER_ICON}</button>`;
}

function homeFilterPanelHtml(mobile) {
  return `<div class="home-filter-content" id="home-filter-panel" hidden>
    ${mobile ? `<div class="search-bar home-search-bar">${SEARCH_ICON}<input id="home-search" placeholder="搜索昵称或 ID" value="${escapeHtml(state.homeQ || "")}" oninput="homeSearch(this.value)"></div>` : ""}
    <div class="home-cats" id="home-cats"></div>
    ${homeScopeTogglesHtml(mobile)}
    <div class="home-filter-actions"><button class="btn-ghost" onclick="homeResetFilters()">清除筛选</button></div>
  </div>`;
}
```

Keep `toggleHomeSubscribed()` and `toggleHomeFavorite()` as the only state mutators; update their DOM synchronization to set `checked` for checkbox controls and `aria-pressed` for the desktop subscribed button.

- [ ] **Step 2: Use the shared panel on desktop and mobile**

In `renderHome()`:

- Mobile badge bar ends with `${homeFilterToggleHtml()}` and is followed by `${homeFilterPanelHtml(true)}`.
- Desktop toolbar contains search, `#platform-tabs`, `${homeSubscribedToggleHtml()}`, and `${homeFilterToggleHtml()}`.
- Desktop toolbar is followed by `${homeFilterPanelHtml(false)}`.
- Remove the always-visible desktop `.home-cats` row and the standalone “特别关注” toolbar pill.

In `renderHomeList()`, change the active filter marker to:

```javascript
$("#home-filter-toggle")?.classList.toggle("has-filter", homePanelHasFilters());
```

- [ ] **Step 3: Style the reused panel and switch without new visual tokens**

Add base rules using existing variables:

```css
.home-filter-content {
  display: grid;
  gap: 12px;
  margin-top: 12px;
  padding: 14px;
  border: var(--border-default);
  border-radius: var(--radius-control);
  background: var(--color-bg-muted);
}
.home-filter-content[hidden] { display: none; }
.home-filter-content .home-cats { margin-top: 0; }
.home-scope-filters { display: grid; gap: 8px; }
.home-scope-switch { min-height: 44px; }
.home-filter-toggle { width: 44px; padding: 0; justify-content: center; flex: 0 0 44px; }
.home-filter-toggle .funnel-icon { width: 18px; height: 18px; }
```

Extend the existing mobile icon-badge selector from `.icon-badge-bar > .fav-toggle` to also include `.icon-badge-bar > .home-filter-toggle`. Do not change `repeat(7, minmax(0, 1fr))` or the 44px target.

- [ ] **Step 4: Run GREEN checks**

```bash
node --check app/static/app.js
../../.venv/bin/python -m pytest -q tests/test_frontend_interactions.py
node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json app/static/app.js app/static/style.css
```

Expected: JavaScript syntax valid, frontend interaction tests pass, detector has no unresolved blocker.

- [ ] **Step 5: Commit the implementation**

```bash
git add app/static/app.js app/static/style.css tests/test_frontend_interactions.py
git commit -m "fix: 收纳特别关注筛选"
```

### Task 3: Verify Responsive Behavior

**Files:**
- Verify: `app/static/app.js`
- Verify: `app/static/style.css`

- [ ] **Step 1: Start the existing app and open the plaza**

Use the repository's normal development command and an unused local port. Sign in with the existing development account; do not add test-only authentication code.

- [ ] **Step 2: Capture one desktop and one mobile screenshot**

Check at approximately `1440x900` and `390x844`:

- Desktop toolbar has one-line search, platforms, “已订阅”, and icon-only filter control.
- Opening the panel reveals categories and “只看特别关注”.
- Mobile remains exactly seven equal badges with no visible “特别关注” text.
- Enabling favorite immediately filters results and activates the filter button.
- Card star buttons remain unchanged; no overlap occurs in light or dark theme.

- [ ] **Step 3: Run the focused regression suite**

```bash
../../.venv/bin/python -m pytest -q \
  tests/test_frontend_interactions.py \
  tests/test_frontend_pwa.py
```

Expected: all tests pass.

- [ ] **Step 4: Inspect the final diff**

```bash
git diff HEAD~2 --check
git diff HEAD~2 -- app/static/app.js app/static/style.css tests/test_frontend_interactions.py
```

Expected: only the approved plaza filter hierarchy, styles, and tests changed. Do not publish or deploy without explicit approval.
