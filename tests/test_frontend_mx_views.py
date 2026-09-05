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
    # 手机底栏：智囊团紧挨「动态」右侧（与桌面导航一致），不落在广场后
    assert mobile.index('route: "timeline"') < mobile.index('route: "mx-views"') < mobile.index('route: "home"')
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
    """实时观点流走全天 feed 接口（按选定快照截断渲染）；抽屉时间线最新在上、带前端现算的翻转徽标。"""
    js = MX_VIEWS_JS
    assert "/api/mx-views/feed" in js
    feed = _fn_body("mxvRenderFeed", js)
    assert "mxv-feed-sep" in feed and "批次" in feed
    tl = _fn_body("mxvTimelineListHtml", js)
    assert "localeCompare" in tl  # 倒序排（最新在上）
    assert "mxvFlipBadge(rows" in tl  # 翻转徽标与同 (大V,标的) 上一条现算比对
    assert "function mxvFlipBadge(" in js
    badge = _fn_body("mxvFlipBadge", js)
    assert "kol_id" in badge and "target_name" in badge and "prev.direction !== op.direction" in badge


def test_mx_views_feed_cutoff_at_selected_snapshot():
    """快照语义：回看时观点流只显示首批次→选定批次（≤选定时刻），其后批次不显示；标题注明截止。"""
    feed = _fn_body("mxvRenderFeed", MX_VIEWS_JS)
    assert "filter((b) => !at || String(b.snapshot_at) <= at)" in feed  # 截断选定时刻之后的批次
    assert "截至" in feed and "_mxv.atLatest" in feed  # 回看时标题注明截止时刻；最新快照不注
    # 批次统计（共 X 条 · Y 批次）基于截断后的数组
    assert feed.index("const batches =") < feed.index("const total =")


