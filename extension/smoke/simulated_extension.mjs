// 模拟扩展内核（冒烟脚本的 node 侧驱动，票 #16 验收：本地冒烟可复现）。
//
// 复用 extension/src 生产模块（auth_client/envelope/engine_frame/buffer/
// host_guard）——冒烟走的就是产品代码，不是重写的替身；只有「chrome.debugger
// 事件源」与「chrome.storage.local」换成 node 侧替身（spec 裁定：真实
// GUI Chrome 会话由 48h 挂机验收覆盖，不进 CI）。
//
// 与 Python 冒烟驱动（scripts/mx_extension_smoke.py）的协议：
//   stdin:  每行一个 JSON 指令 {cmd, ...}
//   stdout: 每行一个 JSON 结果 {ok, ...}
import {WebSocket} from "ws";
import readline from "node:readline/promises";

import { isEngineFrame } from "../src/engine_frame.js";
import { validateIngestHost } from "../src/host_guard.js";
import { createEnvelopeFactory } from "../src/envelope.js";
import { createBuffer } from "../src/buffer.js";
import { createAuthClient } from "../src/auth_client.js";

// chrome.storage.local 替身（持久到内存）
const mem = new Map();
const storage = {
  async get(k) {
    const keys = Array.isArray(k) ? k : [k];
    const out = {};
    for (const key of keys) if (mem.has(key)) out[key] = mem.get(key);
    return out;
  },
  async set(obj) {
    for (const [k, v] of Object.entries(obj)) mem.set(k, v);
  },
  async remove(keys) {
    for (const k of keys) mem.delete(k);
  },
  snapshot() {
    return Object.fromEntries(mem.entries());
  },
};

const seqStore = {
  async load() {
    const got = await storage.get(["mx_seq"]);
    return got.mx_seq || 0;
  },
  async save(v) {
    await storage.set({ mx_seq: v });
  },
};
const getAccount = async () => (await storage.get(["mx_account"])).mx_account || "main";
const envelope = createEnvelopeFactory({ getAccount, seqStore });
const buffer = createBuffer({ cap: 5000 });
const auth = createAuthClient({ storage });

let ws = null;
const lifecycle = []; // 供断言的生命周期事件账本
let account = "";

// 模拟 chrome.debugger.onEvent 的帧入口（Python 侧注入帧）：
// 走与 SW 相同的管线——引擎帧过滤 → 信封 → 发送/缓冲
async function feedFrame(kind, payload) {
  if (kind === "ws_in" || kind === "ws_out") {
    if (isEngineFrame(payload)) return "filtered_engine";
  }
  const env = await envelope.build(kind, payload);
  await sendEnvelope(env);
  return "captured";
}

async function sendEnvelope(env) {
  if (ws && ws.readyState === 1) {
    try {
      ws.send(JSON.stringify(env));
      return "sent";
    } catch {
      /* fallthrough to buffer */
    }
  }
  buffer.push(env);
  return "buffered";
}

async function lifecycleEvent(event, detail = "") {
  const env = await envelope.buildLifecycle(event, detail);
  lifecycle.push({ seq: env.seq, event, detail });
  return sendEnvelope(env);
}

function waitForMessage(sock, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      sock.removeEventListener("message", onMsg);
      reject(new Error("等待网关响应超时"));
    }, timeoutMs);
    function onMsg(m) {
      clearTimeout(timer);
      sock.removeEventListener("message", onMsg);
      resolve(JSON.parse(m.data));
    }
    sock.addEventListener("message", onMsg);
  });
}

async function openSocket(url) {
  // 冒烟脚本连本地网关测试服——走 allowInsecureDev 开关（仅 ws://127.0.0.1
  // 放行；扩展运行时路径绝不带该开关）
  validateIngestHost(url, { allowInsecureDev: true });
  return new Promise((resolve, reject) => {
    const sock = new WebSocket(url);
    sock.on("open", () => resolve(sock));
    sock.on("error", (e) => reject(e));
  });
}

// 指令处理（Python 驱动经 stdin 下发）
async function handle(cmd) {
  switch (cmd.cmd) {
    case "configure": {
      await storage.set({ mx_gateway_url: cmd.url, mx_account: cmd.account || "main" });
      return { ok: true };
    }
    case "pair": {
      const sock = await openSocket(cmd.url);
      const reply = await waitForMessage(sock).catch(() => null); // 吸收首帧前噪声（不会发生，防御）
      void reply;
      const res = await auth.pair(
        { send: (s) => { sock.send(s); return waitForMessage(sock); }, get closeCode() { return null; } },
        cmd.code
      );
      sock.close();
      return res;
    }
    case "auth_connect": {
      // 模拟 SW connectGateway：连网关 → 首帧 auth → 认证通过进入会话
      ws = await openSocket(cmd.url);
      const key = (await storage.get(["mx_device_key"])).mx_device_key;
      ws.send(JSON.stringify({ op: "auth", key }));
      const res = await waitForMessage(ws);
      if (!res.ok) {
        await auth.onServerClose(4003);
        return { ok: false, error: res.error };
      }
      // 认证通过：补传缓冲（按序 = buffer.drain() 的入队顺序，seq 单调）
      const pending = buffer.drain();
      for (const env of pending) {
        const sent = await sendEnvelope(env);
        if (sent !== "sent") {
          buffer.push(env); // 补传途中断线：按序回队
          break;
        }
      }
      ws.on("close", (ev) => {
        auth.onServerClose(ev).then(() => {
          lifecycle.push({ event: "disconnect", detail: `code=${ev.code ?? 1006}` });
        });
      });
      return { ok: true, flushed: pending.length };
    }
    case "feed": {
      // 模拟 chrome.debugger onEvent 批量帧注入
      const results = [];
      for (const f of cmd.frames) results.push(await feedFrame(f.kind, f.payload));
      return { ok: true, results };
    }
    case "lifecycle": {
      const res = await lifecycleEvent(cmd.event, cmd.detail || "");
      return { ok: true, delivery: res };
    }
    case "close_socket": {
      // 模拟断连（不带 ws.close() 的优雅关闭——直接销毁，网关视为异常断开）
      if (ws) {
        ws.terminate();
        ws = null;
      }
      return { ok: true };
    }
    case "drop_oldest_overflow": {
      // 压缓冲上限：灌满 cap+1 条制造一次丢最旧（验收「上限 5000 丢最旧并
      // 计数上报」的账目面——用小 cap 复刻同一逻辑，见 buffer 模块单测）
      const before = buffer.droppedTotal();
      const env = await envelope.build("ws_in", "overflow probe");
      buffer.push(env);
      return { ok: true, droppedTotal: buffer.droppedTotal() - before };
    }
    case "status": {
      return {
        ok: true,
        state: await auth.state(),
        buffered: buffer.size(),
        droppedTotal: buffer.droppedTotal(),
        lifecycle,
        storage: storage.snapshot(),
      };
    }
    case "reconnect": {
      // 模拟 SW 重启后 restoreBuffer + 重连（seq 从 storage 恢复不归零）
      if (ws) {
        ws.terminate();
        ws = null;
      }
      return { ok: true };
    }
    default:
      return { ok: false, error: `未知指令: ${cmd.cmd}` };
  }
}

const rl = readline.createInterface({ input: process.stdin });
const out = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");
for await (const line of rl) {
  if (!line.trim()) continue;
  try {
    out(await handle(JSON.parse(line)));
  } catch (e) {
    out({ ok: false, error: String(e?.message || e) });
  }
}
