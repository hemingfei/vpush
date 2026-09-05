from __future__ import annotations

import functools
import http.server
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Playwright, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


@pytest.fixture
def cicc_page(page: Page):
    page.clock.install()
    page.evaluate("""async () => {
      const { createCiccView } = await import('/views/admin/cicc.js');
      history.replaceState(null, '', '/admin/knowledge');
      document.body.innerHTML = '<main id="cicc-host"></main>';
      const h = window.ciccTest = {
        calls: [], flashes: [], renders: 0, libs: [{slug:'cicc-research'}],
        status: {available:true, ts:1, files_total:12, schedule_enabled:true,
                 storage:{schedule:{time:'04:30'}},
                 cicc_settings:{categories:['公司研究'], keywords:['芯片']}}
      };
      h.view = createCiccView({
        api: async (path, options = {}) => {
          const body = options.body ? JSON.parse(options.body) : null;
          h.calls.push({path, method:options.method || 'GET', body});
          if (path.endsWith('/status')) {
            if (h.deferStatus) return new Promise(resolve => { h.resolveStatus = resolve; });
            return h.status;
          }
          if (h.deferAction) return new Promise(resolve => { h.resolveAction = resolve; });
          if (path.endsWith('/cicc-categories')) return {categories:body.categories};
          if (path.endsWith('/schedule')) return {time:body.time, schedule_enabled:body.enabled};
          return {};
        },
        flash: (...args) => h.flashes.push(args), fmtTs: String,
        currentRouteSeq: () => 1, routeStillActive: () => true,
        renderLocalTab: () => {
          const host = document.querySelector('#cicc-host');
          h.view.rememberDetails(host);
          host.innerHTML = h.view.renderFallback(h.libs) +
            h.libs.map(lib => h.view.renderLibraryControls(lib.slug)).join('');
          h.renders++;
        }
      });
      Object.assign(window, h.view);
      await h.view.loadCiccStatus();
    }""")
    return page


@pytest.mark.parametrize("width", [390, 1280])
def test_cicc_controls_preserve_requests_and_details(cicc_page: Page, width):
    page = cicc_page
    page.set_viewport_size({"width": width, "height": 900})
    page.locator('details.cicc-collect > summary').click()
    expect(page.locator('#cicc-schedule-time')).to_have_value('04:30')
    page.locator('#cicc-schedule-time').fill('05:45')
    page.get_by_role('button', name='保存时间', exact=True).click()
    expect(page.locator('details.cicc-collect')).to_have_attribute('open', '')
    page.locator('summary').filter(has_text='品类定向与关键词白名单').click()
    page.locator('.cicc-cat[value="公司研究"]').uncheck()
    page.locator('.cicc-cat[value="宏观经济"]').check()
    page.locator('#cicc-keywords').fill('芯片,电池')
    page.get_by_role('button', name='保存品类与关键词').click()
    page.get_by_role('button', name='增量采集（近3天）', exact=True).click()
    page.get_by_role('button', name='关闭每日增量', exact=False).click()
    calls = page.evaluate('ciccTest.calls.filter(c => c.method !== "GET")')
    assert calls == [
        {"path": "/api/admin/cicc/schedule", "method": "PUT",
         "body": {"enabled": True, "time": "05:45"}},
        {"path": "/api/admin/ima-collector/cicc-categories", "method": "PUT",
         "body": {"categories": ["宏观经济"], "keywords": "芯片,电池"}},
        {"path": "/api/admin/cicc/trigger", "method": "POST", "body": {"mode": "incr"}},
        {"path": "/api/admin/cicc/schedule", "method": "PUT",
         "body": {"enabled": False, "time": "04:30"}},
    ]
    page.evaluate('ciccTest.libs = []; ciccTest.view.loadCiccStatus()')
    expect(page.get_by_role('heading', name='中金研报采集')).to_be_visible()
    expect(page.locator('details.cicc-collect')).to_have_count(0)


def test_cicc_stop_cancels_poll_and_delayed_refresh(cicc_page: Page):
    page = cicc_page
    page.evaluate('ciccTest.view.startCiccPoll(); ciccTest.view.startCiccPoll()')
    page.clock.run_for(15000)
    assert page.evaluate('ciccTest.calls.length') == 2
    page.evaluate('ciccTest.view.triggerCicc("incr")')
    page.evaluate('ciccTest.view.stopCiccPoll()')
    before = page.evaluate('ciccTest.calls.length')
    page.clock.run_for(30000)
    assert page.evaluate('ciccTest.calls.length') == before


