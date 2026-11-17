// CDP 直连 fallback 测试（票 #23 追加通道）。
// 契约：目标页挑选按 sitePrefix 过滤 page 类型；CDP 报文与 chrome.debugger
// onEvent 同构转换（仅 webSocketFrame* 两事件）；坏报文/无关事件返回 null。
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  pickPageTarget,
  cdpMessageToEvent,
  LOCAL_CDP_LIST_URL,
} from "../src/cdp_fallback.js";

const PREFIX = "https://mx.2026.foodtop1.com/";

const PAGE_TARGET = {
  type: "page",
  url: "https://mx.2026.foodtop1.com/",
  webSocketDebuggerUrl: "ws://127.0.0.1:9223/devtools/page/ABC",
};

test("pickPageTarget 选 sitePrefix 前缀的 page 目标", () => {
  const t = pickPageTarget(
    [
      { type: "service_worker", url: "chrome-extension://x/sw.js", webSocketDebuggerUrl: "ws://x" },
      PAGE_TARGET,
    ],
    PREFIX
  );
  assert.equal(t, PAGE_TARGET);
});

test("pickPageTarget 忽略无 webSocketDebuggerUrl / 前缀不符 / 非 page", () => {
  assert.equal(pickPageTarget([{ type: "page", url: PREFIX }], PREFIX), null);
  assert.equal(pickPageTarget([{ type: "page", url: "https://other.com/", webSocketDebuggerUrl: "ws://x" }], PREFIX), null);
  assert.equal(pickPageTarget([{ type: "iframe", url: PREFIX, webSocketDebuggerUrl: "ws://x" }], PREFIX), null);
  assert.equal(pickPageTarget([], PREFIX), null);
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
});

test("LOCAL_CDP_LIST_URL 固定环回 9223", () => {
  assert.equal(LOCAL_CDP_LIST_URL, "http://127.0.0.1:9223/json/list");
});
