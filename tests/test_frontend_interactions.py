"""前端交互静态回归测试：订阅卡片操作必须按当前路由刷新。

背景：kolCard 的「订阅」按钮在首页、订阅管理、搜索、KOL 详情
多个页面复用 toggleSubscribe()。曾出现成功后无条件调用首页专用的
renderHomeList()，在非首页会因找不到 #kol-list 抛异常并落入 catch 弹出
「操作失败」假错误。本测试静态固化两条约定：
  1. toggleSubscribe 成功后调用路由感知的 refreshKolsView()
  2. refreshKolsView 覆盖所有会出现订阅卡片的页面路由
"""
import re
import subprocess
from pathlib import Path

APP_JS = Path(__file__).parent.parent / "app" / "static" / "app.js"
STYLE_CSS = APP_JS.with_name("style.css")


def test_subscription_push_is_the_only_subscription_management_navigation_entry():
    src = APP_JS.read_text()
    nav = src[src.index("const NAV ="):src.index("const SIDEBAR_SLIM_KEY")]
    mobile = src[src.index("const MOBILE_NAV ="):src.index("function renderBottomNav")]

    for block in (nav, mobile):
        assert 'route: "settings"' in block
        assert 'label: "订阅与推送"' in block
        assert 'route: "mysubs"' not in block
        assert 'route: "combinations"' not in block
    assert "TRENDING_ICON" not in src
    assert "BOOKMARK_ICON" not in src


def test_legacy_subscription_pages_redirect_at_the_router_boundary():
    src = APP_JS.read_text()
    router = _fn_body("router")
    prefixes = src[src.index("const SPA_PREFIXES"):src.index("function routeStillActive")]

    assert '"mysubs"' in prefixes and '"combinations"' in prefixes
    assert 'page === "mysubs"' in router
    assert 'state.settingsTab = "subs"' in router
    assert 'replaceRoute("settings")' in router
    assert 'page === "combinations"' in router
    assert 'state.platform = "combination"' in router
    assert 'replaceRoute("home")' in router
    assert "renderMySubs(renderSeq)" not in router
    assert "renderCombinations(renderSeq)" not in router



def test_knowledge_row_hides_unused_cover_fallback_icon():
    """瘦行不再预留封面列，备用图标不得再撑开行高。"""
    row = _fn_body("imaDocumentRow")
    css = STYLE_CSS.read_text()
    assert "ima-doc-row-icon" not in row
    assert "ima-doc-row-thumb" not in row
    assert "grid-template-columns: minmax(0, 1fr) 20px" not in css



def _fn_body(name: str) -> str:
    """提取指定函数（或变量=函数）的函数体。"""
    src = APP_JS.read_text()
    m = re.search(rf"async\s+function\s+{name}\b|function\s+{name}\b", src)
    assert m, f"未找到函数 {name}"
    i = m.end()
    while i < len(src) and src[i] != "(":
        i += 1
    assert i < len(src), f"{name} 无参数列表"
    depth = 1
    i += 1
    while i < len(src) and depth:
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
        i += 1
    start = src.index("{", i)
    depth, i = 1, start + 1
    while depth:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[start:i]


def _media_block(css: str, query: str, last: bool = False) -> str:
    idx = css.rfind(query) if last else css.find(query)
    assert idx != -1, f"缺少 {query}"
    start = css.find("{", idx)
    depth, i = 1, start + 1
    while depth and i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
        i += 1
    return css[start:i]


def test_toggle_subscribe_refreshes_by_route_not_home():
    """toggleSubscribe 成功后必须调用 refreshKolsView，不得无条件 renderHomeList。"""
    body = _fn_body("toggleSubscribe")
    assert "refreshKolsView()" in body, "toggleSubscribe 应通过 refreshKolsView 刷新当前路由"
    # 首页专用刷新不能出现在 toggleSubscribe 成功路径（无条件调用是跨页假错误的根因）
    assert "renderHomeList();" not in body.replace("refreshKolsView();", "")


def test_refresh_kols_view_covers_all_card_routes():
    """refreshKolsView 必须覆盖所有出现订阅卡片的页面。"""
    body = _fn_body("refreshKolsView")
    for route_call in (
        'isRoute("home")',
        'isRoute("settings")',
        'isRoute("kol/")',
        'isRoute("search")',
    ):
        assert route_call in body, f"refreshKolsView 缺少 {route_call} 路由分支"
    assert "loadHomeKols" in body
    assert "loadSettingsSubscriptions" in body
    assert "renderKolPage" in body
    assert "doSearch" in body
    assert 'isRoute("mysubs")' not in body
    assert 'isRoute("combinations")' not in body


def test_search_page_lists_only_unsubscribed_kols_without_query():
    """显示更多进入搜索页后立即列出未订阅大V，交互搜索也必须携带当前路由令牌。"""
    render = _fn_body("renderSearch")
    search = _fn_body("doSearch")

    assert "await doSearch(seq)" in render
    assert render.count("doSearch(routeRenderSeq)") == 2
    assert "if (!keyword) return" not in search
    assert "kols.filter((k) => !k.subscribed)" in search
    assert re.search(r"keyword\s*\?\s*available\.filter", search)
    assert "所有大V都已订阅" in search
    assert "没有匹配的未订阅大V" in search


def test_kol_detail_page_subscribes_via_toggle_subscribe():
    """KOL 详情页的订阅按钮必须复用 toggleSubscribe（从而获得路由感知刷新）。"""
    src = APP_JS.read_text()
    assert "toggleKolPageSubscribe" in src
    m = re.search(r"async function toggleKolPageSubscribe.*?\n}", src, re.DOTALL)
    assert m, "未找到 toggleKolPageSubscribe"
    assert "toggleSubscribe(" in m.group(0)


# ---- 异步路由竞态：旧路由的渲染不得覆盖新路由 ----

def test_router_emits_route_token():
    """router 每次路由切换必须递增 routeRenderSeq 并把 token 传给渲染函数。"""
    body = _fn_body("router")
    assert "const renderSeq = ++routeRenderSeq;" in body
    for call in ("renderHome(renderSeq)",
                 "renderTimeline(renderSeq)", "renderKolPage(Number(param), renderSeq)",
                 "renderSearch(renderSeq)", "renderSettings(renderSeq)"):
        assert call in body, f"router 未把 token 传给 {call}"
    # 错误状态也不能被过期路由写入
    assert "routeStillActive(renderSeq)" in body


def test_renderers_check_route_token_after_await():
    """各异步渲染函数在 await 之后、写 DOM 之前必须检查 routeStillActive。"""
    for name in ("renderHome", "renderTimeline", "renderKolPage", "renderSettings"):
        body = _fn_body(name)
        assert "routeStillActive(" in body, f"{name} 缺少路由令牌检查"
    # doSearch / loadHomeKols / loadTimeline / loadMyAsks 是局部刷新入口，同样要检查
    for name in ("doSearch", "loadHomeKols", "loadTimeline", "loadMyAsks", "loadSettingsSubscriptions"):
        body = _fn_body(name)
        assert "routeStillActive(" in body, f"{name} 缺少路由令牌检查"
    # renderHomeList 不得在没有 #kol-list 时解引用（旧响应落入非首页）
    assert 'if (!target) return' in _fn_body("renderHomeList")


def test_route_token_guard_checks_latest_seq():
    """routeStillActive 必须与全局 routeRenderSeq 比较，未传 token 视为过期（局部刷新必须带令牌）。"""
    src = APP_JS.read_text()
    m = re.search(r"function routeStillActive\(seq\)\s*\{[^}]*\}", src)
    assert m, "未找到 routeStillActive"
    assert "routeRenderSeq" in m.group(0)
    # 严格令牌：已删除「未传 token 视为活跃」的兼容分支
    assert "undefined" not in m.group(0)


def test_post_tags_filter_timeline_without_inline_user_string():
    """时间线帖子标签必须是可点击按钮：data-tag 传值 + tlPickTag 复用 state.timelineTag。

    约束：onclick 不得把标签文本插进 JS 字符串（XSS 注入面），必须走 this.dataset.tag。
    """
    post_card = _fn_body("postCard")
    pick_tag = _fn_body("tlPickTag")

    assert 'data-tag="${escapeHtml(t)}"' in post_card
    assert "tlPickTag(this.dataset.tag)" in post_card
    assert "state.timelineTag = tag" in pick_tag
    assert "loadTimeline(true, routeRenderSeq, { revert })" in pick_tag


def test_settings_async_responses_are_owned_by_route_and_session_before_mutation():
    """设置页的 /api/me 响应必须在写 state 或 DOM 前确认路由和会话仍是发起者。"""
    src = APP_JS.read_text(encoding="utf-8")
    refresh = _fn_body("refreshSettingsStatus")
    fetch = refresh.index('await api("/api/me")')
    state_write = refresh.index("state.user = user", fetch)
    guard = refresh.index("routeStillActive", fetch)
    assert "const seq = routeRenderSeq" in refresh[:fetch]
    assert "const token = state.token" in refresh[:fetch]
    assert "const sessionGeneration = imaMountState.sessionGeneration" in refresh[:fetch]
    assert guard < state_write
    assert "token !== state.token" in refresh[guard:state_write]
    assert "sessionGeneration !== imaMountState.sessionGeneration" in refresh[guard:state_write]

    render = _fn_body("renderSettings")
    fetch = render.index('await api("/api/me")')
    assignment = render.index("state.user = user", fetch)
    prefetch = render[:fetch]
    guard = render.index("routeStillActive(seq)", fetch)
    assert "const token = state.token" in prefetch
    assert "const sessionGeneration = imaMountState.sessionGeneration" in prefetch
    assert "const user = await api(\"/api/me\")" in render[fetch - 40:fetch + 50]
    assert guard < assignment
    assert "token !== state.token" in render[guard:assignment]
    assert "sessionGeneration !== imaMountState.sessionGeneration" in render[guard:assignment]


def test_render_settings_catch_only_mutates_owned_route_and_session():
    """设置页请求失败时，错误 DOM 也必须由发起请求的路由和会话拥有。"""
    render = _fn_body("renderSettings")
    fetch = render.index('await api("/api/me")')
    error_dom = render.index('$("#main").innerHTML = emptyState(err.message)', fetch)
    catch = render.rindex("} catch (err)", fetch, error_dom + 1)
    guard = render.index("routeStillActive(seq)", catch, error_dom)

    assert "token !== state.token" in render[guard:error_dom]
    assert "sessionGeneration !== imaMountState.sessionGeneration" in render[guard:error_dom]
    assert guard < error_dom
    assert render.index("const token = state.token", 0, fetch) < fetch
    assert render.index("const sessionGeneration = imaMountState.sessionGeneration", 0, fetch) < fetch



def test_bind_code_callbacks_capture_and_require_current_owner_before_side_effects():
    """绑定码响应只能由发起请求的路由、token 和会话写入状态或 DOM。"""
    for name in ("bindChannel", "genBindCode"):
        body = _fn_body(name)
        await_api = body.index('await api("/api/me/bind-code"')
        prefix = body[:await_api]
        for capture in (
            "const routeSeq = routeRenderSeq",
            "const token = state.token",
            "const sessionGeneration = imaMountState.sessionGeneration",
        ):
            assert capture in prefix, f"{name} 必须在请求前捕获会话拥有者"

        guard = body.index("if (!routeStillActive(routeSeq)", await_api)
        pending_write = body.index("pendingBind =", await_api)
        assert guard < pending_write
        owner_check = body[guard:pending_write]
        assert "token !== state.token" in owner_check
        assert "sessionGeneration !== imaMountState.sessionGeneration" in owner_check
        for side_effect in ("renderBindResult(" if name == "bindChannel" else '$(\"#bind-result\").innerHTML',
                             "startSettingsPoll()"):
            assert guard < body.index(side_effect, await_api), f"{name} owner guard 必须先于 {side_effect}"

        catch = body.index("} catch (err)", await_api)
        catch_guard = body.index("if (!routeStillActive(routeSeq)", catch)
        error_flash = body.index("flash(err.message, \"error\")", catch)
        assert catch_guard < error_flash
        catch_owner_check = body[catch_guard:error_flash]
        assert "token !== state.token" in catch_owner_check
        assert "sessionGeneration !== imaMountState.sessionGeneration" in catch_owner_check

def test_feishu_personal_async_callbacks_are_owner_guarded_and_logout_resets_all_state():
    """飞书注册、轮询和倒计时不得跨账号停止新计时器或写设置区。"""
    src = APP_JS.read_text(encoding="utf-8")
    start = _fn_body("startFeishuPersonal")
    assert "const owner" in start and "sessionGeneration" in start and "routeSeq" in start
    assert start.index("await api(") < start.index("fsPersonalState.sessionId =", start.index("await api("))
    assert "fsPersonalOwnerActive(owner)" in start

    poll = _fn_body("startFeishuPersonalPoll")
    assert "fsPersonalOwnerActive(owner)" in poll
    response = poll.index("await api(")
    assert poll.index("fsPersonalOwnerActive(owner)", response) < poll.index("fsPersonalState.verificationUri", response)
    assert "stopFeishuPersonalPoll(owner)" in poll
    assert "fsPersonalState.pollTimer !== timer" in poll

    countdown = _fn_body("startFeishuBindCountdown")
    assert "fsPersonalOwnerActive(owner)" in countdown
    assert "fsPersonalState.countdownTimer !== timer" in countdown
    assert "refreshFeishuBindCode()" in countdown
    assert "startFeishuPersonalPoll(" not in countdown

    clear = _fn_body("clearSessionCaches")
    for statement in (
        "fsPersonalState.owner = null",
        'fsPersonalState.sessionId = ""',
        'fsPersonalState.bindCommand = ""',
        "fsPersonalState.bindExpiresAt = 0",
        'fsPersonalState.verificationUri = ""',
        'fsPersonalState.qrUri = ""',
    ):
        assert statement in clear
    assert clear.index("stopFeishuPersonalPoll()") < clear.index("fsPersonalState.owner = null")


def test_feishu_personal_keeps_polling_while_awaiting_bind():
    """awaiting_bind 不得停轮询；码过期/丢失时自动 refresh-code，避免卡在 0s。"""
    poll = _fn_body("startFeishuPersonalPoll")
    awaiting = poll[poll.index('data.status === "awaiting_bind"'):poll.index('data.status === "active"')]
    assert "stopFeishuPersonalPoll" not in awaiting
    assert "refreshFeishuBindCode" in awaiting

    refresh = _fn_body("refreshFeishuBindCode")
    assert "stopFeishuPersonalPoll" not in refresh
    assert "refreshInFlight" in refresh


def test_weibo_qr_callbacks_are_owner_guarded_and_logout_invalidates_timer():
    """微博二维码请求序列、路由和会话必须共同拥有状态及计时器。"""
    src = APP_JS.read_text(encoding="utf-8")
    start = _fn_body("startWeiboQr")
    assert "const owner" in start and "wbQrSeq" in start and "sessionGeneration" in start
    assert "clearTimeout(wbQrTimer)" in start
    response = start.index("await api(")
    assert start.index("weiboQrOwnerActive(owner)", response) < start.index('$("#wb-qr-box").innerHTML', response)
    assert "wbQrTimer !== timer" in start
    poll = _fn_body("pollWeiboQr")
    response = poll.index("await api(")
    assert poll.index("weiboQrOwnerActive(owner)", response) < poll.index('const statusEl = $("#wb-qr-status")', response)
    assert "weiboQrOwnerActive(owner)" in poll[poll.index("} catch", response):]

    clear = _fn_body("clearSessionCaches")
    assert "clearTimeout(wbQrTimer)" in clear
    assert "wbQrTimer = null" in clear
    assert "wbQrSeq += 1" in clear


def test_mobile_timeline_filter_keeps_pills_out_of_panel():
    """手机端平台条留在吸顶栏；筛选面板是搜索、视图开关和标签。"""
    render = _fn_body("renderTimeline")
    src = APP_JS.read_text()

    assert 'id="tl-pills"' in render
    assert "tlPillsHtml()" in render
    assert 'id="tl-mobile-platforms"' not in render
    assert "function tlMobilePlatformsHtml" not in src
    assert "function tlPickMobilePlatform" not in src
    assert "function tlPlatformOptions" not in src
    assert 'role="radiogroup"' in render
    actions = _fn_body("tlFilterActionsHtml")
    panel = _fn_body("tlFilterPanelHtml")
    assert "tlViewTogglesHtml" not in actions
    assert "tlViewTogglesHtml()" in panel
    assert "tlFilterActionsHtml()" in render
    assert "tlFilterPanelHtml()" in render

    assert "tlSearchBarHtml()" in panel
    assert 'id="tl-q"' in _fn_body("tlSearchBarHtml")
    assert 'id="tl-tag"' in panel
    assert "tlApplyFilter()" in panel
    assert 'id="tl-category"' not in render
    assert "tlApplyRailSearch" in src


def test_timeline_pills_always_show_short_labels():
    """平台条一律图标+短字，选中只换底色；全称留在 aria-label。"""
    pills = _fn_body("tlPillsHtml")
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    assert "tl-pill-icon" not in pills
    assert "iconOnly" not in pills
    assert "platformShortLabel(p)" in pills
    assert "PLATFORM_ICONS[p || \"\"]" in pills
    assert "<span>${short}</span>" in pills
    assert 'aria-label="${label}"' in pills
    assert 'title="${label}"' in pills
    assert 'role="radio"' in pills
    assert "aria-checked" in pills
    assert 'combination: "组合"' in src
    assert ".tl-pill-icon" not in css
    assert ".tl-pills { display: none" not in css
    assert "flex-wrap: nowrap" in css
    assert 'data-platform="xueqiu"]' in css and "margin-inline-end" in css
    pill = re.search(r"\.tl-pill\s*\{([^}]*)\}", css)
    assert pill and "44px" in pill.group(1)
    assert ".tl-pill:focus-visible" in css


def test_mobile_platform_swipe_switches_adjacent_tab():
    """手机在列表上左右滑切相邻平台；胶囊条和按钮不抢手势；不循环。"""
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    ignore = _fn_body("mobilePlatformSwipeIgnore")
    ctx = _fn_body("mobilePlatformSwipeContext")
    surface = _fn_body("mobilePlatformSwipeSurface")
    adj = _fn_body("mobileSwipeAdjacent")
    start = _fn_body("onPlatSwipeStart")
    end = _fn_body("onPlatSwipeEnd")
    assert "isMobileTimelineFilter()" in start
    assert "surface" in start
    assert 'return "timeline"' in surface
    assert "tlPickPlatform" in ctx
    assert "homePickMobilePlatform" in ctx
    assert "switchMySubsPlatform" in ctx
    assert "start.surface" in end
    assert ".tl-pills" in ignore
    assert ".bottom-nav" in ignore
    assert ".post-images" in ignore
    assert "idx + dir" in adj
    assert "return null" in adj
    assert "56" in end
    assert "ensureMobilePlatformSwipe()" in _fn_body("renderBottomNav")
    assert "touch-action: pan-x" in css
    assert "touch-action: pan-y" in css
    assert "-webkit-overflow-scrolling: touch" in css


def test_timeline_filter_status_is_pills_only():
    """平台只由胶囊表达；漏斗里的视图/搜索/标签点亮筛选并写出 chip。"""
    chips = _fn_body("tlActiveChips")
    panel = _fn_body("tlPanelFilterOn")
    pick = _fn_body("tlPickPlatform")
    apply_f = _fn_body("tlApplyFilter")
    render = _fn_body("renderTimeline")
    assert 'key: "platform"' not in chips
    assert "平台：" not in chips
    assert 'key: "favorite"' in chips
    assert 'key: "secondary"' in chips
    assert "timelineFavorite" in panel
    assert "timelineSecondary" in panel
    assert "timelinePlatform || state.timelineTag" not in pick
    assert "timelinePlatform || state.timelineTag" not in apply_f
    assert "state.timelineQ || state.timelinePlatform || state.timelineTag" not in render
    assert "tlSyncFilterChrome" in pick


def test_timeline_filter_controls_revert_on_failure():
    """平台、视图开关、搜索/标签失败时回滚控件，reset 重写次要大V 图标。"""
    load = _fn_body("loadTimeline")
    reset = _fn_body("tlResetFilters")
    paint = _fn_body("tlPaintViewToggles")
    assert "opts.revert" in load
    assert "tlRestoreFilters" in load
    assert "revertPlatform" not in load
    for name in (
        "tlPickPlatform",
        "toggleTimelineFav",
        "toggleTimelineSecondary",
        "tlApplyFilter",
        "tlResetFilters",
        "tlRemoveFilter",
        "tlPickTag",
    ):
        body = _fn_body(name)
        assert "tlSnapshotFilters" in body
        assert "{ revert }" in body
    assert "tlPaintViewToggles" in reset
    assert "EYE_OFF_ICON" in paint


def test_timeline_platform_switch_reverts_on_failure():
    """点平台先出骨架；失败退回上一选中，条上能重试。"""
    load = _fn_body("loadTimeline")
    pick = _fn_body("tlPickPlatform")
    assert "TL_SKELETON" in load
    assert "catch" in load
    assert "加载失败" in load
    assert "tlSnapshotFilters" in pick
    assert "{ revert }" in pick
    assert "aria-busy" in load or "aria-busy" in pick


def test_mobile_platform_filter_keeps_hidden_state_and_applies_immediately():
    """打开筛选或点平台不改关键词/标签；只有清除筛选才重置。"""
    src = APP_JS.read_text()
    pick = _fn_body("tlPickPlatform")
    toggle_panel = _fn_body("tlFilterPanel")
    reset = _fn_body("tlResetFilters")

    assert "function tlClearMobileHiddenFilters" not in src
    assert "tlClearMobileHiddenFilters" not in toggle_panel
    assert "isMobileTimelineFilter()" not in toggle_panel
    assert 'state.timelineQ = ""' not in pick
    assert 'state.timelineTag = ""' not in pick
    assert "state.timelinePlatform = p" in pick
    assert "loadTimeline(true, routeRenderSeq" in pick
    for assignment in (
        'state.timelineQ = ""',
        'state.timelineCategory = ""',
        'state.timelineTag = ""',
    ):
        assert assignment in reset


def test_mobile_platform_filter_is_five_equal_44px_targets():
    """手机分类必须走角标坞；桌面胶囊仍 44px 带短字。"""
    css = STYLE_CSS.read_text()
    render = _fn_body("renderTimeline")
    mobile = _media_block(css, "@media (max-width: 768px)")
    assert ".tl-mobile-platform" not in css
    pill = re.search(r"\.tl-pill\s*\{([^}]*)\}", css)
    assert pill and "44px" in pill.group(1)
    assert "tl-filterbar-top icon-badge-bar" in render
    assert ".icon-badge-bar .tl-pill span" in css and "display: none" in css
    assert "display: none" not in re.search(r"\.topbar-title h1\s*\{([^}]*)\}", mobile).group(1)
    assert "clip: rect(0, 0, 0, 0)" in re.search(r"\.topbar-title h1\s*\{([^}]*)\}", mobile).group(1)


def test_timeline_polish_matches_chip_row_and_browser_surfaces():
    """筛选钮与胶囊同高；组合图标走雪球色；空态留空；选区/光标跟品牌走。"""
    css = STYLE_CSS.read_text()
    feed = _fn_body("renderTimelineFeed")
    pick = _fn_body("tlPickPlatform")
    remove = _fn_body("tlRemoveFilter")
    assert "::selection" in css
    assert "caret-color" in css
    bar = re.search(r"\.tl-filterbar \.fav-toggle\s*\{([^}]*)\}", css)
    assert bar and "44px" in bar.group(1)
    assert 'data-platform="combination"]:not(.selected) .pt-icon { color: var(--color-brand-xueqiu)' in css
    empty = re.search(r"^\.empty\s*>\s*div\s*\{([^}]*)\}", css, re.M)
    assert empty and "18px" in empty.group(1)
    assert "#tl-platform" not in pick
    assert "#tl-platform" not in remove
    assert "tl-feed-more" in feed
    assert "tl-feed-end" in feed
    assert 'style="margin-top:14px' not in feed


def test_settings_subscription_panel_reuses_mobile_badges_and_desktop_toolbar():
    """设置页订阅管理复用原有订阅筛选和卡片列表。"""
    panel = _fn_body("settingsSubscriptionsPanelHtml")
    tabs = _fn_body("renderMySubsTabs")
    mobile_html = _fn_body("mysubsMobileFiltersHtml")

    assert "isMobileTimelineFilter()" in panel
    assert 'id="mysubs-tabs"' in panel
    assert 'id="mysubs-list"' in panel
    assert 'id="mysubs-fav-toggle"' in panel
    assert '"platform-tabs"' in panel
    assert "platformShortLabel(p)" in mobile_html
    assert "switchMySubsPlatform('${p}')" in mobile_html
    assert "toggleMySubsFav()" in mobile_html
    assert "STAR_SVG" in mobile_html
    assert "mysubsMobileFiltersHtml()" in tabs
    assert 'platformTabHTML(p, state.mysubsPlatform' in tabs


def test_settings_subscription_loader_is_route_guarded_local_and_retryable():
    load = _fn_body("loadSettingsSubscriptions")

    assert 'api("/api/my/subscriptions")' in load
    assert load.count("routeStillActive(seq)") >= 2
    assert '$("#main").innerHTML' not in load
    assert '$("#mysubs-list")' in load
    assert "renderMySubsTabs()" in load
    assert "renderMySubsList()" in load
    assert "加载失败:" in load
    assert "重试" in load
    assert "loadSettingsSubscriptions(routeRenderSeq)" in load


def test_subscription_management_is_the_default_settings_tab():
    src = APP_JS.read_text()
    render = _fn_body("renderSettings")
    switch = _fn_body("switchSettingsTab")

    assert 'const SETTINGS_TABS = ["subs", "push", "bind", "llm", "account"]' in src
    assert 'data-tab="subs"' in render
    assert 'id="st-subs"' in render
    assert "settingsSubscriptionsPanelHtml()" in render
    assert 'switchSettingsTab(state.settingsTab || "subs")' in render
    assert 'setPageTitle("订阅与推送")' in render
    assert 'name = "subs"' in switch



def test_platform_tabs_always_show_short_labels():
    """订阅广场/我的订阅桌面平台条与时间线同一套：图标+短字，组合不写全称。"""
    tab = _fn_body("platformTabHTML")
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    assert "platformShortLabel(p)" in tab
    assert 'class="pt-label">${short}</span>' in tab
    assert "function platformShortLabel" in src
    assert "display: none" not in re.search(r"\.pt-label\s*\{([^}]*)\}", css).group(1)
    base = re.search(r"\.platform-tab\s*\{([^}]*)\}", css)
    assert base and "36px" not in base.group(1)
    assert ".platform-tab:focus-visible" in css


def test_product_spec_locks_mobile_platform_badges():
    """产品规范：手机分类条必须是角标，禁止带字胶囊。"""
    product = (APP_JS.parent.parent.parent / "PRODUCT.md").read_text()
    design = (APP_JS.parent.parent.parent / "DESIGN.md").read_text()
    assert "必须用一行等宽图标角标" in product
    assert "禁止改成图标+短字胶囊" in product
    assert "The Mobile Badge Rule" in design
    assert "把角标改回带字胶囊即违规" in design


def test_mobile_mysubs_filter_is_seven_equal_44px_targets():
    """订阅/动态移动端：6 平台 + 星标/筛选共 7 等宽 44px 角标，文字仅 aria。"""
    css = STYLE_CSS.read_text()
    pill = re.search(r"\.tl-pill\s*\{([^}]*)\}", css)
    assert pill and "44px" in pill.group(1)
    assert "特别关注" in _fn_body("mysubsMobileFiltersHtml")
    assert 'aria-label="特别关注"' in _fn_body("mysubsMobileFiltersHtml")
    assert 'aria-label="筛选"' in _fn_body("tlFilterActionsHtml")
    assert ".icon-badge-bar .tl-pill span" in css and "display: none" in css
    assert ".icon-badge-bar > .fav-toggle" in css and "font-size: 0" in css
    assert 'class="icon-badge-bar"' in _fn_body("renderHome")
    assert "tl-filterbar-top icon-badge-bar" in _fn_body("renderTimeline")
    assert "repeat(7, minmax(0, 1fr))" in css
    assert "#tl-filterbar .icon-badge-bar" in css
    assert "repeat(8, minmax(0, 1fr))" in css
    # 不再把筛选条竖着堆成两行
    mobile = re.search(r"@media \(max-width: 768px\) \{(.*)\}\s*/\* ----------", css, re.DOTALL)
    body = mobile.group(1) if mobile else css
    assert ".tl-filterbar-top { flex-direction: column" not in body.replace(" ", "")


