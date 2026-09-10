# V Push 移动端对照基线

## 当前状态

- Web 代码基线：`04ea67bbf44b07e2cca4967090022a3275cee252`
- 计划日期：2026-09-10
- 对照目标：Android Chrome 手机视口与 Flutter Android 原生界面
- 目标视口：360、390、412 CSS px；浅色、深色、系统主题
- 当前工作项：源码清单和计算样式候选值已完成；真实账号截图、录像、fixture 尚未完成

当前没有提交测试账号或可脱敏的稳定数据集，因此本文件不能被当作“视觉对照已通过”的证明。后续应在测试实例上补齐 `coverage.csv` 中标记为 `pending-capture` 的项目。

## 已确认的产品结构

手机底部入口来自 `app/static/app.js` 的 `MOBILE_NAV`：动态、财经新闻、广场、个人设置。新闻功能关闭时隐藏财经新闻；管理员额外显示“更多”。研报中心从动态页内容进入；旧的“我的订阅”和组合路由重定向到广场或动态页。

桌面侧栏仍是功能清单事实来源：最新动态、财经新闻、研报中心、订阅广场、个人设置，以及管理员的内容管理、数据源、研报设置、帖子与日志、用户与注册。客户端不能因为手机没有侧栏就删除可达能力。

## 样式候选基线

候选值来自 `app/static/vendor/design-tokens.css`、`app/static/style.css` 和 `DESIGN.md`，阶段 0 真机采集时以浏览器 computed style 为准：

| 角色 | 候选值 |
| --- | --- |
| 页面底色 | `#f5f5f7` |
| 表面 | `#ffffff` |
| 正文 | `#1d1d1f` |
| 次要文字 | `#6e6e73` |
| 操作蓝 | `#1668e0` |
| 操作蓝按下 | `#1258c4` |
| 危险色 | `#dc2626` |
| 成功色 | `#3a6e4b` |
| 默认边框 | `rgba(12, 18, 34, 0.1)` |
| 正文 | 15px |
| 标题 | 17px / 600 |
| 显示标题 | 30px / 600 |
| 控件高度 | 42–44px |
| 手机底栏最小高度 | 48px + `safe-area-inset-bottom` |

## 采集协议

1. 固定 Chrome 版本、Android 版本、DPR、系统字体缩放、主题、服务端 commit 和测试数据。
2. 每个页面保存首屏、滚动中段、空态、加载态、失败态和主要弹窗截图；动画保存开始/中间/结束帧或短录像。
3. 截图文件名使用 `coverage-id__viewport__theme__state.png`，不保存 token、cookie、绑定码或私人正文。
4. 对比前裁剪系统状态栏和浏览器地址栏；Flutter 截图保留 App 内容区，并单独记录系统栏差异。
5. 文本差异记录换行、基线和字重；不要用像素热图掩盖文案或内容不一致。

## 环境记录

- Flutter 3.47.2 / Dart 3.13.2：可用。
- Android command-line tools：缺失，`flutter doctor -v` 未通过 Android toolchain。
- Java Runtime：当前 shell 未找到，无法运行 Gradle。
- 真机/模拟器：`adb devices -l` 当前没有 Android 设备。
- 结论：可完成 Dart 工程和文档基线；Android APK、插件 ABI、真机视觉和通知验收需补齐工具链后执行。
