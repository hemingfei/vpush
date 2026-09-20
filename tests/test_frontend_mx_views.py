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
    # 内容哈希 URL 由 scripts/bump_assets.py 按文件哈希统一维护，不再手工 pin
    assert re.search(r'href="/mx-views\.[0-9a-f]{12}\.css"', INDEX)
    assert 'from "./views/mx-views.js"' in APP_JS
    assert 'src="/mx-views.js' not in INDEX  # 模块化后不再有独立 script 标签


def test_router_and_nav_register_mx_views():
    prefixes = APP_JS[APP_JS.index("const SPA_PREFIXES"):APP_JS.index("function routeStillActive")]
    assert '"mx-views"' in prefixes
    router = _fn_body("router")
    assert 'page === "mx-views"' in router and "renderMxViews" in router
    assert "mxvTeardown" in router  # 离开页面清理 SSE/定时器
    nav = APP_JS[APP_JS.index("const NAV ="):APP_JS.index("const SIDEBAR_SLIM_KEY")]
    assert 'route: "mx-views"' in nav and 'label: "观点研判"' in nav
    assert 'route: "admin/mx-views"' in nav and 'label: "观点研判"' in nav
    mobile = APP_JS[APP_JS.index("const MOBILE_NAV ="):APP_JS.index("function renderBottomNav")]
    assert 'route: "mx-views"' in mobile and 'label: "研判"' in mobile
    # 手机底栏：研判紧挨「动态」（与桌面导航一致），不落在广场后
    assert mobile.index('route: "timeline"') < mobile.index('route: "mx-views"') < mobile.index('route: "home"')
    assert '"mx-views": loadAdminMxViews' in APP_JS
    # 页面标题随视口宽度在「研判/观点研判」间取用，管理面板标题为「观点研判」
    assert 'setPageTitle(' in MX_VIEWS_JS and '"观点研判"' in MX_VIEWS_JS
    assert '<h2 class="section-title">观点研判</h2>' in MX_VIEWS_JS
    assert 'label: "MX观点"' not in nav


def test_open_raw_modal_falls_back_to_mxv_posts():
    body = _fn_body("openRawModal")
    assert "_mxvPosts" in body


def test_mxv_evidence_raw_button_admin_only():
    """证据帖「查看原始消息」按钮仅管理员渲染，普通账号不显示 MX 原始消息入口。"""
    body = _fn_body("mxvEvidenceHtml", MX_VIEWS_JS)
    assert "state.user?.is_admin" in body
    assert "'MX原始消息'" in body


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
    # 手机单列默认露 4 张：单列检测后按第 5 张上缘定限高，张数常量=4
    assert "singleCol" in collapse and "MXV_KOL_COLLAPSE_ROWS" in collapse
    assert re.search(r"MXV_KOL_COLLAPSE_ROWS = 4", js)


def test_mx_views_feed_half_hour_groups_and_drawer_desc():
    """实时观点流走全天 feed 接口（按选定快照截断渲染），展示按观点发生时间取整到
    整点/半点（00/30）分时段（不再按研判批次分组）；抽屉时间线最新在上、带前端现算的翻转徽标。"""
    js = MX_VIEWS_JS
    assert "/api/mx-views/feed" in js
    feed = _fn_body("mxvRenderFeed", js)
    assert "mxv-feed-sep" in feed and "时段" in feed
    assert "mxvFeedBucketKey(o.occurred_at)" in feed  # 分桶键=观点发生时间（非批次时刻）
    assert "b.key.localeCompare(a.key)" in feed  # 新时段在前，缺时间兜底组垫底
    assert "`${g.label}~${g.end}`" in feed  # 分隔行标出半小时区间
    assert "groups.length < poolBuckets.size" in feed  # 汇总行注明筛选隐藏的时段数
    bucket = _fn_body("mxvFeedBucketKey", js)
    assert "start % 30" in bucket  # 向下取整到整点/半点
    assert "/^(\\d{4}-\\d{2}-\\d{2}) (\\d{2}):(\\d{2})/" in bucket  # key 含日期防跨日串组
    tl = _fn_body("mxvTimelineListHtml", js)
    assert "localeCompare" in tl  # 倒序排（最新在上）
    assert "mxvFlipBadge(rows" in tl  # 翻转徽标与同 (大V,标的) 上一条现算比对
    assert "function mxvFlipBadge(" in js
    badge = _fn_body("mxvFlipBadge", js)
    assert "kol_id" in badge and "target_name" in badge and "prev.direction !== op.direction" in badge


def test_mx_views_feed_cutoff_at_selected_snapshot():
    """快照语义：回看时观点流只显示首批次→选定批次（≤选定时刻），其后批次不显示；标题注明截止。"""
    pool = _fn_body("mxvFeedPool", MX_VIEWS_JS)
    assert "filter((b) => !at || String(b.snapshot_at) <= at)" in pool  # 截断选定时刻之后的批次
    feed = _fn_body("mxvRenderFeed", MX_VIEWS_JS)
    assert "mxvFeedPool()" in feed and "截至" in feed and "_mxv.atLatest" in feed  # 回看时标题注明截止时刻
    # 时段统计基于截断后的 pool（flat/allFlat 均出自 mxvFeedPool 结果）
    assert feed.index("mxvFeedPool()") < feed.index("mxvFeedFlat(pool)")


