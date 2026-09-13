"""Cached quotes and intraday minute prices for the timeline market watch."""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

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
MINUTE_SYMBOLS = {"usSOXX": "usSOXX.OQ", "usYINN": "usYINN.AM"}
QUOTE_URL = "https://qt.gtimg.cn/q="
MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/{market}/query"


def default_group(now: datetime) -> str:
    return "day" if 8 <= now.astimezone(CN_TZ).hour < 20 else "night"


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + (occurrence - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    last_day = next_month - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    # Anonymous Gregorian algorithm; Good Friday is the only Easter-derived NYSE closure.
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def is_us_market_holiday(day: date) -> bool:
    fixed = {
        _observed_fixed_holiday(year, month, holiday_day)
        for year in (day.year - 1, day.year, day.year + 1)
        for month, holiday_day in ((1, 1), (7, 4), (12, 25))
    }
    if day.year >= 2022:
        fixed.add(_observed_fixed_holiday(day.year, 6, 19))
    year = day.year
    movable = {
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _last_weekday(year, 5, 0),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _easter_sunday(year) - timedelta(days=2),
    }
    return day in fixed or day in movable


def parse_quotes(text: str, group: str = "day") -> list[dict]:
    records = dict(re.findall(r'v_([\w.]+)="([^"\r\n]*)";', text))
    items = []
    for symbol, name in GROUPS[group]:
        fields = records.get(symbol, "").split("~")
        try:
            expected = MINUTE_SYMBOLS.get(symbol, symbol)[2:]
            if len(fields) < 33 or fields[2] != expected:
                continue
            price, previous_close, change, percent = (float(fields[i]) for i in (3, 4, 31, 32))
            if not all(math.isfinite(value) for value in (price, previous_close, change, percent)) or min(price, previous_close) <= 0:
                continue
            fmt = "%Y-%m-%d %H:%M:%S" if symbol.startswith("us") else (
                "%Y/%m/%d %H:%M:%S" if symbol.startswith("hk") else "%Y%m%d%H%M%S"
            )
            quoted_at = datetime.strptime(fields[30], fmt).replace(tzinfo=NY_TZ if symbol.startswith("us") else CN_TZ)
        except ValueError:
            continue
        items.append({
            "symbol": symbol, "name": name, "price": price,
            "previous_close": previous_close, "change": change, "percent": percent, "quoted_at": quoted_at.isoformat(),
        })
    if not items:
        raise ValueError("No valid market quotes")
    return items


def parse_intraday(payload: dict, symbol: str) -> dict | None:
    data = payload.get("data", {}).get(MINUTE_SYMBOLS.get(symbol, symbol), {}).get("data", {})
    try:
        date = datetime.strptime(data.get("date", ""), "%Y%m%d").date().isoformat()
    except (ValueError, TypeError):
        return None
    us, hk = symbol.startswith("us"), symbol.startswith("hk")
    end, lunch = (960 if us or hk else 900), (720 if hk else 690)
    duration = end - 570 - (0 if us else 780 - lunch)
    points = []
    for row in data.get("data", []):
        try:
            fields = row.split()
            clock = datetime.strptime(fields[0], "%H%M")
            minute, price = clock.hour * 60 + clock.minute, float(fields[1])
            if not math.isfinite(price) or price <= 0 or not 570 <= minute <= end:
                continue
            if not us and lunch < minute < 780:
                continue
            offset = minute - 570 - (780 - lunch if not us and minute >= 780 else 0)
            points.append({"time": clock.strftime("%H:%M"), "minute": offset, "price": price})
        except (ValueError, TypeError, IndexError, AttributeError):
            continue
    points = sorted({point["time"]: point for point in points}.values(), key=lambda point: point["time"])
    return {"date": date, "duration": duration, "points": points} if points else None


def quote_status(item: dict, now: datetime) -> str:
    symbol = item["symbol"]
    local = now.astimezone(NY_TZ if symbol.startswith("us") else CN_TZ)
    minute = local.hour * 60 + local.minute
    end = 960 if symbol.startswith(("hk", "us")) else 900
    lunch = 720 if symbol.startswith("hk") else 690
    if symbol.startswith("us") and is_us_market_holiday(local.date()):
        return "holiday"
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
        self._cache = {
            group: {"items": {}, "retry_at": 0.0, "refreshing": False}
            for group in GROUPS
        }

    def _intraday(self, client: httpx.Client, symbol: str) -> tuple[str, dict | None]:
        try:
            market = "UsMinute" if symbol.startswith("us") else "minute"
            response = client.get(MINUTE_URL.format(market=market), params={"code": MINUTE_SYMBOLS.get(symbol, symbol)})
            response.raise_for_status()
            return symbol, parse_intraday(response.json(), symbol)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return symbol, None

    def _fetch_group(self, group: str, previous_items: dict) -> dict:
        fresh = {}
        with httpx.Client(timeout=8.0) as client:
            try:
                response = client.get(QUOTE_URL + ",".join(symbol for symbol, _ in GROUPS[group]))
                response.raise_for_status()
                fresh = {
                    item["symbol"]: item
                    for item in parse_quotes(response.content.decode("gb18030"), group)
                }
            except (httpx.HTTPError, ValueError, UnicodeError):
                pass
            items = {}
            for symbol, name in GROUPS[group]:
                previous = previous_items.get(symbol, {"symbol": symbol, "name": name})
                items[symbol] = {
                    **previous,
                    **fresh.get(symbol, {}),
                    "stale": symbol not in fresh,
                }
            if fresh:
                with ThreadPoolExecutor(max_workers=6) as pool:
                    for symbol, intraday in pool.map(
                        lambda symbol: self._intraday(client, symbol), fresh
                    ):
                        item = items[symbol]
                        quote_date = item["quoted_at"][:10]
                        valid = intraday is not None and intraday["date"] == quote_date
                        if valid:
                            item["intraday"] = intraday
                        elif item.get("intraday", {}).get("date") != quote_date:
                            item.pop("intraday", None)
                        item["intraday_stale"] = not valid
        return items

    def _refresh_group(self, group: str) -> None:
        lock = self._locks[group]
        with lock:
            previous_items = {
                symbol: dict(item)
                for symbol, item in self._cache[group]["items"].items()
            }
        items = None
        try:
            items = self._fetch_group(group, previous_items)
        except Exception:  # noqa: BLE001 - a background refresh must release its flag
            logger.exception("market quote refresh failed group=%s", group)
        finally:
            with lock:
                cache = self._cache[group]
                if items is not None:
                    cache["items"] = items
                else:
                    for item in cache["items"].values():
                        item["stale"] = True
                cache["retry_at"] = time.monotonic() + 30
                cache["refreshing"] = False

    def _start_refresh(self, group: str) -> None:
        threading.Thread(
            target=self._refresh_group,
            args=(group,),
            name=f"market-{group}-refresh",
            daemon=True,
        ).start()

    def _snapshot_locked(self, group: str, now: datetime) -> dict:
        items = []
        for item in self._cache[group]["items"].values():
            status = quote_status(item, now)
            intraday = item.get("intraday")
            lagging = False
            if intraday and status == "trading":
                quoted_at = datetime.fromisoformat(item["quoted_at"])
                last_point = datetime.fromisoformat(
                    f'{intraday["date"]}T{intraday["points"][-1]["time"]}'
                ).replace(tzinfo=quoted_at.tzinfo)
                lagging = (quoted_at - last_point).total_seconds() > 180
            items.append(
                {
                    **item,
                    "status": status,
                    "intraday_stale": item["stale"]
                    or item.get("intraday_stale", True)
                    or lagging,
                }
            )
        return {
            "group": group,
            "items": items,
            "stale": any(item["stale"] for item in items),
        }

    def snapshot(self, group: str = "auto") -> dict:
        now = datetime.now(CN_TZ)
        group = default_group(now) if group == "auto" else group
        refresh_sync = False
        refresh_async = False
        lock = self._locks[group]
        with lock:
            cache = self._cache[group]
            if (
                time.monotonic() >= cache["retry_at"]
                and not cache.get("refreshing", False)
            ):
                cold_cache = not cache["items"]
                cache["refreshing"] = True
                if cold_cache:
                    cache["items"] = {
                        symbol: {"symbol": symbol, "name": name, "stale": True}
                        for symbol, name in GROUPS[group]
                    }
                refresh_sync = cold_cache
                refresh_async = not cold_cache
        if refresh_sync:
            self._refresh_group(group)
        elif refresh_async:
            self._start_refresh(group)
        with lock:
            return self._snapshot_locked(group, now)
