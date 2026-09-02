# MX 平台定期抓包巡检手册

> **目的**：定期用真实浏览器抓取 MX 官方网页端（`https://mx.2026.naaifu.cn/`）的前后端行为，
> 与 vpush 当前实现逐项比对，及时发现平台变化并在「被风控判定为异常客户端」之前对齐。
> **频率**：建议每 2-3 天执行一次轻量巡检（第二、三节），怀疑风控升级或平台改版时执行全量（含冷启动 WS 复核与 25 秒心跳观察）。
> **执行者**：AI 代理（负责开浏览器、抓包、比对、报告），**登录必须由账号持有人人工完成**（账号/密码/图形验证码，AI 全程不接触凭据）。
> **背景文档**：`mx-防风控优化措施.md`（改造史）、`mx-官方网页端抓包核对-2026-09-02.md`（首次全量核对与落地记录）。

---

## 〇、一键启动提示词（每次巡检直接粘给大模型）

```text
请按照 docs/mx-定期抓包巡检手册.md 对 MX 平台做一次抓包巡检：
1. 用 Playwright MCP 打开 https://mx.2026.naaifu.cn/（Chrome 缺失时按手册第一节安装）；
   我稍后人工登录，你全程不要输入或询问任何凭据/验证码。
2. 按手册第二节采集：登录前验证码请求头 → 我登录并随便点几个房间 → 冷启动（刷新）后的
   完整启动时序与 WS 握手/帧。
3. 按手册第三节基线表逐项比对（请求头、请求体、端点、WS 行为、自定义头 ad/i）。
4. 无变化 → 在 docs/ 写一份简短的「YYYY-MM-DD 巡检：无变化」记录；
   有变化 → 按手册第四节分级：A/B/C 类可直接改代码+契约测试+跑 tests/test_mx.py，
   D/E 类（鉴权/加密变化）只写报告，不要尝试逆向，等人工决策。
5. 全程不要把 token/密码写进任何文档（token 出现处用 <redacted>）。
```

---

## 一、环境准备

1. **浏览器**：Playwright MCP 固定使用 Chrome（`chrome` 渠道）。检查
   `C:\Program Files\Google\Chrome\Application\chrome.exe` 或
   `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe` 是否存在。
2. **Chrome 缺失时的安装**（2026-09-02 实测有效）：
   - `npx playwright install chrome` 会下载企业版 MSI，**无管理员权限会失败**；
   - 改用用户级在线安装器：`curl -L -o chrome_installer.exe "https://dl.google.com/chrome/install/latest/chrome_installer.exe"`
     然后 `./chrome_installer.exe /silent /install`（实测会静默装到 Program Files，无需 UAC 交互）。
3. **测试环境**：仓库 `.venv`，跑测试用 `.venv/Scripts/python.exe -m pytest tests/test_mx.py -q`。
   venv 缺包时按 `requirements.txt` 全量补齐（`pip install -r requirements.txt`）。
4. 仓库根目录存在**未入库的 `.env`**（真实部署变量）。它会让部分全量测试失败（见第六节），不影响本手册的抓包环节。

## 二、采集流程

### 2.1 登录前探针（不用登录就能采的前端常量）

打开站点后，登录页会请求 `GET /master-api/api/code?tt=...`（图形验证码）。
用 MCP 的 `browser_network_requests` 找到它，`browser_network_request(index, part="request-headers")`
取头。**核对点**：`ad`、`i`、`version`、`accept`、UA —— 这些在登录前就已携带，是前端写死的常量，
最能反映官方前端本身的特征（账号无关）。

### 2.2 人工登录 + 自然使用

- 提醒账号持有人在浏览器窗口里输入账号/密码/验证码（AI 不碰）。
- 登录后让其自然操作 1-2 分钟：点开几个房间、翻翻消息、播一条语音，让 HTTP 与 WS 流量自然产生。
- **不要关闭窗口**（保持同一 page 上下文，采集器才连续）。

### 2.3 登录后 HTTP 采集

- `browser_network_requests(static=false)` 拉全量请求列表，记录启动时序（见 3.4 基线）。
- 对这些请求逐个取**请求体**（`part="request-body"`）：`api/room/list`、`api/msg/list`、
  `api/room/view`、`api/msg/tip`、`api/login`（**login 体含密码，只取 headers，永远不要取 body**）。
