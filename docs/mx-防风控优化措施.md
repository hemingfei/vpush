# MX 平台防风控优化措施总结

> 更新时间：2026-09-02
> 背景：MX 账号因检测到爬取行为被封号。本文档汇总 vpush 项目针对 MX 平台（`app/fetchers/mx/`、`app/scheduler.py`、`app/services/mx_sync.py`）完成的全部防风控改造。

## 一、问题根因（为什么会被检测到）

封号前存在以下暴露面，按严重程度排序：

| # | 问题 | 位置 | 风控可见的信号 |
|---|------|------|----------------|
| 1 | HTTP 与 WS「双人格」 | `client.py` | 同一 token：WS 是 Chrome 浏览器，HTTP 是 `python-httpx/0.x` 裸 UA、无 Origin/Referer |
| 2 | 全量房间顺序轮询 | scheduler | 每 60~180 秒把所有房间 rid 扫一遍，24/7 不停（146 房间 ≈ 8760 次/小时） |
| 3 | 异常大 limit | `client.get_rooms` | ~~limit=1000000 是机器人实锤~~ **2026-09-02 抓包推翻：官方冷启动就是单次 limit=1000000**（见 `mx-官方网页端抓包核对-2026-09-02.md`） |
| 4 | 固定周期节拍 | scheduler | 精确 60/180 秒、每小时整点同步，时间轴上是完美周期信号 |
| 5 | WS 在线还全量 HTTP 轮询 | scheduler | 真人网页端：WS 收推送 + 只拉当前打开的房间 |
| 6 | 被踢后 5 秒硬重连 | `ws.py` | 高频无上限重连是攻击性特征，会把「踢下线」升级成「封号」 |
| 7 | 死 token 继续打 | scheduler | 600 秒退避后永远重试，持续加重风控记录 |
| 8 | 图片下载假 Referer | `avatar_cache.py` | MX 域名图片带着 `Referer: https://weibo.com/` 下载 |
| 9 | 机房 IP + 共享工具指纹 | 部署层 | 「同 token + 新 IP + 异常流量」强关联；`chat-monitor` 类工具的特征库 |

## 二、措施总览

改造后的流量模型：**常态接近零 HTTP 请求**——窗口内靠 WS 实时推送，房间列表每天 2-4 次随机同步，每 20-200 分钟一次单房间兜底，其余全部手动触发。

| 层面 | 措施 | 实现位置 |
|------|------|----------|
| 架构 | 取消自动轮询，WS 推送为主 | `scheduler.poll_once` 跳过 mx |
| 架构 | 每日一次单房间兜底拉取（随机预约时刻，防 WS 假死） | `scheduler._mx_maybe_daily_fallback` |
| 架构 | 消息/房间拉取全部手动触发 | 每房间「拉取历史消息」按钮 + 设置页「登录」按钮（开窗式启动序列，含房间同步） |
| 窗口 | 每日三段随机时段：7-8 开~11:40-12:00 关、12:30-12:50 开~16-16:30 关、19-19:30 开~21-22 关 | `app/services/mx_window.py` |
| WS | 断线只重连一次（16-36 秒随机延时后），失败永久放弃 | `ws.run_forever` |
| WS | TOKEN 过期不重试，立即放弃 | `ws._looks_like_auth_failure` |
| WS | 指数式自我封锁：gave_up 状态 + 手动接入复位 | `ws.py` / `fetcher.get_ws_status` |
| TOKEN | 2 天强制更换提醒 + 过期熔断 | `scheduler._mx_check_token_age` / `MXTokenExpiredError` |
| 特征 | 房间列表官方形态单次全量（limit=1000000，2026-09-02 抓包对齐） | `client.get_rooms` |
| 特征 | 房间同步挂到开窗动作：每次开窗拉一次（与官方「打开网页必拉一次」一致），无后台周期任务 | `scheduler._mx_session_start` |
| 特征 | HTTP 请求头与 WS 同形 | `client._headers` |
| 特征 | **TLS 指纹（JA3/JA4）+ HTTP/2 + 头序对齐 Chrome**（curl_cffi impersonate） | `client.py`（`ws.py` 人格常量） |
| 特征 | WS 握手头补齐 Chrome WebSocket 特征（Pragma/Cache-Control、客户端提示） | `ws._browser_handshake_headers` |
| 特征 | 房间同步复用同一 HTTP 连接，不再每次新建 TLS 握手 | `mx_sync._get_client` |
| 特征 | MX 图片走 MX 站点头（去掉 weibo Referer） | `avatar_cache.headers_for` |
| 告警 | 所有报错统一走系统 KOL「系统通知」 | `scheduler.publish_mx_error` |

