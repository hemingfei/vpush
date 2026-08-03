"""X/Twitter 等通用 RSS 抓取（RSSHub / nitter 源）。"""
from __future__ import annotations

import httpx
import feedparser

from .base import Fetcher, Post, strip_html


class RssFetcher(Fetcher):
    platform = "twitter"

    def __init__(self, source_config=None, client: httpx.Client | None = None):
        super().__init__(source_config)
        self.client = client or httpx.Client(
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )

    def fetch(self, kol: dict) -> list[Post]:
        resp = self.client.get(kol["external_id"])
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        posts = []
        for entry in feed.entries:
            posts.append(
                Post(
                    platform=self.platform,
                    kol_id=kol["id"],
                    kol_name=kol["name"],
                    external_id=entry.get("id") or entry.get("link") or "",
                    title=entry.get("title") or "",
                    content=strip_html(entry.get("summary") or entry.get("description") or ""),
                    url=entry.get("link") or "",
                    published_at=str(entry.get("published") or entry.get("updated") or ""),
                )
            )
        return posts
