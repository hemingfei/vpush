"""调度器：轮询抓取、去重入库、推送通知、失败退避。"""
from __future__ import annotations

import asyncio
import email.utils
import json
import logging
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime

from .backup import run_scheduled
from .channels import channel_bound, channel_enabled
from .db import _UNSET, ALLOWED_PLATFORMS, DB, days_until_purge, user_plain_secret
from . import ai_analysis

# AI分析任务并发控制
_ai_task_semaphore = None
_ai_task_max_concurrent = 3  # 最多同时3个任务
_ai_task_running = set()  # 正在运行的任务ID
from .logging_setup import redact_secrets
from .fetchers.base import (
    PLATFORM_LABELS,
    Fetcher,
    Post,
    is_collapsed_translation,
    twitter_translate_enabled,
    with_twitter_display,
)
from .notifiers.base import Notifier
from .proxy import note_fetch_proxy, tick_proxy_pools

# MX 相关导入
try:
    from .services.mx_sync import MXRoomSyncService
    MX_AVAILABLE = True
except Exception as e:
    MX_AVAILABLE = False
    logger.warning("MX modules not available: %s", e)

# 全局 MX 相关变量
_mx_fetcher = None
_mx_sync_service = None


def get_mx_ws_status() -> dict:
    """获取 MX WebSocket 连接状态。"""
    if _mx_fetcher and hasattr(_mx_fetcher, "get_ws_status"):
        return _mx_fetcher.get_ws_status()
    return {
        "connected": False,
        "last_message_at": None,
        "detail": "MX 未启用或 WS 尚未初始化",
    }

logger = logging.getLogger(__name__)

WEIBO_WARNING_KEY = "weibo_warning_date"
XUEQIU_WARNING_KEY = "xueqiu_warning_date"
BACKUP_ALERT_KEY = "backup_alert_date"
PUSH_ALERT_KEY = "push_alert_last_at"
PUSH_ALERT_INTERVAL = 3600
SOURCE_ALERT_INTERVAL = 6 * 3600
SOURCE_FAIL_THRESHOLD = 3
# 账号已不存在/已停用：确认几次后停用，避免一直重试（如 X「未找到用户」上百次）。
SOURCE_GONE_DISABLE_THRESHOLD = 5
X_DIRECT_ALERT_KEY = "x_direct_alert_at"
X_DIRECT_ALERT_INTERVAL = 6 * 3600
SOURCE_OK_KEY = "source_ok_{platform}"
SOURCE_ERR_KEY = "source_err_{platform}"
SOURCE_FAILS_KEY = "source_fails_{platform}"
XUEQIU_PROBE_ALERT_KEY = "xueqiu_probe_alert_at"
COOKIE_KEEPALIVE_ALERT_KEY = "cookie_keepalive_alert_at"
WEIBO_COOKIE_TIME_KEY = "weibo_cookie_updated_at"
WEIBO_QR_RENEWAL_KEY = "weibo_qr_renewal_at"
# 平台级健康阈值告警：与 maybe_alert_source_failure（单 KOL 连续失败）互补，
# 管「平台整体变差但每轮恰有 1 个大V成功」的温水煮蛙场景。每 6 小时最多一条。
SOURCE_HEALTH_ALERT_KEY = "source_health_alert_at"
SOURCE_HEALTH_MIN_ATTEMPTS = 10  # 24h 尝试次数门槛，够多才评估成功率避免偶发误报
SOURCE_HEALTH_LOW_RATE = 70.0  # 24h 成功率低于此值告警
SOURCE_HEALTH_SILENT_HOURS = 6  # 超过 N 小时无成功抓取判定「整体静默」
SOURCE_HEALTH_CHECK_INTERVAL = 600  # 主循环里每 10 分钟检查一次
WEIBO_QR_RENEWAL_COOLDOWN = 15 * 60
PROXY_TICK_INTERVAL = 60

# X 网页端公开的 guest bearer token（来自 abs.twimg.com 前端包），用于内部翻译接口
X_GUEST_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)


def extract_tweet_id(external_id: str) -> str:
    """从 x.com / twitter.com 状态链接或纯 ID 里提取数字推文 ID。"""
    match = re.search(r"(?:x\.com|twitter\.com)/\w+/status/(\d+)", external_id or "")
    if match:
        return match.group(1)
    return (external_id or "").strip()


def parse_twitter_cookie(cookie: str) -> dict:
    """从完整 Cookie 字符串里解析 X 官方翻译所需的 auth_token / ct0。"""
    out: dict[str, str] = {}
    for part in (cookie or "").split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            if key.strip() in ("auth_token", "ct0"):
                out[key.strip()] = value.strip()
    return out


def _polling_setting(db: DB, key: str, default: int, *, positive: bool = False) -> int:
    """读取后台可覆盖的抓取配置（config_*），未设置时用启动配置默认值。"""
    if db is None:
        return default
    value = db.get_setting(key)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if positive and parsed <= 0:
        return default
    return parsed


