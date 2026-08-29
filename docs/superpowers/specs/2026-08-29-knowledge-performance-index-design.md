# 知识库加载性能与查询索引设计

> 状态：已确认
> 日期：2026-08-29
> 关联：`2026-08-29-knowledge-report-first-redesign.md`

## 1. 目标

把 `/knowledge` 从串行读取大型 JSON 的慢路径改成 SQLite 查询路径，同时保留现有 manifest/state 作为采集与恢复来源。

本轮完成三件事：

1. 消除首屏 `/api/me -> catalog -> documents` 的串行瀑布。
2. 建立可重建的 SQLite 文档读取模型，服务最新流、分库、日期、标签、搜索和阅读详情。
3. 将采集状态从每份 PDF 重写整个 `state.json` 改为限时限量批量落盘，并同步批量更新读取模型。

搜索范围保持现有语义：标题、资料源、标签和摘要。不索引 PDF 全文。

## 2. 现状与基线

2026-08-29 生产数据：

- `manifest.json`：22.47 MiB，16,394 条。
- `state.json`：13.02 MiB，16,503 条。
- `/api/me`：约 0.17 秒。
- `/api/ima-documents/catalog`：约 1–5 秒。
- `/api/ima-documents?limit=50&offset=0`：约 3–17 秒，常见约 9–10 秒。
- `app.js` gzip 后约 127 KiB，CSS gzip 后约 27 KiB；静态资源不是主要瓶颈。

当前一次列表请求分别调用 `document_facets()`、`documents()` 和 `group_summary()`，重复解析 manifest 三次、state 两次，并对全部文档排序后才截取前 50 条。

一次性“manifest/state 各读一次、单次扫描、`heapq.nlargest(50)`”生产数据基准为 0.8–1.1 秒。将同一批数据写入 SQLite 后：

- 最新 50 条：低于 0.2 ms。
- 中文子串搜索：约 3–4 ms。
- FTS5 trigram 构建约 2.8 秒，且 `AI` 等两字符查询不能直接命中。

因此本轮使用 SQLite 普通表和 B-tree 索引，不引入 FTS5。

## 3. 架构边界

### 3.1 主数据源

`manifest.json` 和 `state.json` 继续作为采集结果与恢复来源。远程 PDF/TXT 归档路径保持不变。

SQLite 文档表是 **可重建读取模型**：

- 页面和 API 正常情况下只读 SQLite。
- 索引缺失、版本不匹配或重建失败时，接口回退现有 JSON 查询路径。
- 索引损坏不得影响采集、PDF 文件或 manifest/state。

### 3.2 不增加独立服务

不引入 Elasticsearch、Meilisearch、Typesense、Redis 或新的容器。继续复用现有 `dav.db`、SQLite 事务和部署方式。

## 4. SQLite 读取模型

### 4.1 `ima_document_index`

每个知识库内的每份文档一行，主键为 `(group_id, media_id)`。

字段至少包括：

- `group_id`
- `media_id`
- `day`
- `name`
- `group_name`
- `name_folded`
- `metadata_folded`：资料源与标签的规范化搜索文本
- `abstract`
- `abstract_folded`
- `tags_json`
- `size`
- `chars`
- `has_pdf`
- `has_txt`
- `pdf_path`
- `txt_path`
- `downloaded_at`

索引：

- `(day DESC, name DESC)`：全部知识库最新流。
- `(group_id, day DESC, name DESC)`：单库最新流与日期浏览。
- 唯一主键同时服务文档详情定位。

`unknown` 日期排在有效 `MMDD` 日期之后，保持现有产品规则。

### 4.2 `ima_document_tags`

标签单独规范化，主键为 `(group_id, media_id, tag)`，并建立：

- `(tag, group_id)`
- `(group_id, tag)`

该表用于标签筛选、标签计数和 catalog facets，避免每次解析 `tags_json`。

### 4.3 搜索语义

查询词先 `strip + casefold`。SQL 对下列字段执行子串匹配：

1. `name_folded`：相关性 3。
2. `metadata_folded`：相关性 2。
3. `abstract_folded`：相关性 1。

排序为相关性降序、有效日期优先、日期降序、标题降序。空查询按日期最新流排序。

SQL `LIKE` 查询必须转义 `%`、`_` 和转义符，使用户输入保持字面含义。两字符中文、股票代码和 `AI` 等短词必须正常工作。

## 5. 索引写入与一致性

### 5.1 组清单更新

每个知识库完成目录枚举后，在一个 SQLite 事务中：

1. 将该组 manifest 记录与当前 state 合成读取行。
2. upsert `ima_document_index`。
3. 重建该组 `ima_document_tags`。
4. 删除该组已经不在 manifest 中的文档和标签。

一组失败不得清空旧索引；继续保留最后一次成功结果。

### 5.2 下载进度更新

PDF 下载成功后先更新内存 state，不再每份文件重写 13 MiB JSON。

满足任一条件时 flush：

- 累计 20 份状态变化。
- 距上次 flush 达到 2 秒。
- 当前组结束、取消、服务停止或异常退出清理。

一次 flush 的顺序：

1. 原子写入 `state.json` 临时文件并 `os.replace`。
2. 单个 SQLite 事务批量更新受影响文档的 PDF/TXT 状态、大小、时间和标签。
3. 记录本次 manifest/state 指纹。

若进程在 JSON 成功、SQLite 提交前退出，启动时通过指纹不一致触发重建。读取模型允许短暂落后，不允许领先于尚未落盘的 state。

### 5.3 重建

启动时比较读取模型版本与 manifest/state 的 `mtime_ns + size` 指纹：

