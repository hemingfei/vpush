# VPUSH 财经新闻聚合设计

日期：2026-09-01
状态：已确认

## 目标

在 VPUSH 中增加一个登录后可用的独立“财经新闻”入口，用于聚合可完整阅读的财经媒体长文；现有华尔街见闻快讯继续留在“最新动态”中：

- **动态**回答“刚刚发生了什么”，包含大 V 短内容和现有华尔街见闻快讯。快讯继续采用 15 秒短缓存代理，不入库、不推送、无用户订阅状态。
- **财经新闻**回答“有哪些值得完整阅读的内容”，共享抓取后落库，用户按媒体选择来源，在 VPUSH 内阅读安全清洗后的全文。
- 首版以阅读聚合为唯一目标，不接入 Telegram、飞书、企业微信、Bark 或 Web Push。

产品边界固定为：**动态 = 大 V 动态 + 实时快讯，财经新闻 = 媒体长文，研报库 = 研究文档**。

## 已确认决策

- 新增独立“财经新闻”入口，不设置与快讯共用的二级页签。
- 华尔街见闻快讯继续保留在“最新动态”的平台角标中，数据接口、刷新和界面行为均不变。
- 每位用户独立选择财经来源；新用户默认选择四个内置媒体。
- 首版用户按媒体选择，不开放媒体下的频道级选择；一个媒体可由管理员配置多个 Feed。
- 管理员可新增任意公网 RSS/Atom Feed、编辑媒体与 Feed、停用、手动刷新及归档恢复。
- 管理员后续新增的媒体不会自动加入现有或新用户的新闻流，用户须主动选择。
- 用户点击文章后在 VPUSH 内阅读全文，同时始终保留媒体标识与原文入口。
- 中文来源显示中文；英文来源保留英文原文，不做 LLM 全文翻译。
- 只记录用户上次成功进入新闻流的时间，不做逐篇已读状态。
- 所有启用 Feed 由服务端统一抓取；用户数只影响查询，不增加抓取次数。
- 新闻沿用现有内容保留配置，默认保留 30 天。

## 信息架构

### 桌面导航

普通用户侧栏顺序调整为：

1. 最新动态
2. 财经新闻
3. 研报库
4. 订阅广场
5. 组合订阅
6. 我的订阅
7. 推送设置

“财经新闻”直接显示个人来源下的新闻混排列表、来源选择和全文入口，不设置快讯页签。

### 手机导航

手机底栏增加“财经新闻”，顺序为：动态、财经新闻、广场、组合、订阅、设置；管理员继续在末尾增加“更多”。在 320px 宽度下，管理员的 7 个底栏项仍须保持单项至少约 44px 的可点击宽度。

动态平台条继续保留“快讯”和当前用户可见的平台角标。它仍是一行等宽图标角标，不改成带字胶囊或横向滚动条。实施时不改动快讯位置、筛选或交互。

## 新闻列表与阅读

### 列表

财经新闻列表按 `published_at DESC, id DESC` 混排，单条显示：

- 媒体名
- 发布时间
- “新”标记
- 标题
- 最多两行纯文本摘要
- 可用时显示首图缩略图

列表支持：

- 用户已选择来源内的“全部”混排
- “我的来源 · N”打开带搜索的复选列表，适应管理员后续增加较多媒体
- 临时媒体筛选使用单一选择菜单，只列“全部”和用户已选媒体，不把所有来源铺成大量胶囊
- 关键词搜索标题与摘要
- 无限滚动分页
- 来源更新时间与失败提示

“我的来源”是页内控件，不新增独立设置页。用户没有选择任何媒体时，显示明确空态和“选择来源”操作，不自动恢复默认值。

### 全文页

全文页显示媒体、标题、作者、发布时间、清洗后的正文和“打开原文”链接。正文保留常见语义结构和图片，不复制原站脚本、样式或交互组件。

英文文章保留英文标题和全文。首版不自动翻译，也不调用现有 X 翻译或 LLM 配置。

## 内置来源与管理员 Feed 管理

系统迁移时创建四个内置媒体及其 Feed：

