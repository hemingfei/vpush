# Frontend Interaction Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the remaining news loading, thumbnail fallback, and modal-focus defects, and protect them with real-browser regression tests that run in CI.

**Architecture:** Keep the current classic-script application and existing CSS components. Add one Playwright-backed pytest file that serves the real static application and stubs network responses, then make the smallest production changes in `app.js`; module conversion and digest versioning remain in Plan B.

**Tech Stack:** Vanilla JavaScript, Python 3.12+, pytest 8.3.4, Playwright 1.62.0, system Google Chrome, GitHub Actions.

---

## Prerequisite

Start from the current worktree, not a clean `d554b7c` checkout. The unreleased P0/P1/P2 frontend patch must already be present in `app/static/app.js`, `app/static/style.css`, `app/static/index.html`, `app/static/sw.js`, `tests/test_frontend_interactions.py`, and `tests/test_frontend_pwa.py`. Task 5 runs `python3 scripts/bump_assets.py --bump-app`, so the untracked integer version tool `scripts/bump_assets.py` must also remain in the tree until Plan B replaces it.

## File Map

- Create `requirements-test.txt`: test-only Python dependencies; never copied into the production image.
- Create `tests/test_frontend_runtime.py`: localhost static server and real-browser behavior tests.
- Modify `.github/workflows/docker-publish.yml`: install test dependencies and make the browser tests part of the test job.
- Modify `app/static/app.js`: shared news skeleton, thumbnail rejection cleanup, lightbox focus management, and KOL modal focus reuse.
- Modify `app/static/index.html`: increment the existing `app.js` query version at the final release step.
- Modify `app/static/sw.js`: increment the existing shell cache at the final release step.
- Modify `tests/test_frontend_interactions.py`: remove assertions that require duplicate KOL focus code and update generated asset literals only through the existing version tool.
- Modify `tests/test_frontend_pwa.py`: update generated asset literals only through the existing version tool.

## Task 1: Add Browser Test Infrastructure and Failing Regressions

**Files:**
- Create: `requirements-test.txt`
- Create: `tests/test_frontend_runtime.py`

- [ ] **Step 1: Pin test-only dependencies**

Create `requirements-test.txt`:

```text
pytest==8.3.4
playwright==1.62.0
```

Do not add Playwright to `requirements.txt` or the Docker image.

- [ ] **Step 2: Add the localhost and Chrome fixtures**

Create `tests/test_frontend_runtime.py` with these fixtures and helpers:

```python
from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest
from playwright.sync_api import Page, Playwright, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="session")
def static_origin():
    handler = functools.partial(QuietHandler, directory=str(STATIC))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as instance:
        yield instance


@pytest.fixture
def page(playwright_instance: Playwright, static_origin: str):
    browser = playwright_instance.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.goto(static_origin, wait_until="domcontentloaded")
    yield page
    context.close()
    browser.close()


def install_json_fetch(page: Page, body: str) -> None:
    page.evaluate(
        """body => {
          window.fetch = async () => ({
            ok: true,
            status: 200,
            statusText: "OK",
            json: async () => JSON.parse(body),
          });
        }""",
        body,
    )
```

- [ ] **Step 3: Write the failing news skeleton test**

Append:

```python
def test_news_reset_keeps_full_skeleton_until_response(page: Page):
    page.evaluate(
        """() => {
          document.querySelector('#main').innerHTML = '<div id="news-list"></div><div id="news-load-sentinel"></div>';
          state.newsItems = [];
          state.newsSources = [];
          window.fetch = async () => ({
            ok: true,
            status: 200,
            statusText: 'OK',
            json: () => new Promise(resolve => { window.resolveNews = resolve; }),
          });
          window.pendingNews = loadFinancialNews(true, routeRenderSeq);
        }"""
    )
    cards = page.locator("#news-list .admin-sk-card")
    expect(cards).to_have_count(3)
    expect(cards.first).to_be_visible()
    assert cards.first.bounding_box()["height"] > 0
    page.evaluate(
        """() => window.resolveNews({
          items: [], next_offset: 0, has_more: false, view_started_at: null,
        })"""
    )
    page.evaluate("() => window.pendingNews")
    expect(page.locator("#news-list .admin-sk-card")).to_have_count(0)
```

