# 前端 ES Modules 第一阶段拆分计划（2026-09-04）

## 基线（2026-09-04 实测）

- `app/static/app.js` **13,742 行**，内部已有 13 个 `// ---------- 区块 ----------` 注释分界
- 已拆先例：`core/html.js`(19)、`core/dialog.js`(67)、`views/news.js`(274，factory 依赖注入模式)
- 工具链已就绪：`scripts/bump_assets.py` 自动把 `core/`、`views/` 全部 js 纳入 digest + SW 预缓存；CI 跑 `node --check` + `bump_assets --check`
- 内联 handler 接线点：`INLINE_HANDLERS` 表（254 项，L13483）+ `Object.assign(window, …)`（L13739）
- 前端无 UI 自动化测试；验证 = CI + 手工冒烟

## Phase 1 目标

**不改任何行为**，按 `views/news.js` 的 factory 模式拆出 3 个区块边界清晰的功能区，app.js 降到 **~11,700 行（-14%）**，并沉淀一份拆分规范，让后续「顺手拆」有章可循。

## 任务（按顺序执行；从文件底部往上拆，上方行号不漂移）

### T0 拆分规范文档 `docs/frontend-split-convention.md`
- 目录规则：`core/`＝跨视图共享的 UI 组件/工具；`views/`＝页面级视图
- 模式：factory 依赖注入（照抄 news.js：`createXxxView(deps)` 返回公开函数对象）
- 接线规则：新文件 export handler 集合 → app.js import → 并入 `INLINE_HANDLERS`
- 固定动作清单：`bump_assets --sync` → `node --check` → CI 绿 → 手工冒烟 → 独立 commit
- 禁止：引构建链、批量重命名、顺手改逻辑、同仓并行改 app.js

### T1 `views/feishu-personal.js`（区块 5663–6471，约 800 行）
- 范围：飞书个人机器人扫码注册 + 文档时间线 + 文档源管理
- handlers 约 21 个：`startFeishuPersonal` `cancelFeishuPersonal` `refreshFeishuBindCode` `genBindCode` `loadFeishuDocumentSources` `addFeishuDocumentSource` `renameFeishuDocumentSource` `removeFeishuDocumentSource` `toggleFeishuDocumentSource` `syncFeishuDocumentSource` `selectFeishuSource` `setFeishuSourceDisplay` `queueFeishuDocumentPreview` `loadMoreFeishuTimeline` `jumpFeishuTimelineDay` `jumpFeishuTimelineLatest` `downloadFeishuTimelineAsset` `applyFeishuTimelineUpdate` `authorizeFeishuDocuments` `saveFeishuDocsConfig` `setTheme` 归属按实际代码
- 选择理由：区块天然闭合；09-03 刚上线验收过、上下文新鲜；与其他视图几乎零共享状态
- 冒烟：扫码注册→绑定、时间线浏览/跳天/下载、文档源增删改、渠道绑定卡片

### T2 `views/push-settings.js`（区块 4843–5663，约 820 行）
- 范围：推送设置页（渠道绑定、各平台 cookie、DND、通知、WebPush、备份）
- handlers 约 25 个 `save*/start*/backup*/webpush` 类（`savePushChannels` `saveBarkKey` `saveCustomTgBot` `saveDnd` `saveNotify` `saveDailyReport` `enableWebPush` `disableWebPush` `saveBackupWebDAV` `testBackupWebDAV` `backupRestoreWebDAV` `backupRestoreUpload` `backupDownload` `savePassword` `togglePassword` `saveKeywords` `saveLlm` `loadLlmModels` `savePollingConfig` `saveZsxqPollingConfig` `saveZsxqCookie` `purgeZsxqCache` `saveXueqiuCookie` `saveTwitterCookie` `clearSavedCookie` `pasteCookieField` `saveWecomWebhook` `startWeiboQr` `saveCiccScheduleTime` `saveCiccCategories` `toggleCiccSchedule` `loadCiccStatus` …）
- 交界归属原则：**谁渲染这个按钮，handler 归谁**（与 T1/T3 有交界的按此裁）
- 冒烟：设置页每个保存按钮各点一遍 + 渠道绑定 + DND 开关 + WebPush 开关

### T3 `core/lightbox.js`（区块 203–546，约 340 行）
- 范围：图片灯箱（`openLightbox` `closeLightbox` `lightboxStep` + 渲染辅助），纯 UI 组件，适合做热身收尾
- 依赖注入：`$`、`escapeHtml`、`api`（拉原图 blob）等，照 news.js factory
- 冒烟：广场/动态/KOL 页任意多图帖：放大、左右切换、关闭、原图代理回退（onerror）

### 每个任务的固定流程
1. 新建文件，factory 模式搬代码（**纯位移**：不改逻辑、不改名、不"顺手优化"）
2. app.js：加 import → `INLINE_HANDLERS` 对应条目改为引用新文件导出 → 删除原区块
3. `python scripts/bump_assets.py --sync`；`node --input-type=module --check` 两个文件
4. 按冒烟清单手工验证
5. 独立 commit：`refactor(frontend): extract views/feishu-personal.js（纯位移）`
6. 部署 → 生产冒烟 → 观察一天再进行下一个任务

## 非目标（本阶段明确不做）
- 管理后台主体（区块 6471–13010，约 6,500 行）——留给 Phase 2+，按子域渐进（admin-news → admin-kol → admin-codes …）
- 订阅广场 / 动态主视图（流量最高、共享状态最多，最后拆）
- 壳 / 路由 / 认证 / 主题（全局耦合最深）
- 不引入构建工具、不加测试框架、不改任何行为

## 验收标准
- [ ] app.js ≤ ~11,800 行；新增 3 文件各自 ≤1,000 行
- [ ] CI 全绿（node --check + bump_assets --check + pytest）
- [ ] 规范文档存在，且三处拆分与其一致
- [ ] 生产正常发版，SW 缓存自动更新，无「改了不生效」反馈
- [ ] 冒烟清单全过，零行为回归

## 风险与对策
| 风险 | 对策 |
|---|---|
| 区块间交界函数归属不清 | 「谁渲染谁持有」；拿不准的先留在 app.js，下一轮再收 |
| handler 漏挂 = 按钮无响应 | 冒烟清单逐按钮覆盖；INLINE_HANDLERS 引用未定义标识符会直接白屏，node --check 挡不住，靠冒烟 |
| SW 缓存旧版 | bump_assets 自动换 CACHE 名；发版后强刷验证 |
| 并行会话同时改 app.js | 拆分期间不在同仓并行派活；每次拆分独立小 commit |
