"""MX 大V预估盈亏：操作时间线（actions）契约与边界测试。

actions 逐笔记录 {kind, at}，kind 按台账影子份额分类：
- 买入无底仓=建仓(open)、有底仓=加仓(add)；
- 卖出吃光影子份额=清仓(clear)、部分=减仓(trim)；翻空(flip)单列；
- 行情缺价的事件也照记（操作是事实），降级行同样带 actions。
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


def _lookup_factory(table: dict):
    """价格桩：table 为 {(code, at): price}，at 已按契约归一（T 分隔含秒）。"""
    def lookup(db, requests):
        out = {}
        for r in requests or []:
            key = (r["code"], kpf._normalize_at(r["at"]))
            if key in table:
                out[key] = {"price": table[key], "actual_at": key[1], "name": ""}
        return out
    return lookup


_NAME_CODES = {"贵州茅台": "sh600519", "中科曙光": "sh603019"}


def _patch_codes(monkeypatch):
    monkeypatch.setattr(kpf, "name_to_symbol", lambda: _NAME_CODES)


def _kinds(row: dict) -> list[str]:
    return [a["kind"] for a in row["actions"]]


def _ats(row: dict) -> list[str]:
    return [a["at"] for a in row["actions"]]


def test_actions_full_cycle_kinds_and_times(monkeypatch):
    """建仓→加仓→减仓→清仓全流程：四笔 kind 依次 open/add/trim/clear，时间逐笔对上。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "操作时间大V", "room1")
    t = _today()
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
    row = out["stocks"][0]
    assert _kinds(row) == ["open", "add", "trim", "clear"]
    assert _ats(row) == [f"{t} 09:16:00", f"{t} 10:15:00",
                         f"{t} 13:26:00", f"{t} 14:26:00"]


def test_actions_first_add_word_classified_open(monkeypatch):
    """首条即「加仓」词：无先前头寸，归建仓（open）而非加仓。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "首加仓大V", "room1")
    t = _today()
    # 首条加仓（delta=2 但 kind=hold）；次条再加仓（真加仓 add）
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "加仓"),
        (t, "10:20", "10:15", "stock", "贵州茅台", "bull", "加仓"),
    ])
    px = {
        ("sh600519", f"{t}T09:16:00"): 10.0,
        ("sh600519", f"{t}T10:15:00"): 11.0,
        ("sh600519", ""): 12.0,
    }
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    row = out["stocks"][0]
    assert _kinds(row) == ["open", "add"]


def test_actions_flip_and_partial_trim_kept(monkeypatch):
    """翻空出 flip；减仓两笔只打掉部分份额仍是 trim（未吃光即不清仓）。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "翻空大V", "room1")
    t = _today()
    # 建仓 3 → 减 2（trim，余 1）→ 翻空 -2 钳到 -1 吃光（flip 优先于 clear 语义）
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "贵州茅台", "bull", "减仓"),
        (t, "11:20", "11:15", "stock", "贵州茅台", "bear", ""),
    ])
    px = {
        ("sh600519", f"{t}T09:16:00"): 10.0,
        ("sh600519", f"{t}T10:15:00"): 11.0,
        ("sh600519", f"{t}T11:15:00"): 12.0,
    }
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    row = out["stocks"][0]
    assert _kinds(row) == ["open", "trim", "flip"]


def test_actions_recorded_even_when_price_missing(monkeypatch):
    """缺价事件照记操作时间：降级行（行情不全）也带完整 actions。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "缺价大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "贵州茅台", "bull", "加仓"),  # 这笔缺价
        (t, "11:20", "11:15", "stock", "贵州茅台", "bull", "减仓"),
    ])
    px = {
        ("sh600519", f"{t}T09:16:00"): 10.0,
        ("sh600519", f"{t}T11:15:00"): 12.0,
    }
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    row = out["stocks"][0]
    assert row["events_priced"] == 2 and row["events_total"] == 3  # 降级行
    assert "缺行情" in row["exit_note"]
    # 缺价的加仓仍如实记录（kind 按影子份额分类，不吃价格缺失）
    assert _kinds(row) == ["open", "add", "trim"]
    assert _ats(row)[1] == f"{t} 10:15:00"


def test_actions_absent_for_stance_only_stock(monkeypatch):
    """全程只有表态无操作：不进盈亏名单（无 actions 概念）。"""
    _patch_codes(monkeypatch)
    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "表态大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", ""),
    ])
    # 看多首提 delta=1（观察性建仓）：有操作时间线，kind=open
    px = {("sh600519", f"{t}T09:16:00"): 10.0, ("sh600519", ""): 11.0}
    out = mp.build_kol_pnl(db, kol, price_lookup=_lookup_factory(px))
    row = out["stocks"][0]
    assert _kinds(row) == ["open"]
    # 题材观点不进 stocks（无价格概念），不存在 actions
    kol2 = db.add_kol("mx", "题材大V", "room2")
    _seed_opinions(db, kol2, [
        (t, "09:20", "09:16", "topic", "AI算力", "bull", ""),
    ])
    topic_out = mp.build_kol_pnl(db, kol2, price_lookup=_lookup_factory(px))
    assert topic_out["stocks"] == []


def test_actions_endpoint_payload(monkeypatch):
    """端点载荷带 actions：JSON 可序列化、结构 {kind, at}。"""
    _patch_codes(monkeypatch)
    client = make_client()
    headers = auth_headers(client)
    db = client.app.state.db
    kol = db.add_kol("mx", "端点大V", "room1")
    t = _today()
    _seed_opinions(db, kol, [
        (t, "09:20", "09:16", "stock", "贵州茅台", "bull", "建仓"),
        (t, "10:20", "10:15", "stock", "贵州茅台", "bear", "清仓"),
    ])
    # 桩模式（无行情配置）：available=false 但 stocks 仍逐票回放，actions 仍带
    monkeypatch.setattr(kpf, "_load_price_api_config", lambda: ("", ""))
    resp = client.get(f"/api/kols/{kol}/mx-pnl", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    if data["stocks"]:
        for s in data["stocks"]:
            assert isinstance(s.get("actions"), list)
            for a in s["actions"]:
                assert set(a) == {"kind", "at"}
