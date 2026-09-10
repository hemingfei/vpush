# V Push Flutter Android Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 制作 Android Flutter 客户端，完整还原现有 Web 移动端的页面、操作流程、状态反馈和动效，交付独立的 ARM v7 与 ARM v8 签名 APK。

**Architecture:** 默认按 Flutter 原生重做业务页面规划，复用现有 FastAPI `/api` 和服务端业务规则。以固定版本 Web 的移动端实际渲染为对照，按页面建立交互、视觉和动效验收；仅 Android 系统界面、外部授权/人机验证使用平台能力。

**Tech Stack:** Flutter stable / Dart、Android、Dio、go_router、flutter_secure_storage、shared_preferences、flutter_svg；原生 PDF 与通知 SDK 在双 ABI 验证通过后锁定。优先使用 Flutter 自带 ChangeNotifier / ValueNotifier，不先引入全套状态管理和代码生成框架。

---

## 1. 计划依据与边界

- 计划日期：2026-09-10。
- 仓库根目录：`/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription`。本文任务中的文件路径均相对此目录。
- 已检查的基线：`04ea67bbf44b07e2cca4967090022a3275cee252`；当前工作区的 `work/` 是已有未跟踪内容，不纳入客户端修改。
- 已读取 Web 源码、产品与设计文档、API 路由及现有 Android 包装层。尚未用登录账号在真实 Android Chrome 逐页录制，因此源码值仍是候选基线，最终以阶段 0 的实际渲染取样校正。
- 本机已安装 Flutter 3.47.2 / Dart 3.13.2；`flutter build apk --help` 确认支持 `android-arm`、`android-arm64`。Android 工程已创建并通过 Dart 分析/Flutter 测试，但本机仍缺 Java Runtime、Android command-line tools 和 Android 设备，release APK/插件真机验证待工具链恢复。
- 客户端实现已在 `feat/vpush-flutter-android` 工作树开始：认证/外壳、动态、广场、财经新闻、研报/PDF、个人设置和管理员入口已接入；真实账号视觉对照、Turnstile、系统通知和双 ABI 发布仍未完成。
- 文档沿用仓库 `docs/plans/` 目录；技能默认的 `docs/superpowers/` 被本项目 `.gitignore` 忽略，因此不作为本计划的最终保存位置。

### 本计划采用的假设

1. 用户所说的 Flutter 客户端按“原生 Flutter 业务界面”理解；这项选择尚未收到明确答复。另两种可选路线见下一节。
2. “全部一样”包括普通用户与管理员在手机 Web 上能访问的功能、浅色/深色/跟随系统、加载/空/错误状态及操作权限。完整验收不能只覆盖首页和设置页。
3. 对照设备以 Android Chrome 手机视口为准；不是以 iPhone 苹方字体截图要求所有 Android 设备逐像素一致。
4. 首轮面向 Android 手机与 APK 直接分发；建议最低 Android 8.0 / API 26，延续现有 Android 工程下限。更旧系统、独立平板设计、iOS 和应用商店上架不计入本轮工期。
5. 调试包与现有 App 并存；正式包是否覆盖原来的 `net.vpush.twa`，按第 8 节在正式签名前决定。
6. 默认服务地址为 `https://vpush.net`，通过构建参数支持既有自托管实例；不新增一个 Web 没有的服务器管理产品界面。
7. 若“体验全部一样”包含关闭 App 后的本机系统通知，必须完成阶段 9 的原生通知迁移。仅保留 Telegram 等现有送达渠道不能算此项完成。

## 2. 路线选择

| 路线 | 对齐方式 | 主要代价 | 本计划定位 |
| --- | --- | --- | --- |
| Flutter 原生重做 | 自定义 Flutter 组件、原生列表/阅读界面，逐页对照 Web | 字体、HTML 阅读、滚动、PDF、管理员页面都要移植；Web 改动以后需要同步客户端 | 主计划，符合原生客户端理解 |
| Flutter + WebView | 原样加载移动 Web，Flutter 管启动、文件和系统桥接 | 最接近当前 UI，但 WebView 不等于 Chrome，下载、PDF、验证、后台通知仍需适配；已有 TWA 的重复建设价值较小 | 若绝对同源视觉优先，切换为此路线并重排任务 |
| Flutter 原生外壳 + 局部 Web 阅读器 | 导航、列表和设置原生，复杂正文内嵌 Web | 双栈导航、主题、鉴权、滚动和选中文本容易不一致 | 原生 HTML 阅读验证无法达到要求时的备选，需要记录为设计差异 |

原生 Flutter 和浏览器使用不同渲染、字体回退及文本布局机制，不能承诺所有设备零像素差。工程目标是同一设备与同一内容下，结构、信息密度、颜色、关键尺寸、交互和动效一致，字体栅格化的细小差异单独记录。

## 3. 已核实的实现事实

