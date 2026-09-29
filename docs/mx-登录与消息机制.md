# MX 平台登录与消息机制完整文档

> 更新时间：2026-09-27（基于 hmf 分支 6aea08e 的代码实测梳理；同日对照代码全量复核，
> 精化了管理端点路由、去重兜底键长度、环境变量映射三处表述）
> 目的：单文档覆盖 MX 平台的**登录（会话生命周期）**与**消息（收发全链路）**两大机制，
> 供其他 AI 系统完整复刻或对齐更新。与 `mx-防风控优化措施.md`（改造背景与决策依据）、
> `mx-官方网页端抓包核对-2026-09-02.md`（协议实测）互补，三者不重复展开。

---

## 〇、术语与总览

| 术语 | 含义 |
|------|------|
| TOKEN | MX 平台登录凭据，请求头 `token` 携带；无签名无 sign，纯 token 认证；**官方有效期约 2 天，需人工更换** |
| 房间 / rid | 每个大V 是一个「房间」，房间 ID 即 KOL 的 `external_id`；消息只在房间里发 |
| business-api | `{api_base}` 下的业务接口（消息/房间列表） |
| master-api | 同主机 `/master-api` 前缀的只读启动接口（用户信息/系统配置/公告） |
| 开窗 / 会话 | 「登录」= 打开会话 = 执行官方冷启动序列 + 拉房间列表 + 连 WS，会话有生命周期管理 |
| 熔断 | TOKEN 失效后置 `_mx_token_expired` 标记，停止一切 MX 请求直到 TOKEN 更换或手动重探 |
| 兜底拉取 | 每天一次的随机单房间 HTTP 拉取，防 WS 静默假死 |
| V平台系统通知 | `platform=system` 的 KOL「系统通知」，一切 MX 告警经它发布（入库+推送同正常帖） |

**流量模型总纲**（一切设计围绕它）：**常态接近零 HTTP 请求**。窗口内靠 WS 实时推送收消息；
HTTP 只在开窗（房间列表 1 次）、每日兜底（1 次单房间）、手动拉历史（管理员点击）时发生。
MX 曾封过号，整套机制的目标是让流量画像无限接近「真人每天打开三次网页」。
实现上调度器通用轮询**显式跳过 `platform == "mx"`**（`poll_once`）——复刻时绝不能把
MX 挂进通用轮询管线，否则前功尽弃。

---

## 一、登录机制（会话生命周期）

### 1.1 凭据与认证方式

- 认证仅靠 `token` 请求头（HTTP）与 Socket.IO auth 载荷中的 `token` 字段（WS），**无 sign 签名**（2026-09-02 抓包确认）。
- TOKEN 由管理员从官方网页端登录后提取，填入后台「数据源 → MX」，**约每 2 天必须人工更换**（系统按 `mx_token_updated_at` 设置项计时提醒，见 1.7）。

### 1.2 登录 = 复刻官方网页端冷启动序列

「登录」（无论系统自动开窗还是管理员手动点按钮）都是模拟「真人打开网页」，顺序固定（`mx_sync.boot_sequence` + `_mx_session_start`）：

1. `POST {host}/master-api/api/user/info` — `{"device":"web-browser","tt":<ms>}`；响应里的 `info.token` 若与本地配置不一致，说明服务端已轮换 TOKEN，记警告提示更换
2. `POST /master-api/api/system/config` — `{"tt":<ms>}`
3. `POST {api_base}/api/msg/tip` — `{"tt":<ms>}`（总未读数）
4. `POST /master-api/api/room/grouplist` — `{"tt":<ms>}`
5. `GET /master-api/api/notice?tt=<ms>&token=<token>` — 平台公告（GET，token 走 query，无 Content-Type）
6. `POST {api_base}/api/room/list` — `{"pages":1,"limit":1000000,"tt":<ms>}` **单次全量**拉房间列表（官方冷启动本身就是这个形态，抓包实测）
7. 连接 WebSocket（见第二节）

