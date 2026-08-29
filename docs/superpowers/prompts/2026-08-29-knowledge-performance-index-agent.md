# 交给新 Agent 的执行提示词

你接手的是 `dav-subscription` 的“知识库加载性能与查询索引”实施工作。请严格按下面要求执行。

## 工作位置

必须在已有隔离工作树工作：

```text
/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.worktrees/knowledge-performance-index
```

分支：`feat/knowledge-performance-index`

不要在父目录的 `main` 工作区直接写功能。不要 reset、checkout、stash 或删除已有未提交修改。主工作区有用户未跟踪文件，不要触碰或提交它们。

完整交接材料：

```text
/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.worktrees/knowledge-performance-index/docs/superpowers/handoffs/2026-08-29-knowledge-performance-index.md
```

先完整阅读该文件和：

```text
docs/superpowers/plans/2026-08-29-knowledge-performance-index.md
docs/superpowers/specs/2026-08-29-knowledge-performance-index-design.md
```

## 当前状态

功能工作树当前 HEAD 是：

```text
cc9cc67 fix: align IMA index date ordering
```

已有相关提交：

```text
448247d docs: plan knowledge performance index
b67f0fa feat: add IMA document read model
cc9cc67 fix: align IMA index date ordering
```

当前有一组尚未提交、来自中止修复工作的修改：

```text
 M app/db.py
 M tests/test_db.py
```

这些修改不能删除。它们尝试修复 Task 1 的旧 schema 迁移顺序和完整校验，但尚未通过测试或审查。先检查 `git diff`，在此基础上完成修复。

## 第一优先级：完成 Task 1

Task 1 尚未通过规格审查。必须先处理这些问题，不能开始 Task 2：

1. `DB._open_unlocked()` 的总 `SCHEMA` 不能在迁移之前创建引用旧表缺失字段的 IMA 索引。先确保错误旧表可以启动并进入迁移，再创建依赖索引。
2. 完整校验 `ima_document_index` 的字段顺序、类型、NOT NULL、默认值、`(group_id, media_id)` 主键；校验 `ima_document_tags` 的字段和 `(group_id, media_id, tag)` 主键；校验 meta 的字段、`version DEFAULT 1`、`id INTEGER PRIMARY KEY` 和 `CHECK(id = 1)`。
3. 旧表缺任意字段时，迁移 SQL 只能引用实际存在的列；已有数据保留，新增字段用安全默认值，重复主键采用确定性策略。
4. meta 旧表多行时迁移成单行，优先保留 `id = 1`，否则确定性保留一行。
5. 校验四个索引的实际列顺序和方向：
   - latest：`valid_day DESC, day DESC, name DESC`
   - group latest：`group_id, valid_day DESC, day DESC, name DESC`
   - tag group：`tag, group_id` 前缀
   - group tag：`group_id, tag` 前缀
6. 增加真实 malformed schema 测试和迁移失败回滚测试。

验证命令：

```bash
cd "/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.worktrees/knowledge-performance-index"
PYTHONPATH=. "/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.venv/bin/pytest" -q tests/test_db.py
"/Users/kale/Documents/微信小程序大 v 订阅/dav-subscription/.venv/bin/ruff" check app/db.py tests/test_db.py
git diff --check
```

Task 1 必须经过独立规格审查和代码质量审查；都通过后再提交。提交只包含 `app/db.py`、`tests/test_db.py` 的 Task 1 改动，建议提交信息：

```text
fix: harden IMA index migration
```

## 后续执行规则

Task 1 通过后，严格按计划执行 Task 2 到 Task 8：

- 每个任务先写失败测试，再写最小实现，再运行 focused/full checks。
- 每个任务单独提交，不要把后续任务混入当前提交。
- 每个任务完成后先做规格合规审查，再做代码质量审查；有 Critical/Important 必须修复并重新审查。
- 保持 `manifest.json` / `state.json` 为权威来源；SQLite 只是可重建读模型。
- 不引入 FTS5、Elasticsearch、Meilisearch、Redis、新服务或新依赖。
- 不要求 FakeDB 立即实现新索引 API；用 `getattr`/能力检测维持旧测试兼容。
- 归档读取仍必须经过 ACL、授权路径检查和 `Path.is_file()`。
- JSON `save_state()` 永远先于 SQLite 增量写入。
- storage puller 永远单次原子下载，重试只在 main collector。

## Task 2-8 的核心验收

### Task 2

实现 SQLite 分页、最新流、分组、日期、标签、搜索、catalog stats、详情查询。搜索字段为标题、资料源/元数据、标签、摘要；权重标题 3、元数据 2、摘要 1；支持中文短词、`AI`、股票代码和 literal `%`、`_`、反斜杠。使用参数绑定和 `LIKE ... ESCAPE '\\'`。

### Task 3

实现 service projection、source fingerprint、单事务 rebuild、status、旧索引保留和 JSON fallback。`ready` 的空数据源必须有效；不能只依据 row count 判断。API 不能散落 fallback 分支。

### Task 4

采集期间每 20 条或 2 秒 flush，group 完成/取消/异常/停止/cleanup 都 final flush；JSON 先写，SQLite 后写；成功 listing 才替换 group rows，失败保留旧组。

### Task 5

catalog/list/detail/PDF/TXT 通过 `ImaDocumentService` 读边界使用 SQLite；indexed path 不解析大 JSON；fallback 仍可用；不改变 ACL、详情歧义、归档安全或现有响应。

### Task 6

认证后同时发起 catalog 和首屏 documents，使用 `Promise.allSettled` 隔离失败；手机端行为保持不变；管理员才显示索引状态；正确更新 app/sw cache version。

### Task 7

新增 20-run benchmark：从 catalog 自动选第一个 subscribed group，不能写死 ID；消费完整响应；只输出 latency，不输出 token/header；运行 pytest、ruff、node check、browser regression。

### Task 8

只在所有代码审查和回归通过后发布。遵守 `vpush-vps-deploy` 流程，备份生产 `dav.db`，发布 amd64 镜像，验证 index rebuild、功能和 loopback p95：catalog <200ms、latest list <300ms、采集期间 <750ms；外部 Chrome 单独验证首屏 <1.5s。

## 禁止事项

不要：

- 在父目录 `main` 上实现。
- 删除当前未提交的迁移修复。
- 提交 `.cursor/`、`work/`、probe、`config.demo.yaml`、`docs/research/` 或其它无关文件。
- 打印任何生产 token、密码、Authorization header 或 SSH 私钥。
- 在 IMA/NFS 同步活动期间调 TCP。
- 用 reset/checkout 恢复文件来“清理”工作区。

完成全部任务后，报告每个 commit、测试结果、审查结果、生产验证指标和未解决风险；如果生产发布未执行或无法验证，明确写出，不要声称完成。
