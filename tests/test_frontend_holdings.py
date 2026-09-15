"""持股研判页前端注册静态回归（照 test_frontend_mx_views.py 体例）。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
HOLDINGS_JS = (STATIC / "views" / "holdings.js").read_text(encoding="utf-8")
HOLDINGS_CSS = (STATIC / "holdings.css").read_text(encoding="utf-8")
MAIN_PY = (ROOT / "app" / "main.py").read_text(encoding="utf-8")

# 视图导出且必须注册进 INLINE_HANDLERS 的内联 handler（check_inline_handlers.py 同一契约）
HD_HANDLERS = [
    "hdAddType", "hdSugInput", "hdSugPick", "hdAddSubmit", "hdEditOpen",
    "hdEditSave", "hdEditCancel", "hdDelete", "hdFilter", "hdExpand", "hdMore",
]


def _fn_body(name: str, src: str = APP_JS) -> str:
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


def test_index_html_includes_holdings_assets():
    # 版本号由 scripts/bump_assets.py 按内容摘要统一维护
    assert re.search(r'href="/holdings\.css\?v=[0-9a-f]{12}"', INDEX)
    assert ".hd-root" in HOLDINGS_CSS  # 页面级样式自包含，全部 .hd- 前缀
    assert "--mxv-" not in HOLDINGS_CSS  # 不复用/不改动静色页样式变量


def test_router_and_nav_register_holdings():
    prefixes = APP_JS[APP_JS.index("const SPA_PREFIXES"):APP_JS.index("function routeStillActive")]
    assert '"holdings"' in prefixes
    router = _fn_body("router")
    assert 'page === "holdings"' in router and "renderHoldings" in router
    nav = APP_JS[APP_JS.index("const NAV ="):APP_JS.index("const SIDEBAR_SLIM_KEY")]
    assert 'route: "holdings"' in nav and 'label: "持股研判"' in nav
    mobile = APP_JS[APP_JS.index("const MOBILE_NAV ="):APP_JS.index("function renderBottomNav")]
    assert 'route: "holdings"' in mobile and 'label: "持股"' in mobile
    # 底栏顺序：观点研判 → 持股 → 广场（与桌面「订阅」组相邻关系一致）
    assert (mobile.index('route: "mx-views"') < mobile.index('route: "holdings"')
            < mobile.index('route: "home"'))
    # 后端 SPA 前缀同步（否则刷新 /holdings 直落 404）
    assert '"holdings"' in MAIN_PY


def test_holdings_factory_wiring_and_inline_handlers():
    assert 'import { createHoldingsView } from "./views/holdings.js"' in APP_JS
    assert "createHoldingsView({" in APP_JS  # 工厂接线（frontend-split-convention）
    assert "export function createHoldingsView(dependencies)" in HOLDINGS_JS
    assert "HOLDINGS_ICON" in APP_JS and "HOLDINGS_ICON" in (STATIC / "core" / "icons.js").read_text(encoding="utf-8")
    inline = APP_JS[APP_JS.index("const INLINE_HANDLERS"):]
    for name in HD_HANDLERS:
        assert re.search(rf"export function {name}\b|function {name}\b", HOLDINGS_JS), name
        assert re.search(rf"^\s+{name},$", inline, re.M), name


def test_holdings_page_contract_basics():
    body = _fn_body("renderHoldings", HOLDINGS_JS)
    assert 'setPageTitle("持股研判")' in body
    assert "/api/my/holdings/views" in HOLDINGS_JS
    assert "/api/mx-views/stream" in HOLDINGS_JS  # 复用观点研判版本号 SSE
    assert "hdTeardown" in HOLDINGS_JS  # 离开页面清理 SSE/定时器
    # 加载更多走 before_id 翻旧页，实时增量走 after_id
    assert "before_id" in HOLDINGS_JS and "after_id" in HOLDINGS_JS
