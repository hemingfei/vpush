# Web Icon System and Bottom Navigation D1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 V Push 网页端通用图标，并让移动底栏点击时播放一次 D1 圆形淡蓝反馈，结束后只保留蓝色加粗线框选中态。

**Architecture:** 沿用 `app/static/core/icons.js` 的内联 SVG 注册表和现有依赖注入，不增加运行时依赖。底栏仅在入口集合变化时重建 DOM，点击时先给当前按钮添加一次性动画类再执行路由，因此反馈立即开始且不会被常规路由渲染中断；字符图标按现有视图依赖注入边界替换。

**Tech Stack:** 原生 ES modules、内联 SVG、CSS keyframes、Python pytest、Playwright、现有资产摘要脚本。

---

## 文件结构

- Modify: `app/static/core/icons.js` — 增加通用方向与附件图标，保持 24×24、`currentColor` 和统一线框属性。
- Modify: `app/static/app.js` — 触发底栏 D1、注入图标并替换时间线字符图标。
- Modify: `app/static/index.html` — 移除顶部返回按钮的字符图标，由入口模块注入 SVG；同步资产摘要。
- Modify: `app/static/core/lightbox.js` — 使用注入的关闭和左右方向 SVG。
- Modify: `app/static/views/ima.js` — 使用注入的返回 SVG。
- Modify: `app/static/views/admin/knowledge.js` — 使用注入的面板方向 SVG。
- Modify: `app/static/views/admin/ima-collector.js` — 使用注入的展开、收起和移除 SVG。
- Modify: `app/static/views/admin/kol.js` — 使用注入的分页方向 SVG。
- Modify: `app/static/views/admin/news.js` — 使用注入的展开与收起 SVG。
- Modify: `app/static/style.css` — D1 动画、选中线宽和通用图标尺寸。
- Modify: `tests/test_frontend_interactions.py` — 静态图标和 D1 契约。
- Modify: `tests/test_frontend_runtime.py` — 底栏运行时、重复点击和减少动态效果覆盖。
- Test: `tests/test_frontend_pwa.py` — 验证生成后的资产摘要一致性。
- Modify: `app/static/sw.js` — 由资产摘要脚本同步缓存摘要。
- Modify: `DESIGN.md` — 固化长期图标及 D1 规则。

### Task 1: 实现移动底栏 D1 反馈

**Files:**
- Modify: `tests/test_frontend_interactions.py`
- Modify: `tests/test_frontend_runtime.py`
- Modify: `app/static/app.js:441-489, 5331-5342, 5820-5920`
- Modify: `app/static/style.css:2516-2542`

- [ ] **Step 1: 写入失败的静态契约测试**

在 `tests/test_frontend_interactions.py` 增加：

```python
def test_mobile_bottom_navigation_uses_d1_feedback_contract():
    app = APP_JS.read_text()
    css = STYLE_CSS.read_text()
    render = _fn_body("renderBottomNav")

    assert "goFromBottomNav(this, '${t.route}')" in render
    assert 'nav.dataset.routes !== routeSignature' in render
    assert "function playBottomNavFeedback(button)" in app
    assert 'classList.add("is-feedback")' in app
    assert 'addEventListener("animationend"' in app
    assert "playBottomNavFeedback(button);" in app
    assert "-webkit-tap-highlight-color: transparent" in css
    assert ".bnav-item::before" in css
    assert ".bnav-item.is-feedback::before" in css
    assert "animation: bnav-feedback 220ms" in css
    assert "stroke-width: 2.4" in css
    assert "@keyframes bnav-feedback-reduced" in css
```

