import hashlib

import httpx
import pytest

from app.config import ImgbedConfig
from app.db import DB
from app import imgbed


JPEG = b"\xff\xd8\xff" + b"x" * 3000
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 3000
SOURCE = "https://pbs.twimg.com/media/abc.jpg"
HOSTED = "https://img.053727.xyz/file/vpush/1.png"


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    monkeypatch.setattr("app.imgbed.is_safe_http_url", lambda url: True)


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")


@pytest.fixture
def cfg():
    return ImgbedConfig(
        base_url="https://img.053727.xyz",
        token="imgbed_testtoken",
        channel="telegram",
        channel_name="vpush-imgbed",
        folder="vpush",
    )


def test_enqueue_recent_posts_backfills_twitter_images(db, cfg):
    imgbed.configure(type("C", (), {"imgbed": cfg})())
    kid = db.add_kol("twitter", "A", "1")
    db.insert_post(
        "twitter", kid, "p1", "t", "c", "u", "",
        images=[SOURCE, "https://xqimg.imedao.com/a.png"],
    )
    assert imgbed.enqueue_recent_posts(db) == 1
    assert db.list_pending_hosted_images()[0]["source_url"] == SOURCE


def test_truth_images_enqueue_and_rewrite(db, cfg):
    imgbed.configure(type("C", (), {"imgbed": cfg})())
    truth_src = "https://static-assets-1.truthsocial.com/media/abc.png"
    truth_hosted = "https://img.053727.xyz/file/vpush/2.png"
    kid = db.add_kol("truth", "Donald J. Trump", "realDonaldTrump")
    db.insert_post("truth", kid, "p1", "t", "c", "u", "", images=[truth_src])
    assert imgbed.enqueue_recent_posts(db) == 1
    db.mark_hosted_image(truth_src, status="ready", hosted_url=truth_hosted)
    assert db.list_posts()[0]["images"] == [truth_hosted]


def test_apply_runtime_updates_public_host(db, cfg):
    imgbed.configure(type("C", (), {"imgbed": cfg})())
    imgbed.apply_runtime("https://img.example.net", "imgbed_other")
    assert imgbed.public_host() == "img.example.net"
    assert imgbed.public_url("https://img.example.net/file/a.jpg") is True
    assert imgbed.public_url("https://img.053727.xyz/file/a.jpg") is False


def test_enqueue_and_rewrite_without_config(db, monkeypatch):
    imgbed.configure(type("C", (), {"imgbed": ImgbedConfig()})())
    assert imgbed.enqueue_urls(db, [SOURCE]) == 0
    kid = db.add_kol("twitter", "A", "1")
    db.insert_post("twitter", kid, "p1", "t", "c", "u", "", images=[SOURCE])
    assert db.list_posts()[0]["images"] == [SOURCE]


def _client_factory(handler):
    return lambda **kwargs: httpx.Client(
        transport=httpx.MockTransport(handler),
        **{k: v for k, v in kwargs.items() if k != "transport"},
    )


def test_process_pending_uploads_and_rewrites_feed(db, cfg, monkeypatch):
    imgbed.configure(type("C", (), {"imgbed": cfg})())
    uploaded = {}
    prewarmed = []
    monkeypatch.setattr(imgbed, "_download", lambda url: (JPEG, "image/jpeg"))
    monkeypatch.setattr(imgbed, "_prewarm_hosted_async", lambda url: prewarmed.append(url))

    def handler(request: httpx.Request):
        uploaded["auth"] = request.headers.get("authorization")
        uploaded["folder"] = request.url.params.get("uploadFolder")
        uploaded["channel"] = request.url.params.get("channelName")
        return httpx.Response(200, json=[{"src": "/file/vpush/1.png"}])

    monkeypatch.setattr(imgbed, "_http_client", _client_factory(handler))
    assert imgbed.enqueue_urls(db, [SOURCE, "https://xqimg.imedao.com/a.png"]) == 1
    assert imgbed.process_pending(db, cfg) == 1
    assert uploaded["auth"] == "Bearer imgbed_testtoken"
    assert uploaded["folder"] == "vpush"
    assert uploaded["channel"] == "vpush-imgbed"
    assert prewarmed == [HOSTED]
    kid = db.add_kol("twitter", "A", "1")
    db.insert_post("twitter", kid, "p1", "t", "c", "u", "", images=[SOURCE])
    assert db.list_posts()[0]["images"] == [HOSTED]


def test_same_hash_reuses_hosted_url(db, cfg, monkeypatch):
    imgbed.configure(type("C", (), {"imgbed": cfg})())
    uploads = {"n": 0}
    monkeypatch.setattr(imgbed, "_download", lambda url: (JPEG, "image/jpeg"))
    monkeypatch.setattr(imgbed, "_prewarm_hosted_async", lambda url: None)

    def handler(request: httpx.Request):
        uploads["n"] += 1
        return httpx.Response(200, json=[{"src": "/file/vpush/1.png"}])

    monkeypatch.setattr(imgbed, "_http_client", _client_factory(handler))
    first = "https://pbs.twimg.com/media/one.jpg"
    second = "https://pbs.twimg.com/media/two.jpg"
    imgbed.enqueue_urls(db, [first, second])
    assert imgbed.process_pending(db, cfg, limit=8) == 2
    assert uploads["n"] == 1
    assert db.hosted_image_url(first) == HOSTED
    assert db.hosted_image_url(second) == HOSTED
    assert db.hosted_image_url_by_hash(hashlib.sha256(JPEG).hexdigest()) == HOSTED