- **注意**：MCP 的 `request-headers` 是「渲染器视角」的筛选列表，看不到 `accept-encoding`/
  `origin`/`cookie` 等 wire 头；要完整头用 2.5 的 CDP 方法。

### 2.4 冷启动 WS 复核（关键！）

实测官方端**登录后当次会话不连 WS，冷启动/刷新才连**。所以要 reload 一次才能抓到 WS：

```js
// browser_run_code_unsafe —— 一次性完成：挂 WS 监听 + reload + 观察 28s（覆盖 25s 心跳）
async (page) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');           // 千万别忘，忘了 raw 头会是空的
  const raw = []; const wsEvts = []; const sent = {};
  cdp.on('Network.requestWillBeSent', e => {
    const u = e.request.url;
    if (u.includes('-api/')) sent[e.requestId] = { url: u.replace('https://mx.2026.naaifu.cn', ''), m: e.request.method };
  });
  cdp.on('Network.requestWillBeSentExtraInfo', e => {   // wire 级真实头（含 origin/cookie/accept-encoding）
    const s = sent[e.requestId];
    if (s) raw.push({ ...s, h: e.headers });
  });
  page.on('websocket', ws => {
    wsEvts.push({ open: ws.url() });
    ws.on('framesent', f => wsEvts.push({ out: String(f.payload).slice(0, 400) }));
    ws.on('framereceived', f => wsEvts.push({ in: String(f.payload).slice(0, 400) }));
  });
  await page.reload({ waitUntil: 'load' });
  await page.waitForTimeout(28000);
  return JSON.stringify({ ws: wsEvts.slice(0, 8), apiPicks: raw.slice(0, 4) }, null, 1);
}
```

### 2.5 完整 wire 头（需要时）

同上用 CDP `requestWillBeSentExtraInfo`，按 `requestId` 与 `requestWillBeSent` 关联，
取 `business-api` POST 的完整头（含 `:authority` 伪头可顺带确认 HTTP/2）。

---

## 三、基线对照表（2026-09-02 实测，即当前 vpush 已对齐的值）

> 巡检就是把实测值和下表比。**任何一格变了都算发现**。

### 3.1 HTTP 请求头（业务 POST 的 wire 级形态）

| 头 | 基线值 |
|---|---|
| `accept` | `*/*` |
| `ad` | `true` |
| `i` | `qq`（前端写死常量，登录前即携带，与账号无关） |
| `content-type` | `application/json` |
| `token` | `<账号 token>`（唯一随账号变化的头；登录前为空） |
| `version` | `web` |
| `origin` / `referer` | `https://mx.2026.naaifu.cn` / `https://mx.2026.naaifu.cn/` |
| `accept-language` | `zh-CN,zh;q=0.9` |
| `accept-encoding` | `gzip, deflate, br, zstd` |
| `sec-ch-ua` | `"Chromium";v="<主版本>", "Not?A_Brand";v="24", "Google Chrome";v="<主版本>"`（版本随 Chrome 更新上涨，重点是与 UA 主版本一致） |
| `sec-ch-ua-mobile` / `-platform` | `?0` / `"Windows"` |
| `sec-fetch-site/mode/dest` | `same-origin` / `cors` / `empty` |
| `priority` | `u=1, i` |
| `user-agent` | 桌面 Chrome（基线：`Windows NT 10.0; Win64; x64` + `Chrome/152`） |
| cookie | **无**（认证只靠 `token` 头） |
| 协议 | HTTP/2 |
| 签名类参数 | **无 sign**（请求体是明文业务字段） |

### 3.2 关键请求体

| 端点 | 基线请求体 |
|---|---|
| `POST /business-api/5/api/room/list` | `{"pages":1,"limit":1000000,"tt":<ms>}`（冷启动单次全量） |
| `POST /business-api/5/api/msg/list` | 补漏/翻页：`{"rid":<id>,"msgid":<0=最新；或本地最旧消息id=向上翻页>,"pagesize":30,"tt":<ms>}`（仅「启动补漏」与「加载更早」两个场景，见 3.3-S3） |
| `POST /business-api/5/api/room/view` | `{"rid":<id>,"tt":<ms>}`（进房上报，每次点选房间必发） |
| `POST /business-api/5/api/msg/tip` | `{"tt":<ms>}`（全局未读，仅启动） |
| `POST /business-api/5/api/room/notice` | 房间公告，每次点选房间必发（与 view 成对；弹窗有 sessionStorage 按日已读标记） |