| 用户选项 | Feed | 语言 | 说明 |
| --- | --- | --- | --- |
| Bloomberg | `https://quanwenrss.com/bloomberg` | 英文 | 使用英文全文源 |
| 财新 | `https://quanwenrss.com/caixin` | 中文 | 最新文章全文 |
| FT 中文网 | `https://quanwenrss.com/ft` | 中文 | 综合新闻全文 |
| 摩根士丹利 | `https://quanwenrss.com/morganstanley/china`、`https://quanwenrss.com/morganstanley/global` | 中文、英文 | 两个 Feed 归属同一个用户选项 |

四个内置媒体标记为 `default_selected`。迁移时为所有旧用户建立这四个媒体的选择关系；新注册用户同样默认选择它们。

管理员可在“数据源 → 财经资讯”管理媒体及其 Feed。页面采用媒体主从工作台：左侧媒体列表支持搜索、状态筛选和“显示已归档”，右侧显示当前媒体字段、Feed 列表及操作。窄屏改为先列表、后详情的单列导航。

- 新建、重命名、启用或停用媒体。媒体名去除首尾空白后为 1 至 60 字符，并按大小写不敏感规则保持唯一。
- 在一个媒体下新增、编辑、启用或停用多个 RSS/Atom Feed。Feed 名称为 1 至 80 字符，URL 最长 2048 字符。
- 新增或修改 URL 时先执行“验证并保存”，显示检测到的格式、Feed 标题及最近三篇纯文本预览；预览不返回或渲染上游 HTML。
- 手动刷新单个 Feed、单个媒体或全部财经 Feed；同一 Feed 已在刷新时返回冲突状态，不并发重复抓取。
- 归档和恢复 Feed 或媒体。归档停止抓取并从用户可选目录隐藏，但保留用户选择关系，文章按保留期自然清理；恢复后原用户选择自动生效。
- 所有新增、编辑、启停、刷新、归档和恢复动作写入管理员操作日志。

管理员全局设置仅包含：

- 财经新闻采集总开关，默认开启。
- 刷新周期，默认 10 分钟，允许 5 至 1440 分钟。
- “全部刷新”命令。

文章保留期复用现有 `polling.posts_retention_days`，不增加重复配置。响应大小、超时、端口和 SSRF 规则属于安全边界，不开放为管理员设置。

管理员新增媒体的 `default_selected` 固定为 false，不能配置成自动加入用户。用户不能提交自定义 Feed URL。

当前内置源不接入 Bloomberg 中文摘要 Feed，因为它不满足“站内阅读全文”的已确认目标。

## 采集流程

财经新闻刷新复用现有 `Scheduler`，不创建第二个常驻调度器：

1. 调度循环按管理员设置的周期查询已启用、未归档媒体下的已启用 Feed。
2. 每个 Feed 独立发送条件请求，复用该 Feed 保存的 `ETag` 和 `Last-Modified`。
3. 响应为 `304` 时只更新成功状态；响应有内容时解析 RSS 2.0 或 Atom。
4. 每个 Feed 每轮最多处理响应中按发布时间排序的前 100 个条目；每篇文章规范化身份、时间、标题、摘要、正文、首图和原文 URL。
5. 标题、作者和摘要分别截断到 500、200 和 2000 字符；图片只保留前 30 个。单篇清洗后正文超过 512 KB 时跳过该篇并记录脱敏原因。
6. 正文经过 HTML 白名单清洗后再落库。
7. 按媒体和外部身份幂等写入；内容哈希变化时更新原记录。
8. 单 Feed 或单篇失败只记录该项，不中断其他来源。

网络与 SSRF 边界：

- Feed URL 仅允许 `http` 或 `https`，禁止 URL 用户名/密码，只允许默认的 80/443 端口。
- 拒绝 `localhost`；DNS 没有结果或任一结果属于 loopback、private、link-local、multicast、unspecified、reserved 或云元数据地址时，整次请求拒绝。
- 保存验证、手动刷新和定时刷新每次都重新执行 URL 与 DNS 校验，不能只在保存时检查。
- 实际连接必须固定到本次已验证的公网地址，同时保留原始 Host 和 TLS SNI；不得在校验后重新解析到另一地址。
- 最多跟随 3 次重定向，每一跳都重新执行 URL、端口、DNS 和目标地址校验。
- HTTP 客户端使用 `trust_env=False`，不继承环境代理、Cookie 或认证信息。
- 单次请求的连接超时为 5 秒、读取超时为 15 秒，解压后的最大响应体为 5 MB。
- 原文链接和图片链接只接受 `http` / `https` 协议。
- Feed 返回异常未来时间时钳制为抓取时间；超过保留窗口的旧条目不新增。

