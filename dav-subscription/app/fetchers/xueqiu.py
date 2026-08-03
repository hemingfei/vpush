"""雪球用户原创动态抓取。"""
from __future__ import annotations

import httpx

from .base import Fetcher, Post, strip_html


class XueqiuFetcher(Fetcher):
    platform = "xueqiu"

    def __init__(self, source_config, client: httpx.Client | None = None):
        super().__init__(source_config)
        self.client = client or httpx.Client(
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
                "Referer": "https://xueqiu.com/",
            },
        )
        if self.source_config.cookie:
            self.client.headers["Cookie"] = self.source_config.cookie

    def fetch(self, kol: dict) -> list[Post]:
        resp = self.client.get(
            "https://xueqiu.com/statuses/original/timeline.json",
            params={"user_id": kol["external_id"], "page": 1},
        )
        resp.raise_for_status()
        statuses = (resp.json() or {}).get("statuses") or []
        posts = []
        for s in statuses:
            target = s.get("target") or ""
            url = f"https://xueqiu.com{target}" if target.startswith("/") else target
            posts.append(
                Post(
                    platform=self.platform,
                    kol_id=kol["id"],
                    kol_name=kol["name"],
                    external_id=str(s.get("id") or ""),
                    title=s.get("title") or "",
                    content=strip_html(s.get("description") or ""),
                    url=url,
                    published_at=str(s.get("created_at") or ""),
                )
            )
        return posts
