"""MX 大V预估盈亏：台账回放 + 行情缓存 + 端点测试。

价格通过 price_lookup 桩注入（不依赖真实行情源），
契约口径见 docs/price-query-api.md。
"""
from datetime import datetime, timedelta

from test_api import auth_headers, make_client
from test_mx_kol_holdings import _seed_opinions

from app import kol_price_feed as kpf
from app import mx_kol_pnl as mp


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def _lookup_factory(table: dict, calls=None):
    """价格桩：table 为 {(code, at): price}，at 已按契约归一（T 分隔含秒）。

    calls 收集实际请求（含 at='' 的最新价），供缓存命中断言。
    """
    def lookup(db, requests):
        if calls is not None:
            calls.extend(requests)
        out = {}
        for r in requests or []:
            key = (r["code"], kpf._normalize_at(r["at"]))
            if key in table:
                out[key] = {"price": table[key], "actual_at": key[1], "name": ""}
        return out
    return lookup


# 测试用名称→代码表：绕开 a_share_names.json 的真实映射（桩模块级注入）
_NAME_CODES = {"贵州茅台": "sh600519", "中科曙光": "sh603019", "老白干酒": "sh600559",
               "宁德时代": "sz300750", "新股票": "sz000001"}


def _patch_codes(monkeypatch):
    monkeypatch.setattr(kpf, "name_to_symbol", lambda: _NAME_CODES)


def test_ledger_full_cycle_floating_and_realized(monkeypatch):
    """建仓→加仓→减仓→清仓：均价/已实现/浮动全流程数字核对。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "台账大V", "room1")
    t = _today()
    # 茅台：09:16 建仓 3 份 @10.00，10:15 加仓 2 份 @12.00（均价 (3*10+2*12)/5=10.8），
    # 13:26 减仓 2 份 @13.50（已实现 (13.5-10.8)*2=5.4），14:26 清仓 3 份 @15.00
    # （已实现 (15-10.8)*3=12.6，累计 18）；收益率=利润/累计买入成本 18/54=33.33%
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "贵州茅台", "bull", "加仓"),
        (t, "13:30", "13:26", "stock", "贵州茅台", "bull", "减仓"),
        (t, "14:30", "14:26", "stock", "贵州茅台", "bear", "清仓"),
    ])
    px = {
        ("sh600519", f"{t}T09:16:00"): 10.0,
        ("sh600519", f"{t}T10:15:00"): 12.0,
        ("sh600519", f"{t}T13:26:00"): 13.5,
        ("sh600519", f"{t}T14:26:00"): 15.0,
    }
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    assert out["available"] is True
    row = out["stocks"][0]
    assert row["target_name"] == "贵州茅台" and row["state"] == "closed"
    assert row["units"] == 0.0 and row["avg_cost"] is None  # 全平后无余仓
    assert row["realized_pnl_pct"] == 33.33
    assert row["floating_pnl_pct"] is None
    assert row["events_priced"] == row["events_total"] == 4
    # 时间线 @价标：4 条事件全有
    assert len(out["event_prices"]) == 4
    assert out["event_prices"][f"贵州茅台|{t} 09:16:00"] == "@ 10.00"
    assert out["summary"]["closed_count"] == 1 and out["summary"]["holding_count"] == 0
    assert out["summary"]["winners"] == 1 and out["summary"]["total_return_pct"] == 33.33


def test_ledger_partial_hold_floating_pnl(monkeypatch):
    """部分减仓后仍持仓：浮动盈亏 = (现价-均价)/均价。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "半仓大V", "room1")
    t = _today()
    # 建仓 3 @10 + 加仓 2 @15 → 均价 12；减仓 2 @12（盈亏 0）→ 余 3 份；
    # 现价 15 → 浮动 (15-12)/12 = 25%
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "中科曙光", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "中科曙光", "bull", "加仓"),
        (t, "11:20", "11:15", "stock", "中科曙光", "bull", "减仓"),
    ])
    px = {
        ("sh603019", f"{t}T09:16:00"): 10.0,
        ("sh603019", f"{t}T10:15:00"): 15.0,
        ("sh603019", f"{t}T11:15:00"): 12.0,
        ("sh603019", ""): 15.0,  # 最新价
    }
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    row = out["stocks"][0]
    assert row["state"] == "holding"
    assert row["avg_cost"] == 12.0
    assert row["last_price"] == 15.0
    assert row["floating_pnl_pct"] == 25.0
    assert row["realized_pnl_pct"] == 0.0


