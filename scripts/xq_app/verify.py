#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""App 身份通道端到端验证 —— 交接验收用

在项目 venv 下运行：
    .venv/bin/python scripts/xq_app/verify.py

预期全部 ✅。任何一项 ❌ 都说明通道失效，见 docs/handoff/2026-09-23-xueqiu-app-identity-channel.md 的排查章节。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from xq_client import XueqiuClient          # noqa: E402
from xq_register import register, device_id_from_android_id  # noqa: E402
from xq_crypto import (decode_public_key, derive_sm4_key,   # noqa: E402
                       ecdh_shared_hex, encode_public_key,
                       generate_keypair, point_mul, G, N)

OK, BAD = "✅", "❌"
results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    t0 = time.time()
    try:
        detail = fn()
        results.append((name, True, f"{detail} ({int((time.time()-t0)*1000)}ms)"))
    except Exception as exc:
        results.append((name, False, f"{type(exc).__name__}: {exc}"))


def main() -> int:
    print("=" * 72)
    print("雪球 App 身份通道验证")
    print("=" * 72)

    # --- 1. 国密原语自检 ---
    check("SM2 曲线阶 n·G == ∞", lambda: "OK" if point_mul(N, G) is None else (_ for _ in ()).throw(AssertionError("曲线参数错误")))
    d1, q1 = generate_keypair()
    d2, q2 = generate_keypair()
    check("ECDH 对称性", lambda: "OK" if ecdh_shared_hex(d1, q2) == ecdh_shared_hex(d2, q1) else (_ for _ in ()).throw(AssertionError("EC DH 不对称")))
    check("公钥编码长度 130", lambda: f"len={len(encode_public_key(q1))}" if len(encode_public_key(q1)) == 130 else (_ for _ in ()).throw(AssertionError("编码异常")))

    # --- 2. 隐式账号注册（关键：必须拿到 uid != -1）---
    dev = device_id_from_android_id("Xiaomi", "verify" + "0" * 10)
    cred: dict = {}

    def do_register() -> str:
        out = register(dev, verbose=False)
        cred.update(out)
        assert out.get("uid") and out["uid"] != -1, f"uid 异常: {out.get('uid')}"
        return f"uid={out['uid']} is_new={out.get('is_new')}"

    check("隐式账号注册", do_register)

    if not cred:
        print("\n注册失败，后续检查跳过")
        dump()
        return 1

    # --- 3. 数据接口 ---
    xq = XueqiuClient(app_token=cred["cookie"], device_id=dev)

    def cubes() -> str:
        lst = xq.discover_cubes(count=3)
        assert lst, "排行榜为空"
        return f"{len(lst)} 个组合，首个 {lst[0].get('symbol')}"

    def rebalancing() -> str:
        lst = xq.discover_cubes(count=1)
        rb = xq.cube_rebalancing(lst[0]["symbol"], count=5)
        assert rb, "调仓为空"
        return f"{lst[0]['symbol']} → {len(rb)} 条调仓"

    def timeline() -> str:
        lst = xq.public_timeline(count=5)
        assert lst, "社区流为空"
        return f"{len(lst)} 条帖子"

    def user_tl() -> str:
        lst = xq.user_timeline(1247347556, count=3)
        assert lst, "用户时间线为空"
        return f"{len(lst)} 条"

    def nav() -> str:
        lst = xq.discover_cubes(count=1)
        d = xq.cube_nav(lst[0]["symbol"])
        pts = d["data"][0]["list"]
        return f"{len(pts)} 个净值点"

    check("组合排行榜", cubes)
    check("组合调仓历史", rebalancing)
    check("组合净值曲线", nav)
    check("社区公开流", timeline)
    check("用户时间线", timeline and user_tl)

    # --- 4. 反例校验：浏览器匿名 token 必须失败 ---
    def browser_must_fail() -> str:
        import httpx
        s = httpx.Client(timeout=20, follow_redirects=True)
        s.get("https://xueqiu.com/hq", headers={"User-Agent": "Mozilla/5.0"})
        r = s.get("https://xueqiu.com/cubes/rebalancing/history.json",
                  params={"cube_symbol": "ZH123456", "page": 1, "count": 1},
                  headers={"User-Agent": "Xueqiu Android 14.96.3"})
        body = r.text
        assert "10022" in body or "400016" in body, f"预期被拒，实际: {body[:80]}"
        return "已按预期拒绝（10022/400016）"

    check("对照组：浏览器匿名 token 应被拒", browser_must_fail)

    dump()
    failed = [n for n, ok, _ in results if not ok]
    return 1 if failed else 0


def dump() -> None:
    print()
    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"  {OK if ok else BAD}  {name:<{width}}  {detail}")
    bad = [n for n, ok, _ in results if not ok]
    print()
    if bad:
        print(f"{BAD} {len(bad)} 项失败: {', '.join(bad)}")
    else:
        print(f"{OK} 全部 {len(results)} 项通过")


if __name__ == "__main__":
    raise SystemExit(main())
