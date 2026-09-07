# 移动端纯图标底栏实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `≤768px` 的移动端底栏改为 X 式纯图标导航，并保留 V Push 的 Duty Blue 选中态、动态入口、无障碍名称和滚动显隐。

**Architecture:** 继续使用现有 `MOBILE_NAV`、`renderBottomNav()` 与全局路由，不新增组件或依赖。补充三个语义明确的内联 SVG，复用现有报纸与四宫格图标；渲染层删除可见标签，路由层同步 `aria-current`，CSS 只负责图标尺寸和等宽触控区。

**Tech Stack:** 原生 ES modules、内联 SVG、CSS media query、Python pytest、Playwright、现有 `scripts/bump_assets.py`。

---

## 文件结构

- Modify: `app/static/core/icons.js` — 增加主页、用户、省略号三个移动导航图标。
- Modify: `app/static/app.js` — 调整移动导航图标映射、纯图标 HTML 和 `aria-current`。
- Modify: `app/static/style.css` — 设置 X 式等宽图标底栏、27px 图标和 48px 以上触控区。
- Modify: `DESIGN.md` — 将移动导航约束从“图标+短标签”改为已批准的纯图标规则。
- Modify: `tests/test_frontend_interactions.py` — 固化图标语义、无可见文字和无障碍属性。
- Modify: `tests/test_frontend_runtime.py` — 覆盖 3–5 个入口、320–768px、深浅主题、尺寸、颜色与切页。
- Modify: `app/static/index.html` — 由资产摘要脚本更新查询版本。
- Modify: `app/static/sw.js` — 由资产摘要脚本更新离线缓存版本。

### Task 1: 固化图标语义与无障碍渲染

**Files:**
- Modify: `tests/test_frontend_interactions.py:72-83`
- Modify: `app/static/core/icons.js:15-31`
- Modify: `app/static/app.js:1-12`
- Modify: `app/static/app.js:440-490`
- Modify: `app/static/app.js:5331-5340`

- [ ] **Step 1: 写入失败的静态契约测试**

在 `tests/test_frontend_interactions.py` 的导航测试附近新增：

```python
def test_mobile_navigation_is_icon_only_and_accessible():
    src = APP_JS.read_text()
    mobile = src[src.index("const MOBILE_NAV ="):src.index("let bottomNavLastY")]
    render = _fn_body("renderBottomNav")
    router = _fn_body("router")

    for route, icon, label in (
        ("timeline", "HOME_ICON", "动态"),
        ("news", "NEWS_ICON", "财经新闻"),
        ("home", "GRID_ICON", "广场"),
        ("settings", "USER_ICON", "个人设置"),
    ):
        assert f'route: "{route}", icon: {icon}, label: "{label}"' in mobile
    assert 'route: "more", icon: MORE_ICON, label: "更多"' in render
    assert 'class="bnav-label"' not in render
    assert 'aria-label="${t.label}"' in render
    assert 'title="${t.label}"' in render
    assert 'setAttribute("aria-current", "page")' in router
    assert 'removeAttribute("aria-current")' in router
```

- [ ] **Step 2: 运行测试并确认它因旧图标和旧标签失败**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_frontend_interactions.py::test_mobile_navigation_is_icon_only_and_accessible
```

Expected: FAIL，首个差异为 `HOME_ICON` 不在 `MOBILE_NAV`，且旧渲染仍包含 `class="bnav-label"`。

- [ ] **Step 3: 增加最小内联 SVG 图标**

在 `app/static/core/icons.js` 的导航图标区加入：

```javascript
export const HOME_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg>`;
export const USER_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="7" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>`;
export const MORE_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>`;
```

- [ ] **Step 4: 更新图标导入、入口映射和纯图标 HTML**

在 `app/static/app.js` 的 `./core/icons.js` 导入列表中加入 `HOME_ICON`、`MORE_ICON`、`USER_ICON`，保留仍被桌面导航或其他操作使用的旧图标。

将移动入口和渲染替换为：

