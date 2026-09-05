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
def test_abstract_copy_reuses_toolbar_icon_button(page: Page, static_origin: str, tmp_path: Path, width: int):
    install_badge_reader_bootstrap(page)
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(static_origin)
    page.evaluate("() => go('knowledge/test-report')")
    button = page.get_by_role("button", name="复制摘要", exact=True)
    expect(button).to_be_visible()
    assert "icon-btn" in button.get_attribute("class").split()
    expect(button.locator("svg")).to_have_count(1)
    assert button.inner_text() == ""
    assert button.bounding_box()["width"] == button.bounding_box()["height"] == 44
    page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {configurable: true,
      value: {writeText: async text => { window.copiedAbstract = text; }}})""")
    button.click()
    assert page.evaluate("window.copiedAbstract") == "Summary to copy"
    expect(page.locator(".ima-reader-abstract")).to_have_attribute("open", "")
    page.screenshot(path=str(tmp_path / f"abstract-{width}.png"))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


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