## 三、分层详解

### 1. 架构改造：WS 为主，HTTP 只做兜底（收益最大）

- **自动轮询完全取消**：`scheduler.poll_once` 显式跳过 `platform == "mx"` 的所有大V，平时不产生任何 MX HTTP 请求。WS 推送的消息本身就是全量的，直接入库推送。
- **每日一次兜底拉取**（`_mx_maybe_daily_fallback`，2026-09-02 由「每 20-200 分钟一次」收紧）：每天生成窗口时随机预约一个时刻（离关窗 ≥1 分钟），到点且会话存活才拉 **1 个随机启用房间**的最新消息（复用 `fetcher.fetch`，含有限追平）；错过或会话未存活当天放弃，绝不补打。防 WS 静默假死的同时把兜底量级压到最低。
- **手动触发是唯一主动入口**：
  - 每房间「拉取历史消息」按钮 → `POST /api/admin/sources/mx/rooms/{room_id}/pull-history`，只拉**最新 100 条**（单次请求，不再无限翻页）；
  - （2026-09-02：房间列表同步已并入设置页「登录」按钮的开窗启动序列，独立的「立即同步房间」按钮与端点已移除。）
- **量级对比**：改造前 146 房间 × 60 秒 ≈ 8760 次/小时 + 每小时百万 limit 房间列表；改造后常态 0，每天约 2-4 次房间列表 + 1 次单房间兜底。

### 2. 每日运行窗口（`app/services/mx_window.py`，2026-09-02 起为每日三段）

- **早市**：7:00-8:00 之间随机开启，11:40-12:00 之间随机关闭；**午后**：12:30-12:50 随机开，16:00-16:30 随机关；**晚间**：19:00-19:30 随机开，21:00-22:00 随机关。窗口外零请求。
- 随机值每天重新生成（`generate_mx_daily_windows`），重启服务会重新生成，可接受。
- **每个窗口只尝试启动一次会话**（`_mx_window_loop`）：启动失败或 WS 放弃后不再自动拉起——窗口循环自己绝不制造重连流量；恢复靠换 TOKEN 或下个窗口/次日窗口。三段窗口意味着 WS 连接尝试最多 3 次/天（「每天上线三次」本就比「一次挂 9 小时」更像真人）。
- **重启安全（2026-09-02）**：服务重启后**不自动续连**——生成窗口时，开窗时刻已过（重启前就错过）的窗口当天「不武装」，不会自动开启；只能管理员在后台点「登录」手动拉起，或等下一个尚未到点的窗口到点自动触发。启动日志会标注错过的段。
- **晚间兜底强关（2026-09-02）**：23:30-23:35 之间随机一秒，若 MX 仍在线（如手动登录后忘关，无论会话来源是自动还是手动）一律强制关闭（关标签页式 abort）——正常三段窗口最晚 22 点前已关窗，这是防「人走了页面还开着」的最后保险，当天只执行一次。
- 房间列表同步由开窗动作触发（见第一节），窗口外启动/重启服务不会产生任何 MX 请求。
- 管理员仍可在后台手动接入/断开 WS（窗口策略优先：关窗后手动会话也会被停止；手动拉取历史不受窗口限制，因为是管理员明确点按钮）。

### 3. WS 重连策略（`app/fetchers/mx/ws.py`）