@pytest.mark.parametrize("action", [False, True])
def test_cicc_exit_ignores_inflight_response(cicc_page: Page, action):
    page = cicc_page
    page.evaluate("""action => {
      const h = ciccTest;
      if (action) { h.deferAction = true; void h.view.triggerCicc('incr'); }
      else { h.deferStatus = true; void h.view.loadCiccStatus(); }
      h.view.stopCiccPoll();
      h.view.startCiccPoll();
      if (action) h.resolveAction({});
      else h.resolveStatus({...h.status, files_total:999});
    }""", action)
    assert page.evaluate('ciccTest.renders') == 1
    assert page.evaluate('ciccTest.flashes') == []
    page.clock.run_for(3000)
    assert page.evaluate('ciccTest.calls.length') == 2
    page.evaluate('ciccTest.view.reset()')
    assert page.evaluate('ciccTest.view.renderLibraryControls("cicc-research")') == ''


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/news", "/news/"}:
            self.path = "/index.html"
        super().do_GET()


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


@pytest.fixture
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


def install_news_bootstrap(page: Page, *, delayed: bool = False, fail_image: bool = False) -> None:
    payload = json.dumps({
        "delayed": delayed,
        "failImage": fail_image,
        "sources": {"items": [{"id": 1, "name": "Test", "selected": True}], "collection_enabled": True},
        "news": {"items": [{
            "id": 7, "has_image": True, "source_name": "Test",
            "published_at": "2026-09-04T00:00:00Z", "title": "Title",
            "summary": "Summary", "is_new": False,
        }], "next_offset": 1, "has_more": False, "view_started_at": None},
    }, ensure_ascii=False)
    page.context.add_init_script(
        "const data = " + payload + """;
          localStorage.setItem('dav_token', 'test-token');
          window.fetch = async (input) => {
            const url = String(input);
            if (url.includes('/api/me')) {
              return { ok: true, status: 200, json: async () => ({ id: 1, username: 'test', news_visible: true }) };
            }
            if (url.includes('/api/news/sources')) {
              return { ok: true, status: 200, json: async () => data.sources };
            }
            if (url.includes('/api/news/7/images/')) {
              if (data.failImage) throw new Error('offline');
              return { ok: true, status: 200, blob: async () => new Blob(['x']) };
            }
            if (url.includes('/api/news')) {
              if (data.delayed) {
                return {
                  ok: true,
                  status: 200,
                  json: () => new Promise(resolve => { window.__resolveNews = resolve; }),
                };
              }
              return { ok: true, status: 200, json: async () => data.news };
            }
            return { ok: true, status: 200, json: async () => ({}) };
          };
        """
    )


def install_badge_reader_bootstrap(page: Page) -> None:
    page.context.add_init_script("localStorage.setItem('dav_token', 'test-token')")

    def respond(route):
        path = urlsplit(route.request.url).path
        if path == "/api/me":
            data = {"id": 1, "username": "test", "is_admin": True,
                    "timeline_platforms": ["xueqiu", "combination", "weibo", "twitter", "truth", "zsxq"]}
        elif path == "/api/ima-documents/test-report":
            data = {"media_id": "test-report", "name": "Research report", "abstract": "Summary to copy"}
        elif path in {"/api/my/feed", "/api/catalog", "/api/categories", "/api/recommendations"}:
            data = []
        else:
            data = {}
        route.fulfill(json=data)

    page.route("**/api/**", respond)


