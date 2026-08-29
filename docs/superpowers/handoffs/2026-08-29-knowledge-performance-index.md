# 知识库性能索引实施交接

## 交接对象

- 项目：`dav-subscription`，远程 `https://github.com/icekale/vpush.git`
- 主工作区：`/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription`
- 功能工作树：`/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.worktrees/knowledge-performance-index`
- 功能分支：`feat/knowledge-performance-index`
- 当前功能工作树 HEAD：`cc9cc67 fix: align IMA index date ordering`
- 当前主工作区 HEAD：`448247d docs: plan knowledge performance index`

新 agent 应在功能工作树继续，不能在主工作区 `main` 上直接实现功能。

## 用户目标

执行已确认的“知识库加载性能与查询索引”方案：

1. 用可重建的 SQLite 读模型替代 `/knowledge` 每次解析大型 `manifest.json` / `state.json`。
2. 保留 `manifest.json` 和 `state.json` 作为权威恢复输入，任何索引失败都不能损坏或删除它们。
3. 搜索覆盖标题、资料源、标签和摘要，不搜索 PDF 全文。
4. 使用普通 SQLite 表和 B-tree 索引，不引入 FTS5、Elasticsearch、Meilisearch、Redis 或新服务。
5. 采集状态按数量/时间批量落盘，同时增量更新读模型。
6. `/api/me` 认证语义不变；认证完成后 catalog 和首屏 documents 并行加载。
7. 保持现有 ACL、详情歧义、归档路径授权、手机端行为和存储 puller 单次原子下载语义。

完整实施计划：

`docs/superpowers/plans/2026-08-29-knowledge-performance-index.md`

规格：

`docs/superpowers/specs/2026-08-29-knowledge-performance-index-design.md`

## 已完成提交

按顺序：

- `448247d docs: plan knowledge performance index`
- `a916fde docs: design knowledge performance index`
- `b67f0fa feat: add IMA document read model`
- `cc9cc67 fix: align IMA index date ordering`

`b67f0fa` 和 `cc9cc67` 只实现了 Task 1 的数据库部分；Task 1 尚未通过最终规格审查。

## 当前未提交状态

功能工作树当前有未提交修改：

```text
 M app/db.py
 M tests/test_db.py
```

这些修改来自一次被中止的 Task 1 迁移修复，不能 reset、checkout、stash 或删除。先阅读：

```bash
cd "/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.worktrees/knowledge-performance-index"
git status -sb
git diff -- app/db.py tests/test_db.py
```

当前未提交修改已经尝试：

- 将 IMA 表定义从总 `SCHEMA` 中拆出。
- 在 `_migrate()` 中先执行 `_ensure_ima_document_tables()`，再执行 `_migrate_ima_document_index()`。
- 将文档 `valid_day` 改为 `INTEGER`，四位日期为 `1`，未知日期为 `0`。
- 将 `day` 默认值改为 `'unknown'`。
- 将 meta `version` 默认值/fallback 改为 `1`。
- 修正 latest/group-latest 索引列顺序。
- 尝试对完整旧 schema 做校验，并从缺字段旧表迁移可保留数据。

上述修改尚未被测试或审查确认，必须继续验证。

## 已知基线

在 Task 1 开始前，相关回归测试为：

```text
541 passed, 22307 warnings in 14.21s
```

范围包括：

- `tests/test_db.py`
- `tests/test_ima_documents.py`
- `tests/test_ima_kb.py`
- `tests/test_frontend_interactions.py`
- `tests/test_ima_puller.py`
- `tests/test_ima_storage.py`
- `tests/test_ima_storage_ops.py`

`cc9cc67` 提交时实现代理报告：

- Task 1 targeted：`4 passed, 28 deselected`
- 完整 `tests/test_db.py`：`32 passed`
- `ruff` 通过
- `git diff --check` 通过

这些结果是在当前未提交迁移修复之前/之外得到的；迁移修复完成后必须重新运行。

功能工作树没有自己的 `.venv`。使用主工作区已经存在的环境：

```bash
PYTHONPATH=. "/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.venv/bin/pytest" -q ...
"/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.venv/bin/ruff" check ...
```

## Task 1 阻塞点

上一次规格审查结论为不通过，具体问题如下。

### 1. 迁移顺序必须先于依赖索引创建

旧实现的 `DB._open_unlocked()` 先执行完整 `SCHEMA`，而 `SCHEMA` 中的
`CREATE INDEX idx_ima_doc_latest ... valid_day` 会在旧表缺少 `valid_day` 时直接失败，导致永远进入不了 `_migrate_ima_document_index()`。