# ---- 订阅广场移动端头部密度 ----

def test_mobile_home_filter_reuses_native_and_shared_controls():
    """广场移动端与订阅/动态同一行角标；搜索分类收进漏斗。"""
    render = _fn_body("renderHome")
    mobile_platforms = _fn_body("homeMobilePlatformsHtml")
    pick = _fn_body("homePickMobilePlatform")
    toggle = _fn_body("homeToggleFilter")

    for marker in ('class="icon-badge-bar"', 'id="home-filter-toggle"',
                   'id="home-search"', 'id="platform-tabs"', 'id="home-cats"',
                   'id="home-filter-panel"'):
        assert marker in render
    assert "<details" not in render
    assert "platformShortLabel(p)" in mobile_platforms
    assert "<span>${short}</span>" in mobile_platforms
    assert "homePickMobilePlatform('${p}')" in mobile_platforms
    assert "state.platform = platform" in pick
    assert "homeToggleFilter()" in render
    assert 'toggleAttribute("hidden"' in toggle
    assert "loadHomeKols(routeRenderSeq)" in pick
    assert "state.homeQ || state.homeCategory" in _fn_body("homeHasFilters")


def test_plaza_source_visibility_admin_and_pills():
    """管理员可设广场数据源自动/显示/隐藏；角标和旧 #/zsxq 都认可见列表。"""
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    assert 'STATS_TABS = ["config", "cookies", "proxies", "plaza", "news"]' in src
    tabs = _fn_body("statsTabsHtml")
    assert 'data-tab="${tab}"' in tabs
    assert "proxies:" in tabs
    assert "plaza:" in tabs
    assert "news:" in tabs
    assert "财经资讯" in tabs
    assert "动态广场显示" in _fn_body("loadAdminStats")
    assert "plazaSourceRowsHtml(s.plaza_sources)" in _fn_body("loadAdminStats")
    assert "plaza_platforms" in _fn_body("plazaVisibleSet")
    assert "timeline_platforms" in _fn_body("timelineVisibleSet")
    assert "tlTimelineEntries()" in _fn_body("tlPillsHtml")
    assert "tlPlazaEntries()" in _fn_body("renderPlatformTabs")
    assert "tlPlazaEntries()" in _fn_body("homeMobilePlatformsHtml")
    assert "tlTimelineEntries()" in _fn_body("renderMySubsTabs")
    assert "tlTimelineEntries()" in _fn_body("mysubsMobileFiltersHtml")
    assert "ensurePlazaPlatformSelection()" in _fn_body("renderTimeline")
    assert "ensurePlazaPlatformSelection()" in _fn_body("renderHome")
    assert "ensurePlazaPlatformSelection()" in _fn_body("renderSettings")
    assert 'timelineVisibleSet().has("zsxq")' in src
    assert "/api/admin/plaza-sources" in _fn_body("setPlazaSourceMode")
    assert "applyPlazaSources(data.sources)" in _fn_body("setPlazaSourceMode")
    assert "applyPlazaSources(s.plaza_sources)" in _fn_body("renderStatsData")
    assert ".plaza-src-mode" in css
    assert "44px" in re.search(r"\.plaza-src-mode\s*\{([^}]*)\}", css).group(1)


def test_zsxq_is_plaza_badge_not_sidebar_page():
    """知识星球走动态广场角标，不单独占侧栏；旧 #/zsxq 跳回时间线。"""
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    assert '"zsxq"' in src and "PLATFORM_TABS" in src
    assert 'zsxq: "星球"' in src
    assert "PLATFORM_ICONS" in src and "M13.012 0c.874" in src
    assert 'route: "zsxq"' not in src
    assert "async function renderZsxq" not in src
    assert 'replaceRoute("timeline")' in src
    assert "--color-brand-zsxq" in css
    assert 'data-platform="zsxq"' in css
    assert "state.platform" not in _fn_body("homeHasFilters")
    assert "function postFiles" in src
    assert 'post.platform === "zsxq"' in _fn_body("postCard")
    assert "class=\"p-file\"" in _fn_body("postCard")
    assert "/api/media/zsxq-file/" in _fn_body("postCard")
    assert 'return "zsxq"' in _fn_body("detectAskPlatform")
    assert 'option value="zsxq"' in _fn_body("renderSearch")
    assert "saveZsxqCookie()" in src
    assert "星球动态不混入" in _fn_body("renderTimelineFeed")


# ---- 设置页保存按钮对齐 ----

def test_dnd_save_button_aligns_left_with_other_settings_buttons():
    """免打扰保存按钮必须左对齐（与关键词提醒等模块一致），不得右对齐错开。"""
    css = STYLE_CSS.read_text()
    actions = re.search(r"\.dnd-actions\s*\{([^}]*)\}", css)
    assert actions, "缺少 .dnd-actions 样式"
    assert "justify-content: flex-end" not in actions.group(1), (
        "免打扰保存按钮右对齐会与左侧表单项、下方模块错开"
    )
    settings = APP_JS.read_text()
    dnd_block = settings[settings.index('class="dnd-actions"'):]
    assert "saveDnd()" in dnd_block
    assert "dnd-result" not in dnd_block[:400], "保存反馈应走 toast，不要在按钮旁放结果 span"


def test_success_toast_uses_accent_not_green():
    """日常成功 toast 走克制蓝，不占成功绿。"""
    css = STYLE_CSS.read_text()
    block = re.search(r"\.toast\.success\s*\{([^}]*)\}", css)
    assert block, "未找到 .toast.success"
    assert "color-accent" in block.group(1)
    assert "color-success" not in block.group(1)


def test_submit_ask_requires_category():
    """申请表有分类框，提交必须带 category_id。"""
    body = _fn_body("submitAsk")
    assert "ask-category" in body
    assert "category_id" in body
    assert "请选择分类" in body
    render = _fn_body("renderSearch")
    assert "ask-category" in render


def test_settings_save_feedback_uses_flash():
    """推送设置保存/失败统一走 flash toast，不再用 alert 或行内「已保存 ✅」。"""
    src = APP_JS.read_text()
    start = src.index("// ---------- 推送设置 ----------")
    end = src.index("// ---------- 管理后台")
    settings = src[start:end]
    assert "已保存 ✅" not in settings
    assert "alert(" not in settings
    for span_id in ("dnd-result", "keywords-result", "push-channels-result", "llm-result", "custom-tg-result"):
        assert span_id not in settings
    for name in (
        "saveNotify", "saveDailyReport", "saveTranslateTwitter", "saveDnd", "saveKeywords",
        "saveKeywordsMatchReports",
        "savePushChannels", "saveLlm", "savePassword", "saveCustomTgBot",
        "saveWecomWebhook", "saveBarkKey", "enableWebPush", "disableWebPush",
    ):
        body = _fn_body(name)
        assert "flash(" in body, f"{name} 应使用 flash toast"
        assert "alert(" not in body, f"{name} 不应再用 alert"
    assert "flash(" in _fn_body("savePollingConfig")
    assert "alert(" not in _fn_body("savePollingConfig")
    assert "alert(" not in _fn_body("saveXueqiuCookie")
    assert "alert(" not in _fn_body("saveTwitterCookie")
    assert "flash(" in _fn_body("saveTwitterCookie")
    assert "flash(" in _fn_body("pasteCookieField")


def test_llm_settings_are_openai_compatible_with_model_list():
    render = _fn_body("renderSettings")
    assert "OpenAI 兼容" in render
    assert "DeepSeek、Grok、OpenAI" in render
    assert 'id="set-llm-model-list"' in render
    assert "loadLlmModels()" in render
    assert "/api/me/llm-models" in _fn_body("loadLlmModels")
    assert "escapeHtml" in _fn_body("loadLlmModels")


def test_kol_image_settings_is_fourth_push_section_and_loads_independently():
    """动态图片卡片位于关键词后，并在设置页初始化完成后独立加载。"""
    body = _fn_body("renderSettings")
    push = body[body.index('id="st-push"'):body.index('id="st-bind"')]

    assert push.count('<section class="section-panel">') == 4
    assert push.index("关键词提醒") < push.index("动态图片")
    for copy in ("网页", "推送", "头像仍会显示", "仅影响当前账号"):
        assert copy in push
    assert "RSS" not in push
    assert 'id="kol-images-settings"' in push
    assert "正在加载已订阅大V" in push and 'class="muted' in push

    restore = body.rindex('switchSettingsTab(state.settingsTab || "subs")')
    dnd = body.rindex("toggleDnd()")
    subscriptions = body.rindex("loadSettingsSubscriptions(seq);")
    loader = body.rindex("loadKolImageSettings(seq);")
    assert restore < dnd < subscriptions < loader
    assert "await loadSettingsSubscriptions" not in body
    assert "await loadKolImageSettings" not in body


def test_kol_image_loader_is_route_guarded_local_and_retryable():
    """订阅加载失败只替换动态图片卡片，且可用当前路由令牌重试。"""
    load = _fn_body("loadKolImageSettings")
    render = _fn_body("renderKolImageSettings")

    assert 'api("/api/my/subscriptions")' in load
    assert load.count("routeStillActive(seq)") >= 2
    assert '$("#kol-images-settings")' in load
    assert '$("#main").innerHTML' not in load
    assert "加载失败:" in load
    assert "重试" in load
    assert "loadKolImageSettings(routeRenderSeq)" in load
    assert "正在加载已订阅大V" in load

    assert "emptyState(" in render
    assert "还没有订阅大V" in render
    assert "/home" in render or "go('home')" in render


def test_kol_image_loader_latest_generation_and_revision_win():
    """同路由并发 GET 只允许最新且未跨 mutation 的响应或错误落地。"""
    src = APP_JS.read_text()
    load = _fn_body("loadKolImageSettings")
    error = load[load.index("catch"):]

    for declaration in (
        "let _kolImageLoadGeneration = 0",
        "let _kolImageDataRevision = 0",
        "let _kolImageReloadNeeded = false",
    ):
        assert declaration in src
    assert "const loadGeneration = ++_kolImageLoadGeneration" in load
    assert "const loadRevision = _kolImageDataRevision" in load
    assert load.count("loadGeneration !== _kolImageLoadGeneration") >= 2
    assert load.count("loadRevision !== _kolImageDataRevision") >= 2
    assert load.count("_kolImagePendingIds.size") >= 2
    assert load.count("routeStillActive(seq)") >= 2
    assert load.index("loadGeneration !== _kolImageLoadGeneration") < load.index(
        "_kolImageSubscriptions = subscriptions"
    )
    assert load.index("loadRevision !== _kolImageDataRevision") < load.index(
        "_kolImageSubscriptions = subscriptions"
    )
    assert "_kolImageReloadNeeded = true" in load
    assert "reloadKolImageSettingsIfNeeded()" in load
    for guard in (
        "loadGeneration !== _kolImageLoadGeneration",
        "loadRevision !== _kolImageDataRevision",
        "_kolImagePendingIds.size",
        "routeStillActive(seq)",
    ):
        assert error.index(guard) < error.index("current.innerHTML")


def test_kol_image_rows_reuse_avatar_platform_and_accessible_switch():
    """紧凑行复用头像和开关，并以 !hide_images 映射可见状态。"""
    row = _fn_body("kolImageSettingsRowHtml")

    assert "kolCard" not in row
    assert "avatarHtml(kol.name, kol.avatar_url)" in row
    assert "escapeHtml(kol.name)" in row
    assert "PLATFORM_LABELS[kol.platform]" in row
    assert re.search(r"!\s*kol\.hide_images\s*\?\s*\"checked\"", row)
    assert 'class="switch kol-images-switch"' in row
    assert 'data-kol-id="${kol.id}"' in row
    assert 'aria-label="显示${escapeHtml(kol.name)}（${escapeHtml(platform)}）的动态图片"' in row
    assert "<span>显示</span>" in row
    assert 'onchange="toggleKolImages(${kol.id}, this)"' in row
    assert re.search(r"_kolImagePendingIds\.has\(kol\.id\)\s*\?\s*\"disabled\"", row)


def test_kol_image_search_threshold_fields_and_local_results():
    """十二个起显示搜索；过滤只重绘列表并覆盖名称、ID、平台。"""
    render = _fn_body("renderKolImageSettings")
    filter_body = _fn_body("filterKolImageSettings")

    assert re.search(r"_kolImageSubscriptions\.length\s*>=\s*12", render)
    assert 'placeholder="搜索已订阅大V"' in render
    assert 'oninput="filterKolImageSettings()"' in render
    assert 'id="kol-images-list"' in render
    assert 'role="region"' in render
    assert 'aria-label="已订阅大V的动态图片"' in render
    assert 'id="kol-images-more"' in render

    assert "kol.name" in filter_body
    assert "kol.external_id" in filter_body
    assert "PLATFORM_LABELS[kol.platform]" in filter_body
    assert ".toLowerCase()" in filter_body
    assert ".includes(query)" in filter_body
    assert "没有匹配的已订阅大V" in filter_body
    assert '$("#kol-images-list")' in filter_body
    assert '$("#kol-images-more")' in filter_body
    assert "filtered.length - 5" in filter_body
    assert "还有 ${" in filter_body
    assert "hidden" in filter_body
    assert '$("#kol-images-settings")' not in filter_body


def test_kol_image_toggle_is_inverse_guarded_and_rolls_back():
    """切换即时保存反向 hide_images，进行中禁用，失败回滚并走 toast。"""
    src = APP_JS.read_text()
    body = _fn_body("toggleKolImages")

    assert "const _kolImagePendingIds = new Set()" in src
    assert "if (!input || input.disabled || _kolImagePendingIds.has(kolId)) return" in body
    assert "const seq = routeRenderSeq" in body
    assert "input.disabled = true" in body
    assert "/api/subscriptions/${kolId}/hide-images" in body
    assert re.search(r'method:\s*"PUT"', body)
    assert "hide_images: !show" in body
    assert body.count("routeStillActive(seq)") >= 2
    assert "_kolImageSubscriptions.find" in body
    assert "const previousHideImages = kol.hide_images" in body
    assert "kol.hide_images = !show" in body
    assert body.index("kol.hide_images = !show") < body.index("await api")
    assert "kol.hide_images = previousHideImages" in body
    assert "input.checked = !previousHideImages" in body
    assert "mountedInput.disabled = false" in body
    assert "_kolImagePendingIds.delete(kolId)" in body
    assert body.index("_kolImagePendingIds.delete(kolId)") < body.rindex("routeStillActive(seq)")
    assert 'flash(`${show ? "已显示" : "已隐藏"}' in body
    assert 'flash("保存失败: " + err.message, "error")' in body
    assert "alert(" not in body


def test_kol_image_toggle_syncs_mounted_input_without_losing_keyboard_focus():
    """普通 toggle 收尾原地同步当前行；仅键盘焦点仍在可见行时恢复。"""
    body = _fn_body("toggleKolImages")
    cleanup = body[body.index("finally"):]

    focus_capture = (
        'const restoreFocus = document.activeElement === input '
        '&& input.matches(":focus-visible")'
    )
    assert focus_capture in body
    assert body.index(focus_capture) < body.index("input.disabled = true")
    assert 'document.querySelector(`#kol-images-list input[data-kol-id="${kolId}"]`)' in cleanup
    assert "mountedInput.checked = !kol.hide_images" in cleanup
    assert "mountedInput.disabled = false" in cleanup
    focus_guard = (
        "if (restoreFocus && (document.activeElement === input "
        "|| document.activeElement === document.body))"
    )
    assert focus_guard in cleanup
    assert "mountedInput.focus({ preventScroll: true })" in cleanup
    assert "mountedInput.focus()" not in cleanup
    assert "filterKolImageSettings()" not in cleanup


def test_kol_image_toggle_recovers_stale_route_after_returning_to_settings():
    """旧路由请求收尾时若已回到设置页，必须重拉服务端真值并解除新行禁用。"""
    body = _fn_body("toggleKolImages")
    reload_if_needed = _fn_body("reloadKolImageSettingsIfNeeded")
    cleanup = body[body.index("finally"):]

    assert "_kolImagePendingIds.delete(kolId)" in cleanup
    assert 'isRoute("settings")' in cleanup
    assert "if (routeStillActive(seq))" in cleanup
    assert "_kolImageReloadNeeded = true" in cleanup
    assert "reloadKolImageSettingsIfNeeded()" in cleanup
    assert cleanup.index("_kolImagePendingIds.delete(kolId)") < cleanup.index(
        "reloadKolImageSettingsIfNeeded()"
    )
    assert "renderKolImageSettings()" not in cleanup
    assert "loadKolImageSettings(routeRenderSeq)" in reload_if_needed


def test_kol_image_same_route_pending_load_reloads_after_last_toggle():
    """pending 期间作废 GET；最后一个 toggle 收尾时重拉，普通路径只同步当前行。"""
    body = _fn_body("toggleKolImages")
    cleanup = body[body.index("finally"):]
    reload_if_needed = _fn_body("reloadKolImageSettingsIfNeeded")

    assert body.count("_kolImageDataRevision += 1") >= 2
    assert body.index("_kolImageDataRevision += 1") < body.index("await api")
    assert "_kolImagePendingIds.size === 0 && _kolImageReloadNeeded" in cleanup
    assert "reloadKolImageSettingsIfNeeded()" in cleanup
    assert "else if (routeStillActive(seq))" in cleanup
    assert "mountedInput.disabled = false" in cleanup
    assert "filterKolImageSettings()" not in cleanup
    assert "renderKolImageSettings()" not in cleanup

    assert "if (!_kolImageReloadNeeded || _kolImagePendingIds.size)" in reload_if_needed
    assert 'if (!isRoute("settings")) return' in reload_if_needed
    assert "_kolImageReloadNeeded = false" in reload_if_needed
    assert "loadKolImageSettings(routeRenderSeq)" in reload_if_needed
    assert reload_if_needed.index("_kolImageReloadNeeded = false") < reload_if_needed.index(
        "loadKolImageSettings(routeRenderSeq)"
    )


def test_kol_image_css_is_compact_truncating_and_touchable():
    """动态图片行保持 36px 头像、长名省略、至少 44px 开关，且名单卡片内滚动。"""
    css = STYLE_CSS.read_text()
    container = re.search(r"#kol-images-settings\s*\{([^}]*)\}", css)
    row = re.search(r"\.kol-images-row\s*\{([^}]*)\}", css)
    avatar = re.search(r"\.kol-images-row \.kol-avatar\s*\{([^}]*)\}", css)
    info = re.search(r"\.kol-images-info\s*\{([^}]*)\}", css)
    name = re.search(r"\.kol-images-name\s*\{([^}]*)\}", css)
    switch = re.search(r"\.kol-images-switch\s*\{([^}]*)\}", css)
    empty = re.search(
        r"#kol-images-settings > \.empty,\s*\.kol-images-list > \.empty\s*\{([^}]*)\}",
        css,
    )
    empty_cta = re.search(
        r"#kol-images-settings > \.empty \.btn-add,\s*"
        r"\.kol-images-list > \.empty \.btn-add\s*\{([^}]*)\}",
        css,
    )

    assert ".switch {" in css
    assert container and "width: 100%" in container.group(1) and "max-width: 640px" in container.group(1)
    assert "border:" not in container.group(1) and "box-shadow:" not in container.group(1)
    assert row and "display: flex" in row.group(1) and "min-height: 44px" in row.group(1)
    assert avatar and "width: 36px" in avatar.group(1) and "height: 36px" in avatar.group(1)
    assert info and "min-width: 0" in info.group(1)
    assert name and "overflow: hidden" in name.group(1)
    assert "text-overflow: ellipsis" in name.group(1)
    assert "white-space: nowrap" in name.group(1)
    assert switch and "min-height: 44px" in switch.group(1)
    assert re.search(r"\.kol-images-switch input:disabled\s*~\s*span\s*\{[^}]*opacity:", css)
    assert empty and "padding: 24px" in empty.group(1)
    assert empty_cta and "margin-top: 12px" in empty_cta.group(1)
    list_rule = re.search(r"\.kol-images-list\s*\{([^}]*)\}", css)
    assert list_rule and "max-height: 260px" in list_rule.group(1)
    assert "overflow-y: auto" in list_rule.group(1)
    assert "overscroll-behavior: contain" in list_rule.group(1)
    assert "padding-right: 12px" in list_rule.group(1)
    more = re.search(r"#kol-images-more\s*\{([^}]*)\}", css)
    assert more and "margin-top: 8px" in more.group(1)


def test_stats_proxies_tab():
    src = APP_JS.read_text()
    assert 'data-tab="${tab}"' in _fn_body("statsTabsHtml")
    assert "function loadProxyAdmin" in src
    assert 'STATS_TABS.includes(tab)' in _fn_body("statsTabFromHash")
    assert '"proxies"' in APP_JS.read_text()
    assert "loadProxyAdmin()" in _fn_body("switchStatsTab")
    assert "/api/admin/proxy-routes" in src
    assert "/api/admin/proxy-pools" in src


def test_stats_tabs_expose_tab_aria():
    """数据源分段导航与注册码页同一套 tab 语义。"""
    src = APP_JS.read_text()
    tabs = _fn_body("statsTabsHtml")
    assert 'role="tab"' in tabs
    assert 'id="tab-${tab}"' in tabs
    assert "aria-controls=\"st-${tab}\"" in tabs
    assert "news:" in tabs
    switch = _fn_body("switchStatsTab")
    assert 'setAttribute("aria-selected"' in switch


def test_stats_tabs_scroll_active_tab_into_view():
    """手机横向 tab 深链接后，活动 tab 必须进入可视区域。"""
    switch = _fn_body("switchStatsTab")
    assert "scrollIntoView" in switch
    assert 'block: "nearest"' in switch
    assert 'inline: "nearest"' in switch


def test_proxy_admin_labels_and_mobile_table():
    """出口下拉各有标签；导入有可见 label；节点表走大V表的手机卡片约定。"""
    render = _fn_body("renderProxyAdmin")
    assert "代理池" in render
    assert "指定代理" in render
    assert "导入节点" in render
    assert "<th>操作</th>" in render
    assert 'class="ak-table proxy-nodes"' in render
    assert 'data-label="地址"' in render
    assert 'class="ak-actions"' in render
    assert 'class="btn-sm"' in render
    assert "ak-hide-mobile" in render
    assert 'class="ak-empty"' in render
    assert "还没有节点，先导入或提取。" in render
    css = STYLE_CSS.read_text()
    assert ".ak-table td::before" in css
    wide = _media_block(css, "@media (max-width: 1280px)")
    assert ".ak-table.proxy-nodes thead" in wide
    assert ".proxy-route" in wide


def test_proxy_admin_hardens_write_paths():
    """探测后回写列表、写操作防连点，空池不能存指定池，删节点要确认。"""
    test_fn = _fn_body("testProxyNode")
    assert "loadProxyAdmin()" in test_fn
    assert "btn.disabled" in test_fn
    save = _fn_body("saveProxyRoutes")
    assert "请先创建代理池" in save
    assert "请先导入或提取代理" in save
    delete_node = _fn_body("deleteProxyNode")
    assert "confirm(" in delete_node
    create = _fn_body("createProxyPool")
    assert "请填写代理池名称" in create
    load = _fn_body("loadProxyAdmin")
    assert "textarea[id^='pp-import-']" in load


def test_stats_cookie_repair_deep_link():
    """Cookie 失效要从总览一键进 Cookie 管理，并吃 /admin/stats?tab=cookies。"""
    src = APP_JS.read_text()
    assert "function cookieRepairItems" in src
    assert "function cookieRepairBanner" in src
    assert "function statsTabFromHash" in src
    assert "/admin/stats?tab=" in _fn_body("switchStatsTab")
    assert "statsTabFromHash()" in _fn_body("loadAdminStats")
    assert "saveTwitterCookie()" in _fn_body("loadAdminStats")
    assert "saveZsxqCookie()" in _fn_body("loadAdminKnowledge")
    assert "pasteCookieField('xq-cookie')" in _fn_body("loadAdminStats")
    banner = _fn_body("cookieRepairBanner")
    assert "go('admin/stats?tab=cookies')" in banner
    assert "switchStatsTab('cookies')" not in banner
    assert "Cookie 需要更新" in banner
    repair = _fn_body("cookieRepairItems")
    assert "xueqiu_probe_alert_at" not in repair
    assert "src.xueqiu && !src.xueqiu.ok" in repair


def test_stats_default_tab_is_config():
    switch = _fn_body("switchStatsTab")
    assert 'name === "config" ? "/admin/stats"' in switch
    hash_fn = _fn_body("statsTabFromHash")
    assert 'routeQuery().get("tab") || "config"' in hash_fn


def test_stats_tabs_are_config_workshop_only():
    """数据源页只改管线，不再承担监控总览 / 大V健康。"""
    src = APP_JS.read_text()
    load = _fn_body("loadAdminStats")
    assert "监控总览" not in load
    assert "大V健康" not in load
    assert "大V抓取健康" not in load
    assert 'statsTabsHtml("config")' in load
    assert "data-tab=\"cookies\"" not in load
    assert "data-tab=\"proxies\"" not in load
    assert "data-tab=\"plaza\"" not in load
    assert 'id="st-overview"' not in load
    assert 'id="st-health"' not in load
    hash_fn = _fn_body("statsTabFromHash")
    switch = _fn_body("switchStatsTab")
    assert 'tab === "overview"' in hash_fn or '"overview"' in hash_fn
    assert '"health"' in hash_fn
    assert 'replaceRoute("admin/dashboard")' in load or 'replaceRoute("admin/dashboard")' in switch


def test_dashboard_is_duty_console():
    """全景一屏：值班先于普查；平台表只出现一次。"""
    dash = _fn_body("loadAdminDashboard")
    live = _fn_body("renderStatsData")
    rows = _fn_body("sourceRowsHtml")
    src = APP_JS.read_text()
    assert "核心指标" in dash
    assert "近 14 天推送趋势" in dash
    assert "今日新帖" in dash
    assert "今日推送" in dash
    assert "数据源健康" in dash
    assert "停更" in dash or "kol-health" in dash
    assert dash.count("数据源健康") == 1
    assert dash.find("数据源健康") < dash.find("dash-duty-strip-slot")
    assert dash.find("dash-duty-strip-slot") < dash.find("停更")
    assert dash.find("停更") < dash.find("核心指标")
    assert "setPageTitle(\"全景概览\")" in dash
    assert 'id="dash-duty-strip-slot"' in dash
    assert "dutyStripHtml" in live
    assert 'id="sources-table"' in dash
    assert "sourceRowsHtml" in live
    assert "ok_24h" in rows
    assert "fail_24h" in rows
    assert "consecutive_fails" in rows
    assert "next_retry_at" in rows
    assert "staleEnabledKols" in src
    assert "openAdminKolFromHealth" in src
    assert "startDashboardLiveTimer" in src
    assert "cookieRepairBanner" in dash or "cookieRepairBanner" in live
    assert "trend.length" in dash
    assert "platformRows" in dash
    assert "channelRows" in dash


def test_source_status_splits_cold_start_and_credentials():
    """未开始不画危险红；凭据缺失绑 Cookie；连续失败才是持续失败。"""
    cell = _fn_body("sourceStatusCell")
    never = _fn_body("sourceNeverStarted")
    gap = _fn_body("sourceCredentialGap")
    assert "未开始" in cell
    assert "凭据缺失" in cell
    assert "持续失败" in cell
    assert "暂无成功" in cell
    assert "无成功记录" not in cell
    assert "status-warn" in cell
    assert "sourceNeverStarted" in cell
    assert "sourceCredentialGap" in cell
    assert "last_ok_at" in never
    assert "ok_24h" in never
    assert "fail_24h" in never
    assert "xq-missing" in gap
    assert "xq-bad" in gap
    assert "xueqiu" in gap
    assert "combination" in gap
    cause = _fn_body("sourceCauseCell")
    assert "去更新 Cookie" in cause
    assert "admin/stats?tab=cookies" in cause
    assert "还没跑过" in cause