- **断线后只重连一次**：等待 **16-36 秒随机**延时（`_reconnect_delay`，2026-09-02 由固定 12 秒改为区间随机——固定周期重连节拍本身是机器信号）重连一次；重连成功则恢复额度（下次断线仍有一次机会）；**重连再失败就永久放弃**（`gave_up` 置位），不再发出任何连接请求。
- **TOKEN 过期零重试**：连接阶段被拒且错误形似鉴权失败（401/403/unauthorized/token/登录/认证/过期/无效）→ 不等待、不重试，立即放弃并告警。
- python-socketio 内部重连保持禁用（`reconnection=False`），重连完全由自己的策略控制。
- 恢复路径：管理员后台「登录」按钮（新建客户端、状态自动复位），或换 TOKEN 后下个窗口自动恢复。
- 状态透出：`/api/admin/sources/mx/ws-status` 返回 `connected` / `last_message_at` / `gave_up` / `detail`，设置页直接显示「自动重连失败已停止，请手动接入」等文案。

### 4. TOKEN 管理（每 2 天强制更换）

- **时效提醒**：TOKEN 使用超过 2 天（`mx_token_updated_at` 设置项记录起用时间），系统通知 KOL 发布更换提醒；2 天节流期内不重复提醒。
- **过期熔断**：新增 `MXTokenExpiredError` 专用异常（`client.py`），WS 连接被拒或 HTTP 拉取遇到 token 失效响应时置 `_mx_token_expired` 熔断标记——**所有拉取与连接全部暂停**，避免死 token 继续打把处罚从「踢下线」升级成「封号」。任何链路发现过期都走统一入口 `_mx_trigger_token_expired`：熔断的同时**立即掐断 WS**（关标签页式 abort，不发关闭包，线程中触发也能投递回调度循环）——不会出现「接口已报过期、WS 还挂在死 token 上」的中间态（2026-09-02 补强）。
- **自动恢复**：后台保存新 TOKEN（值发生变化）时自动重置 2 天计时并解除熔断/放弃标记，无需重启。

### 5. 请求特征修正（消灭「一眼假」）

- **TLS/HTTP 指纹对齐 Chrome（2026-09 二次加固，收益最大的残留项）**：只补 UA 头挡不住
  「Chrome UA + Python TLS」的 JA3/JA4 与 UA 一致性校验，也挡不住 httpx 的 HTTP/1.1、
  `accept-encoding: gzip, deflate`（无 br/zstd）、缺失 `sec-ch-ua`/`sec-fetch-*` 这些
  底层特征。`MXClient` 已整体切换到 `curl_cffi.Session(impersonate="chrome146")`：
  TLS 指纹、HTTP/2、头序、UA/客户端提示全部与 Chrome 对齐，`_headers` 只覆盖 XHR 与
  导航请求的差异项（`accept` 用 axios 形态、`sec-fetch-site/mode/dest`、用
  `None` 删除导航特有头）。curl_cffi Session 默认按线程隔离底层 curl 句柄，无状态
  token API 可跨线程共享。
- **人格常量单一来源**：`ws.py` 顶部集中定义 `IMPERSONATE_TARGET` / `BROWSER_UA` /
  `SEC_CH_UA*` / `ACCEPT_LANGUAGE`（UA/提示取 chrome146 模板实测值），HTTP、WS 握手、
  图片下载三处共用；`tests/test_mx.py` 的 `test_persona_constants_are_consistent` 锁定
  主版本一致，`test_http_wire_persona_matches_ws_persona` 用本地回环服务锁定线上实际
  发出的头与 WS 握手同一人格。**改任何一处人格常量都要三处同步。**
- **房间列表官方形态（2026-09-02 修订）**：抓包实测官方冷启动就是单次
  `{"pages":1,"limit":1000000}` 全量——该参数官方自己就发，无罪；曾改为 100/页
  （`ROOM_PAGE_SIZE`）逐页翻，现已恢复官方单次全量形态（既同形又把每次同步从最多
  50 个请求降到 1 个）。详见 `mx-官方网页端抓包核对-2026-09-02.md`。
