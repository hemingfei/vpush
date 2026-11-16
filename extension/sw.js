// MX 采集器 service worker（票 #16：spike sw.js 的产品化）。
//
// 职责（严格被动，ADR-0001 零行为零决策）：
//   1. chrome.debugger attach（Network 域）被动抓 MX 页面的 WS 帧/HTTP 请求
//      ——不注入页面 JS（否决页面 hook：constructor.toString 可被探测）
//   2. 帧按云网关契约封装 {seq, ts, account, type, payload} 上行（wss 直连，
//      不经行为器中转——行为器崩溃只停行为不停采集，user story 7）
//   3. 引擎帧（2/3/0/40/41）本地过滤不上行（user story 21）
//   4. 断线缓冲 + 重连按序补传；上限 5000 丢最旧 + 计数上报（user story 8）
//   5. 配对/认证按网关首帧协议；吊销（close 4003）清密钥等人工重配对
//   6. SW 唤醒后自动重 attach MX 标签页（chrome.alarms 兜底，story 20）
//   7. 生命周期帧上报（attached/detached/disconnect/buffer_overflow，story 19）
//   8. badge 运维面（审计加分项）：免开 options 页看连接/缓冲/配对态
//
// spike 继承的设计决策（不得回退）：
//   ①attach 过滤配置每次事件时 await storage 读取（顶层一次性读取在 SW
//     重启后有竞态——sw_restart 窗口里读到旧值/空值）
//   ②配置变更不 reload SW（重启窗口丢事件）——写 storage 即时生效
//   ③零页面 JS 注入 ④MV3 + Playwright Chromium 开发路径（branded Chrome
//     137+ 已删 --load-extension，spike 首跑 FAIL 实锤）
//
// MV3 审计加固（2026-11-14，modern-web-guidance chrome-extensions 16 规则落地）：
//   ⑤连接互斥 + 陈旧回调守卫——connectGateway 同步互斥位挡同批入口，
//     `ws !== sock` 守卫挡孤儿 socket 的 onclose 串账（原三入口竞态可产生
//     孤儿 WS：变量被覆盖、旧 socket 关闭又触发新连接）
//   ⑥退避账目持久到 chrome.storage.session（src/conn_state.js）——原
//     setTimeout 重连不活过 SW 生命周期，退避在 SW 回收后归零；session 级
//     存储跨 SW 死亡存活、浏览器重启清零（重启无历史风暴，语义正确）
//   ⑦响应体登记写穿 storage.session（src/response_body.js）——SW 死于
//     requestWillBeSent 与 loadingFinished 之间不再静默丢登记
//
// 纯逻辑（引擎帧过滤/信封构造/seq/缓冲账目/配对状态机/host 校验/退避账目/
// 响应体登记）全部在 src/*.js 模块（node --test 本地测试覆盖），本文件只做
// Chrome API 接线。
import { isEngineFrame } from "./src/engine_frame.js";
import { validateIngestHost } from "./src/host_guard.js";
import { createEnvelopeFactory } from "./src/envelope.js";
import { createBuffer } from "./src/buffer.js";
import { createAuthClient } from "./src/auth_client.js";
import { createConnState } from "./src/conn_state.js";
import { shouldCaptureTab, shouldCaptureHttp } from "./src/attach_filter.js";
import { createResponseTracker } from "./src/response_body.js";

const DEBUGGER_VERSION = "1.3";
const ALARM_NAME = "mx-keepalive";
const RECONNECT_ALARM_NAME = "mx-reconnect";
const ALARM_PERIOD_MIN = 0.5; // spike 值：SW 被杀即 detach，靠 alarm 唤醒重挂

// chrome.storage 的 node/测试替身看不到的适配层（纯逻辑模块面对端口编程）；
// session 与 local 同形态（get(keys)/set(obj)），直接作端口传入
const storage = chrome.storage.local;
const sessionStore = chrome.storage.session;

