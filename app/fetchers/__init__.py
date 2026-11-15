from __future__ import annotations

from .base import Fetcher
from .combination import CombinationFetcher
from .ima import ImaFetcher
from .truth import TruthFetcher
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
        "truth": TruthFetcher(db=db),
    }
    # MX 不再由云端轮询：消息经本地行为器+采集器上行到 /api/mx-ingest，
    # 解析/入库在网关内按需构造 MxFetcher。这里不注册 mx 抓取器。
    return fetchers
