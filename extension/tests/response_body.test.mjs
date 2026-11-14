// 响应体采集纯逻辑测试（票 #16 交付物 2：requestWillBeSent + getResponseBody）。
// 协议契约：http 帧 payload 是 {url, method, body, responseBody,
// responseBodyTruncated} 的 JSON 字符串（网关 http 分支记事件按 len 记账）。
import { test } from "node:test";
import assert from "node:assert/strict";

import { createResponseTracker, capBody, RESPONSE_BODY_MAX_BYTES } from "../src/response_body.js";

test("requestWillBeSent 登记 → loadingFinished 取回 → 组装带响应体的 payload", () => {
  const tracker = createResponseTracker();
  assert.equal(tracker.track("req-1", { url: "https://x/api/4/room/view", method: "POST", postData: "rid=801" }), true);
  assert.equal(tracker.size(), 1);
  const entry = tracker.take("req-1");
  assert.deepEqual(entry, { url: "https://x/api/4/room/view", method: "POST", body: "rid=801" });
  assert.equal(tracker.size(), 0, "消费后登记清空");
  // 未登记的 requestId（扩展重启丢在途请求）：take 返回 null
  assert.equal(tracker.take("req-1"), null);
  const payload = tracker.buildPayload(entry, '{"ok":1}');
  assert.deepEqual(payload, {
    url: "https://x/api/4/room/view",
    method: "POST",
    body: "rid=801",
    responseBody: '{"ok":1}',
    responseBodyTruncated: false,
  });
});

test("非法登记（缺 requestId/缺 request）不进表", () => {
  const tracker = createResponseTracker();
  assert.equal(tracker.track(null, { url: "https://x" }), false);
  assert.equal(tracker.track("req-2", null), false);
  assert.equal(tracker.track("req-2", {}), false);
  assert.equal(tracker.size(), 0);
});

test("响应体超限截断：64KB 上限 + truncated 标记", () => {
  const tracker = createResponseTracker();
  const big = "x".repeat(RESPONSE_BODY_MAX_BYTES + 100);
  tracker.track("req-3", { url: "https://x/api", method: "GET" });
  const entry = tracker.take("req-3");
  const payload = tracker.buildPayload(entry, big);
  assert.equal(payload.responseBody.length, RESPONSE_BODY_MAX_BYTES);
  assert.equal(payload.responseBodyTruncated, true);
});

test("响应体在限内不截断", () => {
  const capped = capBody("x".repeat(RESPONSE_BODY_MAX_BYTES));
  assert.equal(capped.truncated, false);
  assert.equal(capped.text.length, RESPONSE_BODY_MAX_BYTES);
});

test("空响应体 / base64 体：null 体记空串、base64 原样传递", () => {
  const tracker = createResponseTracker();
  tracker.track("a", { url: "https://x", method: "GET" });
  const e1 = tracker.take("a");
  const p1 = tracker.buildPayload(e1, null);
  assert.equal(p1.responseBody, "");
  assert.equal(p1.responseBodyTruncated, false);
  tracker.track("b", { url: "https://y", method: "GET" });
  const e2 = tracker.take("b");
  const p2 = tracker.buildPayload(e2, { base64Encoded: true, body: "aGVsbG8=" });
  // base64 体按对象 toString 会失真——取 body 字段是调用方（sw.js）职责；
  // 本模块只认字符串入参，sw.js 在调用前解包
  assert.equal(tracker.buildPayload(e2, "aGVsbG8=").responseBody, "aGVsbG8=");
});
