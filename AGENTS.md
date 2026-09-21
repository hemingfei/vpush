# AGENTS.md

## Agent skills

### Issue tracker

GitHub Issues（`hemingfei/vpush`），经 `gh` CLI 读写；仓库有 upstream fork（`icekale/vpush`）作为第二个 remote，`gh` 默认解析到 upstream——所有 issue/label 操作必须显式 `-R hemingfei/vpush`。见 `docs/agents/issue-tracker.md`。

### Triage labels

默认五标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文：根目录 `CONTEXT.md` 术语表 + `docs/adr/`（懒创建）。见 `docs/agents/domain.md`。