// seq 与上行网关地址走 storage 持久层：SW 随时被杀，seq 重启归零会让补传帧
// 撞旧 seq 被网关幂等窗吞掉（网关按 (account, seq) 24h 幂等）
const seqStore = {
  async load() {
    const got = await storage.get(["mx_seq"]);
    return got.mx_seq || 0;
  },
  async save(v) {
    await storage.set({ mx_seq: v });
  },
};

// account 标签端口：信封构造时每次读取。取值来源 = 本扩展实例安装时在
// options 页配对阶段写入 storage.mx_account 的账号标签（S3 设计）：
// 行为器给每个账号一个专属 Chrome profile（ADR-0001，接力不并行在线），
// chrome.storage.local 按 profile 隔离——每个 profile 里的扩展实例只在
// 自己账号的浏览器里运行，故「按安装配置一次」即可与实际在线账号一致；
// 接力换账号 = 行为器换 profile = 另一个 profile 里的扩展实例带另一标签。
// （agent 与扩展互不感知是 ADR-0001 决策——不存在 agent→extension 写
// storage 的通道；旧注释「agent 写 storage.mx_account」是错误接线描述。）
const getAccount = async () => {
  const got = await storage.get(["mx_account"]);
  return got.mx_account || "main";
};
const envelope = createEnvelopeFactory({ getAccount, seqStore });
const buffer = createBuffer({ cap: 5000 });
const auth = createAuthClient({ storage });
const connState = createConnState({ store: sessionStore });
const respTracker = createResponseTracker({ sessionStore });

let ws = null;
let wsReady = false;
let connecting = false; // connectGateway 同步互斥位（同批入口第二发直接放弃）
let connectingSince = 0; // connecting 起始时刻（keepalive 自检判挂死用，2026-11-16）
let pairingWindowOpen = null; // options 页处于配对中：不自动 auth 打扰

// ---------- badge 运维面（审计加分项） ----------
// 语义（README 同步维护）：无字=已连接且缓冲空；数字=断线缓冲帧数（99 封顶）；
// 琥珀 ! = 待配对/已吊销；红底 = 有丢帧未上报。仅状态跃迁时刷新，不逐帧刷。
const BADGE_COLOR_IDLE = "#9aa0a6";
const BADGE_COLOR_OK = "#34a853";
const BADGE_COLOR_WARN = "#f9ab00";
const BADGE_COLOR_ERROR = "#ea4335";

async function updateBadge() {
  if (!chrome.action?.setBadgeText) return; // manifest 缺 action 键时 undefined（防御）
  try {
    const buffered = buffer.size();
    const dropped = buffer.droppedTotal();
    let text = "";
    let color = BADGE_COLOR_IDLE;
    if ((await auth.state()) === "needs_pair") {
      text = "!";
      color = BADGE_COLOR_WARN;
    } else if (wsReady) {
      color = BADGE_COLOR_OK;
      if (buffered) text = String(Math.min(buffered, 99));
    } else if (buffered) {
      text = String(Math.min(buffered, 99));
    }
    if (dropped > 0) color = BADGE_COLOR_ERROR; // 丢帧账目非零：压过在线绿
    await chrome.action.setBadgeBackgroundColor({ color });
    await chrome.action.setBadgeText({ text });
  } catch {
    /* badge 失败不影响采集 */
  }
}

// ---------- 生命周期上行（可查询面，user story 19） ----------

// buffer_overflow 生命周期上报的统一出口（T3 去重：reportLifecycle 与
// onopen 补传路径共用同一账目面——读计数 → 上报 → 清零，只在有丢帧时发）
async function reportOverflowIfAny(detailPrefix = "累计丢帧") {
  if (buffer.droppedTotal() <= 0) return;
  const dropped = buffer.droppedTotal();
  buffer.resetDropped();
  await send(await envelope.buildLifecycle("buffer_overflow", `${detailPrefix} ${dropped}`));
  await updateBadge();
}

