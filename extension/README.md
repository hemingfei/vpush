# MX 采集器（Extension）

MX 消息采集器：MV3 扩展，`chrome.debugger`（Network 域）**被动**转发 MX 页面的
WS 帧/HTTP 请求到云网关 `/api/mx-ingest`。**零行为、零决策**——不点击、不导航、
不修改页面、不注入页面 JS（行为全部属于行为器 Agent，见 `agent/`）。

架构依据：`docs/adr/0001-local-dual-component-capture.md`；协议契约真相源：
`tests/test_mx_gateway.py` + `app/services/mx_gateway.py`（测试=契约）。

## 目录结构

```
extension/
├── manifest.json          MV3 manifest（debugger/storage/alarms/tabs 权限）
├── sw.js                  采集内核 service worker（spike sw.js 产品化）
├── options.html/js        配置页：网关地址/配对/采集前缀（写 storage 即时生效）
├── src/                   纯逻辑模块（node --test 覆盖）
│   ├── engine_frame.js    引擎帧过滤（与网关 ENGINE_FRAME_RE 逐字节对齐）
│   ├── envelope.js        信封 {seq,ts,account,type,payload} + 持久化单调 seq
│   ├── buffer.js          断线缓冲账目（5000 上限丢最旧 + 丢帧计数）
│   ├── auth_client.js     配对/认证状态机（首帧 pair/auth；4003=吊销清密钥）
│   ├── host_guard.js      上行地址校验（仅 wss 自有域名；拒内网/环回）
│   └── attach_filter.js   attach 前缀判定 + HTTP URL 过滤（每事件 await 读 storage）
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
    `lifecycle`：走 `event`/`detail` 字段
- 引擎帧（`2`/`3`/`0`/`40*`/`41*`）扩展侧过滤不上行（网关双保险防御性丢弃）
- 云端按 `(account, seq)` 24h 幂等窗去重——断线重传安全的前提是 seq 单调

## 本地测试（spec 裁定：本地组件不进 CI）

纯逻辑模块的本地测试（零依赖，node ≥18）：

```bash
node extension/tests/run_tests.mjs
# 等价：node --test extension/tests/*.test.mjs
```

当前 33 用例全绿。仓库 CI 无任何扩展相关接线（无新增 CI 依赖）。

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
`extension/src/` 生产模块**（配对状态机/信封/过滤/缓冲全是产品代码），仅
chrome.debugger 事件源与 chrome.storage.local 换成指令注入与内存替身。

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