- **同步挂到开窗动作（2026-09-02）**：房间列表同步不再有后台周期任务，改为每次开窗（= 真人打开网页）时拉一次，每窗口最多 1 次（≤3 次/天）；`SYNC_MIN/MAX_INTERVAL_SECONDS` 与 `start_periodic_sync` 已整体移除，原 `sync_interval_hours` 配置项更早前已移除，避免留下无效旋钮。
- **房间同步复用连接**：`MXRoomSyncService` 持有同一个 `MXClient`（`_get_client`），不再
  每次同步新建 TLS 连接——同指纹的重复握手在风控日志里是可聚合计数的行为；`stop()` 统一关闭。
- **WS 握手头补齐**：`_browser_handshake_headers` 补齐 Chrome WebSocket 握手的
  Pragma/Cache-Control、`Accept-Encoding: gzip, deflate, br, zstd`、Accept-Language、
  sec-ch-ua 客户端提示和 sec-fetch-* fetch 元数据（按 fetch spec：WS 的 mode 为
  `"websocket"`、dest 为空串、同域 site 为 `same-origin`——早期版本误以为 Chrome 的
  WS 握手不带 sec-fetch-*，实际缺了才是区分特征）；UA 显式覆盖 aiohttp 的
  「Python aiohttp/x」默认值。WS 底层 TLS 仍是 aiohttp/Python 指纹，但一天只
  连一次，量级上风险可接受（彻底解决需 curl_cffi WebSocket + 自写 engineio 层，性价比低）。
- **图片/头像下载修正**：`avatar_cache.headers_for` 新增 MX 域名（`naaifu.cn`）分支——MX 浏览器 UA + MX 站点 Referer；之前 MX 图片错误地带 `weibo.com` Referer，在 MX 自家 CDN 日志里又是一个假信号。
  已评估并**保留 httpx 下载**：SSRF 防护（`url_safety.safe_get` 的逐跳固定 IP + SNI 校验）
  与 httpx 深度耦合，curl_cffi 0.16 的 requests 层不支持 per-request RESOLVE，重写
  SSRF 层的复杂度与回归风险大于 CDN 指纹收益——CDN 是最弱的检测面，且频率低。
- **拉取历史上限**：手动拉取只取最新 100 条、单次请求，不再最多 100 页×50 条地深翻历史。

### 6. 报错统一告警：系统通知 KOL

- 新建专门的系统平台账号「**系统通知**」（`platform=system`，`external_id=system_alert`），自动创建、无需 webhook token/签名。
- **所有 MX 报错统一走它发布**（入库 + 实时推送，与正常发帖同链路，复用免打扰/次要缓冲/重试队列）：
  - WS 断线重连失败（永久放弃时）；
  - TOKEN 过期（WS 被拒 / HTTP 拉取失败时）；
  - 会话启动失败（窗口开启但 WS 启动报错）；
  - 兜底拉取失败（区分 TOKEN 过期与一般错误）；
  - 房间同步失败（`MXRoomSyncService.on_error` 回调）；
  - 手动拉取历史失败（api 层 `on_mx_alert` 回调）；
  - TOKEN 超 2 天的更换提醒。
- 同类错误 30 分钟节流（`_cooldown_ok`，按 key 区分），避免告警刷屏；TOKEN 过期类告警同时触发熔断标记。
- **要收到推送请在后台订阅「系统通知」**；未订阅时消息仍会入信息流。

## 四、改动文件清单

