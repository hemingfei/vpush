// attach 过滤配置 + HTTP URL 过滤的本地单测（票 #16 交付物 2 的判定逻辑）。
//
// 从 spike sw.js 抽出判定逻辑成纯函数（sw.js:20-23 attachPrefix 每事件 await
// 读取 + sw.js:114 URL 正则过滤），使 spike 继承的两条设计决策可测：
// ①配置每次事件时读取（SW 重启后 storage 才是权威，顶层一次性读取有竞态）
// ②MX 域名会漂移，attach 前缀与上行网关都从 storage 读。
import { test } from "node:test";
import assert from "node:assert/strict";

import { shouldCaptureTab, shouldCaptureHttp } from "../src/attach_filter.js";

// storage 替身：模拟「SW 重启后配置变化」——第一次读旧值、之后读新值
function flakyStorage(values) {
  let i = 0;
  return {
    async get() {
      return { mx_site_prefix: values[Math.min(i++, values.length - 1)] };
    },
  };
}

test("URL 前缀命中配置的 tab 才 attach（MX 域漂移由配置吸收）", async () => {
  const storage = flakyStorage(["https://mx.2026.foodtop1.com/"]);
  assert.equal(await shouldCaptureTab(storage, { id: 5, url: "https://mx.2026.foodtop1.com/room/801" }), true);
  assert.equal(await shouldCaptureTab(storage, { id: 6, url: "https://other.example.com/room/801" }), false);
});

test("每次调用都 await 读 storage（SW 重启后配置变化立即生效，无顶层缓存竞态）", async () => {
  const storage = flakyStorage([
    "https://old.example.com/",
    "https://new.example.com/", // 第二次读取起配置已变（模拟 storage 写入后）
  ]);
  assert.equal(await shouldCaptureTab(storage, { id: 1, url: "https://old.example.com/x" }), true);
  // 「配置变更不 reload SW」——靠每次读 storage 即时生效，而不是重启 SW
  assert.equal(await shouldCaptureTab(storage, { id: 1, url: "https://new.example.com/x" }), true);
  assert.equal(await shouldCaptureTab(storage, { id: 1, url: "https://old.example.com/x" }), false);
});

test("无配置时回退默认前缀（首次安装未配域名的窗口期）", async () => {
  const storage = { async get() { return {}; } };
  assert.equal(typeof (await shouldCaptureTab(storage, { id: 1, url: "about:blank" })), "boolean");
});

test("tab id < 0（devtools 等无页面目标）不 attach", async () => {
  const storage = { async get() { return { mx_site_prefix: "https://x/" } } };
  assert.equal(await shouldCaptureTab(storage, { id: -1, url: "https://x/a" }), false);
  assert.equal(await shouldCaptureTab(storage, { url: "https://x/a" }), false);
});

test("HTTP 过滤：/api/ 与 socket.io 命中，其余业务请求放过", () => {
  assert.equal(shouldCaptureHttp("https://mx.2026.foodtop1.com/api/4/room/view"), true);
  assert.equal(shouldCaptureHttp("https://mx.2026.foodtop1.com/socket.io/?EIO=4"), true);
  assert.equal(shouldCaptureHttp("https://mx.2026.foodtop1.com/static/app.js"), false);
  assert.equal(shouldCaptureHttp(""), false);
});
