# Frontend Modules and Asset Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the first production ES-module boundaries and replace manual cache counters with deterministic content-aware asset synchronization.

**Architecture:** Keep native browser modules and the existing network-first service worker; add no bundler or production dependency. Convert `app.js` into the module entry with an explicit compatibility registry for current inline handlers, extract two core modules and the financial-news view, then derive one SHA-256 build digest from the complete CSS/JavaScript asset graph.

**Tech Stack:** Native ES Modules, Vanilla JavaScript, Python standard library (`hashlib`, `pathlib`, `tempfile`, `os.replace`), pytest, Playwright, Service Worker Cache API.

---

## Prerequisite

Complete and release `docs/superpowers/plans/2026-09-04-frontend-interaction-correctness.md` first. Start this plan from that verified commit, not from the pre-repair worktree.

## File Map

- Create `app/static/core/html.js`: escaping and image-proxy helpers.
- Create `app/static/core/dialog.js`: shared focus trap.
- Create `app/static/views/news.js`: financial-news view factory and handlers.
- Modify `app/static/app.js`: ES-module imports, explicit inline-handler registry, dependency injection for the news view, and removal of moved code.
- Modify `app/static/index.html`: module entry and aggregate digest references.
- Modify `app/static/sw.js`: digest cache name and complete module shell.
- Rewrite `scripts/bump_assets.py`: deterministic digest calculation, validation, and synchronization.
- Create `tests/test_asset_versions.py`: byte-change, synchronization, validation, and module-shell tests.
- Modify `tests/test_frontend_interactions.py`: module and inline-handler contracts without fixed version strings; migrate helper source assertions as code moves.
- Modify `tests/test_frontend_pwa.py`: aggregate digest and full shell contracts without fixed version strings.
- Modify `tests/test_frontend_runtime.py`: convert direct internal calls to public route/click behavior before module mode, then add online/offline checks.
- Modify `.github/workflows/docker-publish.yml`: syntax-check every static JavaScript file and run asset consistency before pytest.

## Task 1: Replace Counters with a Deterministic Asset Digest

**Files:**
- Rewrite: `scripts/bump_assets.py`
- Create: `tests/test_asset_versions.py`
- Modify: `tests/test_frontend_interactions.py`
- Modify: `tests/test_frontend_pwa.py`

- [ ] **Step 1: Write the failing digest tests**

Create `tests/test_asset_versions.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import bump_assets


def make_tree(tmp_path: Path) -> Path:
    static = tmp_path / "app" / "static"
    (static / "core").mkdir(parents=True)
    (static / "views").mkdir()
    (static / "style.css").write_text("body { color: black; }\n")
    (static / "app.js").write_text("import './core/html.js';\n")
    (static / "core" / "html.js").write_text("export const x = 1;\n")
    (static / "views" / "news.js").write_text("export const y = 2;\n")
    (static / "index.html").write_text(
        '<link rel="stylesheet" href="/style.css?v=old">\n'
        '<script type="module" src="/app.js?v=old"></script>\n'
    )
    (static / "sw.js").write_text(
        'const CACHE = "dav-shell-old";\n'
        'const SHELL = [\n'
        '  "/",\n'
        '  // asset-modules:start\n'
        '  // asset-modules:end\n'
        '];\n'
    )
    return tmp_path


def test_sync_then_check(tmp_path: Path):
    root = make_tree(tmp_path)
    digest = bump_assets.sync_assets(root)
    assert len(digest) == 12
    assert bump_assets.check_consistency(root)


def test_sync_is_deterministic(tmp_path: Path):
    root = make_tree(tmp_path)
    first = bump_assets.sync_assets(root)
    static = root / "app" / "static"
    before = {path: path.read_bytes() for path in (static / "index.html", static / "sw.js")}
    second = bump_assets.sync_assets(root)
    assert second == first
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize(
    "relative",
    [
        "app/static/style.css",
        "app/static/app.js",
        "app/static/core/html.js",
        "app/static/views/news.js",
    ],
)
def test_changed_asset_fails_check(tmp_path: Path, relative: str):
    root = make_tree(tmp_path)
    bump_assets.sync_assets(root)
    path = root / relative
    path.write_bytes(path.read_bytes() + b"\n")
    assert not bump_assets.check_consistency(root)


@pytest.mark.parametrize(
    ("target_name", "old", "new", "message"),
    [
        ("index.html", '<link rel="stylesheet" href="/style.css?v=old">\n', "", "style.css reference"),
        ("index.html", '<script type="module" src="/app.js?v=old"></script>\n',
         '<script type="module" src="/app.js?v=old"></script>\n' * 2, "app.js reference"),
        ("sw.js", 'const CACHE = "dav-shell-old";\n', "", "service-worker cache"),
        ("sw.js", 'const CACHE = "dav-shell-old";\n',
         'const CACHE = "dav-shell-old";\n' * 2, "service-worker cache"),
    ],
)
def test_invalid_reference_does_not_write(
    tmp_path: Path, target_name: str, old: str, new: str, message: str
):
    root = make_tree(tmp_path)
    static = root / "app" / "static"
    target = static / target_name
    target.write_text(target.read_text().replace(old, new))
    before = {path: path.read_bytes() for path in (static / "index.html", static / "sw.js")}
    with pytest.raises(ValueError, match=message):
        bump_assets.sync_assets(root)
    assert {path: path.read_bytes() for path in before} == before


def test_replace_failure_rolls_back_both_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = make_tree(tmp_path)
    static = root / "app" / "static"
    targets = (static / "index.html", static / "sw.js")
    before = {path: path.read_bytes() for path in targets}
    real_replace = bump_assets.os.replace
    calls = 0

    def fail_second_replace(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second replace failure")
        real_replace(source, target)

    monkeypatch.setattr(bump_assets.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="simulated second replace failure"):
        bump_assets.sync_assets(root)
    assert {path: path.read_bytes() for path in targets} == before


def test_sync_populates_complete_module_shell(tmp_path: Path):
    root = make_tree(tmp_path)
    bump_assets.sync_assets(root)
    sw = (root / "app" / "static" / "sw.js").read_text()
    assert '"/core/html.js"' in sw
    assert '"/views/news.js"' in sw
```

