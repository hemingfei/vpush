"""把被墙图床（主要是 X）的配图异步镜像到自建 CloudFlare ImgBed。

采集仍写入原始 URL；展示时优先用图床公开地址，失败则退回 /api/img-proxy。
"""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import threading
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx

from .avatar_cache import headers_for
from .logging_setup import redact_secrets
from .url_safety import is_safe_http_url, safe_get_limited

logger = logging.getLogger(__name__)

SOURCE_HOSTS = frozenset({
    "pbs.twimg.com",
    "video.twimg.com",
    "abs.twimg.com",
    "static-assets-1.truthsocial.com",
})
ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_BYTES = 10 * 1024 * 1024
UPLOAD_TIMEOUT = 30
BATCH_LIMIT = 8
RETRY_AFTER = timedelta(minutes=15)
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

_config = None


def configure(config) -> None:
    global _config
    _config = getattr(config, "imgbed", None)


def current_config():
    return _config


def enabled(config=None) -> bool:
    cfg = config if config is not None else _config
    if cfg is None:
        return False
    cfg = getattr(cfg, "imgbed", cfg)
    return bool(getattr(cfg, "base_url", "") and getattr(cfg, "token", ""))


def source_host(url: str) -> str:
    try:
        host = urlparse(url).hostname
    except Exception:
        return ""
    return (host or "").lower()


def is_source_url(url: str) -> bool:
    host = source_host(url)
    return host in SOURCE_HOSTS


def public_host() -> str:
    cfg = current_config()
    host = source_host(getattr(cfg, "base_url", "") if cfg is not None else "")
    return host or "img.053727.xyz"


def public_url(url: str) -> bool:
    return source_host(url) == public_host()


def enqueue_urls(db, urls: list[str] | None) -> int:
    if not enabled() or not urls:
        return 0
    queued = 0
    for url in urls:
        raw = (url or "").strip()
        if not is_source_url(raw):
            continue
        if db.enqueue_hosted_image(raw):
            queued += 1
    return queued


def display_url(db, url: str) -> str:
    raw = (url or "").strip()
    if not raw or public_url(raw) or not is_source_url(raw):
        return raw
    hosted = db.hosted_image_url(raw)
    return hosted or raw


def rewrite_urls(db, urls: list[str] | None) -> list[str]:
    if not urls:
        return []
    return [display_url(db, url) for url in urls]


def enqueue_recent_posts(db, limit: int = 40) -> int:
    rows = db.recent_mirrorable_image_rows(limit=limit)
    queued = 0
    for row in rows:
        raw = row.get("images") or ""
        try:
            urls = json.loads(raw) if isinstance(raw, str) and raw.startswith("[") else []
        except (TypeError, ValueError):
            urls = []
        queued += enqueue_urls(db, urls if isinstance(urls, list) else [])
    return queued


def apply_runtime(base_url: str, token: str, channel: str = "", channel_name: str = "", folder: str = "") -> None:
    from .config import ImgbedConfig

    current = current_config() or ImgbedConfig()
    configure(
        type("ImgbedRuntime", (), {"imgbed": ImgbedConfig(
            base_url=base_url or current.base_url,
            token=token or current.token,
            channel=channel or current.channel,
            channel_name=channel_name or current.channel_name,
            folder=folder or current.folder,
        )})()
    )


def probe(base_url: str) -> tuple[bool, str]:
    """轻量连通检查：主机应答（含 4xx）即算可达；网络错误/5xx 判失败。"""
    url = (base_url or "").strip()
    if not url:
        return False, "未配置图床地址"
    try:
        with _http_client(timeout=5, follow_redirects=False) as client:
            resp = client.get(url.rstrip("/") + "/", headers={"User-Agent": BROWSER_UA})
    except Exception as exc:  # noqa: BLE001 - 探测失败是结果不是异常
        return False, redact_secrets(f"{type(exc).__name__}: {exc}")[:200]
    if resp.status_code < 500:
        return True, ""
    return False, f"图床返回 HTTP {resp.status_code}"


def reset_to_env() -> None:
    """清除库内配置后回到环境变量/默认值。"""
    import os

    from .config import ImgbedConfig

    configure(type("ImgbedRuntime", (), {"imgbed": ImgbedConfig(
        base_url=os.environ.get("IMGBED_BASE_URL", "").strip(),
        token=os.environ.get("IMGBED_TOKEN", "").strip(),
        channel=os.environ.get("IMGBED_CHANNEL", "") or "telegram",
        channel_name=os.environ.get("IMGBED_CHANNEL_NAME", "") or "vpush-imgbed",
        folder=os.environ.get("IMGBED_FOLDER", "") or "vpush",
    )})())


def process_pending(db, config=None, limit: int = BATCH_LIMIT) -> int:
    if config is None:
        cfg = _config
    else:
        cfg = getattr(config, "imgbed", None) or config
    if not enabled(cfg):
        return 0
    enqueue_recent_posts(db)
    rows = db.list_pending_hosted_images(limit=limit)
    done = 0
    for row in rows:
        if _mirror_one(db, cfg, row):
            done += 1
    return done


