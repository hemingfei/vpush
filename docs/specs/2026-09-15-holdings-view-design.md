# 持股研判页设计

日期：2026-09-15
状态：待确认

## 目标

新增 `/holdings`「持股研判」页：用户维护自己的持股（标的）清单，页面下方持续展示观点研判内容中与其持股相关的观点，窗口为从当前时刻往前滚动的 30 个自然日，当天新观点实时上屏。该页没有快照时间轴与交易日切换，永远呈现最新视图。

术语（用户持股、相关观点、一个月窗口等）以根目录 `CONTEXT.md` 为准。本页「用户持股」与 KOL 雪球组合的「持仓」（`cube_snapshots`、`/api/kols/{id}/holdings`）是两个互不相干的概念。

## 范围与非目标

做：

- 用户持股 CRUD（个股 + 题材，字段：类型、名称、备注）。
- 相关观点查询：按持股分组的多空聚合卡 + 统一时间流（含中性，可展开依据原帖）。
- SSE 实时上屏与增量拉取。

不做（v1）：

- 月度大V分解下钻（谁在多/空某只票）。
- 数量、成本价、盈亏。
- 股票→行业/题材的自动关联（题材需用户手动添加）。
- 对 `posts`、`mx_opinions` 及标签回流的任何写入——用户持股只是用户侧筛选指针。
- miniprogram / mobile 壳适配（契约文档可后续同步 `docs/mobile-parity/api-contracts.md`）。

## 数据模型

新表 `user_holdings`（`app/db.py` SCHEMA，风格对齐 `subscriptions`）：

```sql
CREATE TABLE IF NOT EXISTS user_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    target_type TEXT NOT NULL,            -- 'stock' | 'topic'
    target_name TEXT NOT NULL,            -- 个股存归一化后规范名；题材 trim 后原样
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, target_type, target_name)
);
CREATE INDEX IF NOT EXISTS idx_user_holdings_user ON user_holdings(user_id);
```

约束在应用层执行：

- 每用户上限 **30** 条（POST 超限 → 400）。
- `target_type` 仅允许 `stock`/`topic`。
- 个股名必须命中全市场名单（`stock_universe.bundled_plain_names()` + settings 托管名单，按 `_normalize_name` 归一后匹配；归一化结果作为 `target_name` 落库）。
- 题材名 trim 后非空即可，不设白名单。
- 重复（同 user + type + name）→ 409。

## API 契约

全部挂 `get_current_user`（登录用户各自隔离，无 admin 特权；未登录 401，他人资源一律 404）。

### 持股 CRUD

- `GET /api/my/holdings` → `[{id, target_type, target_name, note, created_at}]`，按 `created_at` 倒序。
- `POST /api/my/holdings` `{target_type, target_name, note?}` → 201 返回新行。校验失败 400（类型/名单/超限/空名），重复 409。
- `PATCH /api/my/holdings/{id}` `{target_type?, target_name?, note?}` → 部分更新（`model_fields_set` 语义，同 news sources PATCH）。改名等同换标的，重走名单/去重校验。
- `DELETE /api/my/holdings/{id}` → 204。仅删该用户自己的行，不触碰任何共享数据。

### 建议（输入自动补全）

- `GET /api/my/holdings/suggestions?type=stock|topic&q=<前缀>` → `{items: [{name, extra?}]}`，上限 20。
  - `stock`：全市场名单按归一化名前缀/包含匹配，`extra` 带代码（`stock_universe.bundled_universe_codes()`）。
  - `topic`：来源为近 90 天 `mx_opinions` 中 `target_type='topic'` 的去重 `target_name`（按出现频次降序）+ `get_topic_hints(db)` 词表（settings 键 `mx_view_topic_hints`），按 q 过滤。**只建议、不强校验**。

### 相关观点（页面主数据）

- `GET /api/my/holdings/views?after_id=&limit=&holder=`
  - `limit` 默认 50、上限 200；`after_id` 增量（语义同 `/api/mx-views/feed`，返回 `max_id`）；`holder` 形如 `stock:贵州茅台` / `topic:AI算力`，只过滤 `items`，不影响 `summary`。
  - 窗口：`occurred_at >= now - 30 天`（SQL 侧按时间过滤）。
  - 响应：
    ```json
    {
      "window_days": 30,
      "max_id": 123,
      "summary": {
        "targets": [
          {"target_type": "stock", "target_name": "贵州茅台",
           "bull": 3, "bear": 1, "neutral": 2, "latest_at": "..."}
        ]
      },
      "items": [
        {"id": 123, "target_type": "stock", "target_name": "贵州茅台",
         "direction": "bull", "action": "加仓", "confidence": 0.8,
         "summary": "...", "occurred_at": "...",
         "kol": {"id": 1, "name": "...", "avatar": "..."},
         "evidence": [{"post_id": 1, "published_at": "...", "content": "...", "kol_name": "..."}]}
      ]
    }
    ```
  - `summary.targets` 全量窗口聚合（一条 `GROUP BY` ），按观点总数降序、`latest_at` 降序；`items` 按 `occurred_at` 降序、`id` 降序，`evidence` 每条观点最多内联 3 条原帖全文。
  - 空态：无持股 → `targets` 为空数组 + `items` 为空，前端展示引导；有持股无相关观点 → 空态文案。

### 实时

复用 `GET /api/mx-views/stream`（版本号 SSE）。新批次落库 `bump_view_version` 后，`/holdings` 页收到 version 事件即带 `after_id=max_id` 增量拉 `/api/my/holdings/views`（响应同时带回重算后的 `summary`），新条目直接插入时间流顶部。SSE 断开兜底 60s 轮询（与 mx-views 页一致）。增删改持股后前端立即重拉 views。

