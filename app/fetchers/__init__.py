from __future__ import annotations

import logging

from .base import Fetcher

logger = logging.getLogger(__name__)
from .combination import CombinationFetcher
from .ima import ImaFetcher
from .twitter import TwitterFetcher
from .weibo import WeiboFetcher
from .xueqiu import XueqiuFetcher
from .zsxq import ZsxqFetcher


def build_fetchers(config, db) -> dict[str, Fetcher]:
    """根据全局配置构造各平台抓取器。"""
    fetchers = {
        "xueqiu": XueqiuFetcher(config.sources.xueqiu, db),
        "combination": CombinationFetcher(config.sources.xueqiu, db),
        "weibo": WeiboFetcher(config.sources.weibo, db),
        "twitter": TwitterFetcher(db=db),
        "ima": ImaFetcher(config.sources.ima, db),
        "zsxq": ZsxqFetcher(db=db),
    }
    if config.sources.mx.enabled:
        try:
            from .mx.fetcher import MxFetcher
            fetchers["mx"] = MxFetcher(config.sources.mx, db)
        except Exception as e:
            logger.warning("Failed to initialize MxFetcher: %s", e)
    return fetchers
