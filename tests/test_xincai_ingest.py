"""心裁 webhook 接收端：入库、幂等、隔离可见性、不被轮询。"""
from datetime import UTC, datetime, timedelta

import pytest

from app import xincai
from app.db import DB

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


@pytest.fixture()
def db(tmp_path):
    return DB(str(tmp_path / "xincai.db"))


@pytest.fixture()
def admin(db):
    return db.get_user(db.add_user("admin", "x", is_admin=True))


@pytest.fixture()
def member(db):
    return db.get_user(db.add_user("member", "x", is_admin=False))


def _payload(count=2, source_name="财新 · 金融"):
    # fetchedAt 用当前时间：源状态新鲜度看的就是它，写死过去的时间会被判成 stale
    fetched = datetime.now(UTC).isoformat()
    articles = []
    for i in range(count):
        key = 102400000 + i
        articles.append(
            {
                "sourceId": "source-ndvz",
                "sourceName": source_name,
                "key": str(key),
                "externalId": f"xincai:source-ndvz:{key}",
                "title": f"标题 {i}",
                "author": "记者甲",
                "url": f"https://finance.caixin.com/2026-09-23/{key}.html",
                "publishedAt": "2026-09-23T00:00:00.000Z",
                "fetchedAt": fetched,
                "html": (
                    '<p>第一段</p><script>alert(1)</script>'
                    '<figure><img src="https://img.caixin.com/a.png"></figure>'
                ),
                "text": "第一段",
                "contentHash": "abc123",
            }
        )
    return {"sourceName": "心裁 · 财新", "group": "心裁", "articles": articles}


def _source_id(result):
    return next(iter(result["sources"].values()))


def test_ingest_creates_internal_source_and_sanitizes_html(db, admin):
    result = xincai.ingest_articles(db, _payload())

    assert result["ok"] is True
    assert result["accepted"] == 2
    source = db.get_news_source(_source_id(result))
    assert source["internal"] == 1
    assert source["group_name"] == "心裁"

    article_id = db.list_news_articles(
        admin["id"], source_id=_source_id(result), q="", limit=5, offset=0
    )[0]["id"]
    article = db.get_news_article(article_id)
    # 与 RSS 走同一条清洗链路：脚本去掉、图片转成本地索引
    assert "<script" not in article["content_html"]
    assert 'data-news-image-index="0"' in article["content_html"]
    assert article["images"] == ["https://img.caixin.com/a.png"]


def test_ingest_is_idempotent_across_repeats(db, admin):
    first = xincai.ingest_articles(db, _payload())
    second = xincai.ingest_articles(db, _payload())

    assert first["accepted"] == second["accepted"] == 2
    # 重推同一批不新增行——推送端「每轮重推最近 N 篇」靠的就是这条
    rows = db.list_news_articles(
        admin["id"], source_id=_source_id(first), q="", limit=50, offset=0
    )
    assert len(rows) == 2


def test_list_sources_excludes_internal_for_members(db):
    result = xincai.ingest_articles(db, _payload())
    source_id = _source_id(result)

    all_ids = {s["id"] for s in db.list_news_sources()}
    public_ids = {s["id"] for s in db.list_news_sources(exclude_internal=True)}
    assert source_id in all_ids
    assert source_id not in public_ids


def test_member_blocked_on_every_read_path(db, admin, member):
    result = xincai.ingest_articles(db, _payload())
    source_id = _source_id(result)
    article_id = db.list_news_articles(
        admin["id"], source_id=source_id, q="", limit=1, offset=0
    )[0]["id"]

    # 管理员按源浏览看得到，普通用户在源列表 / 列表 / 计数三条路径上都看不到
    assert len(db.list_news_articles(
        admin["id"], source_id=source_id, q="", limit=10, offset=0
    )) == 2
    assert db.list_news_articles(
        member["id"], source_id=source_id, q="", limit=10, offset=0, exclude_internal=True
    ) == []
    assert db.count_news_articles(
        member["id"], source_id=source_id, q="", exclude_internal=True
    ) == 0

    # article_id 自增可枚举：按 id 直读必须也挡住
    assert db.get_news_article(article_id, user_id=member["id"], exclude_internal=True) is None
    assert db.get_news_article(article_id, user_id=member["id"]) is not None

    # 订阅圈视角（source_id=None）同样看不到
    assert db.list_news_articles(
        member["id"], source_id=None, q="", limit=10, offset=0, exclude_internal=True
    ) == []


