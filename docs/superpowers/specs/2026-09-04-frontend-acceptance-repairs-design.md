# Frontend Acceptance Repairs Design

**Date:** 2026-09-04

**Status:** Approved

## Context

The frontend acceptance review found that the current P0/P1/P2 patch is not ready to release despite the full Python suite passing. Four user-visible or accessibility defects remain, the new tests mostly inspect source strings, `app.js` is still a 13,739-line classic script, and `scripts/bump_assets.py --check` cannot detect changed asset bytes.

The repair is split into two independently releasable projects:

1. **Plan A: interaction correctness** fixes visible behavior and adds browser-level regression tests.
2. **Plan B: delivery architecture** introduces a first real ES module boundary and content-aware asset versioning.

Plan A must not wait for Plan B. Each plan gets its own review, full test run, release decision, and rollback point.

## Goals

- Keep a visible, geometry-stable news skeleton for the entire list request.
- Remove a failed news thumbnail and its reserved width when the Blob request fails.
- Apply one focus-trap implementation to every modal flow in this scope, including the image lightbox and KOL editor.
- Test the above behavior in a real browser instead of relying only on source-string assertions.
- Convert the frontend entry to a native ES module without adding a bundler.
- Extract focused `core` modules and the financial-news view while preserving existing routes and inline-handler behavior.
- Replace manual integer cache versions with one deterministic digest derived from all shipped CSS and application module bytes.
- Make CI fail when asset bytes and checked-in cache references drift.

## Non-goals

- No visual redesign or new component system.
- No API, database, route, authentication, or authorization changes.
- No React, Vue, TypeScript, bundler, package manager, or production JavaScript dependency.
- No full-domain split of authentication, timeline, knowledge-base, plaza, or admin code in this cycle.
- No service-worker strategy rewrite; the existing network-first behavior remains.
- No attempt to provide a filesystem transaction across multiple files. The asset tool validates all writes before replacement and reports drift; Git remains the rollback mechanism.

## Plan A: Interaction Correctness

### News loading state

Add one `newsListSkeletonHtml()` renderer in `app/static/app.js`. Both `renderNewsListShell()` and the reset branch of `loadFinancialNews()` use it. The function returns the complete three-card skeleton, not an empty wrapper.

The existing `admin-skeleton`, `admin-sk-card`, `admin-sk-line`, and `admin-sk-head` styles remain the only skeleton styling. No second skeleton component is introduced.

### Thumbnail failure

`loadNewsImageBlob(articleId, index, image, seq)` keeps its current success path. On rejection, it removes `image` only when the element still exists in the document and the route sequence is still current. Removing the node also releases the fixed `96px`/`84px` flex basis, so the copy fills the row without a blank image slot.

A failed image remains non-blocking and produces no toast. Article text and navigation remain usable.

### Modal focus behavior

The existing `trapFocus(container, onEscape)` remains the sole focus-management utility.

- `openLightbox()` appends the overlay, calls `trapFocus(overlay, closeLightbox)`, then focuses the close button.
- `closeLightbox()` stays idempotent and restores focus after the closing overlay leaves the DOM.
- `adminEditKol()` removes its local Tab/Escape/MutationObserver implementation and calls `trapFocus(mask, tryClose)` after registering its close controls.
- The dirty-form confirmation remains in `tryClose`; Escape, backdrop click, and Cancel all pass through it.

### Browser regression tests

Add `tests/test_frontend_runtime.py` using Python Playwright `1.62.0` and the installed system Chrome channel. Add `requirements-test.txt` so browser tooling remains a test-only dependency. Update `.github/workflows/docker-publish.yml` to install the test requirements and run the browser file as part of the existing test job.

The fixture serves `app/static` on localhost and stubs API requests. It must exercise production JavaScript, not copied helper implementations.

Required browser cases:

1. A delayed news-list response leaves three visible skeleton cards until the response resolves.
2. A rejected thumbnail Blob request removes the image and its reserved layout width.
3. The lightbox focuses Close, loops Tab/Shift+Tab, closes on Escape, and restores the image trigger.
4. The KOL editor loops focus, restores its trigger, and preserves the dirty-form confirmation on Escape.

