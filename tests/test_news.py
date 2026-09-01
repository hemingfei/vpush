from datetime import UTC, datetime
from pathlib import Path

import pytest
import httpx

from app.news import (
    NewsNotFound,
    ParsedArticle,
    clean_article_html,
    normalize_article_url,
    normalize_feed_url,
    parse_feed,
)

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def test_parse_rss_extracts_full_text_and_images():
    parsed = parse_feed((FIXTURES / "news_rss.xml").read_bytes(), "https://feed.example/rss", NOW)
    assert parsed.title == "Fixture RSS"
    assert parsed.format == "rss20"
    assert parsed.articles[0].external_id == "rss-guid-1"
    assert parsed.articles[0].images == [
        "https://feed.example/images/one.jpg",
        "https://cdn.example/two.png",
    ]
    assert 'data-news-image-index="0"' in parsed.articles[0].content_html
    assert "<script" not in parsed.articles[0].content_html
    assert "onerror" not in parsed.articles[0].content_html
    assert "javascript:" not in parsed.articles[0].content_html
    assert 'target="_blank"' in parsed.articles[0].content_html
    assert "noopener noreferrer nofollow" in parsed.articles[0].content_html


def test_parse_atom_preserves_english_source_text():
    parsed = parse_feed((FIXTURES / "news_atom.xml").read_bytes(), "https://feed.example/atom", NOW)
    assert parsed.format == "atom10"
    assert parsed.articles[0].title == "Markets remain cautious"
    assert "Markets" in parsed.articles[0].content_html
    assert parsed.articles[0].author == "Atom Author"


def test_normalize_article_url_drops_tracking_only():
    assert normalize_article_url("https://EXAMPLE.com/a?utm_source=x&id=7#part") == "https://example.com/a?id=7"


def test_parse_accepts_empty_valid_feed_and_clamps_future_dates():
    payload = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>'''
    assert parse_feed(payload, "https://feed.example/rss", NOW).articles == []
    future = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Future</title><item><title>Future item</title><link>/future</link><pubDate>Tue, 01 Sep 2099 00:00:00 GMT</pubDate></item></channel></rss>'''
    article = parse_feed(future, "https://feed.example/rss", NOW).articles[0]
    assert article.published_at == NOW.isoformat()


def test_parse_falls_back_to_normalized_url_and_caps_entries():
    items = "".join(
        f"<item><title>Item {i}</title><link>/articles/{i}?utm_medium=x</link></item>"
        for i in range(101)
    )
    payload = f'<rss version="2.0"><channel><title>Many</title>{items}</channel></rss>'.encode()
    parsed = parse_feed(payload, "https://feed.example/rss", NOW)
    assert len(parsed.articles) == 100
    assert parsed.articles[0].external_id == "https://feed.example/articles/0"


def test_clean_article_html_caps_images_and_skips_oversized_body():
    raw = "".join(f'<img src="/img/{i}.jpg">' for i in range(31))
    html, images = clean_article_html(raw, "https://feed.example/article")
    assert len(images) == 30
    assert 'data-news-image-index="29"' in html
    assert 'data-news-image-index="30"' not in html
    assert "src=" not in html
    huge = "<p>" + ("x" * (512 * 1024)) + "</p>"
    with pytest.raises(ValueError, match="正文过大"):
        clean_article_html(huge, "https://feed.example/article")


def test_parse_truncates_text_fields():
    payload = (
        '<rss version="2.0"><channel><title>Feed</title><item>'
        f'<guid>truncate</guid><title>{"t" * 600}</title>'
        f'<author>{"a" * 300}</author><link>https://feed.example/a</link>'
        f'<description>{"s" * 2200}</description></item></channel></rss>'
    ).encode()
    article = parse_feed(payload, "https://feed.example/rss", NOW).articles[0]
    assert len(article.title) == 500
    assert len(article.author) == 200
    assert len(article.summary) == 2000




def test_normalizers_reject_credentials_and_non_http_urls():
    with pytest.raises(ValueError):
        normalize_feed_url("https://user:pass@feed.example/rss")
    with pytest.raises(ValueError):
        normalize_article_url("javascript:alert(1)")