要点：
- `tt` 全部是毫秒时间戳，请求时现取。
- 序列里**任何一步 TOKEN 失效（`MXTokenExpiredError`）→ 全局熔断 + 告警 + 本轮登录中止**；其余单步失败只记入报告、不阻断后续（对齐是最佳努力，不能反过来影响消息链路）。
- 每步的 `{name, ok, detail, ms}` 写入模块级 `_mx_login_report`，后台「接口状态」页展示（`source` 区分 auto/manual）。
- 房间同步把房间落库为 KOL（`kols` 表，`platform='mx'`、`external_id=<rid>`），合并 `extra_data`（teaname/introduce/message_today/star 等），**但保留管理员已设置的 `enabled`/`show_in_plaza`**（同步不覆盖人工开关）。新 KOL 默认启用；头像走本地缓存。
- `MXRoomSyncService` 复用同一个 `MXClient`（同一 TLS 会话），不每轮新建连接——同指纹重复握手可被风控聚合。

### 1.3 每日运行窗口（在线时段管理）

会话只在每天**三段随机窗口**内运行（`mx_window.py`，北京时间）：

| 段 | 开窗 | 关窗 |
|----|------|------|
| 早市 | 07:00:00–08:00:00 随机一秒 | 11:40:00–12:00:00 随机 |
| 午后 | 12:30:00–12:50:00 随机 | 16:00:00–16:30:00 随机 |
| 晚间 | 19:00:00–19:30:00 随机 | 23:30:00–23:55:00 随机 |

- 窗口每天生成一次（`generate_mx_daily_windows`），当天固定；服务重启会重新生成（可接受的随机性损失）。
- `scheduler._mx_window_loop` 每 30 秒 tick 一次（`_mx_window_tick`）：进入窗口 → 若该窗口「武装」且未熔断 → `_mx_session_start()` 自动登录并写操作日志 `mx_auto_login`（user_id=NULL）；离开窗口 → `_mx_session_stop()` 断开并记 `mx_auto_disconnect`。
- **每个窗口只自动登录一次**：失败/WS 放弃后本窗口不再自动拉起——窗口循环绝不自己制造周期性重连流量。恢复靠换 TOKEN 或下个窗口。
- **重启安全**：开窗时刻早于重启时刻的窗口「不武装」（`arm_windows`），重启后不自动续连。
- **重启自动登录例外**（2026-09-16）：工作日 08:00–22:00 内重启，若 TOKEN 在 2 天时效内（`_mx_token_age_fresh`）→ 正处的窗口重新武装；落在窗口间隙则 `_mx_restart_login_pending` 让窗口循环下个 tick 立即补登一次。超龄/年龄未知的 TOKEN 不自动登录，发系统通知提醒。
- **三道会话关闭兜底**：
  1. 关窗时刻到点断开（正常路径）；
  2. 晚间兜底强断：23:30–23:55 随机一秒（`_mx_maybe_nightly_force_close`），MX 无论会话来源（自动/手动）仍在线一律强制断开，并 disarm 当前窗口防重拉——兜住「关窗后手动登录忘关」；
  3. 会话最长时长滚动兜底：会话持续超 **4 小时**（`_MX_MAX_SESSION_HOURS`）强制断开 + disarm（`_mx_maybe_session_timeout`）——计时起点是最近一次 `mx_ws_control("connect")` 时刻，自动/手动统一。
- 强断/disarm 的语义：被 disarm 的窗口当天不再自动开窗，管理员仍可手动「登录」。

### 1.4 管理员手动操作（API 端点）