def test_stale_kols_are_exceptions_not_inventory():
    """停更名单：只启用、从未抓到或超过 48h、最多 10 个。"""
    src = APP_JS.read_text()
    assert "STALE_KOL_HOURS = 48" in src
    assert "STALE_KOL_LIMIT = 10" in src
    rows = _fn_body("staleEnabledKolRows")
    body = _fn_body("staleEnabledKols")
    html = _fn_body("staleKolsHtml")
    assert "enabled" in rows
    assert "subscriber_count" in rows
    assert "STALE_KOL_HOURS" in rows
    assert "STALE_KOL_LIMIT" in body
    duty = _fn_body("dutyStripHtml")
    assert "pending_kol_requests" in duty
    assert "admin/requests" in duty
    assert "kol-health-verdict" in html
    open_fn = _fn_body("openAdminKolFromHealth")
    assert "adminKolsQ" in open_fn
    assert "admin/kols" in open_fn


def test_dashboard_live_refresh_does_not_rebuild_trends():
    """30 秒只打 /api/stats 补活块，不重拉 dashboard、不重建趋势。"""
    src = APP_JS.read_text()
    assert "function stopStatsTimer" in src
    timer = _fn_body("startDashboardLiveTimer")
    assert "/api/stats" in timer
    assert "/api/admin/dashboard" not in timer
    assert "renderStatsData" in timer
    assert "30000" in timer
    refresh = _fn_body("refreshDashboardLive")
    assert "/api/stats" in refresh
    assert "/api/admin/dashboard" not in refresh
    assert refresh.index("_lastAdminStatsSnapshot = st") < refresh.index("renderStatsData(st)")


def test_cookie_clear_is_confirmed_delete_and_hidden_when_unset():
    """已保存 Cookie 才显示清除；确认后走 DELETE，不用 alert。"""
    render = _fn_body("loadAdminStats")
    knowledge = _fn_body("loadAdminKnowledge")
    clear = _fn_body("clearSavedCookie")

    assert "clearSavedCookie('xueqiu'" in render
    assert "clearSavedCookie('weibo'" in render
    assert "clearSavedCookie('twitter'" in render
    assert "clearSavedCookie('ima'" not in knowledge
    assert "clearSavedCookie('zsxq'" in knowledge
    assert "from_env" in render
    assert "btn-ghost danger" in render
    assert 'aria-label="清除雪球 Cookie"' in render
    assert 'aria-label="清除微博 Cookie"' in render
    assert 'aria-label="清除 X Cookie"' in render
    assert 'aria-label="清除 IMA Cookie"' not in knowledge
    assert 'aria-label="清除知识星球 Cookie"' in knowledge
    assert ">清除 Cookie<" not in knowledge

    assert "confirm(" in clear
    assert "停止抓取" in clear
    assert "直到重新保存" in clear
    assert 'method: "DELETE"' in clear
    assert "/api/admin/cookies/" in clear
    assert "flash(" in clear
    assert "alert(" not in clear
    assert "loadAdminStats(routeSeq)" in clear
    assert "_cookieClearPending" in clear
    assert "focusCookieField(" in clear
    assert 'for="xq-cookie"' in render
    assert 'for="tw-cookie"' in render
    assert 'for="zq-cookie"' in knowledge
    assert 'for="ima-cookie"' not in knowledge
    assert 'for="ima-cid"' not in knowledge
    assert 'for="ima-key"' not in knowledge
    assert 'id="ima-pure-token"' not in knowledge
    assert 'id="ima-pure-interval"' not in knowledge
    assert 'id="ima-pure-uid"' not in knowledge
    assert 'id="wb-qr-start"' in render


def test_cookie_save_restores_focus_after_rebuild():
    """保存后整页重绘，焦点要回到刚操作的输入框，和清除同一套。"""
    focus = _fn_body("focusCookieField")
    assert "xq-cookie" in focus
    assert "wb-qr-start" in focus
    assert "tw-cookie" in focus
    assert "ima-cookie" in focus
    assert "zq-cookie" in focus
    assert ".focus()" in focus
    knowledge = _fn_body("loadAdminKnowledge")
    assert "saveImaCredentials()" not in knowledge
    for name in ("saveXueqiuCookie", "saveTwitterCookie"):
        body = _fn_body(name)
        assert "loadAdminStats(routeSeq)" in body
        assert "focusCookieField(" in body
        assert body.index("loadAdminStats(routeSeq)") < body.index("focusCookieField(")
    for name in ("saveZsxqCookie", "saveImaCredentials"):
        body = _fn_body(name)
        assert "reloadAdminSettingsPage(routeSeq)" in body
        assert "focusCookieField(" in body
        assert body.index("reloadAdminSettingsPage(routeSeq)") < body.index("focusCookieField(")


def test_router_me_response_is_session_owned_before_shell_or_state_mutation():
    """router 的 /api/me 成功/失败响应只能由发起路由和会话更新 shell。"""
    body = _fn_body("router")
    fetch = body.index('user = await api("/api/me")')
    owner_guard = body.index("sessionOwnerStillActive(renderSeq, token, sessionGeneration)", fetch)
    state_write = body.index("state.user = user", fetch)
    shell_write = body.index('$("#auth-view").classList.add("hidden")', fetch)

    assert "const token = state.token" in body[:fetch]
    assert "const sessionGeneration = imaMountState.sessionGeneration" in body[:fetch]
    assert "let user" in body[:fetch]
    assert owner_guard < state_write
    assert owner_guard < shell_write
    catch = body.index("} catch", fetch)
    assert "sessionOwnerStillActive(renderSeq, token, sessionGeneration)" in body[catch:]


def test_ima_pdf_download_checks_session_owner_before_every_side_effect():
    """旧会话 PDF 完成后不得创建 URL、插入链接、点击、撤销或提示错误。"""
    body = _fn_body("downloadImaPdf")
    fetch = body.index("await Promise.all")
    owner_guard = body.index("sessionOwnerStillActive(routeSeq, token, sessionGeneration)", fetch)
    side_effects = [
        "URL.createObjectURL(blob)",
        'document.createElement("a")',
        "document.body.appendChild(link)",
        "link.click()",
        "URL.revokeObjectURL(url)",
        'flash(`PDF 下载失败：${err.message}`, "error")',
    ]
    assert "const routeSeq = routeRenderSeq" in body[:fetch]
    assert "const token = state.token" in body[:fetch]
    assert "const sessionGeneration = imaMountState.sessionGeneration" in body[:fetch]
    for side_effect in side_effects:
        assert owner_guard < body.index(side_effect, fetch), side_effect
    assert "imaReaderDocumentGroup()" in body


def test_ima_pdf_download_timeout_revoke_rechecks_session_owner():
    """PDF 延迟释放 URL 时仍须确认下载发起路由和会话拥有者。"""
    body = _fn_body("downloadImaPdf")
    timeout = body.index("setTimeout(() =>")
    callback_end = body.index("}, 1000);", timeout)
    callback = body[timeout:callback_end]
    guard = callback.index("sessionOwnerStillActive(routeSeq, token, sessionGeneration)")
    revoke = callback.index("URL.revokeObjectURL(url)")
    assert guard < revoke


def test_knowledge_reader_pdf_fail_uses_header_download_only():
    """预览失败只留一句说明，下载只走右上角那一个按钮。"""
    fail = _fn_body("showImaPdfFail")
    reader = _fn_body("renderImaDocument")
    load = _fn_body("loadImaPdf")
    css = STYLE_CSS.read_text()
    assert "预览打不开" in fail
    assert "downloadImaPdf" not in fail
    assert "btn-normal" not in fail
    assert "正在打开预览" in reader
    assert "aria-busy" in reader
    assert "ima-reader-status" in load
    assert ".ima-reader-page .ima-pdf-panel iframe" in css


def test_ima_pdf_load_is_owned_by_route_and_reader_generation_before_load_or_fail_side_effects():
    """旧阅读器的 PDF 完成、校验失败和 iframe 错误不得污染当前阅读器。"""
    src = APP_JS.read_text()
    reader = _fn_body("renderImaDocument")
    load = _fn_body("loadImaPdf")
    fail = _fn_body("showImaPdfFail")

    assert "const readerSeq = ++_imaReaderSeq" in reader
    assert "loadImaPdf(mediaId, readerSeq)" in reader
    assert re.search(r"async function loadImaPdf\(mediaId, readerSeq\)", src)
    assert re.search(r"function showImaPdfFail\(mediaId, seq, readerSeq\)", src)

    owner_guard = "if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq) return;"
    assert load.count(owner_guard) >= 2
    head_read = "await blob.slice(0, 5).text()"
    assert load.index(owner_guard) < load.index(head_read)
    assert load.index(owner_guard, load.index(head_read)) < load.index("showImaPdfFail(mediaId, seq, readerSeq)")
    assert "showImaPdfFail(mediaId, seq, readerSeq)" in load
    assert "() => showImaPdfFail(mediaId, seq, readerSeq)" in load
    assert owner_guard in fail
    fail_guard = fail.index(owner_guard)
    for side_effect in ("clearImaPdfUrl()", "panel.hidden = false", "panel.innerHTML"):
        assert fail_guard < fail.index(side_effect)
    validation = load.index("if (blob.size < 64 || head !== \"%PDF-\")")
    assert validation < load.index("showImaPdfFail(mediaId, seq, readerSeq)")
    success_guard = load.index(owner_guard, load.index(head_read))
    for side_effect in ("URL.revokeObjectURL(window._imaPdfUrl)", "URL.createObjectURL(blob)", "frame.src", "panel.hidden = false", "frame.addEventListener"):
        assert success_guard < load.index(side_effect)


def test_cookie_save_nested_stats_reload_preserves_owner_sequence_and_focus_guard():
    """Cookie 保存及清除的嵌套 stats GET 必须继承原路由令牌，再检查会话后聚焦。"""
    for name, reload in (
        ("clearSavedCookie", "loadAdminStats(routeSeq)"),
        ("saveXueqiuCookie", "loadAdminStats(routeSeq)"),
        ("saveTwitterCookie", "loadAdminStats(routeSeq)"),
        ("saveZsxqCookie", "reloadAdminSettingsPage(routeSeq)"),
        ("saveImaCredentials", "reloadAdminSettingsPage(routeSeq)"),
    ):
        body = _fn_body(name)
        reload_call = body.index(reload)
        focus = body.index("focusCookieField(", reload_call)
        assert "loadAdminStats()" not in body
        assert "sessionGeneration" in body
        owner_guard = body.rfind("sessionOwnerStillActive(routeSeq, token, sessionGeneration)", reload_call, focus)
        route_guard = body.rfind("routeStillActive(routeSeq)", reload_call, focus)
        assert max(owner_guard, route_guard) < focus




def test_cookie_tab_primary_buttons_are_44px():
    """Cookie 管理主按钮提到 44px；不改全局 --control-height-2xl，避免登录/筛选错位。"""
    css = STYLE_CSS.read_text()
    block = re.search(r"#st-cookies\s+\.btn-normal\s*\{([^}]*)\}", css)
    assert block, "缺少 #st-cookies .btn-normal"
    assert "44px" in block.group(1)
    tokens = (APP_JS.parent / "vendor" / "design-tokens.css").read_text()
    root = re.search(r"^:root\s*\{", tokens, re.M)
    assert root
    # 只断言浅色 :root 里仍是 42px，避免误伤深色块
    light = tokens.split(":root.theme-dark")[0]
    assert "--control-height-2xl: 42px" in light


def test_ima_credentials_save_uses_flash_not_alert():
    """ima 凭证保存与清除同一套 toast，不再弹系统框。"""
    body = _fn_body("saveImaCredentials")
    assert "flash(" in body
    assert "alert(" not in body


def test_dark_danger_token_meets_cookie_clear_contrast():
    """深色危险字色单独提亮，避免清除按钮掉到 4.5:1 以下。"""
    tokens = (APP_JS.parent / "vendor" / "design-tokens.css").read_text()
    dark = re.search(r":root\.theme-dark\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}", tokens)
    assert dark, "missing :root.theme-dark"
    assert "--color-danger: #f87171" in dark.group(0)
    assert "--color-danger-strong: #fca5a5" in dark.group(0)


def test_ima_document_collector_lives_in_knowledge_settings():
    """IMA 文档采集在知识库设置页，不再出现在数据源抓取/Cookie。"""
    stats = _fn_body("loadAdminStats")
    knowledge = _fn_body("loadAdminKnowledge")
    assert "IMA 文档采集" in knowledge
    assert "saveImaCollector()" in knowledge
    assert "IMA 文档采集" not in stats
    assert "saveImaCollector()" not in stats


def test_ima_settings_have_one_parent_and_keep_zsxq_under_ima():
    """知识库设置页采集在前，知识星球随后，存储在后。"""
    knowledge = _fn_body("loadAdminKnowledge")
    collect = knowledge.index('data-tab="collect"')
    zsxq = knowledge.index('data-tab="zsxq"')
    storage = knowledge.index('data-tab="storage"')
    assert collect < zsxq < storage
    assert '<h2 class="section-title">存储</h2>' in _fn_body("imaStoragePanelHtml")
    assert 'class="cfg-group cfg-group--zsxq"' in knowledge
    assert 'id="pc-zq-pages"' in knowledge
    assert 'id="pc-zq-save"' in knowledge


def test_zsxq_settings_use_one_column_on_narrow_layout():
    """知识星球配置在 800px 及以下不能继续用双列挤压字段。"""
    css = STYLE_CSS.read_text()
    narrow = _media_block(css, "@media (max-width: 800px)")
    assert re.search(r"\.cfg-group--zsxq \.cfg-fields\s*\{[^}]*grid-template-columns:\s*1fr", narrow)


def test_ima_discovery_status_refreshes_without_replacing_group_inputs():
    """定时刷新只更新发现状态，不重绘可能含未保存编辑的群组输入。"""
    body = _fn_body("renderStatsData")
    assert 'ima-group-discovery-status' in body
    assert 'imaGroupDiscoveryStatus.innerHTML = imaGroupDiscoveryStatusText(s.ima_collector)' in body
    assert 'renderImaGroupRows' not in body


def test_ima_sync_feedback_guards_duplicate_requests():
    """立即同步请求期间禁用按钮，并区分已启动和已在运行。"""
    body = _fn_body("triggerImaCollector")
    assert 'const btn = $("#ima-sync-btn")' in body
    assert 'if (btn?.disabled) return' in body
    assert 'btn.disabled = true' in body
    assert 'btn.disabled = false' in body
    assert 'already_running' in body
    catch_block = body[body.index("} catch"):body.index("} finally")]
    finally_block = body[body.index("} finally"):]
    assert "btn.disabled = false" in catch_block
    assert "btn.disabled = false" not in finally_block



def test_ima_save_reloads_with_authoritative_put_status_override():
    """保存后的 PUT 状态必须在等待完成后传给 stats reload，并覆盖 stale IMA 数据。"""
    src = APP_JS.read_text(encoding="utf-8")
    save = _fn_body("saveImaCollector")
    load = _fn_body("loadAdminStats")

    assert re.search(r"async function loadAdminStats\(seq = _adminRenderSeq, authoritativeImaStatus = null\)", src)
    put = 'const savedImaStatus = await api("/api/admin/ima-collector"'
    assert put in save
    assert "saveOwner.savedImaStatus = savedImaStatus" in save
    assert "await reloadAdminSettingsPage(routeSeq, savedImaStatus)" in save
    assert save.index(put) < save.index("saveOwner.putCompleted = true") < save.index("await reloadAdminSettingsPage(routeSeq, savedImaStatus)")
    assert "ima_collector: authoritativeImaStatus" in load
    assert load.index("authoritativeImaStatus") < load.index('$("#admin-body").innerHTML = `')


def test_ima_stats_failure_after_save_renders_cached_stats_with_retry():
    """保存后 stats GET 失败仍须用完整快照合并 IMA 状态，并保留当前路由重试提示。"""
    src = APP_JS.read_text(encoding="utf-8")
    load = _fn_body("loadAdminStats")

    assert "let _lastAdminStatsSnapshot = null" in src
    assert "_lastAdminStatsSnapshot = s" in load
    assert "const fallbackStats = _lastAdminStatsSnapshot" in load
    assert "fallbackStats && authoritativeImaStatus" in load
    assert "statsLoadError" in load
    render = load.index('$("#admin-body").innerHTML = `')
    assert load.index("renderStatsData(s)") > render
    assert load.index("statsLoadError", render) > load.index("renderStatsData(s)")
    assert 'onclick="loadAdminStats(${seq})"' in load
    assert "routeStillActive(seq)" in load[load.index("statsLoadError"):]


def test_ima_collector_pending_save_snapshots_full_form_and_secret_state():
    """stats 重建期间必须使用提交快照，token 只能由 JS 恢复，不能进入 HTML。"""
    src = APP_JS.read_text(encoding="utf-8")
    load = _fn_body("loadAdminKnowledge")
    save = _fn_body("saveImaCollector")
    assert "function imaCollectorFormSnapshot" in src
    assert "function imaCollectorFormRevision" in src
    assert "const snapshot = imaCollectorFormSnapshot()" in save
    assert "formRevision: imaCollectorFormRevision(snapshot)" in save
    assert "const ownerSnapshot =" in load
    for field in ("uid", "interval_seconds", "knowledge_base_id", "root_folder_id"):
        assert f"collector.{field}" in load
    assert "collectorGroups" in load
    assert "restoreImaCollectorOwnerToken" in load
    assert "const pendingToken =" in src
    assert "tokenInput.value = pendingToken" in src
    assert 'value="${ownerSnapshot?.refresh_token' not in src
    assert save.index("imaMountState.saveOwner = saveOwner") < save.index("await api(")
    assert "const onDraftChange =" in save
    assert 'document.addEventListener("input", onDraftChange)' in save
    assert 'document.removeEventListener("input", onDraftChange)' in save


def test_ima_collector_save_rechecks_form_revision_after_stats_reload_before_clearing_token():
    """stats GET 期间输入新 token 后，完成回调不得清除新值。"""
    save = _fn_body("saveImaCollector")
    reload_index = save.index("await reloadAdminSettingsPage(routeSeq, savedImaStatus)")
    clear_index = save.index('tokenInput.value = ""')
    assert "const noNewerEditsAfterReload" in save
    assert save.index("const noNewerEditsAfterReload") > reload_index
    assert "if (noNewerEditsAfterReload)" in save[reload_index:]


def test_ima_collector_full_form_draft_survives_owner_cleanup_and_stats_rebuild():
    """保存 owner 清理后，UID/间隔/知识库/根目录脏编辑仍由后续 stats 重建恢复。"""
    src = APP_JS.read_text(encoding="utf-8")
    load = _fn_body("loadAdminKnowledge")
    save = _fn_body("saveImaCollector")
    assert "collectorDraft" in src
    assert "rememberImaCollectorDraft" in src
    assert "const pendingCollectorDraft" in load
    assert "const collector = collectorDraft || pure" in load
    assert "collectorDraft?.groups" in load
    for field in ("uid", "interval_seconds", "knowledge_base_id", "root_folder_id"):
        assert f"collector.{field}" in load
    assert "restoreImaCollectorOwnerToken(owner, seq, pendingCollectorDraft)" in load
    assert 'value="${collector.refresh_token' not in src
    assert 'value="${pendingCollectorDraft' not in src
    assert "collectorDraftRevision" in src
    assert "clearImaCollectorDraft" in save
    reload_index = save.index("await reloadAdminSettingsPage(routeSeq, savedImaStatus)")
    assert save.index("clearImaCollectorDraft", reload_index) > reload_index
    assert 'document.addEventListener("input", imaCollectorDraftChanged)' in src
    assert 'document.addEventListener("change", imaCollectorDraftChanged)' in src


def test_ima_confirmed_departed_save_reconciles_server_state_on_next_stats_load():
    """离路成功保存的快照只等待下一次 stats 重建确认，服务端规范化值必须胜出。"""
    src = APP_JS.read_text(encoding="utf-8")
    load = _fn_body("loadAdminKnowledge")
    save = _fn_body("saveImaCollector")

    assert "collectorConfirmedRevision" in src
    assert "collectorConfirmedRevision = saveOwner.formRevision" in save
    mark = save.index("collectorConfirmedRevision = saveOwner.formRevision")
    assert save.index("const formStillCurrent =", save.index("await api(")) < mark
    assert save.index("const mountStillCurrent =", save.index("await api(")) < mark
    confirmed = load.index("collectorConfirmedRevision")
    render = load.index('$("#admin-body").innerHTML = `')
    assert confirmed < render
    assert "const confirmedCollectorDraft" in load
    assert "const collectorDraft = confirmedCollectorDraft ? null" in load
    assert "const collector = collectorDraft || pure" in load
    cleanup = load.index("clearImaCollectorDraft", render)
    assert cleanup > render
    assert "collectorDraftRevision === imaMountState.collectorConfirmedRevision" in load
    assert "imaMountState.collectorConfirmedRevision = \"\"" in load
    assert "collectorRevision" in save
    assert "imaMountState.revision === saveOwner.mountRevision" in save


def test_ima_save_reload_owns_mount_generation_bump_and_preserves_stale_guards():
    """同路由 reload 自身的 mount generation bump 不得阻断清理；外部失效仍须中止。"""
    src = APP_JS.read_text(encoding="utf-8")
    load = _fn_body("loadAdminKnowledge")
    save = _fn_body("saveImaCollector")

    assert "return false;" in load
    assert "return true;" in load
    assert load.index("return true;") > load.index("initImaMountState(pure.groups || [], preserveMountDraftForReload)")
    assert "setInterval" not in load
    assert "let statsReloadAccepted;" in save
    assert "reloadAdminSettingsPage(routeSeq, savedImaStatus)" in save
    assert "reloadAdminSettingsPage(routeRenderSeq, savedImaStatus)" in save
    reload = save.index("statsReloadAccepted = await reloadAdminSettingsPage(routeSeq, savedImaStatus);")
    cleanup_guard = save.index("if (!statsReloadAccepted", reload)
    assert save.index("sessionGeneration !== imaMountState.sessionGeneration", 0, reload) < reload
    assert cleanup_guard > reload
    assert "!routeStillActive(statsReloadSeq)" in save[cleanup_guard:]
    assert "imaMountState.saveOwner !== saveOwner" in save[cleanup_guard:]
    assert "generation !== imaMountState.generation" not in save[reload:cleanup_guard]
    assert load.index("initImaMountState(pure.groups || [], preserveMountDraftForReload)") < load.index("startDashboardLiveTimer()")


def test_ima_stats_failure_keeps_polling_and_exposes_route_owned_retry():
    """stats 首次/手动失败要留在当前页并可重试，不能丢掉原轮询。"""
    load = _fn_body("loadAdminStats")
    assert load.index("await api(\"/api/stats\")") < load.index("stopStatsTimer()")
    assert "stats-poll-error" in load
    assert 'id="stats-poll-error"' in load
    assert "role=\"alert\"" in load
    assert 'onclick="loadAdminStats(${seq})"' in load
    assert "routeStillActive(seq)" in load[load.index("} catch"):]
    timer = _fn_body("startDashboardLiveTimer")
    assert "routeStillActive" in timer


def test_ima_sync_responses_and_cleanup_are_owned_by_initiating_route():
    """同步 POST/status 的旧响应不得闪现或重绘新路由。"""
    body = _fn_body("triggerImaCollector")
    assert "const routeSeq = routeRenderSeq" in body
    post = body.index("await api(\"/api/admin/ima-collector/sync\"")
    assert body.index("if (!routeStillActive(routeSeq)) return", post) < body.index("flash(", post)
    status = body.index("await api(\"/api/admin/ima-collector\"")
    assert body.index("if (!routeStillActive(routeSeq)) return", status) < body.index('const target = $("#ima-collector-status")', status)
    assert "if (routeStillActive(routeSeq)" in body[body.index("} catch"):]
    assert "if (routeStillActive(routeSeq)" in body[body.index("} finally"):]


def test_ima_folder_error_retry_has_stable_focus_id():
    """目录失败重试替换分支时，焦点快照能定位新的重试按钮。"""
    error = _fn_body("imaFolderErrorHtml")
    assert 'id="ima-folder-retry-${escapeHtml(groupId)}-${escapeHtml(parentId)}"' in error
    assert "imaFocusSnapshot" in _fn_body("loadImaFolderChildren")
    assert "imaRestoreFocus(focus)" in _fn_body("loadImaFolderChildren")


def test_ima_collector_save_restores_focus_after_rebuild():
    """保存重建设置页后恢复原控件或保存按钮焦点。"""
    body = _fn_body("saveImaCollector")
    render = _fn_body("loadAdminKnowledge")
    assert 'document.activeElement' in body
    assert 'getElementById(focusId)' in body
    assert '.focus({' in body
    assert 'id="ima-collector-save"' in render


def test_ima_save_listener_filters_unrelated_document_events_before_snapshot():
    """临时保存监听器只能观察 IMA 字段，避免其它控件污染共享 draft。"""
    save = _fn_body("saveImaCollector")
    start = save.index("const onDraftChange =")
    end = save.index("imaMountState.saveOwner = saveOwner", start)
    listener = save[start:end]
    owner_guard = listener.index("imaMountState.saveOwner !== saveOwner")
    field_guard = listener.index("event.target")
    snapshot = listener.index("rememberImaCollectorDraft()")
    assert owner_guard < field_guard < snapshot
    for field_id in (
        "ima-pure-uid", "ima-pure-kb", "ima-pure-root",
        "ima-pure-interval", "ima-pure-token",
    ):
        assert field_id not in listener
    assert "interval_seconds" in _fn_body("readImaMountGroups")


def test_push_setting_saves_require_same_route_token_and_session_before_mutation():
    """旧账号的设置 PUT 回调不得修改新账号状态或闪现结果。"""
    for name in ("savePushChannels", "saveTranslateTwitter", "saveDnd"):
        body = _fn_body(name)
        put = body.index('await api("/api/me"')
        for capture in (
            "const routeSeq = routeRenderSeq",
            "const token = state.token",
            "const sessionGeneration = imaMountState.sessionGeneration",
        ):
            assert capture in body[:put]
        guard = body.index("routeStillActive(routeSeq)", put)
        mutation = body.index("state.user", put)
        assert guard < mutation
        assert body.index("token !== state.token", guard) < mutation
        assert body.index("sessionGeneration !== imaMountState.sessionGeneration", guard) < mutation
        catch = body.index("} catch", put)
        catch_guard = body.index("routeStillActive(routeSeq)", catch)
        assert body.index("flash(", catch_guard) > catch_guard


def test_settings_save_callbacks_require_same_route_token_and_session_before_all_side_effects():
    """所有设置保存回调的异步收尾都必须仍属于发起路由和会话。"""
    for name in (
        "saveNotify", "saveDailyReport", "saveCustomTgBot", "saveWecomWebhook",
        "saveBarkKey", "enableWebPush", "disableWebPush", "saveKeywords",
        "saveKeywordsMatchReports", "saveLlm",
    ):
        body = _fn_body(name)
        await_api = body.index("await api(")
        for capture in (
            "const routeSeq = routeRenderSeq",
            "const token = state.token",
            "const sessionGeneration = imaMountState.sessionGeneration",
        ):
            assert capture in body[:await_api], f"{name} 必须在异步请求前捕获会话拥有者"
        guard = body.index("routeStillActive(routeSeq)", await_api)
        assert "token !== state.token" in body[guard:guard + 150]
        assert "sessionGeneration !== imaMountState.sessionGeneration" in body[guard:guard + 180]
        side_effects = ["flash("]
        if name in ("saveCustomTgBot", "saveWecomWebhook", "saveBarkKey", "enableWebPush", "disableWebPush", "saveLlm"):
            side_effects.append("reloadSettings(routeSeq)")
        for side_effect in side_effects:
            assert body.index(side_effect, await_api) > guard, f"{name} 的 {side_effect} 未受响应守卫保护"
        catch = body.index("} catch", await_api)
        catch_guard = body.index("routeStillActive(routeSeq)", catch)
        assert body.index("flash(", catch_guard) > catch_guard, f"{name} 的错误提示未受响应守卫保护"


def test_settings_reload_passes_original_route_sequence():
    """设置异步回调重载时必须继续使用发起请求的路由令牌。"""
    reload = _fn_body("reloadSettings")
    assert "async function reloadSettings(routeSeq)" in APP_JS.read_text()
    assert "if (!routeStillActive(routeSeq)) return;" in reload
    assert "renderSettings(routeSeq)" in reload
    for name in ("saveCustomTgBot", "saveWecomWebhook", "saveBarkKey", "enableWebPush", "disableWebPush", "saveLlm"):
        assert "reloadSettings(routeSeq)" in _fn_body(name), f"{name} 未传递原始路由令牌"