def test_ledger_sell_clamped_to_units(monkeypatch):
    """钳位卖出：首条即减仓无仓可减（delta=0 不入账）；翻空 -2 只卖掉持有的 1 份。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "钳位大V", "room1")
    t = _today()
    # 09:16 无操作看多（+1 份轻仓）；10:15 首条减仓（无仓可减？有 1 份仓：
    # 卖 2 钳到卖 1）——实际用翻空场景更直接：
    # 看多 1 份 → 翻空 -2 → 只卖出 1 份，余 0，跌破阈值出持仓
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "老白干酒", "bull", ""),
        (t, "10:20", "10:15", "stock", "老白干酒", "bear", ""),
    ])
    px = {
        ("sh600559", f"{t}T09:16:00"): 10.0,
        ("sh600559", f"{t}T10:15:00"): 12.0,
    }
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    row = out["stocks"][0]
    # 翻空 delta=-2 但只持有 1 份：卖出 1 份，已实现 (12-10)*1=2，收益率 2/10=20%
    assert row["state"] == "closed"
    assert row["units"] == 0.0
    assert row["realized_pnl_pct"] == 20.0
    # 有真实卖出事件（翻空），exit_note 不再叠「跌破阈值出仓」的推断说明
    assert row["exit_note"] == ""


def test_stale_stock_treated_as_closed(monkeypatch):
    """沉默超 STALE_DAYS：按已了结处理，exit_note 带超时说明，按最新价估算。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "超时大V", "room1")
    old, new = _days_ago(15), _today()
    _seed_opinions(db, kol, [
        (old, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
        (new, "09:20", "09:16", "stock", "宁德时代", "bull", "建仓"),
    ])
    px = {
        ("sh600519", f"{old}T09:16:00"): 10.0,
        ("sh600519", ""): 11.0,   # 超时票无清仓事件：按最新价估算了结
        ("sz300750", f"{new}T09:16:00"): 20.0,
        ("sz300750", ""): 18.0,
    }
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    by = {s["target_name"]: s for s in out["stocks"]}
    assert by["贵州茅台"]["state"] == "stale"
    assert "未提及" in by["贵州茅台"]["exit_note"]
    # stale 票：无卖出事件，成本 10 → 最新 11，了结收益 10%
    assert by["贵州茅台"]["realized_pnl_pct"] == 10.0
    assert by["宁德时代"]["state"] == "holding"
    assert by["宁德时代"]["floating_pnl_pct"] == -10.0
    assert out["summary"]["winners"] == 1 and out["summary"]["losers"] == 1


def test_missing_price_degrades_coverage(monkeypatch):
    """部分事件价格缺失：该票 pct=null、coverage<1；名称解析不到的票不进 stocks。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "缺价大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "贵州茅台", "bull", "加仓"),
        (t, "11:20", "11:15", "stock", "未知名称股票", "bull", "建仓"),
    ])
    px = {("sh600519", f"{t}T09:16:00"): 10.0}  # 只有第一条事件有价
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    by = {s["target_name"]: s for s in out["stocks"]}
    assert "未知名称股票" not in by  # 代码解析不到：不进盈亏名单
    assert by["贵州茅台"]["events_priced"] == 1
    assert by["贵州茅台"]["events_total"] == 2
    assert by["贵州茅台"]["floating_pnl_pct"] is None  # 覆盖不全不出数
    assert out["summary"]["coverage"] < 1.0
    assert out["summary"]["total_return_pct"] is None  # 无票出数


def test_partial_missing_buy_price_no_pnl(monkeypatch):
    """严格覆盖回归：加仓事件缺价（最新价可得）也不得出浮动盈亏。

    旧实现只跳过缺价事件继续算：建仓 3 份 @10 有价、加仓 2 份缺价时，
    加仓份额凭空消失，均价按 10 算出虚高的 +100%——比没有更误导。
    """
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "缺加仓价大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "贵州茅台", "bull", "加仓"),
    ])
    px = {
        ("sh600519", f"{t}T09:16:00"): 10.0,
        ("sh600519", ""): 20.0,  # 最新价有 → 旧 bug 会用残缺均价出 +100%
    }
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    row = out["stocks"][0]
    assert row["events_priced"] == 1 and row["events_total"] == 2
    assert row["avg_cost"] is None
    assert row["floating_pnl_pct"] is None and row["realized_pnl_pct"] is None
    assert "缺行情" in row["exit_note"]
    assert out["summary"]["total_return_pct"] is None
    assert out["summary"]["coverage"] < 1.0


def test_stub_mode_available_false_and_empty(monkeypatch):
    """桩模式（fetch_remote 返回空）：available=false；无事件大V返回 None。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "桩大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
    ])
    out = mp.build_kol_pnl(db, kol, price_lookup=lambda db_, reqs: {})
    assert out is not None and out["available"] is False
    assert out["stocks"] == [] or all(s["floating_pnl_pct"] is None for s in out["stocks"])
    # 只有题材观点/名称全解析不到：无价格请求，available 不降为 false
    kol15 = db.add_kol("mx", "题材大V", "room3")
    _seed_opinions(db, kol15, [
        (t, "09:20", "09:16", "topic", "AI算力", "bull", ""),
    ])
    topic_out = mp.build_kol_pnl(db, kol15, price_lookup=lambda db_, reqs: {})
    assert topic_out["available"] is True and topic_out["stocks"] == []
    # 无任何观点
    kol2 = db.add_kol("mx", "空大V", "room2")
    assert mp.build_kol_pnl(db, kol2, price_lookup=lambda db_, reqs: {}) is None


