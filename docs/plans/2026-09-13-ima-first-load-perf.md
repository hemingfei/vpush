# 研报中心首载性能：四项优化 + 验收

日期：2026-09-13　基线版本：v1.12.186

## 背景（已实测，生产数据）

| 环节 | 现状 | 证据 |
| --- | --- | --- |
| `/api/me` 服务端 | 0–16ms（10 次），日志典型 4ms | 冻结快照实测 |
| `GET /api/ima-documents?limit=50` | **冷页缓存 6.5 / 7.5 / 9.2 / 11.8s**；热 0.25–1.5s | `/tmp/measure` 冻结快照 + `posix_fadvise(DONTNEED)` |
| `GET /api/ima-documents/catalog` | 冷 23–35ms，热 0.2–2ms | 同上 |
| 列表响应体 | 231KB → gz 77KB（50 条） | 同上 |
| 首屏 JS（app.js 静态导入闭包） | **188.2KB gz / 20 文件**，其中 `views/admin/*.js` 9 个 **73.4KB gz** | 本机按模块图递归 gzip |
| 首屏 CSS | 34.4KB gz（style.css 192KB raw） | 同上 |

预取修复（d699b55，v1.12.185）已把 `/api/me` 往返移出关键路径，省 1×RTT（50–300ms）；本次四项针对剩余的秒级瓶颈。

冷态慢的根因链：

- `app/db.py:5287-5294` `ima_document_page()` 的列表查询
  `SELECT d.*, {rank_sql} AS match_rank ... ORDER BY match_rank DESC, (d.sort_date = '') ASC, d.sort_date DESC, d.name DESC LIMIT ? OFFSET ?`
- 无搜索词时 `rank_sql = "0"`（`app/db.py:5232`），`match_rank` 是常量却排在排序键首位，索引永远无法满足排序。
- `EXPLAIN QUERY PLAN`（冻结快照 37,478 行）：
  - 现状多组：`SEARCH d USING INDEX sqlite_autoindex_ima_document_index_1 (group_id=?)` + `USE TEMP B-TREE FOR ORDER BY`
  - 单组且保留 `match_rank` 排序：**仍然** `USE TEMP B-TREE FOR ORDER BY`（被常量首键挡住）
  - 单组且去掉 `match_rank`：`SEARCH d USING INDEX idx_ima_doc_group_latest (group_id=?)`，**无排序步骤**
  - 多组且去掉 `match_rank`：仍 `USE TEMP B-TREE FOR ORDER BY`（SQLite 不合并多个 IN 索引扫描）
- 生产索引：`idx_ima_doc_downloaded`、`idx_ima_doc_group_latest(group_id, sort_date DESC, name DESC)`、`idx_ima_doc_latest(sort_date DESC, name DESC)`、`sqlite_autoindex_ima_document_index_1`（唯一索引，被当作覆盖索引全扫 106MB）。
- `sort_date` 不变式：非空值全部符合 `^\d{4}-\d{2}-\d{2}$`（全库 0 例外），空值 66 行 → DESC 时空串自然沉底，`(d.sort_date = '') ASC` 冗余。
- 页缓存冷 + `sqlite3.cache_size` 2000 页（8MB）时，这次排序要读完整覆盖索引 → 6.5–11.8s。

## 验收指标（全部需在验收阶段给出实测数字）

1. 冻结快照冷页缓存下，默认列表查询（全组、limit=50、offset=0）：**P50 < 150ms**（现状 6.5–11.8s），`EXPLAIN QUERY PLAN` 无 `TEMP B-TREE FOR ORDER BY`。
2. 首屏 JS 静态闭包：**≤ 120KB gz**（现状 188.2KB）。
3. `/api/ima-documents?limit=50` 响应体：**≤ 120KB**（现状 231KB），详情接口字段不缩水。
4. 全量 `pytest -q` 绿（基线 2194 passed），CI 绿，VPS 部署 v1.12.187 后容器 healthy、`/healthz` ok、md5 与 tag 一致。
5. 交付可复跑的基准脚本（`scripts/ima_page_bench.py`），任何人可在 VPS 上重放冷/热数字。

## Phase 1 排序治本（最大收益）

文件：`app/db.py`（`ima_document_page()` 5256-5360 区域、`_ima_page_filters()` 5181+），新增 `tests/test_db.py` 用例。

改动：

1. 无搜索词（`rank_sql` 为常量 `"0"`、`requested_query` 为空）时：
   - 去掉 `match_rank` 与 `(d.sort_date = '')` 两个排序键，只留 `d.sort_date DESC, d.name DESC`（附注释说明 `sort_date` 格式不变式）。
   - 按组切片合并：`SELECT ... WHERE d.group_id = ? AND <filters> ORDER BY d.sort_date DESC, d.name DESC LIMIT ?` 每组 UNION ALL，内层 LIMIT 取 `offset + limit + 1`，外层再 `ORDER BY d.sort_date DESC, d.name DESC LIMIT ? OFFSET ?`。
   - 单组（`len(groups) == 1`）走同一条路径即可，无需特例。
2. 有搜索词时保持现有 SQL（rank 参与排序，扫全库不可避免，风险为零）。
3. 分面查询（`COUNT(*)` / `GROUP BY group_id` / days / tags）不变，仍用 `where_sql`。

测试（TDD）：

- 先写失败用例：`EXPLAIN QUERY PLAN` 断言默认列表查询不出现 `TEMP B-TREE FOR ORDER BY` 且命中 `idx_ima_doc_group_latest`。
- 等价性矩阵：同一 fixture 数据下，新查询与旧 SQL（测试内保留旧实现副本作为基准）在 `q/day/tag/rating/ticker/group/offset/limit` 组合下返回完全相同的 `(group_id, media_id)` 序列与 `has_more`。
- 边角：空 `sort_date` 沉底、`offset` 超过总数、组内不足 `limit` 时的跨组补齐。

