#!/usr/bin/env node
// 本地测试入口（零依赖）：node extension/tests/run_tests.mjs
// 等价直跑：node --test extension/tests/*.test.mjs
//
// spec #14 Testing Decisions 裁定：本地组件不进 CI。本脚本只在本地跑
// （开发/验收用），仓库 CI 无任何扩展相关接线。
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const files = readdirSync(here)
  .filter((f) => f.endsWith(".test.mjs"))
  .sort()
  .map((f) => path.join(here, f));

// 直接转发 node --test（默认 reporter 带统计尾行，退出码即结果）
const res = spawnSync(
  process.execPath,
  ["--test", ...files],
  { stdio: "inherit" }
);
process.exit(res.status ?? 1);
