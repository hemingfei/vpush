# 前端 ES Modules 第三阶段：imaKb（2026-04-08）

> 延续 `docs/frontend-split-convention.md`：纯位移、factory DI、每切片独立 commit + 冒烟。不拆广场/动态/搜索。

**Goal:** 把研报库用户侧与采集器从 `app/static/app.js` 拆出，admin 知识库页最后收。

**基线:** app.js **8500** 行；v1.12.136 已上线。ima 不是整块注释，按函数名抽（同 Phase 2 S4–S6）。

## 切片

### S1 `views/ima.js`（约 1,500 行）
用户研报库列表 + 阅读器。

- 列表：`renderKnowledge` `renderImaDocuments` 筛选/搜索/订阅/壳
- 阅读器：`renderImaDocument` `loadImaPdf` `downloadImaPdf` `backFromImaReader`
- 状态进 factory：`_imaItems` `_imaListSnapshot` `_imaPdfAbort` 等（不要带走 `_feishu*`）
- **留下：** `onKnowledgeTabsKey`（后台页签）、飞书时间线（夹在阅读器中间）、`fmtCacheBytes`（注入）
- `clearImaPdfUrl` 里的飞书 observer 拆成 app.js 依赖再注入
- `renderImaDocument` 注入 `loadFeishuTimeline` / `feishuSourceDisplay`

冒烟：研报库列表、分组订阅/退订、日/标签/搜索、打开阅读器、PDF、返回

### S2 `views/admin/ima-collector.js`
挂载组 / 文件夹树 / ACL / 保存 / 同步。

- `imaMount*` `imaFolder*` ACL 系列 `saveImaCollector` `triggerImaCollector` `saveImaCredentials` `retryImaGroupAcl`
- 注入同一份 `imaMountState`（用户侧 S1 也用 `sessionGeneration`）
- **留下：** `loadAdminKnowledge` `switchKnowledgeSettingsTab` `isAdminSettingsPath`

冒烟：选组、改间隔、勾选文件夹、ACL 增删、保存、触发同步、凭证

### S3 `views/admin/knowledge.js`
`/admin/knowledge` 壳。

- `loadAdminKnowledge` `imaStoragePanelHtml` `switchKnowledgeSettingsTab` `onKnowledgeTabsKey`
- 其它页签（本地库/存储/飞书/星球）handler 仍留原处，谁渲染谁持有

冒烟：知识库设置五页签、采集未保存切换确认、存储面板入口

## 非目标
广场 / 动态 / 搜索 / 壳路由认证主题 / 懒加载 admin 模块 / 构建链

## 验收
- [ ] 三文件各自独立 commit；`check_inline_handlers.py` + `node --check` + 相关 pytest 绿
- [ ] 不 `git add -A`；不 push，除非用户明确要求
