# VPUSH Financial News Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved authenticated financial-news center, secure shared RSS/Atom ingestion, full administrator Feed management, per-user media selection, in-app full-text reading, and the WSCN quick-news navigation move.

**Architecture:** Add one focused `NewsService` domain module that reuses and tightens the existing `app.url_safety` pinned-request boundary, owns feed parsing/sanitizing, conditional refreshes, image fetching, and per-Feed executor locks. Keep persistence in the existing `DB` class, expose user/admin routes from the existing API router, call the shared service from the existing Scheduler, and add the UI to the current static SPA without introducing a second frontend or scheduler.

**Tech Stack:** Python 3.12, FastAPI, SQLite, `httpx`, `feedparser`, `bleach`, vanilla JavaScript/CSS, pytest, Playwright smoke verification.

---

## Scope And File Map

**Create**

- `app/news.py` - built-in source definitions, Feed URL normalization, RSS/Atom parsing, HTML sanitizing, bounded refresh executor, image retrieval.
- `tests/test_news.py` - parser, sanitizer, conditional refresh, failure isolation, image-security tests.
- `tests/fixtures/news_rss.xml` - deterministic RSS 2.0 fixture.
- `tests/fixtures/news_atom.xml` - deterministic Atom fixture.

**Modify**

- `requirements.txt` - pin `feedparser` and `bleach`.
- `app/url_safety.py` - add strict default-port validation and bounded streaming on top of the existing pinned-IP redirect handling.
- `app/db.py` - four news tables, `users.news_last_seen_at`, built-in migration, dynamic source relations, Feed/article CRUD and cleanup.
- `app/main.py` - create one shared `NewsService`, pass it to API/Scheduler, close it before SQLite, add the `news` SPA prefix.
- `app/scheduler.py` - submit due Feed refreshes and clean old news in the existing loop.
- `app/api.py` - user news API, authenticated image API, personal source update, administrator source/Feed/settings/refresh API.
- `app/static/app.js` - admin Feed manager, news list/reader/source picker, Information Center tabs, navigation migration.
- `app/static/style.css` - responsive admin master-detail, news list/reader, source dialog, Information Center tabs.
- `app/static/index.html` - static asset cache-buster revisions.
- `app/static/sw.js` - shell cache revision.
- `app/version.py` - patch release version.
- `PRODUCT.md` - add media-reading capability and the person/media/document boundary.
- `DESIGN.md` - replace the obsolete fixed seven-badge rule and document the Information Center.
- `tests/test_url_safety.py` - strict URL, port, redirect, DNS and decompressed-size coverage.
- `tests/test_db.py` - migration, defaults, archive/restore, user relations, article queries and cleanup.
- `tests/test_scheduler.py` - due refresh and retention integration.
- `tests/test_api.py` - user/admin API, authorization, seen anchor, audit and image tests.
- `tests/test_frontend_interactions.py` - static SPA contracts for both management and reading flows.
- `tests/test_spa_routes.py` - `/news` and `/news/{id}` shell fallback.
- `tests/test_frontend_pwa.py` - cache revision contract.

## Delivery Gates

1. Tasks 1-4 establish secure data capability without exposing routes.
2. Tasks 5-7 expose and schedule the backend while the old UI remains unchanged; no news article is connected to any notifier, retry queue, digest or push log.
3. Tasks 8-10 add administrator UI, reader UI and navigation migration.
4. Task 11 runs the full suite, real-Feed smoke test and desktop/mobile browser verification.

### Task 1: Extend The Existing Pinned URL Fetcher

**Files:**
- Modify: `app/url_safety.py`
- Modify: `tests/test_url_safety.py`

- [ ] **Step 1: Write strict-policy and bounded-body failing tests**

Add tests that preserve current permissive callers while defining the stricter news policy:

```python
from app.url_safety import safe_get_limited


def test_safe_get_limited_rejects_credentials_and_nondefault_ports(monkeypatch):
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    for url in (
        "https://user:pass@feed.example/rss",
        "https://feed.example:8443/rss",
        "http://feed.example:8080/rss",
    ):
        with pytest.raises(ValueError, match="不安全的下载地址"):
            safe_get_limited(client, url, max_bytes=1024, default_ports_only=True)


def test_safe_get_limited_stops_after_decompressed_limit(monkeypatch):
    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * 1025)
        )
    )
    with pytest.raises(ValueError, match="响应体过大"):
        safe_get_limited(client, "https://feed.example/rss", max_bytes=1024)


def test_safe_get_limited_revalidates_redirect_target(monkeypatch):
    def handler(request):
        if request.headers["host"] == "feed.example":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
        raise AssertionError("blocked redirect must not be requested")

    monkeypatch.setattr("app.url_safety._resolve_host_ips", lambda host: ["93.184.216.34"])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="不安全的下载地址"):
        safe_get_limited(client, "https://feed.example/rss", max_bytes=1024)
```

- [ ] **Step 2: Run the new tests and verify the missing API failure**

Run: `pytest tests/test_url_safety.py -q`

Expected: FAIL during collection because `safe_get_limited` is not defined.

- [ ] **Step 3: Add the strict wrapper without changing existing `safe_get` behavior**

Add a query-redacted label, strict pinning wrapper and bounded streaming function:

```python
def _safe_url_label(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return "invalid-url"
    return urlunparse((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", "", ""))[:160]


def _strict_pinned_request(url: str, default_ports_only: bool) -> tuple[str, str]:
    raw = (url or "").strip()
    if len(raw) > 2048:
        raise ValueError("不安全的下载地址: URL 过长")
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError:
        raise ValueError(f"不安全的下载地址: {_safe_url_label(raw)}") from None
    if parsed.username or parsed.password or (parsed.hostname or "").lower() == "localhost":
        raise ValueError(f"不安全的下载地址: {_safe_url_label(raw)}")
    expected_port = 443 if parsed.scheme == "https" else 80
    if default_ports_only and port not in (None, expected_port):
        raise ValueError(f"不安全的下载地址: {_safe_url_label(raw)}")
    return _pinned_request(raw)


def safe_get_limited(
    client: httpx.Client,
    url: str,
    *,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    default_ports_only: bool = False,
    timeout: httpx.Timeout | float = 15,
) -> httpx.Response:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        pinned, host_header = _strict_pinned_request(current, default_ports_only)
        hostname = urlparse(current).hostname or ""
        request_headers = {**(headers or {}), "Host": host_header}
        with client.stream(
            "GET",
            pinned,
            timeout=timeout,
            follow_redirects=False,
            headers=request_headers,
            extensions={"sni_hostname": hostname},
        ) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    return httpx.Response(
                        response.status_code,
                        headers=response.headers,
                        request=response.request,
                    )
                current = urljoin(current, location)
                continue
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ValueError("响应体过大")
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=bytes(body),
                request=response.request,
            )
    raise ValueError(f"重定向次数过多: {_safe_url_label(url)}")
```

Also make `_blocked_ip()` reject `is_loopback`, `is_private`, `is_link_local`, `is_multicast`, `is_unspecified`, and `is_reserved` in addition to the explicit CGNAT/NAT64 networks.

- [ ] **Step 4: Run all URL safety tests**

Run: `pytest tests/test_url_safety.py -q`

Expected: PASS, including the existing pinned-host/SNI and redirect tests.

- [ ] **Step 5: Commit the security primitive**