def test_mx_views_feed_two_column_batch_layout():
    """实时观点流批内两列报纸流：左列装较新一半（顶部=最新），右列底部=最早；窄屏回落单列。"""
    js = MX_VIEWS_JS
    feed = _fn_body("mxvRenderFeed", js)
    assert "mxv-feed-cols" in feed and "mxv-feed-col" in feed
    assert "Math.ceil(" in feed  # 左列 = 较新一半（向上取整）
    assert "slice(0, cut)" in feed and "slice(cut)" in feed
    assert "single" in feed  # 单条批次不拆两列
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-feed-cols{display:grid;grid-template-columns:1fr 1fr" in css
    compact = css.replace(" ", "")
    assert "@media(max-width:760px)" in compact and ".mxv-feed-cols{grid-template-columns:1fr" in compact


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
    assert "transition:background .15s" in css  # 平滑过渡不跳变


def test_mx_views_boards_heat_view_default():
    """双榜默认热力标签云：提及总数降序，颜色=净方向、深浅/字号=热度；可切回明细列表。"""
    js = MX_VIEWS_JS
    assert "function mxvHeatHtml(" in js
    # 热力与明细共用的排序：提及大V总数（多+空+中）降序 → |净多空| 降序
    assert ("const mxvByHeat = (a, b) => (b.bull + b.bear + (b.neutral || 0))"
            " - (a.bull + a.bear + (a.neutral || 0))") in js
    heat = _fn_body("mxvHeatHtml", js)
    assert "sort(mxvByHeat)" in heat  # 按提及总数降序
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
    # 注册进工厂返回与 app.js 内联处理器（工厂 return 是文件里最后一个 return {）
    assert "mxvBoardMode," in js.rsplit("return {", 1)[1]
    assert "mxvBoardMode," in APP_JS
    css = (STATIC / "mx-views.css").read_text()
    for cls in (".mxv-heat{", ".mxv-heat.bull{", ".mxv-heat.bear{", ".mxv-heat.h4{",
                ".mxv-heat.hl{", ".mxv-board-head{", ".mxv-heat-legend{"):
        assert cls in css.replace(" ", ""), cls


def test_mx_views_board_list_matches_heat_order_and_stock_bull_bear():
    """明细排序与热力一致；个股明细不打分，改用与题材榜一致的多空列，操作列保留最右。"""
    js = MX_VIEWS_JS
    boards = _fn_body("mxvRenderBoards", js)
    assert boards.count("sort(mxvByHeat)") == 2  # 题材 + 个股明细都按热力排序
    assert "${s.bull}多/${s.neutral || 0}中/${s.bear}空" in boards  # 个股明细多/中/空三段与题材榜同款
    assert "strength" not in boards  # 明细不再显示打分
    assert '<span class="mxv-actions">' in boards  # 操作列保留在最右
    assert boards.index("中/${s.bear}空") < boards.index('<span class="mxv-actions">')  # 多空中在操作前


def test_mx_views_board_list_more_limit():
    """双榜明细默认最多 20 条，超出出「更多」展开全部/「收起」折回；切视图与重进页面重置。"""
    js = MX_VIEWS_JS
    assert "const MXV_BOARD_LIST_LIMIT = 20;" in js
    boards = _fn_body("mxvRenderBoards", js)
    assert boards.count("slice(0, MXV_BOARD_LIST_LIMIT)") == 2  # 题材 + 个股都截断
    assert "boardExpanded" in boards and "mxvBoardMore('${kind}')" in boards
    assert "收起 ▴" in boards and "更多 ▾" in boards  # 展开态切换文案
    more = _fn_body("mxvBoardMore", js)
    assert "boardExpanded[kind] = !_mxv.boardExpanded[kind]" in more
    mode = _fn_body("mxvBoardMode", js)
    assert "_mxv.boardExpanded[kind] = false" in mode  # 热力/明细切换重置折叠
    teardown = _fn_body("mxvTeardown", js)
    assert "boardExpanded" in teardown  # 重进页面回到默认折叠
    # 注册进工厂返回与 app.js 内联处理器
    exported = js.rsplit("return {", 1)[1]
    assert "mxvBoardMore," in exported and "mxvBoardMore," in APP_JS
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-board .mxv-more{" in css  # 后代选择器含空格，用原文断言


def test_mx_views_neutral_counts_everywhere():
    """中性大V全链路可见：明细行 多/空/中，热力徽标 净/总数(含中)，抽屉顶部中立统计，大V/个股卡片中性段。"""
    js = MX_VIEWS_JS
    boards = _fn_body("mxvRenderBoards", js)
    assert "${t.bull}多/${t.neutral || 0}中/${t.bear}空" in boards  # 题材明细三段计数（多/中/空）
    assert "${s.bull}多/${s.neutral || 0}中/${s.bear}空" in boards  # 个股明细同款
    assert boards.count("mxvRatioHtml(t.bull, t.bear, t.neutral || 0)") == 1  # 比例条中段传中性
    assert boards.count("mxvRatioHtml(s.bull, s.bear, s.neutral || 0)") == 1
    ratio = _fn_body("mxvRatioHtml", js)
    assert '<div class="n" style="width:${np}%"></div>' in ratio  # 中段黄色块（.mxv-ratio .n 上色）
    assert "看多${bull} 中立${neutral} 看空${bear}" in ratio  # 无障碍标签含中立
    heat = _fn_body("mxvHeatHtml", js)
    assert "<b>${total}</b>${escapeHtml(r.name)}<b>${net}</b>" in heat  # 布局 = (多+空+中) 名称 (多-空)
    assert "const all = (r) => r.bull + r.bear + (r.neutral || 0);" in heat  # 热度与总数含中性
    assert "中${r.neutral || 0}" in heat  # tooltip 含中性
    drawer = _fn_body("mxvOpenTarget", js)
    assert "中 · 截至" in drawer and "◎ 中立 ${neu.count}" in drawer  # 抽屉顶部中立统计+名单
    kolcards = _fn_body("mxvKolCardsHtml", js)
    assert 'class="n" style="width:${Math.round((n / tot) * 100)}%"' in kolcards  # 比例条中性段
    assert "neutral_names" in kolcards and "◎" in kolcards  # 名单加中立行
    stockcards = _fn_body("mxvStockCardsHtml", js)
    assert "neutralMap" in stockcards and "namesLine(neutralNames, sNeu" in stockcards
    assert "${s.bull + s.bear + sNeu} 大V" in stockcards  # 大V计数含中性
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-kolcard .mini .n{background:var(--mxv-faint);}" in css  # 后代选择器含空格，用原文断言
    assert ".mxv-ratio .n{background:var(--mxv-gold);}" in css  # 比例条中段=黄色中性


def test_mx_views_day_picker_is_calendar():
    """顶部交易日选择为真实月历弹层：周一起始网格、可翻月、仅有数据日可点；不再用 select 下拉。"""
    js = MX_VIEWS_JS
    root = _fn_body("mxvRootHtml", js)
    assert "<select" not in root  # 下拉已替换
    assert 'id="mxv-day-btn"' in root and "mxvCalToggle()" in root
    assert 'id="mxv-cal-slot"' in root  # 弹层挂载点在 .mxv-root 内（继承主题变量）
    assert root.index('id="mxv-cal-slot"') < root.index('id="mxv-drawer-slot"')
    for fn in ("mxvCalToggle", "mxvCalClose", "mxvCalNav", "mxvCalPick", "mxvCalRender", "mxvCalHtml"):
        assert f"function {fn}(" in js, fn
    cal = _fn_body("mxvCalHtml", js)
    assert cal.index('"一"') < cal.index('"日"')  # 周一起始的星期表头
    assert "mxvCalNav(-1)" in cal and "mxvCalNav(1)" in cal  # 上/下月导航
    assert "new Set(_mxv.days)" in cal and "disabled" in cal  # 无数据日禁用
    assert "mxvCalPick(" in cal
    # 选择：关弹层 + 换日路由；Esc/点外关闭；离开页面清理
    pick = _fn_body("mxvCalPick", js)
    assert "mxvCalClose()" in pick and "mxvPickDay(" in pick
    assert 'closest("#mxv-day-btn")' in js  # 点外关闭白名单
    assert "mxvCalClose()" in _fn_body("mxvTeardown", js)
    # 注册：工厂返回 + app.js 内联处理器
    exported = js.rsplit("return {", 1)[1]
    for fn in ("mxvCalToggle", "mxvCalNav", "mxvCalPick"):
        assert f"{fn}," in exported, fn
        assert f"{fn}," in APP_JS, fn
    css = (STATIC / "mx-views.css").read_text()
    for cls in (".mxv-cal{", ".mxv-cal .cal-grid{", ".mxv-cal .cal-d.has{", ".mxv-cal .cal-d.sel{"):
        assert cls in css, cls  # 后代选择器含空格，用原文断言


def test_mx_views_banner_evolution_advice_and_chips_momentum():
    """横幅总结两层渲染：evolution/advice 带标签，老快照无新字段回退单 text；chip 带动量箭头。"""
    boards = _fn_body("mxvRenderBoards", MX_VIEWS_JS)
    assert "s.evolution" in boards and "s.advice" in boards
    assert "mxv-sum-tag" in boards
    assert "legacy" in boards  # 无演变/建议时回退旧 text（历史快照兼容）
    chips = _fn_body("mxvChipsHtml", MX_VIEWS_JS)
    assert "it.momentum" in chips and "mxvMomo(momo)" in chips  # 动量箭头
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-badge.flip{" in css.replace(" ", "") or ".mxv-badge.flip" in css
    assert ".mxv-sum-tag" in css


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
    # 大V卡片 / 观点流条目渲染移入各自函数；条目模板含标的高亮键与两列容器
    kols = _fn_body("mxvRenderKols", js)
    assert "mxvKolCardsHtml" in kols and "mxvStockCardsHtml" in kols
    feed = _fn_body("mxvRenderFeed", js)
    assert "mxvFeedItemHtml" in feed
    assert "mxv-feed-item" in _fn_body("mxvFeedItemHtml", js)
    assert "mxvOpenKol" in _fn_body("mxvKolCardsHtml", js)


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
