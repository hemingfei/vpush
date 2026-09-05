"""PWA Service Worker 静态回归测试：API 永不缓存，外壳仍可离线。"""
import re
from pathlib import Path
from scripts.bump_assets import asset_digest, module_urls

SW_JS = Path(__file__).parent.parent / "app" / "static" / "sw.js"
STATIC = SW_JS.parent
ROOT = Path(__file__).resolve().parents[1]


def test_fetch_handler_excludes_api_route():
    src = SW_JS.read_text()
    fetch_block = src[src.index('self.addEventListener("fetch"'):]
    assert re.search(r'pathname\.startsWith\("/api/"\)', fetch_block)
    assert '"/feed/"' not in fetch_block


def test_fetch_handler_still_guards_method_and_origin():
    src = SW_JS.read_text()
    fetch_block = src[src.index('self.addEventListener("fetch"'):]
    assert re.search(r'request\.method !== "GET"', fetch_block)
    assert re.search(r'url\.origin !== self\.location\.origin', fetch_block)


def test_fetch_handler_navigate_falls_back_to_shell():
    src = SW_JS.read_text()
    fetch_block = src[src.index('self.addEventListener("fetch"'):]
    assert 'request.mode === "navigate"' in fetch_block
    assert "networkFirstNavigate" in src
    nav = src[src.index("async function networkFirstNavigate"):]
    assert 'caches.match("/")' in nav


def test_shell_assets_and_registration_present():
    """离线外壳与注册入口仍存在。"""
    src = SW_JS.read_text()
    for marker in ("/manifest.webmanifest", 'caches.open(CACHE)', "networkFirst"):
        assert marker in src, f"sw.js 缺少 {marker}"
    # 前端注册 Service Worker 的入口仍在
    app_js = (SW_JS.parent / "app.js").read_text()
    assert 'navigator.serviceWorker.register("/sw.js")' in app_js


def test_sw_handles_push_and_notificationclick():
    src = SW_JS.read_text()
    assert 'self.addEventListener("push"' in src
    assert "showNotification" in src
    assert 'self.addEventListener("notificationclick"' in src
    assert "clients.openWindow" in src

def test_frontend_assets_match_financial_news_release_revision():
    html = (STATIC / "index.html").read_text()
    sw = SW_JS.read_text()
    app = (STATIC / "app.js").read_text()
    digest = asset_digest(ROOT)
    assert f'href="/style.css?v={digest}"' in html
    assert f'src="/app.js?v={digest}"' in html
    assert f'const CACHE = "dav-shell-{digest}";' in sw
    for url in module_urls(ROOT):
        assert f'"{url}"' in sw
    assert 'const APP_VERSION = "1.12.145";' in app


def test_pwa_icons_have_light_and_dark_sets():
    """安装图标需同时提供亮/暗两套 PNG，并在 manifest / HTML / SW 里接上。"""
    for name in (
        "icon-mark.svg",
        "icon-mark-dark.svg",
        "icon-192.png",
        "icon-512.png",
        "icon-192-dark.png",
        "icon-512-dark.png",
    ):
        path = STATIC / name
        assert path.is_file() and path.stat().st_size > 0, f"缺少 PWA 图标 {name}"

    manifest = (STATIC / "manifest.webmanifest").read_text()
    assert '"/icon-192.png"' in manifest
    assert '"/icon-512.png"' in manifest
    assert "maskable" in manifest

    html = (STATIC / "index.html").read_text()
    assert 'href="/icon-192.png"' in html
    assert 'href="/icon-192-dark.png"' in html
    assert 'media="(prefers-color-scheme: dark)"' in html
    assert 'href="/splash-ios-dark.png"' in html

    sw = SW_JS.read_text()
    assert "/icon-192-dark.png" in sw
    assert "/icon-512-dark.png" in sw


def test_status_bar_follows_app_theme():
    html = (STATIC / "index.html").read_text()
    assert 'name="apple-mobile-web-app-status-bar-style" content="default"' in html
    assert 'statusBar.content = dark ? "black-translucent" : "default"' in html
    app = (STATIC / "app.js").read_text()
    assert 'apple-mobile-web-app-status-bar-style' in app
    assert 'dark ? "black-translucent" : "default"' in app
    manifest = (STATIC / "manifest.webmanifest").read_text()
    assert '"theme_color": "#f8f8fb"' in manifest
    assert '"background_color": "#f8f8fb"' in manifest


def test_dark_manifest_for_theme_colored_status_bars():
    """部分安卓 PWA 独立窗口只认 manifest 静态 theme_color：
    必须有深色 manifest，且防闪脚本与 applyTheme 都会按主题切换链接。"""
    dark = (STATIC / "manifest-dark.webmanifest").read_text()
    assert '"theme_color": "#11141a"' in dark
    assert '"background_color": "#0f1115"' in dark
    assert "/icon-512-dark.png" in dark

    html = (STATIC / "index.html").read_text()
    assert 'id="manifest" rel="manifest" href="/manifest.webmanifest?v=2"' in html
    assert 'manifestLink.href = dark ? "/manifest-dark.webmanifest?v=2" : "/manifest.webmanifest?v=2"' in html

    app = (STATIC / "app.js").read_text()
    assert 'manifestLink.setAttribute("href", dark ? "/manifest-dark.webmanifest?v=2" : "/manifest.webmanifest?v=2")' in app

    sw = SW_JS.read_text()
    assert '"/manifest-dark.webmanifest"' in sw

    css = (STATIC / "style.css").read_text()
    assert "padding-top: env(safe-area-inset-top, 0px)" in css
