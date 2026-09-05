"""MX观点页前端注册静态回归。"""
import re
from pathlib import Path

STATIC = Path(__file__).parent.parent / "app" / "static"
APP_JS = (STATIC / "app.js").read_text()
INDEX = (STATIC / "index.html").read_text()
# MX观点页已并入 ES 模块体系：由 app.js import，不再是独立 <script> 标签
MX_VIEWS_JS = (STATIC / "views" / "mx-views.js").read_text()


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
    # 版本号由 scripts/bump_assets.py 按内容摘要统一维护，不再手工 pin
    assert re.search(r'href="/mx-views\.css\?v=[0-9a-f]{12}"', INDEX)
    assert 'from "./views/mx-views.js"' in APP_JS
    assert 'src="/mx-views.js' not in INDEX  # 模块化后不再有独立 script 标签


def test_router_and_nav_register_mx_views():
    prefixes = APP_JS[APP_JS.index("const SPA_PREFIXES"):APP_JS.index("function routeStillActive")]
    assert '"mx-views"' in prefixes
    router = _fn_body("router")
    assert 'page === "mx-views"' in router and "renderMxViews" in router
    assert "mxvTeardown" in router  # 离开页面清理 SSE/定时器
    nav = APP_JS[APP_JS.index("const NAV ="):APP_JS.index("const SIDEBAR_SLIM_KEY")]
    assert 'route: "mx-views"' in nav and 'label: "智囊团"' in nav
    assert 'route: "admin/mx-views"' in nav and 'label: "智囊团"' in nav
    mobile = APP_JS[APP_JS.index("const MOBILE_NAV ="):APP_JS.index("function renderBottomNav")]
    assert 'route: "mx-views"' in mobile and 'label: "智囊团"' in mobile
    assert '"mx-views": loadAdminMxViews' in APP_JS
    # 页面/管理面板标题统一为「智囊团」
    assert 'setPageTitle("智囊团")' in MX_VIEWS_JS
    assert '<h2 class="section-title">智囊团</h2>' in MX_VIEWS_JS
    assert 'label: "MX观点"' not in nav


def test_open_raw_modal_falls_back_to_mxv_posts():
    body = _fn_body("openRawModal")
    assert "_mxvPosts" in body


def test_mx_views_assets_exist_with_scope():
    css = (STATIC / "mx-views.css").read_text()
    js = MX_VIEWS_JS
    assert ".mxv-root" in css
    assert "#0b0f1a" in css  # 暗色主题底色（.theme-dark 覆盖，页面跟随全局主题）
    assert "async function renderMxViews(" in js
    assert "window._mxvPosts" in js
    assert "/api/mx-views/stream" in js


def test_mx_views_skeleton_functions_exist():
    js = MX_VIEWS_JS
    for fn in ("renderMxViews", "mxvLoadDay", "mxvApplySnapshot", "mxvGoLatest",
               "mxvBindTimeline", "mxvEnsureSSE", "mxvTeardown"):
        assert f"function {fn}(" in js, fn
    assert "EventSource(" in js and "event: version" in js.replace("\\n", "\n") or "addEventListener" in js


def test_mx_views_timeline_is_click_drag_scrubber():
    """时间轴替代左右按钮：pointer 拖动 + 点按滑动，无 mxvStep。"""
    js = MX_VIEWS_JS
    assert "function mxvStep(" not in js  # 左右按钮已移除
    body = _fn_body("mxvTimelineHtml", js)
    assert "mxv-tl-track" in body and "mxvGoLatest()" in body
    assert "mxvStep(" not in body
    for fn in ("mxvTlDown", "mxvTlMove", "mxvTlUp", "mxvTlIdxFromX", "mxvTlPreview"):
        assert f"function {fn}(" in js, fn
    bind = _fn_body("mxvBindTimeline", js)
    assert "pointerdown" in bind
    down = _fn_body("mxvTlDown", js)
    assert "pointermove" in down and "pointerup" in down  # window 级拖动监听
    css = (STATIC / "mx-views.css").read_text()
    assert "touch-action:none" in css.replace(" ", "")  # 拖动不触发页面滚动


