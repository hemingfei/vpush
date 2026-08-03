import json
from pathlib import Path

import httpx

from app.config import XueqiuConfig
from app.db import DB
from app.fetchers.xueqiu import XueqiuFetcher

FIXTURES = Path(__file__).parent / "fixtures"


def test_xueqiu_parse_fixture():
    payload = json.loads((FIXTURES / "xueqiu_sample.json").read_text(encoding="utf-8"))

    def handler(request):
        assert request.headers.get("Cookie", "").startswith("xq_a_token=")
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = XueqiuFetcher(XueqiuConfig(cookie="xq_a_token=abc"), db=DB(":memory:"), client=client)
    posts = fetcher.fetch({"id": 1, "name": "大V", "external_id": "123"})
    assert len(posts) == 2
    assert posts[0].external_id == "101"
    assert posts[0].url == "https://xueqiu.com/101"
    assert "大涨" in posts[0].content
    assert "<strong>" not in posts[0].content
    assert posts[0].kol_name == "大V"


def test_xueqiu_cookie_refresh_on_401():
    fixture = json.loads((FIXTURES / "xueqiu_sample.json").read_text(encoding="utf-8"))
    timeline_hits = {"n": 0}

    def handler(request):
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"set-cookie": "xq_a_token=newtoken; Path=/; Domain=.xueqiu.com"},
            )
        timeline_hits["n"] += 1
        if timeline_hits["n"] == 1:
            return httpx.Response(401)
        assert request.headers.get("Cookie", "").startswith("xq_a_token=newtoken")
        return httpx.Response(200, json=fixture)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = DB(":memory:")
    fetcher = XueqiuFetcher(XueqiuConfig(cookie="xq_a_token=old"), db=db, client=client)
    posts = fetcher.fetch({"id": 1, "name": "大V", "external_id": "123"})
    assert len(posts) == 2
    assert "xq_a_token=newtoken" in db.get_setting("xueqiu_cookie")


from app.config import WeiboConfig
from app.fetchers.weibo import WeiboFetcher


def test_weibo_parse_fixture():
    payload = json.loads((FIXTURES / "weibo_sample.json").read_text(encoding="utf-8"))

    def handler(request):
        assert request.headers.get("Cookie", "").startswith("SUB=")
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = WeiboFetcher(WeiboConfig(cookie="SUB=xyz"), client=client)
    posts = fetcher.fetch({"id": 2, "name": "微博大V", "external_id": "1234567890"})
    assert len(posts) == 1
    assert posts[0].external_id == "M1"
    assert posts[0].url == "https://m.weibo.cn/detail/M1"
    assert "行情" in posts[0].content


from app.fetchers.rss import RssFetcher


def test_rss_parse_fixture():
    content = (FIXTURES / "rss_sample.xml").read_bytes()

    def handler(request):
        return httpx.Response(200, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = RssFetcher(client=client)
    posts = fetcher.fetch({"id": 3, "name": "X大V", "external_id": "https://rss.example/feed"})
    assert len(posts) == 1
    assert posts[0].external_id == "1"
    assert posts[0].url == "https://x.com/status/1"
    assert "world" in posts[0].content