def test_mx_views_feed_two_column_batch_layout():
    """实时观点流时段内两列报纸流：左列装较新一半（顶部=最新），右列底部=最早；窄屏回落单列。"""
    js = MX_VIEWS_JS
    feed = _fn_body("mxvRenderFeed", js)
    assert "mxv-feed-cols" in feed and "mxv-feed-col" in feed
    assert "Math.ceil(" in feed  # 左列 = 较新一半（向上取整）
    assert "slice(0, cut)" in feed and "slice(cut)" in feed
    assert "single" in feed  # 单条时段不拆两列
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
    assert "mxvHeatHtml(topicSorted" in boards and "mxvHeatHtml(stockSorted" in boards  # 回填中性后再渲染
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
    assert '${s.bull}多/<span class="neu">${s.neutral || 0}中</span>/${s.bear}空' in boards  # 多/中/空，中与图形同色
    assert "strength" not in boards  # 明细不再显示打分
    assert '<span class="mxv-actions"' in boards  # 操作列保留在最右
    assert boards.index('/${s.bear}空</span>') < boards.index('<span class="mxv-actions"')  # 多空中在操作前
    assert 'title="${escapeHtml(actions)}"' in boards  # 操作列定宽截断时 hover 看全文
    css = (STATIC / "mx-views.css").read_text()
    # 操作列定宽：长短不一的操作文字不挤压 flex:1 比例条，红黄绿图与多/中/空列纵向对齐
    assert (".mxv-row .mxv-actions{width:96px;flex:none;overflow:hidden;text-overflow:ellipsis;"
            "white-space:nowrap;cursor:pointer;}") in css


