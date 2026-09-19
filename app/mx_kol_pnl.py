"""MX 大V预估盈亏：在预估持仓回放之上叠加价格台账。

口径（与 mx_kol_holdings 同源同窗）：
- 份额即仓位分：回放时间线的 delta 直接当买卖「份额」——买入事件(delta>0)
  按事件时刻价入成本池，卖出事件(delta<0)按 min(|delta|, 持有量) 了结
  （镜像持仓分的 max(0,…)) 钳位，clear 全平；
- 浮动盈亏%（在持）= (最新价 - 平均成本) / 平均成本；
- 已了结收益率%（清仓/翻空出仓/超时未提及）= 累计已实现利润 / 累计卖出成本；
- 严格覆盖：某票全部仓位变动事件价 + 需要的现价都拿到才出 pct，否则 null
  （半吊子数字比没有更误导）。
题材（topic）无价格概念，不参与盈亏。

每票附 actions 操作时间线（kind+at，建仓/加仓/减仓/清仓/翻空减仓）：
按台账份额语义分类（买入无底仓=建仓、卖出吃光持有=清仓），与盈亏数字
同源；行情缺价的事件也照记——操作发生是事实，缺的只是价格。

价格来源 kol_price_feed：名称→代码→(code, at) 批量查价（契约见
docs/price-query-api.md），历史价永久缓存、最新价 TTL 300s。
行情源未接入（桩模式）时 available=false，前端显示占位提示。
本模块纯计算不落库（价格缓存除外），历史不可变，结果可随时重算。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))


def _action_kind(delta: float, units_before: float, ev_kind: str = "") -> str:
    """按台账份额语义分类单笔操作（open/add/trim/clear/flip，前端 1:1 出徽章）。

    与 holdings 时间线的 kind 同源但修正两类口径：
    - 首条即「加仓」词（时间线 kind=hold 但 delta>0）：无先前头寸，对用户实为建仓；
    - 减仓把份额恰好打光 = 清仓（台账视角持有归零）；翻空（flip）保留独立
      语义（变盘信号）优先于清仓判定。
    units_before 必须是**本事件入账前**的影子份额（仅累加 delta，不吃价格缺失）。
    """
    if delta > 0:
        return "add" if units_before > 0 else "open"
    if ev_kind == "flip":
        return "flip"
    return "clear" if units_before + delta <= 0 else "trim"

# 与 mx_kol_holdings.STALE_DAYS 同口径的展示文案；天数本身以 holdings 返回为准
STALE_LABEL = "超时未提及"


def build_kol_pnl(db, kol_id: int, days: int = 30, price_lookup=None) -> dict | None:
    """回放大V近 N 天操作时间线 → 逐票价格台账 → 浮动/已了结盈亏。

    price_lookup(db, requests) 供测试注入价格桩；缺省用 kol_price_feed.get_prices。
    返回 None 表示大V无任何信号（与 build_kol_holdings 的空态一致）。
    """
    from .kol_price_feed import get_prices as _default_lookup, resolve_codes
    from .mx_kol_holdings import build_kol_holdings

    lookup = price_lookup or _default_lookup
    from .kol_price_feed import _normalize_at
    holdings = build_kol_holdings(db, kol_id, days=days)
    if not holdings:
        return None
    stale_days = int(holdings.get("stale_days") or 10)

    # 只取个股事件（题材无价格概念）。timeline 最新在前，回放需早→晚
    stock_events = [e for e in holdings.get("timeline") or []
                    if e.get("target_type") == "stock"]
    stock_events.sort(key=lambda e: (e.get("trading_day") or "", e.get("occurred_at") or ""))

    # 持仓态判定基准：holdings.holdings 是过滤后的在持名单（score>=阈值 且未超时）
    live_names = {h.get("target_name") for h in holdings.get("holdings") or []}

    # 名称 → 代码（解析不到的票无盈亏，coverage 降级）
    names = sorted({e.get("target_name") for e in stock_events if e.get("target_name")})
    code_map = resolve_codes(names)

    # 收集价格请求：所有仓位变动事件（delta≠0）的时刻价 + 全部已解析票的最新价。
    # 最新价不只服务在持股（浮动盈亏）——stale/跌破阈值的票出仓时也要按最新价
    # 估值被动了结，这两类名单回放后才确定，干脆每股都要（多一次缓存查询可忽略）
    requests: list[dict] = []
    for ev in stock_events:
        code = code_map.get(ev.get("target_name"))
        if code and ev.get("delta"):
            requests.append({"code": code, "at": ev.get("occurred_at") or ""})
    for code in sorted(set(code_map.values())):
        requests.append({"code": code, "at": ""})  # 最新价
    prices = lookup(db, requests) if requests else {}
    # 行情可用性：无需查价（没有个股事件/代码全解析失败）不算「未接入」；
    # 有请求但一个价都没拿到才说明行情源缺位（桩模式）
    available = True if not requests else bool(prices)
    # 归一后的键对齐：lookup 内部会把 at 归一成契约格式，这里同样归一再取
    def _price(code: str, at: str) -> dict | None:
        return prices.get((code, _normalize_at(at)))

    # 逐票台账回放
    stocks: list[dict] = []
    event_prices: dict[str, str] = {}  # "名称|occurred_at" → "@ 15.20" 展示用
    # coverage 分母含代码解析不到的票：行情覆盖率的语义是「整体事件里拿到价格的比例」，
    # 名称映射失败和价格查询失败对用户是同一种缺失
    unresolved_events = sum(1 for e in stock_events
                            if e.get("delta") and e.get("target_name") not in code_map)
    for name in names:
        code = code_map.get(name)
        if not code:
            continue  # 名称解析不到代码：无行情锚点，不进盈亏名单（计入 coverage 降级）
        evs = [e for e in stock_events if e.get("target_name") == name]
        units = 0.0            # 持有份额
        cost_pool = 0.0        # 成本池（份额×买价）
        buy_cost = 0.0         # 累计买入成本（收益率分母）
        realized = 0.0         # 累计已实现利润
        opened_at = ""
        closed_at = ""
        priced_events = 0
        moved_events = 0
        actions: list[dict] = []  # 操作时间线（kind+at）：操作是事实，行情缺价也照记
        shadow_units = 0.0        # 影子份额（仅累加 delta）：操作分类锚点，不吃价格缺失
        for ev in evs:  # 早 → 晚
            delta = float(ev.get("delta") or 0.0)
            if not opened_at:
                opened_at = ev.get("occurred_at") or ""
            if not delta:
                continue  # hold 表态不动台账，但也不需要价格
            moved_events += 1
            ev_kind = str(ev.get("kind") or "")
            at = ev.get("occurred_at") or ""
            # 操作分类（先于价格判定）：买入无底仓=建仓/有底仓=加仓；卖出吃光
            # 影子份额=清仓、部分=减仓；翻空单列。钳位后无实际变动的不记
            kind = _action_kind(delta, shadow_units, ev_kind) if delta > 0 or shadow_units > 0 else ""
            if kind:
                actions.append({"kind": kind, "at": at})
            shadow_units = max(0.0, shadow_units + delta)
            px = _price(code, at) if code else None
            if not px:
                continue  # 价格缺失：该事件无法入账（票级严格覆盖判定兜底）
            priced_events += 1
            price = px["price"]
            event_prices[f"{name}|{at}"] = f"@ {price:.2f}"
            if delta > 0:
                units += delta
                cost_pool += delta * price
                buy_cost += delta * price
            else:
                sell = min(-delta, units)
                if sell <= 0:
                    continue  # 无仓可卖（钳位后 delta 为 0 的情形已过滤）
                avg = cost_pool / units
                realized += (price - avg) * sell
                units -= sell
                cost_pool -= avg * sell
                closed_at = at or closed_at
        if not moved_events:
            continue  # 全程只有表态无操作：无价格锚点，不进盈亏名单

        state = "holding" if name in live_names else "closed"
        exit_note = ""
        if state == "closed":
            # 区分主动了结与超时未提及：取该票最后一个事件日判断
            last_day = max(e.get("trading_day") or "" for e in evs)
            try:
                stale_cut = (datetime.now(CN_TZ).date() - timedelta(days=stale_days))
                from datetime import date as _date
                if _date.fromisoformat(last_day) < stale_cut:
                    state = "stale"
                    exit_note = f"超{stale_days}天未提及，按最新价估算"
            except ValueError:
                pass
            if not exit_note and not closed_at:
                exit_note = "跌破仓位阈值出仓"

        # 严格覆盖：任一仓位变动事件缺价则本票盈亏全部不出数。
        # 缺价事件被跳过后账面均价失真（少计买入/卖出），半吊子数字比没有更误导；
        # units/事件计数仍如实保留供 coverage 与行数展示
        if priced_events < moved_events:
            stocks.append({
                "target_name": name,
                "code": code or "",
                "state": state,
                "avg_cost": None,
                "last_price": None,
                "floating_pnl_pct": None,
                "realized_pnl_pct": None,
                "units": round(units, 2),
                "opened_at": opened_at,
                "closed_at": closed_at,
                "actions": actions,
                "events_priced": priced_events,
                "events_total": moved_events,
                "exit_note": "部分操作事件缺行情，无法估算",
            })
            continue

        # 了结收益率：利润 / 累计买入成本（投入口径）。无任何卖出事件时不给数
        # （从未了结的票谈“已实现收益”是误导，浮动盈亏才是它的口径）
        realized_pct = round(realized / buy_cost * 100, 2) if (buy_cost > 0 and closed_at) else None
        if state in ("stale", "closed") and units > 0:
            px = _price(code, "") if code else None
            if px and state == "stale":
                realized += (px["price"] - cost_pool / units) * units
                realized_pct = round(realized / buy_cost * 100, 2) if buy_cost > 0 else None
                units, cost_pool = 0.0, 0.0  # 全部视作了结

        row = {
            "target_name": name,
            "code": code or "",
            "state": state,
            "avg_cost": round(cost_pool / units, 3) if units > 0 and cost_pool > 0 else None,
            "last_price": None,
            "floating_pnl_pct": None,
            "realized_pnl_pct": realized_pct,
            "units": round(units, 2),
            "opened_at": opened_at,
            "closed_at": closed_at,
            "actions": actions,
            "events_priced": priced_events,
            "events_total": moved_events,
            "exit_note": exit_note,
        }
        if state == "holding":
            px = _price(code, "") if code else None  # 最新价
            if px and units > 0 and cost_pool > 0:
                row["last_price"] = px["price"]
                row["floating_pnl_pct"] = round((px["price"] - cost_pool / units)
                                                / (cost_pool / units) * 100, 2)
        stocks.append(row)

    # 汇总：总回报 = 各票（浮动+已实现）按卖出成本+成本池等权聚合太绕，
    # 采用「各票收益率简单平均」口径（份额本就是相对分，等权即按票数）
    rated = [s for s in stocks if s["floating_pnl_pct"] is not None
             or s["realized_pnl_pct"] is not None]
    winners = 0
    losers = 0
    total = 0.0
    for s in rated:
        # 主收益率：在持看浮动，已了结看已实现；两者都有（部分了结+余仓）时
        # 浮动优先（当前状态的市场判定）
        pct = s["floating_pnl_pct"] if s["floating_pnl_pct"] is not None else s["realized_pnl_pct"]
        if pct is None:
            continue
        total += pct
        if pct > 0:
            winners += 1
        elif pct < 0:
            losers += 1
    moved_total = sum(s["events_total"] for s in stocks) + unresolved_events
    moved_priced = sum(s["events_priced"] for s in stocks)
    holding_rows = [s for s in stocks if s["state"] == "holding"]
    closed_rows = [s for s in stocks if s["state"] != "holding"]

    return {
        "kol": holdings.get("kol") or {},
        "window_days": days,
        "stale_days": stale_days,
        "available": available,
        "stocks": stocks,
        "event_prices": event_prices,
        "summary": {
            "holding_count": len(holding_rows),
            "closed_count": len(closed_rows),
            "winners": winners,
            "losers": losers,
            "total_return_pct": round(total / len(rated), 2) if rated else None,
            "coverage": round(moved_priced / moved_total, 3) if moved_total else 1.0,
        },
        "generated_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    }