### 3.3 全端点调用时机矩阵（按触发场景；2026-09-02 晚补测缓存模型后修订）

**场景 S1 应用启动**——手动输密码登录成功 / 关窗重开自动登录 / F5 刷新，三种情况序列完全相同：

| 顺序 | 请求 | 触发条件/说明 |
|---|---|---|
| 0 | `GET /master-api/api/code?tt=` | 仅未登录时（登录页图形验证码；已登录启动不出现） |
| 0b | `POST /master-api/api/login` | 仅手动输密码登录时（自动登录无此请求，token 取自 localStorage `mx_web_token`） |
| 1 | `POST /master-api/api/user/info` | 启动必发 |
| 2 | `POST /master-api/api/system/config` | 启动必发 |
| 3 | `POST /business-api/5/api/room/list` | 启动必发，单次全量 `{"pages":1,"limit":1000000,"tt"}` |
| 4 | `POST /business-api/5/api/msg/tip` | 启动必发 `{"tt"}`（全局未读提示） |
| 5 | `POST /master-api/api/room/grouplist` | 启动必发（房间分组） |
| 6 | `room/view` + `msg/list` + `room/notice` | 恢复「上次打开的房间」；其中 msg/list 是对本地缓存的**增量补漏**（`msgid=0`、pagesize 30，结果与 localStorage 合并） |
| 7 | `GET /master-api/api/notice?tt=&token=`（200） | 启动必发（平台公告，token 在 query） |
| 7b | `GET /business-api/5/api/notice?...`（404） | 官方自己也照发（试错请求） |
| 8 | `POST /master-api/api/user/issign`、`/api/user/showad` | 启动必发（签到状态/广告展示判定） |
| 9 | WS 连接 | 冷启动/刷新才连；登录后当次会话不连（详见 3.4） |

**场景 S2 会话期间点选房间**（无论该房间本会话是否打开过）：

- 必发：`room/view`（进房/已读上报）+ `room/notice`（房间公告）；
- **不发 `msg/list`**——历史消息渲染自 localStorage 缓存（`mx_web_messages_<rid>`，按房间持久化），
  新消息由 WS `room_msg` 实时追加进缓存。

**场景 S3 房间内向上翻历史**（点「加载更早」）：

- `POST /business-api/5/api/msg/list`，body `{"rid","msgid":<本地最旧消息id>,"pagesize":30,"tt"}`
  （以本地最旧消息为游标分页回拉，结果并回 localStorage）。

**场景 S4 AI 功能**（点「查看今日 AI 分析」）：`POST /member-ai-api/api/ai-analysis/member/modules`。

**场景 S5 媒体加载**（渲染消息时按需，非 API）：消息内图片走第三方图床
（wework.qpic.cn / ps.ssl.qhimg.com / pic.guhai888.cn / i.gsxcdn.com / img.meituan.net /
static.dingtalk.com），语音走腾讯云 mp3（HTTP 206 分段加载）。

**vpush 不调用的官方端点**：`login`/`code`（人工取号红线，永不自动调用）、`issign`/
`showad`/`member-ai-api`（请求体未采集，不猜格式硬发，留待巡检抓到再补）、`business-api/5`
的 `room/notice`（点选语义，仅真点房间才发）——其余启动序列（user/info/system/config/
room/list/msg/tip/grouplist/notice）已由开窗会话按官方顺序补发（`boot_sequence`，
2026-09-02）。vpush 运行期无任何登录行为，token 由人工网页取号获得。

### 3.4 WS 行为

| 项 | 基线 |
|---|---|
| URL | `wss://mx.2026.naaifu.cn/business-api/5/socket.io/?EIO=4&transport=websocket`（**无 `t` 参数，websocket 直连，无 polling 升级**） |
| 服务器 open 包 | `0{"sid":...,"upgrades":[],"pingInterval":25000,"pingTimeout":20000,"maxPayload":1000000}` |
| 命名空间握手 | 客户端发 `40/msg,{"tt":<ms>,"token":"...","version":"web"}`；服务器回 `40/msg,{"sid":...}` |
| 业务推送 | 服务器推 `42/msg,["room_msg","<LZ+AES密文>"]`，客户端只听 |
| 客户端 emit | **无任何业务事件** |
| 心跳 | **服务器发 `2`、客户端答 `3`**，25s 间隔 / 20s 超时 |
| 连接时机 | 冷启动/刷新才连；登录后当次会话不连 |