```bash
git add app/url_safety.py tests/test_url_safety.py
git commit -m "feat: add bounded public URL fetches"
```

### Task 2: Add News Schema, Built-In Sources And Default Selection Migration

**Files:**
- Modify: `app/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write migration and default-selection tests**

Add tests for four media, five Feed rows, old-user backfill, new-user defaults, and one-time migration behavior:

```python
def test_news_migration_seeds_builtin_sources_and_feeds(tmp_path):
    db = DB(str(tmp_path / "news.db"))
    sources = db._rows("SELECT slug, default_selected FROM news_sources ORDER BY id")
    feeds = db._rows("SELECT url FROM news_feeds ORDER BY id")
    assert [row["slug"] for row in sources] == ["bloomberg", "caixin", "ft", "morganstanley"]
    assert all(row["default_selected"] == 1 for row in sources)
    assert len(feeds) == 5


def test_new_user_gets_only_builtin_news_sources(tmp_path):
    db = DB(str(tmp_path / "news-user.db"))
    uid = db.add_user("reader", "hash")
    assert len(db.list_user_news_source_ids(uid)) == 4
    db._execute(
        "INSERT INTO news_sources (slug, name) VALUES ('custom-test', 'Custom Test')"
    )
    uid2 = db.add_user("reader2", "hash")
    assert len(db.list_user_news_source_ids(uid2)) == 4


def test_news_default_backfill_runs_once(tmp_path):
    path = tmp_path / "news-once.db"
    db = DB(str(path))
    uid = db.add_user("reader", "hash")
    db._execute("DELETE FROM user_news_sources WHERE user_id = ?", (uid,))
    db.close()
    reopened = DB(str(path))
    assert reopened.list_user_news_source_ids(uid) == []