| 范围 | 事实来源 | 对计划的影响 |
| --- | --- | --- |
| 页面与路由 | `app/static/app.js` 的 `NAV`、`MOBILE_NAV`、`go`、主渲染分支 | 按现有入口迁移，不重新设计底部导航 |
| 样式与资产 | `app/static/style.css`、`vendor/design-tokens.css`、`core/icons.js`、`core/platforms.js`、SVG/PNG 资产 | 复用图标形状，按最终 CSS 计算值移植，不能只照 `DESIGN.md` |
| 登录与账户 | `app/api.py`、`app/static/app.js` | Bearer token；登录/注册可启用 Turnstile；没有已核实的 refresh-token 协议 |
| 新闻 | `app/static/views/news.js` | 来源选择、列表、已读更新、站内正文和受鉴权图片 |
| 研报与文档 | `app/static/views/ima.js`、`app/static/app.js` | 多库权限、目录/日期/标签/搜索、PDF、飞书时间线、受鉴权附件、列表快照 |
| 设置与绑定 | `views/push-settings.js`、`views/feishu-personal.js` | 四个页签：推送设置、渠道绑定、AI 网关、账号；包含扫码与绑定状态轮询 |
| 管理员 | `views/admin/` 及 `app.js` 管理容器 | 内容管理、数据源、研报设置、帖子与日志、用户与注册；全部在全量范围内 |
| 行情 | `views/market.js` 与动态页布局 | 迁移手机断点实际显示的行情模块，不擅自增加行情底部 Tab |
| 已有 Android | `android-twa/` | 包名 `net.vpush.twa`，版本 1.12.163，versionCode 112163，minSdk 26；覆盖安装必须匹配签名 |
| 系统通知 | `app/static/sw.js`、`app/notifiers/webpush.py`、`app/channels.py` | 当前使用浏览器 Web Push，不能直接搬到 Dart 或普通 WebView |

### 页面覆盖矩阵

| 页面族 | 必须复刻的内容/行为 | 对应阶段 |
| --- | --- | --- |
| 登录/注册 | 密码可见、邀请码、错误提示、Turnstile、会话恢复/失效、退出 | 1、2 |
| 应用外壳 | 顶栏、主题按钮、底栏、滚动隐藏、返回、管理员更多 | 2 |
| 动态 | 全部可见平台、筛选角标、特别关注、快讯、图文/转发/组合动态、关键词命中、新内容提示、分页和刷新 | 3 |
| 广场/订阅 | 搜索、平台、分类/标签、已订阅、特别关注、订阅类型、取消、求添加 | 4 |
| 大 V 详情/组合 | 资料、历史动态、持仓、净值、调仓信息 | 4 |
| 财经新闻 | 来源选择、开关隐藏、列表、长文、图片、已读、原文入口 | 5 |
| 研报中心 | 库订阅与权限、日期/标签/搜索、列表/阅读切换、摘要/翻译、PDF、下载、上下篇 | 6 |
| 飞书文档/附件 | 时间线、日期与工具栏、原文、图片/附件、知识星球文件 | 3、6 |
| 个人设置 | 推送、免打扰、摘要/翻译、关键词/研报匹配、动态图片、渠道、AI 网关、账号 | 7 |
| 管理员 | 全部手机可达管理页、容器页签、表单、确认弹窗、权限和错误状态 | 8 |
| Android 集成 | 通知、链接跳转、复制、下载/打开文件、启动、后台恢复、返回手势 | 9 |

当前手机底栏是“动态 / 财经新闻 / 广场 / 个人设置”，新闻关闭时隐藏，管理员追加“更多”。底栏视觉上以图标呈现，不自动加入文字标签。“我的订阅”旧路由转广场的已订阅筛选；研报入口位于动态页。沿用这些信息架构。

## 4. “一样”的验收方法

### 4.1 基线采集

- 固定 Web commit、Android 设备型号/系统、Chrome 版本、主题、语言、字体缩放、视口和测试数据。
- 使用脱敏测试实例与稳定 fixture；固定用户名、标题、图片、计数、时间及服务器响应。不能拿不断更新的生产时间线做截图差分。
- 取 360、390、412 CSS px 宽度的代表视口，记录实际内容高度及 DPR；Flutter 使用对应逻辑宽度。覆盖普通账号、管理员、新闻关闭、受限知识库。
- 每个页面采集首屏、长列表滚动、主要弹窗、键盘展开、加载、空和错误状态；对动画录屏并标出开始、峰值、结束。
- 给每项交互分配编号，记录“前置状态 → 操作 → 结果 → 对应 API → 截图/录像文件”。阶段 0 输出 `docs/mobile-parity/coverage.csv`，其完成率是全量验收依据。
- 横屏和大字体 1.3 倍做可用性检查；默认字号做视觉精对齐，不通过禁用系统字号满足截图指标。

### 4.2 视觉与动效门槛

| 项目 | 拟定验收门槛 |
| --- | --- |
| 导航、文案、图标、信息层级 | 与冻结版本逐项一致；不添加 Material 默认大标题、FAB、胶囊标签或额外页面动画 |
| 尺寸与排版 | 关键控件位置、间距、宽高误差不超过 1 逻辑像素；选定正文样本换行一致；系统字体导致的差异显式记录 |
| 颜色与描边 | Token 值一致；透明色在同一背景合成对比；CSS 1px 按 DPR 换算，不一律当物理 1px |
| 截图差分 | 对齐内容区域后生成热图；候选门槛为超过色差阈值的非文字像素占比 ≤1%，先用基线重复采集噪声校准；文字另验字重/基线/行数，不以遮掉所有文字冒充一致 |
| 动效 | 时长误差 ≤1 个 60Hz 帧；曲线、位移、透明度、触发和中断行为一致；低端设备掉帧另计性能问题 |
| 无障碍/减弱动画 | 图标有语义标签、触控区与 Web 对齐；系统关闭动画时取消位移/循环，保留必要状态反馈 |
| 数据与操作 | 相同账号、相同筛选返回相同内容；所有修改服务端确认后可在 Web 看到；失败不能显示成功 |
| 返回与恢复 | 返回后筛选、阅读上下文和滚动位置符合 Web 基线；键盘/弹窗/图片预览优先关闭，随后页面返回 |

### 4.3 已提取的动效样本

以下来自源码，阶段 0 检查移动断点覆盖及浏览器实际生效值后写入 `motion.json`。