| 端点 | 行为 |
|------|------|
| `POST /api/admin/sources/mx/session/login` | 手动登录：完整冷启动序列 + 房间同步 + 连 WS，**不受窗口限制**；逐接口报告返回给前端 |
| `POST /api/admin/sources/mx/ws/connect` | 只连 WS（不复刻冷启动），同时复位 gave_up 状态 |
| `POST /api/admin/sources/mx/ws/disconnect` | 只断 WS（保留抓取器与房间同步） |
| `GET /api/admin/sources/mx/ws-status` | 状态：`connected` / `last_message_at` / `gave_up` / `detail` / `login_report` |
| `POST /api/admin/sources/mx/rooms/{room_id}/pull-history` | 手动拉该房间最新 100 条历史（见 2.4） |
| `GET/PUT /api/admin/sources/mx` | MX 配置读写（保存即触发热应用 `apply_mx_config`；body 带 `hot_apply=false` 只保存——无人值守回填+容器重启流程用，重启后由窗口循环自动补登） |
| `GET/PUT /api/admin/sources/mx/rooms`、`/rooms/{room_id}` | 房间列表、房间启用/广场可见开关 |

配置来源：`sources.mx`（config.yaml）或环境变量 `MX_ENABLED / MX_TOKEN / MX_API_BASE /
MX_WS_URL / MX_WS_PATH / MX_WS_ENABLED / MX_PAGE_SIZE / MX_MAX_HISTORY_PAGES`
（映射表在 `app/config.py`；`ws_namespace` 仅 dataclass 默认值 `/msg`，无环境变量映射）。

手动登录的几个特殊语义（`mx_manual_login`）：
- **半开重探**：熔断态下管理员点「登录」视为对 TOKEN 的主动复核——先清熔断标记再走完整登录；若仍鉴权失败会重新熔断。这是熔断的两条解除路径之一。
- 窗口内的手动登录（无论成败）记「本窗口已手动尝试」（`_mx_manual_attempted_idx`），窗口循环不得在后续 tick 自动重跑启动序列。
- 窗口内的手动登录成功且全部步骤 ok → 视为本窗口会话已开启（`_mx_window_open=True`）。

### 1.5 TOKEN 失效的判定与熔断

**判定（精确信号，弱词不触发）**——误熔断代价极高（停掉全部拉取与 WS），只认两类强特征：

- HTTP 业务响应：`code == 401 或 502`（实测即 TOKEN 失效），或 `msg` 含强特征短语（`client._TOKEN_EXPIRED_MSG_MARKERS`：token失效/过期/无效/未登录/请重新登录/登录失效 等，匹配前转小写去空格）。WAF 拦截页、代理错误文本里碰巧出现「认证」「token」这类弱词**不**触发。
- WS 连接阶段被拒：握手状态码 401/403，或错误文本含同类强特征短语（`ws._WS_AUTH_MSG_MARKERS`）。

**熔断动作（统一入口 `scheduler._mx_trigger_token_expired`）**：
1. 置 `_mx_token_expired = True`；
2. **立即掐断 WS**（`_mx_schedule_ws_abort` → `_mx_abort_ws`）：先同步置位 `ws_client._should_stop` 让 run_forever 失去重连理由，再把 abort 协程投递回调度事件循环（线程中触发也能投递，`run_coroutine_threadsafe` 兜底）——绝不能出现「接口已报过期、WS 还挂在死 token 上」的中间态。掐断方式是「关标签页式」直接关底层连接，不发任何关闭包（见 2.2 stop）。

**熔断期间的抑制**：
- 窗口循环到点不开窗、不调登录、不写自动登录操作日志（死 TOKEN 上登录 100% 失败，照常走动作只会误导管理员）；
- 每日兜底拉取跳过；
- 熔断跨时段跨天持续。

**解除路径（只有两条）**：
1. 后台保存新 TOKEN（`update_mx_config` → `apply_mx_config`：无论 token 值是否变化，保存即复位熔断/放弃标记；token 实际变化时重置 2 天时效计时）——管理员主动保存视为一次人工确认；
2. 管理员手动「登录」半开重探（见 1.4）。

**告警**：TOKEN 过期告警走 `publish_mx_error(key="token_expired")` → V平台 KOL「系统通知」发布 + 30 分钟节流（同 key）。

### 1.6 TOKEN 2 天时效管理

