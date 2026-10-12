import httpx
import pytest

from app.avatar_cache import cache_avatar, cache_image_file
from app.db import DB


def make_db(tmp_path) -> DB:
    return DB(tmp_path / "t.db")


def test_cache_avatar_downloads_once(tmp_path):
    db = make_db(tmp_path)
    kid = db.add_kol("weibo", "A", "1")
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            content=b"\xff\xd8\xff" * 20,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    url1 = cache_avatar(db, kid, "https://img.example/a.jpg", client=client)
    assert url1 == f"/avatars/{kid}.jpg"
    assert (tmp_path / "avatars" / f"{kid}.jpg").exists()
    assert db.get_kol(kid)["avatar_url"] == url1
    assert db.get_kol(kid)["avatar_source"] == "https://img.example/a.jpg"

    # 同一来源再次调用：命中本地缓存，不再下载
    url2 = cache_avatar(db, kid, "https://img.example/a.jpg", client=client)
    assert url2 == url1
    assert hits["n"] == 1

    # 本地文件丢了：必须重新下载，不能只信 DB 路径
    (tmp_path / "avatars" / f"{kid}.jpg").unlink()
    url3 = cache_avatar(db, kid, "https://img.example/a.jpg", client=client)
    assert url3 == url1
    assert (tmp_path / "avatars" / f"{kid}.jpg").exists()
    assert hits["n"] == 2


def test_cache_avatar_rejects_non_image_and_failure(tmp_path):
    db = make_db(tmp_path)
    kid = db.add_kol("twitter", "B", "2")

    def handler(request):
        if request.url.path == "/bad":
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")
        if request.url.path == "/fail":
            return httpx.Response(403)
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG" * 10)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert cache_avatar(db, kid, "https://img.example/bad", client=client) == "https://img.example/bad"
    assert cache_avatar(db, kid, "https://img.example/fail", client=client) == "https://img.example/fail"
    assert (tmp_path / "avatars").exists() is False or not list((tmp_path / "avatars").glob(f"{kid}.*"))


def test_cache_avatar_keeps_local_url(tmp_path):
    db = make_db(tmp_path)
    kid = db.add_kol("weibo", "C", "3")
    db.update_kol_avatar(kid, "/avatars/3.jpg")
    assert cache_avatar(db, kid, "/avatars/3.jpg") == "/avatars/3.jpg"


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """MockTransport 的测试域名不真实解析：统一解析到公网 IP，不触发真实 DNS。"""
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])


def test_cache_avatar_blocks_internal_url(tmp_path):
    """内网地址直接拒绝且不发请求，退回原 URL（不落盘）。"""
    from app import url_safety

    db = make_db(tmp_path)
    kid = db.add_kol("weibo", "D", "4")
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"x")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    url = "http://169.254.169.254/latest/meta-data/"
    assert url_safety.is_safe_http_url(url) is False
    assert cache_avatar(db, kid, url, client=client) == url
    assert requested == []


def test_headers_for_zsxq():
    from app.avatar_cache import headers_for
    assert headers_for("https://images.zsxq.com/abc")["Referer"] == "https://wx.zsxq.com/"
    assert headers_for("https://wx2.sinaimg.cn/x.jpg")["Referer"] == "https://weibo.com/"


def test_cache_image_file_distinguishes_html_from_failure(tmp_path):
    """200 且 content-type 非图片 → 返回 None（确认非图片，如网页链接卡片）；
    下载失败等不确定情况仍返回原 URL，调用方据此决定是否降级。"""
    db = make_db(tmp_path)

    def handler(request):
        if request.url.path.startswith("/page"):
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")
        if request.url.path.startswith("/gone"):
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG" * 600)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert cache_image_file(db, "https://img.example/page/1", "mx_images", "/mx-images", client=client) is None
    assert cache_image_file(db, "https://img.example/gone", "mx_images", "/mx-images", client=client) == "https://img.example/gone"
    # 合法图片缓存需 > 2048 字节（过小按坏图退回原 URL）
    local = cache_image_file(db, "https://img.example/real.png", "mx_images", "/mx-images", client=client)
    assert local and local.startswith("/mx-images/")


