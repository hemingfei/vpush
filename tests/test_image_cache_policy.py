"""图片直连（不缓存）策略：名单匹配、采集侧跳过、补缓存跳过、管理端点。"""
import json

import httpx
import pytest

from app.avatar_cache import (
    DEFAULT_DIRECT_HOSTS,
    direct_access_hosts,
    normalize_direct_hosts,
    should_direct_access,
)
from app.db import DB
from app.image_backfill import backfill_external_images


def make_db(tmp_path) -> DB:
    return DB(tmp_path / "t.db")


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """MockTransport 的测试域名不真实解析：统一解析到公网 IP，不触发真实 DNS。"""
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])


def test_normalize_direct_hosts():
    assert normalize_direct_hosts(
        [" Static.DingTalk.com. ", "", "a.example.com", "static.dingtalk.com"]
    ) == ["static.dingtalk.com", "a.example.com"]  # 小写/去尾点/去空/去重保序
    with pytest.raises(ValueError):
        normalize_direct_hosts(["not a domain"])
    with pytest.raises(ValueError):
        normalize_direct_hosts(["https://x.example.com"])  # 只收裸域名
    with pytest.raises(ValueError):
        normalize_direct_hosts(["localhost"])  # 必须带 TLD


def test_should_direct_access_default_and_matching(tmp_path):
    db = make_db(tmp_path)
    # 默认名单含钉钉 CDN
    assert direct_access_hosts(db) == ["static.dingtalk.com"]
    assert should_direct_access(db, "https://static.dingtalk.com/media/a.png?bizType=im")
    # 精确 host 与子域名都命中，别的域名不命中
    assert not should_direct_access(db, "https://dingtalk.com/a.png")
    assert not should_direct_access(db, "https://static.dingtalk.com.evil.com/a.png")
    db.set_setting("image_direct_hosts", "dingtalk.com")
    assert should_direct_access(db, "https://img.dingtalk.com/a.png")  # 子域名命中
    # 非法/空 URL 不命中
    assert not should_direct_access(db, "")
    assert not should_direct_access(db, "/mx-images/abc.jpg")


# ---- 采集侧：MX ----

def _mx_fetcher(tmp_path):
    from types import SimpleNamespace

    from app.fetchers.mx.fetcher import MxFetcher

    db = DB(tmp_path / "mx.db")
    config = SimpleNamespace(
        api_base="https://mx.test/business-api/5",
        token="t",
        page_size=50,
        max_history_pages=5,
        ws_enabled=False,
    )
    return db, MxFetcher(config, db)


def test_mx_pic_message_direct_host_keeps_external(tmp_path, monkeypatch):
    """直连名单内的 pic 消息：保留外链、不触发下载；名单外正常走缓存。"""
    db, fetcher = _mx_fetcher(tmp_path)
    kid = db.add_kol("mx", "房间A", "101")
    kol = db.get_kol(kid)
    calls = []

    def fake_cache(db_, url, folder, prefix, client=None):
        calls.append(url)
        return f"{prefix}/cached.jpg"

    monkeypatch.setattr("app.fetchers.mx.fetcher.cache_image_file", fake_cache)
    pic = lambda url: json.dumps([{"type": "pic", "url": url}])  # noqa: E731

    post = fetcher._parse_message_to_post(
        {"id": 1, "rid": 101, "msg": pic("https://static.dingtalk.com/media/a.png"), "createtime": 1700000000000},
        kol,
    )
    assert post.images == ["https://static.dingtalk.com/media/a.png"]  # 保留外链
    assert calls == []  # 未尝试下载

    post2 = fetcher._parse_message_to_post(
        {"id": 2, "rid": 101, "msg": pic("https://img.example.com/b.png"), "createtime": 1700000000001},
        kol,
    )
    assert post2.images == ["/mx-images/cached.jpg"]  # 名单外照常缓存
    assert calls == ["https://img.example.com/b.png"]


# ---- 补缓存 ----

def test_backfill_skips_direct_hosts(tmp_path):
    """补缓存跳过直连域名；名单清空后同一条目恢复正常补缓存。"""
    db = make_db(tmp_path)
    kid = db.add_kol("mx", "房间A", "101")
    url = "https://static.dingtalk.com/media/backfill.png"
    db.insert_post("mx", kid, "m1", "", "正文", "", "2026-09-01 10:00:00", images=[url])

    stats = backfill_external_images(db, now=1000.0)
    assert stats["images_skipped"] == 1
    assert stats["images_ok"] == 0
    assert json.loads(
        db._rows("SELECT images FROM posts WHERE external_id='m1'")[0]["images"]
    ) == [url]  # 外链原样保留

    # 名单清空（显式覆盖默认名单）：恢复补缓存
    db.set_setting("image_direct_hosts", "")
    def handler(request):
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG" * 600)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    stats = backfill_external_images(db, client=client, now=1000.0)
    assert stats["images_ok"] == 1


# ---- 管理端点 ----

def test_api_image_policy_endpoints():
    from test_api import auth_headers, make_client, user_headers

    client = make_client("imgpolicy.db")
    admin = auth_headers(client)
    user = user_headers(client, "policyuser1")

    assert client.get("/api/admin/images/policy", headers=user).status_code == 403
    got = client.get("/api/admin/images/policy", headers=admin)
    assert got.status_code == 200
    assert got.json()["direct_hosts"] == ["static.dingtalk.com"]  # 默认名单

    saved = client.put(
        "/api/admin/images/policy",
        json={"direct_hosts": ["Static.DingTalk.com.", "pic.guhai888.cn", "pic.guhai888.cn"]},
        headers=admin,
    )
    assert saved.status_code == 200
    assert saved.json()["direct_hosts"] == ["static.dingtalk.com", "pic.guhai888.cn"]
    assert client.get("/api/admin/images/policy", headers=admin).json()[
        "direct_hosts"
    ] == ["static.dingtalk.com", "pic.guhai888.cn"]

    bad = client.put(
        "/api/admin/images/policy",
        json={"direct_hosts": ["not a domain"]},
        headers=admin,
    )
    assert bad.status_code == 400

    # 空名单可保存：显式覆盖默认名单
    empty = client.put("/api/admin/images/policy", json={"direct_hosts": []}, headers=admin)
    assert empty.status_code == 200
    assert client.get("/api/admin/images/policy", headers=admin).json()["direct_hosts"] == []
