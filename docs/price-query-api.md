# 股价查询 API 设计文档（v1）

> 面向实现方：定义一套供 vpush 调用的 A 股股价查询 HTTP API，服务于「大V预估盈亏」功能——
> 把大V公开发言中的操作事件（建仓/加仓/减仓/清仓）锚定到股价：事件时刻价作预估成本/卖价，最新价算浮动盈亏。
> §2.1 的时刻价规则是实现正确性的关键，其余皆常规。

## 1. 背景与调用量级

- 只查 A 股个股（沪深必选；北交所可选）
- **历史时刻价不可变**：同一 (code, at) 任何时间查询结果相同，可无限期缓存
- 最新价随行情变化：调用方自带 5 分钟 TTL 本地缓存
- 量级：单次页面打开触发一次批量（≤50 item），日均千 item 级；单笔查询主要留给调试与低频场景

## 2. 接口定义

### 2.1 核心语义：时刻价规则（一条规则覆盖全部边界）

**返回「不超过 at 时刻」的最近一个有效成交价格，并返回该价格实际形成的时刻 actual_at。**

关键约束：**不使用任何 at 之后的价格（无未来信息）**。落地到各时段：

| at 落点 | price 取值 | kind |
|---|---|---|
| 连续竞价 09:30-11:30 / 13:00-15:00 | at 分钟或之前最后一笔成交 | trade |
| 开盘集合竞价 09:15-09:25 | 前一交易日收盘价（当日尚无成交） | close |
| 09:25-09:30 | 当日开盘价（09:25 撮合产生） | auction |
| 午间休市 11:30-13:00 | 当日上午最后一笔成交 | trade |
| 收盘后 15:00 之后 | 当日收盘价 | close |
| 非交易日（周末/节假日） | 之前最近交易日的收盘价 | close |
| at 当日停牌 | 停牌前最近有效价格（可能跨交易日） | 同上 |

停牌（含长期停牌）**不报错**：best-effort 返回最近有效价 + 如实的 actual_at，由调用方按 actual_at 距 at 的远近决定是否采纳。

### 2.2 单笔查询

`GET /api/v1/price?code=sh600519&at=2026-09-01T09:16:00`

参数：

- `code` 必填。交易所前缀 + 6 位数字：`sh` / `sz` / `bj`
- `at` 可选。北京时间 `YYYY-MM-DDTHH:MM:SS`（无时区后缀，服务端按北京时间解释；必须含时间部分）。**省略 = 查最新价**

响应 `200`：

```json
{
  "code": "sh600519",
  "name": "贵州茅台",
  "at": "2026-09-01T09:16:00",
  "price": 1450.00,
  "actual_at": "2026-08-31T15:00:00",
  "kind": "close"
}
```

字段：

- `price`：float，A 股两位小数（最多接受 4 位）
- `actual_at`：price 实际形成时刻（取前收则为前收日 15:00:00；最新价为最后成交/收盘时刻）
- `kind`：`trade` / `close` / `auction`，推荐提供（可缺省）
- `name`：证券简称，推荐提供（调用方用于校验代码映射）

### 2.3 批量查询

`POST /api/v1/prices`，请求体：

```json
{
  "items": [
    {"code": "sh600519", "at": "2026-09-01T09:16:00"},
    {"code": "sz300750"},
    {"code": "sh999999"}
  ]
}
```

- 单次 ≤ 50 item，超出整单 400；items 空也 400
- item 内 `at` 可省略（该 item 查最新价）；同一 (code, at) 允许重复
- **逐 item 独立成败**：整体 HTTP 200，失败在 item 内表达，不得因单项失败拖垮整单
- 响应 items 顺序与请求一一对齐

响应 `200`：

