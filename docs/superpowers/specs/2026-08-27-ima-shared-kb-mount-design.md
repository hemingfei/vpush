# IMA 共享知识库文件夹挂载设计

日期：2026-08-27
状态：已确认，待书面规格复核

## 1. 目标与范围

进入管理后台「数据源 → 抓取设置 → IMA」时，自动发现当前 IMA 账号可见的共享知识库。管理员在知识库内选择一个或多个文件夹后，V Push 只递归同步这些文件夹中的 PDF，并把选择持久化到现有 `ima_pure_groups` 配置中。

本次包含：

- 共享知识库自动发现、增量合并和失败保留。
- 知识库文件夹的按需加载、父目录递归挂载和未来子目录自动纳入。
- 现有单库/手工群组配置的兼容回退。
- 递归同步、路径元数据、日期归属、循环与异常目录树保护。
- 管理后台两栏桌面布局和手机端上下布局。
- 后端、同步器、前端交互和真实桌面/手机浏览器验收。

不包含：新增数据库表、修改普通用户订阅/ACL 规则、IMA 原文解密、全文 TXT 展示、移动端阅读页或新的 UI 组件库。

## 2. 现有边界

- 配置存储继续使用 `IMA_PURE_GROUPS_KEY = "ima_pure_groups"`，数据库仍是 SQLite settings。
- `ImaPureClient.discover_groups()` 使用 `search_knowledge_base`，已有游标重复保护和共享库过滤。
- `ImaPureClient.list_items(folder_id)` 使用 `get_knowledge_list`，负责一层列表的游标分页。
- 当前 manifest 逻辑只把根目录下一层 `media_type=99` 目录视作日期目录；本设计把目录遍历抽成通用递归逻辑，同时保留旧数据字段和文件路径规则。
- 管理 API 已有 `/api/admin/ima-collector`、原子 settings 写入、Refresh Token 脱敏和管理员鉴权，新增行为沿用这些边界。
- IMA 订阅库的 OpenAPI 原文权限仍受产品限制；本功能只改变目录选择和 PDF 同步范围，不扩大 IMA 权限。

## 3. 配置模型

`ImaGroupConfig` 增加 `folder_ids`，内部保留三态语义以兼容旧 JSON：

```json
{
  "id": "kb-123",
  "name": "投研周报",
  "knowledge_base_id": "kb-123",
  "root_folder_id": "root-123",
  "folder_ids": ["folder-a", "folder-b"],
  "enabled": true,
  "source": "discovered"
}
```

| `folder_ids` 内部值 | 含义 |
|---|---|
| `None` | 旧配置没有该字段；启用时回退到 `[root_folder_id]`，停用时为空 |
| `()` | 新配置明确没有挂载目录；不参与同步 |
| 非空元组 | 只递归这些目录 |

`public()` 始终输出数组：旧配置会输出兼容后的有效挂载目录，便于新前端下一次保存时完成 JSON 迁移。`enabled` 是现有兼容字段，实际同步条件为 `enabled` 且有效 `folder_ids` 非空。新前端把是否启用完全绑定到挂载数组是否为空，因此新发现知识库默认输出 `folder_ids=[]`、`enabled=false`。

每个挂载根目录代表该目录及其当前、未来所有子目录。保存和同步都按知识库隔离；同一文件夹被多个选择路径覆盖时只处理一次。

知识库清单合并规则：

1. 按 `id` 匹配，匹配不到时按 `knowledge_base_id` 匹配旧手工群组。
2. `manual` 群组保留管理员手工名称和根目录；发现结果只补充其知识库存在性。
3. 已存在的 `discovered` 群组保留 `folder_ids` 和挂载状态，只更新名称和发现到的根目录。
4. 新发现的 `discovered` 群组不继承任何目录选择，默认不启用。
5. 发现请求完整成功后，清除本次结果中已经不存在的 `discovered` 群组；`manual` 群组不清除。
6. 网络、认证、格式或分页失败时不替换清单，保留上次成功结果并记录脱敏错误。

## 4. IMA 目录归一化

`get_knowledge_list` 的原始条目不直接返回前端，也不让同步器依赖单一字段。文件夹 ID 和名称按以下顺序提取：

- ID：`folder_info.folder_id` → `folder_id` → `media_id`（仅当其以 `folder_` 开头）。
- 名称：`folder_info.name` → `name` → `title` → 文件夹 ID。
- 文件夹判定：`media_type == 99`、存在有效 `folder_info.folder_id`、存在 `folder_id` 且没有文件 `media_id`，或 `media_id` 以 `folder_` 开头，任一成立。
- `has_children`：优先读取响应中的 `folder_number`、`sub_folder_count`、`children_count` 等计数字段；没有字段时为 `null`，前端仍允许展开一次并以空结果收起。

