---
name: V Push
description: 值班台——灰底白面、1px 描边、克制蓝只标操作与命中
colors:
  duty-blue: "#1668e0"
  duty-blue-strong: "#1258c4"
  duty-blue-text: "#1668e0"
  duty-blue-text-on-dark: "#5a9bf5"
  paper: "#f5f5f7"
  surface: "#ffffff"
  ink: "#1d1d1f"
  ink-strong: "#222c3c"
  ink-muted: "#6e6e73"
  ink-faint: "#667080"
  line: "rgba(12, 18, 34, 0.1)"
  line-strong: "rgba(12, 18, 34, 0.16)"
  danger: "#dc2626"
  success: "#3a6e4b"
  night-bg: "#0f1115"
  night-surface: "#171a20"
  night-ink: "#e4e6eb"
  white: "#ffffff"
typography:
  display:
    fontFamily: "SF Pro SC, SF Pro Display, PingFang SC, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 600
  title:
    fontFamily: "SF Pro SC, SF Pro Display, PingFang SC, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 600
  body:
    fontFamily: "SF Pro SC, SF Pro Display, PingFang SC, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
  label:
    fontFamily: "SF Pro SC, SF Pro Display, PingFang SC, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 500
  caption:
    fontFamily: "SF Pro SC, SF Pro Display, PingFang SC, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    letterSpacing: "1px"
rounded:
  2xs: "6px"
  xs: "10px"
  control: "12px"
  sm: "14px"
  md: "18px"
  card: "20px"
  pill: "999px"
spacing:
  2: "8px"
  3: "12px"
  4: "16px"
  5: "20px"
components:
  button-primary:
    backgroundColor: "{colors.duty-blue}"
    textColor: "{colors.white}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "42px"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "{colors.duty-blue-strong}"
    textColor: "{colors.white}"
    rounded: "{rounded.control}"
    height: "42px"
  button-ghost:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "44px"
    typography: "{typography.label}"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "44px"
    typography: "{typography.label}"
  chip-selected:
    backgroundColor: "{colors.duty-blue}"
    textColor: "{colors.white}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "44px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    typography: "{typography.label}"
  nav-item-active:
    backgroundColor: "rgba(22, 119, 255, 0.12)"
    textColor: "{colors.duty-blue-text}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  form-control:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "42px"
    typography: "{typography.body}"
  section-panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "22px 22px"
---

# Design System: V Push

## Overview

**Creative North Star: "The Duty Console"**

V Push 是值班台，不是内容社区，也不是营销落地页。界面服务于通知管线：状态当场可见，失败说人话，密度优先于展示。灰底（paper）托住白面（surface），表面用 1px 描边分开，不靠投影堆层级。字用 SF Pro SC / 苹方阅读档。Duty Blue 只标操作与命中。

深色是一等公民，不是换皮彩蛋：同一套角色，只换底、字、线；实底按钮保持同一蓝值，蓝字提亮以保证对比。登录页的径向浅蓝停在登录，不进主壳。

不做插画、霓虹暗色、装饰渐变铺底、为展示而展开的空白。克制是品牌，不是未完工。

**Key Characteristics:**
- 值班台气质：可靠、直接、工具感；信息密度优先
- 默认平面：表面靠描边与色调分层
- Duty Blue 稀缺：只服务选中、主操作、焦点
- 触控一等：控件高度 42–44px，手机浏览器不降级
- 深色与浅色同构，只换色值不换哲学

## Colors

单一强调色加中性灰阶。平台品牌色（雪球、微博、X、知识星球）只给未选中图标，不抢 Duty Blue 的操作语义。

### Primary
- **Duty Blue**: 主按钮、选中胶囊、焦点描边、侧栏选中字。实底配白字。面积目标 ≤10%。
- **Duty Blue Strong**: 主按钮 hover / active，比填充更深一档。
- **Duty Blue Text**: 浅底上的蓝字与描边。深色下改用 **Duty Blue Text on Dark**，填充蓝值不变。

### Neutral
- **Paper**: 应用底、侧栏、顶栏。白面坐在它上面。
- **Surface**: 卡片、输入、未选中胶囊、幽灵按钮。
- **Ink / Ink Strong**: 正文与标题。
- **Ink Muted / Ink Faint**: 辅助说明、分组标签、占位。
- **Line / Line Strong**: 默认分隔与控件描边。
- **Night Background / Night Surface / Night Ink**: 深色同构角色。

### Semantic
- **Danger**: 破坏操作、校验失败、退出 hover。
- **Success**: 健康、绑定成功。不用来做装饰绿。
- **White**: 实底按钮与选中胶囊上的字/图标。

### Named Rules
**The Duty Blue Rule.** Duty Blue 只出现在选中、主按钮、焦点。任何一屏不超过约 10% 面积。稀缺才有效。

**The Peer Dark Rule.** `html.theme-dark` 换底/字/线，不换角色。主按钮蓝值保持；蓝字提到 Duty Blue Text on Dark。

## Typography

**Display Font:** SF Pro SC（回退 SF Pro Display / PingFang SC / Helvetica Neue）
**Body Font:** 同一套无衬线栈
**Label/Mono Font:** 标签同无衬线；等宽只用代码与原始标识（`ui-monospace`）

**Character:** 系统阅读档，中文优先。字重只有 500 与 600 两档强调，正文保持默认 Regular，不靠字重制造戏剧。

### Hierarchy
- **Display** (600, 30px): 登录字标。主壳不用。
- **Title** (600, 17px): 顶栏页名、侧栏品牌名、区块标题。
- **Body** (400, 15px): 正文、主按钮字、输入字。
- **Label** (500, 13px): 导航项、胶囊、幽灵按钮、次要操作。
- **Caption** (600, 12px, 字距约 1px): 分组标签、eyebrow、元信息。

