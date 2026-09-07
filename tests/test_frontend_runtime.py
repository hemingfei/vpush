from __future__ import annotations

import functools
import http.server
import json
import re
import threading
from datetime import datetime, timezone
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


def test_market_refresh_failure_visibility_and_cleanup(page: Page):
    page.clock.install(time=datetime(2026, 9, 4, 3, 0, tzinfo=timezone.utc))
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
    page.clock.install(time=datetime(2026, 9, 4, 11, 59, 50, tzinfo=timezone.utc))
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
    assert len(page.locator('.market-spark polyline').get_attribute('points').split()) == 3
    assert page.locator('.market-spark polyline').get_attribute('points').split()[-1].startswith('22.0,')
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
def test_mobile_navigation_scroll_direction(page: Page, static_origin: str, tmp_path: Path, reduced_motion: str):
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
                    assert len(geometry["navigation"]) == 4
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
    return tuple(values)


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
        (False, False, [("timeline", "动态"), ("home", "广场"), ("settings", "个人设置")]),
        (False, True, [("timeline", "动态"), ("news", "财经新闻"), ("home", "广场"), ("settings", "个人设置")]),
        (True, True, [("timeline", "动态"), ("news", "财经新闻"), ("home", "广场"), ("settings", "个人设置"), ("more", "更多")]),
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
    expect(nav_items).to_have_count(5)
    button = page.locator('.bnav-item[data-route="timeline"]')
    original_button = button.element_handle()
    assert original_button is not None
    assert page.evaluate("() => document.querySelector('#bottom-nav .bnav-item').style.backgroundColor") == ""
    button.click()
    expect(button).to_have_class(re.compile(r"\bis-feedback\b"))
    feedback = button.evaluate("""el => ({
        highlight: getComputedStyle(el).webkitTapHighlightColor,
        background: getComputedStyle(el).backgroundColor,
        stroke: getComputedStyle(el.querySelector('svg')).strokeWidth,
        circleWidth: getComputedStyle(el, '::before').width,
        circleHeight: getComputedStyle(el, '::before').height,
        circleRadius: getComputedStyle(el, '::before').borderRadius,
        pointerEvents: getComputedStyle(el, '::before').pointerEvents,
        opacity: Number.parseFloat(getComputedStyle(el, '::before').opacity),
        animations: el.getAnimations({subtree: true})
            .filter(animation => animation.animationName === 'bottom-nav-feedback')
            .map(animation => ({name: animation.animationName, duration: animation.effect.getTiming().duration})),
    })""")
    assert feedback["highlight"] == "rgba(0, 0, 0, 0)"
    assert feedback["background"] == "rgba(0, 0, 0, 0)"
    assert feedback["stroke"] == "2.4px"
    assert feedback["circleWidth"] == "42px"
    assert feedback["circleHeight"] == "42px"
    assert feedback["circleRadius"] == "50%"
    assert feedback["pointerEvents"] == "none"
    assert 0 <= feedback["opacity"] <= 1
    assert feedback["animations"] == [{"name": "bottom-nav-feedback", "duration": 220}]
    button.click()
    assert page.evaluate("original => document.querySelector('.bnav-item[data-route=timeline]') === original", original_button)
    assert button.evaluate("el => el.getAnimations({subtree: true}).filter(a => a.animationName === 'bottom-nav-feedback').length") == 1
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
    expect(nav_items).to_have_count(5)
    button = page.locator('.bnav-item[data-route="timeline"]')
    button.click()
    expect(button).to_have_class(re.compile(r"\bis-feedback\b"))
    assert button.evaluate("el => getComputedStyle(el, '::before').animationDuration") == "0.08s"
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
    }]))
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(static_origin)
    page.evaluate("() => go('timeline')")
    expect(page.locator(".post-item .p-meta .cat:not(a)")).to_be_visible()
    expect(page.get_by_role("link", name="查看原文")).to_be_visible()
    geo = page.evaluate("""() => {
      const cat = document.querySelector('.p-meta .cat:not(a)');
      const origin = document.querySelector('.p-meta a');
      const icon = origin.querySelector('svg');
      const cr = cat.getBoundingClientRect();
      const or = origin.getBoundingClientRect();
      const ir = icon.getBoundingClientRect();
      return {
        catH: cr.height, originH: or.height, iconH: ir.height,
        topDelta: Math.abs(cr.top - or.top),
      };
    }""")
    assert geo["originH"] < 28, geo
    assert abs(geo["originH"] - geo["catH"]) <= 2, geo
    assert geo["topDelta"] <= 2, geo
    assert 10 <= geo["iconH"] <= 14, geo


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
        expect(card.locator(".kol-card-meta")).to_have_text("财经" + ("-1.25%" if i == 1 else ""))
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
    assert icon.bounding_box()["width"] == 17
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
