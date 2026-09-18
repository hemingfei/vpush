"""Origin Cache-Control: hashed JS/CSS are immutable; HTML/manifest revalidate."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.static_assets import (
    IMMUTABLE_CACHE_CONTROL,
    REVALIDATE_CACHE_CONTROL,
    file_digest,
    hashed_url,
    resolve_fingerprinted_path,
    should_revalidate,
    static_dir,
)


def make_client(name="cache.db"):
    tmp = tempfile.mkdtemp()
    app = create_app(db_path=Path(tmp) / name)
    return TestClient(app)


def test_html_and_manifest_revalidate():
    client = make_client()
    app_js = hashed_url(static_dir() / "app.js")
    style = hashed_url(static_dir() / "style.css")
    for path in ("/", "/index.html", "/timeline", "/manifest.webmanifest", "/manifest-dark.webmanifest"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.headers.get("cache-control") == REVALIDATE_CACHE_CONTROL, path
        assert resp.headers.get("etag")
        if path != "/manifest.webmanifest" and path != "/manifest-dark.webmanifest":
            assert app_js in resp.text
            assert style in resp.text
            assert 'type="importmap"' in resp.text


def test_hashed_js_css_are_immutable():
    client = make_client("hashed.db")
    static = static_dir()
    for relative in ("app.js", "style.css", "vendor/design-tokens.css", "core/html.js"):
        url = hashed_url(static / relative)
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert resp.headers.get("cache-control") == IMMUTABLE_CACHE_CONTROL, url
        assert "text/html" not in resp.headers.get("content-type", "")


def test_unhashed_js_css_and_sw_revalidate():
    client = make_client("unhashed.db")
    for path in ("/app.js", "/style.css", "/core/html.js", "/sw.js"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.headers.get("cache-control") == REVALIDATE_CACHE_CONTROL, path


def test_wrong_hash_is_not_served():
    client = make_client("wrong-hash.db")
    resp = client.get("/app.deadbeefdead.js")
    assert resp.status_code == 404


def test_api_and_health_are_not_immutable():
    client = make_client("api-cache.db")
    for path in ("/api/me", "/healthz"):
        resp = client.get(path)
        cache = resp.headers.get("cache-control", "")
        assert "max-age=31536000" not in cache
        assert "immutable" not in cache


def test_should_revalidate_directory_and_html_paths():
    assert should_revalidate("")
    assert should_revalidate("/")
    assert should_revalidate(".")
    assert should_revalidate("index.html")
    assert should_revalidate("manifest.webmanifest")
    assert should_revalidate("app.js")
    assert not should_revalidate("logo-mark.svg")


def test_resolve_fingerprinted_path_rejects_traversal(tmp_path: Path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "app.js").write_text("ok\n")
    digest = file_digest(static / "app.js")
    assert resolve_fingerprinted_path(static, f"app.{digest}.js") == "app.js"
    assert resolve_fingerprinted_path(static, f"../app.{digest}.js") is None
    assert resolve_fingerprinted_path(static, f"app.{'0' * 12}.js") is None