URL 安全校验使用 Python 标准库 `urllib.parse`、`socket` 和 `ipaddress`，保存验证与正式抓取共用同一个安全客户端，避免两套规则漂移。

Feed 的 ETag、Last-Modified、最后尝试时间、最后成功时间、内部错误、公开错误状态和连续失败次数保存在 `news_feeds`。管理员页面显示 Feed 级状态；普通用户新闻列表只显示与所选媒体相关的归一化“更新延迟 / 暂时不可用”状态，不暴露内部网络信息。

## 解析与 HTML 安全

新增两个成熟小依赖：

- `feedparser`：兼容 RSS、Atom、命名空间和常见日期格式。
- `bleach`：对白名单 HTML 做安全清洗。

不手写 RSS/Atom 兼容层或 HTML 清洗器。

正文允许以下标签：`p`、`br`、`h2`、`h3`、`hr`、`ul`、`ol`、`li`、`blockquote`、`strong`、`b`、`em`、`i`、`a`、`img`、`figure`、`figcaption`、`pre`、`code`、`table`、`thead`、`tbody`、`tr`、`th`、`td`。允许的属性仅为：

- 链接：`href`、`title`
- 图片：`alt`、`title`、`width`、`height`、`data-news-image-index`
- 表格单元格：`colspan`、`rowspan`

相对链接先按文章原文 URL 解析为绝对地址，再执行协议白名单。图片 `src` 不直接保留：清洗阶段用 Bleach token filter 按出现顺序提取到文章 `images` JSON，并把正文节点改成无 `src` 的 `data-news-image-index`。其余标签和属性全部移除，包括：

- `script`、`style`、`iframe`、`object`、`embed`、表单和媒体执行标签
- 所有 `on*` 事件属性
- `javascript:`、`data:` 等非 HTTP(S) 链接
- 来源内联样式和不必要的追踪属性

清洗后的外链统一使用 `target="_blank" rel="noopener noreferrer nofollow"`。前端渲染全文后，使用带登录凭据的图片 API 获取 Blob，再为对应 `data-news-image-index` 设置临时对象 URL；离开全文页时释放对象 URL。浏览器不直接请求 Feed 提供的图片地址，也不复用现有固定图床代理。

## 数据模型

### `news_sources`

媒体表：

- `id INTEGER PRIMARY KEY`
- `slug TEXT NOT NULL UNIQUE`：稳定内部标识，内置媒体使用固定值；自定义媒体由服务端生成 `custom-<uuid>`，创建后不可修改
- `name TEXT NOT NULL COLLATE NOCASE UNIQUE`：用户侧显示名称
- `enabled INTEGER NOT NULL DEFAULT 1`
- `built_in INTEGER NOT NULL DEFAULT 0`
- `default_selected INTEGER NOT NULL DEFAULT 0`：仅四个内置媒体为 1
- `archived_at TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

管理员新增媒体固定 `built_in=0, default_selected=0`。停用只暂停抓取，媒体仍在用户来源目录中并可阅读旧文章；归档则暂停抓取并从用户可选目录隐藏。

### `news_feeds`

媒体下的 Feed 与运行状态表：

- `id INTEGER PRIMARY KEY`
- `source_id INTEGER NOT NULL REFERENCES news_sources(id)`
- `name TEXT NOT NULL COLLATE NOCASE`
- `url TEXT NOT NULL`
- `normalized_url TEXT NOT NULL UNIQUE`
- `enabled INTEGER NOT NULL DEFAULT 1`
- `etag TEXT NOT NULL DEFAULT ''`
- `last_modified TEXT NOT NULL DEFAULT ''`
- `last_attempt_at TEXT`
- `last_success_at TEXT`
- `last_error_code TEXT NOT NULL DEFAULT ''`：可公开的归一化错误码
- `last_error_detail TEXT NOT NULL DEFAULT ''`：仅管理员和日志可见的脱敏详情
- `consecutive_failures INTEGER NOT NULL DEFAULT 0`
- `archived_at TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `UNIQUE(source_id, name)`

