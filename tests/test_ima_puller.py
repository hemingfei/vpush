import hashlib
import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest

from app.ima_puller import (
    _error_status,
    allowed_url,
    safe_dest,
    save_pdf,
    serve_puller,
)


def test_safe_dest_rejects_escape(tmp_path):
    with pytest.raises(ValueError):
        safe_dest(tmp_path, "../etc/passwd.pdf")
    with pytest.raises(ValueError):
        safe_dest(tmp_path, "a/../../x.pdf")
    with pytest.raises(ValueError):
        safe_dest(tmp_path, "notes.txt")


def test_safe_dest_accepts_group_day_pdf(tmp_path):
    dest = safe_dest(tmp_path, "group__abc/0829/Report.pdf")
    assert dest == tmp_path / "group__abc" / "0829" / "Report.pdf"


def test_allowed_url_https_ima_only():
    assert allowed_url("https://res-skb.ima.qq.com/a.pdf?sign=1") is True
    assert allowed_url("http://res-skb.ima.qq.com/a.pdf") is False
    assert allowed_url("https://example.com/a.pdf") is False
    assert allowed_url("https://ima.qq.com.evil.test/a.pdf") is False


def _fake_opener_factory(monkeypatch, puller, body=b"%PDF-1.7abcd", on_open=None):
    class Resp:
        def read(self, n):
            data = getattr(self, "_data", body)
            self._data = b""
            return data[:n]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeOpener:
        def open(self, req, data=None, timeout=120):
            if on_open is not None:
                on_open(req, timeout)
            assert req.get_header("X-ima-sign") == "sig" or req.headers.get("X-IMA-Sign") == "sig"
            return Resp()

    monkeypatch.setattr(
        puller.urllib.request,
        "build_opener",
        lambda *handlers: FakeOpener(),
    )