前端目录项只收到：

```json
{
  "id": "folder-a",
  "name": "2026 年周报",
  "parent_id": "root-123",
  "has_children": true,
  "file_count": 12,
  "folder_count": 3
}
```

计数缺失时省略或返回 `0` 不影响选择。目录接口只读取一层，前端按 `group_id + parent_id` 缓存已经成功的结果，切换知识库或重新发现时清理对应缓存。

## 5. 管理 API

### 5.1 读取现有状态

`GET /api/admin/ima-collector` 保持现有响应结构，扩展：

- 每个 `config.groups[]` 增加 `folder_ids` 和 `mounted_folder_count`。
- 增加 `discovery`：`status` 为 `never`、`ok`、`failed` 或 `not_configured`，以及 `at` 和脱敏 `error`。
- 不返回 Refresh Token 原文。

### 5.2 触发发现

`POST /api/admin/ima-collector/discover`，仅管理员可用，无请求体。

成功响应使用 HTTP 200：

```json
{
  "ok": true,
  "status": "finished",
  "config": { "groups": [] },
  "discovery": { "status": "ok", "at": "2026-08-27T12:00:00Z", "error": "" }
}
```

未配置 UID 或 Refresh Token 返回 HTTP 400。网络、认证、IMA 错误返回 HTTP 200 且 `ok=false`，响应仍带上未改变的当前配置和 `discovery.status=failed`，这样前端可以直接显示“保留上次结果”而不丢失列表。

发现结果写入单独的 discovery 状态 setting；不得复用同步完成时间推断发现时间。错误先经过现有 `_safe_error()`，不记录 URL 查询参数、Token、签名或 Cookie。

### 5.3 按需读取目录

`GET /api/admin/ima-collector/groups/{group_id}/folders?parent_id=`，仅管理员可用。

- `group_id` 和 `parent_id` 使用 `[A-Za-z0-9_:-]{1,128}`；空 `parent_id` 表示知识库根目录。
- `group_id` 必须是当前配置中的群组，停用或未挂载的群组也允许读取目录。
- 服务端使用现有 Refresh Token 创建该群组的 `ImaPureClient`，调用一次父目录列表并返回归一化的一层目录。
- 成功响应包含 `group_id`、实际 `parent_id`、`items`；不返回原始条目、Cookie、Refresh Token 或签名 URL。
- 目录请求失败返回 HTTP 502，错误文本脱敏；前端只影响当前父目录并显示重试入口。

### 5.4 保存挂载配置

`PUT /api/admin/ima-collector` 继续是唯一保存入口。`ImaGroupIn.folder_ids` 类型为可省略的字符串数组：

- 字段省略：兼容旧前端，保留已有 `folder_ids`；若已有配置也没有该字段，则根据旧 `enabled/root_folder_id` 回退。
- 字段显式为 `[]`：明确解除该群组全部挂载。
- 每组最多 256 个 ID，每个 ID 不能为空且最多 128 字符；精确去重后保存。
- 前端根据已加载的父子关系去掉被父目录覆盖的子目录；服务端不信任该归一化，只保证精确去重，递归同步再用 visited 集合做最终保护。
- `enabled=false` 时有效挂载数组归一化为空；有挂载数组的新前端发送 `enabled=true`。
- `source` 不接受客户端覆盖，按已有配置或发现结果确定。
- 组 ID、名称、知识库 ID、旧根目录字段继续执行现有校验，重复组 ID 直接返回 HTTP 400。
- 使用一次 `set_settings_atomic` 写入所有变更。Refresh Token 留空仍保持已保存值。

保存后若某组挂载数组为空，移除该组的 manifest 索引，但只保留本地 PDF/TXT 和 state 文件；重新挂载同一目录时可复用本地文件，不强制重新下载。

## 6. 数据流

1. 管理员打开抓取设置，页面先读取现有 `/api/stats`，渲染保存值和上一次目录选择。
2. 当前 tab 首次进入 `config` 时调用一次发现接口；发现过程中保留现有目录草稿，不因状态轮询重绘目录树。
3. 发现成功后更新左栏库清单；已存在库的草稿按知识库 ID 合并，新库显示为“未挂载”。
4. 管理员点击左栏知识库，前端只请求其根目录；点击展开按钮后再请求对应父目录。
5. 复选框只修改浏览器内的 draft set，不立即触发同步。父目录勾选后，已加载子目录显示继承状态且不可重复勾选。
6. 点击“保存采集配置”后，前端提交完整群组数组和显式 `folder_ids`；成功后重新读取状态但保留原焦点。
7. 定时同步先发现一次并合并清单，再逐个处理有效挂载的群组；新库因为没有挂载目录而跳过。