修改 URL 时重新规范化和验证，清空 ETag、Last-Modified 与旧运行状态。Feed 归档不级联删除文章。

### `user_news_sources`

媒体目录必须使用关系表，不把可变媒体 ID 塞进用户 JSON：

- `user_id INTEGER NOT NULL REFERENCES users(id)`
- `source_id INTEGER NOT NULL REFERENCES news_sources(id)`
- `selected_at TEXT NOT NULL`
- `PRIMARY KEY(user_id, source_id)`

媒体归档时保留关系；查询时忽略归档媒体。停用媒体仍可阅读旧文章，并在用户界面显示“管理员已暂停更新”；恢复媒体后原选择自动生效。

### `news_articles`

共享内容表：

- `id INTEGER PRIMARY KEY`
- `source_id INTEGER NOT NULL REFERENCES news_sources(id)`
- `feed_id INTEGER NOT NULL REFERENCES news_feeds(id)`
- `external_id TEXT NOT NULL`
- `title TEXT NOT NULL`
- `url TEXT NOT NULL`
- `author TEXT NOT NULL DEFAULT ''`
- `summary TEXT NOT NULL DEFAULT ''`
- `content_html TEXT NOT NULL DEFAULT ''`
- `images TEXT NOT NULL DEFAULT '[]'`：按正文顺序保存通过 URL 初检的图片地址 JSON 数组
- `published_at TEXT NOT NULL`：UTC ISO 8601
- `fetched_at TEXT NOT NULL`：UTC ISO 8601
- `content_hash TEXT NOT NULL`
- `UNIQUE(source_id, external_id)`

`external_id` 优先使用 Feed 的 GUID/Atom ID；缺失时使用规范化原文 URL。URL 规范化移除 fragment，以及 `utm_*`、`fbclid`、`gclid` 追踪参数，保留其他查询参数。去重范围限定在同一媒体内，避免不同媒体合法转载时错误合并。

索引至少覆盖：

- `(published_at DESC, id DESC)`
- `(source_id, published_at DESC, id DESC)`

### `users` 与全局设置

`users` 只增加：

- `news_last_seen_at TEXT`：上次成功显示财经新闻列表时的 UTC ISO 8601 服务端时间锚点，初始为空。

全局 `settings` 只保存 `news_enabled` 和 `news_refresh_interval_seconds`。Feed 运行状态不写入 `settings`。

不新增逐用户逐文章状态表。

## 用户 API

### `GET /api/news/sources`

返回所有未归档媒体、启用状态以及当前用户是否选择。Feed URL 和内部错误不返回给普通用户。

### `GET /api/news`

参数：

- `limit`：默认 30，上限沿用 API 分页约束。
- `offset`：默认 0。
- `source_id`：可选，只能是用户已选择且未归档的媒体。
- `q`：可选，搜索标题与摘要。

返回对象包含：

- `items`
- `next_offset`
- `has_more`
- `view_started_at`：本次查询开始时的服务端时间
- `source_status`：用户所选来源的最后成功时间和可公开错误状态；只返回“更新延迟 / 暂时不可用”等归一化状态，不暴露上游响应、堆栈或内部错误文本。

每项由服务端根据旧的 `news_last_seen_at` 返回 `is_new`。首次访问时锚点为空，历史库存全部视为非新文章。

### `POST /api/news/seen`

列表成功显示后，前端提交该次 GET 返回的 `view_started_at`。服务端只允许锚点单调前进，避免较旧请求覆盖较新的访问状态。这样在 GET 与 POST 之间新发布的文章仍会在下次显示为“新”。

### `GET /api/news/{id}`

返回单篇全文。要求登录，并且文章媒体仍被用户选择且未归档；否则返回 404。媒体停用不影响旧文章阅读。

### `GET /api/news/{id}/images/{index}`

