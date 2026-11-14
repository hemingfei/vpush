// 配对/认证客户端状态机的本地单测（票 #16 交付物 6）。
//
// 契约真相源 = tests/test_mx_gateway.py + app/services/mx_gateway.py：
// - 连接后首帧二选一：{"op":"pair","code":8位码} → {ok:true,device_key}（码
//   一次性，作废）；{"op":"auth","key":设备密钥} → {ok:true}；
// - 首帧非 pair/auth → {ok:false} + close 4001；
// - 未知/被吊销密钥 → {ok:false,"设备密钥无效或已吊销"} + close 4003；
// - 存量连接被吊销时服务端直接 close 4003（无前置 ok 帧）；
// - 密钥存 chrome.storage.local（本测试用内存 store 替身）。
import { test } from "node:test";
import assert from "node:assert/strict";

import { createAuthClient } from "../src/auth_client.js";

function memoryKV() {
  // chrome.storage.local.get 形态：key 或 key[] 皆可（实现对齐 Chrome API）
  const m = new Map();
  return {
    async get(k) {
      const keys = Array.isArray(k) ? k : [k];
      const out = {};
      for (const key of keys) if (m.has(key)) out[key] = m.get(key);
      return out;
    },
    async set(obj) {
      for (const [k, v] of Object.entries(obj)) m.set(k, v);
    },
    async remove(keys) {
      for (const k of keys) m.delete(k);
    },
    _m: m,
  };
}

// 假 ws：记录发送帧；reply+closeCode 组合模拟网关响应（拒绝时网关先回
// {ok:false} 再 close(4003)，客户端是被关方，closeCode 在 send 返回时即已定）
function fakeWs({ reply, closeCode } = {}) {
  const sent = [];
  let closed = null;
  return {
    sent,
    get closeCode() {
      return closed;
    },
    send(s) {
      sent.push(JSON.parse(s));
      if (closeCode != null) closed = closeCode; // 网关在回拒后关闭
      if (reply) return Promise.resolve(reply);
      return Promise.resolve({ ok: true });
    },
    close(code) {
      closed = code;
      return Promise.resolve();
    },
  };
}

test("无密钥时状态为 needs_pair（触发配对流程）", async () => {
  const client = createAuthClient({ storage: memoryKV() });
  assert.equal(await client.state(), "needs_pair");
});

test("pair 成功：下发密钥存 storage，状态转 has_key", async () => {
  const storage = memoryKV();
  const client = createAuthClient({ storage });
  const ws = fakeWs({ reply: { ok: true, device_key: "k".repeat(64) } });
  const res = await client.pair(ws, "12345678");
  assert.deepEqual(res, { ok: true });
  assert.deepEqual(ws.sent, [{ op: "pair", code: "12345678" }]);
  assert.equal((await storage.get("mx_device_key")).mx_device_key, "k".repeat(64));
  assert.equal(await client.state(), "has_key");
});

test("pair 失败（码无效/已用）：不存密钥，仍 needs_pair", async () => {
  const storage = memoryKV();
  const client = createAuthClient({ storage });
  const ws = fakeWs({ reply: { ok: false, error: "配对码无效或已使用" } });
  const res = await client.pair(ws, "00000000");
  assert.equal(res.ok, false);
  assert.equal(res.error, "配对码无效或已使用");
  assert.deepEqual(await storage.get("mx_device_key"), {});
  assert.equal(await client.state(), "needs_pair");
});

test("auth 成功：首帧 {op:auth,key}，收到 {ok:true}", async () => {
  const storage = memoryKV();
  await storage.set({ mx_device_key: "k".repeat(64) });
  const client = createAuthClient({ storage });
  const ws = fakeWs({});
  const res = await client.auth(ws);
  assert.deepEqual(res, { ok: true });
  assert.deepEqual(ws.sent, [{ op: "auth", key: "k".repeat(64) }]);
});

test("auth 被拒 + close 4003（吊销/未知密钥）：清本地密钥，状态回 needs_pair", async () => {
  const storage = memoryKV();
  await storage.set({ mx_device_key: "dead".repeat(16) });
  const client = createAuthClient({ storage });
  const ws = fakeWs({
    reply: { ok: false, error: "设备密钥无效或已吊销" },
    closeCode: 4003,
  });
  const res = await client.auth(ws);
  assert.equal(res.ok, false);
  assert.deepEqual(await storage.get("mx_device_key"), {}, "被吊销的密钥必须清掉");
  assert.equal(await client.state(), "needs_pair");
});

test("serverClose 4003（存量连接被吊销，无前置 ok 帧）：同样清密钥回 needs_pair", async () => {
  const storage = memoryKV();
  await storage.set({ mx_device_key: "k".repeat(64) });
  const client = createAuthClient({ storage });
  assert.equal(await client.state(), "has_key");
  // 吊销时网关 fire-and-forget close(4003)，扩展只看到 close 事件
  await client.onServerClose(4003);
  assert.deepEqual(await storage.get("mx_device_key"), {});
  assert.equal(await client.state(), "needs_pair");
});

test("serverClose 非 4003（网络断开等）：密钥保留，状态仍 has_key（自动重连口径）", async () => {
  const storage = memoryKV();
  await storage.set({ mx_device_key: "k".repeat(64) });
  const client = createAuthClient({ storage });
  await client.onServerClose(1006);
  assert.equal((await storage.get("mx_device_key")).mx_device_key, "k".repeat(64));
  assert.equal(await client.state(), "has_key");
});

test("撤销本地密钥（用户主动重配对入口）", async () => {
  const storage = memoryKV();
  await storage.set({ mx_device_key: "k".repeat(64) });
  const client = createAuthClient({ storage });
  await client.forget();
  assert.equal(await client.state(), "needs_pair");
});