- `mx_token_updated_at`（DB settings）记录起用时刻；首次运行（无记录）以当前时间起算。
- 超 2 天：每轮窗口 tick 检查（`_mx_check_token_age`），发「请更换」系统通知，2 天节流。
- 超龄 TOKEN 的重启自动登录被拒绝（`_mx_token_age_fresh`，年龄未知按过期处理）。
- 仅 token 值实际变化才刷新计时（保存同值不刷新）。

### 1.7 WS 重连策略（防攻击性特征）

（详见 2.2 客户端，这里列策略层）
- 断线后等 **16–36 秒随机**延时重连，**只重连一次**；这次再失败 → `gave_up=True` 永久放弃自动重连 + on_give_up 告警。
- 重连成功则恢复额度（下次断线仍有一次机会）。
- 连接阶段被拒且判定 TOKEN 失效 → 不等待不重试，立即放弃并触发熔断。
- python-socketio 内部重连禁用（`reconnection=False`），策略完全自己控制。
- 恢复：管理员「登录」/「接入 WS」新建客户端（状态自动复位），或次日窗口。

---

## 二、消息机制（收发全链路）

### 2.1 API 加密与解密（`crypto.py`）

MX 所有业务接口的 `data` 字段是**密文字符串**，解密链：

```
密文字符串
  → LZ-String 解压（注意 UTF-16 码元视角，见下）
  → Base64 解码
  → AES-128-CBC 解密（key/iv 按日期派生）
  → UTF-8 解码 → 合并代理对 → JSON 解析
```

**密钥派生**（`generate_key`）：
```
md5 = md5("YYYY-MM-DD")           # 北京时间日期字符串
key = md5 前 16 位 hex 字符的 utf-8 字节（16 字节）
iv  = md5[8:14] 的 utf-8 字节 + b"\x00" * 10（补足 16 字节）
```

**日期源与偏移**：
- HTTP 响应用**北京时间**日期（`decrypt_api_data`）；WS 消息用**本地/北京双日期源**共用一次解压（`decrypt_ws_data`）——容器时区可能与北京不一致时的容错。
- 每个日期源尝试偏移 `[0, -1, +1]` 天（跨午夜边界容错）。
- LZ-String 解压是全链路最贵的一步且与密钥无关——**只做一次**再循环密钥（性能关键）。

**UTF-16 代理对坑**（必须复刻，否则 emoji 必挂）：
- 服务端按 JS 的 UTF-16 码元（charCodeAt）压缩。密文经 JSON/HTTP 传输后相邻合法代理对会被 Python 解码合并成一个增补平面字符（一个字符变半个），比特流错位导致解压失败——**解压前必须把增补平面字符还原成代理对码元**（`_to_utf16_units`）。
- 解密后明文若按码元落地，emoji 是两个孤立代理字符，入库/UTF-8 推送直接报错——**解密后必须合并代理对**（`combine_surrogate_pairs`）。

解密失败返回 None：调用方按「保留原始数据」降级，绝不丢消息（见 2.3）。

### 2.2 WebSocket 实时链路（`ws.py`）

**连接参数**（2026-09-02 抓包对齐）：
- URL：`wss://mx.2026.naaifu.cn/business-api/5`（即 `{api_base}`），path `/socket.io`，namespace `/msg`，**websocket 直连**（无 polling 升级）。
- auth 载荷（callable 形式，每次连接时求值保证 tt 新鲜）：`{"tt": <ms>, "token": <token>, "version": "web"}`。
- 握手头按 Chrome WebSocket 形态：UA/`sec-ch-ua*` 客户端提示/`Pragma: no-cache`/`Cache-Control: no-cache`/`Accept-Encoding: gzip, deflate, br, zstd`/`Accept-Language`/`sec-fetch-site: same-origin`/`sec-fetch-mode: websocket`/`sec-fetch-dest: empty`/`Origin: https://<host>`。UA 必须显式覆盖，否则 aiohttp 默认 UA 单条握手就是机器人实锤。
- **连上后「只听不说」**：不 emit 任何业务事件（官方网页端行为一致）；心跳由 socket.io 库的 ping/pong 处理。
- 人格常量单一来源（`ws.py` 顶部）：`IMPERSONATE_TARGET="chrome146"`、`BROWSER_UA`、`SEC_CH_UA*`、`ACCEPT_LANGUAGE` —— HTTP（curl_cffi impersonate）、WS 握手（aiohttp）、图片下载三处必须同形，否则「同 token 多客户端人格」就是风控现成特征。