def test_price_cache_hit_and_latest_ttl(monkeypatch):
    """get_prices 缓存语义：历史价命中不重查；最新价 TTL 内命中、过期重查。"""
    client = make_client()
    db = client.app.state.db
    t = _today()
    calls: list[dict] = []
    real = kpf.fetch_remote

    def counting_fetch(requests):
        calls.extend(requests)
        return {(r["code"], r["at"]): {"price": 10.0, "actual_at": "", "name": ""}
                for r in requests}

    monkeypatch.setattr(kpf, "fetch_remote", counting_fetch)
    hist = {"code": "sh600519", "at": f"{t}T09:16:00"}
    latest = {"code": "sh600519", "at": ""}
    # 首查：两个都 miss → 2 次远程请求
    got = kpf.get_prices(db, [hist, latest])
    assert got[(hist["code"], hist["at"])]["price"] == 10.0
    assert len(calls) == 2
    # 二查：历史价 + TTL 内最新价都命中缓存 → 0 次远程
    calls.clear()
    got2 = kpf.get_prices(db, [hist, latest])
    assert got2[(hist["code"], hist["at"])]["price"] == 10.0
    assert calls == []
    # 最新价过期（把 fetched_ts 拨回 10 分钟前）：只重查最新价
    db._execute("UPDATE kol_price_cache SET fetched_ts = ? WHERE at = ''",
                (__import__("time").time() - 600,))
    calls.clear()
    kpf.get_prices(db, [hist, latest])
    assert calls == [latest]