- [ ] **Step 2: 运行静态测试并确认失败**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_frontend_interactions.py::test_mobile_bottom_navigation_uses_d1_feedback_contract
```

Expected: FAIL，首个失败项为底栏仍调用 `go()`，且 CSS 中不存在 D1 动画。

- [ ] **Step 3: 写入失败的 Playwright 行为测试**

在 `tests/test_frontend_runtime.py` 的移动底栏测试后增加：

```python
def test_mobile_bottom_navigation_d1_feedback_restarts_and_clears(page: Page, static_origin: str):
    page.set_viewport_size({"width": 390, "height": 840})
    page.emulate_media(reduced_motion="no-preference")
    install_badge_reader_bootstrap(page)
    page.route("**/api/me", lambda route: route.fulfill(json={
        "id": 1, "username": "test", "is_admin": False, "news_visible": True,
    }))
    page.goto(static_origin)
    page.evaluate("() => go('timeline')")

    active = page.locator('.bnav-item[data-route="timeline"]')
    active.click()
    page.wait_for_function("document.querySelector('[data-route=timeline]').classList.contains('is-feedback')")
    state = active.evaluate("""el => ({
        tap: getComputedStyle(el).webkitTapHighlightColor,
        background: getComputedStyle(el).backgroundColor,
        stroke: getComputedStyle(el.querySelector('.nav-svg')).strokeWidth,
        durations: el.getAnimations({subtree: true}).map(a => a.effect.getTiming().duration),
    })""")
    assert state["tap"] in ("rgba(0, 0, 0, 0)", "transparent")
    assert state["background"] == "rgba(0, 0, 0, 0)"
    assert float(state["stroke"].replace("px", "")) == pytest.approx(2.4)
    assert 220 in state["durations"]

    page.wait_for_function("!document.querySelector('[data-route=timeline]').classList.contains('is-feedback')")
    active.click()
    page.wait_for_function("document.querySelector('[data-route=timeline]').classList.contains('is-feedback')")
    assert active.evaluate("el => el.getAnimations({subtree: true}).length") == 1


def test_mobile_bottom_navigation_reduced_motion_uses_opacity_only(page: Page, static_origin: str):
    page.set_viewport_size({"width": 390, "height": 840})
    page.emulate_media(reduced_motion="reduce")
    install_badge_reader_bootstrap(page)
    page.route("**/api/me", lambda route: route.fulfill(json={
        "id": 1, "username": "test", "is_admin": False, "news_visible": True,
    }))
    page.goto(static_origin)
    page.evaluate("() => go('timeline')")
    state = page.locator('.bnav-item[data-route="timeline"]').evaluate("""el => {
        el.classList.add('is-feedback');
        const animation = el.getAnimations({subtree: true})[0];
        return {
            duration: animation.effect.getTiming().duration,
            transforms: animation.effect.getKeyframes().map(frame => frame.transform),
        };
    }""")
    assert state["duration"] == 80
    assert set(state["transforms"]) <= {"none"}
```

- [ ] **Step 4: 运行行为测试并确认失败**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_frontend_runtime.py::test_mobile_bottom_navigation_d1_feedback_restarts_and_clears \
  tests/test_frontend_runtime.py::test_mobile_bottom_navigation_reduced_motion_uses_opacity_only
```

Expected: FAIL，因为点击后不存在 `is-feedback` 状态，减少动态效果也没有独立动画。

- [ ] **Step 5: 实现不会被路由渲染中断的单次反馈**

在底栏滚动状态附近增加反馈函数：

```javascript
function playBottomNavFeedback(button) {
  if (!button) return;
  button.classList.remove("is-feedback");
  void button.offsetWidth;
  button.classList.add("is-feedback");
  button.addEventListener("animationend", () => button.classList.remove("is-feedback"), { once: true });
}

function goFromBottomNav(button, path) {
  playBottomNavFeedback(button);
  go(path);
}
```

`renderBottomNav()` 只在入口集合变化时替换 DOM，并把点击处理改为：

```javascript
const nav = $("#bottom-nav");
const routeSignature = tabs.map((tab) => tab.route).join("|");
if (nav.dataset.routes !== routeSignature) {
  nav.innerHTML = tabs.map((t) => `
    <button class="bnav-item" data-route="${t.route}" aria-label="${t.label}" title="${t.label}" onclick="goFromBottomNav(this, '${t.route}')">
      <span class="bnav-icon">${t.icon}</span>
    </button>`).join("");
  nav.dataset.routes = routeSignature;
}
```

把 `goFromBottomNav` 加入 `INLINE_HANDLERS`，保证内联处理器可调用。