提交：`perf(db): 研报列表按组索引切片排序，去掉常量排序键`

## Phase 2 启动预热

文件：`app/main.py`（`create_app()` 87 行附近）、`app/db.py`（新增只读预热函数），测试 `tests/test_db.py` 或 `tests/test_api.py`。

改动：

- `warm_ima_document_page(limit=50)`：对可读组最多的前 N 个用户（或直接对 `_configured_groups()`）跑一次 Phase 1 的页面查询，纯读、异常只 `logger.warning`。
- 启动后在守护线程里跑（`threading.Thread(..., daemon=True)`，可延后 1–2 秒），不阻塞启动、失败不影响主流程；用环境变量/配置开关短路，测试里默认不启动（避免测试进程多线程）。
- 只有 `ima_documents` 启用时才预热。

测试：直接调用预热函数：断言执行了一次查询、空库不抛错、开关关闭时不执行。

提交：`perf(startup): 启动后后台预热研报列表页缓存`

## Phase 3 列表响应体瘦身

文件：`app/db.py`（`_ima_public_document()` 595-621）、`app/static/views/ima.js`（若需同步）、测试 `tests/test_db.py`。

步骤：

1. 先在冻结快照上量字段组成（`SELECT SUM(LENGTH(...))` 覆盖 17 个字段 × 最重的 3 组 × 最新 50 行），把结论写进提交信息。
2. 按实测裁剪：`abstract`/`abstract_zh` 截断到首屏片段所需长度（前端只需 snippet，见 `app/static/views/ima.js:392` 与 1327/1393），`abstract_src_hash`/`pdf_path`/`txt_path` 从列表移除（详情由 `/api/ima-documents/{media_id}` 返回，字段不变）。
3. 前端同步：只改真正引用了被移除字段的地方；`limit` 保持 50（改小属于 UX 变更，需用户单独确认）。

测试：断言列表项字段集合与单条长度预算；断言详情接口仍含 `pdf_path`/`txt_path`。

提交：`perf(api): 研报列表响应体裁剪`

## Phase 4 admin 视图懒加载

文件：`app/static/app.js`、`app/static/views/admin/*.js`（不改内容）、`tests/test_frontend_interactions.py`、`app/static/index.html` + `app/static/sw.js`（摘要同步）。

现状：`app/static/app.js:61-72` 静态导入 9 个 admin 视图模块；工厂在模块顶层即调用（5287、6229、6264、6308、6357、6398、6456、6492、6541）；`ciccView` 还被顶层函数引用（343、5303、5313、5328、5330）。

改动：

- 删除 9 条 `views/admin/*.js` 静态导入；新增 `ensureAdminViews()`：`await Promise.all([import("./views/admin/codes.js"), ...])` 后创建各视图对象，结果存入 `let` 变量，重复调用复用同一 Promise。
- `router()` 的 `page === "admin"` 分支在渲染前 `await ensureAdminViews()`。
- 顶层引用 `ciccView` 的调用点改为「未加载则跳过/按需 `await`」，避免初始化顺序耦合。
- 保留 `views/news.js`、`views/ima.js`、`views/market.js`、`views/feishu-personal.js`、`views/push-settings.js` 静态导入（研报/动态首屏要用）。

测试：`tests/test_frontend_interactions.py` 新增规则——`app.js` 不得静态导入 `./views/admin/`；`node --check`；`python -m scripts.bump_assets --sync` 更新 `index.html`/`sw.js` 摘要。

提交：`perf(web): admin 视图改动态导入，首屏少 73KB gz`

## Phase 5 验收

1. 全量 `.venv/bin/python -m pytest -q`（基线 2194 passed）+ `node --check app/static/app.js`。
2. 冷/热基准：VPS 冻结快照 `/tmp/measure/dav.db`（去掉我遗留的 `bench_list_idx`），用 `scripts/ima_page_bench.py` 的 `posix_fadvise(DONTNEED)` 造冷，跑容器内 `python3`，对照 6.5/7.5/9.2/11.8s。
3. 首屏字节：重跑模块图 gzip 统计，对照 188.2KB / 73.4KB。
4. 响应体：同一 harness 量 `/api/ima-documents` 的 JSON 字节，对照 231KB / 77KB gz。
5. 发版 v1.12.187：`git push` main + tag + Release → VPS 备份 `data/backups/dav.db.<ts>` → `git clone --depth 1 --branch v1.12.187` → `docker build` → `docker compose up -d --no-build vpush` → 容器 healthy、`APP_VERSION`、`/healthz`、`app.js`/`version.py` md5 对齐。
6. 清理 VPS：`/tmp/measure`、`/tmp/vpush-v1.12.187`、临时脚本。
7. 出验收报告：改前/改后数字表 + 未做项 + 回滚命令。

## 风险与回滚

- Phase 1 改动直接影响列表内容顺序，等价性测试是硬门槛；若等价性无法满足，退回「保留 `(sort_date='')` 但去掉 `match_rank`」的中间方案（单组可走索引，多组仍排序）。
- Phase 2 预热只读；若观察到启动竞争，直接把开关置 0。
- Phase 3 若前端某处理需要被移除字段，保留该字段并只截断长文本。
- Phase 4 风险最高（首屏与后台路由初始化顺序），失败即回滚单次提交。
- 回滚命令：`cd /opt/vpush && docker tag icekale/vpush:v1.12.186 dav-subscription-vpush:latest && docker compose up -d --no-build vpush`