def test_mx_views_kol_overview_modes_and_collapse():
    """大V总览：今日操作下方、默认一行+更多展开、关注置顶、大V/个股切换。"""
    js = MX_VIEWS_JS
    root = _fn_body("mxvRootHtml", js)
    assert root.index("mxv-banner") < root.index("mxv-kols") < root.index("mxv-boards") < root.index("mxv-feed")
    for fn in ("mxvRenderKols", "mxvKolCardsHtml", "mxvStockCardsHtml",
               "mxvApplyKolCollapse", "mxvKolMode", "mxvKolMore", "mxvOpenKolStockAt"):
        assert f"function {fn}(" in js, fn
    kols = _fn_body("mxvRenderKols", js)
    assert "mxvKolMode('kol')" in kols and "mxvKolMode('stock')" in kols
    assert "mxvKolMore()" in kols and "mxvApplyKolCollapse" in kols
    kolcards = _fn_body("mxvKolCardsHtml", js)
    assert "_mxv.followed" in kolcards  # 关注大V置顶
    stocks = _fn_body("mxvStockCardsHtml", js)
    assert "b.bull + b.bear" in stocks  # 默认按大V人数降序
    collapse = _fn_body("mxvApplyKolCollapse", js)
    assert "scrollHeight" in collapse and "maxHeight" in collapse


def test_mx_views_feed_all_batches_and_drawer_desc():
    """实时观点流走全天 feed 接口；抽屉时间线最新在上。"""
    js = MX_VIEWS_JS
    assert "/api/mx-views/feed" in js
    feed = _fn_body("mxvRenderFeed", js)
    assert "mxv-feed-sep" in feed and "批次" in feed
    tl = _fn_body("mxvTimelineListHtml", js)
    assert "localeCompare" in tl  # 倒序排（最新在上）


def test_mx_views_feed_two_column_batch_layout():
    """实时观点流批内两列报纸流：左列装较新一半（顶部=最新），右列底部=最早；窄屏回落单列。"""
    js = MX_VIEWS_JS
    feed = _fn_body("mxvRenderFeed", js)
    assert "mxv-feed-cols" in feed and "mxv-feed-col" in feed
    assert "Math.ceil(" in feed  # 左列 = 较新一半（向上取整）
    assert "slice(0, cut)" in feed and "slice(cut)" in feed
    assert "single" in feed  # 单条批次不拆两列
    css = (STATIC / "mx-views.css").read_text().replace(" ", "")
    assert ".mxv-feed-cols{display:grid;grid-template-columns:1fr 1fr" in css
    assert "@media(max-width:760px)" in css and ".mxv-feed-cols{grid-template-columns:1fr" in css


def test_mx_views_target_highlight_linkage():
    """悬停/点选标的 → 观点流内同标的集体高亮放大；点击可锁定，Esc/点空白解除；双榜悬停同样联动。"""
    js = MX_VIEWS_JS
    assert 'data-mxv-hl=' in js  # feed 条目/双榜行/热力块/chip 均带标的键
    for fn in ("mxvSetHighlight", "mxvBindFeedHighlight", "mxvBindBoardHighlight"):
        assert f"function {fn}(" in js, fn
    setter = _fn_body("mxvSetHighlight", js)
    assert "classList.toggle" in setter and "dataset.mxvHl" in setter
    bind = _fn_body("mxvBindFeedHighlight", js)
    assert "pointerover" in bind and "pointerleave" in bind and "click" in bind
    assert "hlPinned" in bind  # 点击锁定/再点解除
    board = _fn_body("mxvBindBoardHighlight", js)
    assert "mxv-boards" in board and "mxv-banner" in board
    assert "Escape" in js  # Esc 解锁
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-feed-item.hl" in css
    compact = css.replace(" ", "")
    assert "scale(1.03)" in compact  # 放大一点
    assert "transition:background .15s" in compact  # 平滑过渡不跳变


def test_mx_views_boards_heat_view_default():
    """双榜默认热力标签云：提及总数降序，颜色=净方向、深浅/字号=热度；可切回明细列表。"""
    js = MX_VIEWS_JS
    assert "function mxvHeatHtml(" in js
    heat = _fn_body("mxvHeatHtml", js)
    assert "b.bull + b.bear" in heat  # 按提及总数降序
    assert "mxv-heat-wrap" in heat and "data-mxv-hl=" in heat
    assert "function mxvBoardMode(" in js and "function mxvBoardHead(" in js
    head = _fn_body("mxvBoardHead", js)
    assert "mxvBoardMode('${kind}','heat')" in head and "mxvBoardMode('${kind}','list')" in head
    boards = _fn_body("mxvRenderBoards", js)
    assert "题材多空榜" in boards and "个股强度榜" in boards
    assert 'boardMode.topic === "list"' in boards and 'boardMode.stock === "list"' in boards
    assert "mxvHeatHtml(p.topics" in boards and "mxvHeatHtml(p.stocks" in boards
    # 明细列表行仍保留（切换用），且带高亮键
    assert 'data-mxv-hl="topic:${escapeHtml(t.name)}"' in boards
    assert 'data-mxv-hl="stock:${escapeHtml(s.name)}"' in boards
    # 注册进工厂返回与 app.js 内联处理器
    assert "mxvBoardMode," in js.split("return {")[1]
    assert "mxvBoardMode," in APP_JS
    css = (STATIC / "mx-views.css").read_text()
    for cls in (".mxv-heat{", ".mxv-heat.bull{", ".mxv-heat.bear{", ".mxv-heat.h4{",
                ".mxv-heat.hl{", ".mxv-board-head{", ".mxv-heat-legend{"):
        assert cls in css.replace(" ", ""), cls