| 动作 | 源码参数 | Flutter 实现约束 |
| --- | --- | --- |
| 通用颜色/边框变化 | 160ms，CSS ease | `Cubic(0.25, 0.1, 0.25, 1)`，不用默认 Material easing 替换 |
| 登录卡片出现 | 240ms，cubic-bezier(0.22, 1, 0.36, 1)，向下偏移 10px → 0，透明 → 不透明 | 独立控制位移与透明度 |
| 登录/注册表单出现 | 160ms，cubic-bezier(0.16, 1, 0.3, 1)，4px → 0 | 还原切换过程和焦点行为 |
| 底栏隐藏/显示 | 180ms ease，translateY(100%) | 向下累计 24px 隐藏，向上累计 8px 显示；顶端/无滚动重置；隐藏时禁止命中 |
| 底栏点击反馈 | 220ms ease-out，42px 圆形背景透明度 0→1→0 | 原图标保留；减弱动画时 80ms linear |
| 图片灯箱 | 遮罩进入 250ms ease-out，图片进入 280ms ease-out，关闭 200ms ease-in | 小图不强行放大；滑动切图、关闭和透明度过渡一并对齐 |
| 骨架屏 | 1.4s 循环 shimmer | 占位布局与最终内容相符，减弱动画时静止 |
| 快讯脉冲 | 2.4s ease-in-out 循环 | 仅在对应可见组件运行 |
| Toast | 进入 180ms ease-out，退出透明度 300ms ease | 按 Web 位置显示，不替换成底部 SnackBar |

Web 某些声明存在组合变量的情况，例如新动态提示的 `animation` 使用 `--ease-standard`；必须取实际计算样式与录像，不能仅凭字符串推断有效时长。

## 5. 代码组织与技术约束

```text
mobile/flutter_app/
  pubspec.yaml                         # 依赖、资产、应用版本；提交 pubspec.lock
  lib/main.dart                        # 初始化与依赖组装
  lib/app.dart                         # 应用主题与路由容器
  lib/core/api_client.dart             # JSON/二进制请求、鉴权、错误、取消
  lib/core/session_store.dart          # 安全会话持久化、账号隔离
  lib/core/app_router.dart             # Web 路由映射、返回、深链
  lib/core/theme/vpush_tokens.dart     # 颜色、字号、尺寸
  lib/core/theme/vpush_motion.dart     # 时长、曲线、减弱动画
  lib/core/widgets/                    # 实际复用的图标、按钮、弹窗、Toast、图片预览
  lib/features/auth/                  # 页面、认证控制器与接口模型
  lib/features/shell/                 # 顶栏、底栏、滚动隐藏和主题切换
  lib/features/timeline/              # 动态与快讯、图片/转发/组合卡片
  lib/features/plaza/                 # 广场、筛选、订阅和大 V 详情
  lib/features/news/                  # 来源、列表与文章阅读
  lib/features/knowledge/             # 库目录、文档/PDF、飞书时间线
  lib/features/settings/              # 推送/渠道/AI 网关/账号
  lib/features/admin/                 # 五个现有管理容器
  lib/platform/                      # 外部链接、文件、系统栏、授权与通知
  assets/brand/                       # 已有 SVG/PNG 的必要副本
  test/                              # 有业务意义的控制器、路由、组件和 Golden 测试
  integration_test/                   # 真机登录/阅读/订阅/恢复等端到端流程
  android/                           # Android 构建、Manifest、必要的平台桥接
docs/mobile-parity/                   # 基线、覆盖矩阵、API 样本、差异记录
docs/android-flutter-release.md       # 打包、签名、安装升级说明
scripts/build_flutter_android.sh      # 本地与 CI 共用打包入口
.github/workflows/flutter-android.yml # 分析、测试、双 ABI 构建与私有产物
```

- 初始状态管理使用页面级 controller + ChangeNotifier；共享 session/theme 单例由启动层注入。只有出现实际维护负担再引入其他框架。
- API 请求通过 Dio 统一处理，模型按页面族组织；不建立每个接口一套 use-case/repository 的空壳层。
- 字体先在同一 Android 设备对照 Chrome 实际回退字体。未经授权不打包苹果字体；如系统回退不能达到要求，再评估可合法分发的共同字体及对 Web 的影响。
- 图标从当前 SVG 和 `core/icons.js` 按使用范围导出，保留 viewBox、stroke 与选中线宽；不拿近似 Material 图标代替。
- Token 使用 Android 安全存储；偏好使用 shared_preferences。按“服务实例 + 用户”隔离缓存，退出清理敏感文件与正在进行的请求。
- 普通图片做有界内存缓存，长列表按需构建。PDF 下载到应用缓存文件后按页渲染；避免全文件多份内存副本。初版不引入离线数据库和全量同步。
- 前台轮询沿用 Web：动态 60 秒、快讯 15 秒、设置绑定状态 10 秒；不可见页停轮询，恢复前台按 Web 更新语义补查。不要把后台轮询当系统推送。
- 保留老请求与新账号/新页面隔离：每次请求捕获 session generation 与页面 generation，晚到响应只能更新所属状态。

## 6. 分阶段执行任务

每个阶段完成后进行一次独立提交。涉及状态、鉴权和数据变更的代码先写可复现失败的测试，再实现并复测；纯 Token 和文案搬运使用视觉核对，不编写镜像实现的无意义单测。