- [ ] **Step 2: Run the tests and verify failure**

```bash
PYTHONPATH=. ./.venv/bin/pytest tests/test_asset_versions.py -q
```

Expected: import or attribute failures because `asset_digest()`, `sync_assets()`, and root-aware `check_consistency()` do not exist.

- [ ] **Step 3: Implement the asset graph and digest**

Rewrite `scripts/bump_assets.py` around these functions:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path("app/static")
DIGEST_LEN = 12


def asset_paths(root: Path = ROOT) -> list[Path]:
    static = root / STATIC
    paths = [static / "style.css", static / "app.js"]
    paths += sorted((static / "core").glob("**/*.js")) if (static / "core").exists() else []
    paths += sorted((static / "views").glob("**/*.js")) if (static / "views").exists() else []
    missing = [path for path in paths[:2] if not path.is_file()]
    if missing:
        raise ValueError("missing required assets: " + ", ".join(map(str, missing)))
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def asset_digest(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in asset_paths(root):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(relative + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()[:DIGEST_LEN]


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one reference, found {count}")
    return updated


def module_urls(root: Path = ROOT) -> list[str]:
    static = root / STATIC
    return [
        "/" + path.relative_to(static).as_posix()
        for path in asset_paths(root)
        if path.suffix == ".js" and path.name != "app.js"
    ]


def rendered_targets(root: Path = ROOT) -> dict[Path, str]:
    static = root / STATIC
    digest = asset_digest(root)
    index = (static / "index.html").read_text("utf-8")
    sw = (static / "sw.js").read_text("utf-8")
    index = replace_once(index, r'href="/style\.css\?v=[^"]+"',
                         f'href="/style.css?v={digest}"', "style.css reference")
    index = replace_once(index, r'src="/app\.js\?v=[^"]+"',
                         f'src="/app.js?v={digest}"', "app.js reference")
    sw = replace_once(sw, r'const CACHE = "dav-shell-[^"]+";',
                      f'const CACHE = "dav-shell-{digest}";', "service-worker cache")
    lines = "\n".join(f'  "{url}",' for url in module_urls(root))
    block = f"  // asset-modules:start\n{lines}\n  // asset-modules:end"
    sw = replace_once(sw, r"  // asset-modules:start[\s\S]*?  // asset-modules:end",
                      block, "service-worker module block")
    return {static / "index.html": index, static / "sw.js": sw}


def check_consistency(root: Path = ROOT) -> bool:
    try:
        expected = rendered_targets(root)
    except ValueError as error:
        print(error, file=sys.stderr)
        return False
    stale = [path for path, text in expected.items() if path.read_text("utf-8") != text]
    if stale:
        print("stale asset digest: " + ", ".join(map(str, stale)), file=sys.stderr)
        return False
    print(f"asset digest ok: {asset_digest(root)}")
    return True


def atomic_write(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sync_assets(root: Path = ROOT) -> str:
    rendered = rendered_targets(root)
    originals = {target: target.read_bytes() for target in rendered}
    temporary: list[tuple[Path, Path]] = []
    replaced: list[Path] = []
    try:
        for target, text in rendered.items():
            fd, name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.append((Path(name), target))
        try:
            for source, target in temporary:
                os.replace(source, target)
                replaced.append(target)
        except OSError:
            for target in replaced:
                atomic_write(target, originals[target])
            raise
        return asset_digest(root)
    finally:
        for source, _ in temporary:
            source.unlink(missing_ok=True)
```

All references are validated and both temporary files are durable before the first replacement. Cross-file replacement is not a filesystem transaction, so the error path restores every already-replaced target and re-raises; the failure-injection test enforces byte-identical rollback.

Add this CLI and keep the existing `if __name__ == "__main__": main()` entry:

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize content-derived frontend asset versions")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    if args.sync:
        print(f"asset digest synced: {sync_assets()}")
        return
    raise SystemExit(0 if check_consistency() else 1)


if __name__ == "__main__":
    main()
```

Do not retain `--bump-app`, `--bump-css`, or `--bump-all`.

- [ ] **Step 4: Add module markers to the production service worker**

In `app/static/sw.js`, after `"/app.js",` add:

```javascript
  // asset-modules:start
  // asset-modules:end
```

The first production `--sync` call will fill this block after modules exist.

- [ ] **Step 5: Remove fixed-version coupling from existing tests**

In both frontend test files, import the digest helpers and define the repo root next to the existing path constants:

```python
from pathlib import Path
from scripts.bump_assets import asset_digest, module_urls

ROOT = Path(__file__).resolve().parents[1]
```

`tests/test_frontend_interactions.py` already imports `Path`; add only the bump_assets import and `ROOT`. `tests/test_frontend_pwa.py` already imports `Path` too.

Replace assertions for numeric `style.css?v=...`, `app.js?v=...`, and `dav-shell-v...` with:

```python
digest = asset_digest(ROOT)
assert f'href="/style.css?v={digest}"' in html
assert f'src="/app.js?v={digest}"' in html
assert f'const CACHE = "dav-shell-{digest}";' in sw
```

In `tests/test_frontend_pwa.py`, also assert the current module shell:

```python
for url in module_urls(ROOT):
    assert f'"{url}"' in sw
```

Delete fixed integer asset literals from these assertions. The synchronization script must never edit test source.

- [ ] **Step 6: Synchronize and run all asset-focused tests**

```bash
python3 scripts/bump_assets.py --sync
python3 scripts/bump_assets.py --check
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_asset_versions.py \
  tests/test_frontend_interactions.py \
  tests/test_frontend_pwa.py -q
```

Expected: all selected tests pass and `--check` prints one 12-character digest.

- [ ] **Step 7: Commit**

```bash
git add scripts/bump_assets.py tests/test_asset_versions.py \
  tests/test_frontend_interactions.py tests/test_frontend_pwa.py \
  app/static/index.html app/static/sw.js
git commit -m "build(frontend): derive versions from asset content"
```

## Task 2: Convert the Entry to an ES Module Safely

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `tests/test_frontend_interactions.py`
- Modify: `tests/test_frontend_runtime.py`
- Modify: `.github/workflows/docker-publish.yml`

- [ ] **Step 1: Add failing module and handler-contract tests**

In `tests/test_frontend_interactions.py`, add:

```python
EVENT_ATTRIBUTE_RE = re.compile(
    r'\bon(?:click|change|input|keydown|focus|error|load|submit)="(.*?)"'
    r'(?=\$\{|\s+[A-Za-z_:][-A-Za-z0-9_:.]*=|[>`])',
    re.DOTALL,
)
INLINE_CALL_RE = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(")
INLINE_MEMBER_RE = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\.")
INLINE_DYNAMIC_CALL_RE = re.compile(r"\$\{[A-Za-z_$][\w$]*\}\s*\(")
INLINE_BUILTINS = {
    "clearTimeout", "confirm", "decodeURIComponent", "encodeURIComponent",
    "if", "setTimeout",
}
INLINE_SAFE_MEMBER_ROOTS = {"document", "event", "this", "window"}
INDEX_HTML = APP_JS.with_name("index.html")


def _event_attribute_source(source: str) -> str:
    return "\n".join(EVENT_ATTRIBUTE_RE.findall(source))


def _inline_handler_calls(source: str) -> set[str]:
    attributes = [re.sub(r"\$\{.*?\}", "", item) for item in EVENT_ATTRIBUTE_RE.findall(source)]
    return {
        name
        for item in attributes
        for name in INLINE_CALL_RE.findall(item)
        if name not in INLINE_BUILTINS
    }


def _inline_handler_registry(source: str) -> set[str]:
    match = re.search(r"const INLINE_HANDLERS = \{(.*?)^\};", source, re.MULTILINE | re.DOTALL)
    assert match, "INLINE_HANDLERS registry missing"
    return set(re.findall(r"^\s*([A-Za-z_$][\w$]*)\s*,?\s*$", match.group(1), re.MULTILINE))


def test_app_uses_native_module_entry():
    html = INDEX_HTML.read_text()
    assert re.search(r'<script type="module" src="/app\.js\?v=[0-9a-f]{12}"></script>', html)


def test_inline_handlers_have_exact_explicit_exports():
    src = APP_JS.read_text()
    required = _inline_handler_calls(INDEX_HTML.read_text() + "\n" + src)
    exported = _inline_handler_registry(src)
    assert exported == required
    assert "window.VPush" not in src


def test_inline_handlers_do_not_read_module_lexicals():
    attrs = _event_attribute_source(INDEX_HTML.read_text() + "\n" + APP_JS.read_text())
    assert not INLINE_DYNAMIC_CALL_RE.search(attrs)
    runtime_attrs = re.sub(r"\$\{.*?\}", "", attrs)
    roots = set(INLINE_MEMBER_RE.findall(runtime_attrs))
    assert roots <= INLINE_SAFE_MEMBER_ROOTS
    assert ".then(" not in runtime_attrs
    assert "routeRenderSeq" not in runtime_attrs
    assert "state." not in runtime_attrs
```

- [ ] **Step 2: Run and verify failure**

```bash
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_frontend_interactions.py::test_app_uses_native_module_entry \
  tests/test_frontend_interactions.py::test_inline_handlers_have_exact_explicit_exports \
  tests/test_frontend_interactions.py::test_inline_handlers_do_not_read_module_lexicals -q
```

Expected: all three fail against the classic script and `window.VPush` facade.

- [ ] **Step 3: Remove direct lexical reads from event attributes**

Replace every direct module-lexical read and dynamic function name in event attributes with these wrappers:

```javascript
function reloadTimelineRail() { return loadTimelineRail(routeRenderSeq); }
function reloadTimeline() { return loadTimeline(true, routeRenderSeq); }
function runSearch() { return doSearch(routeRenderSeq); }
function reloadKolImageSettings() { return loadKolImageSettings(routeRenderSeq); }
function selectNewsSource(value) {
  state.newsFilterSourceId = value;
  return loadFinancialNews(true, routeRenderSeq);
}
function queueNewsSearch(value) {
  state.newsQuery = value;
  clearTimeout(window._newsSearchTimer);
  window._newsSearchTimer = setTimeout(() => loadFinancialNews(true, routeRenderSeq), 250);
}
function updateAdminNewsQuery(value) { adminNewsState.q = value; renderAdminNews(); }
function updateAdminNewsStatus(value) { adminNewsState.status = value; renderAdminNews(); }
function updateAdminNewsArchived(checked) { adminNewsState.showArchived = checked; renderAdminNews(); }
function selectAdminCodeFilter(key) {
  saveCodesForm();
  _codesUi.filter = key;
  return loadAdminCodes(false);
}
function searchAdminCodes(value) { _codesUi.q = value; renderCodesList(); }
function clearAdminCodesResult() { _codesUi.result = null; return loadAdminCodes(); }
function retryImaGroupAcl() { return fetchAclCandidateUsers(true).then(() => renderImaGroupAcl()); }
function selectFeishuSource(button) {
  const group = button.dataset.group;
  return button.dataset.sourceTarget === "knowledge"
    ? selectImaDocumentGroup(group)
    : selectFeishuTimelineSource(group);
}
function selectPlatformTab(button) {
  const platform = button.dataset.platform;
  return button.dataset.platformTarget === "admin"
    ? switchAdminKolsPlatform(platform)
    : switchPlatform(platform);
}
```

Apply these exact template changes:

- `loadTimelineRail(routeRenderSeq)` to `reloadTimelineRail()`.
- Both `loadTimeline(true, routeRenderSeq)` uses to `reloadTimeline()`.
- Both `doSearch(routeRenderSeq)` uses to `runSearch()`. In `test_search_page_lists_only_unsubscribed_kols_without_query()`, change `assert render.count("doSearch(routeRenderSeq)") == 2` to `assert render.count("runSearch()") == 2`. Keep `assert "await doSearch(seq)" in render`.
- `loadKolImageSettings(routeRenderSeq)` to `reloadKolImageSettings()`.
- `loadAdminNews(routeRenderSeq)` to `loadAdminNews()`.
- News source selection to `selectNewsSource(this.value)`.
- News search input to `queueNewsSearch(this.value)`.
- News retry calls omit `routeRenderSeq`; give `renderFinancialNewsList()` and `renderFinancialNewsArticle()` defaults of `routeRenderSeq`.
- The three `adminNewsState` assignments call `updateAdminNewsQuery(this.value)`, `updateAdminNewsStatus(this.value)`, and `updateAdminNewsArchived(this.checked)`.
- The `_codesUi.filter`, `_codesUi.q`, and `_codesUi.result` assignments call `selectAdminCodeFilter(key)`, `searchAdminCodes(this.value)`, and `clearAdminCodesResult()`.
- The ACL retry calls only `retryImaGroupAcl()`; no bare callback remains in the attribute.
- Change `feishuSourcePillsHtml(..., onSelect)` to accept a target string (`"timeline"` or `"knowledge"`), render `data-source-target`, and call `selectFeishuSource(this)`; update its two callers.
- Change `platformTabHTML(..., handler)` to accept a target string (`"home"` or `"admin"`), render `data-platform-target`, and call `selectPlatformTab(this)`; update its two callers.

Run the lexical test and inspect its reported member roots. The only permitted dotted roots are `document`, `event`, `this`, and `window`; do not add application variables to the allowlist.

- [ ] **Step 4: Generate and insert the explicit registry**

Generate the complete registry from the just-added test helper:

```bash
python3 - <<'PY' > /tmp/inline-handlers.js
from pathlib import Path
import runpy
namespace = runpy.run_path('tests/test_frontend_interactions.py')
source = Path('app/static/index.html').read_text() + '\n' + Path('app/static/app.js').read_text()
names = sorted(namespace['_inline_handler_calls'](source))
print('const INLINE_HANDLERS = {')
for name in names:
    print(f'  {name},')
print('};')
print('Object.assign(window, INLINE_HANDLERS);')
PY
```

Insert the complete contents of `/tmp/inline-handlers.js` immediately before `applyTheme()` and `router()`. Delete `window.VPush` entirely. Run the exact-set test after insertion; a missing or extra name must fail.

- [ ] **Step 5: Rewrite browser tests against the public surface while the script is still classic**

In `tests/test_frontend_runtime.py`, import `json` and `urlsplit`, then make the static handler serve the SPA document for the route used by the tests:

```python
from urllib.parse import urlsplit

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/news":
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        pass
```

Add a pre-navigation bootstrap. It must run with `page.context.add_init_script(...)`, not `page.evaluate(...)`, because module initialization reads the token and starts routing immediately:

```python
def install_news_bootstrap(page: Page, *, delayed: bool, items: list[dict]) -> None:
    payload = json.dumps(items)
    page.context.add_init_script(
        f"""
        localStorage.setItem('dav_token', 'browser-test-token');
        const response = body => new Response(JSON.stringify(body), {{
          status: 200,
          headers: {{'Content-Type': 'application/json'}},
        }});
        const items = {payload};
        window.fetch = async input => {{
          const path = new URL(String(input), location.origin).pathname;
          if (path === '/api/me') return response({{username: 'tester', is_admin: false, news_visible: true}});
          if (path === '/api/news/sources') return response({{items: [], collection_enabled: true}});
          if (path === '/api/news') {{
            if ({str(delayed).lower()}) return new Promise(resolve => {{
              window.__resolveNews = body => resolve(response(body));
            }});
            return response({{items, next_offset: items.length, has_more: false, view_started_at: null}});
          }}
          if (path === '/api/news/7/images/0') throw new Error('offline');
          return response({{items: []}});
        }};
        """
    )
```

Replace the four browser tests with these public-surface versions. Delete every `page.evaluate` call that reads `state` / `routeRenderSeq` or invokes `newsListItemHtml()`, `loadFinancialNews()`, `loadNewsImageBlob()`, `openLightbox()`, or `adminEditKol()`.

```python
def test_news_reset_keeps_full_skeleton_until_response(page: Page, static_origin: str):
    install_news_bootstrap(page, delayed=True, items=[])
    page.goto(f"{static_origin}/news", wait_until="domcontentloaded")
    page.wait_for_selector("#news-page")
    cards = page.locator("#news-list .admin-sk-card")
    expect(cards).to_have_count(3)
    expect(cards.first).to_be_visible()
    assert cards.first.bounding_box()["height"] > 0
    page.evaluate(
        """() => window.__resolveNews({
          items: [], next_offset: 0, has_more: false, view_started_at: null,
        })"""
    )
    expect(page.locator("#news-list .admin-sk-card")).to_have_count(0)


def test_rejected_news_thumbnail_releases_layout_slot(page: Page, static_origin: str):
    install_news_bootstrap(
        page,
        delayed=False,
        items=[{
            "id": 7,
            "has_image": True,
            "source_name": "Test",
            "published_at": "2026-09-04T00:00:00Z",
            "title": "Title",
            "summary": "Summary",
            "is_new": False,
        }],
    )
    page.goto(f"{static_origin}/news", wait_until="domcontentloaded")
    page.wait_for_selector("#news-page")
    expect(page.locator('[data-news-thumbnail="7"]')).to_have_count(0)


def test_lightbox_traps_and_restores_focus(page: Page):
    page.evaluate(
        """() => {
          document.body.insertAdjacentHTML('beforeend', `
            <div class="post-images">
              <img id="lightbox-trigger" tabindex="0" src="/logo-mark.svg" alt="one" onclick="openLightbox(this)">
              <img src="/logo.svg" alt="two">
            </div>`);
        }"""
    )
    page.locator("#lightbox-trigger").click()
    expect(page.locator(".lightbox-close")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(page.locator(".lightbox-next")).to_be_focused()
    page.keyboard.press("Tab")
    expect(page.locator(".lightbox-close")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator(".lightbox")).to_have_count(0, timeout=1_000)
    expect(page.locator("#lightbox-trigger")).to_be_focused()


def test_kol_editor_uses_shared_focus_and_dirty_close_guard(page: Page):
    page.evaluate(
        """() => {
          const trigger = document.createElement('button');
          trigger.id = 'kol-edit-trigger';
          trigger.textContent = 'edit';
          trigger.setAttribute('onclick', 'adminEditKol(1)');
          document.body.appendChild(trigger);
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
    page.locator("#kol-edit-trigger").click()
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

Run the full browser file now, before changing the script tag:

```bash
PYTHONPATH=. ./.venv/bin/pytest tests/test_frontend_runtime.py -q
```

Expected: all four tests pass against the classic-script public surface.

- [ ] **Step 6: Switch the entry tag**

In `app/static/index.html`, replace the exact prefix `<script src="/app.js?v=` with `<script type="module" src="/app.js?v=`. This preserves the current query token. Run `--sync` immediately after the source change so the query becomes the calculated digest.

In `.github/workflows/docker-publish.yml`, replace `node --check app/static/app.js` with `node --input-type=module --check < app/static/app.js`. Leave the miniprogram `node --check` lines unchanged. Classic `--check` rejects `import` and would fail this commit's CI.

- [ ] **Step 7: Synchronize and run focused tests**

```bash
python3 scripts/bump_assets.py --sync
node --input-type=module --check < app/static/app.js
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_frontend_interactions.py \
  tests/test_frontend_runtime.py -q
```

Expected: module, registry, no-lexical-read, source contracts, and all four public-surface browser tests pass.

- [ ] **Step 8: Commit**

```bash
git add app/static/app.js app/static/index.html app/static/sw.js \
  tests/test_frontend_interactions.py tests/test_frontend_runtime.py \
  .github/workflows/docker-publish.yml
git commit -m "refactor(frontend): convert app entry to native module"
```

## Task 3: Extract Core HTML and Dialog Modules

**Files:**
- Create: `app/static/core/html.js`
- Create: `app/static/core/dialog.js`
- Modify: `app/static/app.js`
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Add failing extraction assertions and prepare path-aware source helpers**

Near the path constants in `tests/test_frontend_interactions.py`, add:

```python
DIALOG_JS = APP_JS.parent / "core" / "dialog.js"
NEWS_JS = APP_JS.parent / "views" / "news.js"
```

Change the helper signature without changing existing callers:

```python
def _fn_body(name: str, path: Path = APP_JS) -> str:
    """提取指定文件中的函数体。"""
    src = path.read_text()
    # keep the existing parser body unchanged
```

Add:

```python
def test_core_helpers_are_real_modules():
    src = APP_JS.read_text()
    assert 'from "./core/html.js"' in src
    assert 'from "./core/dialog.js"' in src
    assert "function escapeHtml(" not in src
    assert "function trapFocus(" not in src
```

Run the test and expect failure.

- [ ] **Step 2: Move HTML helpers**

Create `app/static/core/html.js` by moving `escapeHtml()`, `imgProxyUrl()`, and `imgOnError()` out of `app.js`, adding exports:

```javascript
export function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
}

export function imgProxyUrl(url) {
  return `/api/img-proxy?url=${encodeURIComponent(url)}`;
}

export function imgOnError(img) {
  if (!img || img.dataset.proxied) return;
  const src = img.getAttribute("src") || "";
  if (src.startsWith("/api/img-proxy")) return;
  img.dataset.proxied = "1";
  img.src = imgProxyUrl(src);
  img.onerror = null;
}
```

Import them at the top of `app.js`:

```javascript
import { escapeHtml, imgOnError, imgProxyUrl } from "./core/html.js";
```

Keep `imgOnError` in `INLINE_HANDLERS`; the registry test enforces this because markup calls it.

- [ ] **Step 3: Move the focus helper**

Create `app/static/core/dialog.js` by moving the existing helper out of `app.js` and adding the export:

```javascript
export function trapFocus(container, onEscape) {
  const previousActive = document.activeElement;
  const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function handleKeydown(e) {
    if (e.key === "Escape") {
      if (typeof onEscape === "function") {
        e.preventDefault();
        onEscape();
      }
      return;
    }
    if (e.key !== "Tab") return;
    const focusables = Array.from(container.querySelectorAll(focusableSelector)).filter((el) => el.offsetParent !== null || el === document.activeElement);
    if (!focusables.length) {
      e.preventDefault();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey) {
      if (document.activeElement === first || !container.contains(document.activeElement)) {
        e.preventDefault();
        last.focus();
      }
    } else if (document.activeElement === last || !container.contains(document.activeElement)) {
      e.preventDefault();
      first.focus();
    }
  }

  container.addEventListener("keydown", handleKeydown);
  setTimeout(() => {
    if (!container.contains(document.activeElement)) {
      const initial = container.querySelector("[autofocus]") || container.querySelector(focusableSelector);
      if (initial) initial.focus();
    }
  }, 0);

  const observer = new MutationObserver(() => {
    if (!document.body.contains(container)) {
      observer.disconnect();
      container.removeEventListener("keydown", handleKeydown);
      if (previousActive && previousActive.isConnected) previousActive.focus();
    }
  });
  observer.observe(document.body, { childList: true });

  return () => {
    observer.disconnect();
    container.removeEventListener("keydown", handleKeydown);
    if (previousActive && previousActive.isConnected) previousActive.focus();
  };
}
```

Import it in `app.js`:

```javascript
import { trapFocus } from "./core/dialog.js";
```

Migrate the existing `test_trap_focus_utility_and_a11y_enhancements()` source assertions: read the helper body with `_fn_body("trapFocus", DIALOG_JS)`, assert its selector/observer/focus-restoration details there, and retain `trapFocus(overlay, closeLightbox)` plus `trapFocus(mask, tryClose)` call-site assertions against `APP_JS`. No test may continue requiring `function trapFocus` in `app.js`.

- [ ] **Step 4: Synchronize and verify**

```bash
python3 scripts/bump_assets.py --sync
node --input-type=module --check < app/static/app.js
for file in app/static/core/*.js; do node --input-type=module --check < "$file"; done
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_frontend_interactions.py \
  tests/test_frontend_runtime.py \
  tests/test_asset_versions.py -q
```

Expected: all tests pass; the service-worker module block contains `/core/dialog.js` and `/core/html.js`.

- [ ] **Step 5: Commit**

```bash
git add app/static/app.js app/static/core app/static/index.html app/static/sw.js \
  tests/test_frontend_interactions.py
git commit -m "refactor(frontend): extract core browser helpers"
```

## Task 4: Extract the Financial-News View

**Files:**
- Create: `app/static/views/news.js`
- Modify: `app/static/app.js`
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Add failing module-boundary tests**

Add:

```python
def test_financial_news_is_a_view_module():
    src = APP_JS.read_text()
    assert 'from "./views/news.js"' in src
    assert "function renderNewsCenter(" not in src
    assert "function loadNewsImageBlob(" not in src
    assert "createNewsView({" in src
```

Run it and expect failure.

- [ ] **Step 2: Create the news-view factory**

Move the complete financial-news block from `renderNewsCenter()` through `saveNewsSources()` into `app/static/views/news.js`. Also move `clearNewsImageUrls()`, `stopNewsAutoLoad()`, `clearNewsReaderState()`, `startNewsAutoLoad()`, `selectNewsSource()`, and `queueNewsSearch()`.

Start the file with:

```javascript
export function createNewsView(dependencies) {
  const {
    $,
    state,
    api,
    apiBlob,
    routeStillActive,
    currentRouteSeq,
    setPageTitle,
    emptyState,
    go,
    flash,
    escapeHtml,
    trapFocus,
    fmtPublished,
    externalLinkIcon,
  } = dependencies;
  let searchTimer = null;
```

Place the moved functions after these declarations in their existing relative order. Apply exactly these substitutions inside the moved code:

- Replace every default or assignment using `routeRenderSeq` with `currentRouteSeq()`.
- Replace `EXTERNAL_LINK_ICON` with `externalLinkIcon`.
- Replace `window._newsSearchTimer` with `searchTimer`.
- Keep `newsListSkeletonHtml()` and the Plan A failed-thumbnail removal in the module.

End the factory with:

```javascript
  return {
    clearNewsReaderState,
    loadFinancialNews,
    openNewsArticle,
    openNewsSourcePicker,
    queueNewsSearch,
    renderFinancialNewsArticle,
    renderFinancialNewsList,
    renderNewsCenter,
    saveNewsSources,
    selectNewsSource,
  };
}
```

No news function listed above remains defined in `app.js`.

- [ ] **Step 3: Instantiate the view in the entry**

At the top of `app.js`, import:

```javascript
import { createNewsView } from "./views/news.js";
```

After all dependency functions/constants are defined and before event registration, instantiate and destructure:

```javascript
const {
  clearNewsReaderState,
  loadFinancialNews,
  openNewsArticle,
  openNewsSourcePicker,
  queueNewsSearch,
  renderFinancialNewsArticle,
  renderFinancialNewsList,
  renderNewsCenter,
  saveNewsSources,
  selectNewsSource,
} = createNewsView({
  $,
  state,
  api,
  apiBlob,
  routeStillActive,
  currentRouteSeq: () => routeRenderSeq,
  setPageTitle,
  emptyState,
  go,
  flash,
  escapeHtml,
  trapFocus,
  fmtPublished,
  externalLinkIcon: EXTERNAL_LINK_ICON,
});
```

Delete the old in-entry news functions. Keep the returned inline handlers in `INLINE_HANDLERS`; rerun its exact-set test.

- [ ] **Step 4: Migrate existing news source-contract tests**

The public browser tests were already rewritten in Task 2 and must remain unchanged. Move only the source location used by the existing news contracts:

- `test_news_reader_functions_cover_sources_seen_and_blob_cleanup()` reads `src = NEWS_JS.read_text()` for the `function {name}` / `async function {name}` loop (`renderNewsCenter`, `loadFinancialNews`, `openNewsSourcePicker`, `saveNewsSources`, `openNewsArticle`, `loadNewsImages`, `clearNewsImageUrls`) and calls `_fn_body(name, NEWS_JS)` for `loadFinancialNews` and `clearNewsImageUrls`.
- `test_news_pagination_appends_without_replacing_existing_thumbnails()` calls `_fn_body("loadFinancialNews", NEWS_JS)`.
- `test_news_source_picker_is_searchable_checkbox_dialog()` calls `_fn_body(..., NEWS_JS)` for both functions.
- `test_news_source_picker_preserves_selection_across_search()` calls `_fn_body(..., NEWS_JS)` for both functions.
- `test_news_list_shell_renders_shimmer_skeleton()` calls `_fn_body("renderNewsListShell", NEWS_JS)`.

Do not weaken or delete their behavioral assertions; only point them at the file that now owns the code. Keep navigation, visibility, admin-news, and CSS contracts on their current sources.

- [ ] **Step 5: Synchronize and verify the extraction**

```bash
python3 scripts/bump_assets.py --sync
node --input-type=module --check < app/static/app.js
for file in app/static/core/*.js app/static/views/*.js; do node --input-type=module --check < "$file"; done
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_frontend_runtime.py \
  tests/test_frontend_interactions.py \
  tests/test_asset_versions.py -q
```

Expected: all tests pass and `/views/news.js` is present in the service-worker shell.

- [ ] **Step 6: Commit**

```bash
git add app/static/app.js app/static/views/news.js app/static/index.html app/static/sw.js \
  tests/test_frontend_interactions.py
git commit -m "refactor(frontend): extract financial news view"
```

## Task 5: Extend CI and Verify Online, Upgrade, and Offline Loads

**Files:**
- Modify: `.github/workflows/docker-publish.yml`
- Modify: `tests/test_frontend_runtime.py`

- [ ] **Step 1: Add a failing service-worker browser test**

Add a session-independent test that creates a browser context with service workers allowed:

```python
def test_module_shell_survives_offline_reload(playwright_instance, static_origin):
    browser = playwright_instance.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(service_workers="allow")
    page = context.new_page()
    page.goto(static_origin, wait_until="networkidle")
    page.reload(wait_until="networkidle")
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    context.set_offline(True)
    page.reload(wait_until="domcontentloaded")
    expect(page.locator(".login-brand-title")).to_have_text("V Push")
    context.close()
    browser.close()
```

Before the SW module shell is complete, expect this test to expose any missing import in offline mode.

- [ ] **Step 2: Check all JavaScript and asset consistency in CI**

Replace the web-app part of the syntax step with:

```yaml
      - name: 前端静态检查
        run: |
          find app/static -type f -name '*.js' -print0 | while IFS= read -r -d '' file; do
            node --input-type=module --check < "$file"
          done
          python scripts/bump_assets.py --check
          node --check miniprogram/utils/api.js
          node --check miniprogram/pages/*/*.js
```

Keep the existing sidecar test unchanged.

- [ ] **Step 3: Run all focused checks**

```bash
find app/static -type f -name '*.js' -print0 | while IFS= read -r -d '' file; do
  node --input-type=module --check < "$file"
done
python3 scripts/bump_assets.py --check
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_asset_versions.py \
  tests/test_frontend_runtime.py \
  tests/test_frontend_interactions.py \
  tests/test_frontend_pwa.py \
  tests/test_frontend_xss.py -q
```

Expected: all commands pass, including the offline reload.

- [ ] **Step 4: Run the complete suite**

```bash
PYTHONPATH=. ./.venv/bin/pytest
```

Expected: all tests pass with no unexpected browser-test skip.

- [ ] **Step 5: Run the content-mutation acceptance probe without touching the worktree**

```bash
tmp="$(mktemp -d)"
cp -R app scripts "$tmp/"
printf '\n' >> "$tmp/app/static/core/html.js"
ROOT="$tmp" python3 - <<'PY'
import os
from pathlib import Path
from scripts import bump_assets
root = Path(os.environ['ROOT'])
raise SystemExit(0 if not bump_assets.check_consistency(root) else 1)
PY
rm -rf "$tmp"
```

Expected: the copied tree reports a stale digest and the shell command exits 0. The real worktree remains unchanged.

- [ ] **Step 6: Manually verify browser upgrade behavior**

Using desktop Chrome:

1. Load the previous Plan A build and confirm its service worker controls the page.
2. Start the Plan B build on the same origin and reload once.
3. Confirm the new digest appears in `index.html`, the new worker activates, and `/core/*.js` plus `/views/news.js` return 200.
4. Navigate directly to `/news`, exercise filtering and the source modal, then switch offline and reload.

Expected: no `ReferenceError`, failed module request, stale UI, or blank offline shell.

- [ ] **Step 7: Commit CI and browser acceptance**

```bash
git add .github/workflows/docker-publish.yml tests/test_frontend_runtime.py
git commit -m "ci(frontend): verify modules and offline asset shell"
```

- [ ] **Step 8: Review the final Plan B diff**

```bash
git status --short
git diff HEAD~5 --stat
git log -6 --oneline
```

Expected: only Plan B files are in the five commits. Preserve unrelated pre-existing worktree changes and do not deploy until independent review approves the module registry and digest behavior.
