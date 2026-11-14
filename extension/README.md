# MX 采集器（Extension）

MX 消息采集器：MV3 扩展，`chrome.debugger`（Network 域）**被动**转发 MX 页面的
WS 帧/HTTP 请求到云网关 `/api/mx-ingest`。**零行为、零决策**——不点击、不导航、
不修改页面、不注入页面 JS（行为全部属于行为器 Agent，见 `agent/`）。

架构依据：`docs/adr/0001-local-dual-component-capture.md`；协议契约真相源：
`tests/test_mx_gateway.py` + `app/services/mx_gateway.py`（测试=契约）。

## 目录结构

```
extension/
├── manifest.json          MV3 manifest（debugger/storage/alarms/tabs 权限；action badge）
├── sw.js                  采集内核 service worker（spike sw.js 产品化）
├── options.html/js        配置页：网关地址/账号标签/配对/采集前缀（写 storage 即时生效）
├── src/                   纯逻辑模块（node --test 覆盖）
│   ├── engine_frame.js    引擎帧过滤（与网关 ENGINE_FRAME_RE 逐字节对齐）
│   ├── envelope.js        信封 {seq,ts,account,type,payload} + 持久化单调 seq
│   ├── buffer.js          断线缓冲账目（5000 上限丢最旧 + 丢帧计数）
│   ├── auth_client.js     配对/认证状态机（首帧 pair/auth；4003=吊销清密钥）
│   ├── conn_state.js      重连退避账目（互斥门+下刻门，session 持久跨 SW 死亡）
│   ├── host_guard.js      上行地址校验（仅 wss 自有域名；拒内网/环回）
│   ├── attach_filter.js   attach 前缀判定 + HTTP URL 过滤（每事件 await 读 storage）
│   └── response_body.js   HTTP 响应体采集（登记写穿 session/64KB 截断/组装）
├── tests/                 本地测试（零依赖 node:test；不进 CI）
├── smoke/                 冒烟驱动（node 侧模拟扩展内核）
└── README.md
scripts/mx_extension_smoke.py  全链冒烟（起网关测试服 + 驱动模拟扩展）
```

## 上行协议（网关契约摘要）

- 连接后**首帧认证**（浏览器 WS API 不能自定义 header）：
  - `{"op":"pair","code":"8位码"}` → `{ok:true, device_key}`（码一次性）
  - `{"op":"auth","key":"设备密钥"}` → `{ok:true}`；拒绝 + close **4003** =
    密钥无效/已吊销 → 扩展清本地密钥，等人工重新配对
- 信封：`{seq, ts, account, type: ws_in|ws_out|http|lifecycle, payload}`
  - `ws_in/ws_out`：SIO 帧原文（字符串）；`http`：`{url,method,body}` 的
    **JSON 字符串**（网关 http 分支只收 str，记 `http_frame` 事件）；
    `Network.loadingFinished` 后对已登记请求调 `Network.getResponseBody`，
    追发 `{url,method,body,responseBody,responseBodyTruncated}` 帧（响应体
    64KB 截断，超限置 truncated 标记——纯逻辑在 `src/response_body.js`）；
    `lifecycle`：走 `event`/`detail` 字段
- 引擎帧（`2`/`3`/`0`/`40*`/`41*`）扩展侧过滤不上行（网关双保险防御性丢弃）
- 云端按 `(account, seq)` 24h 幂等窗去重——断线重传安全的前提是 seq 单调

## 本地测试（spec 裁定：本地组件不进 CI）

纯逻辑模块的本地测试（零依赖，node ≥18）：

```bash
node extension/tests/run_tests.mjs
# 等价：node --test extension/tests/*.test.mjs
```

当前 50 用例全绿。仓库 CI 无任何扩展相关接线（无新增 CI 依赖）。

## badge 运维面（工具栏图标角标）

免开 options 页看采集健康度（状态跃迁时刷新，不逐帧刷）：

