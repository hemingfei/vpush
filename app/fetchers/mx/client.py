"""MX platform API client."""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

from curl_cffi import requests as cffi_requests

from .crypto import decrypt_api_data
from .ws import ACCEPT_LANGUAGE, IMPERSONATE_TARGET

logger = logging.getLogger(__name__)

# 房间列表官方形态：2026-09-02 官方网页端抓包实测，冷启动就是单次
# {"pages":1,"limit":1000000} 全量拉取——该参数官方自己就发（无罪，频率才是信号）；
# 旧的「100/页翻页」反而与官方不符且请求数更多，已恢复官方形态
ROOM_LIST_LIMIT = 1000000

# Chrome 同源 XHR 的 accept 形态：官方网页端实测为 */*（fetch 默认值），
# 不是 axios 的 "application/json, text/plain, */*"
XHR_ACCEPT = "*/*"
# 导航请求特有头：impersonate 默认会带，XHR 不该带；headers 里置 None 即从请求中删除
_NAV_ONLY_HEADERS = ("upgrade-insecure-requests", "sec-fetch-user")


# 业务 msg 中「确定是 TOKEN 失效/未登录」的强特征短语（匹配前转小写、去空格）。
# 只认强特征：WAF 拦截页、代理错误等文本可能碰巧含「认证」「过期」「token」这类
# 弱词，而误熔断会停掉全部拉取与 WS，解锁代价高（需换 token 或手动登录半开重探）
_TOKEN_EXPIRED_MSG_MARKERS = (
    "token失效", "token已失效", "token过期", "token已过期",
    "token无效", "token错误", "token不存在",
    "invalidtoken", "tokenexpired", "expiredtoken", "tokenunauthorized",
    "令牌失效", "令牌过期", "令牌无效",
    "未登录", "请重新登录", "请先登录", "重新登录",
    "登录失效", "登录过期", "登录已过期", "登录已失效",
)


class MXTokenExpiredError(RuntimeError):
    """TOKEN 过期/无效：调用方据此停止重试并通过系统 KOL 告警，绝不能继续打。"""