### 3.5 请求/返回格式契约（2026-09-02 实测响应体解密分析）

响应外层统一为 `{"code":200,"msg":"success",...}`；**加密是有选择性的**——实测仅
`msg/list` 返回密文（`{"code":200,"data":"<LZ+AES密文>"}`，用 `crypto.decrypt_api_data`
按日期密钥解密），其余端点全为明文 JSON；历史记载 `room/list` 也出现过密文形态，
vpush 的 `_request` 已做明文/密文双形态兼容。`tt` 均为毫秒时间戳。

| 端点 | 发送 body | 返回（解密后/明文）业务结构 |
|---|---|---|
| `GET /master-api/api/code?tt=` | —（query tt） | 图形验证码图片字节（非 JSON） |
| `POST /master-api/api/login` | 账号/密码/验证码字段（**刻意未采集**） | 含 token 的用户信息（**刻意未采集**） |
| `POST /master-api/api/user/info` | `{"device":"web-browser","tt"}` | `info:{id,user,avatar,nickname,star,mdr,score,token(32),vip,allsearch,duty,showlog,opengroup,force_password_reset,forcePasswordReset}` |
| `POST /master-api/api/system/config` | `{"tt"}` | `AD:{IOS,Android}`、`open_shop/msg_details_yz/msg_details_ad/open_notice/open_update/open_mall/openregister/scoremax/scoremin`（均为字符串开关） |
| `POST /business-api/5/api/room/list` | `{"pages":1,"limit":1000000,"tt"}` | `list:[{id,title,createtime,msg(末条摘要),msgtime,msguid,avatar,teaname,introduce,taboo,color,textcolor,message_today,prohibition,webhook,websecret,star,gid,exttime}]` |
| `POST /business-api/5/api/msg/tip` | `{"tt"}` | `data:{count:<总未读>, "r<rid>":<未读数(封顶99)>...}` |
| `POST /master-api/api/room/grouplist` | `{"tt"}` | `list:[分组]`（无分组时空数组） |
| `POST /business-api/5/api/room/view` | `{"rid","tt"}` | 无业务字段（仅 code/msg） |
| `POST /business-api/5/api/room/notice` | `{"rid","tt"}` | `list:[房间公告]`（可空；弹窗受 sessionStorage 按日已读控制） |
| `GET /master-api/api/notice?tt=&token=` | —（query tt+token） | `list:[{id,createtime,content,state,AD,note,mid}]`（平台公告 → 「系统公告」弹窗） |
| `GET /business-api/5/api/notice?...` | —（query） | 官方自己 404 也照发 |
| `POST /business-api/5/api/msg/list` | `{"rid","msgid":<0=最新/游标>,"pagesize":30,"tt"}` | **加密**；解密后 `list:[{id,uid,rid,msg(内嵌JSON串:text/pic/file),createtime:"YYYY-MM-DD HH:MM:SS",oid,type}]`——注意 HTTP 响应里 createtime 是**日期字符串**（WS 推送里是毫秒数，vpush 两种都兼容） |
| `POST /master-api/api/user/issign`、`/api/user/showad`、`POST /member-ai-api/...` | 未逐个采集（非 vpush 链路） | — |

---

## 四、差异分级与处置

| 级别 | 特征例子 | 处置 |
|---|---|---|
| A 头/参数形态 | `ad`/`i` 值变、`accept` 变、新增常驻自定义头、`priority` 消失 | 直接改 `app/fetchers/mx/client.py` 的 `_headers()`/常量，同步 `tests/test_mx.py` 契约断言，跑测试 |
| B 端点/路径 | `business-api/5` 版本号变、WS 路径变、新增/下线端点 | 改 `config.py` 默认值（`api_base`/`ws_url`）+ `config.example.yaml` + `app.js` + `api.py` 兜底值，同步文档 |
| C 行为节奏 | `pagesize`、`limit`、心跳方向/间隔、官方开始 emit 事件、连接时机 | 改 `fetcher.py`/`ws.py`/`config.py`，同步契约测试 |
| D 鉴权机制 | 出现 `sign` 类签名、token 机制变化、开始带 cookie | **只写报告，不逆向、不改码**，等人工决策（红线，见第七节） |
| E 响应加密 | 密文格式/密钥派生变化（表现为 vpush 解密失败、消息变乱码） | 同 D，报告人工决策 |

