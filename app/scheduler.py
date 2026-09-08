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
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta

from .backup import run_scheduled
from .channels import channel_bound, channel_enabled, is_permanent_push_error
from .db import _UNSET, ALLOWED_PLATFORMS, DB, POST_TAGS_MAX, days_until_purge, user_plain_secret
from . import ai_analysis
from . import mx_view_analysis

# AI分析任务并发控制
_ai_task_semaphore = None
_ai_task_max_concurrent = 3  # 最多同时3个任务
_ai_task_running = set()  # 正在运行的任务ID
_ai_task_running_lock = threading.Lock()  # 手动端点线程与调度循环并发读写集合，用锁保证「查+占」原子


def try_begin_ai_task_run(task_id: int) -> bool:
    """手动/调度共用的 AI 任务运行互斥：任务已在跑返回 False。

    调度器与 api.py 的「立即运行」端点共用同一集合：任务执行可达数分钟，
    external_id 只带秒级时间戳，UNIQUE 约束兜不住不同秒触发的重复运行，
    双跑会产出双份报告。占住后必须配对调用 end_ai_task_run 释放。
    """
    with _ai_task_running_lock:
        if task_id in _ai_task_running:
            return False
        _ai_task_running.add(task_id)
        return True


def end_ai_task_run(task_id: int) -> None:
    """释放 D1 互斥（配合 try_begin_ai_task_run 使用）。"""
    with _ai_task_running_lock:
        _ai_task_running.discard(task_id)


from .logging_setup import redact_secrets
from .mx_llm_tagging import mx_llm_tag_auto_loop
from .fetchers.base import (
    CN_TZ,
    PLATFORM_LABELS,
    Fetcher,
    Post,
    is_collapsed_translation,
    is_stale_backfill,
    parse_published_at,
    twitter_translate_enabled,
    with_twitter_display,
)
from .notifiers.base import Notifier
from .proxy import note_fetch_proxy, tick_proxy_pools

# MX 相关导入
try:
    from .fetchers.mx.client import MXTokenExpiredError
    from .services.mx_sync import MXRoomSyncService
    from .services.mx_window import (
        arm_windows,
        generate_mx_daily_windows,
        in_window as mx_in_window,
        pick_daily_fallback_slot,
    )
    MX_AVAILABLE = True
except Exception as e:
    MX_AVAILABLE = False
    logger.warning("MX modules not available: %s", e)

    class MXTokenExpiredError(RuntimeError):
        """MX 模块不可用时的占位类型（仅供 except 匹配）。"""

# 全局 MX 相关变量
_mx_fetcher = None
_mx_sync_service = None
_mx_login_report = None

# MX 实时/兜底消息本地规则打标输入（词表/股票名/别名）的缓存时长：
# WS 消息逐条打标，全量股票名单不能逐条查库；60 秒与管理员改词表的
# 下批生效速度对齐（轮询管线也是每轮现取一次）
MX_RULE_TAG_INPUTS_TTL = 60.0


def get_mx_ws_status() -> dict:
    """获取 MX WebSocket 连接状态（含最近一次「登录」的逐接口报告）。"""
    if _mx_fetcher and hasattr(_mx_fetcher, "get_ws_status"):
        status = _mx_fetcher.get_ws_status()
    else:
        status = {
            "connected": False,
            "last_message_at": None,
            "gave_up": False,
            "detail": "MX 未启用或 WS 尚未初始化",
        }
    status["login_report"] = _mx_login_report
    return status

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
CICC_ALERT_CHECK_INTERVAL = 600  # 中金存储告警/通知检查节流
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
X_RATE_LIMIT_BACKOFF_SECONDS = 900  # X 429 窗口约 15 分钟，30s 起跳会在窗内反复撞限
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
    """Cookie、登录、限流或代理池枯竭时停整平台；单大V超时不连坐。"""
    from .proxy import ProxyUnavailable

    if isinstance(exc, ProxyUnavailable):
        return True
    text = str(exc)
    if any(token in text for token in ("cookie", "WAF", "反爬", "登录")):
        return True
    if "HTTP 429" in text and ("X GraphQL" in text or "X typeahead" in text):
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


def _parse_edge_translation(payload) -> str:
    if not isinstance(payload, list) or not payload:
        return ""
    item = payload[0]
    if not isinstance(item, dict):
        return ""
    trans = item.get("translations")
    if not isinstance(trans, list) or not trans:
        return ""
    text = trans[0].get("text") if isinstance(trans[0], dict) else ""
    return text.strip() if isinstance(text, str) else ""


def translate_text(
    text: str,
    target: str = "zh-CN",
    client=None,
    tweet_id: str | None = None,
    twitter_cookie: str | None = None,
    **_ignored,
) -> str:
    """把 X/Truth 内容转成中文。优先 Grok，失败回退 Edge，再 MyMemory。"""
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
        try:
            # ponytail: unofficial Edge 接口，挂了再走 MyMemory/原文
            resp = client.post(
                "https://edge.microsoft.com/translate/translatetext",
                params={"from": "", "to": "zh-Hans", "isEnterpriseClient": "false"},
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                    ),
                },
                json=[text[:2000]],
            )
            resp.raise_for_status()
            translated = _parse_edge_translation(resp.json())
            if translated and not is_collapsed_translation(translated, text):
                return translated
        except Exception as exc:  # noqa: BLE001
            errors.append(f"edge_translate: {exc}")
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


def _truth_backfill_candidate(text: str) -> bool:
    """值得回填的原文：去掉链接后仍有实质英文内容（纯链接/中文帖不翻）。"""
    value = (text or "").strip()
    if len(value) < 20:
        return False
    without_links = re.sub(r"https?://\S+", "", value).strip()
    if len(without_links) < 8 or _already_chinese(value):
        return False
    return sum(1 for ch in value if ch.isascii() and ch.isalpha()) >= 8


def backfill_truth_translations(db, limit: int = 3) -> int:
    """低频补翻特朗普近 1 天漏翻的帖子；每轮少量，回填完自然停。

    译不动（原样返回/收成省略号）的帖子写 src=content 标记为已处理，避免每轮重扫。
    """
    rows = db.list_untranslated_truth_posts(limit=limit * 3)
    if not rows:
        return 0
    from .fetchers.twitter import configured_twitter_cookie

    tw_cookie = configured_twitter_cookie(db)
    done = 0
    for row in rows:
        if done >= limit:
            break
        content = (row["content"] or "").strip()
        if not _truth_backfill_candidate(content):
            db.set_post_translation(row["id"], row["title"] or "", content, row["title"] or "", content)
            continue
        try:
            translated = translate_text(content, twitter_cookie=tw_cookie)
        except Exception as exc:  # noqa: BLE001 - 单帖失败留待下轮
            logger.warning("Truth 翻译回填失败 post=%s err=%s", row["id"], exc)
            continue
        if not translated or is_collapsed_translation(translated, content) or translated == content:
            db.set_post_translation(row["id"], row["title"] or "", content, row["title"] or "", content)
            continue
        db.set_post_translation(
            row["id"],
            translated.splitlines()[0][:80],
            translated,
            row["title"] or "",
            content,
        )
        done += 1
    return done


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


# AI 分析任务停用告警冷却：同一任务 30 分钟内只发一条「系统通知」
AI_TASK_STOP_ALERT_COOLDOWN = 1800


def build_system_alert_post(db: DB, title: str, content: str) -> Post | None:
    """构造系统 KOL「系统通知」的告警帖（必要时自动创建该 KOL），返回 Post。

    只负责构造；入库与实时推送由调用方的管线完成（Scheduler.ingest_external_post
    或 api 层的 on_external_post 回调），便于调度器内外复用同一告警形态。
    """
    kol = db.get_kol_by_external("system", "system_alert")
    if kol is None:
        try:
            kol_id = db.add_kol(
                platform="system",
                name="系统通知",
                external_id="system_alert",
            )
            db.update_kol(kol_id, enabled=True, silent=False)
        except Exception:
            logger.error("创建系统通知 KOL 失败", exc_info=True)
            return None
    else:
        kol_id = kol["id"]
    return Post(
        platform="system",
        kol_id=kol_id,
        kol_name="系统通知",
        external_id=f"system_alert_{uuid.uuid4().hex[:12]}",
        title=title,
        content=content,
        url="",
        published_at=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        post_type="post",
    )