| 文件 | 改动 |
|------|------|
| `app/fetchers/mx/ws.py` | 重连策略（12 秒一次/永久放弃/TOKEN 过期零重试）、gave_up 状态、give-up 回调；人格常量集中定义（`IMPERSONATE_TARGET`/`BROWSER_UA`/`SEC_CH_UA*`，chrome146）、WS 握手头补齐 Chrome WebSocket 特征 |
| `app/fetchers/mx/client.py` | **HTTP 层切换 curl_cffi impersonate（TLS/JA3/H2/头序对齐 Chrome）**、XHR 形态头覆盖与导航头删除、`MXTokenExpiredError`、session 注入（测试用） |
| `app/fetchers/mx/fetcher.py` | `start_ws` 透传 give-up 回调；`get_ws_status` 暴露 gave_up |
| `app/scheduler.py` | poll_once 跳过 mx；窗口管理循环；兜底拉取循环；TOKEN 时效/熔断；`_publish_system_alert` / `publish_mx_error`；手动 WS 控制透传回调 |
| `app/services/mx_window.py` | 新增：每日随机窗口生成与判定 |
| `app/services/mx_sync.py` | 随机 2-6 小时间隔；`on_error`/`should_run` 门控回调；**复用同一 `MXClient`，`stop()` 统一关闭** |
| `app/api.py` | 拉取历史限 100 条；`on_mx_alert` 接线；WS 接口文案；移除 sync_interval_hours |
| `app/main.py` | `on_mx_alert=scheduler.publish_mx_error` 接线 |
| `app/avatar_cache.py` | MX 域名图片请求头分支 |
| `app/config.py` | 移除 `sync_interval_hours` 字段与 `MX_SYNC_INTERVAL_HOURS` 环境变量映射 |
| `app/static/app.js` | WS 状态展示；移除同步间隔输入框 |
| `tests/test_mx.py` | 重连策略/窗口/告警/熔断/分页/请求头等契约测试；**新增线上人格（curl_cffi 实测）、WS 握手人格、人格常量一致性、同步客户端复用** |

## 五、运维配套（代码管不住的部分）

1. **只订阅真看的房间**——订阅数决定暴露面量级。
2. **IP 类型比「固定 IP」更重要**：优先部署在家庭宽带（如 Unraid/NAS），机房 IP
   （尤其境外 VPS）叠加「中国站 + 无手机端活跃」本身就是高权重风控信号——换了新
   token 也会很快再被标记。多实例不要共用同一个 token。
3. **换新号后低量爬坡**：IP 与行为指纹大概率已在风控记录，先按默认窗口跑几天再逐步放开。
4. **订阅「系统通知」KOL**，TOKEN 提醒和一切报错都从这里出来；TOKEN 到期及时手动更换。
5. **换 TOKEN 的取号环境要分散**：不要每次都从同一台设备/同一网络环境重新登录取 token。

## 六、遗留事项与残留风险（2026-09-02 更新）

- ~~**抓包核对清单**~~：**五项已全部核对完成并关闭**（2026-09-02 全量抓包 +
  逐项落地，详见 `mx-官方网页端抓包核对-2026-09-02.md` 与本文件第八节）：
  1. WS 握手：官方为 **websocket 直连**（无 polling 升级），与现实现一致；
  2. WS 连上后官方**不 emit 任何业务事件**，「只听不说」一致；
  3. **不存在 sign 类签名**（认证仅 `token` 头），无需逆向、该项直接关闭；
  4. 头形态差异（`accept`/`ad`/`i`/`priority`）已全部对齐；
  5. 官方网页端为桌面 Chrome 人格，与现实现（桌面 Chrome146，curl_cffi 模板上限）一致合理。
  后续按 `mx-定期抓包巡检手册.md` 每 2-3 天巡检一次，防止平台改版产生新差异。
- **图片/头像下载保留 httpx**：（仍未变）SSRF 防护与 httpx 深度耦合（见「请求特征修正」），
  CDN 是最弱检测面，暂不引入 curl_cffi 重写。
- **WS 底层 TLS 仍是 Python 指纹**：（仍未变）改三段窗口后每天最多 3 次连接（每窗口一次），
  量级仍可接受，详见「请求特征修正」。
- **兜底追平的量级**：（进一步收敛）`fetcher.fetch` 消息突发时最多向后追 3 页
  （`BACKFILL_PAGES=3`）不变；兜底本身已从「每 20-200 分钟一次」收紧为「每天最多 1 次」。
