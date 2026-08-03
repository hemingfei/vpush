import json
from pathlib import Path

import httpx

from app.config import XueqiuConfig
from app.fetchers.xueqiu import XueqiuFetcher

FIXTURES = Path(__file__).parent / "fixtures"


def test_xueqiu_parse_fixture():
    payload = json.loads((FIXTURES / "xueqiu_sample.json").read_text(encoding="utf-8"))

    def handler(request):
        assert request.headers.get("Cookie", "").startswith("xq_a_token=")
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = XueqiuFetcher(XueqiuConfig(cookie="xq_a_token=abc"), client=client)
    posts = fetcher.fetch({"id": 1, "name": "大V", "external_id": "123"})
    assert len(posts) == 2
    assert posts[0].external_id == "101"
    assert posts[0].url == "https://xueqiu.com/101"
    assert "大涨" in posts[0].content
    assert "<strong>" not in posts[0].content
    assert posts[0].kol_name == "大V"
