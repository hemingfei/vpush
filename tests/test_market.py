from datetime import datetime
from unittest.mock import patch

import httpx
import pytest

from app.market import CN_TZ, GROUPS, MINUTE_SYMBOLS, MarketQuotes, default_group, parse_intraday, parse_quotes, quote_status


def quote_payload(price="3930.12", timestamp="20260904103000", group="day"):
    rows = []
    for symbol, name in GROUPS[group]:
        fields = [""] * 33
        fields[1:5] = [name, MINUTE_SYMBOLS.get(symbol, symbol)[2:], price, "3942.09"]
        formatted = timestamp
        if timestamp != "bad-time" and symbol.startswith(("hk", "us")):
            fmt = "%Y/%m/%d %H:%M:%S" if symbol.startswith("hk") else "%Y-%m-%d %H:%M:%S"
            formatted = datetime.strptime(timestamp, "%Y%m%d%H%M%S").strftime(fmt)
        fields[30:33] = [formatted, "-11.97", "-0.30"]
        rows.append(f'v_{symbol}="{"~".join(fields)}";')
    return "\n".join(rows)


def test_parse_quotes_preserves_order_and_exchange_time():
    items = parse_quotes(quote_payload())
    assert [item["symbol"] for item in items] == [symbol for symbol, _ in GROUPS["day"]]
    assert items[0] == {
        "symbol": "sh000001", "name": "上证指数", "price": 3930.12,
        "previous_close": 3942.09, "change": -11.97, "percent": -0.3, "quoted_at": "2026-09-04T10:30:00+08:00",
    }


@pytest.mark.parametrize("payload", [
    "", 'v_sh000001="";', quote_payload("NaN"), quote_payload("inf"),
    quote_payload("0"), quote_payload(timestamp="bad-time"),
])
def test_rejects_incomplete_or_invalid_snapshot(payload):
    with pytest.raises(ValueError):
        parse_quotes(payload)


@pytest.mark.parametrize("now, expected", [
    ("2026-09-04T10:31:00", "trading"),
    ("2026-09-04T10:34:00", "delayed"),
    ("2026-09-04T12:00:00", "break"),
    ("2026-09-04T15:00:00", "closed"),
    ("2026-09-06T10:00:00", "closed"),
    ("2026-09-07T10:00:00", "delayed"),
])
def test_trading_status_requires_recent_exchange_quote(now, expected):
    assert quote_status(parse_quotes(quote_payload())[0], datetime.fromisoformat(now).replace(tzinfo=CN_TZ)) == expected


def test_shared_cache_failure_cooldown_and_recovery():
    cache = MarketQuotes()
    response = httpx.Response(200, content=quote_payload().encode("gb18030"), request=httpx.Request("GET", "https://qt.gtimg.cn"))
    with patch("app.market.httpx.Client") as factory, patch("app.market.time.monotonic", return_value=100) as clock, patch.object(cache, "_intraday", side_effect=lambda client, symbol: (symbol, None)):
        get = factory.return_value.__enter__.return_value.get
        get.return_value = response
        first = cache.snapshot("day")
        assert not first["stale"]
        assert cache.snapshot("day") == first
        assert get.call_count == 1
        clock.return_value = 131
        get.side_effect = httpx.ReadTimeout("unavailable")
        failed = cache.snapshot("day")
        assert failed["stale"]
        assert [item["price"] for item in failed["items"]] == [item["price"] for item in first["items"]]
        assert all(item["stale"] for item in failed["items"])
        cache.snapshot("day")
        assert get.call_count == 2
        clock.return_value = 162
        get.side_effect = None
        assert not cache.snapshot("day")["stale"]


def test_cold_failure_returns_no_fabricated_quotes():
    with patch("app.market.httpx.Client") as factory:
        factory.return_value.__enter__.return_value.get.side_effect = httpx.ConnectError("offline")
        result = MarketQuotes().snapshot("night")
        assert result["group"] == "night" and result["stale"]
        assert len(result["items"]) == 6
        assert all("price" not in item for item in result["items"])


def test_market_api_requires_login_and_returns_snapshot():
    from tests.test_api import make_client, user_headers

    client = make_client()
    with patch("app.api.MarketQuotes.snapshot", return_value={"items": [], "stale": True}) as snapshot:
        assert client.get("/api/market/indices").status_code == 401
        snapshot.assert_not_called()
        response = client.get("/api/market/indices", headers=user_headers(client, "market-reader"))
        assert response.status_code == 200
        assert response.json() == {"items": [], "stale": True}
        snapshot.assert_called_once_with("auto")
        headers = user_headers(client, "market-second")
        assert client.get("/api/market/indices?group=night", headers=headers).status_code == 200
        snapshot.assert_called_with("night")
        assert client.get("/api/market/indices?group=arbitrary", headers=headers).status_code == 422


def test_bad_symbol_does_not_hide_other_quotes():
    items = parse_quotes(quote_payload().replace("~399001~", "~000001~"))
    assert len(items) == 5
    assert "sz399001" not in {item["symbol"] for item in items}


@pytest.mark.parametrize("hour,group", [(7, "night"), (8, "day"), (19, "day"), (20, "night"), (0, "night")])
def test_auto_group_beijing_boundaries(hour, group):
    assert default_group(datetime(2026, 9, 4, hour, tzinfo=CN_TZ)) == group


@pytest.mark.parametrize("timestamp,offset", [("20260904103000", "-04:00"), ("20261204103000", "-05:00")])
def test_us_quotes_use_exchange_timezone_and_etf_codes(timestamp, offset):
    items = parse_quotes(quote_payload(timestamp=timestamp, group="night"), "night")
    assert len(items) == 6
    assert all(item["quoted_at"].endswith(offset) for item in items)
    assert items[-2]["symbol"] == "usSOXX"


