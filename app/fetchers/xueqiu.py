"""雪球用户原创动态抓取。"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import httpx

from .. import xq_identity
from ..avatar_cache import cache_avatar
from .base import (
    Fetcher,
    Post,
    ThreadLocalClient,
    catchup_pages,
    format_published_at,
    strip_html,
)

logger = logging.getLogger(__name__)

XUEQIU_COOKIE_KEY = "xueqiu_cookie"
XUEQIU_COOKIE_TIME_KEY = "xueqiu_cookie_updated_at"
# App 域名路径：不触发阿里云 WAF 挑战（xueqiu.com/statuses/* 会），须与 App UA + App token 成对
XUEQIU_TIMELINE_URL = "https://api.xueqiu.com/v4/statuses/user_timeline.json"

# 网页 cookie 兜底通道已于 2026-09-23 随 waf-bot 一起下线：App 隐式账号是唯一身份来源。
# 下线顺序是「先删兜底代码、再停容器」——否则容器停掉后 /data/waf_cookies.json 会冻结在
# 最后一次成功值，cookie 失效后表现为静默失败，比没有兜底更危险。
#
# XUEQIU_COOKIE_KEY 保留：后台「Cookie 管理」与 kol_requests 的昵称解析仍在用，
# 但不再参与抓取链路。

# 探测式轮询：先用 count=1 轻量探测（约 11.7KB），最新帖已入库则跳过本轮全量拉取（约 207KB）。
# 判定不依赖本地水位，而是拿探测到的帖子 ID 回查 DB —— 天然免疫「水位写错导致静默漏帖」：
# 帖子只要没真正入库，探测就一定判定为「有更新」，全量拉取照常发生。
XUEQIU_PROBE_ENABLED = os.environ.get("XUEQIU_PROBE", "1") != "0"
# 连续跳过的轮次上限：到点强制全量一次，兜住「探测接口返回陈旧数据」这类反常情况。
XUEQIU_PROBE_FORCE_FULL_EVERY = max(1, int(os.environ.get("XUEQIU_PROBE_FORCE_FULL", "10")))
_probe_skip_streak: dict[int, int] = {}  # kol_id -> 连续跳过次数；进程内即可，重启归零无害


def apply_xueqiu_cookie(client: httpx.Client, cookie: str) -> None:
    """用域 Cookie jar 发送登录态，让 HTTPX 跟随 www 跳转时仍携带 Cookie。"""
    client.headers.pop("Cookie", None)
    client.cookies.clear()
    for part in (cookie or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name:
            client.cookies.set(name, value, domain=".xueqiu.com", path="/")


def resolve_xueqiu_identity(
    db=None, cookie: str = ""
) -> tuple[str, str, str, bool]:
    """当前雪球身份 (cookie, ua, timeline_url, is_app)。

    只有 App 隐式账号一条通道（api.xueqiu.com，不触发 WAF 挑战）。注册失败直接抛出，
    由调度器按平台级退避重试 —— 不再静默退回网页 cookie：那条路径在本服务出口 IP 上
    已被 400016/110017 拦截，且其数据源（waf-bot）已下线，留着只会制造「有兜底」的错觉。

    db / cookie 参数保留仅为兼容既有调用签名，不再读取。
    """
    if not xq_identity.enabled():
        raise RuntimeError(
            "雪球 App 身份通道已被 XUEQIU_APP_IDENTITY=0 关闭，且网页 cookie 兜底已下线"
        )
    return (
        xq_identity.identity()["cookie"],
        xq_identity.APP_UA,
        XUEQIU_TIMELINE_URL,
        True,
    )


def normalize_xueqiu_id(external_id: str | None) -> str:
    """从雪球主页链接提取数字用户 ID；纯数字原样返回；其余原样返回（保留原有报错信息）。

    管理后台允许粘贴「主页链接/UID」（如 https://xueqiu.com/u/4514680565），
    若把完整 URL 直接当 user_id 传给接口会 400，这里统一归一化。
    """
    value = (external_id or "").strip()
    match = re.search(r"xueqiu\.com/u/(\d+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"\d+", value):
        return value
    return value


def classify_status(status: dict) -> str | None:
    """判断动态流中的一项类型：post（发帖）/ reply（回复他人）/ None（转发等不推送项）。

    雪球 user_timeline 里回复项的特征：正文以「回复<a>@某人</a>」开头（commentId > 0），
    转发项也带 retweeted_status，不能仅凭该字段跳过（否则会把回复一起丢掉）。
    """
    desc = (status.get("description") or "").lstrip()
    if desc.startswith("回复") and status.get("commentId"):
        return "reply"
    if status.get("retweeted_status"):
        return None
    return "post"


def _is_waf_html(resp: httpx.Response) -> bool:
    """判断响应是否为拦截用的 HTML 页，而不是预期的 JSON。"""
    content_type = resp.headers.get("content-type", "")
    return "text/html" in content_type and any(
        marker in resp.text for marker in ("renderData", "aliyun_waf", "acw_sc__v2")
    )


XUEQIU_AUTH_ERROR_CODES = {"10022", "400016"}
XUEQIU_AUTH_ERROR_MARKERS = ("重新登录", "请登录", "登录帐号", "登录账号", "login", "cookie")


def xueqiu_session_dead(resp: httpx.Response) -> bool:
    """登录失效：401/403、认证错误码，或 JSON 中明确要求重新登录。"""
    if resp.status_code in (401, 403):
        return True
    try:
        data = resp.json()
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    if str(data.get("error_code") or "") in XUEQIU_AUTH_ERROR_CODES:
        return True
    auth_text = " ".join(
        str(data.get(key) or "") for key in ("error_description", "msg", "message")
    ).lower()
    return any(marker in auth_text for marker in XUEQIU_AUTH_ERROR_MARKERS)


def merge_cookie_strings(old: str, cookies, prefer_domain: str = "") -> str:
    """把旧 Cookie 与本次会话新下发的 cookie 合并（同名以新值为准）。

    雪球首页刷新只会回发部分 token（如 xq_a_token），直接覆盖会丢掉
    u / device_id / xqat 等其他会话字段，合并可完整保留登录态。
    prefer_domain 非空时，同名多域只覆盖匹配该域的新值。
    """
    items: dict[str, str] = {}
    for part in (old or "").split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            items[key] = value
    jar = getattr(cookies, "jar", cookies)
    for cookie in jar:
        domain = getattr(cookie, "domain", "") or ""
        if not prefer_domain or prefer_domain in domain or cookie.name not in items:
            items[cookie.name] = cookie.value
    return "; ".join(f"{k}={v}" for k, v in items.items())


def _avatar_url(user: dict) -> str:
    """从雪球 user 对象拼头像地址（photo_domain + profile_image_url 180x180 变体）。"""
    photo_domain = user.get("photo_domain") or ""
    variants = (user.get("profile_image_url") or "").split(",")
    if not variants or not variants[0]:
        return ""
    first = variants[1] if len(variants) > 1 and variants[1] else variants[0]
    if photo_domain.startswith("//"):
        return f"https:{photo_domain}{first}"
    if photo_domain.startswith("http"):
        return f"{photo_domain}{first}"
    return ""


def _dewatermark_image(url: str, images_dir: str | Path) -> str:
    return url


def _dewatermark_images(urls: list[str], db) -> list[str]:
    return list(urls)


def _extract_images(status: dict) -> list[str]:
    """雪球动态图片：original_pictures / pics / pic 字段（最多 4 张）。"""
    out: list[str] = []
    for pics_key in ("original_pictures", "pics"):
        for pic in status.get(pics_key) or []:
            url = (pic or {}).get("url") or ""
            if url.startswith("//"):
                url = f"https:{url}"
            if url and url not in out:
                out.append(url)
            if len(out) >= 4:
                return out
    # 新版接口：pic 为逗号分隔的图片列表（带 !thumb 缩略图后缀，去掉取原图）
    for url in (status.get("pic") or "").split(","):
        url = url.strip()
        if url.startswith("//"):
            url = f"https:{url}"
        if "!" in url:
            url = url.split("!")[0]
        if url and url not in out:
            out.append(url)
        if len(out) >= 4:
            break
    return out


def resolve_profile(external_id: str, cookie: str = "", db=None) -> dict:
    """查询雪球用户昵称与头像（取最新一条动态里的 user 信息），失败返回空 dict。

    与抓取同源：只走 App 隐式账号（api.xueqiu.com）。cookie 参数保留仅为兼容调用签名。
    """
    uid = normalize_xueqiu_id(external_id)
    try:
        from ..proxy import ProxyUnavailable, acquire_client_proxy

        try:
            proxy, _pid = acquire_client_proxy(db, "xueqiu")
        except ProxyUnavailable:
            return {}
        if not xq_identity.enabled():
            return {}
        # App token 必须与 App UA 成对，与网页 cookie 混用必被拒（10022/400016）
        identity_cookie = xq_identity.identity()["cookie"]
        ua = xq_identity.APP_UA
        url = XUEQIU_TIMELINE_URL
        client = httpx.Client(
            timeout=15,
            follow_redirects=True,
            proxy=proxy,
            headers={
                "User-Agent": ua,
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://xueqiu.com/u/{uid}",
            },
        )
        apply_xueqiu_cookie(client, identity_cookie)
    except Exception:  # noqa: BLE001 - 非 ASCII ID（误填昵称）/ 身份不可用时回退空结果，不阻断审批
        return {}
    try:
        resp = client.get(
            url,
            params={"user_id": uid, "page": 1, "count": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        statuses = (data or {}).get("statuses") or []
        if statuses:
            user = statuses[0].get("user") or {}
            screen_name = user.get("screen_name")
            avatar = _avatar_url(user)
            if screen_name:
                return {"screen_name": str(screen_name).strip(), "avatar_url": avatar}
    except Exception:  # noqa: BLE001 - 昵称解析失败不阻断导入
        return {}
    finally:
        client.close()
    return {}


class XueqiuFetcher(Fetcher):
    platform = "xueqiu"

    def __init__(self, source_config, db, client: httpx.Client | None = None):
        super().__init__(source_config)
        self.db = db
        headers = {
            "User-Agent": xq_identity.APP_UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": "https://xueqiu.com",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://xueqiu.com/",
        }

        def _make_client():
            from ..proxy import acquire_client_proxy, attach_proxy

            proxy, pid = acquire_client_proxy(self.db, "xueqiu")
            c = httpx.Client(
                timeout=20, headers=headers, proxy=proxy, follow_redirects=True
            )
            attach_proxy(c, pid)
            return c

        self._http = ThreadLocalClient(_make_client, injected=client)
        # 身份在 _apply_cookie 里逐次判定（唯一通道：App 隐式账号）
        self._app_identity = False
        self._timeline_url = XUEQIU_TIMELINE_URL

    @property
    def client(self):
        return self._http.get()

    @client.setter
    def client(self, value):
        self._http.set(value)

    def _apply_cookie(self) -> None:
        """应用当前身份：唯一通道是 App 隐式账号；注册失败直接抛出，由调度器退避。"""
        cookie, ua, self._timeline_url, self._app_identity = resolve_xueqiu_identity(
            self.db, self.source_config.cookie
        )
        self.client.headers["User-Agent"] = ua
        apply_xueqiu_cookie(self.client, cookie)

    def _refresh_cookie(self) -> None:
        """身份失效后自动续期：换新设备指纹重新注册隐式账号。"""
        try:
            xq_identity.rotate_identity()
        except Exception as exc:  # noqa: BLE001 - 节流/注册失败时把错误交给调用方退避
            logger.warning("雪球 App 身份续期失败（%s）", exc)
        self._apply_cookie()

    def fetch(self, kol: dict) -> list[Post]:
        self._apply_cookie()
        # 用户时间线 JSON 接口：固定走 api.xueqiu.com（网页域已被 400016/110017 拦截）
        url = self._timeline_url
        uid = normalize_xueqiu_id(kol["external_id"])
        self.client.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Origin": "https://xueqiu.com",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://xueqiu.com/u/{uid}",
            }
        )

        def get_page(page: int, count: int = 20) -> dict:
            params = {"user_id": uid, "page": page, "count": count}
            resp = self.client.get(url, params=params)
            if xueqiu_session_dead(resp) or _is_waf_html(resp):
                # 身份失效：续期一次后重打（只重试一次，仍失败就把错误交给调用方退避）
                self._refresh_cookie()
                resp = self.client.get(url, params=params)
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                raise RuntimeError(
                    "雪球接口返回异常，请检查 xueqiu cookie 配置后重试"
                ) from None

        def probe_no_update() -> bool:
            """count=1 轻量探测：最新帖已入库 → 本轮判定无新帖。

            任何异常或不确定都返回 False（退回全量）—— 宁可多拉一次，不能漏帖。
            """
            if self.db is None:  # 无 DB 时无法佐证「已入库」，一律走全量
                return False
            try:
                data = get_page(1, count=1)
            except Exception as exc:  # noqa: BLE001 - 探测失败不阻断，退回全量
                logger.debug("雪球探测失败，退回全量拉取: %s", exc)
                return False
            statuses = (data or {}).get("statuses") or []
            newest_id = str((statuses[0] if statuses else {}).get("id") or "")
            if not newest_id:
                return False
            return (self.platform, newest_id) in self.db.existing_post_keys(
                [(self.platform, newest_id)]
            )

        def build(statuses: list) -> list[Post]:
            posts = []
            for s in statuses:
                post_type = classify_status(s)
                if post_type is None:
                    continue  # 纯转发不推送（回复项单独识别并保留）
                target = s.get("target") or ""
                url = f"https://xueqiu.com{target}" if target.startswith("/") else target
                content = strip_html(s.get("description") or "")
                if content.endswith(("…", "...")):
                    # 时间线长文被截断（尾部 …）：同响应的 text 字段是完整正文，优先使用
                    # （详情接口 statuses/show.json 已被雪球下线，返回 405，不再依赖）
                    full = strip_html(s.get("text") or "")
                    if len(full) > len(content):
                        content = full
                posts.append(
                    Post(
                        platform=self.platform,
                        kol_id=kol["id"],
                        kol_name=kol["name"],
                        external_id=str(s.get("id") or ""),
                        title=s.get("title") or "",
                        content=content,
                        url=url,
                        published_at=format_published_at(str(s.get("created_at") or "")),
                        post_type=post_type,
                        images=_dewatermark_images(_extract_images(s), self.db),
                    )
                )
            return posts

        # 探测式轮询：先用 count=1（约 11.7KB）判断有没有新帖，避免为「无更新」付出全量 207KB。
        # 到上限后强制全量一次，防止探测长期返回陈旧数据而一直走不到全量路径。
        if XUEQIU_PROBE_ENABLED:
            streak = _probe_skip_streak.get(kol["id"], 0)
            if streak >= XUEQIU_PROBE_FORCE_FULL_EVERY:
                _probe_skip_streak[kol["id"]] = 0
                logger.debug("雪球 KOL %s 已连续跳过 %d 轮，本轮强制全量校验", kol["id"], streak)
            elif probe_no_update():
                _probe_skip_streak[kol["id"]] = streak + 1
                logger.debug("雪球 KOL %s 无新帖（探测命中已入库帖），跳过全量", kol["id"])
                return []
            else:
                _probe_skip_streak[kol["id"]] = 0

        first_statuses = (get_page(1) or {}).get("statuses") or []
        posts = build(first_statuses)
        if first_statuses:
            user = first_statuses[0].get("user") or {}
            avatar = _avatar_url(user)
            if avatar and avatar != (self.db.get_kol(kol["id"]) or {}).get("avatar_url"):
                self.db.update_kol_avatar(kol["id"], cache_avatar(self.db, kol["id"], avatar))
        return catchup_pages(
            self.db, lambda p: build((get_page(p) or {}).get("statuses") or []), posts
        )