- [ ] **Step 4: Write the failing thumbnail rejection test**

Append:

```python
def test_rejected_news_thumbnail_releases_layout_slot(page: Page):
    page.evaluate(
        """() => {
          document.querySelector('#main').innerHTML = '<div id="news-list"></div>';
          document.querySelector('#news-list').innerHTML = newsListItemHtml({
            id: 7,
            has_image: true,
            source_name: 'Test',
            published_at: '2026-09-04T00:00:00Z',
            title: 'Title',
            summary: 'Summary',
            is_new: false,
          });
          window.fetch = async () => { throw new Error('offline'); };
          const image = document.querySelector('[data-news-thumbnail="7"]');
          window.pendingImage = loadNewsImageBlob(7, 0, image, routeRenderSeq);
        }"""
    )
    page.evaluate("() => window.pendingImage")
    expect(page.locator('[data-news-thumbnail="7"]')).to_have_count(0)
```

- [ ] **Step 5: Write the failing lightbox focus test**

Append:

```python
def test_lightbox_traps_and_restores_focus(page: Page):
    page.evaluate(
        """() => {
          document.body.insertAdjacentHTML('beforeend', `
            <div class="post-images">
              <img id="lightbox-trigger" tabindex="0" src="/logo-mark.svg" alt="one">
              <img src="/logo.svg" alt="two">
            </div>`);
          const trigger = document.querySelector('#lightbox-trigger');
          trigger.focus();
          openLightbox(trigger);
        }"""
    )
    expect(page.locator(".lightbox-close")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(page.locator(".lightbox-next")).to_be_focused()
    page.keyboard.press("Tab")
    expect(page.locator(".lightbox-close")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator(".lightbox")).to_have_count(0, timeout=1_000)
    expect(page.locator("#lightbox-trigger")).to_be_focused()
```

- [ ] **Step 6: Write the failing KOL modal focus test**

Append:

```python
def test_kol_editor_uses_shared_focus_and_dirty_close_guard(page: Page):
    page.evaluate(
        """() => {
          const trigger = document.createElement('button');
          trigger.id = 'kol-edit-trigger';
          trigger.textContent = 'edit';
          document.body.appendChild(trigger);
          trigger.focus();
          window.fetch = async url => ({
            ok: true,
            status: 200,
            statusText: 'OK',
            json: async () => String(url).includes('/api/kols/')
              ? { id: 1, name: 'Test', category_id: null, is_private: false,
                  visible_users: [], platform: 'twitter', original_only: false }
              : [],
          });
        }"""
    )
    page.evaluate("() => adminEditKol(1)")
    expect(page.locator("#ek-name")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(page.locator("[data-close]")).to_be_focused()
    page.keyboard.press("Tab")
    expect(page.locator("#ek-name")).to_be_focused()
    page.locator("#ek-name").fill("Changed")
    page.evaluate("() => { window.confirm = () => false; }")
    page.keyboard.press("Escape")
    expect(page.locator(".modal-mask")).to_have_count(1)
    page.evaluate("() => { window.confirm = () => true; }")
    page.keyboard.press("Escape")
    expect(page.locator(".modal-mask")).to_have_count(0)
    expect(page.locator("#kol-edit-trigger")).to_be_focused()
```

- [ ] **Step 7: Run the new tests and verify the expected failures**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest tests/test_frontend_runtime.py -q
```

Expected: three failures and one pass. The skeleton count is `0`, the rejected thumbnail remains, and the lightbox does not focus/trap/restore. The KOL runtime test already passes and protects behavior while Task 3 removes its duplicate implementation.

- [ ] **Step 8: Keep the failing tests uncommitted until Task 3**

```bash
git status --short requirements-test.txt tests/test_frontend_runtime.py
```

Expected: both files are visible as Plan A changes. Do not create a red commit while the three regression tests still fail.

## Task 2: Fix News Loading and Thumbnail Failure

**Files:**
- Modify: `app/static/app.js` near `newsListItemHtml()`, `renderNewsListShell()`, `loadFinancialNews()`, and `loadNewsImageBlob()`
- Test: `tests/test_frontend_runtime.py`

- [ ] **Step 1: Add one shared skeleton renderer**

Immediately before `renderNewsListShell()`, add:

```javascript
function newsListSkeletonHtml() {
  const card = '<div class="admin-sk-card"><div class="admin-sk-line admin-sk-head"></div><div class="admin-sk-line"></div></div>';
  return `<div class="admin-skeleton" aria-hidden="true">${card.repeat(3)}</div>`;
}
```

- [ ] **Step 2: Reuse it in both loading paths**

In `renderNewsListShell()`, replace the hard-coded three-card block with:

```javascript
<div id="news-list" class="news-list">${newsListSkeletonHtml()}</div>
```

In the reset branch of `loadFinancialNews()`, replace the empty wrapper with:

```javascript
list.innerHTML = newsListSkeletonHtml();
```

- [ ] **Step 3: Remove rejected thumbnails safely**

Replace the empty catch in `loadNewsImageBlob()` with:

```javascript
  } catch {
    if (routeStillActive(seq) && image && document.body.contains(image)) image.remove();
  }