## 7. 递归同步

`ImaPureClient.manifest()` 接受群组的有效挂载目录集合，按以下算法构造 manifest：

1. 为每个挂载根目录建立待访问队列，维护 `visited_folder_ids`、`seen_media_ids`、当前路径和深度。
2. 调用 `list_items(folder_id)`，分页由现有游标逻辑完成。
3. 文件夹条目加入队列；PDF 条目按现有 `media_id`、名称、大小、摘要、封面校验规则入库。选中目录下的直接文件也必须处理。
4. 对同一知识库内重复到达的文件夹或媒体 ID 只保留第一次，避免父子重复选择造成双扫描和 state key 冲突。
5. 每条记录新增：
   - `source_folder_id`：文件所在的直接父目录。
   - `source_root_folder_id`：命中的挂载根目录。
   - `folder_path`：从遍历起点到直接父目录的名称数组。
6. 日期取 `folder_path` 中最后一个匹配 `^\d{4}$` 的目录名；没有明确 `MMDD` 目录时为 `unknown`。不根据服务器时区猜日期。
7. 设置单知识库最大深度 32、最大访问目录数 10,000；超过上限抛出该群组错误并保留旧 manifest。目录 ID 循环由 visited 集合截断。
8. 单群组请求或文件失败不影响其他群组。群组目录请求整体异常时不调用 `save_group_manifest`，因此旧 manifest 和本地文件继续可读。
9. 正常完成后按现有 `save_group_manifest` 替换该群组的 manifest 记录；未选择的旧目录记录从索引中移除，但本地文件和 state 不删除。

同步结果保留现有 `total/pending/downloaded/failed/last_error` 字段，并在每组增加 `folder_count`、`skipped` 和 `last_error`。顶层继续返回 `discovery_error`、`group_errors`、`succeeded_groups`、`failed_groups`，前端已有状态读取不被破坏。

## 8. UI 设计

### 8.1 桌面端

沿用现有 `section-panel`、`cfg-group`、design tokens 和 settings tab，不引入新依赖或独立视觉主题。连接区只显示 UID、检查间隔和 Refresh Token；知识库 ID、根目录 ID作为隐藏兼容字段提交，不能再要求管理员手填。

“知识库群组”区域改为两栏：

- 左栏固定为约 240–320px 的知识库列表，按钮行至少 44px 高。每行显示库名、来源状态和“已挂载 N 个文件夹”/“未挂载”，当前项使用已有 accent soft 背景和描边。
- 右栏占剩余宽度，顶部显示当前库名、挂载数量和目录加载状态；下面是一层层加载的文件夹树。目录行保持稳定的复选框、文件夹图标、名称和展开按钮布局，长名称使用截断并以 `title`/可访问名称保留完整内容。
- 两栏内部使用 1px 描边和现有 surface 色，不使用渐变、装饰性圆形、阴影卡片或嵌套卡片。目录树超过可用高度时只在目录区域滚动，页面不横向溢出。
- 重新发现按钮使用现有 refresh icon，并保留清晰文字标签；展开/收起使用图标按钮并提供 `aria-label` 和悬停提示。保存按钮仍是页面唯一主操作。

### 8.2 目录选择状态

- 精确已选目录：原生 checkbox checked。
- 被已选父目录覆盖的子目录：显示 checked、disabled 和“继承”语义，不写入额外选择。
- 已加载子目录中存在直接选择：父 checkbox 显示 indeterminate；父目录勾选后清理其已知子选择。
- 已保存但当前目录接口找不到的 ID：在目录区顶部显示“已选择但当前不可见”的警告行，允许管理员明确取消；不会因刷新或保存其他字段而静默删除。
- 空目录：显示无目录空态，不显示伪造 checkbox。
- 加载失败：保留当前已展开内容和草稿，在当前区域显示错误及“重试”，不替换整个 IMA 设置区。
- 新发现知识库：左栏显示未挂载，右栏加载后所有 checkbox 默认不选。

### 8.3 手机端

在 `max-width: 800px` 时从两栏改为单列，顺序固定为“知识库列表 → 当前库文件夹列表”。知识库行、目录行、展开按钮、复选框和重新发现/保存按钮均保持至少 44px 触控区域；文本可换行或省略，不允许挤出屏幕或覆盖相邻控件。

列表区和目录区采用相同的边框、间距和字体 token；目录列表可独立滚动但不产生横向滚动。保存按钮在底部占满可用宽度，状态文本在按钮上方换行。切换知识库时保留 scroll position 之外的 draft 选择，不因手机重排丢失选择。

### 8.4 可访问性与焦点