def test_mx_views_board_list_more_limit():
    """双榜明细默认最多 4 条，「更多」按同步步进展开（两榜联动，每次+4）；热力/明细切换与重进页面重置。"""
    js = MX_VIEWS_JS
    assert "const MXV_BOARD_LIST_LIMIT = 4;" in js and "const MXV_HEAT_ROWS = 4;" in js
    boards = _fn_body("mxvRenderBoards", js)
    assert "MXV_BOARD_LIST_LIMIT * _mxv.boardStep" in boards  # 两榜共用同步步进
    assert "mxvBoardMore('${kind}')" in boards
    assert "收起 ▴" in boards and "更多 ▾" in boards and "data-heat-more" in boards  # 热力按钮测量后亮出
    more = _fn_body("mxvBoardMore", js)
    assert "_mxv.boardStep = canMore ? _mxv.boardStep + 1 : 1;" in more  # 任一榜更多=同步一档；收起=一起回默认
    mode = _fn_body("mxvBoardMode", js)
    assert "_mxv.boardStep = 1;" in mode  # 热力/明细切换重置折叠
    teardown = _fn_body("mxvTeardown", js)
    assert "boardStep: 1" in teardown  # 重进页面回到默认折叠
    # 注册进工厂返回与 app.js 内联处理器
    exported = js.rsplit("return {", 1)[1]
    assert "mxvBoardMore," in exported and "mxvBoardMore," in APP_JS
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-board .mxv-more{" in css  # 后代选择器含空格，用原文断言


def test_mx_views_neutral_counts_everywhere():
    """中性大V全链路可见：明细行 多/空/中，热力徽标 净/总数(含中)，抽屉顶部中立统计，大V/个股卡片中性段。"""
    js = MX_VIEWS_JS
    boards = _fn_body("mxvRenderBoards", js)
    assert '${t.bull}多/<span class="neu">${t.neutral || 0}中</span>/${t.bear}空' in boards  # 题材明细多/中/空
    assert '${s.bull}多/<span class="neu">${s.neutral || 0}中</span>/${s.bear}空' in boards  # 个股明细同款
    assert boards.count("mxvRatioHtml(t.bull, t.bear, t.neutral || 0)") == 1  # 比例条中段传中性
    assert boards.count("mxvRatioHtml(s.bull, s.bear, s.neutral || 0)") == 1
    ratio = _fn_body("mxvRatioHtml", js)
    assert '<div class="n" style="width:${np}%"></div>' in ratio  # 中段黄色块（.mxv-ratio .n 上色）
    assert "看多${bull} 中立${neutral} 看空${bear}" in ratio  # 无障碍标签含中立
    heat = _fn_body("mxvHeatHtml", js)
    assert 'max = Math.max(1, ...sorted.map((r) => r.bull + r.bear + (r.neutral || 0)))' in heat  # 热度含中性
    assert '中${r.neutral || 0}' in heat  # tooltip 含中性
    drawer = _fn_body("mxvRenderDrawerBody", js)
    assert "中 · 截至" in drawer and "◎ 中立 ${neu.count}" in drawer  # 抽屉顶部中立统计+名单
    kolcards = _fn_body("mxvKolCardsHtml", js)
    assert 'class="n" style="width:${Math.round((n / tot) * 100)}%"' in kolcards  # 比例条中性段
    assert "neutral_names" in kolcards and "◎" in kolcards  # 名单加中立行
    assert "stats.byKol" in kolcards  # 旧快照无 neutral_names 时用 feed 现算兜底
    stockcards = _fn_body("mxvStockCardsHtml", js)
    assert "neutralMap" in stockcards and "namesLine(neutralNames, sNeu" in stockcards
    assert "${s.bull + s.bear + sNeu} 大V" in stockcards  # 大V计数含中性
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-kolcard .mini .n{background:var(--mxv-muted);}" in css  # 后代选择器含空格，用原文断言
    assert ".mxv-ratio .n{background:var(--mxv-muted);}" in css  # 比例条中段与文字「中」同色
    assert ".mxv-net .neu{color:var(--mxv-muted);}" in css


def test_mx_views_neutral_backfill_from_feed_and_actions_expand():
    """旧快照 payload 无 neutral：由 feed 观点按当前立场口径现算回填（≤选定快照、首 hit=最新立场）；
    明细操作列截断时点击展开多行/再点收回，未截断不拦截行点击。"""
    js = MX_VIEWS_JS
    stats = _fn_body("mxvNeutralStats", js)
    assert "String(b.snapshot_at) > at" in stats  # 只统计 ≤ 选定快照的批次
    assert "!(key in latest)" in stats  # 批次倒序+批内倒序：首 hit 即最新立场
    assert "counts[`${ttype}:${name}`]" in stats and "byKol" in stats
    fill = _fn_body("mxvFillNeutral", js)
    assert "r.neutral != null" in fill  # 新快照有字段用字段，旧快照现算兜底
    boards = _fn_body("mxvRenderBoards", js)
    assert 'map(mxvFillNeutral("topic", stats))' in boards and 'map(mxvFillNeutral("stock", stats))' in boards
    feed = _fn_body("mxvLoadFeed", js)
    assert "mxvRenderBoards(false)" in feed  # feed 到达后重渲染双榜回填中性数；feed 已自行渲染，传 false 不重复渲染
    toggle = _fn_body("mxvActionsToggle", js)
    assert "stopPropagation()" in toggle and 'classList.toggle("open")' in toggle
    assert "scrollWidth" in toggle  # 未截断不拦截，行点击照常打开抽屉
    assert 'onclick="mxvActionsToggle(this,event)"' in boards
    exported = js.rsplit("return {", 1)[1]
    assert "mxvActionsToggle," in exported and "mxvActionsToggle," in APP_JS
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-row .mxv-actions.open{" in css  # 展开态换行显示全部（后代选择器用原文断言）


def test_mx_views_heat_two_rows_and_row_clamp():
    """热力标签卡两行：上=名称+净多空，下=多中空迷你条（条上居中总数）；默认最多 10 行，溢出才亮「更多」。"""
    js = MX_VIEWS_JS
    heat = _fn_body("mxvHeatHtml", js)
    assert '<span class="r1">${escapeHtml(r.name)}<b>${net}</b></span>' in heat  # 行1 = 名称+净多空
    assert '<span class="r2">${segs}<em>${total}</em></span>' in heat  # 行2 = 多中空条+居中总数
    assert 'data-kind="${type}"' in heat  # 限高测量按榜定位
    clamp = _fn_body("mxvApplyHeatClamp", js)
    assert "MXV_HEAT_ROWS" in clamp and "scrollHeight" in clamp  # 溢出测量
    assert 'classList.add("clamped")' in clamp and "hidden = false" in clamp  # 限高并亮出更多
    render = _fn_body("mxvRenderBoards", js)
    assert "mxvApplyHeatClamp();" in render  # 渲染后测量限高
    resize = _fn_body("mxvBindKolResize", js)
    assert "mxvApplyHeatClamp()" in resize  # 窗口变化重测
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-heat{display:inline-flex;flex-direction:column;" in css  # 两行卡片
    assert ".mxv-heat-wrap.clamped{overflow:hidden;}" in css  # 限高裁切
    assert ".mxv-heat .r2 em{" in css  # 条上居中总数
    assert ".mxv-heat .r2 i.n{background:var(--mxv-muted);}" in css  # 迷你条中段与明细同色
    # 全档统一软底+描边：不再有实底色档（实底与迷你条同色相撞、总数看不清），热度只用字号/字重区分
    assert ".mxv-heat.bull.h3{background:" not in css and ".mxv-heat.bear.h4{background:" not in css
    assert ".mxv-heat.h3,.mxv-heat.h4{font-weight:700;}" in css


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


def test_admin_mx_views_kol_dropdown_multiselect_keeps_open():
    """分析大V范围下拉：勾选后菜单保持展开，可连续多选。

    勾选会 innerHTML 重建 #mxva-kol-items，被点条目随即脱离 DOM；点击冒泡到 document
    时 e.target 已游离，点外判定会查不到元素而误判关闭。docClick 必须忽略游离目标；
    点外收起还必须限定在自身面板（.mxva-kol-wrap）内，不能越权关掉别处同款菜单。
    """
    js = MX_VIEWS_JS
    bind = _fn_body("mxvAdminBind", js)
    assert "isConnected" in bind  # 游离目标（勾选后列表重建所致）不参与点外判定
    assert "wrap.contains(e.target)" in bind  # 点外判定限定自身面板内（querySelector .mxva-kol-wrap）
    assert 'classList.remove("open")' in bind  # 真正点外仍要收起
    toggle = _fn_body("mxvAdminKolToggleItem", js)
    assert "open" not in toggle  # 勾选本身不得收起菜单


def test_admin_topic_candidates_use_index_delegation():
    """新题材候选按钮不带内联 JS 字符串：只带下标，点击时从 cfg.topic_candidates 取名字。

    escapeHtml 会把 `'` 转成 `&#39;`，但浏览器解析 HTML 属性时先解码实体再交给 JS 引擎，
    LLM 自由文本题材名含撇号即按钮 SyntaxError，含 `');` 序列即任意 JS 执行。
    """
    js = MX_VIEWS_JS
    assert "mxvAdminAdopt('${escapeHtml(c)}')" not in js  # 名称不得拼进内联 JS 字符串
    assert "mxvAdminDismiss('${escapeHtml(c)}')" not in js
    body = _fn_body("loadAdminMxViews", js)
    assert 'data-cand-idx="${i}"' in body
    assert 'data-cand-act="adopt"' in body and 'data-cand-act="dismiss"' in body
    bind = _fn_body("mxvAdminBind", js)
    assert 'closest("[data-cand-idx]")' in bind  # #mxva-cands 容器上事件委托
    assert "topic_candidates" in bind  # 名字在点击时从 cfg 取，服务端数据不进 JS 上下文


def test_mx_views_timeline_drag_survives_sse_and_poll():
    """拖动时间轴中：SSE version 事件与兜底轮询不得重渲染顶掉拖动预览（松手 mxvTlUp 再对齐）。"""
    js = MX_VIEWS_JS
    refresh = _fn_body("mxvRefreshLatest", js)
    assert "if (_mxv.tlDrag) return;" in refresh  # SSE/轮询/兜底定时器共用此入口
    sse = _fn_body("mxvEnsureSSE", js)
    assert "_mxv.tlDrag" in sse  # version 事件拖动中不抢渲染，只标记有新


def test_mxv_posts_cache_deduped_by_post_id():
    """证据帖缓存按 post_id 去重：抽屉反复打开不重复累积。"""
    ev = _fn_body("mxvEvidenceHtml", MX_VIEWS_JS)
    assert "some((p) => p.id === e.post_id)" in ev


def test_mxv_target_drawer_race_guard_checks_type():
    """标的抽屉竞态守卫必须同时比对 type：题材与个股同名时旧响应不得污染新抽屉。"""
    body = _fn_body("mxvOpenTarget", MX_VIEWS_JS)
    assert "!_mxv.drawer || _mxv.drawer.type !== type || _mxv.drawer.name !== name" in body


def test_mxv_calendar_today_is_beijing_and_popover_positions_dynamically():
    """月历「今天」按北京时区口径（与后端交易日对齐）；弹层按触发按钮实时定位，CSS 默认值仅作回退。"""
    js = MX_VIEWS_JS
    cal = _fn_body("mxvCalHtml", js)
    assert "(480 + new Date().getTimezoneOffset())" in cal  # UTC+8 换算
    assert "function mxvCalPlace(" in js
    place = _fn_body("mxvCalPlace", js)
    assert "getBoundingClientRect" in place  # 打开时按触发按钮定位
    assert 'style.transform = "none"' in place  # 覆盖 CSS 的居中位移
    render = _fn_body("mxvCalRender", js)
    assert "mxvCalPlace()" in render
    css = (STATIC / "mx-views.css").read_text()
    assert ".mxv-cal{position:absolute;top:46px;" in css.replace(" ", "")  # 固定定位保留作回退


def test_mx_views_timeline_server_values_are_escaped():
    """时间轴 title/aria-valuetext 与观点流方向徽标等服务端值插值统一走 escapeHtml。"""
    tl = _fn_body("mxvTimelineHtml", MX_VIEWS_JS)
    assert 'title="${escapeHtml(s.snapshot_at)} · ${escapeHtml(s.message_count)}条消息"' in tl
    assert 'aria-valuetext="${escapeHtml(snaps[idx].snapshot_at)}"' in tl
    item = _fn_body("mxvFeedItemHtml", MX_VIEWS_JS)
    assert 'class="mxv-badge ${escapeHtml(o.direction)}"' in item  # 受控枚举，转义后仍是同一字符串


def test_mx_kol_collapse_reruns_once_after_lazy_avatar_loads():
    """折叠测量早于懒加载头像：卡内 img 首个 load/error 后重测一次（防抖只跑一回）。"""
    js = MX_VIEWS_JS
    assert "function mxvBindKolImgReflow(" in js
    kols = _fn_body("mxvRenderKols", js)
    assert "mxvBindKolImgReflow()" in kols
    reflow = _fn_body("mxvBindKolImgReflow", js)
    assert "once: true" in reflow  # 一次性监听
    assert "let done = false" in reflow  # 多张头像只触发一次重测，避免闪烁


def test_mx_render_boards_feed_rerender_is_skippable():
    """mxvRenderBoards 支持 rerenderFeed=false：feed 加载路径不重复渲染观点流两次。"""
    js = MX_VIEWS_JS
    boards = _fn_body("mxvRenderBoards", js)
    assert "if (rerenderFeed) mxvRenderFeed();" in boards
    assert "mxvRenderKols();" in boards  # 大V卡片依赖 feed 回填的中性数，仍需重渲染


def test_mx_views_feed_filters():
    """观点流筛选：右上角 观点流/个股/大V 视图切换；方向/操作词/大V 三组多选 +
    「操作」一键全选真实操作 + 搜索多选大V下拉 + 关键词搜索行（标的/大V名，输入即筛选）+ 重置；空时段隐藏。"""
    js = MX_VIEWS_JS
    assert "mxvFeedAction" not in js and "mxvFeedKol(" not in js  # 旧单选处理器已移除
    assert 'data-feed-view=' in js and '${key}' in js  # 右上角四视图切换（模板插值）
    render = _fn_body("mxvRenderFeed", js)
    for view in ('"stream"', '"stock"', '"topic"', '"kol"'):
        assert f'viewBtn({view}' in render
    assert 'mxvFeedTargetHtml(flat, "stock", allFlat)' in render and 'mxvFeedTargetHtml(flat, "topic", allFlat)' in render
    # 个股/题材视图各只显示自己的标的类型；名单排序用筛选数据，比例条用全量口径（不随筛选变化）
    target = _fn_body("mxvFeedTargetHtml", js)
    assert "o.target_type !== ttype" in target and "当前筛选无题材观点" in target
    assert "mxvRatioHtml(bar.bull, bar.bear, bar.neutral)" in target  # 多/中/空比例条（全量）
    assert "b.total - a.total || Math.abs(b.net) - Math.abs(a.net)" in target  # 大V数→|净多空|排序
    assert "mxvFeedKolHtml(flat, allFlat)" in render  # 大V视图迷你比例条同全量口径
    for token in ("data-feed-dir=", "data-feed-act=", "data-feed-kol=",
                  "data-feed-kol-toggle", "data-feed-kol-clear", "data-feed-reset",
                  "data-feed-kol-all"):
        assert token in js  # 方向/操作词多选 + 大V多选下拉（含全选切换）+ 重置
    # 操作词不做特殊归类：无「观察」白名单、「操作」一键等硬编码，chips 随观点数据自动出现
    assert "WATCH_ACTIONS" not in js and "data-feed-ops" not in js
    assert "mxvFeedFlat" in js and "mxvFeedTargetHtml" in js and "mxvFeedKolHtml" in js
    render = _fn_body("mxvRenderFeed", js)
    assert "当前筛选无观点" in render and "mxvFeedPool" in render
    bind = _fn_body("mxvBindFeedHighlight", js)
    assert "data-feed-kol-toggle" in bind and 'addEventListener("change"' in bind
    assert 'addEventListener("input"' in bind  # 下拉搜索
    assert "feedFreshPending" in js  # fresh 动画仅在数据到达后播一次，筛选重渲染不闪
    assert "mxv_feed_filters" in js and "mxvSaveFilters" in js and "mxvLoadFilters" in js  # 筛选本地持久化
    # 抽屉独立筛选：打开继承观点流筛选（有筛选时）否则恢复上次抽屉状态；抽屉内可再调并存 localStorage
    assert "mxv_drawer_filters" in js and "mxvInitDrawerFilters" in js and "mxvSaveDrawerFilters" in js
    init_fn = _fn_body("mxvInitDrawerFilters", js)
    assert "fromFeed" in init_fn  # 仅观点流入口继承；双榜/总览入口用抽屉上次状态
    bind_fn = _fn_body("mxvBindFeedHighlight", js)
    assert "mxvOpenKol(Number(kolId), true)" in bind_fn and ", hl.slice(ci + 1), true)" in bind_fn  # 观点流入口带来源
    for token in ('[data-drawer-dir]', '[data-drawer-act]', '[data-drawer-kol]', '[data-drawer-reset]'):
        assert token in js  # 抽屉内筛选 chips（点击委托选择器）
    assert 'chip("drawer-dir"' in js and 'chip("drawer-act"' in js and 'chip("drawer-kol"' in js
    timeline = _fn_body("mxvTimelineListHtml", js)
    assert "mxvDrawerMatch" in timeline and "已按当前筛选显示" in timeline  # 抽屉时间线走抽屉筛选
    # 抽屉操作行展示完整词表（0 计数置后半透明可点）+ 已选无数据词保留，杜绝筛选卡死
    dfn = _fn_body("mxvDrawerFiltersHtml", js)
    assert "vocab.filter((w) => !(w in actCounts))" in dfn and 'cls = ""' in dfn
    assert "mxv-fchip.zero" in Path("app/static/mx-views.css").read_text(encoding="utf-8")
    ffn = _fn_body("mxvFeedFiltersHtml", js)
    assert "[..._mxv.feedActs].filter((w) => !(w in actCounts))" in ffn  # 观点流同样保留已选 0 计数词
    # 关键词搜索行：搜标的（个股/题材）与大V名，空格分隔=全部命中；随筛选持久化、计入 dirty、重置/清空按钮/Esc 都能清
    assert 'feedSearch: ""' in js  # 状态初始化
    assert "search: _mxv.feedSearch" in _fn_body("mxvSaveFilters", js)  # 与方向/操作/大V 同套持久化
    assert 'typeof saved.search === "string"' in _fn_body("mxvLoadFilters", js)
    match_fn = _fn_body("mxvFeedMatch", js)
    assert "mxvFeedSearchKws()" in match_fn and "kws.every((k) => hay.includes(k))" in match_fn
    assert "mxv-fsearch" in ffn and "data-feed-search-clear" in ffn
    assert "_mxv.feedSearch.trim() ? 1 : 0" in ffn  # 搜索词计入 dirty（亮「重置」）
    bind = _fn_body("mxvBindFeedHighlight", js)
    assert 'data-feed-search-clear' in bind and ".mxv-fsearch" in bind  # 清空按钮 + 输入委托
    assert bind.count('_mxv.feedSearch = ""') >= 2  # 清空按钮与「重置」都清搜索词
    # 中文输入法兼容：组字期间（isComposing；旧 Safari/WebView 补 keyCode 229）
    # 不重渲染——innerHTML 重建输入框会打断组词、拼音上屏成英文；游离目标
    # （Firefox/Safari 组字后对旧输入框补发的 input）一并过滤；
    # compositionend 才统一筛选；Esc 同样避开组字期（先取消组词）
    assert "e.isComposing || e.keyCode === 229 || !e.target.isConnected" in bind
    assert 'addEventListener("compositionend"' in bind
    assert "!e.target.isConnected" in bind
    assert "e.isComposing || e.keyCode === 229" in js


def test_mx_kol_holdings_drawer_entry_and_shell():
    """大V头像旁「持仓」按钮打开右侧预估持仓抽屉（不跳页）。

    两个卡片入口都出 .mxv-hold-btn：大V总览卡片（内联 onclick + stopPropagation 防触发
    卡片本身的 mxvOpenKol）与观点流大V卡片（data-act 委托）；大V抽屉里按钮在头像下方、
    筛选行上方独立成块（data-kol-id 委托，换壳开持仓抽屉）。抽屉外壳复用 #mxv-drawer-slot 挂载、
    与智囊团抽屉同 z-index 体系、Esc 可关；页头不出「‹ 动态」返回钮（关闭走外壳 ✕）。
    """
    js = MX_VIEWS_JS
    mxc = (STATIC / "views" / "mx-kol-holdings.js").read_text(encoding="utf-8")
    # 总览卡片：头像包进 .mxv-avawrap，角标按钮带 stopPropagation
    kol_cards = _fn_body("mxvKolCardsHtml", js)
    assert "mxv-avawrap" in kol_cards and "mxv-hold-btn" in kol_cards
    assert 'event.stopPropagation();mxcOpenDrawer(' in kol_cards
    # 观点流大V卡片：走 data-act="mxc" 委托（innerHTML 重建不重绑）
    feed_kol = _fn_body("mxvFeedKolHtml", js)
    assert 'class="mxv-hold-btn" data-act="mxc" data-kol-id=' in feed_kol
    bind = _fn_body("mxvBindFeedHighlight", js)
    assert 'dataset.act === "mxc"' in bind and "openHoldingsDrawer(" in bind
    # 大V抽屉头部行内变体：委托挂 #mxv-drawer-body，点击换壳（先收起原抽屉）；
    # 位置在头像行下方、方向/操作筛选行上方（独立块，不再顶右上角）——在 kol 分支内比对顺序
    drawer_body = _fn_body("mxvRenderDrawerBody", js)
    assert 'mxv-hold-btn inline" data-kol-id=' in drawer_body
    assert "查看持仓</button>" in drawer_body
    kol_branch = drawer_body[drawer_body.index("} else {"):]
    assert kol_branch.index("border-radius:50%") < kol_branch.index('mxv-hold-btn inline"')
    assert kol_branch.index('mxv-hold-btn inline"') < kol_branch.index("mxvDrawerFiltersHtml(")
    dbind = _fn_body("mxvBindDrawerFilters", js)
    assert ".mxv-hold-btn[data-kol-id]" in dbind and "openHoldingsDrawer(" in dbind
    # 抽屉实现（mx-kol-holdings.js）：外壳/关闭/Esc/路由离开清理/完整页跳转
    for fn in ("mxcOpenDrawer", "mxcCloseDrawer"):
        assert f"function {fn}(" in mxc, fn
    open_fn = _fn_body("mxcOpenDrawer", mxc)
    assert "mxv-drawer-slot" in open_fn and "closeViewsDrawer" in open_fn  # 与智囊团抽屉互斥
    assert "mxc-drawer-mask" in open_fn and 'class="mxc-drawer hd-root"' in open_fn
    assert "go('/mx-kol/" in open_fn  # 外壳「完整页」按钮
    inner = _fn_body("mxcInnerHtml", mxc)
    assert "‹ 动态" in inner  # 返回钮仅页面宿主出（抽屉宿主由 _mxc.drawerEl 三元裁掉）
    teardown = _fn_body("mxvTeardown", js)
    assert ".mxc-drawer-mask" in teardown and ".mxc-drawer" in teardown  # 路由离开摘抽屉
    # Esc 关闭：与月历同层 keydown
    assert 'querySelector(".mxc-drawer")' in js and "closeHoldingsDrawer()" in js
    # 装配：工厂互调依赖（打开/关闭）+ window 注册（内联 onclick 可达）
    app = APP_JS
    assert "openHoldingsDrawer: (kolId) => mxcOpenDrawer(kolId)" in app
    assert "closeViewsDrawer: () => mxvCloseDrawer()" in app
    assert "closeHoldingsDrawer: () => mxcCloseDrawer()" in app
    handlers = app[app.index("const INLINE_HANDLERS"):]
    for name in ("mxcOpenDrawer", "mxcCloseDrawer", "mxcSetView", "mxcChangeDays", "mxcRecentInput"):
        assert name in handlers, name
    css = (STATIC / "mx-views.css").read_text(encoding="utf-8")
    mxc_css = (STATIC / "mx-kol-holdings.css").read_text(encoding="utf-8")
    assert ".mxv-avawrap" in css and ".mxv-hold-btn" in css and ".mxv-hold-btn.inline" in css
    assert ".mxc-drawer-mask" in mxc_css and ".mxc-drawer{" in mxc_css and ".mxc-drawer-top" in mxc_css


def test_mx_feed_kol_card_click_still_opens_drawer():
    """观点流大V卡片点主体开大V抽屉的守卫修复：卡上无 data-mxv-hl 祖先时，
    kol 分支须用自身 data-kol-id 兜底，不能被 closest("[data-mxv-hl]") 拦死（ca94378 引入的回归）。"""
    js = MX_VIEWS_JS
    bind = _fn_body("mxvBindFeedHighlight", js)
    assert "const kolId = actEl.dataset.kolId || (item && item.dataset.kolId);" in bind
    # kol 分支不再依赖 data-mxv-hl 祖先；target 分支仍须守卫（观点流行外无 hl 上下文）
    assert "if (!item) return;" in bind
    assert bind.index('actEl.dataset.act === "kol"') < bind.index('actEl.dataset.act === "target"')


def test_mx_kol_holdings_slider_change_and_sort():
    """最近观点滑动栏可整程拖动 + 松手刷新 + 按仓位/按时间排序。

    回归：此前 oninput 直接重绘汇总，innerHTML 连带替换 range 元素自身，
    按住拖动即被打断；现拖动中（input）只改数值/提示文案，松手（change）才刷新并持久化。"""
    mxc = (STATIC / "views" / "mx-kol-holdings.js").read_text(encoding="utf-8")
    html = _fn_body("mxcRecentHtml", mxc)
    assert 'oninput="mxcRecentInput(this.value)"' in html
    assert 'onchange="mxcRecentChange(this.value)"' in html
    # 排序段控与滑动栏同带：按仓位（默认）/按时间，点击走 mxcSetSort
    assert "mxcSetSort('${k}')" in html
    assert '["weight", "按仓位"' in html and '["time", "按时间"' in html
    # 拖动中不得重绘汇总（重绘会替换 range 元素、拖动即断），也不写存储
    inp = _fn_body("mxcRecentInput", mxc)
    assert "mxcRenderSummary" not in inp and "localStorage" not in inp
    # 松手才刷新汇总 + 持久化
    chg = _fn_body("mxcRecentChange", mxc)
    assert "mxcSaveRecent" in chg and "mxcRenderSummary" in chg
    # 排序切换：按时间按 last_at 新→旧，切换即重绘
    srt = _fn_body("mxcSetSort", mxc)
    assert "mxcSaveSort" in srt and "mxcRenderSummary" in srt
    sort_rows = _fn_body("mxcSortRows", mxc)
    assert "last_at" in sort_rows and "localeCompare" in sort_rows
    # 口径持久化：天数 + 排序都在挂载时恢复
    prefs = _fn_body("mxcLoadPrefs", mxc)
    assert "MXC_RECENT_KEY" in prefs and "MXC_SORT_KEY" in prefs
    # 默认 3 天；从未存过（null）不得覆盖默认——Number(null)=0 会把天数顶成“0=不筛选”
    assert "recent: 3" in mxc
    assert "raw != null" in prefs and "localStorage.getItem(MXC_RECENT_KEY)" in prefs
    # window 注册（内联 onclick 可达）
    handlers = APP_JS[APP_JS.index("const INLINE_HANDLERS"):]
    for name in ("mxcRecentInput", "mxcRecentChange", "mxcSetSort"):
        assert name in handlers, name
    # 排序段控样式（贴行尾 + 小号按钮）
    mxc_css = (STATIC / "mx-kol-holdings.css").read_text(encoding="utf-8")
    assert ".mxc-recent .mxc-sort" in mxc_css


def test_mx_kol_pnl_panel_contract():
    """预估盈亏面板：持仓+盈亏并行拉取渐进渲染、桩态占位、徽章配色与 @价标。

    盈亏接口（/mx-pnl）与持仓（/mx-holdings）分端点：行情链路慢时持仓先画，
    盈亏后到（mxcRenderPnl 独立入口）；行情未接入（available=false）出低调占位
    不报错；盈亏徽章 A 股口径盈红亏绿；时间线行内嵌成交价 @ 15.20。
    """
    mxc = (STATIC / "views" / "mx-kol-holdings.js").read_text(encoding="utf-8")
    # 并行取数：盈亏失败不阻塞持仓（catch 落空态而非抛错）
    load = _fn_body("mxcLoad", mxc)
    assert "/api/kols/${kolId}/mx-pnl?days=" in load
    assert "mxcRenderPnl" in load
    pnl_catch = load[load.index(".catch"):]
    assert "_mxc.pnl = null" in pnl_catch  # 失败落空态（面板出「待行情接入」）
    # 主体结构：盈亏面板节插在汇总与时间线之间
    inner = _fn_body("mxcInnerHtml", mxc)
    assert 'id="mxc-pnl"' in inner
    assert inner.index('id="mxc-summary"') < inner.index('id="mxc-pnl"') < inner.index('id="mxc-timeline"')
    # 渲染入口：RenderAll 里持仓渲染后跟盈亏渲染
    render_all = _fn_body("mxcRenderAll", mxc)
    assert "mxcRenderPnl()" in render_all
    # 桩态占位：available=false 单行提示不报错
    pnl_fn = _fn_body("mxcRenderPnl", mxc)
    assert "行情数据未接入" in pnl_fn
    assert "待行情接入" in pnl_fn
    # 在持浮动 + 已了结分段；覆盖率不足给提示
    assert "在持浮动" in pnl_fn and "已了结" in pnl_fn
    assert "行情覆盖" in pnl_fn
    # 徽章：盈=up 红、亏=down 绿、持平=flat（A 股口径），null 不出徽章
    badge = _fn_body("mxcPctBadge", mxc)
    for cls in ('"up"', '"down"', '"flat"'):
        assert cls in badge, cls
    assert "return \"\"" in badge  # pct 为 null 返回空串（不占位）
    # 持仓汇总行内嵌浮动盈亏徽章
    summary = _fn_body("mxcRenderSummary", mxc)
    assert "pnlByName" in summary and "mxcPctBadge" in summary
    # 时间线 @价标：event_prices 以 名称|occurred_at 为键
    row = _fn_body("mxcRowHtml", mxc)
    assert "event_prices" in row and "mxc-price" in row
    # teardown 清盈亏态（换大V不带残留）
    teardown = _fn_body("mxcTeardown", mxc)
    assert "pnl: null" in teardown
    # 样式：盈亏行/徽章/价标/说明齐备，配色走 .hd- token（明暗双主题随变量切换）
    mxc_css = (STATIC / "mx-kol-holdings.css").read_text(encoding="utf-8")
    for sel in (".mxc-pnl-row", ".mxc-pnl-pct", ".mxc-pnl-sub", ".mxc-pnl-note",
                ".mxc-pnl-name", ".mxc-pnl-cost", ".mxc-price", ".mxc-pnl-exit"):
        assert sel in mxc_css, sel
    assert ".mxc-pnl-pct.up" in mxc_css and ".mxc-pnl-pct.down" in mxc_css
    assert "var(--hd-bull-soft)" in mxc_css and "var(--hd-bear-soft)" in mxc_css
    # 滑杆/排序与盈亏面板同口径：change/setSort 都要连刷 mxcRenderPnl，
    # 否则拖完滑杆后汇总和盈亏列表的过滤范围不一致
    recent_change = _fn_body("mxcRecentChange", mxc)
    assert "mxcRenderPnl()" in recent_change
    set_sort = _fn_body("mxcSetSort", mxc)
    assert "mxcRenderPnl()" in set_sort
    # 无收益率归因区分：行情不全 vs 无卖出事件（被动出仓没有成交可算）
    assert "无卖出事件" in pnl_fn
    # 已了结默认折叠：超出 5 条折叠进「更多」，点击 toggle 全量/收起
    assert "MXC_CLOSED_LIMIT" in pnl_fn and "slice(0, MXC_CLOSED_LIMIT)" in pnl_fn
    assert "closedExpanded" in pnl_fn and "mxcToggleClosed()" in pnl_fn
    toggle = _fn_body("mxcToggleClosed", mxc)
    assert "closedExpanded = !_mxc.closedExpanded" in toggle and "mxcRenderPnl()" in toggle
    # window 注册（内联 onclick 可达）
    handlers = APP_JS[APP_JS.index("const INLINE_HANDLERS"):]
    assert "mxcToggleClosed" in handlers
    # 折叠按钮样式存在
    assert ".mxc-more" in mxc_css
    # available=true 且无个股操作：中性空态（不再误报「待行情接入」）
    assert "窗口内无个股操作" in pnl_fn
    # 持仓行第 5 列徽章：grid 必须有 5 列，否则徽章掉到下一行首列
    assert "grid-template-columns:minmax(84px,auto) auto 1fr auto auto" in mxc_css
    # 盈亏行 flex-wrap：窄屏成本说明折行到徽章下（无 wrap 时 order 不生效）
    assert "flex-wrap:wrap" in mxc_css
    # 离线外壳：SHELL 预缓存名单带上两个补充样式表（离线打开持仓/盈亏页不裸奔）
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    assert re.search(r'"/holdings\.[0-9a-f]{12}\.css"', sw)
    assert re.search(r'"/mx-kol-holdings\.[0-9a-f]{12}\.css"', sw)


def test_mx_kol_pnl_actions_contract():
    """盈亏行操作时间线：后端 actions=[{kind,at}] 逐笔渲染建仓/加仓/减仓/清仓/翻空徽章。

    徽章复用时间线 MXC_KINDS 文案与配色（买=红系/卖=绿系）；在持与已了结两段
    都嵌；行情缺价的票操作也照记（降级行同样有时间线）。长窗口同一票几十笔
    操作全铺开会盖过其他票：默认每类只露最近一次，其余折叠进「更多」。
    """
    mxc = (STATIC / "views" / "mx-kol-holdings.js").read_text(encoding="utf-8")
    # 渲染函数消费 actions 字段，文案/配色走 MXC_KINDS（与时间线徽章同源无双写）
    acts = _fn_body("mxcPnlActs", mxc)
    assert "actions" in acts and "MXC_KINDS" in acts
    for label in ("买入建仓", "买入加仓", "卖出减仓", "卖出清仓", "翻空减仓"):
        assert label in mxc, label
    # 在持与已了结行都嵌操作时间线
    pnl = _fn_body("mxcRenderPnl", mxc)
    assert pnl.count("mxcPnlActs(") >= 2  # liveRows + closedRows
    # 徽章带时间：title 提示全量时刻，行内显示 MM-DD HH:MM
    assert "slice(5, 16)" in acts
    # 样式：折行容器（多笔操作铺开）+ 徽章配色复用 .mxc-kind buy/sell
    mxc_css = (STATIC / "mx-kol-holdings.css").read_text(encoding="utf-8")
    assert ".mxc-pnl-acts" in mxc_css and "flex-wrap:wrap" in mxc_css
    assert ".mxc-kind.buy" in mxc_css and ".mxc-kind.sell" in mxc_css
    # 默认折叠：latest 表按 kind 留最近一笔，差额进「更多」；展开态按票名记
    # （盈亏接口后到补刷时不丢），toggle 只重画盈亏面板
    assert "latest[" in acts and "mxcToggleActs(" in acts
    toggle_acts = _fn_body("mxcToggleActs", mxc)
    assert "actsOpen" in toggle_acts and "mxcRenderPnl()" in toggle_acts
    # teardown 清展开态（换大V不带残留票名）
    teardown = _fn_body("mxcTeardown", mxc)
    assert "actsOpen: {}" in teardown
    # window 注册（内联 onclick 可达）
    handlers = APP_JS[APP_JS.index("const INLINE_HANDLERS"):]
    assert "mxcToggleActs" in handlers
    # 行内按钮覆写样式存在（左对齐徽章流，不吃 .mxc-more 的块级居中）
    assert ".mxc-acts-more" in mxc_css
