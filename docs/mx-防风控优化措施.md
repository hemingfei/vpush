# MX 平台防风控优化措施总结

> 更新时间：2026-09-02
> 背景：MX 账号因检测到爬取行为被封号。本文档汇总 vpush 项目针对 MX 平台（`app/fetchers/mx/`、`app/scheduler.py`、`app/services/mx_sync.py`）完成的全部防风控改造。

## 一、问题根因（为什么会被检测到）

封号前存在以下暴露面，按严重程度排序：

| # | 问题 | 位置 | 风控可见的信号 |
|---|------|------|----------------|
| 1 | HTTP 与 WS「双人格」 | `client.py` | 同一 token：WS 是 Chrome 浏览器，HTTP 是 `python-httpx/0.x` 裸 UA、无 Origin/Referer |
| 2 | 全量房间顺序轮询 | scheduler | 每 60~180 秒把所有房间 rid 扫一遍，24/7 不停（146 房间 ≈ 8760 次/小时） |
| 3 | 异常大 limit | `client.get_rooms` | `limit=1000000` 拉房间列表，单条日志就是机器人实锤 |
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
| 架构 | 随机单房间兜底拉取（防 WS 假死） | `scheduler._mx_fallback_loop` |
| 架构 | 消息/房间拉取全部手动触发 | 每房间「拉取历史消息」+「立即同步房间」按钮 |
| 窗口 | 每日 7-8 点随机开、16-17 点随机关 | `app/services/mx_window.py` |
| WS | 断线只重连一次（12 秒后），失败永久放弃 | `ws.run_forever` |
| WS | TOKEN 过期不重试，立即放弃 | `ws._looks_like_auth_failure` |
| WS | 指数式自我封锁：gave_up 状态 + 手动接入复位 | `ws.py` / `fetcher.get_ws_status` |
| TOKEN | 2 天强制更换提醒 + 过期熔断 | `scheduler._mx_check_token_age` / `MXTokenExpiredError` |
| 特征 | 房间列表 100/页正常翻页 | `client.get_rooms` |
| 特征 | 房间同步随机 2-6 小时 | `mx_sync.SYNC_MIN/MAX_INTERVAL_SECONDS` |
| 特征 | HTTP 请求头补齐浏览器 UA/Origin/Referer | `client._headers` |
| 特征 | MX 图片走 MX 站点头（去掉 weibo Referer） | `avatar_cache.headers_for` |
| 告警 | 所有报错统一走系统 KOL「系统通知」 | `scheduler.publish_mx_error` |

## 三、分层详解

### 1. 架构改造：WS 为主，HTTP 只做兜底（收益最大）

- **自动轮询完全取消**：`scheduler.poll_once` 显式跳过 `platform == "mx"` 的所有大V，平时不产生任何 MX HTTP 请求。WS 推送的消息本身就是全量的，直接入库推送。
- **随机兜底拉取**（`_mx_fallback_loop`）：窗口内每**随机 20-200 分钟**拉 **1 个随机启用房间**的最新消息（复用 `fetcher.fetch`，含有限追平），防 WS 静默假死/漏消息。随机间隔 + 每轮单房间，不产生「固定周期扫全量」的爬虫签名。
- **手动触发是唯一主动入口**：
  - 每房间「拉取历史消息」按钮 → `POST /api/admin/sources/mx/rooms/{room_id}/pull-history`，只拉**最新 100 条**（单次请求，不再无限翻页）；
  - 「立即同步房间」按钮 → `POST /api/admin/sources/mx/rooms/sync`，手动同步房间列表。
- **量级对比**：改造前 146 房间 × 60 秒 ≈ 8760 次/小时 + 每小时百万 limit 房间列表；改造后常态 0，窗口内每天约 2-4 次房间列表 + 若干单房间兜底。

### 2. 每日运行窗口（`app/services/mx_window.py`）

- 每天在 **7:00-8:00** 之间随机一个时刻自动启动 MX（WS 会话 + 兜底拉取），**16:00-17:00** 之间随机一个时刻停止；窗口外零请求。
- 随机值每天重新生成（`generate_mx_daily_window`），重启服务会重新生成，可接受。
- **每个窗口只尝试启动一次会话**（`_mx_window_loop`）：启动失败或 WS 放弃后不再自动拉起——窗口循环自己绝不制造重连流量；恢复靠换 TOKEN 或次日窗口。
- 房间列表同步同样受窗口门控（`MXRoomSyncService.should_run` 回调），窗口外启动服务时连初始同步都跳过。
- 管理员仍可在后台手动接入/断开 WS（窗口策略优先：关窗后手动会话也会被停止；手动拉取历史不受窗口限制，因为是管理员明确点按钮）。

### 3. WS 重连策略（`app/fetchers/mx/ws.py`）

- **断线后只重连一次**：等待 12 秒（`RECONNECT_DELAY_SECONDS`）重连一次；重连成功则恢复额度（下次断线仍有一次机会）；**重连再失败就永久放弃**（`gave_up` 置位），不再发出任何连接请求。
- **TOKEN 过期零重试**：连接阶段被拒且错误形似鉴权失败（401/403/unauthorized/token/登录/认证/过期/无效）→ 不等待、不重试，立即放弃并告警。
- python-socketio 内部重连保持禁用（`reconnection=False`），重连完全由自己的策略控制。
- 恢复路径：管理员后台「主动连接」（新建客户端、状态自动复位），或换 TOKEN 后次日窗口自动恢复。
- 状态透出：`/api/admin/sources/mx/ws-status` 返回 `connected` / `last_message_at` / `gave_up` / `detail`，设置页直接显示「自动重连失败已停止，请手动接入」等文案。

