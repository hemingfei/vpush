// host 校验的本地单测（票 #16 交付物 8：仅允许 wss 到自有域名；拒绝内网/环回）。
//
// 判定语义对齐云端 app/url_safety.py 的 is_safe_http_url（私有网段/环回/
// 链路本地/元数据地址全拒），差别仅在协议层：采集器上行只认 wss（生产），
// 本地冒烟脚本经显式 allowInsecureDev 开关放行 ws://127.0.0.1（开关不进扩展
// 默认路径，见 README「本地冒烟」节）。
import { test } from "node:test";
import assert from "node:assert/strict";

import { validateIngestHost } from "../src/host_guard.js";

test("自有域名的 wss 地址通过校验", () => {
  assert.doesNotThrow(() => validateIngestHost("wss://ingest.example.com/api/mx-ingest"));
  assert.doesNotThrow(() => validateIngestHost("wss://mx-gw.foo2026.cn/api/mx-ingest"));
});

test("非 wss 协议拒绝（ws/http/wss 大小写不敏感口径仍须 wss）", () => {
  for (const url of [
    "ws://ingest.example.com/api/mx-ingest",
    "http://ingest.example.com/api/mx-ingest",
    "https://ingest.example.com/api/mx-ingest",
    "ftp://ingest.example.com/x",
  ]) {
    assert.throws(() => validateIngestHost(url), `应拒绝: ${url}`);
  }
});

test("环回地址拒绝（wss 也不行——环回不是自有域名）", () => {
  for (const url of [
    "wss://127.0.0.1/api/mx-ingest",
    "wss://localhost/api/mx-ingest",
    "wss://[::1]/api/mx-ingest",
    "wss://0.0.0.0/api/mx-ingest",
  ]) {
    assert.throws(() => validateIngestHost(url), `应拒绝环回: ${url}`);
  }
});

test("内网私网地址拒绝（RFC1918/链路本地/内网主机名形态）", () => {
  for (const url of [
    "wss://10.1.2.3/api/mx-ingest",
    "wss://172.16.0.9/api/mx-ingest",
    "wss://192.168.1.20/api/mx-ingest",
    "wss://169.254.1.2/api/mx-ingest",
    "wss://192.168.1.20.nip.io/api/mx-ingest",
  ]) {
    assert.throws(() => validateIngestHost(url), `应拒绝内网: ${url}`);
  }
});

test("云元数据地址段拒绝（169.254.169.254 等）", () => {
  assert.throws(() => validateIngestHost("wss://169.254.169.254/latest/meta-data"));
});

test("缺 host / 非法 URL 拒绝", () => {
  for (const url of ["", "wss://", "not a url"]) {
    assert.throws(() => validateIngestHost(url), `应拒绝: ${url}`);
  }
});

test("本地开发开关 allowInsecureDev 放行 ws://127.0.0.1（仅冒烟脚本用）", () => {
  assert.doesNotThrow(() =>
    validateIngestHost("ws://127.0.0.1:8000/api/mx-ingest", { allowInsecureDev: true })
  );
  // 开关只放行环回，不放行其它 ws 目标
  assert.throws(() =>
    validateIngestHost("ws://ingest.example.com/api/mx-ingest", { allowInsecureDev: true })
  );
});