| badge | 语义 |
| ----- | ---- |
| 无字 | 已连接且缓冲空 |
| 数字（≤99） | 断线缓冲中的帧数 |
| 琥珀 `!` | 待配对 / 密钥已吊销（需人工重新配对） |
| 红色底色 | 有丢帧（buffer_overflow 账目非零） |

## MV3 审计加固（2026-11-14）

对照 `GoogleChrome/modern-web-guidance` chrome-extensions 技能 16 条
mandatory rules 的审计落地（设计决策 7/8/9 继承 spike 决策不回退）：

1. **响应体登记写穿 `chrome.storage.session`**（`src/response_body.js`）：
   SW 死于 `requestWillBeSent` 与 `loadingFinished` 之间时，重启经
   `restore()` 装回，响应体帧不再静默丢失；debugger 重 attach（新
   Network 会话 = 新 requestId 空间）时 `clear()` 清陈旧登记。
2. **连接互斥 + 陈旧回调守卫**（`sw.js`）：`connecting` 同步互斥位挡
   同批多入口（alarm/onclose/onInstalled），`ws !== sock` 守卫挡孤儿
   socket 的 `onclose` 串账——原三入口竞态可产生孤儿 WS 连接。
3. **重连退避持久化**（`src/conn_state.js`）：档位与下刻门存
   `storage.session`——SW 被 30s 回收后不从 0 档重新快连；真退避由
   `acquire()` 门控（alarm 敲门早到即放弃），浏览器重启 session 清零
   从 0 档开始（新会话无历史风暴）。旧 `setTimeout` 重连不活过 SW
   生命周期，已废。
4. **manifest 收窄**：移除 `host_permissions` 的 `http://127.0.0.1/*`
   （无消费方——WS 连网关不受 host_permissions 约束，`https://*/*`
   是 chrome.debugger attach MX 页面所需，域名漂移可配故保留）；CSP
   `connect-src` 移除 `ws://127.0.0.1`（扩展运行时 host_guard 本就
   拒绝明文 ws）。`mx_gateway_url` 运行时可配，`connect-src wss:`
   无法钉死单域——**权威校验在 `src/host_guard.js`**（仅 wss+公网域名，
   拒内网/环回）。


### 账号标签（跨账号去重的接线，S3）

`account` 字段的取值来源是 **options 页配对时必填的「账号标签」**
（存 `chrome.storage.local.mx_account`，随设备密钥同一安装面）。设计依据：
行为器给每个账号一个专属 Chrome profile（ADR-0001，接力不并行在线），
`chrome.storage.local` 按 profile 隔离——每个 profile 里的扩展实例只在
自己账号的浏览器里运行，故「按安装配置一次」即可与实际在线账号一致；
接力换账号 = 行为器换 profile = 另一个 profile 里的扩展实例带另一标签。
**行为器与扩展互不感知是 ADR-0001 的架构决策**——不存在 agent→extension
写 storage 的通道，两组件只经云端网关间接协同。

## 本地冒烟（端到端验收）

复现链路：起 T1 网关测试服（进程内 uvicorn + 生产 `build_gateway_app`）→
配对 → 认证 → 喂帧上行（混入引擎帧验证过滤）→ 服务端确认入库 → 断连 →
缓冲累计 → 重连补传（按序）→ `(account, seq)` 幂等 → seq 持久化连贯。

```bash
# 前置：node_modules 装 ws（一次性；已 gitignore，不入库）
cd <repo根> && npm install --no-save ws

# 跑冒烟（主 venv 依赖同 tests/test_mx_gateway.py）
C:/Users/hemin/Documents/vpush/.venv/Scripts/python.exe scripts/mx_extension_smoke.py
```

