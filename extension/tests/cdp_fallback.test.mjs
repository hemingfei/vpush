// CDP 直连 fallback 测试（票 #23 追加通道）。
// 契约：目标页挑选按 sitePrefix 过滤 page 类型；CDP 报文与 chrome.debugger
// onEvent 同构转换（仅 webSocketFrame* 两事件）；坏报文/无关事件返回 null。
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  RELAY_WS_URL,
  cdpMessageToEvent,
} from "../src/cdp_fallback.js";

test("RELAY_WS_URL 固定环回 9333（relay 桥接端点）", () => {
  assert.equal(RELAY_WS_URL, "ws://127.0.0.1:9333");
});

test("cdpMessageToEvent 转换 Received/Sent 为同构事件", () => {
  const params = { response: { payloadData: "42/msg,[...]" } };
  const got = cdpMessageToEvent(JSON.stringify({ method: "Network.webSocketFrameReceived", params }));
  assert.equal(got.method, "Network.webSocketFrameReceived");
  assert.equal(got.source.tabId, -1);
  assert.deepEqual(got.params, params);
  const sent = cdpMessageToEvent(JSON.stringify({ method: "Network.webSocketFrameSent", params }));
  assert.equal(sent.method, "Network.webSocketFrameSent");
});

test("cdpMessageToEvent 过滤无关方法/坏报文", () => {
  assert.equal(cdpMessageToEvent(JSON.stringify({ method: "Network.requestWillBeSent", params: {} })), null);
  assert.equal(cdpMessageToEvent("not json"), null);
  assert.equal(cdpMessageToEvent("{}"), null);
  assert.equal(cdpMessageToEvent(JSON.stringify({ method: "hello", params: {} })), null);
});