async function reportLifecycle(event, detail = "") {
  const env = await envelope.buildLifecycle(event, detail);
  await send(env);
  // 断连期间 lifecycle 帧也进缓冲（断连事件本身除外——服务端断连记录由
  // 网关 _on_disconnect 落账，客户端再补发就是重复事件）
  await reportOverflowIfAny();
}

// ---------- 上行与缓冲补传 ----------

function rawSend(obj) {
  if (!wsReady || !ws || ws.readyState !== 1) return false;
  try {
    ws.send(JSON.stringify(obj));
    return true;
  } catch {
    return false;
  }
}

async function send(obj) {
  if (rawSend(obj)) return;
  buffer.push(obj);
  await persistBuffer();
  await updateBadge(); // 缓冲增长上 badge（断线运维面）
}

async function persistBuffer() {
  // 缓冲持久化：断线期间 SW 也可能被杀，内存缓冲会蒸发（spike 已知缺陷）。
  // 5000 × ~1KB 量级在 storage.local 10MB 限额内，IndexedDB 是 ADR 后续路线。
  try {
    await storage.set({ mx_buffer: buffer.items() });
  } catch {
    // 持久化失败不阻塞采集（内存缓冲仍在，本次 SW 生命周期内补传有效）
  }
}

async function restoreBuffer() {
  try {
    const got = await storage.get(["mx_buffer"]);
    if (Array.isArray(got.mx_buffer)) {
      for (const item of got.mx_buffer) buffer.push(item);
    }
  } catch {
    /* 空恢复 */
  }
}

// ---------- 配对 / 认证 / 重连 ----------

async function gatewayUrl() {
  const got = await storage.get(["mx_gateway_url"]);
  const raw = got.mx_gateway_url || "";
  // 生产只允许 wss 到自有域名；本地冒烟脚本配 ws://127.0.0.1 会被拒——
  // 扩展路径不做 insecure 开关（host_guard 的 allowInsecureDev 只在
  // node 冒烟脚本里用，绝不进扩展运行时）
  const url = validateIngestHost(raw);
  return url.toString();
}

// 退避重连排程（SW 存活期快路径；SW 死亡后由 0.5min 保活 alarm 兜底敲门，
// 真退避门控在 connState.acquire——旧 setTimeout 方案不活过 SW 生命周期，
// 审计已废）
async function scheduleReconnect(delayMs) {
  await chrome.alarms.create(RECONNECT_ALARM_NAME, {
    when: Date.now() + delayMs,
  });
}