**事件处理**：
- 订阅 `room_msg` 事件为主通道；另有 `*` 通配兜底（单参透传、多参归一成列表），防止未知事件静默丢失。
- 消息解析（LZ-String + AES，CPU 密集）**必须丢线程池**（`asyncio.to_thread`），逐条 await 保持顺序——直接在事件循环上跑会拖垮 socket.io 心跳导致服务端断连。
- 解析结果可能是 dict 或 list（list = 一批消息，逐条分发）。
- WS 客户端自身维护 `connected` / `last_message_at` / `gave_up` / `manually_stopped` / `stop_reason` 状态，供状态接口展示。

**断开语义（关键）**：`stop()` 模拟「用户直接关闭标签页」——**不发 socket.io `41`/Engine.IO CLOSE 包/WS Close 帧**，直接关闭底层 aiohttp 会话掐断 TCP（服务端只看到 transport close）。优雅关闭握手（sio.disconnect()）绝不能用在「退出/关窗」语义上。

### 2.3 消息解析与去重（`fetcher.py`）

**原始消息结构**（WS 推送 / HTTP 历史同构）：
```
{
  "id" / "msgid": 消息ID（去重主键的来源）,
  "rid" / "room_id": 房间ID,
  "msg": JSON 字符串 —— 内容体（见下）,
  "createtime" / "created_at" / "ts": 毫秒/秒时间戳,
  ... 其他原始字段
}
```

**`msg` 字段解析**（`_parse_msg_content`）：`msg` 是 JSON 数组字符串，元素类型：
- `{"type":"text","msg":"<文本>"}` — 正文；若整条文本是文件分享形态（`url=<URL>,fileName=<名>` 键值串，或 `分享了一份文件：<名>\n<URL>`），提取为附件
- `{"type":"pic","url":"<URL>"}` — 图片，最多取 **4** 张，统一走本地缓存（下载失败/内存库保留原 URL；直连白名单域名如钉钉 CDN 跳过缓存）
- `{"type":"file","url":"<URL>","name":"<名>"}` — 文件；判定是否按图片处理：URL 带图片扩展名→图片；URL 带非图片扩展名（.pdf/.zip）→附件；URL 无扩展名→看文件名扩展名，仍无→按图片（转存图常无后缀）；**公众号/短链域名（mp.weixin.qq.com / url.cn / t.cn）明确排除**（下载下来是 HTML，当图片渲染必挂）
- 纯文件消息（无文字）合成占位正文：全音频 `[语音]`，否则 `[文件]`——占位正文保住消息不被丢弃
- `msg` 不是 JSON 时整串当纯文本

**正文归一化**（`normalize_mx_text`）：MX 服务端对换行做了双重转义（JSON 解码一次后仍剩字面量 `\n`/`\r` 字符串，与真实 CR/CRLF 混杂）——先还原转义序列再归并真实换行，连续换行压成单个；只含列表符号的悬空占位行（`-`/`*`/`1.` 等）替换为空行而非删除（保段落边界）。

**去重主键**：`(platform="mx", external_id)`，posts 表 UNIQUE 约束 + `INSERT OR IGNORE` 天然幂等。
- `external_id` = 消息 `id`/`msgid`/`msg_id` 的字符串。
- **缺 id 时的确定性兜底键**（`_fallback_external_id`）：正文非空按正文做摘要；纯图/文件消息按原始字段序列化做摘要（**下划线开头的运行时注入字段如 `_receivedAt` 不参与摘要**——WS 先到 HTTP 兜底再到时间戳不同，参与会绕过去重）。有 createtime 时形如 `{room_id}-{createtime}-{md5前8位}`，无 createtime 时形如 `{room_id}-{md5前12位}`。
- 双链路去重靠的就是这个键：WS 实时 + HTTP 兜底/手动拉取重复到达，同一键只入库一次。