当前未提交改动把 IMA 表定义和依赖索引移出总 `SCHEMA`，并尝试在 `_migrate()` 中先建表/迁移、后建索引。新 agent 必须证明：

- 新数据库能启动。
- 正确的新 schema 能重复启动。
- 旧的缺 `valid_day` schema 能启动并迁移。
- 旧表缺任意新增字段时能启动并保留可迁移数据。
- 迁移不会在创建依赖索引前引用不存在的列。

### 2. 旧 schema 校验必须完整

不能只检查 `day` 默认值、`valid_day` 类型或 meta `version`。必须校验：

- `ima_document_index` 全部字段顺序、SQLite 类型、`NOT NULL`、默认值、`(group_id, media_id)` 主键顺序。
- `ima_document_tags` 全部字段、`NOT NULL` 和 `(group_id, media_id, tag)` 主键顺序。
- `ima_document_index_meta` 全部字段、`version DEFAULT 1`、`id INTEGER PRIMARY KEY` 和 `CHECK (id = 1)`。
- 四个命名索引存在且列顺序正确；latest 两个索引的日期/名称列为降序。

如果表字段齐全但主键/约束错误，也必须重建，而不是继续使用错误结构。

### 3. 旧数据迁移必须允许缺字段

旧表迁移 SQL 不能无条件 `SELECT` 不存在的列。对每列使用“旧列存在则转换，否则安全默认值”的表达式；对无法恢复的新增字段填默认值；对重复主键选择确定性保留策略。迁移失败必须在同一事务内回滚，不得留下半迁移表。

meta 旧表可能有多行，迁移为合法单行；优先保留 `id = 1` 的记录，否则按确定性顺序保留一条。

### 4. 必须补真正的旧 schema 回归测试

至少增加这些测试，不要只测试新 DB：

- 手工创建缺 `valid_day` 的旧文档表，初始化 `DB` 后启动成功、旧行仍在、字段类型正确。
- 手工创建缺多个字段的旧文档表，初始化成功、已有字段数据保留、新字段为默认值。
- 手工创建错误主键/约束的 tags 或 meta 表，初始化后结构修复。
- 手工创建多行 meta，初始化后只保留一行。
- 使用 `PRAGMA index_info` / `PRAGMA index_xinfo` 检查四个索引列顺序和 DESC 方向。
- 迁移中注入异常时，旧表/旧 meta 不被破坏。

## Task 1 完成判定

必须满足以下条件才可标记 Task 1 完成：

1. 上述阻塞点都已修复。
2. 先运行 targeted 测试，再运行完整 `tests/test_db.py`、ruff、`git diff --check`。
3. 对 Task 1 做一次独立规格审查，审查结果必须为 `APPROVED`，没有 Critical/Important finding。
4. 再做一次独立代码质量审查；审查问题必须修复并重新审查。
5. 提交 Task 1 修复，提交信息可用：`fix: harden IMA index migration`；不要把后续 Task 代码混入该提交。

## 后续任务顺序

Task 1 通过后按计划顺序执行，不能跳过审查：

### Task 2：SQLite 查询语义

修改 `app/db.py`、`tests/test_db.py`：

- `ima_document_page()`：最新流、分库、日期、标签、搜索、分页、facets、ACL group 过滤。
- `ima_document_catalog_stats()`：catalog 统计和首项。
- `ima_document_from_index()`：详情和重复 media ID 歧义。
- `ima_document_index_count()`。
- literal `%` / `_` / `\\` LIKE 转义，并加 `ESCAPE '\\'`。
- 搜索权重：标题 3、元数据/资料源 2、摘要 1；再按有效日期、日期、标题排序。
- 保持 `unknown` 日期在有效日期之后。

### Task 3：服务重建、指纹和 JSON 回退

修改 `app/ima_documents.py`、`tests/test_ima_documents.py`：

- manifest/state 到 SQLite 行的 projection。
- `IMA_INDEX_VERSION = 1` 和基于文件 mtime/size 的 source fingerprint。
- 后台/启动重建，先内存生成，再单事务替换。
- 成功前后更新 meta；失败保留旧索引并返回安全错误。
- `ready`、`rebuilding`、`failed` 有旧行时继续读旧索引；`fallback` 或没有可用索引才读 JSON。
- 空数据源可以是 fingerprint 匹配的 `ready`，不能只用 row count 判断有效性。
- API route 不应各自实现 fallback 分支。

### Task 4：批量保存状态和增量索引

