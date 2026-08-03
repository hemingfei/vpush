"""微博（m.weibo.cn）用户动态抓取。"""
from __future__ import annotations

import httpx

from .base import Fetcher, Post, strip_html


class WeiboFetcher(Fetcher):
    platform = "weibo"

    def __init__(self, source_config, client: httpx.Client | None = None):
        super().__init__(source_config)
        self.client = client or httpx.Client(
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Mobile/15E148",
                "Referer": "https://m.weibo.cn/",
            },
        )
        if self.source_config.cookie:
            self.client.headers["Cookie"] = self.source_config.cookie
        if self.source_config.token:
            self.client.headers["X-XSRF-TOKEN"] = self.source_config.token

    def fetch(self, kol: dict) -> list[Post]:
        uid = kol["external_id"]
        resp = self.client.get(
            "https://m.weibo.cn/api/container/getIndex",
            params={"type": "uid", "value": uid, "containerid": f"107603{uid}"},
        )
        resp.raise_for_status()
        cards = ((resp.json() or {}).get("data") or {}).get("cards") or []
        posts = []
        for card in cards:
            if card.get("card_type") != 9:
                continue
            mblog = card.get("mblog") or {}
            mid = mblog.get("id")
            if not mid:
                continue
            text = strip_html(mblog.get("text") or "")
            posts.append(
                Post(
                    platform=self.platform,
                    kol_id=kol["id"],
                    kol_name=kol["name"],
                    external_id=str(mid),
                    title=(mblog.get("raw_text") or text)[:80],
                    content=text,
                    url=f"https://m.weibo.cn/detail/{mid}",
                    published_at=str(mblog.get("created_at") or ""),
                )
            )
        return posts