**WS 实时消息的房间路由**：消息只有 rid，按 rid 查 KOL——房间信息带 TTL 缓存（命中 300s / 未命中 60s），未知房间的噪音事件不至于打爆数据库。实时链路（kol 来自缓存）不处理已停用房间；入库前调度器还会按数据库实时状态再兜底一次。

**「解析不出任何内容才丢弃」原则**：完全无文本/图片/文件的消息丢弃（整包 JSON 当正文入库会变垃圾推送）；但解密失败时**保留原始字段**（`decrypted` 键附带明文），绝不把 rid/msg 埋进 `{"raw":...}` 导致消息被下游静默丢弃。

**Post 结构**：`platform="mx"`、`kol_id`/`kol_name`（来自房间）、`external_id`、`title=""`、`content`（归一化正文）、`images`（≤4）、`detail`（原始消息字段 + 提取的 `files`，前端时间线从 detail 自行解析附件）、`published_at`（createtime 毫秒/秒自适应格式化）。

### 2.4 HTTP 拉取链路（兜底与手动）

**fetch 主流程**（`fetcher.fetch`，兜底与轮询复用）：
1. `POST /api/room/view` `{"rid":<rid>,"tt":<ms>}` 进房上报——官方每次打开房间都先发，对齐「人打开了房间」行为链；失败只记日志不阻断，TOKEN 过期照常上抛熔断
2. `POST /api/msg/list` `{"rid":<rid>,"msgid":0,"pagesize":30,"tt":<ms>}` 拉最新一页（`pagesize=30` 官方实测值；`msgid=0` 表示最新）
3. **有限追平**（`_backfill_history`，`BACKFILL_PAGES=3`）：首页不足 30 条=已到历史起点直接返回；首页最末一帖未入库（爆发发帖漏抓）→ 用 `msgid` 游标（页内最小数字 id）向后翻最多 3 页，遇到已入库帖/空页/游标未前移即停；未追平记 timeline gap 告警

**每日一次兜底拉取**（`_mx_maybe_daily_fallback`）：
- 每天生成窗口时在**当天仍武装的窗口内**随机预约一个时刻（离关窗 ≥1 分钟）。
- 到点且会话存活（WS 在线）才执行：随机挑 1 个启用房间跑一次完整 fetch，入库并推送。
- 错过（时刻已过会话未存活/窗口已结束）→ 当天直接放弃，绝不补打。量级必须压到真人水平。

**手动拉历史**（`api.py pull-history`）：管理员点击，拉该房间最新 **100** 条（单次请求 `pagesize=100`），按发布时间升序批量入库（`insert_posts_batch`），失败走 on_mx_alert 告警。不受窗口限制。

### 2.5 消息入库与推送（调度器侧）

WS 实时消息回调链（`on_mx_message`，全链路 `asyncio.to_thread` 执行）：
1. 查数据库该 KOL 实时状态，**停用房间不入库不推送**（立即生效，与轮询平台「停用即不抓取」同口径）
2. 入库前先走**本地规则打标**（词表话题 ≤3 + 股票名/别名 ≤6，总上限 10；输入带 60s TTL 缓存）——消息即时带标签
3. `db.save_post`（唯一约束去重，已存在返回 None 直接跳过）
4. **大V 屏蔽词命中的消息：入库留档但不推送**
5. `notify_subscribers` 推送给订阅者（复用全平台统一的推送管线：免打扰缓冲、次要缓冲、重试队列）

**LLM 打标循环**（`mx_llm_tag_auto_loop`）：独立于 MX 会话的常驻任务，每轮现读配置（开关/时段），对入库的 MX 帖子 LLM 打标后**整体替换**本地规则标签。MX 未启用也照常调度（只读 posts 表）。