修改 `app/ima_documents.py`、`tests/test_ima_documents.py`：

- 每 `20` 条或 `2` 秒 flush。
- group 完成、取消、异常、停止、cleanup 都必须 final flush。
- JSON `save_state()` 必须先于 SQLite batch update。
- listing 成功后才替换 group rows；listing 失败保留旧组。
- 翻译和标签写入也保持 JSON-first，再更新 SQLite。
- storage puller 仍然单次原子下载，不能把 retry 逻辑移到 puller。

### Task 5：切换 API

修改 `app/api.py`、`app/ima_kb.py`、`tests/test_ima_kb.py`：

- catalog/list/detail/PDF/TXT 都经 `ImaDocumentService` 统一读边界。
- indexed path 不得再次解析 manifest/state。
- JSON fallback 仍可用。
- 保持 `/api/me`、ACL、订阅用户/管理员/外部用户行为。
- 归档路径仍必须经过授权检查和 `Path.is_file()`，不能信任任意 SQLite 路径。
- catalog 使用 `attach_catalog_summary()` 合并预计算统计；JSON fallback 保留原 `attach_catalog_stats()`。

### Task 6：前端首屏并行

修改 `app/static/app.js`、`app/static/index.html`、`app/static/sw.js`、`tests/test_frontend_interactions.py`：

- `/api/me` 语义不变。
- 认证后同时发起 catalog 和首屏 documents。
- 使用 `Promise.allSettled` 隔离 catalog/list 失败。
- 失败时保留现有 retry/phone-blocked/read-return 行为。
- 管理员状态显示索引 rebuilding/fallback/failed；普通知识库页面不显示内部状态。
- 按计划版本递增静态资源 cache bust，不能随意改 CSS 版本。

### Task 7：基准和完整回归

新增 `scripts/benchmark_ima_knowledge.py`，修改测试：

- 读取 `VPUSH_TOKEN` 和可选 `VPUSH_BASE_URL`。
- 先从 catalog 自动选第一个 subscribed group，不能写死 group ID。
- 每路由 20 次，消费完整 response body，打印 min/median/p95/max。
- 不打印 token、Authorization header 或密码。
- 运行相关 pytest、ruff、`node --check`、`git diff --check` 和浏览器回归。

### Task 8：发布和生产验收

仅在前面所有任务和审查通过后执行：

- 读取并遵守 `vpush-vps-deploy` 技能。
- 版本号不能复用已有 tag。
- 发布 amd64 镜像，只等待 `publish-amd64`。
- 部署前备份 `/opt/vpush/data/dav.db` 到 backups。
- 只重建 `vpush`，不要误动其它容器。
- 验证 `/healthz`、版本、容器健康、index status、文档数、catalog/list/detail/PDF。
- loopback API p95 目标：catalog <200ms，latest list <300ms，采集期间 latest list <750ms。
- 外部 Chrome 单独验证缓存静态资源后的知识库可用时间 <1.5s。
- 不在 IMA/NFS 工作期间调 TCP。

## 不得提交的内容

不要提交或恢复这些与本任务无关的文件：

- `.cursor/`
- `work/`
- `scripts/ima_probe.py`、`scripts/ima_web_probe.py` 以及其它 probe/临时脚本
- `config.demo.yaml`
- `docs/research/`
- 主工作区其他未跟踪文件

当前功能工作树的 handoff/prompt 文档如果已单独提交，不要把主工作区的同名文件重复加入。

## 交接后的第一组命令

```bash
cd "/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.worktrees/knowledge-performance-index"
git status -sb
git diff --check
PYTHONPATH=. "/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.venv/bin/pytest" -q tests/test_db.py
"/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.venv/bin/ruff" check app/db.py tests/test_db.py
```

如果迁移测试失败，先按“Task 1 阻塞点”修复，不能继续 Task 2。

## 安全和生产上下文

- Unraid `192.168.5.28` 仅测试，不是生产。
- 生产主 VPS：`root@179.255.150.134`；存储 VPS：`root@198.12.125.212`。
- SSH 保持端口 22、key-only；恢复 key 仍是 `/Volumes/main/存储VPS-SSH/id_ed25519_ima-storage`。
- 任何 token/key/password 只通过环境变量或容器内临时进程传递，不能写入日志或交接文档。
- storage puller：`vpush-ima-puller.service`，`10.80.0.2:8743`，单次原子下载；main collector 才拥有有界重试。
- production archive：`/data/ima-archive`；manifest/state：`/data/ima/manifest.json`、`/data/ima/state.json`。
