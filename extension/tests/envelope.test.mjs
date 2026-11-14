// 信封构造与持久化单调 seq 的本地单测（票 #16 交付物 3/5；幂等契约真相源 =
// tests/test_mx_gateway.py test_duplicate_account_seq_is_idempotent——同
// (account, seq) 只入库一次，故 seq 跨 SW 重启必须单调，重发才安全）。
import { test } from "node:test";
import assert from "node:assert/strict";

import { createEnvelopeFactory } from "../src/envelope.js";

function memorySeqStore() {
  let n = 0;
  return {
    async load() {
      return n;
    },
    async save(v) {
      n = v;
    },
  };
}

// account 标签取值器替身：接力换账号时 getAccount 返回新值
function accountGetter(initial) {
  let current = initial;
  return {
    getAccount: async () => current,
    set(v) {
      current = v;
    },
  };
}

test("信封形态与网关契约逐字段对齐：seq/ts/account/type/payload", async () => {
  const acct = accountGetter("main");
  const factory = createEnvelopeFactory({ getAccount: acct.getAccount, seqStore: memorySeqStore() });
  const env = await factory.build("ws_in", '42/msg,["room_msg",{}]');
  assert.deepEqual(Object.keys(env).sort(), ["account", "payload", "seq", "ts", "type"]);
  assert.equal(env.account, "main");
  assert.equal(env.type, "ws_in");
  assert.equal(env.payload, '42/msg,["room_msg",{}]');
  assert.equal(typeof env.ts, "number");
  assert.equal(env.seq, 1);
});

test("seq 单调递增，跨「SW 重启」（重建 factory 同一 store）不回退", async () => {
  const store = memorySeqStore();
  const acct = accountGetter("main");
  const f1 = createEnvelopeFactory({ getAccount: acct.getAccount, seqStore: store });
  const s1 = (await f1.build("ws_in", "a")).seq;
  const s2 = (await f1.build("ws_out", "b")).seq;
  assert.equal(s2, s1 + 1);
  // 模拟 SW 重启：factory 重建，store 持久层不变
  const f2 = createEnvelopeFactory({ getAccount: acct.getAccount, seqStore: store });
  const s3 = (await f2.build("ws_in", "c")).seq;
  assert.equal(s3, s2 + 1, "重启后 seq 必须从持久值继续，不能归零重发");
});

test("type 合法集 = ws_in|ws_out|http|lifecycle（网关 FRAME_TYPES 同集）", async () => {
  const factory = createEnvelopeFactory({ getAccount: accountGetter("main").getAccount, seqStore: memorySeqStore() });
  await assert.rejects(() => factory.build("ws_in2", "x"));
  await assert.rejects(() => factory.build("", "x"));
  for (const t of ["ws_in", "ws_out", "http", "lifecycle"]) {
    assert.equal((await factory.build(t, "p")).type, t);
  }
});

test("lifecycle 事件带 event/detail 字段（网关 handle_envelope lifecycle 分支读取）", async () => {
  const factory = createEnvelopeFactory({ getAccount: accountGetter("main").getAccount, seqStore: memorySeqStore() });
  const env = await factory.buildLifecycle("attached", "tab 801 已挂");
  assert.equal(env.type, "lifecycle");
  assert.equal(env.event, "attached");
  assert.equal(env.detail, "tab 801 已挂");
  assert.equal(env.payload, undefined, "lifecycle 走 event/detail 通道，不占 payload");
});

test("接力换账号后信封 account 标签跟随切换（跨账号去重按标签判定）", async () => {
  const acct = accountGetter("main");
  const factory = createEnvelopeFactory({ getAccount: acct.getAccount, seqStore: memorySeqStore() });
  const e1 = await factory.build("ws_in", "a");
  assert.equal(e1.account, "main");
  acct.set("backup"); // 接力切换：备用账号补位
  const e2 = await factory.build("ws_in", "b");
  assert.equal(e2.account, "backup");
  assert.equal(e2.seq, e1.seq + 1, "换账号不重置 seq（幂等键是 (account, seq)）");
});

test("http 帧 payload 序列化为 JSON 字符串（网关 http 分支只收字符串 payload）", async () => {
  const factory = createEnvelopeFactory({ getAccount: accountGetter("main").getAccount, seqStore: memorySeqStore() });
  const env = await factory.build("http", { url: "https://x/api/1", method: "GET", body: null });
  // 网关契约：http 帧 payload 非 str 直接丢（handle_envelope isinstance 判定），
  // http_frame 事件记 len(payload)——payload 必须是 JSON 字符串
  assert.equal(typeof env.payload, "string");
  assert.deepEqual(JSON.parse(env.payload), { url: "https://x/api/1", method: "GET", body: null });
});