```json
{
  "items": [
    {"code": "sh600519", "at": "2026-09-01T09:16:00", "status": "ok",
     "name": "贵州茅台", "price": 1450.00, "actual_at": "2026-08-31T15:00:00", "kind": "close"},
    {"code": "sz300750", "status": "ok", "name": "宁德时代",
     "price": 188.55, "actual_at": "2026-09-18T10:47:12", "kind": "trade"},
    {"code": "sh999999", "status": "error", "error": "unknown_code"}
  ]
}
```

### 2.4 时刻价规则与 kind 的参考实现（伪代码）

```
price_at(code, at):
  bar = 分钟线上「时间 <= at」的最后一根有成交的 K 线     # 跨日/停牌向前回溯
  if bar 存在且 bar.日期 == at.日期:
      if at < 09:25:  前一日收盘价, kind=close           # 开盘集合竞价期无当日成交
      elif at < 09:30: 当日开盘价, kind=auction           # 09:25 撮合已产生开盘价
      else: bar.close, kind=trade
  else:
      最近交易日的收盘价, kind=close                      # 非交易日/停牌/盘前
  actual_at = 所取价格的形成时刻
```

## 3. 错误模型

HTTP 层（整单失败）：400 参数格式错（code 非法 / at 格式错 / items 超 50 或空）；401 token 无效；429 限流；5xx 内部错误。

item 层（批量内单项失败，`status: "error"`）：

- `unknown_code`：代码不存在，或前缀不支持（如未实现 bj）
- `no_data`：at 早于该证券任何可得价格（如上市前）

## 4. 非功能约定

- 鉴权：`Authorization: Bearer <token>`，HTTPS
- 时间口径：一律北京时间，格式 `YYYY-MM-DDTHH:MM:SS`
- 限流：调用方承诺 ≤ 10 req/s（批量摊薄后实际更低）
- 延迟：历史查询 P95 < 1s；最新价允许 ≤ 1 分钟延迟
- 幂等/可缓存：GET 幂等；(code, at) 历史查询结果永久不变，可被任意中间层透明缓存；仅「最新价」（无 at）会变
- 数据覆盖：沪深 A 股全量、上市以来全部历史（至少 2 年）；北交所可选

## 5. 调用方接入示例（联调参考）

打开大V盈亏页 → 收集其 30-90 天窗口内全部事件 (code, occurred_at) + 在持股最新价 → 去重 → 1 次 POST /api/v1/prices → 历史项写本地永久缓存，最新价项 TTL 300s。

## 6. 已接入实现：tickflow-stock-panel（2026-09）

当前生产实现是 tickflow-stock-panel（同机 docker，`0.0.0.0:3018`），其仓库
`docs/price-query-api.md` 是该实现的适配契约（价格口径：不复权原始价；北交所按
`unknown_code`；本地无分钟K的交易日降级为日线边界）。联调实测要点：

- **最新价 item 必须整体省略 `at` 字段**：发空串 `"at": ""` 会被服务端按
  at 格式非法拒 400（整批失败）。vpush 侧 `fetch_remote` 已按此构造请求体。
- token 在 tickflow 侧生成（`POST /api/v1/token` 面板登录态调用，存其
  `data/user_data/secrets.json` 的 `vpush_api_token`；未配置时端点一律 401）。

vpush 侧接入配置（config.yaml 或环境变量，两者均填才生效，半套即桩模式）：

```yaml
price_api_base: "http://host.docker.internal:3018/api/v1"
price_api_token: "<tickflow 生成的 token>"
```

- 生产 docker（自定义网络 `dav`）：vpush 容器访问同机宿主机端口用
  `host.docker.internal`（`docker-compose.prod.yml` 已配 `extra_hosts:
  host-gateway`），不要用 `127.0.0.1`（那是容器自身）。
- 环境变量 `PRICE_API_BASE` / `PRICE_API_TOKEN` 由 `.env` 注入（compose
  `env_file`），`PRICE_API_BASE` 形如 `http://host.docker.internal:3018/api/v1`。
- 两者留空（或只填其一）即桩模式：盈亏页显示「行情数据未接入」。