async function connectGateway() {
  if (connecting) return; // 同批多入口（alarm/onclose/onInstalled）互斥
  if (ws && ws.readyState <= 1) return; // 已有活/半活连接
  const slot = await connState.acquire(); // 真退避门（session 持久，跨 SW 死亡）
  if (!slot) return; // 门内：等下一次 alarm 敲门
  connecting = true;
  connectingSince = Date.now();
  let url;
  try {
    url = await gatewayUrl();
  } catch (e) {
    connecting = false;
    // 网关地址未配置/非法：不重试（无目标可连），等 options 页写入配置
    console.warn("[mx] 网关地址未配置或非法:", e.message);
    return;
  }
  let sock;
  try {
    sock = new WebSocket(url);
  } catch {
    connecting = false;
    await connState.bump();
    await scheduleReconnect(await connState.penaltyMs());
    return;
  }
  ws = sock;
  // 连接看门狗（2026-11-16 过夜实锤）：网络黑洞下 WebSocket 卡在 CONNECTING
  // 永不回调（onopen/onclose 都不来），connecting=true 永挂——后续 alarm 全部
  // `if (connecting) return` 静默，断连 12 小时不自愈。10s 未 open 即主动
  // close（合法操作，触发 onclose 走 bump+重连）；onopen 正常到达时撤销。
  const openWatchdog = setTimeout(() => {
    if (ws === sock && sock.readyState === 0) {
      try { sock.close(); } catch (e) { /* 已死则无事 */ }
    }
  }, 10000);
  sock.onopen = async () => {
    clearTimeout(openWatchdog);
    if (ws !== sock) return; // 陈旧回调守卫
    connecting = false;
    // 首帧认证（浏览器 WS API 不能自定义 header——网关契约）。
    // 配对窗口开着时让 options 页走 pair，这里不抢首帧
    const state = await auth.state();
    if (state === "has_key" && !pairingWindowOpen) {
      // 传给 auth_client 的 ws 适配器：closeCode 透出网关拒绝后的关闭码
      // （拒绝路径 = 回 {ok:false} + close 4003，适配器须能读到 close 状态）
      const res = await auth.auth({
        send: (s) => sendFrameAwaitReply(sock, s),
        get closeCode() {
          return sock._closeCode ?? null;
        },
      });
      if (!res.ok) {
        // auth 拒绝（吊销）：auth_client 已清密钥；断开后自动重连会卡在
        // needs_pair，等人工重新配对（close 4003 由 onclose 收尾）
        console.warn("[mx] 认证被拒:", res.error);
        await updateBadge();
        return;
      }
    }
    wsReady = true;
    await connState.reset(); // 成功清账：档位与下刻门归零
    await chrome.alarms.clear(RECONNECT_ALARM_NAME);
    await updateBadge();
    const pending = buffer.drain();
    await persistBuffer();
    if (pending.length) {
      await reportLifecycle("ingest_connected", `补传 ${pending.length} 条缓冲帧`);
    }
    for (const env of pending) {
      if (!rawSend(env)) {
        buffer.push(env); // 补传途中又断：按序回队
        await persistBuffer();
        return;
      }
    }
    if (buffer.droppedTotal() > 0) {
      // 补传后的丢帧账目上报（与 reportLifecycle 内部共用 reportOverflowIfAny
      // 的读-报-清序列，仅文案区分补传场景）
      await reportOverflowIfAny("补传后上报累计丢帧");
    }
  };
  sock.onmessage = () => {
    /* 网关下发只有 pair/auth 响应（在首帧路径处理）；业务帧无下行 */
  };
  sock.onclose = (ev) => {
    if (ws !== sock) return; // 陈旧回调守卫：孤儿 socket 的 onclose 不串账
    wsReady = false;
    ws = null;
    connecting = false;
    auth.onServerClose(ev.code).then(async () => {
      await updateBadge();
      if (ev.code === 4003) {
        // 吊销：清密钥等人工重新配对（自动重试死密钥只会反复 4003）
        console.warn("[mx] 设备密钥已被吊销（4003），等待重新配对");
        return;
      }
      reportLifecycle("disconnect", `code=${ev.code}`).then(async () => {
        await connState.bump();
        await scheduleReconnect(await connState.penaltyMs());
      });
    });
  };
  sock.onerror = () => {
    if (ws === sock) wsReady = false; // onclose 必随其后，收尾在那边
  };
}

// 首帧发送 + 等一条 JSON 应答（pair/auth 的同步问答面）。命名即语义：
// sendFrameAwaitReply——发一帧、等一答；不解析协议之外的东西。
function sendFrameAwaitReply(sock, text) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      sock.removeEventListener("message", onMsg);
      resolve(null);
    }, 10000);
    function onClose(ev) {
      // 拒绝路径网关回 {ok:false} 后立即 close(4003)：响应帧与 close 事件
      // 都可能先到，close 码记录到 sock 上供 auth_client 适配器读取
      sock._closeCode = ev.code;
    }
    function onMsg(m) {
      try {
        const parsed = JSON.parse(m.data);
        clearTimeout(timer);
        sock.removeEventListener("message", onMsg);
        sock.removeEventListener("close", onClose);
        resolve(parsed);
      } catch {
        /* 非 JSON 忽略，继续等 */
      }
    }
    sock.addEventListener("message", onMsg);
    sock.addEventListener("close", onClose);
    sock.send(text);
  });
}

