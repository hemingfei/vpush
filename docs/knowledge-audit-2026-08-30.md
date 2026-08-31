# 知识库与知识库设置 全量审计报告（前后端）

日期：2026-08-30 · 基线：main f58271c（v1.12.94）· 方式：双 agent 独立通读 + 关键疑点脚本复现（零改动）

范围：后端 `app/ima_documents.py`（3,695 行）+ `app/api.py` 知识库 25 条路由 + `app/db.py` ima 表/ACL + 调度集成；前端 `app/static/app.js`（11,232 行）知识库与知识库设置全部区块 + index.html + sw.js + style.css。

## 总评

- **P0：无。** 后端鉴权/ACL 在 25 条路由逐条双重收敛（路由层 + SQL `IN` 收敛）、路径 confinement 与 symlink 防护逐层到位；前端外部内容转义纪律良好，PDF 走 Bearer+blob 无 query token 泄漏，未发现可远程利用的 XSS。
- **P1：7 条**（后端 3 / 前端 4）。后端 3 条全部脚本一分钟复现，病根相同——「多条写路径各自为政」；前端 4 条集中在最年轻的本地库页签。
- **P2：30 条**（后端 17 / 前端 13），以健壮性与死代码为主。

## P1（建议一批修掉，均小改动）

### 后端

| # | 位置 | 问题 | 修法 |
|---|------|------|------|
| B1 | `ima_documents.py:2121-2125,3144,3149-3180` | **标记 JSON 损坏 → 整库索引被静默清空**（管理页无报错）。与 docstring 及 OSError 分支语义自相矛盾；NFS 截断/非原子编辑即可触发 | JSONDecodeError 分支改为与不可读分支一致：返回带 error 的 entry，让 prune 保住该组 |
| B2 | `ima_documents.py:3396-3403→3458` | **增量同步把「-副本」重复行写回读模型**（计数/facets 虚增，违反性能规格 §10.1 两路径一致；重启才收敛） | `_replace_group_index` 建行前套用与 `_normalize_manifest_records` 相同的组内 stem 去重 |
| B3 | `ima_documents.py:3129-3133,1719-1735` | **每次重扫清空索引 abstract_zh 翻译缓存**（state.json 还在，仅内存 dict 没回填）；当前被中文摘要掩盖，遇非中文摘要会反复重译 | `_save_state_locked` 将 merged 原地写回传入 state，或扫描路径字段级合并 |

### 前端

| # | 位置 | 问题 | 修法 |
|---|------|------|------|
| F1 | `app.js:7187-7188` | 本地库卡片内联 onclick 字符串插值 slug——存储机可写者建恶意目录名即可在管理员页面注入 JS（利用前提高，模式性问题） | 改 `data-slug` + addEventListener，全仓同类模式统一 |
| F2 | `app.js:7082-7088,7194-7251` | 本地库页 15s 轮询重渲染击穿「扫描中」状态：5 分钟 NFS 首扫期间按钮复活可点，只反复吃 409 | 模块级 `_scanInFlight` 标志驱动渲染 |
| F3 | `app.js:1606-1618,1654` | 阅读器上一份/下一份用未校验路由的旧快照，深链时跳到无关文档 | 渲染 nav 前做与 `currentImaListSnapshot` 相同的 route 校验 |
| F4 | `app.js:1277-1285` | 非管理员零订阅时双空态堆叠 | 合并为一个空态 |

## P2 摘要（详情见两份原始报告）

**后端 17 条**，最值得先做：扫描/建库端点同步全库扫描（生产 5k PDF × 63ms ≈ 10 分钟占住 HTTP 与 `_sync_lock`，应后台化）；`os.walk` 无 onerror（NFS 抖动静默清空索引，与 B1 反向同型）；enabled/改名写回与进行中扫描的丢失更新竞态；无 IMA 凭证时调度搭车扫描不触发（纯本地部署落空）；translate 端点无节流（全量读写 13MB state + 共享翻译配额）；query token 进反代日志/历史（30 天有效，建议短时签名）；sidecar tags 未按规格 §11 裁 ≤5；改名后 group_name 滞后；ValueError 一律 404（name 非法应 400）；停用组 SQLite/state 孤儿行；failed 状态不自愈；stop() 无取消点；启动 17 分钟 NFS stat 风暴；PDF 2.0 魔数误判；死代码两处。