```javascript
const MOBILE_NAV = [
  { route: "timeline", icon: HOME_ICON, label: "动态" },
  { route: "news", icon: NEWS_ICON, label: "财经新闻" },
  { route: "home", icon: GRID_ICON, label: "广场" },
  { route: "settings", icon: USER_ICON, label: "个人设置" },
];

function renderBottomNav(user) {
  resetBottomNavScroll();
  const tabs = MOBILE_NAV.filter((tab) => tab.route !== "news" || state.newsVisible);
  if (user.is_admin) tabs.push({ route: "more", icon: MORE_ICON, label: "更多" });
  $("#bottom-nav").innerHTML = tabs.map((t) => `
    <button class="bnav-item" data-route="${t.route}" aria-label="${t.label}" title="${t.label}" onclick="go('${t.route}')">
      <span class="bnav-icon">${t.icon}</span>
    </button>`).join("");
  ensureMobilePlatformSwipe();
}
```

将路由中的移动高亮循环改为：

```javascript
const activeBottom = navPage === "admin" ? "more" : navPage;
document.querySelectorAll(".bnav-item").forEach((button) => {
  const active = button.dataset.route === activeBottom;
  button.classList.toggle("active", active);
  if (active) button.setAttribute("aria-current", "page");
  else button.removeAttribute("aria-current");
});
```

- [ ] **Step 5: 运行静态契约测试并确认通过**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_frontend_interactions.py::test_mobile_navigation_is_icon_only_and_accessible \
  tests/test_frontend_interactions.py::test_subscription_push_is_the_only_subscription_management_navigation_entry \
  tests/test_frontend_interactions.py::test_financial_news_navigation_keeps_quick_news_in_timeline \
  tests/test_frontend_interactions.py::test_financial_news_visibility_is_runtime_controlled
```

Expected: 4 passed。

- [ ] **Step 6: 提交语义与渲染改动**

```bash
git add app/static/core/icons.js app/static/app.js tests/test_frontend_interactions.py
git commit -m "refactor: make mobile navigation icon only"
```

### Task 2: 落地移动布局并验证运行时矩阵

**Files:**
- Modify: `tests/test_frontend_runtime.py:437-459`
- Modify: `app/static/style.css:2515-2543`
- Modify: `DESIGN.md:251-255`

- [ ] **Step 1: 写入失败的浏览器矩阵测试**

在 `tests/test_frontend_runtime.py` 的 `_contrast_ratio()` 后新增：

```python
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

    for index, (_, label) in enumerate(expected):
        button = buttons.nth(index)
        expect(button).to_have_attribute("aria-label", label)
        expect(button).to_have_attribute("title", label)
        expect(button.locator("svg")).to_be_visible()
        button_box = button.bounding_box()
        icon_box = button.locator("svg").bounding_box()
        assert button_box and button_box["height"] >= 48
        assert icon_box and 26 <= icon_box["width"] <= 28 and 26 <= icon_box["height"] <= 28

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
```

- [ ] **Step 2: 运行矩阵测试并确认它因旧 18px CSS 失败**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_frontend_runtime.py::test_mobile_bottom_navigation_is_icon_only \
  --basetemp=/tmp/vpush-mobile-nav-pytest
```

Expected: FAIL，图标宽高为约 `18px`，不满足 `26 <= size <= 28`。

- [ ] **Step 3: 用最小 CSS 改成 X 式等宽图标栏**

将 `app/static/style.css` 的底栏布局块调整为：

```css
.bottom-nav {
  display: none;
  position: fixed;
  left: 0; right: 0; bottom: 0;
  z-index: 50;
  background: var(--color-bg);
  border-top: var(--border-default);
  padding: 4px 8px calc(4px + env(safe-area-inset-bottom));
  justify-content: space-around;
  transition: transform 180ms ease;
}
.bottom-nav[inert] { transform: translateY(100%); pointer-events: none; }
@media (prefers-reduced-motion: reduce) {
  .bottom-nav { transition: none; }
}
.bnav-item {
  min-width: 0;
  min-height: 52px;
  flex: 1;
  display: grid;
  place-items: center;
  padding: 0;
  border: none;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--color-text-muted);
}
.bnav-item .bnav-icon {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  line-height: 1;
}
.bnav-item .bnav-icon svg { width: 27px; height: 27px; }
.bnav-item.active { color: var(--color-accent-text); }
```