def test_mx_views_css_key_components():
    css = (STATIC / "mx-views.css").read_text()
    for cls in (".mxv-statusbar", ".mxv-timeline", ".mxv-tl-head", ".mxv-banner", ".mxv-chip",
                ".mxv-board", ".mxv-row", ".mxv-drawer", ".mxv-kolcard", "@keyframes mxvFlashIn"):
        assert cls in css, cls


def test_mx_views_theme_adaptive_and_more_in_head():
    """用户页跟随明暗主题（浅色默认 + .theme-dark 暗色覆盖）；更多/收起按钮在头部、切换按钮左侧。"""
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-root{" in css  # 浅色变量为默认
    assert ".theme-dark .mxv-root{" in css  # 暗色变量挂在主题类下
    for legacy in ("#101c33", "#1a2a4d", "#101a2e", "#131d33", "#2a3f6e"):
        # 深色只允许出现在 --mxv-* 调色板变量定义行，规则里一律走变量
        for line in css.splitlines():
            if legacy in line:
                assert "--mxv-" in line, f"{legacy} 出现在非变量行: {line.strip()}"
                break
        else:
            assert False, f"未找到 {legacy}（暗色调色板缺失）"
    assert ".mxv-more[hidden]{display:none;}" in css.replace(" ", "")  # hidden 不再被 display:block 抵消
    kols = _fn_body("mxvRenderKols", MX_VIEWS_JS)
    assert 0 < kols.index("mxv-kols-more") < kols.index("mxv-mode")  # 更多在按大V/按个股左侧
    root = _fn_body("mxvRootHtml", MX_VIEWS_JS)
    # 抽屉挂载点必须在 .mxv-root 内：抽屉颜色全走 --mxv-* 变量，挂在外面解析不到
    assert root.index('id="mxv-feed"') < root.index('id="mxv-drawer-slot"') < root.rindex("</div>")


def test_mx_views_boards_render_function():
    js = MX_VIEWS_JS
    body = _fn_body("mxvRenderBoards", js)
    for marker in ("mxv-banner", "mxv-boards", "mxv-chip", "mxvRenderKols", "mxvRenderFeed"):
        assert marker in body, marker
    # mxv-ratio 多空比例条由辅助函数 mxvRatioHtml 产出，渲染体以调用形式接入双榜
    assert "mxv-ratio" in _fn_body("mxvRatioHtml", js)
    assert body.count("mxvRatioHtml(") >= 2
    # 大V卡片 / 观点流条目渲染移入各自函数
    kols = _fn_body("mxvRenderKols", js)
    assert "mxvKolCardsHtml" in kols and "mxvStockCardsHtml" in kols
    feed = _fn_body("mxvRenderFeed", js)
    assert "mxv-feed-item" in feed and "mxvOpenKol" in _fn_body("mxvKolCardsHtml", js)


def test_mx_views_drawer_functions():
    js = MX_VIEWS_JS
    for fn in ("mxvOpenTarget", "mxvOpenKol", "mxvCloseDrawer"):
        assert f"function {fn}(" in js, fn
    body = _fn_body("mxvOpenTarget", js)
    assert "/api/mx-views/target" in body and "at=" in body
    kolbody = _fn_body("mxvOpenKol", js)
    assert "/api/mx-views/kol/" in kolbody
    allsrc = js
    assert "openRawModal(" in allsrc and "_mxvPosts" in allsrc


def test_admin_mx_views_page_function():
    js = MX_VIEWS_JS
    assert "async function loadAdminMxViews(" in js
    body = _fn_body("loadAdminMxViews", js)
    for marker in ("/api/admin/mx-views/config", "/api/admin/mx-views/status",
                   "mxvAdminSaveConfig", "mxvAdminStartBackfill", "mxvAdminAdopt"):
        assert marker in body, marker
    assert "admin-body" in body
