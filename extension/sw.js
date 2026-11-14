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
//
// spike 继承的设计决策（不得回退）：
//   ①attach 过滤配置每次事件时 await storage 读取（顶层一次性读取在 SW
//     重启后有竞态——sw_restart 窗口里读到旧值/空值）
//   ②配置变更不 reload SW（重启窗口丢事件）——写 storage 即时生效
//   ③零页面 JS 注入 ④MV3 + Playwright Chromium 开发路径（branded Chrome
//     137+ 已删 --load-extension，spike 首跑 FAIL 实锤）
//
// 纯逻辑（引擎帧过滤/信封构造/seq/缓冲账目/配对状态机/host 校验）全部在
// src/*.js 模块（node --test 本地测试覆盖），本文件只做 Chrome API 接线。
import { isEngineFrame } from "./src/engine_frame.js";
import { validateIngestHost } from "./src/host_guard.js";
import { createEnvelopeFactory } from "./src/envelope.js";
import { createBuffer } from "./src/buffer.js";
import { createAuthClient } from "./src/auth_client.js";
import { shouldCaptureTab, shouldCaptureHttp } from "./src/attach_filter.js";

const DEBUGGER_VERSION = "1.3";
const ALARM_NAME = "mx-keepalive";
const ALARM_PERIOD_MIN = 0.5; // spike 值：SW 被杀即 detach，靠 alarm 唤醒重挂
const RECONNECT_BASE_MS = 2000; // 指数退避基数（spike 固定 2s 的产品化）
const RECONNECT_MAX_MS = 120000;

// chrome.storage.local 的 node/测试替身看不到的适配层（纯逻辑模块面对端口编程）
const storage = chrome.storage.local;

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

// account 标签端口：信封构造时每次读取（接力换账号补位时后续帧带新标签，
// 云端跨账号模糊去重按标签豁免同账号）。agent 写 storage.mx_account。
const getAccount = async () => {
  const got = await storage.get(["mx_account"]);
  return got.mx_account || "main";
};
const envelope = createEnvelopeFactory({ getAccount, seqStore });
const buffer = createBuffer({ cap: 5000 });
const auth = createAuthClient({ storage });

let ws = null;
let wsReady = false;
let reconnectAttempts = 0;
let pairingWindowOpen = null; // options 页处于配对中：不自动 auth 打扰

// ---------- 生命周期上行（可查询面，user story 19） ----------

