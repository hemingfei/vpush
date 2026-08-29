# IMA Storage Direct Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DMIT only calls IMA `get_media`; the storage VPS GETs the signed CDN URL and writes the PDF under `/srv/vpush-ima`.

**Architecture:** A stdlib ThreadingHTTPServer on `10.80.0.2:8743` accepts a synchronous `POST /pull` with url+headers+relative dest. `ImaPureClient.download()` uses it when `IMA_PULL_URL` is set, otherwise keeps the current local urllib path. NFS stays for serving files. No queue: `get_media` is followed immediately by pull so the signed URL does not sit on disk.

**Tech Stack:** Python 3 stdlib (`http.server`, `urllib`), pytest, systemd, WireGuard, existing FastAPI app.

**Spec:** `docs/superpowers/specs/2026-08-29-ima-storage-direct-download-design.md`

---

## File Map

**Application**

- Create `app/ima_puller.py`: path lock, host allowlist, CDN GET, atomic write, HTTP handler, `__main__` server.
- Modify `app/ima_documents.py`: `ImaPureClient.download()` optional puller; `_fetch` 403 retry; skip DMIT `mkdir` when pulling.
- Modify `docker-compose.prod.yml`: pass `IMA_PULL_URL` and `IMA_PULL_TOKEN`.
- Modify `docker-compose.yml`: same env keys, empty default.
- Modify `.env.example`: document the two keys, no secrets.

**Tests**

- Create `tests/test_ima_puller.py`: path escape, host allowlist, save_pdf, HTTP token, 403.
- Modify `tests/test_ima_documents.py`: download via puller; `_fetch` retries once on 403.

**Operations**

- Create `deploy/ima-storage/vpush-ima-puller.service`.
- Modify `deploy/ima-storage/README.md`: install, token file, firewall bind, rollback.

Do not add a queue, Redis, extra container, or IMA credentials on the storage VPS.

---

### Task 1: Puller path lock and atomic write

**Files:**
- Create: `app/ima_puller.py`
- Test: `tests/test_ima_puller.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ima_puller.py -q --tb=line`

Expected: FAIL with `ModuleNotFoundError: app.ima_puller`

- [ ] **Step 3: Write minimal implementation**

Create `app/ima_puller.py`:

```python
from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

MAX_PDF_BYTES = 200 * 1024 * 1024
MAX_JSON_BYTES = 1_000_000


def allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and host.endswith(".ima.qq.com")


def safe_dest(root: Path, dest: str) -> Path:
    text = str(dest or "").replace("\\", "/").lstrip("/")
    if not text.endswith(".pdf") or text.endswith("/.pdf"):
        raise ValueError("dest must be a .pdf path")
    root = root.resolve()
    candidate = (root / text).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("dest escapes archive root")
    if candidate.parent.exists() and candidate.parent.is_symlink():
        raise ValueError("archive directory must not be a symlink")
    return candidate


def save_pdf(
    root: Path,
    dest: str,
    url: str,
    headers: dict[str, str],
    expected_size: int = 0,
) -> dict[str, str | int]:
    if not allowed_url(url):
        raise PermissionError("url host not allowed")
    destination = safe_dest(root, dest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request_headers = {str(k): str(v) for k, v in headers.items()}
    request_headers["User-Agent"] = "okhttp/4.12.0"
    request = urllib.request.Request(url, headers=request_headers)
    fd, temp_name = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".part", dir=destination.parent
    )
    os.close(fd)
    temp = Path(temp_name)
    digest = hashlib.md5()
    size = 0
    first = b""
    try:
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"IMA PDF HTTP {exc.code}") from exc
        with response, temp.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                if size + len(chunk) > MAX_PDF_BYTES:
                    raise RuntimeError("IMA PDF too large")
                if not first:
                    first = chunk[:8]
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if not first.startswith(b"%PDF-1."):
            raise RuntimeError("IMA download is not a PDF")
        if expected_size and size != int(expected_size):
            raise RuntimeError(f"IMA PDF size mismatch got={size} expected={expected_size}")
        os.replace(temp, destination)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return {"size": size, "md5": digest.hexdigest(), "path": str(destination)}
```

Keep later HTTP helpers out of this file until Task 2. Tests import `MAX_PDF_BYTES` — define it here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ima_puller.py -q --tb=short`

Expected: PASS (the four tests above)

- [ ] **Step 5: Commit**

```bash
git add app/ima_puller.py tests/test_ima_puller.py
git commit -m "feat: add IMA puller path lock and atomic PDF write"
```

---

### Task 2: Puller HTTP server

**Files:**
- Modify: `app/ima_puller.py`
- Test: `tests/test_ima_puller.py`

- [ ] **Step 1: Write the failing HTTP tests**

Append to `tests/test_ima_puller.py`:

```python
import json
import threading
import urllib.error
import urllib.request