- [ ] **Step 6: 实现 D1 CSS 和稳定选中态**

在底栏 CSS 中加入：

```css
.bnav-item {
  position: relative;
  isolation: isolate;
  -webkit-tap-highlight-color: transparent;
}
.bnav-item::before {
  content: "";
  position: absolute;
  z-index: 0;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  opacity: 0;
  transform: scale(0.72);
  pointer-events: none;
}
.bnav-item .bnav-icon { position: relative; z-index: 1; }
.bnav-item.is-feedback::before {
  animation: bnav-feedback 220ms cubic-bezier(0.16, 1, 0.3, 1);
}
.bnav-item.active .bnav-icon .nav-svg { stroke-width: 2.4; }
@keyframes bnav-feedback {
  0% { opacity: 0; transform: scale(0.72); }
  28% { opacity: 1; transform: scale(1); }
  100% { opacity: 0; transform: scale(1); }
}
@keyframes bnav-feedback-reduced {
  0%, 35% { opacity: 1; transform: none; }
  100% { opacity: 0; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .bnav-item.is-feedback::before {
    animation: bnav-feedback-reduced 80ms linear;
  }
}
```

保持 `.bnav-item.active` 背景透明，只设置 Duty Blue 文字色。

- [ ] **Step 7: 运行 D1 测试**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_frontend_interactions.py::test_mobile_bottom_navigation_uses_d1_feedback_contract \
  tests/test_frontend_runtime.py::test_mobile_bottom_navigation_d1_feedback_restarts_and_clears \
  tests/test_frontend_runtime.py::test_mobile_bottom_navigation_reduced_motion_uses_opacity_only \
  tests/test_frontend_runtime.py::test_mobile_bottom_navigation_is_icon_only
```

Expected: 全部 PASS。

- [ ] **Step 8: 提交底栏改动**

```bash
git add app/static/app.js app/static/style.css tests/test_frontend_interactions.py tests/test_frontend_runtime.py
git commit -m "feat: add bottom navigation D1 feedback"
```

### Task 2: 统一网页端控件图标

**Files:**
- Modify: `app/static/core/icons.js`
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/core/lightbox.js`
- Modify: `app/static/views/ima.js`
- Modify: `app/static/views/admin/knowledge.js`
- Modify: `app/static/views/admin/ima-collector.js`
- Modify: `app/static/views/admin/kol.js`
- Modify: `app/static/views/admin/news.js`
- Modify: `app/static/style.css`
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: 写入失败的图标注册表与替换契约测试**

在 `tests/test_frontend_interactions.py` 增加：

```python
def test_generic_control_icons_use_the_central_svg_registry():
    icons = ICONS_JS.read_text()
    app = APP_JS.read_text()
    index = INDEX_HTML.read_text()
    lightbox = (STATIC / "core/lightbox.js").read_text()
    ima = (STATIC / "views/ima.js").read_text()
    knowledge = (STATIC / "views/admin/knowledge.js").read_text()
    collector = (STATIC / "views/admin/ima-collector.js").read_text()

    for name in (
        "CHEVRON_LEFT_ICON", "CHEVRON_RIGHT_ICON", "CHEVRON_UP_ICON",
        "CHEVRON_DOWN_ICON", "PAPERCLIP_ICON",
    ):
        assert f"export const {name}" in icons
    assert 'id="btn-back" class="icon-btn hidden" aria-label="返回上一页"></button>' in index
    assert '$("#btn-back").innerHTML = CHEVRON_LEFT_ICON;' in app
    for old in (">✕</button>", ">‹</button>", ">›</button>"):
        assert old not in lightbox
    assert 'aria-hidden="true">‹</span>' not in ima
    assert 'aria-hidden="true">›</span>' not in knowledge
    assert '${expanded ? "⌄" : "›"}' not in collector
    assert 'aria-hidden="true">×</span>' not in collector
```

测试文件已有 `ICONS_JS`，在常量区补充：

```python
INDEX_HTML = APP_JS.with_name("index.html")
```