要求与全文相同的登录和媒体权限。服务端从文章 `images` 取目标 URL，每次请求重新执行完整 SSRF 校验并用安全客户端抓取，只接受 JPEG、PNG、WebP 和 GIF，最大 10 MB，不持久化服务端缓存，响应使用 `Cache-Control: private, max-age=86400`。列表首图和全文内图片均由前端以带登录凭据的请求取得 Blob URL；越界索引、非图片响应或不安全目标返回 400/502，不回显内部地址。

### 个人设置

复用现有个人设置更新接口接收 `news_source_ids` 数组，并在一个事务内同步 `user_news_sources`。服务端接受未归档媒体 ID；停用媒体可以继续保留或取消选择，但不能产生抓取任务。

## 管理员 API

- `GET /api/admin/news/settings`、`PATCH /api/admin/news/settings`：读取和更新总开关及刷新周期。
- `GET /api/admin/news/sources`：列出媒体、Feed、文章数和运行状态，可包含已归档项。
- `POST /api/admin/news/sources`、`PATCH /api/admin/news/sources/{id}`：新增或编辑媒体。
- `POST /api/admin/news/sources/{id}/archive`、`POST /api/admin/news/sources/{id}/restore`：归档或恢复媒体。
- `POST /api/admin/news/sources/{id}/refresh`：刷新媒体下全部可用 Feed。
- `POST /api/admin/news/feeds/validate`：使用正式安全客户端临时验证 URL，返回格式、标题和最近三篇预览，不落库。
- `POST /api/admin/news/sources/{id}/feeds`、`PATCH /api/admin/news/feeds/{id}`：验证后新增或编辑 Feed。
- `POST /api/admin/news/feeds/{id}/archive`、`POST /api/admin/news/feeds/{id}/restore`：归档或恢复 Feed。
- `POST /api/admin/news/feeds/{id}/refresh`：刷新单个 Feed。
- `POST /api/admin/news/refresh`：刷新全部可用 Feed。

所有写操作要求管理员权限、使用既有管理员鉴权并写操作日志。操作日志中的 Feed URL 隐去 query 和 fragment。手动刷新复用每 Feed 锁；目标正在刷新时返回 `409`。API 不提供硬删除，避免误操作造成正文与用户选择级联丢失。

## 快讯保持原位

现有 `/api/live/wscn`、预热线程、短缓存、搜索、重要筛选、轮询、无限滚动、请求缓存和滚动位置全部保持不变。华尔街见闻快讯继续作为“最新动态”的平台角标，不接入财经新闻页面。

快讯继续不入库、不进入用户财经新闻来源设置、不参与财经新闻搜索，也不与财经长文混排。本功能不得重构或迁移现有 WSCN 链路。

## 错误处理

- URL 验证触发 SSRF 规则：拒绝保存，并返回不含解析地址或内部网络细节的明确原因。
- Feed 验证无法解析出有效 RSS/Atom 文档时拒绝保存；结构有效但暂时没有条目的 Feed 可以保存，预览显示为空。现有 Feed 编辑失败时保持旧配置不变。
- 单来源刷新失败：保留数据库旧内容，记录最后错误，向用户显示该来源更新延迟；其他来源正常展示。
- XML 整体不可解析：本轮不改数据库旧内容。
- 单篇缺少稳定身份、标题或合法 URL：跳过该篇并记录脱敏日志。
- 单篇正文为空：允许保存摘要，并在全文页提供原文入口；不把整源判为失败。
- 来源恢复：首次成功后清除公开错误状态和连续失败计数。
- 全局采集关闭：财经新闻页面保留但显示“管理员已暂停财经新闻采集”，数据库旧内容仍可阅读。
- 所有来源都无缓存且刷新失败：显示可重试空态，不退回快讯或动态内容。

## 内容授权边界

四个内置 `quanwenrss.com` Feed 的公开隐私政策只说明其使用外部 RSS，没有授予 VPUSH 对媒体全文的再分发许可。管理员添加其他 Feed 时，也必须自行确认对应内容许可。因此首版限定为：

- 登录后的自托管个人阅读
- 始终标明媒体与原文链接
- 不创建公开文章页
- 不允许搜索引擎索引
- 不提供站外分享或全文导出接口
- 不把全文或逐篇新闻推送给多人