async function reportLifecycle(event, detail = "") {
  const env = await envelope.buildLifecycle(event, detail);
  await send(env);
  // 断连期间 lifecycle 帧也进缓冲（断连事件本身除外——服务端断连记录由
  // 网关 _on_disconnect 落账，客户端再补发就是重复事件）
  if (buffer.droppedTotal() > 0 && wsReady) {
    const dropped = buffer.droppedTotal();
    buffer.resetDropped();
    await send(await envelope.buildLifecycle("buffer_overflow", `累计丢帧 ${dropped}`));
  }
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

async function scheduleReconnect() {
  if (ws && ws.readyState <= 1) return; // 已有活连接（重连竞态双保险）
  const delay = Math.min(
    RECONNECT_BASE_MS * 2 ** reconnectAttempts,
    RECONNECT_MAX_MS
  );
  reconnectAttempts += 1;
  setTimeout(connectGateway, delay);
}

async function connectGateway() {
  let url;
  try {
    url = await gatewayUrl();
  } catch (e) {
    // 网关地址未配置/非法：不重试（无目标可连），等 options 页写入配置
    console.warn("[mx] 网关地址未配置或非法:", e.message);
    return;
  }
  try {
    ws = new WebSocket(url);
  } catch {
    scheduleReconnect();
    return;
  }
  wsReady = false;
  ws.onopen = async () => {
    // 首帧认证（浏览器 WS API 不能自定义 header——网关契约）。
    // 配对窗口开着时让 options 页走 pair，这里不抢首帧
    const state = await auth.state();
    if (state === "has_key" && !pairingWindowOpen) {
      // 传给 auth_client 的 ws 适配器：closeCode 透出网关拒绝后的关闭码
      // （拒绝路径 = 回 {ok:false} + close 4003，适配器须能读到 close 状态）
      const res = await auth.auth({
        send: (s) => jsonReply(ws, s),
        get closeCode() {
          return ws._closeCode ?? null;
        },
      });
      if (!res.ok) {
        // auth 拒绝（吊销）：auth_client 已清密钥；断开后自动重连会卡在
        // needs_pair，等人工重新配对
        console.warn("[mx] 认证被拒:", res.error);
        return;
      }
      wsReady = true;
      reconnectAttempts = 0;
      const pending = buffer.drain();
      await persistBuffer();
      await reportLifecycle("ingest_connected", `补传 ${pending.length} 条缓冲帧`);
      for (const env of pending) {
        if (!rawSend(env)) {
          buffer.push(env); // 补传途中又断：按序回队
          await persistBuffer();
          return;
        }
      }
      if (buffer.droppedTotal() > 0) {
        const dropped = buffer.droppedTotal();
        buffer.resetDropped();
        await reportLifecycle("buffer_overflow", `补传后上报累计丢帧 ${dropped}`);
      }
    }
  };
  ws.onmessage = () => {
    /* 网关下发只有 pair/auth 响应（在首帧路径处理）；业务帧无下行 */
  };
  ws.onclose = (ev) => {
    wsReady = false;
    auth.onServerClose(ev.code).then(() => {
      if (ev.code === 4003) {
        // 吊销：清密钥等人工重配对（自动重试死密钥只会反复 4003）
        console.warn("[mx] 设备密钥已被吊销（4003），等待重新配对");
        return;
      }
      reportLifecycle("disconnect", `code=${ev.code}`).then(scheduleReconnect);
    });
  };
  ws.onerror = () => {
    wsReady = false;
  };
}

// 首帧发送 + 等一条 JSON 响应（pair/auth 的同步问答面）
function jsonReply(sock, text) {
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
          { send: (s) => jsonReply(pairSock, s), get closeCode() { return null; } },
          msg.code
        );
        pairSock.close();
        reply(res);
        if (res.ok) {
          pairingWindowOpen = null;
          reconnectAttempts = 0;
          connectGateway(); // 配对完成立即用新密钥上线
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
        gatewayConfigured: Boolean(got.mx_gateway_url),
        sitePrefix: got.mx_site_prefix || "",
      });
      return;
    }
    if (msg?.cmd === "forget") {
      await auth.forget();
      if (ws && ws.readyState <= 1) ws.close();
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
        await send(
          await envelope.build("http", {
            url,
            method: params.request.method,
            body: params.request.postData ?? null,
          })
        );
      } else if (method === "Network.webSocketCreated") {
        // HTTP body 抓取按需启用：getResponseBody 只对关注请求调用（spike
        // 验证路径：requestWillBeSent → requestId → Network.getResponseBody）
      }
    } catch (e) {
      await reportLifecycle("on_event_error", String(e?.message || e));
    }
  })();
});

chrome.debugger.onDetach.addListener(async (source, reason) => {
  await reportLifecycle("detached", `tab=${source.tabId} reason=${reason}`);
});

// ---------- SW 保活 + 唤醒重挂（story 20） ----------

chrome.alarms.create(ALARM_NAME, { periodInMinutes: ALARM_PERIOD_MIN });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== ALARM_NAME) return;
  (async () => {
    // SW 被杀即 debugger detach：唤醒时全 tab 扫描重挂（浏览器休眠唤醒后
    // 采集自动恢复的机制面）
    const tabs = await chrome.tabs.query({});
    for (const t of tabs) maybeAttach(t);
    if (!ws || ws.readyState > 1) connectGateway();
  })();
});

// ---------- 启动面 ----------

chrome.runtime.onInstalled.addListener(async () => {
  await restoreBuffer();
  await reportLifecycle("installed");
  connectGateway();
});
chrome.runtime.onStartup.addListener(async () => {
  await restoreBuffer();
  await reportLifecycle("browser_startup");
  connectGateway();
});

restoreBuffer().then(() => connectGateway());