### 4. TOKEN 管理（每 2 天强制更换）

- **时效提醒**：TOKEN 使用超过 2 天（`mx_token_updated_at` 设置项记录起用时间），系统通知 KOL 发布更换提醒；2 天节流期内不重复提醒。
- **过期熔断**：新增 `MXTokenExpiredError` 专用异常（`client.py`），WS 连接被拒或 HTTP 拉取遇到 token 失效响应时置 `_mx_token_expired` 熔断标记——**所有拉取与连接全部暂停**，避免死 token 继续打把处罚从「踢下线」升级成「封号」。
- **自动恢复**：后台保存新 TOKEN（值发生变化）时自动重置 2 天计时并解除熔断/放弃标记，无需重启。

### 5. 请求特征修正（消灭「一眼假」）

- **房间列表正常分页**：`get_rooms` 从 `limit=1000000` 改为每页 100（`ROOM_PAGE_SIZE`）逐页拉全量，50 页安全上限；不再有单条日志可定罪的参数。
- **同步间隔随机化**：房间列表同步从固定周期改为**每轮随机 2-6 小时**（`SYNC_MIN/MAX_INTERVAL_SECONDS`）；原 `sync_interval_hours` 配置项（含 UI 输入框、环境变量映射、API 字段）已整体移除，避免留下无效旋钮。
- **HTTP 请求头与 WS 同形**：`client._headers` 补齐浏览器 UA + 按 `api_base` 派生的 Origin/Referer（与 `ws.py` 握手头同一形态），消除「同一 token 一个 Chrome 一个 python-httpx」的自相矛盾。
- **图片/头像下载修正**：`avatar_cache.headers_for` 新增 MX 域名（`naaifu.cn`）分支——MX 浏览器 UA + MX 站点 Referer；之前 MX 图片错误地带 `weibo.com` Referer，在 MX 自家 CDN 日志里又是一个假信号。
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
| `app/fetchers/mx/ws.py` | 重连策略（12 秒一次/永久放弃/TOKEN 过期零重试）、gave_up 状态、give-up 回调 |
| `app/fetchers/mx/client.py` | 浏览器形态请求头、房间列表分页、`MXTokenExpiredError`、transport 注入（测试用） |
| `app/fetchers/mx/fetcher.py` | `start_ws` 透传 give-up 回调；`get_ws_status` 暴露 gave_up |
| `app/scheduler.py` | poll_once 跳过 mx；窗口管理循环；兜底拉取循环；TOKEN 时效/熔断；`_publish_system_alert` / `publish_mx_error`；手动 WS 控制透传回调 |
| `app/services/mx_window.py` | 新增：每日随机窗口生成与判定 |
| `app/services/mx_sync.py` | 随机 2-6 小时间隔；`on_error`/`should_run` 门控回调 |
| `app/api.py` | 拉取历史限 100 条；`on_mx_alert` 接线；WS 接口文案；移除 sync_interval_hours |
| `app/main.py` | `on_mx_alert=scheduler.publish_mx_error` 接线 |
| `app/avatar_cache.py` | MX 域名图片请求头分支 |
| `app/config.py` | 移除 `sync_interval_hours` 字段与 `MX_SYNC_INTERVAL_HOURS` 环境变量映射 |
| `app/static/app.js` | WS 状态展示；移除同步间隔输入框 |
| `tests/test_mx.py` | 重连策略/窗口/告警/熔断/分页/请求头等 12+ 个新契约测试 |

## 五、运维配套（代码管不住的部分）

1. **只订阅真看的房间**——订阅数决定暴露面量级。
2. **固定一个 IP 部署**，不要多实例共用同一个 token。
3. **换新号后低量爬坡**：IP 与行为指纹大概率已在风控记录，先按默认窗口跑几天再逐步放开。
4. **订阅「系统通知」KOL**，TOKEN 提醒和一切报错都从这里出来；TOKEN 到期及时手动更换。

## 六、遗留事项与残留风险

- **请求签名检查未做**：官方网页 JS 是否对 `/api/msg/list` 附加 `sign` 类参数，需要抓包分析官方前端——这属于对对方防护机制的主动逆向，未纳入本工程，是否执行自行决策。
- **兜底追平的量级**：`fetcher.fetch` 在消息突发时最多向后追 3 页（`BACKFILL_PAGES=3`），属于补洞必需，量级有界。
- **本质风险仍在**：MX 的 API 加密密钥按日期派生（`crypto.generate_key`），说明平台是有意防爬的。以上措施把流量压到真人量级、消除显眼特征，是**显著降低风险**，不是消除风险。长期稳定要么找平台要授权接口，要么接受偶发封号、换号换 TOKEN 的运营成本。

## 七、验证

- `tests/test_mx.py` 全量通过（54 个用例，含重连策略、TOKEN 过期零重试、分页、请求头、随机窗口边界、告警节流、熔断标记、2 天提醒等新契约测试）。
- 全量测试套件与改动前 HEAD 基线逐项对比：失败集合完全一致（均为 Windows symlink/网络类存量环境问题），本次改造零回归。
