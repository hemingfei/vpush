// 响应体采集纯逻辑测试（票 #16 交付物 2：requestWillBeSent + getResponseBody）。
// 协议契约：http 帧 payload 是 {url, method, body, responseBody,
// responseBodyTruncated} 的 JSON 字符串（网关 http 分支记事件按 len 记账）。
// MV3 审计修复1（2026-11-14）：登记写穿 storage.session——SW 死于两事件之间
// 经 restore() 装回，响应体帧不再静默丢失；重 attach clear 清陈旧登记。
import { test } from "node:test";
import assert from "node:assert/strict";

import { createResponseTracker, capBody, RESPONSE_BODY_MAX_BYTES } from "../src/response_body.js";

// chrome.storage.session 形态的内存替身
function fakeSession() {
  const mem = new Map();
  return {
    async get(keys) {
      const out = {};
      for (const k of keys) if (mem.has(k)) out[k] = mem.get(k);
      return out;
    },
    async set(obj) {
      for (const [k, v] of Object.entries(obj)) mem.set(k, v);
    },
    dump() {
      return mem.get("mx_resp_pending");
    },
  };
}

test("requestWillBeSent 登记 → loadingFinished 取回 → 组装带响应体的 payload", async () => {
  const tracker = createResponseTracker();
  assert.equal(await tracker.track("req-1", { url: "https://x/api/4/room/view", method: "POST", postData: "rid=801" }), true);
  assert.equal(tracker.size(), 1);
  const entry = await tracker.take("req-1");
  assert.deepEqual(entry, { url: "https://x/api/4/room/view", method: "POST", body: "rid=801" });
  assert.equal(tracker.size(), 0, "消费后登记清空");
  // 未登记的 requestId（扩展重启丢在途请求）：take 返回 null
  assert.equal(await tracker.take("req-1"), null);
  const payload = tracker.buildPayload(entry, '{"ok":1}');
  assert.deepEqual(payload, {
    url: "https://x/api/4/room/view",
    method: "POST",
    body: "rid=801",
    responseBody: '{"ok":1}',
    responseBodyTruncated: false,
  });
});

test("非法登记（缺 requestId/缺 request）不进表", async () => {
  const tracker = createResponseTracker();
  assert.equal(await tracker.track(null, { url: "https://x" }), false);
  assert.equal(await tracker.track("req-2", null), false);
  assert.equal(await tracker.track("req-2", {}), false);
  assert.equal(tracker.size(), 0);
});

test("响应体超限截断：64KB 上限 + truncated 标记", async () => {
  const tracker = createResponseTracker();
  const big = "x".repeat(RESPONSE_BODY_MAX_BYTES + 100);
  await tracker.track("req-3", { url: "https://x/api", method: "GET" });
  const entry = await tracker.take("req-3");
  const payload = tracker.buildPayload(entry, big);
  assert.equal(payload.responseBody.length, RESPONSE_BODY_MAX_BYTES);
  assert.equal(payload.responseBodyTruncated, true);
});

test("响应体在限内不截断", () => {
  const capped = capBody("x".repeat(RESPONSE_BODY_MAX_BYTES));
  assert.equal(capped.truncated, false);
  assert.equal(capped.text.length, RESPONSE_BODY_MAX_BYTES);
});

test("空响应体 / base64 体：null 体记空串、base64 原样传递", async () => {
  const tracker = createResponseTracker();
  await tracker.track("a", { url: "https://x", method: "GET" });
  const e1 = await tracker.take("a");
  const p1 = tracker.buildPayload(e1, null);
  assert.equal(p1.responseBody, "");
  assert.equal(p1.responseBodyTruncated, false);
  await tracker.track("b", { url: "https://y", method: "GET" });
  const e2 = await tracker.take("b");
  const p2 = tracker.buildPayload(e2, { base64Encoded: true, body: "aGVsbG8=" });
  // base64 体按对象 toString 会失真——取 body 字段是调用方（sw.js）职责；
  // 本模块只认字符串入参，sw.js 在调用前解包
  assert.equal(tracker.buildPayload(e2, "aGVsbG8=").responseBody, "aGVsbG8=");
});

test("修复1：登记写穿 sessionStore（take 后账目同步清）", async () => {
  const session = fakeSession();
  const tracker = createResponseTracker({ sessionStore: session });
  await tracker.track("w-1", { url: "https://x/api", method: "GET", postData: "a=1" });
  assert.deepEqual(session.dump(), [["w-1", { url: "https://x/api", method: "GET", body: "a=1" }]]);
  await tracker.take("w-1");
  assert.deepEqual(session.dump(), [], "消费后 session 账目同步清空");
});

test("修复1：新实例 restore 装回 session 存活的登记（SW 死亡重启场景）", async () => {
  const session = fakeSession();
  const first = createResponseTracker({ sessionStore: session });
  await first.track("s-1", { url: "https://x/api/1", method: "POST", postData: "x" });
  await first.track("s-2", { url: "https://x/api/2", method: "GET" });
  // —— SW 被 30s 回收，新 SW 实例从 session 恢复 ——
  const second = createResponseTracker({ sessionStore: session });
  assert.equal(await second.restore(), 2, "两条在途登记全部装回");
  const e = await second.take("s-1");
  assert.deepEqual(e, { url: "https://x/api/1", method: "POST", body: "x" });
  // restore 幂等：不覆盖内存已有同 id 登记
  assert.equal(await second.restore(), 1);
});

test("修复1：clear 清内存与 session（重 attach 新 Network 会话清陈旧登记）", async () => {
  const session = fakeSession();
  const tracker = createResponseTracker({ sessionStore: session });
  await tracker.track("c-1", { url: "https://x/api", method: "GET" });
  await tracker.clear();
  assert.equal(tracker.size(), 0);
  assert.deepEqual(session.dump(), []);
  const fresh = createResponseTracker({ sessionStore: session });
  assert.equal(await fresh.restore(), 0, "clear 后 restore 无账可装");
});

test("写穿失败不阻塞登记（sessionStore.set 抛错吞掉）", async () => {
  const boom = {
    async get() { return {}; },
    async set() { throw new Error("quota"); },
  };
  const tracker = createResponseTracker({ sessionStore: boom });
  assert.equal(await tracker.track("q-1", { url: "https://x/api", method: "GET" }), true, "主链路不丢");
  const taken = await tracker.take("q-1");
  assert.equal(taken?.url, "https://x/api");
});
