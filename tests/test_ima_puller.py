import hashlib
from pathlib import Path

import pytest

from app.ima_puller import MAX_PDF_BYTES, allowed_url, save_pdf, safe_dest


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
