import tempfile
from pathlib import Path

from app.db import DB
from app.fetchers.base import Post
from app.scheduler import poll_once


class FakeFetcher:
    def __init__(self, posts):
        self.posts = posts

    def fetch(self, kol):
        return self.posts


class FakeFetcherError:
    def fetch(self, kol):
        raise RuntimeError("boom")


class FakeNotifier:
    channel = "test"

    def __init__(self):
        self.calls = []

    def notify(self, post):
        self.calls.append(post)


def make_db() -> DB:
    tmp = tempfile.mkdtemp()
    return DB(Path(tmp) / "test.db")


def make_post(kol_id):
    return Post(
        platform="xueqiu",
        kol_id=kol_id,
        kol_name="A",
        external_id="p1",
        title="t",
        content="c",
        url="u",
        published_at="",
    )


def test_new_post_pushed_once():
    db = make_db()
    kid = db.add_kol("xueqiu", "A", "1")
    post = make_post(kid)
    notifier = FakeNotifier()

    poll_once(db, {"xueqiu": FakeFetcher([post])}, [notifier])
    assert len(notifier.calls) == 1
    assert len(db.list_posts()) == 1
    assert db.list_push_logs()[0]["status"] == "success"

    poll_once(db, {"xueqiu": FakeFetcher([post])}, [notifier])
    assert len(notifier.calls) == 1
    assert len(db.list_posts()) == 1


def test_fetch_error_does_not_crash():
    db = make_db()
    db.add_kol("xueqiu", "A", "1")
    notifier = FakeNotifier()
    poll_once(db, {"xueqiu": FakeFetcherError()}, [notifier])
    assert len(db.list_posts()) == 0
    assert len(notifier.calls) == 0


def test_push_failure_logged():
    db = make_db()
    kid = db.add_kol("xueqiu", "A", "1")
    post = make_post(kid)

    class FailingNotifier(FakeNotifier):
        def notify(self, post):
            raise RuntimeError("down")

    notifier = FailingNotifier()
    poll_once(db, {"xueqiu": FakeFetcher([post])}, [notifier])
    logs = db.list_push_logs()
    assert logs[0]["status"] == "failed"
    assert "down" in logs[0]["error"]
