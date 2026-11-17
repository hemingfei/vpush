// WS 静默看门狗测试（票 #23 防线二）。
// 语义契约：静默超随机阈值（3-10min）触发一次 reload；帧到达（含引擎帧）
// 刷新时间戳并解除防重入；阈值每次触发后重采样；attach 基线防秒触发。
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  createWsWatchdog,
  SILENCE_THRESHOLD_RANGE_MS,
} from "../src/ws_watchdog.js";

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

const [LO, HI] = SILENCE_THRESHOLD_RANGE_MS;

test("阈值区间常量 = 3-10 分钟（用户口径锁定）", () => {
  assert.equal(LO, 3 * 60 * 1000);
  assert.equal(HI, 10 * 60 * 1000);
});

test("有帧到达时静默不触发（含引擎帧——onEvent 统一刷）", async () => {
  let t = 1000000;
  const store = fakeStore();
  const wd = createWsWatchdog({ store, now: () => t, random: () => 0.5 });
  await wd.noteFrame();
  t += 1000; // 帧后 1s：远未到任何阈值
  assert.equal(await wd.shouldReload(), false, "帧后短静默不该触发");
  t += LO - 2000; // 总静默仍在阈值下界内
  assert.equal(await wd.shouldReload(), false, "静默未超阈值下界不触发");
});

test("静默超阈值触发一次；markReloaded 后同静默期不再触发", async () => {
  let t = 1000000;
  const store = fakeStore();
  const wd = createWsWatchdog({ store, now: () => t, random: () => 0.5 });
  await wd.noteFrame();
  t += HI + 1; // 静默超任何采样阈值
  assert.equal(await wd.shouldReload(), true, "静默超阈值应触发");
  await wd.markReloaded();
  assert.equal(await wd.shouldReload(), false, "防重入：本静默期已 reload");
});

test("新帧到达解除防重入：恢复后的新静默期可再次触发", async () => {
  let t = 1000000;
  const store = fakeStore();
  const wd = createWsWatchdog({ store, now: () => t, random: () => 0.5 });
  await wd.noteFrame();
  t += HI + 1;
  assert.equal(await wd.shouldReload(), true);
  await wd.markReloaded();
  // reload 生效：页面重建 WS 开始来帧
  t += 1000;
  await wd.noteFrame();
  t += HI + 1; // 又一段静默
  assert.equal(await wd.shouldReload(), true, "新静默期允许再次触发");
});

test("阈值每次 markReloaded 后重采样（自愈节奏不可预测）", async () => {
  let t = 1000000;
  const store = fakeStore();
  const rands = [];
  const wd = createWsWatchdog({
    store,
    now: () => t,
    random: () => {
      const r = [0.1, 0.9, 0.5][rands.length] ?? 0.5;
      rands.push(r);
      return r;
    },
  });
  await wd.noteFrame();
  t += HI + 1;
  await wd.shouldReload(); // 惰性落账第一个阈值（0.1 采样）
  await wd.markReloaded(); // 重采样（0.9）
  const snap = await wd.snapshot();
  const first = LO + 0.1 * (HI - LO);
  const second = LO + 0.9 * (HI - LO);
  assert.equal(snap.thresholdMs, second, "markReloaded 后阈值已重采样");
  assert.notEqual(snap.thresholdMs, first);
});

test("noteAttached 基线：无帧史时从 attach 时刻起算（不秒触发）", async () => {
  let t = 1000000;
  const store = fakeStore();
  const wd = createWsWatchdog({ store, now: () => t, random: () => 0.5 });
  await wd.noteAttached(); // SW 重启后无帧史：基线 = 现在
  t += 1000; // 1 秒后
  assert.equal(await wd.shouldReload(), false, "attach 后 1s 不触发");
  t += HI + 1;
  assert.equal(await wd.shouldReload(), true, "attach 后静默超阈值触发");
});

test("noteAttached 不覆盖已有帧时间戳（避免把活跃连接误判为静默）", async () => {
  let t = 1000000;
  const store = fakeStore();
  const wd = createWsWatchdog({ store, now: () => t, random: () => 0.5 });
  await wd.noteFrame(); // t=1000000 有帧
  t += 10000;
  await wd.noteAttached(); // 不该覆盖 t=1000000 的帧时间戳
  t += HI; // 从帧时刻算静默超阈值（从 attach 算只有 HI-10000 未到）
  assert.equal(await wd.shouldReload(), true, "帧时间戳未被 attach 覆盖");
});
