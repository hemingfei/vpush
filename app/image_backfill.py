"""帖子外链图片补缓存：定期重试下载仍存外链的帖子图片，成功后回写 posts.images。

背景：采集入库时图片下载失败（超时/风控/网络抖动）会按失败兜底口径把原始外链
留在 posts.images（cache_image_file：下载失败返回原 URL），外链图床有防盗链或
签名过期问题，时间一长就成死图。本任务作为事后兜底定期重试：

- 成功：images 条目替换为本地缓存地址 /<prefix>/<sha1>.<ext>
- 确定性非图片（HTTP 200 但 content-type 非图片，cache_image_file 返回 None）：
  记入跳过表不再重试，避免死链接占满每轮批次
- 其余失败（超时/非 200/写盘失败）：保持外链并记冷却时间，到期后自动再试

只改 posts.images：前端图片渲染只读该字段；detail.msg 保留采集原貌（历史记录，
附件解析口径不受影响）。已是本地缓存的条目（/<prefix>/ 开头）原样保留。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time

import httpx

from .avatar_cache import cache_image_file, should_direct_access
from .image_cleanup import POST_IMAGE_DIRS

logger = logging.getLogger(__name__)

# 平台 → (数据目录, 本地 URL 前缀)：与采集侧 cache_image_file 的调用口径一致；
# weibo 采集侧从未缓存过帖子图片，补缓存是它第一次有本地目录
PREFIX_BY_PLATFORM = {
    "mx": ("mx_images", "/mx-images"),
    "zsxq": ("zsxq_images", "/zsxq-images"),
    "xueqiu": ("xq_images", "/xq-images"),
    "weibo": ("weibo_images", "/weibo-images"),
}

# 单轮最多发起下载的图片张数：每张超时上限 15s，任务跑在后台线程不阻塞调度循环
BATCH_LIMIT = 20
# 每轮扫描的候选帖子窗口（按发布时间倒序取最近 N 条带外链图的帖子），
# 避免全表扫描；失败的 URL 靠冷却轮转让出批次名额
CANDIDATE_WINDOW = 200
# 下载失败后的重试冷却：期内不再碰该 URL
URL_COOLDOWN_SECONDS = 6 * 3600
# 跳过表（确定性非图片的 URL 键）上限，超出丢最旧的
MAX_SKIP_ENTRIES = 10000

_STATE_KEY = "image_backfill_state"


def _url_key(url: str) -> str:
    """URL 的稳定短键（与缓存文件名的 sha1 前缀同口径）。"""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _load_state(db) -> dict:
    raw = db.get_setting(_STATE_KEY)
    if not raw:
        return {"skip": [], "cooldown": {}}
    try:
        state = json.loads(raw)
    except (TypeError, ValueError):
        return {"skip": [], "cooldown": {}}
    if not isinstance(state, dict):
        return {"skip": [], "cooldown": {}}
    state.setdefault("skip", [])
    state.setdefault("cooldown", {})
    return state


def _save_state(db, state: dict, now: float) -> None:
    skip = state["skip"][-MAX_SKIP_ENTRIES:]
    cooldown = {k: v for k, v in state["cooldown"].items() if v > now}
    db.set_setting(
        _STATE_KEY,
        json.dumps({"skip": skip, "cooldown": cooldown}, ensure_ascii=False),
    )


def backfill_external_images(
    db,
    limit: int = BATCH_LIMIT,
    client: httpx.Client | None = None,
    now: float | None = None,
) -> dict:
    """扫描最近帖子里的外链图并尝试补缓存，返回本轮统计。

    Args:
        db: 数据库实例
        limit: 单轮最多发起下载的图片张数
        client: 可注入的 httpx 客户端（测试用）；缺省自建
        now: 当前时间戳（测试用）；缺省取 time.time()
    """
    now = time.time() if now is None else now
    stats = {
        "posts_scanned": 0,
        "images_ok": 0,
        "images_failed": 0,  # 下载失败保持外链，进冷却等下轮
        "images_skipped": 0,  # 确定性非图片 / 冷却期内
        "posts_updated": 0,
    }
    state = _load_state(db)
    skip = set(state["skip"])
    cooldown = state["cooldown"]
    state_dirty = False
    owns_client = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=True)
    try:
        rows = db._rows(
            "SELECT platform, external_id, images FROM posts "
            "WHERE images LIKE '%http%' ORDER BY published_at DESC LIMIT ?",
            (CANDIDATE_WINDOW,),
        )
        for row in rows:
            if stats["images_ok"] + stats["images_failed"] >= limit:
                break
            mapping = PREFIX_BY_PLATFORM.get(row["platform"])
            if not mapping:
                continue
            folder, prefix = mapping
            try:
                images = json.loads(row["images"])
            except (TypeError, ValueError):
                continue
            if not isinstance(images, list):
                continue
            stats["posts_scanned"] += 1
            updated = False
            for i, entry in enumerate(images):
                if stats["images_ok"] + stats["images_failed"] >= limit:
                    break
                url = entry if isinstance(entry, str) else ""
                if not url.startswith(("http://", "https://")):
                    continue  # 本地缓存或非法条目，原样保留
                if should_direct_access(db, url):
                    # 直连名单内的域名：按管理员策略保留外链，不下载不冷却
                    stats["images_skipped"] += 1
                    continue
                key = _url_key(url)
                if key in skip:
                    stats["images_skipped"] += 1
                    continue
                if cooldown.get(key, 0) > now:
                    stats["images_skipped"] += 1
                    continue
                cached = cache_image_file(db, url, folder, prefix, client=client)
                if cached is None:
                    # 200 但内容不是图片：确定性失败，进跳过表不再耗带宽
                    skip.add(key)
                    cooldown.pop(key, None)
                    stats["images_skipped"] += 1
                    state_dirty = True
                elif cached == url:
                    # 下载失败（超时/非 200/写盘失败等）：保持外链，进冷却下轮再试
                    cooldown[key] = now + URL_COOLDOWN_SECONDS
                    stats["images_failed"] += 1
                    state_dirty = True
                else:
                    cooldown.pop(key, None)
                    images[i] = cached
                    stats["images_ok"] += 1
                    updated = True
                    state_dirty = True
            if updated:
                db._execute(
                    "UPDATE posts SET images = ? WHERE platform = ? AND external_id = ?",
                    (
                        json.dumps(images, ensure_ascii=False),
                        row["platform"],
                        row["external_id"],
                    ),
                )
                stats["posts_updated"] += 1
    finally:
        if owns_client:
            client.close()
    if state_dirty:
        _save_state(db, {"skip": sorted(skip), "cooldown": cooldown}, now)
    return stats