def test_admin_credential_saves_require_same_route_token_and_session_before_side_effects():
    """旧路由或旧账号的凭证回调不得导航、重绘或恢复当前页面焦点。"""
    twitter = _fn_body("saveTwitterCookie")
    post = twitter.index('await api("/api/admin/')
    for capture in (
        "const routeSeq = routeRenderSeq",
        "const token = state.token",
        "const sessionGeneration = imaMountState.sessionGeneration",
    ):
        assert capture in twitter[:post]
    guard = twitter.index("routeStillActive(routeSeq)", post)
    for side_effect in ("flash(", "history.replaceState", "await loadAdminStats(routeSeq)", "focusCookieField"):
        assert guard < twitter.index(side_effect, post)
    catch = twitter.index("} catch", post)
    assert twitter.index("routeStillActive(routeSeq)", catch) < twitter.index("flash(", catch)
    reload = twitter.index("await loadAdminStats(routeSeq)", post)
    assert twitter.index("routeStillActive(routeSeq)", reload) < twitter.index("focusCookieField", reload)
    ima = _fn_body("saveImaCredentials")
    post = ima.index('await api("/api/admin/')
    for capture in (
        "const routeSeq = routeRenderSeq",
        "const token = state.token",
        "const sessionGeneration = imaMountState.sessionGeneration",
    ):
        assert capture in ima[:post]
    guard = ima.index("sessionOwnerStillActive(routeSeq, token, sessionGeneration)", post)
    for side_effect in ("flash(", "await reloadAdminSettingsPage(routeSeq)", "focusCookieField"):
        assert guard < ima.index(side_effect, post)
    catch = ima.index("} catch", post)
    assert ima.index("sessionOwnerStillActive(routeSeq, token, sessionGeneration)", catch) < ima.index("flash(", catch)


def test_admin_target_callbacks_require_route_token_session_and_owned_side_effects():
    """剩余设置/后台异步回调必须只影响发起路由和账号。"""
    for name in (
        "savePassword", "clearSavedCookie", "saveXueqiuCookie", "saveZsxqCookie",
        "savePollingConfig", "setPlazaSourceMode", "purgeZsxqCache",
    ):
        body = _fn_body(name)
        await_api = body.index("await api(")
        for capture in (
            "const routeSeq = routeRenderSeq",
            "const token = state.token",
            "const sessionGeneration = imaMountState.sessionGeneration",
        ):
            assert capture in body[:await_api], f"{name} 必须在请求前捕获会话 owner"
        guard = body.index("sessionOwnerStillActive(routeSeq, token, sessionGeneration)", await_api)
        assert "token" in body[guard:guard + 100], f"{name} 缺少 token 守卫"
        assert "sessionGeneration" in body[guard:guard + 140], f"{name} 缺少 session 守卫"
        catch = body.index("} catch", await_api)
        catch_guard = body.index("sessionOwnerStillActive(routeSeq, token, sessionGeneration)", catch)
        assert body.index("flash(", catch_guard) > catch_guard, f"{name} 错误提示未受守卫保护"

    for name in ("clearSavedCookie", "saveXueqiuCookie"):
        body = _fn_body(name)
        reload = body.index("await loadAdminStats(")
        assert "await loadAdminStats(routeSeq)" in body
        reload_guard = body.index("sessionOwnerStillActive(routeSeq, token, sessionGeneration)", reload)
        assert reload_guard < body.index("focusCookieField", reload)
    zsxq = _fn_body("saveZsxqCookie")
    reload = zsxq.index("await reloadAdminSettingsPage(")
    reload_guard = zsxq.index("sessionOwnerStillActive(routeSeq, token, sessionGeneration)", reload)
    assert reload_guard < zsxq.index("focusCookieField", reload)

    polling = _fn_body("savePollingConfig")
    assert "if (btn && document.body.contains(btn)) btn.disabled = false" in polling


def test_ima_save_listener_checks_owner_before_ima_field_ids():
    """IMA 临时监听器先确认保存 owner，再读取事件字段。"""
    save = _fn_body("saveImaCollector")
    start = save.index("const onDraftChange =")
    end = save.index("imaMountState.saveOwner = saveOwner", start)
    listener = save[start:end]
    owner = listener.index("imaMountState.saveOwner !== saveOwner")
    fields = listener.index("event.target")
    snapshot = listener.index("rememberImaCollectorDraft()")
    assert owner < fields < snapshot
    assert "event.target" in listener
    assert "ima-pure-uid" not in listener
    assert "ima-pure-interval" not in listener
    assert "ima-pure-token" not in listener
    assert "imaMountState.saveOwner === saveOwner" in listener
    assert "interval_seconds" in _fn_body("readImaMountGroups")


def test_ima_config_blocks_use_shared_layout_and_no_inline_spacing():
    stats = _fn_body("loadAdminKnowledge")
    mount_group = _fn_body("imaMountGroupRowHtml")
    folder = _fn_body("imaFolderRowHtml")
    config = stats
    css = STYLE_CSS.read_text()

    assert 'class="ima-mount-kb-row' in mount_group
    assert 'role="option"' in mount_group
    assert 'class="ima-folder-row"' in folder
    assert 'type="checkbox"' in folder
    assert 'aria-expanded=' in folder
    assert '<h3 class="ima-source-title">IMA 凭证</h3>' not in config
    assert 'class="ima-credential-fields"' not in config
    assert "saveImaCredentials()" not in config
    assert 'style="margin-top:' not in config
    assert 'style="margin:6px' not in config
    assert ".ima-code-field .form-control" in css
    assert ".ima-mount-layout" in css


def test_ima_config_uses_small_sync_icon_and_consistent_brand_case():
    stats = _fn_body("loadAdminKnowledge")
    css = STYLE_CSS.read_text()

    assert '<h3 class="ima-source-title">IMA 凭证</h3>' not in stats
    assert "保存 IMA 凭证" not in stats
    assert "saveImaCredentials()" not in stats
    assert ".ima-selected-head .refresh-icon" in css
    assert "width: 16px" in css
    assert "height: 16px" in css


def test_ima_group_render_has_safe_mount_rows_and_recovery_controls():
    """IMA 设置展示知识库列表、文件夹树和可恢复的目录加载控件。"""
    src = APP_JS.read_text()
    kb_row = _fn_body("imaMountGroupRowHtml")
    folder_row = _fn_body("imaFolderRowHtml")
    render = _fn_body("loadAdminKnowledge")
    assert 'id="ima-kb-list"' in render
    assert 'id="ima-folder-tree"' in render
    assert 'id="ima-group-discovery-status"' in render
    assert 'id="ima-discover-btn"' in render
    assert 'data-group-id="${escapeHtml(groupId)}"' in kb_row
    assert 'role="option"' in kb_row
    assert 'escapeHtml(group?.name || groupId)' in kb_row
    assert 'data-folder-id="${escapeHtml(folderId)}"' in folder_row
    assert 'aria-expanded="${expanded}"' in folder_row
    assert "knownEmpty" in folder_row
    assert "item?.has_children === false" in folder_row
    assert 'onchange="toggleImaFolder(this)"' in folder_row
    assert 'onclick="retryImaFolderLoad(this)"' in src
    assert "尚未发现共享知识库" in src


def test_ima_mount_expand_uses_stable_cache_and_parent_inheritance():
    """目录展开按知识库/父目录缓存，选择父目录后子项继承且不可重复选择。"""
    expand = _fn_body("toggleImaFolderExpand")
    load = _fn_body("loadImaFolderChildren")
    toggle = _fn_body("toggleImaFolder")
    assert "imaMountCacheKey(groupId, folderId)" in expand
    assert "imaMountState.folders.has(key)" in expand
    assert "encodeURIComponent(groupId)" in load
    assert "encodeURIComponent(parentId)" in load
    assert "imaMountState.parents" in toggle
    assert "selected.delete(selectedId)" in toggle
    assert "input.disabled" in toggle
    assert "imaMountState.dirty = true" in toggle


def test_ima_mount_normalizes_inherited_descendants_after_parent_links_arrive():
    """新学到父子关系后，去掉已被祖先覆盖的精确子选择，且不因此标 dirty。"""
    normalize = _fn_body("normalizeImaMountDraft")
    load = _fn_body("loadImaFolderChildren")
    selection = _fn_body("imaFolderSelectionState")
    assert "imaFolderAncestorSelected" in normalize
    assert "selected.delete" in normalize
    assert "imaMountState.dirty" not in normalize
    assert "normalizeImaMountDraft(groupId)" in load
    assert load.index("imaMountState.parents.set") < load.index("normalizeImaMountDraft(groupId)")
    assert "renderImaFolderTree(groupId)" in load
    assert "renderImaMountGroups()" not in load
    assert "const inherited = imaFolderAncestorSelected" in selection


def test_ima_mount_tree_exposes_the_knowledge_base_root():
    """没有子文件夹的知识库仍可显式挂载整个根目录。"""
    render = _fn_body("renderImaFolderTree")
    toggle = _fn_body("toggleImaFolder")
    orphans = _fn_body("imaFolderOrphansHtml")
    assert 'name: "整个知识库"' in render
    assert "imaFolderRowHtml(groupKey" in render
    assert "has_children: true" in render
    assert "tree.scrollTop" in render
    assert "imaRenderFolderBranch" not in render
    assert "imaRenderFolderBranch(groupId, folderId, depth + 1)" in _fn_body("imaFolderRowHtml")
    assert "folderId === String(group?.root_folder_id || \"\")" in toggle
    assert "selected.clear()" in toggle
    assert "new Set([rootId])" in orphans
    select = _fn_body("selectImaMountGroup")
    assert "loadImaFolderChildren" not in select

def test_ima_stats_timer_uses_the_render_token_before_repainting():
    """旧 stats 定时请求完成后不得覆盖更新的后台渲染。"""
    timer = _fn_body("startDashboardLiveTimer")
    assert "const timerSeq = _adminRenderSeq" in timer
    assert "routeStillActive(timerSeq)" in timer
    timer_start = timer.index("const timerSeq = _adminRenderSeq")
    render_index = timer.index("renderStatsData(fresh)")
    assert timer.index("routeStillActive(timerSeq)", timer_start) < render_index


def test_ima_discovery_catch_and_finally_require_generation_owner():
    """stats 重建或保存后，旧 discovery 的异常和收尾都不得碰当前控件。"""
    discover = _fn_body("discoverImaGroups")
    catch_start = discover.index("} catch")
    finally_start = discover.index("} finally")
    catch = discover[catch_start:finally_start]
    finally_block = discover[finally_start:]
    assert "generation === imaMountState.generation" in catch
    assert "imaMountState.discoverySeq === discoverySeq" in catch
    assert "routeStillActive(routeSeq)" in catch
    assert "imaMountState.discoveryOwner !== request" in finally_block
    assert "routeStillActive(routeSeq)" in finally_block
    assert "generation === imaMountState.generation" not in finally_block


def test_ima_force_folder_retry_supersedes_inflight_owner():
    """force retry 必须替换同 key 的旧 owner，普通请求仍保持 loading 去重。"""
    load = _fn_body("loadImaFolderChildren")
    assert "if (!force && imaMountState.loading.has(key)) return" in load
    assert "const request =" in load
    assert load.index("if (!force && imaMountState.loading.has(key)) return") < load.index("const request =")
    assert "imaMountState.folderRequests.set(key, request)" in load
    assert "imaMountState.folderRequests.get(key) === request" in load


def test_ima_pending_token_restores_across_current_stats_route_not_owner_route():
    """重进知识库设置时，当前共享 owner 的 token/表单仍可恢复，不能按发起路由丢弃。"""
    src = APP_JS.read_text(encoding="utf-8")
    restore = _fn_body("restoreImaCollectorOwnerToken")
    load = _fn_body("loadAdminKnowledge")
    assert "if (owner && owner !== imaMountState.saveOwner) return;" in restore
    assert "owner.routeSeq !== seq" not in restore
    owner_start = load.index("const ownerIsCurrent =")
    owner_end = load.index("const pendingCollectorDraft =", owner_start)
    owner_logic = load[owner_start:owner_end]
    assert "const ownerIsCurrent = owner && owner === pendingOwner" in owner_logic
    assert "owner.routeSeq === seq" not in owner_logic
    assert "restoreImaCollectorOwnerToken(owner, seq, pendingCollectorDraft)" in load


def test_ima_folder_edit_updates_live_save_owner_snapshot_and_stays_dirty():
    """PUT 后 reload 等待期间改目录，必须推进 owner 快照并保留 dirty。"""
    toggle = _fn_body("toggleImaFolder")
    dirty = toggle.index("imaMountState.dirty = true")
    assert "const draft = rememberImaCollectorDraft()" in toggle
    remember = toggle.index("const draft = rememberImaCollectorDraft()")
    assert "imaMountState.saveOwner.liveSnapshot = draft" in toggle
    owner = toggle.index("imaMountState.saveOwner.liveSnapshot = draft")
    assert dirty < remember < owner
    assert "if (imaMountState.saveOwner)" in toggle


def test_ima_departed_save_does_not_clear_until_current_reload_reconciles():
    """离开发起路由后的成功回调不得清 draft；同路由须 reload 后再按新编辑判定清理。"""
    save = _fn_body("saveImaCollector")
    departed = save.index('if (!routeStillActive(routeSeq) && !isAdminSettingsPath())')
    departed_end = save.index("reloadAdminSettingsPage(routeSeq, savedImaStatus)", departed)
    assert "clearImaCollectorDraft" not in save[departed:departed_end]
    assert "saveOwner.putCompleted = true" in save
    assert save.index("await reloadAdminSettingsPage(routeSeq, savedImaStatus)") < save.index("imaMountState.dirty = false")
    assert "const noNewerEditsAfterReload =" in save
    assert "if (noNewerEditsAfterReload)" in save


def test_ima_collector_save_is_owned_by_initiating_route_and_preserves_drafts():
    """旧的 collector 保存回调不得重绘新路由，stats 重建不得丢失脏挂载 draft。"""
    src = APP_JS.read_text(encoding="utf-8")
    load = _fn_body("loadAdminKnowledge")
    save = _fn_body("saveImaCollector")

    assert re.search(r"async function loadAdminKnowledge\(seq = _adminRenderSeq, authoritativeImaStatus = null\)", src)
    assert "routeStillActive(seq)" in load
    assert "const preserveMountDraft = imaMountState.dirty" in load
    assert "initImaMountState(pure.groups || [], preserveMountDraftForReload)" in load
    assert "const routeSeq = routeRenderSeq" in save
    assert "const saveButton = $(\"#ima-collector-save\")" in save
    assert "saveButton.disabled = true" in save
    assert "!isAdminSettingsPath()" in save
    assert "routeStillActive(routeSeq)" in save
    assert "reloadAdminSettingsPage(routeSeq, savedImaStatus)" in save
    assert "imaMountState.dirty = false" in save
    assert "document.body.contains(saveButton)" in save


def test_ima_collector_save_has_shared_busy_owner_for_rebuilt_buttons():
    """首次 PUT 期间 stats 重建出的保存按钮也必须由共享 owner 禁用。"""
    src = APP_JS.read_text(encoding="utf-8")
    load = _fn_body("loadAdminKnowledge")
    save = _fn_body("saveImaCollector")
    assert "saveOwner: null" in src
    assert 'imaMountState.saveOwner ? " disabled" : ""' in load
    assert "if (imaMountState.saveOwner) return;" in save
    assert "imaMountState.saveOwner = saveOwner" in save
    assert "imaMountState.saveOwner === saveOwner" in save
    assert save.index("imaMountState.saveOwner = saveOwner") < save.index("await api(")


def test_ima_collector_save_clears_only_matching_mount_revision():
    """PUT 完成时，离开路由或编辑新 draft 都不得清掉新 dirty 状态。"""
    init = _fn_body("initImaMountState")
    toggle = _fn_body("toggleImaFolder")
    save = _fn_body("saveImaCollector")
    assert "revision: 0" in APP_JS.read_text(encoding="utf-8")
    assert "if (!preserve && !imaMountState.saveOwner) imaMountState.revision += 1" in init
    assert "imaMountState.revision += 1" in toggle
    assert "const mountRevision = imaMountState.revision" in save
    assert "imaMountState.saveOwner = saveOwner" in save
    assert "saveOwner.liveSnapshot =" in save
    assert "imaMountState.dirty = false" in save
    assert save.index("await reloadAdminSettingsPage(routeSeq, savedImaStatus)") < save.index("imaMountState.dirty = false")


def test_ima_collector_save_cleanup_requires_current_form_and_mount_revision():
    """表单回到原值但目录版本已变化时，不得清理保存草稿、dirty 或 token。"""
    save = _fn_body("saveImaCollector")
    reload_index = save.index("await reloadAdminSettingsPage(routeSeq, savedImaStatus)")
    guard_index = save.index("const noNewerEditsAfterReload")
    clear_index = save.index("clearImaCollectorDraft(saveOwner.formRevision)")
    assert guard_index > reload_index
    assert "const mountStillCurrentAfterReload = imaMountState.revision === saveOwner.mountRevision;" in save
    assert "const noNewerEditsAfterReload = formStillCurrentAfterReload && mountStillCurrentAfterReload && liveRevision === saveOwner.formRevision;" in save
    assert guard_index < clear_index
    assert save.index("mountStillCurrentAfterReload", guard_index) < clear_index


def test_ima_stats_preserves_newer_mount_revision_before_mount_state_init():
    """目录改动后即使表单回到原值，stats 重建也必须先按新版 revision 保留 draft。"""
    load = _fn_body("loadAdminKnowledge")
    preserve_index = load.index("const preserveMountDraft")
    init_index = load.index("initImaMountState(pure.groups || [], preserveMountDraftForReload)")
    preserve_decision = load[preserve_index:init_index]
    assert "imaMountState.revision !== owner.mountRevision" in preserve_decision
    assert preserve_index < init_index


def test_ima_collector_save_failure_flash_is_route_owned():
    """离开 stats 后返回的旧 PUT 失败不得把错误 toast 显示到当前页面。"""
    save = _fn_body("saveImaCollector")
    catch_start = save.index("} catch")
    finally_start = save.index("} finally")
    catch = save[catch_start:finally_start]
    assert re.search(
        r"if \(routeStillActive\(routeSeq\) && isAdminSettingsPath\(\)\)\s*\{\s*flash",
        catch,
    )


def test_ima_discovery_ignores_stale_responses_and_releases_current_button():
    """发现请求跨 stats 重建时只能更新当前状态和当前 DOM。"""
    src = APP_JS.read_text(encoding="utf-8")
    discover = _fn_body("discoverImaGroups")
    assert "discoverySeq" in discover
    assert "imaMountState.discoverySeq" in src
    assert "imaMountState.discoverySeq === discoverySeq" in discover
    assert "imaMountState.generation" in discover
    assert '$("#ima-discover-btn")' in discover
    assert '$("#ima-group-discovery-status")' in discover
    assert "if (currentButton && document.body.contains(currentButton))" in discover


def test_ima_folder_requests_have_per_key_ownership_and_focus_guards():
    """同 key 目录请求不得互相清理，异步重绘只恢复仍然有效的焦点。"""
    src = APP_JS.read_text(encoding="utf-8")
    load = _fn_body("loadImaFolderChildren")
    select = _fn_body("selectImaMountGroup")
    expand = _fn_body("toggleImaFolderExpand")
    toggle = _fn_body("toggleImaFolder")
    assert "imaMountState.folderRequests" in src
    assert "const request =" in load
    assert "request.generation === imaMountState.generation" in load
    assert "imaMountState.folderRequests.get(key) === request" in load
    assert "imaMountState.folderRequests.delete(key)" in load
    assert "imaFocusSnapshot" in select and "imaFocusSnapshot" in expand and "imaFocusSnapshot" in load
    assert "imaRestoreFocus(focus)" in select
    assert "imaRestoreFocus(focus)" in expand
    assert "imaRestoreFocus(focus)" in toggle
    focus = _fn_body("imaRestoreFocus")
    assert "document.activeElement" in focus
    assert "focus({ preventScroll: true })" in focus


def test_ima_discovery_error_redacts_url_and_secret_key_values_before_escape():
    """发现错误中的 URL、token、sign 等敏感内容必须先脱敏再 escapeHtml。"""
    sample = "自动发现失败：https://ima.qq.com/api?token=secret&sign=signature"
    assert "https://ima.qq.com" in sample and "token=secret" in sample and "sign=signature" in sample
    safe = _fn_body("imaSafeError")
    for pattern in ("https?:", "token", "refresh_token", "authorization", "sign", "q-sign", "Bearer", "<redacted>"):
        assert pattern in safe
    stats = _fn_body("imaGroupDiscoveryStatusText")
    assert "imaSafeError(discoveryError)" in stats
    assert "escapeHtml(safeError)" in stats


def test_ima_group_save_reads_rows_and_preserves_legacy_token_fields():
    """采集配置保存同时提交群组，并保留旧 scalar/token 兼容字段。"""
    save = _fn_body("saveImaCollector")
    assert "groups: readImaMountGroups()" in save
    assert "function readImaMountGroups" in APP_JS.read_text()
    assert "folder_ids" in _fn_body("readImaMountGroups")
    for field in ("uid", "knowledge_base_id", "root_folder_id", "interval_seconds"):
        assert f"{field}:" in save
    assert "if (token) body.refresh_token = token" in save
    knowledge = _fn_body("loadAdminKnowledge")
    assert 'id="ima-pure-token"' not in knowledge
    assert 'id="ima-pure-interval"' not in knowledge
    assert 'id="ima-pure-uid"' not in knowledge
    assert re.search(r'id="ima-pure-token"[^>]*', knowledge) is None
    assert 'value="${pure.refresh_token' not in APP_JS.read_text()


def test_ima_collector_acl_granted_via_separate_put():
    """采集页与用户管理都能授权；ACL 不塞进 collector groups，也不出现在阅读目录。"""
    src = APP_JS.read_text()
    save = _fn_body("saveImaCollector")
    read = _fn_body("readImaMountGroups")
    catalog = _fn_body("renderKnowledge")
    open_user = _fn_body("adminOpenUser")
    persist = _fn_body("adminSaveUserKnowledge")
    load_users = _fn_body("loadAdminUsers")
    assert "<h4>研报库</h4>" in open_user
    assert 'id="um-kb"' in open_user
    assert "data-kb-group" in open_user
    assert "勾选后即可阅读" in open_user
    assert "可自行订阅" not in open_user
    assert "谁能订" not in src
    assert "谁能定" not in src
    assert "knowledgeAclPanelHtml" not in catalog
    assert "knowledgeAclPanelHtml" not in src
    assert "/api/admin/users/" in persist
    assert "ima-kb" in persist
    assert "group_ids" in persist
    assert "/api/admin/ima-collector" in load_users
    assert "acl_usernames" not in save
    assert "acl_usernames" not in read
    knowledge = _fn_body("loadAdminKnowledge")
    assert "谁能阅读" not in knowledge
    assert "查看权限" in knowledge
    assert 'id="ima-group-acl"' in knowledge
    assert "filterAclSuggest" in src
    assert "ima-acl-chip" in src
    assert "ima-acl-search" in src
    assert "ArrowDown" in _fn_body("onAclSearchKey")
    assert 'role="combobox"' in _fn_body("aclPickerHtml")
    assert "saveImaGroupAcl" in src
    assert "/groups/" in _fn_body("saveImaGroupAcl")
    assert 'id="ima-acl-save"' not in knowledge
    assert "s.ima_collector" in knowledge
    assert "initImaMountState" in knowledge


def test_ima_group_acl_search_precedes_compact_chips_and_stays_immediate():
    picker = _fn_body("aclPickerHtml")
    render = _fn_body("renderImaGroupAcl")
    apply = _fn_body("applyAclNamesToPicker")

    assert picker.index("ima-acl-search") < picker.index("ima-acl-chips")
    assert "ima-acl-more" in picker
    assert "toggleImaAclExpanded" in picker
    assert "data-count" in picker
    assert "compact" in render
    assert "syncImaAclMoreButton" in apply
    assert "saveImaGroupAcl" in _fn_body("addAclUser")
    assert "saveImaGroupAcl" in _fn_body("removeAclUser")


def test_ima_discovery_status_is_safe_and_does_not_render_secrets():
    """发现错误只输出 escaped 文本，IMA token 不得进入 HTML value/placeholder。"""
    src = APP_JS.read_text()
    stats = _fn_body("imaGroupDiscoveryStatusText")
    assert "discovery_error" in stats
    assert "escapeHtml" in stats
    assert "last_result" in stats
    assert "refresh_token" not in stats
    assert "imaGroupDiscoveryStatusText" in _fn_body("loadAdminKnowledge")
    assert 'id="ima-pure-token"' not in _fn_body("loadAdminKnowledge")
    assert 'placeholder="${pure.refresh_token' not in _fn_body("loadAdminKnowledge")
    assert 'value="${pure.refresh_token' not in src


def test_admin_stats_has_zsxq_cache_settings():
    """知识库设置页有知识星球组；星球保存带翻页/间隔；数据源保存不再带 zsxq_*。"""
    stats = _fn_body("loadAdminStats")
    knowledge = _fn_body("loadAdminKnowledge")
    assert "pc-zq-pages" not in stats
    assert "pc-zq-pages" in knowledge
    assert "pc-zq-delay" in knowledge
    assert "pc-zq-file-delay" in knowledge
    assert "pc-zq-prefetch" in knowledge
    assert "zq-cache-stat" in knowledge
    assert "purgeZsxqCache()" in knowledge
    polling = _fn_body("savePollingConfig")
    assert "zsxq_max_pages" not in polling
    zsxq = _fn_body("saveZsxqPollingConfig")
    assert "zsxq_max_pages" in zsxq
    assert "zsxq_fetch_delay_seconds" in zsxq
    assert "zsxq_file_delay_seconds" in zsxq
    assert "zsxq_prefetch_files" in zsxq
    purge = _fn_body("purgeZsxqCache")
    assert "/api/admin/zsxq-cache/purge" in purge
    assert "loadAdminStats" not in purge
    fmt = _fn_body("fmtCacheBytes")
    assert 'return "0 MB"' in fmt
    assert "KB" in fmt
    assert "fmtCacheBytes(" in knowledge
    assert "fmtCacheBytes(" in purge


def test_post_header_does_not_clip_platform_or_time():
    """卡片头「名字 · 平台 · 时间」同行时，名字省略不得裁掉平台图标和时间。

    回归：.p-name-line overflow:hidden + .p-name flex:1 会让短名也把
    后面的平台圆标和发布时间裁出可视区（VPS 手机端时间线「时间消失」）。
    """
    css = STYLE_CSS.read_text()
    name_line = re.search(r"\.post-item \.p-name-line\s*\{([^}]*)\}", css)
    name = re.search(r"\.post-item \.p-name\s*\{([^}]*)\}", css)
    time = re.search(r"\.post-item \.p-time\s*\{([^}]*)\}", css)
    platform = re.search(r"\.post-item \.p-name-line \.p-platform\s*\{([^}]*)\}", css)
    assert name_line, "缺少 .p-name-line 规则"
    assert name, "缺少 .p-name 规则"
    assert time, "缺少 .p-time 规则"
    assert platform, "缺少 .p-platform 规则"
    assert "overflow: hidden" not in name_line.group(1)
    assert re.search(r"flex:\s*1(?!\s*1\s*0)", name.group(1)) is None
    assert "flex-shrink: 0" in time.group(1)
    assert "flex-shrink: 0" in platform.group(1)

    post_card = _fn_body("postCard")
    assert 'class="p-time"' in post_card
    assert "fmtPublished(post.published_at)" in post_card
    assert 'class="p-platform"' in post_card