// options 页配对入口：pairingWindowOpen 挡 SW 的 auth 首帧，让码直达网关
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    if (msg?.cmd === "pair") {
      pairingWindowOpen = true;
      if (ws && ws.readyState <= 1) ws.close();
      try {
        const url = await gatewayUrl();
        const pairSock = new WebSocket(url);
        await new Promise((res, rej) => {
          pairSock.onopen = res;
          pairSock.onerror = () => rej(new Error("网关连接失败"));
          setTimeout(() => rej(new Error("网关连接超时")), 10000);
        });
        const res = await auth.pair(
          { send: (s) => sendFrameAwaitReply(pairSock, s), get closeCode() { return null; } },
          msg.code
        );
        pairSock.close();
        reply(res);
        if (res.ok) {
          pairingWindowOpen = null;
          await connState.reset(); // 配对成功：清退避账目，立即上线不被门挡
          await updateBadge();
          connectGateway();
        }
      } catch (e) {
        reply({ ok: false, error: String(e.message || e) });
      } finally {
        pairingWindowOpen = null;
      }
      return;
    }
    if (msg?.cmd === "status") {
      const got = await storage.get(["mx_gateway_url", "mx_site_prefix", "mx_device_key"]);
      reply({
        state: await auth.state(),
        connected: wsReady,
        buffered: buffer.size(),
        droppedTotal: buffer.droppedTotal(),
        reconnect: await connState.snapshot(),
        gatewayConfigured: Boolean(got.mx_gateway_url),
        sitePrefix: got.mx_site_prefix || "",
      });
      await updateBadge(); // options 页开着时 badge 同步（轮询驱动）
      return;
    }
    if (msg?.cmd === "forget") {
      await auth.forget();
      if (ws && ws.readyState <= 1) ws.close();
      await updateBadge();
      reply({ ok: true });
      return;
    }
    if (msg?.cmd === "testGateway") {
      try {
        const url = await gatewayUrl();
        reply({ ok: true, url: url.toString() });
      } catch (e) {
        reply({ ok: false, error: String(e.message || e) });
      }
      return;
    }
    reply({ ok: false, error: "未知指令" });
  })();
  return true; // 异步 reply
});

// ---------- debugger attach（被动采集内核） ----------

async function maybeAttach(tab) {
  if (!(await shouldCaptureTab(storage, tab))) return;
  try {
    await chrome.debugger.attach({ tabId: tab.id }, DEBUGGER_VERSION);
    await chrome.debugger.sendCommand({ tabId: tab.id }, "Network.enable");
    // 新 Network 会话 = 新 requestId 空间：上一会话的响应体登记全部作废，
    // 清表（含 SW 死亡后从 session 恢复的陈旧登记，防跨会话累积）
    await respTracker.clear();
    await reportLifecycle("attached", `tab=${tab.id} url=${tab.url}`);
  } catch (e) {
    // "Already attached to debugger with given target id" → 已挂（幂等），忽略；
    // 外部 CDP attach 不通知扩展（chrome.debugger 事件只报自己会话）——双
    // debugger 共存已由 spike Phase A 实证
    if (!String(e?.message || e).includes("Already attached")) {
      await reportLifecycle("attach_failed", `tab=${tab?.id} err=${String(e?.message || e)}`);
    }
  }
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "loading") maybeAttach(tab); // 导航/reload 后重 attach
});
chrome.tabs.onCreated.addListener((tab) => maybeAttach(tab));

// ---------- Network 事件（帧捕获） ----------

