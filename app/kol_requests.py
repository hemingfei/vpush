"""Shared KOL request validation, approval and notifications."""
from __future__ import annotations

import logging
import os
import re

from .avatar_cache import cache_avatar
from .db import DB, user_plain_secret
from .fetchers.base import PLATFORM_LABELS
from .fetchers.combination import resolve_combination_profile
from .fetchers.twitter import resolve_x_profile
from .fetchers.weibo import WEIBO_COOKIE_KEY, resolve_weibo_profile
from .fetchers.xueqiu import XUEQIU_COOKIE_KEY, resolve_profile
from .fetchers.zsxq import resolve_zsxq_profile

logger = logging.getLogger(__name__)


class KolRequestError(ValueError):
    """The request cannot be approved with the supplied input."""


class KolRequestNotFound(KolRequestError):
    """The request does not exist or has already been handled."""


# ---- 大V申请输入甄别与归一化（过滤无效信息 + 平台纠错提示） ----
# X 的系统页面路径（用户主页链接不会以这些开头）
_TWITTER_SYSTEM_PATHS = {"home", "explore", "search", "settings", "notifications",
                         "messages", "compose", "bookmarks", "jobs", "login", "signup",
                         "account", "i"}


def detect_platform_from_link(text: str) -> str | None:
    """从链接粗判所属平台；雪球组合链接优先于雪球用户链接。"""
    if re.search(r"(?:xueqiu\.com/P/|ZH\d)", text):
        return "combination"
    if "xueqiu.com" in text:
        return "xueqiu"
    if re.search(r"weibo\.(com|cn)", text):
        return "weibo"
    if re.search(r"(?:^|[/:.])x\.com|twitter\.com", text):
        return "twitter"
    if "ima.qq.com" in text:
        return "ima"
    if re.search(r"(?:wx\.)?zsxq\.com", text):
        return "zsxq"
    if re.search(r"(?:^|[/:.])truthsocial\.com", text):
        return "truth"
    return None


def normalize_kol_request_input(platform: str, raw: str) -> tuple[str, str | None]:
    """校验并归一化用户的大V申请输入。

    返回 (external_id, error)：error 非空时申请无效（external_id 为空）。
    链接能识别出平台但与所选平台不符时，返回纠错提示让用户切换平台。
    """
    text = (raw or "").strip()
    if not text:
        return "", "请输入大V主页链接或 ID"
    detected = detect_platform_from_link(text)
    if detected is not None and detected != platform:
        return "", (
            f"检测到这是「{PLATFORM_LABELS[detected]}」的主页链接，"
            f"请把平台切换为「{PLATFORM_LABELS[detected]}」（当前选的是「{PLATFORM_LABELS[platform]}」）"
        )
    if platform == "xueqiu":
        m = re.search(r"xueqiu\.com/(?:u/)?(\d+)", text)
        if m:
            return m.group(1), None
        if text.isdigit():
            return text, None
        return "", "无法识别的雪球主页链接，请使用 xueqiu.com/u/<数字ID> 形式（或直接填数字 ID）"
    if platform == "combination":
        m = re.search(r"(?:xueqiu\.com/P/)?(ZH\d+)", text)
        if m:
            return m.group(1), None
        return "", "无法识别的雪球组合链接，请使用 xueqiu.com/P/ZHxxxxxx 或组合代码 ZHxxxxxx"
    if platform == "weibo":
        m = re.search(r"(?:weibo\.com|m\.weibo\.cn)/u/(\d+)", text)
        if m:
            return m.group(1), None
        if text.isdigit():
            return text, None
        return "", "无法识别的微博主页链接，请复制对方主页「.../u/<数字UID>」形式的链接"
    if platform == "ima":
        if "ima.qq.com" in text:
            m = re.search(r"knowledgeBaseId=([0-9A-Za-z_-]+)", text)
            if m:
                return m.group(1), None
        if re.fullmatch(r"[0-9A-Za-z_-]{6,64}", text):
            return text, None
        return "", "无法识别的 ima 知识库链接，请使用 wiki URL 里的 knowledgeBaseId（或直接填知识库 ID）"
    if platform == "zsxq":
        m = re.search(r"(?:group/|group_id=)(\d{6,})", text)
        if m:
            return m.group(1), None
        if text.isdigit():
            return text, None
        return "", "无法识别的知识星球链接，请使用 wx.zsxq.com 群链接或星球 ID"
    if platform == "twitter":
        m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)", text)
        if m:
            path = m.group(1)
            if re.search(r"/status/|/i(?:/|$)", text) or path in _TWITTER_SYSTEM_PATHS:
                return "", "这是 X 的系统页面/推文链接，请复制用户主页链接（x.com/<用户名>）"
            return path, None
        if re.fullmatch(r"@?[A-Za-z0-9_]{1,15}", text):
            return text.lstrip("@"), None
        return "", "无法识别的 X 用户名，请使用 x.com/<用户名> 链接或 @用户名"
    return "", f"不支持的平台: {platform}"