def make_news_service(tmp_path, handler):
    from app.db import DB
    from app.news import NewsService

    db = DB(str(tmp_path / "service.db"))
    source_id = db.add_news_source("测试媒体")
    feed_id = db.add_news_feed(
        source_id, "主源", "https://feed.example/rss", "https://feed.example/rss"
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    return NewsService(db, client=client), db, client, feed_id


def test_refresh_feed_sends_conditional_headers_and_handles_304(tmp_path, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(304, headers={"etag": '"v2"'})

    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    service, db, client, feed_id = make_news_service(tmp_path, handler)
    db._execute(
        "UPDATE news_feeds SET etag = ?, last_modified = ? WHERE id = ?",
        ('"v1"', "Mon, 01 Sep 2026 00:00:00 GMT", feed_id),
    )
    result = service.refresh_feed(feed_id)
    assert result["status"] == "not_modified"
    assert requests[0].headers["if-none-match"] == '"v1"'
    assert requests[0].headers["if-modified-since"] == "Mon, 01 Sep 2026 00:00:00 GMT"
    assert db.get_news_feed(feed_id)["consecutive_failures"] == 0
    service.close()
    client.close()
    db.close()


def test_submit_feed_rejects_duplicate_inflight_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    service, db, client, feed_id = make_news_service(
        tmp_path, lambda request: httpx.Response(304)
    )
    lock = service._feed_lock(feed_id)
    assert lock.acquire(blocking=False)
    try:
        assert not service.submit_feed(feed_id)
    finally:
        lock.release()
        service.close()
        client.close()
        db.close()


def test_refresh_feed_upserts_articles_and_recovers_failure(tmp_path, monkeypatch):
    payload = (FIXTURES / "news_rss.xml").read_bytes()
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    service, db, client, feed_id = make_news_service(
        tmp_path, lambda request: httpx.Response(200, headers={"etag": '"fresh"'}, content=payload)
    )
    result = service.refresh_feed(feed_id)
    assert result["status"] == "updated" and result["articles"] == 2
    assert len(db._rows("SELECT * FROM news_articles")) == 2
    feed = db.get_news_feed(feed_id)
    assert feed["etag"] == '"fresh"' and feed["consecutive_failures"] == 0
    service.close()
    client.close()
    db.close()


def test_refresh_feed_failure_is_recorded_without_touching_articles(tmp_path, monkeypatch):
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    service, db, client, feed_id = make_news_service(
        tmp_path, lambda request: httpx.Response(500, content=b"upstream")
    )
    result = service.refresh_feed(feed_id)
    assert result["error_code"] == "http_error"
    feed = db.get_news_feed(feed_id)
    assert feed["last_error_code"] == "http_error"
    assert feed["consecutive_failures"] == 1
    assert db._rows("SELECT * FROM news_articles") == []
    service.close()
    client.close()
    db.close()


def test_fetch_image_rejects_non_image_and_oversized_body(tmp_path, monkeypatch):
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    service, db, client, feed_id = make_news_service(
        tmp_path, lambda request: httpx.Response(200, headers={"content-type": "text/html"}, content=b"html")
    )
    uid = db.add_user("reader", "hash")
    source_id = db.get_news_feed(feed_id)["source_id"]
    db.set_user_news_sources(uid, [source_id])
    article_id = db.upsert_news_article({
        "source_id": source_id, "feed_id": feed_id, "external_id": "img-1",
        "title": "Image", "url": "https://example.com/article", "author": "",
        "summary": "", "content_html": "<img data-news-image-index=\"0\">",
        "images": ["https://feed.example/image.jpg"],
        "published_at": "2026-09-01T00:00:00+00:00",
        "fetched_at": "2026-09-01T00:00:00+00:00", "content_hash": "img",
    })
    with pytest.raises(NewsNotFound, match="图片不存在"):
        service.fetch_image(article_id, -1, uid)
    with pytest.raises(ValueError, match="图片类型"):
        service.fetch_image(article_id, 0, uid)

    service.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "image/jpeg"}, content=b"x" * (10 * 1024 * 1024 + 1)
            )
        ),
        trust_env=False,
    )
    with pytest.raises(ValueError, match="地址不安全|响应体过大"):
        service.fetch_image(article_id, 0, uid)
    service.close()
    client.close()
    db.close()




def test_parse_skips_entry_without_article_url():
    payload = b'''<rss version="2.0"><channel><title>Missing URL</title><item><title>No URL</title></item></channel></rss>'''
    assert parse_feed(payload, "https://feed.example/rss", NOW).articles == []


def test_refresh_feed_redacts_query_from_network_error(tmp_path, monkeypatch):
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])

    def handler(request):
        raise httpx.ConnectError("secret=value", request=request)

    service, db, client, feed_id = make_news_service(tmp_path, handler)
    result = service.refresh_feed(feed_id)
    assert result["error_code"] == "network_error"
    detail = db.get_news_feed(feed_id)["last_error_detail"]
    assert "secret" not in detail and "value" not in detail
    service.close()
    client.close()
    db.close()


def test_submit_due_skips_disabled_collection_and_submits_due_feeds(tmp_path, monkeypatch):
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    service, db, client, feed_id = make_news_service(
        tmp_path, lambda request: httpx.Response(304)
    )
    db.set_setting("news_enabled", "0")
    assert service.submit_due() == []
    accepted = []
    service.submit_feed = lambda current_id: accepted.append(current_id) or True
    db.set_setting("news_enabled", "1")
    db._execute(
        "UPDATE news_feeds SET last_attempt_at = ? WHERE id != ?",
        ("2099-01-01T00:00:00+00:00", feed_id),
    )
    db._execute(
        "UPDATE news_feeds SET last_attempt_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00+00:00", feed_id),
    )
    assert service.submit_due() == [feed_id]
    assert accepted == [feed_id]
    service.close()
    client.close()
    db.close()