- [ ] **Step 2: 运行契约测试并确认失败**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_frontend_interactions.py::test_generic_control_icons_use_the_central_svg_registry
```

Expected: FAIL，因为方向和附件图标尚未导出。

- [ ] **Step 3: 增加统一通用图标**

在 `app/static/core/icons.js` 增加：

```javascript
export const CHEVRON_LEFT_ICON = `<svg class="ui-icon chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>`;
export const CHEVRON_RIGHT_ICON = `<svg class="ui-icon chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>`;
export const CHEVRON_UP_ICON = `<svg class="ui-icon chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>`;
export const CHEVRON_DOWN_ICON = `<svg class="ui-icon chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;
export const PAPERCLIP_ICON = `<svg class="ui-icon paperclip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>`;
```

给现有 `X_ICON` 和 `EXTERNAL_LINK_ICON` 增加 `ui-icon` class，不改变路径。

- [ ] **Step 4: 替换图标专用字符**

按现有依赖注入方式传递并使用以下常量：

```text
index.html 顶部返回按钮       CHEVRON_LEFT_ICON，由 app.js 启动时注入
core/lightbox.js 关闭按钮     X_ICON
core/lightbox.js 左右切换     CHEVRON_LEFT_ICON / CHEVRON_RIGHT_ICON
views/ima.js 阅读器返回       CHEVRON_LEFT_ICON
admin/knowledge.js 面板入口   CHEVRON_RIGHT_ICON
admin/ima-collector.js 展开   CHEVRON_RIGHT_ICON / CHEVRON_DOWN_ICON
admin/ima-collector.js 移除   X_ICON
admin/kol.js 分页             CHEVRON_LEFT_ICON / CHEVRON_RIGHT_ICON
admin/news.js 展开状态        CHEVRON_UP_ICON / CHEVRON_DOWN_ICON
app.js 时间线展开状态         CHEVRON_UP_ICON / CHEVRON_DOWN_ICON
app.js 附件                   PAPERCLIP_ICON
app.js 查看原文               EXTERNAL_LINK_ICON
```

图标加文字的按钮使用如下顺序，不把 SVG 放进 `aria-label`：

```javascript
`${CHEVRON_LEFT_ICON}<span>上一页</span>`
`<span>下一页</span>${CHEVRON_RIGHT_ICON}`
`${expanded ? CHEVRON_UP_ICON : CHEVRON_DOWN_ICON}<span>${expanded ? "收起" : "展开全文"}</span>`
```

顶部返回按钮在 `app.js` 注册点击事件前执行：

```javascript
$("#btn-back").innerHTML = CHEVRON_LEFT_ICON;
```

- [ ] **Step 5: 统一控件内图标尺寸**

在 `app/static/style.css` 增加基础规则，并用组件选择器覆盖尺寸：

```css
.ui-icon { width: 1em; height: 1em; display: block; flex: 0 0 auto; }
.icon-btn .ui-icon { width: 20px; height: 20px; }
.lightbox-close .ui-icon { width: 18px; height: 18px; }
.lightbox-nav .ui-icon { width: 26px; height: 26px; }
.ima-reader-back .ui-icon,
.ima-folder-panel-toggle .ui-icon,
.ima-folder-expand .ui-icon,
.pager .ui-icon,
.post-expand-btn .ui-icon,
.p-file .ui-icon { width: 16px; height: 16px; }
```

对图标加文字的现有控件补充 `inline-flex`、`align-items: center` 和不改变原布局的 `gap`；删除仅服务于字符字号的规则。

- [ ] **Step 6: 运行静态契约与现有模块测试**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_frontend_interactions.py::test_generic_control_icons_use_the_central_svg_registry \
  tests/test_frontend_interactions.py::test_ima_modules_receive_cross_module_dependencies \
  tests/test_frontend_interactions.py::test_mobile_bottom_navigation_uses_d1_feedback_contract
```

Expected: 全部 PASS。

- [ ] **Step 7: 提交图标统一改动**

