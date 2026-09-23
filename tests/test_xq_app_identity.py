"""雪球 App 身份通道（隐式账号 + api.xueqiu.com）的离线用例。

conftest 默认关闭该通道；这里显式打开并 stub `xq_identity.identity`，全程不发真实请求。
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app import xq_identity
from app.config import XueqiuConfig
from app.db import DB
from app.fetchers.combination import CUBE_QUOTE_URL, CombinationFetcher, REBALANCING_URL
from app.fetchers.xueqiu import (
    XUEQIU_TIMELINE_URL,
    XueqiuFetcher,
)

FIXTURES = Path(__file__).parent / "fixtures"
APP_COOKIE = "xq_a_token=app-token; u=2431759417"


@pytest.fixture
def app_identity(monkeypatch):
    """打开 App 通道并 stub 隐式账号（返回当前 token 的 getter）。"""
    monkeypatch.setenv("XUEQIU_APP_IDENTITY", "1")
    state = {"cookie": APP_COOKIE}

    def identity() -> dict:
        return {"cookie": state["cookie"], "device_id": "MAC", "user_id": 2431759417}

    def rotate_identity() -> dict:
        state["cookie"] = "xq_a_token=rotated; u=2431759417"
        return identity()

    monkeypatch.setattr(xq_identity, "identity", identity)
    monkeypatch.setattr(xq_identity, "rotate_identity", rotate_identity)
    return state


def _timeline_client(seen: list[httpx.Request], payload: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_timeline_uses_app_domain_and_token(app_identity):
    """社区帖子改走 api.xueqiu.com/v4/statuses/*，且 UA 与 token 成对。"""
    payload = json.loads((FIXTURES / "xueqiu_sample.json").read_text(encoding="utf-8"))
    seen: list[httpx.Request] = []
    fetcher = XueqiuFetcher(
        XueqiuConfig(cookie="xq_a_token=web-token"),
        db=DB(":memory:"),
        client=_timeline_client(seen, payload),
    )

    posts = fetcher.fetch({"id": 1, "name": "大V", "external_id": "123"})

    assert posts
    assert {r.url.host for r in seen} == {"api.xueqiu.com"}  # 不碰 xueqiu.com 挑战域
    first = seen[0]
    assert first.url.path == "/v4/statuses/user_timeline.json"
    assert first.headers["User-Agent"] == xq_identity.APP_UA
    assert first.headers["Cookie"].startswith("xq_a_token=app-token")


def test_expired_app_token_rotates_and_retries(app_identity):
    """App token 失效（401）→ 换设备指纹重注册一次后重打，不需要人工介入。"""
    payload = json.loads((FIXTURES / "xueqiu_sample.json").read_text(encoding="utf-8"))
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "app-token" in request.headers.get("Cookie", ""):
            return httpx.Response(401, json={"error_code": "10022"}, request=request)
        return httpx.Response(200, json=payload, request=request)

    fetcher = XueqiuFetcher(
        XueqiuConfig(cookie=""),
        db=DB(":memory:"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    posts = fetcher.fetch({"id": 1, "name": "大V", "external_id": "123"})

    assert posts
    assert "xq_a_token=app-token" in seen[0].headers["Cookie"]
    assert "xq_a_token=rotated" in seen[1].headers["Cookie"]
    assert all(r.url.host == "api.xueqiu.com" for r in seen)


def test_register_failure_raises_without_web_fallback(monkeypatch, app_identity):
    """注册失败不再静默退回网页 cookie（该通道已随 waf-bot 下线）：直接抛出由调度器退避。

    这里刻意保留一个 DB 里的旧 cookie，验证它不会被拿来兜底 —— 否则会制造「有兜底」的错觉，
    而那条路径在本服务出口 IP 上已被 400016/110017 拦截。
    """
    monkeypatch.setattr(
        xq_identity, "identity", lambda: (_ for _ in ()).throw(RuntimeError("网络不可达"))
    )
    payload = json.loads((FIXTURES / "xueqiu_sample.json").read_text(encoding="utf-8"))
    seen: list[httpx.Request] = []
    fetcher = XueqiuFetcher(
        XueqiuConfig(cookie="xq_a_token=web-token"),
        db=DB(":memory:"),
        client=_timeline_client(seen, payload),
    )

    with pytest.raises(RuntimeError):
        fetcher.fetch({"id": 1, "name": "大V", "external_id": "123"})

    assert seen == []  # 没有退回任何请求
    assert XUEQIU_TIMELINE_URL.startswith("https://api.xueqiu.com/")


def test_cube_skips_homepage_warm_with_app_token(app_identity):
    """组合调仓用 App token 后不再预热首页（EdgeOne 挑战只在网页 cookie 路径出现）。"""
    calls: list[str] = []

    class Fake:
        impersonate = "chrome124"

        def __init__(self):
            self.headers: dict = {}
            self.cookies = httpx.Cookies()

        def get(self, url, params=None, headers=None):
            calls.append(url)
            request = httpx.Request("GET", url)
            if "history.json" in url:
                return httpx.Response(200, json={"list": []}, request=request)
            return httpx.Response(200, json={}, request=request)

    fetcher = CombinationFetcher(
        XueqiuConfig(cookie="xq_a_token=web-token"), db=DB(":memory:"), client=Fake()
    )

    fetcher.fetch({"id": 1, "name": "伯言-A股", "external_id": "ZH3623878"})

    # 网页域的 cube 接口对本服务出口 IP 直接 400016（实测），必须改打 api 域
    assert REBALANCING_URL.startswith("https://api.xueqiu.com/")
    assert REBALANCING_URL in calls
    assert not any(url.startswith("https://xueqiu.com/") for url in calls)  # App 身份不预热首页
    assert fetcher.client.cookies["xq_a_token"] == "app-token"
    assert fetcher.client.headers["User-Agent"] == xq_identity.APP_UA


def test_cube_snapshot_uses_api_host_without_app_identity():
    """没有 App 身份（回滚开关）时组合快照也走 api 域 —— 限流是出口 IP 打网页域造成的。"""
    calls: list[str] = []

    class Fake:
        impersonate = "chrome124"

        def __init__(self):
            self.headers: dict = {}
            self.cookies = httpx.Cookies()

        def get(self, url, params=None, headers=None):
            calls.append(url)
            return httpx.Response(200, json={}, request=httpx.Request("GET", url))

    fetcher = CombinationFetcher(
        XueqiuConfig(cookie="xq_a_token=web-token"), db=DB(":memory:"), client=Fake()
    )

    fetcher._snapshot(1, "ZH2223199", "nav", CUBE_QUOTE_URL, {"cube_symbol": "ZH2223199"}, force=True)

    # cube 走 api 域（首页预热仍打网页域，不在此断言范围内）
    assert [u for u in calls if "cubes" in u] == [CUBE_QUOTE_URL]
