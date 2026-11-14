// 引擎帧过滤的本地单测（node --test，零依赖；spec #14 裁定本地组件不进 CI）。
//
// 契约真相源：app/services/mx_gateway.py 的 ENGINE_FRAME_RE = ^(?:[023]|4[01])——
// 网关对引擎帧做防御性丢弃；扩展侧过滤必须与网关同一判定（测试=契约，票 #16
// 交付物 4）：凡是网关会丢的帧扩展就不该发，网关会收的帧扩展绝不能误杀。
import { test } from "node:test";
import assert from "node:assert/strict";

import { isEngineFrame } from "../src/engine_frame.js";

test("引擎帧（2/3/0/40/41 全变体）判定为不上行", () => {
  // 网关测试 test_engine_frames_dropped_never_ingested 用到的全部形态 +
  // 带命名空间前缀的变体（41/msg 与 40/msg 同理，正则前缀匹配兜住）
  const engineFrames = [
    "2",
    "3",
    "0",
    "40",
    "41",
    "40/msg",
    "41/msg",
    '40/msg,{"sid":"x"}',
    '0{"sid":"s","pingInterval":25000}',
  ];
  for (const f of engineFrames) {
    assert.equal(isEngineFrame(f), true, `应判定为引擎帧: ${JSON.stringify(f)}`);
  }
});

test("业务帧不误杀（42 事件帧等网关会收的形态）", () => {
  const legitFrames = [
    '42/msg,["room_msg",{"rid":801,"id":1,"msg":"早"}]',
    "42",
    "42/msg",
    "1",
    "4",
    "44/x",
    "40x", // "40" 前缀但第三字符非命名空间分隔——正则 ^(?:[023]|4[01]) 仍命中 "40"，见下
  ];
  // 注意 "40x"：网关正则按前缀命中会丢弃（防御性），扩展同判定——不算误杀，
  // 因为它不是合法业务帧。真正要保住的是 42* 帧与普通字符串。
  assert.equal(isEngineFrame("40x"), true, "40 前缀与网关同判（防御性丢弃）");
  for (const f of legitFrames.filter((x) => x !== "40x")) {
    assert.equal(isEngineFrame(f), false, `不应判定为引擎帧: ${JSON.stringify(f)}`);
  }
});

test("空帧判定为引擎帧（网关不收空 payload，扩展侧同口径不发）", () => {
  assert.equal(isEngineFrame(""), true);
  assert.equal(isEngineFrame(null), true);
  assert.equal(isEngineFrame(undefined), true);
});