@pytest.mark.parametrize("width", [375, 768, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_platform_badges_keep_blue_selection(page: Page, static_origin: str, tmp_path: Path, width: int, theme: str):
    install_badge_reader_bootstrap(page)
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.goto(static_origin)
    page.evaluate("() => go('timeline')")
    expect(page.locator("#tl-pills .tl-pill").first).to_be_visible()
    page.evaluate("theme => document.documentElement.className = 'theme-' + theme", theme)
    expect(page.locator("#tl-platform-bar .star-icon")).to_have_count(0)
    for platform in ["", "live", "xueqiu", "combination", "weibo", "twitter", "zsxq", "truth"]:
        button = page.locator(f'#tl-pills [data-platform="{platform}"]')
        button.click()
        expect(button).to_have_attribute("aria-checked", "true")
        page.wait_for_timeout(180)
        colors = button.evaluate("""el => ({
          base: getComputedStyle(el).backgroundColor,
          badge: getComputedStyle(el, '::before').backgroundColor,
          ink: getComputedStyle(el).color,
          imageFilter: getComputedStyle(el.querySelector('.pt-icon')).filter
        })""")
        assert "rgb(22, 104, 224)" in (colors["base"], colors["badge"]), (platform, colors)
        assert colors["ink"] == "rgb(255, 255, 255)", (platform, colors)
        if platform in {"xueqiu", "truth"}:
            assert colors["imageFilter"] == "brightness(0) invert(1)"
    page.screenshot(path=str(tmp_path / f"badges-{width}-{theme}.png"))
    if width <= 768:
        page.locator("#tl-filter-toggle").click()
        page.locator("#timeline-fav-toggle").click()
        expect(page.locator("#tl-filter-toggle")).to_have_class(re.compile("has-filter"))
        expect(page.locator("#tl-filter-toggle .funnel-icon")).to_have_css("background-color", "rgb(22, 104, 224)")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [375, 1440])
def test_abstract_has_no_copy_button(page: Page, static_origin: str, tmp_path: Path, width: int):
    install_badge_reader_bootstrap(page)
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(static_origin)
    page.evaluate("() => go('knowledge/test-report')")
    expect(page.get_by_text("Summary to copy", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="复制摘要", exact=True)).to_have_count(0)
    expect(page.locator(".ima-reader-abstract")).to_have_attribute("open", "")
    page.screenshot(path=str(tmp_path / f"abstract-{width}.png"))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_zsxq_attachment_download_uses_auth_header_not_query_token(page: Page, static_origin: str):
    page.context.add_init_script("localStorage.setItem('dav_token', 'test-token')")
    page.goto(static_origin, wait_until="domcontentloaded")
    page.wait_for_function("typeof downloadZsxqFile === 'function'")
    page.evaluate("""() => {
      document.body.insertAdjacentHTML('beforeend',
        '<button type="button" class="p-file" data-file-id="file-1" data-name="note.pdf" onclick="downloadZsxqFile(this)">📎 note.pdf</button>');
      window.__blobReqs = [];
      const orig = window.fetch;
      window.fetch = async (input, init = {}) => {
        const url = String(input);
        const headers = init.headers || {};
        window.__blobReqs.push({ url, auth: headers.Authorization || headers.authorization || '' });
        if (url.includes('/api/media/zsxq-file/')) {
          return { ok: true, status: 200, blob: async () => new Blob(['pdf'], { type: 'application/pdf' }) };
        }
        return orig(input, init);
      };
      URL.createObjectURL = () => 'blob:test';
      URL.revokeObjectURL = () => {};
    }""")
    page.locator(".p-file").click()
    reqs = page.evaluate("window.__blobReqs")
    assert reqs, "expected attachment fetch"
    assert all("token=" not in item["url"] for item in reqs)
    assert any("/api/media/zsxq-file/file-1" in item["url"] for item in reqs)
    assert any(item["auth"] == "Bearer test-token" for item in reqs)


def test_news_reset_keeps_full_skeleton_until_response(page: Page, static_origin: str):
    install_news_bootstrap(page, delayed=True)
    page.goto(f"{static_origin}/news", wait_until="domcontentloaded")
    cards = page.locator("#news-list .admin-sk-card")
    expect(cards).to_have_count(3)
    expect(cards.first).to_be_visible()
    assert cards.first.bounding_box()["height"] > 0
    page.evaluate("() => window.__resolveNews({ items: [], next_offset: 0, has_more: false, view_started_at: null })")
    expect(page.locator("#news-list .admin-sk-card")).to_have_count(0)


def test_rejected_news_thumbnail_releases_layout_slot(page: Page, static_origin: str):
    install_news_bootstrap(page, fail_image=True)
    page.goto(f"{static_origin}/news", wait_until="domcontentloaded")
    expect(page.locator('[data-news-thumbnail="7"]')).to_have_count(0)


def test_lightbox_traps_and_restores_focus(page: Page):
    page.evaluate(
        """() => {
          document.body.insertAdjacentHTML('beforeend', `
            <div class="post-images">
              <img id="lightbox-trigger" tabindex="0" src="/logo-mark.svg" alt="one"
                   onclick="openLightbox(this)">
              <img src="/logo.svg" alt="two">
            </div>`);
          document.querySelector('#lightbox-trigger').focus();
          document.querySelector('#lightbox-trigger').click();
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


def test_kol_editor_uses_shared_focus_and_dirty_close_guard(page: Page):
    page.evaluate(
        """() => {
          const trigger = document.createElement('button');
          trigger.id = 'kol-edit-trigger';
          trigger.textContent = 'edit';
          trigger.setAttribute('onclick', 'adminEditKol(1)');
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
          trigger.click();
        }"""
    )
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