**执行进度（2026-09-10）：** 阶段 1 的 Android-only 工程和候选依赖已建立；阶段 2–5 的可运行页面骨架、API controller、图片/附件/行情组件和测试已完成首轮；阶段 6–8 已接入研报/PDF、飞书时间线、设置绑定轮询和管理员分区的首轮功能；阶段 9 已加入外链校验、缓存文件和系统打开入口；阶段 10 已加入双 ABI 构建脚本、ABI 校验、校验和输出和 CI。`html` 固定为 `0.15.6` 以兼容 `flutter_html 3.0.0`。真实账号视觉对照、Turnstile、原生通知、管理员全部子页面、真机插件/性能/签名验证仍未完成，当前只能称为可运行 Beta，不能称为完整视觉复刻或正式发布。

### 阶段 0：冻结移动 Web 基线（2–3 人日）

**新建文件：** `docs/mobile-parity/baseline.md`、`coverage.csv`、`api-contracts.md`、`motion.json`、`captures/`、`fixtures/`。

- [x] 记录基线 commit、设备/浏览器、实际计算样式候选值、客户端工具链状态；真实账号权限、新闻功能开关仍待测试实例。
- [x] 按页面覆盖矩阵枚举源码确认的手机入口、子页签和管理员容器；真实账号可达性仍待测试实例确认。
- [ ] 用脱敏数据采集三种宽度、两种主题的截图；为底栏、列表更新、弹窗、灯箱和登录制作操作录屏。
- [x] 记录已核实的请求方法与 URL、鉴权和错误语义；真实返回 shape、分页样本和脱敏 fixture 仍待测试实例。
- [ ] 采集断网、401、403、422、429、500、无权限库、无 PDF、长标题、超长正文和重复分页样本。

**验收：** 每个可达功能在 coverage.csv 有编号、入口、角色、操作步骤与期望；每个页面族至少一个可重复的视觉与接口样本。没有登录测试账号时可继续源码清单，但不能声称视觉基线已完成。

### 阶段 1：工程与高风险验证（2–4 人日）

**新建文件：** `mobile/flutter_app/`、`docs/mobile-parity/platform-spikes.md`。

- [x] 在实现分支建立 Android-only Flutter 工程，并记录 Flutter/Dart 版本；JDK/Android SDK 缺失已记录为阻塞。

```bash
flutter doctor -v
flutter create --platforms=android --org net.vpush --project-name vpush mobile/flutter_app
```

- [x] 工程生成后把开发包 applicationId 设置为 `net.vpush.app.dev`、namespace 设置为 `net.vpush.app.dev`、minSdk 设为 26，并保留调试签名。
- [ ] 第一轮构建两个 release ABI 并安装到 ARM64/ARMv7 设备；当前被 Android command-line tools、JDK 和设备缺失阻塞。空工程与候选依赖已完成 `pub get`。
- [ ] PDF 优先验证 `pdfrx` 候选；依赖已解析，中文/鉴权/长文档/双 ABI/16KB 页真机验证待工具链和 fixture。
- [ ] 用真实测试实例验证 Turnstile：受控 HTTPS 验证页仅传回一次性 challenge token，Flutter 提交现有登录/注册 API；白名单限制域名与回调，JWT 不通过 URL 传递。验证通过/取消/过期/失败四条路径。
- [ ] 如果站点 WAF 对原生 HTTP 请求发起浏览器挑战，定位为客户端接入配置问题，采用站点支持的接入方式验证；不得把验证关闭作为客户端完成条件。
- [ ] `flutter_html` 候选依赖已解析；真实脱敏文章、表格、图片和文本选择覆盖待 fixture 后验证。
- [ ] 选定通知 SDK/服务覆盖范围并验证两个 ABI；大陆安卓优先评估一个支持所需厂商通道的聚合服务，FCM 仅适用于明确依赖 GMS 的设备范围。资格/凭证、SDK 许可证、厂商覆盖和服务费用是选型输入。

**验收：** 两个 ABI 的插件验证 APK 可安装、启动并执行 PDF/验证/通知样例；形成通过/失败证据和唯一选定依赖组合。CLI 列出 armv7 不能代替插件真机验证。

### 阶段 2：设计组件、认证与应用外壳（4–6 人日）

**新建文件：** `lib/core/` 上述文件、`lib/features/auth/login_page.dart`、`auth_controller.dart`、`lib/features/shell/app_shell.dart`、`bottom_navigation.dart`、`test/core/session_test.dart`、`test/shell/navigation_test.dart`。

- [ ] 迁移当前生效的颜色、字号、行高、圆角、尺寸和 SVG，建立浅色、深色、系统主题；实现通用按钮、输入框、弹窗和顶部 Toast。
- [ ] 对认证写失败用例：错误密码 401 只显示业务错误；业务请求 401 清除当前会话；旧账号 A 的晚到 401 不清除新账号 B；超时不误报登录过期。
- [ ] 接入 `/api/auth/turnstile`、`/api/auth/login`、`/api/auth/register`、`/api/me`；保留后端 validation detail、注册关闭和限流提示，不发明 refresh-token 自动续期。
- [ ] 按 MOBILE_NAV 实现底栏图标、选中色/线宽、点击反馈、新闻开关和管理员更多；研报及旧路由按 Web 映射。
- [ ] 实现向下 24 / 向上 8 逻辑像素累计隐藏逻辑，边缘滚动 clamp，隐藏控件移出可点击/可聚焦范围。
- [ ] 写组件用例验证 23px 不隐藏、再 1px 隐藏、上移 7px 不显示、再 1px 显示；新闻关闭后入口与路由均受控；普通用户不能打开管理员页。
- [ ] 登录页视觉、焦点、键盘和过渡录屏对照；处理 edge-to-edge、安全区、Android 状态栏和导航栏随 App 主题切换。

**验证命令（Flutter 工程目录）：**

