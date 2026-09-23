"""探测式轮询（方案 A）的单元测试。

覆盖：命中跳过、未命中全量、探测异常退回、强制全量、开关关闭。
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import XueqiuConfig
from app.db import DB
from app.fetchers import xueqiu as xq

FIXTURES = Path(__file__).parent / "fixtures"
PAYLOAD = json.loads((FIXTURES / "xueqiu_sample.json").read_text(encoding="utf-8"))
WEB_URL = "https://xueqiu.com/statuses/user_timeline.json"
KOL = {"id": 1, "name": "大V", "external_id": "123"}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """隔离身份解析与跳过计数，让每个用例互不影响，且不发真实网络请求。"""
    monkeypatch.setattr(
        xq,
        "resolve_xueqiu_identity",
        lambda db, cookie: (cookie or "xq_a_token=abc", "UA", WEB_URL, False),
    )
    monkeypatch.setattr(xq, "_probe_skip_streak", {})
    monkeypatch.setattr(xq, "XUEQIU_PROBE_ENABLED", True)


def _fetcher(handler, db=None):
    return xq.XueqiuFetcher(
        XueqiuConfig(cookie="xq_a_token=abc"),
        db=db or DB(":memory:"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _seed_latest(db: DB, external_id: str) -> None:
    """把某帖标记为已入库，模拟「上一轮已经拉过它」。"""
    db.insert_post("xueqiu", 1, external_id, "t", "c", "https://xueqiu.com/x", "2026-09-01 00:00")


def test_probe_hit_skips_full_fetch():
    """最新帖已入库 → 只发 1 次 count=1 探测，跳过全量。"""
    calls: list[dict] = []

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={"statuses": PAYLOAD["statuses"][:1]})

    db = DB(":memory:")
    _seed_latest(db, "101")                     # 探测会看到 id=101，且它已在库
    posts = _fetcher(handler, db).fetch(KOL)

    assert posts == []                          # 无新帖
    assert len(calls) == 1, calls               # 没有触发全量
    assert calls[0]["count"] == "1"
    assert calls[0]["page"] == "1"


def test_probe_miss_falls_through_to_full_fetch():
    """最新帖未入库 → 照常全量拉取。"""
    calls: list[dict] = []

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=PAYLOAD)

    fetcher = _fetcher(handler)                 # 空库：探测必然未命中
    posts = fetcher.fetch(KOL)

    assert [p.external_id for p in posts] == ["101", "102"]
    assert calls[0]["count"] == "1"             # 先探测
    assert any(c["count"] == "20" for c in calls), calls   # 再全量


def test_probe_error_falls_back_to_full_fetch():
    """探测请求报错 → 退回全量，绝不因探测失败而漏帖。"""
    calls: list[dict] = []

    def handler(request):
        count = request.url.params.get("count")
        calls.append({"count": count})
        if count == "1":
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=PAYLOAD)

    posts = _fetcher(handler).fetch(KOL)

    assert [p.external_id for p in posts] == ["101", "102"]
    assert any(c["count"] == "20" for c in calls)


def test_forced_full_fetch_after_skip_streak(monkeypatch):
    """连续跳过到上限 → 强制全量一次，兜住探测长期返回陈旧数据。"""
    monkeypatch.setattr(xq, "XUEQIU_PROBE_FORCE_FULL_EVERY", 3)
    counts: list[str] = []

    def handler(request):
        counts.append(request.url.params.get("count"))
        return httpx.Response(200, json={"statuses": PAYLOAD["statuses"][:1]})

    db = DB(":memory:")
    _seed_latest(db, "101")
    fetcher = _fetcher(handler, db)

    for _ in range(3):                          # 前 3 轮都命中探测 → 跳过
        fetcher.fetch(KOL)
    assert counts.count("1") == 3 and "20" not in counts, counts

    counts.clear()
    fetcher.fetch(KOL)                          # 第 4 轮达到上限 → 强制全量
    assert "1" not in counts and counts.count("20") >= 1, counts


def test_probe_disabled_goes_straight_to_full(monkeypatch):
    """开关关闭 → 不探测，直接全量（回滚路径）。"""
    monkeypatch.setattr(xq, "XUEQIU_PROBE_ENABLED", False)
    counts: list[str] = []

    def handler(request):
        counts.append(request.url.params.get("count"))
        return httpx.Response(200, json=PAYLOAD)

    db = DB(":memory:")
    _seed_latest(db, "101")
    posts = _fetcher(handler, db).fetch(KOL)

    assert "1" not in counts and "20" in counts       # 没有探测请求
    assert [p.external_id for p in posts] == ["101", "102"]
