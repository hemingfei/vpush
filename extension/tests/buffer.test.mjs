// 断线缓冲账目的本地单测（票 #16 交付物 5：上限 5000 丢最旧 + 丢帧计数上报）。
// user story 8：断线缓冲帧、重连按序补传、网络抖动不丢消息。
import { test } from "node:test";
import assert from "node:assert/strict";

import { createBuffer } from "../src/buffer.js";

test("缓冲按入队顺序保留（重连补传按序的账目前提）", () => {
  const buf = createBuffer({ cap: 5 });
  for (const x of ["a", "b", "c"]) buf.push(x);
  assert.deepEqual(buf.items(), ["a", "b", "c"]);
});

test("超上限丢最旧（FIFO shift），丢帧计数累加", () => {
  const buf = createBuffer({ cap: 3 });
  for (const x of ["a", "b", "c", "d", "e"]) buf.push(x);
  assert.deepEqual(buf.items(), ["c", "d", "e"], "最旧的 a/b 被丢");
  assert.equal(buf.droppedTotal(), 2, "丢帧计数=2");
});

test("drain 取空缓冲（重连 flush 语义），取出后缓冲清空", () => {
  const buf = createBuffer({ cap: 5 });
  buf.push("a");
  buf.push("b");
  assert.deepEqual(buf.drain(), ["a", "b"]);
  assert.deepEqual(buf.items(), []);
  // drain 后丢帧计数不清零——buffer_overflow 生命周期上报要用累计值
  assert.equal(buf.droppedTotal(), 0);
});

test("丢帧计数跨 drain 持续累计（上报 buffer_overflow 后仍可见）", () => {
  const buf = createBuffer({ cap: 2 });
  buf.push("a");
  buf.push("b");
  buf.push("c"); // 丢 a
  assert.equal(buf.droppedTotal(), 1);
  buf.drain(); // 补传走 [b, c]
  buf.push("x");
  buf.push("y");
  buf.push("z"); // 丢 x
  assert.equal(buf.droppedTotal(), 2, "计数跨 drain 累计");
});

test("生产上限 5000（spec 决策值）：恰好装满不丢，第 5001 条起丢最旧", () => {
  const buf = createBuffer({ cap: 5000 });
  for (let i = 1; i <= 5001; i++) buf.push(i);
  assert.equal(buf.items().length, 5000);
  assert.equal(buf.items()[0], 2, "第 1 条被丢");
  assert.equal(buf.items()[4999], 5001);
  assert.equal(buf.droppedTotal(), 1);
});