```bash
flutter analyze
flutter test test/core/session_test.dart test/shell/navigation_test.dart
```

**验收：** 认证状态用例全部通过，三种宽度/两种主题下外壳匹配基线，可从登录进入正确角色导航。此阶段交付第一份可操作预览 APK。

### 阶段 3：动态与快讯（5–7 人日）

**新建文件：** `lib/features/timeline/timeline_page.dart`、`timeline_controller.dart`、`post_card.dart`、`live_feed.dart`、`market_panel.dart`、`test/timeline/timeline_controller_test.dart`。

- [ ] 按 `/api/my/feed`、`/api/live/wscn` 的实际合同实现首次加载、筛选、分页、更新探测与稳定去重。
- [ ] 实现帖子、引用/转发、平台标识、组合调仓、附件、关键词、图片隐藏、原文/翻译切换；复用现有文案与内容格式规则。
- [ ] 按移动断点复制单行等宽平台图标角标，不转成文字 chip 或横滑标签。
- [ ] 保留动态和快讯各自滚动/筛选状态；按 Web 还原顶部自动消费新内容与离顶提示行为，避免阅读中插入内容顶走视线。
- [ ] 对照基线加入刷新入口、骨架、空态、错误重试、底部加载状态；Web 没有的下拉刷新/振动不默认添加。
- [ ] 完成灯箱、手势切图、打开原文、知识星球文件下载；只迁移手机视口可见的行情内容。
- [ ] 控制器测试覆盖旧筛选请求晚到、分页与刷新并发、重复 ID、无下一页、后台恢复、取消后错误不覆盖当前页面。

**验证：** `flutter test test/timeline/timeline_controller_test.dart`；用 fixture 完成“滚动 → 新帖到达 → 点击提示 → 开图 → 返回 → 切快讯 → 返回”录像，列表无重复且位置符合基线。

### 阶段 4：广场、订阅与大 V 详情（3–4 人日）

**新建文件：** `lib/features/plaza/plaza_page.dart`、`plaza_controller.dart`、`kol_detail_page.dart`、`test/plaza/subscription_test.dart`。

- [ ] 接入目录、搜索、推荐、分类、标签、已订阅和特别关注，搜索防抖参照 Web 的 200ms；乱序结果不能覆盖新关键字。
- [ ] 实现订阅、取消、订阅类型、特别关注、次要关注和求添加；按当前权限决定按钮与反馈。
- [ ] 成功后更新所有已打开页面的相同订阅状态；请求失败恢复按钮、保留上下文，不显示虚假成功。
- [ ] 大 V 详情实现资料、帖子与组合持仓/净值，数值格式、涨跌色和空态遵循 Web。
- [ ] 用例覆盖连续点击不重复提交、失败回退、取消后两个页面状态同步、旧 `/mysubs` 和 `/combinations` 路由跳转。

**验证：** `flutter test test/plaza/subscription_test.dart`；测试账号在 App 订阅后，Web 广场能看到同一变更，取消后 Web 与 App 一致。

### 阶段 5：财经新闻（3–4 人日）

**新建文件：** `lib/features/news/news_page.dart`、`article_page.dart`、`news_controller.dart`、`test/news/news_reader_test.dart`。

- [ ] 接入新闻来源、列表、文章详情和已读协议；来源选择通过现有 `/api/me` 保存。
- [ ] 使用阶段 1 通过的正文渲染方式，逐项对齐标题、媒体、时间、段落、引用、列表、表格和内文图；图片请求携带正确鉴权。
- [ ] 保持 Web 的站内阅读内容边界和原文入口；不额外添加公开全文分享。
- [ ] 测试新闻关闭时退出不可访问页面、文章删除/无权限、图片失败不抹掉正文、返回恢复列表、晚到已读更新归属正确。

**验证：** `flutter test test/news/news_reader_test.dart`；长文截图核对行数/宽度，慢网加载的正文和图片状态与 Web 一致。

### 阶段 6：研报、PDF 与飞书时间线（5–8 人日）

**新建文件：** `lib/features/knowledge/knowledge_page.dart`、`knowledge_controller.dart`、`document_reader.dart`、`pdf_reader.dart`、`feishu_timeline.dart`、`test/knowledge/reader_state_test.dart`。

- [ ] 接入知识库目录、授权/订阅、日期/标签/搜索和分页；搜索遵循服务端既有短查询及全文检索规则，客户端不另做搜索结果算法。
- [ ] 将 group、doc_group、q、day、tag 与列表快照建模，确保从搜索打开文档后可以回到原查询、原日期和原滚动位置。
- [ ] 对齐摘要折叠、翻译结果、文件元信息、上下篇、无 PDF、无权限和限流状态；快速切文档时旧翻译/PDF 不能覆盖当前文档。
- [ ] PDF 通过鉴权请求下载到缓存文件后渲染；验证返回内容是 PDF，传入 group 权限上下文；取消下载、释放 renderer 和文件句柄。
- [ ] PDF 的“打开”和“下载”使用 Android 文件/应用选择界面，对照 Web 手机实际 PDF 入口记录系统层差异；不把桌面 iframe 行为当手机基线。
- [ ] 飞书时间线保留日期工具栏、图片/附件、原文和更新提示；切离页面停止轮询，页面销毁后响应不能更新 UI。
- [ ] 写用例覆盖无权 group、文档 A 下载晚于 B、返回快照不属于当前 query、不合法 PDF 响应、附件错误、重复打开/关闭资源释放。

**验证：** `flutter test test/knowledge/reader_state_test.dart`；真机循环打开/关闭 PDF 20 次、阅读长文档并切换主题，记录内存趋势，不能崩溃或持续线性增长。