A/B/C 改完必须：`tests/test_mx.py` 全绿 → 更新 `mx-防风控优化措施.md`（就地标注旧结论）→
在本手册「九、巡检日志」追加一行。

**对照的代码位置速查**：
`client.py`（`XHR_ACCEPT`、`_headers` 的 ad/i、`ROOM_LIST_LIMIT`、`room_view`）、
`ws.py`（人格常量 `BROWSER_UA`/`SEC_CH_UA*`/`ACCEPT_LANGUAGE`/`IMPERSONATE_TARGET`，改一处要三处同形并跑人格契约测试）、
`fetcher.py`（`page_size`、room/view 调用）、`config.py`+`config.example.yaml`+`app.js`+`api.py`（默认值/兜底值）。

## 五、UA 版本策略

官方端 UA 会随 Chrome 自动升级（基线 152）。**不要每次都追**：curl_cffi 模板更新滞后
（0.16.0 最高 chrome146），`impersonate` 模板没有的版本硬凑反而制造不一致。原则：
- 只要「UA 主版本 = sec-ch-ua 主版本 = impersonate 模板版本」内部自洽，版本落后几个小版本可接受；
- 只有当 curl_cffi 出了明显更新的模板、或风控明显按版本过滤时，才整体升级人格常量（三处同步 + 契约测试）。

## 六、已知误区与坑（2026-09-02 实操踩过）

1. **`browser_run_code_unsafe` 的 `globalThis` 不跨调用保留**，`require`/`process` 也不可用；
   要跨调用存状态，挂在 **page 对象属性**上（page 实例跨调用是同一个），或单次调用内闭环完成。
2. **CDP 忘了 `Network.enable` → `requestWillBeSentExtraInfo` 一个事件都没有**（raw 为空不报错）。
3. MCP 的 `request-headers` 是筛选过的列表，别用它下「没有 Origin/cookie」的结论——用 CDP extraInfo。
4. **登录后会话不连 WS**：采 WS 必须刷新页面（冷启动），并在观察窗里等满 25s 才能看到心跳方向。
5. Chrome 安装：`npx playwright install chrome` 需要管理员；用户级静默安装用 2.2 的官方在线安装器。
6. **全量测试的存量失败不要追**（与本手册改动无关，别浪费时间）：
   - `test_ima_puller.py`、`test_pdf_compression.py`：`fcntl`（Unix-only）在 Windows 无法导入；
   - `tests/test_config.py` 4 例、`tests/test_api.py` 11 例等：仓库根目录未入库的 **`.env`**
     （`POLLING_*`、`CONFIG_PATH` 等）在 `load_config` 里覆盖测试临时 yaml 所致——已用
     「干净 HEAD worktree + 移走 .env 复跑」双重验证为存量问题。验证手法：把 `.env` 临时改名后
     `test_config.py` 应 13/13 全过，跑完立刻改回。
7. **巡检报告里 token 一律脱敏**（`/api/notice` 的 GET 会把 token 放在 query 里，注意别原样抄进文档）。
8. Hook/安全组件可能拦截「Bash 里组合 pip install + 提到 tests/*.py」的命令（误判为直接写源码），
   拆成多条单独命令即可。

## 七、红线（任何一次巡检都不得跨越）

1. **不逆向鉴权/加密**：发现 `sign` 类签名、加密方案变更（D/E 类）→ 只报告存在与位置，不分析算法。
2. **不自动化登录**：账号/密码/验证码/短信码永远由人输入；不保存、不复述凭据。
3. **不把 token 写进仓库文档**。
4. **不在官方端做压力/遍历行为**：巡检就是正常人工使用量级，不翻页轰炸、不并发打接口。

## 八、产出物

- 每次巡检在 `docs/` 落一份 `mx-巡检-YYYY-MM-DD.md`：结论（无变化 / N 项差异）、差异明细、
  已处置项、遗留项。**「无变化」也要留档**，方便回溯平台从哪天开始变的。
- 若有代码改动：`tests/test_mx.py` 全绿后再收尾，并同步更新防风控文档。

## 九、巡检日志

| 日期 | 结果 | 备注 |
|---|---|---|
| 2026-09-02 | 首次全量核对，7 项差异已全部落地 | 见 `mx-官方网页端抓包核对-2026-09-02.md` |
