from __future__ import annotations

from .base import Fetcher
from .rss import RssFetcher
from .weibo import WeiboFetcher
from .xueqiu import XueqiuFetcher


def build_fetchers(config) -> dict[str, Fetcher]:
    """根据全局配置构造各平台抓取器。"""
    return {
        "xueqiu": XueqiuFetcher(config.sources.xueqiu),
        "weibo": WeiboFetcher(config.sources.weibo),
        "twitter": RssFetcher(),
    }
