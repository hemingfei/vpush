// 重连退避账目测试（MV3 审计修复2/3：连接互斥门 + 退避跨 SW 死亡持久化）。
// 语义契约：门内 acquire 返回 null；放行即布下刻门；失败 bump 档位、成功
// reset 清账；阶梯 base*2^n 封顶 MAX，与 sw.js 旧 setTimeout 常量逐值对齐。
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  createConnState,
  RECONNECT_BASE_MS,
  RECONNECT_MAX_MS,
  MAX_ATTEMPTS,
} from "../src/conn_state.js";

function fakeStore() {
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
      return Object.fromEntries(mem.entries());
    },
  };
}

test("acquire 首次放行并按当前档位布下刻门", async () => {
  let t = 1000;
  const store = fakeStore();
  const cs = createConnState({ store, now: () => t });
  const slot = await cs.acquire();
  assert.equal(slot.attempts, 0);
  const got = await store.get(["mx_reconnect_next_at"]);
  assert.equal(got.mx_reconnect_next_at, 1000 + RECONNECT_BASE_MS, "0 档门 = base 2s");
});

test("门内 acquire 返回 null（真退避，不是快连）", async () => {
  let t = 1000;
  const store = fakeStore();
  const cs = createConnState({ store, now: () => t });
  await cs.acquire();
  t += RECONNECT_BASE_MS - 1; // 门开前 1ms
  assert.equal(await cs.acquire(), null);
  t += 1; // 门开
  const slot = await cs.acquire();
  assert.equal(slot.attempts, 0, "失败前档位不涨");
});

test("失败 bump 抬门：阶梯 2s→4s→8s，封顶 120s", async () => {
  let t = 1000;
  const store = fakeStore();
  const cs = createConnState({ store, now: () => t });
  assert.equal(await cs.penaltyMs(), RECONNECT_BASE_MS);
  await cs.acquire();
  await cs.bump(); // 第 1 次失败
  assert.equal(await cs.penaltyMs(), RECONNECT_BASE_MS * 2);
  t += RECONNECT_BASE_MS;
  await cs.acquire();
  await cs.bump(); // 第 2 次
  assert.equal(await cs.penaltyMs(), RECONNECT_BASE_MS * 4);
  // 连败到顶：档位封 MAX_ATTEMPTS，门时长封顶 120s
  for (let i = 0; i < MAX_ATTEMPTS + 3; i++) {
    t += RECONNECT_MAX_MS;
    const s = await cs.acquire();
    assert.ok(s, "门开必放行");
    await cs.bump();
  }
  const snap = await cs.snapshot();
  assert.equal(snap.attempts, MAX_ATTEMPTS, "档位封顶不越界");
  assert.equal(await cs.penaltyMs(), RECONNECT_MAX_MS);
});

test("成功 reset 清账：档位与下刻门归零，立即再放行", async () => {
  let t = 1000;
  const store = fakeStore();
  const cs = createConnState({ store, now: () => t });
  await cs.acquire();
  await cs.bump();
  await cs.bump();
  await cs.reset();
  const snap = await cs.snapshot();
  assert.equal(snap.attempts, 0);
  assert.equal(snap.nextAt, 0);
  assert.equal(snap.nextInMs, 0);
  t += 1;
  assert.ok(await cs.acquire(), "reset 后无门");
});

test("同刻并发 acquire 只有先到者拿到（互斥门）", async () => {
  const t = 1000;
  const store = fakeStore();
  const cs = createConnState({ store, now: () => t });
  const results = await Promise.all([cs.acquire(), cs.acquire(), cs.acquire()]);
  // 三发同刻：第一发布门，其余在门内 → 至多一个非 null
  assert.equal(results.filter(Boolean).length, 1);
});

test("快照 nextInMs 观测面随时间衰减", async () => {
  let t = 1000;
  const store = fakeStore();
  const cs = createConnState({ store, now: () => t });
  await cs.acquire();
  const s1 = await cs.snapshot();
  assert.equal(s1.nextInMs, RECONNECT_BASE_MS);
  t += RECONNECT_BASE_MS;
  const s2 = await cs.snapshot();
  assert.equal(s2.nextInMs, 0);
});