**前端 13 条**：死代码一批（`syncImaListChrome`/`toggleImaDocumentsFilters`/`imaDocumentGroupControls`/`searchImaDocuments`/`openKnowledgeLatest`/`closeImaPdf` 等约 3-5% 代码量，连同只写不读的 `_imaOffset`/`imaDocumentsLastDay` 一起清）；cicc 轮询不随路由停止、重置 `<details>` 开合；`loadImaPdf` 无 AbortController；401 硬登出丢路由（已知取舍）；编辑保存双端点非原子（提示「可能已部分保存」）；与后端中文文案字符串耦合（应按 status 判断）；offset 分页漂移（研报场景影响小）；`/text` 端点+CSS 半接线无入口。

## 测试缺口（修 P1 时一并补，防回归）

1. 「先成功扫描→标记损坏→重扫」prune 保组用例（B1）
2. `_sync_group` 增量组替换的去重用例（B2；现测只测 rebuild 路径）
3. 「重扫后索引 abstract_zh 保持」用例（B3）

## 正向确认（审计过的亮点）

后端：路径防护逐层拒绝（resolve+is_relative_to+symlink 全覆盖）、`_like_pattern` 转义、`_safe_error` 脱敏、禁用库全链路不可见且 ACL 保留、`local-` 前缀隔离在 discovery/写配置/restore/purge/rebuild 全生效。前端：三层竞态序号（route/list/reader）、阅读返回快照（滚动+焦点）、catalog 失败降级用列表 groups+警示条、SW `/api/` 永不缓存且版本断言一致、深色模式全 token 化。性能规格 §7 前端加载链路逐条吻合。

## 追加审计：水印/压缩批次落地验收（2026-08-30 晚）

对并行会话「PDF 水印去除与压缩」计划完成后的全量验收：

- **水印清零（全量验证非抽样）**：4,956/4,956 残留 0（wm_verify_all.py 逐文件检查 WM 尺寸图流）。全站压缩回刷完成（16,628 断点闭环）。
- **排序方案再进化（好评）**：a0a7ed7 把 IMA sort_date 的年份从「当前年补全」改为媒体创建时间 ts——修掉了原方案在跨年时会把历史文档排错的隐患；v4 重建；前端日期非当年才带年份。
- **审计 P2 跟进**：2bcd187 零 IO 快路径根治了启动期 NFS stat 风暴（该问题曾致全站接口 40-80 倍减速）；用户报的两个 UI 问题（返回标签/摘要挤压）已由 267716a 重构与 v1.12.97 的 is-clamped+展开方案解决。
- **部署一致性**：生产 v1.12.97，容器 app.js 与仓库 md5 一致；`?v=` cache-bust URL 内容正确。注意：无查询串的 `/app.js` 在 CF 有 7 天旧缓存（对用户无影响，HTML 恒带 ?v=）。
- **发现 1（设计内）**：每日 00:30 增量 timer 在 8/30 被年度回补占用而跳过，8/30 当天研报缺位；8/31 00:30 自动补采，无需人工。
- **发现 2（流程风险，建议修）**：v1.12.95 发版提交带了过期工作副本，覆盖了 d77ca9a 的两个前端修复（本次无害——被更优方案取代，属侥幸）。建议：发版提交必须基于 `git pull` 后的干净树；可在 CI 加关键标记断言防止复发。**已修复（3086d63，已推 main）**：新增 `tests/test_release_guards.py` 哨兵断言（12 项关键修复指纹：审计 F1/F2/B2、本地库扫描器、跨年排序、去水印管道、摘要钳制、预览区高度等），docker-publish.yml 的 test job 失败即镜像不发布；修复被有意取代时按文件内维护约定更新标记。
- **卫生项（可选）**：VPS `/root/cicc/` 多份 state 备份与日志、repo 内已合并的 8 个 worktree、WM 验证脚本可按需清理。