def _mirror_one(db, cfg, row: dict) -> bool:
    source_url = (row.get("source_url") or "").strip()
    if not is_source_url(source_url):
        db.mark_hosted_image(source_url, status="skipped", last_error="非白名单图床")
        return False
    if not is_safe_http_url(source_url):
        db.mark_hosted_image(source_url, status="skipped", last_error="不安全的下载地址")
        return False
    existing = db.hosted_image_url(source_url)
    if existing:
        return False
    try:
        content, content_type = _download(source_url)
        digest = hashlib.sha256(content).hexdigest()
        reused = db.hosted_image_url_by_hash(digest)
        if reused:
            db.mark_hosted_image(
                source_url,
                status="ready",
                hosted_url=reused,
                content_hash=digest,
            )
            _prewarm_hosted_async(reused)
            return True
        hosted = _upload(cfg, source_url, content, content_type)
        db.mark_hosted_image(
            source_url,
            status="ready",
            hosted_url=hosted,
            content_hash=digest,
        )
        _prewarm_hosted_async(hosted)
        return True
    except Exception as exc:  # noqa: BLE001 - 镜像失败不能影响抓取
        db.mark_hosted_image(
            source_url,
            status="failed",
            last_error=redact_secrets(exc)[:300],
        )
        logger.warning("图床镜像失败 url=%s err=%s", source_url[:120], type(exc).__name__)
        return False


def _http_client(**kwargs) -> httpx.Client:
    return httpx.Client(**kwargs)


def _prewarm_hosted_async(hosted_url: str) -> None:
    """镜像成功后立刻拉一次公开地址，把 CF 边缘缓存烧热（新图首访不再吃 7-14s 冷启动）。"""
    if not hosted_url:
        return
    threading.Thread(target=_prewarm_hosted, args=(hosted_url,), daemon=True).start()


def _prewarm_hosted(hosted_url: str) -> None:
    try:
        with _http_client(timeout=15, follow_redirects=False) as client:
            client.get(hosted_url, headers={"User-Agent": BROWSER_UA})
    except Exception:  # noqa: BLE001 - 预热失败不影响镜像
        pass


def _download(url: str) -> tuple[bytes, str]:
    client = _http_client(timeout=15, follow_redirects=False, headers=headers_for(url))
    try:
        resp = safe_get_limited(client, url, max_bytes=MAX_BYTES, timeout=15)
    finally:
        client.close()
    if resp.status_code != 200 or not resp.content:
        raise RuntimeError(f"源图下载失败 HTTP {resp.status_code}")
    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_TYPES:
        raise RuntimeError(f"非图片内容 {content_type or 'unknown'}")
    if len(resp.content) <= 2048:
        raise RuntimeError("图片过小")
    return resp.content, content_type


def _upload(cfg, source_url: str, content: bytes, content_type: str) -> str:
    ext = ALLOWED_TYPES[content_type]
    filename = f"{hashlib.sha1(source_url.encode()).hexdigest()[:16]}.{ext}"
    guessed = mimetypes.guess_type(filename)[0] or content_type
    params = {
        "uploadChannel": cfg.channel or "telegram",
        "returnFormat": "full",
        "uploadNameType": "index",
        "serverCompress": "false",
    }
    if cfg.channel_name:
        params["channelName"] = cfg.channel_name
    if cfg.folder:
        params["uploadFolder"] = cfg.folder.strip("/")
    files = {"file": (filename, content, guessed)}
    headers = {
        "Authorization": f"Bearer {cfg.token}",
        "User-Agent": BROWSER_UA,
        "Origin": cfg.base_url.rstrip("/"),
        "Referer": cfg.base_url.rstrip("/") + "/",
    }
    with _http_client(timeout=UPLOAD_TIMEOUT, follow_redirects=False) as client:
        resp = client.post(
            cfg.base_url.rstrip("/") + "/upload",
            params=params,
            files=files,
            headers=headers,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"图床上传失败 HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise RuntimeError("图床上传响应不是 JSON") from exc
    hosted = _extract_hosted_url(payload, cfg.base_url)
    if not hosted:
        raise RuntimeError("图床上传未返回公开地址")
    if not hosted.startswith(cfg.base_url.rstrip("/") + "/"):
        raise RuntimeError("图床返回了非本域地址")
    return hosted


def _extract_hosted_url(payload, base_url: str) -> str:
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("publicUrl", "src"):
            raw = str(item.get(key) or "").strip()
            if not raw:
                continue
            if raw.startswith("/"):
                return base_url.rstrip("/") + raw
            return raw
    return ""


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def retry_cutoff() -> str:
    return (datetime.now(UTC) - RETRY_AFTER).strftime("%Y-%m-%d %H:%M:%S")