chrome.debugger.onEvent.addListener((source, method, params) => {
  (async () => {
    try {
      if (method === "Network.webSocketFrameReceived" || method === "Network.webSocketFrameSent") {
        const data = params?.response?.payloadData ?? "";
        if (isEngineFrame(data)) return; // 引擎帧不上行（与网关同判定）
        await send(
          await envelope.build(method.endsWith("Received") ? "ws_in" : "ws_out", data)
        );
      } else if (method === "Network.requestWillBeSent") {
        const url = params?.request?.url ?? "";
        if (!shouldCaptureHttp(url)) return;
        // 登记 + 先发请求面（响应体另帧补充：loadingFinished 后才能取）；
        // 登记写穿 storage.session——SW 死于两事件之间不丢登记（审计⑦）
        await respTracker.track(params?.requestId, params?.request);
        await send(
          await envelope.build("http", {
            url,
            method: params.request.method,
            body: params.request.postData ?? null,
          })
        );
      } else if (method === "Network.loadingFinished") {
        // 响应体采集（票 #16 交付物 2：requestWillBeSent + getResponseBody）：
        // loadingFinished 后 getResponseBody 才可用；只对已登记的关注请求取
        // （登记/组装纯逻辑在 src/response_body.js，node --test 覆盖）
        const entry = await respTracker.take(params?.requestId);
        if (!entry) return;
        let body = null;
        try {
          const resp = await chrome.debugger.sendCommand(
            { tabId: source.tabId }, "Network.getResponseBody",
            { requestId: params.requestId }
          );
          body = resp?.body ?? null; // base64 体按原样传（截断语义在 capBody）
        } catch {
          body = null; // 体取不到（流式/已被网络栈清理）：帧照发，体置 null
        }
        await send(
          await envelope.build("http", respTracker.buildPayload(entry, body))
        );
      } else if (method === "Network.loadingFailed") {
        await respTracker.take(params?.requestId); // 失败请求：只清登记不上行
      }
    } catch (e) {
      await reportLifecycle("on_event_error", String(e?.message || e));
    }
  })();
});

chrome.debugger.onDetach.addListener(async (source, reason) => {
  await reportLifecycle("detached", `tab=${source.tabId} reason=${reason}`);
});

// ---------- SW 保活 + 唤醒重挂（story 20） + 退避重连敲门 ----------

chrome.alarms.create(ALARM_NAME, { periodInMinutes: ALARM_PERIOD_MIN });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== ALARM_NAME && alarm.name !== RECONNECT_ALARM_NAME) return;
  (async () => {
    if (alarm.name === RECONNECT_ALARM_NAME) {
      // 退避到点的重连尝试：门控在 connState.acquire（早到/被挡直接放弃）
      connectGateway();
      return;
    }
    // SW 被杀即 debugger detach：唤醒时全 tab 扫描重挂（浏览器休眠唤醒后
    // 采集自动恢复的机制面）
    const tabs = await chrome.tabs.query({});
    for (const t of tabs) maybeAttach(t);
    // connecting 挂死自检（2026-11-16 过夜实锤第二道保险）：onopen 看门狗之外，
    // 每 tick 复核——connecting=true 超过 5 分钟（十倍于正常握手）即判死锁，
    // 强制复位（socket 由看门狗/浏览器超时自理，复位后本 tick 立即重试）。
    if (connecting && Date.now() - connectingSince > 5 * 60 * 1000) {
      console.warn("[mx] connecting 挂死 >5min，强制复位重试");
      connecting = false;
    }
    if (!ws || ws.readyState > 1) connectGateway();
  });
});

// ---------- 启动面 ----------

chrome.runtime.onInstalled.addListener(async () => {
  await restoreBuffer();
  await reportLifecycle("installed");
  await updateBadge();
  connectGateway();
});
chrome.runtime.onStartup.addListener(async () => {
  await restoreBuffer();
  await respTracker.restore(); // 浏览器重启 session 已清——防御性空操作
  await reportLifecycle("browser_startup");
  await updateBadge();
  connectGateway();
});

restoreBuffer().then(() => connectGateway());
respTracker.restore(); // SW 被杀重启：session 里存活的在途登记装回内存表