```bash
git add app/static/core/icons.js app/static/index.html app/static/app.js \
  app/static/core/lightbox.js app/static/views/ima.js \
  app/static/views/admin/knowledge.js app/static/views/admin/ima-collector.js \
  app/static/views/admin/kol.js app/static/views/admin/news.js \
  app/static/style.css tests/test_frontend_interactions.py
git commit -m "refactor: unify web control icons"
```

### Task 3: 固化设计约束并同步静态资产

**Files:**
- Modify: `DESIGN.md:211, 247-255`
- Modify: `app/static/index.html`
- Modify: `app/static/sw.js`
- Test: `tests/test_frontend_pwa.py`

- [ ] **Step 1: 更新长期设计约束**

在 `DESIGN.md` 的 Motion 与 Navigation 规则中加入：

```markdown
- 通用控件图标使用 24×24、currentColor、2px 圆角线框；品牌、渠道和数据可视化 SVG 例外。
- 移动底栏点击显示 42px、12% Duty Blue 的圆形反馈层，220ms 后完全消失；当前入口只保留 Duty Blue 和 2.4px 线框，不保留背景。
- 底栏关闭原生矩形 tap highlight；prefers-reduced-motion 下仅保留 80ms 透明度反馈。
```

- [ ] **Step 2: 同步内容摘要资产版本**

Run:

```bash
PYTHONPATH=. .venv/bin/python scripts/bump_assets.py --sync
```

Expected: 输出以 `asset digest synced:` 开头并跟随 12 位十六进制摘要；只生成 `app/static/index.html` 和 `app/static/sw.js` 的摘要变化。

- [ ] **Step 3: 检查摘要一致性**

Run:

```bash
PYTHONPATH=. .venv/bin/python scripts/bump_assets.py --check
```

Expected: 输出以 `asset digest ok:` 开头，摘要与上一步相同。

- [ ] **Step 4: 提交设计与资产摘要**

```bash
git add DESIGN.md app/static/index.html app/static/sw.js
git commit -m "docs: codify web icon interaction rules"
```

### Task 4: 全量回归和浏览器验收

**Files:**
- Test only; do not modify unrelated production files.

- [ ] **Step 1: 运行前端静态与 PWA 测试**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_frontend_interactions.py \
  tests/test_frontend_pwa.py
```

Expected: 全部 PASS。

- [ ] **Step 2: 运行前端 Playwright 测试**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_frontend_runtime.py \
  --basetemp=/tmp/vpush-web-icon-runtime
```

Expected: 全部 PASS。

- [ ] **Step 3: 运行 Impeccable 检测器**

Run:

```bash
node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json \
  app/static/index.html app/static/app.js app/static/style.css \
  app/static/core/icons.js app/static/core/lightbox.js \
  app/static/views/ima.js app/static/views/admin/knowledge.js \
  app/static/views/admin/ima-collector.js app/static/views/admin/kol.js \
  app/static/views/admin/news.js
```

Expected: 无阻断级问题；任何发现均只修复本次改动导致的问题。

- [ ] **Step 4: 做浏览器视觉验收**

使用 Playwright 在 `390×840` 和 `768×840` 下分别检查浅色、深色、普通用户和管理员：

```text
1. 点击未选中入口：出现 42px 圆形淡蓝闪动，没有矩形高亮。
2. 动画结束：按钮背景透明，当前通用图标为 Duty Blue、2.4px 线框。
3. 重复点击当前入口：动画重新开始且只有一个动画实例。
4. prefers-reduced-motion：只有 80ms 透明度反馈，没有扩散。
5. 3–5 个入口：按钮等宽，图标不位移，不遮挡安全区。
6. 桌面侧栏与其他按钮：没有获得 D1 动效。
7. 顶部返回、灯箱、IMA、后台展开/分页及附件图标：SVG 可见且文字不溢出。
```

保存动画结束状态的浅色、深色截图，并检查底栏区域像素不为空、无蓝色矩形残留。

- [ ] **Step 5: 检查最终差异和工作区**

Run:

```bash
git diff HEAD~3 --check
git status --short
git log -4 --oneline
```

Expected: `git diff --check` 无输出；只保留用户原有的无关未跟踪或未提交文件。