def test_stale_latest_price_not_served_after_ttl(monkeypatch):
    """最新价过期且重查失败：不回退过期缓存值（陈旧现价会污染浮动盈亏）。"""
    client = make_client()
    db = client.app.state.db
    t = _today()
    latest = {"code": "sh600519", "at": ""}
    calls: list[dict] = []

    def fetch_ok(requests):
        calls.extend(requests)
        return {(r["code"], r["at"]): {"price": 10.0, "actual_at": "", "name": ""}
                for r in requests}

    monkeypatch.setattr(kpf, "fetch_remote", fetch_ok)
    assert kpf.get_prices(db, [latest])[(latest["code"], "")]["price"] == 10.0
    # 过期 + 远程挂了：不回退 10.0 旧值，按查不到处理
    db._execute("UPDATE kol_price_cache SET fetched_ts = ? WHERE at = ''",
                (__import__("time").time() - 600,))
    monkeypatch.setattr(kpf, "fetch_remote", lambda reqs: {})
    calls.clear()
    got = kpf.get_prices(db, [latest])
    assert ("sh600519", "") not in got
    # 过期 + 远程返回新价：正常更新（丢弃逻辑不能误伤成功项）
    db._execute("UPDATE kol_price_cache SET fetched_ts = ? WHERE at = ''",
                (__import__("time").time() - 600,))
    monkeypatch.setattr(kpf, "fetch_remote", lambda reqs: {
        (r["code"], r["at"]): {"price": 12.0, "actual_at": "", "name": ""} for r in reqs})
    got = kpf.get_prices(db, [latest])
    assert got[("sh600519", "")]["price"] == 12.0


def test_resolve_codes_normalizes_input(monkeypatch):
    """名称归一：带空格/全角字母的名称与词表同口径匹配。

    真实词表（name_to_symbol）的键构建时走 _normalize_name（去空格+全角转半角），
    查询侧同口径归一后「Ａ 公司」/「A公司」都能命中（旧实现只 strip 永远查不到）。
    """
    monkeypatch.setattr(kpf, "name_to_symbol", lambda: {"贵州茅台": "sh600519", "A公司": "sz000001"})
    out = kpf.resolve_codes(["贵州茅台", " 贵州茅台 ", "不存在的票"])
    assert out == {"贵州茅台": "sh600519"}
    # 返回键为归一后名称（code_map 消费方同口径）
    assert kpf.resolve_codes(["Ａ 公司"]) == {"A公司": "sz000001"}
    assert kpf.resolve_codes(["A公司"]) == {"A公司": "sz000001"}


def test_price_api_config_load(monkeypatch):
    """配置 → (base, token)：环境变量注入；半套配置按桩模式处理。

    fetch_remote 的请求 URL/头由该函数决定，桩掉它即等价于断言 fetch_remote
    不发请求（不依赖 httpx mock）。
    """
    from app.config import Config

    # 未配置：两者皆空
    monkeypatch.delenv("PRICE_API_BASE", raising=False)
    monkeypatch.delenv("PRICE_API_TOKEN", raising=False)
    monkeypatch.setattr("app.config.load_config", lambda *a, **k: Config())
    assert kpf._load_price_api_config() == ("", "")
    # 半套配置（只有 base 或只有 token）：视为未配置
    cfg = Config()
    cfg.price_api_base = "http://127.0.0.1:3018/api/v1/"
    monkeypatch.setattr("app.config.load_config", lambda *a, **k: cfg)
    assert kpf._load_price_api_config() == ("", "")
    cfg = Config()
    cfg.price_api_token = "tok"
    monkeypatch.setattr("app.config.load_config", lambda *a, **k: cfg)
    assert kpf._load_price_api_config() == ("", "")
    # 成套配置：base 去尾部斜杠
    cfg = Config()
    cfg.price_api_base = "http://host.docker.internal:3018/api/v1/"
    cfg.price_api_token = "tok"
    monkeypatch.setattr("app.config.load_config", lambda *a, **k: cfg)
    assert kpf._load_price_api_config() == ("http://host.docker.internal:3018/api/v1", "tok")
    # 配置读取异常：按桩处理，不抛
    def boom(*a, **k):
        raise RuntimeError("config broken")
    monkeypatch.setattr("app.config.load_config", boom)
    assert kpf._load_price_api_config() == ("", "")