正式公开运营或接入全文推送前，必须单独确认 Feed 服务与原媒体许可。无法确认时，管理员应停用或归档该 Feed；产品层面的“摘要 + 原文跳转”双模式不纳入首版。

## 实施阶段

### 阶段 1：安全来源管理

- 增加依赖、四张新闻表、用户访问锚点和内置来源迁移。
- 实现共用安全 HTTP 客户端、URL/DNS/IP/重定向校验和 Feed 验证预览。
- 实现管理员全局设置、媒体/Feed 管理 API、主从工作台、归档恢复与操作日志。

完成条件：管理员能安全管理任意公网 RSS/Atom；内网、云元数据、DNS 变化和重定向绕过均被测试阻止；归档不丢用户选择或级联删除文章。

### 阶段 2：共享采集

- 实现条件请求、RSS/Atom 解析、HTML 清洗、媒体内去重更新、状态记录和内容清理。
- 接入现有 Scheduler、手动刷新锁和管理员 Feed 级状态。

完成条件：四个内置媒体及新增测试 Feed 均可入库；单 Feed 失败不阻塞其他来源；恶意 HTML 无法进入存储后的正文。

### 阶段 3：个人新闻流

- 增加媒体来源目录、用户来源关系更新、新闻列表、全文和 seen API。
- 实现来源选择、混排、搜索、分页、新文章标记和站内全文。

完成条件：新建自定义媒体不自动加入用户；不同用户只看到各自来源；重复刷新不产生重复文章；首次访问不把历史库存全部标新。

### 阶段 4：财经新闻入口

- 增加桌面与手机“财经新闻”导航并接入个人新闻流和全文页。
- 保持快讯在“最新动态”中的位置和现有行为。
- 同步更新产品约定、静态资源版本和相关前端测试。

完成条件：财经新闻入口在桌面与 320px 手机宽度下可正常使用；现有快讯位置和行为无回归。

## 验证

最小自动验证集：

1. RSS 和 Atom 固定样本分别验证标题、正文、图片、作者和时间解析。
2. 恶意 HTML 固定样本验证脚本、iframe、事件属性和危险协议被移除。
3. SSRF 测试覆盖 Feed 和文章图片请求的 URL 凭据、危险端口、IPv4/IPv6 内网、localhost、云元数据、混合 DNS 结果、DNS 重绑定防护和逐跳重定向复验。
4. DB 测试验证媒体/Feed 归档恢复、用户关系保留、媒体内去重、内容更新和 30 天清理。
5. 管理员 API 测试验证权限、Feed 验证预览、URL 唯一性、刷新冲突、全局设置和操作日志。
6. 用户 API 测试验证登录、媒体来源目录、分页、搜索、来源约束、全文权限与单调 seen 锚点。
7. 调度测试验证可用 Feed 发现、条件请求、单 Feed 失败隔离、状态恢复和停机行为。
8. 前端契约测试验证管理员主从工作台、财经新闻导航、快讯保留在动态、来源保存、新标记和全文入口。
9. Playwright 在桌面和手机视口验证 Feed 管理、验证预览、财经新闻列表、来源选择、全文页、底栏及无重叠。
10. 真实来源只做本地 smoke test，不作为 CI 的稳定依赖。

## 首版不包含

- 逐篇已读、收藏、稍后读、阅读进度和跨设备同步
- 实时推送、每日摘要、关键词提醒和免打扰规则
- LLM 摘要、全文翻译、相似新闻聚类和推荐算法
- 用户自定义 RSS URL、用户按 Feed/频道选择、需要 Cookie/Token/Basic Auth 的私有 Feed，以及跨媒体自由组合 Feed
- 管理员控制新媒体自动加入用户；所有新增媒体均需用户主动选择
- 公开文章页、搜索引擎索引、站外分享和内容再发布 API
- 新的图片缓存、通用内容抽象或第二套调度框架

## 后续触发条件

首版稳定运行且用户确实持续阅读后，二期优先考虑“每天一条财经摘要推送”。只有摘要仍无法满足明确需求时，再评估逐篇推送、LLM 翻译或频道级筛选。
