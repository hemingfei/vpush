"""外链图片补缓存：backfill_external_images 的行为与状态持久化。"""
import json

import httpx
import pytest

from app.db import DB
from app.image_backfill import backfill_external_images


def make_db(tmp_path) -> DB:
    return DB(tmp_path / "t.db")


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """MockTransport 的测试域名不真实解析：统一解析到公网 IP，不触发真实 DNS。"""
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])


def add_post(db, platform, external_id, images, published_at="2026-09-01 10:00:00"):
    kid = db.add_kol(platform, f"KOL-{external_id}", external_id)
    pid = db.insert_post(
        platform, kid, external_id, "", "正文", "", published_at, images=images
    )
    assert pid is not None
    return pid


def png_url(name):
    return f"https://img.example/{name}.png"


def make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok_handler(request):
    if request.url.path.startswith("/bad"):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")
    if request.url.path.startswith("/gone"):
        return httpx.Response(503)
    # 合法图片需 > 2048 字节（cache_image_file 按坏图退回原 URL 的阈值）
    return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG" * 600)


def get_images(db, platform, external_id):
    row = db._rows(
        "SELECT images FROM posts WHERE platform = ? AND external_id = ?",
        (platform, external_id),
    )[0]
    return json.loads(row["images"])


def test_backfill_caches_success_and_updates_posts(tmp_path):
    db = make_db(tmp_path)
    add_post(db, "mx", "m1", [png_url("a"), "/mx-images/aaaaaaaaaaaaaaaa.jpg"])

    stats = backfill_external_images(db, client=make_client(ok_handler))

    assert stats["images_ok"] == 1
    assert stats["posts_updated"] == 1
    images = get_images(db, "mx", "m1")
    assert images[0].startswith("/mx-images/")  # 外链替换为本地缓存
    assert images[1] == "/mx-images/aaaaaaaaaaaaaaaa.jpg"  # 已是本地的原样保留


def test_backfill_platform_prefix_mapping(tmp_path):
    db = make_db(tmp_path)
    add_post(db, "weibo", "w1", [png_url("w")])
    add_post(db, "xueqiu", "x1", [png_url("x")])
    add_post(db, "zsxq", "z1", [png_url("z")])

    backfill_external_images(db, client=make_client(ok_handler))

    assert get_images(db, "weibo", "w1")[0].startswith("/weibo-images/")
    assert get_images(db, "xueqiu", "x1")[0].startswith("/xq-images/")
    assert get_images(db, "zsxq", "z1")[0].startswith("/zsxq-images/")


def test_backfill_download_failure_enters_cooldown(tmp_path):
    """下载失败保持外链 + 进冷却：冷却期内不重试，过期后自动再试。"""
    db = make_db(tmp_path)
    add_post(db, "mx", "m1", [png_url("flaky")])
    hits = {"n": 0}

    def flaky_handler(request):
        hits["n"] += 1
        if hits["n"] == 1:  # 首次下载失败，之后恢复
            return httpx.Response(503)
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG" * 600)

    client = make_client(flaky_handler)
    stats = backfill_external_images(db, client=client, now=1000.0)
    assert stats["images_failed"] == 1
    assert get_images(db, "mx", "m1") == [png_url("flaky")]  # 保持外链

    # 冷却期内（6h）：跳过不下载（不发请求）
    stats = backfill_external_images(db, client=client, now=1000.0 + 60)
    assert stats["images_ok"] == 0 and stats["images_skipped"] == 1
    assert hits["n"] == 1

    # 冷却过期：再试成功
    stats = backfill_external_images(db, client=client, now=1000.0 + 7 * 3600)
    assert stats["images_ok"] == 1
    assert get_images(db, "mx", "m1")[0].startswith("/mx-images/")


def test_backfill_non_image_enters_permanent_skip(tmp_path):
    """200 但 content-type 非图片（网页卡片）：进跳过表永不再试。"""
    db = make_db(tmp_path)
    url = "https://img.example/bad/1"
    add_post(db, "mx", "m1", [url])

    stats = backfill_external_images(db, client=make_client(ok_handler), now=1000.0)
    assert stats["images_skipped"] == 1
    assert get_images(db, "mx", "m1") == [url]  # 原样保留

    # 下一轮直接跳过，不再发请求
    stats = backfill_external_images(db, client=make_client(ok_handler), now=9999999.0)
    assert stats["images_ok"] == 0 and stats["images_skipped"] == 1


def test_backfill_respects_limit(tmp_path):
    """limit 只计实际发起下载的张数，冷却/跳过的不占名额。"""
    db = make_db(tmp_path)
    add_post(db, "mx", "m1", [png_url(f"n{i}") for i in range(5)])

    stats = backfill_external_images(db, limit=2, client=make_client(ok_handler))
    assert stats["images_ok"] == 2

    # 剩余 3 张下一轮补上
    stats = backfill_external_images(db, limit=2, client=make_client(ok_handler))
    assert stats["images_ok"] == 2
    stats = backfill_external_images(db, limit=2, client=make_client(ok_handler))
    assert stats["images_ok"] == 1
    assert len(get_images(db, "mx", "m1")) == 5
    assert all(u.startswith("/mx-images/") for u in get_images(db, "mx", "m1"))


def test_backfill_state_persists_across_calls(tmp_path):
    """跳过表/冷却状态持久化在 settings 表，跨调用与进程重启生效。"""
    db = make_db(tmp_path)
    add_post(db, "mx", "m1", ["https://img.example/bad/2", png_url("gone3")])

    backfill_external_images(db, client=make_client(ok_handler), now=1000.0)
    raw = db.get_setting("image_backfill_state")
    state = json.loads(raw)
    assert state["skip"] and state["cooldown"]  # 两类状态都落库

    # 新 DB 实例（模拟重启）读同一库：跳过表仍生效
    db2 = DB(db.path)
    stats = db2 and backfill_external_images(db2, client=make_client(ok_handler), now=1000.0 + 60)
    assert stats["images_ok"] == 0