def approve_kol_request(
    db: DB,
    request_id: int,
    admin: dict,
    notifiers_config=None,
    category_id: int | None = None,
) -> dict | None:
    """审批通过大V申请（HTTP 端点与 TG 审批按钮共用）。"""
    req = db.get_kol_request(request_id)
    if req is None or req["status"] != "pending":
        raise KolRequestNotFound("申请不存在或已处理")
    # 兜底：旧申请可能未经新校验入库（昵称/垃圾文本），审批前再验一次，
    # 避免上架无法抓取的坏大V（如雪球昵称而非数字 ID）
    normalized, err = normalize_kol_request_input(req["platform"], req["external_id"])
    stored = req["external_id"]
    if req["platform"] == "twitter":
        stored = stored.lstrip("@")  # 旧代码未归一化，@用户名 会原样入库
    if err or normalized != stored:
        raise KolRequestError(
            f"该申请的外部ID「{req['external_id']}」无效（{err or '格式不符'}），建议点「拒绝」",
        )
    name = (req["name"] or "").strip()
    avatar_url = ""
    # 申请通常只填了主页链接，审批时自动补昵称与头像，避免上架占位名
    if req["platform"] == "xueqiu":
        profile = resolve_profile(
            req["external_id"],
            db.get_setting(XUEQIU_COOKIE_KEY) or os.environ.get("XUEQIU_COOKIE", ""),
            db=db,
        )
        name = name or profile.get("screen_name") or ""
        avatar_url = profile.get("avatar_url") or ""
    elif req["platform"] == "combination":
        profile = resolve_combination_profile(
            req["external_id"],
            db.get_setting(XUEQIU_COOKIE_KEY) or os.environ.get("XUEQIU_COOKIE", ""),
            db=db,
        )
        name = name or profile.get("name") or ""
        avatar_url = profile.get("avatar_url") or ""
    elif req["platform"] == "weibo":
        profile = resolve_weibo_profile(
            req["external_id"],
            db.get_setting(WEIBO_COOKIE_KEY) or os.environ.get("WEIBO_COOKIE", ""),
            db=db,
        )
        name = name or profile.get("name") or ""
        avatar_url = profile.get("avatar_url") or ""
    elif req["platform"] == "twitter":
        profile = resolve_x_profile(req["external_id"], db=db)
        name = name or profile.get("name") or ""
        avatar_url = profile.get("avatar_url") or ""
    elif req["platform"] == "zsxq":
        profile = resolve_zsxq_profile(req["external_id"], db=db)
        name = name or profile.get("name") or ""
        avatar_url = profile.get("avatar_url") or ""
    name = name or f"{req['platform']}_{req['external_id']}"
    if category_id is None:
        category_id = req.get("category_id")
    if category_id is not None and db.get_category(category_id) is None:
        raise KolRequestError("分类不存在")
    try:
        kid = db.add_kol(req["platform"], name, req["external_id"], category_id=category_id)
        if avatar_url:
            db.update_kol_avatar(kid, cache_avatar(db, kid, avatar_url))
    except ValueError as exc:
        raise KolRequestError(str(exc)) from None
    db.set_kol_request_status(request_id, "approved")
    db.log_admin_action(admin["id"], "approve_kol_request", str(request_id), f"{name} {req['external_id']}")
    try:
        db.add_subscription(req["user_id"], kid)
    except Exception:  # noqa: BLE001 - 自动订阅失败不阻塞审批
        logger.warning("审批后自动订阅失败 request=%s", request_id, exc_info=True)
    if notifiers_config is not None:
        from .channels import channel_bound
        from .notifiers.feishu import FeishuNotifier
        from .notifiers.telegram import TelegramNotifier
        from .notifiers.wecom import WeComNotifier

        requester = db.get_user(req["user_id"])
        message = f"✅ 你申请的大V「{name}」已通过审批，已自动为你订阅"
        if requester and requester["telegram_chat_id"] and notifiers_config.telegram.bot_token:
            notifier = None
            try:
                notifier = TelegramNotifier(
                    notifiers_config.telegram,
                    chat_id=requester["telegram_chat_id"],
                    bot_token=requester.get("telegram_bot_token") or None,
                )
                notifier.send_text(message)
            except Exception:  # noqa: BLE001
                logger.warning("审批通知 TG 发送失败 user=%s", requester["username"], exc_info=True)
            finally:
                if notifier is not None:
                    notifier.client.close()
        if requester and channel_bound(requester, "feishu", notifiers_config, db):
            from .feishu_personal import build_personal_feishu_kwargs

            notifier = None
            try:
                kwargs = build_personal_feishu_kwargs(db, notifiers_config.feishu, requester)
                notifier = FeishuNotifier(
                    notifiers_config.feishu,
                    open_id=kwargs["open_id"],
                    chat_id=kwargs["chat_id"],
                    app_id=kwargs["app_id"],
                    app_secret=kwargs["app_secret"],
                )
                notifier.send_text(message)
            except Exception:  # noqa: BLE001
                logger.warning("审批通知飞书发送失败 user=%s", requester["username"], exc_info=True)
            finally:
                if notifier is not None:
                    notifier.client.close()
        if requester and requester.get("wecom_webhook"):
            notifier = None
            try:
                notifier = WeComNotifier(
                    notifiers_config.wecom,
                    webhook_url=user_plain_secret(requester, "wecom_webhook", db),
                )
                notifier.send_text(message)
            except Exception:  # noqa: BLE001
                logger.warning("审批通知企业微信发送失败 user=%s", requester["username"], exc_info=True)
            finally:
                if notifier is not None:
                    notifier.client.close()
    return db.get_kol(kid)


def reject_kol_request(db: DB, request_id: int, admin: dict) -> None:
    """拒绝大V申请（HTTP 端点与 TG 审批按钮共用）。"""
    req = db.get_kol_request(request_id)
    if req is None or req["status"] != "pending":
        raise KolRequestNotFound("申请不存在或已处理")
    db.set_kol_request_status(request_id, "rejected")
    db.log_admin_action(admin["id"], "reject_kol_request", str(request_id), req["external_id"])
