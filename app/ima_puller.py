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
