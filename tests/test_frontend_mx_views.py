"""MX观点页前端注册静态回归。"""
from pathlib import Path

STATIC = Path(__file__).parent.parent / "app" / "static"
APP_JS = (STATIC / "app.js").read_text()
INDEX = (STATIC / "index.html").read_text()


def _fn_body(name: str, src: str = APP_JS) -> str:
    import re

    m = re.search(rf"async\s+function\s+{name}\b|function\s+{name}\b", src)
    assert m, f"未找到函数 {name}"
    start = src.index("{", src.index("(", m.end()))
    depth, i = 1, start + 1
    while depth:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[start:i]


def test_index_html_includes_mx_views_assets():
    assert 'href="/mx-views.css?v=1"' in INDEX
    assert 'src="/mx-views.js?v=1"' in INDEX


def test_router_and_nav_register_mx_views():
    prefixes = APP_JS[APP_JS.index("const SPA_PREFIXES"):APP_JS.index("function routeStillActive")]
    assert '"mx-views"' in prefixes
    router = _fn_body("router")
    assert 'page === "mx-views"' in router and "renderMxViews" in router
    nav = APP_JS[APP_JS.index("const NAV ="):APP_JS.index("const SIDEBAR_SLIM_KEY")]
    assert 'route: "mx-views"' in nav and 'label: "MX观点"' in nav
    assert 'route: "admin/mx-views"' in nav and 'label: "MX观点"' in nav
    mobile = APP_JS[APP_JS.index("const MOBILE_NAV ="):APP_JS.index("function renderBottomNav")]
    assert 'route: "mx-views"' in mobile
    assert '"mx-views": loadAdminMxViews' in APP_JS


def test_open_raw_modal_falls_back_to_mxv_posts():
    body = _fn_body("openRawModal")
    assert "_mxvPosts" in body


def test_mx_views_assets_exist_with_scope():
    css = (STATIC / "mx-views.css").read_text()
    js = (STATIC / "mx-views.js").read_text()
    assert ".mxv-root" in css
    assert "#0b0f1a" in css  # 固定暗底，不随主题
    assert "async function renderMxViews(" in js
    assert "window._mxvPosts" in js
    assert "/api/mx-views/stream" in js


def test_mx_views_skeleton_functions_exist():
    js = (STATIC / "mx-views.js").read_text()
    for fn in ("renderMxViews", "mxvLoadDay", "mxvApplySnapshot", "mxvGoLatest",
               "mxvStep", "mxvEnsureSSE", "mxvTeardown"):
        assert f"function {fn}(" in js, fn
    assert "EventSource(" in js and "event: version" in js.replace("\\n", "\n") or "addEventListener" in js


def test_mx_views_css_key_components():
    css = (STATIC / "mx-views.css").read_text()
    for cls in (".mxv-statusbar", ".mxv-timeline", ".mxv-tl-head", ".mxv-banner", ".mxv-chip",
                ".mxv-board", ".mxv-row", ".mxv-drawer", ".mxv-kolcard", "@keyframes mxvFlashIn"):
        assert cls in css, cls


def test_mx_views_boards_render_function():
    js = (STATIC / "mx-views.js").read_text()
    body = _fn_body("mxvRenderBoards", js)
    for marker in ("mxv-banner", "mxv-boards", "mxv-chip", "mxv-kolcard",
                   "mxvOpenTarget", "mxvOpenKol", "mxv-feed-item"):
        assert marker in body, marker
    # mxv-ratio 多空比例条由辅助函数 mxvRatioHtml 产出，渲染体以调用形式接入双榜
    assert "mxv-ratio" in _fn_body("mxvRatioHtml", js)
    assert body.count("mxvRatioHtml(") >= 2