## 前端

### 路由与导航

- 路由 `/holdings`，页面名「持股研判」，手机底栏第 6 项「持股」。
- 同步修改：前端 `NAV`（「订阅」组、观点研判旁）与 `MOBILE_NAV`（`app.js`）、前端 `SPA_PREFIXES`（`app.js`）、后端 `SPA_PREFIXES`（`app/main.py`，防刷新 404）、`router()` 分发分支。

### 页面结构（自上而下）

1. **持股管理区**：持股行列表（类型徽章「股」/「题」+ 名称 + 备注 + 编辑/删除按钮）、添加行（类型切换 + 建议列表输入 + 备注输入 + 添加按钮）、空态引导文案；编辑走小弹窗（名称、备注均可改）。上限 30，达上限禁用添加并提示。
2. **聚合卡区**：每只持股一张卡（名称、净方向色点、多/空/中计数、最新观点时间），横向滚动或网格；点击卡片 ↔ 筛选时间流（再点取消），选中卡高亮。
3. **时间流**：相关观点倒序列表——方向徽章（多红/空绿沿用 mx-views 配色）、标的名、操作词、摘要、KOL 名与时间；点条目原位展开依据原帖全文。「加载更多」按 `limit` 翻页。
4. 实时新条目顶部插入，带一次高亮渐隐。

### 样式

- 新建 `app/static/holdings.css`，整页暗色，视觉 token 与 `app/static/mx-views.css` 对齐；**不改动现有 `mx-views.css`**，避免观点研判页回归。
- `index.html` 新增带内容摘要版本号的 css link（`scripts/bump_assets.py` 维护，CI `--check` 会校验）。
- 新视图按 `docs/frontend-split-convention.md` 工厂模式落 `app/static/views/holdings.js`，内联 onclick 经 `INLINE_HANDLERS` 注册（CI `check_inline_handlers.py` 覆盖）。

## 测试计划

- `tests/test_holdings_api.py`（照 `test_mx_views_api.py` 的 `make_client`/`auth_headers` 模式）：CRUD 全路径；校验（非法类型、个股不在名单、题材空名、超限 30、重复 409）；越权 404；views 的窗口过滤（>30 天不出现）、summary 计数、holder 过滤不影响 summary、`after_id` 增量与 `max_id`、evidence 截断 3 条；suggestions 两类型。
- `tests/test_frontend_holdings.py`（静态回归，照 `test_frontend_mx_views.py`）：路由分发、NAV/MOBILE_NAV 注册、前后端 SPA_PREFIXES、INLINE_HANDLERS、index.html css link 及版本号。
- `tests/test_frontend_runtime.py` 增加真浏览器用例：页面渲染、经 UI 添加/删除持股（fetch 桩）、聚合卡筛选联动、空态。
- **既有断言迁移**：底栏项数从 5 变 6，`test_frontend_mx_views.py` / `test_frontend_runtime.py` 中相关计数与 icon_only 契约表需同步加「持股」行（近期提交刚经历过 4→5→6 同类迁移，模式现成）。

## 影响与回滚

全部为新增（新表、新端点、新视图文件、导航增量），不改任何现有端点与页面行为；唯一共享改动是导航数组与 SPA_PREFIXES 两处数组追加。回滚即移除新增文件与两处数组项。

## 增量：标签快讯接入（2026-09-15）

在 LLM 观点之外，把现有标签体系作为第二条信号源接入本页（只读 `posts.tags`，仍不写任何共享数据）：

- **命中口径**：`posts.tags` 精确含标的名（JSON 元素边界匹配，与动态页标签筛选同源；规则/LLM/观点回流打标都落这一列）。多空方向角标取观点回流登记（`attach_view_directions`）。
- **API**：`GET /api/my/holdings/tag-posts`，与 `/views` 同参语义（`after_id` 增量 / `before_id` 翻页 / `holder` 下钻，`summary` 恒全量）；`max_id` 用全局 `max_post_id_any()` 水位（未命中标的的帖也推进游标）。聚合为 `holdings_tag_post_summary`（单次扫描，每标的一对 `SUM/MAX(CASE … LIKE …)` 列）。
- **前端**：流区改双页签——「观点」（原相关观点流）/「快讯」（标签命中帖，同一 `mxv-feed-item` 行网格，行尾「全文」展开原帖正文）；两条流统一按天分段、单列一行一条消息（观点流分组键由「交易日+批次」收敛为按天，分隔行不再带快照时刻）；**聚合卡与观点研判「大V观点总览」按个股卡同构**（`mxv-stockcard`：标的名前缀股/题徽章 + N 大V + 操作词统计 + 多/中/空占比条 + 三行去重大V名单，卡区改 auto-fill 网格，`--mxv-*` 变量注入提升到 `.hd-root` 作用域），卡名行追加 `#N 帖`（近 30 天标签提及）。
- **总览卡数据**：`summary.targets` 附带 `kols`（去重大V口径：总数 + 各方向计数与名单，名单按该标的观点数降序截前 12、计数不受截断影响；同大V跨方向只计一次）与 `actions`（操作词 × 次数，按次数降序、词序稳定）；同大V同方向被 action 维度拆组时在聚合层合并。
- **实时**：新帖入库不 `bump_view_version`，快讯到账靠恒开 60s 兜底轮询（SSE version 事件仍同时增量拉两条流）。