from app.ima_puller import serve_puller


def _start(tmp_path, monkeypatch, token="secret"):
    import app.ima_puller as puller

    class Resp:
        def read(self, n):
            data = getattr(self, "_data", b"%PDF-1.7xxxx")
            self._data = b""
            return data[:n]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(puller.urllib.request, "urlopen", lambda req, timeout=120: Resp())
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
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ima_puller.py::test_pull_requires_token tests/test_ima_puller.py::test_pull_writes_pdf -q --tb=line`

Expected: FAIL with `ImportError: cannot import name 'serve_puller'`

- [ ] **Step 3: Add the HTTP server**

Append to `app/ima_puller.py`:

```python
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class PullError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _error_status(exc: Exception) -> int:
    text = str(exc)
    if isinstance(exc, PermissionError):
        return 400
    if isinstance(exc, ValueError):
        return 400
    if "HTTP 403" in text:
        return 403
    if "not a PDF" in text:
        return 415
    if "size mismatch" in text:
        return 409
    if "too large" in text:
        return 413
    if "HTTP" in text:
        return 502
    return 502


def make_handler(root: Path, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, status: int, body: bytes, content_type: str = "text/plain") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] != "/healthz":
                self._send(404, b"no")
                return
            self._send(200, b"ok")

        def do_POST(self) -> None:
            if self.path.split("?", 1)[0] != "/pull":
                self._send(404, b"no")
                return
            if self.headers.get("Authorization") != f"Bearer {token}":
                self._send(401, b"auth")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._send(400, b"length")
                return
            if length <= 0 or length > MAX_JSON_BYTES:
                self._send(413, b"too big")
                return
            try:
                payload = json.loads(self.rfile.read(length).decode())
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._send(400, b"json")
                return
            if not isinstance(payload, dict):
                self._send(400, b"json")
                return
            dest = str(payload.get("dest") or "")
            url = str(payload.get("url") or "")
            headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else {}
            try:
                expected = int(payload.get("expected_size") or 0)
            except (TypeError, ValueError):
                expected = 0
            try:
                result = save_pdf(root, dest, url, headers, expected)
            except Exception as exc:  # noqa: BLE001
                self._send(_error_status(exc), str(exc).encode()[:200])
                return
            body = json.dumps({"size": result["size"], "md5": result["md5"]}).encode()
            self._send(200, body, "application/json")

    return Handler