### 阶段 7：个人设置与绑定（3–5 人日）

**新建文件：** `lib/features/settings/settings_page.dart`、`settings_controller.dart`、`channel_binding.dart`、`feishu_registration.dart`、`test/settings/settings_test.dart`。

- [ ] 按现有四页签迁移所有设置表单、说明文案、保存按钮、加载/成功/失败状态。
- [ ] 接入总开关、每日摘要、翻译、跨午夜免打扰、特别关注穿透、关键词（20 个/每个 50 字）、研报匹配、逐大 V 图片和渠道选择。
- [ ] 完成 Telegram/飞书/企业微信/Bark 的既有绑定配置、绑定码复制、二维码个人机器人创建、取消、过期刷新与前台状态轮询。
- [ ] 完成 AI 网关配置、模型获取/测试、账号修改密码和退出；敏感字段依服务端掩码协议显示，不把掩码作为新密钥回传。
- [ ] 浏览器通知显示既有浏览器设备的绑定状态；不能把“在此浏览器开启”按钮伪装成本机已启用。App 本机通知入口由阶段 9 实现，作为必要的平台文案差异记录。
- [ ] 测试轮询不会覆盖正在编辑的表单、保存失败不丢输入、二维码取消停止轮询、跨午夜值往返一致、账号切换清除旧绑定状态。

**验证：** `flutter test test/settings/settings_test.dart`；修改后用 Web 同账号核对值。测试推送仅发往测试账号绑定的收件渠道。

### 阶段 8：管理员功能全量迁移（5–8 人日）

**新建文件：** `lib/features/admin/admin_page.dart`、`content_page.dart`、`sources_page.dart`、`knowledge_settings_page.dart`、`ops_page.dart`、`accounts_page.dart`、`test/admin/admin_access_test.dart`。

- [ ] 以阶段 0 完整清单为准，迁移“内容管理”内目录、求添加、分类/标签与新闻来源管理。
- [ ] 迁移“数据源”内现有 Cookie、扫码、采集/轮询、代理和基础设施配置，以及手机可见的运行状态。
- [ ] 迁移“研报设置”内知识库、IMA/CICC、飞书文档、导入/同步和权限配置；保留各状态与失败说明。
- [ ] 迁移“帖子与日志”的查询/操作，以及“用户与注册”的用户授权、邀请码及配额操作。
- [ ] 对照 Web 复刻现有页签路由、确认弹窗、危险操作前置条件和表格的手机呈现；不新增通用表单生成器。
- [ ] 测试普通用户深链访问被拒、管理员权限在会话内撤销、403 的错误呈现、重复提交、错误回滚；实际管理写操作只针对可重建测试数据。

**验证：** `flutter test test/admin/admin_access_test.dart`；coverage.csv 所有管理员条目通过。用户端已完成但此阶段未完成时，只能称用户端 Beta，不能称“完整复刻”。

### 阶段 9：Android 系统适配与通知（4–8 人日）

**新建文件：** `lib/platform/file_actions.dart`、`external_links.dart`、`push_registration.dart`、`integration_test/android_lifecycle_test.dart`、`docs/mobile-parity/android-differences.md`。

**仅原生通知需要的后端修改：** `app/api.py`、`app/db.py`、`app/channels.py`、`app/scheduler.py` 中实际分发接点；新增 `app/notifiers/android_push.py` 和设备绑定相关测试。不要重写现有通知管线。

- [ ] 外部链接和 App Links 按现有 Web 路径映射；未登录保存目标，登录后恢复。只拦截支持的本站路径，外站交给系统浏览器/对应 App。
- [ ] 文件通过应用缓存 + FileProvider/系统保存对话框处理；不申请“所有文件访问”来完成 PDF 下载。无目标 App 时明确显示原因。
- [ ] 完成系统返回/预测返回、键盘、状态栏、安全区、启动屏和后台恢复；返回业务页面不套用额外 Material 过渡。
- [ ] 依阶段 1 的选定通道实现设备 token 注册、刷新、解绑及多设备归属。建议新增 `PUT /api/me/android-devices/{installation_id}`、`DELETE /api/me/android-devices/{installation_id}`，服务端以当前登录用户判定归属；这些是拟新增接口，不是现有接口。
- [ ] 后端新建 android 通道，复用已有免打扰、关键词、特别关注、摘要及失败处理规则；检索所有硬编码通道枚举与选择逻辑，确保旧客户端保存设置时不意外丢失新通道。
- [ ] 本机通知与浏览器通知分别表示状态，保留原有浏览器设备送达。用户主动开启时申请 Android 13+ 通知权限，拒绝时界面保持未开启。
- [ ] 通知点击只携带受支持的资源标识/路由，不携带 JWT；回前台后重新鉴权。注销后解绑设备，即使解绑网络失败，本地也不向下个账号展示旧账号内容。
- [ ] 测试前台、后台、普通进程被系统回收、锁屏、离线重连、token 轮换、通知权限撤回及点击进入正确页面；强行停止 App 的系统限制单独记录，不能承诺强停后保证送达。
- [ ] 以无 GMS 的目标国产设备和 ARM v7 设备验证实际通道；FCM 在 GMS 模拟器成功不能代表国产设备验收通过。

**验收：** 系统行为差异全部列明；每种承诺支持的设备/通道都有通知到达与点击证据。通知资格或凭证未准备好时，其余页面仍可推进，但完整系统通知验收不可标记完成。

### 阶段 10：统一对照、性能与发布准备（4–6 人日）

**新建文件：** `test/goldens/`、`integration_test/parity_flow_test.dart`、`scripts/build_flutter_android.sh`、`.github/workflows/flutter-android.yml`、`docs/android-flutter-release.md`、`docs/mobile-parity/release-checklist.md`。