def test_fetch_remote_omits_empty_at(monkeypatch):
    """契约细节：最新价 item 只发 code，不发空串 at（实测空串被服务端 400 整批拒）。

    用桩 httpx.Client 捕获实际请求体断言，不发真实网络请求。
    """
    import httpx

    monkeypatch.setattr(kpf, "_load_price_api_config",
                        lambda: ("http://tickflow.local/api/v1", "tok"))
    captured: list[dict] = []

    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"items": [
                {"code": "sh600519", "status": "ok", "price": 10.0,
                 "actual_at": "", "name": "贵州茅台"},
                {"code": "sz300750", "status": "ok", "price": 20.0,
                 "actual_at": "", "name": "宁德时代"},
            ]}

    class _Client:
        def __init__(self, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def post(self, url, json=None, headers=None):
            captured.append({"url": url, "json": json, "headers": headers})
            return _Resp()

    monkeypatch.setattr(kpf.httpx, "Client", _Client)
    out = kpf.fetch_remote([
        {"code": "sh600519", "at": "2026-09-15T09:16:00"},
        {"code": "sz300750", "at": ""},   # 最新价：at 应整体省略
    ])
    body = captured[0]["json"]
    assert body["items"][0] == {"code": "sh600519", "at": "2026-09-15T09:16:00"}
    assert body["items"][1] == {"code": "sz300750"}          # 不含空串 at
    assert "at" not in body["items"][1]
    assert captured[0]["url"] == "http://tickflow.local/api/v1/prices"
    assert captured[0]["headers"] == {"Authorization": "Bearer tok"}
    assert out[("sz300750", "")]["price"] == 20.0            # 响应无 at 也能对齐键


def test_api_endpoint_contract(monkeypatch):
    """端点：正常结构 + 空态 available=false + 401/400/404/days 钳位。"""
    _patch_codes(monkeypatch)
    # 桩模式（真实链路走 fetch_remote，price_api 配置为空）：
    # 显式桩掉配置读取，避免本机 config.yaml / 环境变量让测试打到真实行情源
    monkeypatch.setattr(kpf, "_load_price_api_config", lambda: ("", ""))
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "盈亏大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
    ])
    # 桩模式（price_api 配置为空 → fetch_remote 不发请求）
    resp = client.get(f"/api/kols/{kol}/mx-pnl", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["kol"]["name"] == "盈亏大V"
    assert data["window_days"] == 30 and "summary" in data and "stocks" in data
    # 空态大V：窗口内无观点 → 无价格请求 → 不算「行情未接入」
    kol2 = db.add_kol("mx", "空盈亏大V", "room2")
    empty = client.get(f"/api/kols/{kol2}/mx-pnl", headers=headers).json()
    assert empty["available"] is True and empty["stocks"] == []
    # 非法输入
    kol3 = db.add_kol("weibo", "微博盈亏", "w1")
    assert client.get(f"/api/kols/{kol3}/mx-pnl", headers=headers).status_code == 400
    assert client.get("/api/kols/99999/mx-pnl", headers=headers).status_code == 404
    clamped = client.get(f"/api/kols/{kol}/mx-pnl?days=365", headers=headers).json()
    assert clamped["window_days"] == 90
    assert client.get(f"/api/kols/{kol}/mx-pnl").status_code == 401


def test_holdings_timeline_has_delta():
    """契约：build_kol_holdings 时间线事件带 delta（盈亏台账的输入）。"""
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "delta大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "贵州茅台", "bull", "清仓"),
    ])
    from app.mx_kol_holdings import build_kol_holdings
    out = build_kol_holdings(db, kol)
    by_kind = {e["kind"]: e["delta"] for e in out["timeline"]}
    assert by_kind["open"] == 3.0     # 建仓 +3
    assert by_kind["clear"] == -3.0   # 清仓 -全部
