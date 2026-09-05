"""追平翻页：检测首页尾部缺口，向后翻页直到撞见已知帖或页数封顶。"""
import logging

from app.fetchers.base import (
    BACKFILL_PAGES,
    Post,
    _gap_warned_at,
    catchup_pages,
    tail_is_unseen,
    warn_timeline_gap,
)


def make_post(i: int) -> Post:
    return Post(
        platform="xueqiu",
        kol_id=1,
        kol_name="测试",
        external_id=str(i),
        title=f"t{i}",
        content=f"c{i}",
        url=f"https://xueqiu.com/{i}",
        published_at="",
    )


class StubDB:
    def __init__(self, known_ids: set[str]):
        self.known = known_ids
        self.queries: list[tuple] = []

    def existing_post_keys(self, pairs):
        self.queries.extend(pairs)
        return {p for p in pairs if p[1] in self.known}


def post_list(ids: list[int]) -> list[Post]:
    return [make_post(i) for i in ids]


def test_tail_seen_means_no_extra_requests():
    db = StubDB({"1"})  # 首页最旧一帖(1)已入库
    calls = []

    def fetch_page(page):
        calls.append(page)
        return []

    result = catchup_pages(db, fetch_page, post_list([5, 4, 3, 2, 1]))
    assert calls == []
    assert [p.external_id for p in result] == ["5", "4", "3", "2", "1"]


def test_known_newest_on_page_does_not_backfill_older_unseen():
    """首页已有已入库的新帖时，尾帖未见只是从未存过的更早历史，不是停机缺口。"""
    db = StubDB({"5"})  # 最新帖已在库，尾帖 1 未见
    calls = []

    def fetch_page(page):
        calls.append(page)
        return post_list([0, -1])

    result = catchup_pages(db, fetch_page, post_list([5, 4, 3, 2, 1]))
    assert calls == []
    assert [p.external_id for p in result] == ["5", "4", "3", "2", "1"]


def test_gap_paginates_until_known_post():
    db = StubDB({"1"})
    pages = {2: post_list([0, -1]), 3: post_list([-2])}

    def fetch_page(page):
        return pages.get(page, [])

    result = catchup_pages(db, fetch_page, post_list([5, 4, 3, 2]))  # 尾帖 2 未入库
    # 第 3 页尾帖 (-2) 不在库中会继续；这里第 3 页只有一条且未知 → 继续，
    # 第 4 页空列表终止。合并结果含首页 + 补页，无重复。
    ids = [p.external_id for p in result]
    assert ids[:4] == ["5", "4", "3", "2"]
    assert set(ids) >= {"0", "-1", "-2"}
    assert len(ids) == len(set(ids))


def test_gap_stops_when_batch_tail_is_known():
    db = StubDB({"1", "-2"})
    def fetch_page(page):
        return {2: post_list([0, -2]), 3: []}.get(page, [])  # 第 2 页尾帖已知

    result = catchup_pages(db, fetch_page, post_list([5, 2]))
    ids = [p.external_id for p in result]
    assert "0" in ids and "-2" in ids


def test_gap_stops_when_known_is_not_the_tail():
    db = StubDB({"-1"})  # 第 2 页中间已知，尾帖仍未见
    calls = []

    def fetch_page(page):
        calls.append(page)
        return {2: post_list([0, -1, -2]), 3: post_list([-99])}.get(page, [])

    result = catchup_pages(db, fetch_page, post_list([5, 2]))
    assert 3 not in calls
    assert "-99" not in [p.external_id for p in result]


def test_trailing_gap_warns_once_per_window(monkeypatch):
    _gap_warned_at.clear()
    records = []
    monkeypatch.setattr(logging.getLogger("app.fetchers.base"), "handle", None, raising=False)
    monkeypatch.setattr(
        "app.fetchers.base.logger.warning",
        lambda msg, *a: records.append(msg % a if a else msg),
    )
    db = StubDB(set())  # 全都不认识：永远追不平

    def fetch_page(page):
        return post_list([-100 - page])

    catchup_pages(db, fetch_page, post_list([5]))
    assert len(records) == 1  # 第一次告警
    catchup_pages(db, fetch_page, post_list([6]))
    assert len(records) == 1  # 冷却期内不再刷屏
    assert f"第 {BACKFILL_PAGES} 页" in records[0]


def test_first_gap_warning_is_not_suppressed_on_short_uptime(monkeypatch):
    _gap_warned_at.clear()
    records = []
    monkeypatch.setattr("app.fetchers.base.time.monotonic", lambda: 1.0)
    monkeypatch.setattr(
        "app.fetchers.base.logger.warning",
        lambda msg, *a: records.append(msg % a if a else msg),
    )

    warn_timeline_gap("xueqiu")

    assert len(records) == 1


def test_backfill_page_error_keeps_first_page():
    db = StubDB(set())

    def fetch_page(page):
        raise RuntimeError("网络断了")

    result = catchup_pages(db, fetch_page, post_list([7]))
    assert [p.external_id for p in result] == ["7"]


def test_tail_is_unseen_handles_empty_and_none():
    assert tail_is_unseen(None, post_list([1])) is False
    assert tail_is_unseen(StubDB({"1"}), []) is False
    assert tail_is_unseen(StubDB({"1"}), post_list([1])) is False
    assert tail_is_unseen(StubDB(set()), post_list([9])) is True
