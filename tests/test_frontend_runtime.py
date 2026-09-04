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


def test_news_reset_keeps_full_skeleton_until_response(page: Page):
    page.evaluate(
        """() => {
          document.querySelector('#main').innerHTML = '<div id="news-list"></div><div id="news-load-sentinel"></div>';
          document.querySelector('#app-view')?.classList.remove('hidden');
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
