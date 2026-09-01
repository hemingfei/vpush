from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.news import (
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
