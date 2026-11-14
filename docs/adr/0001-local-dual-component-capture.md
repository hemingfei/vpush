# ADR-0001: 本地双组件（行为器+采集器）替代云端直连

- 状态: 已接受（Accepted）
- 日期: 2026-11-14
- 背景与决策会话: MX 防风控新架构调研 + 四轮 grilling（全部决策入档）

## 背景与问题

MX 平台风控已使云端程序化连接不可用：2026-10-12 实锤平台周期性回收 WS 连接并对
被回收 token 置「连上即断」风暴标记；TLS 指纹（curl_cffi chrome146）、原生 WS 栈、
四档退避、拟人化八项等全部工程手段均无法阻止回收。同一 token 下真实浏览器连接
长期存活（scripts/mx_ws_probe.py 实测）。继续在云端「伪装成浏览器」的路线已被
判定为死路。

## 决策

采集与行为全部下沉到用户本地，由两个互相独立的组件构成：

1. **行为器（Agent）**：本地 Python 进程。打开/关闭专用 Chrome 实例、全自动登录
   （seed 免登 → 掉登录态 → 视觉识码重登，复用 mx_login 链路）、按三段随机窗口
   调度、每 5-10 分钟 CDP 真点击切房间。是唯一的行为决策者。
2. **采集器（Extension）**：MV3 扩展。chrome.debugger attach（Network 域）被动抓
   MX 页面的 HTTP 请求与 WS 帧，原样透传（wss 直连云端网关，不预解析）。
   零行为、零决策。
3. **云端**：FastAPI ws 网关（/api/mx-ingest，配对码绑定设备）→ 复用现有解析层
   （ws.py _dispatch_sio_event、fetcher.py parse_mx_message、on_posts 入库）。
4. **云端直连链路直接删除**（分层口径）：连接层全删（ws.py connect/重连/风暴
   标记、scheduler WS 循环/4h 强断/重连额度、生产 HTTP 三连、mx_activity 云端
   行为调度）；解析层保留为新架构资产。
5. **多账号接力**：备用账号补位主账号下线窗口（如午间间隙），主账号回归备用即
   下线；跨账号模糊去重（房间+时间相邻+内容相似 ≥90%），同账号重复如实入库。

## 否决的替代方案

- **MITM 代理（mitmproxy + 根证书）**：解密重加密后 TLS 指纹变成 mitmproxy 的——
  撞平台实锤在查的指纹检测。
- **页面内 hook（MAIN world 注入）**：constructor.toString 等可被页面 JS 探测。
- **Electron/Tauri 壳**：webview 指纹≠日常 Chrome，违背「真实浏览器」初衷。
- **纯独立 CDP agent（无扩展）**：Chrome 136+ 远程调试端口在默认 user-data-dir
  失效须独立 profile；Playwright/ChromeDriver 携带的自动化痕迹常驻。
- **冻结云端直连作为备份**：用户裁定「云端那套已经无法使用了」——非冻结，删除。

## 依据（spike 实证，2026-11-14）

- **Phase A PASS**：chrome.debugger 扩展与外部 CDP（connect_over_cdp）同时 attach
  同一 tab，三场景（扩展先挂/新 tab/reload 后）双方各自完整收到全部六类 Network
  事件，零互扰；CDP 点击 isTrusted=true。双 debugger 客户端共存前提坐实，
  native messaging 兜底通道不需要。
- **Phase B PASS**：真实 MX 会话——mx_login 全自动登录（AI 视觉识码）+ CDP 点击
  切房间，CDP 与扩展双源命中完全一致（view+notice 回访两连形态，与 801aaa1
  ground truth 吻合）、切房间零 WS emit 坐实、扩展帧完整上行 ingest。
- spike 产物在 .scratch/mx-spike/（扩展 sw.js + spike_dual_debugger.py +
  spike_mx_real.py），是 P1 开发的采集内核原型。

## 影响

- 防踢战线（四档退避/重连额度/风暴标记/4h 强断/Jenkins 换 token 链路）整体退役。
- 新增本地运维面：agent 常驻、Chrome 专用 profile、扩展分发（load-unpacked 或
  自托管 CRX，不进 Chrome Web Store）。
- 断采不兜底（Q4 用户裁定）：电脑关机/窗口外接受缺口，靠多账号接力对冲。
- 已知环境坑（开发须知）：branded Chrome 137+ 移除 --load-extension（扩展只能
  挂 Playwright Chromium 或组策略安装）；resvg-py 未装时 rasterize_svg 回落
  sync Playwright 在 async 进程内崩溃（装 resvg-py）；user_supplied LLM 的
  IP 固定安全体对 Ark 域名 IPv4 直连 400（生产 Jenkins 环境不受影响）。

## 后续（P1 路线，已与用户共识）

1. 扩展产品化（设备配对/IndexedDB 缓冲重传/seq 持久化/48h 挂机验证）
2. agent 产品化（三段窗口调度/接力逻辑/账号 profile 注册表）
3. 云端 ws 网关 + 分层删除云端直连
4. 48h 挂机 + 观察项（页面是否探测 attach、token 有效期边界、多标签多连接）