@pytest.mark.parametrize("symbol,now,expected", [
    ("hkHSI", "2026-09-04T15:30:00+08:00", "trading"),
    ("hkHSI", "2026-09-04T12:30:00+08:00", "break"),
    ("sh000001", "2026-09-04T15:30:00+08:00", "closed"),
    ("us.INX", "2026-09-04T21:30:00+08:00", "trading"),
    ("us.INX", "2026-12-04T21:30:00+08:00", "closed"),
    ("us.INX", "2026-12-04T22:30:00+08:00", "trading"),
    ("us.INX", "2026-09-05T02:00:00+08:00", "trading"),
])
def test_exchange_sessions_and_us_dst(symbol, now, expected):
    current = datetime.fromisoformat(now)
    assert quote_status({"symbol": symbol, "quoted_at": now}, current) == expected


def minute_payload(symbol, rows, date="20260904"):
    return {"data": {MINUTE_SYMBOLS.get(symbol, symbol): {"data": {"date": date, "data": rows}}}}


@pytest.mark.parametrize("symbol,duration,afternoon", [("sh000001", 240, 120), ("hkHSI", 330, 150), ("usSOXX", 390, 210)])
def test_intraday_uses_minute_prices_and_exchange_sessions(symbol, duration, afternoon):
    data = parse_intraday(minute_payload(symbol, [
        "1300 105.25 99999 12345", "0930 100 88888", "0931 NaN 1", "0932 -1 2", "0933 inf 1",
        "bad", "2500 102 1", "0800 103 1", "1831 107 1", "0930 101 88888", "1230 104 1",
    ]), symbol)
    assert data["date"] == "2026-09-04" and data["duration"] == duration
    assert data["points"][0] == {"time": "09:30", "minute": 0, "price": 101.0}
    assert data["points"][-1] == {"time": "13:00", "minute": afternoon, "price": 105.25}
    assert len(data["points"]) == (3 if symbol.startswith("us") else 2)


def test_intraday_rejects_daily_history_and_invalid_dates():
    assert parse_intraday({"data": {"hkHSI": {"day": [["2026-09-04", "100", "105"]]}}}, "hkHSI") is None
    assert parse_intraday(minute_payload("hkHSI", ["0930 100"], "bad"), "hkHSI") is None
    assert parse_intraday(minute_payload("hkHSI", ["0930 NaN"]), "hkHSI") is None


@pytest.mark.parametrize("symbol,endpoint,code", [
    ("sh000001", "minute", "sh000001"), ("hkHSI", "minute", "hkHSI"),
    ("us.INX", "UsMinute", "us.INX"), ("usSOXX", "UsMinute", "usSOXX.OQ"), ("usYINN", "UsMinute", "usYINN.AM"),
])
def test_intraday_requests_correct_endpoint_and_code(symbol, endpoint, code):
    def respond(request):
        assert request.url.path == f"/appstock/app/{endpoint}/query"
        assert dict(request.url.params) == {"code": code}
        return httpx.Response(200, json=minute_payload(symbol, ["0930 100", "0931 101"]))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result_symbol, data = MarketQuotes()._intraday(client, symbol)
    assert result_symbol == symbol and len(data["points"]) == 2


def test_intraday_cache_refresh_failure_and_trading_day_rollover():
    cache = MarketQuotes()
    series = parse_intraday(minute_payload("sh000001", ["0930 100", "1030 101"]), "sh000001")
    with patch("app.market.httpx.Client") as factory, patch("app.market.time.monotonic", return_value=100) as clock, patch.object(cache, "_intraday") as minute:
        get = factory.return_value.__enter__.return_value.get
        get.return_value = httpx.Response(200, content=quote_payload().encode("gb18030"), request=httpx.Request("GET", "https://qt.gtimg.cn"))
        minute.side_effect = lambda client, symbol: (symbol, series)
        first = cache.snapshot("day")["items"][0]
        assert first["intraday"] == series and not first["intraday_stale"]
        cache.snapshot("day")
        assert minute.call_count == 6
        clock.return_value = 131
        minute.side_effect = lambda client, symbol: (symbol, None)
        failed = cache.snapshot("day")["items"][0]
        assert failed["intraday"] == series and failed["intraday_stale"]
        clock.return_value = 162
        get.return_value = httpx.Response(200, content=quote_payload(timestamp="20260907093000").encode("gb18030"), request=httpx.Request("GET", "https://qt.gtimg.cn"))
        minute.side_effect = lambda client, symbol: (symbol, series)
        rollover = cache.snapshot("day")["items"][0]
        assert "intraday" not in rollover and rollover["intraday_stale"]
        clock.return_value = 193
        series = {**series, "date": "2026-09-07"}
        recovered = cache.snapshot("day")["items"][0]
        assert recovered["intraday"]["date"] == "2026-09-07" and not recovered["intraday_stale"]


def test_live_quote_with_lagging_minutes_is_marked_delayed():
    cache = MarketQuotes()
    item = parse_quotes(quote_payload())[0]
    item.update(stale=False, intraday_stale=False, intraday=parse_intraday(minute_payload("sh000001", ["0930 100", "1000 101"]), "sh000001"))
    cache._cache["day"] = {"items": {"sh000001": item}, "retry_at": float("inf")}
    with patch("app.market.quote_status", return_value="trading"):
        assert cache.snapshot("day")["items"][0]["intraday_stale"]
    with patch("app.market.quote_status", return_value="closed"):
        assert not cache.snapshot("day")["items"][0]["intraday_stale"]