def test_safe_dest_rejects_symlink_parent(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir(parents=True)
    link_dir = tmp_path / "group__abc"
    link_dir.symlink_to(real_dir)
    with pytest.raises(ValueError, match="symlink"):
        safe_dest(tmp_path, "group__abc/Report.pdf")


def test_safe_dest_rejects_symlink_ancestor(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    real = archive / "realgroup"
    real.mkdir()
    (real / "0829").mkdir()
    link = archive / "group"
    link.symlink_to(real)
    with pytest.raises(ValueError):
        safe_dest(archive, "group/0829/Report.pdf")


def test_error_status_filename_too_long():
    assert _error_status(OSError(36, "File name too long")) == 400
    assert _error_status(RuntimeError("IMA PDF HTTP 502")) == 502


def test_save_pdf_long_title_keeps_part_under_name_max(tmp_path, monkeypatch):
    import app.ima_puller as puller

    _fake_opener_factory(monkeypatch, puller)
    # Final name sits on NAME_MAX. The old `{name}.XXXXXXXX.part` prefix overflowed.
    title = ("a" * 251) + ".pdf"
    dest = f"g/0830/{title}"
    result = save_pdf(
        tmp_path,
        dest,
        "https://res-skb.ima.qq.com/a.pdf",
        {"X-IMA-Sign": "sig"},
        expected_size=12,
    )
    path = tmp_path / "g" / "0830" / title
    assert path.read_bytes().startswith(b"%PDF-1.7")
    assert result["size"] == 12
    leftovers = list(path.parent.glob(".vpush-*")) + list(path.parent.glob("*.part"))
    assert leftovers == []


def test_save_pdf_uses_archive_lock_for_replace(tmp_path, monkeypatch):
    import app.ima_puller as puller

    _fake_opener_factory(monkeypatch, puller)
    entered = []

    @contextmanager
    def fake_lock(path):
        entered.append(path)
        yield

    monkeypatch.setattr(puller, "archive_lock", fake_lock)
    save_pdf(
        tmp_path,
        "g/0829/a.pdf",
        "https://res-skb.ima.qq.com/a.pdf",
        {"X-IMA-Sign": "sig"},
        expected_size=12,
    )

    assert entered == [tmp_path]


def test_save_pdf_writes_atomically(tmp_path, monkeypatch):
    import app.ima_puller as puller

    _fake_opener_factory(monkeypatch, puller)
    dest = "g/0829/a.pdf"
    result = save_pdf(
        tmp_path,
        dest,
        "https://res-skb.ima.qq.com/a.pdf",
        {"X-IMA-Sign": "sig"},
        expected_size=12,
    )
    path = tmp_path / "g" / "0829" / "a.pdf"
    assert path.read_bytes().startswith(b"%PDF-1.7")
    assert not list(path.parent.glob("*.part"))
    assert result["size"] == 12
    assert result["md5"] == hashlib.md5(b"%PDF-1.7abcd").hexdigest()


def test_save_pdf_rejects_redirect_off_allowlist(tmp_path, monkeypatch):
    import app.ima_puller as puller

    class FakeOpener:
        def open(self, req, data=None, timeout=120):
            handler = puller.AllowedRedirectHandler()
            handler.redirect_request(
                req, None, 302, "", {}, "https://example.com/evil.pdf"
            )

    monkeypatch.setattr(
        puller.urllib.request,
        "build_opener",
        lambda *handlers: FakeOpener(),
    )
    dest_path = tmp_path / "g" / "0829" / "a.pdf"
    with pytest.raises(PermissionError):
        save_pdf(
            tmp_path,
            "g/0829/a.pdf",
            "https://res-skb.ima.qq.com/a.pdf",
            {"X-IMA-Sign": "sig"},
        )
    assert not dest_path.exists()
    assert not list(dest_path.parent.glob("*.part"))


def test_save_pdf_rejects_non_pdf_and_cleans_part(tmp_path, monkeypatch):
    import app.ima_puller as puller

    _fake_opener_factory(monkeypatch, puller, body=b"NOTPDF-content")
    dest_path = tmp_path / "g" / "0829" / "a.pdf"
    with pytest.raises(RuntimeError, match="not a PDF"):
        save_pdf(
            tmp_path,
            "g/0829/a.pdf",
            "https://res-skb.ima.qq.com/a.pdf",
            {"X-IMA-Sign": "sig"},
        )
    assert not dest_path.exists()
    assert not list(dest_path.parent.glob("*.part"))


def test_save_pdf_rejects_size_mismatch_and_cleans_part(tmp_path, monkeypatch):
    import app.ima_puller as puller

    _fake_opener_factory(monkeypatch, puller)
    dest_path = tmp_path / "g" / "0829" / "a.pdf"
    with pytest.raises(RuntimeError, match="size mismatch"):
        save_pdf(
            tmp_path,
            "g/0829/a.pdf",
            "https://res-skb.ima.qq.com/a.pdf",
            {"X-IMA-Sign": "sig"},
            expected_size=999,
        )
    assert not dest_path.exists()
    assert not list(dest_path.parent.glob("*.part"))


def test_save_pdf_rejects_oversize_and_cleans_part(tmp_path, monkeypatch):
    import app.ima_puller as puller

    monkeypatch.setattr(puller, "MAX_PDF_BYTES", 8)
    _fake_opener_factory(monkeypatch, puller, body=b"%PDF-1.7-way-too-long")
    dest_path = tmp_path / "g" / "0829" / "a.pdf"
    with pytest.raises(RuntimeError, match="too large"):
        save_pdf(
            tmp_path,
            "g/0829/a.pdf",
            "https://res-skb.ima.qq.com/a.pdf",
            {"X-IMA-Sign": "sig"},
        )
    assert not dest_path.exists()
    assert not list(dest_path.parent.glob("*.part"))


def test_save_pdf_uses_range_for_large_files(tmp_path, monkeypatch):
    import app.ima_puller as puller

    body = b"%PDF-1.7" + b"x" * 32
    monkeypatch.setattr(puller, "RANGE_MIN_BYTES", 20)
    monkeypatch.setattr(puller, "RANGE_PARTS", 4)
    seen: list[str] = []

    class Resp:
        def __init__(self, data):
            self._data = data
            self.status = 206

        def read(self, n):
            data = self._data
            self._data = b""
            return data[:n]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeOpener:
        def open(self, req, data=None, timeout=120):
            rng = req.headers.get("Range") or req.get_header("Range") or ""
            seen.append(rng)
            assert rng.startswith("bytes=")
            start, end = rng.split("=", 1)[1].split("-")
            return Resp(body[int(start) : int(end) + 1])

    monkeypatch.setattr(puller.urllib.request, "build_opener", lambda *handlers: FakeOpener())
    result = save_pdf(
        tmp_path,
        "g/a.pdf",
        "https://res-skb.ima.qq.com/a.pdf",
        {"X-IMA-Sign": "sig"},
        expected_size=len(body),
    )
    assert (tmp_path / "g" / "a.pdf").read_bytes() == body
    assert result["size"] == len(body)
    assert len(seen) == 4
    assert not list((tmp_path / "g").glob("*.part"))


def _start(tmp_path, monkeypatch, token="secret"):
    import app.ima_puller as puller

    # save_pdf uses build_opener(...).open(...), not bare urlopen.
    # Patching urllib.request.build_opener is process-wide, so FakeOpener
    # must only intercept IMA CDN GETs and let localhost /pull through.
    real_build_opener = urllib.request.build_opener
    body = b"%PDF-1.7abcd"

    class Resp:
        def read(self, n):
            data = getattr(self, "_data", body)
            self._data = b""
            return data[:n]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeOpener:
        def open(self, req, data=None, timeout=120):
            url = req.get_full_url() if hasattr(req, "get_full_url") else str(req)
            if allowed_url(url):
                return Resp()
            return real_build_opener().open(req, data, timeout)

    monkeypatch.setattr(
        puller.urllib.request,
        "build_opener",
        lambda *handlers: FakeOpener(),
    )
    server = serve_puller(tmp_path, token, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, f"http://127.0.0.1:{port}"


def test_pull_requires_token(tmp_path, monkeypatch):
    server, base = _start(tmp_path, monkeypatch)
    try:
        req = urllib.request.Request(
            base + "/pull",
            data=json.dumps({
                "dest": "g/a.pdf",
                "url": "https://res-skb.ima.qq.com/a.pdf",
                "headers": {},
                "expected_size": 12,
            }).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("should 401")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        server.shutdown()


def test_pull_writes_pdf(tmp_path, monkeypatch):
    server, base = _start(tmp_path, monkeypatch)
    try:
        req = urllib.request.Request(
            base + "/pull",
            data=json.dumps({
                "dest": "g/a.pdf",
                "url": "https://res-skb.ima.qq.com/a.pdf",
                "headers": {"X-IMA-Sign": "sig"},
                "expected_size": 12,
            }).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer secret",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode())
        assert body["size"] == 12
        assert (tmp_path / "g" / "a.pdf").read_bytes().startswith(b"%PDF-1.7")
        health = urllib.request.urlopen(base + "/healthz", timeout=5).read()
        assert health == b"ok"
    finally:
        server.shutdown()