- **本质风险仍在**：（永真）MX 的 API 加密密钥按日期派生（`crypto.generate_key`），说明平台是有意防爬的。以上措施把流量压到真人量级、消除显眼特征，是**显著降低风险**，不是消除风险。长期稳定要么找平台要授权接口，要么接受偶发封号、换号换 TOKEN 的运营成本。

## 七、验证

- `tests/test_mx.py` 全量通过（57 个用例，含重连策略、TOKEN 过期零重试、分页、请求头、随机窗口边界、告警节流、熔断标记、2 天提醒，以及二次加固新增的线上人格实测/WS 握手人格/常量一致性/同步客户端复用等契约测试）。
- 线上人格实测：本地回环 HTTP 服务捕获 curl_cffi 实际发出的请求，UA 逐字节等于 `BROWSER_UA`、客户端提示一致、导航特有头已删除、无重复头。
- 全量测试套件与改动前 HEAD 基线逐项对比：失败集合完全一致（均为 Windows symlink/网络类存量环境问题），本次改造零回归。

## 八、2026-09-02 抓包核对修订（已落地）

用真实账号人工登录官方网页端抓包逐项核对（详见 `mx-官方网页端抓包核对-2026-09-02.md`），
按实测对齐以下实现（`tests/test_mx.py` 59 例全部通过）：

| 改动 | 实测依据 |
|------|---------|
| HTTP 头补 `ad: true`、`i: qq`（前端写死的常驻渠道标记，登录前请求即携带、与账号无关） | 两账号 + 登录前请求实测一致 |
| `accept` 改为 `*/*`（官方是 fetch 默认形态，不是 axios 默认值） | wire 级请求头实测 |
| WS 地址默认改为 `wss://mx.2026.naaifu.cn/business-api/5`（官方实际连 `{api_base}/socket.io/`） | WS 握手 URL 实测 |
| `get_rooms` 恢复官方单次 `limit=1000000` 全量（推翻本文件旧的「机器人实锤」判断） | 两个账号冷启动实测一致 |
| `page_size` 默认 50 → 30（官方 `msg/list` 实测 pagesize=30） | 请求体实测 |
| 拉取消息前先发 `room/view {rid,tt}` 进房上报（官方每次打开房间都先发；失败不阻断拉取，TOKEN 过期照常上抛熔断） | 进房行为链实测 |
| 确认无需改动：websocket 直连、`/msg` 命名空间、auth 载荷 `{tt,token,version:"web"}`、「只听不说」、无 sign 签名、服务器 ping/客户端 pong 心跳 | 全部与现实现一致 |

注意：**已保存过配置的部署不会被新默认值覆盖**，需在后台「数据源 → MX」把 WebSocket 地址
更新为 `wss://mx.2026.naaifu.cn/business-api/5`。

## 九、2026-09-02 调度策略修订（多窗口 / 兜底限频 / 重连随机化）

按运营方要求对运行节奏二次收紧（`tests/test_mx.py` 61 例全部通过）：

| 改动 | 修订前 | 修订后 |
|------|--------|--------|
| 运行窗口 | 单窗口：7-8 点随机开、16-17 点随机关 | **三段窗口**：7-8 开~11:40-12:00 关、12:30-12:50 开~16-16:30 关、19-19:30 开~21-22 关（各段开/关时刻每天独立随机生成） |
| 兜底拉取 | 窗口内每随机 20-200 分钟拉 1 个随机房间（每天若干次） | **每天最多 1 次**：生成窗口时随机预约时刻（离关窗 ≥1 分钟），到点且会话存活才拉 1 个随机房间；错过或会话未存活当天放弃不补打 |
| WS 重连延时 | 断线后固定 12 秒重连一次 | **16-36 秒随机**（固定周期的重连节拍本身是机器信号） |

附注：
- 三段窗口后 WS 连接尝试从每天 1 次变为**每窗口 1 次（最多 3 次/天）**——「每天上线三段、
  每段两三个小时」比「一次挂 9 小时」更像真人；「断线只重连一次、放弃不自动拉起」纪律不变。
