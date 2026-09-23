#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测式轮询（方案 A）收益评估 —— 只读统计，不改任何数据

用途：在**生产环境**上测算「count=1 探测 + 按需全量」能省多少带宽。
本地 data/ 下是开发库，需要指向真实库（Docker 内通常为 /data/dav.db）。

用法：
    python3 scripts/xq_poll_probe_estimate.py data/dav.db
    python3 scripts/xq_poll_probe_estimate.py /data/dav.db --platform xueqiu

输出：
    · 各 KOL 的发帖频率与所属档位
    · 分档汇总的「该轮有更新概率」与预期带宽节省
    · 不适合走探测的高频 KOL 清单
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from datetime import datetime, timezone

# 与 app/scheduler.py 保持一致（可被后台 config_* 覆盖，此处用默认值）
TIERS = [
    ("组合档",      30,   120),   # COMMINATION_BASE / IDLE_CAP
    ("优先大V",     180,  180),   # PRIORITY_IDLE_CAP
    ("普通大V",     300,  900),   # NORMAL_IDLE_CAP
    ("次要大V",     900,  3600),  # SECONDARY_BASE / IDLE_CAP
]

PROBE_BYTES = 11_767      # count=1 实测
FULL_BYTES = 207_407      # count=20 实测


def parse_ts(v) -> float | None:
    """published_at 在库里有三种格式：毫秒时间戳 / 'YYYY-MM-DD HH:MM' / ISO8601。"""
    if v is None:
        return None
    s = str(v).strip()
    if s.isdigit():
        n = int(s)
        return n / 1000 if n > 1e11 else n          # 毫秒或秒
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=None).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db", help="数据库路径")
    ap.add_argument("--platform", default="xueqiu", help="平台（默认 xueqiu）")
    ap.add_argument("--min-posts", type=int, default=2, help="少于该帖数的 KOL 跳过（默认 2）")
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    cur = con.cursor()

    kols = list(cur.execute(
        "SELECT id, name, external_id, enabled, priority, secondary FROM kols WHERE platform=?",
        (args.platform,)))
    if not kols:
        print(f"库里没有 platform={args.platform} 的 KOL"); return 1

    print(f"库: {args.db}   平台: {args.platform}   KOL 数: {len(kols)}\n")
    rows = []
    for kid, name, ext, enabled, priority, secondary in kols:
        ts = [t for t in (parse_ts(v) for (v,) in cur.execute(
            "SELECT published_at FROM posts WHERE kol_id=? AND published_at IS NOT NULL", (kid,))) if t]
        if len(ts) < args.min_posts:
            continue
        ts.sort()
        span_h = (ts[-1] - ts[0]) / 3600
        if span_h <= 0:
            continue
        rate = (len(ts) - 1) / span_h          # 帖/小时
        rows.append(dict(id=kid, name=name, ext=ext, n=len(ts), span_h=span_h, rate=rate,
                         enabled=bool(enabled), priority=bool(priority), secondary=bool(secondary),
                         last=ts[-1]))

    if not rows:
        print("没有可统计的 KOL（帖子样本不足）"); return 1

    rows.sort(key=lambda r: -r["rate"])
    print(f"{'KOL':<20}{'帖数':>6}{'跨度天':>8}{'帖/天':>8}  档位")
    print("-" * 58)
    for r in rows[:60]:
        d = "" if r["enabled"] else "（停用）"
        print(f"{str(r['name'])[:18]:<20}{r['n']:>6}{r['span_h']/24:>8.1f}{r['rate']*24:>8.2f}  "
              f"{'优先' if r['priority'] else '次要' if r['secondary'] else '普通'}{d}")
    if len(rows) > 60:
        print(f"... 另有 {len(rows)-60} 个未显示")
    rates = sorted(r["rate"] for r in rows)
    print(f"\n合计 {len(rows)} 个  |  帖/小时  最小={rates[0]:.3f}  中位={rates[len(rates)//2]:.3f}  "
          f"均值={sum(rates)/len(rates):.3f}  最大={rates[-1]:.3f}")

    print("\n=== 方案 A 收益预测（按实际轮询间隔）===")
    print(f"{'档位':<10}{'间隔s':>7}{'KOL数':>7}{'P(有更新)':>11}{'平均带宽':>11}{'节省':>8}")
    print("-" * 58)
    tot_base = tot_a = 0.0
    for tier, base, cap in TIERS:
        grp = [r for r in rows if _tier_of(r) == tier]
        if not grp:
            continue
        T = ((base + cap) / 2) / 3600          # 用基础与封顶的均值近似稳态
        P = sum(1 - math.exp(-r["rate"] * T) for r in grp) / len(grp)
        bw = (1 - P) * PROBE_BYTES + P * FULL_BYTES
        tot_base += len(grp) * FULL_BYTES
        tot_a += len(grp) * bw
        print(f"{tier:<10}{int(T*3600):>7}{len(grp):>7}{P*100:>10.1f}%{bw/1024:>10.1f}K"
              f"{100*(1-bw/FULL_BYTES):>7.1f}%")
    print("-" * 58)
    print(f"{'合计':<10}{'':>7}{len(rows):>7}{'':>11}{'':>11}{100*(1-tot_a/tot_base):>7.1f}%")

    hot = [r for r in rows if _tier_of(r) == "次要大V" and r["rate"] > 0.5]
    if hot:
        print("\n=== 建议直接全量、不走探测的 KOL（次要档 + 高频）===")
        for r in hot[:15]:
            print(f"  {str(r['name'])[:18]:<20} {r['rate']*24:.2f} 帖/天")
    return 0


def _tier_of(r: dict) -> str:
    # 组合（external_id 以 ZH 开头）走独立高频档：基础 30s、空轮封顶 120s
    if str(r.get("ext") or "").upper().startswith("ZH"):
        return "组合档"
    if r["secondary"]:
        return "次要大V"
    if r["priority"]:
        return "优先大V"
    return "普通大V"


if __name__ == "__main__":
    sys.exit(main())
