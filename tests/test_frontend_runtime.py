from __future__ import annotations

import functools
import http.server
import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="需要 playwright（pip install playwright && playwright install chromium），CI 必装",
)
from playwright.sync_api import Page, Playwright, expect, sync_playwright  # noqa: E402

from app.static_assets import resolve_fingerprinted_path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def _wait_for_call(page: Page, state: dict, method: str, timeout_ms: int = 5000):
    """轮询等待 page.route 网络桩捕获指定 method 的调用，超时返回 None。

    sync Playwright 的 route 回调只在 wait_* 调用期间派发；点击/evaluate 返回后
    立即读 state["calls"] 会在请求未到达时偶发空——CI 慢机上必现竞态
    （run 35615024544 实测）。本机 Playwright 无 expect.poll，手写同语义轮询。
    """
    import time as _time

    deadline = _time.monotonic() + timeout_ms / 1000
    while _time.monotonic() < deadline:
        found = next((c for c in state["calls"] if c["method"] == method), None)
        if found:
            return found
        page.wait_for_timeout(50)
    return next((c for c in state["calls"] if c["method"] == method), None)


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
        parsed = urlsplit(self.path)
        path = parsed.path
        logical = resolve_fingerprinted_path(STATIC, path)
        if logical:
            query = f"?{parsed.query}" if parsed.query else ""
            self.path = f"/{logical}{query}"
        elif path in {"/news", "/news/"}:
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
        "sources": {"items": [{"id": 1, "name": "Test", "selected": True, "group_name": "测试组"}], "collection_enabled": True, "unread_count": 2},
        "news": {"items": [{
            "id": 7, "has_image": True, "source_name": "Test",
            "published_at": "2026-09-04T00:00:00Z", "title": "Title",
            "summary": "Summary", "is_new": False,
        }], "next_offset": 1, "has_more": False, "view_started_at": None},
    }, ensure_ascii=False)
    page.context.add_init_script(
        "const data = " + payload + """;
          localStorage.setItem('dav_token', 'test-token');
          window.__newsRequests = [];
          window.fetch = async (input) => {
            const url = String(input);
            if (url.includes('/api/news')) window.__newsRequests.push(url);
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


def test_market_refresh_failure_visibility_and_cleanup(page: Page):
    page.clock.install(time=datetime(2026, 9, 4, 3, 0, tzinfo=UTC))
    page.evaluate("""async () => {
      const { createMarketView } = await import('/views/market.js');
      document.body.innerHTML = '<section id="tl-market"></section>';
      const h = window.marketTest = { calls: 0, failed: false, defer: false };
      h.payload = {status:'trading', stale:false, items:[
        {symbol:'sh000001', name:'上证指数', status:'trading', price:3930.12, change:11.97, percent:0.3, quoted_at:'2026-09-04T10:30:00+08:00'},
        {symbol:'sz399001', name:'深证成指', status:'trading', price:13516.97, change:-108.15, percent:-0.79, quoted_at:'2026-09-04T10:30:00+08:00'}
      ]};
      h.view = createMarketView({escapeHtml: s => s, api: async () => {
        h.calls++;
        if (h.defer) return new Promise(resolve => h.resolve = resolve);
        if (h.failed) throw new Error('offline');
        return h.payload;
      }});
      h.view.startMarketQuotes();
    }""")
    expect(page.locator('.market-change.positive')).to_have_text('+0.30%')
    expect(page.locator('.market-change.negative')).to_have_text('-0.79%')
    page.evaluate('marketTest.failed = true')
    page.clock.run_for(30000)
    expect(page.locator('.market-status')).to_have_text('更新失败')
    expect(page.locator('.market-price').first).to_have_text('3,930.12')
    page.evaluate('marketTest.failed = false')
    page.get_by_role('button', name='重试', exact=True).click()
    expect(page.locator('.market-status')).to_have_text('交易中')
    count = page.evaluate('marketTest.calls')
    page.evaluate("Object.defineProperty(document, 'visibilityState', {configurable:true, value:'hidden'})")
    page.clock.run_for(60000)
    assert page.evaluate('marketTest.calls') == count
    page.evaluate("""Object.defineProperty(document, 'visibilityState', {configurable:true, value:'visible'});
      document.dispatchEvent(new Event('visibilitychange'));""")
    assert page.evaluate('marketTest.calls') == count + 1
    page.evaluate('marketTest.defer = true')
    page.clock.run_for(30000)
    page.evaluate("marketTest.view.stopMarketQuotes(); document.querySelector('#tl-market').innerHTML = 'new route'; marketTest.resolve(marketTest.payload)")
    page.clock.run_for(60000)
    expect(page.locator('#tl-market')).to_have_text('new route')
    assert page.evaluate('marketTest.calls') == count + 2


def test_market_initial_failure_has_retry_and_no_zero_quotes(page: Page):
    page.evaluate("""async () => {
      const { createMarketView } = await import('/views/market.js');
      document.body.innerHTML = '<section id="tl-market"></section>';
      createMarketView({escapeHtml: s => s, api: async () => { throw new Error('offline'); }}).startMarketQuotes();
    }""")
    expect(page.locator('.market-status')).to_have_text('暂不可用')
    expect(page.locator('.market-price')).to_have_text(['--'] * 6)
    expect(page.get_by_role('button', name='重试', exact=True)).to_be_visible()


def test_market_holiday_status_explains_previous_trading_date(page: Page):
    page.evaluate("""async () => {
      const { createMarketView } = await import('/views/market.js');
      document.body.innerHTML = '<section id="tl-market"></section>';
      createMarketView({escapeHtml: s => s, api: async () => ({group:'night',stale:false,items:[{
        symbol:'us.INX',name:'标普 500 指数',price:7718.60,change:-29.55,percent:-0.38,status:'holiday',
        quoted_at:'2026-09-04T16:00:00-04:00',previous_close:7748.15,
        intraday:{date:'2026-09-04',duration:390,points:[{time:'09:30',minute:0,price:7740},{time:'16:00',minute:390,price:7718.6}]}
      }]})}).startMarketQuotes();
    }""")
    expect(page.locator('.market-status')).to_have_text('今日休市')
    expect(page.locator('.market-footer')).to_contain_text('最近交易日 · 09/04')


@pytest.mark.parametrize("daily_percent,expected_class", [(3.52, "positive"), (-3.52, "negative"), (0, "flat")])
def test_market_switches_automatically_and_ignores_other_group_responses(page: Page, daily_percent, expected_class):
    page.clock.install(time=datetime(2026, 9, 4, 11, 59, 50, tzinfo=UTC))
    page.evaluate("""async () => {
      const { createMarketView } = await import('/views/market.js');
      document.body.innerHTML = '<section id="tl-market"></section>';
      const h = window.marketTest = {calls: [], resolve: {}};
      h.view = createMarketView({escapeHtml: s => s, api: path => {
        h.calls.push(path);
        return new Promise(resolve => h.resolve[path] = resolve);
      }});
      h.view.startMarketQuotes();
    }""")
    expect(page.get_by_role('button', name='A股 / 港股')).to_have_attribute('aria-pressed', 'true')
    page.clock.run_for(30000)
    expect(page.get_by_role('button', name='美股', exact=True)).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('.market-name')).to_have_text(['标普 500 指数', '纳斯达克指数', '纳斯达克 100', '道琼斯指数', 'SOXX', 'YINN'])
    page.evaluate("marketTest.resolve['/api/market/indices?group=day']({group:'day',items:[],stale:true})")
    expect(page.locator('.market-status')).to_have_text('加载中')
    page.evaluate("""dailyPercent => marketTest.resolve['/api/market/indices?group=night']({group:'night',stale:false,items:[{
      symbol:'usSOXX',name:'SOXX',price:519.86,change:17.66,percent:dailyPercent,status:'closed',quoted_at:'2026-09-04T16:00:01-04:00',
      previous_close:502.20,
      intraday:{date:'2026-09-04',duration:390,points:[{time:'09:30',minute:0,price:550},{time:'10:30',minute:60,price:520},{time:'11:40',minute:130,price:519.86}]}
    }]})""", daily_percent)
    expect(page.locator('.market-spark')).to_have_count(1)
    expect(page.locator('.market-spark')).to_have_attribute('aria-label', re.compile('SOXX.*2026-09-04 日内分时.*09:30.*11:40.*昨收 502.20'))
    expect(page.locator('.market-spark')).to_have_class(re.compile(expected_class))
    points = page.locator('.market-spark polyline').get_attribute('points')
    assert points is not None
    assert len(points.split()) == 3
    assert points.split()[-1].startswith('22.0,')
    expect(page.locator('.market-spark-baseline')).to_have_attribute('y1', '18')
    expect(page.locator('.market-footer')).to_contain_text('最近交易日 · 09/04')
    assert '近20' not in page.locator('#tl-market').inner_text()
    assert '腾讯行情' not in page.locator('#tl-market').inner_text()
    page.get_by_role('button', name='A股 / 港股').click()
    expect(page.get_by_role('checkbox', name='自动')).not_to_be_checked()
    page.clock.run_for(60000)
    expect(page.get_by_role('button', name='A股 / 港股')).to_have_attribute('aria-pressed', 'true')
    page.get_by_role('checkbox', name='自动').check()
    expect(page.get_by_role('button', name='美股', exact=True)).to_have_attribute('aria-pressed', 'true')
    page.evaluate('marketTest.view.stopMarketQuotes()')


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


def test_theme_switch_keeps_browser_chrome_and_page_background_in_sync(page: Page):
    for mode, color, manifest, rgb in (
        ("light", "#f5f5f7", "/manifest.webmanifest?v=3", "rgb(245, 245, 247)"),
        ("dark", "#0f1115", "/manifest-dark.webmanifest?v=3", "rgb(15, 17, 21)"),
    ):
        page.evaluate("mode => setTheme(mode)", mode)
        assert page.locator('meta[name="theme-color"]').get_attribute("content") == color
        assert page.locator("#manifest").get_attribute("href") == manifest
        assert page.locator("html").evaluate("el => getComputedStyle(el).backgroundColor") == rgb

    page.emulate_media(color_scheme="light")
    page.evaluate("setTheme('auto')")
    assert page.locator('meta[name="theme-color"]').get_attribute("content") == "#f5f5f7"
    page.emulate_media(color_scheme="dark")
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute("content", "#0f1115")
    expect(page.locator("#manifest")).to_have_attribute("href", "/manifest-dark.webmanifest?v=3")


@pytest.mark.parametrize("reduced_motion", ["reduce", "no-preference"])
def test_mobile_navigation_scroll_direction(
    page: Page,
    static_origin: str,
    tmp_path: Path,
    reduced_motion: Literal["reduce", "no-preference"],
):
    page.set_viewport_size({"width": 380, "height": 840})
    page.emulate_media(reduced_motion=reduced_motion)
    install_badge_reader_bootstrap(page)
    page.goto(static_origin)
    page.evaluate("go('home')")
    expect(page.locator("#kol-list")).to_be_visible()
    nav = page.locator("#bottom-nav")
    page.evaluate("document.querySelector('#main').style.minHeight = '3000px'")

    def scroll(y):
        page.evaluate("y => window.scrollTo(0, y)", y)
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")

    scroll(100)
    expect(nav).to_have_attribute("inert", "")
    page.wait_for_function("document.querySelector('#bottom-nav').getBoundingClientRect().top >= innerHeight")
    page.screenshot(path=str(tmp_path / f"nav-hidden-{reduced_motion}.png"))
    page.set_viewport_size({"width": 380, "height": 880})
    expect(nav).to_have_attribute("inert", "")
    page.set_viewport_size({"width": 380, "height": 840})
    scroll(96)
    expect(nav).to_have_attribute("inert", "")
    scroll(92)
    expect(nav).not_to_have_attribute("inert", "")
    page.wait_for_function("document.querySelector('#bottom-nav').getBoundingClientRect().bottom <= innerHeight")
    scroll(102)
    expect(nav).not_to_have_attribute("inert", "")
    scroll(116)
    expect(nav).to_have_attribute("inert", "")
    scroll(0)
    expect(nav).not_to_have_attribute("inert", "")
    page.wait_for_function("document.querySelector('#bottom-nav').getBoundingClientRect().bottom <= innerHeight")
    page.screenshot(path=str(tmp_path / f"nav-visible-{reduced_motion}.png"))
    if reduced_motion == "reduce":
        assert nav.evaluate("el => getComputedStyle(el).transitionDuration") == "0s"
    scroll(200)
    page.evaluate("go('more')")
    expect(page.locator(".more-grid")).to_be_visible()
    expect(nav).not_to_have_attribute("inert", "")
    scroll(400)
    expect(nav).to_have_attribute("inert", "")
    page.set_viewport_size({"width": 1280, "height": 840})
    expect(nav).not_to_have_attribute("inert", "")
    expect(nav).to_be_hidden()
    page.set_viewport_size({"width": 380, "height": 840})
    page.evaluate("document.querySelector('#main').style.minHeight = ''")
    page.evaluate("go('timeline')")
    expect(page.locator("#feed")).to_be_visible()
    scroll(0)
    expect(nav).not_to_have_attribute("inert", "")


@pytest.mark.parametrize("width", [320, 380, 768, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_timeline_long_text_keeps_navigation_in_viewport(
    playwright_instance: Playwright, static_origin: str, tmp_path: Path, width: int, theme: str,
):
    browser = playwright_instance.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(
        viewport={"width": width, "height": 840}, is_mobile=width <= 768,
        has_touch=width <= 768, service_workers="block",
    )
    try:
        page = context.new_page()
        install_badge_reader_bootstrap(page)
        page.route("**/api/me", lambda route: route.fulfill(json={
            "id": 1, "username": "test", "is_admin": True, "news_visible": False,
        }))
        post = {"id": 1, "kol_id": 1, "kol_name": "Test", "platform": "twitter",
                "published_at": "2026-09-05T12:00:00Z", "content": "Post body " * 120}
        page.route("**/api/my/feed?*", lambda route: route.fulfill(json=[post]))
        for field, value in [("title", "LongTitle" * 8),
                             ("category_name", "LongCategory" * 8),
                             ("tags", ["LongTag" * 12])]:
            post[field] = value
            page.goto(static_origin)
            page.evaluate("go('timeline')")
            expect(page.locator(".post-item")).to_be_visible()
            page.evaluate("theme => document.documentElement.className = 'theme-' + theme", theme)
            page.locator(".post-expand-btn").click()
            for scroll_y in [0, 600, 0]:
                page.evaluate("y => window.scrollTo(0, y)", scroll_y)
                page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                geometry = page.evaluate("""() => ({
                    document: document.documentElement.scrollWidth,
                    viewport: document.documentElement.clientWidth,
                    navigation: [...document.querySelectorAll('.bnav-item')].map(el => {
                        const rect = el.getBoundingClientRect();
                        return {left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom};
                    }),
                })""")
                assert geometry["document"] <= width + 1, (field, geometry)
                assert geometry["viewport"] == width, (field, geometry)
                if width <= 768:
                    # MOBILE_NAV 六项：动态/财经新闻/研判/持股/广场/个人设置
                    assert len(geometry["navigation"]) == 6
                    for rect in geometry["navigation"]:
                        assert 0 <= rect["left"] < rect["right"] <= width
                        if scroll_y == 0:
                            page.wait_for_function("document.querySelector('#bottom-nav').getBoundingClientRect().bottom <= innerHeight")
                else:
                    expect(page.locator("#bottom-nav")).to_be_hidden()
            page.screenshot(path=str(tmp_path / f"navigation-{field}-{width}-{theme}.png"))
            if width <= 768:
                page.locator('.bnav-item[data-route="home"]').click()
                expect(page.locator("#kol-list")).to_be_visible()
                page.locator('.bnav-item[data-route="more"]').click()
                expect(page.locator(".more-grid")).to_be_visible()
            del post[field]
    finally:
        context.close()
        browser.close()


def _rgb(value: str) -> tuple[int, int, int]:
    values = [int(part) for part in re.findall(r"\d+", value)[:3]]
    assert len(values) == 3, value
    return values[0], values[1], values[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    def luminance(rgb: tuple[int, int, int]) -> float:
        channels = []
        for value in rgb:
            channel = value / 255
            channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    lighter, darker = sorted((luminance(_rgb(foreground)), luminance(_rgb(background))), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize(
    ("is_admin", "news_visible", "expected"),
    [
        (False, False, [("timeline", "动态"), ("mx-views", "研判"), ("holdings", "持股"), ("home", "广场"), ("settings", "个人设置")]),
        (False, True, [("timeline", "动态"), ("news", "财经新闻"), ("mx-views", "研判"), ("holdings", "持股"), ("home", "广场"), ("settings", "个人设置")]),
        (True, True, [("timeline", "动态"), ("news", "财经新闻"), ("mx-views", "研判"), ("holdings", "持股"), ("home", "广场"), ("settings", "个人设置"), ("more", "更多")]),
    ],
)
@pytest.mark.parametrize("width", [320, 768])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_mobile_bottom_navigation_is_icon_only(
    page: Page, static_origin: str, tmp_path: Path,
    is_admin: bool, news_visible: bool, expected: list[tuple[str, str]],
    width: int, theme: str,
):
    page.set_viewport_size({"width": width, "height": 840})
    page.emulate_media(reduced_motion="reduce")
    install_badge_reader_bootstrap(page)
    page.route("**/api/me", lambda route: route.fulfill(json={
        "id": 1, "username": "test", "is_admin": is_admin,
        "news_visible": news_visible,
    }))
    page.goto(static_origin)
    page.evaluate("() => go('timeline')")
    page.evaluate("theme => document.documentElement.className = 'theme-' + theme", theme)

    nav = page.locator("#bottom-nav")
    buttons = nav.locator(".bnav-item")
    expect(buttons).to_have_count(len(expected))
    assert nav.inner_text().strip() == ""
    assert buttons.evaluate_all("els => els.map(el => el.dataset.route)") == [route for route, _ in expected]
    nav_box = nav.bounding_box()
    pad = nav.evaluate("""el => {
      const s = getComputedStyle(el);
      return {top: s.paddingTop, bottom: s.paddingBottom, left: s.paddingLeft, right: s.paddingRight};
    }""")
    assert pad["top"] == "0px" and pad["bottom"] == "0px"
    assert pad["left"] == "12px" and pad["right"] == "12px"

    for index, (_, label) in enumerate(expected):
        button = buttons.nth(index)
        expect(button).to_have_attribute("aria-label", label)
        expect(button).to_have_attribute("title", label)
        expect(button.locator("svg")).to_be_visible()
        button_box = button.bounding_box()
        icon_box = button.locator("svg").bounding_box()
        assert button_box and 47 <= button_box["height"] <= 50
        assert nav_box and abs(nav_box["height"] - button_box["height"]) <= 2
        assert icon_box and 23 <= icon_box["width"] <= 25 and 23 <= icon_box["height"] <= 25

    active = page.locator('.bnav-item[data-route="timeline"]')
    inactive = page.locator('.bnav-item[data-route="home"]')
    expect(active).to_have_attribute("aria-current", "page")
    active.focus()
    expect(active).to_be_focused()
    colors = page.evaluate("""() => {
        const root = getComputedStyle(document.documentElement);
        const resolveColor = (value) => {
            const probe = document.createElement('span');
            probe.style.color = value;
            document.body.append(probe);
            const color = getComputedStyle(probe).color;
            probe.remove();
            return color;
        };
        return {
            active: getComputedStyle(document.querySelector('.bnav-item.active')).color,
            inactive: getComputedStyle(document.querySelector('.bnav-item:not(.active)')).color,
            activeToken: resolveColor(root.getPropertyValue('--color-accent-text')),
            inactiveToken: resolveColor(root.getPropertyValue('--color-text-muted')),
            background: getComputedStyle(document.querySelector('#bottom-nav')).backgroundColor,
        };
    }""")
    assert _rgb(colors["active"]) == _rgb(colors["activeToken"])
    assert _rgb(colors["inactive"]) == _rgb(colors["inactiveToken"])
    assert _contrast_ratio(colors["active"], colors["background"]) >= 3
    assert _contrast_ratio(colors["inactive"], colors["background"]) >= 3

    inactive.click()
    expect(page.locator("#kol-list")).to_be_visible()
    expect(inactive).to_have_attribute("aria-current", "page")
    expect(active).not_to_have_attribute("aria-current", "page")
    page.screenshot(path=str(tmp_path / f"bottom-nav-{len(expected)}-{width}-{theme}.png"))


def test_mobile_bottom_navigation_d1_feedback_restarts_without_rebuilding(page: Page, static_origin: str):
    page.set_viewport_size({"width": 390, "height": 840})
    page.emulate_media(reduced_motion="no-preference")
    install_badge_reader_bootstrap(page)
    page.goto(static_origin)
    page.evaluate("() => go('timeline')")

    nav_items = page.locator("#bottom-nav .bnav-item")
    nav_items.first.wait_for(state="visible")
    # bootstrap 管理员（news 可见）：MOBILE_NAV 六项 + admin「更多」= 7
    expect(nav_items).to_have_count(7)
    button = page.locator('.bnav-item[data-route="timeline"]')
    original_button = button.element_handle()
    assert original_button is not None
    assert page.evaluate("() => document.querySelector('#bottom-nav .bnav-item').style.backgroundColor") == ""
    # 220ms 反馈动画期间 animationend 会摘 is-feedback 类（app.js playBottomNavFeedback）；
    # 点击与读值同处一次同步 evaluate，防慢 runner 往返超窗后类已摘、动画列表读空
    feedback = page.evaluate("""() => {
        const button = document.querySelector('.bnav-item[data-route="timeline"]');
        button.click();
        return {
            hasClass: button.classList.contains('is-feedback'),
            highlight: getComputedStyle(button).webkitTapHighlightColor,
            background: getComputedStyle(button).backgroundColor,
            stroke: getComputedStyle(button.querySelector('svg')).strokeWidth,
            circleWidth: getComputedStyle(button, '::before').width,
            circleHeight: getComputedStyle(button, '::before').height,
            circleRadius: getComputedStyle(button, '::before').borderRadius,
            pointerEvents: getComputedStyle(button, '::before').pointerEvents,
            opacity: Number.parseFloat(getComputedStyle(button, '::before').opacity),
            animations: button.getAnimations({subtree: true})
                .filter(animation => animation.animationName === 'bottom-nav-feedback')
                .map(animation => ({name: animation.animationName, duration: animation.effect.getTiming().duration})),
        };
    }""")
    assert feedback["hasClass"] is True
    assert feedback["highlight"] == "rgba(0, 0, 0, 0)"
    assert feedback["background"] == "rgba(0, 0, 0, 0)"
    assert feedback["stroke"] == "2.4px"
    assert feedback["circleWidth"] == "42px"
    assert feedback["circleHeight"] == "42px"
    assert feedback["circleRadius"] == "50%"
    assert feedback["pointerEvents"] == "none"
    assert 0 <= feedback["opacity"] <= 1
    assert feedback["animations"] == [{"name": "bottom-nav-feedback", "duration": 220}]
    # 二次点击重启动画且不重建 DOM：点击与读动画数同样合并，理由同上
    restart = page.evaluate("""(original) => {
        const button = document.querySelector('.bnav-item[data-route=timeline]');
        button.click();
        return {
            sameElement: button === original,
            animations: button.getAnimations({subtree: true})
                .filter(a => a.animationName === 'bottom-nav-feedback').length,
        };
    }""", original_button)
    assert restart["sameElement"] is True
    assert restart["animations"] == 1
    page.wait_for_function("el => !el.classList.contains('is-feedback')", arg=original_button)
    assert page.locator('.bnav-item.is-feedback').count() == 0


def test_mobile_bottom_navigation_d1_feedback_reduced_motion_has_no_transform(page: Page, static_origin: str):
    page.set_viewport_size({"width": 390, "height": 840})
    page.emulate_media(reduced_motion="reduce")
    install_badge_reader_bootstrap(page)
    page.goto(static_origin)
    page.evaluate("() => go('timeline')")

    nav_items = page.locator("#bottom-nav .bnav-item")
    nav_items.first.wait_for(state="visible")
    expect(nav_items).to_have_count(7)
    # reduce 档反馈动画仅 80ms，animationend 即摘 is-feedback 类（app.js playBottomNavFeedback）；
    # 点击与读值必须同处一次同步 evaluate——分两次往返时慢 runner（xdist 并行）可超 80ms
    # 窗口，类已摘除后 animation-duration 回落初始值 0s（CI run 35431263784 即此 flake）
    duration = page.evaluate("""() => {
        const button = document.querySelector('.bnav-item[data-route="timeline"]');
        button.click();
        return button.classList.contains('is-feedback')
            ? getComputedStyle(button, '::before').animationDuration : null;
    }""")
    assert duration == "0.08s"
    transforms = page.evaluate("""() => [...document.styleSheets].flatMap(sheet => {
        try { return [...sheet.cssRules]; } catch { return []; }
    }).filter(rule => rule.type === CSSRule.KEYFRAMES_RULE && rule.name === 'bottom-nav-feedback')
      .flatMap(rule => [...rule.cssRules].map(frame => frame.style.transform))""")
    assert transforms and all(value == "translate(-50%, -50%)" for value in transforms)
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
    platforms = page.locator("#tl-pills .tl-pill").evaluate_all(
        "els => els.map(el => el.dataset.platform)"
    )
    assert platforms == ["", "live", "xueqiu", "combination", "weibo", "twitter", "zsxq", "truth"]
    expect(page.locator("#tl-platform-bar .star-icon")).to_have_count(0)
    for platform in platforms:
        button = page.locator(f'#tl-pills [data-platform="{platform}"]')
        icon = button.locator(".pt-icon")
        other = "xueqiu" if platform == "" else ""
        page.locator(f'#tl-pills [data-platform="{other}"]').click()
        expect(button).to_have_attribute("aria-checked", "false")
        expect(icon).to_be_visible()
        before = icon.bounding_box()
        assert before and before["width"] == before["height"]
        assert 22 <= before["width"] <= 34
        unselected = icon.evaluate("""el => ({
          color: getComputedStyle(el).color,
          background: getComputedStyle(el).backgroundColor,
          filter: getComputedStyle(el).filter,
          tag: el.tagName,
          pathFills: [...el.querySelectorAll('path')].map(path => getComputedStyle(path).fill)
        })""")
        if platform == "combination":
            assert set(unselected["pathFills"]) == {"none"}, unselected
        if platform == "xueqiu":
            assert unselected["tag"] == "svg"
            assert set(unselected["pathFills"]) == {"rgb(40, 125, 255)"}
        if platform == "twitter":
            accent = page.evaluate("""() => {
              const probe = document.body.appendChild(document.createElement('span'));
              probe.style.color = 'var(--color-accent-text)';
              const value = getComputedStyle(probe).color;
              probe.remove();
              return value;
            }""")
            assert unselected["color"] == accent, (theme, unselected, accent)
        assert unselected["tag"] == "svg"
        ink = unselected["pathFills"][0] if platform == "xueqiu" else unselected["color"]
        assert _contrast_ratio(ink, unselected["background"]) >= 3, (platform, unselected)
        assert unselected["filter"] == "none"

        button.click()
        expect(button).to_have_attribute("aria-checked", "true")
        page.wait_for_timeout(180)
        selected = button.evaluate("""el => ({
          base: getComputedStyle(el).backgroundColor,
          badge: getComputedStyle(el, '::before').backgroundColor,
          ink: getComputedStyle(el).color,
          iconColor: getComputedStyle(el.querySelector('.pt-icon')).color,
          iconFilter: getComputedStyle(el.querySelector('.pt-icon')).filter,
          iconTag: el.querySelector('.pt-icon').tagName,
          pathFills: [...el.querySelectorAll('.pt-icon path')].map(path => getComputedStyle(path).fill)
        })""")
        if platform == "combination":
            assert set(selected["pathFills"]) == {"none"}, selected
        if platform == "xueqiu":
            assert set(selected["pathFills"]) == {"rgb(255, 255, 255)"}
        assert "rgb(22, 104, 224)" in (selected["base"], selected["badge"]), (platform, selected)
        assert selected["ink"] == "rgb(255, 255, 255)", (platform, selected)
        after = icon.bounding_box()
        assert after and (after["width"], after["height"]) == (before["width"], before["height"])
        assert selected["iconTag"] == "svg"
        assert selected["iconColor"] == "rgb(255, 255, 255)", (platform, selected)
        assert selected["iconFilter"] == "none"
        if platform == "truth":
            fill = icon.evaluate("""el => {
              const bb = el.getBBox();
              const vb = el.viewBox.baseVal;
              return {x: bb.width / vb.width, y: bb.height / vb.height};
            }""")
            assert fill["x"] >= 0.75 and fill["y"] >= 0.70, fill

    page.screenshot(path=str(tmp_path / f"badges-{width}-{theme}.png"))
    if width <= 768:
        page.locator("#tl-filter-toggle").click()
        page.locator("#timeline-fav-toggle").click()
        expect(page.locator("#tl-filter-toggle")).to_have_class(re.compile("has-filter"))
        expect(page.locator("#tl-filter-toggle .funnel-icon")).to_have_css("background-color", "rgb(22, 104, 224)")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [375, 1280])
def test_post_origin_link_aligns_with_tags(page: Page, static_origin: str, width: int):
    install_badge_reader_bootstrap(page)
    page.route("**/api/my/feed*", lambda route: route.fulfill(json=[{
        "id": 1, "kol_id": 1, "kol_name": "淡淡的相思林", "platform": "xueqiu",
        "published_at": "2026-09-07T14:14:00+08:00", "content": "body",
        "category_name": "行业研究", "url": "https://xueqiu.com/1",
        "tags": ["实盘", "大盘", "调仓", "德明利", "剑桥科技"],
    }]))
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(static_origin)
    page.evaluate("() => go('timeline')")
    expect(page.locator(".post-item .p-meta span.cat")).to_be_visible()
    expect(page.get_by_role("button", name="复制图卡")).to_be_visible()
    expect(page.get_by_role("link", name="查看原文")).to_be_visible()
    geo = page.evaluate("""() => {
      const cat = document.querySelector('.p-meta span.cat');
      const exportBtn = document.querySelector('.p-meta .post-card-export');
      const origin = document.querySelector('.p-meta-actions a');
      const icon = origin.querySelector('svg');
      const cr = cat.getBoundingClientRect();
      const er = exportBtn.getBoundingClientRect();
      const or = origin.getBoundingClientRect();
      const ir = icon.getBoundingClientRect();
      const tags = [...document.querySelectorAll('.p-meta > .cat')];
      const lastTag = tags[tags.length - 1].getBoundingClientRect();
      const pills = [...document.querySelectorAll('.p-meta > .cat, .p-meta-actions .cat, .p-meta-actions a')];
      const rows = new Set(pills.map((el) => Math.round(el.getBoundingClientRect().top / 4)));
      return {
        catH: cr.height, originH: or.height, iconH: ir.height,
        actionTopDelta: Math.abs(er.top - or.top),
        exportLeft: er.left, originLeft: or.left,
        rowCount: rows.size,
        actionsAfterTags: er.top + 2 >= lastTag.top,
        firstRowGap: er.top <= cr.top + 4 && lastTag.top > cr.bottom + 4,
      };
    }""")
    assert geo["originH"] < 28, geo
    assert abs(geo["originH"] - geo["catH"]) <= 2, geo
    assert geo["actionTopDelta"] <= 2, geo
    assert geo["exportLeft"] < geo["originLeft"], geo
    assert 10 <= geo["iconH"] <= 14, geo
    assert geo["rowCount"] <= 4, geo
    assert geo["actionsAfterTags"], geo
    assert not geo["firstRowGap"], geo


def _install_card_export_stub(page: Page) -> None:
    page.evaluate("""() => {
      window.htmlToImage = {
        toCanvas: async (node) => {
          window.__exportCardHtml = node.outerHTML;
          const canvas = document.createElement("canvas");
          canvas.width = 12;
          canvas.height = 12;
          const ctx = canvas.getContext("2d");
          ctx.fillStyle = "#fff";
          ctx.fillRect(0, 0, 12, 12);
          return canvas;
        },
      };
      window.__clipWrites = [];
      navigator.clipboard.write = async (items) => { window.__clipWrites.push(items); };
      window.ClipboardItem = class { constructor(dict) { this.dict = dict; } };
    }""")


def test_post_card_export_copies_from_timeline_and_kol(page: Page, static_origin: str):
    install_badge_reader_bootstrap(page)
    posts = [
        {
            "id": 11, "kol_id": 2, "kol_name": "Kale", "platform": "twitter",
            "kol_external_id": "icekale", "published_at": "2026-09-17 09:00",
            "title": "Hello", "content": "X post full text",
            "url": "https://x.com/icekale/status/1", "images": [],
        },
        {
            "id": 12, "kol_id": 1, "kol_name": "调研爱好者", "platform": "xueqiu",
            "kol_external_id": "3576712780", "published_at": "2026-09-17 08:00",
            "title": "雪球标题", "content": "雪球正文很长，超过两百字。" + ("哈" * 80),
            "url": "https://xueqiu.com/1", "category_name": "行业研究",
        },
        {
            "id": 13, "kol_id": 3, "kol_name": "组合A", "platform": "combination",
            "published_at": "2026-09-17 07:00", "content": "",
            "detail": {
                "stats": [["仓位", "80%"]],
                "actions": [{"type": "买入", "stock": "茅台", "symbol": "600519", "prev": "0%", "target": "10%"}],
                "holdings": [{"name": "茅台", "symbol": "600519", "weight": 10}],
                "cash": "20%",
            },
            "url": "https://xueqiu.com/P/ZH1",
        },
    ]
    page.route("**/api/my/feed*", lambda route: route.fulfill(json=posts))
    page.route("**/api/kols/2/posts*", lambda route: route.fulfill(json=[posts[0]]))
    page.route("**/api/kols/2", lambda route: route.fulfill(json={
        "id": 2, "name": "Kale", "platform": "twitter", "external_id": "icekale", "subscribed": True,
    }))
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(static_origin)
    _install_card_export_stub(page)
    page.evaluate("() => go('timeline')")
    expect(page.get_by_role("button", name="复制图卡")).to_have_count(3)
    page.get_by_role("button", name="复制图卡").first.click()
    page.wait_for_function("() => (window.__exportCardHtml || '').includes('X post full text')")
    expect(page.locator("#toast")).to_contain_text("已复制，去微信粘贴即可")
    twitter_html = page.evaluate("window.__exportCardHtml")
    assert "@icekale" in twitter_html
    assert "VPush" in twitter_html
    assert "vpush.net" not in twitter_html
    assert page.evaluate("window.__clipWrites.length") == 1

    page.get_by_role("button", name="复制图卡").nth(1).click()
    page.wait_for_function("() => (window.__exportCardHtml || '').includes('超过两百字')")
    xueqiu_html = page.evaluate("window.__exportCardHtml")
    assert "哈" * 80 in xueqiu_html
    assert 'data-platform="xueqiu"' in xueqiu_html
    assert "xueqiu-icon" in xueqiu_html

    page.evaluate("() => setTheme('dark')")
    page.get_by_role("button", name="复制图卡").nth(2).click()
    page.wait_for_function("() => (window.__exportCardHtml || '').includes('调仓明细')")
    combo_html = page.evaluate("window.__exportCardHtml")
    assert "is-dark" in combo_html
    assert 'data-platform="combination"' in combo_html
    assert "茅台" in combo_html
    assert "现有持仓" in combo_html
    assert "调仓明细" in combo_html

    page.evaluate("() => go('kol/2')")
    expect(page.get_by_role("heading", name="Kale · 最近动态")).to_be_visible()
    expect(page.get_by_role("button", name="复制图卡")).to_have_count(1)
    page.evaluate("() => { window.__exportCardHtml = ''; }")
    page.get_by_role("button", name="复制图卡").click()
    page.wait_for_function("() => (window.__exportCardHtml || '').includes('X post full text')")
    expect(page.locator("#toast")).to_contain_text("已复制，去微信粘贴即可")
    assert "@icekale" in page.evaluate("window.__exportCardHtml")


def test_post_card_export_shares_on_phone(page: Page, static_origin: str):
    install_badge_reader_bootstrap(page)
    page.route("**/api/my/feed*", lambda route: route.fulfill(json=[{
        "id": 11, "kol_id": 2, "kol_name": "Kale", "platform": "twitter",
        "kol_external_id": "icekale", "published_at": "2026-09-17 09:00",
        "title": "Hello", "content": "X post full text",
        "url": "https://x.com/icekale/status/1", "images": [],
    }]))
    page.set_viewport_size({"width": 375, "height": 900})
    page.goto(static_origin)
    _install_card_export_stub(page)
    page.evaluate("""() => {
      window.__shares = [];
      navigator.canShare = () => true;
      navigator.share = async (data) => { window.__shares.push(data); };
    }""")
    page.evaluate("() => go('timeline')")
    page.get_by_role("button", name="复制图卡").click()
    page.wait_for_function("() => (window.__shares || []).length === 1")
    shared = page.evaluate("() => window.__shares[0]")
    assert shared["files"]
    assert page.evaluate("window.__clipWrites.length") == 0


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


@pytest.mark.parametrize("width", [390, 768, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_plaza_name_platform_icons(page: Page, static_origin: str, tmp_path: Path, width: int, theme: str):
    install_badge_reader_bootstrap(page)
    platforms = ["xueqiu", "combination", "weibo", "twitter", "zsxq", "truth"]
    names = ["雪球", "雪球组合", "微博", "X", "知识星球", "Truth Social"]
    catalog = [
        {"id": i + 1, "name": "测试名字" * (12 if i == 0 else 1),
         "platform": platform, "external_id": str(i), "enabled": True,
         "category_name": "财经", "quote": {"day_percent_gain": -1.25}}
        for i, platform in enumerate(platforms)
    ]
    page.route("**/api/catalog*", lambda route: route.fulfill(json=catalog))
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(static_origin)
    page.evaluate("theme => setTheme(theme)", theme)
    page.evaluate("() => go('home')")
    expect(page.locator(".kol-card")).to_have_count(6)
    for i, label in enumerate(names):
        card = page.locator(".kol-card").nth(i)
        badge = card.get_by_role("img", name=label, exact=True)
        expect(badge).to_be_visible()
        expect(badge).to_have_attribute("title", label)
        expect(badge.locator("svg")).to_have_count(1)
        expect(card.locator(".kol-card-meta")).to_have_text("财经" + ("-1.25%" if i == 1 else "") + f"外部 ID：{i}")
        geometry = card.evaluate("""el => {
          const name = el.querySelector('.name').getBoundingClientRect();
          const badge = el.querySelector('.p-platform').getBoundingClientRect();
          const card = el.getBoundingClientRect();
          return {separate: name.right <= badge.left, contained: badge.right <= card.right,
                  overflow: el.scrollWidth > el.clientWidth};
        }""")
        assert geometry == {"separate": True, "contained": True, "overflow": False}
    icon = page.locator('.kol-card .xueqiu-icon')
    assert icon.evaluate("el => getComputedStyle(el.querySelector('path')).fill") == "rgb(40, 125, 255)"
    assert icon.evaluate("el => getComputedStyle(el).filter") == "none"
    icon_box = icon.bounding_box()
    assert icon_box is not None
    assert icon_box["width"] == 17
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(tmp_path / f"plaza-icons-{width}-{theme}.png"), full_page=True)


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
    # hmf 新闻页改版为 .news-page 多栏目布局，加载骨架在实时资讯栏 #news-rt-list 内，共 4 张
    cards = page.locator(".news-page .admin-sk-card")
    expect(cards).to_have_count(4)
    expect(cards.first).to_be_visible()
    card_box = cards.first.bounding_box()
    assert card_box is not None
    assert card_box["height"] > 0
    page.evaluate("() => window.__resolveNews({ items: [], next_offset: 0, has_more: false, view_started_at: null })")
    expect(page.locator(".news-page .admin-sk-card")).to_have_count(0)


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


def test_admin_views_retry_after_chunk_load_failure(page: Page, static_origin: str):
    install_badge_reader_bootstrap(page)
    attempts: list[str] = []

    def serve_cicc(route):
        attempts.append(route.request.url)
        if len(attempts) == 1:
            route.fulfill(status=503, content_type="text/javascript", body="")
        else:
            route.continue_()

    page.route(re.compile(r".*/views/admin/cicc(?:\.[0-9a-f]{12})?\.js"), serve_cicc)
    page.goto(static_origin, wait_until="domcontentloaded")
    page.wait_for_function("typeof window.go === 'function'")

    def is_cicc_module(req):
        return bool(re.search(r"/views/admin/cicc(?:\.[0-9a-f]{12})?\.js", req.url))

    with page.expect_request(is_cicc_module):
        page.evaluate("go('admin/content')")
    page.wait_for_timeout(200)
    with page.expect_request(is_cicc_module):
        page.evaluate("go('admin/content')")
    page.wait_for_timeout(200)

    assert len(attempts) == 2
    assert "retry=" not in attempts[0]
    assert attempts[1].endswith("?retry=1")


def test_module_shell_survives_offline_reload(playwright_instance, static_origin):
    browser = playwright_instance.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(service_workers="allow")
    page = context.new_page()
    page.goto(static_origin, wait_until="networkidle")
    page.reload(wait_until="networkidle")
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    context.set_offline(True)
    page.reload(wait_until="domcontentloaded")
    expect(page.locator(".login-brand-title")).to_have_text("VPush")
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


def test_holdings_view_manage_cards_feed_flow(page: Page):
    """持股研判视图（工厂级打桩）：管理区渲染/建议回填/增改删、聚合卡筛选联动、
    时间流依据展开、快讯页签（标签命中帖）展开全文；持仓变更后整页重拉
    （桩数据不变，断言请求与反馈）。"""
    # 桩数据日期硬编码 09-15/09-14，而 hdDayLabel 对今天/昨天显示相对文案——
    # 固定浏览器时钟到 09-20，桩日期永远落在 MM-DD 分支，断言与真实运行日期解耦
    page.clock.install(time=datetime(2026, 9, 20, 3, 0, tzinfo=UTC))
    page.evaluate("""async () => {
      const { createHoldingsView } = await import('/views/holdings.js');
      document.body.innerHTML = '<main id="main"></main>';
      const h = window.hdTest = { calls: [], flashes: [] };
      h.holdings = [
        {id: 1, target_type: 'stock', target_name: '贵州茅台', note: '白酒龙头'},
        {id: 2, target_type: 'topic', target_name: 'AI算力', note: ''},
      ];
      h.allItems = [
        {id: 11, target_type: 'stock', target_name: '贵州茅台', direction: 'bull', action: '', confidence: 'high', summary: '批价回暖', occurred_at: '2026-09-15 10:00:00', kol_name: '王哥', avatar: '', evidence: [{post_id: 3, author: '王哥', time: '2026-09-15 09:59:00', content: '飞天批价回暖'}]},
        {id: 10, target_type: 'stock', target_name: '贵州茅台', direction: 'bear', action: '减仓', confidence: 'high', summary: '批价松动', occurred_at: '2026-09-15 09:30:00', kol_name: '李哥', avatar: '', evidence: []},
        {id: 9, target_type: 'topic', target_name: 'AI算力', direction: 'neutral', action: '', confidence: 'high', summary: '中性观察', occurred_at: '2026-09-14 09:00:00', kol_name: '王哥', avatar: '', evidence: []},
      ];
      h.views = (holder) => ({
        window_days: 30, max_id: 11,
        summary: {targets: [
          {target_type: 'stock', target_name: '贵州茅台', bull: 1, bear: 1, neutral: 0, total: 2, latest_at: '2026-09-15 10:00:00',
           kols: {count: 2, bull: 1, bear: 1, neutral: 0, bull_names: ['王哥'], bear_names: ['李哥'], neutral_names: []},
           actions: {减仓: 1}},
          {target_type: 'topic', target_name: 'AI算力', bull: 0, bear: 0, neutral: 1, total: 1, latest_at: '2026-09-14 09:00:00',
           kols: {count: 1, bull: 0, bear: 0, neutral: 1, bull_names: [], bear_names: [], neutral_names: ['王哥']},
           actions: {}},
        ]},
        items: holder ? h.allItems.filter(it => it.target_name === holder.split(':')[1]) : h.allItems,
      });
      h.tagPosts = (holder) => ({
        window_days: 30, max_id: 33,
        summary: {targets: [
          {target_type: 'stock', target_name: '贵州茅台', tag_count: 2, latest_at: '2026-09-15 09:00:00'},
          {target_type: 'topic', target_name: 'AI算力', tag_count: 0, latest_at: ''},
        ]},
        items: [
          {id: 33, platform: 'mx', published_at: '2026-09-15 09:00:00', kol_name: '王哥', avatar: '', content: '飞天整箱批价 rose', target_names: ['贵州茅台'], direction: 'bull'},
          {id: 32, platform: 'mx', published_at: '2026-09-15 08:30:00', kol_name: '李哥', avatar: '', content: '白酒板块成交低迷', target_names: ['贵州茅台'], direction: ''},
        ].filter(it => !holder || it.target_names.includes(holder.split(':')[1])),
      });
      h.view = createHoldingsView({
        $: (sel) => document.querySelector(sel),
        state: {token: ''},
        api: async (path, options = {}) => {
          h.calls.push({path, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null});
          if (path === '/api/my/holdings') return h.holdings;
          if (path.startsWith('/api/my/holdings/suggestions')) return {items: [{name: '贵州茅台', extra: '600519'}]};
          if (path.startsWith('/api/my/holdings/views')) {
            const u = new URL(path, location.origin);
            return h.views(u.searchParams.get('holder') || '');
          }
          if (path.startsWith('/api/my/holdings/tag-posts')) {
            const u = new URL(path, location.origin);
            return h.tagPosts(u.searchParams.get('holder') || '');
          }
          return {};
        },
        escapeHtml: (s) => String(s ?? ''),
        setPageTitle: () => {},
        routeStillActive: () => true,
        flash: (msg, type) => h.flashes.push([msg, type || 'success']),
        showConfirm: async () => true, // 应用内确认弹窗（f35a7c9 起替代原生 confirm）
      });
      Object.assign(window, h.view);
      await h.view.renderHoldings(1);
    }""")
    expect(page.locator(".hd-item")).to_have_count(2)
    expect(page.locator(".mxv-stockcard")).to_have_count(2)
    expect(page.locator(".mxv-feed-item")).to_have_count(3)
    expect(page.locator(".mxv-feed-item .target").first).to_have_text("贵州茅台")
    # 聚合卡 = 总览按个股卡同构：名称 + 股/题徽章 + N 大V + 操作词 + 占比条 + 三行名单
    card = page.locator(".mxv-stockcard").first
    expect(card.locator(".n b")).to_have_text("贵州茅台")
    expect(card.locator(".n")).to_contain_text("2 大V")
    expect(card.locator(".n")).to_contain_text("#2 帖")  # 标签提及数
    expect(card.locator(".mxv-actions")).to_have_text("减仓×1")
    expect(card.locator(".mxv-ratio .b")).to_be_visible()
    expect(card.locator(".mxv-ratio .s")).to_be_visible()
    expect(card.locator(".names")).to_have_count(3)
    expect(card.locator(".names").nth(0)).to_contain_text("王哥")
    expect(card.locator(".names").nth(1)).to_contain_text("李哥")
    expect(card.locator(".names").nth(2)).to_contain_text("暂无")
    # 相关观点按天分段单列：一天一段、一行一条消息（无批次时间分割）
    expect(page.locator(".mxv-feed-cols.single")).to_have_count(2)
    expect(page.locator(".mxv-feed-sep").first).to_have_text("09-15 · 2 条")
    # 快讯页签：标签命中帖同一行网格，方向徽章来自观点回流登记；点击展开全文
    page.locator(".hd-feed-tabs").get_by_role("button", name="快讯").click()
    expect(page.locator(".mxv-feed-item.has-post")).to_have_count(2)
    expect(page.locator(".mxv-feed-item .mxv-badge.bull")).to_have_text("↑看多")
    expect(page.locator(".mxv-feed-item .mxv-badge.neutral")).to_have_text("帖")
    page.locator(".mxv-feed-item.has-post").first.click()
    expect(page.locator(".hd-ev-content")).to_have_text("飞天整箱批价 rose")
    page.locator(".mxv-feed-item.has-post").first.click()
    expect(page.locator(".hd-ev-item")).to_have_count(0)
    page.locator(".hd-feed-tabs").get_by_role("button", name="观点").click()
    expect(page.locator(".mxv-feed-item")).to_have_count(3)
    # 关注列表可折叠：收起后添加区消失，再展开恢复
    page.get_by_role("button", name="收起", exact=True).click()
    expect(page.locator("#hd-add-input")).to_have_count(0)
    page.get_by_role("button", name="展开", exact=True).click()
    expect(page.locator("#hd-add-input")).to_have_count(1)
    # 依据原帖：有依据的行点击展开/收起（行尾「依据 N」指示）
    expect(page.locator(".mxv-feed-item.has-ev")).to_have_count(1)
    page.locator(".mxv-feed-item.has-ev").click()
    expect(page.locator(".hd-ev-content")).to_have_text("飞天批价回暖")
    page.locator(".mxv-feed-item.has-ev").click()
    expect(page.locator(".hd-ev-item")).to_have_count(0)
    # 聚合卡筛选：两条流请求都带 holder；再点取消恢复全量
    page.locator(".hd-card").first.click()
    expect(page.locator(".mxv-feed-item")).to_have_count(2)
    holder_calls = page.evaluate(
        "hdTest.calls.filter(c => c.path.includes('holder=') && c.method === 'GET').map(c => c.path.split('?')[0])")
    assert holder_calls == ["/api/my/holdings/views", "/api/my/holdings/tag-posts"]
    page.locator(".hd-card").first.click()
    expect(page.locator(".mxv-feed-item")).to_have_count(3)
    # 建议：个股/板块共用搜索框，两路合并去重；点选回填并记住类型
    page.fill("#hd-add-input", "贵")
    expect(page.locator(".hd-sug-item")).to_have_count(1)  # 桩两路同名 → 去重一条
    page.locator(".hd-sug-item").click()
    assert page.input_value("#hd-add-input") == "贵州茅台"
    # 添加：POST 携带类型/名称（点选自动识别，无备注字段），成功后整页重拉
    page.get_by_role("button", name="添加", exact=True).click()
    adds = page.evaluate("hdTest.calls.filter(c => c.method === 'POST')")
    assert adds == [{"path": "/api/my/holdings", "method": "POST",
                     "body": {"target_type": "stock", "target_name": "贵州茅台"}}]
    expect(page.locator(".hd-item")).to_have_count(2)  # 桩数据不变，重拉后仍两行
    # 手输类型探测：未点选建议时按个股名单精确命中 → stock（提交前发探测请求）
    page.fill("#hd-add-input", "贵州茅台")
    expect(page.locator(".hd-sug-item")).to_have_count(1)
    page.get_by_role("button", name="添加", exact=True).click()
    adds = page.evaluate("hdTest.calls.filter(c => c.method === 'POST')")
    assert adds[-1]["body"] == {"target_type": "stock", "target_name": "贵州茅台"}
    sug_calls = page.evaluate(
        "hdTest.calls.filter(c => c.path.includes('/api/my/holdings/suggestions')).map(c => c.path)")
    assert any("suggestions?type=stock&q=%E8%B4%B5%E5%B7%9E%E8%8C%85%E5%8F%B0" in p
               for p in sug_calls)  # 提交前探测请求发生过
    # 删除：应用内确认弹窗（桩 showConfirm 恒真）后 DELETE + flash 反馈；按钮为低调灰 ghost 样式
    assert "ghost" in page.locator(".hd-btn.ghost").first.get_attribute("class")
    page.get_by_role("button", name="删", exact=True).first.click()
    deletes = page.evaluate("hdTest.calls.filter(c => c.method === 'DELETE')")
    assert deletes == [{"path": "/api/my/holdings/1", "method": "DELETE", "body": None}]
    assert "已删除" in [f[0] for f in page.evaluate("hdTest.flashes")]


def test_holdings_kol_board_tabs_expand_sort(page: Page):
    """大V持股板块（工厂级打桩）：页顶 tab 切换、四榜渲染、行展开大V名单、
    窗口钮重拉、最近观点滑动栏筛选、清仓榜盈亏排序与割肉/止盈徽。"""
    page.evaluate("""async () => {
      const { createHoldingsView } = await import('/views/holdings.js');
      document.body.innerHTML = '<main id="main"></main>';
      const h = window.hdTest = { calls: [], flashes: [] };
      h.kolSummary = (days) => ({
        window_days: days,
        heavy: [
          {target_name: '贵州茅台', kol_count: 2, kols: [
            {kol_id: 1, name: '王哥', avatar: ''}, {kol_id: 2, name: '李哥', avatar: ''}]},
          {target_name: '中科曙光', kol_count: 2, kols: [
            {kol_id: 1, name: '王哥', avatar: ''}, {kol_id: 4, name: '钱哥', avatar: ''}]},
        ],
        attack: [
          {target_name: '五粮液', kol_count: 2, last_at: '2026-09-19 10:00:00', kols: [
            {kol_id: 1, name: '王哥', avatar: ''}, {kol_id: 2, name: '李哥', avatar: ''}]},
        ],
        topics: [
          {target_name: 'AI算力', kol_count: 3, kols: [
            {kol_id: 1, name: '王哥', avatar: ''}, {kol_id: 2, name: '李哥', avatar: ''},
            {kol_id: 3, name: '赵哥', avatar: ''}]},
        ],
        clears: [
          {target_name: '贵州茅台', kol_count: 2, kols: [
            {kol_id: 1, name: '王哥', avatar: ''}, {kol_id: 2, name: '李哥', avatar: ''}],
           entries: [
            {kol_id: 1, name: '王哥', avatar: '', at: '2026-09-19 14:30:00', realized_pnl_pct: -12.5, signal: 'cut'},
            {kol_id: 2, name: '李哥', avatar: '', at: '2026-09-19 15:00:00', realized_pnl_pct: 8.3, signal: 'profit'},
            {kol_id: 4, name: '孙哥', avatar: '', at: '2026-09-18 10:00:00', realized_pnl_pct: null, signal: ''},
           ]},
        ],
        generated_at: '2026-09-20 10:00',
      });
      h.holdings = [];
      h.view = createHoldingsView({
        $: (sel) => document.querySelector(sel),
        state: {token: ''},
        api: async (path, options = {}) => {
          h.calls.push(path);
          if (path.startsWith('/api/my/holdings/kol-summary')) {
            const u = new URL(path, location.origin);
            return h.kolSummary(Number(u.searchParams.get('days')) || 30);
          }
          if (path === '/api/my/holdings') return h.holdings;
          return {items: [], summary: {targets: []}, max_id: 0};
        },
        escapeHtml: (s) => String(s ?? ''),
        setPageTitle: () => {},
        routeStillActive: () => true,
        flash: (msg, type) => h.flashes.push([msg, type || 'success']),
        showConfirm: async () => true,
      });
      Object.assign(window, h.view);
      await h.view.renderHoldings(1);
    }""")
    # 页顶 tab：默认我的持股（空清单空态），切到大V持股后四榜骨架出现
    expect(page.locator(".hd-view-tabs")).to_have_count(1)
    page.locator(".hd-view-tabs").get_by_role("button", name="大V持股").click()
    expect(page.locator(".hd-kol-board")).to_have_count(1)
    # 重仓票榜：人数降序（后端排好），行显示票名 + 人数
    rows = page.locator(".hd-krow")
    expect(rows).to_have_count(2)
    expect(rows.nth(0).locator(".hd-krow-name")).to_have_text("贵州茅台")
    expect(rows.nth(0).locator(".hd-kcount")).to_have_text("2 人")
    # 行展开：两行共享大V王哥（ Regression：曾按 kol_id 记展开态，点一行会把
    # 所有含王哥的行连带点亮、再点缩不回）。点茅台行只开茅台，曙光保持收起
    rows.nth(0).click()
    expect(page.locator(".hd-kol-chip")).to_have_count(2)
    expect(page.locator(".hd-kol-chip").first).to_contain_text("王哥")
    expect(page.locator(".hd-krow-kols")).to_have_count(1)  # 只有茅台一行处于展开
    expect(rows.nth(1).locator(".hd-krow-kols")).to_have_count(0)
    # 下钻走现有单大V页路由（带前导斜杠）
    href_like = page.locator(".hd-kol-chip").first.get_attribute("onclick")
    assert "go('/mx-kol/1')" in href_like
    # 交错开缩互不干扰：再开曙光 → 各自展开；收曙光 → 茅台不受影响仍展开
    rows.nth(1).click()
    expect(page.locator(".hd-kol-chip")).to_have_count(4)
    expect(page.locator(".hd-krow-kols")).to_have_count(2)
    rows.nth(1).click()
    expect(page.locator(".hd-kol-chip")).to_have_count(2)  # 曙光收起，茅台仍开
    expect(rows.nth(0).locator(".hd-krow-kols")).to_have_count(1)
    # 再点茅台整行收起
    rows.nth(0).click()
    expect(page.locator(".hd-kol-chip")).to_have_count(0)
    # 窗口钮：切 90 天重拉（请求带 days=90）
    page.locator(".hd-pills").get_by_role("button", name="90天").click()
    assert any("days=90" in c for c in page.evaluate("hdTest.calls"))
    # 共同进攻榜：≥2 人才上榜，带最近动作时间
    page.locator(".hd-kol-controls").get_by_role("button", name="共同进攻").click()
    expect(rows).to_have_count(1)
    expect(rows.nth(0).locator(".hd-krow-name")).to_have_text("五粮液")
    expect(rows.nth(0).locator(".hd-kmeta")).to_contain_text("09-19")
    # 题材方向榜
    page.locator(".hd-kol-controls").get_by_role("button", name="题材方向").click()
    expect(rows).to_have_count(1)
    expect(rows.nth(0).locator(".hd-krow-name")).to_have_text("AI算力")
    # 清仓榜：行内汇总（平均盈亏 + 割肉/止盈计数徽）；展开后按盈亏排序、无价沉底
    page.locator(".hd-kol-controls").get_by_role("button", name="清仓").click()
    expect(rows).to_have_count(1)
    expect(rows.nth(0).locator(".hd-badge.cut")).to_contain_text("割肉 1")
    expect(rows.nth(0).locator(".hd-badge.win")).to_contain_text("止盈 1")
    rows.nth(0).click()
    chips = page.locator(".hd-kol-chip.static")
    expect(chips).to_have_count(3)
    # 默认亏多的在前：王哥 -12.5% → 李哥 +8.3% → 孙哥无价（—）沉底
    expect(chips.nth(0)).to_contain_text("王哥")
    expect(chips.nth(0).locator(".hd-kol-pct.cut")).to_have_text("-12.5%")
    expect(chips.nth(1)).to_contain_text("李哥")
    expect(chips.nth(1).locator(".hd-kol-pct.win")).to_have_text("+8.3%")
    expect(chips.nth(2)).to_contain_text("孙哥")
    expect(chips.nth(2).locator(".hd-kol-pct")).to_have_text("—")
    # 切排序「盈↑」：赚的在前，无价仍沉底
    page.locator(".hd-kol-controls").get_by_role("button", name="盈↑").click()
    chips = page.locator(".hd-kol-chip.static")
    expect(chips.nth(0)).to_contain_text("李哥")
    expect(chips.nth(1)).to_contain_text("王哥")
    expect(chips.nth(2)).to_contain_text("孙哥")
    # 最近观点滑动栏（回共同进攻榜验证筛选）：0=不筛；大值滤掉旧动作
    page.locator(".hd-kol-controls").get_by_role("button", name="共同进攻").click()
    page.locator("#hd-kol-recent-range").evaluate("el => { el.value = 0; el.dispatchEvent(new Event('change')); }")
    expect(rows).to_have_count(1)
    page.locator("#hd-kol-recent-range").evaluate("el => { el.value = 30; el.dispatchEvent(new Event('change')); }")
    # 桩 last_at 2026-09-19、时钟 2026-09-20：30 天内仍在
    expect(rows).to_have_count(1)
    page.locator("#hd-kol-recent-range").evaluate("el => { el.value = 0; el.dispatchEvent(new Event('change')); }")
    # 回我的持股：tab 状态保持，渲染我的持股空态
    page.locator(".hd-view-tabs").get_by_role("button", name="我的持股").click()
    expect(page.locator(".hd-kol-board")).to_have_count(0)


def test_mx_kol_holdings_slider_drags_while_held_and_sorts(page: Page):
    """预估持仓「最近观点」滑块按住可整程左右拖动，松手（change）才刷新汇总并持久化；
    排序段控按仓位/按时间（last_at 新→旧）可切换。抽屉宿主装配（mxcOpenDrawer 桩依赖）。

    回归：此前 oninput 直接重绘汇总，innerHTML 连带替换 range 元素自身，
    按住拖动即被打断——用例断言拖动全程元素存活且值跟手。"""
    page.clock.install(time=datetime(2026, 9, 17, 4, 0, tzinfo=UTC))  # 北京 12:00
    page.evaluate("""async () => {
      localStorage.removeItem("mxc_recent_days");
      localStorage.removeItem("mxc_sort");
      document.body.innerHTML = '<main id="mxv-drawer-slot"></main>';
      const { createMxKolHoldingsView } = await import("/views/mx-kol-holdings.js");
      const h = window.mxcTest = {};
      const holdings = [
        { target_name: "甲股", weight: 50, direction: "bull", since: "2026-08-01 09:00", last_at: "2026-08-25 10:00", last_day: "2026-08-25" },
        { target_name: "乙股", weight: 30, direction: "bull", since: "2026-09-02 09:00", last_at: "2026-09-17 09:00", last_day: "2026-09-17" },
        { target_name: "丙股", weight: 20, direction: "neutral", since: "2026-09-03 09:00", last_at: "2026-09-15 15:00", last_day: "2026-09-15" },
      ];
      const view = createMxKolHoldingsView({
        $: (sel) => document.querySelector(sel),
        state: {},
        api: async () => ({ kol: { kol_id: 42, name: "测试大V", avatar: "" }, window_days: 30,
          timeline: [], holdings, topics: [], opinion_count: 3, generated_at: "2026-09-17 12:00" }),
        escapeHtml: (s) => String(s), setPageTitle: () => {}, go: () => {},
        routeStillActive: () => true, emptyState: () => "", flash: () => {},
        closeViewsDrawer: () => {},
        mxHoldingsInScope: () => true,
      });
      Object.assign(window, view);
      h.rows = () => [...document.querySelectorAll("#mxc-summary .mxc-h-name")].map((e) => e.textContent);
    }""")
    page.evaluate("mxcOpenDrawer(42)")
    page.wait_for_selector("#mxc-summary .mxc-h-name")
    # 全新存储（键不存在）默认 3 天：甲股(08-25)超 3 天被滤——null 守卫防 Number(null)=0 顶掉默认
    assert page.evaluate('Number(document.getElementById("mxc-recent-range").value)') == 3
    assert page.evaluate('localStorage.getItem("mxc_recent_days")') is None
    assert page.evaluate("window.mxcTest.rows()") == ["乙股", "丙股"]

    box = page.locator("#mxc-recent-range").bounding_box()
    cy = box["y"] + box["height"] / 2
    handle = page.evaluate_handle("document.getElementById('mxc-recent-range')")
    # 按住拖动：中点 → 最右 → 最左 → 中点偏右，全程不松手
    page.mouse.move(box["x"] + box["width"] / 2, cy)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] - 2, cy, steps=8)
    assert page.evaluate("Number(document.getElementById('mxc-recent-range').value)") == 20
    assert page.evaluate("el => el.isConnected", handle)  # 旧代码此处已被重绘替换 → False，拖动即断
    page.mouse.move(box["x"] + 2, cy, steps=8)
    assert page.evaluate("Number(document.getElementById('mxc-recent-range').value)") == 0
    # 拖动中只改数值/提示文案：汇总不刷新（保持默认 3 天口径的 2 行，不随拖动值变化）
    assert page.evaluate("window.mxcTest.rows()") == ["乙股", "丙股"]
    assert page.evaluate('document.getElementById("mxc-recent-val").textContent') == "0"
    page.mouse.move(box["x"] + box["width"] * 0.55, cy, steps=6)
    page.mouse.up()
    # 松手（change）才刷新：v≈11 → cutoff 09-06 滤掉甲股（08-25），并落 localStorage
    expect(page.locator("#mxc-summary .mxc-h-name")).to_have_count(2)
    assert page.evaluate("window.mxcTest.rows()") == ["乙股", "丙股"]
    assert page.evaluate('localStorage.getItem("mxc_recent_days")') == "11"
    assert page.locator("#mxc-summary .hd-hint[title]").count() == 1  # 「已滤」提示

    # 排序：回不筛选后按时间 = last_at 新→旧；按仓位回落权重序；选择落 localStorage
    page.evaluate("mxcRecentChange(0)")
    page.locator(".mxc-recent .mxc-sort button", has_text="按时间").click()
    assert page.evaluate("window.mxcTest.rows()") == ["乙股", "丙股", "甲股"]
    assert page.locator(".mxc-recent .mxc-sort .on", has_text="按时间").count() == 1
    page.locator(".mxc-recent .mxc-sort button", has_text="按仓位").click()
    assert page.evaluate("window.mxcTest.rows()") == ["甲股", "乙股", "丙股"]
    assert page.evaluate('localStorage.getItem("mxc_sort")') == "weight"

    # 键盘步进走同一 change 路径：数值 +1 即时刷新（cutoff 09-16 滤掉丙股）
    page.focus("#mxc-recent-range")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("Number(document.getElementById('mxc-recent-range').value)") == 1
    assert page.evaluate("window.mxcTest.rows()") == ["乙股"]


def test_action_mark_modal_flow_and_chip_refresh(page: Page, static_origin: str):
    """操作标注弹窗（app.js 全局函数 + 网络层桩）：打开 → 自动标注对照 → 选操作
    → 填个股 → 提交 POST body 断言 → 未生效反馈 → 达成一致后角标就地翻成普通标签款
    （与消息标签去重，全重合则一张不剩）。

    回归口径：弹窗复用 tag-vote 外壳；POST body {target_name, action}；
    effective/my_marks 为列表（一帖多标）；DELETE 带 target_name 逐条撤销；
    refreshActionMarkChips 按响应 effective 有无在普通标签款/「标注中」间就地切换。
    app.js 的 api 是模块内 const，window 层覆盖不了——统一走 page.route 网络桩。"""
    page.clock.install(time=datetime(2026, 9, 20, 3, 0, tzinfo=UTC))
    # 完整引导 app.js：token + /api 全量路由拦截（me 带标注权限，feed 空列表）
    page.context.add_init_script("localStorage.setItem('dav_token', 'test-token')")
    state = {"effective": [], "calls": [], "flashes": []}

    def respond(route):
        path = urlsplit(route.request.url).path
        body = route.request.post_data
        data = []
        if path == "/api/me":
            data = {"id": 1, "username": "test", "is_admin": True,
                    "can_mx_action_mark": True, "timeline_platforms": []}
        elif path == "/api/posts/77/action-mark":
            state["calls"].append({
                "path": path, "method": route.request.method,
                "body": json.loads(body) if body else None,
            })
            eff = state["effective"]
            data = {
                "post": {"id": 77, "kol_id": 5, "kol_name": "测试大V",
                         "published_at": "2026-09-20 14:30:00",
                         "excerpt": "全部清仓了，落袋为安", "stock_tags": ["贵州茅台"]},
                "auto_tags": ["清仓", "贵州茅台"],
                "llm_tagged": True,
                "marks": ([
                    {"username": "alice", "is_admin": False, "target_name": "贵州茅台",
                     "action": "清仓", "updated_at": "2026-09-20 15:00:00"},
                    {"username": "bob", "is_admin": False, "target_name": "贵州茅台",
                     "action": "清仓", "updated_at": "2026-09-20 15:01:00"},
                ] if eff else [
                    {"username": "alice", "is_admin": False, "target_name": "贵州茅台",
                     "action": "清仓", "updated_at": "2026-09-20 15:00:00"},
                ]),
                "effective": eff,
                "my_marks": [{"target_name": "贵州茅台", "action": "清仓"}],
                "can_mark": True, "is_admin": False,
                "config": {"agree_n": 2, "usernames": ["alice", "bob"]},
                "actions": ["建仓", "加仓", "低吸", "减仓", "高抛", "清仓", "做T", "观察", "none"],
            }
        route.fulfill(json=data)

    page.route("**/api/**", respond)
    page.goto(static_origin)
    page.wait_for_function("typeof openActionMarkModal === 'function'")

    page.evaluate("""() => {
      // 卡片角标：初始标注中 1/2，裁决后就地翻已生效；
      // 放进真实卡片结构（生效标签全去重移除后，撤销回落要按卡片定位重插）
      document.body.insertAdjacentHTML('beforeend',
        '<div class="post-item" data-post-id="77"><div class="p-meta">'
        + '<button class="cat am-chip is-pending" data-post-id="77">✍ 标注中 1/2</button>'
        + '</div></div>');
    }""")
    page.evaluate("openActionMarkModal(77)")
    page.wait_for_selector("#action-mark-mask")
    # 弹窗骨架：摘要、自动标注区（消息标签对照）、个股建议、操作词按钮、我的标注预选
    expect(page.locator("#action-mark-mask .tag-vote-excerpt")).to_contain_text("全部清仓了")
    expect(page.locator("#action-mark-mask .am-auto-tags .cat-tag")).to_have_count(2)
    expect(page.locator("#action-mark-mask .am-auto-tags .cat-tag").first).to_have_text("清仓")
    expect(page.locator("#action-mark-mask .am-suggest")).to_have_text("贵州茅台")
    expect(page.locator("#action-mark-mask .am-act-btn")).to_have_count(9)
    expect(page.locator("#action-mark-mask .am-act-btn.on")).to_have_text("清仓")  # my_marks 预选
    expect(page.locator("#action-mark-mask .am-mark-row")).to_have_count(1)
    # 点建议填个股 → 选清仓 → 提交
    page.locator("#action-mark-mask .am-suggest").click()
    assert page.evaluate('document.getElementById("am-target").value') == "贵州茅台"
    page.locator('#action-mark-mask .am-act-btn[data-action="清仓"]').click()
    page.locator("#action-mark-mask .tag-vote-actions .btn-normal").click()
    # POST body 断言：弹窗重绘出现两行标注即说明响应已落地；calls 读取改
    # 轮询等待网络桩捕获——expect(to_have_count(1)) 提交前后同值，同步无效，
    # 直接读会在 POST 未到达时偶发空（CI 慢机竞态，run 35615024544 实测）
    expect(page.locator("#action-mark-mask .am-mark-row")).to_have_count(1)
    post = _wait_for_call(page, state, "POST")
    assert post and post["path"] == "/api/posts/77/action-mark"
    assert post["body"] == {"target_name": "贵州茅台", "action": "清仓"}
    # 达成一致后（响应带 effective 列表）角标就地翻已生效
    state["effective"] = [{"target_name": "贵州茅台", "action": "清仓",
                           "by_admin": False, "voters": ["alice", "bob"]}]
    page.evaluate("submitActionMark(77)")
    # 生效后就地翻成普通标签款：动作词/标的与消息标签（清仓、贵州茅台）全重合，
    # 去重后一张不剩（旧「人工:」实心高亮角标已废除）
    expect(page.locator('.am-chip[data-post-id="77"]')).to_have_count(0)
    expect(page.locator('.am-mark-tag[data-post-id="77"]')).to_have_count(0)
    # 生效行带「已生效」徽章（alice + bob 两行同标且都生效）
    expect(page.locator("#action-mark-mask .am-mark-row .tag-pending-badge.is-approved")).to_have_count(2)
    # 逐条撤销走 DELETE?target_name=，回落「标注中」虚线角标
    state["effective"] = []
    page.evaluate("deleteActionMark(77, '贵州茅台', 0)")
    deleted = _wait_for_call(page, state, "DELETE")
    assert deleted and deleted["path"] == "/api/posts/77/action-mark"
    chip = page.locator('.am-chip[data-post-id="77"]')
    expect(chip).to_have_class(re.compile("is-pending"))
    expect(chip).to_contain_text("标注中 1/2")
    page.evaluate("closeActionMarkModal()")
    expect(page.locator("#action-mark-mask")).to_have_count(0)


def test_action_mark_modal_multi_target_marks(page: Page, static_origin: str):
    """一帖多标：同帖多标的各自成行展示、各自生效（生效后普通标签款两张并列），
    逐条撤销只撤指定标的。"""
    page.clock.install(time=datetime(2026, 9, 20, 3, 0, tzinfo=UTC))
    page.context.add_init_script("localStorage.setItem('dav_token', 'test-token')")
    state = {"calls": []}

    def respond(route):
        path = urlsplit(route.request.url).path
        data = []
        if path == "/api/me":
            data = {"id": 1, "username": "admin", "is_admin": True,
                    "can_mx_action_mark": True, "timeline_platforms": []}
        elif path == "/api/posts/88/action-mark":
            state["calls"].append({"path": path, "method": route.request.method,
                                   "query": urlsplit(route.request.url).query})
            data = {
                "post": {"id": 88, "kol_id": 5, "kol_name": "测试大V",
                         "published_at": "2026-09-20 14:30:00",
                         "excerpt": "赛力斯和比亚迪都清仓了", "stock_tags": ["赛力斯", "比亚迪"]},
                "auto_tags": ["清仓"],
                "llm_tagged": True,
                "marks": [
                    {"username": "admin", "is_admin": True, "target_name": "赛力斯",
                     "action": "清仓", "updated_at": "2026-09-20 15:00:00"},
                    {"username": "admin", "is_admin": True, "target_name": "比亚迪",
                     "action": "清仓", "updated_at": "2026-09-20 15:00:30"},
                ],
                "effective": [
                    {"target_name": "赛力斯", "action": "清仓", "by_admin": True, "voters": ["admin"]},
                    {"target_name": "比亚迪", "action": "清仓", "by_admin": True, "voters": ["admin"]},
                ],
                "my_marks": [{"target_name": "赛力斯", "action": "清仓"},
                             {"target_name": "比亚迪", "action": "清仓"}],
                "can_mark": True, "is_admin": True,
                "config": {"agree_n": 2, "usernames": []},
                "actions": ["建仓", "加仓", "低吸", "减仓", "高抛", "清仓", "做T", "观察", "none"],
            }
        route.fulfill(json=data)

    page.route("**/api/**", respond)
    page.goto(static_origin)
    page.wait_for_function("typeof openActionMarkModal === 'function'")
    page.evaluate("openActionMarkModal(88)")
    page.wait_for_selector("#action-mark-mask")
    # 两条人工标注各自成行且都带已生效徽章
    expect(page.locator("#action-mark-mask .am-mark-row")).to_have_count(2)
    expect(page.locator("#action-mark-mask .am-mark-row .tag-pending-badge.is-approved")).to_have_count(2)
    # 逐条撤销按钮存在（我的标注）
    expect(page.locator("#action-mark-mask .am-mark-del")).to_have_count(2)
    # 角标多生效并列：先造角标容器，DELETE 响应落地后就地翻成普通标签款
    # （动作词「清仓」与消息标签重合被去重，只补赛力斯/比亚迪两张，无「人工:」前缀）
    page.evaluate("""() => {
      document.body.insertAdjacentHTML('beforeend',
        '<button class="cat am-chip" data-post-id="88"></button>');
    }""")
    page.evaluate("deleteActionMark(88, '赛力斯', 0)")
    mark_tags = page.locator('.am-mark-tag[data-post-id="88"]')
    expect(mark_tags).to_have_count(2)
    expect(mark_tags.nth(0)).to_have_text("赛力斯")
    expect(mark_tags.nth(1)).to_have_text("比亚迪")
    expect(page.locator('.am-chip[data-post-id="88"]')).to_have_count(0)
    # 逐条撤销：点比亚迪的 ×（calls 读取轮询等待网络桩捕获，理由同上）
    page.locator("#action-mark-mask .am-mark-del").nth(1).click()
    deleted = _wait_for_call(page, state, "DELETE")
    assert deleted and "target_name=" in deleted["query"]
    page.evaluate("closeActionMarkModal()")


def test_action_mark_modal_llm_action_preselect(page: Page, static_origin: str):
    """LLM 自动标注的操作词直接预选进表单：无人工标注时按 auto_tags 预选操作
    并预填个股；改选后「自动预选」提示撤掉；有我的标注时人工优先于自动。"""
    page.clock.install(time=datetime(2026, 9, 20, 3, 0, tzinfo=UTC))
    page.context.add_init_script("localStorage.setItem('dav_token', 'test-token')")
    state = {"my_marks": []}

    def respond(route):
        path = urlsplit(route.request.url).path
        data = []
        if path == "/api/me":
            data = {"id": 1, "username": "admin", "is_admin": True,
                    "can_mx_action_mark": True, "timeline_platforms": []}
        elif path == "/api/posts/99/action-mark":
            data = {
                "post": {"id": 99, "kol_id": 5, "kol_name": "测试大V",
                         "published_at": "2026-09-20 14:30:00",
                         "excerpt": "今天加了5500w联特", "stock_tags": ["联特科技"]},
                "auto_tags": ["联特科技", "加仓"],
                "llm_tagged": True,
                "marks": [], "effective": [],
                "my_marks": state["my_marks"],
                "can_mark": True, "is_admin": True,
                "config": {"agree_n": 2, "usernames": []},
                "actions": ["建仓", "加仓", "低吸", "减仓", "高抛", "清仓", "做T", "观察", "none"],
            }
        route.fulfill(json=data)

    page.route("**/api/**", respond)
    page.goto(static_origin)
    page.wait_for_function("typeof openActionMarkModal === 'function'")
    page.evaluate("openActionMarkModal(99)")
    page.wait_for_selector("#action-mark-mask")
    # 无人工标注：LLM 打的「加仓」直接预选，个股预填，命中标签高亮 + 预选提示
    expect(page.locator('#action-mark-mask .am-act-btn.on')).to_have_text("加仓")
    assert page.evaluate('document.getElementById("am-target").value') == "联特科技"
    expect(page.locator('#action-mark-mask .am-auto-tags .cat-tag.on')).to_have_text("加仓")
    expect(page.locator("#am-auto-hint")).to_contain_text("已按自动标注预选")
    # 人工改选：提示撤掉，自动标注区高亮跟随改选
    page.locator('#action-mark-mask .am-act-btn[data-action="低吸"]').click()
    expect(page.locator("#am-auto-hint")).to_have_count(0)
    expect(page.locator('#action-mark-mask .am-act-btn.on')).to_have_text("低吸")
    expect(page.locator('#action-mark-mask .am-auto-tags .cat-tag.on')).to_have_count(0)
    page.evaluate("closeActionMarkModal()")
    # 有我的标注时人工优先：预选我标的「减仓」，不出自动预选提示
    state["my_marks"] = [{"target_name": "联特科技", "action": "减仓"}]
    page.evaluate("openActionMarkModal(99)")
    page.wait_for_selector("#action-mark-mask")
    expect(page.locator('#action-mark-mask .am-act-btn.on')).to_have_text("减仓")
    expect(page.locator("#am-auto-hint")).to_have_count(0)
    page.evaluate("closeActionMarkModal()")


def test_news_list_groups_by_day_and_unread_toggle_sends_param(page: Page, static_origin: str):
    install_news_bootstrap(page)
    page.goto(f"{static_origin}/news", wait_until="domcontentloaded")
    # 默认进实时资讯页签：先切到「财经新闻」再断言列表行为
    page.get_by_role("tab", name="财经新闻").click()
    # 未读徽标：侧栏与底栏入口显示来源接口返回的未读数
    badge = page.locator("[data-news-badge]:not([hidden])")
    expect(badge.first).to_have_text("2")
    # 未读开关：点击后列表请求带 unread=1 且开关进入选中态
    toggle = page.locator(".news-unread-toggle")
    expect(toggle).to_be_visible()
    toggle.click()
    expect(toggle).to_have_class(re.compile(r"is-on"))
    expect(page.locator("#news-list .news-day-sep").first).to_be_visible()
    sent = page.evaluate("() => window.__newsRequests")
    assert any("unread=1" in url for url in sent)