- 一致：直接使用索引。
- 不一致且存在旧索引：继续服务旧索引，在后台事务重建。
- 索引为空：API 暂时回退 JSON，后台重建。
- 重建失败：保留旧索引或 JSON 回退，记录明确错误，不替换为半成品。

重建行先在内存中完整生成，再在单个 SQLite 事务中删除旧行、批量插入并校验条数；校验通过才提交。任一步失败都回滚到旧索引，用户不会看到半张表。

## 6. API 查询路径

### 6.1 列表

`GET /api/ima-documents` 正常路径只查询 SQLite：

- SQL 完成 ACL 后的可读 group 限定。
- SQL 完成关键词、标签、日期、group、limit 和 offset。
- SQL 返回 days、tag counts、document count 和当前页。
- 不读取 manifest/state，不在 Python 中构建并排序全部文档。

### 6.2 Catalog

`GET /api/ima-documents/catalog` 使用 SQLite `GROUP BY group_id` 计算文档数和最新文档；ACL/订阅仍使用现有数据库逻辑。

### 6.3 文档详情与 PDF

文档详情通过 `(group_id, media_id)` 定位。PDF/TXT 路径来自索引列，但仍经过现有安全路径校验；索引值不得绕过归档根目录约束。

索引不可用时，以上接口统一回退当前 store 查询，不复制第二套回退实现。

## 7. 前端加载链路

### 7.1 首次进入

直接打开 `/knowledge`：

1. 保留 `/api/me` 身份确认。
2. 身份确认后立即挂载知识库列表骨架。
3. 并行请求 catalog 和当前路由对应的首批 50 条文档。
4. 两个请求独立落位；catalog 失败不得阻止已有文档列表显示，列表失败保留明确重试。

### 7.2 SPA 内部导航

继续保留每次 `router()` 的 `/api/me` 校验，使 token 版本、管理员权限和用户状态变化立即生效。该接口生产实测约 0.17 秒，不是本轮瓶颈，不增加用户缓存和失效规则。

身份校验完成后，catalog 与文档列表仍并行加载。现有列表快照、阅读返回、搜索防抖和分页行为保持不变。

### 7.3 静态资源

本轮不拆分 `app.js`，不改 service worker 缓存策略。只有在后端优化后冷启动仍不达标时，才单独评估路由级拆包。

## 8. 错误与可观测性

新增日志和状态：

- 索引模式：`ready`、`rebuilding`、`fallback`、`failed`。
- 最近成功重建时间、条数、耗时和错误摘要。
- API 调试日志区分 SQLite 命中与 JSON fallback。
- state flush 记录批次数、文档数和耗时；不记录 token、签名 URL 或摘要正文。

管理员知识库状态接口展示索引状态和最近重建错误，但普通用户页面不展示实现细节。

## 9. 迁移与发布

1. 数据库迁移创建读取表、标签表和索引，不删除旧文件。
2. 发布后后台重建读取模型；重建期间继续使用 JSON fallback。
3. 重建成功后自动切换 SQLite 查询。
4. 观察一轮目录同步和 PDF 下载，确认批量 state flush 与索引增量更新。
5. 保留回退开关；回滚应用版本无需转换 manifest/state。

无需停机，也不需要预先在生产手工生成索引。

## 10. 测试与验收

### 10.1 正确性

- 最新流、分库、日期、标签、搜索结果与现有 JSON 路径一致。
- 搜索覆盖标题、资料源、标签和摘要。
- `AI`、中文两字符、股票代码以及包含 `%` / `_` 的字面查询正确。
- 相关性和日期排序与现有规则一致。
- ACL、订阅、空库、未知日期和重复 media ID 行为不变。
- stale 文档只在该组成功枚举后删除；枚举失败保留旧索引。
- 索引缺失、损坏、版本过期和重建失败均可回退。
- PDF/TXT 路径继续通过安全校验。

### 10.2 采集稳定性

- 下载成功 20 份以内或 2 秒以内会落盘。
- 组结束、取消、停止和异常清理强制 flush。
- 活跃采集期间不会每份 PDF 重写一次 state。
- JSON 写入成功但 SQLite 未提交的故障可在重启后自动修复。

### 10.3 性能目标

在当前生产数据规模和 1 核主 VPS 上，API p95 使用容器内 loopback 已认证请求测量；用户可见时间使用外部 Chrome 测量：

- `/api/ima-documents/catalog` 无采集时 p95 小于 200 ms。
- `/api/ima-documents?limit=50&offset=0` 无采集时 p95 小于 300 ms。
- 活跃采集期间文档列表 p95 小于 750 ms。
- 静态资源已缓存时，从进入 `/knowledge` 到可操作首批列表小于 1.5 秒。
- SQLite 正常路径不得调用 `load_manifest()` 或 `load_state()`。

性能测试至少运行 20 次，并分别覆盖空查询、单库、日期、标签、中文搜索和 `AI` 搜索。

### 10.4 回归

- IMA 文档、知识库 ACL、同步、存储 puller 和前端交互测试通过。
- `node --check app/static/app.js` 通过。
- Chrome 桌面浅色/深色验证首次加载、搜索、切库、加载更多、阅读返回和错误回退。
- 390px 继续显示现有知识库桌面端限制，不改变手机策略。

## 11. 非目标

- PDF 全文检索、OCR、RAG、向量数据库或语义搜索。
- FTS5、外部搜索服务或搜索结果高亮。
- 修改 PDF 存储架构、NFS/WireGuard 或存储机 puller。
- 路由级 JavaScript 拆包和 service worker 重构。
- 删除 manifest/state 或将 SQLite 变成唯一恢复来源。