def test_mobile_post_name_aligns_with_platform_badge():
    """移动端名字与平台角标必须同一中线：不能只用 min-height 把名字撑高却让文字贴顶。"""
    css = STYLE_CSS.read_text()
    mobile = re.search(
        r"@media \(max-width: 768px\) \{.*?\.post-item a\.p-name\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert mobile, "缺少移动端 .post-item a.p-name 规则"
    body = mobile.group(1)
    assert "display: block" in body
    assert "line-height: 44px" in body
    assert "height: 44px" in body


def test_timeline_type_roles_follow_four_step_ramp():
    """时间线字号只走四档：头像字形 20、分组标签淡灰 400 + 等宽数字。"""
    css = STYLE_CSS.read_text()
    avatar = re.search(r"\.post-item \.p-header \.kol-avatar\s*\{([^}]*)\}", css)
    group = re.search(r"^\.tl-group-head\s*\{([^}]*)\}", css, re.M)
    badge = re.search(r"^\.tl-badge-avatars \.ph\s*\{([^}]*)\}", css, re.M)
    assert avatar, "缺少帖子头像字号"
    assert "var(--text-icon)" in avatar.group(1)
    assert group, "缺少日期分组标签"
    assert "var(--text-xs)" in group.group(1)
    assert "font-weight: 400" in group.group(1)
    assert "var(--color-text-faint)" in group.group(1)
    assert "tabular-nums" in group.group(1)
    assert badge, "缺少新帖胶囊头像字母"
    assert "var(--text-xs)" in badge.group(1)


def test_new_badge_avatars_fit_inside_capsule():
    """新帖胶囊跟 X NewTweetsPill：40px 条、32px 头像、1px 同色圈、-12px 叠、X 小阴影。"""
    css = STYLE_CSS.read_text()
    js = APP_JS.read_text()
    btn = re.search(r"^\.tl-new-badge-btn\s*\{([^}]*)\}", css, re.M)
    av = re.search(r"^\.tl-badge-avatars > \*\s*\{([^}]*)\}", css, re.M)
    arrow = re.search(r"^\.tl-badge-arrow\s*\{([^}]*)\}", css, re.M)
    assert btn, "缺少 .tl-new-badge-btn"
    assert "height: 40px" in btn.group(1)
    assert "padding: 4px 16px" in btn.group(1)
    assert "overflow: hidden" in btn.group(1)
    assert "var(--text-body)" in btn.group(1)
    assert "0 0 8px rgba(101, 119, 134, 0.2)" in btn.group(1)
    assert av, "缺少胶囊头像尺寸"
    assert "width: 32px" in av.group(1) and "height: 32px" in av.group(1)
    assert "border: 1px solid var(--color-accent)" in av.group(1)
    assert "margin-left: -12px" in av.group(1)
    assert "var(--color-white)" not in av.group(1)
    assert "52px" not in av.group(1) and "24px" not in av.group(1)
    assert arrow, "缺少箭头尺寸"
    assert "width: 20px" in arrow.group(1) and "height: 20px" in arrow.group(1)
    assert 'd="M12 3.59l7.457 7.45-1.414 1.42L13 7.41V21h-2V7.41l-5.043 5.05-1.414-1.42L12 3.59z"' in js
    assert not re.search(r"\.tl-new-badge-btn\s*\{[^}]*overflow:\s*visible", css)


def test_kol_card_name_wraps_full_combination_title():
    """订阅卡片名字独占一行可换行；平台/涨跌标签在下一行，不能把组合名裁成省略号。"""
    css = STYLE_CSS.read_text()
    name = re.search(r"^\.kol-card-info \.name\s*\{([^}]*)\}", css, re.M)
    meta = re.search(r"^\.kol-card-meta\s*\{([^}]*)\}", css, re.M)
    head = re.search(r"^\.kol-card-head\s*\{([^}]*)\}", css, re.M)
    assert name, "缺少 .kol-card-info .name"
    assert "white-space: nowrap" not in name.group(1)
    assert "text-overflow: ellipsis" not in name.group(1)
    assert "overflow-wrap: anywhere" in name.group(1) or "word-break: break-word" in name.group(1)
    assert meta, "缺少 .kol-card-meta"
    assert "display: flex" in meta.group(1) and "flex-wrap: wrap" in meta.group(1)
    assert head and "align-items: flex-start" in head.group(1)
    card = _fn_body("kolCard")
    assert "kol-card-meta" in card
    assert "PLATFORM_LABELS[kol.platform]" in card


def test_timeline_new_badge_pins_to_sticky_filterbar():
    """新帖胶囊挂在吸顶筛选条上，往下滚仍能点，不能跟着时间线一起滑走。"""
    render = _fn_body("renderTimeline")
    html = re.search(r'\$\("#main"\)\.innerHTML = `(.*?)`;', render, re.S)
    assert html, "renderTimeline 未写入主栏 HTML"
    chunk = html.group(1)
    feed = re.search(r'<section class="section-panel tl-feed-panel".*?</section>', chunk, re.S)
    assert feed, "缺少时间线面板"
    assert 'id="tl-new-badge"' not in feed.group(0)
    assert chunk.index('id="tl-filterbar"') < chunk.index('id="tl-new-badge"') < chunk.index('id="tl-feed-panel"')
    css = STYLE_CSS.read_text()
    bar = re.search(r"^\.tl-filterbar\s*\{([^}]*)\}", css, re.M)
    assert bar and "position: sticky" in bar.group(1)
    badge = re.search(r"^\.tl-new-badge\s*\{([^}]*)\}", css, re.M)
    assert badge, "缺少 .tl-new-badge"
    assert "position: absolute" in badge.group(1)
    assert "top: 100%" in badge.group(1)




def test_ima_documents_group_switching_contract():
    """文档列表必须按 URL 群组切换，并让两个控件共享安全的选择逻辑。"""
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    assert "imaDocumentsGroup" in src
    assert "imaDocumentsGroupFromRoute" in src
    assert "imaDocumentsRoute" in src
    assert 'routeQuery().get("group")' in src
    assert "group_name" in src
    assert "params.set(\"group\"" in _fn_body("imaDocumentsRequestPath")
    assert "ima-doc-source" in src
    assert "selectImaDocumentGroup" in src
    assert "routeQuery()" in src
    assert "replaceImaDocumentsRoute(imaDocumentsRoute(value, state.imaDocumentsQuery, \"\", \"\"))" in src
    assert "selectImaDocumentGroup(value)" in src
    assert "state.imaDocumentsDay = \"\"" in src
    assert "escapeHtml(group.id" in src or "escapeHtml(group.value" in src
    assert "escapeHtml(group.name" in src
    assert "没有访问权限" in src


def test_ima_documents_group_controls_render_response_groups_safely():
    """群组控件必须依据响应 groups 渲染，值和标签都经过 escapeHtml。"""
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    assert "data.groups" in render or "groups =" in render
    assert "escapeHtml(group.id" in src or "escapeHtml(group.value" in src
    assert "escapeHtml(group.name" in src
    assert "ima-doc-source" in src
    assert "escapeHtml(group.name" in src


def test_ima_documents_all_group_labels_and_single_group_title():
    """全部知识库结果显示来源标签，单群组结果不重复显示；标题包含名称和数量。"""
    src = APP_JS.read_text()
    assert "item.group_name" in src
    assert "selectedGroupName" in src or "groupName" in src
    assert "count" in _fn_body("renderImaDocuments")


def test_ima_document_group_switch_refreshes_locally():
    """群组切换只更新文档局部路由并使旧请求失效，不触发全局 router。"""
    src = APP_JS.read_text()
    select = _fn_body("selectImaDocumentGroup")
    helper = _fn_body("replaceImaDocumentsRoute")
    assert "replaceRoute(" not in select
    assert "replaceImaDocumentsRoute(imaDocumentsRoute(value, state.imaDocumentsQuery, \"\", \"\"))" in select
    assert "state.imaDocumentsTag = \"\"" in select
    assert "state.imaDocumentsGroup" in select
    assert "state.imaDocumentsDay = \"\"" in select
    assert "state.imaDocumentsQuery" in select
    assert "const seq = ++routeRenderSeq;" in select
    assert "renderImaDocuments(seq)" in select
    assert "normalizeRoute" in helper
    assert "history.replaceState" in helper
    assert "router(" not in helper


def test_ima_documents_filters_round_trip_through_local_url():
    """文档列表从 URL 恢复 q/day，搜索和日期变化通过专用 handler 更新局部 URL。"""
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    route = _fn_body("imaDocumentsRoute")
    assert 'routeQuery().get("q")' in render
    assert 'routeQuery().get("day")' in render
    assert "function imaDocumentsRoute(group, query, day, tag)" in src or "function imaDocumentsRoute(group, query, day)" in src
    assert 'params.set("group", group)' in route
    assert 'params.set("q", query)' in route
    assert 'params.set("day", day)' in route
    assert 'params.set("tag"' in route or 'params.set("tag"' in _fn_body("imaDocumentsRequestPath")
    assert "submitImaDocumentsSearch" in src
    assert "selectImaDocumentsDay" in src
    assert "replaceImaDocumentsRoute(imaDocumentsRoute(" in src
    assert "state.imaDocumentsDay = \"\"" in _fn_body("selectImaDocumentGroup")
    assert "toggleImaDayPicker" in _fn_body("imaDocumentsDayNavHtml")
    assert "kb-desk-day" in _fn_body("imaDocumentsDayNavHtml")
    assert "imaDocumentsDayNavHtml(" in render
    assert "submitImaDocumentsSearch()" in render


def test_local_library_cards_delegate_via_data_attributes():
    """本地库卡片 slug 来自存储机目录名，不得走内联 onclick 字符串插值（F1）。"""
    src = APP_JS.read_text()
    assert "onclick=\"openLocalLibraryModal('" not in src
    assert "onclick=\"toggleLocalLibrary('" not in src
    card = _fn_body("localLibraryCardHtml")
    assert "data-ll-edit" in card and "data-ll-toggle" in card
    assert 'e.target.closest("[data-ll-edit]")' in src
    assert 'e.target.closest("[data-ll-toggle]")' in src


def test_local_scan_button_driven_by_inflight_flag():
    """扫描中状态由模块级标志驱动，15s 轮询重渲染不得复活按钮（F2）。"""
    src = APP_JS.read_text()
    assert "let _scanInFlight = false" in src
    scan = _fn_body("scanLocalLibraries")
    render = _fn_body("renderLocalTab")
    assert "_scanInFlight = true" in scan
    assert "_scanInFlight = false" in scan
    assert "onclick=\"scanLocalLibraries()\"" in render
    assert "_scanInFlight ? \"disabled\" : \"\"" in render
    assert '_scanInFlight ? "扫描中…" : "扫描本地库"' in render


def test_knowledge_settings_p1_p2_control_density():
    """星球日常/高级分层；存储去重不进主工具栏；本地库授权勾选；中金采集默认收起。"""
    knowledge = _fn_body("loadAdminKnowledge")
    assert "高级（翻页、间隔、App 通道）" in knowledge
    assert 'id="pc-zq-comments"' in knowledge
    assert knowledge.index('id="pc-zq-comments"') < knowledge.index('id="pc-zq-pages"')
    storage = _fn_body("imaStoragePanelHtml")
    assert "onclick=\"runStorageDedup()\"" not in storage
    assert "去重每月 1 日 04:00 自动执行" in storage
    assert "onclick=\"runStorageConsistency()\"" in storage
    health = _fn_body("loadStorageHealth")
    assert "onclick=\"runStorageDedup()\"" in health
    card = _fn_body("localLibraryCardHtml")
    assert "<details open" not in card
    assert "details.cicc-collect" in card or 'class="cicc-collect"' in card
    modal = _fn_body("openLocalLibraryModal")
    assert "aclPickerHtml" in modal
    assert "data-acl-remove" in _fn_body("aclChipHtml")
    assert 'id="ll-users"' not in modal
    save = _fn_body("saveLocalLibraryModal")
    assert "现在扫描以应用到库内文档" in save
    assert "[data-ll-user]:checked" not in save
    assert "ima-collector/groups" not in save


def test_ima_reader_nav_requires_matching_snapshot_route():
    """阅读器上一篇/下一篇与结果计数只使用与返回列表路由匹配的快照（F3）。"""
    src = APP_JS.read_text()
    nav = _fn_body("imaReaderNavHtml")
    render = _fn_body("renderImaDocument")
    assert "snapshot = null" in src  # nav 从入参取快照，不再自取模块级变量
    assert "_imaListSnapshot" not in nav
    assert "normalizeRoute(backRoute)" in render
    assert "imaReaderNavHtml(mediaId, item.group_id || documentGroup, listSnapshot)" in render


def test_ima_documents_refresh_and_retry_advance_local_route_seq():
    """刷新与重试必须递增局部路由序号，避免旧请求覆盖新结果。"""
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    refresh = _fn_body("refreshImaDocuments")
    assert "const seq = ++routeRenderSeq;" in refresh
    assert "renderImaDocuments(seq, { keepOld: true })" in refresh
    assert 'onclick="refreshImaDocuments()"' in render
    assert "refreshImaDocuments()" in render


def test_ima_refresh_keeps_old_reports_and_uses_inline_retry():
    refresh = _fn_body("refreshImaDocuments")
    render = _fn_body("renderImaDocuments")
    error = _fn_body("imaReportRefreshErrorHtml")

    assert "keepOld: true" in refresh
    assert "const oldHtml" in render
    assert "ima-report-refresh-error" in error
    assert "最新研报暂时无法更新" in error
    assert "refreshImaDocuments()" in error
    assert "body.innerHTML = oldHtml" in render
    assert "if (!keepOld)" in render
    before_request = render[render.index("if (!keepOld)"):render.index("await api(")]
    assert "_imaItems.length = 0" in before_request
    assert "state.imaDocumentsHasMore = false" in before_request
    success = render[render.index("await api("):]
    assert success.index("_imaItems.length = 0") < success.index("_imaItems.push(...items)")


def test_ima_report_states_do_not_drop_incomplete_documents():
    empty = _fn_body("imaDocumentsEmptyHtml")
    row = _fn_body("imaDocumentRow")
    fail = _fn_body("showImaPdfFail")

    assert "没有找到相关研报" in empty
    assert "换个公司、代码或主题试试" in empty
    assert 'fmtImaDayShort(item.sort_date || item.day) || "—"' in row
    assert "预览打不开" in fail
    assert "downloadImaPdf" not in fail
    assert "btn-normal" not in fail


def test_ima_report_first_layout_is_flat_dense_and_full_width():
    css = STYLE_CSS.read_text()

    assert ".ima-report-page" in css
    assert ".ima-report-head" in css
    assert ".ima-report-columns" in css
    assert ".ima-report-body" in css
    assert ".ima-report-title" in css
    assert ".ima-report-source" in css
    assert "grid-template-columns: 64px minmax(0, 1fr) 132px" in css
    assert re.search(r"\.ima-report-searchbox svg[\s\S]{0,80}width:\s*16px", css)
    assert re.search(r"\.ima-doc-row\s*\{[^}]*min-height:\s*50px", css)
    assert "box-shadow: none" in css
    assert not re.search(r"\.kb-desk\s*\{", css)
    assert ".kb-reader" not in css


def test_ima_dedicated_reader_fills_the_desktop_surface():
    css = STYLE_CSS.read_text()

    assert ".ima-reader-page" in css
    assert ".ima-reader-toolbar" in css
    assert ".ima-reader-info" in css
    assert ".ima-reader-nav" in css
    assert re.search(r"\.ima-reader-page \.ima-pdf-panel\s*\{[^}]*flex:\s*1", css)
    assert "clip-path" not in css[css.index(".ima-reader-page"):]
    assert "color-scheme: light" not in css[css.index(".ima-reader-page"):]


def test_ima_search_ignores_single_ascii_character():
    body = _fn_body("imaUsableSearchQuery")
    assert "length < 2" in body
    assert r"/^[\x00-\x7F]*$/" in body
    src = APP_JS.read_text()
    assert "imaUsableSearchQuery(" in src


def test_report_keyword_watch_uses_settings_switch_not_library_subscribe():
    src = APP_JS.read_text()
    settings = _fn_body("renderSettings")
    assert "匹配研报库" in settings
    assert "set-kw-reports" in settings
    assert "saveKeywordsMatchReports" in settings
    assert "每日研报入库结束" in settings
    assert "管理订阅" not in settings
    assert "toggleReportKeyword" in src
    assert "REPORT_WATCH_BLOCKED_TAGS" in src
    assert "imaReaderWatchHtml" in src
    modal = _fn_body("adminOpenUser")
    assert "勾选后即可阅读" in modal
    assert "可自行订阅" not in modal
    css = STYLE_CSS.read_text()
    assert ".ima-reader-watch .ima-doc-tag.is-action" in css
    assert "min-height: 44px" in css[css.index(".ima-reader-watch .ima-doc-tag.is-action"):css.index(".ima-reader-watch .ima-doc-tag.is-action") + 280]
    assert "管理订阅" not in _fn_body("knowledgeSourceControlsHtml")


def test_ima_source_filter_is_compact_and_subscription_management_survives():
    src = APP_JS.read_text()
    controls = _fn_body("knowledgeSourceControlsHtml")

    assert 'id="ima-doc-source"' in controls
    assert 'aria-label="资料源"' in controls
    assert "selectImaDocumentGroup(this.value)" in controls
    assert "ima-source-manage" not in controls
    assert "管理订阅" not in controls
    assert "subscribeKnowledge" in src
    assert "unsubscribeKnowledge" in src


def test_timeline_filterbar_stays_in_main_column():
    """筛选条只占主列，不横跨右侧栏留下空走廊；不居中、不收窄整页。"""
    render = _fn_body("renderTimeline")
    html = re.search(r'\$\("#main"\)\.innerHTML = `(.*?)`;', render, re.S)
    assert html, "renderTimeline 未写入主栏 HTML"
    chunk = html.group(1)
    assert chunk.index("tl-layout") < chunk.index('id="tl-filterbar"')
    assert 'class="tl-main"' in chunk
    assert chunk.index('class="tl-main"') < chunk.index('id="tl-filterbar"') < chunk.index('id="tl-feed-panel"')
    assert chunk.index('id="tl-feed-panel"') < chunk.index('id="tl-rail"')
    css = STYLE_CSS.read_text()
    assert re.search(r"\.tl-main\s*\{[^}]*min-width:\s*0", css)
    assert "top: 128px" not in css
    assert ".tl-layout { margin: 0 auto" not in css.replace("\n", " ")
    wide = re.search(r"@media \(min-width:\s*1280px\)\s*\{([\s\S]*?)\n\}", css)
    assert wide, "缺少宽屏布局块"
    assert re.search(
        r"\.tl-filterbar\s*\{[^}]*height:\s*64px[^}]*display:\s*flex[^}]*align-items:\s*center",
        wide.group(1),
    )
    assert re.search(
        r"\.tl-rail-head\s*\{[^}]*height:\s*64px[^}]*display:\s*flex[^}]*align-items:\s*center",
        wide.group(1),
    )


def test_timeline_wide_rail_markup():
    """宽屏动态页有右侧栏：开关可搬家，推荐未订阅，标签走 tlPickTag。"""
    render = _fn_body("renderTimeline")
    assert "isWideTimeline()" in render
    assert 'id="tl-rail"' in render
    assert "loadTimelineRail" in render
    assert "tlViewTogglesHtml" in render
    assert "recommendations?unsubscribed=1" in _fn_body("loadTimelineRail")
    assert "railFailHtml" in _fn_body("loadTimelineRail")
    assert "重试" in _fn_body("railFailHtml")
    assert "tlPickTag" in _fn_body("renderRailTags")
    css = STYLE_CSS.read_text()
    assert ".tl-rail" in css
    assert "min-width: 1280px" in css or "min-width:1280px" in css
    assert "max-width: 1279px" in css or "max-width:1279px" in css


def test_live_rail_reuses_sidebar_and_shows_summary():
    """快讯宽屏侧栏复用现有外壳，只显示概览和刷新操作。"""
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    rail = _fn_body("liveRailHtml")
    assert 'id="tl-live-rail"' in _fn_body("renderTimeline")
    assert "liveRailHtml()" in _fn_body("renderLiveRail")
    for text in ("快讯概览", "已加载", "重要快讯", "最新快讯", "刷新快讯"):
        assert text in rail
    assert "_livePosts.filter" in rail
    assert "refreshTimeline()" in rail
    assert "数据来源渠道" not in rail
    assert "wallstreetcn.com/live/global" not in rail
    assert ".tl-layout.live-mode .tl-rail-view" in css
    assert ".tl-layout.live-mode #tl-rail-recs" in css
    assert ".tl-layout.live-mode #tl-rail-tags" in css
    assert ".tl-layout.live-mode .tl-live-rail" in css

def test_timeline_rail_subscription_button_toggles_in_place():
    """推荐按钮用自身状态在 POST/DELETE 间切换，不确认、不刷新推荐列表。"""
    render = _fn_body("renderRailRecs")
    assert 'data-subscribed="0"' in render
    assert "railToggleSubscribe" in render
    assert "tl-rail-subscribe-state" in render
    assert "tl-rail-subscribe-action" in render

    toggle = _fn_body("railToggleSubscribe")
    assert 'method: "POST"' in toggle
    assert 'method: "DELETE"' in toggle
    assert "/api/subscriptions/${kolId}" in toggle
    assert "confirm(" not in toggle
    assert "btn.disabled = true" in toggle
    assert 'setAttribute("aria-busy", "true")' in toggle
    assert "btn.disabled = false" in toggle
    assert 'removeAttribute("aria-busy")' in toggle
    assert 'classList.toggle("subscribed", nextSubscribed)' in toggle
    assert "renderRailRecs(" not in toggle
    assert (
        'flash(`${subscribed ? "退订" : "订阅"}「${name}」失败: ${err.message}`, "error")'
        in toggle
    )


def test_timeline_rail_subscription_button_restores_keyboard_focus_safely():
    """原生 disabled 后仅在键盘焦点掉到 body 时恢复，不抢走用户的新焦点。"""
    toggle = _fn_body("railToggleSubscribe")
    focus_capture = (
        'const restoreFocus = document.activeElement === btn '
        '&& btn.matches(":focus-visible")'
    )
    assert "if (!btn || btn.disabled) return" in toggle
    assert focus_capture in toggle
    assert toggle.index(focus_capture) < toggle.index("btn.disabled = true")

    cleanup = toggle[toggle.index("finally"):]
    focus_guard = (
        "if (restoreFocus && btn.isConnected "
        "&& document.activeElement === document.body)"
    )
    assert "btn.disabled = false" in cleanup
    assert focus_guard in cleanup
    assert cleanup.index("btn.disabled = false") < cleanup.index(focus_guard)
    assert "btn.focus({ preventScroll: true })" in cleanup
    assert "btn.focus()" not in cleanup


def test_timeline_rail_subscription_button_has_quiet_fixed_states():
    """推荐按钮固定宽度；已订阅用现有淡蓝令牌，悬停和键盘聚焦显示退订。"""
    css = STYLE_CSS.read_text()
    rule = re.search(r"\.tl-rail-subscribe\s*\{([^}]*)\}", css)
    assert rule and "width: 72px" in rule.group(1)
    missing_label_layout = [
        declaration
        for declaration in ("padding: 0 6px", "white-space: nowrap")
        if declaration not in rule.group(1)
    ]
    assert not missing_label_layout
    subscribed = re.search(r"\.tl-rail-subscribe\.subscribed\s*\{([^}]*)\}", css)
    assert subscribed and "background: var(--color-accent-soft)" in subscribed.group(1)
    assert "color: var(--color-text-strong)" in subscribed.group(1)
    assert "color: var(--color-accent-text)" not in subscribed.group(1)
    assert ".tl-rail-subscribe.subscribed:hover .tl-rail-subscribe-action" in css
    assert ".tl-rail-subscribe.subscribed:focus-visible .tl-rail-subscribe-action" in css
    assert ".tl-rail-subscribe.subscribed:hover .tl-rail-subscribe-state" in css
    assert ".tl-rail-subscribe.subscribed:focus-visible .tl-rail-subscribe-state" in css
    state_swap = re.search(
        r"\.tl-rail-subscribe\.subscribed:hover \.tl-rail-subscribe-state,\s*"
        r"\.tl-rail-subscribe\.subscribed:focus-visible \.tl-rail-subscribe-state\s*\{([^}]*)\}",
        css,
    )
    action_swap = re.search(
        r"\.tl-rail-subscribe\.subscribed:hover \.tl-rail-subscribe-action,\s*"
        r"\.tl-rail-subscribe\.subscribed:focus-visible \.tl-rail-subscribe-action\s*\{([^}]*)\}",
        css,
    )
    assert state_swap and "display: none" in state_swap.group(1)
    assert action_swap and "display: inline" in action_swap.group(1)


def test_timeline_rail_fills_main_and_survives_resize():
    """主列铺满、右侧 300px；75ch 只限正文；跨 1280px 重排开关。"""
    css = STYLE_CSS.read_text()
    assert "minmax(680px, 1fr) 300px" in css
    assert ".tl-filterbar-top,\n  .tl-layout" not in css and ".tl-filterbar-top,.tl-layout" not in css.replace(" ", "")
    assert re.search(r"\.tl-layout \.tl-feed-panel\s*\{[^}]*flex:\s*1", css)
    render = _fn_body("renderTimeline")
    assert "tlSearchBarHtml()" in render
    assert "tlApplyRailSearch" in APP_JS.read_text()
    assert 'id="tl-category"' not in render
    rail = render[render.index('id="tl-rail"'):]
    assert rail.index("tlSearchBarHtml()") < rail.index("tl-rail-view")
    assert "${tlSearchBarHtml()}${tlViewTogglesHtml()}" not in render
    assert 'class="tl-rail-head"' in rail
    assert 'class="tl-rail-body"' in rail
    assert ".tl-rail-head > .tl-rail-search" in css
    assert re.search(r"\.tl-rail-body\s*\{[^}]*margin-top:\s*16px", css)
    assert re.search(
        r"\.tl-rail-view\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)",
        css,
    )
    assert not re.search(r"\.tl-rail-search\s*\{[^}]*radius-card", css)
    assert re.search(r"\.tl-layout \.tl-feed-panel\s*\{[^}]*margin-top:\s*16px", css)
    assert re.search(r"@media \(min-width:\s*1280px\)[\s\S]*?\.tl-rail\s*\{[^}]*top:\s*56px", css)
    assert "calc(75ch + 2 * var(--section-padding-lg-x))" not in css
    assert ".post-item .p-content" in css and "max-width: 75ch" in css
    assert ".tl-rail-rec .btn-ghost" in css
    assert ".tl-rail-rec-meta" in css and "text-overflow: ellipsis" in css
    src = APP_JS.read_text()
    assert "ensureWideTimelineWatch" in src
    assert "ensureWideTimelineWatch()" in _fn_body("renderTimeline")
    watch = _fn_body("ensureWideTimelineWatch")
    assert "min-width: 1280px" in watch
    assert 'addEventListener("change"' in watch
    assert "renderTimeline(" in watch
    assert "tlSyncFilterChrome()" in _fn_body("tlPickTag")
    assert "renderRailTags" in _fn_body("tlRemoveFilter")


def test_timeline_new_badge_shows_posted_not_count():
    """新帖胶囊跟 X：可见文案是「已发布」，不画 +N，条数只在 aria-label。"""
    src = APP_JS.read_text()
    assert "已发布" in _fn_body("tlNewBadgeLabel")
    assert 'id="tl-new-count"' not in src
    assert "tl-badge-more" not in _fn_body("tlBadgeAvatarsHtml")
    assert "条新${unit}" in _fn_body("pollFeedUpdates")
    assert ".tl-badge-more" not in STYLE_CSS.read_text()
    start = _fn_body("startTimelinePoll")
    assert "15000" in start and "60000" in start
    vis = _fn_body("ensureTimelineVisibilityPoll")
    assert 'addEventListener("visibilitychange"' in vis
    assert "pollFeedUpdates()" in vis


def test_timeline_live_source_is_platform_pill():
    """快讯作为平台条第二项：移除独立动态按钮，保留快讯模式与平台条。"""
    render = _fn_body("renderTimeline")
    pills = _fn_body("tlPillsHtml")
    src = APP_JS.read_text()
    assert 'class="tl-source-switch"' not in render
    assert 'class="tl-source-switch"' not in src
    assert 'class="tl-filterbar-top icon-badge-bar${live ? " is-hidden" : ""}"' not in render
    assert 'data-platform="live"' in pills
    assert "快讯" in pills
    assert "WSCN_LIVE_ICON" in pills
    assert "tlPickSource('live')" in pills
    assert "pollFeedUpdates" in src
    assert 'data-score="' in _fn_body("liveFeedItem")
    css = STYLE_CSS.read_text()
    assert '.live-item[data-score="2"]' in css
    assert '.live-item[data-score="3"]' in css


def test_timeline_source_switch_reuses_shell_when_feed_exists():
    """已在动态页时切快讯只同步壳层，不整页 innerHTML。"""
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    assert "function syncTimelineSourceView" in src
    assert "syncTimelineSourceView(" in _fn_body("tlPickSource")
    assert "syncTimelineSourceView(" in _fn_body("tlPickPlatform")
    render = _fn_body("renderTimeline")
    assert 'class="tl-layout${live ? " live-mode" : ""}"' in render
    assert "const wide = isWideTimeline()" in render
    assert "isWideTimeline() && !live" not in render
    assert ".tl-layout.live-mode" in css
    assert ".tl-layout.live-mode .tl-live-rail" in css


def test_live_feed_is_prefetched_and_shares_inflight_request():
    """进入动态页即预取快讯；点快讯应复用进行中的同一请求。"""
    render = _fn_body("renderTimeline")
    load = _fn_body("loadTimeline")
    src = APP_JS.read_text()
    assert "prefetchLiveFeed()" in render
    assert "prefetchLiveFeed()" in _fn_body("router")
    assert "function prefetchLiveFeed" in src
    assert "function liveWscnRequest" in src
    assert "liveWscnRequest(" in load
    assert "liveWscnRequest(" in _fn_body("prefetchLiveFeed")


def test_xueqiu_badge_uses_official_mark():
    """雪球角标用官方图，盒尺寸仍走 .pt-icon。"""
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    assert 'src="/xueqiu-mark.png"' in src
    assert (APP_JS.parent / "xueqiu-mark.png").is_file()
    assert "img.pt-icon { display: block; object-fit: contain; }" in css
    assert ".pt-icon { width: 16px; height: 16px; flex-shrink: 0; }" in css
    assert ".icon-badge-bar .tl-pill .pt-icon { width: 20px; height: 20px; }" in css
    assert ".post-item .p-name-line .p-platform .pt-icon { width: 13px; height: 13px; }" in css


def test_live_pill_icon_matches_platform_badge_size():
    """快讯角标与其他平台同尺寸，选中不得反色出白圆。"""
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    icon = re.search(r"const WSCN_LIVE_ICON = `([^`]+)`", src).group(1)
    assert 'class="pt-icon"' in icon
    assert "#FFF" not in icon and "#1378F0" not in icon
    assert 'fill="currentColor"' in icon
    assert ".tl-pill.selected .wscn-live-icon" not in css
    assert ".tl-pill .wscn-live-icon { width: 18px" not in css


def test_timeline_pills_stay_content_sized():
    """桌面筛选胶囊按内容收缩，禁止等宽拉伸。"""
    render = _fn_body("renderTimeline")
    css = STYLE_CSS.read_text()
    assert "--tl-pill-count" not in render
    pills = re.search(r"\.tl-pills\s*\{([^}]*)\}", css)
    assert pills and "display: flex" in pills.group(1)
    assert "grid-template-columns: repeat(var(--tl-pill-count" not in css
    assert not re.search(r"\.tl-pill \{ width: 100%;", css)


def test_leaving_live_mode_rerenders_timeline_shell():
    """从快讯点回平台必须重绘时间线壳层，否则宽屏侧栏不会恢复。"""
    pick = _fn_body("tlPickPlatform")
    assert "renderTimeline(routeRenderSeq)" in pick
    assert "isLiveTimeline()" in pick


def test_live_feed_high_priority_text_is_red_and_not_linked():
    """重点快讯的时间、标题和正文统一标红，正文不作为链接。"""
    item = _fn_body("liveFeedItem")
    css = STYLE_CSS.read_text()
    assert '<div class="live-body">' in item
    assert '<a class="live-body"' not in item
    assert '.live-item[data-score="2"] .live-body' in css
    assert '.live-item[data-score="3"] .live-body' in css
    assert '.live-item[data-score="2"] .live-title' in css
    assert '.live-item[data-score="3"] .live-title' in css


def test_web_combination_posts_use_structured_rebalance_details():
    """网页组合帖应展示推送渠道相同的调仓、成交价、现金和现有持仓内容。"""
    card = _fn_body("postCard")
    detail = _fn_body("combinationDetailHtml")
    css = STYLE_CSS.read_text()
    assert "combinationDetailHtml(post)" in card
    for text in ("stats", "actions", "price", "holdings", "cash", "成交价", "现有持仓"):
        assert text in detail
    assert "combo-detail" in detail
    assert ".combo-detail" in css
    assert ".combo-action" in css


def test_web_combination_pc_rows_are_compact_single_line():
    """PC 调仓一行四列、持仓两列；不重复「成交价」前缀、不用 emoji 撑高。"""
    detail = _fn_body("combinationDetailHtml")
    css = STYLE_CSS.read_text()
    assert "combo-action-head" not in detail
    assert "成交价 ${" not in detail
    assert "combo-action-cols" in detail
    for glyph in ("🗑", "🆕", "➕", "➖", "💵"):
        assert glyph not in detail
    assert ".combo-action {" in css
    assert "grid-template-columns: 3.5em minmax(0, 1fr) auto" in css
    assert "combo-action-meta" in detail
    assert ".combo-holdings {" in css
    assert "grid-template-columns: 1fr 1fr" in css
    assert "@media (max-width: 768px)" in css


def test_live_toolbar_keeps_existing_filter_structure():
    """时钟和重要筛选放进白色内容区；搜索复用动态页同一搜索框。"""
    render = _fn_body("renderTimeline")
    head = _fn_body("liveFeedHeadHtml")
    search = _fn_body("tlSearchBarHtml")
    apply_s = _fn_body("tlApplyRailSearch")
    filtered = _fn_body("liveFilteredPosts")
    css = STYLE_CSS.read_text()
    assert "liveFeedHeadHtml()" in render
    assert 'id="live-clock"' in head
    assert 'id="live-important"' in head
    assert "toggleLiveImportant" in head
    assert "live-search" not in head
    assert 'id="live-q"' not in head
    assert 'id="tl-q"' in search
    assert "isLiveTimeline()" in search
    assert "isLiveTimeline()" in apply_s
    assert "liveSearch" in apply_s
    assert "score" in filtered and "state.liveImportant" in filtered
    assert "state.liveQ" in filtered
    assert ".live-feed-head" in css
    assert ".live-search" not in css
    assert "日期" not in head


def test_timeline_feeds_use_scroll_loading_instead_of_more_button():
    """快讯和其他动态源都在列表底部自动加载下一页，并显示加载状态。"""
    src = APP_JS.read_text()
    auto = _fn_body("startFeedAutoLoad")
    stop = _fn_body("stopFeedAutoLoad")
    load_more = _fn_body("feedLoadMore")
    live_render = _fn_body("renderLiveFeed")
    timeline_render = _fn_body("renderTimelineFeed")
    assert 'id="feed-load-sentinel"' in live_render
    assert 'id="feed-load-sentinel"' in timeline_render
    assert "startFeedAutoLoad()" in live_render
    assert "startFeedAutoLoad()" in timeline_render
    assert "IntersectionObserver" in auto
    assert 'rootMargin: "400px 0px"' in auto
    assert "feedLoadMore()" in auto
    assert "disconnect()" in stop
    assert "stopFeedAutoLoad()" in load_more
    assert "正在加载更多" in load_more
    assert 'onclick="feedLoadMore()"' not in live_render
    assert 'onclick="timelineLoadMore()"' not in timeline_render
    assert ".feed-load-spinner" in STYLE_CSS.read_text()


    """渠道勾选不能只看 users.feishu_*，否则个人机器人用户会看到「还没有绑定」。"""
    assert "feishu_personal" in _fn_body("feishuChannelBound")
    assert "feishuChannelBound(user)" in _fn_body("pushChannelsHtml")


def test_settings_webpush_toggle():
    """设置页浏览器通知：开启走订阅 API，关闭走 DELETE。"""
    status = _fn_body("channelStatusHtml")
    assert "enableWebPush()" in status
    assert "disableWebPush()" in status
    assert "webpush_bound" in status
    assert "webPushSupported()" in status
    assert "当前环境不可用" in status
    enable = _fn_body("enableWebPush")
    assert "Notification.requestPermission" in enable
    assert "/api/me/webpush" in enable
    assert "pushManager.subscribe" in enable
    disable = _fn_body("disableWebPush")
    assert 'method: "DELETE"' in disable
    assert "/api/me/webpush" in disable


def test_settings_tabs_use_tab_aria():
    """设置分页与数据源页同一套 tab/tabpanel，切换时写 aria-selected。"""
    render = _fn_body("renderSettings")
    assert 'role="tablist" aria-label="设置分页"' in render
    assert 'role="tab"' in render and "aria-controls=" in render
    assert 'role="tabpanel"' in render
    for tab in ("subs", "push", "bind", "llm", "account"):
        assert f'id="tab-{tab}"' in render
        assert f'aria-controls="st-{tab}"' in render
        assert f'id="st-{tab}"' in render
        assert f'aria-labelledby="tab-{tab}"' in render
    switch = _fn_body("switchSettingsTab")
    assert 'setAttribute("aria-selected"' in switch
    assert "el.hidden = !on" in switch


def test_channel_status_poll_skips_identical_and_restores_focus():
    """渠道状态轮询不得无条件拆掉正在聚焦的开启/关闭按钮。"""
    paint = _fn_body("paintPushStatus")
    assert "html === _pushStatusHtml" in paint
    assert "activeElement" in paint
    assert "match.focus" in paint
    refresh = _fn_body("refreshSettingsStatus")
    assert "paintPushStatus(user)" in refresh
    assert "el.innerHTML = channelStatusHtml" not in refresh


def test_ima_document_counts_use_real_total_not_page_plus():
    """列表/阅读器计数用 document_count，不再用当前页条数拼 50+。"""
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    more = _fn_body("loadImaDocumentsMore")
    reader = _fn_body("renderImaDocument")
    assert "function imaResolvedCount(" in src
    assert "function imaDocumentsCountLabel(" in src
    assert "function imaReaderBackLabel(" not in src
    assert "imaDocumentsCountLabel(" in render
    assert "snapshot.documentCount" in render
    assert "data.document_count" in render
    assert "imaDocumentsCountLabel(" in more
    assert "imaReaderBackLabel" not in reader
    assert "ima-back-count" not in reader
    assert "条结果" not in reader
    assert "imaSnapshotIsFiltered" in src
    assert 'has_more ? "+" : ""' not in render
    assert 'imaDocumentsHasMore ? "+" : ""' not in more
    assert 'hasMore ? "+" : ""' not in reader


def test_ima_pdf_preview_is_inline_on_desktop():
    """PC / 手机 Web 统一内嵌 iframe；右上角新标签作 iOS 逃生舱。"""
    reader = _fn_body("renderImaDocument")
    load = _fn_body("loadImaPdf")
    assert "function imaInlinePdfFrame(" not in APP_JS.read_text()
    assert "ima-pdf-frame" in reader
    assert "ima-pdf-phone-open" not in reader
    assert "openImaPdfNewTab()" in reader
    assert "ima-pdf-phone-open" not in load
    assert "signal: abort.signal" in load or "{ signal: abort.signal }" in load
    assert "#view=FitH" in load


def test_ima_reader_clamps_long_abstract_and_keeps_preview_floor():
    """长摘要默认三行截断，展开后仍限高，预览区保底高度。"""
    src = APP_JS.read_text()
    reader = _fn_body("renderImaDocument")
    css = STYLE_CSS.read_text()
    assert "IMA_ABSTRACT_CLAMP_CHARS" in src
    assert "function toggleImaAbstract(" in src
    assert "is-clamped" in reader
    assert "ima-abstract-more" in reader
    assert "toggleImaAbstract(this)" in reader
    assert ".ima-reader-abstract.is-clamped:not(.is-expanded) p" in css
    assert "-webkit-line-clamp: 3" in css
    assert ".ima-reader-page .ima-pdf-panel {" in css
    assert "min-height: 240px;" in css
    assert "contain: strict;" in css
    assert "align-items: baseline;" in css
    assert ".ima-reader-filemeta {" in css


def test_ima_document_reader_preserves_group_context_and_metadata():
    """阅读页标题显示接口返回的群组和日期，并从当前 URL 保留列表筛选上下文。"""
    src = APP_JS.read_text()
    reader = _fn_body("renderImaDocument")
    assert "let backRoute = imaDocumentsRoute(" in reader
    assert 'currentQuery.get("group")' in reader
    assert 'currentQuery.get("q")' in reader
    assert 'currentQuery.get("day")' in reader
    assert "state.imaDocumentsGroup" in reader
    assert "state.imaDocumentsQuery" in reader
    assert "state.imaDocumentsDay" in reader
    assert "imaDocumentsRoute(listGroup, query, day, tag)" in reader
    assert "item.group_name" in reader
    assert "item.day" in reader
    assert "ima-reader-day" in reader
    assert "ima-reader-toolbar" in reader
    assert "ima-reader-info" in reader
    assert "<details open" in reader
    assert "查看 PDF" not in reader
    assert "ima-reader-download" not in reader
    assert "下载 PDF" not in reader
    assert 'class="btn-ghost ima-reader-back"' not in reader
    assert "ima-back-icon" in reader
    assert ">返回</button>" in reader
    assert "imaDisplayTitle" in reader and "item.size" in reader
    assert "ima-reader-abstract" in reader
    assert "ima-reader-empty" in reader
    assert "还没有预览文件" in reader
    assert "回列表" not in reader
    assert "ima-reader-filemeta" in reader
    assert "section-meta ima-reader-filemeta" not in reader
    assert "needs_translation" in reader
    assert "/translate" in reader


def test_ima_document_reader_requests_keep_current_group_for_all_endpoints():
    reader = _fn_body("renderImaDocument")
    pdf = _fn_body("loadImaPdf")
    download = _fn_body("downloadImaPdf")
    assert "const groupQuery = documentGroup ?" in reader
    assert "${encodeURIComponent(mediaId)}${groupQuery}" in reader
    assert "${encodeURIComponent(mediaId)}/translate${groupQuery}" in reader
    assert 'method: "POST"' in reader
    assert "imaReaderDocumentGroup()" in pdf
    assert "const groupQuery = group ?" in pdf
    assert "${encodeURIComponent(mediaId)}/pdf${groupQuery}" in pdf
    assert "imaReaderDocumentGroup()" in download
    assert "const groupQuery = group ?" in download
    assert "pdf?download=1${groupQuery}" in download
    assert "${encodeURIComponent(mediaId)}${detailQuery}" in download


def test_ima_document_reader_route_preserves_list_filters_without_inline_query_injection():
    """文档行通过 handler 打开，并把当前列表 group/q/day/tag 安全带入阅读 URL。"""

    src = APP_JS.read_text()
    row = _fn_body("imaDocumentRow")
    route = _fn_body("imaDocumentReaderRoute")
    opener = _fn_body("openImaDocument")
    assert "function imaDocumentReaderRoute(mediaId, groupId = \"\")" in src
    assert "state.imaDocumentsTag" in route
    assert "data-media-id=" in row
    assert "data-group-id=\"${escapeHtml(item.group_id || \"\")}\"" in row
    assert 'onclick="openImaDocument(this.dataset.mediaId, this.dataset.groupId)"' in row
    assert "openImaDocument(this.dataset.mediaId, this.dataset.groupId)" in row
    assert "_imaDocumentRoute(item.media_id)" not in row
    assert "imaDocumentReaderRoute(id, groupId)" in opener
    assert "history.pushState" in opener
    assert "++routeRenderSeq" in opener
    assert "mountKnowledgeReaderShell" in opener
    assert "renderImaDocument(seq, id)" in opener


def test_ima_document_row_group_scope_is_escaped_and_reaches_reader_route():
    """全库列表的同名文档必须把所属库安全传给阅读路由。"""
    src = APP_JS.read_text()
    row = _fn_body("imaDocumentRow")
    route = _fn_body("imaDocumentReaderRoute")
    opener = _fn_body("openImaDocument")

    assert 'data-group-id="${escapeHtml(item.group_id || "")}"' in row
    assert row.count("this.dataset.groupId") >= 2
    assert "function imaDocumentReaderRoute(mediaId, groupId = \"\")" in src
    assert 'params.set("doc_group", groupId)' in route
    assert "imaDocumentsRoute(" in route
    assert route.index("listGroup") < route.index("state.imaDocumentsQuery")
    assert "function openImaDocument(mediaId, groupId = \"\", replace = false)" in src
    assert "imaDocumentReaderRoute(id, groupId)" in opener


def test_ima_knowledge_subscription_callbacks_require_current_session_owner():
    """订阅异步响应在成功/失败副作用前都必须仍属于原路由和会话。"""
    for name, success in (("subscribeKnowledge", "已订阅"), ("unsubscribeKnowledge", "已退订")):
        body = _fn_body(name)
        request = body.index("await api(")
        prefix = body[:request]
        for capture in (
            "const routeSeq = routeRenderSeq",
            "const token = state.token",
            "const sessionGeneration = imaMountState.sessionGeneration",
        ):
            assert capture in prefix
        owner_guard = "sessionOwnerStillActive(routeSeq, token, sessionGeneration)"
        success_guard = body.index(owner_guard, request)
        for side_effect in (
            f'flash("{success}")',
            "replaceImaDocumentsRoute(",
            "refreshKnowledge()",
        ):
            assert success_guard < body.index(side_effect, request)
        catch = body.index("} catch (err)", request)
        error_guard = body.index(owner_guard, catch)
        assert error_guard < body.index('flash(err.message ||', catch)
        assert error_guard < body.index("btn.disabled = false", catch)


def test_ima_document_reader_backroute_uses_detail_group_when_url_has_none():
    """直接打开阅读页时，详情返回的群组 ID 也能恢复筛选列表。"""
    reader = _fn_body("renderImaDocument")
    assert "let backRoute = imaDocumentsRoute(listGroup, query, day, tag)" in reader
    assert "item.group_id" in reader
    assert "backRoute = imaDocumentsRoute(item.group_id, query, day, tag)" in reader
    assert reader.index("const item = await api") < reader.index("backRoute = imaDocumentsRoute(item.group_id, query, day, tag)")
    assert reader.index("backRoute = imaDocumentsRoute(item.group_id, query, day, tag)") < reader.index("ima-reader-abstract")
    assert reader.index("backRoute = imaDocumentsRoute(item.group_id, query, day, tag)") < reader.index("loadImaPdf")


def test_ima_document_reader_error_actions_use_scoped_backroute():
    """详情加载失败时，权限和普通错误都必须返回当前列表筛选上下文。"""
    reader = _fn_body("renderImaDocument")
    error = reader[reader.index("  } catch (err) {"):]
    assert error.count('onclick="go(\'${escapeHtml(backRoute)}\')"') == 2
    assert 'onclick="go(\'knowledge\')"' not in error
    assert 'onclick="closeKnowledgeReader()"' not in error


def test_ima_document_reader_omits_empty_source_metadata():
    """没有代码时不输出空的阅读页代码标记。"""
    reader = _fn_body("renderImaDocument")
    assert "const ticker = imaDocTicker(item.name)" in reader
    assert "ticker ?" in reader
    assert "${tickerMeta}" in reader


def test_ima_document_reader_removes_covers_and_labels_text_metadata():
    """阅读页不再渲染缩略图。"""
    src = APP_JS.read_text()
    reader = _fn_body("renderImaDocument")
    css = STYLE_CSS.read_text()
    for value in ("imaSafeCoverUrl", "coverHtml", "item.cover_url", "ima-reader-cover"):
        assert value not in reader, f"阅读页仍包含 {value}"
    assert "function imaSafeCoverUrl" not in src
    assert ".ima-reader-cover" not in css
    assert "imaDisplayTitle(item.name)" in reader


def test_ima_report_header_owns_search_date_and_filters():
    render = _fn_body("renderImaDocuments")
    head_start = render.index('<header class="ima-report-head">')
    head_end = render.index("</header>", head_start)
    head = render[head_start:head_end]

    assert 'id="ima-doc-q"' in head
    assert 'id="ima-doc-day-nav-slot"' in head
    assert 'id="ima-doc-source"' in _fn_body("knowledgeSourceControlsHtml")
    assert 'id="ima-doc-tag"' in head
    assert head.index('id="ima-doc-q"') < head.index('id="ima-doc-day-nav-slot"')


def test_knowledge_desk_defaults_to_latest_stream():
    """无日期时拉最新流并分页，不把 URL 写成某一天。"""
    render = _fn_body("renderImaDocuments")
    nav = _fn_body("imaDocumentsDayNavHtml")
    day = _fn_body("selectImaDocumentsDay")
    assert "streamMode" in render
    assert "paged" in render
    assert 'params.set("limit"' in _fn_body("imaDocumentsRequestPath")
    assert "replaceImaDocumentsRoute(imaDocumentsRoute(selectedGroup, query, data.day, tag))" not in render
    assert "最新" in nav
    assert "if (!day) return" not in day


def test_ima_report_row_is_document_first_and_keeps_optional_metadata():
    row = _fn_body("imaDocumentRow")
    meta = _fn_body("imaReportMetaHtml")

    assert "ima-report-date" in row
    assert "ima-report-title" in row
    assert "ima-report-meta" in row
    assert "ima-report-source" in row
    assert 'fmtImaDayShort(item.sort_date || item.day) || "—"' in row
    assert "imaListTitle(item.name)" in row
    assert "imaDocTicker(item.name)" in meta
    assert "imaDistinctiveTags" in meta
    assert "fmtDocSize" in meta
    assert "item.group_name" in row
    assert "unknown" not in row


def test_ima_report_search_is_debounced_and_explicitly_pages():
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    queued = _fn_body("queueImaDocumentsSearch")
    more = _fn_body("loadImaDocumentsMore")

    assert "250" in queued
    assert "clearTimeout(_imaSearchTimer)" in queued
    assert "submitImaDocumentsSearch()" in queued
    assert 'oninput="queueImaDocumentsSearch()"' in render
    assert 'id="ima-docs-more"' in render
    assert 'role="status"' in render
    assert 'startImaDocumentsAutoLoad()' in render
    auto = _fn_body("startImaDocumentsAutoLoad")
    assert "IntersectionObserver" in auto
    assert "root: body" in auto
    assert "正在加载更多" in more
    assert "加载失败，重试" in more


def test_ima_report_render_reuses_mounted_header_and_cancels_stale_search():
    render = _fn_body("renderImaDocuments")
    submit = _fn_body("submitImaDocumentsSearch")
    stop = _fn_body("stopImaDocumentsAutoLoad")
    queued = _fn_body("queueImaDocumentsSearch")

    assert render.index('querySelector(".ima-report-head")') < render.index("listRoot.innerHTML")
    assert "document.activeElement" in render
    assert '$("#ima-doc-source")' in render
    assert '$("#ima-report-page")' in submit
    assert "return" in submit
    assert "clearTimeout(_imaSearchTimer)" in stop
    assert "_imaSearchTimer = null" in stop
    assert "_imaSearchComposing" in queued or "isComposing" in queued


def test_ima_reader_captures_and_restores_the_loaded_result_set():
    src = APP_JS.read_text()
    capture = _fn_body("captureImaListSnapshot")
    current = _fn_body("currentImaListSnapshot")
    restore = _fn_body("restoreImaListSnapshot")
    opener = _fn_body("openImaDocument")
    refresh = _fn_body("refreshImaDocuments")

    assert "_imaItems.map" in capture
    assert "scrollTop" in capture
    assert "state.imaDocumentsHasMore" in capture
    assert "location.pathname + location.search" in capture
    assert "captureImaListSnapshot" in opener
    assert "snapshot.route" in current
    assert "location.pathname + location.search" in current
    assert "requestAnimationFrame" in restore
    assert "scrollTop" in restore
    assert "api(" not in restore
    assert "consumed" in capture or "consumed" in restore
    assert "consumed" in current
    assert "renderImaDocuments" in refresh


def test_ima_reader_has_one_app_download_and_result_neighbors():
    reader = _fn_body("renderImaDocument")
    nav = _fn_body("imaReaderNavHtml")
    back = _fn_body("backFromImaReader")

    assert "ima-reader-toolbar" in reader
    assert "backFromImaReader" in reader
    assert "ima-reader-download" not in reader
    assert "下载 PDF" not in reader
    assert 'class="btn-ghost ima-reader-back"' not in reader
    assert "ima-back-icon" in reader
    assert ">返回</button>" in reader
    assert "<details open" in reader
    assert "imaReaderNavHtml" in reader
    assert "openImaDocument" in nav
    assert ", true)" in nav
    assert "this.dataset.mediaId" in nav
    assert "data-media-id=" in nav
    assert "history.back()" in back
    assert "go(fallbackRoute)" in back
    assert "downloadImaPdf" not in _fn_body("showImaPdfFail")


def test_ima_reader_separates_document_group_from_list_source_filter():
    route = _fn_body("imaDocumentReaderRoute")
    reader = _fn_body("renderImaDocument")
    group = _fn_body("imaReaderDocumentGroup")

    assert 'params.set("doc_group", groupId)' in route
    assert 'currentQuery.get("group")' in reader
    assert 'currentQuery.get("doc_group")' in reader
    assert "imaDocumentsRoute(listGroup, query, day, tag)" in reader
    assert 'routeQuery().get("doc_group")' in group
    assert "imaReaderDocumentGroup()" in _fn_body("loadImaPdf")
    assert "imaReaderDocumentGroup()" in _fn_body("downloadImaPdf")


def test_ima_day_picker_restricts_to_available_days():
    """日期菜单只列出有文档的 MMDD，点选走 selectImaDocumentsDay。"""
    src = APP_JS.read_text()
    nav = _fn_body("imaDocumentsDayNavHtml")
    menu = _fn_body("imaDayMenuHtml")
    pick = _fn_body("pickImaDay")
    row = _fn_body("imaDocumentRow")
    meta = _fn_body("imaReportMetaHtml")
    reader = _fn_body("renderImaDocument")
    assert "toggleImaDayPicker" in nav
    assert "aria-haspopup" in nav
    assert "kb-desk-day-option" in menu
    assert "selectImaDocumentsDay" in pick
    assert "closeImaDayPicker" in src
    assert "imaDocTicker" in meta
    assert "fmtImaDayShort" in row
    assert "imaListTitle" in row
    assert "white-space: nowrap" in STYLE_CSS.read_text() or "ellipsis" in STYLE_CSS.read_text()
    assert "<details" in reader
    assert "navpanes=0" not in _fn_body("loadImaPdf")


def test_ima_document_list_hides_tag_rail_but_keeps_tag_filtering():
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    assert 'id="ima-doc-tag-rail"' not in render
    assert "imaDocTagRailHtml" not in src
    assert 'id="ima-doc-tag"' in render
    assert "tagSelect.hidden" in render or "tagSelect.removeAttribute(\"hidden\")" in render or "hidden" in render
    assert "uniqueTags" in render


def test_financial_news_navigation_keeps_quick_news_in_timeline():
    src = APP_JS.read_text()
    nav = src[src.index("const NAV ="):src.index("const SIDEBAR_SLIM_KEY")]
    mobile = src[src.index("const MOBILE_NAV ="):src.index("function renderBottomNav")]
    assert nav.index('route: "timeline"') < nav.index('route: "news"') < nav.index('route: "knowledge"')
    assert 'label: "财经新闻"' in nav
    assert 'route: "news"' in mobile
    assert 'data-platform="live"' in _fn_body("tlPillsHtml")


def test_news_reader_functions_cover_sources_seen_and_blob_cleanup():
    src = APP_JS.read_text()
    for name in (
        "renderNewsCenter", "loadFinancialNews", "openNewsSourcePicker",
        "saveNewsSources", "openNewsArticle", "loadNewsImages", "clearNewsImageUrls",
    ):
        assert f"function {name}" in src or f"async function {name}" in src
    seen = _fn_body("loadFinancialNews")
    assert '"/api/news/seen"' in seen
    assert "view_started_at" in seen
    images = _fn_body("clearNewsImageUrls")
    assert "URL.revokeObjectURL" in images


def test_news_source_picker_is_searchable_checkbox_dialog():
    body = _fn_body("openNewsSourcePicker")
    assert 'type="search"' in body
    body = body + _fn_body("newsSourcePickerRows")
    assert 'type="checkbox"' in body
    assert 'role="dialog"' in body
    assert "我的来源" in body


def test_news_source_picker_preserves_selection_across_search():
    open_picker = _fn_body("openNewsSourcePicker")
    save = _fn_body("saveNewsSources")
    assert "newsSelectedIds" in open_picker
    assert "mask._newsSelectedIds" in save
    assert "newsSourcePickerRows(event.target.value" in open_picker


def test_admin_news_tab_is_full_feed_manager():
    src = APP_JS.read_text()
    assert 'const STATS_TABS = ["config", "cookies", "proxies", "plaza", "news"]' in src
    for name in (
        "loadAdminNews", "renderAdminNews", "openNewsSourceModal",
        "openNewsFeedModal", "validateNewsFeedDraft", "refreshAdminNewsFeed",
        "archiveAdminNewsSource", "restoreAdminNewsSource",
    ):
        assert f"function {name}" in src or f"async function {name}" in src
    assert "财经资讯" in src
    assert "显示已归档" in src
    assert "验证并保存" in src


def test_admin_news_master_detail_is_responsive():
    css = STYLE_CSS.read_text()
    assert ".news-admin-layout" in css
    assert "grid-template-columns: 240px minmax(0, 1fr)" in css
    mobile = _media_block(css, "@media (max-width: 768px)", last=True)
    assert ".news-admin-layout" in mobile
    assert "grid-template-columns: 1fr" in mobile


def test_frontend_asset_urls_bust_browser_cache():
    """前端改动必须递增静态资源版本，避免 CDN/浏览器继续使用旧 JS/CSS。"""
    html = (APP_JS.parent / "index.html").read_text()
    sw = (APP_JS.parent / "sw.js").read_text()
    assert 'href="/style.css?v=261"' in html
    assert 'src="/app.js?v=371"' in html
    assert 'dav-shell-v240' in sw


def test_ima_discovery_button_stays_compact_on_mobile():
    css = STYLE_CSS.read_text()
    assert ".refresh-icon { width: 16px; height: 16px; flex: 0 0 auto; }" in css
    assert ".ima-groups-toolbar { width: auto; }" in css
    assert ".ima-groups-toolbar button { width: auto; }" in css


def test_ima_documents_follow_latest_dynamic_navigation():
    src = APP_JS.read_text()
    nav = src[src.index("const NAV ="):src.index("const SIDEBAR_SLIM_KEY")]
    mobile = src[src.index("const MOBILE_NAV ="):src.index("function renderBottomNav")]
    timeline = src[src.index("async function renderTimeline"):src.index("function startTimelinePoll")]
    assert nav.index('route: "timeline"') < nav.index('route: "knowledge"')
    assert 'route: "ima-documents"' not in nav
    assert "IMA 文档" not in nav
    assert 'label: "研报库"' in nav
    assert 'group: "资料"' not in nav
    assert 'route: "ima-documents"' not in mobile
    assert 'route: "knowledge"' not in mobile
    assert "renderKnowledgePhoneBlocked" not in src
    assert "知识库请在电脑上打开" not in src
    assert 'class="tl-ima-entry"' in timeline
    assert "go('knowledge')" in timeline
    assert "研报库" in timeline
    assert "打开研报库" in timeline
    css = STYLE_CSS.read_text()
    assert ".tl-ima-entry { display: none; }" in css
    # 手机（≤768px）也显示入口：知识库已放开移动端
    assert "@media (max-width: 900px) {\n  .tl-ima-entry { display: block; margin: 0 0 12px; }" in css



def test_knowledge_parallel_loads_catalog_and_first_page():
    render = _fn_body("renderKnowledge")
    list_fn = _fn_body("renderImaDocuments")
    path_fn = _fn_body("imaDocumentsRequestPath")
    skeleton = render.index("admin-skeleton")
    catalog = render.index('api("/api/ima-documents/catalog")')
    documents = render.index("api(imaDocumentsRequestPath())")
    first_await = render.index("await ")
    settled = render.index("Promise.allSettled")
    assert skeleton < catalog < first_await
    assert skeleton < documents < first_await
    assert "Promise.allSettled" in render
    assert settled >= first_await
    assert "prefetched" in list_fn
    assert "await prefetched" in list_fn
    assert "imaDocumentsRequestPath()" in list_fn
    assert "研报库目录加载失败" in render
    assert "refreshKnowledge()" in render
    assert "refreshImaDocuments()" in list_fn
    assert 'params.set("limit", "50")' in path_fn
    assert 'params.set("q", query)' in path_fn
    assert "currentImaListSnapshot()" in render
    assert "mediaId || currentImaListSnapshot()" in render
    assert "!mediaId && !snapshot" in render
    assert "catalogOk && selectedGroup" in render
    assert "!subscribed.length && catalogOk" in render


def test_knowledge_index_status_copy_is_admin_only():
    status_fn = _fn_body("imaCollectorStatusText")
    knowledge = _fn_body("renderKnowledge")
    assert "索引重建中" in status_fn
    assert "索引回退" in status_fn
    assert "索引异常" in status_fn
    assert "status.index" in status_fn
    assert "索引重建中" not in knowledge
    assert "索引回退" not in knowledge
    assert "索引异常" not in knowledge


def test_knowledge_report_first_shell_uses_one_surface_per_route():
    src = APP_JS.read_text()
    list_shell = _fn_body("mountKnowledgeListShell")
    reader_shell = _fn_body("mountKnowledgeReaderShell")
    render = _fn_body("renderKnowledge")

    assert 'id="ima-report-page"' in list_shell
    assert 'id="kb-list"' in list_shell
    assert 'id="kb-reader"' not in list_shell
    assert 'id="ima-reader-page"' in reader_shell
    assert 'id="kb-reader"' in reader_shell
    assert 'id="kb-list"' not in reader_shell
    assert "mediaId" in render
    assert "mountKnowledgeReaderShell()" in render
    assert "mountKnowledgeListShell()" in render


def test_knowledge_defaults_to_all_readable_sources():
    render = _fn_body("renderKnowledge")
    controls = _fn_body("knowledgeSourceControlsHtml")

    assert "subscribed.length === 1" not in render
    assert "rememberedKnowledgeGroup" not in APP_JS.read_text()
    assert 'id="ima-doc-source"' in controls
    assert '>全部研报<' in controls
    assert "state.imaCatalogSubscribed" in controls
    assert "管理订阅" not in controls
    assert "knowledgeLibRowHtml" in render
    assert "subscribeKnowledge" in APP_JS.read_text()


def test_ima_display_title_strips_pdf_and_english_duplicate():
    body = _fn_body("imaDisplayTitle")
    js = (
        "function imaDisplayTitle(name) " + body + "\n"
        "const samples = ["
        "  ['x.pdf', 'x'],"
        "  ['高盛-蒙牛乳业（2319.HK）1H26速评：营收全面复苏 Mengniu Dairy （2319.HK）： First Take.pdf',"
        "   '高盛-蒙牛乳业（2319.HK）1H26速评：营收全面复苏'],"
        "  ['笔记-副本', '笔记']"
        "];"
        "for (const [raw, want] of samples) {"
        "  const got = imaDisplayTitle(raw);"
        "  if (got !== want) { console.error(JSON.stringify({raw, got, want})); process.exit(1); }"
        "}"
    )
    subprocess.run(["node", "-e", js], check=True)


def test_knowledge_report_list_does_not_auto_open_a_reader():
    render = _fn_body("renderImaDocuments")
    assert "ensureKnowledgeReaderOpen" not in APP_JS.read_text()
    assert "openImaDocument(items[0]" not in render
    assert "mountKnowledgeReaderShell" not in render


def test_ima_report_metadata_contract_keeps_existing_capabilities():
    src = APP_JS.read_text()
    render = _fn_body("renderImaDocuments")
    reader = _fn_body("renderImaDocument")

    assert 'placeholder="搜标题、公司、代码、行业或资料源"' in render
    assert 'params.set("tag"' in _fn_body("imaDocumentsRequestPath")
    assert "data.days" in render
    assert "loadImaDocumentsMore" in src
    assert "loadImaPdf(mediaId, readerSeq)" in reader
    assert "needs_translation" in reader
    assert "renderImaDocuments" in _fn_body("selectImaDocumentGroup")
    assert ".ima-report-page" in STYLE_CSS.read_text()


def test_ima_documents_search_leaves_day_view():
    src = APP_JS.read_text()
    submit = _fn_body("submitImaDocumentsSearch")
    tag = _fn_body("selectImaDocumentsTag")
    day = _fn_body("selectImaDocumentsDay")
    clear = _fn_body("clearImaDocumentsFilters")
    render = _fn_body("renderImaDocuments")
    more = _fn_body("loadImaDocumentsMore")
    assert "state.imaDocumentsDay = \"\"" in submit
    assert "state.imaDocumentsDay = \"\"" in tag
    assert "state.imaDocumentsQuery = \"\"" in day
    assert "state.imaDocumentsTag = \"\"" in day
    assert "if (!day) return" not in day
    assert "state.imaDocumentsDay = \"\"" in clear
    assert "_imaListSeq" in render
    assert "_imaListSeq" in more


def test_register_placeholder_matches_username_min_length():
    html = (APP_JS.parent / "index.html").read_text()
    assert 'id="reg-username"' in html
    assert "6-30 位，字母或中文开头" in html
    assert "至少 6 位字符" in html
    assert "至少 2 位字符" not in html
    assert "USERNAME_RE" in APP_JS.read_text()
    assert "usernameRuleError" in APP_JS.read_text()
    assert 'id="page-title"' in html and "<h1 id=\"page-title\"" in html
    assert 'class="skip-link" href="#main"' in html
    assert "Bark / 浏览器" in html


def test_settings_controls_are_44px_by_default():
    css = STYLE_CSS.read_text()
    tab = css[css.index(".settings-tab {"):css.index(".settings-tab:hover")]
    assert "min-height: 44px" in tab
    btn = css[css.index(".channel-btn {"):css.index(".channel-btn.primary")]
    assert "min-height: 44px" in btn
    icon = css[css.index(".icon-btn {"):css.index(".icon-btn:hover")]
    assert "width: 44px" in icon and "height: 44px" in icon
    ghost = css[css.index(".btn-ghost {"):css.index(".btn-ghost:hover")]
    assert "min-height: 44px" in ghost


def test_settings_section_titles_are_h2_under_page_h1():
    render = _fn_body("renderSettings")
    assert '<h2 class="section-title">推送开关</h2>' in render
    assert 'id="set-x-translate"' in render
    assert '<h3 class="section-title">' not in render


def test_login_tabs_own_tabpanels():
    html = (APP_JS.parent / "index.html").read_text()
    assert 'aria-controls="login-form"' in html
    assert 'aria-controls="register-form"' in html
    assert 'id="login-form"' in html and 'role="tabpanel"' in html
    switch = _fn_body("switchAuthMode")
    assert "loginForm.hidden = !isLogin" in switch
    assert "registerForm.hidden = isLogin" in switch


def test_admin_backup_page_three_panels_download_skips_webdav():
    """备份页：侧栏入口、三块标题；本机下载不得走 WebDAV 上传。"""
    src = APP_JS.read_text()
    assert 'route: "admin/backup"' in src
    body = _fn_body("loadAdminBackup")
    assert "本机备份" in body
    assert "WebDAV 定时" in body
    assert "恢复" in body
    download = _fn_body("backupDownload")
    assert "/api/admin/backup/download" in download
    assert "/api/admin/backup/webdav" not in download
    assert "restore" not in download
    restore = _fn_body("backupRestoreWebDAV")
    assert "confirm(" in restore
    assert "/api/admin/backup/restore/webdav" in restore
    assert "cfg-unit" not in body
    assert "backup-grid" in body
    assert 'class="backup-file-input"' in body


def test_admin_users_page_uses_modal_not_prompt():
    """用户管理：搜索/筛选/管理面板，不再用 prompt/alert 改名、重置密码、测试推送。"""
    src = APP_JS.read_text()
    start = src.index("async function loadAdminUsers")
    end = src.index("// ---------- 主题")
    body = src[start:end]
    assert "prompt(" not in body
    assert "alert(" not in body
    assert "adminOpenUser" in body
    assert "renderAdminUsers" in body
    assert "adminUsersApplyFilter" in body
    assert "userChannelIconsHtml" in body
    assert "adminUserOriginHtml" in body
    assert "adminUserLoginHtml" in body
    open_user = _fn_body("adminOpenUser")
    assert "modal-mask" in open_user
    assert "um-block" in open_user
    assert "um-name" in open_user
    assert "um-pass" in open_user
    assert "um-push-msg" in open_user
    assert "无密码，不能网页登录" in open_user
    assert "登录名不合规" in open_user
    assert "下划线或连字符" in open_user
    for name in ("adminSaveUsername", "adminSavePassword", "adminSendTestPush", "adminDeleteUser", "adminToggleAdmin", "adminSaveUserKnowledge"):
        fn = _fn_body(name)
        assert "flash(" in fn, f"{name} 应使用 flash toast"
        assert "prompt(" not in fn
        assert "alert(" not in fn


def test_admin_users_page_has_batch_bar():
    """用户管理：勾选列 + 表上方批量条（开/关推送/删除）。"""
    render = _fn_body("renderAdminUsers")
    assert 'id="au-batch-bar"' in render
    assert 'id="au-checkall"' in render
    assert "au-check" in render
    assert "adminUserToggleSelect" in render
    assert "开启推送" in render
    assert "关闭推送" in render
    assert "adminUsersBatch(" in render
    assert "/api/admin/users/batch" in _fn_body("adminUsersBatch")
    src = APP_JS.read_text()
    assert "let _adminUsersSelected" in src
    delete_fn = _fn_body("adminUsersBatch")
    assert "confirm(" in delete_fn
    assert "adminDeleteImpact" in delete_fn
    assert "enable_notify" in delete_fn
    assert "disable_notify" in delete_fn
    assert "delete" in delete_fn
    assert "不能删除管理员" in _fn_body("adminDeleteUser")


def test_admin_users_page_has_inactive_policy():
    """用户管理：未激活天数设置 + 筛选 Tab + 状态列文案。"""
    render = _fn_body("renderAdminUsers")
    assert "未激活" in render
    assert "au-policy" in render
    assert ">登录<" in render
    assert "登录名不合规" in render
    assert 'id="au-inactive-n"' in render
    assert 'id="au-inactive-m"' in render
    assert 'id="au-inactive-save"' in render
    assert "rc-field" in render
    assert "rc-generate" in render
    assert "列为未激活" in render
    assert "之后删除" in render
    assert "adminSaveInactivePolicy" in render
    assert "btn-normal" in render
    assert "inactivePolicyRuleLabel" in render
    assert "领码或网页注册后从未登录" in render
    assert "没有未激活账号" in render
    src = APP_JS.read_text()
    assert "adminSaveInactivePolicy" in src
    assert "adminInactivePolicySyncSave" in src
    assert "adminRefreshInactivePreview" in src
    assert "每天扫一次" in _fn_body("inactivePolicyHint")
    assert "未改过" in _fn_body("inactivePolicyHint")
    assert "默认" in _fn_body("inactivePolicyRuleLabel")
    assert "规则" in _fn_body("inactivePolicyRuleLabel")
    assert "下次扫描将删除" in _fn_body("adminSaveInactivePolicy")
    assert "/api/admin/inactive-users-policy" in _fn_body("adminSaveInactivePolicy")
    assert "/api/admin/inactive-users-policy" in _fn_body("loadAdminUsers")
    filt = _fn_body("adminUsersFiltered")
    assert "inactive" in filt
    assert "days_until_purge" in render
    assert "status-warn" in render


def test_admin_codes_page_has_batch_bar():
    """注册码：列表上方批量条 + 行勾选 + 批次标题全选 + 全选当前筛选。"""
    load = _fn_body("loadAdminCodes")
    assert 'id="rc-batch-bar"' in load
    assert "复制" in load
    assert "作废未用" in load
    assert "清掉废码" in load
    assert 'id="rc-checkall"' in load
    assert "adminCodesTogglePage" in load
    assert "全选当前筛选" in load
    groups = _fn_body("renderCodeGroups")
    assert "rc-batch-check" in groups
    assert "adminCodesToggleBatch" in groups
    row = _fn_body("renderCodeRow")
    assert "rc-check" in row
    assert "adminCodesToggle(this)" in row
    assert "adminCodesBatch" in APP_JS.read_text()
    batch = _fn_body("adminCodesBatch")
    assert "/api/admin/register-codes/batch" in batch
    assert "confirm(" in batch
    assert "copyText(" in _fn_body("adminCodesCopySelected")
    src = APP_JS.read_text()
    assert "adminCodesTogglePage" in src
    assert "adminCodesSyncPageCheck" in src
    assert "adminSaveCodeNote" not in src
    css = STYLE_CSS.read_text()
    assert ".admin-batch-bar" in css
    assert ".rc-check" in css
    assert ".rc-checkall" in css


def test_register_codes_mobile_has_field_labels_and_compact_grid():
    """注册码页移动端：每格带 data-label 字段名、备注独占整行、批次操作两列等宽。"""
    row = _fn_body("renderCodeRow")
    batch = _fn_body("renderCodeGroups")
    css = STYLE_CSS.read_text()

    for label in ("邀请码", "备注", "状态", "使用者", "时间", "操作"):
        assert f'data-label="{label}"' in row
    assert "rc-note-cell" in row
    assert "rc-note-input" not in row
    assert "adminSaveCodeNote" not in row
    assert "rc-counts" in batch  # 可用/已用独立元素，不再混在长行里断行
    assert ".rc-table td::before" in css
    assert 'content: attr(data-label)' in css
    assert "rc-note-cell" in css
    assert "grid-column: 1 / -1" in css
    assert "repeat(2, minmax(0, 1fr))" in css  # 批次操作与表格均为两列等宽网格
    assert ".settings-tabs" in css and "flex-wrap: nowrap" in css  # 筛选一行横向滚动
    hide = re.search(r"([^{}]+)\{[^}]*scrollbar-width:\s*none", css)
    assert hide and ".settings-tabs" in hide.group(1)  # 横向滑动时隐藏滚动条，避免移动端滑动框


def test_register_codes_desktop_controls_share_one_grid():
    """注册码页桌面：生成栏用标签网格对齐，搜索不再套一层 form-control。"""
    body = _fn_body("loadAdminCodes")
    css = STYLE_CSS.read_text()
    assert 'class="rc-generate"' in body
    assert "rc-field-note" in body
    assert "rc-preset" in body
    assert "常用" in body
    assert "cat-chip" not in body
    assert 'class="form-control"' not in body.split('id="rc-q"')[1][:80]
    assert "rc-list-head" in body
    assert "search-bar rc-search" in body
    assert "max-width: 860px" in css
    assert ".rc-preset" in css
    assert "height: var(--control-height-2xl)" in css
    groups = _fn_body("renderCodeGroups")
    assert "rc-batch-title" in groups
    assert "rc-batch-meta" in groups


def test_logout_clears_timeline_and_bind_cache():
    """登出必须清掉动态缓存和绑定码，避免下一账号看到上一账号的数据。"""
    body = _fn_body("logout")
    assert "clearSessionCaches()" in body
    clear = _fn_body("clearSessionCaches")
    assert "_tlPosts.length = 0" in clear
    assert "_tlLoadedFilter = null" in clear
    assert "pendingBind = null" in clear
    assert "state.timelineFavorite = false" in clear
    assert "state.timelineSecondary = false" in clear


def test_logout_clears_ima_account_state_and_invalidates_inflight_requests():
    """登出必须清掉 IMA 账号状态，并使旧请求无法继续拥有当前会话。"""
    clear = _fn_body("clearSessionCaches")
    for statement in (
        "imaMountState.groups = []",
        "imaMountState.drafts = new Map()",
        "imaMountState.folders = new Map()",
        "imaMountState.parents = new Map()",
        "imaMountState.folderRequests = new Map()",
        "imaMountState.discoveryOwner = null",
        "imaMountState.saveOwner = null",
        "imaMountState.collectorDraft = null",
        "imaMountState.collectorConfirmedRevision = \"\"",
        "imaMountState.collectorConfirmedLiveRevision = -1",
        "imaMountState.collectorConfirmedMountRevision = -1",
        "_lastAdminStatsSnapshot = null",
    ):
        assert statement in clear
    assert "imaMountState.generation += 1" in clear
    assert clear.index("imaMountState.saveOwner = null") < clear.index("imaMountState.generation += 1")


def test_ima_old_save_listener_returns_before_observing_new_account_input():
    """旧保存闭包收到新账号输入时，必须先确认仍拥有 saveOwner。"""
    save = _fn_body("saveImaCollector")
    start = save.index("const onDraftChange =")
    end = save.index("imaMountState.saveOwner = saveOwner", start)
    listener = save[start:end]
    assert "if (imaMountState.saveOwner !== saveOwner) return;" in listener
    assert listener.index("imaMountState.saveOwner !== saveOwner") < listener.index("rememberImaCollectorDraft()")


def test_ima_save_response_requires_current_session_and_owner_before_mutation():
    """登出后旧 PUT 响应不得写入新账号的 IMA 状态或界面。"""
    save = _fn_body("saveImaCollector")
    put = save.index('const savedImaStatus = await api("/api/admin/ima-collector"')
    mutation = save.index("saveOwner.savedImaStatus = savedImaStatus", put)
    assert "const sessionGeneration = imaMountState.sessionGeneration" in save
    guard = save.index("sessionGeneration !== imaMountState.sessionGeneration", put)
    assert guard < mutation
    assert "imaMountState.saveOwner !== saveOwner" in save[guard:mutation]


def test_ima_stats_timer_caches_fresh_snapshot_before_render():
    """定时 stats 成功后必须先缓存完整快照，再更新可见状态。"""
    timer = _fn_body("startDashboardLiveTimer")
    render_index = timer.index("renderStatsData(fresh)")
    assert "_lastAdminStatsSnapshot = fresh" in timer
    assert timer.index("_lastAdminStatsSnapshot = fresh") < render_index


def test_ima_stats_timer_owns_each_overlapping_request_and_stop_invalidates_it():
    """每次定时 tick 都有独立 owner；后发 tick 或停表不得让旧响应落地。"""
    src = APP_JS.read_text(encoding="utf-8")
    timer = _fn_body("startDashboardLiveTimer")
    stop = _fn_body("stopStatsTimer")
    assert "let _adminStatsTimerSeq = 0" in src
    assert "_adminStatsTimerSeq += 1" in stop
    timer_start = timer.index("const timerSeq = _adminRenderSeq")
    body = timer[timer_start:]
    assert "const timerRequestSeq = ++_adminStatsTimerSeq" in body
    guard = body.index("if (!routeStillActive(timerSeq)")
    assert "timerRequestSeq !== _adminStatsTimerSeq" in body[guard:]
    assert body.index("_lastAdminStatsSnapshot = fresh") > guard
    assert body.index("renderStatsData(fresh)") > guard


def test_ima_pending_save_uses_session_owner_across_stats_reentry_but_logout_invalidates():
    """stats 重入只改变 mount generation；登出仍须让旧 PUT 失去 session owner。"""
    src = APP_JS.read_text(encoding="utf-8")
    clear = _fn_body("clearSessionCaches")
    save = _fn_body("saveImaCollector")
    assert "sessionGeneration: 0" in src
    assert "imaMountState.sessionGeneration += 1" in clear
    assert "const sessionGeneration = imaMountState.sessionGeneration" in save
    assert "sessionGeneration" in save[save.index("const saveOwner ="):save.index("imaMountState.saveOwner = saveOwner")]
    put = save.index('const savedImaStatus = await api("/api/admin/ima-collector"')
    mutation = save.index("saveOwner.savedImaStatus = savedImaStatus", put)
    guard = save.index("sessionGeneration !== imaMountState.sessionGeneration", put)
    assert guard < mutation
    post_put = save[put:save.index("} catch", put)]
    assert "generation !== imaMountState.generation" not in post_put
    assert "reloadAdminSettingsPage(routeRenderSeq, savedImaStatus)" in post_put
    assert clear.index("imaMountState.saveOwner = null") < clear.index("imaMountState.sessionGeneration += 1")


def test_api_401_only_logs_out_the_session_that_started_the_request():
    """账号切换后，旧账号的 api/apiBlob 401 不得登出新账号。"""
    src = APP_JS.read_text(encoding="utf-8")
    for name in ("api", "apiBlob"):
        start = src.index(f"async function {name}")
        brace = src.index("{", src.index(")", start))
        depth, end = 1, brace + 1
        while depth:
            if src[end] == "{": depth += 1
            elif src[end] == "}": depth -= 1
            end += 1
        body = src[brace:end]
        token = body.index("const requestToken = state.token")
        fetch = body.index("await fetch(", token)
        unauthorized = body.index("resp.status === 401", fetch)
        assert token < fetch < unauthorized
        assert "state.token === requestToken" in body[unauthorized:]
        assert body.index("logout()", unauthorized) > body.index("state.token === requestToken", unauthorized)
        assert body.index("path.startsWith(\"/api/auth/\")", unauthorized) < body.index("logout()", unauthorized)


def test_sticky_chrome_is_opaque_canvas_not_glass():
    """壳层（顶栏/筛选条/侧栏/底栏）用不透明画布色，禁止半透明+saturate 放大色块。"""
    tokens = (APP_JS.parent / "vendor" / "design-tokens.css").read_text()
    css = STYLE_CSS.read_text()
    assert "rgba(15, 17, 21, 0.82)" not in tokens
    assert "rgba(245, 245, 247, 0.78)" not in tokens
    body = re.search(r"^body\s*\{([^}]*)\}", css, re.M)
    assert body and "gradient-page-admin-wide" not in body.group(1)
    topbar = re.search(r"^\.topbar\s*\{([^}]*)\}", css, re.M)
    assert topbar and "backdrop-filter" not in topbar.group(1)
    assert "background: var(--color-bg)" in topbar.group(1)
    bar = re.search(r"^\.tl-filterbar\s*\{([^}]*)\}", css, re.M)
    assert bar and "backdrop-filter" not in bar.group(1)
    assert "calc(-1 * var(--page-pad-x))" in bar.group(1)
    assert css.count("--page-pad-x:") >= 3
    sidebar = re.search(r"^\.sidebar\s*\{([^}]*)\}", css, re.M)
    assert sidebar and "backdrop-filter" not in sidebar.group(1)
    assert "background: var(--color-bg)" in sidebar.group(1)
    bottom = re.search(r"^\.bottom-nav\s*\{([^}]*)\}", css, re.M)
    assert bottom and "backdrop-filter" not in bottom.group(1)
    assert "background: var(--color-bg)" in bottom.group(1)
    assert "backdrop-filter" not in css


def test_admin_kols_keeps_selection_against_filter_ids():
    """跨页勾选按筛选全集清理，不得按当前页 id 丢掉选中项。"""
    body = _fn_body("loadAdminKols")
    assert "state.adminKols = kols" in body
    assert "data.ids" in body
    assert "pageIds.has(id)" not in body


def test_admin_kols_add_keeps_filters_and_marks_row():
    """添加不得改写筛选；新行在当前筛选里就标出，否则说明看不到。"""
    add = _fn_body("adminBatchAddKols")
    load = _fn_body("loadAdminKols")
    assert "state.adminKolsPlatform" not in add
    assert "state.adminKolsCategory" not in add
    assert "goToLast" not in add
    assert "focusIds" in add
    assert "不在当前筛选" in add
    assert "focusIds" in load
    assert "ak-row-flash" in load


def test_admin_kols_add_is_one_form():
    """添加大V与批量导入合为一块：多行输入同时覆盖单条和批量。"""
    src = APP_JS.read_text()
    load = _fn_body("loadAdminKols")
    assert "添加大V" in load
    assert "批量导入大V" not in load
    assert "adminAddKol" not in src
    assert 'id="ad-name"' not in load
    assert 'id="ad-external"' not in load
    assert 'id="ad-batch-lines"' in load
    assert 'onclick="adminBatchAddKols()"' in load
    assert ">添加<" in load


def test_admin_kols_mobile_table_uses_data_labels():
    """窄屏表用 data-label 卡片，桌面仍是表。"""
    body = _fn_body("loadAdminKols")
    assert "ak-table" in body
    assert 'data-label="昵称"' in body
    assert 'data-label="档位"' in body
    assert 'data-label="操作"' in body
    assert "ak-hide-mobile" in body
    css = STYLE_CSS.read_text()
    assert ".ak-table" in css
    assert "ak-hide-mobile" in css
    assert "ak-actions" in css


def test_admin_kols_edit_modal_is_dialog():
    """编辑弹层对齐用户管理：dialog + 焦点循环；白名单仅私有时出现。"""
    body = _fn_body("adminEditKol")
    assert 'role="dialog"' in body
    assert "aria-modal" in body
    assert "aria-labelledby" in body
    assert 'e.key === "Tab"' in body or 'e.key==="Tab"' in body
    assert "ek-users-wrap" in body
    assert "hidden" in body


def test_admin_kols_batch_normal_is_one_request():
    """设普通走一次 batch action=normal，不再连续打两次 flag。"""
    load = _fn_body("loadAdminKols")
    assert "adminKolBatch('normal')" in load
    src = APP_JS.read_text()
    assert "async function adminKolBatchTier" not in src


def test_admin_kols_platform_tab_reads_pending_search():
    """点平台 tab 时要把未提交的搜索框读进 state，避免筛丢。"""
    body = _fn_body("switchAdminKolsPlatform")
    assert "ak-q" in body


def test_admin_kols_filter_controls_match_input_height():
    """列表筛选与平台 tab 跟输入同高 42px，不得用 32px 药丸贴在 42px 框旁边。"""
    body = _fn_body("loadAdminKols")
    chunk = body.split('id="ak-q"')[1].split("admin-kols-tabs")[0]
    assert "btn-ghost" in chunk
    assert 'class="btn-sm"' not in chunk
    assert "ak-filters" in body
    assert "ak-platform-tabs" in body
    css = STYLE_CSS.read_text()
    assert re.search(r"\.toolbar \.btn-ghost[^{]*\{[^}]*--control-height-2xl", css)
    assert re.search(r"\.platform-tab\s*\{[^}]*44px", css, re.S)


def test_admin_kols_mobile_filters_and_actions_align():
    """窄屏：筛选两列网格；操作钮等宽，奇数个时最后一个铺满，避免删除孤一块。"""
    body = _fn_body("loadAdminKols")
    assert "ak-search-btn" in body
    assert "ak-clear-btn" in body
    css = STYLE_CSS.read_text()
    assert ".ak-filters #ak-q" in css
    assert "last-child:nth-child(odd)" in css
    assert ".ak-table td.ak-actions .btn-sm" in css
    assert "margin-right: 0" in css


def test_admin_kols_add_fields_have_accessible_names():
    """添加区控件要有可达名称，不能只靠 placeholder。"""
    body = _fn_body("loadAdminKols")
    src = APP_JS.read_text()
    assert 'id="ad-batch-platform"' not in body
    assert "默认平台" not in body
    assert "adminPlatformDefaultCat" not in src
    assert 'aria-label="分类"' in body
    assert 'aria-label="大V主页链接，每行一个"' in body
    assert "平台由链接自动识别" in body
    assert "adminBatchLinesHint()" in body
    assert "function adminBatchLinesHint(" in src


def test_admin_kols_import_result_preserves_lines():
    """导入失败明细按行展示，不能塞进 inline span 把换行挤掉。"""
    body = _fn_body("loadAdminKols")
    css = STYLE_CSS.read_text()
    assert '<span id="ad-batch-result"' not in body
    assert "ad-batch-result" in body
    assert "ak-add-result" in body
    assert re.search(r"\.ak-add-result\s*\{[^}]*white-space:\s*pre-line", css)


def test_type_emphasis_stays_on_ramp():
    """强调用字重/等宽，不上 1.1em 或 700。绑定码走 mono token。"""
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    assert "font-size:1.1em" not in src
    assert "class=\"bind-code\"" in _fn_body("fsPersonalStateHtml")
    assert 'resultEl.style.fontWeight = "600"' in _fn_body("adminBatchAddKols")
    paste = re.search(r"^\.cookie-paste\s*\{([^}]*)\}", css, re.M)
    bind = re.search(r"^\.bind-code\s*\{([^}]*)\}", css, re.M)
    add_lines = re.search(r"^\.ak-add-lines\s*\{([^}]*)\}", css, re.M)
    assert paste and "var(--font-mono)" in paste.group(1) and "var(--text-sm)" in paste.group(1)
    assert bind and "var(--font-mono)" in bind.group(1) and "var(--text-body)" in bind.group(1)
    assert add_lines and "var(--font-mono)" in add_lines.group(1) and "var(--text-sm)" in add_lines.group(1)


def test_admin_kols_mutations_disable_while_in_flight():
    """添加/导入/保存/批量进行中要禁用，防连点。"""
    for name in ("adminBatchAddKols", "adminKolBatch", "saveKolEdit"):
        body = _fn_body(name)
        assert "disabled" in body, f"{name} 无进行中禁用"


def test_admin_kols_delete_and_private_name_consequences():
    """单删要说清级联；私有空名单要明示对所有人隐藏。"""
    delete = _fn_body("adminDeleteKol")
    assert "订阅" in delete
    assert "帖子" in delete
    save = _fn_body("saveKolEdit")
    assert "对所有人隐藏" in save


def test_admin_kols_edit_modal_dirty_check():
    """未保存修改时点遮罩/Esc 必须确认，不能直接丢掉白名单。"""
    body = _fn_body("adminEditKol")
    assert "dirty" in body.lower() or "未保存" in body


def test_admin_kols_batch_can_unset_tier():
    """批量栏能设普通档，不能只设优先/次要。"""
    body = _fn_body("loadAdminKols")
    assert "adminKolBatch('priority', false)" in body or "adminKolBatchTier(" in body or "设普通" in body


def test_admin_kols_tier_and_private_copy():
    """档位用普通/优先/次要；私有用警告色；原创只在微博显示。"""
    body = _fn_body("loadAdminKols")
    assert "普通" in body and "优先" in body and "次要" in body
    assert "status-warn" in body
    assert 'k.platform === "weibo"' in body or "k.platform == \"weibo\"" in body


def test_admin_kols_errors_use_flash_not_alert():
    """大V管理失败走 flash error，不弹 alert。"""
    for name in (
        "adminBatchAddKols",
        "adminKolBatch",
        "adminToggleKol",
        "adminTogglePriority",
        "adminToggleSecondary",
        "adminDeleteKol",
        "saveKolEdit",
    ):
        body = _fn_body(name)
        assert "alert(" not in body, f"{name} 仍使用 alert"
        assert 'flash(' in body and '"error"' in body, f"{name} 失败未走 flash error"


def test_admin_kols_empty_and_filter_controls():
    """空状态要算上平台筛选；搜索可点、可清除；全选支持 indeterminate。"""
    body = _fn_body("loadAdminKols")
    assert "adminKolsPlatform" in body
    assert "adminKolsClearFilter" in body or "清除" in body
    assert "adminKolsApplyFilter()" in body
    assert "indeterminate" in _fn_body("adminKolSyncCheckall")


def test_type_scale_uses_four_reading_roles():
    """产品字号只保留四档阅读角色：12 元信息 / 13 控件 / 15 正文 / 17 标题。"""
    tokens = (APP_JS.parent / "vendor" / "design-tokens.css").read_text()
    css = STYLE_CSS.read_text()
    assert re.search(r"--text-xs:\s*12px", tokens)
    assert re.search(r"--text-sm:\s*13px", tokens)
    assert re.search(r"--text-body:\s*15px", tokens)
    assert re.search(r"--text-title:\s*17px", tokens)
    assert re.search(r"--text-display:\s*30px", tokens)
    assert "--font-mono:" in tokens
    assert re.search(r"--font-weight-bold:\s*600", tokens)
    for retired in ("--text-md:", "--text-lg:", "--text-xl:", "--text-title-sm:"):
        assert retired not in tokens, f"token 仍保留已废弃的 {retired}"
        assert retired not in css, f"样式仍引用已废弃的 {retired}"

    body = re.search(r"^body\s*\{([^}]*)\}", css, re.M)
    assert body and "font-size: var(--text-body)" in body.group(1)
    assert "font-size: 14px" not in css

    content = re.search(r"\.post-item \.p-content\s*\{([^}]*)\}", css)
    assert content, "未找到 .post-item .p-content"
    block = content.group(1)
    assert "font-size: var(--text-body)" in block
    assert "word-break: break-all" not in block
    assert "overflow-wrap:" in block
    assert re.search(r"line-height:\s*1\.65", block)

    time = re.search(r"\.post-item \.p-time\s*\{([^}]*)\}", css)
    assert time and "tabular-nums" in time.group(1)

    for size in ("10px", "11px"):
        for match in re.finditer(rf"font-size:\s*{re.escape(size)}", css):
            window = css[max(0, match.start() - 80) : match.end()]
            assert "cube-nav" in window, f"{size} 只能用于图表刻度: {window!r}"


def test_success_token_is_muted_sage():
    """成功色用鼠尾草绿，不用高饱和交通灯绿。"""
    tokens = (APP_JS.parent / "vendor" / "design-tokens.css").read_text()
    assert "--color-success: #3a6e4b;" in tokens
    assert "#16a34a" not in tokens
    assert "rgba(52, 199, 123" not in tokens


def test_admin_chart_system_uses_tokens_and_external_rate_label():
    """管理端图表：净值面积走数据色、成功率数字在条外、趋势有名称、KPI 有 class。"""
    src = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    assert "var(--color-data-positive-soft)" in src
    assert "var(--color-data-negative-soft)" in src
    assert "rgba(230,67,64" not in src
    rate = _fn_body("rateBar")
    assert "rate-row" in rate
    assert "rate-label" in rate
    assert "background:${color}" not in rate
    assert "aria-label" in _fn_body("loadAdminDashboard")
    assert 'class="dash-stat"' in _fn_body("statCard")
    assert ".dash-stats" in css
    assert ".dash-split" in css
    assert "grid-template-columns: minmax(0, 1fr) auto" in css
    assert "qr-frame" in src
    assert 'class="qr-card"' in _fn_body("startWeiboQr")
    assert "onclick=\"loadAdminDashboard()\"" in _fn_body("loadAdminDashboard")


def test_weibo_qr_poll_is_serial():
    """微博扫码轮询必须等上一轮结束再调度下一轮，避免成功后被并发 404 盖成过期。"""
    start = _fn_body("startWeiboQr")
    poll = _fn_body("pollWeiboQr")
    assert "setInterval" not in start
    assert "setInterval" not in poll
    assert "await pollWeiboQr(" in start
    assert "setTimeout" in start.split("await pollWeiboQr", 1)[1]


def test_admin_stock_names_are_manually_editable():
    """常用股票名有独立保存，不依赖「保存词表」。"""
    render = _fn_body("loadAdminTagsTab")
    assert "stock-names-input" in render
    assert "adminSaveStockNames" in render
    assert "保存股票名" in render
    assert "全市场" in render
    body = _fn_body("adminSaveStockNames")
    assert "/api/tags" in body
    assert "stock_names" in body
    assert "dropped_aliases" in body


def test_admin_tag_page_has_llm_maintain():
    """标签管理页可一键跑 LLM 维护，不必再走脚本。"""
    render = _fn_body("loadAdminTagsTab")
    assert "标签维护" in render
    assert "LLM" in render
    assert "adminMaintainTags" in render
    assert "维护并回填待打标" in render
    body = _fn_body("adminMaintainTags")
    assert "/api/tags/maintain" in body
    assert "backfill" in body
    assert "textContent" in body


def test_sidebar_has_slim_toggle_matching_rail():
    """宽屏点侧栏 V 收成与 ≤900px 相同的图标轨；窄屏 logo 不可点。"""
    html = (APP_JS.parent / "index.html").read_text()
    css = STYLE_CSS.read_text()
    src = APP_JS.read_text()
    assert 'id="sidebar-toggle"' in html
    assert "sidebar-brand-toggle" in html
    assert 'id="sidebar-logo"' in html
    assert "sidebar-slim" in html
    assert "toggleSidebarSlim" in src
    assert "SIDEBAR_COLLAPSE_ICON" not in src
    assert 'localStorage.setItem(SIDEBAR_SLIM_KEY' in _fn_body("toggleSidebarSlim")
    assert "max-width: 900px" in _fn_body("toggleSidebarSlim")
    assert "html.sidebar-slim .sidebar { width: 68px" in css
    idx = 0
    rail = ""
    while True:
        nxt = css.find("@media (max-width: 900px)", idx)
        if nxt == -1:
            break
        block = _media_block(css[nxt:], "@media (max-width: 900px)")
        if ".sidebar { width: 68px" in block:
            rail = block
            break
        idx = nxt + 1
    assert ".sidebar { width: 68px" in rail
    assert "pointer-events: none" in rail
    assert "@media (max-width: 768px)" in css
    assert ".sidebar { display: none; }" in _media_block(css, "@media (max-width: 768px)")


def test_ima_mount_settings_use_two_panes_and_lazy_folder_api():
    src = APP_JS.read_text()
    stats = _fn_body("loadAdminKnowledge")
    assert 'class="ima-mount-layout"' in stats
    assert 'id="ima-kb-list"' in stats
    assert 'id="ima-folder-tree"' in stats
    assert "loadImaFolderChildren" in src
    assert "/api/admin/ima-collector/groups/" in src
    assert "/folders?parent_id=" in src
    assert "readImaMountGroups" in _fn_body("saveImaCollector")
    assert "folder_ids" in _fn_body("readImaMountGroups")
    assert "addImaGroupRow" not in stats
    assert "root_folder_id" not in _fn_body("imaMountGroupRowHtml")


def test_ima_mount_uses_master_detail_and_selected_group_controls():
    knowledge = _fn_body("loadAdminKnowledge")
    row = _fn_body("imaMountGroupRowHtml")
    interval = _fn_body("imaIntervalSegHtml")
    render = _fn_body("renderImaMountGroups")

    assert 'class="ima-mount-layout"' in knowledge
    assert 'id="ima-kb-list"' in knowledge
    assert 'id="ima-kb-select"' in knowledge
    assert 'id="ima-selected-group-name"' in knowledge
    assert 'id="ima-selected-interval"' in knowledge
    assert 'id="ima-group-acl"' in knowledge
    assert 'id="ima-folder-panel"' in knowledge
    assert "imaIntervalSegHtml" not in row
    assert 'id="ima-interval-${escapeHtml(groupId)}-${sec}"' in interval
    assert 'aria-pressed="${current === sec}"' in interval
    assert "renderImaSelectedGroup" in render
    assert 'role="option"' in row
    assert 'aria-selected="${selected}"' in row


def test_ima_folder_panel_is_collapsed_and_preserves_lazy_tree():
    src = APP_JS.read_text()
    knowledge = _fn_body("loadAdminKnowledge")
    toggle = _fn_body("toggleImaFolderPanel")

    assert "folderPanelGroupId" in src
    assert 'id="ima-folder-panel-toggle"' in knowledge
    assert 'aria-expanded="false"' in knowledge
    assert 'id="ima-folder-panel"' in knowledge
    assert "hidden" in knowledge
    assert "imaMountState.folderPanelGroupId" in toggle
    assert "renderImaFolderTree" in toggle
    assert "loadImaFolderChildren" not in toggle


def test_ima_mount_ui_preserves_draft_and_uses_safe_dynamic_text():
    src = APP_JS.read_text()
    for name in (
        "imaMountState", "renderImaMountGroups", "renderImaFolderTree",
        "toggleImaFolder", "imaSafeError", "focusId",
    ):
        assert name in src
    for fn in ("imaMountGroupRowHtml", "imaFolderRowHtml", "imaGroupDiscoveryStatusText"):
        body = _fn_body(fn)
        assert "escapeHtml" in body
    render = _fn_body("renderStatsData")
    assert "renderImaMountGroups" not in render


def test_ima_master_detail_css_matches_duty_console_and_mobile_contract():
    css = STYLE_CSS.read_text()
    desktop = css[css.index(".ima-mount-layout"):]
    narrow = _media_block(css, "@media (max-width: 900px)", last=True)

    assert "grid-template-columns: minmax(240px, 280px) minmax(0, 1fr)" in desktop
    assert ".ima-mount-rail" in css
    assert ".ima-mount-detail" in css
    assert ".ima-detail-section" in css
    assert ".ima-kb-select" in css
    assert re.search(r"\.ima-kb-select\s*\{[^}]*display:\s*none", css)
    assert re.search(r"\.ima-mount-layout\s*\{[^}]*grid-template-columns:\s*1fr", narrow)
    assert re.search(r"\.ima-kb-list\s*\{[^}]*display:\s*none", narrow)
    assert re.search(r"\.ima-kb-select\s*\{[^}]*display:\s*block", narrow)
    assert "position: sticky" in narrow
    assert "min-height: 44px" in css
    for selector in (".ima-mount-layout", ".ima-mount-rail", ".ima-mount-detail", ".ima-detail-section"):
        rule = css[css.index(selector):css.index("}", css.index(selector))]
        assert "box-shadow" not in rule


def test_ima_discovery_success_releases_only_its_owned_button():
    """发现成功安装新 state 后仍应由原请求释放当前按钮，旧请求不能释放它。"""
    discover = _fn_body("discoverImaGroups")
    success_start = discover.index('if (result.ok && result.config)')
    else_start = discover.index("} else {", success_start)
    success = discover[success_start:else_start]
    finally_block = discover[discover.index("} finally"):]
    assert "imaMountState.discoveryOwner = request" in success
    assert "imaMountState.discoveryBusy = true" in success
    assert "imaMountState.discoveryOwner !== request" in finally_block
    assert "generation === imaMountState.generation" not in finally_block
    assert "const currentButton = $(\"#ima-discover-btn\")" in finally_block


def test_ima_collector_dirty_bar_excludes_acl_and_can_discard():
    src = APP_JS.read_text()
    knowledge = _fn_body("loadAdminKnowledge")
    dirty = _fn_body("renderImaCollectorDirtyState")
    discard = _fn_body("discardImaCollectorChanges")
    progress = _fn_body("applyImaCollectorProgress")
    savebar = knowledge[knowledge.index('id="ima-collector-savebar"'):knowledge.index("</section>", knowledge.index('id="ima-collector-savebar"'))]
    runtime = knowledge[knowledge.index("ima-collector-runtime"):knowledge.index("ima-collector-savebar")]

    assert 'id="ima-collector-savebar" hidden' in knowledge
    assert 'id="ima-collector-discard"' in savebar
    assert 'id="ima-collector-save"' in savebar
    assert knowledge.count('id="ima-collector-save"') == 1
    assert 'id="ima-sync-progress"' in runtime
    assert 'id="ima-collector-status"' in runtime
    assert "bar.hidden = !(imaMountState.dirty || imaMountState.collectorDirty)" in dirty
    assert "renderImaCollectorDirtyState()" in _fn_body("renderImaMountGroups")
    assert "renderImaCollectorDirtyState()" in _fn_body("setImaGroupInterval")
    assert "renderImaCollectorDirtyState()" in _fn_body("toggleImaFolder")
    assert "renderImaCollectorDirtyState" not in _fn_body("saveImaGroupAcl")
    assert "renderImaCollectorDirtyState" not in _fn_body("addAclUser")
    assert "renderImaCollectorDirtyState" not in _fn_body("removeAclUser")
    assert "saveImaGroupAcl" not in dirty
    assert "ima-selected-group-state" in progress
    assert "confirm(" in discard
    assert "collectorDraft = null" in discard
    assert "collectorDraftRevision = \"\"" in discard
    assert "loadAdminKnowledge(routeRenderSeq)" in discard
    assert src.count("function discardImaCollectorChanges") == 1


def test_ima_collector_save_restores_focus_only_when_original_focus_survives():
    """保存期间用户切换到其他控件后，旧保存回调不得抢回焦点。"""
    save = _fn_body("saveImaCollector")
    assert "const focusElement = document.activeElement" in save
    assert "const restoreFocus = document.activeElement === focusElement" in save
    assert "|| document.activeElement === document.body" in save
    focus_start = save.index("const restoreFocus =")
    focus_index = save.index("focusTarget?.focus({ preventScroll: true })")
    assert "if (!focusMoved && restoreFocus)" in save[focus_start:focus_index]
    assert focus_index > focus_start


def test_ima_collector_save_tracks_focus_moves_through_stats_reload():
    """焦点在 stats reload await 期间移动时，完成回调不得抢焦点。"""
    save = _fn_body("saveImaCollector")
    assert "let focusMoved = false" in save
    assert "const onFocusIn" in save
    assert "event.target !== document.body" in save
    assert 'document.addEventListener("focusin", onFocusIn)' in save
    assert 'document.removeEventListener("focusin", onFocusIn)' in save
    reload_index = save.index("await reloadAdminSettingsPage(routeSeq, savedImaStatus)")
    post_reload_guard = save.index("!focusMoved", reload_index)
    assert post_reload_guard > reload_index
    assert "if (!focusMoved" in save[reload_index:]


def test_ima_collector_save_decides_focus_after_stats_reload_await():
    """restoreFocus 判定必须发生在 stats reload 完成后，而非 reload 前。"""
    save = _fn_body("saveImaCollector")
    reload_index = save.index("await reloadAdminSettingsPage(routeSeq, savedImaStatus)")
    restore_index = save.index("const restoreFocus =")
    assert restore_index > reload_index
    assert "const restoreFocus =" not in save[:reload_index]
    assert "if (!focusMoved && restoreFocus)" in save[restore_index:]


def test_ima_collector_storage_status_text_contract():
    """管理页 collector 状态文案应反映存储健康，且无 storage 时保持原语义。"""
    body = _fn_body("imaCollectorStatusText")
    js = (
        "function imaCollectorStatusText(status) " + body + "\n"
        "const base = {"
        "  config: { refresh_token: { set: true }, groups: [{ folder_ids: ['f1'] }], interval_seconds: 3600 },"
        "  documents: 12,"
        "  last_finished_at: '2026-08-28T00:00:00Z',"
        "  last_result: { downloaded: 3, failed: 0 }"
        "};\n"
        "const cases = ["
        "  [{ ...base, storage: { status: 'unavailable' } }, '研报库存储暂不可用'],"
        "  [{ ...base, storage: { status: 'stale' } }, '研报库存储状态过期'],"
        "  [{ ...base, storage: { status: 'readonly' } }, '研报库存储当前只读'],"
        "  [{ ...base, storage: { status: 'capacity_blocked' } }, '研报库存储空间已达限制'],"
        "  [{ ...base, storage: { status: 'available', used_percent: 23 } }, '已归档 12 份 · 上次新增 3 份 · 存储 23%'],"
        "  [base, '已归档 12 份 · 上次新增 3 份'],"
        "  [{ ...base, index: { status: 'ready' } }, '已归档 12 份 · 上次新增 3 份'],"
        "  [{ ...base, index: { status: 'rebuilding' } }, '已归档 12 份 · 上次新增 3 份 · 索引重建中'],"
        "  [{ ...base, index: { status: 'fallback' } }, '已归档 12 份 · 上次新增 3 份 · 索引回退'],"
        "  [{ ...base, index: { status: 'failed' } }, '已归档 12 份 · 上次新增 3 份 · 索引异常']"
        "];\n"
        "for (const [status, want] of cases) {"
        "  const got = imaCollectorStatusText(status);"
        "  if (got !== want) { console.error(JSON.stringify({got, want})); process.exit(1); }"
        "}"
    )
    subprocess.run(["node", "-e", js], check=True)


def test_knowledge_settings_nav_and_empty_state():
    src = APP_JS.read_text()
    assert '{ route: "admin/knowledge"' in src
    assert 'label: "研报库设置"' in src
    assert "knowledge: loadAdminKnowledge" in _fn_body("renderAdmin")
    assert "go('admin/knowledge')" in _fn_body("renderKnowledge")
    assert "admin/stats?tab=config" not in _fn_body("renderKnowledge")
    stats = _fn_body("loadAdminStats")
    assert "研报库设置" in stats
    assert "go('admin/knowledge')" in stats
    assert "IMA 与知识星球设置已移至" in stats


def test_knowledge_settings_storage_and_phone_sync_blocks():
    knowledge = _fn_body("loadAdminKnowledge")
    assert "ima_phone_sync.command" not in knowledge
    assert "手机同步" not in knowledge
    assert "Refresh Token" not in knowledge
    assert 'id="ima-pure-token"' not in knowledge
    assert 'id="ima-storage-status"' in _fn_body("imaStoragePanelHtml")
    assert "refreshImaStorage()" in _fn_body("imaStoragePanelHtml")
    assert "backupImaStorage()" in _fn_body("imaStoragePanelHtml")
    assert "立即备份" in _fn_body("imaStoragePanelHtml")
    assert "刷新状态" in _fn_body("imaStoragePanelHtml")


def test_knowledge_settings_uses_collect_tabs_and_interval_chips():
    knowledge = _fn_body("loadAdminKnowledge")
    assert 'data-tab="collect"' in knowledge
    assert 'data-tab="zsxq"' in knowledge
    assert 'data-tab="storage"' in knowledge
    assert "imaIntervalSegHtml" in _fn_body("renderImaSelectedGroup")
    assert "imaCollectorProgressHtml" in knowledge or "ima-sync-progress" in knowledge
    assert "saveImaCredentials()" not in knowledge
    save = _fn_body("saveImaCollector")
    assert "ima-pure-interval" not in save
    trigger = _fn_body("triggerImaCollector")
    assert "group_id" in trigger
    assert "请先挂载该知识库并保存" in trigger
    assert "同步当前库" in _fn_body("loadAdminKnowledge")


def test_save_polling_splits_zsxq_fields():
    polling = _fn_body("savePollingConfig")
    zsxq = _fn_body("saveZsxqPollingConfig")
    for key in ("zsxq_max_pages", "zsxq_fetch_delay_seconds", "zsxq_file_delay_seconds",
                "zsxq_prefetch_files", "zsxq_fetch_comments", "zsxq_app_channel"):
        assert key not in polling
        assert key in zsxq
    assert 'id="pc-zq-save"' in _fn_body("loadAdminKnowledge")


def test_knowledge_keyboard_walks_rows_without_opening_documents():
    body = _fn_body("onKnowledgeListKey")
    # 列表 j/k 只移动焦点，Enter 才打开，避免连按连下载整份 PDF
    assert "openImaDocument(row.dataset.mediaId" not in body
    assert "rows[idx].focus()" in body
    # 阅读页 j/k 沿快照结果集翻上/下一份
    assert "_imaListSnapshot" in body
    assert "openImaDocument(next.media_id" in body


def test_reader_pdf_has_new_tab_open_helper():
    body = _fn_body("openImaPdfNewTab")
    assert "window.open(window._imaPdfUrl" in body
    assert "flash(" in body
    assert "openImaPdfNewTab()" in _fn_body("renderImaDocument")


def test_knowledge_desk_serves_phone_without_refusal():
    src = APP_JS.read_text()
    assert "renderKnowledgePhoneBlocked" not in src
    assert "isPhoneShell" not in src
    css = STYLE_CSS.read_text()
    # 手机壳层给阅读台独立高度，不再整页拒绝
    assert "研报库阅读台（手机）" in css
    assert "100dvh - 120px" in css
    assert "grid-template-columns: 44px minmax(0, 1fr) 84px" in css
    # 同优先级后者胜：手机覆盖块必须声明在桌面规则之后，否则被覆盖回桌面网格
    assert css.index("研报库阅读台（手机）") > css.index("grid-template-columns: minmax(0, 1fr) auto")
    # 手机与 PC 同 iframe 预览；新标签按钮仍在工具栏
    assert "ima-pdf-frame" in _fn_body("renderImaDocument")
    assert "ima-pdf-phone-open" not in _fn_body("renderImaDocument")
    assert "ima-pdf-phone-open" not in _fn_body("loadImaPdf")
    assert "ima-back-count" not in _fn_body("renderImaDocument")
    assert "ima-reader-download" not in _fn_body("renderImaDocument")
    # 遗留手机块不得再拉伸阅读工具栏按钮（曾把下载钮撑出屏）
    assert "flex: 1; justify-content: center" not in css


def test_user_modal_kb_grants_include_local_libraries():
    body = _fn_body("loadAdminUsers")
    assert "/api/admin/ima-local-libraries" in body
    assert "state.imaKbGroups = imaGroups.concat(localGroups)" in body
    modal = _fn_body("adminOpenUser")
    assert "本地库" in modal
    assert "group.local" in modal


def test_knowledge_zero_sub_empty_state_wraps_source_controls():
    body = _fn_body("renderKnowledge")
    # 零订阅空态的资料源控件必须套标准容器，裸渲染会错位溢出
    assert "ima-report-filters-row" in body
    css = STYLE_CSS.read_text()
    assert ".ima-report-filters-row { padding: 12px 16px; flex-wrap: wrap; }" in css
    assert ".ima-report-filters > .ima-report-source" in css
    assert "width: 100%;" in css[css.index(".ima-report-source select"):css.index(".ima-report-head .ima-doc-filter-chips")]
