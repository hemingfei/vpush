"""MX platform API client."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from .crypto import decrypt_api_data

logger = logging.getLogger(__name__)


class MXClient:
    """MX platform API client."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._http = httpx.Client(timeout=30.0)

    def close(self):
        self._http.close()

    def _headers(self) -> dict[str, str]:
        return {
            "token": self.token,
            "Content-Type": "application/json",
            "version": "web",
        }

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
        logger.info(f"Request to {method} {url}, data: {json_data}")
        response = self._http.request(method, url, headers=headers, content=body)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Response from MX: {json.dumps(result, ensure_ascii=False)}")

        if self._check_token_expired(result):
            raise RuntimeError("MX token expired")

        if isinstance(result, dict) and "data" in result:
            encrypted_data = result["data"]
            logger.info(f"Encrypted data: {encrypted_data}")
            if isinstance(encrypted_data, str) and encrypted_data:
                decrypted = decrypt_api_data(encrypted_data)
                logger.info(f"Decrypted data: {decrypted}")
                if decrypted is not None:
                    return decrypted

        return result

    def get_rooms(self) -> list[dict]:
        """获取房间列表。

        Returns:
            房间列表
        """
        data = {
            "pages": 1,
            "limit": 1000000,
            "tt": int(time.time() * 1000),
        }
        result = self._request("POST", "/api/room/list", data)
        if isinstance(result, dict) and "list" in result:
            return result["list"]
        if isinstance(result, list):
            return result
        return []

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
