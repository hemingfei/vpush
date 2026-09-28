# V Push Frontend Design System Unification

## Goal

统一 V Push 前端的视觉规范和 design tokens，采用已确认的 A 方向：灰底白面、1px 描边、克制 Duty Blue、默认无卡片阴影。保持现有业务功能、信息架构、路由、权限、API、数据结构和文案语义不变。

## Scope and Source of Truth

- 唯一前端源目录：`app/static/`。
- Rust 项目的 `static` 是指向该目录的符号链接，默认服务此目录。
- `static/vendor/design-tokens.css` 与 `static-assets/` 不作为本轮编辑源；后者存在已知的构建产物差异。
- 主要修改文件：
  - `app/static/vendor/design-tokens.css`
  - `app/static/style.css`
  - 必要时更新 `DESIGN.md`
- 不引入 React、shadcn 或其他运行时依赖，不重写原生 JS 架构。

## Visual Direction

- 页面底色使用 Paper，主要内容使用 Surface，次级区域使用 Surface-muted。
- Duty Blue 只表达主操作、当前选中、当前导航、焦点和必要反馈。
- 平台品牌图标保留其品牌识别，但选中状态统一由 Duty Blue 表达。
- 默认平面优先：卡片使用描边，不使用阴影；阴影只用于登录卡、下拉、toast 等真实浮层。
- 统一轮廓：小组件 6px、控件 12px、卡片 16px、筛选/状态胶囊 999px。
- 统一控件高度：紧凑 34px、标准 42px、触控 44px。
- 统一动效时长约 160ms，反馈不超过 220ms，并尊重 `prefers-reduced-motion`。

## Token Rules

- 保留现有语义 token 体系，补齐缺失角色，不为单个页面或单个值创建 token。
- 颜色角色包括背景、surface、文字层级、accent、success、warning、danger、边框和焦点。
- 间距使用 8px 基准，覆盖 `space-2` 到 `space-6`，页面区块避免硬编码重复值。
- 字体使用现有系统字体栈；正文、标题、标签、说明保持固定字号层级，不使用流式字号。
- 阴影只保留 xs/sm/lg/focus 等有明确层级含义的 token。
- 深色模式保持同构角色和形状，只替换背景、文字、描边、状态色和阴影值。

## Shared Component States

在 `style.css` 统一以下共享视觉状态：

- Buttons: primary、ghost、small、danger 的 default、hover、focus-visible、active、disabled、loading。
- Inputs: label、placeholder、focus、error、disabled；错误区域保留固定占位，避免布局跳动。
- Tables: 表头、行 hover、刷新/选中反馈、空态、移动端折叠结构；数字使用等宽数字。
- Navigation: 桌面侧栏、收窄图标轨、移动底栏共享 active、hover、focus 语义，选中不改变尺寸。
- Dialogs and toast: 使用统一 surface、border、shadow、semantic state tokens。
- Platform filters: 桌面平台胶囊与移动角标沿用同一 active 语义。

## Migration Order

1. 基础 token 与共享状态。
2. 核心工作台：登录/注册、顶栏、侧栏、动态流、筛选、内容卡片。
3. 管理员后台：标题区、筛选/操作区、表格、移动折叠表格、表单、弹窗和批量操作。
4. 移动端：390px 底栏、角标筛选、内容可读性和触控尺寸；900px 收窄导航过渡。

## Responsive and Accessibility Requirements

- 验证 1280px 桌面、900px 收窄布局、390px 移动布局。
- 触控目标至少 44px；不以选中态改变控件尺寸。
- 保留并统一 `:focus-visible` 焦点环、跳过链接和可访问名称。
- 正文与占位文字满足 WCAG AA 对比度要求；错误、成功、警告不能只依靠颜色传达。
- 页面在深色模式下使用已有 `html.theme-dark` 机制，不新增第二套主题切换逻辑。

## Verification

- 运行 Impeccable detector：
  `node /Users/kale/.agents/skills/impeccable/scripts/detect.mjs --json <changed targets>`
- 运行现有项目测试与静态检查。
- 运行 asset digest 一致性检查，确认 `index.html`、`sw.js`、import map 和 CSS/JS hash 与源文件一致。
- 运行 Rust 编译/测试检查，确认前端改动未影响服务端构建。
- 浏览器检查 1280px、900px、390px 和深色模式，确认无溢出、重叠、断层或不可操作控件。

## Non-Goals

- 不改变业务逻辑、API、权限、数据、路由或文案语义。
- 不重构全部 JavaScript 模块。
- 不增加新的产品功能、营销落地页或装饰性插画。
- 不同步或编辑 `vpush-rust/static-assets/`，除非后续构建流程明确要求生成同步产物。