- （房间同步当轮未改，随后在同日第十节修订中改为开窗触发。）
- 改动文件：`app/services/mx_window.py`（重写）、`app/scheduler.py`（窗口/兜底编排）、
  `app/fetchers/mx/ws.py`（重连延时）、`tests/test_mx.py`（61 例契约）。

## 十、2026-09-02 房间同步改为开窗即拉

抓包实测：官方网页端每次「打开应用」（无论手动输密码登录，还是本地 token 自动登录，
甚至仅刷新页面）都会拉一次房间列表，会话中途不再重拉——「打开一次网页 = 拉一次房间列表」。

据此把房间同步从「每轮随机 2-6 小时且窗口内执行」改为**挂到开窗动作上**：
`_mx_session_start` 先同步一次房间列表、再连 WS，每窗口最多 1 次（≤3 次/天）；
TOKEN 熔断时开窗不同步。`MXRoomSyncService` 的后台周期任务（`start_periodic_sync`、
`SYNC_MIN/MAX_INTERVAL_SECONDS`、`on_error`/`should_run` 挂点）整体移除；
设置页按钮随后整合为「登录 / 退出」两个（见第十二节）。`tests/test_mx.py` 当轮 63 例全部通过。

## 十一、2026-09-02 开窗补发官方启动序列（消灭「会话无初始化」特征）

`user/info`、`system/config`、`msg/tip`、`room/grouplist`、平台 `notice` 是官方网页端
每次打开页面必发的只读启动调用，此前 vpush 从不触碰——请求头是完整 web 人格却从不做
web 初始化，是「会话建模」层面最后一类可识别差异。现于 `_mx_session_start` 按官方顺序
补发（`MXRoomSyncService.boot_sequence` → `client.user_info/system_config/msg_tip/
room_grouplist/master_notice`，同一复用连接）：

```
开窗 → user/info → system/config → room/list(同步) → msg/tip → grouplist → notice → WS
```

- 全部只读、无业务副作用；单条失败只记日志不阻断，TOKEN 过期向上抛出触发熔断告警；
- `user/info` 返回内含服务端当前 token：与本地配置不一致即记告警日志（服务端可能已
  轮换，提前发现而不是等 401）；
- `issign`/`showad`/`member-ai` 请求体未采集，不猜格式硬发（留待巡检抓到再补）；
- `login`/`code` 属人工取号流程，永远不自动调用（红线）。
- `tests/test_mx.py` 65 例全部通过。

## 十二、2026-09-02 后台按钮整合：登录 / 退出 + 接口状态

设置页 MX 面板的「测试连接 / 立即同步房间 / 主动连接 / 关闭连接」四个按钮全部移除，
整合为两个：

- **登录**：不受窗口限制的完整开窗动作——官方冷启动序列 → 房间同步 → 连接 WS；
  逐接口结果（成功/失败、耗时、摘要如「账号 xxx」「129 个房间」「总未读 n」）在
  「接口状态」面板展示，并计入 `/ws-status` 的 `login_report`（刷新页面不丢）；
  窗口内的手动登录会标记本窗口会话已开启，避免窗口循环重复拉起。
- **退出**：模拟用户直接关闭标签页——不做任何关闭握手（不发 socket.io `41` /
  engine.io CLOSE 包 / WS Close 帧），直接掐断底层 TCP 连接（服务端只会看到
  transport close）；窗口到点的自动关窗同理。窗口循环到点自动停止其余链路。
  实测佐证（CDP 帧级监听 + 页面刷新拆旧连接）：拆连瞬间出站数据帧为**零**
  （无 41/CLOSE），捕获到的只有新连接的握手帧——浏览器的退出就是「连接消失」。

WS 状态展示保留；「接口状态」默认显示最近一次登录报告。删除端点：
`POST /admin/sources/mx/test`、`POST /admin/sources/mx/rooms/sync`；新增端点：
`POST /admin/sources/mx/session/login`。`tests/test_mx.py` 67 例全部通过。
