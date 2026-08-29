# 知识库设置页签与分库采集间隔

日期：2026-08-29
状态：已确认，待实施

已确认稿：桌面/手机渲染图  
`work/ui-validation/knowledge-settings-mock-desktop.png`  
`work/ui-validation/knowledge-settings-mock-mobile.png`  
可点 HTML：`.superpowers/brainstorm/36117-1787986225/content/knowledge-settings-mock.html`

## 1. 目标

管理员打开 `/admin/knowledge` 时，首屏只做一件事：给共享知识库选文件夹，并给每个库设采集间隔。网页 Cookie / OpenAPI、手填 UID / Refresh Token、全局检查间隔都离开本页。

## 2. 信息架构

顶栏三个页签，默认 **采集**：

| 页签 | 内容 |
|------|------|
| 采集 | 现有左库右文件夹挂载；每行 `1h / 6h / 24h`；页脚 Token 状态、立即同步、保存挂载 |
| 星球 | 现有知识星球 Cookie 与抓取参数，逻辑不改 |
| 存储 | 现有远程存储状态与刷新/备份，逻辑不改 |

桌面：库列表 ≤300px，右栏文件夹。手机：先库后文件夹；间隔档在库名下方整组显示，不被裁切。触控目标 ≥44px。灰底白面、1px 描边、克制蓝、原生 checkbox。

不新增设置表。不改订阅/ACL。不把 Cookie/OpenAPI 挪到数据源页。

## 3. 采集页

删除：

- 「IMA 凭证」整块（`#ima-cookie` / `#ima-cid` / `#ima-key`、保存/粘贴/清除）
- 连接区手填 UID、全局间隔分钟、Refresh Token
- 隐藏的 kb/root 输入仍可由采集配置 API 内部使用，不在 DOM 展示

保留并收紧：

- 重新发现
- 两栏挂载（父目录递归规则不变）
- 保存挂载：写入各库 `folder_ids` 与 `interval_seconds`
- 立即同步：只同步**当前选中**且已挂载的库
- 页脚：未在跑时显示 `Token 已保存/未保存`；同步中显示当前库 + 阶段 + 进度条（见第 4.1 节）

间隔控件：每行分段按钮，值只能是 3600 / 21600 / 86400 秒，默认 3600。未挂载的库也可以先改间隔，保存时一起写入。

## 4. 后端

`ImaGroupConfig` 增加 `interval_seconds: int = 3600`。`public()` 带上该字段。读写现有 `ima_pure_groups` JSON。发现/合并库时保留已有间隔，新库默认 3600。非法值夹到最近档：`<3h → 1h`，`<12h → 6h`，否则 24h。

全局 `ima_pure_interval_seconds` 不再出现在本页。调度改为：

- 进程唤醒周期 = 已挂载库间隔的最小值，且不少于 1800 秒
- 每次只采集「已挂载且到期」的库：`now - last_started_at(group) >= interval_seconds`；从未跑过则到期
- 各库上次开始/结束时间写入 settings 键 `ima_pure_group_runtime`（JSON 对象，不加表）

`POST /api/admin/ima-collector/sync` 接受可选 JSON `{ "group_id": "..." }`：

- 有 `group_id`：只跑该库（忽略是否到期）；未挂载则 409
- 无 `group_id`：保持现行为（手动全量，给旧客户端），本页按钮不走这条

`PUT /api/admin/ima-collector` 保存 groups 时写入每库 `interval_seconds`。不再要求本页提交 uid/token/interval。

## 4.1 实时进度

现在同步中只显示「同步中…」，`last_result` 要等整轮结束才更新。改为内存进度，挂在 `GET /api/admin/ima-collector` 的 `progress` 上，不写库、不加 WebSocket。

```json
{
  "group_id": "7479082602225992",
  "group_name": "全球顶级投行研报库",
  "phase": "download",
  "listed": 11449,
  "pending": 9600,
  "downloaded": 1858,
  "failed": 2
}
```

`phase` 为 `listing` 或 `download`。列目录时 `listed` 为已扫到的文件数；下载时条为 `downloaded / pending`。每完成一份 PDF 更新内存；`status()` 读取该快照。未在跑时 `progress` 为 `null`。

采集页在 `running` 时每 2 秒只刷新页脚进度，不重绘挂载树。立即同步按钮显示「同步中」并禁用。空闲后恢复上次结果文案。

`/api/admin/ima-credentials` 暂留，本页不再调用。IMA 时间线抓取器代码不删。

## 5. 对现网三库的默认

现有已挂载库保存后若没有间隔字段，按 1h。管理员把投行库改成 6h、SemiAnalysis 改成 24h 是操作，不是迁移脚本。

## 6. 验收

- 桌面 1440 与手机 390：采集首屏无 Cookie/OpenAPI/UID/Token 表单；三页签可切；间隔档可点
- 保存后刷新，各库间隔仍在
- 立即同步只让选中库出现在本次 `last_result` 的 succeeded/failed 里
- 同步中页脚显示库名、`下载 x / y` 或 `列目录 n`，进度条约每 2 秒变；不重绘文件夹树
- 定时：1h 库到期会跑，24h 库未到期不跑
- `tests/test_frontend_interactions.py` 覆盖页签与间隔控件；`tests/test_ima_documents.py` 覆盖分库到期与 `group_id` 同步
- 不提交 `.cursor/`、`work/`、密钥

## 7. 不做

- 存储机直下 PDF（另有计划）
- 删除 ImaFetcher / OpenAPI 后端
- 每库独立线程同时采集
- 自定义分钟数
