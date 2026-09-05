"""Truth 翻译回填：只补近期英文原帖、跳过链接/中文帖、限额与去重。"""
from __future__ import annotations

import time

import pytest

from app.db import DB
from app import scheduler


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def _seed(db, n=1):
    kid = db.add_kol("truth", "Donald J. Trump", "realDonaldTrump")
    for i in range(n):
        db.insert_post(
            "truth", kid, f"p{i}", f"Title {i}",
            f"This is a long enough English post number {i} for the backfill test.",
            "https://truthsocial.com/@realDonaldTrump/x", _now(),
        )


def test_backfill_translates_and_stores_src(db, monkeypatch):
    _seed(db, 2)
    monkeypatch.setattr(scheduler, "translate_text", lambda text, **kw: f"中文：{text[:10]}")
    assert scheduler.backfill_truth_translations(db, limit=3) == 2
    for row in db.list_posts():
        assert row["content"].startswith("中文：")
        assert row["content_src"].startswith("This is")
        assert row["title_src"] == f"Title {row['external_id'][-1]}"


def test_backfill_skips_link_only_and_chinese(db, monkeypatch):
    kid = db.add_kol("truth", "Donald J. Trump", "realDonaldTrump")
    db.insert_post(
        "truth", kid, "link", "RT",
        "RT: https://truthsocial.com/users/realDonaldTrump/statuses/111111",
        "u", _now(),
    )
    db.insert_post(
        "truth", kid, "zh", "中文",
        "这是一条足够长的中文帖子内容，本来就不需要再做任何翻译处理了。",
        "u", _now(),
    )
    calls = []
    monkeypatch.setattr(
        scheduler, "translate_text", lambda text, **kw: calls.append(text) or "译"
    )
    assert scheduler.backfill_truth_translations(db, limit=3) == 0
    assert calls == []
    # 已标记处理：再跑不再扫到，也不会反复调翻译
    assert scheduler.backfill_truth_translations(db, limit=3) == 0


def test_backfill_respects_limit(db, monkeypatch):
    _seed(db, 3)
    monkeypatch.setattr(scheduler, "translate_text", lambda text, **kw: "中文译文" + text[:5])
    assert scheduler.backfill_truth_translations(db, limit=2) == 2
    assert sum(1 for r in db.list_posts() if r["content"].startswith("中文译文")) == 2


def test_backfill_marks_unchanged_translation_processed(db, monkeypatch):
    _seed(db, 1)
    monkeypatch.setattr(scheduler, "translate_text", lambda text, **kw: text)
    assert scheduler.backfill_truth_translations(db, limit=3) == 0
    row = db.list_posts()[0]
    assert row["content_src"] == row["content"]


def test_backfill_only_recent_window(db, monkeypatch):
    kid = db.add_kol("truth", "Donald J. Trump", "realDonaldTrump")
    db.insert_post(
        "truth", kid, "old", "Old",
        "This old English post is two days old and outside the one day window.",
        "u", "2026-09-01 08:00",
    )
    monkeypatch.setattr(scheduler, "translate_text", lambda text, **kw: "中文")
    assert scheduler.backfill_truth_translations(db, limit=3) == 0
    row = db.list_posts()[0]
    assert row["content_src"] == ""
