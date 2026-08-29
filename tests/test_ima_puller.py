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


def test_save_pdf_writes_atomically(tmp_path, monkeypatch):
    import app.ima_puller as puller

    class Resp:
        def read(self, n):
            data = getattr(self, "_data", b"%PDF-1.7abcd")
            self._data = b""
            return data[:n]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=120):
        assert req.get_header("X-ima-sign") == "sig" or req.headers.get("X-IMA-Sign") == "sig"
        return Resp()

    monkeypatch.setattr(puller.urllib.request, "urlopen", fake_urlopen)
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