保留现有 `@media (max-width: 768px) { .bottom-nav { display: flex; } }` 和 `.page-main` 的安全区留白，不改滚动显隐代码。

- [ ] **Step 4: 同步设计系统约束**

将 `DESIGN.md` 的移动导航规则替换为：

```markdown
- **Mobile ≤768px:** 纯图标底栏；3–5 个入口等宽，图标约 27px、触控区至少 48px；标签只保留在 `aria-label` / `title`，active 使用 Duty Blue Text，不加胶囊或圆底。
```

- [ ] **Step 5: 运行浏览器矩阵和既有滚动回归**

Run:

```bash
rm -rf /tmp/vpush-mobile-nav-pytest
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_frontend_runtime.py::test_mobile_bottom_navigation_is_icon_only \
  tests/test_frontend_runtime.py::test_mobile_navigation_scroll_direction \
  tests/test_frontend_runtime.py::test_timeline_long_text_keeps_navigation_in_viewport \
  --basetemp=/tmp/vpush-mobile-nav-pytest
```

Expected: 22 passed。随后列出并逐张检查截图：

```bash
find /tmp/vpush-mobile-nav-pytest -name '*.png' -print | sort
```

检查标准：所有入口完整且等宽；没有可见汉字；浅色选中为 `#1668e0`，深色使用主题提亮蓝；未选中为中性灰；无重叠、裁切、横向溢出或圆底。

- [ ] **Step 6: 提交布局、测试与设计约束**

```bash
git add app/static/style.css DESIGN.md tests/test_frontend_runtime.py
git commit -m "style: align mobile navigation with x"
```

### Task 3: 更新资产摘要并完成发布前验证

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/sw.js`
- Verify: `app/static/app.js`
- Verify: `app/static/style.css`
- Verify: `app/static/core/icons.js`
- Verify: `tests/test_frontend_interactions.py`
- Verify: `tests/test_frontend_runtime.py`

- [ ] **Step 1: 运行 JavaScript 语法和定向测试**

```bash
node --check app/static/app.js
node --check app/static/core/icons.js
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_frontend_interactions.py::test_mobile_navigation_is_icon_only_and_accessible \
  tests/test_frontend_runtime.py::test_mobile_bottom_navigation_is_icon_only \
  tests/test_frontend_runtime.py::test_mobile_navigation_scroll_direction
```

Expected: 两个 `node --check` 退出码均为 0；定向测试全部通过。

- [ ] **Step 2: 运行 Impeccable 静态设计检查**

```bash
node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json \
  app/static/app.js app/static/core/icons.js app/static/style.css DESIGN.md
```

Expected: 无需要修复的 P0/P1 设计违规；如有输出，仅处理与本次底栏改动直接相关的问题后重跑本步骤。

- [ ] **Step 3: 同步内容派生的前端缓存版本**

```bash
PYTHONPATH=. .venv/bin/python scripts/bump_assets.py --sync
PYTHONPATH=. .venv/bin/python scripts/bump_assets.py --check
```

Expected: 输出同一个 12 位十六进制摘要，第二条显示 `asset digest ok:` 后跟该摘要；只更新 `app/static/index.html` 和 `app/static/sw.js`。

- [ ] **Step 4: 运行完整测试套件**

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

Expected: 全部通过，无失败、错误或意外跳过。

- [ ] **Step 5: 检查最终差异边界**

```bash
git diff --check
git status --short
git diff --stat HEAD~2
```

Expected: 无空白错误；最终改动仅涉及文件结构中列出的源码、测试、设计约束和两个资产版本文件；既有 `android-twa/`、`app/static/.well-known/`、`work/` 不被暂存或修改。

- [ ] **Step 6: 提交缓存摘要**

```bash
git add app/static/index.html app/static/sw.js
git commit -m "chore: refresh frontend asset digest"
```

- [ ] **Step 7: 记录实施交付状态**

```bash
git log -5 --oneline
git status --short --branch
```

Expected: 设计规格提交、图标语义提交、布局提交和资产摘要提交顺序清晰；工作树只保留实施前已有的未跟踪目录。此计划不包含推送 GitHub 或部署 VPS，需用户在实现验收后另行确认。
