"""Cached quotes and daily close histories for the timeline market watch."""
from __future__ import annotations

import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

CN_TZ = ZoneInfo("Asia/Shanghai")
NY_TZ = ZoneInfo("America/New_York")
GROUPS = {
    "day": (
        ("sh000001", "上证指数"), ("sz399001", "深证成指"),
        ("sh000688", "科创50"), ("sz399006", "创业板"),
        ("hkHSI", "恒生指数"), ("hkHSTECH", "恒生科技"),
    ),
    "night": (
        ("us.INX", "标普 500 指数"), ("us.IXIC", "纳斯达克指数"),
        ("us.NDX", "纳斯达克 100"), ("us.DJI", "道琼斯指数"),
        ("usSOXX", "SOXX"), ("usYINN", "YINN"),
    ),
}
HISTORY_SYMBOLS = {"usSOXX": "usSOXX.OQ", "usYINN": "usYINN.AM"}
QUOTE_URL = "https://qt.gtimg.cn/q="
HISTORY_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


def default_group(now: datetime) -> str:
    return "day" if 8 <= now.astimezone(CN_TZ).hour < 20 else "night"


def parse_quotes(text: str, group: str = "day") -> list[dict]:
    records = dict(re.findall(r'v_([\w.]+)="([^"\r\n]*)";', text))
    items = []
    for symbol, name in GROUPS[group]:
        fields = records.get(symbol, "").split("~")
        try:
            expected = HISTORY_SYMBOLS.get(symbol, symbol)[2:]
            if len(fields) < 33 or fields[2] != expected:
                continue
            price, change, percent = (float(fields[i]) for i in (3, 31, 32))
            if not all(math.isfinite(value) for value in (price, change, percent)) or price <= 0:
                continue
            fmt = "%Y-%m-%d %H:%M:%S" if symbol.startswith("us") else (
                "%Y/%m/%d %H:%M:%S" if symbol.startswith("hk") else "%Y%m%d%H%M%S"
            )
            quoted_at = datetime.strptime(fields[30], fmt).replace(tzinfo=NY_TZ if symbol.startswith("us") else CN_TZ)
        except ValueError:
            continue
        items.append({
            "symbol": symbol, "name": name, "price": price,
            "change": change, "percent": percent, "quoted_at": quoted_at.isoformat(),
        })
    if not items:
        raise ValueError("No valid market quotes")
    return items


def parse_history(payload: dict, symbol: str) -> list[dict]:
    data = payload.get("data", {}).get(HISTORY_SYMBOLS.get(symbol, symbol), {})
    rows = data.get("qfqday") or data.get("day") or []
    points = []
    for row in rows:
        try:
            date = datetime.strptime(row[0], "%Y-%m-%d").date().isoformat()
            close = float(row[2])
            if math.isfinite(close) and close > 0:
                points.append({"date": date, "close": close})
        except (ValueError, TypeError, IndexError):
            continue
    points = sorted({point["date"]: point for point in points}.values(), key=lambda point: point["date"])[-20:]
    # Reject sparse legacy series instead of drawing over years of missing data.
    if len(points) < 2 or (datetime.fromisoformat(points[-1]["date"]) - datetime.fromisoformat(points[0]["date"])).days > 45:
        return []
    return points


def quote_status(item: dict, now: datetime) -> str:
    symbol = item["symbol"]
    local = now.astimezone(NY_TZ if symbol.startswith("us") else CN_TZ)
    minute = local.hour * 60 + local.minute
    end = 960 if symbol.startswith(("hk", "us")) else 900
    lunch = 720 if symbol.startswith("hk") else 690
    if local.weekday() >= 5 or minute < 570 or minute >= end:
        return "closed"
    if not symbol.startswith("us") and lunch < minute < 780:
        return "break"
    if not item.get("quoted_at"):
        return "unavailable"
    # Holidays and lagging feeds must never appear as live trading.
    age = (now - datetime.fromisoformat(item["quoted_at"])).total_seconds()
    return "trading" if 0 <= age <= 180 else "delayed"


class MarketQuotes:
    def __init__(self):
        self._locks = {group: threading.Lock() for group in GROUPS}
        self._cache = {group: {"items": {}, "retry_at": 0.0, "history_at": 0.0} for group in GROUPS}

    def _history(self, client: httpx.Client, symbol: str) -> tuple[str, list[dict]]:
        try:
            response = client.get(HISTORY_URL, params={"param": f"{HISTORY_SYMBOLS.get(symbol, symbol)},day,,,20,qfq"})
            response.raise_for_status()
            return symbol, parse_history(response.json(), symbol)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return symbol, []

    def snapshot(self, group: str = "auto") -> dict:
        now = datetime.now(CN_TZ)
        group = default_group(now) if group == "auto" else group
        with self._locks[group]:
            cache = self._cache[group]
            if time.monotonic() >= cache["retry_at"]:
                fresh = {}
                with httpx.Client(timeout=8.0) as client:
                    try:
                        response = client.get(QUOTE_URL + ",".join(symbol for symbol, _ in GROUPS[group]))
                        response.raise_for_status()
                        fresh = {item["symbol"]: item for item in parse_quotes(response.content.decode("gb18030"), group)}
                    except (httpx.HTTPError, ValueError, UnicodeError):
                        pass
                    for symbol, name in GROUPS[group]:
                        previous = cache["items"].get(symbol, {"symbol": symbol, "name": name})
                        cache["items"][symbol] = {**previous, **fresh.get(symbol, {}), "stale": symbol not in fresh}
                    if fresh and time.monotonic() >= cache["history_at"]:
                        with ThreadPoolExecutor(max_workers=6) as pool:
                            for symbol, points in pool.map(lambda symbol: self._history(client, symbol), fresh):
                                item = cache["items"][symbol]
                                if points:
                                    item["history"] = points
                                item["history_stale"] = not bool(points)
                        cache["history_at"] = time.monotonic() + 300
                cache["retry_at"] = time.monotonic() + 30
            items = [{**item, "status": quote_status(item, now)} for item in cache["items"].values()]
            return {
                "group": group, "items": items,
                "stale": any(item["stale"] for item in items), "history_period": 20,
            }