```

Do not flash an error and do not change the successful Blob/object-URL path.

- [ ] **Step 4: Run focused tests**

```bash
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_frontend_runtime.py::test_news_reset_keeps_full_skeleton_until_response \
  tests/test_frontend_runtime.py::test_rejected_news_thumbnail_releases_layout_slot \
  tests/test_frontend_interactions.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Keep the partial fix uncommitted**

```bash
git diff --check -- app/static/app.js tests/test_frontend_runtime.py
```

Expected: exit 0. Do not commit yet because the lightbox regression remains red until Task 3.

## Task 3: Unify Modal Focus Management

**Files:**
- Modify: `app/static/app.js` near `openLightbox()`, `closeLightbox()`, and `adminEditKol()`
- Modify: `tests/test_frontend_interactions.py`
- Test: `tests/test_frontend_runtime.py`

- [ ] **Step 1: Connect the lightbox to the shared helper**

After `document.body.appendChild(overlay)` in `openLightbox()`, use:

```javascript
  document.body.appendChild(overlay);
  document.body.classList.add("lightbox-open");
  document.addEventListener("keydown", lightboxKeyHandler);
  trapFocus(overlay, closeLightbox);
  overlay.querySelector(".lightbox-close")?.focus();
```

Let the shared trap own Escape. Change `lightboxKeyHandler()` to arrows only:

```javascript
function lightboxKeyHandler(e) {
  if (e.key === "ArrowLeft") lightboxStep(-1);
  else if (e.key === "ArrowRight") lightboxStep(1);
}
```

Make repeated close calls select only a live overlay:

```javascript
function closeLightbox() {
  const overlay = document.querySelector(".lightbox:not(.closing)");
  if (!overlay) return;
  overlay.classList.add("closing");
  const remove = () => overlay.remove();
  overlay.addEventListener("animationend", remove, { once: true });
  setTimeout(remove, 240);
  document.body.classList.remove("lightbox-open");
  document.removeEventListener("keydown", lightboxKeyHandler);
}
```

The `.closing` filter prevents a second Escape or a newly opened lightbox from targeting an overlay already waiting for animation removal.

- [ ] **Step 2: Replace KOL modal duplicate logic**

Delete the local `mask.addEventListener("keydown", ...)`, trigger capture, first-input focus, and local `MutationObserver` block from `adminEditKol()`.

After registering backdrop and Cancel handling, use:

```javascript
  mask.querySelector("[data-close]").addEventListener("click", tryClose);
  trapFocus(mask, tryClose);
  mask.querySelector("input, select, textarea, button")?.focus();
```

Do not bypass `tryClose`; it owns the unsaved-change confirmation.

- [ ] **Step 3: Tighten the source contract test**

In `test_trap_focus_utility_and_a11y_enhancements()`, retain the utility assertions and add call-site assertions without asserting duplicate implementation details:

```python
    assert "trapFocus(overlay, closeLightbox)" in src
    edit = _fn_body("adminEditKol")
    assert "trapFocus(mask, tryClose)" in edit
    assert 'if (e.key === "Tab")' not in edit
```

- [ ] **Step 4: Run focus tests**

```bash
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_frontend_runtime.py \
  tests/test_frontend_interactions.py -q
```

Expected: all browser and source-contract tests pass, including lightbox focus, KOL dirty-close behavior, news skeleton, and thumbnail rejection.