def build_ai_task_stop_alert(db: DB, task_id: int, reason: str) -> Post | None:
    """构造「AI 分析任务重试耗尽已停用」告警帖；冷却窗口内返回 None 不重复发。

    任务在自动重试仍失败后被停用（见 ai_analysis._register_failure），此处通过
    系统 KOL「系统通知」告知管理员，入库后实时推送给订阅者。
    """
    if not _cooldown_ok(db, f"ai_task_stop_alert_{task_id}", AI_TASK_STOP_ALERT_COOLDOWN):
        return None
    task = db.get_ai_task(task_id) or {}
    target_kol = (
        db.get_kol(task["target_kol_id"]) if task.get("target_kol_id") else None
    )
    kol_label = f"「{target_kol['name']}」" if target_kol else f"ID {task.get('target_kol_id')}"
    title = "⚠️ AI 分析任务连续失败已停止"
    content = (
        f"任务「{task.get('name') or task_id}」（目标 KOL：{kol_label}）"
        f"自动重试一次后仍失败，已停止调度，本次错误：\n"
        f"{(reason or '未知错误')[:300]}\n"
        "请检查 LLM 配置与网络后，在管理后台 AI 分析页重新启用任务。"
    )
    return build_system_alert_post(db, title, content)


def build_mx_view_fail_alert(db: DB, reason: str) -> Post | None:
    """MX 观点快照连续失败 ≥3 次的告警帖；冷却 30 分钟。"""
    if not _cooldown_ok(db, "mx_view_fail_alert", AI_TASK_STOP_ALERT_COOLDOWN):
        return None
    title = "⚠️ MX 观点研判连续失败"
    content = (
        f"MX 大V观点快照批次连续失败 {mx_view_analysis.get_fail_count(db)} 次，本次错误：\n"
        f"{(reason or '未知错误')[:300]}\n"
        "游标未推进，下个快照时刻会自动重试；也可到 管理后台 → 智囊团 手动跑一批诊断。"
    )
    return build_system_alert_post(db, title, content)


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
        # MX 走 WebSocket 实时推送，不参与轮询自动拉取历史消息；
        # 需要补历史时由管理员在后台手动触发「拉取历史」。
        if kol["platform"] == "mx":
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
                # 同轮已有 worker 判定整平台故障时，不再让排队任务继续撞上游。
                with platform_lock[kol["platform"]]:
                    if now < state.skip_until:
                        return
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
            if _is_platform_wide_error(exc) and "HTTP 429" in str(exc):
                delay = max(delay, X_RATE_LIMIT_BACKOFF_SECONDS)
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
        # 同轮并发请求可能已判定整平台故障；单个成功不能清掉该退避。
        platform_blocked = now < state.skip_until
        recovered = kol["id"] in state.alerted_kols
        if recovered:
            state.alerted_kols.discard(kol["id"])
        state.kol_fails[kol["id"]] = 0
        if not platform_blocked:
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
            post.platform in ("twitter", "truth")
            and translate_twitter
            and (post.platform, post.external_id) not in existing_keys
        ):
            # 仅翻译新帖，避免每轮重复调用翻译接口
            try:
                # Truth 的数字 id 不是 tweet id，不能走 POST 模式
                tweet_id = extract_tweet_id(post.external_id) if post.platform == "twitter" else ""
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
                    extra = {"twitter_cookie": tw_cookie} if tw_cookie else {}
                    post.title = translate_text(post.title or "", **extra)
                    post.content = translate_text(post.content or "", **extra)
            except Exception as exc:  # noqa: BLE001 - 翻译失败退回原文
                logger.warning("X 内容翻译失败 post=%s err=%s", post.external_id, exc)
    # 关键词规则打标：仅对新帖（与翻译同判据），纯本地计算零成本，异常不影响入库
    try:
        from .tagging import (
            STOCK_PER_POST_MAX,
            TAG_PER_POST_MAX,
            rule_tag_posts,
            stock_tag_posts,
        )

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
                # 合并：话题标签（≤3）+ 股票标签（≤6），总上限 10
                topics = tagged.get(i, [])
                stocks = stock_tagged.get(i, [])
                post.tags = (
                    list(topics[:TAG_PER_POST_MAX]) + list(stocks[:STOCK_PER_POST_MAX])
                )[:POST_TAGS_MAX]
    except Exception as exc:  # noqa: BLE001 - 打标失败不影响抓取/推送
        logger.warning(
            "规则打标失败 platform=%s kol=%s err=%s", kol["platform"], kol["name"], exc
        )
    # 批量入库（一个事务），再逐条推送
    # 首次抓取判定：baseline_ready=0 的大V（新增时写入）本轮仅建立历史基线，不推送。
    # 否则订阅新大V时，最近 N 条历史帖会一次性连推（连珠炮刷屏）。
    # 首次成功 fetch（含空列表）即打标：空账号/偶发空窗后，下一轮新帖必须正常推送。
    first_fetch = not kol.get("baseline_ready")
    watermark = db.max_published_at(kol["id"])
    post_ids = db.insert_posts_batch(posts)
    try:
        from . import imgbed

        for post, post_id in zip(posts, post_ids):
            if post_id is None:
                continue
            imgbed.enqueue_urls(db, post.images)
    except Exception:  # noqa: BLE001 - 图床入队失败不影响抓取推送
        logger.exception("图床入队失败 platform=%s kol=%s", kol["platform"], kol["name"])
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
        if is_stale_backfill(post.published_at, watermark):
            logger.info(
                "历史回灌入库不推送 platform=%s kol=%s id=%s at=%s wm=%s",
                post.platform, post.kol_name, post.external_id, post.published_at, watermark,
            )
            continue
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
    from types import SimpleNamespace

    from .db import user_plain_secret
    from .url_safety import is_allowed_trusted_llm_base

    for user in db.list_users():
        if user.get("is_admin"):
            api_key = user_plain_secret(user, "llm_api_key", db)
            api_base = (user.get("llm_api_base") or "").strip()
            if api_key and is_allowed_trusted_llm_base(api_base):
                return SimpleNamespace(
                    api_base=api_base,
                    api_key=api_key,
                    model=(user.get("llm_model") or "").strip() or "grok-4.6",
                    user_supplied=False,
                )
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
        # 卡片超限等确定性错误重发必败，不入重试队列
        if retry_queue is not None and not is_permanent_push_error(exc):
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


