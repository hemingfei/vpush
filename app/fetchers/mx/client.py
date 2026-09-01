"""MX platform API client."""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from .crypto import decrypt_api_data
from .ws import BROWSER_UA

logger = logging.getLogger(__name__)

# 房间列表正常分页大小：绝不能发异常大 limit（单条日志就是机器人实锤）
ROOM_PAGE_SIZE = 100
# 房间列表翻页安全上限（50 页 = 5000 个房间，远超实际规模）
MAX_ROOM_PAGES = 50


class MXTokenExpiredError(RuntimeError):
    """TOKEN 过期/无效：调用方据此停止重试并通过系统 KOL 告警，绝不能继续打。"""


class MXClient:
    """MX platform API client."""

    def __init__(self, base_url: str, token: str, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._http = httpx.Client(timeout=30.0, transport=transport)

    def close(self):
        self._http.close()

    def _headers(self) -> dict[str, str]:
        """请求头与网页端形态一致：同一个 token 下 WS 和 HTTP 必须像同一个客户端，
        否则「一个 Chrome 一个 python-httpx」的自相矛盾就是风控的现成特征。"""
        host = urlparse(self.base_url).netloc
        headers = {
            "token": self.token,
            "Content-Type": "application/json",
            "version": "web",
            "User-Agent": BROWSER_UA,
        }
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
        response = self._http.request(method, url, headers=headers, content=body)
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
        """获取房间列表：每页 100 正常翻页拉全量。

        Returns:
            房间列表
        """
        rooms: list[dict] = []
        for page in range(1, MAX_ROOM_PAGES + 1):
            data = {
                "pages": page,
                "limit": ROOM_PAGE_SIZE,
                "tt": int(time.time() * 1000),
            }
            result = self._request("POST", "/api/room/list", data)
            if isinstance(result, dict) and "list" in result:
                batch = result["list"]
            elif isinstance(result, list):
                batch = result
            else:
                batch = []
            if not batch:
                break
            rooms.extend(batch)
            if len(batch) < ROOM_PAGE_SIZE:
                break
        return rooms

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