- [ ] **Step 5: Commit**

```bash
git add requirements-test.txt app/static/app.js \
  tests/test_frontend_runtime.py tests/test_frontend_interactions.py
git commit -m "fix(frontend): close remaining interaction regressions"
```

## Task 4: Put Browser Regressions in CI

**Files:**
- Modify: `.github/workflows/docker-publish.yml`

- [ ] **Step 1: Include test requirements in the pip cache key**

Change the setup-python cache input to:

```yaml
          cache-dependency-path: |
            requirements.txt
            requirements-test.txt
```

- [ ] **Step 2: Install test requirements and run the browser file**

Replace the existing backend test step with:

```yaml
      - name: 安装依赖并跑测试
        run: |
          pip install -r requirements.txt -r requirements-test.txt
          python -m pytest -q --maxfail=1
```

GitHub's Ubuntu runner supplies the `google-chrome` channel. Do not download a second Chromium build.

- [ ] **Step 3: Run the same commands locally**

```bash
./.venv/bin/pip install -r requirements-test.txt
PYTHONPATH=. ./.venv/bin/pytest tests/test_frontend_runtime.py -q
```

Expected: four browser tests pass.

- [ ] **Step 4: Validate workflow syntax structurally**

```bash
python3 - <<'PY'
from pathlib import Path
text = Path('.github/workflows/docker-publish.yml').read_text()
assert 'requirements-test.txt' in text
assert 'python -m pytest -q --maxfail=1' in text
assert 'playwright install' not in text
PY
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/docker-publish.yml requirements-test.txt
git commit -m "ci: run frontend browser regressions"
```

## Task 5: Version, Verify, and Prepare Plan A for Release

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/sw.js`
- Modify: `tests/test_frontend_interactions.py`
- Modify: `tests/test_frontend_pwa.py`

- [ ] **Step 1: Increment only the application asset version**

```bash
python3 scripts/bump_assets.py --bump-app
```

Expected: `app.js` and `dav-shell` each increment once; CSS remains unchanged. This command is temporary and will be replaced in Plan B.

- [ ] **Step 2: Run static checks**

```bash
node --check app/static/app.js
node --check app/static/sw.js
python3 scripts/bump_assets.py --check
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 3: Run focused frontend tests**

```bash
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_frontend_runtime.py \
  tests/test_frontend_interactions.py \
  tests/test_frontend_pwa.py \
  tests/test_frontend_xss.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run the complete suite**

```bash
PYTHONPATH=. ./.venv/bin/pytest
```

Expected: all tests pass; no failure or unexpected skip in `tests/test_frontend_runtime.py`.

- [ ] **Step 5: Run the frontend detector**

```bash
set +e
node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json \
  app/static/index.html app/static/style.css app/static/app.js > /tmp/vpush-detect.json
detector_rc=$?
set -e
test "$detector_rc" -eq 0 -o "$detector_rc" -eq 2
python3 - <<'PY'
import json
from pathlib import Path
findings = json.loads(Path('/tmp/vpush-detect.json').read_text())
assert not [item for item in findings if item['severity'] == 'warning']
PY
```

Expected: the detector may exit 2 for existing advisories, but the JSON contains zero `warning` findings. Design-token `advisory` findings are outside this plan.

- [ ] **Step 6: Manually verify the four flows in desktop Chrome**

Run the application locally and verify:

1. News initial load and filter/search reload retain visible skeleton cards.
2. A blocked news image leaves no blank thumbnail column.
3. Lightbox Tab/Shift+Tab/Escape and focus restoration work.
4. KOL dirty edit rejects the first Escape when confirmation is cancelled and restores focus after confirmed close.

Expected: behavior matches the browser tests with no console error.

- [ ] **Step 7: Commit the generated versions**

```bash
git add app/static/index.html app/static/sw.js \
  tests/test_frontend_interactions.py tests/test_frontend_pwa.py
git commit -m "chore(frontend): bump assets for interaction fixes"
```

- [ ] **Step 8: Review the final Plan A diff**

```bash
git status --short
git diff HEAD~3 --stat
git log -3 --oneline
```

Expected: only the files listed in this plan are part of the three Plan A commits. Preserve unrelated pre-existing worktree changes.