# ---- MX 域名图片走 curl_cffi Chrome 人格 ----

class _FakeCffiResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


def test_mx_image_get_follows_same_domain_redirects_only(monkeypatch):
    """重定向只跟随 MX 域名：同域跳转照常跟，出域一律中止抛错。"""
    import app.avatar_cache as ac

    calls = []

    class FakeSession:
        def get(self, url, **kw):
            calls.append(url)
            if url.endswith("/a.png"):
                return _FakeCffiResponse(
                    302, headers={"location": "https://cdn.mx.2026.foodtop1.com/b.png"}
                )
            return _FakeCffiResponse(
                200, content=b"\x89PNG" * 10, headers={"content-type": "image/png"}
            )

    monkeypatch.setattr(ac, "_get_mx_image_session", lambda: FakeSession())
    resp = ac.mx_image_get("https://mx.2026.foodtop1.com/up/a.png")
    assert resp.status_code == 200
    assert calls == [
        "https://mx.2026.foodtop1.com/up/a.png",
        "https://cdn.mx.2026.foodtop1.com/b.png",
    ]

    class EvilSession:
        def get(self, url, **kw):
            return _FakeCffiResponse(302, headers={"location": "https://evil.example.com/c.png"})

    monkeypatch.setattr(ac, "_get_mx_image_session", lambda: EvilSession())
    with pytest.raises(ValueError):
        ac.mx_image_get("https://mx.2026.foodtop1.com/up/a.png")


def test_mx_image_get_redirect_budget(monkeypatch):
    """同域重定向超过 3 次也中止（首跳 + 3 跳上限）。"""
    import app.avatar_cache as ac

    class LoopSession:
        def get(self, url, **kw):
            return _FakeCffiResponse(302, headers={"location": url + "x"})

    monkeypatch.setattr(ac, "_get_mx_image_session", lambda: LoopSession())
    with pytest.raises(ValueError):
        ac.mx_image_get("https://mx.2026.foodtop1.com/a")


def test_cache_image_file_mx_domain_uses_cffi_persona(tmp_path, monkeypatch):
    """MX 域名 URL（不传 client）走 curl_cffi 人格下载并落盘；非 MX 域名不受影响。"""
    import app.avatar_cache as ac

    db = make_db(tmp_path)
    seen = {}

    def fake_mx_get(url, timeout=15):
        seen["url"] = url
        return _FakeCffiResponse(
            200, content=b"\x89PNG" * 600, headers={"content-type": "image/png"}
        )

    monkeypatch.setattr(ac, "mx_image_get", fake_mx_get)
    local = ac.cache_image_file(
        db, "https://mx.2026.foodtop1.com/Uploads/x.png", "mx_images", "/mx-images"
    )
    assert local and local.startswith("/mx-images/")
    assert seen["url"] == "https://mx.2026.foodtop1.com/Uploads/x.png"


def test_cache_avatar_mx_domain_uses_cffi_persona(tmp_path, monkeypatch):
    import app.avatar_cache as ac

    db = make_db(tmp_path)
    kid = db.add_kol("mx", "KOL", "9")

    def fake_mx_get(url, timeout=15):
        return _FakeCffiResponse(
            200, content=b"\xff\xd8\xff" * 40, headers={"content-type": "image/jpeg"}
        )

    monkeypatch.setattr(ac, "mx_image_get", fake_mx_get)
    url = ac.cache_avatar(db, kid, "https://mx.2026.naaifu.cn/avatar/9.jpg")
    assert url == f"/avatars/{kid}.jpg"
    assert (tmp_path / "avatars" / f"{kid}.jpg").exists()