def format_startup_message(*, now: datetime | None = None, instance: str | None = None) -> str:
    from .version import APP_VERSION

    if instance is None:
        instance = (os.environ.get("VPUSH_INSTANCE") or "").strip()
    stamp = (now or datetime.now(CN_TZ)).strftime("%Y-%m-%d %H:%M")
    lines = ["✅ V Push 服务已启动", f"v{APP_VERSION}"]
    if instance:
        lines.append(instance)
    lines.append(stamp)
    return "\n".join(lines)


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
        news_service=None,
        ima_archive_file=None,
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
        self.news_service = news_service
        # callable(relative_txt_path) -> Path | None；研报结构化抽取读文本用
        self.ima_archive_file = ima_archive_file
        self.states: dict[str, PlatformState] = {}
        self._digest: dict[int, list[Post]] = {}
        self._dnd_buffer: dict[int, list[Post]] = {}
        self._secondary_buffer: dict[int, list[Post]] = {}
        self._secondary_first_at: dict[int, float] = {}
        self.retry_queue = PushRetryQueue()
        self._stop = asyncio.Event()
        self._last_cleanup = 0.0
        self._last_report_extract = time.monotonic()
        self._last_digest_flush = time.monotonic()
        self._last_xueqiu_probe = time.monotonic()
        self._last_cookie_keepalive = time.monotonic()
        self._last_retry = 0.0
        self._last_health_check = time.monotonic()
        self._last_cicc_alert_check = 0.0
        self._last_knowledge_notify = 0.0
        self._last_proxy_tick = 0.0
        self._last_mx_view_check = 0.0
        self._mx_view_check_running = False
        self._mx_sync_service = None
        self._mx_ws_task = None
        self._mx_ws_on_message = None
        self._mx_ws_on_give_up = None
        # 每日多窗口管理：WS 会话只在窗口内运行（每日三段随机时段，见 mx_window.py）
        self._mx_window_task: asyncio.Task | None = None
        # MX 消息 LLM 打标循环：独立于 MX 会话（只读 posts 表），MX 未启用也照常调度
        self._mx_tag_task: asyncio.Task | None = None
        # MX 消息本地规则打标输入缓存：(monotonic, (tag_rules, stock_names, stock_aliases))，
        # WS 消息逐条打标，全量名单 TTL 内复用（并发解析线程下的重复取一次无害）
        self._mx_rule_tag_cache: tuple[float, tuple] | None = None
        self._mx_windows: list | None = None
        self._mx_window_date = None
        self._mx_window_open = False
        # 重启安全：开窗时刻已错过的窗口不武装（重启后不自动续连）
        self._mx_armed: list[bool] | None = None
        # 每日一次兜底拉取的预约时刻（随窗口一起生成，当天固定；错过不补打）
        self._mx_fallback_at: datetime | None = None
        self._mx_fallback_done = False
        # 晚间兜底断开：23:30-23:55 之间随机一秒，若 MX 仍在线则强制断开（防手动登录忘关）
        self._mx_force_close_at: datetime | None = None
        self._mx_force_close_done = False
        # 本窗口内 WS 已永久放弃自动重连（防窗口循环反复拉起，违背「只重连一次」）
        self._mx_ws_gave_up = False
        # TOKEN 过期熔断：置位后不再发起任何拉取/WS，直到管理员更换 TOKEN，
        # 或管理员手动「登录」半开重探成功（见 mx_manual_login）
        self._mx_token_expired = False
        # 本窗口已做过手动登录尝试的窗口下标：窗口循环据此跳过自动登录，
        # 防止手动登录部分失败后 30s tick 重跑完整启动序列
        self._mx_manual_attempted_idx: int | None = None
        # 最近一次会话（WS）启动时刻：自动/手动统一在 mx_ws_control("connect") 记录，
        # 供 30s 循环做会话最长时长滚动兜底（见 _mx_maybe_session_timeout）
        self._mx_session_started_at: datetime | None = None
        # 事件循环引用：线程侧（publish_mx_error 阻塞口径）需要把 WS 掐断投递回调度循环
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_imgbed = 0.0
        self._last_truth_backfill = 0.0

    def _submit_news_due(self):
        if self.news_service is None:
            return []
        try:
            return self.news_service.submit_due()
        except Exception:  # noqa: BLE001 - 新闻失败不能停止其他调度
            logger.exception("财经新闻刷新异常")
            return []

    def stop(self):
        self._stop.set()

        # 停止 MX 相关任务
        if self._mx_ws_task:
            self._mx_ws_task.cancel()
            self._mx_ws_task = None
        if self._mx_window_task:
            self._mx_window_task.cancel()
            self._mx_window_task = None
        if self._mx_tag_task:
            self._mx_tag_task.cancel()
            self._mx_tag_task = None
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

    def ingest_external_post(self, post: Post) -> int | None:
        """外部来源（系统 KOL webhook）发帖：入库 + 实时推送，返回 post_id（重复为 None）。

        与 MX 实时消息同链路：复用免打扰/次要合并缓冲与推送重试队列，
        大V 屏蔽词命中只入库不推送，静默源同样不打推送。
        """
        post_id = self.db.save_post(post)
        if not post_id:
            return None
        if self.db.is_post_blocked(post_id):
            logger.info(
                "关键词拦截不推送 platform=%s kol=%s id=%s",
                post.platform, post.kol_name, post.external_id,
            )
            return post_id
        kol = self.db.get_kol(post.kol_id) or {}
        if kol.get("silent"):
            logger.info(
                "静默源入库不打推送 platform=%s kol=%s id=%s",
                post.platform, post.kol_name, post.external_id,
            )
            return post_id
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
        return post_id

    def _mx_rule_tag_inputs(self) -> tuple:
        """MX 本地规则打标输入（话题词表/股票名/股票别名），TTL 缓存。

        WS 消息逐条打标，全量股票名单不能逐条查库；60 秒与管理员改词表的
        下批生效速度对齐（轮询管线也是每轮现取一次）。
        """
        cached = self._mx_rule_tag_cache
        now = time.monotonic()
        if cached is not None and now - cached[0] < MX_RULE_TAG_INPUTS_TTL:
            return cached[1]
        from .stock_universe import aliases_for_tagging, names_for_plain_text_tagging

        excluded = self.db.get_stock_name_exclusions()
        inputs = (
            self.db.get_tag_vocabulary(),
            names_for_plain_text_tagging(self.db.get_stock_names(), excluded),
            aliases_for_tagging(self.db.get_stock_aliases(), excluded),
        )
        self._mx_rule_tag_cache = (now, inputs)
        return inputs

    def _apply_mx_rule_tags(self, post) -> None:
        """MX 消息入库前先走本地规则打标（消息即时带上标签），LLM 打标完成后
        由 mx_llm_tagging.update_post_tags_llm 整体替换。

        与轮询管线 _process_posts 同口径：话题（≤3）+ 股票（≤6）合并，总上限 10。
        打标失败不影响入库与推送。
        """
        try:
            from .tagging import (
                STOCK_PER_POST_MAX,
                TAG_PER_POST_MAX,
                rule_tag_posts,
                stock_tag_posts,
            )

            tag_rules, stock_names, stock_aliases = self._mx_rule_tag_inputs()
            topics = rule_tag_posts([post], tag_rules).get(0) or []
            stocks = stock_tag_posts([post], stock_names, aliases=stock_aliases).get(0) or []
            post.tags = (
                list(topics)[:TAG_PER_POST_MAX] + list(stocks)[:STOCK_PER_POST_MAX]
            )[:POST_TAGS_MAX]
        except Exception:  # noqa: BLE001 - 打标失败不影响入库推送
            logger.warning(
                "MX 消息规则打标失败 kol=%s id=%s",
                getattr(post, "kol_name", ""),
                getattr(post, "external_id", ""),
                exc_info=True,
            )

    def _publish_system_alert_sync(self, title: str, content: str) -> int | None:
        """（阻塞版）用系统平台账号「系统通知」发布告警：入库 + 实时推送。

        与系统 KOL webhook 同链路（ingest_external_post），但无需 token/签名，
        供调度器内部发布 WS 重连失败、TOKEN 过期等运行状态消息。
        """
        post = build_system_alert_post(self.db, title, content)
        if post is None:
            return None
        return self.ingest_external_post(post)

    def check_and_broadcast_wscn(self) -> None:
        """检查快讯缓存中新的重要快讯，转发到已配置的系统 KOL 播报。

        由 api.py 的 wscn 后台刷新循环每 TTL 秒调用一次。读 settings 表判断
        是否启用及目标 KOL/score 阈值，用 wscn_broadcast_last_id 跳过已处理条目，
        逐条 ingest_external_post（INSERT OR IGNORE 天然去重，重复不推）。
        """
        try:
            if self.db.get_setting("wscn_broadcast_enabled") != "1":
                return
            kol_id_raw = self.db.get_setting("wscn_broadcast_kol_id") or ""
            kol_id = int(kol_id_raw) if kol_id_raw.isdigit() else 0
            if kol_id <= 0:
                return
            kol = self.db.get_kol(kol_id)
            if not kol or kol["platform"] != "system":
                logger.warning(
                    "wscn auto broadcast: 目标 KOL %s 不存在或非系统平台，跳过",
                    kol_id,
                )
                return
            threshold_raw = self.db.get_setting("wscn_broadcast_score_threshold") or "2"
            threshold = int(threshold_raw) if threshold_raw.isdigit() else 2
            last_id_raw = self.db.get_setting("wscn_broadcast_last_id") or "0"
            last_id = int(last_id_raw) if last_id_raw.isdigit() else 0

            from .api import _fetch_wscn_lives

            data = _fetch_wscn_lives(limit=30)
            items = data.get("items") or []
            # id 升序处理：先发的先播报，时间线顺序正确
            candidates = [
                it for it in items
                if int(it.get("id") or 0) > last_id
                and int(it.get("score") or 1) >= threshold
            ]
            candidates.sort(key=lambda x: int(x.get("id") or 0))
            if not candidates:
                return
            kol_name = kol["name"]
            max_id = last_id
            broadcast_count = 0
            for item in candidates:
                item_id = int(item["id"])
                title = (item.get("highlight_title") or "").strip() or "重要快讯"
                content = item.get("body") or ""
                url = (item.get("url") or "").strip()
                raw_ts = item.get("published_at") or ""
                try:
                    dt = datetime.fromisoformat(raw_ts) if raw_ts else datetime.now(CN_TZ)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=CN_TZ)
                    published_at = dt.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    published_at = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
                post = Post(
                    platform="system",
                    kol_id=kol_id,
                    kol_name=kol_name,
                    external_id=f"wscn_flash_{item_id}",
                    title=title,
                    content=content,
                    url=url,
                    published_at=published_at,
                    post_type="wscn_flash",
                )
                post_id = self.ingest_external_post(post)
                if post_id:
                    broadcast_count += 1
                # 无论是否重复，推进 last_id 避免反复检查已处理条目
                if item_id > max_id:
                    max_id = item_id
            if max_id > last_id:
                self.db.set_setting("wscn_broadcast_last_id", str(max_id))
            if broadcast_count:
                logger.info(
                    "wscn auto broadcast: 检查 %d 条重要快讯，播报 %d 条到 KOL %s",
                    len(candidates), broadcast_count, kol_name,
                )
        except Exception:
            logger.warning("wscn auto broadcast check failed", exc_info=True)

    async def _publish_system_alert(self, title: str, content: str):
        """用系统平台账号「系统通知」发布运行告警（异步入口）。

        发布失败只记日志，绝不能反过来影响调用方（WS 重连任务等）。
        """
        try:
            post_id = await asyncio.to_thread(
                self._publish_system_alert_sync, title, content
            )
            if post_id:
                logger.info("系统告警已发布 title=%s post_id=%s", title, post_id)
        except Exception:
            logger.error(f"发布系统告警失败 title={title}", exc_info=True)

    async def _alert_ai_task_stopped(self, task_id: int, reason: str) -> None:
        """AI 分析任务重试耗尽被停用后，经系统 KOL「系统通知」告知。

        构造/冷却判定走线程（阻塞 DB），推送复用 ingest_external_post 管线；
        任何异常只记日志，不影响调度主流程。
        """
        try:
            post = await asyncio.to_thread(
                build_ai_task_stop_alert, self.db, task_id, reason
            )
            if post is None:
                return
            post_id = await asyncio.to_thread(self.ingest_external_post, post)
            if post_id:
                logger.info(
                    "AI 任务停用告警已发布 task_id=%s post_id=%s", task_id, post_id
                )
        except Exception:
            logger.error("发布 AI 任务停用告警失败 task_id=%s", task_id, exc_info=True)

    def _mx_touch_loop(self):
        """记录当前事件循环（供线程侧把 WS 掐断等动作投递回调度循环）。"""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    def _mx_trigger_token_expired(self):
        """TOKEN 过期统一入口：熔断 + 立即掐断 WS。

        任何链路（HTTP 拉取/WS 被拒/手动登录）发现 TOKEN 失效都必须走这里——
        不能出现「接口已报过期、WS 还挂在死 token 上」的中间态。
        """
        self._mx_token_expired = True
        self._mx_schedule_ws_abort()

    def _mx_schedule_ws_abort(self):
        """把「立即掐断 WS」调度回事件循环执行（publish_mx_error 可能在线程中调用）。"""
        task = self._mx_ws_task
        fetcher = self.fetchers.get("mx")
        ws_client = getattr(fetcher, "ws_client", None) if fetcher else None
        if ws_client is not None:
            # 先同步置位：让 run_forever 立刻失去重连/继续的理由
            ws_client._should_stop = True
            ws_client.manually_stopped = True
            ws_client.connected = False
        if task is None and ws_client is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(self._mx_abort_ws(task, ws_client))
        elif self._loop is not None and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._mx_abort_ws(task, ws_client), self._loop)
        elif task is not None:
            task.cancel()  # 兜底：拿不到事件循环时至少取消任务

    async def _mx_abort_ws(self, task, ws_client):
        """掐断 WS：取消运行任务 + 关标签页式断开（不发任何关闭包）。"""
        if task is not None and not task.done():
            task.cancel()
        if ws_client is not None:
            try:
                await ws_client.stop(reason="TOKEN 已熔断，系统强制断开")
            except Exception:  # noqa: BLE001 - 尽力掐断
                logger.debug("MX WS 掐断失败（忽略）", exc_info=True)
        # 竞态保护：掐断期间窗口循环可能已 connect 出新任务，只清自己的旧引用
        if self._mx_ws_task is task:
            self._mx_ws_task = None

    def publish_mx_error(self, key: str, title: str, content: str):
        """MX 平台报错统一走系统 KOL「系统通知」发布；同 key 30 分钟节流。

        key=token_expired 时同时置熔断标记：在管理员更换 TOKEN 前不再发起
        任何 MX 拉取/连接，避免死 TOKEN 继续打加重风控处罚。
        供调度器内部与 api 层（on_mx_alert）统一调用；阻塞版可在线程中调用。
        """
        try:
            if key == "token_expired":
                self._mx_trigger_token_expired()
            if not _cooldown_ok(self.db, f"mx_alert_{key}", 1800):
                return
            post_id = self._publish_system_alert_sync(title, content)
            if post_id:
                logger.info("MX 报错告警已发布 key=%s post_id=%s", key, post_id)
        except Exception:
            logger.error(f"发布 MX 报错失败 key={key}", exc_info=True)

    # ---- MX 每日运行窗口：7-8 点随机开、16-17 点随机关，窗口外零请求 ----

    # ---- MX 每日运行窗口：每日三段随机时段（早/午后/晚间），窗口外零请求 ----

    # 会话最长时长（小时）：晚间强关只覆盖 23:30-23:55，之后手动登录的会话
    # 可能整夜在线；按「最近一次会话启动时刻」滚动兜底，30s 循环里超时即强断
    _MX_MAX_SESSION_HOURS = 4

    def _mx_windows_today(self) -> list:
        """取（必要时生成）当天的运行窗口与兜底预约时刻，生成后当天固定。"""
        today = datetime.now(CN_TZ).date()
        if self._mx_window_date != today or self._mx_windows is None:
            self._mx_window_date = today
            self._mx_windows = generate_mx_daily_windows(today)
            # 重启安全：生成时刻（≈重启时刻）已过开窗点的窗口不武装——重启后
            # 不自动续连，只能管理员「登录」手动拉起，或等下一个未到点的窗口
            self._mx_armed = arm_windows(self._mx_windows, datetime.now(CN_TZ))
            # 兜底预约槽只从当天仍武装的窗口里挑：已错过开窗点的窗口不会自动
            # 拉起会话，选中它们只会得到「时刻一到就放弃」的迟到执行
            self._mx_fallback_at = pick_daily_fallback_slot(self._mx_windows, self._mx_armed)
            self._mx_fallback_done = False
            # 新的一天重置「本窗口已手动登录尝试」标记（窗口下标跨天复用）
            self._mx_manual_attempted_idx = None
            # 晚间兜底断开时刻：23:30-23:55 之间随机（与晚间关窗同区间，先到者
            # 关窗并 disarm 当前窗口，见 _mx_maybe_nightly_force_close；这条额外
            # 兜住「关窗后手动登录忘关」的场景）
            self._mx_force_close_at = datetime(
                today.year, today.month, today.day, 23, 30, tzinfo=CN_TZ
            ) + timedelta(seconds=random.randint(0, 1500))
            self._mx_force_close_done = False
            missed = [i + 1 for i, armed in enumerate(self._mx_armed) if not armed]
            logger.info(
                "MX 今日运行时段：%s；每日兜底拉取预约时刻：%s%s",
                "、".join(
                    f"{s.strftime('%H:%M:%S')}~{e.strftime('%H:%M:%S')}"
                    for s, e in self._mx_windows
                ),
                self._mx_fallback_at.strftime("%H:%M:%S") if self._mx_fallback_at else "无",
                f"；第 {'、'.join(map(str, missed))} 段因重启错过登录时刻，今天不再自动登录"
                if missed
                else "",
            )
        return self._mx_windows

    def _mx_current_window_index(self) -> int | None:
        """now 所处的窗口下标；不在任何窗口内时返回 None。"""
        now = datetime.now(CN_TZ)
        for i, (start, stop) in enumerate(self._mx_windows_today()):
            if start <= now < stop:
                return i
        return None

    def _mx_in_window(self) -> bool:
        return mx_in_window(datetime.now(CN_TZ), self._mx_windows_today())

    def _mx_session_active(self) -> bool:
        return bool(self._mx_ws_task and not self._mx_ws_task.done())

    def _mx_log_auto_event(self, action: str, detail: str) -> None:
        """把系统自动的 MX 平台登录/断开写入操作日志（user_id=NULL，非管理员手动操作）。"""
        try:
            self.db.log_admin_action(None, action, "mx", detail)
        except Exception:  # noqa: BLE001 - 日志失败不影响窗口管理
            logger.debug("写入 MX 自动登录/断开操作日志失败", exc_info=True)

    def _mx_view_check_tick(self) -> None:
        """快照触发检查（线程内执行）：到期即跑；连续失败≥3 发系统通知。"""
        result = mx_view_analysis.run_due_view_batch(
            self.db, llm_config=_system_llm_config(self.db, self.llm_config)
        )
        if result is None:
            return
        if result.get("failed") and int(result.get("consecutive") or 0) >= 3:
            post = build_mx_view_fail_alert(self.db, str(result.get("error") or ""))
            if post is not None:
                self.ingest_external_post(post)

    async def _mx_window_loop(self):
        """MX 每日运行时段管理循环：到点自动 MX 平台登录、时段结束自动断开，顺带检查 TOKEN 时效。

        每个时段只尝试登录一次；失败/放弃后不再自动拉起（避免形成
        周期性重连流量），靠 TOKEN 更换或次日时段恢复。
        """
        while not self._stop.is_set():
            try:
                await self._mx_window_tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("MX window loop error", exc_info=True)
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                raise

    async def _mx_window_tick(self):
        """窗口循环单次 tick（每 30 秒一次）：开/关窗、TOKEN 时效与各类兜底检查。

        独立成函数便于对「强关 disarm 后不再重拉」「手动登录后不重跑」等
        时序约束做回归测试（tests/test_mx.py 直接驱动单次 tick）。
        """
        self._mx_touch_loop()
        idx = self._mx_current_window_index()
        if idx is not None:
            if not self._mx_window_open:
                if not self._mx_armed[idx] or self._mx_manual_attempted_idx == idx:
                    pass  # 重启前已错过该窗口的开窗时刻，或本窗口已手动登录尝试过：不自动续连（管理员可手动「登录」）
                else:
                    self._mx_window_open = True
                    self._mx_ws_gave_up = False  # 新窗口：复位放弃标记
                    await self._mx_session_start()
                    start, stop = self._mx_windows[idx]
                    await asyncio.to_thread(
                        self._mx_log_auto_event,
                        "mx_auto_login",
                        f"第 {idx + 1} 段运行时段 {start:%H:%M:%S}~{stop:%H:%M:%S} "
                        "到点，系统自动执行 MX 平台登录（启动序列 + 房间同步 + WS 推送）",
                    )
        elif self._mx_window_open:
            self._mx_window_open = False
            await self._mx_session_stop()
            await asyncio.to_thread(
                self._mx_log_auto_event,
                "mx_auto_disconnect",
                "运行时段结束，系统自动执行 MX 平台断开（时段外零请求）",
            )
        await asyncio.to_thread(self._mx_check_token_age)
        await self._mx_maybe_daily_fallback()
        await self._mx_maybe_nightly_force_close()
        await self._mx_maybe_session_timeout()

    async def _mx_session_start(self):
        """系统自动执行 MX 平台登录：按官方冷启动序列执行（启动请求 → 房间列表 → WS）。

        逐接口结果写入模块级 _mx_login_report（source=auto），后台「接口状态」
        展示的是系统自动登录的真实启动过程，而不只是 WS 连接结果。TOKEN 过期
        即熔断告警并中止本次登录；其余失败只告警不阻断消息链路。
        """
        global _mx_login_report
        self._mx_touch_loop()

        steps: list[dict] = []

        def record(name: str, ok: bool, detail: str):
            steps.append({"name": name, "ok": ok, "detail": str(detail)[:100]})

        def finish():
            global _mx_login_report
            _mx_login_report = {
                "time": datetime.now(CN_TZ).strftime("%H:%M:%S"),
                "ok": bool(steps) and all(s["ok"] for s in steps),
                "steps": steps,
                "source": "auto",
            }

        if self._mx_token_expired:
            logger.warning("MX 平台登录取消：TOKEN 已过期未更换，跳过登录")
            record("前置检查", False, "TOKEN 已熔断（过期），请更换 TOKEN 后等待下个运行时段")
            finish()
            return
        # 官方网页端每次「打开应用」都会：补发启动只读序列（user/info → system/config
        # → msg/tip → grouplist → 平台公告）→ 拉一次房间列表 → 连 WS（2026-09-02
        # 抓包实测）。vpush 开窗完全按此顺序执行，使请求足迹与「真人打开网页」一致。
        if self._mx_sync_service is not None:
            token_expired = False
            try:
                boot_steps = await asyncio.to_thread(self._mx_sync_service.boot_sequence)
                steps.extend(boot_steps or [])
            except MXTokenExpiredError:
                token_expired = True
            except Exception as exc:  # noqa: BLE001 - 启动序列异常不阻断消息链路
                record("启动序列", False, str(exc)[:100])
                await asyncio.to_thread(
                    self.publish_mx_error,
                    "room_sync",
                    "MX 房间同步失败",
                    f"⚠️ 登录时的启动序列/房间列表同步失败：{exc}",
                )
            else:
                try:
                    count = await self._mx_sync_service.sync_rooms()
                    record("room/list", True, f"{count} 个房间")
                except MXTokenExpiredError:
                    token_expired = True
                except Exception as exc:  # noqa: BLE001
                    record("room/list", False, str(exc)[:100])
                    await asyncio.to_thread(
                        self.publish_mx_error,
                        "room_sync",
                        "MX 房间同步失败",
                        f"⚠️ 登录时的房间列表同步失败：{exc}",
                    )
            if token_expired:
                self._mx_trigger_token_expired()
                record("TOKEN 校验", False, "TOKEN 已过期/无效，本次登录中止")
                finish()
                await asyncio.to_thread(
                    self.publish_mx_error,
                    "token_expired",
                    "MX TOKEN 已过期",
                    "⚠️ MX TOKEN 已过期或无效，MX 平台登录失败，已暂停拉取与实时推送。"
                    "\n请到后台「数据源 → MX」更换 TOKEN（TOKEN 需每 2 天更换一次）。",
                )
                return
        if self.mx_config.ws_enabled:
            try:
                message = await self.mx_ws_control("connect", source="auto")
                record("websocket", True, message)
                logger.info(f"MX 平台登录：{message}")
            except Exception as exc:
                record("websocket", False, str(exc)[:100])
                logger.error(f"MX 平台登录失败：{exc}", exc_info=True)
                await asyncio.to_thread(
                    self.publish_mx_error,
                    "session_start",
                    "MX 平台登录失败",
                    f"⚠️ MX 平台登录时 WebSocket 启动失败：{exc}",
                )
        else:
            record("websocket", True, "ws_enabled=false，跳过实时推送")
            logger.info("MX 平台登录完成，但实时推送未启用（ws_enabled=false），仅完成启动序列与房间同步")
        finish()

    async def _mx_session_stop(self):
        """系统自动执行 MX 平台断开：断开 WS 监听（运行时段外零请求）。"""
        if self._mx_session_active():
            try:
                await self.mx_ws_control("disconnect", source="auto")
            except Exception:  # noqa: BLE001 - 断开尽力即可
                logger.warning("MX 平台断开失败", exc_info=True)
        logger.info("MX 平台已断开：运行时段结束，会话停止")

    async def _mx_maybe_daily_fallback(self):
        """每日一次兜底拉取：到达当天预约时刻且会话存活时执行，每天最多 1 次。

        兜底的存在意义只是防 WS 静默假死，量级必须压到真人水平：时刻一过
        或会话未存活直到关窗，当天直接放弃，绝不补打。
        """
        if self._mx_fallback_at is None or self._mx_fallback_done:
            return
        now = datetime.now(CN_TZ)
        if now < self._mx_fallback_at:
            return
        if not self._mx_in_window():
            self._mx_fallback_done = True
            logger.info("MX 每日兜底拉取放弃：预约时刻后会话未存活（运行时段已结束）")
            return
        if self._mx_token_expired or not self._mx_session_active():
            # 会话还没起来（或 TOKEN 刚过期）：等下一个 30s tick，直到窗口结束
            return
        self._mx_fallback_done = True
        logger.info(
            "MX 每日兜底拉取开始（预约 %s）", self._mx_fallback_at.strftime("%H:%M:%S")
        )
        await self._mx_fallback_pull_once()

    async def _mx_maybe_nightly_force_close(self):
        """晚间兜底断开：23:30-23:55 之间随机一秒，MX 若仍在线一律强制断开。

        晚间窗口关窗（23:30-23:55 随机）与这条兜底同区间，先到者关窗——强关
        先到时必须同时 disarm 当前窗口，否则窗口循环看到「窗口内 + 未开窗 +
        已武装」会在下个 tick 把会话重新拉起直到关窗。这条额外兜住「关窗后
        手动登录忘关」等场景，无论会话来源（自动/手动）到点即关，当天只执行一次。
        """
        if self._mx_force_close_at is None or self._mx_force_close_done:
            return
        now = datetime.now(CN_TZ)
        if now < self._mx_force_close_at:
            return
        # 取当前窗口下标可能触发当日窗口的首次生成（生成过程会复位各当日闩锁），
        # 因此必须先取下标、再置「今天已强关」标记，避免生成把标记冲掉
        idx = self._mx_current_window_index()
        self._mx_force_close_done = True
        if not (self._mx_window_open or self._mx_session_active()):
            logger.info("MX 晚间兜底检查：会话未在线，无需断开")
            return
        logger.info(
            "MX 晚间兜底断开触发（预约 %s）：强制断开仍在运行的会话",
            self._mx_force_close_at.strftime("%H:%M:%S"),
        )
        self._mx_window_open = False
        await self._mx_session_stop()
        # disarm 当前窗口（若强关时仍在窗口内）：先于窗口关窗到达时防止重拉
        if idx is not None:
            self._mx_armed[idx] = False
        await asyncio.to_thread(
            self._mx_log_auto_event,
            "mx_auto_disconnect",
            f"晚间兜底检查（预约 {self._mx_force_close_at:%H:%M:%S}）："
            "系统自动执行 MX 平台断开（防止登录后未断开）",
        )

    async def _mx_maybe_session_timeout(self):
        """会话最长时长滚动兜底：在线持续超过 _MX_MAX_SESSION_HOURS 小时强制断开。

        晚间强关只覆盖 23:30-23:55，之后手动登录的会话可能整夜在线，这里按
        最近一次会话启动时刻（自动/手动统一在 mx_ws_control("connect") 记录）
        滚动兜底。超时强断同样 disarm 当前窗口，避免窗口循环立刻重拉；
        会话来源不限（自动开窗/管理员手动登录一视同仁），只断当前这一个会话，
        之后新发起的会话从新的启动时刻重新计时。
        """
        if self._mx_session_started_at is None or not self._mx_session_active():
            return
        held = datetime.now(CN_TZ) - self._mx_session_started_at
        if held < timedelta(hours=self._MX_MAX_SESSION_HOURS):
            return
        logger.warning(
            "MX 会话已持续超过 %s 小时，滚动兜底强制断开", self._MX_MAX_SESSION_HOURS
        )
        idx = self._mx_current_window_index()
        if idx is not None:
            self._mx_armed[idx] = False
        self._mx_window_open = False
        await self._mx_session_stop()
        # mx_ws_control("disconnect") 内部会清启动时刻；这里显式再清一次，
        # 防止断开链路异常时兜底被反复触发
        self._mx_session_started_at = None
        await asyncio.to_thread(
            self._mx_log_auto_event,
            "mx_auto_disconnect",
            f"会话持续超过 {self._MX_MAX_SESSION_HOURS} 小时，"
            "系统自动执行 MX 平台断开（超时兜底）",
        )

    async def _mx_fallback_pull_once(self):
        """随机拉 1 个启用房间的最新消息（含有限追平），入库并推送。"""
        fetcher = self.fetchers.get("mx")
        if fetcher is None:
            return
        kols = [k for k in self.db.list_kols(platform="mx") if k.get("enabled")]
        if not kols:
            return
        kol = random.choice(kols)

        def _pull():
            posts = fetcher.fetch(kol) or []
            # 只给新帖打标：已入库的旧帖重打是白算（入库去重也存不进去）
            known = self.db.existing_post_keys([("mx", p.external_id) for p in posts])
            saved = 0
            for post in posts:
                if ("mx", post.external_id) not in known:
                    # 与 WS 实时同口径：入库前先走本地规则打标，LLM 打标后整体替换
                    self._apply_mx_rule_tags(post)
                if self.ingest_external_post(post) is not None:
                    saved += 1
            return len(posts), saved

        try:
            total, saved = await asyncio.to_thread(_pull)
            logger.info(
                "MX 兜底拉取 room=%s(%s)：%d 条，新增 %d",
                kol["name"], kol["external_id"], total, saved,
            )
        except MXTokenExpiredError:
            logger.error("MX 兜底拉取发现 TOKEN 过期", exc_info=True)
            await asyncio.to_thread(
                self.publish_mx_error,
                "token_expired",
                "MX TOKEN 已过期",
                "⚠️ MX TOKEN 已过期，兜底拉取失败，MX 已暂停拉取与实时推送。"
                "\n请到后台「数据源 → MX」更换 TOKEN（TOKEN 需每 2 天更换一次）。",
            )
        except Exception as exc:
            logger.warning(
                "MX 兜底拉取失败 room=%s: %s", kol.get("external_id"), exc, exc_info=True
            )
            await asyncio.to_thread(
                self.publish_mx_error,
                "fallback_pull",
                "MX 兜底拉取失败",
                f"⚠️ MX 兜底拉取房间 {kol.get('name')}（{kol.get('external_id')}）失败：{exc}",
            )

    def _mx_check_token_age(self):
        """TOKEN 时效检查：超过 2 天未更换 → 系统 KOL 提醒手动更换（每轮一次）。"""
        now_ts = int(time.time())
        try:
            updated = int(self.db.get_setting("mx_token_updated_at") or 0)
        except (TypeError, ValueError):
            updated = 0
        if not updated:
            # 首次运行：以当前时间作为 TOKEN 起用时间
            self.db.set_setting("mx_token_updated_at", str(now_ts))
            return
        if now_ts - updated < 2 * 86400:
            return
        if not _cooldown_ok(self.db, "mx_token_reminder", 2 * 86400):
            return
        days = max(1, (now_ts - updated) // 86400)
        self._publish_system_alert_sync(
            "MX TOKEN 已超过 2 天，请更换",
            f"⚠️ MX TOKEN 已使用约 {days} 天，按风控对策必须每 2 天更换一次。"
            "\n请到后台「数据源 → MX」更新 TOKEN；更换后自动恢复拉取与实时推送。",
        )

    async def _send_startup_message(self):
        """启动提示只推送给管理员（走管理员各自绑定的渠道），普通用户不推送。"""
        if self.notifiers_config is None:
            return
        import httpx

        from .channels import build_channel_notifier, iter_user_channels

        message = format_startup_message()
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
            # 房间同步改为开窗触发（见 _mx_session_start），与官方网页端
            # 「打开网页必拉一次房间列表」的行为一致，不再有后台周期任务
            self._mx_sync_service = MXRoomSyncService(self.mx_config, self.db)

            if "mx" in self.fetchers:
                mx_fetcher = self.fetchers["mx"]
                global _mx_fetcher
                _mx_fetcher = mx_fetcher  # 供 get_mx_ws_status 读取连接状态

                async def on_mx_message(post: Post):
                    """处理 MX 实时消息，直接推送。"""
                    try:
                        # 把数据库操作放在单独线程中，避免事务冲突
                        def _save_and_notify():
                            # 停用房间不入库不推送：以数据库实时状态为准（房间缓存有
                            # TTL），停用立即生效，与轮询平台「停用即不抓取」口径一致
                            kol_row = self.db.get_kol(post.kol_id) or {}
                            if not kol_row.get("enabled", True):
                                logger.info(
                                    "MX 房间已停用，实时消息不处理 platform=%s kol=%s id=%s",
                                    post.platform, post.kol_name, post.external_id,
                                )
                                return
                            # 入库前先走本地规则打标（消息即时带标签），LLM 打标
                            # 完成后由打标循环整体替换
                            self._apply_mx_rule_tags(post)
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

                async def on_ws_give_up(reason: str, token_expired: bool = False):
                    """WS 永久放弃自动重连：置状态标记并用系统账号发布告警。"""
                    self._mx_ws_gave_up = True
                    if token_expired:
                        self._mx_trigger_token_expired()
                        await self._publish_system_alert(
                            "MX TOKEN 已过期",
                            "⚠️ MX TOKEN 已过期或无效，WebSocket 连接被拒，已停止重试。"
                            "\n请到后台「数据源 → MX」更换 TOKEN（TOKEN 需每 2 天更换一次），"
                            "更换后自动恢复。",
                        )
                    else:
                        await self._publish_system_alert(
                            "MX WebSocket 自动重连失败",
                            "⚠️ MX WebSocket 断线后自动重连失败，已停止自动重连，"
                            "消息暂停实时更新。\n"
                            f"失败原因：{reason or '未知'}\n"
                            "请到后台「数据源 → MX」手动接入，或检查 MX 账号/网络状态。",
                        )

                self._mx_ws_on_message = on_mx_message
                self._mx_ws_on_give_up = on_ws_give_up

            # 启动每日窗口管理：WS 会话与兜底拉取的启停全部由窗口驱动，
            # 不再服务一启动就常驻在线
            if self._mx_window_task is None or self._mx_window_task.done():
                self._mx_window_task = asyncio.create_task(self._mx_window_loop())

            logger.info("MX platform initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MX platform: {e}", exc_info=True)

    async def _stop_mx(self):
        """停止 MX 房间同步、窗口管理与 WebSocket，并移除 mx 抓取器（禁用/重配时调用）。"""
        global _mx_fetcher
        if self._mx_ws_task:
            self._mx_ws_task.cancel()
            self._mx_ws_task = None
        if self._mx_window_task:
            self._mx_window_task.cancel()
            self._mx_window_task = None
        self._mx_window_open = False
        self._mx_ws_gave_up = False
        # WS 任务已被取消：清掉会话启动时刻，超时兜底不再基于旧会话计时
        self._mx_session_started_at = None
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
            client = getattr(mx_fetcher, "mx_client", None)
            if client is not None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001 - 尽力关闭即可
                    logger.warning("关闭 MX HTTP 会话失败", exc_info=True)

    async def mx_manual_login(self) -> dict:
        """后台「登录」按钮：像真人打开网页一样执行启动序列 + 房间同步 + 连接 WS。

        不受每日窗口限制（管理员明确点击，与手动拉取历史同一定位）；逐接口
        结果写入模块级 _mx_login_report 供前端「接口状态」展示；TOKEN 过期即
        熔断并计入报告。熔断态下允许「半开重探」：先解除熔断再走完整登录，
        登录中再遇鉴权失败会重新熔断（告警仍走 30 分钟节流）。
        """
        global _mx_login_report
        self._mx_touch_loop()
        steps: list[dict] = []

        def record(name: str, ok: bool, detail: str):
            steps.append({"name": name, "ok": ok, "detail": str(detail)[:100]})

        if not (MX_AVAILABLE and self.mx_config and self.mx_config.enabled):
            record("前置检查", False, "MX 平台未启用")
        elif not self.mx_config.token:
            record("前置检查", False, "未配置 API TOKEN")
        else:
            if self._mx_token_expired:
                # 半开重探：管理员手动点「登录」视为对 TOKEN 的主动复核，先清熔断
                # 标记再走完整登录；若仍鉴权失败会在下方 boot/sync 链路重新熔断
                self._mx_token_expired = False
                logger.info("MX 手动登录：TOKEN 熔断态下半开重探，重新执行完整登录")
            service = self._mx_sync_service
            temp = None
            if service is None:
                temp = MXRoomSyncService(self.mx_config, self.db)
                service = temp
            # 窗口内的手动登录尝试：无论成败都记「本窗口已尝试」，部分失败时
            # 窗口循环不得在下个 30s tick 自动重跑完整启动序列
            window_idx = self._mx_current_window_index()
            if window_idx is not None:
                self._mx_manual_attempted_idx = window_idx
            try:
                try:
                    steps.extend(await asyncio.to_thread(service.boot_sequence))
                except MXTokenExpiredError:
                    self._mx_trigger_token_expired()  # boot 报告里已含失败步骤
                except Exception as exc:  # noqa: BLE001 - 启动序列异常不能炸掉登录接口
                    logger.error("MX 启动序列异常: %s", exc, exc_info=True)
                    record("启动序列", False, str(exc)[:100])
                else:
                    try:
                        count = await service.sync_rooms()
                        record("room/list", True, f"{count} 个房间")
                    except MXTokenExpiredError:
                        self._mx_trigger_token_expired()
                        record("room/list", False, "TOKEN 已过期/无效")
                    except Exception as exc:
                        record("room/list", False, str(exc)[:100])
            finally:
                if temp is not None:
                    temp.stop()
            if self._mx_token_expired:
                record("websocket", False, "TOKEN 已熔断，跳过连接")
            elif self.mx_config.ws_enabled:
                try:
                    record("websocket", True, await self.mx_ws_control("connect"))
                except Exception as exc:
                    record("websocket", False, str(exc)[:100])
            else:
                record("websocket", True, "ws_enabled=false，跳过实时推送")
            if steps and all(s["ok"] for s in steps) and self._mx_in_window():
                # 窗口内的手动登录视为本窗口会话已开启，避免窗口循环重复拉起
                self._mx_window_open = True

        report = {
            "time": datetime.now(CN_TZ).strftime("%H:%M:%S"),
            "ok": bool(steps) and all(s["ok"] for s in steps),
            "steps": steps,
            "source": "manual",
        }
        _mx_login_report = report
        return report

    async def mx_ws_control(self, action: str, source: str = "manual") -> str:
        """控制 MX WebSocket（connect 接入 / disconnect 断开），返回提示消息。

        source 标记真实触发者：manual=管理员在后台点击（按钮/接口），auto=系统
        运行时段到点自动登录/断开。日志必须按来源如实记录，不得把系统自动动作记成手动。
        与 _stop_mx 不同：断开保留 mx 抓取器与房间同步，只停 WS 监听任务，
        以便随后可重新接入。
        """
        source_label = "系统自动" if source == "auto" else "管理员手动"
        if action == "disconnect":
            if self._mx_ws_task:
                self._mx_ws_task.cancel()
                self._mx_ws_task = None
            # 会话已结束：清掉启动时刻，超时兜底从下次连接重新计时
            self._mx_session_started_at = None
            fetcher = self.fetchers.get("mx")
            if fetcher is None:
                raise RuntimeError("MX 平台未启用")
            try:
                reason = (
                    "运行时段结束，系统自动断开" if source == "auto" else "已由管理员手动断开"
                )
                await fetcher.stop_ws(reason=reason)
            except Exception as exc:  # noqa: BLE001 - 尽力断开，失败时给出可读错误
                logger.warning("主动断开 MX WebSocket 失败", exc_info=True)
                raise RuntimeError("断开 WebSocket 失败，请查看服务端日志") from exc
            logger.info("MX WebSocket 已断开（%s）", source_label)
            return "已断开 MX WebSocket 连接"
        if action == "connect":
            if not (MX_AVAILABLE and self.mx_config and self.mx_config.enabled):
                raise RuntimeError("MX 平台未启用")
            if not self.mx_config.ws_enabled:
                raise RuntimeError("实时推送未启用（ws_enabled=false），请先在配置中启用")
            if "mx" not in self.fetchers:
                raise RuntimeError("MX 抓取器未初始化")
            if self._mx_ws_task and not self._mx_ws_task.done():
                return "MX WebSocket 已在运行"
            if self._mx_ws_on_message is None:
                raise RuntimeError("MX 消息回调未初始化，请重启服务后重试")
            mx_fetcher = self.fetchers["mx"]
            global _mx_fetcher
            _mx_fetcher = mx_fetcher  # 供 get_mx_ws_status 读取连接状态
            self._mx_ws_task = asyncio.create_task(
                mx_fetcher.start_ws(
                    self._mx_ws_on_message, on_ws_give_up=self._mx_ws_on_give_up
                )
            )
            # 会话启动时刻（自动/手动唯一共同入口，超时兜底据此计时）；
            # 「已在运行」的早退分支不刷新，保证时刻对应当前存活会话的真实起点
            self._mx_session_started_at = datetime.now(CN_TZ)
            logger.info("MX WebSocket 已发起连接（%s）", source_label)
            return "已发起 MX WebSocket 连接"
        raise RuntimeError(f"未知操作：{action}")

    async def apply_mx_config(self, mx_config) -> None:
        """MX 配置变更后热应用：停掉旧任务，按需重建抓取器并重启同步/窗口管理。"""
        old_token = self.mx_config.token if self.mx_config else ""
        await self._stop_mx()
        self.mx_config = mx_config
        # 保存配置即复位熔断/放弃标记（无论 token 是否变化）：管理员主动保存视为
        # 一次人工确认，避免误熔断后「原样重存也解不开、只能重启进程」
        self._mx_token_expired = False
        self._mx_ws_gave_up = False
        if not (MX_AVAILABLE and mx_config and mx_config.enabled):
            logger.info("MX platform disabled, hot-reload skipped")
            return
        from .fetchers.mx.fetcher import MxFetcher

        self.fetchers["mx"] = MxFetcher(mx_config, self.db)
        if (mx_config.token or "") != (old_token or ""):
            # TOKEN 更换：重置 2 天时效计时（仅 token 实际变化才刷新更新时间）
            self.db.set_setting("mx_token_updated_at", str(int(time.time())))
            logger.info("MX TOKEN 已更换，重置时效计时")
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

        # MX LLM 打标自动循环：常驻运行，每轮现读配置——开关关闭/未在配置的
        # 时间段内时自行空转，改配置无需重启
        self._mx_tag_task = asyncio.create_task(
            mx_llm_tag_auto_loop(
                self.db,
                lambda: _system_llm_config(self.db, self.llm_config),
                publish_alert=self._publish_system_alert_sync,
            )
        )

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
            try:
                await asyncio.to_thread(self._submit_news_due)
            except Exception:  # noqa: BLE001
                logger.exception("财经新闻调度异常")
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
                    # next_run_at 为空说明从未排期（老数据或无有效调度日）：
                    # 先补算下次运行时间，不立即触发
                    if not task.get("next_run_at"):
                        next_run = ai_analysis.calculate_next_run(task, now)
                        if next_run:
                            self.db.update_ai_task(task_id, next_run_at=next_run.isoformat())
                        continue
                    # 检查是否已在运行（手动「立即运行」端点共用同一互斥，占用必须同步完成，
                    # 避免 create_task 尚未执行时下一轮循环再次命中同一任务）
                    if not try_begin_ai_task_run(task_id):
                        continue
                    # 初始化信号量（懒加载）
                    global _ai_task_semaphore
                    if _ai_task_semaphore is None:
                        _ai_task_semaphore = asyncio.Semaphore(_ai_task_max_concurrent)

                    # 异步运行任务（互斥已在上面占用，wrapper 只负责收尾释放）
                    async def run_task_wrapper(tid):
                        try:
                            async with _ai_task_semaphore:
                                result = await asyncio.to_thread(
                                    ai_analysis.run_analysis_task, tid, self.db
                                )
                            # 自动重试仍失败：任务已被停用，经「系统通知」告知管理员
                            if isinstance(result, dict) and result.get("retries_exhausted"):
                                await self._alert_ai_task_stopped(
                                    tid, str(result.get("message") or "")
                                )
                        finally:
                            end_ai_task_run(tid)

                    # 在事件循环中运行
                    asyncio.create_task(run_task_wrapper(task_id))
            except Exception:  # noqa: BLE001
                logger.exception("AI分析任务检查异常")

            # --- MX 观点快照检查（每 20 秒） ---
            if now_mono - self._last_mx_view_check >= 20:
                self._last_mx_view_check = now_mono
                # 批次内含 LLM 调用（超时上限分钟级）：后台单飞执行，
                # 内联 await 会卡住调度主循环，延误重试/保活/备份等任务
                if not self._mx_view_check_running:
                    self._mx_view_check_running = True

                    async def _mx_view_tick() -> None:
                        try:
                            await asyncio.to_thread(self._mx_view_check_tick)
                        except Exception:  # noqa: BLE001
                            logger.exception("MX 观点快照检查异常")
                        finally:
                            self._mx_view_check_running = False

                    asyncio.create_task(_mx_view_tick())

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
            if now_mono - self._last_cicc_alert_check >= CICC_ALERT_CHECK_INTERVAL:
                self._last_cicc_alert_check = now_mono
                try:
                    from .cicc_alerts import maybe_check_cicc

                    await asyncio.to_thread(
                        maybe_check_cicc, self.db, self.notifiers, self.notifiers_config
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("中金存储告警异常")
            if now_mono - self._last_knowledge_notify >= 60:
                self._last_knowledge_notify = now_mono
                try:
                    from .knowledge_notify import maybe_notify_knowledge_keywords

                    await asyncio.to_thread(
                        maybe_notify_knowledge_keywords, self.db, self.notifiers_config
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("研报关键词提醒异常")
            if now_mono - self._last_proxy_tick >= PROXY_TICK_INTERVAL:
                self._last_proxy_tick = now_mono
                try:
                    await asyncio.to_thread(tick_proxy_pools, self.db)
                except Exception:  # noqa: BLE001
                    logger.exception("代理池刷新异常")
            if now_mono - self._last_imgbed >= 20:
                self._last_imgbed = now_mono
                try:
                    from . import imgbed

                    await asyncio.to_thread(imgbed.process_pending, self.db)
                except Exception:  # noqa: BLE001
                    logger.exception("图床镜像异常")
            if now_mono - self._last_truth_backfill >= 60:
                self._last_truth_backfill = now_mono
                try:
                    if _polling_bool(self.db, "config_translate_twitter_content", False):
                        await asyncio.to_thread(backfill_truth_translations, self.db)
                except Exception:  # noqa: BLE001
                    logger.exception("Truth 翻译回填异常")
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
            # 研报结构化抽取（每小时一批，LLM 离线批处理；失败不影响主流程）
            if now_mono - self._last_report_extract > 3600:
                self._last_report_extract = now_mono
                try:
                    done = await asyncio.to_thread(self._run_report_extraction_task)
                    if done:
                        logger.info("研报结构化抽取本轮完成 %d 篇", done)
                except Exception:  # noqa: BLE001
                    logger.exception("研报结构化抽取异常")

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
                if retention > 0:
                    try:
                        removed_news = await asyncio.to_thread(
                            self.db.delete_news_articles_older_than, retention
                        )
                        if removed_news:
                            logger.info("清理过期财经新闻 %d 条（保留 %d 天）", removed_news, retention)
                    except Exception:  # noqa: BLE001
                        logger.exception("财经新闻清理失败")
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
            if is_permanent_push_error(row.get("error") or ""):
                # 卡片超限等内容性错误永不成功，重启不再复活重试
                continue
            post_row = self.db.get_post(row["post_id"])
            if post_row is None:
                continue
            if post_row.get("hidden") or post_row.get("blocked"):
                # 入库后管理员隐藏/关键词拦截的帖：重试不再外推
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
                if is_permanent_push_error(exc):
                    # 卡片超限等内容性错误重发必败，立即放弃，不再退避空转刷日志
                    self.retry_queue.drop(item)
                else:
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
                        if not is_permanent_push_error(exc):
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

    def _run_report_extraction_task(self) -> int:
        """研报结构化抽取：每小时一批，读 txt → LLM → 结构化落库。

        开关与预算都在 settings：report_extract_enabled（默认开，='0' 关）、
        report_extract_model（默认 gemini-3.8-flash-high）、
        report_extract_daily_limit（默认 1000 篇/天）。LLM 用站点配置
        （管理员个人 Grok/Gemini 网关），批处理不走实时路径。
        """
        db = self.db
        if db.get_setting("report_extract_enabled") == "0":
            return 0
        daily_limit = int(db.get_setting("report_extract_daily_limit") or 1000)
        today = time.strftime("%Y%m%d")
        done_key = f"report_extract_done_{today}"
        done_today = int(db.get_setting(done_key) or 0)
        if done_today >= daily_limit:
            return 0
        site_llm = _system_llm_config(db, self.llm_config)
        if site_llm is None:
            return 0
        model = db.get_setting("report_extract_model") or "gemini-3.8-flash-high"
        # 默认圈定研报类知识库（投行/中金/SemiAnalysis/外行），排除飞书短讯类
        groups = [
            g.strip()
            for g in (
                db.get_setting("report_extract_groups")
                or "7479082602225992,local-cicc-research,7476629605476515,legacy"
            ).split(",")
            if g.strip()
        ]
        from .llm import extract_report_structure
        from .report_text import pdf_first_pages_text as _pdf_first_pages_text
        from .stock_universe import bundled_universe_codes

        universe = bundled_universe_codes()
        resolve = self.ima_archive_file
        if resolve is None:
            return 0
        pipeline_version = "2"
        version_key = "report_extract_pipeline_version"
        if db.get_setting(version_key) != pipeline_version:
            reset = db.reset_report_extractions(("failed", "notext", "empty", "nofile"))
            db.set_setting(version_key, pipeline_version)
            if reset:
                logger.info("研报结构化抽取：重新排队可恢复结果 %d 篇", reset)
        batch = min(80, daily_limit - done_today)
        docs = db.pending_report_extractions(limit=batch, group_ids=groups or None)
        if not docs:
            return 0
        import hashlib

        completed = 0
        unresolved = 0
        for doc in docs:
            group_id = str(doc["group_id"] or "")
            media_id = str(doc["media_id"] or "")
            # txt 优先；txt 缺失（如中金/投行库只有 PDF）走 pymupdf 前几页兜底
            has_txt = bool(doc["txt_path"])
            txt_path = resolve(doc["txt_path"]) if has_txt else None
            pdf_path = resolve(doc["pdf_path"]) if doc["pdf_path"] else None
            if has_txt and txt_path is None:
                # 应存在的 txt 路径解析失败，可能是存储机暂时不可读：不落行，下轮重试
                unresolved += 1
                continue
            text = ""
            try:
                if txt_path is not None and txt_path.is_file():
                    text = txt_path.read_text(encoding="utf-8", errors="replace")
                elif pdf_path is not None and pdf_path.is_file():
                    text = _pdf_first_pages_text(pdf_path)
            except (OSError, ValueError):
                text = ""
            if not text.strip():
                # txt 与 pdf 都取不到文本：落行防重试（修复文本源后可重置重抽）
                db.save_report_extraction(group_id, media_id, status="notext")
                continue
            txt_hash = hashlib.sha256(text[:20000].encode("utf-8", "ignore")).hexdigest()[:16]
            try:
                result = extract_report_structure(text, site_llm, model=model, universe=universe)
            except Exception as exc:
                logger.warning("研报抽取失败 %s/%s: %s", group_id, media_id, exc)
                db.save_report_extraction(
                    group_id, media_id, txt_hash=txt_hash, model=model, status="failed"
                )
                continue
            db.save_report_extraction(
                group_id,
                media_id,
                txt_hash=txt_hash,
                report_kind=result.get("report_kind", ""),
                rating=result.get("rating", ""),
                target_price=result.get("target_price", ""),
                thesis=result.get("thesis", ""),
                tickers=result.get("tickers", []),
                model=model,
                status=result.get("status", "ok"),
            )
            completed += 1
        if unresolved and unresolved == len(docs):
            logger.warning("研报抽取：%d 篇路径均不可解析，疑似知识库存储不可读，本批跳过", unresolved)
            return 0
        if completed:
            db.set_setting(done_key, str(done_today + completed))
            logger.info("研报结构化抽取：%d 篇（今日累计 %d/%d）", completed, done_today + completed, daily_limit)
        return completed

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
        # 精选窗口按北京时间零点起算（用户时区）；与 published_at 同为北京钟面文本，
        # list_daily_posts 里直接字典序比较
        since = (
            datetime.now(CN_TZ)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .strftime("%Y-%m-%d %H:%M")
        )

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
