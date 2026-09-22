# 财经资讯（News Stream）移动端与 PC 端重构设计规范

## 1. 概述 (Overview)

### 1.1 背景与现状痛点
当前 VPush 系统的「财经资讯」流虽然功能完备，但在现代多端设备体验上存在明显的体验瓶颈：
- **移动端首屏容积率低**：顶部由导航条、大号搜索框、媒体源下拉框、主题分类横条纵向层叠堆积，共占用约 240px 高度（相当于移动端 35%~40% 的首屏视口高度），用户打开页面甚至看不到一张完整的新闻卡片。
- **信息层次与已读/未读区分弱**：卡片排版机械平铺，未读与已读资讯视觉对比弱，刷流时容易重复点击；标签杂乱折行，破坏阅读重心；缩略图比例生硬（84×56），浅色配图缺乏内阴影容易融入背景。
- **PC 宽屏未充分利用**：在 PC 宽屏下直接将移动端单列居中拉伸至 1120px，行长过长导致视线跳行疲劳，右侧大面积留白浪费。
- **视觉微质感与全站规范脱节**：部分控件样式与全站的 `design-tokens.css`（品牌 Duty Blue `#1668e0`、微圆角 `--radius-control`）以及 `core/icons.js` 的 Lucide 2.0 线性 SVG 图标规范存在局部不一致。

### 1.2 目标与收益
- **移动端首屏利用率提升 65%**：顶部重构为「48px 紧凑品牌/源切换栏 + 36px 主题滑动胶囊栏」，搜索与媒体源筛选折叠收纳至轻量浮层/抽屉，首屏可立即呈现 2~3 张完整资讯卡片。
- **打造彭博 / 财新级微报质感**：
  - 未读文章：左侧带精致品牌蓝微指示条，加粗标题（650 字重），轻微浮起。
  - 已读文章：标题自然退火（中灰 500 字重），背景微弱沉底，快速下滑时视线自动跳过已读。
  - 缩略图升级为 **96×64 (3:2 黄金比例)**，增加 `inset 0 0 0 1px rgba(0,0,0,0.06)` 防穿透微边框。
  - 来源、时间、主题标签紧凑归纳在卡片底部，给标题和摘要留足呼吸感。
- **PC 宽屏双栏高效流**：
  - 左侧主信息流 (~72%)：主题分类 + 紧凑搜索 + 一键「只看未读」，舒适阅读行宽。
  - 右侧常驻侧边栏 (300px Sticky)：阅读概览（未读数统计 + 一键全部标为已读）+ 媒体来源订阅列表（直观展示各源未读数并支持瞬时切源）。
- **严格遵循全站设计系统**：品牌 Duty Blue `--color-accent`、系统字体族 `--font-sans`、Lucide 2.0 线性 SVG 图标体系。

---

## 2. 架构设计与技术方案 (Architecture)

### 2.1 技术路线
- **遵循项目轻量原生规范**：保持 ES Module 与原生 CSS 架构，不引入臃肿的第三方 UI 库，纯原生 CSS Grid / Flexbox 配合 CSS 自定义属性（Variables）实现。
- **CSS 结构解耦**：
  - 核心样式整合在 `app/static/news/news.css`（或模块对应的 CSS 文件），严格使用 `app/static/core/design-tokens.css` 暴露的语义变量。
  - 保持深色模式（Dark Mode）与浅色模式（Light Mode）原生同步适配。
- **图标体系**：
  - 统一从 `app/static/core/icons.js` 导入已有的 Lucide 2.0 线性 SVG 图标（`SEARCH_ICON`、`FILTER_ICON`、`EYE_ICON`、`GEAR_ICON`、`CHECK_ICON`、`X_ICON`、`CHEVRON_DOWN_ICON` 等）。

---

## 3. 详细设计 (Detailed Design)

### 3.1 移动端紧凑顶部导航与控制栏 (Mobile Consolidated Header)
- **第一层：48px 极简主栏**：
  - 左侧：页面标题与当前媒体源切换器（如 `全部资讯 ▾`），点击唤起轻量选择菜单。
  - 右侧：
    - 紧凑搜索按钮（带 `SEARCH_ICON`），点击平滑展开全宽搜索输入框。
    - 快速筛选按钮（带 `FILTER_ICON`），点击唤起筛选抽屉。
- **第二层：36px 主题滑动微胶囊栏**：
  - 水平滚动 Chip 组：`全部`、`宏观`、`国际`、`科技`、`公司`、`市场` 等。
  - 选中态：`background: var(--color-accent); color: #fff; font-weight: 600; border-radius: 14px;`。
  - 未选中态：`background: var(--color-surface); color: var(--color-text-muted); border: 1px solid var(--border-soft);`。
  - 隐藏原生滚动条，支持平滑手势滑动与两端微渐变遮罩。

### 3.2 新闻卡片微质感与图文排版 (News Card Typography & Micro-Textures)
- **卡片容器**：
  - `background: var(--color-surface); border: 1px solid var(--border-default); border-radius: var(--radius-control, 10px); padding: 12px 14px; display: flex; gap: 14px; align-items: flex-start;`
