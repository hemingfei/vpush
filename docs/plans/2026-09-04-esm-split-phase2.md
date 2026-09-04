# 前端 ES Modules 第二阶段拆分计划（2026-09-04）

## 基线（第一阶段验收后实测）

- app.js **12,232 行**（Phase 1 前 13,742）
- 已拆出：`views/feishu-personal.js`(864)、`views/push-settings.js`(737)、`views/news.js`(274)、`core/lightbox.js`(106)、`core/dialog.js`(67)、`core/html.js`(19)；规范文档 `docs/frontend-split-convention.md` 已生效；v1.12.135 已发布验收
- **管理后台区块：4873–11412，共 6,540 行**，内部无二级分界注释，靠函数命名分域
- 其中 **imaKb 簇（采集器/挂载组/ACL/文档浏览/阅读器）约 105 个函数 ≈ 2,500 行**，且用户侧研报库浏览与后台设置混居——本阶段不动（见非目标）
- 其余子域合计 ≈ 4,000 行，命名边界清晰，是本阶段的主战场

## Phase 2 目标

把管理后台区块中 **imaKb 以外的全部子域**（约 4,000 行）拆到 `views/admin/*.js`，app.js 降到 **~8,300 行**；新增一个防漏挂的静态校验关卡。全程延续 Phase 1 铁律：纯位移、factory 依赖注入、每切片独立 commit + 冒烟。

## T0 防漏挂静态校验（先于一切切片）

`scripts/check_inline_handlers.py`（约 40 行，无框架）：
- 解析 app.js 的 `INLINE_HANDLERS` 全部键名
- 解析 app.js 顶层 `function/const` 定义 + 各 view/core 模块的 import 绑定
- 断言每个键都可解析到定义，漏挂/重名即非零退出
- CI 在 `node --check` 之后追加一行调用（改 `.github/workflows/docker-publish.yml`）
- 附测试 `tests/test_inline_handlers_check.py`

动机：Phase 2 要在 254 项的接线表上动 6 次刀，「按钮无响应」是最大风险，语法检查挡不住，必须静态把关。

## 切片（按此顺序；规模以开工时实测为准）

### S1 `views/admin/codes.js`（约 550–700 行）
- 范围：邀请码——`adminCodes*`（13 个 handler）、`adminGenerateCodes` `adminRevokeCode` `adminRevokeBatch` `searchAdminCodes` `selectAdminCodeFilter` `adminCodesToggle*` `renderCodes*` `renderCodeRow` `renderCodeGroups` `codeStatus*` `codeCanRevoke` `codeCanPurge` `formatInvite*` `saveCodesForm` `clearAdminCodesResult` `adminBatchLinesHint`
- 冒烟：生成码（各类型/批量）、复制、备注、撤销/批量撤销、列表筛选翻页

### S2 `views/admin/news.js`（约 650–900 行）
- 范围：内容源管理——`loadAdminNews` `renderAdminNews` `adminNews*`（toggle/update/archive/restore/feed 系列）`selectAdminNewsSource` `saveAdminNewsSettings` `refreshAdminNewsFeed` `refreshAllAdminNews` `adminFilterPosts` `adminPostsLoadMore` `adminTogglePost` `renderAdminPosts` `postRowHtml` `sourceRowsHtml` `sourceEventRowsHtml` `sourceStatus*` `sourceCause*` `abnormalSourceEvents` `validateNewsFeedDraft` `openNewsSourceModal` `openNewsFeedModal` `closeNewsModal`
- 冒烟：源列表启停/归档/恢复、feed 增删改、帖子筛选与加载更多、异常源告警显示

### S3 `views/admin/users.js`（约 700–1,000 行）
- 范围：用户与审批——`loadAdminUsers` `renderAdminUsers` `adminUser*`（选择/翻页/筛选）`adminUsersBatch` `adminUsersApplyFilter` `adminOpenUser` `adminDeleteUser` `adminSaveUsername` `adminSaveUserKnowledge` `adminSavePassword` `adminSendTestPush` `adminToggleAdmin` `adminApproveRequest` `adminRejectRequest` `adminToggleSecondary` `adminTogglePriority` `inactivePolicy*`（draft/hint/label/saved/paint）`adminSaveInactivePolicy` `adminInactivePolicySyncSave` `adminInactivePolicyKeydown` `userHasBoundChannel` `userChannelIconsHtml`
- 冒烟：用户列表筛选翻页、批量操作、开小号改密、审批通过/拒绝、免打扰闲置策略保存