- 左栏使用 `role=listbox`/`option` 或等价的按钮语义，当前知识库可由键盘识别。
- 文件夹树使用原生 checkbox；展开按钮有 `aria-expanded`，目录名称与 checkbox 绑定。
- 发现、目录加载、保存状态使用 `aria-live="polite"`；错误使用现有状态色和文本，不只依赖颜色。
- 所有可操作控件保留 `:focus-visible` 轮廓；保存/发现后整页重绘时恢复触发操作前的焦点。
- 不增加解释快捷键、教程式大段文字或营销文案；必要说明只出现在状态和字段辅助文本中。

## 9. 错误和稳定性

| 场景 | 后端行为 | UI 行为 |
|---|---|---|
| 缺 UID/Token | 发现 400；同步 `not_configured` | 显示凭证缺失，保留已有库清单 |
| 发现网络/认证失败 | 不写群组清单，保存脱敏错误 | 显示上次结果和重试按钮 |
| 发现返回空列表 | 视为完整成功，移除旧 discovered，保留 manual | 显示无共享库空态 |
| 单库目录失败 | 该组失败，不替换旧 manifest | 目录区只显示当前库错误 |
| 单文件下载失败 | 记录文件失败，其他文件继续 | 现有同步失败统计增加 |
| 目录权限失效 | 记录群组错误，旧文件不删除 | 显示已选目录不可见/重试 |
| 空目录正常返回 | 新组保存空 manifest；已有组按现有“空响应保留旧 manifest”规则处理 | 显示空目录，不误报成功下载 |
| 父子重复选择 | 保存精确去重，遍历 visited 去重 | 子项继承显示，禁止重复勾选 |
| 目录循环/超大 | 终止当前组并保留旧 manifest | 显示该组失败，不阻塞其他库 |
| 定时状态刷新 | 只更新状态 setting | 不重绘目录草稿或输入框 |

所有管理员接口继续依赖 `require_admin`。路径参数、查询参数和 JSON 数组在边界处校验；错误消息不得回显凭据或可复用签名 URL。

## 10. 测试与验收

### 后端单元测试

`tests/test_ima_documents.py` 覆盖：

- 旧 JSON 无 `folder_ids` 时回退根目录，显式空数组不回退。
- 发现成功保留已有选择、新库为空挂载、移除消失 discovered；发现失败保留旧清单。
- 文件夹字段归一化、根目录直接文件、任意深度递归、重复父子选择、重复目录/媒体 ID、unknown 日期、路径元数据。
- 游标重复、循环目录、深度/节点上限和单组异常隔离。
- 旧 manifest/state/PDF 路径可读，解除挂载不删除本地文件。

`tests/test_ima_kb.py` 覆盖：

- 发现 API 成功、未配置、失败保留和错误脱敏。
- 文件夹 API 的管理员鉴权、未知组、参数校验、根目录和子目录响应。
- PUT 的 `folder_ids` 类型/数量/格式/重复校验、旧前端省略字段兼容、显式空数组和原子写入。
- 新组无挂载时不触发同步，选择目录后只同步选中组。

### 前端契约与浏览器验收

`tests/test_frontend_interactions.py` 覆盖：

- 不再渲染旧的手工群组输入、添加群组和根目录编辑行。
- 两栏 DOM、知识库挂载计数、懒加载接口、父子继承状态、发现/目录失败重试和显式 `folder_ids` 提交。
- 状态轮询不调用目录重绘；保存和发现保留焦点；所有动态文本经过 `escapeHtml`。
- CSS 在 800px 以下切换单列，目录和按钮最小 44px，长名称不使用固定宽度造成溢出。

真实浏览器至少检查：

- 1440px 桌面：多个库、长库名、深层目录、父目录选择、两个库切换和保存。
- 390px 手机：库列表到目录列表的顺序、触控尺寸、长名称换行/省略、加载/失败/空态和底部保存按钮。
- 发现失败、目录失败、刷新期间未保存草稿、父目录未来新增子目录语义。
- `node --check app/static/app.js`、`git diff --check`、相关 pytest 和完整 pytest。

验收标准是：新发现库不会下载任何文件；选择父目录后当前及未来子目录可同步；网络失败不丢旧结果；刷新/窄屏/长文本不产生重叠、横向溢出、焦点丢失或重复请求。

## 11. 升级策略

不新增数据库迁移。旧 `ima_pure_groups` 在读取时即时兼容，下一次管理员保存时带上 `folder_ids`。旧 manifest、state、本地 PDF/TXT 不迁移、不删除。前端缓存版本随实现版本递增，避免旧 service worker 长期提交不带 `folder_ids` 的表单；后端仍保留省略字段的兼容分支，以覆盖缓存未及时更新的客户端。
