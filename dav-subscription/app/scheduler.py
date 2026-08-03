"""调度器：轮询抓取、去重入库、推送通知、失败退避。"""
from __future__ import annotations

import asyncio
import logging
import random
import time

from .db import DB
from .fetchers.base import Fetcher, Post
from .notifiers.base import Notifier

logger = logging.getLogger(__name__)


class PlatformState:
    """每个平台连续失败次数与退避截止时间。"""

    def __init__(self):
        self.fail_count = 0
        self.skip_until = 0.0


def notify_post(db: DB, post_id: int, post: Post, notifiers: list[Notifier]) -> None:
    """向所有通知器推送，失败记录日志并重试一次。"""
    for notifier in notifiers:
        try:
            notifier.notify(post)
            db.add_push_log(post_id, notifier.channel, "success")
        except Exception as exc:  # noqa: BLE001 - 推送失败只记录
            logger.warning("推送失败 channel=%s post=%s err=%s", notifier.channel, post.external_id, exc)
            db.add_push_log(post_id, notifier.channel, "failed", str(exc))
            try:
                notifier.notify(post)
                db.add_push_log(post_id, notifier.channel, "success")
            except Exception as exc2:  # noqa: BLE001
                logger.error("推送重试失败 channel=%s post=%s err=%s", notifier.channel, post.external_id, exc2)
                db.add_push_log(post_id, notifier.channel, "failed", str(exc2))


def poll_once(
    db: DB,
    fetchers: dict[str, Fetcher],
    notifiers: list[Notifier],
    states: dict[str, PlatformState] | None = None,
) -> None:
    """执行一轮：遍历启用 KOL → 抓取 → 去重 → 推送。"""
    states = states or {}
    now = time.monotonic()
    for kol in db.list_kols():
        if not kol["enabled"]:
            continue
        fetcher = fetchers.get(kol["platform"])
        if fetcher is None:
            continue
        state = states.setdefault(kol["platform"], PlatformState())
        if now < state.skip_until:
            continue
        try:
            posts = fetcher.fetch(kol)
        except Exception as exc:  # noqa: BLE001 - 单源失败不影响其他
            state.fail_count += 1
            delay = min(30 * (2 ** (state.fail_count - 1)), 600)
            state.skip_until = time.monotonic() + delay
            logger.warning(
                "抓取失败 platform=%s kol=%s err=%s 下次尝试 %.0fs 后",
                kol["platform"],
                kol["name"],
                exc,
                delay,
            )
            continue
        state.fail_count = 0
        for post in posts:
            post_id = db.insert_post(
                post.platform,
                post.kol_id,
                post.external_id,
                post.title,
                post.content,
                post.url,
                post.published_at,
            )
            if post_id is None:
                continue
            logger.info("新帖 platform=%s kol=%s id=%s", post.platform, post.kol_name, post.external_id)
            notify_post(db, post_id, post, notifiers)


class Scheduler:
    def __init__(self, db, fetchers, notifiers, polling_config):
        self.db = db
        self.fetchers = fetchers
        self.notifiers = notifiers
        self.polling_config = polling_config
        self.states: dict[str, PlatformState] = {}
        self._stop = asyncio.Event()

    def stop(self):
        self._stop.set()

    async def _send_startup_message(self):
        for notifier in self.notifiers:
            try:
                await asyncio.to_thread(notifier.send_text, "✅ 大V订阅服务已启动")
            except Exception as exc:  # noqa: BLE001
                logger.warning("启动消息发送失败 channel=%s err=%s", notifier.channel, exc)

    async def run(self):
        if self.polling_config.notify_on_start:
            await self._send_startup_message()
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                await asyncio.to_thread(poll_once, self.db, self.fetchers, self.notifiers, self.states)
            except Exception:  # noqa: BLE001 - 任何异常都不能终止循环
                logger.exception("轮询周期异常")
            elapsed = time.monotonic() - started
            delay = self.polling_config.interval_seconds + random.uniform(
                0, self.polling_config.jitter_seconds
            )
            await asyncio.sleep(max(0.0, delay - elapsed))