- [ ] 逐项复查 coverage.csv，不只跑通主流程；三种宽度、双主题、普通/管理员、新闻关闭、大字体和键盘均有结果。
- [ ] Flutter Golden 用于后续自身回归；Web 对照用真实设备截图/录像。两种测试不能互相代替，不自动更新失败 Golden 来掩盖差异。
- [ ] 相同 fixture 下对照截图与热图，复查动效的开始/中间/结束帧和连续点击中断行为。
- [ ] 中端 ARM64 60Hz 真机以 profile 模式测量：列表滚动采样 60 秒，UI 与 raster 帧时长分别 P95 ≤16.7ms；若基线设备不能达到，给出实测瓶颈后修复，不只报平均 FPS。
- [ ] ARM v7 真机跑同一流程与大 PDF 测试：无崩溃/ANR/持续内存增长；拟定滚动帧超时比例 ≤5%。冷启动到首个可交互外壳目标 ≤2.5 秒，网络数据耗时单列，不把该目标当已测结果。
- [ ] 运行分析、针对性业务测试、Golden 与端到端；涉及后端的修改运行相关 pytest 及现有渠道回归。

```bash
dart format --output=none --set-exit-if-changed lib test integration_test
flutter analyze
flutter test
flutter test integration_test/parity_flow_test.dart
```

- [ ] CI 固定 Flutter/JDK/SDK 组合、提交应用依赖锁文件、输出版本/commit/校验和及 ABI 检查结果；没有签名密钥时明确产物仅为测试包，不用 debug 签名冒充正式包。
- [ ] 按第 8 节生成两个签名 APK，验证干净安装和上一版本覆盖升级；准备安装说明、已知差异、性能结果和回滚说明。

**验收：** 功能覆盖条目 100% 有通过证据或明确列出的平台差异；没有丢失数据、错误权限、核心流程崩溃等阻断问题；两个 APK 签名、ABI、安装/升级都通过。

## 7. 接口复用清单

以下路径已在当前源码中核实。响应字段与分页参数由阶段 0 的 fixtures 固定，不能直接假设所有接口都返回统一 `items/next_cursor` 包装。

| 业务 | 现有接口 |
| --- | --- |
| 认证 | `GET /api/auth/turnstile`、`POST /api/auth/login`、`POST /api/auth/register` |
| 个人资料/设置 | `GET/PUT /api/me`、`POST /api/me/password`、`POST /api/me/llm-models`、`POST /api/me/llm-test` |
| 目录与订阅 | `GET /api/catalog`、`GET /api/recommendations`、`GET /api/my/subscriptions`、`POST /api/subscriptions`、`PUT/DELETE /api/subscriptions/{kol_id}` |
| 订阅属性 | `PUT /api/subscriptions/{kol_id}/favorite`、`/secondary`、`/hide-images` |
| 动态与快讯 | `GET /api/my/feed`、`GET /api/live/wscn`、`GET /api/market/indices` |
| 大 V /组合 | `GET /api/kols/{kol_id}`、`/posts`、`/holdings`、`/nav` |
| 求添加 | `POST /api/kol-requests`、`GET /api/my/kol-requests` |
| 新闻 | `GET /api/news/sources`、`GET /api/news`、`POST /api/news/seen`、`GET /api/news/{article_id}`、`GET /api/news/{article_id}/images/{index}` |
| 知识库与文档 | `GET /api/ima-documents/catalog`、`GET /api/ima-documents`、`GET /api/ima-documents/{media_id}`、`GET /api/ima-documents/{media_id}/pdf` |
| 库订阅/摘要 | `POST/DELETE /api/ima-documents/groups/{group_id}/subscribe`、`POST /api/ima-documents/{media_id}/translate` |
| 附件 | `GET /api/media/zsxq-file/{file_id}`、`GET /api/ima-documents/{media_id}/assets/{asset_id}` |
| 绑定 | `POST /api/me/bind-code`、`/api/me/feishu-personal/...`、`POST/DELETE /api/me/webpush` |
| 管理员 | 保留各现有 `/api/admin/...` 方法、参数与权限，逐容器录入合同清单 |

`GET /api/version` 当前返回服务端版本与仓库更新地址，不是 Android APK 更新协议。App 展示自己的构建版本；首版采用人工下载升级，不据此接口提示安装服务端版本号对应的 APK。

## 8. ARM v7 / ARM v8 构建与升级策略

### 双包产出

| 用户下载名称 | Android ABI | Flutter target | 用途 |
| --- | --- | --- | --- |
| `vpush-<版本>-armv7.apk` | `armeabi-v7a` | `android-arm` | 支持 32 位 App 的 ARM 设备 |
| `vpush-<版本>-arm64.apk` | `arm64-v8a` | `android-arm64` | 64 位 Android；包括不再支持 32 位 App 的设备 |

从 Flutter 工程目录执行，版本号从 `pubspec.yaml` 读取；服务地址不是秘密，不把任何凭证放进 dart-define。

```bash
flutter pub get
flutter build apk --release --split-per-abi \
  --target-platform android-arm,android-arm64 \
  --dart-define=API_BASE_URL=https://vpush.net
```

预期输出：

```text
build/app/outputs/flutter-apk/app-armeabi-v7a-release.apk
build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
```

ARM64 的 APK 不依赖另一份 APK；不是 Android 安装会话里需要组合的配置 split。可对外改名，不把 x86_64 包加入正式双包交付；测试模拟器可另建调试包。

### 验证要求