### S4 `views/admin/kol.js`（约 900–1,300 行）
- 范围：大V管理——`loadAdminKols` `adminKols*`（filter/clearFilter/page/select）`adminKol*`（batch/batchCategory/toggleSelect/togglePage/clearSelect）`adminEditKol` `adminDeleteKol` `adminDeleteKolFromHome` `adminToggleKol` `saveKolEdit` `adminSaveTags` `adminSaveStockNames` `adminMaintainTags` `formatMaintainResult` `adminBatchAddKols` `adminAddCategory` `adminDeleteCategory` `adminRenameCategory` `switchAdminKolsPlatform` `staleKols*` `reloadKolImageSettings` `filterKolImageSettings` `toggleKolImages` `openAdminKolFromHealth` `adminBackfillTags`
- 冒烟：大V列表筛选翻页批量、编辑/删除、标签回填与维护、分类增删改、图片设置

### S5 `views/admin/infra.js`（约 750–1,100 行）
- 范围：代理与存储——`loadProxyAdmin` `renderProxyAdmin` `proxy*`（create/delete/test/import/extract/busy/status*）`syncProxyPoolForm` `syncProxyRouteInputs` `saveProxyRoutes` `runStorageDedup` `runStorageConsistency` `loadStorageHealth` `backupImaStorage` `backupWebDAV*`（body/status/download/restore/restoreUpload）`saveBackupWebDAV` `testBackupWebDAV` `backupDownload` `saveStorageAlerts` `fmtCacheBytes` `scanLocalLibraries` `loadLocalLibraries` `saveLocalLibrary*` `localLibrary*` `toggleLocalLibrary` `openLocalLibraryCreateModal`
- 冒烟：代理池增删测、路由保存、存储健康/去重/一致性、WebDAV 备份恢复下载、本地库扫描与新建

### S6 `views/admin/dashboard.js`（约 450–800 行）
- 范围：仪表盘与日志——`loadAdminDashboard` `refreshDashboardLive` `startDashboardLiveTimer` `dutyStripHtml` `dashboardFetchMetaHtml` `loadAdminStats` `renderStatsData` `switchStatsTab` `statCard` `rateBar` `loadAdminSysLogsPanel` `loadAdminErrorLogs` `adminFilterLogs` `startSysLogsTimer` `stopSysLogsTimer` `stopStatsTimer` `fmtTs` `fmtDbTime` `fmtRelativeFromMs` `parseDbUtcMs`（时间格式化若多切片共用则下沉 common）
- 冒烟：仪表盘实时刷新、值班条、统计三 tab、系统日志/错误日志筛选

### 共享件下沉规则（不预设、按需触发）
`closeAdminModal` `statCard` `fmtTs` `fmtDbTime` `copyText` `copyDataAttr` 等若被 **第二个切片** 用到，即下沉 `views/admin/common.js`（禁止第一个切片就预抽）。admin 壳与导航（`renderAdmin` `isAdminSettingsPath` `reloadAdminSettingsPage`）留在 app.js，Phase 2 结束时再评估。

### 每切片固定流程（同 Phase 1）
纯位移 → app.js import + INLINE_HANDLERS 接线 → `bump_assets --sync` → `node --check` + `check_inline_handlers.py` → pytest → 独立 commit → 部署 → 后台逐 tab 冒烟 →（顺利时相邻两切片可合并一次部署）

## 非目标（本阶段不做）
- **imaKb 簇 ~2,500 行**（105 个函数）：文档浏览/阅读器是用户侧视图，采集器/ACL/挂载组是后台设置，两者边界需要先摸清——留给 Phase 3，届时拆 `views/ima.js` + `views/admin/ima-collector.js` + `views/admin/knowledge.js`
- 订阅广场 / 动态 / 大V动态页 / 搜索（用户侧主视图，Phase 3）
- 壳 / 路由 / 认证 / 主题（最后收）
- 不引构建链、不加测试框架、不改行为

## 验收标准
- [ ] app.js ≤ ~8,500 行；新增 6+ 文件各自 ≤1,300 行
- [ ] `check_inline_handlers.py` 进 CI 且全绿（T0 完成即生效，先于 S1）
- [ ] 每切片 CI 全绿 + 对应后台 tab 冒烟全过，零行为回归
- [ ] 管理后台区块仅剩 imaKb 簇与 admin 壳
- [ ] 全部切片与 `docs/frontend-split-convention.md` 规范一致

## 风险与对策
| 风险 | 对策 |
|---|---|
| 254 项接线表动 6 次刀，漏挂 = 按钮无响应 | T0 静态校验先上，CI 拦截 |
| imaKb 与各切片边界交叠（如 loadAdminKnowledge 里的 ima 状态） | 切片时「谁渲染谁持有」； imaKb 触碰的一律留下，不硬拽 |
| 共享 helper 被多切片复制 | 第二次需要时立即下沉 common.js，禁止复制粘贴 |
| admin 壳（renderAdmin）依赖各切片渲染函数 | 壳留在 app.js，import 各切片的 create 工厂，依赖方向永远是 壳→切片 |
| 时间格式化等工具函数散布 | 先随首个切片走，第二次复用时下沉 common |