def test_placeholder_feed_never_polled(db):
    result = xincai.ingest_articles(db, _payload())
    source_id = _source_id(result)

    feeds = db.list_news_feeds(source_id)
    assert len(feeds) == 1 and feeds[0]["enabled"] == 0
    # 内置源的 feed 照常被轮询，但这条占位 feed 永远不出现在 due 列表里
    due_ids = {f["id"] for f in db.list_due_news_feeds((NOW + timedelta(days=1)).isoformat())}
    assert feeds[0]["id"] not in due_ids


def test_items_without_external_id_are_skipped_not_fatal(db):
    body = _payload()
    body["articles"].append({"title": "没有 externalId"})
    result = xincai.ingest_articles(db, body)

    assert result["accepted"] == 2
    assert result["skipped"] == 1


def test_rejects_bad_payload(db):
    with pytest.raises(xincai.XincaiIngestError):
        xincai.ingest_articles(db, {"articles": []})
    with pytest.raises(xincai.XincaiIngestError):
        xincai.ingest_articles(db, {"articles": "不是列表"})
    with pytest.raises(xincai.XincaiIngestError):
        xincai.ingest_articles(db, {"articles": [{}] * (xincai.MAX_BATCH_ARTICLES + 1)})


def test_timestamps_normalized_to_utc_iso(db, admin):
    body = _payload(1)
    body["articles"][0]["publishedAt"] = "2026-09-23T08:30:00.000Z"
    result = xincai.ingest_articles(db, body)

    article = db.list_news_articles(
        admin["id"], source_id=_source_id(result), q="", limit=1, offset=0
    )[0]
    assert article["published_at"] == "2026-09-23T08:30:00+00:00"


def test_name_colliding_with_public_source_is_rejected(db):
    db.add_news_source("财新 · 金融", "国内综合")
    with pytest.raises(xincai.XincaiIngestError):
        xincai.ingest_articles(db, _payload())


def test_internal_source_reports_ok_not_paused(db, admin):
    """占位 feed 是 enabled=0，按 feed 判会永远显示「已暂停」，改看入库时间。"""
    result = xincai.ingest_articles(db, _payload())
    source_id = _source_id(result)
    db.set_user_news_sources(admin["id"], [source_id])

    statuses = {s["id"]: s for s in db.news_source_statuses()}
    assert statuses[source_id]["code"] == "ok"
    assert statuses[source_id]["last_success_at"]


def test_renamed_source_keeps_identity(db, admin):
    """显示名改了不该产生重复源：身份按对端 sourceId 走，名字只是标签。"""
    first = xincai.ingest_articles(db, _payload())
    source_id = _source_id(first)

    # 管理员在后台改名（vpush 上真实发生过：财新 · 中国 → 财新 · 政经）
    db._execute("UPDATE news_sources SET name = ? WHERE id = ?", ("财新 · 政经", source_id))

    second = xincai.ingest_articles(db, _payload(source_name="财新 · 中国"))
    assert _source_id(second) == source_id
    assert db.get_news_source(source_id)["name"] == "财新 · 政经"  # 保留管理员改的名字
    internal = [s for s in db.list_news_sources() if int(s.get("internal") or 0)]
    assert len(internal) == 1  # 没有长出第二个源


def test_internal_source_goes_paused_when_stale(db, admin):
    result = xincai.ingest_articles(db, _payload())
    source_id = _source_id(result)
    db.set_user_news_sources(admin["id"], [source_id])
    stale = (datetime.now(UTC) - timedelta(hours=db._INTERNAL_FRESH_HOURS + 2)).isoformat()
    db._execute("UPDATE news_feeds SET last_success_at = ? WHERE source_id = ?", (stale, source_id))

    statuses = {s["id"]: s for s in db.news_source_statuses()}
    assert statuses[source_id]["code"] == "paused"
