"""Truth Social 抓取器：CNN 存档的头部窗口解析、增量过滤与基线裁剪。"""
from __future__ import annotations

import json

import pytest

from app.db import DB
from app.fetchers.truth import (
    ARCHIVE_URL,
    TruthFetcher,
    entry_images,
    entry_published_at,
    parse_archive_head,
)

NEW = {
    "id": "1789999999999999999",
    "created_at": "2026-09-04T12:00:00.000Z",
    "content": "A big announcement!",
    "url": "https://truthsocial.com/@realDonaldTrump/1789999999999999999",
    "media": ["https://static-assets.truthsocial.com/x/original/pic.jpg", "https://static-assets.truthsocial.com/x/original/clip.mp4"],
    "replies_count": 1,
}
OLD_IN_WINDOW = {
    "id": "1788888888888888888",
    "created_at": "2026-08-20T08:00:00.000Z",
    "content": "Earlier post",
    "url": "https://truthsocial.com/@realDonaldTrump/1788888888888888888",
    "media": [],
}
TOO_OLD = {
    "id": "1000000000000000001",
    "created_at": "2022-02-14T15:54:32.528Z",
    "content": "Get Ready!",
    "url": "https://truthsocial.com/@realDonaldTrump/1000000000000000001",
    "media": [],
}


def serialize(entries) -> bytes:
    return json.dumps(entries, indent=2, ensure_ascii=False).encode()


def test_parse_archive_head_cuts_at_last_complete_object():
    raw = serialize([NEW, OLD_IN_WINDOW, TOO_OLD])
    # 模拟 Range 截断：砍掉最后一个对象的中段
    truncated = raw[: raw.rindex(b'"content"')]
    entries = parse_archive_head(truncated)
    assert [e["id"] for e in entries] == [NEW["id"], OLD_IN_WINDOW["id"]]


def test_entry_helpers_filter_images_and_format_time():
    assert entry_images(NEW) == ["https://static-assets.truthsocial.com/x/original/pic.jpg"]
    assert entry_images({"media": []}) == []
    assert entry_published_at(NEW) == "2026-09-04 20:00"


@pytest.fixture(autouse=True)
def _no_avatar_download(monkeypatch):
    """默认拦掉真实头像下载：抓取器引导逻辑单独在用例里打桩验证。"""
    monkeypatch.setattr(
        "app.avatar_cache.cache_avatar",
        lambda db_, kid, url, client=None: "/avatars/fake.jpg",
    )


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")


def _kol(db, name="特朗普", avatar=""):
    kid = db.add_kol("truth", name, "realDonaldTrump")
    if avatar:
        db.update_kol_avatar(kid, avatar)
    return db.get_kol(kid)


def test_first_fetch_is_baseline_only_recent_30d(db, monkeypatch):
    fetcher = TruthFetcher(db=db)
    monkeypatch.setattr(fetcher, "_request", lambda full: [NEW, TOO_OLD])
    posts = fetcher.fetch(_kol(db))
    assert [p.external_id for p in posts] == [NEW["id"]]
    assert posts[0].platform == "truth"
    assert posts[0].title == "A big announcement!"
    assert posts[0].published_at == "2026-09-04 20:00"
    assert posts[0].images == [NEW["media"][0]]
    assert posts[0].url.endswith("/" + NEW["id"])
    assert db.max_external_id_num("truth") == 0  # 未入库前仍为 0，入库由调度器负责


def test_incremental_fetch_only_returns_newer_ids(db, monkeypatch):
    fetcher = TruthFetcher(db=db)
    kid = db.add_kol("truth", "特朗普", "realDonaldTrump")
    db.insert_post("truth", kid, str(int(NEW["id"]) - 5), "旧帖", "旧帖", "u", "")
    seen = {}

    def fake_request(full):
        seen["full"] = full
        return [NEW, OLD_IN_WINDOW]

    monkeypatch.setattr(fetcher, "_request", fake_request)
    posts = fetcher.fetch(db.get_kol(kid))
    assert seen["full"] is False
    assert [p.external_id for p in posts] == [NEW["id"]]


def test_gap_window_falls_back_to_full_archive(db, monkeypatch):
    fetcher = TruthFetcher(db=db)
    kid = db.add_kol("truth", "特朗普", "realDonaldTrump")
    db.insert_post("truth", kid, "1500000000000000000", "很旧的已入库帖", "c", "u", "")
    calls = []

    def fake_request(full):
        calls.append(full)
        return [NEW] if not full else [NEW, OLD_IN_WINDOW, TOO_OLD]

    monkeypatch.setattr(fetcher, "_request", fake_request)
    posts = fetcher.fetch(db.get_kol(kid))
    assert calls == [False, True]  # 头部窗口没盖住上次位置 → 整档回补
    assert {p.external_id for p in posts} == {NEW["id"], OLD_IN_WINDOW["id"]}


def test_avatar_bootstrap_downloads_once(db, monkeypatch):
    fetcher = TruthFetcher(db=db)
    kol = _kol(db)
    used = []
    monkeypatch.setattr(fetcher, "_request", lambda full: [NEW])
    import app.fetchers.truth as truth_mod

    monkeypatch.setattr(truth_mod, "TRUMP_X_AVATAR", "https://pbs.twimg.com/x.jpg")

    def fake_cache(db_, kid, url, client=None):
        used.append(url)
        db.update_kol_avatar(kid, "/avatars/1.jpg")
        return "/avatars/1.jpg"

    monkeypatch.setattr("app.avatar_cache.cache_avatar", fake_cache)
    fetcher.fetch(kol)
    assert used == ["https://pbs.twimg.com/x.jpg"]
    # 已有头像后不再下载
    kol = db.get_kol(kol["id"])
    fetcher.fetch(kol)
    assert len(used) == 1


def test_archive_url_is_cnn_bucket():
    assert ARCHIVE_URL.startswith("https://ix.cnn.io/data/truth-social/")
