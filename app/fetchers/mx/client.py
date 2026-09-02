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
        if isinstance(data, dict):
            code = data.get("code")
            if code == 502 or code == 401:
                return True
            msg = str(data.get("msg") or "")
            if any(keyword in msg for keyword in ("token", "登录", "认证", "过期", "无效")):
                return True
        return False

    def _request(self, method: str, path: str, json_data: dict = None) -> Any:
        url = f"{self.base_url}{path}"
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