```

Add a legacy-database test that creates `users` and `settings` before opening `DB`, then confirms `news_last_seen_at` and four relations are added.

- [ ] **Step 2: Run migration tests and verify they fail**

Run: `pytest tests/test_db.py -k news -q`

Expected: FAIL because the news tables and `list_user_news_source_ids()` do not exist.

- [ ] **Step 3: Add the schema and indexes to `SCHEMA`**

Add the approved four tables and user field:

```sql
CREATE TABLE IF NOT EXISTS news_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    built_in INTEGER NOT NULL DEFAULT 0,
    default_selected INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS news_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES news_sources(id),
    name TEXT NOT NULL COLLATE NOCASE,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    etag TEXT NOT NULL DEFAULT '',
    last_modified TEXT NOT NULL DEFAULT '',
    last_attempt_at TEXT,
    last_success_at TEXT,
    last_error_code TEXT NOT NULL DEFAULT '',
    last_error_detail TEXT NOT NULL DEFAULT '',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_id, name)
);
CREATE TABLE IF NOT EXISTS user_news_sources (
    user_id INTEGER NOT NULL REFERENCES users(id),
    source_id INTEGER NOT NULL REFERENCES news_sources(id),
    selected_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, source_id)
);
CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES news_sources(id),
    feed_id INTEGER NOT NULL REFERENCES news_feeds(id),
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    content_html TEXT NOT NULL DEFAULT '',
    images TEXT NOT NULL DEFAULT '[]',
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    UNIQUE (source_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_news_articles_time ON news_articles(published_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_source_time ON news_articles(source_id, published_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_news_feeds_due ON news_feeds(enabled, archived_at, last_attempt_at);
```

Add `news_last_seen_at TEXT` to the `users` declaration and idempotently `ALTER TABLE users` inside `_migrate()` for old databases.

- [ ] **Step 4: Seed built-ins and backfill exactly once**

Define immutable seed tuples in `app/db.py`, insert them with `INSERT OR IGNORE`, and use a `news_default_sources_v1` settings marker for the one-time old-user backfill. Initialize `news_enabled=1` and `news_refresh_interval_seconds=600` only when each key is absent. Add `_insert_default_news_sources(user_id)` and call it inside the same transaction as both `add_user()` and `register_with_code()`.

Use these exact seeds:

```python
_BUILTIN_NEWS = (
    ("bloomberg", "Bloomberg", (("最新财经", "https://quanwenrss.com/bloomberg"),)),
    ("caixin", "财新", (("最新文章", "https://quanwenrss.com/caixin"),)),
    ("ft", "FT 中文网", (("综合新闻", "https://quanwenrss.com/ft"),)),
    ("morganstanley", "摩根士丹利", (
        ("中国", "https://quanwenrss.com/morganstanley/china"),
        ("全球", "https://quanwenrss.com/morganstanley/global"),
    )),
)
```

- [ ] **Step 5: Cover user deletion and account transfer**

Update `delete_user()` to delete `user_news_sources`. Update `transfer_subscriptions()` in the same transaction to run `INSERT OR IGNORE INTO user_news_sources (user_id, source_id, selected_at) SELECT ?, source_id, selected_at FROM user_news_sources WHERE user_id = ?`, advance the target `news_last_seen_at` to the later non-null anchor, then delete the source user's relations.

- [ ] **Step 6: Run DB migration tests**

Run: `pytest tests/test_db.py -k 'news or transfer_subscriptions or delete_user' -q`

Expected: PASS.

- [ ] **Step 7: Commit schema and migration**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: add financial news schema"
```

### Task 3: Add News Persistence Methods

**Files:**
- Modify: `app/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write DB behavior tests**

Cover these behaviors with direct DB tests:

```python
def test_news_source_archive_preserves_user_relation(tmp_path):
    db = DB(str(tmp_path / "archive.db"))
    uid = db.add_user("reader", "hash")
    source_id = db.add_news_source("路透市场")
    db.set_user_news_sources(uid, [source_id])
    db.set_news_source_archived(source_id, True)
    assert source_id in db.list_user_news_source_ids(uid, include_archived=True)
    assert source_id not in db.list_user_news_source_ids(uid)
    db.set_news_source_archived(source_id, False)
    assert source_id in db.list_user_news_source_ids(uid)


def test_news_article_upsert_updates_without_duplicate(tmp_path):
    db = DB(str(tmp_path / "article.db"))
    source_id = db.add_news_source("测试媒体")
    feed_id = db.add_news_feed(source_id, "主源", "https://feed.example/rss", "https://feed.example/rss")
    article = {
        "source_id": source_id, "feed_id": feed_id, "external_id": "guid-1",
        "title": "First", "url": "https://example.com/1", "author": "A",
        "summary": "S", "content_html": "<p>One</p>", "images": [],
        "published_at": "2026-09-01T00:00:00+00:00",
        "fetched_at": "2026-09-01T00:01:00+00:00", "content_hash": "h1",
    }
    first = db.upsert_news_article(article)
    article.update(title="Updated", content_hash="h2")
    second = db.upsert_news_article(article)
    assert first == second
    assert db.get_news_article(first)["title"] == "Updated"


def test_news_seen_anchor_only_moves_forward(tmp_path):
    db = DB(str(tmp_path / "seen.db"))
    uid = db.add_user("reader", "hash")
    assert db.advance_news_seen(uid, "2026-09-01T10:00:00+00:00")
    assert not db.advance_news_seen(uid, "2026-09-01T09:00:00+00:00")
    assert db.get_user(uid)["news_last_seen_at"] == "2026-09-01T10:00:00+00:00"
```

Also test media-name uniqueness, global normalized-URL uniqueness, Feed URL-change state reset, media/Feed disable semantics (`enabled=0` pauses fetching but keeps cached articles readable), selected-source filtering, null first-seen behavior, archived detail denial, and 30-day cleanup.

- [ ] **Step 2: Run the new DB tests and verify missing-method failures**

Run: `pytest tests/test_db.py -k news -q`

Expected: FAIL on the first undefined CRUD method.

- [ ] **Step 3: Implement source and Feed CRUD**

Add these concrete `DB` methods under a `# ---- Financial news ----` section:

```python
list_news_sources(include_archived: bool = False) -> list[dict]
get_news_source(source_id: int) -> dict | None
add_news_source(name: str) -> int
update_news_source(source_id: int, *, name: str | None = None, enabled: bool | None = None) -> dict
set_news_source_archived(source_id: int, archived: bool) -> None
list_news_feeds(source_id: int | None = None, include_archived: bool = False) -> list[dict]
get_news_feed(feed_id: int) -> dict | None
get_news_feed_by_normalized_url(normalized_url: str) -> dict | None
add_news_feed(source_id: int, name: str, url: str, normalized_url: str) -> int
update_news_feed(feed_id: int, *, name: str | None = None, url: str | None = None,
                 normalized_url: str | None = None, enabled: bool | None = None) -> dict
set_news_feed_archived(feed_id: int, archived: bool) -> None
```

`add_news_source()` generates `custom-{uuid.uuid4().hex}` and forces `built_in=0, default_selected=0`. URL edits clear ETag, Last-Modified, attempt/success/error fields and failure count in the same SQL update. Convert uniqueness `sqlite3.IntegrityError` into stable `ValueError` messages.

- [ ] **Step 4: Implement relation, status and article methods**

Add these methods with transactions where multiple writes occur:

```python
list_user_news_source_ids(user_id: int, include_archived: bool = False) -> list[int]
set_user_news_sources(user_id: int, source_ids: list[int]) -> None
list_due_news_feeds(before_iso: str) -> list[dict]
mark_news_feed_attempt(feed_id: int, attempted_at: str) -> None
mark_news_feed_success(feed_id: int, *, etag: str, last_modified: str, succeeded_at: str) -> None
mark_news_feed_failure(feed_id: int, code: str, detail: str, attempted_at: str) -> None
upsert_news_article(article: dict) -> int
delete_news_articles_older_than(days: int) -> int
list_news_articles(user_id: int, *, source_id: int | None, q: str,
                   limit: int, offset: int) -> list[dict]
count_news_articles(user_id: int, *, source_id: int | None, q: str) -> int
get_news_article(article_id: int, user_id: int | None = None) -> dict | None
advance_news_seen(user_id: int, view_started_at: str) -> bool
news_source_statuses(user_id: int) -> list[dict]
```

`set_user_news_sources()` must validate every ID as unarchived before deleting/reinserting relations. `list_news_articles()` must join `user_news_sources` and exclude archived sources, but must not exclude disabled sources because their cached articles remain readable. Parse `images` JSON at the DB boundary and expose `has_image` in list rows.

`news_source_statuses()` aggregates each selected media as follows: `paused` when the media is disabled or has no enabled Feed; `unavailable` when enabled Feed rows have failures and none has ever succeeded; `delayed` when at least one enabled Feed has `consecutive_failures > 0`; otherwise `ok`. Return only the code and maximum `last_success_at` to ordinary users; internal details remain in administrator rows.

- [ ] **Step 5: Make `/me` relation updates atomic at DB level**

Extend `update_user_atomic()` with `news_source_ids=_UNSET`. Inside its existing transaction, validate unarchived IDs, replace `user_news_sources` only when the argument is provided, and preserve an explicit empty list.

- [ ] **Step 6: Run news DB tests and then all DB tests**

Run: `pytest tests/test_db.py -k news -q`

Expected: PASS.

Run: `pytest tests/test_db.py -q`

Expected: PASS with no existing migration or transaction regression.

- [ ] **Step 7: Commit persistence methods**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: add financial news persistence"
```

### Task 4: Parse Feeds And Sanitize Full Text

**Files:**
- Create: `app/news.py`
- Create: `tests/test_news.py`
- Create: `tests/fixtures/news_rss.xml`
- Create: `tests/fixtures/news_atom.xml`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pinned dependencies and deterministic fixtures**

Append:

```text
feedparser==6.0.11
bleach==6.2.0
```

Create an RSS fixture with GUID, title, author, RFC 822 date, relative article link, summary, `content:encoded`, safe anchor, malicious script/event attributes, and two images. Create an Atom fixture with entry ID, alternate link, ISO date, author and HTML content. The fixture article timestamps must be fixed in 2026 and must not call live services.

- [ ] **Step 2: Write parser and sanitizer tests**

```python
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


def test_parse_atom_preserves_english_source_text():
    parsed = parse_feed((FIXTURES / "news_atom.xml").read_bytes(), "https://feed.example/atom", NOW)
    assert parsed.format == "atom10"
    assert parsed.articles[0].title == "Markets remain cautious"
    assert "Markets" in parsed.articles[0].content_html


def test_normalize_article_url_drops_tracking_only():
    assert normalize_article_url("https://EXAMPLE.com/a?utm_source=x&id=7#part") == "https://example.com/a?id=7"
```

Also test empty valid Feed acceptance, future-date clamping, missing ID fallback to normalized URL, 100-entry cap, text truncation, 30-image cap and a cleaned body larger than 512 KB being skipped.

- [ ] **Step 3: Run parser tests and verify they fail**

Run: `pytest tests/test_news.py -q`

Expected: FAIL because `app.news` does not exist.

- [ ] **Step 4: Implement the domain data types and normalizers**

Create immutable domain records and complete URL normalizers:

```python
_TRACKING_QUERY_KEYS = {"fbclid", "gclid"}


@dataclass(frozen=True)
class ParsedArticle:
    external_id: str
    title: str
    url: str
    author: str
    summary: str
    content_html: str
    images: list[str]
    published_at: str
    fetched_at: str
    content_hash: str


@dataclass(frozen=True)
class ParsedFeed:
    title: str
    format: str
    articles: list[ParsedArticle]


def _normalized_parts(url: str) -> tuple[SplitResult, str]:
    parsed = urlsplit((url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("文章地址必须是 HTTP(S)")
    if parsed.username or parsed.password:
        raise ValueError("文章地址不能包含认证信息")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    host_label = f"[{host}]" if ":" in host else host
    port = parsed.port
    default_port = 443 if scheme == "https" else 80
    netloc = host_label if port in (None, default_port) else f"{host_label}:{port}"
    return parsed, urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def normalize_feed_url(url: str) -> str:
    return _normalized_parts(url)[1]


def normalize_article_url(url: str) -> str:
    parsed, normalized = _normalized_parts(url)
    base = urlsplit(normalized)
    query = urlencode([
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ])
    return urlunsplit((base.scheme, base.netloc, base.path, query, ""))
```

Then implement `clean_article_html(raw_html: str, base_url: str) -> tuple[str, list[str]]` and `parse_feed(payload: bytes, feed_url: str, fetched_at: datetime) -> ParsedFeed` with the exact sanitizer and parser behavior in Step 5. These signatures and return fields are final and are used unchanged by Tasks 5-7.

Use `feedparser.parse(payload)`. Require a recognized `parsed.version`; accept zero entries. Prefer `entry.content[0].value`, then summary/description. Prefer GUID/Atom ID, then normalized article URL. Convert `published_parsed`/`updated_parsed` to UTC and clamp a future value to `fetched_at`.

- [ ] **Step 5: Implement a Bleach token filter for links and images**

Build `bleach.Cleaner` with tags `p, br, h2, h3, hr, ul, ol, li, blockquote, strong, b, em, i, a, img, figure, figcaption, pre, code, table, thead, tbody, tr, th, td`; temporary attributes `a[href,title]`, `img[src,alt,title,width,height]`, and `th/td[colspan,rowspan]`; protocols `http, https`; and `strip=True`. Add a closure-backed `bleach.html5lib_shim.Filter` after sanitizing that:

```python
# <a>: resolve against article URL, keep only http(s), add target="_blank"
# and rel="noopener noreferrer nofollow".
# <img>: resolve and syntax-check http(s), append at most 30 URLs,
# remove src, and write data-news-image-index with the saved list index.
```

The returned HTML may contain `img[alt,title,width,height,data-news-image-index]` but no `img[src]`. Measure the UTF-8 encoded cleaned body and skip the article if it exceeds 512 KiB.

- [ ] **Step 6: Run parser tests**

Run: `pytest tests/test_news.py -q`

Expected: PASS.

- [ ] **Step 7: Commit parsing and sanitizing**

```bash
git add requirements.txt app/news.py tests/test_news.py tests/fixtures/news_rss.xml tests/fixtures/news_atom.xml
git commit -m "feat: parse and sanitize financial feeds"
```

### Task 5: Build Shared Refresh Service And Scheduler Integration

**Files:**
- Modify: `app/news.py`
- Modify: `app/main.py`
- Modify: `app/scheduler.py`
- Modify: `tests/test_news.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: Write conditional-refresh and executor-lock tests**

Use `httpx.MockTransport` and a temporary DB to assert:

```python
def make_news_service(tmp_path, handler):
    db = DB(str(tmp_path / "service.db"))
    source_id = db.add_news_source("测试媒体")
    feed_id = db.add_news_feed(
        source_id, "主源", "https://feed.example/rss", "https://feed.example/rss"
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    return NewsService(db, client=client), db, client, feed_id


def test_refresh_feed_sends_conditional_headers_and_handles_304(tmp_path):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(304, headers={"etag": '"v2"'})
    service, db, client, feed_id = make_news_service(tmp_path, handler)
    db._execute(
        "UPDATE news_feeds SET etag = ?, last_modified = ? WHERE id = ?",
        ('"v1"', "Mon, 01 Sep 2026 00:00:00 GMT", feed_id),
    )
    result = service.refresh_feed(feed_id)
    assert result["status"] == "not_modified"
    assert requests[0].headers["if-none-match"] == '"v1"'
    assert db.get_news_feed(feed_id)["consecutive_failures"] == 0
    service.close()
    client.close()
    db.close()


def test_submit_feed_rejects_duplicate_inflight_refresh(tmp_path):
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
```

Add tests for 200 upsert, one Feed failure not changing another Feed, public error codes, query-redacted internal errors, content-type rejection for images, and 10 MB image limit.

- [ ] **Step 2: Run service tests and verify failures**

Run: `pytest tests/test_news.py -k 'refresh or submit or image' -q`

Expected: FAIL because `NewsService` is not defined.

- [ ] **Step 3: Implement one shared `NewsService`**

Before `NewsService`, add stable domain errors used by both user and administrator routes:

```python
class NewsInputError(ValueError):
    """Administrator or Feed input is invalid or unsafe."""


class NewsNotFound(LookupError):
    """Requested article, image index, source or Feed is inaccessible."""


class NewsUpstreamError(RuntimeError):
    """A validated public upstream failed or returned unusable content."""
```

Add the complete constructor, lock lookup, submission wrapper and shutdown behavior:

```python
class NewsService:
    def __init__(self, db, client: httpx.Client | None = None):
        self.db = db
        self.client = client or httpx.Client(trust_env=False)
        self._owns_client = client is None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="news-feed")
        self._locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._closed = False

    def _feed_lock(self, feed_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(int(feed_id), threading.Lock())

    def submit_feed(self, feed_id: int) -> bool:
        if self._closed:
            return False
        lock = self._feed_lock(feed_id)
        if not lock.acquire(blocking=False):
            return False
        self._executor.submit(self._run_submitted, int(feed_id), lock)
        return True

    def _run_submitted(self, feed_id: int, lock: threading.Lock) -> None:
        try:
            self.refresh_feed(feed_id)
        finally:
            lock.release()

    def close(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=False)
        if self._owns_client:
            self.client.close()
```

In the same class implement the final public contracts `validate_feed(url: str) -> dict`, `refresh_feed(feed_id: int) -> dict`, `submit_due() -> list[int]`, and `fetch_image(article_id: int, index: int, user_id: int) -> tuple[bytes, str]` with the exact behavior in Step 4.

- [ ] **Step 4: Implement Feed validation and refresh behavior**

Use one `httpx.Timeout(connect=5, read=15, write=5, pool=5)` and call `safe_get_limited(self.client, url, max_bytes=5 * 1024 * 1024, default_ports_only=True, timeout=timeout)` for the 5 MB Feed limit. Validation returns only `format`, Feed `title`, and three plain-text `{title, published_at}` preview rows.

Refresh must:

1. Reload the Feed and parent source from DB and reject disabled/archived rows.
2. Mark `last_attempt_at` before network I/O.
3. Send saved ETag and Last-Modified.
4. Treat 304 as success without article writes.
5. Parse and upsert up to 100 entries on 2xx.
6. Map failures to `unsafe_url`, `network_error`, `http_error`, or `invalid_feed`.
7. Store a query-redacted detail capped to 300 characters.

`submit_due()` returns immediately when `news_enabled != "1"`; otherwise it computes `before_iso` from `news_refresh_interval_seconds`, loads only enabled/unarchived Feed rows whose attempt time is due, calls `submit_feed()` for each, and returns the accepted IDs.

`fetch_image()` checks article/user permission through DB, raises `NewsNotFound` for a missing/inaccessible article or index, performs a fresh strict fetch with a 10 MB cap, raises `NewsInputError` for unsafe targets/non-image content, raises `NewsUpstreamError` for upstream failures, and accepts only `image/jpeg`, `image/png`, `image/webp`, and `image/gif`.

- [ ] **Step 5: Wire the shared instance through application lifecycle**

In `create_app()`, instantiate `news_service = NewsService(db)`, pass `news_service=news_service` as the final keyword to the existing Scheduler constructor call, assign `app.state.news_service = news_service`, and pass the same keyword to the existing `create_api_router` call. During shutdown, stop/await Scheduler first, call `news_service.close()`, then close DB.

Extend `Scheduler.__init__()` with optional `news_service=None` so existing tests and callers remain valid. In each loop call `news_service.submit_due()` inside its own exception boundary. In the six-hour cleanup block call `db.delete_news_articles_older_than(posts_retention_days)` next to post cleanup.

- [ ] **Step 6: Add Scheduler integration tests**

Add a fake service with a call counter and assert one loop submits due Feed work without breaking KOL polling. Add a cleanup test that inserts old/new news rows and confirms only old rows are deleted.

- [ ] **Step 7: Run service and scheduler tests**

Run: `pytest tests/test_news.py tests/test_scheduler.py -k 'news or refresh_feed or submit_feed' -q`

Expected: PASS.

- [ ] **Step 8: Commit shared ingestion**

```bash
git add app/news.py app/main.py app/scheduler.py tests/test_news.py tests/test_scheduler.py
git commit -m "feat: schedule shared financial feed refreshes"
```

### Task 6: Add Authenticated User News API

**Files:**
- Modify: `app/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write user API tests first**

Add tests for source catalog, personal selection, list/search/pagination, first-visit `is_new=False`, monotonic seen, full-text permission and image permission:

```python
def insert_news_article(db, source_id, published_at):
    feed_id = db.list_news_feeds(source_id=source_id)[0]["id"]
    return db.upsert_news_article({
        "source_id": source_id,
        "feed_id": feed_id,
        "external_id": f"article-{source_id}-{published_at}",
        "title": "测试财经新闻",
        "url": "https://example.com/article",
        "author": "作者",
        "summary": "摘要",
        "content_html": "<p>正文</p>",
        "images": [],
        "published_at": published_at,
        "fetched_at": published_at,
        "content_hash": "hash",
    })


def test_news_list_and_seen_anchor_are_user_scoped():
    client = make_client()
    first_headers = user_headers(client, "news_first")
    second_headers = user_headers(client, "news_second")
    db = client.app.state.db
    first_uid = db.get_user_by_username("news_first")["id"]
    second_uid = db.get_user_by_username("news_second")["id"]
    source_ids = [row["id"] for row in db.list_news_sources()]
    db.set_user_news_sources(first_uid, source_ids[:1])
    db.set_user_news_sources(second_uid, [])
    article_id = insert_news_article(db, source_ids[0], "2026-09-01T10:00:00+00:00")
    first = client.get("/api/news", headers=first_headers).json()
    assert first["items"][0]["id"] == article_id
    assert first["items"][0]["is_new"] is False
    assert client.post("/api/news/seen", headers=first_headers,
                       json={"view_started_at": first["view_started_at"]}).status_code == 200
    assert client.get(f"/api/news/{article_id}", headers=second_headers).status_code == 404
```

Also assert unauthenticated 401, archived source 404, disabled source remains readable, invalid source selection 400, and image response has `Cache-Control: private, max-age=86400` plus `X-Content-Type-Options: nosniff`.

- [ ] **Step 2: Run user news API tests and verify 404 failures**

Run: `pytest tests/test_api.py -k news -q`

Expected: FAIL because `/api/news` routes do not exist.

- [ ] **Step 3: Add request models and personal-source transaction**

Add the exact seen model and add one field to the existing personal-update model:

```python
class NewsSeenIn(BaseModel):
    view_started_at: str
```

Add `news_source_ids: list[int] | None = None` to the existing `MeUpdate` model without changing its other fields.

- [ ] **Step 4: Add the user endpoints**

Implement exact routes:

```python
GET  /api/news/sources
GET  /api/news?limit=30&offset=0&source_id=&q=
POST /api/news/seen
GET  /api/news/{article_id}
GET  /api/news/{article_id}/images/{index}
```

`GET /api/news/sources` returns `{"items": sources, "collection_enabled": bool}`; each source includes `id`, `slug`, `name`, `enabled`, `selected`, and normalized public status. Capture `view_started_at = datetime.now(UTC).isoformat()` before querying the list. Return `next_offset`, `has_more`, source statuses, and `is_new = bool(anchor and published_at > anchor)`. Parse the submitted timestamp, require timezone awareness, normalize to UTC, and call `advance_news_seen()`.

Map `NewsNotFound` to 404, `NewsInputError` to 400 and `NewsUpstreamError` to 502 without returning internal exception text. The image endpoint calls `news_service.fetch_image()`, returns `Response(content=body, media_type=content_type)`, and sets `Cache-Control: private, max-age=86400`.

- [ ] **Step 5: Run focused and existing auth tests**

Run: `pytest tests/test_api.py -k 'news or update_me or register or wechat' -q`

Expected: PASS.

- [ ] **Step 6: Commit user API**

```bash
git add app/api.py tests/test_api.py
git commit -m "feat: expose personal financial news API"
```

### Task 7: Add Administrator Feed Management API

**Files:**
- Modify: `app/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write administrator API tests**

Cover administrator permission, settings bounds, media-name bounds/uniqueness, Feed validation, normalized URL uniqueness, URL-edit state reset, archive/restore, single-Feed 409, batch busy reporting and audit redaction:

```python
def test_admin_news_feed_crud_archives_without_deleting_articles(monkeypatch):
    client = make_client()
    headers = auth_headers(client)
    monkeypatch.setattr(client.app.state.news_service, "validate_feed", lambda url: {
        "format": "rss20", "title": "Fixture", "entries": []
    })
    source = client.post("/api/admin/news/sources", headers=headers,
                         json={"name": "路透市场"}).json()
    feed = client.post(f"/api/admin/news/sources/{source['id']}/feeds", headers=headers,
                       json={"name": "市场", "url": "https://feed.example/rss"}).json()
    assert client.post(f"/api/admin/news/feeds/{feed['id']}/archive", headers=headers).status_code == 200
    assert client.post(f"/api/admin/news/feeds/{feed['id']}/restore", headers=headers).status_code == 200


def test_admin_news_audit_redacts_feed_query(monkeypatch):
    client = make_client()
    headers = auth_headers(client)
    monkeypatch.setattr(client.app.state.news_service, "validate_feed", lambda url: {
        "format": "atom10", "title": "Fixture", "entries": []
    })
    source_id = client.post("/api/admin/news/sources", headers=headers,
                            json={"name": "审计媒体"}).json()["id"]
    client.post(f"/api/admin/news/sources/{source_id}/feeds", headers=headers,
                json={"name": "主源", "url": "https://feed.example/rss?secret=value"})
    detail = client.app.state.db.list_admin_logs(10)[0]["detail"]
    assert "secret" not in detail and "value" not in detail
```

- [ ] **Step 2: Run tests and verify missing-route failures**

Run: `pytest tests/test_api.py -k admin_news -q`

Expected: FAIL with 404 responses.

- [ ] **Step 3: Add administrator request models**

Define separate create/update models so PATCH omission differs from false/empty:

```python
class NewsSettingsIn(BaseModel):
    enabled: bool | None = None
    refresh_interval_minutes: int | None = None

class NewsSourceCreateIn(BaseModel):
    name: str

class NewsSourceUpdateIn(BaseModel):
    name: str | None = None
    enabled: bool | None = None

class NewsFeedCreateIn(BaseModel):
    name: str
    url: str

class NewsFeedUpdateIn(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None

class NewsFeedValidateIn(BaseModel):
    url: str
```

Trim and enforce media 1-60, Feed name 1-80, URL 1-2048, settings 5-1440 minutes. Call `normalize_feed_url()` before DB writes.

- [ ] **Step 4: Implement exact administrator routes**

Add these exact routes and response contracts:

```text
GET   /api/admin/news/settings
PATCH /api/admin/news/settings
GET   /api/admin/news/sources?include_archived=0
POST  /api/admin/news/sources
PATCH /api/admin/news/sources/{source_id}
POST  /api/admin/news/sources/{source_id}/archive
POST  /api/admin/news/sources/{source_id}/restore
POST  /api/admin/news/sources/{source_id}/refresh
POST  /api/admin/news/feeds/validate
POST  /api/admin/news/sources/{source_id}/feeds
PATCH /api/admin/news/feeds/{feed_id}
POST  /api/admin/news/feeds/{feed_id}/archive
POST  /api/admin/news/feeds/{feed_id}/restore
POST  /api/admin/news/feeds/{feed_id}/refresh
POST  /api/admin/news/refresh
```

Settings responses are `{"enabled": true, "refresh_interval_minutes": 10}`. The source list returns this concrete shape:

```json
{
  "items": [
    {
      "id": 1,
      "slug": "bloomberg",
      "name": "Bloomberg",
      "enabled": true,
      "archived_at": null,
      "article_count": 20,
      "feeds": [
        {
          "id": 1,
          "name": "最新财经",
          "url": "https://quanwenrss.com/bloomberg",
          "enabled": true,
          "archived_at": null,
          "last_attempt_at": "2026-09-01T10:00:00+00:00",
          "last_success_at": "2026-09-01T10:00:01+00:00",
          "last_error_code": "",
          "last_error_detail": "",
          "consecutive_failures": 0
        }
      ]
    }
  ]
}
```

Feed validation returns `{"format": "rss20", "title": "Fixture", "entries": []}` for an empty valid Feed. Create/update routes return the saved row; archive/restore routes return `{"ok": true}`.

Before network validation, normalize the URL and use `get_news_feed_by_normalized_url()` to reject duplicates, allowing the current Feed ID during an edit. Feed create/update then calls `news_service.validate_feed()` before writing. Archive actions only set `archived_at`; no DELETE endpoint is added.

Single-Feed refresh returns 409 when `submit_feed()` returns false. Source/all refresh endpoints submit each eligible Feed and return HTTP 202 with:

```json
{"accepted_feed_ids": [1, 2], "busy_feed_ids": [3]}
```

Reject manual refresh with 409 when global collection is disabled; URL validation remains available.

- [ ] **Step 5: Audit every write with redacted URLs**

Use the existing `_audit()` helper. Add `news_audit_url(url)` that records only scheme, host, port and path. Write stable action names such as `news_source_create`, `news_feed_update`, `news_feed_refresh`, `news_source_archive`, and `news_settings_update`.

- [ ] **Step 6: Run administrator and full API tests**

Run: `pytest tests/test_api.py -k 'admin_news or news_' -q`

Expected: PASS.

Run: `pytest tests/test_api.py -q`

Expected: PASS.

- [ ] **Step 7: Commit administrator API**

```bash
git add app/api.py tests/test_api.py
git commit -m "feat: manage financial feeds from admin API"
```

### Task 8: Build Administrator Feed Management UI

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/style.css`
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Write static UI contract tests**

Add tests that require the fifth data-source tab and final function names:

```python
def test_admin_news_tab_is_full_feed_manager():
    src = APP_JS.read_text()
    assert 'const STATS_TABS = ["config", "cookies", "proxies", "plaza", "news"]' in src
    for name in (
        "loadAdminNews", "renderAdminNews", "openNewsSourceModal",
        "openNewsFeedModal", "validateNewsFeedDraft", "refreshAdminNewsFeed",
        "archiveAdminNewsSource", "restoreAdminNewsSource",
    ):
        assert f"function {name}" in src or f"async function {name}" in src
    assert "财经资讯" in src
    assert "显示已归档" in src
    assert "验证并保存" in src


def test_admin_news_master_detail_is_responsive():
    css = STYLE_CSS.read_text()
    assert ".news-admin-layout" in css
    assert "grid-template-columns: 240px minmax(0, 1fr)" in css
    mobile = _media_block(css, "@media (max-width: 768px)")
    assert ".news-admin-layout" in mobile
    assert "grid-template-columns: 1fr" in mobile
```

- [ ] **Step 2: Run frontend contracts and verify failures**

Run: `pytest tests/test_frontend_interactions.py -k admin_news -q`

Expected: FAIL because the tab/functions/styles do not exist.

- [ ] **Step 3: Route the news subtab without loading unrelated stats**

Extend `STATS_TABS`. At the start of `loadAdminStats(seq)`, return `loadAdminNews(seq)` when `statsTabFromHash() === "news"`. Extract the five-button data-source tab strip into `statsTabsHtml(active)` and reuse it in the existing stats page and news manager, avoiding a second copy of tab markup.

- [ ] **Step 4: Implement administrator state and rendering**

Use one module state object:

```javascript
const adminNewsState = {
  settings: null, sources: [], selectedId: 0,
  q: "", status: "all", showArchived: false, busy: false,
};
```

`loadAdminNews()` fetches settings and source rows, preserves a still-valid selected ID, and calls `renderAdminNews()`. Render:

- global enabled checkbox, 5-1440 minute number field and refresh-all icon button;
- searchable/status-filtered 240px media rail with archived toggle;
- selected media name/status/actions and Feed rows;
- last success, last public error, failure count and article count;
- add/edit dialogs with labels, keyboard Escape, backdrop close, focus placement and explicit save/cancel;
- a concise notice in the new-media/Feed dialog that administrators must confirm content permission before enabling full-text collection;
- validation preview as escaped plain text only.

All server-returned names, URLs, errors and preview text pass through `escapeHtml()`.

- [ ] **Step 5: Implement actions without full-page races**

Each save/toggle/archive/restore/refresh captures `routeRenderSeq`, disables only its initiating control, calls the exact API, checks `routeStillActive()`, reloads the admin news data, and uses `flash()` for success/error. Do not start a new polling timer; manual reload and existing route lifecycle are sufficient for v1.

- [ ] **Step 6: Add responsive quiet-console CSS**

Use existing tokens, 1px borders and surfaces. The media rail and detail are siblings, not cards nested inside cards. Give URL text `overflow-wrap:anywhere`; keep icon controls 42px touch targets; collapse to one column at 768px; ensure modal fields and action rows wrap without horizontal overflow at 320px.

- [ ] **Step 7: Run administrator frontend contracts**

Run: `pytest tests/test_frontend_interactions.py -k 'admin_news or stats_tab' -q`

Expected: PASS.

- [ ] **Step 8: Commit administrator UI**

```bash
git add app/static/app.js app/static/style.css tests/test_frontend_interactions.py
git commit -m "feat: add financial feed admin workspace"
```

### Task 9: Build Personal News List, Source Picker And Reader

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/style.css`
- Modify: `app/main.py`
- Modify: `tests/test_frontend_interactions.py`
- Modify: `tests/test_spa_routes.py`

- [ ] **Step 1: Write route and interaction contracts**

```python
def test_news_reader_functions_cover_sources_seen_and_blob_cleanup():
    src = APP_JS.read_text()
    for name in (
        "renderNewsCenter", "loadFinancialNews", "openNewsSourcePicker",
        "saveNewsSources", "openNewsArticle", "loadNewsImages", "clearNewsImageUrls",
    ):
        assert f"function {name}" in src or f"async function {name}" in src
    seen = _fn_body("loadFinancialNews")
    assert '"/api/news/seen"' in seen
    assert "view_started_at" in seen
    images = _fn_body("clearNewsImageUrls")
    assert "URL.revokeObjectURL" in images


def test_news_source_picker_is_searchable_checkbox_dialog():
    body = _fn_body("openNewsSourcePicker")
    assert 'type="search"' in body
    assert 'type="checkbox"' in body
    assert 'role="dialog"' in body
    assert "我的来源" in body
```

Add `/news` and `/news/123` to `tests/test_spa_routes.py`, and assert both responses include `X-Robots-Tag: noindex, nofollow`.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `pytest tests/test_frontend_interactions.py -k news_reader -q && pytest tests/test_spa_routes.py -q`

Expected: FAIL for missing functions and missing SPA prefix.

- [ ] **Step 3: Add SPA route and reader state**

Add `news` to both backend and frontend SPA prefix sets. Route `page === "news"` to `renderNewsCenter(renderSeq, rawParam)`. Add state for sources, selected filter, query, items, offset, has-more, request sequence, observer and Blob URLs. Reset/abort/revoke all of it from `clearSessionCaches()` and route cleanup.

In the existing security-header middleware, set `X-Robots-Tag: noindex, nofollow` when the request path is `/news`, starts with `/news/`, or starts with `/api/news`.

- [ ] **Step 4: Implement list loading and seen acknowledgment**

Implement these final reader functions without changing their names in Task 10: `renderNewsCenter(seq, articleId)`, `renderFinancialNewsList(seq)`, `renderFinancialNewsArticle(articleId, seq)`, `loadFinancialNews(reset, seq)`, and `openNewsArticle(articleId)` (which routes to `news/{id}`). `renderNewsCenter` renders the article reader when `articleId` is present; otherwise it calls `renderFinancialNewsList`. `loadFinancialNews` sends `limit=30`, offset, selected media and query; discards stale responses with both route and request sequence; appends escaped rows; then POSTs the exact returned `view_started_at` only after rows are in the DOM.

Use an `IntersectionObserver` sentinel for pagination. First-load history must not receive a “新” badge; render only server-provided `is_new=true`.

- [ ] **Step 5: Implement media filter and searchable source picker**

Render “我的来源 · N” as a command button. The dialog reads `items` and `collection_enabled` from `/api/news/sources`, lists all unarchived media, uses checkboxes, client-side name search, and shows disabled media as “管理员已暂停更新”. When global collection is disabled, keep cached list/reader access working and show the page notice “管理员已暂停财经新闻采集”. Saving sends the complete checked ID list through `PUT /api/me`, including an explicit empty array. On success reload sources and reset the list.

The temporary source filter is one native `<select>` containing “全部” plus selected media only.

- [ ] **Step 6: Implement authenticated full-text images**

Add `apiBlob(path)` using the same bearer token and 401 logout behavior as `api()`. After safe `content_html` is inserted, query `[data-news-image-index]`, fetch `/api/news/{id}/images/{index}`, create object URLs, and set `img.src`. Track every URL in a Set and revoke it before route changes or rerenders.

The reader always shows media, title, author/time when present, sanitized body, and an external “打开原文” link with `target="_blank" rel="noopener noreferrer nofollow"`.

- [ ] **Step 7: Add list, dialog and reader CSS**

Keep list typography at reading size, summaries to two lines, stable 96x64 thumbnails, and article body at a readable max width without card nesting. Make tables scroll inside the article body, images responsive, source dialog fit 320px, and all controls at least 42px high.

- [ ] **Step 8: Run personal news frontend tests**

Run: `pytest tests/test_frontend_interactions.py -k news -q`

Expected: PASS.

Run: `pytest tests/test_spa_routes.py -q`

Expected: PASS.

- [ ] **Step 9: Commit reader UI**

```bash
git add app/static/app.js app/static/style.css app/main.py tests/test_frontend_interactions.py tests/test_spa_routes.py
git commit -m "feat: add personal financial news reader"
```

### Task 10: Move WSCN Quick News Into The Information Center

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/style.css`
- Modify: `PRODUCT.md`
- Modify: `DESIGN.md`
- Modify: `tests/test_frontend_interactions.py`

- [ ] **Step 1: Rewrite the existing quick-news navigation tests first**

Replace tests asserting that WSCN is the second timeline platform pill with contracts that assert:

```python
def test_information_center_owns_quick_news_and_financial_news():
    src = APP_JS.read_text()
    nav = src[src.index("const NAV ="):src.index("const SIDEBAR_SLIM_KEY")]
    mobile = src[src.index("const MOBILE_NAV ="):src.index("function renderBottomNav")]
    assert nav.index('route: "timeline"') < nav.index('route: "news"') < nav.index('route: "knowledge"')
    assert 'route: "news"' in mobile
    assert "财经新闻" in _fn_body("newsTabsHtml")
    assert "快讯" in _fn_body("newsTabsHtml")
    assert "data-platform=\"live\"" not in _fn_body("tlPillsHtml")


def test_information_center_defaults_to_financial_news_and_remembers_session_tab():
    src = APP_JS.read_text()
    assert 'const NEWS_TAB_KEY = "newsTab"' in src
    assert 'sessionStorage.getItem(NEWS_TAB_KEY) || "financial"' in src
    assert 'sessionStorage.setItem(NEWS_TAB_KEY' in _fn_body("switchNewsTab")
```

Update mobile badge assertions from the obsolete fixed seven items to the current user-scoped `timeline_platforms` entries plus “全部”, and preserve the minimum 44px target regardless of the returned count.

- [ ] **Step 2: Run migration contracts and verify failures**

Run: `pytest tests/test_frontend_interactions.py -k 'information_center or live_' -q`

Expected: FAIL until the old live pill is removed.

- [ ] **Step 3: Add desktop/mobile Information Center navigation**

Add a Lucide-style newspaper icon constant. Insert `news` immediately after `timeline` in desktop and mobile navigation. The mobile order becomes dynamic, information, plaza, combinations, subscriptions, settings; administrators append “more”. Keep each item flexible with a 44px minimum at 320px.

- [ ] **Step 4: Reuse the existing WSCN renderer under news tabs**

Add `NEWS_TAB_KEY`, default `financial`, `newsTabsHtml()` and `switchNewsTab(tab)`. Keep `renderNewsCenter()` as the route owner and mount one stable shell:

```javascript
async function renderNewsCenter(seq, articleId = "") {
  if (articleId) return renderFinancialNewsArticle(Number(articleId), seq);
  if (!$("#news-center")) {
    $("#main").innerHTML = `<div class="news-center" id="news-center">${newsTabsHtml()}<div id="news-panel"></div></div>`;
  }
  if (state.newsTab === "live") return renderTimeline(seq);
  return renderFinancialNewsList(seq);
}
```

`switchNewsTab(tab)` saves the outgoing financial/live scroll, writes session state, repaints tab ARIA state, clears only `#news-panel`, and calls `renderNewsCenter(routeRenderSeq)`; it must not replace all of `#main`.

Change `isLiveTimeline()` to return `isRoute("news") && state.newsTab === "live"`. Make `renderTimeline(seq)` derive `const informationCenter = isLiveTimeline()` from the route, target `#news-panel` instead of `#main` in that mode, and title the page “资讯”. In Information Center mode, do not render `tlPillsHtml()` or the研报库 entry; render only the existing live search/filter action, new badge, `liveFeedHeadHtml()`, Feed panel and wide live rail. This keeps every existing internal `renderTimeline(routeRenderSeq)` retry on the correct Information Center shell without passing an optional flag.

Refactor `renderFinancialNewsList()` to target `#news-panel` when the shell exists. Existing WSCN fetching, 15-second polling, cache, search, important filter, infinite loading and scroll state remain unchanged.

- [ ] **Step 5: Remove live mode from the dynamic platform strip**

Delete `TL_SOURCE_KEY`, `state.timelineSource`, `tlPersistSource()`, `tlPickSource()`, the live pill insertion and the branch that moves from live to KOL. Timeline route always renders KOL content. Keep `_livePosts`, prefetch and WSCN functions because the Information Center reuses them. Update `syncTimelineSourceView()` so it is only used by Information Center tab switching, never to place quick news back into the dynamic platform strip.

Update route scroll persistence so timeline uses `_tlSavedScrollY`, news/live uses `_liveSavedScrollY`, and financial news maintains its own list scroll position.

- [ ] **Step 6: Update product and design contracts**

In `PRODUCT.md`, add the authenticated Information Center, administrator Feed management and the fixed boundary “动态 = 人，资讯 = 媒体，研报库 = 文档”. Keep the self-hosted/non-public positioning and explicitly state financial news is reading-only in v1.

In `DESIGN.md`, replace “固定 7 格” with equal-width platform badges derived from the current user's subscribed `timeline_platforms` plus “全部”, retaining at least 44px targets. Add the Information Center’s two stable tabs and note that media selection uses a searchable checkbox dialog plus a single-select temporary filter.

- [ ] **Step 7: Run all frontend interaction tests**

Run: `pytest tests/test_frontend_interactions.py -q`

Expected: PASS, including updated quick-news and mobile contracts.

- [ ] **Step 8: Commit navigation migration**

```bash
git add app/static/app.js app/static/style.css PRODUCT.md DESIGN.md tests/test_frontend_interactions.py
git commit -m "feat: move quick news into information center"
```

### Task 11: Version, Full Verification And Browser Acceptance

**Files:**
- Modify: `app/version.py`
- Modify: `app/static/app.js`
- Modify: `app/static/index.html`
- Modify: `app/static/sw.js`
- Modify: `tests/test_frontend_pwa.py`

- [ ] **Step 1: Bump coherent static and application versions**

At plan authoring time the shared worktree already contains unrelated pending release bumps to `1.12.124`, `app.js?v=370`, and `dav-shell-v239`; preserve them. For this feature, change backend and frontend `APP_VERSION` from `1.12.124` to `1.12.125`, change `style.css?v=261` to `262`, `app.js?v=370` to `371`, and `dav-shell-v239` to `dav-shell-v240`. If those unrelated pending changes are not present when execution starts, stop this step and rebase the four targets to one increment above the then-current values rather than overwriting newer metadata.

Add a PWA test asserting the final cache name and both final index query revisions.

- [ ] **Step 2: Run format-independent focused suites**

Run:

```bash
pytest tests/test_url_safety.py tests/test_news.py tests/test_db.py -q
pytest tests/test_api.py -k news -q
pytest tests/test_scheduler.py -k news -q
pytest tests/test_frontend_interactions.py tests/test_spa_routes.py tests/test_frontend_pwa.py -q
```

Expected: all PASS.

- [ ] **Step 3: Run the complete regression suite**

Run: `pytest -q`

Expected: all PASS with zero failures and zero collection errors.

- [ ] **Step 4: Run a real-Feed local smoke test without CI dependency**

Run:

```bash
.venv/bin/python - <<'PY'
import tempfile
from pathlib import Path
from app.db import DB
from app.news import NewsService

with tempfile.TemporaryDirectory() as tmp:
    db = DB(str(Path(tmp) / "news-smoke.db"))
    service = NewsService(db)
    try:
        for url in (
            "https://quanwenrss.com/bloomberg",
            "https://quanwenrss.com/caixin",
            "https://quanwenrss.com/ft",
            "https://quanwenrss.com/morganstanley/china",
            "https://quanwenrss.com/morganstanley/global",
        ):
            preview = service.validate_feed(url)
            assert preview["format"] in {"rss20", "atom10"}, (url, preview)
            print(url, preview["format"], preview["title"], len(preview["entries"]))
    finally:
        service.close()
        db.close()
PY
```

Expected: five lines; Bloomberg/财新/FT report RSS, Morgan Stanley feeds report Atom, with no unsafe-URL or parse errors.

- [ ] **Step 5: Start an isolated local server for browser verification**

Run:

```bash
rm -f /tmp/vpush-news-review.db
DB_PATH=/tmp/vpush-news-review.db WEB_ADMIN_PASSWORD=review123 DAV_UI_ONLY=1 \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Expected: server listens on `http://127.0.0.1:8765`; login is `admin` / `review123`.

- [ ] **Step 6: Verify desktop and 320px mobile flows with Playwright**

At 1440x900 and 320x720:

1. Log in and confirm desktop/mobile navigation places “资讯” after “动态”.
2. Open `资讯`; confirm default “财经新闻”, switch to “快讯”, then return and reload to verify session tab memory.
3. Confirm quick news retains search, important filter, 15-second update detection and infinite loading.
4. Open “我的来源”, search, save an explicit empty selection, verify empty state, then restore Bloomberg.
5. Open a full article; verify sanitized text, external link, authenticated Blob images, no direct third-party image `src`, and no overlap.
6. Open `数据源 → 财经资讯`; add `https://feeds.bbci.co.uk/news/business/rss.xml` under a new “BBC Business” media, inspect validation preview, edit/disable/refresh/archive/restore it.
7. Attempt `http://127.0.0.1/rss`, `http://169.254.169.254/latest`, a credential URL and port 8080; each must be rejected without exposing resolved internal addresses.
8. Capture desktop/mobile screenshots; in Playwright assert every rendered article image has `img.complete === true`, `img.naturalWidth > 0`, and a `blob:` source, and assert `document.documentElement.scrollWidth === document.documentElement.clientWidth` at 320px.

Expected: all flows usable; no console errors, horizontal page overflow, overlapping controls, blank rendered images or network request directly to Feed image hosts.

- [ ] **Step 7: Inspect final diff and commit integration metadata**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors; only planned files are modified. Do not add unrelated `.cursor/`, `config.demo.yaml`, `docs/research/`, `work/`, or other existing untracked paths.

Commit:

```bash
git add app/version.py app/static/app.js app/static/index.html app/static/sw.js tests/test_frontend_pwa.py
git commit -m "chore: release financial news center"
```

## Final Acceptance Checklist

- [ ] Four built-in media/five Feed rows migrate idempotently; old and new users get only those defaults.
- [ ] Administrator custom media never auto-selects for users.
- [ ] Feed validation, scheduled refresh, manual refresh and image retrieval share pinned-IP SSRF protection.
- [ ] Credentials, nondefault ports, private/reserved IPs, mixed DNS answers, unsafe redirects and oversized decompressed bodies are blocked.
- [ ] RSS and Atom parse into one article model; HTML and image URLs cannot execute or trigger direct browser requests.
- [ ] Feed failures retain old content and do not stop sibling Feed refreshes.
- [ ] Disabled media remain readable with a paused status; archived media are hidden but recover relations/history.
- [ ] User list/search/filter/pagination/full text/seen anchor obey media permissions.
- [ ] Financial articles never enter Telegram, Feishu, WeCom, Bark or Web Push paths.
- [ ] WSCN remains short-cached and nonpersistent under `资讯 → 快讯`; dynamic timeline contains people only.
- [ ] Administrator and user layouts work at desktop and 320px with no overlap.
- [ ] `PRODUCT.md`, `DESIGN.md`, asset versions and service-worker cache agree with shipped behavior.
- [ ] Full pytest suite, real-Feed smoke test and Playwright acceptance all pass.