- **未读状态 (Unread)**：
  - 左边缘：`border-left: 3px solid var(--color-accent);`
  - 标题：`font-size: 1rem; font-weight: 650; line-height: 1.42; color: var(--color-text-strong); margin-bottom: 6px;`
  - 摘要：`font-size: 0.84rem; color: var(--color-text-muted); line-height: 1.5; margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;`
- **已读状态 (Read)**：
  - 无左侧高亮边框。
  - 标题：`font-weight: 500; color: var(--color-text-muted);`（平滑退火）。
  - 卡片整体：`opacity: 0.85; background: var(--color-surface-muted);`。
- **缩略图**：
  - 尺寸：移动端 `96×64px` (3:2 黄金比例)，PC 端 `112×75px`。
  - 圆角：`8px`。
  - 防穿透微边框：`box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.06);`（暗色模式下为 `rgba(255, 255, 255, 0.08)`）。
  - `object-fit: cover;`，优雅加载失败占位处理。
- **底部元数据**：
  - `display: flex; align-items: center; gap: 8px; font-size: 0.75rem; color: var(--color-text-faint);`
  - 来源：加粗突出显示（未读时可展示 `--color-accent`）。
  - 时间：相对时间格式化（`03:14`、`10分钟前`、`昨天`）。
  - 主题微标签：`background: var(--color-surface-accent); color: var(--color-accent); padding: 1px 6px; border-radius: 4px;`。

### 3.3 PC 端宽屏双栏与侧栏 (Desktop Layout)
- **容器布局**：
  - `max-width: 1240px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 24px; align-items: start;`
- **主信息流 (左侧 ~72%)**：
  - 顶部工具栏：主题 Chip 栏 + 内嵌搜索框（带 `SEARCH_ICON`）+「只看未读」Toggle 按钮（带 `EYE_ICON`）。
  - 列表流：按日期自然分组（`今天`、`昨天`），卡片悬浮提供微抬升与边框高亮。
- **常驻侧边栏 (右侧 300px Sticky)**：
  - `position: sticky; top: 20px; display: flex; flex-direction: column; gap: 14px;`
  - **阅读概览卡片**：
    - 展示「今日未读数」（带胶囊微徽标）。
    - 提供「一键全部标为已读」按钮（带 `CHECK_ICON`）。
  - **媒体来源卡片**：
    - 列出各媒体源（财新网、华尔街见闻、路透等）及对应的未读数量。
    - 点击媒体源即时过滤左侧列表，右上角「管理」按钮直达来源配置。

### 3.4 交互细节与状态流转 (Interactions & State Transitions)
- **已读状态即时流转**：
  - 点击卡片查看正文/外链时，卡片状态乐观更新为已读，未读蓝色边框 0.15s 淡出，未读计数器瞬时 -1。
- **一键全读与防误触撤销 (Undo Toast)**：
  - 点击「全部标为已读」，所有项瞬时变已读。
  - 底部弹出 5 秒胶囊 Toast：`已将当前 N 篇资讯标为已读 [撤销]`，用户可在 5 秒内一键恢复。
- **骨架屏与零抖动 (CLS = 0)**：
  - 严格按 3:2 缩略图与两行标题骨架占位，数据载入后绝不发生高度跳变。
- **移动端触感反馈**：
  - 点击按压卡片时提供 `transform: scale(0.99)` 与轻微暗度变化，松开平滑回弹。

---

## 4. 边界条件与容错处理 (Error Handling & Edge Cases)

1. **配图加载失败或无配图**：
   - 当文章无配图或图片加载 404 时，隐藏缩略图区域，文本自适应撑满整行，保持整齐一致。
2. **超长标题与极长来源名**：
   - 标题统一强制 2 行 `-webkit-line-clamp: 2` 省略，来源名称限制最大宽度并单行省略，避免打乱卡片结构。
3. **空搜索/空筛选结果**：
   - 提供友好的空状态（居中展示 `INBOX_ICON`，文案「暂无相关财经资讯」，并附带「清除筛选」按钮）。
4. **离线/弱网重试**：
   - 网络请求失败时显示微提示与「点击重试」操作，保留现有已加载内容不闪退。

---

## 5. 验证与测试策略 (Testing Strategy)

1. **响应式多端验证**：
   - 移动端：测试 iPhone SE (375px)、iPhone 15 Pro (393px)、Android 主流宽度 (360px~412px)。
   - 平板/小窗：测试 iPad 竖屏与横屏 (768px~1024px) 下折叠与抽屉过渡。
   - PC 宽屏：测试 1280px、1440px、1920px 宽屏下的双栏比例与侧边栏 Sticky 贴顶。
2. **主题对比验证**：
   - 浅色模式与深色模式下的对比度、边框微质感、未读蓝条清晰度。
3. **交互与状态测试**：
   - 点击即读、一键全读、5秒撤销功能测试。
   - 搜索实时过滤、主题分类切换、媒体源切换测试。
4. **打包与资产完整性**：
   - 确保无多余依赖，无 CSS/JS 语法错误，通过既有静态资源版本控制与 Service Worker 缓存策略。