扩展侧由 `extension/smoke/simulated_extension.mjs` 驱动——**import 的是
`extension/src/` 生产模块**（配对状态机/信封/过滤/缓冲/响应体采集全是
产品代码），仅 chrome.debugger 事件源与 chrome.storage.local 换成指令注入
与内存替身。响应体采集的 chrome.debugger `Network.getResponseBody` 调用
本身（真实 GUI Chrome 会话）无法在模拟驱动里行使——冒烟经 `src/response_body.js`
单测路径 + `http_response` 指令断言信封带响应体；**真实浏览器下的手动验证
（48h 挂机验收）**：打开 MX 房间后看 lifecycle/`http_frame` 事件流里是否
出现带 `responseBody` 的帧。

## load-unpacked 安装（开发验证）

Chrome 137+ branded 已删除 `--load-extension`（spike 首跑 FAIL 实锤），开发期
用 **Playwright Chromium**（spike 先例，`~/AppData/Local/ms-playwright/
chromium-*/chrome-win64/chrome.exe`）：

1. 启动时 `--load-unpacked` 不存在——用 Chromium 的 `chrome://extensions`
   开发者模式「加载已解压的扩展程序」指向 `extension/` 目录；或沿用 spike
   脚本的启动参数方式（Playwright Chromium 对 `--load-extension` 仍有效）。
2. options 页依次：填网关地址（`wss://…/api/mx-ingest`，校验按钮会拒绝
   内网/环回/非 wss）→ 后台生成配对码 → 输入配对 → 确认状态「已连接」。
3. MX 域名漂移时改「采集范围」前缀，**保存即时生效、不重启采集**（设计决策：
   配置变更不 reload SW——重启窗口丢事件）。
4. **账号标签**（配对必填）：填该扩展实例所属的 MX 账号名（如 `main`）；
   接力双账号部署 = 两个 profile 各装一份扩展、各配各的标签（跨账号去重
   按 (account, seq) 幂等与标签判定，标签错配会导致备用账号帧被误吞）。

## 分发（不进 Chrome Web Store）

`debugger` 权限过不了 Web Store 审核——自托管两条路（运营方一两台常开机器，
Out of Scope 终端用户分发）：

- **自托管 CRX**：`chrome.exe --pack-extension=extension/` 产出 `.crx` + 私钥；
  放自有 HTTPS 站点 + `update_url` 指向自托管 update manifest（扩展经
  `update_url` 自动更新）。
- **组策略 force-install**（Windows 域环境推荐）：注册表
  `HKLM\Software\Policies\Google\Chrome\ExtensionInstallForcelist` 写
  `<扩展ID>;<update_url>`；或 Chrome 企业策略模板 `ExtensionInstallForcelist`。
  配合自托管 update manifest。

## 设计决策（spike 继承，不得回退）

1. attach 过滤配置**每次事件时 `await` storage 读取**（顶层一次性读取在 SW
   重启后有竞态）——`src/attach_filter.js`
2. 配置变更**不 reload SW**（重启窗口丢事件）——options 页只写 storage
3. **零页面 JS 注入**（ADR 否决页面 hook：constructor.toString 可被探测）
4. MV3 + Playwright Chromium 开发路径（branded Chrome 137+ 无 `--load-extension`）
5. seq 持久化（`chrome.storage.local.mx_seq`）——内存计数器重启归零会让补传
   帧撞旧 seq 被网关幂等窗吞掉
6. 吊销（close 4003）清本地密钥转人工配对——自动重试死密钥只会反复 4003
7. 连接互斥（`connecting` 位 + `ws !== sock` 守卫）与退避门（`conn_state`
   下刻门）——孤儿 WS 与风暴快连双防线（MV3 审计 2026-11-14）
8. SW 死亡不丢的短命状态放 `chrome.storage.session`（响应体登记/退避账目），
   跨浏览器的长命状态放 `chrome.storage.local`（seq/缓冲/密钥/配置）
9. 配置变更不 reload SW 的 corollary：`mx_gateway_url` 运行时可配，CSP/
   host_permissions 只能放宽到「wss 任意域」，逐域校验在 host_guard 运行时做
