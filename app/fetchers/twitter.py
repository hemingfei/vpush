"""X/Twitter 官方 GraphQL 直抓。

两条通道，由设置 `x_auth_mode` 选择：

1. **Cookie 通道（默认）**——依赖登录 Cookie（TWITTER_COOKIE 里的 auth_token /
   ct0），调用 X 网页端同源 GraphQL（x.com/i/api），配 curl_cffi 浏览器指纹。
   queryId 由 X 前端轮换，每 6 小时自动从前端 main bundle 提取一次，失败时用
   内置默认值兜底。

2. **App 身份通道（`x_auth_mode=oauth1`）**——走 X Android 客户端的
   api.x.com/graphql，用 OAuth1 签名（凭据 x_oauth_token / x_oauth_token_secret）。
   不需要浏览器指纹、不需要 x-client-transaction-id，凭证也不随 web session
   回收而失效；UserByScreenName 对第三方账号可直接解析，无需 typeahead 兜底。

接口失败则抛出，由调度器告警并放慢采集。HTTP 客户端用 curl_cffi.Session；
该对象非线程安全，生产同平台 2 并发共享 fetcher，用 ThreadLocalClient 每线程
懒建一个 session；外部注入的 client（测试 mock / 解析头像）直接复用。
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import logging
import os
import random
import re
import string
import threading
import time
from urllib.parse import quote

import httpx
from curl_cffi import requests as cffi
from curl_cffi.requests.errors import RequestsError

from ..avatar_cache import cache_avatar
from .base import (
    Fetcher,
    Post,
    ThreadLocalClient,
    format_published_at,
    tail_is_unseen,
    warn_timeline_gap,
)

logger = logging.getLogger(__name__)


class QueryIdExpiredError(RuntimeError):
    """X 轮换了 GraphQL queryId（接口返回 400/404，或错误信息里点名 queryid）。

    单独成类是为了能和 429/网络/鉴权失败区分开：只有它才需要更新
    DEFAULT_QUERY_IDS，也只有它值得写 queryId 相关告警。
    """


TWITTER_COOKIE_KEY = "twitter_cookie"
TWITTER_COOKIE_TIME_KEY = "twitter_cookie_updated_at"


def configured_twitter_cookie(db=None, override: str | None = None) -> str:
    """后台写入的 Cookie 优先，否则回退环境变量。"""
    if override:
        return override
    if db is not None:
        stored = db.get_setting(TWITTER_COOKIE_KEY)
        if stored:
            return stored
    return os.environ.get("TWITTER_COOKIE", "")


# X 网页端公开的 guest bearer token（来自 abs.twimg.com 前端包）
GUEST_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
DEFAULT_QUERY_IDS = {
    "UserTweets": "T1x2zehUOKCWNpKwZCpnbg",
    "UserByScreenName": "Gb-d6r0vxPOADdG62OEBpQ",
}
QUERY_ID_TTL = 6 * 3600  # 每 6 小时重新从前端提取一次 queryId
QUERY_ID_RETRY_COOLDOWN = 300  # 提取失败后 5 分钟重试，避免每次轮询都打前端
PROBE_TTL = 6 * 3600  # queryId 主动探测间隔（进程内计时，重启即重新探测）
PROBE_COOLDOWN = 600  # 探测失败后的冷却，避免反复打
PROBE_SCREEN_NAME = "Twitter"  # 探测目标：官方账号，长期稳定存在
CHANNEL_COOLDOWN = 900  # 单通道撞 429 后的冷却，对齐 X 的 15 分钟窗口
FETCH_COUNT = 20

# UserTweets 时间线所需的标准 feature switches（X 网页端常用集合）
FEATURES = {
    "rweb_video_screen_enabled": False,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": False,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_query_ids: dict[str, str] = dict(DEFAULT_QUERY_IDS)
_query_ids_loaded = 0.0
_query_ids_error_until = 0.0
_query_ids_lock = threading.Lock()

# queryId 主动探测状态：UserByScreenName 只在新增大V 时用到，平时抓取不经过它，
# queryId 轮换后可能长期无人察觉——所以按 TTL 主动探一次，失效立刻告警。
_probe_at = 0.0
_probe_error_until = 0.0
_probe_lock = threading.Lock()

# 通道级冷却：两条通道的 GraphQL 配额在服务端独立计数，一侧撞 429 时换另一侧
# 重试即可——不让整个平台退避，否则 2 倍容量买不到 2 倍可用性。
_channel_until: dict[str, float] = {}
_channel_lock = threading.Lock()


def _channel_cooling(channel: str) -> bool:
    with _channel_lock:
        return time.time() < _channel_until.get(channel, 0.0)


def _mark_channel_cooling(channel: str) -> None:
    with _channel_lock:
        _channel_until[channel] = time.time() + CHANNEL_COOLDOWN


def channel_runtime_status() -> dict:
    """两条通道的运行时状态（供后台展示）：是否处于 429 冷却、还剩多久。"""
    now = time.time()
    with _channel_lock:
        snapshot = dict(_channel_until)
    out: dict[str, dict] = {}
    for ch in ("app", "cookie"):
        until = snapshot.get(ch, 0.0)
        out[ch] = {
            "cooling": now < until,
            "cooling_left_seconds": max(0, int(until - now)),
        }
    return out


def x_channel_overview(db) -> dict:
    """后台用：X 抓取通道总览（模式 / 凭证 / 分流覆盖 / 冷却）。

    模式与 `_channel_for` 的退化逻辑保持一致——凭证不全时不分流，
    否则后台显示的分布会和实际抓取对不上。
    """
    app_auth = configured_x_app_auth(db)
    cookie = configured_twitter_cookie(db)
    kols: list[dict] = []
    if db is not None:
        with contextlib.suppress(Exception):  # noqa: BLE001 - 总览失败不影响状态接口
            kols = db.list_kols("twitter") or []

    if app_auth and cookie:
        mode = "split"
    elif app_auth:
        mode = "app_only"
    else:
        mode = "cookie_only"

    split = {"app": 0, "cookie": 0}
    for k in kols:
        if mode == "split":
            split["app" if int(k.get("id") or 0) % 2 else "cookie"] += 1
        elif mode == "app_only":
            split["app"] += 1
        else:
            split["cookie"] += 1

    return {
        "mode": mode,
        "app_ready": bool(app_auth),
        "cookie_ready": bool(cookie),
        "app_token_len": len(app_auth[0]) if app_auth else 0,
        "cookie_len": len(cookie),
        "kol_total": len(kols),
        "split": split,
        "channels": channel_runtime_status(),
    }


# ---------------------------------------------------------------- App 身份通道（OAuth1）
# 走 X Android 客户端的 api.x.com/graphql：不需要浏览器 TLS 指纹，不需要
# x-client-transaction-id，凭证是 OAuth1（不随 web session 回收而失效）。
#
# 实测（2026-09）：同一凭证打 x.com/i/api 一律 403（无论 POST/GET、无论配
# Chrome UA + curl_cffi 浏览器指纹），打 api.x.com 正常返回；且 App 通道下
# UserByScreenName 对第三方账号也能正常解析（web 通道自 2026-08 起返回空壳，
# 需靠 typeahead 兜底）。

X_AUTH_MODE_KEY = "x_auth_mode"  # "cookie"（默认）| "oauth1"
X_OAUTH_TOKEN_KEY = "x_oauth_token"
X_OAUTH_SECRET_KEY = "x_oauth_token_secret"

# Twitter for Android 官方 OAuth 凭据（明文存在于 APK 中）
APP_CONSUMER_KEY = "3nVuSoBZnx6U4vzUxf5w"
APP_CONSUMER_SECRET = "Bcs59EFbbsdF6Sl9Ng71smgStWEGwXXKSjYvPVt7qys"
APP_UA = "TwitterAndroid/12.27.1 (Android 14; com.twitter.android)"
APP_GRAPHQL_BASE = "https://api.x.com/graphql"


def configured_x_app_auth(db=None) -> tuple[str, str] | None:
    """读取 App 身份通道凭证 (token, secret)；未启用或凭证缺失返回 None。"""
    mode = ""
    if db is not None:
        mode = db.get_setting(X_AUTH_MODE_KEY) or ""
    mode = mode or os.environ.get("X_AUTH_MODE", "cookie")
    if mode != "oauth1":
        return None

    token = secret = ""
    if db is not None:
        token = db.get_setting(X_OAUTH_TOKEN_KEY) or ""
        secret = db.get_setting(X_OAUTH_SECRET_KEY) or ""
    token = token or os.environ.get("X_OAUTH_TOKEN", "")
    secret = secret or os.environ.get("X_OAUTH_TOKEN_SECRET", "")
    return (token, secret) if token and secret else None


def _oauth1_sign(method: str, url: str, params: dict, token: str, secret: str) -> str:
    """OAuth1 HMAC-SHA1 签名。

    body 为 JSON（非 form-encoded）时不参与签名，只签 URL query 参数——
    与 X Android 客户端行为一致。
    """
    oauth = {
        "oauth_consumer_key": APP_CONSUMER_KEY,
        "oauth_nonce": "".join(
            random.choices(string.ascii_letters + string.digits, k=32)
        ),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    signing = "&".join(
        f"{quote(str(k), safe='')}={quote(str(v), safe='')}"
        for k, v in sorted({**params, **oauth}.items())
    )
    base = f"{method.upper()}&{quote(url, safe='')}&{quote(signing, safe='')}"
    key = f"{quote(APP_CONSUMER_SECRET, safe='')}&{quote(secret, safe='')}"
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    return "OAuth " + ", ".join(
        f'{quote(str(k), safe="")}="{quote(str(v), safe="")}"'
        for k, v in sorted(oauth.items())
    )


def _app_headers(
    method: str, url: str, params: dict, app_auth: tuple[str, str]
) -> dict[str, str]:
    token, secret = app_auth
    return {
        "Authorization": _oauth1_sign(method, url, params, token, secret),
        "User-Agent": APP_UA,
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "zh-CN",
        "Content-Type": "application/json",
    }


def _cookie_parts(cookie: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (cookie or "").split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            out[key.strip()] = value.strip()
    return out


def _auth_headers(cookie: str) -> dict[str, str]:
    parts = _cookie_parts(cookie)
    auth, ct0 = parts.get("auth_token", ""), parts.get("ct0", "")
    return {
        "Authorization": f"Bearer {GUEST_BEARER_TOKEN}",
        "Cookie": f"auth_token={auth}; ct0={ct0}; lang=zh-CN",
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "User-Agent": UA,
        "Content-Type": "application/json",
    }


def _html_headers(cookie: str) -> dict[str, str]:
    """浏览器式请求头：只带 UA + Cookie，用于拉取 x.com 页面与前端 bundle。

    不能复用 _auth_headers——带 Authorization / x-csrf-token 的请求打到 HTML
    路由会直接返回 401（实测 2026-08），导致 queryId 提取永远失败。
    """
    parts = _cookie_parts(cookie)
    auth, ct0 = parts.get("auth_token", ""), parts.get("ct0", "")
    return {
        "User-Agent": UA,
        "Cookie": f"auth_token={auth}; ct0={ct0}; lang=zh-CN",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def _refresh_query_ids(client, cookie: str) -> None:
    """从 X 前端 main bundle 提取最新的 UserTweets / UserByScreenName queryId。"""
    global _query_ids_loaded, _query_ids_error_until
    with _query_ids_lock:
        now = time.time()
        if now - _query_ids_loaded < QUERY_ID_TTL:
            return
        if now < _query_ids_error_until:
            return  # 上次提取失败，冷却期内不重复打前端
        try:
            headers = _html_headers(cookie)
            page = client.get("https://x.com/", headers=headers)
            page.raise_for_status()
            match = re.search(
                r'src="(https://abs\.twimg\.com/responsive-web/client-web/main\.[^"]+\.js)"',
                page.text,
            )
            if not match:
                return
            bundle = client.get(match.group(1))
            bundle.raise_for_status()
            text = bundle.text
            for op in ("UserTweets", "UserByScreenName"):
                found = re.search(
                    r'queryId:"([^"]+)"[^}]{0,300}?operationName:"'
                    + re.escape(op)
                    + r'"',
                    text,
                )
                if found:
                    _query_ids[op] = found.group(1)
            _query_ids_loaded = now
            logger.info("X queryId 已从前端更新: %s", _query_ids)
        except Exception as exc:  # noqa: BLE001 - 提取失败用内置默认值兜底
            _query_ids_error_until = now + QUERY_ID_RETRY_COOLDOWN
            logger.warning(
                "X queryId 提取失败，使用默认值，%.0f 秒后重试: %s",
                QUERY_ID_RETRY_COOLDOWN,
                exc,
            )


def extract_screen_name(external_id: str) -> str:
    """从 x.com/twitter.com 主页链接或纯用户名（含 @前缀）里提取 screen_name。"""
    value = (external_id or "").strip()
    match = re.search(r"(?:x\.com|twitter\.com)/(?:@?)([A-Za-z0-9_]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"@?[A-Za-z0-9_]{1,15}", value):
        return value.lstrip("@")
    return ""


def _visibility_tweet(tweet: dict) -> dict:
    if (
        tweet.get("__typename") == "TweetWithVisibilityResults"
        and isinstance(tweet.get("tweet"), dict)
    ):
        return tweet["tweet"]
    return tweet


def _unwrap_tweet_result(node) -> dict | None:
    if not isinstance(node, dict):
        return None
    if isinstance(node.get("result"), dict):
        node = node["result"]
    if not isinstance(node, dict):
        return None
    return _visibility_tweet(node)


def _retweeted_tweet(tweet: dict) -> dict | None:
    legacy = tweet.get("legacy") or {}
    return _unwrap_tweet_result(
        legacy.get("retweeted_status_result") or tweet.get("retweeted_status_result")
    )


def _quoted_tweet(tweet: dict) -> dict | None:
    legacy = tweet.get("legacy") or {}
    return _unwrap_tweet_result(
        tweet.get("quoted_status_result")
        or legacy.get("quoted_status_result")
        or tweet.get("quoted_status")
        or legacy.get("quoted_status")
    )


def _with_quoted_content(text: str, images: list[str], tweet: dict) -> tuple[str, list[str]]:
    quoted = _quoted_tweet(tweet)
    if not quoted:
        return text, images
    q_text, q_images, q_video = _tweet_text_and_images(quoted)
    if not q_text:
        if q_images:
            q_text = "图片"
        elif q_video:
            q_text = "视频"
        else:
            return text, images
    screen = _tweet_screen_name(quoted)
    label = f"RT @{screen}:" if screen else "RT:"
    text = f"{text}\n\n{label}\n{q_text}" if text else f"{label}\n{q_text}"
    out = list(images)
    for url in q_images:
        if url not in out and len(out) < 4:
            out.append(url)
    return text, out


def _tweet_screen_name(tweet: dict) -> str:
    core = tweet.get("core") or {}
    user = (core.get("user_results") or {}).get("result") or {}
    return str(
        (user.get("core") or {}).get("screen_name")
        or (user.get("legacy") or {}).get("screen_name")
        or ""
    ).strip()


def _tweet_text_and_images(tweet: dict) -> tuple[str, list[str], bool]:
    legacy = tweet.get("legacy") or {}
    text = (legacy.get("full_text") or legacy.get("text") or "").strip()
    images = extract_twitter_images(legacy)
    media = (legacy.get("extended_entities") or {}).get("media") or []
    has_video = any((item.get("type") or "") in ("video", "animated_gif") for item in media)
    note = (((tweet.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {})
    note_text = (note.get("text") or "").strip()
    if note_text and len(note_text) > len(text):
        text = note_text
    return text, images, has_video


def extract_twitter_images(legacy: dict) -> list[str]:
    """X 推文图片：extended_entities.media 里的照片 URL（最多 4 张）。"""
    out: list[str] = []
    for media in (legacy.get("extended_entities") or {}).get("media") or []:
        if media.get("type") != "photo":
            continue
        url = media.get("media_url_https") or media.get("media_url") or ""
        if url and url not in out:
            out.append(url)
        if len(out) >= 4:
            break
    return out


def resolve_x_profile(external_id: str, cookie: str = "", db=None) -> dict:
    """按 X 用户名/主页链接解析昵称与头像。

    优先 typeahead（web 通道）；App 身份通道下直接走 UserByScreenName。
    失败（凭证失效/风控/未配置）时返回空 dict，调用方回退占位名。
    """
    cookie = cookie or configured_twitter_cookie(db)
    screen_name = extract_screen_name(external_id)
    app_auth = configured_x_app_auth(db)
    if not screen_name or (not cookie and not app_auth):
        return {}
    from ..proxy import ProxyUnavailable, acquire_client_proxy, attach_proxy

    try:
        proxy, pid = acquire_client_proxy(db, "twitter")
    except ProxyUnavailable:
        return {}
    client = cffi.Session(impersonate="chrome124", timeout=20, proxy=proxy)
    attach_proxy(client, pid)
    try:
        fetcher = TwitterFetcher(db=db, client=client)
        # App 通道没有 Cookie，typeahead（x.com/i/api）不可用，直接走 UserByScreenName
        picked = None if app_auth else fetcher._typeahead_pick(screen_name, cookie)
        if picked:
            avatar = (
                picked.get("profile_image_url_https")
                or picked.get("profile_image_url")
                or ""
            ).replace("_normal", "_400x400")
            return {
                "name": picked.get("name") or "",
                "avatar_url": avatar,
                "screen_name": picked.get("screen_name") or screen_name,
            }
        data = fetcher._graphql(
            "UserByScreenName",
            {"screen_name": screen_name, "withSafetyModeUserFields": True},
            cookie,
        )
        result = ((data.get("data") or {}).get("user") or {}).get("result") or {}
        name = (
            (result.get("core") or {}).get("name")
            or (result.get("legacy") or {}).get("name")
            or ""
        )
        avatar = ((result.get("avatar") or {}).get("image_url") or "").replace(
            "_normal", "_400x400"
        )
        return {"name": name, "avatar_url": avatar, "screen_name": screen_name}
    except Exception as exc:  # noqa: BLE001 - 解析失败退回占位名
        logger.warning("X 昵称解析失败 screen=%s err=%s", screen_name, exc)
        return {}
    finally:
        client.close()


def _walk_tweet_results(entry: dict, out: list[dict]) -> None:
    """递归展开时间线条目（单条推文 / 模块内多推文 / 置顶）。"""
    content = entry.get("content") or {}
    typename = content.get("__typename") or content.get("entryType") or ""
    if typename == "TimelineTimelineItem":
        _append_tweet(content.get("itemContent"), out)
        return
    if typename == "TimelineTimelineModule":
        for item in content.get("items") or []:
            _walk_tweet_results({"content": item.get("item") or item}, out)
    else:
        _append_tweet(content, out)


def _append_tweet(node, out: list[dict]) -> None:
    """从 itemContent 里取出推文；结构不标准时向下找 itemContent。"""
    if not isinstance(node, dict):
        return
    tweet = (node.get("tweet_results") or {}).get("result")
    if isinstance(tweet, dict):
        out.append(_visibility_tweet(tweet))
        return
    item_content = node.get("itemContent")
    if isinstance(item_content, dict):
        _append_tweet(item_content, out)


def _collect_timeline_tweets(data: dict, screen_name: str) -> list[dict]:
    """从 UserTweets 响应里取出推文节点；用户不存在/停用时抛错。

    注意空返回是合法结果——X 在服务端降级时也会返回一个只有 cursor 的
    TimelineAddEntries（实测 2026-09 约 1/9），是否重试由调用方决定。
    """
    result = ((data.get("data") or {}).get("user") or {}).get("result", {})
    if not result or result.get("__typename") == "UserUnavailable":
        raise RuntimeError(f"X 用户不存在或已停用: {screen_name}")
    instructions = ((result.get("timeline") or {}).get("timeline") or {}).get(
        "instructions"
    ) or []
    tweets: list[dict] = []
    for instruction in instructions:
        if instruction.get("type") == "TimelineAddEntries":
            for entry in instruction.get("entries") or []:
                _walk_tweet_results(entry, tweets)
        elif instruction.get("type") == "TimelinePinEntry":
            _walk_tweet_results(instruction.get("entry") or {}, tweets)
    return tweets


class TwitterFetcher(Fetcher):
    platform = "twitter"

    def __init__(self, source_config=None, db=None, client=None):
        super().__init__(source_config)
        self.db = db
        self._user_ids: dict[str, str] = {}

        def _make():
            from ..proxy import acquire_client_proxy, attach_proxy

            proxy, pid = acquire_client_proxy(self.db, "twitter")
            sess = cffi.Session(impersonate="chrome124", timeout=25, proxy=proxy)
            attach_proxy(sess, pid)
            return sess

        self._http = ThreadLocalClient(_make, injected=client)

    def _client_for(self):
        return self._http.get()

    def fetch(self, kol: dict) -> list[Post]:
        """X 直抓；失败按错误类型分流后抛出，不再走备用内容通道。

        - 网络类错误（SSL/超时/连接重置）：只记 warn，不标「直抓失败」——避免抖动时
          刷告警；调度器退避等网络恢复。
        - 鉴权/接口类错误（401/403/GraphQL errors/cookie 失效）：记下失败时间与原因，
          供告警和放慢采集，然后抛出。
        """
        cookie = configured_twitter_cookie(self.db)
        self._maybe_probe_query_id(cookie)
        try:
            posts = self._fetch_direct(kol, cookie)
            if self.db is not None:
                self.db.set_setting("x_direct_last_ok_at", str(int(time.time())))
            return posts
        except (httpx.TransportError, RequestsError) as exc:
            if self.db is not None:
                self.db.add_source_event(
                    "twitter",
                    "warn",
                    f"X网络抖动(直抓): {str(exc)[:200]}",
                )
            logger.warning("X 直抓网络错误，本轮跳过 kol=%s err=%s", kol["name"], exc)
            raise
        except Exception as exc:
            if self.db is not None:
                self.db.set_setting("x_direct_last_fallback_at", str(int(time.time())))
                self.db.set_setting("x_direct_fallback_reason", str(exc)[:300])
                self.db.add_source_event(
                    "twitter",
                    "warn",
                    f"X直抓失败: {str(exc)[:200]}",
                )
            logger.warning("X 直抓失败 kol=%s err=%s", kol["name"], exc)
            raise

    def _channel_for(self, kol: dict) -> str:
        """按大V 稳定分流到两条通道（生产实测：两通道 GraphQL 配额独立计数）。

        奇数 id 走 App 通道、偶数走 Cookie 通道；首选通道处于 429 冷却期时临时
        让给另一条。凭证不全时退化：App 缺失走 Cookie，Cookie 缺失走 App。
        """
        app_auth = configured_x_app_auth(self.db)
        if not app_auth:
            return "cookie"
        # Cookie 缺失时不能分流到 web 通道：空 Cookie 打 x.com/i/api 会返回 200
        # 但内容是陈旧推文（实测拿到 2020~2022 年的旧帖），静默给错数据比报错更危险。
        if not configured_twitter_cookie(self.db):
            return "app"
        preferred = "app" if int(kol.get("id") or 0) % 2 else "cookie"
        other = "cookie" if preferred == "app" else "app"
        if _channel_cooling(preferred) and not _channel_cooling(other):
            return other
        return preferred

    def _graphql(
        self,
        operation: str,
        variables: dict,
        cookie: str,
        prefer: str | None = None,
    ) -> dict:
        """双通道分发，撞 429 时在通道之间失败转移。

        为什么要转移：两条通道的配额在服务端独立计数（生产实测），但调度器的
        `_is_platform_wide_error` 会把任意 `X GraphQL ... 429` 判为平台级故障并让
        整个 X 平台退避 15 分钟。若把 429 原样抛上去，一侧撞限会把另一侧一起拖停，
        双通道的 2 倍容量就白买了。所以在 fetcher 内部消化：一侧 429 → 标记该通道
        冷却 → 换另一条重试；两条都失败才抛给调度器做平台级退避。

        单通道场景行为不变：没有备选通道时 429 原样抛出。
        """
        app_auth = configured_x_app_auth(self.db)
        prefer_app = bool(app_auth) and prefer != "cookie"
        # Cookie 为空时不能走 web 通道：空 Cookie 打 x.com/i/api 会返回 200，但内容
        # 是陈旧推文（实测拿到 2020~2022 年的旧帖），静默给错数据比直接报错更危险。
        # 有 App 凭证就改走 App；都没有时保持原样，由下层抛出「未配置凭证」。
        if not prefer_app and not cookie and app_auth:
            prefer_app = True
        order = ["app"] if prefer_app else ["cookie"]
        # 备选通道只在凭证齐备时加入；prefer="cookie" 是显式要求，不做转移。
        if prefer_app and cookie:
            order.append("cookie")
        elif not prefer_app and app_auth and prefer is None:
            order.append("app")

        last_exc: Exception | None = None
        for channel in order:
            try:
                if channel == "app" and app_auth:
                    return self._graphql_app(operation, variables, app_auth)
                return self._graphql_web(operation, variables, cookie)
            except QueryIdExpiredError:
                raise  # queryId 轮换与通道无关，换通道救不了
            except RuntimeError as exc:
                if len(order) == 1 or "429" not in str(exc):
                    raise
                _mark_channel_cooling(channel)
                logger.info(
                    "X %s 通道撞 429，切换另一条通道重试（operation=%s）", channel, operation
                )
                last_exc = exc
        raise last_exc if last_exc else RuntimeError(f"X GraphQL {operation} 无可用通道")

    def _graphql_app(
        self, operation: str, variables: dict, app_auth: tuple[str, str]
    ) -> dict:
        """App 身份通道：api.x.com/graphql + OAuth1。"""
        # 不做 queryId 前端提取——提取需要登录态 HTML，而该通道没有 Cookie；
        # 实测 web 通道的 queryId 在 App 通道同样有效。
        query_id = _query_ids.get(operation) or DEFAULT_QUERY_IDS[operation]
        url = f"{APP_GRAPHQL_BASE}/{query_id}/{operation}"
        params = {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(FEATURES, separators=(",", ":")),
        }
        resp = self._client_for().post(
            url,
            params=params,
            json={"variables": variables, "features": FEATURES},
            headers=_app_headers("POST", url, params, app_auth),
        )
        return self._parse_graphql(operation, resp, channel="app")

    def _graphql_web(self, operation: str, variables: dict, cookie: str) -> dict:
        """Cookie 通道：x.com/i/api/graphql + 浏览器指纹。"""
        _refresh_query_ids(self._client_for(), cookie)
        query_id = _query_ids.get(operation) or DEFAULT_QUERY_IDS[operation]
        resp = self._client_for().post(
            f"https://x.com/i/api/graphql/{query_id}/{operation}",
            params={
                "variables": json.dumps(variables, separators=(",", ":")),
                "features": json.dumps(FEATURES, separators=(",", ":")),
            },
            json={"variables": variables, "features": FEATURES},
            headers=_auth_headers(cookie),
        )
        return self._parse_graphql(operation, resp, channel="cookie")

    @staticmethod
    def _parse_graphql(operation: str, resp, channel: str = "") -> dict:
        """两通道共用的响应校验：非 200 与 GraphQL errors 的分流提示。

        channel 会写进异常消息（形如 `X GraphQL(app) UserTweets HTTP 401`），
        便于从 source_events / 后台一眼看出是哪条通道失败——两条通道的凭证
        与失效原因完全不同，不区分就会指错排查方向。
        """
        tag = f"({channel})" if channel else ""
        if resp.status_code != 200:
            detail = ""
            with contextlib.suppress(Exception):  # noqa: BLE001 - 非 JSON 响应体忽略
                err = resp.json()
                errs = err.get("errors") or []
                code = err.get("code") or next(
                    (e.get("code") for e in errs if e.get("code")), ""
                )
                if code:
                    detail = f" code {code}"
                else:
                    msg = next(
                        (e.get("message") for e in errs if e.get("message")), ""
                    )
                    if msg:
                        detail = f" {str(msg)[:80]}"
            if resp.status_code in (400, 404):
                raise QueryIdExpiredError(
                    f"X GraphQL{tag} {operation} HTTP {resp.status_code}{detail}"
                    "（可能 X 轮换了 GraphQL queryId，需更新 DEFAULT_QUERY_IDS）"
                )
            raise RuntimeError(
                f"X GraphQL{tag} {operation} HTTP {resp.status_code}{detail}"
            )
        data = resp.json()
        if data.get("errors"):
            msg = str(data["errors"][0].get("message", data["errors"]))
            if "queryid" in msg.lower() or "invalidrequest" in msg.lower():
                raise QueryIdExpiredError(
                    f"X GraphQL{tag} {operation} 错误: {msg}"
                    "（可能 X 轮换了 GraphQL queryId，需更新 DEFAULT_QUERY_IDS）"
                )
            raise RuntimeError(f"X GraphQL{tag} {operation} 错误: {msg}")
        return data

    def _maybe_probe_query_id(self, cookie: str) -> None:
        """按 TTL 主动探测 UserByScreenName 的 queryId 是否仍然有效。

        为什么只探它：UserTweets 每轮抓取都在用，一旦失效立刻暴露；而
        UserByScreenName 只在新增大V 时用到，queryId 轮换后可能很久没人发现。

        判据严格：只认 QueryIdExpiredError（400/404 或错误信息点名 queryid）。
        429 / 网络 / 鉴权失败一律不算——它们在探测里出现不代表 queryId 有问题。
        探测失败不影响本轮抓取。
        """
        global _probe_at, _probe_error_until
        with _probe_lock:
            now = time.time()
            if now - _probe_at < PROBE_TTL or now < _probe_error_until:
                return

        try:
            data = self._graphql(
                "UserByScreenName",
                {"screen_name": PROBE_SCREEN_NAME, "withSafetyModeUserFields": True},
                cookie,
            )
            result = ((data.get("data") or {}).get("user") or {}).get("result") or {}
            if not result.get("rest_id"):
                # 官方账号都解析不出 rest_id，说明该 queryId 已不适用于当前接口
                raise QueryIdExpiredError(
                    f"探测目标无 rest_id（__typename={result.get('__typename')}）"
                )
        except QueryIdExpiredError as exc:
            with _probe_lock:
                _probe_error_until = time.time() + PROBE_COOLDOWN
            logger.warning("X queryId 探测失败：%s", exc)
            if self.db is not None:
                self.db.add_source_event(
                    "twitter",
                    "warn",
                    f"X queryId 疑似失效，需更新 DEFAULT_QUERY_IDS: {str(exc)[:140]}",
                )
        except Exception as exc:  # noqa: BLE001 - 探测不得影响抓取
            with _probe_lock:
                _probe_error_until = time.time() + PROBE_COOLDOWN
            logger.debug("X queryId 探测未完成（非 queryId 问题，忽略）：%s", exc)
        else:
            with _probe_lock:
                _probe_at = time.time()
            logger.debug("X queryId 探测通过：%s", _query_ids)

    def _typeahead_pick(self, screen_name: str, cookie: str) -> dict | None:
        """typeahead 解析：只认精确匹配 screen_name 的结果。

        不能取 users[0] 兜底——typeahead 搜索结果可能把显示名相同但 handle
        不同的账号排前面（实测搜 qinbafrank 只返回停更镜像号 qinbafrank9），
        取首个会静默解析到错误账号，永远抓不到新帖。无精确匹配返回 None，
        由调用方回退 UserByScreenName。
        """
        headers = _auth_headers(cookie)
        resp = self._client_for().get(
            "https://x.com/i/api/1.1/search/typeahead.json",
            params={"q": screen_name, "result_type": "users"},
            headers=headers,
        )
        if resp.status_code == 429:
            raise RuntimeError("X typeahead HTTP 429")
        if resp.status_code != 200:
            return None
        users = (resp.json() or {}).get("users") or []
        target = screen_name.lower()
        return next(
            (u for u in users if (u.get("screen_name") or "").lower() == target),
            None,
        )

    def _typeahead_users(
        self, screen_name: str, cookie: str
    ) -> tuple[str, str]:
        """经 typeahead 接口解析 uid（2026-08 起 UserByScreenName 对第三方账号返回空壳，
        typeahead 仍可用）；返回 (user_id, avatar_url)，解析失败返回空。"""
        picked = self._typeahead_pick(screen_name, cookie)
        if not picked:
            return "", ""
        user_id = picked.get("id_str") or ""
        img = picked.get("profile_image_url_https") or picked.get("profile_image_url") or ""
        return user_id, img.replace("_normal", "_400x400") if img else ""

    def _resolve_user(
        self, screen_name: str, cookie: str, prefer: str | None = None
    ) -> dict:
        if screen_name in self._user_ids:
            return {"user_id": self._user_ids[screen_name], "avatar": ""}
        # typeahead 打 x.com/i/api，只有 Cookie 通道能用；App 通道直接走
        # UserByScreenName（该通道对第三方账号可直接解析，无需兜底）。
        use_app = bool(configured_x_app_auth(self.db)) and prefer != "cookie"
        if use_app:
            user_id, avatar = "", ""
        else:
            user_id, avatar = self._typeahead_users(screen_name, cookie)
        if not user_id:
            # 回退 UserByScreenName（web 通道自 2026-08 起对第三方账号返回空壳，
            # 仅 typeahead 无精确匹配时才走到这里；App 通道则直接可用）
            data = self._graphql(
                "UserByScreenName",
                {"screen_name": screen_name, "withSafetyModeUserFields": True},
                cookie,
                prefer=prefer,
            )
            result = ((data.get("data") or {}).get("user") or {}).get("result") or {}
            user_id = result.get("rest_id") or ""
            avatar = ((result.get("avatar") or {}).get("image_url") or "").replace(
                "_normal", "_400x400"
            )
        if not user_id:
            raise RuntimeError(f"X 未找到用户 {screen_name}")
        self._user_ids[screen_name] = user_id
        return {"user_id": user_id, "avatar": avatar}

    def _fetch_direct(self, kol: dict, cookie: str) -> list[Post]:
        if not cookie and not configured_x_app_auth(self.db):
            raise RuntimeError(
                "未配置 X 凭证（后台「数据源 → Cookie 管理」填写 Cookie，"
                "或设置 x_auth_mode=oauth1 启用 App 身份通道）"
            )
        screen_name = extract_screen_name(kol["external_id"])
        if not screen_name:
            raise RuntimeError(f"无法识别 X 用户名: {kol['external_id']}")
        channel = self._channel_for(kol)
        user = self._resolve_user(screen_name, cookie, prefer=channel)
        variables = {
            "userId": user["user_id"],
            "count": FETCH_COUNT,
            "includePromotedContent": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
        # X 偶发返回 200 + 空 timeline：服务端降级时秒回（0.3s vs 正常 0.7~1.8s）
        # 一个只有 cursor 的 TimelineAddEntries，且 result 里缺 legacy/core 字段。
        # 若直接当作「没有新帖」，会静默丢数据且 x_direct_last_ok_at 仍被标成功。
        # 实测 2026-09 约 1/9 命中，故重试一次再判定失败。
        tweets: list[dict] = []
        for attempt in (1, 2):
            data = self._graphql("UserTweets", variables, cookie, prefer=channel)
            tweets = _collect_timeline_tweets(data, screen_name)
            if tweets or attempt == 2:
                break
            logger.info("X 空时间线，重试一次 kol=%s", kol["name"])
            time.sleep(0.8)
        if not tweets:
            raise RuntimeError(
                f"X 连续返回空时间线（疑似服务端降级，非「没有新帖」）: {screen_name}"
            )
        posts = []
        for tweet in tweets:
            legacy = tweet.get("legacy") or {}
            tweet_id = tweet.get("rest_id") or legacy.get("id_str") or ""
            if not tweet_id:
                continue
            original = _retweeted_tweet(tweet)
            source = original or tweet
            text, images, has_video = _tweet_text_and_images(source)
            if original:
                screen = _tweet_screen_name(original)
                if screen and not text.startswith(f"RT @{screen}"):
                    text = f"RT @{screen}:\n{text}" if text else f"RT @{screen}"
            text, images = _with_quoted_content(text, images, source)
            if not text:
                if images:
                    text = "图片"
                elif has_video:
                    text = "视频"
                else:
                    continue
            post_type = "retweet" if original else ("reply" if legacy.get("in_reply_to_status_id_str") else "")
            posts.append(
                Post(
                    platform=self.platform,
                    kol_id=kol["id"],
                    kol_name=kol["name"],
                    external_id=tweet_id,
                    title=text[:80],
                    content=text,
                    url=f"https://x.com/{screen_name}/status/{tweet_id}",
                    published_at=format_published_at(
                        str(legacy.get("created_at") or "")
                    ),
                    post_type=post_type,
                    images=images,
                )
            )
        if user.get("avatar") and self.db is not None:
            current = (self.db.get_kol(kol["id"]) or {}).get("avatar_url") or ""
            if user["avatar"] != current:
                self.db.update_kol_avatar(
                    kol["id"], cache_avatar(self.db, kol["id"], user["avatar"])
                )
        # GraphQL 分页要跟 cursor 令牌，X 暂不做追平翻页；至少把「首页尾部
        # 是新帖=可能存在滚出首页的漏帖」从静默变成可感知
        if tail_is_unseen(self.db, posts):
            warn_timeline_gap(self.platform)
        return posts
