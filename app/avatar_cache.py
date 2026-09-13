"""头像本地缓存：把远端头像下载到数据目录并返回本地 URL。

解决第三方图床（sinaimg / pbs.twimg 等）签名链接过期、外链被拦截导致的头像显示失败。
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .url_safety import safe_get_limited

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

# 平台 → (数据目录名, 本地 URL 前缀)：采集侧 cache_image_file、补缓存 image_backfill、
# 清理 image_cleanup、静态挂载 main.py 全部引用此唯一映射，防止新增平台时漏改某处。
PLATFORM_IMAGE_DIRS = {
    "mx": ("mx_images", "/mx-images"),
    "zsxq": ("zsxq_images", "/zsxq-images"),
    "xueqiu": ("xq_images", "/xq-images"),
    "weibo": ("weibo_images", "/weibo-images"),
}
MAX_BYTES = 5 * 1024 * 1024
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# 新浪图床有防盗链校验，需带 weibo.com Referer 才能下载；对 X/雪球图床无副作用
DOWNLOAD_HEADERS = {"User-Agent": UA, "Referer": "https://weibo.com/"}
ZSXQ_HEADERS = {"User-Agent": UA, "Referer": "https://wx.zsxq.com/"}
# MX 图片/头像必须用 MX 站点的浏览器形态下载：之前错误地带 weibo.com Referer，
# 在 MX 自家 CDN 的日志里又是一个「账号行为自相矛盾」的风控信号
MX_SITE_DOMAIN = "naaifu.cn"
MX_REFERER = "https://mx.2026.naaifu.cn/"

# .part 临时文件清扫：写盘中断（进程崩溃/断电）会留下残留，超龄（1 小时）即清；
# 下载函数被 WS 解析线程高频调用，清扫入口按小时节流
_PART_MAX_AGE_SECONDS = 3600.0
_PART_CLEANUP_INTERVAL_SECONDS = 3600.0
_last_part_cleanup_monotonic = 0.0

# 图片直连（不缓存）策略：settings 键与默认名单。名单内域名的帖子图片不做
# 服务端下载缓存，保留原始外链由浏览器直接访问（如钉钉 CDN 国内直连快、
# 服务端下载反而慢且有风控）；图片补缓存任务同样跳过这些域名。
DIRECT_HOSTS_SETTING = "image_direct_hosts"
DEFAULT_DIRECT_HOSTS = "static.dingtalk.com"

# 域名形态校验：一段或多段「字母数字连字符」标签，至少两段（必须有 TLD）
_HOST_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)

# 直连名单缓存：名单变更频率极低，但 should_direct_access 被采集入库和补缓存
# 热循环逐 URL 调用，每次查库+解析字符串开销不必要。30 秒 TTL 足够管理员改完
# 策略后快速生效，同时消除每轮补缓存 ~200 次冗余 DB 读。
_DIRECT_HOSTS_CACHE: dict = {"db_path": None, "raw": None, "hosts": [], "expires": 0.0}
_DIRECT_HOSTS_TTL = 30.0


def normalize_direct_hosts(entries) -> list[str]:
    """清洗直连域名列表：小写、去尾点、去空、去重保序；非法条目抛 ValueError。"""
    out: list[str] = []
    seen: set[str] = set()
    for entry in entries or []:
        host = str(entry or "").strip().lower().rstrip(".")
        if not host:
            continue
        if not _HOST_RE.match(host):
            raise ValueError(f"非法域名：{entry}")
        if host not in seen:
            seen.add(host)
            out.append(host)
    return out


def _parse_direct_hosts(raw: str) -> list[str]:
    """settings 存储值 → 域名列表（容忍逗号/换行混用与空白）。"""
    hosts: list[str] = []
    for chunk in (raw or "").replace(",", "\n").split("\n"):
        host = chunk.strip().lower().rstrip(".")
        if host:
            hosts.append(host)
    return hosts


def direct_access_hosts(db) -> list[str]:
    """读取直连域名名单；从未配置时用默认名单。

    带 30 秒 TTL 内存缓存：should_direct_access 被采集/补缓存热循环逐 URL
    调用，名单变更极少，缓存消除每轮数百次冗余 DB 读+字符串解析。
    """
    now = time.time()
    db_path = str(getattr(db, "path", "") or "")
    cache = _DIRECT_HOSTS_CACHE
    raw = db.get_setting(DIRECT_HOSTS_SETTING)
    if raw is None:
        raw = DEFAULT_DIRECT_HOSTS
    if (
        cache["db_path"] == db_path
        and cache["raw"] == raw
        and now < cache["expires"]
    ):
        return cache["hosts"]
    hosts = _parse_direct_hosts(raw)
    cache.update(db_path=db_path, raw=raw, hosts=hosts, expires=now + _DIRECT_HOSTS_TTL)
    return hosts


def should_direct_access(db, url: str) -> bool:
    """URL 是否命中直连名单：host 精确相等或是名单域名的子域名。"""
    host = (urlparse(str(url or "")).hostname or "").lower()
    if not host:
        return False
    for entry in direct_access_hosts(db):
        if host == entry or host.endswith("." + entry):
            return True
    return False


def _cleanup_stale_part_files(dest: Path) -> None:
    """清扫目录内超龄的 .part 临时文件（正常流程写完即原子替换，残留即异常痕迹）。"""
    now = time.time()
    try:
        for part in dest.glob("*.part"):
            try:
                if now - part.stat().st_mtime > _PART_MAX_AGE_SECONDS:
                    part.unlink(missing_ok=True)
            except OSError:  # noqa: BLE001 - 单个文件清不掉不影响其他文件
                continue
    except OSError:  # noqa: BLE001 - 目录不可读时放弃本次清扫
        return


def _maybe_cleanup_part_files(dest: Path) -> None:
    """节流清扫入口：每小时最多实际扫一次目录。"""
    global _last_part_cleanup_monotonic
    now = time.monotonic()
    if now - _last_part_cleanup_monotonic < _PART_CLEANUP_INTERVAL_SECONDS:
        return
    _last_part_cleanup_monotonic = now
    _cleanup_stale_part_files(dest)


def headers_for(url: str) -> dict[str, str]:
    if "zsxq.com" in (url or ""):
        return dict(ZSXQ_HEADERS)
    if MX_SITE_DOMAIN in (url or ""):
        # 延迟导入：app.fetchers.mx 包初始化会反向导入本模块，顶层导入会成环
        from .fetchers.mx.ws import BROWSER_UA

        return {"User-Agent": BROWSER_UA, "Referer": MX_REFERER}
    return dict(DOWNLOAD_HEADERS)


def cache_image_file(db, url: str, folder: str, url_prefix: str, client: httpx.Client | None = None) -> str | None:
    """下载图片到数据目录 folder，返回本地 URL；内存库或下载失败时保留原 URL。

    返回 None 表示服务端 200 但 content-type 不是图片（内容确定性非图片，
    如网页链接卡片），调用方可据此降级处理；下载失败等不确定情况仍返回原 URL。
    """
    url = (url or "").strip()
    if not url or url.startswith("/"):
        return url
    db_path = str(getattr(db, "path", "") or "")
    if not db_path or db_path == ":memory:":
        return url
    dest = Path(db_path).parent / folder
    dest.mkdir(parents=True, exist_ok=True)
    _maybe_cleanup_part_files(dest)
    # 键必须是完整 URL 的函数：CDN 常用顺序/短文件名，取远程文件名会让
    # 不同帖子同名图片互相覆盖，引用旧内容的帖子永久显示错图
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    for ext in ALLOWED_TYPES.values():
        existing = dest / f"{key}.{ext}"
        if existing.exists() and existing.stat().st_size > 2048:
            return f"{url_prefix}/{existing.name}"
    owns_client = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=True, headers=headers_for(url))
    try:
        resp = safe_get_limited(
            client, url, max_bytes=MAX_BYTES, headers=headers_for(url), timeout=15
        )
        if resp.status_code != 200 or not resp.content:
            return url
        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        ext = ALLOWED_TYPES.get(content_type)
        if not ext:
            # 200 但内容不是图片（网页/文件等），与「下载失败」区分开
            return None
        if len(resp.content) <= 2048:
            return url
        target = dest / f"{key}.{ext}"
        # WS 解析已并发跑在线程池里，同一 URL 可能被两个线程同时下载缓存：
        # 先写临时文件再原子替换，避免交错写同一目标文件产出坏图
        tmp = dest / f"{key}.{uuid.uuid4().hex[:8]}.part"
        try:
            tmp.write_bytes(resp.content)
            os.replace(tmp, target)
        except OSError:
            tmp.unlink(missing_ok=True)
            return url
        return f"{url_prefix}/{target.name}"
    except Exception:  # noqa: BLE001 - 下载失败/响应过大等退回原 URL
        logger.debug("cache_image_file 下载失败: %s", url[:120], exc_info=True)
        return url
    finally:
        if owns_client:
            client.close()


def cache_avatar(db, kol_id: int, remote_url: str, client: httpx.Client | None = None) -> str:
    """下载并缓存头像到本地，返回本地 URL；无需缓存或失败时原样返回远端 URL。"""
    url = (remote_url or "").strip()
    if not url or url.startswith("/avatars/"):
        return url
    kol = db.get_kol(kol_id)
    local = (kol.get("avatar_url") or "") if kol else ""
    if kol and kol.get("avatar_source") == url and local.startswith("/avatars/"):
        cached = Path(db.path).parent / local.lstrip("/")
        if cached.is_file() and cached.stat().st_size > 0:
            return local
    owns_client = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=True, headers=headers_for(url))
    try:
        resp = safe_get_limited(
            client, url, max_bytes=MAX_BYTES, headers=headers_for(url), timeout=15
        )
        if resp.status_code != 200 or not resp.content:
            return url
        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        ext = ALLOWED_TYPES.get(content_type)
        if not ext or len(resp.content) > MAX_BYTES:
            return url
        avatars = Path(db.path).parent / "avatars"
        avatars.mkdir(parents=True, exist_ok=True)
        _maybe_cleanup_part_files(avatars)
        target = avatars / f"{kol_id}.{ext}"
        # 与 cache_image_file 同口径：先写临时文件再原子替换，避免并发写同一
        # 目标文件（或写盘中断）产出坏图/半张头像
        tmp = avatars / f"{kol_id}.{uuid.uuid4().hex[:8]}.part"
        try:
            tmp.write_bytes(resp.content)
            os.replace(tmp, target)
        except OSError:  # noqa: BLE001 - 写盘失败退回远端 URL，并清掉残留临时文件
            tmp.unlink(missing_ok=True)
            return url
        local = f"/avatars/{kol_id}.{ext}"
        db.update_kol_avatar(kol_id, local)
        db.update_kol_avatar_source(kol_id, url)
        return local
    except Exception:  # noqa: BLE001 - 缓存失败退回远端 URL
        logger.debug("cache_avatar 下载失败: %s", url[:120], exc_info=True)
        return url
    finally:
        if owns_client:
            client.close()
