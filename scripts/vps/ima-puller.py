#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

MAX_PDF_BYTES = 200 * 1024 * 1024
MAX_JSON_BYTES = 1_000_000
RANGE_MIN_BYTES = 8 * 1024 * 1024
RANGE_PARTS = 4


@contextmanager
def path_lock(destination: Path):
    fd = os.open(destination.parent, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


class AllowedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise PermissionError("redirect url host not allowed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


log = logging.getLogger("ima-puller")


def allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and host.endswith(".ima.qq.com")


def safe_dest(root: Path, dest: str) -> Path:
    text = str(dest or "").replace("\\", "/").lstrip("/")
    if not text.endswith(".pdf") or text.endswith("/.pdf"):
        raise ValueError("dest must be a .pdf path")
    root = root.resolve()
    current = root
    for part in Path(text).parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError("archive directory must not be a symlink")
    candidate = (root / text).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("dest escapes archive root")
    if candidate.parent.exists() and candidate.parent.is_symlink():
        raise ValueError("archive directory must not be a symlink")
    return candidate


def _http_open(request: urllib.request.Request):
    try:
        opener = urllib.request.build_opener(AllowedRedirectHandler())
        return opener.open(request, timeout=120)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"IMA PDF HTTP {exc.code}") from exc


def _read_limited(response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_PDF_BYTES:
            raise RuntimeError("IMA PDF too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _download_ranged(url: str, headers: dict[str, str], expected_size: int) -> bytes:
    chunk = (expected_size + RANGE_PARTS - 1) // RANGE_PARTS
    spans = []
    for index in range(RANGE_PARTS):
        start = index * chunk
        end = min(expected_size - 1, (index + 1) * chunk - 1)
        if start <= end:
            spans.append((start, end))

    def fetch(span: tuple[int, int]) -> tuple[int, bytes]:
        start, end = span
        part_headers = dict(headers)
        part_headers["Range"] = f"bytes={start}-{end}"
        request = urllib.request.Request(url, headers=part_headers)
        with _http_open(request) as response:
            data = _read_limited(response)
        expect = end - start + 1
        if len(data) != expect:
            raise RuntimeError(f"IMA PDF HTTP range length got={len(data)} expected={expect}")
        return start, data

    with ThreadPoolExecutor(max_workers=len(spans)) as pool:
        parts = list(pool.map(fetch, spans))
    parts.sort(key=lambda item: item[0])
    return b"".join(data for _, data in parts)


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
    fd, temp_name = tempfile.mkstemp(
        prefix=".vpush-", suffix=".part", dir=destination.parent
    )
    os.close(fd)
    temp = Path(temp_name)
    digest = hashlib.md5()
    size = 0
    first = b""
    try:
        if int(expected_size or 0) >= RANGE_MIN_BYTES:
            data = _download_ranged(url, request_headers, int(expected_size))
            first = data[:8]
            size = len(data)
            if not first.startswith(b"%PDF-1."):
                raise RuntimeError("IMA download is not a PDF")
            if expected_size and size != int(expected_size):
                raise RuntimeError(f"IMA PDF size mismatch got={size} expected={expected_size}")
            digest.update(data)
            temp.write_bytes(data)
        else:
            request = urllib.request.Request(url, headers=request_headers)
            response = _http_open(request)
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
        with path_lock(destination):
            os.replace(temp, destination)
        log.info("saved %s (%d bytes)", destination, size)
    except Exception as exc:
        log.warning("save failed %s: %s", destination, exc)
        temp.unlink(missing_ok=True)
        raise
    return {"size": size, "md5": digest.hexdigest(), "path": str(destination)}


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
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 36:
        return 400
    if "File name too long" in text or "ENAMETOOLONG" in text:
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
                log.warning("pull auth failed from %s", self.client_address[0])
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
                log.warning("pull failed dest=%s: %s", dest, exc)
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
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    server = serve_puller(Path(args.root), token, host=args.bind, port=args.port)
    log.info("ima-puller listening bind=%s port=%s root=%s", args.bind, args.port, args.root)
    server.serve_forever()


if __name__ == "__main__":
    main()
