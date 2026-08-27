# 知识库按日瘦行 + 阅读页摘要 / PDF

日期：2026-08-27
状态：已确认

打开一个库不再一次拉完全部文档。默认按日浏览、列表瘦行；点开后只看中文摘要和 PDF。目录页交互、手机端拦截、订阅/授权不变。

## 1. 列表：按日，搜索才出日

- 进入已订阅库（或管理员「全部知识库」）时，默认最新有文档的一天。URL 带 `day`，例如 `knowledge?group=legacy&day=0826`。未带 `day`、也没有 `q`/`tag` 时，服务端按最新一天返回，前端 `replaceState` 补上 `day`。
- 日期导航：`‹ 8月26日 ›`，只在 `days` 里有文件的日期之间跳。最新一天禁用「后一天」，最早一天禁用「前一天」。现有日期下拉仍可用来跳到任意有文件的一天。
- 搜索标题/摘要或点标签：离开按日。请求不再带 `day`。命中多时按时间线同样方式无限滚动，每页 50 条。
- 搜索与标签可叠加（AND）。再选一天则清掉 `q`/`tag`，回到该日。
- 清掉搜索/标签，或点「清除筛选」：回到进入搜索前的那一天；没有则回到最新一天。
- 库内没有文档：空状态，不显示日期导航。URL 带了不存在的 `day`：该日空列表，导航仍按真实 `days` 跳。
- 管理员看「全部知识库」：同一套规则，行上保留库名。

目录「打开」进该库最新一天；「最新」仍直接打开最新一份的阅读页。手机端仍是「知识库请在电脑上打开」。

## 2. 行：只要标题

每一行只显示标题、日期、类型（`PDF` / `全文` / `摘要`）。不要封面、摘要、标签。标签只从筛选下拉里选。管理员看全部库时，行上可多一个库名。

点行进阅读页。阅读页返回列表时保留当时的 `group` / `day` / `q` / `tag`。

## 3. 阅读页：摘要 + PDF

不再请求、不再渲染整份 TXT（`#ima-text-view` 去掉）。`GET /api/ima-documents/{id}/text` 保留，阅读页不用。

结构从上到下：

1. 库名、日期、标题、标签；有封面则保留小图。
2. 一段纯文字摘要（优先中文译文，见 §5）。
3. 有 PDF：类型/体积 +「下载 PDF」；下方 iframe 预览占满剩余高度，打开即加载。不要「查看 PDF / 收起 PDF」。
4. 没有 PDF：只留标题和摘要，说明还没有预览文件。

## 4. 接口

`GET /api/ima-documents`

| 条件 | 行为 |
|---|---|
| 有 `q` 或 `tag` | 忽略 `day`，按日+名倒序，`limit`（默认 50，走 `bounded_limit`）+ `offset`，`has_more` |
| 只有 `day` | 只返回该日，不分页 |
| 都没有 | 等同最新一天，响应带上实际 `day` |

响应：`groups`、`items`、`days`、`tags`、`day`（按日模式为实际日期，搜索模式为 `""`）、`has_more`、`offset`。

列表 `items` 不含 `abstract`、`cover_url`。`has_pdf` / `has_txt` 只看 state 里是否有路径，列表不对每份文件 `stat`。`size` 用 state/manifest 数字，不回落到 `pdf.stat()`。

`days` / `tags` 按当前库（管理员「全部」则按可读库）从 manifest + state 标签收集，不按当前搜索词收窄，也不再先跑一遍 `documents()`。

`group_summary`、目录 `attach_catalog_stats` 改为走同一套廉价扫描（份数、最新一天/标题/`media_id`）。目录卡片文案和按钮不变。

详情 `GET /api/ima-documents/{id}` 增加：

- `abstract`：原文
- `abstract_zh`：已缓存译文，没有则为 `""`
- `needs_translation`：原文不是中文，且没有译文，或 `abstract_src_hash` 对不上当前原文（需重译）

## 5. 摘要译成中文

已是中文（沿用 `_already_chinese`）不请求翻译，`needs_translation=false`，页面直接显示 `abstract`。

否则打开阅读页先显示原文，PDF 照常加载；同时 `POST /api/ima-documents/{id}/translate`（需登录且可读该库）。成功后把摘要换成译文。失败保持原文，不挡阅读、不弹错误条。

翻译顺序：

1. 同一套 X Cookie，打现有 `https://api.x.com/2/grok/translation.json`，尝试带原文正文（例如 `content_type=TEXT` + `text` + `dst_lang=zh-cn`），**不传 tweet id**，也不走推文翻译。
2. X 4xx / 空译文 / Cookie 不齐：短摘要（≤500 字）才回退 MyMemory；更长的保留原文。
3. 不加付费 xAI key。

译成功写入该文档 state：`abstract_zh`、`abstract_src_hash`（原文哈希）。原文变更则重译。不在采集流水线里预译。

## 6. 不做

新日历组件、手机阅读页、列表封面、阅读页展示 TXT、采集时预译、付费翻译、改目录订阅/授权、为消双推去动 Unraid。

## 7. 测试

- store：按日只返回该日；搜索/标签 `limit`/`offset`/`has_more`；facets / catalog stats / group_summary 不 `stat` 文件、不依赖完整 `documents()`。
- API：无 `day`/`q`/`tag` 时落到最新一天；列表 item 无 `abstract`；详情带 `needs_translation`。
- 翻译：中文跳过；写入 `abstract_zh`；X 正文尝试；X 失败后短文本走 MyMemory、长文本保留原文。
- 前端字符串：瘦行无 `ima-doc-abstract`；阅读页无 `ima-text-view`、有下载和 PDF 面板；搜索提交清掉 `day`。