### Named Rules
**The Reading-Size Rule.** 主壳从 Title 起跳，不把 Display 带进值班台。列表与筛选用 Label / Caption，不把标题字号铺满工具条。

## Layout

桌面是左栏 + 主列。侧栏 220px，贴顶全高，底色同 Paper，右边一条默认线。宽屏点品牌 V 可收到 68px 图标轨。≤900px 自动收成图标轨（品牌 V 不再切换，避免把窄屏轨写进偏好）。≤768px 侧栏让位，改用底栏。

顶栏高 56px，左右 24px；主列内边距 24px，窄屏 16px。内容铺满可用宽，正文可读性由帖文行宽上限管，不靠居中留白。区块间距约 18px，内部节奏走 spacing 2–5（8 / 12 / 16 / 20）。

触控目标 42–44px。筛选条可横滑，不换行挤碎。

### Named Rules
**The Scan Density Rule.** 密度优先。不为展示加空、不放大选中、不让控件跳跃。选中用 Duty Blue，尺寸不变。

## Elevation & Depth

默认平面。表面靠 Paper / Surface 色差和 1px 线分层。阴影词库存在，但休息态卡片、侧栏、顶栏、胶囊都不投影。

阴影只给真正浮起来的层：登录卡、toast、下拉、偶尔的邀请横幅图标。焦点用 2px 实线 + 淡蓝环，不用大投影冒充层次。

### Shadow Vocabulary
- **xs** (`0 2px 10px rgba(15, 23, 42, 0.04)`): 浮层轻抬。深色改为更不透明的黑。
- **sm** (`0 8px 24px rgba(15, 23, 42, 0.06)`): 登录卡、下拉。
- **lg** (`0 22px 56px rgba(15, 23, 42, 0.1)`): 少用，大浮层。
- **focus-ring** (`0 0 0 3px rgba(0, 113, 227, 0.08)`): 输入焦点，配合 Duty Blue 边。

动效：`--ease-standard` 为 160ms ease。主按钮 active 下移 1px。尊重 `prefers-reduced-motion`。

### Named Rules
**The Flat-By-Default Rule.** 休息态平面。阴影只回答「这层浮在上面」。卡片加阴影即违规。

## Shapes

控件 12px（control），卡片 20px（card），胶囊与头像 999px（pill）。中间档 6 / 10 / 14 / 18 给图标钮、小组件、软角容器。边是 1px 实线，不虚线、不双描、不厚边框当装饰。

选中胶囊变实底，圆角不变。侧栏项圆角同控件，不做成胶囊。

### Named Rules
**The Quiet Corner Rule.** 卡片偏圆、控件中圆、筛选全圆。不要把三种轮廓用在同一角色上。

## Components

克制且可扫。密度优先，选中态用 Duty Blue，不放大、不跳跃。

### Buttons
- **Shape:** 控件圆角（12px），高 42px（主）或至少 44px（幽灵）。
- **Primary:** Duty Blue 实底，白字 15px / 600，左右 20px。Hover / active 用 Duty Blue Strong；active 下移 1px。
- **Ghost:** Surface 底 + 强描边，Ink Strong，13px。Hover 加深描边，不填蓝。危险幽灵用 Danger 字与淡红边。

### Chips
- **Style:** 胶囊，高 44px，Surface + 强描边，13px。
- **State:** Hover 描边与字变 Duty Blue Text。Selected 实底 Duty Blue、白字。未选中平台图标可用品牌色；选中后图标反白。同一套语言用于动态筛选与首页平台条。

### Cards / Containers
- **Corner Style:** 卡片圆角（20px）。
- **Background:** Surface，坐在 Paper 上。
- **Shadow Strategy:** 无。见 Flat-By-Default。
- **Border:** 默认 1px 线。
- **Internal Padding:** 22px。

### Inputs / Fields
- **Style:** Surface，强描边，控件圆角，高 42px，左右 14px，正文 15px。
- **Focus:** 边改 Duty Blue Text + focus-ring。
- **Error / Disabled:** 错误用 Danger 说明，贴在字段下；禁用降不透明度，不改形状。

### Navigation
- **Desktop:** 侧栏项透明底，13px，hover 极淡蓝底，active 用 accent-soft 底 + Duty Blue Text，字重 600。分组标签 Caption。
- **Slim / ≤900px:** 图标轨，标签隐藏。
- **Mobile ≤768px:** 底栏，图标+短标签。
- **Theme switcher:** 无边小图标钮，选中淡蓝底 + Duty Blue Text。

### Timeline filters (signature)
最新动态的平台胶囊横排可扫。特别关注 / 次要大V 是描边切换，开态描边与字走 Duty Blue，不另起一套选中语言。筛选状态必须和列表一致：点选立刻改控件，请求失败则回滚或明示，不能 pill 已亮、列表仍是上一档。

## Do's and Don'ts

### Do:
- **Do** 用描边和 Paper / Surface 分层，休息态卡片不投影。
- **Do** 把 Duty Blue 留给选中、主按钮、焦点；平台色只给未选中图标。
- **Do** 保持控件 42–44px，选中不改尺寸。
- **Do** 把深色写成同构角色：换值，不换形状或阴影策略。
- **Do** 让失败、加载、空态当场可见，文案说人话。

### Don't:
- **Don't** 做营销落地页、插画、霓虹暗色、装饰渐变铺主壳。
- **Don't** 把登录页径向浅蓝带进侧栏或动态流。
- **Don't** 用第二套强调色（紫、橙、渐变）表示「选中」。
- **Don't** 同一筛选条件用三种控件各说一遍还不互相同步。
- **Don't** 为了好看加大字号或留白，把值班台做成展示页。