- `unzip -l` / APK Analyzer 检查 v7 包只包含 v7 的本地库、v8 包只包含 v8 的本地库，且 `libflutter.so`、`libapp.so` 和所有插件 `.so` 完整。
- 用 SDK Build Tools 的 `apksigner verify --verbose --print-certs` 验证签名；用 `apkanalyzer manifest application-id`、`version-code`、`min-sdk`、`target-sdk` 读取最终 APK 信息。
- 用 `adb shell getprop ro.product.cpu.abilist` 核实设备支持 ABI；在 64 位设备上能装 v7 不代表覆盖了旧 32 位系统，在只支持 64 位的设备上 v7 不能安装。
- 检查 64 位原生依赖的 16KB 内存页兼容与 APK 对齐，并在匹配页大小的设备/模拟器运行。构建成功不等于运行兼容。
- Flutter/Gradle 的 ABI split 可能变换最终 versionCode；检查生成物，不只看 `pubspec.yaml` 的数字。两种 ABI 分别记录已发布最高 code，后续构建必须单调递增，并实际测试允许的 ABI 切换升级路径。
- 同一次发布，两种 APK 的 versionName、功能、API 地址与签名一致；提供 SHA-256、大小、最低 Android、版本/commit、安装说明。

### 包名与旧客户端

**开发期建议：** 使用 `net.vpush.app.dev` 与旧客户端并存。原生 UI 和通知在独立测试包验证后再制作正式候选包。

**正式包可选策略：**

1. **独立安装：** 使用 `net.vpush.app`，独立签名与版本序列；旧 TWA 保留以便对比，用户在新 App 重新登录。无需迁移浏览器存储，风险和工作量较低。
2. **覆盖旧包：** 保持 `net.vpush.twa`，使用原签名证书，最终 versionCode 高于设备已安装版本；核查线上最高版本，不能仅依赖当前源码的 112163。TWA 登录态在 Chrome origin 存储内，不能假定 Flutter 可读取，升级后重新登录应写入说明。

计划建议开发期并存，正式分发前再选是否替换旧客户端。签名密钥不进仓库；正式构建通过受保护的本机配置/CI secret 注入。App Links 的 `assetlinks.json` 要匹配正式包名与证书指纹。SDK 的 compile/target 值使用阶段 1 验证过且满足分发渠道要求的组合，不直接照抄旧包 targetSdk 35。

“回滚”优先是同签名、更高 versionCode 的修复版。不能承诺 Android 允许正常覆盖安装低 versionCode 的旧 APK；独立测试包也不能覆盖正式包数据。

## 9. 排期与里程碑

按一位熟悉 Flutter 的工程师、可用的测试后端/账号/两类 ARM 真机估算；设计对照和测试包含在各阶段中。人日是工作量，不是 AI 运行时长承诺。

| 里程碑 | 包含阶段 | 交付 |
| --- | --- | --- |
| M0 对照与技术可行性 | 0–1 | 完整范围清单、截图/录屏、API fixture、双 ABI 插件验证包 |
| M1 可交互外壳 | 2 | 登录、主题、导航、基础动效，约累计 8–13 人日 |
| M2 用户核心流程 | 3–5 | 动态、快讯、订阅、大 V、新闻，约累计 19–28 人日 |
| M3 完整业务界面 | 6–8 | 研报/飞书/设置/管理员齐全，约累计 32–49 人日 |
| M4 正式候选包 | 9–10 | 通知与系统适配、完整对照报告、双 ABI 签名包，约累计 40–63 人日 |

总工作量约 **40–63 人日，即单人 8–13 个工作周**。通知厂商资质、外部审核、采购测试机和签名资料等待不计在内。管理员实际子功能数量、正文/PDF 差异和 Web 基线变动是主要变动项，阶段 0–1 后重新估算。

依赖顺序为：基线 → 双 ABI/关键插件验证 → 认证与外壳 → 核心页面 → 阅读/设置/管理 → 全量对照与发布。通知通道验证在阶段 1 前置，实际接入在阶段 9 收口，避免最后才发现所选 SDK 不支持 v7。

## 10. 开工时需要落定的三项选择

这些选择不妨碍本次计划交付；在相应实现阶段前记录结论即可，不要求用户先回答一长串问题。

1. **业务界面路线：** 本计划默认 Flutter 原生；若首要要求是直接复用 Web 像素/动效，应改为 WebView 计划，不执行原生页面迁移任务。
2. **本机通知覆盖：** 明确目标是否含无 GMS 的国产安卓、需要哪些厂商后台送达；阶段 1 选定一个通道，准备测试凭证。若决定首版不做本机通知，必须把它列为明确差异，不能称通知体验完全相同。
3. **正式升级策略：** 新包并存还是替换 `net.vpush.twa`；开发期先用独立测试包，正式签名和 App Links 配置前确定。

## 11. 最终交付清单

- [ ] Flutter Android 源码、锁定依赖、必要后端补充及有意义的测试。
- [ ] 普通用户与管理员完整覆盖清单，每项附测试结果。
- [ ] 三种宽度/两种主题的 Web ↔ Flutter 截图对照和关键动效录像。
- [ ] 登录、订阅、新闻、PDF/附件、绑定、系统通知的端到端证据。
- [ ] ARM v7、ARM v8 两个可独立安装的正式签名 APK，以及 SHA-256、版本、ABI、签名指纹和包大小记录。
- [ ] 真机性能结果、系统行为差异、已知问题、安装/升级与回滚说明。

后续 Web 调整时，将影响页面的样式/交互变更同步登记到 coverage.csv 与差异表；没有重新对照的客户端版本不能继续宣称与最新 Web 完全一致。