def serve_puller(root: Path, token: str, host: str = "127.0.0.1", port: int = 8743) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("pull token required")
    return ThreadingHTTPServer((host, port), make_handler(Path(root), token))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8743)
    parser.add_argument("--token-file", required=True)
    args = parser.parse_args()
    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    server = serve_puller(Path(args.root), token, host=args.bind, port=args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
```

Do not log `url`, `sign`, or token. `log_message` is a no-op on purpose.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_ima_puller.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_puller.py tests/test_ima_puller.py
git commit -m "feat: add WireGuard IMA pull HTTP server"
```

---

### Task 3: Client download uses puller when configured

**Files:**
- Modify: `app/ima_documents.py` (`ImaPureClient.download`, around line 1080)
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ima_documents.py` (reuse existing `ImaDocumentConfig` / `ImaPureClient` imports):

```python
def test_download_posts_to_puller_when_url_configured(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    seen = {}

    class FakeResponse:
        def read(self):
            return json.dumps({"size": 8, "md5": "d" * 32}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=120):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        seen["body"] = json.loads(req.data.decode())
        return FakeResponse()

    monkeypatch.setenv("IMA_PULL_URL", "http://10.80.0.2:8743/pull")
    monkeypatch.setenv("IMA_PULL_TOKEN", "tok")
    monkeypatch.setenv("IMA_ARCHIVE_ROOT", str(archive))
    monkeypatch.setattr(ima_documents.urllib.request, "urlopen", fake_urlopen)
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    dest = archive / "g" / "a.pdf"
    result = client.download(
        {
            "jump_url_info": {
                "url": "https://res-skb.ima.qq.com/file.pdf?sign=1",
                "headers": {"X-IMA-Sign": "sig"},
            }
        },
        dest,
        expected_size=8,
    )
    assert seen["url"] == "http://10.80.0.2:8743/pull"
    assert seen["auth"] == "Bearer tok"
    assert seen["body"]["dest"] == "g/a.pdf"
    assert seen["body"]["headers"]["X-IMA-Sign"] == "sig"
    assert result["size"] == 8
    assert result["md5"] == "d" * 32
```

`tests/test_ima_documents.py` already imports `json` and patches `ima_documents.urllib.request.urlopen` elsewhere; do the same here.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py::test_download_posts_to_puller_when_url_configured -q --tb=short`

Expected: FAIL (current `download()` talks to the CDN URL, not the puller)

- [ ] **Step 3: Implement puller branch in `download()`**

Replace `ImaPureClient.download` so the first lines after resolving `url`/`headers` are:

```python
        pull_url = os.environ.get("IMA_PULL_URL", "").strip()
        if pull_url:
            archive_root = Path(os.environ.get("IMA_ARCHIVE_ROOT", "")).expanduser()
            if not str(archive_root):
                raise RuntimeError("IMA_ARCHIVE_ROOT required when IMA_PULL_URL is set")
            dest = str(destination.resolve().relative_to(archive_root.resolve()))
            payload = json.dumps(
                {
                    "dest": dest,
                    "url": str(url),
                    "headers": headers,
                    "expected_size": int(expected_size or 0),
                },
                ensure_ascii=False,
            ).encode()
            request = urllib.request.Request(
                pull_url,
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + os.environ.get("IMA_PULL_TOKEN", "").strip(),
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    body = json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"IMA PDF HTTP {exc.code}") from exc
            return {
                "size": int(body.get("size") or 0),
                "md5": str(body.get("md5") or ""),
                "path": str(destination),
            }
```

Keep the existing local urllib/`.part`/`os.replace` path in an `else` (current code unchanged). Local tests that do not set `IMA_PULL_URL` stay on that path.

- [ ] **Step 4: Run related tests**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py tests/test_ima_puller.py -q --tb=line`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "feat: download IMA PDFs through storage puller when configured"
```

---

### Task 4: Retry expired CDN links once; skip DMIT mkdir when pulling

**Files:**
- Modify: `app/ima_documents.py` (`_fetch` inside `_sync_group`, around line 2328)
- Test: `tests/test_ima_documents.py`

- [ ] **Step 1: Write the failing test**

```python
def test_sync_retries_get_media_after_pdf_http_403(tmp_path, monkeypatch):
    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    calls = {"get_media": 0, "download": 0}

    class FakeClient:
        def __init__(self, config, group=None):
            self.config = config

        def manifest(self, listing_cache=None):
            return [{"media_id": "file_new", "name": "n.pdf", "day": "0829", "size": 8}]

        def get_media(self, media_id):
            calls["get_media"] += 1
            return {"jump_url_info": {"url": "https://res-skb.ima.qq.com/n.pdf", "headers": {}}}

        def download(self, media, destination, expected_size=0):
            calls["download"] += 1
            if calls["download"] == 1:
                raise RuntimeError("IMA PDF HTTP 403")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"%PDF-1.7")
            return {"size": 8, "md5": "d" * 32, "path": str(destination)}

        def _pdf_info(self, path):
            return 8, "d" * 32

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    result = service.sync_once()
    assert calls["get_media"] == 2
    assert calls["download"] == 2
    assert result["downloaded"] == 1
```

Use the same `FakeDB` / settings keys already used by `test_sync_restores_legacy_hashed_files_without_redownload`. If `sync_once` requires enabled groups from settings, copy that fixture's settings plus a groups JSON with one enabled group and `folder_ids` so listing runs. If the default config already enables the legacy kb/root pair, the snippet above is enough.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py::test_sync_retries_get_media_after_pdf_http_403 -q --tb=short`

Expected: FAIL (`get_media` called once, `downloaded == 0`)

- [ ] **Step 3: Change `_fetch`**

Replace the download branch:

```python
            pull_url = os.environ.get("IMA_PULL_URL", "").strip()
            if not pull_url:
                pdf.parent.mkdir(parents=True, exist_ok=True)
            if pdf.parent.is_symlink():
                raise ValueError("archive directory must not be a symlink")
            if (not pull_url) and pdf.is_file():
                size, md5 = client._pdf_info(pdf)
                if record.get("size") and size != int(record["size"]):
                    pdf.unlink(missing_ok=True)
            if pull_url or not pdf.is_file():
                last_error: Exception | None = None
                for _ in range(2):
                    media = client.get_media(media_id)
                    try:
                        result = client.download(media, pdf, int(record.get("size") or 0))
                        return record, pdf, int(result["size"]), str(result["md5"])
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                        if "HTTP 403" not in str(exc):
                            raise
                raise last_error
            size, md5 = client._pdf_info(pdf)
            return record, pdf, int(size), str(md5)
```

When `IMA_PULL_URL` is set, skip DMIT `mkdir` and skip NFS `is_file()` before GET so 8 workers are not blocked on `stat`. Completeness still comes from `state.json`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_ima_documents.py tests/test_ima_puller.py tests/test_ima_storage.py -q --tb=line`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ima_documents.py tests/test_ima_documents.py
git commit -m "fix: retry IMA PDF 403 once and skip NFS mkdir when pulling"
```

---

### Task 5: Compose and env wiring

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `docker-compose.yml` (same two env keys if that file already lists `IMA_ARCHIVE_ROOT`)
- Modify: `.env.example`

- [ ] **Step 1: Add env keys**

In `docker-compose.prod.yml` `vpush.environment`, next to `IMA_ARCHIVE_ROOT`:

```yaml
      - IMA_PULL_URL=${IMA_PULL_URL:-}
      - IMA_PULL_TOKEN=${IMA_PULL_TOKEN:-}
```

Mirror in `docker-compose.yml` if it has an `environment:` block for vpush.

In `.env.example` after `IMA_ARCHIVE_HOST_PATH=`:

```text
# 存储机直下：DMIT 只 POST 签名链接，PDF GET 在存储机。留空则仍由容器本机下载。
# IMA_PULL_URL=http://10.80.0.2:8743/pull
IMA_PULL_URL=
IMA_PULL_TOKEN=
```

- [ ] **Step 2: Confirm compose still interpolates**

Run: `python3 -c "from pathlib import Path; t=Path('docker-compose.prod.yml').read_text(); assert 'IMA_PULL_URL' in t and 'IMA_PULL_TOKEN' in t"`

Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add docker-compose.prod.yml docker-compose.yml .env.example
git commit -m "chore: pass IMA puller URL and token into compose"
```

If `docker-compose.yml` has no IMA env block, skip that file and say so in the commit body.

---

### Task 6: systemd unit and runbook

**Files:**
- Create: `deploy/ima-storage/vpush-ima-puller.service`
- Modify: `deploy/ima-storage/README.md`

- [ ] **Step 1: Add the unit**

`deploy/ima-storage/vpush-ima-puller.service`:

```ini
[Unit]
Description=V Push IMA storage PDF puller
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=99
Group=100
UMask=0077
NoNewPrivileges=true
ExecStart=/usr/bin/python3 /usr/local/lib/vpush-ima/ima-puller.py --root /srv/vpush-ima --bind 10.80.0.2 --port 8743 --token-file /etc/vpush/ima-pull.token
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Extend the runbook**

Append to `deploy/ima-storage/README.md`:

```markdown
## Storage PDF puller

Install the stdlib server (no pip):

```bash
install -m 755 app/ima_puller.py /usr/local/lib/vpush-ima/ima-puller.py
install -m 644 deploy/ima-storage/vpush-ima-puller.service /etc/systemd/system/
install -m 640 /dev/null /etc/vpush/ima-pull.token
chown 99:100 /etc/vpush/ima-pull.token
```

Put the same random token in `/etc/vpush/ima-pull.token` (storage) and `/opt/vpush/.env` as `IMA_PULL_TOKEN` (DMIT). Set `IMA_PULL_URL=http://10.80.0.2:8743/pull`. Values never go on the shell command line or into Git.

```bash
systemctl daemon-reload
systemctl enable --now vpush-ima-puller.service
curl -sS --interface 10.80.0.2 http://10.80.0.2:8743/healthz
```

Expected: `ok`. `ss -tlnp | grep 8743` must show `10.80.0.2:8743` only, not `0.0.0.0` or the public IP.

On DMIT, recreate `vpush` after editing `.env`. Rollback: delete `IMA_PULL_URL` / `IMA_PULL_TOKEN` from `.env`, recreate `vpush`; optionally `systemctl stop vpush-ima-puller`.
```

- [ ] **Step 3: Commit**

```bash
git add deploy/ima-storage/vpush-ima-puller.service deploy/ima-storage/README.md
git commit -m "docs: install IMA storage puller on WireGuard only"
```

---

## Production rollout (after Task 6, same engineer)

Not extra product scope — just the enablement order:

1. Install puller on `198.12.125.212`, confirm `healthz` via `10.80.0.2`.
2. Set env on DMIT, recreate `vpush`, trigger one IMA sync.
3. Confirm new PDFs appear under `/mnt/vpush-ima` and `ss` on DMIT shows fewer `:443` connections to `res-skb.ima.qq.com` / `43.159.*`, plus `10.80.0.2:8743`.
4. If IMA `429`/`51`, drop `IMA_DOWNLOAD_WORKERS` to 4. If puller errors, unset `IMA_PULL_URL` and recreate.

Do not copy IMA refresh tokens onto the storage VPS.

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Sync RPC, no queue | 2, 3 |
| Path lock, `*.ima.qq.com`, `.pdf` only | 1 |
| Token, bind `10.80.0.2:8743` | 2, 6 |
| `download()` uses puller when env set | 3 |
| Local path unchanged when env empty | 3 |
| 403 → one more `get_media` | 4 |
| Skip DMIT mkdir when pulling | 4 |
| Compose / `.env.example` | 5 |
| systemd + runbook + rollback | 6 |
| NFS kept for reads | no code change |
| No IMA token on storage | 6 |

## Placeholder scan

No TBD / “handle edge cases later”. 403 mapping, size cap, and host allowlist are in Task 1–2 code.