def test_upload_failure_keeps_original_url(db, cfg, monkeypatch):
    imgbed.configure(type("C", (), {"imgbed": cfg})())
    monkeypatch.setattr(imgbed, "_download", lambda url: (JPEG, "image/jpeg"))

    def handler(request: httpx.Request):
        return httpx.Response(500, text="no")

    monkeypatch.setattr(imgbed, "_http_client", _client_factory(handler))
    imgbed.enqueue_urls(db, [SOURCE])
    assert imgbed.process_pending(db, cfg) == 0
    kid = db.add_kol("twitter", "A", "1")
    db.insert_post("twitter", kid, "p1", "t", "c", "u", "", images=[SOURCE])
    assert db.list_posts()[0]["images"] == [SOURCE]
    row = db._rows("SELECT status, last_error FROM hosted_images WHERE source_url = ?", (SOURCE,))[0]
    assert row["status"] == "failed"
    assert row["last_error"]


def test_purge_expired_hosted_images_uses_retention_days(db):
    old = SOURCE
    fresh = "https://pbs.twimg.com/media/fresh.jpg"
    db.enqueue_hosted_image(old)
    db.enqueue_hosted_image(fresh)
    db._conn.execute(
        "UPDATE hosted_images SET created_at = datetime('now', '-40 days') WHERE source_url = ?",
        (old,),
    )
    db._conn.commit()
    assert imgbed.purge_expired(db) == 1
    left = {row["source_url"] for row in db._rows("SELECT source_url FROM hosted_images")}
    assert left == {fresh}
    db.set_setting("imgbed_retention_days", "0")
    db._conn.execute(
        "UPDATE hosted_images SET created_at = datetime('now', '-40 days') WHERE source_url = ?",
        (fresh,),
    )
    db._conn.commit()
    assert imgbed.purge_expired(db) == 0
    assert db._rows("SELECT source_url FROM hosted_images")[0]["source_url"] == fresh


def _age_hosted(db, source_url, days=40):
    db._conn.execute(
        "UPDATE hosted_images SET created_at = datetime('now', ?) WHERE source_url = ?",
        (f"-{days} days", source_url),
    )
    db._conn.commit()


def test_purge_expired_deletes_remote_file(db, cfg, monkeypatch):
    imgbed.configure(type("C", (), {"imgbed": cfg})())
    db.enqueue_hosted_image(SOURCE)
    db.mark_hosted_image(SOURCE, status="ready", hosted_url=HOSTED)
    _age_hosted(db, SOURCE)
    deleted = []

    def handler(request: httpx.Request):
        deleted.append((request.method, str(request.url), request.headers.get("authorization")))
        return httpx.Response(200, json={"success": True, "fileId": "vpush/1.png"})

    monkeypatch.setattr(imgbed, "_http_client", _client_factory(handler))
    assert imgbed.purge_expired(db) == 1
    assert deleted[0][0] == "GET"
    assert "/api/manage/delete/vpush/1.png" in deleted[0][1]
    assert deleted[0][2] == "Bearer imgbed_testtoken"
    assert db._rows("SELECT source_url FROM hosted_images") == []


def test_purge_expired_keeps_shared_remote_file(db, cfg, monkeypatch):
    imgbed.configure(type("C", (), {"imgbed": cfg})())
    old = SOURCE
    fresh = "https://pbs.twimg.com/media/fresh.jpg"
    db.enqueue_hosted_image(old)
    db.enqueue_hosted_image(fresh)
    db.mark_hosted_image(old, status="ready", hosted_url=HOSTED)
    db.mark_hosted_image(fresh, status="ready", hosted_url=HOSTED)
    _age_hosted(db, old)
    deleted = []

    def handler(request: httpx.Request):
        deleted.append(str(request.url))
        return httpx.Response(200, json={"success": True})

    monkeypatch.setattr(imgbed, "_http_client", _client_factory(handler))
    assert imgbed.purge_expired(db) == 1
    assert deleted == []
    left = {row["source_url"] for row in db._rows("SELECT source_url FROM hosted_images")}
    assert left == {fresh}


def test_purge_expired_keeps_local_when_remote_delete_fails(db, cfg, monkeypatch):
    imgbed.configure(type("C", (), {"imgbed": cfg})())
    db.enqueue_hosted_image(SOURCE)
    db.mark_hosted_image(SOURCE, status="ready", hosted_url=HOSTED)
    _age_hosted(db, SOURCE)

    def handler(request: httpx.Request):
        return httpx.Response(403, json={"success": False, "error": "no delete permission"})

    monkeypatch.setattr(imgbed, "_http_client", _client_factory(handler))
    assert imgbed.purge_expired(db) == 0
    assert db._rows("SELECT source_url FROM hosted_images")[0]["source_url"] == SOURCE