**告警统一出口**：`publish_mx_error(key, title, content)` —— 所有 MX 报错（TOKEN 过期/WS 放弃/会话启动失败/兜底失败/同步失败/手动拉取失败）经 V平台 KOL「系统通知」发布，同 key 30 分钟节流；`key=token_expired` 同时触发熔断。

---

## 三、请求特征规范（「不像机器人」的硬约束）

复刻时以下任何一条缺失都可能构成「一眼假」信号：

| 层面 | 规范 |
|------|------|
| HTTP 客户端 | `curl_cffi.Session(impersonate="chrome146")`：TLS 指纹（JA3/JA4）、HTTP/2、头序全部对齐 Chrome。普通 httpx/requests 的 Python TLS 指纹 + Chrome UA 是最强检测信号 |
| HTTP 头 | `token` / `Content-Type: application/json` / `version: web` / **`ad: true` + `i: qq`**（前端写死的渠道标记，登录前请求就带） / `accept: */*`（fetch 默认，不是 axios 形态） / `accept-language: zh-CN,zh;q=0.9` / `sec-fetch-site: same-origin` / `sec-fetch-mode: cors` / `sec-fetch-dest: empty` / `Origin`+`Referer` 指向站点根；导航特有头（`upgrade-insecure-requests`/`sec-fetch-user`）置 None 删除 |
| WS 握手 | 见 2.2；UA/客户端提示与 HTTP 同源常量 |
| 图片下载 | MX 域名（naaifu.cn）走 MX 站点 Referer + 浏览器 UA（不走其他站的 Referer） |
| 频率形态 | 窗口外零请求；重连延时 16-36s 随机（固定节拍是机器信号）；每窗口只登录一次；兜底每天 ≤1 次；`tt` 每请求现取 |
| 量级 | 房间列表 ≤3 次/天；单房间 HTTP 拉取 ≈1 次/天 + 手动 |

---

## 四、关键文件索引

| 文件 | 职责 |
|------|------|
| `app/fetchers/mx/client.py` | HTTP 客户端：curl_cffi impersonate、请求头、TOKEN 失效判定（`MXTokenExpiredError`）、房间列表/历史/进房上报/冷启动只读端点 |
| `app/fetchers/mx/crypto.py` | AES-128-CBC + LZ-String 解密、日期密钥派生、UTF-16 代理对处理 |
| `app/fetchers/mx/ws.py` | Socket.IO WS 客户端：人格常量（单一来源）、握手头、重连策略（一次/放弃/熔断零重试）、关标签页式断开、消息解析线程池化 |
| `app/fetchers/mx/fetcher.py` | 消息→Post 解析、msg 内容解析（text/pic/file）、去重键、兜底追平、房间缓存、WS 状态透出 |
| `app/services/mx_window.py` | 每日三段随机窗口生成/判定/武装、重启自动登录时段、兜底预约时刻 |
| `app/services/mx_sync.py` | 官方冷启动序列（boot_sequence）、房间→KOL 同步（保留人工开关）、复用 HTTP 会话 |
| `app/scheduler.py` | 会话生命周期（窗口循环/自动登录断开/三道关闭兜底）、TOKEN 熔断统一入口与 WS 掐断、2 天时效、每日兜底拉取、实时消息入库推送、手动登录半开重探、`mx_ws_control`、告警出口 `publish_mx_error` |
| `app/api.py` | 管理端点（login/ws connect/disconnect/ws-status/pull-history/config/rooms）、MX 拉取告警接线 |
| `app/config.py` | `MxConfig`（enabled/token/api_base/ws_url/ws_path/ws_namespace/ws_enabled/page_size=30/max_history_pages） |
| `app/main.py` | 端点→调度器回调接线（on_mx_config_changed/on_mx_ws_control/on_mx_session_login/on_mx_alert） |
| `app/mx_llm_tagging.py` | LLM 打标常驻循环（整体替换规则标签） |
| `tests/test_mx.py` | 契约测试全集：重连/熔断/窗口/人格一致性/分页/请求头/告警节流（复刻后应建同等测试） |