class MXClient:
    """MX platform API client.

    HTTP 层用 curl_cffi impersonate：TLS 指纹（JA3/JA4）、HTTP/2、头序与 Chrome
    完全对齐——只补 UA/Origin 头挡不住「Chrome UA + Python TLS」的 JA3 与 UA
    一致性校验。Session 默认按线程隔离底层 curl 句柄，无状态 token API 可跨线程
    共享；session 参数仅供测试注入假客户端。
    """

    def __init__(self, base_url: str, token: str, session=None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._injected_session = session
        self._session = session or cffi_requests.Session(
            impersonate=IMPERSONATE_TARGET
        )

    def close(self):
        if self._injected_session is not None:
            return
        try:
            self._session.close()
        except Exception:  # noqa: BLE001 - 尽力关闭即可
            logger.warning("MX HTTP session close failed", exc_info=True)

    def _headers(self) -> dict[str, str]:
        """请求头与网页端同源 XHR 形态一致：同一个 token 下 WS 和 HTTP 必须像
        同一个客户端。UA / sec-ch-ua / accept-encoding 由 impersonate 模板提供，
        这里只覆盖 XHR 与导航请求的差异项（None 表示从默认头中删除）。"""
        host = urlparse(self.base_url).netloc
        headers = {
            "token": self.token,
            "Content-Type": "application/json",
            "version": "web",
            # 官方前端常驻自定义头：登录前的请求就已携带，两账号实测一致，
            # 为前端写死的渠道标记（与账号无关，2026-09-02 抓包）；缺失即「一眼假」
            "ad": "true",
            "i": "qq",
            "accept": XHR_ACCEPT,
            "accept-language": ACCEPT_LANGUAGE,
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
        }
        for nav_header in _NAV_ONLY_HEADERS:
            headers[nav_header] = None
        if host:
            headers["Origin"] = f"https://{host}"
            headers["Referer"] = f"https://{host}/"
        return headers

    def _check_token_expired(self, data: Any) -> bool:
        """业务响应是否「确定」指向 TOKEN 失效/未登录（弱关键词不熔断）。

        精确信号只有两类：平台业务码 401/502（实测即 TOKEN 失效），以及
        msg 中的强特征短语（见 _TOKEN_EXPIRED_MSG_MARKERS）。弱词（如仅出现
        「认证」）不再单独触发，避免 WAF/代理错误文本误熔断停掉全部拉取。
        """
        if not isinstance(data, dict):
            return False
        code = data.get("code")
        if code == 502 or code == 401:
            return True
        msg = str(data.get("msg") or "").lower().replace(" ", "").replace("\u3000", "")
        return any(marker in msg for marker in _TOKEN_EXPIRED_MSG_MARKERS)

    def _request(self, method: str, path: str, json_data: dict = None, base_url: str = None) -> Any:
        url = f"{base_url or self.base_url}{path}"
        headers = self._headers()
        body = json.dumps(json_data) if json_data else None
        response = self._session.request(
            method, url, headers=headers, data=body, timeout=30.0
        )
        response.raise_for_status()
        result = response.json()

        if self._check_token_expired(result):
            raise MXTokenExpiredError("MX token expired")

        if isinstance(result, dict) and "data" in result:
            encrypted_data = result["data"]
            if isinstance(encrypted_data, str) and encrypted_data:
                decrypted = decrypt_api_data(encrypted_data)
                if decrypted is not None:
                    return decrypted

        return result

    def get_rooms(self) -> list[dict]:
        """获取房间列表：与官方网页端一致，单次 limit=1000000 全量拉取。

        Returns:
            房间列表
        """
        data = {
            "pages": 1,
            "limit": ROOM_LIST_LIMIT,
            "tt": int(time.time() * 1000),
        }
        result = self._request("POST", "/api/room/list", data)
        if isinstance(result, dict) and "list" in result:
            return result["list"]
        if isinstance(result, list):
            return result
        return []

    def room_view(self, room_id: int) -> None:
        """进房上报：官方网页端每次打开房间都先发 {"rid","tt"}（抓包实测），
        拉取消息前调用一次即可对齐「人打开了房间」的行为链。"""
        data = {"rid": room_id, "tt": int(time.time() * 1000)}
        self._request("POST", "/api/room/view", data)

    # ---- 官方冷启动序列的只读端点（2026-09-02 抓包实测）----
    # master-api 与 business-api 同主机不同前缀。vpush 在开窗会话启动时按官方
    # 顺序补发这些只读请求，使「开窗」的请求足迹与「真人打开网页」一致；
    # 全部只读、无业务副作用，失败由调用方按最佳努力处理。

    def _master_base(self) -> str:
        parsed = urlparse(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}/master-api"

    def user_info(self) -> Any:
        return self._request(
            "POST", "/api/user/info",
            {"device": "web-browser", "tt": int(time.time() * 1000)},
            base_url=self._master_base(),
        )

    def system_config(self) -> Any:
        return self._request(
            "POST", "/api/system/config", {"tt": int(time.time() * 1000)},
            base_url=self._master_base(),
        )

    def msg_tip(self) -> Any:
        return self._request("POST", "/api/msg/tip", {"tt": int(time.time() * 1000)})

    def room_grouplist(self) -> Any:
        return self._request(
            "POST", "/api/room/grouplist", {"tt": int(time.time() * 1000)},
            base_url=self._master_base(),
        )

    def master_notice(self) -> Any:
        """平台公告（GET，token 在 query；官方启动必发，business 版 404 照发故跳过）。"""
        url = (
            f"{self._master_base()}/api/notice"
            f"?tt={int(time.time() * 1000)}&token={self.token}"
        )
        # GET 无 body：不带 Content-Type（与官方 axios 形态一致）
        headers = {k: v for k, v in self._headers().items() if k != "Content-Type"}
        response = self._session.request("GET", url, headers=headers, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        if self._check_token_expired(result):
            raise MXTokenExpiredError("MX token expired")
        return result

    def get_room_history(
        self, room_id: int, msg_id: int = 0, limit: int = 50
    ) -> list[dict]:
        """获取房间历史消息。

        Args:
            room_id: 房间ID
            msg_id: 消息ID游标，0表示最新
            limit: 每页数量

        Returns:
            消息列表
        """
        data = {
            "rid": room_id,
            "msgid": msg_id,
            "pagesize": limit,
            "tt": int(time.time() * 1000),
        }
        result = self._request("POST", "/api/msg/list", data)
        if isinstance(result, dict) and "list" in result:
            return result["list"]
        if isinstance(result, list):
            return result
        return []