Existing fast source-contract tests remain for markup and token regressions, but they are not accepted as substitutes for these runtime cases.

## Plan B: Delivery Architecture

### Module boundary

Keep `app/static/app.js` as the entry file and load it with `<script type="module">`.

Create:

- `app/static/core/html.js`: HTML escaping and image-proxy URL helpers.
- `app/static/core/dialog.js`: `trapFocus()` and its focusable selector.
- `app/static/views/news.js`: financial-news list, article, source-picker, image-loading, and auto-load behavior.

The news module receives the small set of existing runtime dependencies it needs from the entry module. It returns the route renderer and the handlers referenced by generated markup. This avoids circular imports and does not create a general framework.

`app.js` explicitly assigns only functions still referenced by inline `onclick`, `oninput`, `onchange`, or `onkeydown` attributes to `window`. The temporary `window.VPush` facade is removed. Internal helpers remain module-scoped.

The migration is staged: first convert the entry and expose current handlers, then extract core helpers, then extract the news view. Tests must pass after each stage.

### Content-aware asset digest

Replace integer versions with a 12-character lowercase SHA-256 digest computed over sorted relative paths and bytes for:

- `app/static/style.css`
- `app/static/app.js`
- every `app/static/core/**/*.js`
- every `app/static/views/**/*.js`

The digest does not include `index.html`, `sw.js`, tests, images, or existing version tokens, so calculation is deterministic and non-recursive.

`scripts/bump_assets.py` becomes a synchronization/check tool:

- `--check` recomputes the digest and fails unless `index.html` CSS/entry queries and the service-worker cache name all match it.
- `--sync` recomputes the digest, validates every expected reference exactly once, prepares all resulting text in memory, writes temporary sibling files, and replaces the targets only after every validation and temporary write succeeds.
- The script no longer edits tests or increments counters.
- Error messages identify the missing, duplicate, or stale reference and exit non-zero.

`app/static/sw.js` keeps network-first fetches. Its shell list adds every extracted module using bare paths so a newly installed worker pre-caches the complete module graph for offline startup. The cache name uses the same aggregate digest.

### Asset tests and CI

Replace fixed version literals in `tests/test_frontend_interactions.py` and `tests/test_frontend_pwa.py` with assertions against the digest calculated from the current asset graph.

Add focused tests for `scripts/bump_assets.py` using a temporary static tree:

1. A synchronized tree passes `--check`.
2. Changing one byte in CSS, the entry, a core module, or the news module makes `--check` fail.
3. `--sync` updates HTML and SW to the newly calculated digest.
4. A missing or duplicate reference fails before any target is replaced.
5. The SW shell contains every module in the current graph.

CI runs `node --check` for the entry, service worker, and every extracted module, followed by `python scripts/bump_assets.py --check`.

## Rollout and Rollback

Plan A is released first. Its rollback unit is the interaction commit together with the conventional integer asset-version update still used before Plan B.

Plan B is released only after Plan A is stable. Before release, verify a cold online load, an update from the previous service worker, one offline reload after a successful online load, and direct navigation to the financial-news route.

Rollback of Plan B restores the previous classic entry, HTML script tag, service worker, and asset tool together. The two module systems must never be mixed across a rollback.

## Acceptance Criteria

### Plan A

- All four browser regression cases pass on desktop Chrome.
- News loading never shows an empty list area while a reset request is pending.
- Failed thumbnails leave no image node or reserved image width.
- Lightbox and KOL editor support Tab, Shift+Tab, Escape, and trigger-focus restoration.
- Existing frontend tests and the complete Python suite pass.
- No unrelated files are changed.

### Plan B

- `index.html` loads `app.js` with `type="module"`.
- `core/html.js`, `core/dialog.js`, and `views/news.js` are imported and used in production.
- `window.VPush` is absent; only required inline-event handlers are explicitly exposed.
- Changing any covered asset byte makes `python scripts/bump_assets.py --check` fail.
- Running `python scripts/bump_assets.py --sync` restores consistency without editing tests.
- The service-worker shell includes the full module graph and uses the aggregate digest.
- Online cold load, service-worker upgrade, and offline reload pass in Chrome.
- All JavaScript syntax checks, focused tests, and the complete Python suite pass.