---

## 五、复刻核对清单

复刻或移植到其他系统时，按此清单逐项核对（每项都有对应实现依据）：

**登录侧**
- [ ] 冷启动序列顺序与参数（1.2），逐接口报告
- [ ] 房间列表单次 `limit=1000000` 官方形态；同步保留人工 enabled/show_in_plaza
- [ ] 三段随机窗口 + 武装机制 + 每窗口一次登录 + 重启安全（1.3）
- [ ] 工作日 08:00-22:00 重启自动登录（含 TOKEN 2 天时效门禁）（1.3）
- [ ] 三道关闭兜底：关窗/晚间强断/4h 会话超时，强断都 disarm（1.3）
- [ ] TOKEN 失效判定只认强特征（401/502 + 强短语），弱词不熔断（1.5）
- [ ] 熔断 = 标记 + 立即掐 WS（跨线程投递回事件循环）+ 窗口期抑制（1.5）
- [ ] 熔断解除仅两条路：保存配置 / 手动登录半开重探（1.5）
- [ ] 2 天时效计时与提醒；仅 token 实际变化才刷新（1.6）
- [ ] WS 断线只重连一次（16-36s 随机），失败永久放弃并告警（1.7）

**消息侧**
- [ ] 解密链完整：LZ-String（码元视角）→ base64 → AES-128-CBC（日期密钥）→ 代理对合并 → JSON（2.1）
- [ ] 密钥日期源：HTTP 北京时间，WS 本地+北京双源；偏移 [0,-1,+1]；解压只做一次（2.1）
- [ ] WS：websocket 直连、`/msg` namespace、auth `{tt,token,version}`、只听不说、Chrome 握手头（2.2）
- [ ] 断开不发任何关闭包（关标签页式）（2.2）
- [ ] 消息解析丢线程池、逐条保序（2.2）
- [ ] msg 内容解析：text/pic(≤4)/file 图片判定/占位正文/文本内嵌文件提取（2.3）
- [ ] 正文换行双重转义还原 + 悬空列表符号行处理（2.3）
- [ ] 去重键：id 优先；缺 id 确定性兜底（运行时字段不参与摘要）（2.3）
- [ ] 解密失败保留原始字段绝不丢消息（2.3）
- [ ] HTTP 拉取：room/view 进房上报 → msg/list pagesize=30 → 最多 3 页游标追平（2.4）
- [ ] 每日兜底：武装窗口内随机预约、会话存活才拉、错过不补（2.4）
- [ ] 入库推送：停用房间不入库、规则打标先行、唯一键去重、屏蔽词入库不推送（2.5）
- [ ] 告警统一走系统 KOL + 30 分钟节流（2.5）

**特征侧**
- [ ] curl_cffi impersonate（chrome146）+ 全套请求头（含 `ad: true`/`i: qq`）（三）
- [ ] 人格常量三处同源（HTTP/WS/图片）（三）

---

## 六、已知边界与残留风险（复刻方须知）

1. **WS 底层 TLS 仍是 Python/aiohttp 指纹**（非 curl_cffi）：一天 ≤3 次连接，量级上风险可接受；彻底解决需 curl_cffi WebSocket + 自写 engineio 层，性价比低。
2. **图片/头像下载保留 httpx**（SSRF 防护与 httpx 深度耦合）；CDN 是最弱检测面且频率低。
3. **本质风险仍在**：API 密钥按日期派生说明平台有意防爬。整套措施是显著降低风险，不是消除；长期要么拿授权，要么接受偶发封号换号的运营成本。
4. **运维配套**：订阅「系统通知」KOL 才能收到告警推送；TOKEN 每 2 天人工更换；多实例不要共用 token；换号后先低量爬坡。
5. 平台改版风险：按 `docs/mx-定期抓包巡检手册.md` 每 2-3 天巡检一次官方网页端行为差异。