def _polling_bool(db: DB, key: str, default: bool = False) -> bool:
    value = db.get_setting(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# 无新帖自适应降频：空轮越多间隔越长（2 倍步进），有新帖立即恢复基础间隔。
# 以下为默认值，均可在后台「数据源」页抓取设置区调参（config_* 即时生效）：
#   普通大V空轮封顶 900s（合并推送周期 600s，低活跃大V晚几分钟看到可接受）；
#   优先大V温和拉伸封顶 180s（实时性最坏 +2min）；X 直抓失败期间再 ×4（封顶 1800s）；
#   雪球组合独立高频档：基础 30s、空轮封顶 120s，调仓最坏 ~2min 内发现并实时推送；
#   次要大V低频档：基础 900s（15min）、空轮封顶 3600s（1h）、长摘要 3600s（1h）。
NORMAL_IDLE_CAP_SECONDS = 900
PRIORITY_IDLE_CAP_SECONDS = 180
X_FALLBACK_CAP_SECONDS = 1800
COMBINATION_BASE_SECONDS = 30
COMBINATION_IDLE_CAP_SECONDS = 120
SECONDARY_BASE_SECONDS = 900
SECONDARY_IDLE_CAP_SECONDS = 3600
SECONDARY_DIGEST_INTERVAL_SECONDS = 3600
SECONDARY_MIN_DIGEST_COUNT = 1


def _in_x_fallback(db: DB) -> bool:
    """X 直抓当前是否处于失败状态（最近一次失败晚于最近一次直抓成功）。"""
    fallback_at = db.get_setting("x_direct_last_fallback_at")
    if not fallback_at:
        return False
    direct_ok = db.get_setting("x_direct_last_ok_at")
    return not direct_ok or fallback_at > direct_ok


def _is_platform_wide_error(exc: BaseException) -> bool:
    """只有 cookie/登录/代理池枯竭才停整平台；单大V超时不连坐。"""
    from .proxy import ProxyUnavailable

    if isinstance(exc, ProxyUnavailable):
        return True
    text = str(exc)
    if any(token in text for token in ("cookie", "WAF", "反爬", "登录")):
        return True
    return "login" in text.lower()


def _is_terminal_kol_error(exc: BaseException) -> bool:
    """单大V已确定抓不到：账号没了、停用、或外部 ID 本身无效。"""
    text = str(exc)
    return any(
        token in text
        for token in (
            "未找到用户",
            "用户不存在或已停用",
            "UserUnavailable",
            "无法识别 X 用户名",
        )
    )


def _load_poll_tuning(
    db: DB, interval_seconds: int, priority_interval_seconds: int
) -> dict:
    """一轮抓取只读一次后台 config_*，避免每个大V反复 get_setting。"""
    return {
        "interval": interval_seconds,
        "priority_interval": priority_interval_seconds,
        "combination_base": _polling_setting(
            db, "config_combination_base_seconds", COMBINATION_BASE_SECONDS, positive=True
        ),
        "combination_cap": _polling_setting(
            db, "config_combination_idle_cap_seconds", COMBINATION_IDLE_CAP_SECONDS, positive=True
        ),
        "priority_cap": _polling_setting(
            db, "config_priority_idle_cap_seconds", PRIORITY_IDLE_CAP_SECONDS, positive=True
        ),
        "secondary_base": _polling_setting(
            db, "config_secondary_base_seconds", SECONDARY_BASE_SECONDS, positive=True
        ),
        "secondary_cap": _polling_setting(
            db, "config_secondary_idle_cap_seconds", SECONDARY_IDLE_CAP_SECONDS, positive=True
        ),
        "normal_cap": _polling_setting(
            db, "config_normal_idle_cap_seconds", NORMAL_IDLE_CAP_SECONDS, positive=True
        ),
        "x_fallback_cap": _polling_setting(
            db, "config_x_fallback_cap_seconds", X_FALLBACK_CAP_SECONDS, positive=True
        ),
        "x_fallback": _in_x_fallback(db),
        "translate_twitter": _polling_bool(db, "config_translate_twitter_content", False),
    }


def _effective_interval(
    db: DB,
    kol: dict,
    state: PlatformState,
    interval_seconds: int,
    priority_interval_seconds: int,
    tuning: dict | None = None,
) -> int:
    """单个大V本轮的有效抓取间隔。

    基础间隔（雪球组合高频档 > 优先大V > 普通大V）× 空轮拉伸（2 倍步进，
    封顶）→ 有效间隔；平台为 X 且直抓失败时再 ×4（封顶），避免空打已挂接口。
    各档位数值可在后台「数据源」页调参。
    """
    if tuning is None and db is not None:
        tuning = _load_poll_tuning(db, interval_seconds, priority_interval_seconds)
    if kol["platform"] == "combination":
        base = (tuning or {}).get("combination_base") or COMBINATION_BASE_SECONDS
        cap = (tuning or {}).get("combination_cap") or COMBINATION_IDLE_CAP_SECONDS
    else:
        if kol.get("priority"):
            base = priority_interval_seconds
            cap = (tuning or {}).get("priority_cap") or PRIORITY_IDLE_CAP_SECONDS
        elif kol.get("secondary"):
            base = (tuning or {}).get("secondary_base") or SECONDARY_BASE_SECONDS
            cap = (tuning or {}).get("secondary_cap") or SECONDARY_IDLE_CAP_SECONDS
        else:
            base = interval_seconds
            cap = (tuning or {}).get("normal_cap") or NORMAL_IDLE_CAP_SECONDS
    empty = min(state.empty_rounds.get(kol["id"], 0), 6)
    effective = min(base * (2**empty), cap)
    if kol["platform"] == "twitter" and (tuning or {}).get("x_fallback"):
        x_cap = (tuning or {}).get("x_fallback_cap") or X_FALLBACK_CAP_SECONDS
        effective = min(effective * 4, x_cap)  # 直抓失败期放慢，避免空打已挂的接口
    return effective


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_MYMEMORY_COOLDOWN = 30 * 60
_mymemory_skip_until = 0.0


def _already_chinese(text: str) -> bool:
    """原文已是中文就不必再译（X/MyMemory 都会空耗并刷 429）。"""
    cjk = len(_CJK_RE.findall(text))
    if cjk < 8:
        return False
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return cjk >= latin


def _x_translation_text(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    result = payload.get("result")
    if not isinstance(result, dict):
        return ""
    text = result.get("text") or ""
    return text.strip() if isinstance(text, str) else ""


def _parse_x_translation_body(body: str) -> str:
    """Grok 翻译常先推一段空 text 的 JSON，再跟译文；不能用 resp.json()。"""
    decoder = json.JSONDecoder()
    found = ""
    idx = 0
    data = body or ""
    while idx < len(data):
        while idx < len(data) and data[idx].isspace():
            idx += 1
        if idx >= len(data):
            break
        obj, idx = decoder.raw_decode(data, idx)
        text = _x_translation_text(obj)
        if text:
            found = text
    return found


def translate_text(
    text: str,
    target: str = "zh-CN",
    client=None,
    tweet_id: str | None = None,
    twitter_cookie: str | None = None,
    **_ignored,
) -> str:
    """把 X 内容转成中文。优先官方翻译，失败回退 MyMemory。"""
    import httpx

    global _mymemory_skip_until

    text = (text or "").strip()
    if not text or _already_chinese(text):
        return text
    if twitter_cookie is None:
        from .fetchers.twitter import configured_twitter_cookie

        twitter_cookie = configured_twitter_cookie()
    owns_client = client is None
    client = client or httpx.Client(timeout=15)
    errors = []
    try:
        x_cookie = parse_twitter_cookie(twitter_cookie)
        if x_cookie.get("auth_token") and x_cookie.get("ct0"):
            try:
                if tweet_id:
                    payload = {
                        "content_type": "POST",
                        "id": tweet_id,
                        "dst_lang": "zh-cn",
                        "include_polls": True,
                    }
                else:
                    payload = {
                        "content_type": "TEXT",
                        "text": text[:2000],
                        "dst_lang": "zh-cn",
                    }
                resp = client.post(
                    "https://api.x.com/2/grok/translation.json",
                    headers={
                        "Authorization": f"Bearer {X_GUEST_BEARER_TOKEN}",
                        "Content-Type": "application/json",
                        "Cookie": (
                            f"auth_token={x_cookie['auth_token']}; ct0={x_cookie['ct0']}; lang=zh-CN"
                        ),
                        "x-csrf-token": x_cookie["ct0"],
                        "x-twitter-active-user": "yes",
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                        ),
                    },
                    json=payload,
                )
                resp.raise_for_status()
                translated = _parse_x_translation_body(resp.text)
                if translated and not is_collapsed_translation(translated, text):
                    return translated
            except Exception as exc:  # noqa: BLE001
                errors.append(f"x_translate: {exc}")
            if len(text) > 500:
                return text
        if time.monotonic() < _mymemory_skip_until:
            return text
        try:
            resp = client.get(
                "https://api.mymemory.translated.net/get",
                params={"q": text[:500], "langpair": "en|zh-CN"},
            )
            if resp.status_code == 429:
                _mymemory_skip_until = time.monotonic() + _MYMEMORY_COOLDOWN
                logger.warning("MyMemory 翻译限流，%d 分钟内回退原文", _MYMEMORY_COOLDOWN // 60)
                return text
            resp.raise_for_status()
            translated = ((resp.json() or {}).get("responseData") or {}).get("translatedText") or ""
            if translated and not is_collapsed_translation(translated, text):
                return translated
        except Exception as exc:  # noqa: BLE001
            errors.append(f"mymemory: {exc}")
    finally:
        if owns_client:
            client.close()
    if errors:
        raise RuntimeError("; ".join(errors) or "无可用翻译源")
    return text


class PushRetryQueue:
    """推送失败重试队列：指数退避（1m/5m/15m），超过次数放弃。"""

    RETRY_DELAYS = (60, 300, 900)

    def __init__(self):
        self._items: dict[tuple, dict] = {}
        self._lock = threading.Lock()

    def add(self, post: Post, channel: str, user_id: int | None = None) -> None:
        # external_id 在不同平台可能相同（如数字 UID），key 必须带上平台避免互相覆盖
        key = (channel, user_id, post.platform, post.external_id)
        with self._lock:
            if key not in self._items:
                self._items[key] = {
                    "post": post,
                    "channel": channel,
                    "user_id": user_id,
                    "attempts": 0,
                    "next_at": time.monotonic() + self.RETRY_DELAYS[0],
                    "key": key,
                }

    def due(self) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            return [item for item in list(self._items.values()) if item["next_at"] <= now]

    def pending(self) -> int:
        with self._lock:
            return len(self._items)

    def fail(self, item: dict) -> bool:
        """记录一次重试失败；超过次数上限则移除，返回是否继续保留。"""
        with self._lock:
            item["attempts"] += 1
            if item["attempts"] >= len(self.RETRY_DELAYS):
                self._items.pop(item["key"], None)
                return False
            item["next_at"] = time.monotonic() + self.RETRY_DELAYS[item["attempts"]]
            return True

    def drop(self, item: dict) -> None:
        with self._lock:
            self._items.pop(item["key"], None)


def _post_sort_key(post: Post) -> float:
    """帖子发布时间 → 时间戳；无法解析的排在最后（保持抓取顺序）。"""
    raw = (post.published_at or "").strip()
    if not raw:
        return float("inf")
    if raw.isdigit():
        try:
            ts = int(raw)
            return ts / 1000 if ts > 1e12 else float(ts)
        except ValueError:
            pass
    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",  # 微博
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            return datetime.strptime(raw, fmt).timestamp()
        except ValueError:
            continue
    try:
        # RFC 2822（RSS 源常用），如 "Tue, 04 Aug 2026 21:00:00 +0800"
        return email.utils.parsedate_to_datetime(raw).timestamp()
    except (TypeError, ValueError):
        return float("inf")


def _sub_type_matches(sub_type: str, post_type: str) -> bool:
    """订阅类型（post/reply/both）是否覆盖这条动态（post/reply/空）。"""
    if post_type == "reply":
        return sub_type in ("reply", "both")
    return sub_type in ("post", "both", "")


def _can_still_push(user: dict, channel: str, post: Post, db: DB) -> bool:
    """推送前复查用户状态：通知开关、渠道选择与绑定、订阅关系与类型是否仍成立。

    失败重试/重启恢复时使用，避免退订、关闭通知或改选渠道的用户仍收到旧帖重试。
    """
    if not user or not user.get("notify_enabled"):
        return False
    if not channel_enabled(user, channel):
        return False
    if channel == "telegram" and not user.get("telegram_chat_id"):
        return False
    if channel == "feishu" and not channel_bound(user, "feishu", db=db):
        return False
    if channel == "wecom" and not user.get("wecom_webhook"):
        return False
    if channel == "bark" and not user.get("bark_key"):
        return False
    if channel == "webpush" and not channel_bound(user, "webpush", db=db):
        return False
    sub_type = db.subscribed_kol_types(user["id"]).get(post.kol_id)
    if sub_type is None:
        return False
    return _sub_type_matches(sub_type, post.post_type)


def _in_dnd_window(user: dict, now=None) -> bool:
    """用户是否处于免打扰时段（支持跨午夜；start/end 留空或相同时关闭）。"""
    start = (user.get("dnd_start") or "").strip()
    end = (user.get("dnd_end") or "").strip()
    if not start or not end or start == end:
        return False
    now = now or datetime.now()
    cur = now.strftime("%H:%M")
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end  # 跨午夜（如 23:00-07:00）


def _dnd_favorite_passthrough(user: dict) -> bool:
    """用户是否允许「特别关注」的大V穿透免打扰（默认不穿透）。"""
    return bool(user.get("dnd_allow_favorite"))


def _keyword_hit(keywords: list[str], post: Post) -> bool:
    """帖子正文/标题是否命中任一关键词（大小写不敏感）。"""
    if not keywords:
        return False
    text = "\n".join(
        part
        for part in (
            post.content,
            post.title,
            post.content_src,
            post.title_src,
        )
        if part
    ).lower()
    return any(kw.lower() in text for kw in keywords if kw.strip())


class PlatformState:
    """每个平台的抓取退避，以及按大 V 隔离的告警状态。"""

    def __init__(self):
        self.fail_count = 0
        self.skip_until = 0.0
        self.kol_skip_until: dict[int, float] = {}
        self.last_fetched: dict[int, float] = {}
        self.empty_rounds: dict[int, int] = {}  # 无新帖连续空轮数，驱动自适应降频
        self.kol_fails: dict[int, int] = {}
        self.alerted_kols: set[int] = set()


# 告警总开关：默认 None 时回退环境变量 ALERTS_ENABLED（兼容测试与老配置）；
# 应用启动时由 main.py 按 config.alerts_enabled 注入（config.yaml 与环境变量均可配置）
_ALERTS_ENABLED_FLAG: bool | None = None


def set_alerts_enabled(value: bool) -> None:
    """应用启动时注入告警总开关（config.alerts_enabled 统一来源）。"""
    global _ALERTS_ENABLED_FLAG
    _ALERTS_ENABLED_FLAG = bool(value)


def _alerts_enabled() -> bool:
    """管理员告警总开关（默认 true）。

    本地开发/测试实例务必置 false：用生产 config 启动时会抢生产 bot 轮询、
    并向真实管理员误发告警（典型场景：没配 TWITTER_COOKIE 触发 X 降级告警）。
    """
    if _ALERTS_ENABLED_FLAG is not None:
        return _ALERTS_ENABLED_FLAG
    return os.environ.get("ALERTS_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _send_admin_text(notifiers: list[Notifier], message: str, what: str) -> None:
    # 告警正文常含上游异常原文（bot token/webhook key 等 URL 凭据），发出前脱敏
    message = redact_secrets(message)
    for notifier in notifiers:
        try:
            notifier.send_text(message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s发送失败 channel=%s err=%s", what, notifier.channel, exc)


def _cooldown_ok(db: DB, key: str, interval: int) -> bool:
    now = int(time.time())
    last = db.get_setting(key)
    if last:
        try:
            if now - int(last) < interval:
                return False
        except (TypeError, ValueError):
            pass
    db.set_setting(key, str(now))
    return True


def _daily_ok(db: DB, key: str) -> bool:
    today = time.strftime("%Y-%m-%d")
    if db.get_setting(key) == today:
        return False
    db.set_setting(key, today)
    return True


def maybe_alert_source_failure(
    db: DB, notifiers: list[Notifier], platform: str, kol_name: str, detail: str, fail_count: int
) -> bool:
    """数据源连续失败时向管理员推送告警（每平台每 6 小时最多一次）。发出了返回 True。"""
    if not _alerts_enabled() or not _cooldown_ok(db, f"source_alert_{platform}", SOURCE_ALERT_INTERVAL):
        return False
    label = PLATFORM_LABELS.get(platform, platform)
    _send_admin_text(
        notifiers,
        f"⚠️ 数据源告警：{label}「{kol_name}」连续失败 {fail_count} 次。\n错误：{detail[:200]}",
        "数据源告警",
    )
    return True


def maybe_alert_kol_auto_disabled(
    notifiers: list[Notifier], platform: str, kol_name: str, detail: str, fail_count: int
) -> None:
    """自动停用大V后通知管理员（不受平台告警冷却限制，只发一次）。"""
    if not _alerts_enabled():
        return
    label = PLATFORM_LABELS.get(platform, platform)
    _send_admin_text(
        notifiers,
        (
            f"⏸️ 已自动停用：{label}「{kol_name}」连续失败 {fail_count} 次，已暂停抓取。\n"
            f"错误：{detail[:200]}\n"
            "可在大V管理里重新启用。"
        ),
        "数据源自动停用",
    )


def maybe_alert_source_recovered(
    db: DB, notifiers: list[Notifier], platform: str, kol_name: str
) -> None:
    """数据源从连续失败中恢复后通知管理员。"""
    if not _alerts_enabled():
        return
    label = PLATFORM_LABELS.get(platform, platform)
    _send_admin_text(
        notifiers,
        f"✅ 数据源已恢复：{label}「{kol_name}」重新抓取成功。",
        "数据源恢复通知",
    )


def maybe_alert_source_health(db: DB, notifiers: list[Notifier]) -> None:
    """平台级健康阈值告警：24h 成功率过低、或长时间无成功抓取（整体静默）。

    与 maybe_alert_source_failure（单 KOL 连续失败）互补——那个管单点失败，
    这里管「平台整体变差但每轮恰有 1 个大V成功」的温水煮蛙场景：
    降频后每轮 KOL 少，成功率口径可能仍高，但若长时间整体没成功就该人工介入。
    每 6 小时最多一条（SOURCE_ALERT_INTERVAL），多平台问题合并推送。
    """
    if not _alerts_enabled():
        return
    now = int(time.time())
    last = db.get_setting(SOURCE_HEALTH_ALERT_KEY)
    if last:
        try:
            if now - int(last) < SOURCE_ALERT_INTERVAL:
                return
        except (TypeError, ValueError):
            pass
    issues = []
    for platform in sorted(ALLOWED_PLATFORMS):
        if not any(k["enabled"] for k in db.list_kols(platform=platform)):
            continue  # 无启用大V的平台不评估
        label = PLATFORM_LABELS.get(platform, platform)
        # 1) 24h 成功率过低（尝试次数足够多才评估，避免偶发误报）
        ev = db.source_event_stats(platform, 24)
        total = ev["ok"] + ev["fail"]
        if total >= SOURCE_HEALTH_MIN_ATTEMPTS:
            rate = ev["ok"] * 100 / total
            if rate < SOURCE_HEALTH_LOW_RATE:
                issues.append(
                    f"{label}：24h 成功率 {rate:.0f}%（成功 {ev['ok']}/失败 {ev['fail']}）"
                )
        # 2) 长时间无成功抓取（整体静默，如平台全挂但退避未触发单点告警）
        ok_at = db.get_setting(f"source_ok_{platform}")
        if ok_at:
            try:
                silent_hours = (now - int(ok_at)) / 3600
            except (TypeError, ValueError):
                silent_hours = 0
            if silent_hours >= SOURCE_HEALTH_SILENT_HOURS:
                issues.append(f"{label}：已 {silent_hours:.0f} 小时无成功抓取")
    if not issues:
        return
    db.set_setting(SOURCE_HEALTH_ALERT_KEY, str(now))
    _send_admin_text(
        notifiers,
        "⚠️ 数据源健康告警\n" + "\n".join(f"· {i}" for i in issues),
        "数据源健康告警",
    )


def maybe_warn_weibo_login(db: DB, notifiers: list[Notifier], detail: str) -> None:
    """微博自动登录失败时向各渠道推告警，每天最多一次。"""
    if not _alerts_enabled() or not _daily_ok(db, WEIBO_WARNING_KEY):
        return
    _send_admin_text(
        notifiers,
        f"⚠️ 微博 cookie 自动登录失败，请检查 weibo.username/password 或手动更新 cookie。详情：{detail[:200]}",
        "微博告警",
    )


def maybe_warn_xueqiu_cookie(db: DB, notifiers: list[Notifier], detail: str) -> None:
    """雪球 cookie 失效时向各渠道推告警，每天最多一次。"""
    if not _alerts_enabled() or not _daily_ok(db, XUEQIU_WARNING_KEY):
        return
    _send_admin_text(
        notifiers,
        f"⚠️ 雪球 cookie 失效，请到后台「数据源 → Cookie 管理」粘贴新 Cookie。详情：{detail[:200]}",
        "雪球告警",
    )


def maybe_alert_backup_failure(db: DB, notifiers: list[Notifier], detail: str) -> None:
    """定时备份失败时向管理员告警，每天最多一次。"""
    if not _alerts_enabled() or not _daily_ok(db, BACKUP_ALERT_KEY):
        return
    _send_admin_text(notifiers, f"⚠️ 定时备份失败：{detail[:200]}", "备份告警")


def maybe_alert_push_failure(db: DB, notifiers: list[Notifier], detail: str) -> None:
    """用户推送失败时向管理员告警，每小时最多一次避免刷屏。"""
    if not _alerts_enabled() or not _cooldown_ok(db, PUSH_ALERT_KEY, PUSH_ALERT_INTERVAL):
        return
    _send_admin_text(
        notifiers,
        f"⚠️ 用户推送失败（每小时最多提醒一次）：{detail[:200]}",
        "推送告警",
    )


def _x_fallback_advice(reason: str) -> str:
    """按降级原因给出对应建议，避免把瞬时故障误报成 Cookie 失效。

    优先看响应体里的 X 错误 code（_graphql 已把 code 拼进原因）：
    - code 353：X 反爬规则更新（需会话绑定的 guest token），要升级代码
    - code 89 / 32：auth token 真失效，才建议重新登录
    - queryId：接口轮换，要更新代码
    无 code 的裸 401/403 两者皆有可能，提示兼顾。
    """
    text = (reason or "").lower()
    if "code 353" in text:
        return "X 反爬规则已更新（GraphQL 需会话绑定的 guest token），需要升级代码后重新部署。"
    if any(k in text for k in ("invalidrequest", "queryid")):
        return "X 已轮换 GraphQL queryId，需要更新代码中的 DEFAULT_QUERY_IDS 后重新部署。"
    if "未配置" in text and "twitter_cookie" in text:
        return "未配置 X Cookie，请到后台「数据源 → Cookie 管理」粘贴，或设置 TWITTER_COOKIE 后重启。"
    if any(k in text for k in (
        "code 89", "code 32", "invalid or expired token",
        "could not authenticate", "not authorized",
    )):
        return "请到后台「数据源 → Cookie 管理」更新 X Cookie，保存后即时生效。"
    if any(k in text for k in (
        "500", "502", "503", "504", "429", "serviceunavailable", "unavailable",
        "ssl", "timeout", "timed out", "eof", "connection", "reset", "network",
        "deadline",  # DeadlineExceeded: X 后端超时，同 503 一类瞬时故障
    )):
        return "X 服务端暂时不可用或网络抖动，无需操作；持续出现再检查 Cookie。"
    if any(k in text for k in ("401", "403", "forbidden", "unauthorized")):
        return "X 拒绝了请求（401/403）：请到后台「数据源 → Cookie 管理」更新 X Cookie（刚更新仍复现则可能是接口规则变更，需升级代码）。"
    return "失败期间会放慢采集并告警，请留意是否持续失败。"


def maybe_alert_x_fallback(db: DB, notifiers: list[Notifier]) -> None:
    """X 直抓失败时通知管理员（每 6 小时最多一次）。"""
    if not _alerts_enabled():
        return
    fallback_at = db.get_setting("x_direct_last_fallback_at")
    if not fallback_at:
        return
    try:
        fallback_ts = int(fallback_at)
    except (TypeError, ValueError):
        return
    now = int(time.time())
    last = db.get_setting(X_DIRECT_ALERT_KEY)
    if last:
        try:
            if int(last) >= fallback_ts:
                return  # 本次降级已告警过
            if now - int(last) < X_DIRECT_ALERT_INTERVAL:
                return  # 仍在告警冷却期
        except (TypeError, ValueError):
            pass
    reason = db.get_setting("x_direct_fallback_reason") or "X 官方接口不可用"
    message = (
        "⚠️ X 直抓失败，本轮未取到新帖\n"
        f"原因：{reason[:200]}\n"
        f"{_x_fallback_advice(reason)}"
    )
    _send_admin_text(notifiers, message, "X 失败告警")
    db.set_setting(X_DIRECT_ALERT_KEY, str(now))


def notify_subscribers(
    db: DB,
    post_id: int,
    post: Post,
    notifiers_config,
    notifiers=None,
    retry_queue: PushRetryQueue | None = None,
    client=None,
    dnd_buffer: dict[int, list[Post]] | None = None,
    secondary_buffer: dict[int, list[Post]] | None = None,
    only_favorites: bool = False,
) -> None:
    """把新帖推送给订阅了该大V的用户（各自绑定的渠道）。"""
    if notifiers_config is None:
        return
    import httpx

    from .channels import CHANNELS, channel_bound, channel_enabled, deliver_post

    owns_client = client is None
    client = client or httpx.Client(timeout=15)
    try:
        subscribers = db.subscribers_of_kol(post.kol_id)
        keywords_by_user = db.get_users_keywords([u["id"] for u in subscribers])
        for user in subscribers:
            sub_type = user.get("subscribe_type") or "post"
            if not _sub_type_matches(sub_type, post.post_type):
                continue  # 订阅类型不覆盖该动态（帖子/回复分订）
            favorite = bool(user.get("favorite"))
            if only_favorites and not favorite:
                continue
            keywords = keywords_by_user.get(user["id"], [])
            keyword_hit = _keyword_hit(keywords, post)
            if (
                dnd_buffer is not None
                and _in_dnd_window(user)
                and not (favorite and _dnd_favorite_passthrough(user))
                and not keyword_hit
            ):
                # 免打扰时段：缓冲，结束时统一补一条汇总（关键词命中实时穿透）
                dnd_buffer.setdefault(user["id"], []).append(post)
                continue
            # 个人次要：非 favorite 用户进延迟缓冲，按 digest 周期统一推摘要
            if bool(user.get("secondary")) and not favorite and secondary_buffer is not None:
                secondary_buffer.setdefault(user["id"], []).append(post)
                continue
            delivery = with_twitter_display(post, twitter_translate_enabled(user))
            for channel in CHANNELS:
                if not channel_enabled(user, channel) or not channel_bound(user, channel, notifiers_config, db):
                    continue
                deliver_post(
                    db,
                    post_id,
                    delivery,
                    user,
                    channel,
                    notifiers_config,
                    client,
                    retry_queue=retry_queue,
                    alert_notifiers=notifiers,
                    alert_cb=maybe_alert_push_failure,
                    favorite=favorite,
                    keyword=keyword_hit,
                )
    finally:
        if owns_client:
            client.close()


def poll_once(
    db: DB,
    fetchers: dict[str, Fetcher],
    notifiers: list[Notifier],
    states: dict[str, PlatformState] | None = None,
    notifiers_config=None,
    interval_seconds: int = 180,
    priority_interval_seconds: int = 60,
    digest: dict[int, list[Post]] | None = None,
    retry_queue: PushRetryQueue | None = None,
    dnd_buffer: dict[int, list[Post]] | None = None,
    secondary_buffer: dict[int, list[Post]] | None = None,
    llm_config=None,
) -> None:
    """执行一轮：并发抓取启用 KOL → 去重 → 推送。"""
    states = states if states is not None else {}
    now = time.monotonic()
    tuning = _load_poll_tuning(db, interval_seconds, priority_interval_seconds)
    from .stock_universe import aliases_for_tagging, names_for_plain_text_tagging

    tag_rules = db.get_tag_vocabulary()
    excluded = db.get_stock_name_exclusions()
    stock_names = names_for_plain_text_tagging(db.get_stock_names(), excluded)
    stock_aliases = aliases_for_tagging(db.get_stock_aliases(), excluded)
    # 无人订阅的大V不抓取：没有订阅者就没有推送/阅读对象，白耗抓取配额。
    # 新上架的大V需要先有用户订阅（订阅广场/组合订阅）才开始抓取。
    subscribed_ids = db.kol_ids_with_subscribers()
    jobs = []
    for kol in db.list_kols():
        if not kol["enabled"]:
            continue
        if kol["id"] not in subscribed_ids:
            continue
        fetcher = fetchers.get(kol["platform"])
        if fetcher is None:
            continue
        state = states.setdefault(kol["platform"], PlatformState())
        if now < state.skip_until:
            continue
        if now < state.kol_skip_until.get(kol["id"], 0):
            continue
        # 自适应间隔：优先大V更短，空轮拉伸，X 直抓失败期间加倍
        effective = _effective_interval(
            db, kol, state, interval_seconds, priority_interval_seconds, tuning
        )
        # 从未抓取过的大V首轮立即抓取（monotonic 基准在容器启动早期可能小于间隔，
        # 用「从未抓取」标记判断而不是拿 0 当基准，避免首轮被误跳过）
        if kol["id"] in state.last_fetched and now - state.last_fetched[kol["id"]] < effective:
            continue
        jobs.append((kol, fetcher, state))
    if not jobs:
        maybe_alert_x_fallback(db, notifiers)
        return
    # 并发抓取：跨平台并行、同平台最多 2 个并发
    platforms = {kol["platform"] for kol, _, _ in jobs}
    platform_sem = {p: threading.Semaphore(2) for p in platforms}
    platform_lock = {p: threading.Lock() for p in platforms}
    # 本轮各平台 ok/fail 计数（稳定性事件表，避免每轮每个大V都记一条）
    round_stats: dict[str, dict] = {}

    import httpx

    def _worker(job):
        kol, fetcher, state = job
        client = httpx.Client(timeout=15)
        try:
            with platform_sem[kol["platform"]]:
                _fetch_kol_once(
                    db,
                    fetchers,
                    notifiers,
                    states,
                    kol,
                    fetcher,
                    state,
                    now,
                    interval_seconds,
                    priority_interval_seconds,
                    notifiers_config,
                    digest,
                    retry_queue,
                    platform_lock[kol["platform"]],
                    client,
                    dnd_buffer,
                    secondary_buffer,
                    round_stats,
                    llm_config,
                    tuning,
                    tag_rules,
                    stock_names,
                    stock_aliases,
                )
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as ex:
        list(ex.map(_worker, jobs))
    for platform, st in round_stats.items():
        if st["ok"]:
            db.add_source_event(
                platform,
                "ok",
                f"ok={st['ok']} fail={st['fail']}",
                ok_count=st["ok"],
            )
        if st["fail"]:
            db.add_source_event(
                platform,
                "fail",
                f"fail={st['fail']} ok={st['ok']} kol={st['kol']} err={st['err'][:200]}",
                fail_count=st["fail"],
            )
        # 健康最终状态按整轮聚合写入（worker 内不再写），并发顺序不再影响结果
        if st["fail"]:
            db.set_setting(SOURCE_ERR_KEY.format(platform=platform), st["err"][:300])
            db.set_setting(SOURCE_FAILS_KEY.format(platform=platform), str(st["fail"]))
            db.set_setting(
                f"source_next_retry_at_{platform}",
                str(int(time.time()) + min(30 * (2 ** (st["fail"] - 1)), 600)),
            )
        elif st["ok"]:
            db.set_setting(SOURCE_OK_KEY.format(platform=platform), str(int(time.time())))
            db.set_setting(SOURCE_ERR_KEY.format(platform=platform), "")
            db.set_setting(SOURCE_FAILS_KEY.format(platform=platform), "0")
            # 整轮无失败才清掉重试倒计时；有失败保留，避免并发顺序导致状态抖动
            db.set_setting(f"source_next_retry_at_{platform}", "")
    logger.info("轮询完成：%d 个大V，耗时 %.0fms", len(jobs), (time.monotonic() - now) * 1000)
    maybe_alert_x_fallback(db, notifiers)


def _fetch_kol_once(
    db: DB,
    fetchers: dict[str, Fetcher],
    notifiers: list[Notifier],
    states: dict[str, PlatformState],
    kol: dict,
    fetcher: Fetcher,
    state: PlatformState,
    now: float,
    interval_seconds: int,
    priority_interval_seconds: int,
    notifiers_config,
    digest: dict[int, list[Post]] | None,
    retry_queue: PushRetryQueue | None,
    state_lock: threading.Lock,
    client=None,
    dnd_buffer: dict[int, list[Post]] | None = None,
    secondary_buffer: dict[int, list[Post]] | None = None,
    round_stats: dict[str, dict] | None = None,
    llm_config=None,
    tuning: dict | None = None,
    tag_rules=None,
    stock_names=None,
    stock_aliases=None,
) -> None:
    """并发 worker：抓取单个大V并处理新帖（状态读写加锁保护）。"""
    effective = _effective_interval(
        db, kol, state, interval_seconds, priority_interval_seconds, tuning
    )
    # 与 poll_once 一致：从未抓取过的大V立即抓取，避免用 0 当基准误跳过首轮
    if kol["id"] in state.last_fetched and now - state.last_fetched[kol["id"]] < effective:
        return
    # 轮内随机错峰（0.2~1.2s），避免同平台并发扎堆
    time.sleep(random.uniform(0.2, 1.2))
    try:
        posts = fetcher.fetch(kol)
    except Exception as exc:  # noqa: BLE001 - 单源失败不影响其他
        import httpx
        from curl_cffi.requests.errors import RequestsError

        from .proxy import ProxyUnavailable

        if isinstance(exc, (httpx.TransportError, RequestsError, ProxyUnavailable)):
            note_fetch_proxy(fetcher, False, str(exc))
        should_alert = False
        should_disable = False
        with state_lock:
            state.fail_count += 1
            delay = min(30 * (2 ** (state.fail_count - 1)), 600)
            until = time.monotonic() + delay
            state.kol_skip_until[kol["id"]] = until
            if _is_platform_wide_error(exc):
                state.skip_until = until
            if round_stats is not None:
                st = round_stats.setdefault(
                    kol["platform"], {"ok": 0, "fail": 0, "err": "", "kol": ""}
                )
                st["fail"] += 1
                st["err"] = str(exc)[:300]
                st["kol"] = kol["name"]
            kol_fail = state.kol_fails.get(kol["id"], 0) + 1
            state.kol_fails[kol["id"]] = kol_fail
            should_alert = kol_fail == SOURCE_FAIL_THRESHOLD or kol_fail % 10 == 0
            if (
                kol_fail >= SOURCE_GONE_DISABLE_THRESHOLD
                and _is_terminal_kol_error(exc)
                and not _is_platform_wide_error(exc)
            ):
                should_disable = True
                state.kol_fails[kol["id"]] = 0
                state.alerted_kols.discard(kol["id"])
        if should_disable:
            db.update_kol(kol["id"], enabled=False)
            logger.warning(
                "自动停用大V platform=%s kol=%s fails=%s err=%s",
                kol["platform"],
                kol["name"],
                kol_fail,
                exc,
            )
            maybe_alert_kol_auto_disabled(
                notifiers, kol["platform"], kol["name"], str(exc), kol_fail
            )
        elif should_alert:
            if maybe_alert_source_failure(
                db, notifiers, kol["platform"], kol["name"], str(exc), kol_fail
            ):
                with state_lock:
                    state.alerted_kols.add(kol["id"])
        logger.warning(
            "抓取失败 platform=%s kol=%s err=%s 下次尝试 %.0fs 后",
            kol["platform"],
            kol["name"],
            exc,
            delay,
        )
        if kol["platform"] == "weibo" and ("登录" in str(exc) or "login" in str(exc).lower()):
            maybe_warn_weibo_login(db, notifiers, str(exc))
        if kol["platform"] == "xueqiu" and any(
            kw in str(exc) for kw in ("cookie", "WAF", "反爬")
        ):
            maybe_warn_xueqiu_cookie(db, notifiers, str(exc))
        # 数据源健康最终状态由 poll_once 依据 round_stats 聚合后一次性写入，
        # 避免并发 worker 互相清空同平台的成功/失败状态
        return
    note_fetch_proxy(fetcher, True)
    recovered = False
    with state_lock:
        recovered = kol["id"] in state.alerted_kols
        if recovered:
            state.alerted_kols.discard(kol["id"])
        state.kol_fails[kol["id"]] = 0
        state.fail_count = 0
        state.skip_until = 0.0
        state.kol_skip_until.pop(kol["id"], None)
        state.last_fetched[kol["id"]] = time.monotonic()
        if round_stats is not None:
            st = round_stats.setdefault(
                kol["platform"], {"ok": 0, "fail": 0, "err": "", "kol": ""}
            )
            st["ok"] += 1
    if recovered:
        maybe_alert_source_recovered(db, notifiers, kol["platform"], kol["name"])
    # 按发布时间升序推送，避免各平台返回顺序（置顶等）导致乱序
    posts = sorted(posts, key=_post_sort_key)
    existing_keys = db.existing_post_keys([(p.platform, p.external_id) for p in posts])
    translate_twitter = bool((tuning or {}).get("translate_twitter"))
    for post in posts:
        post.category = kol.get("category_name") or ""
        if (
            post.platform == "twitter"
            and translate_twitter
            and (post.platform, post.external_id) not in existing_keys
        ):
            # 仅翻译新帖，避免每轮重复调用翻译接口
            try:
                tweet_id = extract_tweet_id(post.external_id)
                from .fetchers.twitter import configured_twitter_cookie

                tw_cookie = configured_twitter_cookie(db)
                x_cookie = parse_twitter_cookie(tw_cookie)
                post.title_src = post.title or ""
                post.content_src = post.content or ""
                if tweet_id and x_cookie.get("auth_token") and x_cookie.get("ct0"):
                    # X 官方翻译按整条推文返回，翻译一次后拆出标题
                    translated = translate_text(
                        post.content or "",
                        tweet_id=tweet_id,
                        twitter_cookie=tw_cookie,
                    )
                    post.content = translated
                    post.title = translated.splitlines()[0][:80] if translated else (post.title or "")
                else:
                    post.title = translate_text(post.title or "")
                    post.content = translate_text(post.content or "")
            except Exception as exc:  # noqa: BLE001 - 翻译失败退回原文
                logger.warning("X 内容翻译失败 post=%s err=%s", post.external_id, exc)
    # 关键词规则打标：仅对新帖（与翻译同判据），纯本地计算零成本，异常不影响入库
    try:
        from .tagging import rule_tag_posts, stock_tag_posts

        fresh = [p for p in posts if (p.platform, p.external_id) not in existing_keys]
        if fresh:
            if tag_rules is None:
                tag_rules = db.get_tag_vocabulary()
            tagged = rule_tag_posts(fresh, tag_rules)
            if stock_names is None:
                from .stock_universe import names_for_plain_text_tagging

                stock_names = names_for_plain_text_tagging(
                    db.get_stock_names(), db.get_stock_name_exclusions()
                )
            if stock_aliases is None:
                stock_aliases = db.get_stock_aliases()
            stock_tagged = stock_tag_posts(fresh, stock_names, aliases=stock_aliases)
            for i, post in enumerate(fresh):
                # 合并：话题标签（≤3）+ 股票标签（≤2），总上限 5
                topics = tagged.get(i, [])
                stocks = stock_tagged.get(i, [])
                post.tags = list(topics[:3]) + list(stocks[:2])
    except Exception as exc:  # noqa: BLE001 - 打标失败不影响抓取/推送
        logger.warning(
            "规则打标失败 platform=%s kol=%s err=%s", kol["platform"], kol["name"], exc
        )
    # 批量入库（一个事务），再逐条推送
    # 首次抓取判定：baseline_ready=0 的大V（新增时写入）本轮仅建立历史基线，不推送。
    # 否则订阅新大V时，最近 N 条历史帖会一次性连推（连珠炮刷屏）。
    # 首次成功 fetch（含空列表）即打标：空账号/偶发空窗后，下一轮新帖必须正常推送。
    first_fetch = not kol.get("baseline_ready")
    post_ids = db.insert_posts_batch(posts)
    if first_fetch:
        db.mark_kol_baseline(kol["id"])
    # 空轮判定用「本轮是否新增入库」：时间线接口总是返回最近 N 条（含旧帖），
    # 用 posts 是否为空会永远判为有新帖，降频失效；有新帖立即重置，否则空轮 +1
    new_count = sum(1 for pid in post_ids if pid is not None)
    with state_lock:
        state.empty_rounds[kol["id"]] = 0 if new_count else state.empty_rounds.get(kol["id"], 0) + 1
    # 大V 屏蔽词命中的帖在入库时已标记拦截：只留档，不进任何推送链路
    blocked_ids = db.blocked_post_ids([pid for pid in post_ids if pid is not None])
    for post, post_id in zip(posts, post_ids):
        if post_id is None:
            continue
        if post_id in blocked_ids:
            logger.info(
                "关键词拦截不推送 platform=%s kol=%s id=%s",
                post.platform, post.kol_name, post.external_id,
            )
            continue
        if first_fetch:
            logger.info("基线入库 platform=%s kol=%s id=%s", post.platform, post.kol_name, post.external_id)
            continue  # 首轮仅入库建基线，历史帖不推送；后续轮次新帖正常推送
        logger.info("新帖 platform=%s kol=%s id=%s", post.platform, post.kol_name, post.external_id)
        if kol.get("silent"):
            # 静默源：只入库建基线/记录，不推送到任何渠道（高频星球防轰炸用）
            logger.info("静默源入库不打推送 platform=%s kol=%s id=%s", post.platform, post.kol_name, post.external_id)
            continue
        if not kol.get("priority") and kol["platform"] != "combination":
            if kol.get("secondary"):
                if secondary_buffer is not None:
                    # 次要大V：所有非特别关注订阅者进用户级合并缓冲，
                    # 跨大V按 secondary_digest_interval 周期统一推一条摘要
                    _buffer_secondary_subscribers(db, kol["id"], post, secondary_buffer)
                    notify_subscribers(
                        db, post_id, post, notifiers_config, notifiers, retry_queue,
                        client=client, dnd_buffer=dnd_buffer, secondary_buffer=secondary_buffer,
                        only_favorites=True,
                    )
                else:
                    # 次要合并禁用（secondary_digest_interval=0）时实时推送
                    notify_subscribers(
                        db, post_id, post, notifiers_config, notifiers, retry_queue,
                        client=client, dnd_buffer=dnd_buffer, secondary_buffer=secondary_buffer,
                    )
            elif digest is not None:
                # 普通大V进入合并摘要缓冲，按 digest_interval 周期统一推送
                digest.setdefault(kol["id"], []).append(post)
                _buffer_personal_secondary(db, kol["id"], post, secondary_buffer)
            else:
                notify_subscribers(
                    db, post_id, post, notifiers_config, notifiers, retry_queue,
                    client=client, dnd_buffer=dnd_buffer, secondary_buffer=secondary_buffer,
                )
        else:
            notify_subscribers(
                db, post_id, post, notifiers_config, notifiers, retry_queue,
                client=client, dnd_buffer=dnd_buffer, secondary_buffer=secondary_buffer,
            )


def _buffer_personal_secondary(db, kol_id: int, post: Post, secondary_buffer) -> None:
    """KOL 级摘要缓冲时，把个人次要用户（非特别关注）的帖子同时进用户级延迟缓冲。

    这些用户不参与 KOL 摘要（notify_digest_subscribers 会跳过），改由用户级
    延迟缓冲按次要合并周期统一推送，避免同一帖双重到达。
    """
    if secondary_buffer is None:
        return
    for user in db.subscribers_of_kol(kol_id):
        if (
            bool(user.get("secondary"))
            and not bool(user.get("favorite"))
            and _sub_type_matches(user.get("subscribe_type") or "post", post.post_type)
        ):
            secondary_buffer.setdefault(user["id"], []).append(post)


def _buffer_secondary_subscribers(db, kol_id: int, post: Post, secondary_buffer) -> None:
    """次要大V新帖：所有非特别关注订阅者进用户级合并缓冲。

    与 _buffer_personal_secondary 的区别：次要大V是全局档位，所有订阅者
    （除特别关注）都应延迟合并推送，而不是只有个人次要用户。多条次要大V
    共享同一缓冲，flush 时按用户跨大V合并成一条摘要，避免每个次要大V
    各发一条摘要。
    """
    if secondary_buffer is None:
        return
    for user in db.subscribers_of_kol(kol_id):
        if not bool(user.get("favorite")) and _sub_type_matches(
            user.get("subscribe_type") or "post", post.post_type
        ):
            secondary_buffer.setdefault(user["id"], []).append(post)


def _user_llm_config(user: dict, fallback=None, db: DB | None = None):
    """用户自配 LLM 优先；没配或地址不安全时回退站点 Grok。"""
    from .db import user_plain_secret

    if not user.get("llm_api_key"):
        return fallback
    api_key = user_plain_secret(user, "llm_api_key", db)
    if not api_key:
        return fallback
    from types import SimpleNamespace

    from .url_safety import is_allowed_user_llm_base

    api_base = (user.get("llm_api_base") or "").strip() or (
        getattr(fallback, "api_base", "") if fallback else ""
    )
    if not api_base or not is_allowed_user_llm_base(api_base):
        return fallback
    return SimpleNamespace(
        api_base=api_base,
        api_key=api_key,
        model=(user.get("llm_model") or "").strip()
        or (getattr(fallback, "model", "") if fallback else "")
        or "grok-4.6",
        user_supplied=True,
    )


def _system_llm_config(db: DB, fallback=None):
    """站点 LLM：管理员推送设置（Grok）优先，没有再退环境变量。"""
    for user in db.list_users():
        if user.get("is_admin"):
            cfg = _user_llm_config(user, db=db)
            if cfg is not None:
                return cfg
    if fallback and getattr(fallback, "api_key", ""):
        return fallback
    return None


def _admin_llm_config(db: DB, fallback=None):
    """旧名兼容，等同 _system_llm_config。"""
    return _system_llm_config(db, fallback)


def _send_digest_bundle(
    notifier,
    summary,
    posts: list[Post],
    kol: dict,
    db: DB,
    channel: str,
    user: dict,
    retry_queue: PushRetryQueue | None,
    notifiers,
) -> None:
    """发 AI 要点 + 摘要卡片。卡片发出后才算送达；仅要点成功仍入重试。"""
    sent_digest = False
    try:
        if summary:
            notifier.send_text(f"📊 AI 摘要\n\n{summary}")
        notifier.send_digest(posts, kol["name"], kol["platform"])
        sent_digest = True
        for post in posts:
            db.add_push_log(
                db.get_post_id(post.platform, post.external_id),
                channel,
                "success",
                user_id=user["id"],
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("摘要推送失败 user=%s channel=%s err=%s", user["username"], channel, exc)
        maybe_alert_push_failure(
            db,
            notifiers or [],
            f"user={user['username']} channel={channel} digest err={exc}",
        )
        if sent_digest:
            return
        if retry_queue is not None:
            for post in posts:
                retry_queue.add(post, channel, user["id"])
        for post in posts:
            db.add_push_log(
                db.get_post_id(post.platform, post.external_id),
                channel,
                "failed",
                str(exc),
                user_id=user["id"],
            )


def notify_digest_subscribers(
    db: DB,
    posts: list[Post],
    kol: dict,
    notifiers_config,
    notifiers=None,
    retry_queue: PushRetryQueue | None = None,
    dnd_buffer: dict[int, list[Post]] | None = None,
    llm_config=None,
    summary_cache: dict | None = None,
) -> None:
    """把合并摘要推送给订阅了该大V的用户（各自绑定的渠道）。

    用户自配 LLM 优先，否则用站点 Grok（管理员推送设置 / 环境变量）。
    生成失败自动降级，不影响摘要推送。summary_cache 透传给 summarize_posts，
    同一批帖文、同一模型的多个订阅用户只调一次大模型。
    """
    if notifiers_config is None or not posts:
        return
    import httpx

    from .channels import build_channel_notifier, iter_user_channels

    client = httpx.Client(timeout=15)
    site_llm = _system_llm_config(db, llm_config)
    try:
        subscribers = db.subscribers_of_kol(kol["id"])
        keywords_by_user = db.get_users_keywords([u["id"] for u in subscribers])
        for user in subscribers:
            sub_type = user.get("subscribe_type") or "post"
            matched = [p for p in posts if _sub_type_matches(sub_type, p.post_type)]
            if not matched:
                continue
            favorite = bool(user.get("favorite"))
            if bool(user.get("secondary")) and not favorite:
                # 个人次要用户不参与 KOL 摘要：帖子已进用户级延迟缓冲，避免重复推送
                continue
            keywords = keywords_by_user.get(user["id"], [])
            if (
                dnd_buffer is not None
                and _in_dnd_window(user)
                and not (favorite and _dnd_favorite_passthrough(user))
            ):
                delayed, instant = [], []
                for post in matched:
                    if _keyword_hit(keywords, post):
                        instant.append(post)
                    else:
                        delayed.append(post)
                if delayed:
                    dnd_buffer.setdefault(user["id"], []).extend(delayed)
                if not instant:
                    continue
                matched = instant
            matched = [
                with_twitter_display(p, twitter_translate_enabled(user)) for p in matched
            ]
            summary = None
            llm_cfg = _user_llm_config(user, site_llm, db=db)
            if llm_cfg is not None:
                try:
                    from .llm import summarize_posts

                    summary = summarize_posts(matched, llm_cfg, cache=summary_cache)
                except Exception as exc:  # noqa: BLE001 - 摘要失败降级，不影响推送
                    logger.warning(
                        "LLM 摘要异常 user=%s kol=%s err=%s", user["username"], kol["name"], exc
                    )
            for channel in iter_user_channels(user, notifiers_config, db):
                notifier = build_channel_notifier(
                    channel,
                    user,
                    notifiers_config,
                    client=client,
                    favorite=favorite,
                    db=db,
                )
                _send_digest_bundle(
                    notifier, summary, matched, kol, db, channel, user, retry_queue, notifiers
                )
    finally:
        client.close()


def flush_digest(
    db: DB,
    digest: dict[int, list[Post]],
    notifiers: list[Notifier],
    notifiers_config,
    retry_queue: PushRetryQueue | None = None,
    dnd_buffer: dict[int, list[Post]] | None = None,
    llm_config=None,
) -> None:
    """到点把缓冲的摘要统一推送给订阅者（不再做全局推送）。"""
    if not digest:
        return
    summary_cache: dict = {}
    for kol_id, posts in list(digest.items()):
        try:
            kol = db.get_kol(kol_id)
            if kol is None or not posts:
                digest.pop(kol_id, None)
                continue
            notify_digest_subscribers(
                db, posts, kol, notifiers_config, notifiers, retry_queue, dnd_buffer, llm_config, summary_cache
            )
            digest.pop(kol_id, None)
        except Exception:  # noqa: BLE001
            logger.exception("摘要推送失败 kol=%s", kol_id)


def _scheduler_loop_delay(
    interval_seconds: int,
    priority_interval_seconds: int,
    jitter_seconds: int,
    db=None,
) -> float:
    """主循环单轮等待时间：取全局/优先/雪球组合间隔中较小者，保证更短间隔被调度。

    此前主循环固定按全局间隔 sleep，导致 poll_once 里对优先大V的更短到期判断
    永远等不到下一次调用，优先间隔形同虚设。由 poll_once 的内部到期判断决定
    每个 KOL 本轮是否抓取，这里只负责把轮询节奏提到最短间隔。
    """
    combination_base = _polling_setting(
        db, "config_combination_base_seconds", COMBINATION_BASE_SECONDS, positive=True
    )
    base = min(interval_seconds, priority_interval_seconds, combination_base)
    base = max(base, 1)  # 防御：非法配置（0/负值）不能退化成忙轮询
    return base + random.uniform(0, jitter_seconds)


def probe_xueqiu(db: DB, notifiers: list[Notifier], source_config) -> None:
    """主动探测雪球抓取接口可用性（与抓取同路径，不用首页）。"""
    import httpx

    from .fetchers.xueqiu import (
        XUEQIU_COOKIE_KEY,
        XUEQIU_TIMELINE_URL,
        _is_waf_html,
        normalize_xueqiu_id,
    )

    cookie = db.get_setting(XUEQIU_COOKIE_KEY) or source_config.cookie
    target = next((k for k in db.list_kols(platform="xueqiu") if k["enabled"]), None)
    if target is None:
        return  # 没有启用的雪球大V，无从探测
    # UID 可能被录成主页链接，直接拼进请求会 400 造成误报
    xueqiu_uid = normalize_xueqiu_id(target["external_id"])
    from .proxy import ProxyUnavailable, acquire_client_proxy

    try:
        proxy, _pid = acquire_client_proxy(db, "xueqiu")
    except ProxyUnavailable:
        return
    client = httpx.Client(
        timeout=15,
        follow_redirects=True,
        proxy=proxy,
        headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://xueqiu.com/u/{xueqiu_uid}",
            **({"Cookie": cookie} if cookie else {}),
        },
    )
    try:
        resp = client.get(
            XUEQIU_TIMELINE_URL,
            params={"user_id": xueqiu_uid, "page": 1, "count": 1},
        )
        blocked = (
            _is_waf_html(resp)
            or resp.status_code in (401, 403)
            or resp.headers.get("content-type", "").startswith("text/html")
        )
        if resp.status_code == 200 and not blocked:
            try:
                resp.json()
            except ValueError:
                blocked = True
        if blocked:
            db.set_setting(SOURCE_ERR_KEY.format(platform="xueqiu"), "接口异常（探测）")
            now = int(time.time())
            last = db.get_setting(XUEQIU_PROBE_ALERT_KEY)
            if not last or now - int(last) >= SOURCE_ALERT_INTERVAL:
                db.set_setting(XUEQIU_PROBE_ALERT_KEY, str(now))
                _send_admin_text(
                    notifiers,
                    "⚠️ 雪球探测异常：抓取接口返回异常，"
                    "cookie 可能失效。请到后台「数据源 → Cookie 管理」粘贴新的雪球 Cookie。",
                    "雪球探测告警",
                )
            return
        db.set_setting(SOURCE_OK_KEY.format(platform="xueqiu"), str(int(time.time())))
        db.set_setting(SOURCE_ERR_KEY.format(platform="xueqiu"), "")
    except Exception as exc:  # noqa: BLE001
        db.set_setting(SOURCE_ERR_KEY.format(platform="xueqiu"), str(exc)[:300])
        logger.warning("雪球探测失败: %s", exc)
    finally:
        client.close()


def _alert_cookie_keepalive(db: DB, notifiers: list[Notifier], label: str, detail: str = "") -> None:
    now = int(time.time())
    last = db.get_setting(COOKIE_KEEPALIVE_ALERT_KEY)
    if last and now - int(last) < SOURCE_ALERT_INTERVAL:
        return
    db.set_setting(COOKIE_KEEPALIVE_ALERT_KEY, str(now))
    message = (
        f"⚠️ {label} cookie 保活失败：会话可能已过期或登录态被清除。"
        f"请到后台「数据源 → Cookie 管理」更新 {label} Cookie。"
        f"{'微博可扫码续期。' if label == '微博' else ''}"
        + (f" 详情：{detail[:120]}" if detail else "")
    )
    _send_admin_text(notifiers, message, "cookie 保活告警")


def keepalive_xueqiu_cookie(
    db: DB, notifiers: list[Notifier], source_config, client=None
) -> None:
    """定时探测雪球 cookie 是否仍有效，失效时告警（与抓取同路径）。

    请求 timeline JSON：有效 cookie 返回 200，失效返回 400。无法自动续期，需手动更新。
    """
    from .fetchers.xueqiu import (
        XUEQIU_COOKIE_KEY,
        XUEQIU_COOKIE_TIME_KEY,
        XUEQIU_TIMELINE_URL,
        merge_cookie_strings,
        normalize_xueqiu_id,
    )

    cookie = db.get_setting(XUEQIU_COOKIE_KEY) or source_config.cookie
    if not cookie:
        return
    # 没有启用的雪球大V则无从探测（与 probe_xueqiu 一致）
    target = next((k for k in db.list_kols(platform="xueqiu") if k["enabled"]), None)
    if target is None:
        return
    # UID 可能被录成主页链接，直接拼进请求会 400 造成误判 cookie 失效
    xueqiu_uid = normalize_xueqiu_id(target["external_id"])
    import httpx

    owns_client = client is None
    if owns_client:
        from .proxy import ProxyUnavailable, acquire_client_proxy

        try:
            proxy, _pid = acquire_client_proxy(db, "xueqiu")
        except ProxyUnavailable as exc:
            _alert_cookie_keepalive(db, notifiers, "雪球", str(exc))
            return
        client = httpx.Client(
            timeout=20,
            follow_redirects=True,
            proxy=proxy,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://xueqiu.com/u/{xueqiu_uid}",
                "Cookie": cookie,
            },
        )
    try:
        resp = client.get(
            XUEQIU_TIMELINE_URL,
            params={"user_id": xueqiu_uid, "page": 1, "count": 1},
        )
        status = resp.status_code
        if status == 200:
            try:
                resp.json()
            except ValueError:
                status = 0  # 内容不是合法 JSON，按失效处理
        if status != 200:
            db.set_setting(SOURCE_ERR_KEY.format(platform="xueqiu"), "cookie 无效或已过期（保活探测）")
            _alert_cookie_keepalive(db, notifiers, "雪球", f"timeline HTTP {status}")
            return
        # 会话有效：合并本次响应下发的 cookie（一般无新 token，原样保留），更新状态
        new_cookie = merge_cookie_strings(cookie, client.cookies, "xueqiu.com")
        if new_cookie:
            db.set_setting(XUEQIU_COOKIE_KEY, new_cookie)
            db.set_setting(XUEQIU_COOKIE_TIME_KEY, str(int(time.time())))
        db.set_setting(SOURCE_OK_KEY.format(platform="xueqiu"), str(int(time.time())))
        db.set_setting(SOURCE_ERR_KEY.format(platform="xueqiu"), "")
    finally:
        if owns_client:
            client.close()


def keepalive_weibo_cookie(db: DB, notifiers: list[Notifier], weibo_config, client=None) -> None:
    """定时访问微博首页刷新会话；失效时尝试账号密码自动登录，失败则告警。"""
    from .fetchers.weibo import WEIBO_COOKIE_KEY, WeiboFetcher

    cookie = db.get_setting(WEIBO_COOKIE_KEY) or weibo_config.cookie
    if not cookie:
        return
    import httpx

    owns_client = client is None
    if owns_client:
        from .proxy import ProxyUnavailable, acquire_client_proxy

        try:
            proxy, _pid = acquire_client_proxy(db, "weibo")
        except ProxyUnavailable as exc:
            _alert_cookie_keepalive(db, notifiers, "微博", str(exc))
            return
        client = httpx.Client(
            timeout=20,
            follow_redirects=True,
            proxy=proxy,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Referer": "https://weibo.com/",
                "Cookie": cookie,
            },
        )
    try:
        resp = client.get("https://weibo.com/")
        # 会话有效：最终停留在 weibo.com（未登录会被 302 到 passport 登录页）
        if resp.status_code == 200 and "passport.weibo.com" not in str(resp.url):
            from .fetchers.xueqiu import merge_cookie_strings

            new_cookie = merge_cookie_strings(cookie, client.cookies, "weibo.com")
            if new_cookie:
                db.set_setting(WEIBO_COOKIE_KEY, new_cookie)
                db.set_setting(WEIBO_COOKIE_TIME_KEY, str(int(time.time())))
                db.set_setting(SOURCE_ERR_KEY.format(platform="weibo"), "")
            return
        # 会话已失效：有账号密码则自动登录续期，否则告警
        db.set_setting(SOURCE_ERR_KEY.format(platform="weibo"), "保活：会话已失效")
        if weibo_config.username and weibo_config.password:
            try:
                fetcher = WeiboFetcher(weibo_config, db, client=client)
                fetcher._login()
                db.set_setting(WEIBO_COOKIE_TIME_KEY, str(int(time.time())))
                db.set_setting(SOURCE_ERR_KEY.format(platform="weibo"), "")
                logger.info("微博 cookie 保活：已通过账号密码自动续期")
            except Exception as exc:  # noqa: BLE001
                _alert_cookie_keepalive(db, notifiers, "微博", str(exc))
                db.set_setting(SOURCE_ERR_KEY.format(platform="weibo"), f"保活登录失败: {exc}"[:300])
        else:
            # 没有账号密码：直接把二维码发到管理员 TG，扫码后自动保存
            if not _start_weibo_qr_renewal(db, notifiers):
                _alert_cookie_keepalive(db, notifiers, "微博")
    finally:
        if owns_client:
            client.close()


def _start_weibo_qr_renewal(db: DB, notifiers: list[Notifier]) -> bool:
    """把微博扫码二维码发到管理员 TG，后台线程轮询并自动保存 cookie。"""
    import threading

    from .fetchers.weibo import WEIBO_COOKIE_KEY
    from .weibo_qr import create_qr, poll_qr

    now = int(time.time())
    last = db.get_setting(WEIBO_QR_RENEWAL_KEY)
    if last and now - int(last) < WEIBO_QR_RENEWAL_COOLDOWN:
        return False  # 冷却期内不重复发码
    tg = next((n for n in notifiers if n.channel == "telegram"), None)
    if tg is None or not getattr(tg, "chat_id", None):
        return False
    try:
        client, qrid, image_url = create_qr(db=db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("微博续期二维码生成失败: %s", exc)
        return False
    try:
        image = client.get(image_url).content
    except Exception as exc:  # noqa: BLE001
        logger.warning("微博续期二维码下载失败: %s", exc)
        client.close()
        return False
    db.set_setting(WEIBO_QR_RENEWAL_KEY, str(now))
    try:
        tg.send_photo(image, "⚠️ 微博会话已过期，请用微博 App 扫码登录（10 分钟内有效）")
    except Exception as exc:  # noqa: BLE001
        logger.warning("微博二维码发送失败: %s", exc)
        client.close()
        return False

    def _poll():
        try:
            for _ in range(200):  # 每 3 秒，最长 10 分钟
                time.sleep(3)
                result = poll_qr(client, qrid)
                if result["status"] in ("pending", "scanned"):
                    continue
                if result["status"] == "ok" and result.get("cookie"):
                    db.set_setting(WEIBO_COOKIE_KEY, result["cookie"])
                    db.set_setting(WEIBO_COOKIE_TIME_KEY, str(int(time.time())))
                    tg.send_text("✅ 微博 cookie 已更新，抓取恢复")
                else:
                    tg.send_text(
                        f"微博扫码未完成：{result.get('detail') or result['status']}，"
                        "可到后台「数据源 → Cookie 管理」重新扫码"
                    )
                break
            else:
                tg.send_text("微博二维码已过期，可到后台「数据源 → Cookie 管理」重新扫码")
        except Exception as exc:  # noqa: BLE001
            logger.warning("微博续期轮询异常: %s", exc)
        finally:
            client.close()

    threading.Thread(target=_poll, daemon=True).start()
    return True


class Scheduler:
    def __init__(
        self,
        db,
        fetchers,
        notifiers,
        polling_config,
        notifiers_config=None,
        xueqiu_config=None,
        weibo_config=None,
        llm_config=None,
        mx_config=None,
    ):
        self.db = db
        self.fetchers = fetchers
        self.notifiers = notifiers
        self.polling_config = polling_config
        self.notifiers_config = notifiers_config
        self.xueqiu_config = xueqiu_config
        self.weibo_config = weibo_config
        self.llm_config = llm_config
        self.mx_config = mx_config
        self.states: dict[str, PlatformState] = {}
        self._digest: dict[int, list[Post]] = {}
        self._dnd_buffer: dict[int, list[Post]] = {}
        self._secondary_buffer: dict[int, list[Post]] = {}
        self._secondary_first_at: dict[int, float] = {}
        self.retry_queue = PushRetryQueue()
        self._stop = asyncio.Event()
        self._last_cleanup = 0.0
        self._last_digest_flush = time.monotonic()
        self._last_xueqiu_probe = time.monotonic()
        self._last_cookie_keepalive = time.monotonic()
        self._last_retry = 0.0
        self._last_health_check = time.monotonic()
        self._last_proxy_tick = 0.0
        self._mx_sync_service = None
        self._mx_ws_task = None

    def stop(self):
        self._stop.set()

        # 停止 MX 相关任务
        if self._mx_ws_task:
            self._mx_ws_task.cancel()
            self._mx_ws_task = None
        if self._mx_sync_service:
            self._mx_sync_service.stop()
            self._mx_sync_service = None
        global _mx_fetcher
        _mx_fetcher = None
        
        # 尽力把缓冲中未推送的合并摘要发出去，避免重启/关闭丢消息
        try:
            flush_digest(
                self.db, self._digest, self.notifiers, self.notifiers_config,
                retry_queue=self.retry_queue,
                dnd_buffer=self._dnd_buffer,
            )
        except Exception:  # noqa: BLE001
            logger.exception("关闭时摘要推送失败")
        # 免打扰缓冲也尽量补推（关闭时立即发汇总，避免丢失）
        try:
            self._flush_dnd_buffers(force=True)
        except Exception:  # noqa: BLE001
            logger.exception("关闭时免打扰汇总推送失败")
        # 个人次要缓冲同样补推，避免重启丢消息
        try:
            self._flush_secondary_buffers()
        except Exception:  # noqa: BLE001
            logger.exception("关闭时个人次要缓冲推送失败")
    
    async def _send_startup_message(self):
        """启动提示只推送给管理员（走管理员各自绑定的渠道），普通用户不推送。"""
        if self.notifiers_config is None:
            return
        import httpx

        from .channels import build_channel_notifier, iter_user_channels

        message = "✅ V Push服务已启动"
        client = httpx.Client(timeout=15)
        sent_any = False
        try:
            for user in self.db.list_users():
                if not user.get("is_admin"):
                    continue
                for channel in iter_user_channels(user, self.notifiers_config, self.db):
                    try:
                        notifier = build_channel_notifier(
                            channel, user, self.notifiers_config, client=client, db=self.db
                        )
                        await asyncio.to_thread(notifier.send_text, message)
                        sent_any = True
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "启动提示发送失败 user=%s channel=%s err=%s",
                            user["username"],
                            channel,
                            exc,
                        )
        finally:
            client.close()
        if not sent_any:
            logger.info("没有可接收启动提示的管理员绑定渠道")

    async def _init_mx(self):
        """初始化 MX 平台功能：房间同步、WebSocket 连接等。"""
        try:
            logger.info("Initializing MX platform...")

            # 创建并启动房间同步服务（初始同步在后台执行，避免阻塞 WS 上线）
            self._mx_sync_service = MXRoomSyncService(self.mx_config, self.db)

            # 启动定时同步（含后台初始同步）
            await self._mx_sync_service.start_periodic_sync()

            # 启动 WebSocket（如果启用）
            if self.mx_config.ws_enabled and "mx" in self.fetchers:
                mx_fetcher = self.fetchers["mx"]
                global _mx_fetcher
                _mx_fetcher = mx_fetcher  # 供 get_mx_ws_status 读取连接状态

                async def on_mx_message(post: Post):
                    """处理 MX 实时消息，直接推送。"""
                    try:
                        # 把数据库操作放在单独线程中，避免事务冲突
                        def _save_and_notify():
                            post_id = self.db.save_post(post)
                            if not post_id:
                                return
                            # 大V 屏蔽词命中的消息：入库留档但不推送
                            if self.db.is_post_blocked(post_id):
                                logger.info(
                                    "关键词拦截不推送 platform=%s kol=%s id=%s",
                                    post.platform, post.kol_name, post.external_id,
                                )
                                return
                            notify_subscribers(
                                self.db,
                                post_id,
                                post,
                                self.notifiers_config,
                                self.notifiers,
                                self.retry_queue,
                                dnd_buffer=self._dnd_buffer,
                                secondary_buffer=self._secondary_buffer,
                            )
                        await asyncio.to_thread(_save_and_notify)
                    except Exception as e:
                        logger.error(f"Failed to process MX real-time message: {e}", exc_info=True)

                self._mx_ws_task = asyncio.create_task(mx_fetcher.start_ws(on_mx_message))

            logger.info("MX platform initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MX platform: {e}", exc_info=True)

    async def _stop_mx(self):
        """停止 MX 房间同步与 WebSocket，并移除 mx 抓取器（禁用/重配时调用）。"""
        global _mx_fetcher
        if self._mx_ws_task:
            self._mx_ws_task.cancel()
            self._mx_ws_task = None
        _mx_fetcher = None
        if self._mx_sync_service:
            self._mx_sync_service.stop()
            self._mx_sync_service = None
        mx_fetcher = self.fetchers.pop("mx", None)
        if mx_fetcher is not None:
            try:
                await mx_fetcher.stop_ws()
            except Exception:  # noqa: BLE001 - 任务已被 cancel，尽力断开即可
                logger.warning("停止 MX WebSocket 失败", exc_info=True)

    async def apply_mx_config(self, mx_config) -> None:
        """MX 配置变更后热应用：停掉旧任务，按需重建抓取器并重启同步/WS。"""
        await self._stop_mx()
        self.mx_config = mx_config
        if not (MX_AVAILABLE and mx_config and mx_config.enabled):
            logger.info("MX platform disabled, hot-reload skipped")
            return
        from .fetchers.mx.fetcher import MxFetcher

        self.fetchers["mx"] = MxFetcher(mx_config, self.db)
        await self._init_mx()

    async def run(self):
        if self.polling_config.notify_on_start:
            await self._send_startup_message()
        self._recover_failed_pushes()
        
        # 初始化 MX 功能（若配置热加载已提前初始化过则跳过，避免重复启动同步/WS）
        if (
            MX_AVAILABLE
            and self.mx_config
            and self.mx_config.enabled
            and self._mx_sync_service is None
        ):
            await self._init_mx()
        
        while not self._stop.is_set():
            started = time.monotonic()
            interval_seconds = _polling_setting(
                self.db, "config_interval_seconds", self.polling_config.interval_seconds
            )
            priority_interval = _polling_setting(
                self.db,
                "config_priority_interval_seconds",
                self.polling_config.priority_interval_seconds,
            )
            digest_interval = _polling_setting(
                self.db, "config_digest_interval_seconds", self.polling_config.digest_interval_seconds
            )
            secondary_digest_interval = _polling_setting(
                self.db,
                "config_secondary_digest_interval_seconds",
                self.polling_config.secondary_digest_interval_seconds,
            )
            secondary_min_count = _polling_setting(
                self.db,
                "config_secondary_min_digest_count",
                SECONDARY_MIN_DIGEST_COUNT,
            )
            try:
                await asyncio.to_thread(
                    poll_once,
                    self.db,
                    self.fetchers,
                    self.notifiers,
                    self.states,
                    self.notifiers_config,
                    interval_seconds,
                    priority_interval,
                    self._digest if digest_interval > 0 else None,
                    self.retry_queue,
                    self._dnd_buffer,
                    secondary_buffer=self._secondary_buffer if secondary_digest_interval > 0 else None,
                    llm_config=self.llm_config,
                )
                self.db.set_setting("stats_last_poll_at", str(int(time.time())))
                self.db.set_setting(
                    "stats_last_poll_duration_ms",
                    str(int((time.monotonic() - started) * 1000)),
                )
                self.db.set_setting("stats_last_poll_error", "")
            except Exception:  # noqa: BLE001 - 任何异常都不能终止循环
                logger.exception("轮询周期异常")
                self.db.set_setting("stats_last_poll_error", "轮询周期异常")
            now_mono = time.monotonic()
            # 推送失败重试（每 60 秒检查一次）
            if now_mono - self._last_retry >= 60:
                self._last_retry = now_mono
                try:
                    await asyncio.to_thread(self._retry_due_pushes)
                except Exception:  # noqa: BLE001
                    logger.exception("重试推送异常")
            # 合并摘要到点统一推送（普通大V，优先大V保持实时）
            if (
                digest_interval > 0
                and self._digest
                and now_mono - self._last_digest_flush >= digest_interval
            ):
                self._last_digest_flush = now_mono
                try:
                    await asyncio.to_thread(
                        flush_digest,
                        self.db,
                        self._digest,
                        self.notifiers,
                        self.notifiers_config,
                        self.retry_queue,
                        self._dnd_buffer,
                        self.llm_config,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("摘要推送失败")
            # 次要大V：每轮按用户首帖入缓冲计时，到期才发；个人次要共用此缓冲
            if secondary_digest_interval > 0 and self._secondary_buffer:
                try:
                    await asyncio.to_thread(
                        self._flush_secondary_buffers,
                        secondary_min_count,
                        secondary_digest_interval,
                        now_mono,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("次要大V合并摘要推送失败")
            # 免打扰时段结束：补推汇总
            try:
                await asyncio.to_thread(self._flush_dnd_buffers)
            except Exception:  # noqa: BLE001
                logger.exception("免打扰汇总推送失败")
            # 雪球 cookie 主动探测
            probe_interval = _polling_setting(
                self.db,
                "config_source_probe_interval_seconds",
                self.polling_config.source_probe_interval_seconds,
            )
            if probe_interval > 0 and now_mono - self._last_xueqiu_probe >= probe_interval:
                self._last_xueqiu_probe = now_mono
                try:
                    await asyncio.to_thread(
                        probe_xueqiu,
                        self.db,
                        self.notifiers,
                        self.xueqiu_config,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("雪球探测异常")
            # 雪球/微博 cookie 保活（刷新会话防过期）
            keepalive_interval = _polling_setting(
                self.db,
                "config_cookie_keepalive_interval_seconds",
                self.polling_config.cookie_keepalive_interval_seconds,
            )
            if keepalive_interval > 0 and now_mono - self._last_cookie_keepalive >= keepalive_interval:
                self._last_cookie_keepalive = now_mono
                try:
                    await asyncio.to_thread(
                        keepalive_xueqiu_cookie,
                        self.db,
                        self.notifiers,
                        self.xueqiu_config,
                    )
                    await asyncio.to_thread(
                        keepalive_weibo_cookie,
                        self.db,
                        self.notifiers,
                        self.weibo_config,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("cookie 保活异常")
            # 每日精选：每天到达设定小时且当天未发过时推送；发送成功才标记已发，
            # 失败保留未发状态下一轮重试，避免发送失败当天漏发
            if self._daily_report_due():
                try:
                    report_ok = await asyncio.to_thread(self._send_daily_report)
                except Exception:  # noqa: BLE001
                    logger.exception("每日精选推送异常")
                    report_ok = False
                if report_ok:
                    self.db.set_setting("daily_report_last_date", time.strftime("%Y-%m-%d"))
            # 定时 WebDAV 备份：到点后当天未成功则跑，失败可在后续循环重试
            try:
                backup_ok = await asyncio.to_thread(run_scheduled, self.db)
            except Exception:  # noqa: BLE001
                logger.exception("定时备份异常")
                backup_ok = False
            if backup_ok is False:
                try:
                    maybe_alert_backup_failure(
                        self.db,
                        self.notifiers,
                        self.db.get_setting("backup_last_error") or "定时备份失败",
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("备份失败告警异常")

            # --- AI分析任务检查 ---
            try:
                from datetime import timezone
                now = datetime.now(timezone.utc)
                now_str = now.isoformat()
                due_tasks = self.db.get_due_ai_tasks(now_str)
                for task in due_tasks:
                    task_id = task["id"]
                    # 检查是否已在运行
                    if task_id in _ai_task_running:
                        continue
                    # 初始化信号量（懒加载）
                    global _ai_task_semaphore
                    if _ai_task_semaphore is None:
                        _ai_task_semaphore = asyncio.Semaphore(_ai_task_max_concurrent)

                    # 异步运行任务
                    async def run_task_wrapper(tid):
                        if tid in _ai_task_running:
                            return
                        _ai_task_running.add(tid)
                        try:
                            async with _ai_task_semaphore:
                                await asyncio.to_thread(ai_analysis.run_analysis_task, tid, self.db)
                        finally:
                            _ai_task_running.discard(tid)

                    # 在事件循环中运行
                    asyncio.create_task(run_task_wrapper(task_id))
            except Exception:  # noqa: BLE001
                logger.exception("AI分析任务检查异常")

            # --- 清理旧日志（每小时一次） ---
            try:
                if not hasattr(self.db, "_last_ai_log_cleanup") or \
                   (time.time() - getattr(self.db, "_last_ai_log_cleanup", 0)) > 3600:
                    clean_days = int(self.db.get_setting("ai_log_retention_days") or "30")
                    removed = self.db.delete_old_ai_logs(clean_days)
                    if removed > 0:
                        logger.info("清理了 %d 条旧AI分析日志", removed)
                    self.db._last_ai_log_cleanup = time.time()
            except Exception:  # noqa: BLE001
                pass
            # 平台级健康阈值检查（每 10 分钟一次，轻量 SQL）：成功率过低/整体静默告警
            if now_mono - self._last_health_check >= SOURCE_HEALTH_CHECK_INTERVAL:
                self._last_health_check = now_mono
                try:
                    await asyncio.to_thread(
                        maybe_alert_source_health, self.db, self.notifiers
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("数据源健康告警异常")
            if now_mono - self._last_proxy_tick >= PROXY_TICK_INTERVAL:
                self._last_proxy_tick = now_mono
                try:
                    await asyncio.to_thread(tick_proxy_pools, self.db)
                except Exception:  # noqa: BLE001
                    logger.exception("代理池刷新异常")
            # 股票黑话别名识别 + 误标清理：每天一次（配 LLM 才识别，清理恒执行）
            if self._stock_alias_due():
                ran = False
                try:
                    ran = await asyncio.to_thread(self._run_stock_alias_task)
                except Exception:  # noqa: BLE001
                    logger.exception("股票别名识别异常")
                    ran = True  # 失败也记已跑，避免当天反复打 LLM
                if ran:
                    self.db.set_setting("stock_alias_last_date", time.strftime("%Y-%m-%d"))
            try:
                removed_users = await asyncio.to_thread(self.db.purge_inactive_users_if_due)
                if removed_users:
                    logger.info("清理未激活用户 %d 人", removed_users)
            except Exception:  # noqa: BLE001
                logger.exception("未激活用户清理失败")
            # 定期清理过期帖子（默认每 6 小时检查一次）
            if now_mono - self._last_cleanup > 6 * 3600:
                self._last_cleanup = now_mono
                retention = self.polling_config.posts_retention_days
                if retention > 0:
                    try:
                        removed = await asyncio.to_thread(
                            self.db.delete_posts_older_than, retention
                        )
                        if removed:
                            logger.info("清理过期帖子 %d 条（保留 %d 天）", removed, retention)
                    except Exception:  # noqa: BLE001
                        logger.exception("帖子清理失败")
                log_retention = self.polling_config.push_logs_retention_days
                if log_retention > 0:
                    try:
                        removed_logs = await asyncio.to_thread(
                            self.db.delete_push_logs_older_than, log_retention
                        )
                        if removed_logs:
                            logger.info("清理推送日志 %d 条（保留 %d 天）", removed_logs, log_retention)
                    except Exception:  # noqa: BLE001
                        logger.exception("推送日志清理失败")
                # 数据源稳定性事件保留 7 天足够看趋势，过长无意义
                try:
                    removed_events = self.db.delete_source_events_older_than(7)
                    if removed_events:
                        logger.info("清理数据源事件 %d 条（保留 7 天）", removed_events)
                except Exception:  # noqa: BLE001
                    logger.exception("数据源事件清理失败")
                # 管理员操作日志保留 180 天，避免无限增长
                try:
                    removed_admin = self.db.delete_admin_logs_older_than(180)
                    if removed_admin:
                        logger.info("清理操作日志 %d 条（保留 180 天）", removed_admin)
                except Exception:  # noqa: BLE001
                    logger.exception("操作日志清理失败")
            elapsed = time.monotonic() - started
            delay = _scheduler_loop_delay(
                interval_seconds,
                priority_interval,
                self.polling_config.jitter_seconds,
                db=self.db,
            )
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=max(0.0, delay - elapsed)
                )
            except TimeoutError:
                pass

    def _recover_failed_pushes(self) -> None:
        """重启后把最近 24 小时失败的推送重新入队。"""
        if self.notifiers_config is None:
            return
        from .fetchers.base import Post

        rows = self.db.list_failed_push_logs(since_hours=24, limit=2000)
        recovered = 0
        for row in rows:
            post_row = self.db.get_post(row["post_id"])
            if post_row is None:
                continue
            user_id = row["user_id"]
            kol = self.db.get_kol(post_row["kol_id"])
            try:
                detail = json.loads(post_row["detail"]) if post_row.get("detail") else None
            except (TypeError, ValueError):
                detail = None
            try:
                images = json.loads(post_row["images"]) if post_row.get("images") else []
            except (TypeError, ValueError):
                images = []
            if not isinstance(images, list):
                images = []
            post = Post(
                platform=post_row["platform"],
                kol_id=post_row["kol_id"],
                kol_name=post_row["kol_name"] or "",
                external_id=post_row["external_id"],
                title=post_row["title"],
                content=post_row["content"],
                url=post_row["url"],
                published_at=post_row["published_at"],
                category=(kol or {}).get("category_name") or "",
                post_type=post_row.get("post_type") or "",
                detail=detail,
                images=images,
                title_src=post_row.get("title_src") or "",
                content_src=post_row.get("content_src") or "",
            )
            # 重试前复查：退订/关闭通知/改选渠道的用户不再恢复推送
            if user_id is not None:
                user = self.db.get_user(user_id)
                if user is None or not _can_still_push(user, row["channel"], post, self.db):
                    continue
            self.retry_queue.add(post, row["channel"], user_id)
            recovered += 1
        if recovered:
            logger.info("重启恢复待重试推送 %d 条", recovered)

    def _retry_due_pushes(self) -> None:
        """到点的失败推送补发；含同步网络与 DB 写，只能在 to_thread 里跑。"""
        for item in self.retry_queue.due():
            try:
                self._retry_push(item)
            except Exception as exc:  # noqa: BLE001
                logger.warning("重试推送失败 channel=%s err=%s", item["channel"], exc)
                self.retry_queue.fail(item)
        # 把待重试数量落库，供后台「数据源」页展示
        self.db.set_setting("stats_retry_pending", str(self.retry_queue.pending()))

    def _retry_push(self, item: dict) -> None:
        post = item["post"]
        user = self.db.get_user(item["user_id"]) if item["user_id"] is not None else None
        # 退订/关闭通知/改选渠道后不再重试旧帖
        if item["user_id"] is not None and (
            user is None or not _can_still_push(user, item["channel"], post, self.db)
        ):
            self.retry_queue.drop(item)
            return
        delivery_post = with_twitter_display(post, twitter_translate_enabled(user))
        if item["user_id"] is not None:
            subscription = self.db.get_subscription(item["user_id"], post.kol_id)
            if subscription and subscription["hide_images"]:
                delivery_post = replace(delivery_post, images=[])
        favorite = bool(
            item["user_id"] is not None
            and post.kol_id in self.db.subscribed_favorite_ids(item["user_id"])
        )
        keywords = self.db.get_user_keywords(user["id"]) if user is not None else []
        if (
            user is not None
            and _in_dnd_window(user)
            and not (favorite and _dnd_favorite_passthrough(user))
            and not _keyword_hit(keywords, post)
        ):
            # 免打扰时段内的重试也进免打扰缓冲，避免深夜打扰
            self._dnd_buffer.setdefault(user["id"], []).append(post)
            self.retry_queue.drop(item)
            return
        notifier = self._build_retry_notifier(
            item["channel"], item["user_id"], favorite=favorite
        )
        try:
            notifier.notify(delivery_post)
        finally:
            # 按用户重建的 notifier 持有独立 client，用完即关；
            # user_id 为 None 时复用全局 notifier，不能关它的连接
            if item["user_id"] is not None and getattr(notifier, "client", None) is not None:
                notifier.client.close()
        post_id = self.db.get_post_id(post.platform, post.external_id)
        if post_id:
            # 翻转前取原失败原因落日志：mark_failed_push_success 会清空 error，不记就追溯不到了
            orig_error = self.db.get_failed_push_error(post_id, item["channel"], item["user_id"])
            if orig_error:
                logger.info(
                    "推送重试成功 channel=%s user=%s post=%s（原失败原因: %s）",
                    item["channel"], item["user_id"], post_id, orig_error,
                )
            self.db.mark_failed_push_success(post_id, item["channel"], item["user_id"])
        self.retry_queue.drop(item)

    def _flush_dnd_buffers(self, force: bool = False) -> None:
        """免打扰时段结束后，给每个用户补推一条汇总。"""
        if not self._dnd_buffer:
            return
        now = datetime.now()
        for user_id in list(self._dnd_buffer):
            posts = self._dnd_buffer.get(user_id) or []
            if not posts:
                continue
            user = self.db.get_user(user_id)
            if user is None:
                self._dnd_buffer.pop(user_id, None)
                continue
            if not force and _in_dnd_window(user, now):
                continue  # 仍在免打扰时段，等时段结束再推
            try:
                self._send_dnd_summary(user, posts)
            except Exception as exc:  # noqa: BLE001
                logger.warning("免打扰汇总推送失败 user=%s err=%s", user["username"], exc)
                continue
            self._dnd_buffer.pop(user_id, None)

    def _pop_secondary_user(self, user_id: int) -> None:
        self._secondary_first_at.pop(user_id, None)
        self._secondary_buffer.pop(user_id, None)

    def _flush_secondary_buffers(
        self, min_count: int = 1, interval: int = 0, now_mono: float | None = None
    ) -> None:
        """次要合并缓冲：按用户首帖计时，跨大V一条摘要。

        interval=0 强制发（关闭/测试，仍尊重 min_count）。
        interval>0 等满周期；条数不够再等一个周期后强制发。
        DND 中整包交给 _dnd_buffer。
        """
        if not self._secondary_buffer:
            return
        now = datetime.now()
        now_mono = time.monotonic() if now_mono is None else now_mono
        max_wait = interval * 2 if interval > 0 else 0
        for user_id in list(self._secondary_buffer):
            posts = self._secondary_buffer.get(user_id) or []
            if not posts:
                continue
            self._secondary_first_at.setdefault(user_id, now_mono)
            user = self.db.get_user(user_id)
            if user is None:
                self._pop_secondary_user(user_id)
                continue
            if _in_dnd_window(user, now):
                self._dnd_buffer.setdefault(user_id, []).extend(posts)
                self._pop_secondary_user(user_id)
                continue
            waited = now_mono - self._secondary_first_at[user_id]
            if interval > 0 and waited < interval:
                continue
            if len(posts) < min_count and (interval <= 0 or waited < max_wait):
                continue
            try:
                self._send_dnd_summary(user, posts, title="🔕 次要大V合并摘要", use_llm=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("次要大V汇总推送失败 user=%s err=%s", user["username"], exc)
                continue
            self._pop_secondary_user(user_id)

    def _send_dnd_summary(
        self, user: dict, posts: list[Post], title: str | None = None, use_llm: bool = True
    ) -> None:
        """把缓冲的动态汇总成一条推送给用户（按所选通道），并补写推送日志。

        默认标题为「免打扰时段汇总」；次要大V合并摘要传 title="🔕 次要大V合并摘要"
        且 use_llm=False（纯汇总，不调 LLM 不耗 token）。use_llm=True 时先尝试
        生成 AI 要点（失败自动降级为普通汇总，不影响推送）。
        """
        if self.notifiers_config is None or not posts:
            return
        posts = [with_twitter_display(p, twitter_translate_enabled(user)) for p in posts]
        import httpx

        from .channels import (
            CHANNELS,
            build_channel_notifier,
            channel_bound,
            channel_enabled,
        )

        summary = None
        if use_llm:
            from .llm import summarize_posts

            llm_cfg = _user_llm_config(
                user,
                _system_llm_config(self.db, getattr(self, "llm_config", None)),
                db=self.db,
            )
            if llm_cfg is not None:
                try:
                    summary = summarize_posts(posts, llm_cfg)
                except Exception as exc:  # noqa: BLE001 - 摘要失败降级，不影响汇总
                    logger.warning("LLM 摘要异常 user=%s err=%s", user["username"], exc)

        client = httpx.Client(timeout=15)
        try:
            for channel in CHANNELS:
                if not channel_enabled(user, channel) or not channel_bound(user, channel, self.notifiers_config, self.db):
                    continue
                sent_any = False
                try:
                    notifier = build_channel_notifier(channel, user, self.notifiers_config, client=client, db=self.db)
                    if summary:
                        notifier.send_text(f"📊 AI 摘要\n\n{summary}")
                        sent_any = True
                    if title is not None:
                        notifier.send_dnd_summary(posts, title=title)
                    else:
                        notifier.send_dnd_summary(posts)
                    sent_any = True
                    for post in posts:
                        post_id = self.db.get_post_id(post.platform, post.external_id)
                        if post_id:
                            self.db.add_push_log(post_id, channel, "success", user_id=user["id"])
                except Exception as exc:  # noqa: BLE001
                    logger.warning("免打扰汇总 %s 发送失败 user=%s err=%s", channel, user["username"], exc)
                    maybe_alert_push_failure(
                        self.db,
                        self.notifiers or [],
                        f"user={user['username']} channel={channel} dnd err={exc}",
                    )
                    if sent_any:
                        continue
                    # 失败渠道的帖子逐条写失败日志并入重试队列，避免免打扰缓冲静默丢失；
                    # 重试按单帖发送（_retry_push），不依赖内存中的摘要文本
                    for post in posts:
                        post_id = self.db.get_post_id(post.platform, post.external_id)
                        if post_id:
                            self.db.add_push_log(
                                post_id, channel, "failed", f"dnd summary: {exc}", user_id=user["id"]
                            )
                        self.retry_queue.add(post, channel, user["id"])
        finally:
            client.close()

    def _build_retry_notifier(
        self,
        channel: str,
        user_id: int | None,
        favorite: bool = False,
    ):
        from .channels import CHANNEL_LABELS, build_channel_notifier, channel_bound

        if user_id is None:
            for notifier in self.notifiers:
                if notifier.channel == channel:
                    return notifier
            raise RuntimeError(f"无全局通知器: {channel}")
        user = self.db.get_user(user_id)
        if user is None:
            raise RuntimeError("用户不存在")
        if not channel_bound(user, channel, self.notifiers_config, self.db):
            raise RuntimeError(f"用户未绑定 {CHANNEL_LABELS.get(channel, channel)}")
        return build_channel_notifier(
            channel,
            user,
            self.notifiers_config,
            favorite=favorite,
            db=self.db,
        )

    def _daily_report_due(self) -> bool:
        hour_cfg = _polling_setting(
            self.db, "config_daily_report_hour", self.polling_config.daily_report_hour
        )
        now = datetime.now()
        if now.hour < hour_cfg:
            return False
        return self.db.get_setting("daily_report_last_date") != now.strftime("%Y-%m-%d")

    def _stock_alias_due(self) -> bool:
        """股票别名识别任务是否到期：每天最多一次（settings 日期键控制）。"""
        return self.db.get_setting("stock_alias_last_date") != datetime.now().strftime("%Y-%m-%d")

    def _run_stock_alias_task(self) -> bool:
        """股票黑话别名自动识别（LLM，每日一次）+ 历史误标清理（纯规则）。

        与管理端「标签维护」共用 run_tag_maintenance。并发占用时返回 False，
        调用方不记今日已跑，下一轮再试。
        """
        from .tagging import try_run_tag_maintenance

        result = try_run_tag_maintenance(
            self.db, _system_llm_config(self.db, getattr(self, "llm_config", None))
        )
        if result is None:
            return False
        last = dict(result)
        last["at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.set_tag_maintain_last(last)
        if result.get("error"):
            logger.warning("标签维护识别异常: %s", result["error"])
        logger.info(
            "标签维护：别名 +%d 股票 +%d 清理 %d llm=%s",
            len(result.get("added_aliases") or []),
            len(result.get("added_stock_names") or []),
            result.get("cleaned") or 0,
            result.get("llm_used"),
        )
        return True

    def _send_daily_report(self) -> bool:
        """给开启每日精选的用户推送今日订阅总览；全部成功返回 True，任一失败返回 False。

        返回 False 时调用方不标记「今日已发」，下一轮会重试，避免发送失败当天漏发。
        """
        if self.notifiers_config is None:
            return True
        # 清理过期的每日精选投递状态（每天一次，防止表无限增长）
        try:
            self.db.delete_daily_report_deliveries_older_than(
                max(1, getattr(self.polling_config, "push_logs_retention_days", 90))
            )
        except Exception:  # noqa: BLE001 - 清理失败不影响推送
            logger.warning("每日精选投递状态清理失败", exc_info=True)
        from .channels import build_channel_notifier, iter_user_channels
        from .fetchers.base import Post

        failed = False
        report_date = datetime.now().strftime("%Y-%m-%d")
        since = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

        def _deliver(channel: str, user) -> None:
            """按渠道幂等投递每日精选：当日该渠道已成功则跳过（部分失败重试不重复发）。

            成功立即标记投递状态（持久化，进程重启也不重复）；异常只标记该渠道失败。
            """
            nonlocal failed
            if self.db.daily_report_delivered(user["id"], report_date, channel):
                logger.info(
                    "每日精选 channel=%s 当日已投递成功，跳过 user=%s",
                    channel, user["username"],
                )
                return
            notifier = build_channel_notifier(
                channel, user, self.notifiers_config, db=self.db
            )
            try:
                if daily_text:
                    notifier.send_text(daily_text)
                else:
                    notifier.send_daily(posts)
                for post in posts:
                    post_id = self.db.get_post_id(post.platform, post.external_id)
                    if post_id:
                        self.db.add_push_log(post_id, channel, "success", user_id=user["id"])
                self.db.mark_daily_report_delivered(user["id"], report_date, channel)
            except Exception as exc:  # noqa: BLE001
                failed = True
                self.db.mark_daily_report_failed(user["id"], report_date, channel)
                logger.warning(
                    "每日精选推送失败 user=%s channel=%s err=%s", user["username"], channel, exc
                )
                maybe_alert_push_failure(
                    self.db,
                    self.notifiers or [],
                    f"user={user['username']} channel={channel} daily err={exc}",
                )
            finally:
                client = getattr(notifier, "client", None)
                if client is not None:
                    client.close()

        for user in self.db.daily_report_users():
            kol_ids = sorted(
                self.db.readable_subscribed_kol_ids(user["id"], bool(user.get("is_admin")))
            )
            rows = self.db.list_daily_posts(kol_ids, since, 15, user_id=user["id"])
            if not rows:
                continue
            posts = [
                with_twitter_display(
                    Post(
                        platform=r["platform"],
                        kol_id=r["kol_id"],
                        kol_name=r["kol_name"] or "",
                        external_id=r["external_id"],
                        title=r["title"],
                        content=r["content"],
                        url=r["url"],
                        published_at=r["published_at"],
                        favorite=bool(r.get("favorite")),
                        title_src=r.get("title_src") or "",
                        content_src=r.get("content_src") or "",
                    ),
                    twitter_translate_enabled(user),
                )
                for r in rows
            ]
            summary = None
            llm_cfg = _user_llm_config(
                user,
                _system_llm_config(self.db, getattr(self, "llm_config", None)),
                db=self.db,
            )
            if llm_cfg is not None:
                try:
                    from .llm import summarize_daily

                    summary = summarize_daily(posts, llm_cfg)
                except Exception as exc:  # noqa: BLE001 - 综述失败降级为原始列表，不影响推送
                    logger.warning("LLM 每日综述异常 user=%s err=%s", user["username"], exc)
            # LLM 精炼综述优先；未配置/失败时降级为原始贴文列表（保底不空发）
            daily_text = None
            if summary is not None:
                from .llm import render_daily_summary

                daily_text = render_daily_summary(summary, posts)

            for channel in iter_user_channels(user, self.notifiers_config, self.db):
                _deliver(channel, user)
        return not failed
