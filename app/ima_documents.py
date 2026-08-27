"""Pure-VPS IMA document collector and local PDF/TXT archive."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .fetchers.ima_inspect import item_cover, item_text

logger = logging.getLogger(__name__)

BASE = os.environ.get("IMA_BASE", "https://ima.qq.com/cgi-bin")
GUID = os.environ.get("IMA_GUID", "7497986728819336")
APP_VER = os.environ.get("IMA_APP_VER", "2.6.7.0515")
Q36 = os.environ.get("IMA_Q36", "07cf2a0a18c8863cfbfa8957100013719518")
IUA = os.environ.get(
    "IMA_IUA",
    "PR=IMA&PP=com.tencent.ima&PPVN="
    + APP_VER
    + "&PL=ADR&DN=OnePlus+PJD110&MO=PJD110&RL=1440*3168&OS=16",
)
CLIENT_TYPE = "256001"
TOKEN_TTL = 7000

IMA_PURE_UID_KEY = "ima_pure_uid"
IMA_PURE_REFRESH_TOKEN_KEY = "ima_pure_refresh_token"
IMA_PURE_KB_ID_KEY = "ima_pure_knowledge_base_id"
IMA_PURE_ROOT_FOLDER_KEY = "ima_pure_root_folder_id"
IMA_PURE_GROUPS_KEY = "ima_pure_groups"
IMA_PURE_INTERVAL_KEY = "ima_pure_interval_seconds"
IMA_PURE_LAST_STARTED_KEY = "ima_pure_last_started_at"
IMA_PURE_LAST_FINISHED_KEY = "ima_pure_last_finished_at"
IMA_PURE_LAST_RESULT_KEY = "ima_pure_last_result"
IMA_LEGACY_GROUP_ID = "legacy"
IMA_LEGACY_GROUP_NAME = "IMA 文档"
IMA_PURE_UID_DEFAULT = "001aa361168019ef"
IMA_PURE_KB_ID_DEFAULT = "7464369361259867"
IMA_PURE_ROOT_FOLDER_DEFAULT = "folder_7489327974078249"
IMA_PURE_INTERVAL_DEFAULT = 3600
IMA_PURE_INTERVAL_MIN = 1800
IMA_PURE_INTERVAL_MAX = 604800

PUB_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAx9h6SY1LO88wRVKdOC5U
tjYTXfMpUqCK22FemW9ba4812nVjF4Va+guoHXdBePkhsQmz94PeqqZiSN/YekiV
CU6HbWivdhKcs6LcYMT+sw4cwtMZ1NOJEkY1ujOWFnmNmpK243wwlf+RwE/L+xOJ
8vy/EBuYDv06M+BbccO832bOpWsOFYPPP5KtOmOaqXq6Fgu1vOrXmQIo0q8WmO09
PvjHLwIruqthV2dBcVI1qMEKejM1SKwzCWb78t+fUsr3OjDqApWma3h10hGKcin4
NIGdfITwmiBmS+R1Mr8P/ssNq0ptvr9+VqUvsJD7ASVCPo9EG658fZYGil6oH5JN
OQIDAQAB
-----END PUBLIC KEY-----
"""


def bkn(token: str) -> int:
    value = 5381
    for char in token:
        value = (33 * value + ord(char)) & 0xFFFFFFFF
    return value & 0x7FFFFFFF


def encrypt_body(plain: bytes) -> tuple[bytes, str, str]:
    """Return AES key, base64 AES-GCM body, and base64 RSA-wrapped key."""
    key = os.urandom(16)
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, plain, None)
    body = base64.b64encode(nonce + encrypted).decode("ascii")
    public_key = serialization.load_pem_public_key(PUB_PEM)
    wrapped = public_key.encrypt(
        key,
        padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return key, body, base64.b64encode(wrapped).decode("ascii")


def decrypt_body(cipher_b64: str, key: bytes) -> bytes:
    raw = base64.b64decode(cipher_b64)
    return AESGCM(key).decrypt(raw[:12], raw[12:], None)


def _safe_error(exc: BaseException) -> str:
    text = str(exc).splitlines()[0][:240]
    text = re.sub(r"https?://\S+", "<url>", text)
    text = re.sub(r"(?i)((?:bearer|token|access_token|refresh_token|signature|sig)\s+)[^\s]+", r"\1<redacted>", text)
    return re.sub(
        r"(?i)((?:ima-token|token|access_token|refresh_token|authorization|signature|sig|sign|q-sign|x-ima-cookie)\s*[=:]\s*)[^&;,\s]+",
        r"\1<redacted>",
        text,
    )


def _setting(db: Any, key: str, env_key: str, default: str = "") -> str:
    value = db.get_setting(key) if db is not None else None
    return str(value or os.environ.get(env_key, "") or default).strip()


def _optional_int(value: Any) -> int | None:
    if value is None:
        return 0
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"-?\d+", text):
            return int(text)
    return None


def _interval(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = IMA_PURE_INTERVAL_DEFAULT
    return max(IMA_PURE_INTERVAL_MIN, min(IMA_PURE_INTERVAL_MAX, number))


def _secret_status(value: str) -> dict[str, Any]:
    return {"set": bool(value), "preview": "已保存" if value else ""}


@dataclass(frozen=True)
class ImaGroupConfig:
    id: str
    name: str
    knowledge_base_id: str
    root_folder_id: str
    enabled: bool = True
    source: str = "manual"

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "knowledge_base_id": self.knowledge_base_id,
            "root_folder_id": self.root_folder_id,
            "enabled": self.enabled,
            "source": self.source,
        }


def _legacy_group(kb: str, root: str) -> ImaGroupConfig:
    return ImaGroupConfig(
        id=IMA_LEGACY_GROUP_ID,
        name=IMA_LEGACY_GROUP_NAME,
        knowledge_base_id=kb,
        root_folder_id=root,
    )


def _discovery_payload(payload: Any) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    return data if isinstance(data, dict) else {}


def _discovery_page_items(payload: Any) -> list[dict[str, Any]]:
    data = _discovery_payload(payload)
    items: list[dict[str, Any]] = []
    for field in ("searched_knowledge_bases", "knowledge_base_list", "knowledge_list", "info_list"):
        candidate = data.get(field)
        if isinstance(candidate, list) and candidate:
            items.extend(item for item in candidate if isinstance(item, dict))
            break
    if items:
        return items
    for section in data.get("results") or []:
        if not isinstance(section, dict):
            continue
        for item in section.get("knowledge_base_list") or []:
            if isinstance(item, dict):
                items.append(item)
    return items


def _prepare_discovery_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("type") == 1:
        return None
    group_id_value = item.get("id") or item.get("knowledge_base_id")
    if not isinstance(group_id_value, str) or not group_id_value.strip():
        return None
    basic = item.get("basic_info") if isinstance(item.get("basic_info"), dict) else {}
    name_value = item.get("name") or item.get("kb_name") or basic.get("name") or group_id_value
    root_value = item.get("root_folder_id") or item.get("folder_id") or group_id_value
    if not all(isinstance(value, str) and value.strip() for value in (name_value, root_value)):
        return None
    prepared = dict(item)
    prepared["id"] = group_id_value.strip()
    prepared["name"] = name_value.strip()
    prepared["root_folder_id"] = root_value.strip()
    return prepared


def normalize_discovered_groups(payload: Any) -> tuple[ImaGroupConfig, ...]:
    groups: list[ImaGroupConfig] = []
    for item in _discovery_page_items(payload):
        prepared = _prepare_discovery_item(item)
        if prepared is None:
            continue
        root_value = prepared.get("root_folder_id")
        name_value = prepared.get("name")
        group_id = prepared["id"]
        if not isinstance(root_value, str) or not root_value.strip():
            continue
        if not isinstance(name_value, str) or not name_value.strip():
            continue
        groups.append(
            ImaGroupConfig(
                id=group_id,
                name=name_value.strip()[:100],
                knowledge_base_id=group_id,
                root_folder_id=root_value.strip(),
                source="discovered",
            )
        )
    return tuple(groups)


def merge_groups(
    existing: tuple[ImaGroupConfig, ...],
    discovered: tuple[ImaGroupConfig, ...],
) -> tuple[ImaGroupConfig, ...]:
    by_id = {group.id: group for group in existing}
    kb_to_id = {group.knowledge_base_id: group.id for group in existing}
    for group in discovered:
        previous = by_id.get(group.id)
        if previous is None:
            previous = by_id.get(kb_to_id.get(group.knowledge_base_id, ""))
        manual = previous and previous.source == "manual"
        target_id = previous.id if previous else group.id
        by_id[target_id] = ImaGroupConfig(
            id=target_id,
            name=previous.name if manual else group.name,
            knowledge_base_id=group.knowledge_base_id,
            root_folder_id=previous.root_folder_id if manual else group.root_folder_id,
            enabled=previous.enabled if previous else True,
            source=previous.source if manual else "discovered",
        )
        kb_to_id[group.knowledge_base_id] = target_id
    return tuple(by_id.values())


def _read_groups(db: Any, kb: str, root: str) -> tuple[ImaGroupConfig, ...]:
    raw = db.get_setting(IMA_PURE_GROUPS_KEY) if db is not None else None
    if raw:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            payload = []
        groups = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            required_fields = ("id", "name", "knowledge_base_id", "root_folder_id")
            if any(
                not isinstance(item.get(field), str) or not item[field].strip()
                for field in required_fields
            ):
                continue
            enabled = item.get("enabled", True)
            if not isinstance(enabled, bool):
                continue
            source = item.get("source", "manual")
            if not isinstance(source, str):
                continue
            groups.append(
                ImaGroupConfig(
                    id=item["id"].strip(),
                    name=item["name"].strip()[:100],
                    knowledge_base_id=item["knowledge_base_id"].strip(),
                    root_folder_id=item["root_folder_id"].strip(),
                    enabled=enabled,
                    source="discovered" if source == "discovered" else "manual",
                )
            )
        if groups:
            normalized_groups = []
            for group in groups:
                if group.id == IMA_LEGACY_GROUP_ID:
                    group = ImaGroupConfig(
                        id=group.id,
                        name=group.name,
                        knowledge_base_id=kb,
                        root_folder_id=root,
                        enabled=group.enabled,
                        source=group.source,
                    )
                normalized_groups.append(group)
            return tuple(normalized_groups)
    return (_legacy_group(kb, root),)


@dataclass(frozen=True)
class ImaDocumentConfig:
    uid: str = IMA_PURE_UID_DEFAULT
    refresh_token: str = ""
    knowledge_base_id: str = IMA_PURE_KB_ID_DEFAULT
    root_folder_id: str = IMA_PURE_ROOT_FOLDER_DEFAULT
    interval_seconds: int = IMA_PURE_INTERVAL_DEFAULT
    groups: tuple[ImaGroupConfig, ...] = ()

    @classmethod
    def from_db(cls, db: Any = None) -> ImaDocumentConfig:
        raw_interval = _setting(db, IMA_PURE_INTERVAL_KEY, "IMA_INTERVAL_SECONDS", str(IMA_PURE_INTERVAL_DEFAULT))
        uid = _setting(db, IMA_PURE_UID_KEY, "IMA_UID", IMA_PURE_UID_DEFAULT)
        refresh_token = _setting(db, IMA_PURE_REFRESH_TOKEN_KEY, "IMA_REFRESH_TOKEN")
        knowledge_base_id = _setting(db, IMA_PURE_KB_ID_KEY, "IMA_KB_ID", IMA_PURE_KB_ID_DEFAULT)
        root_folder_id = _setting(db, IMA_PURE_ROOT_FOLDER_KEY, "IMA_ROOT_FOLDER_ID", IMA_PURE_ROOT_FOLDER_DEFAULT)
        return cls(
            uid=uid,
            refresh_token=refresh_token,
            knowledge_base_id=knowledge_base_id,
            root_folder_id=root_folder_id,
            interval_seconds=_interval(raw_interval),
            groups=_read_groups(db, knowledge_base_id, root_folder_id),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.uid
            and self.refresh_token
            and any(
                group.enabled and group.knowledge_base_id and group.root_folder_id
                for group in self.groups
            )
        )

    def public(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "knowledge_base_id": self.knowledge_base_id,
            "root_folder_id": self.root_folder_id,
            "interval_seconds": self.interval_seconds,
            "refresh_token": _secret_status(self.refresh_token),
            "groups": [group.public() for group in self.groups],
            "configured": self.configured,
        }


class ImaPureClient:
    def __init__(self, config: ImaDocumentConfig, group: ImaGroupConfig | None = None):
        self.config = config
        self.group = group
        self.token = ""
        self.token_at = 0.0
        self.ctk = ""
        self.ctk_expire = 0

    @property
    def effective_knowledge_base_id(self) -> str:
        if self.group is not None:
            return self.group.knowledge_base_id
        for group in self.config.groups:
            if group.enabled and group.knowledge_base_id and group.root_folder_id:
                return group.knowledge_base_id
        return self.config.knowledge_base_id

    @property
    def effective_root_folder_id(self) -> str:
        if self.group is not None:
            return self.group.root_folder_id
        for group in self.config.groups:
            if group.enabled and group.knowledge_base_id and group.root_folder_id:
                return group.root_folder_id
        return self.config.root_folder_id

    @staticmethod
    def _cookie(token: str, uid: str) -> str:
        return (
            f"IMA-GUID={GUID};APP-VERSION={APP_VER};IMA-Q36={Q36};IMA-IUA={IUA};"
            f"UID-TYPE=2;IMA-UID={uid};IMA-TOKEN={token};"
            f"IMA-TOKEN-TYPE=IDC_TOKEN_IMATOKEN_BIND_SOCIAL;CLIENT-TYPE={CLIENT_TYPE}"
        )

    def _headers(self, token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "okhttp/4.12.0",
            "from_browser_ima": "1",
            "x-ima-cookie": self._cookie(token, self.config.uid),
            "x-ima-bkn": str(bkn(token)),
            "referer": "https://ima.qq.com",
            "origin": "https://ima.qq.com",
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _open_json(request: urllib.request.Request) -> tuple[dict[str, Any], Any]:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read()), response.headers
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"IMA HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("IMA network request failed") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("IMA returned invalid JSON") from exc

    def refresh(self) -> str:
        request = urllib.request.Request(
            BASE + "/oversea/auth_login/refresh",
            data=json.dumps(
                {"user_id": self.config.uid, "refresh_token": self.config.refresh_token}
            ).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "okhttp/4.12.0",
                "from_browser_ima": "1",
            },
        )
        data, _ = self._open_json(request)
        token = str(data.get("token") or "")
        if not token:
            raise RuntimeError(f"IMA refresh failed code={data.get('code')}")
        self.token = token
        self.token_at = time.time()
        return token

    def _token(self) -> str:
        if self.token and time.time() - self.token_at < TOKEN_TTL:
            return self.token
        return self.refresh()

    @staticmethod
    def _payload(data: dict[str, Any]) -> dict[str, Any]:
        payload = data.get("data")
        if isinstance(payload, dict) and "knowledge_list" in payload:
            return payload
        return data

    def discover_groups(self) -> tuple[ImaGroupConfig, ...]:
        raw_items: list[dict[str, Any]] = []
        cursor = ""
        seen_cursors: set[str] = set()
        while True:
            if cursor in seen_cursors:
                raise RuntimeError("IMA group discovery pagination repeated cursor")
            seen_cursors.add(cursor)
            token = self._token()
            request = urllib.request.Request(
                BASE + "/knowledge_tab_reader/search_knowledge_base",
                data=json.dumps(
                    {"query": "", "limit": 50, "cursor": cursor},
                    ensure_ascii=False,
                ).encode(),
                method="POST",
                headers=self._headers(token),
            )
            data, _ = self._open_json(request)
            code = data.get("code", data.get("retcode"))
            if code not in (0, None):
                raise RuntimeError(f"IMA group discovery failed code={code}")
            payload = _discovery_payload(data)
            raw_items.extend(_discovery_page_items(payload))
            if payload.get("is_end") is True or not payload.get("next_cursor"):
                break
            next_cursor = str(payload["next_cursor"])
            if next_cursor in seen_cursors:
                raise RuntimeError("IMA group discovery pagination repeated cursor")
            cursor = next_cursor
        return normalize_discovered_groups({"knowledge_base_list": raw_items})

    def list_items(self, folder_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor = ""
        seen_cursors: set[str] = set()
        while True:
            if cursor in seen_cursors:
                raise RuntimeError("IMA list pagination repeated cursor")
            seen_cursors.add(cursor)
            body: dict[str, Any] = {
                "knowledge_base_id": getattr(
                    self, "_discovery_knowledge_base_id", self.effective_knowledge_base_id
                ),
                "folder_id": folder_id,
                "limit": "50",
            }
            if cursor:
                body["cursor"] = cursor
            token = self._token()
            request = urllib.request.Request(
                BASE + "/knowledge_tab_reader/get_knowledge_list",
                data=json.dumps(body, ensure_ascii=False).encode(),
                method="POST",
                headers=self._headers(token),
            )
            data, _ = self._open_json(request)
            if data.get("code") not in (0, None):
                raise RuntimeError(f"IMA list failed code={data.get('code')}")
            payload = self._payload(data)
            if not isinstance(payload, dict):
                return items
            page_items = payload.get("knowledge_list")
            if isinstance(page_items, list):
                items.extend(page_items)
            if payload.get("is_end") is True or not payload.get("next_cursor"):
                return items
            next_cursor = str(payload["next_cursor"])
            if next_cursor in seen_cursors:
                raise RuntimeError("IMA list pagination repeated cursor")
            cursor = next_cursor

    def manifest(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for folder in self.list_items(self.effective_root_folder_id):
            if not isinstance(folder, dict) or folder.get("media_type") != 99:
                continue
            folder_info = folder.get("folder_info")
            if not isinstance(folder_info, dict):
                continue
            folder_id = folder_info.get("folder_id")
            if not isinstance(folder_id, str) or not folder_id.strip():
                continue
            day_value = folder_info.get("name")
            if day_value is None:
                day_value = folder.get("name")
            if day_value is not None and not isinstance(day_value, str):
                continue
            day = (day_value or "unknown").strip() if isinstance(day_value, str) else "unknown"
            for item in self.list_items(folder_id):
                if not isinstance(item, dict):
                    continue
                media_type = item.get("media_type")
                if media_type is not None and (
                    isinstance(media_type, bool) or not isinstance(media_type, int)
                ):
                    continue
                if media_type == 99:
                    continue
                media_id_value = item.get("media_id")
                if not isinstance(media_id_value, str) or not media_id_value.strip():
                    continue
                media_id = media_id_value.strip()
                try:
                    media_id = ImaDocumentStore.validate_media_id(media_id)
                except ValueError:
                    logger.warning("IMA ignored invalid media id")
                    continue
                name_value = item.get("name")
                if name_value is not None and not isinstance(name_value, str):
                    continue
                file_size = _optional_int(item.get("file_size"))
                if file_size is None:
                    continue
                md5_value = item.get("md5_sum")
                if md5_value is not None and not isinstance(md5_value, str):
                    continue
                ts_value = item.get("create_time")
                if ts_value is not None and (
                    isinstance(ts_value, bool)
                    or not isinstance(ts_value, (str, int, float))
                ):
                    continue
                name = item_display_name(item, media_id)
                if not (name.lower().endswith(".pdf") or media_id.lower().startswith("pdf_")):
                    continue
                record = {
                    "media_id": media_id,
                    "name": name,
                    "day": day,
                    "size": file_size or 0,
                    "md5": md5_value or "",
                    "ts": str(ts_value or ""),
                    "abstract": item_text(item)[:2000],
                    "cover_url": item_cover(item)[:2000],
                }
                if self.group is not None:
                    record["group_id"] = self.group.id
                    record["group_name"] = self.group.name
                records.append(record)
        records.sort(key=lambda item: (item["day"], item["media_id"]))
        return records

    def get_media(self, media_id: str) -> dict[str, Any]:
        token = self._token()
        plain = json.dumps(
            {
                "media_id": media_id,
                "source_knowledge_base_id": self.effective_knowledge_base_id,
            },
            ensure_ascii=False,
            indent=2,
        ).encode()
        key, encrypted, wrapped_key = encrypt_body(plain)
        extra = {"x-ima-cm": "1", "x-ima-ckey": wrapped_key}
        if self.ctk:
            extra["x-ima-ctk"] = self.ctk
        request = urllib.request.Request(
            BASE + "/s/file_manager/get_media",
            data=encrypted.encode(),
            method="POST",
            headers=self._headers(token, extra),
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("ascii")
                self.ctk = response.headers.get("x-ima-ctk") or self.ctk
                try:
                    self.ctk_expire = int(response.headers.get("x-ima-ctk-expire", 0) or 0)
                except ValueError:
                    self.ctk_expire = 0
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"IMA get_media HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
            raise RuntimeError("IMA get_media network response failed") from exc
        try:
            result = json.loads(decrypt_body(raw, key))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("IMA get_media response decrypt failed") from exc
        if result.get("code") != 0:
            raise RuntimeError(f"IMA get_media failed code={result.get('code')}")
        info = result.get("jump_url_info") or {}
        if not info.get("url") and not result.get("jump_url"):
            raise RuntimeError("IMA get_media returned no signed URL")
        return result

    @staticmethod
    def _pdf_info(path: Path) -> tuple[int, str]:
        digest = hashlib.md5()
        size = 0
        first = b""
        with path.open("rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                if not first:
                    first = chunk[:8]
                digest.update(chunk)
                size += len(chunk)
        if not first.startswith(b"%PDF-1."):
            raise RuntimeError("archive file is not a PDF")
        return size, digest.hexdigest()

    def download(
        self,
        media: dict[str, Any],
        destination: Path,
        expected_size: int = 0,
    ) -> dict[str, Any]:
        info = media.get("jump_url_info") or {}
        url = info.get("url") or media.get("jump_url")
        if not url:
            raise RuntimeError("IMA signed URL missing")
        headers = {str(k): str(v) for k, v in (info.get("headers") or {}).items()}
        headers["User-Agent"] = "okhttp/4.12.0"
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=destination.name + ".", suffix=".part", dir=destination.parent
        )
        os.close(fd)
        temp = Path(temp_name)
        digest = hashlib.md5()
        size = 0
        first = b""
        try:
            request = urllib.request.Request(str(url), headers=headers)
            try:
                response = urllib.request.urlopen(request, timeout=120)
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"IMA PDF HTTP {exc.code}") from exc
            with response, temp.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    if not first:
                        first = chunk[:8]
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if not first.startswith(b"%PDF-1."):
                raise RuntimeError("IMA download is not a PDF")
            if expected_size and size != int(expected_size):
                raise RuntimeError(f"IMA PDF size mismatch got={size} expected={expected_size}")
            os.replace(temp, destination)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        return {"size": size, "md5": digest.hexdigest(), "path": str(destination)}


def item_display_name(item: dict[str, Any], media_id: str) -> str:
    for key in ("title", "name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return media_id


MAX_FILENAME_BYTES = 240


def _fit_utf8(value: str, max_bytes: int) -> str:
    if len(value.encode("utf-8")) <= max_bytes:
        return value
    while value and len(value.encode("utf-8")) > max_bytes:
        value = value[:-1]
    return value.rstrip(" .")


def safe_filename(
    name: str,
    fallback: str,
    *,
    max_chars: int | None = None,
    max_bytes: int = MAX_FILENAME_BYTES,
) -> str:
    value = (name or fallback).replace("/", "_").replace("\\", "_").replace("\x00", "")
    value = re.sub(r"^[.]+", "_", value).strip() or fallback
    if max_chars is not None:
        value = value[:max_chars] or fallback
    if value.lower().endswith(".pdf"):
        stem, suffix = value[:-4], ".pdf"
    else:
        stem, suffix = value, ".pdf"
    stem = _fit_utf8(stem, max_bytes)
    if not stem:
        stem = _fit_utf8(str(fallback), max_bytes) or "document"
    return f"{stem}{suffix}"


def _safe_component(value: str, fallback: str = "unknown") -> str:
    value = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff().]+", "_", str(value or "")).strip("._")
    return value or fallback


def abstract_src_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def translation_fields(abstract: str, state_item: dict[str, Any]) -> dict[str, Any]:
    from .scheduler import _already_chinese

    text = str(abstract or "")
    cached = str(state_item.get("abstract_zh") or "")
    src_hash = str(state_item.get("abstract_src_hash") or "")
    fresh = bool(cached) and src_hash == abstract_src_hash(text)
    already = _already_chinese(text)
    return {
        "abstract": text,
        "abstract_zh": cached if fresh else "",
        "needs_translation": bool(text) and (not already) and (not fresh),
    }


class ImaDocumentStore:
    def __init__(self, root: str | Path):
        raw_root = Path(root).expanduser()
        if raw_root.exists() and raw_root.is_symlink():
            raise ValueError("archive root must not be a symlink")
        self.root = raw_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self.state_path = self.root / "state.json"
        self._state_lock = threading.Lock()
        self._legacy_group_id = IMA_LEGACY_GROUP_ID
        self._group_metadata: dict[str, tuple[str, str]] = {
            IMA_LEGACY_GROUP_ID: (IMA_LEGACY_GROUP_NAME, IMA_LEGACY_GROUP_ID)
        }

    @staticmethod
    def validate_media_id(media_id: str) -> str:
        value = str(media_id or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
            raise ValueError("invalid media id")
        return value

    def _is_legacy_group(self, group_id: str) -> bool:
        return not group_id or group_id == IMA_LEGACY_GROUP_ID or group_id.startswith("legacy:")

    def _record_group_id(self, record: dict[str, Any]) -> str:
        return str(record.get("group_id") or self._legacy_group_id or IMA_LEGACY_GROUP_ID)

    def _group_namespace(self, group_id: str) -> str:
        digest = hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:16]
        return f"{_safe_component(group_id)}__{digest}"

    def state_key(self, record: dict[str, Any]) -> str:
        media_id = self.validate_media_id(record.get("media_id", ""))
        group_id = self._record_group_id(record)
        if self._is_legacy_group(group_id):
            return media_id
        return f"{self._group_namespace(group_id)}__{media_id}"

    def _state_item(self, state: dict[str, dict[str, Any]], record: dict[str, Any]) -> dict[str, Any]:
        return state.get(self.state_key(record)) or {}

    def _safe_path(self, relative: str) -> Path | None:
        candidate = (self.root / relative).resolve()
        if candidate == self.root or not candidate.is_relative_to(self.root):
            return None
        return candidate

    def _day_dir(self, day: str) -> Path:
        return self.root / _safe_component(day)

    @staticmethod
    def _collision_token(media_id: str) -> str:
        return hashlib.sha256(media_id.encode("utf-8")).hexdigest()[:8]

    def _archive_path(self, relative: str) -> Path:
        day_path = self.root / Path(relative).parent
        if day_path.is_symlink():
            raise ValueError("archive directory must not be a symlink")
        candidate = self._safe_path(relative)
        if candidate is None:
            raise ValueError("archive path escapes root")
        if candidate.parent.exists() and candidate.parent.is_symlink():
            raise ValueError("archive directory must not be a symlink")
        return candidate

    def pdf_path(self, record: dict[str, Any], *, occupied: set[str] | None = None) -> Path:
        media_id = self.validate_media_id(record.get("media_id", ""))
        filename = safe_filename(str(record.get("name") or media_id), media_id)
        day = _safe_component(str(record.get("day") or "unknown"))
        relative = Path(day) / filename
        group_id = self._record_group_id(record)
        if not self._is_legacy_group(group_id):
            relative = Path(self._group_namespace(group_id)) / relative
        if occupied and str(relative) in occupied:
            path = Path(filename)
            token = self._collision_token(media_id)
            stem = _fit_utf8(path.stem, MAX_FILENAME_BYTES - len(token) - 2)
            filename = f"{stem}__{token}{path.suffix or '.pdf'}"
            relative = Path(day) / filename
            if not self._is_legacy_group(group_id):
                relative = Path(self._group_namespace(group_id)) / relative
        return self._archive_path(str(relative))

    def txt_path(self, record: dict[str, Any], *, occupied: set[str] | None = None) -> Path:
        return self.pdf_path(record, occupied=occupied).with_suffix(".txt")

    @staticmethod
    def _path_is_file(path: Path | None) -> bool:
        if path is None:
            return False
        try:
            return path.is_file()
        except OSError:
            return False

    def _find_existing_pdf(
        self,
        record: dict[str, Any],
        item: dict[str, Any],
        media_id: str,
        occupied: set[str],
    ) -> Path | None:
        day = _safe_component(str(record.get("day") or item.get("day") or "unknown"))
        candidates: list[Path] = []
        current = self._state_path(item.get("pdf"))
        if current is not None:
            candidates.append(current)
        try:
            candidates.append(self.pdf_path(record, occupied=occupied))
        except ValueError:
            pass
        group_id = self._record_group_id(record)
        prefix = "" if self._is_legacy_group(group_id) else f"{self._group_namespace(group_id)}/"
        for filename in (
            safe_filename(str(record.get("name") or media_id), media_id, max_chars=180, max_bytes=10_000),
            safe_filename(str(item.get("name") or media_id), media_id),
            safe_filename(media_id, media_id),
        ):
            try:
                candidates.append(self._archive_path(f"{prefix}{day}/{filename}"))
            except ValueError:
                continue
        seen: set[str] = set()
        for path in candidates:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            if self._path_is_file(path):
                return path
        return None

    def _occupied_pdfs(self, state: dict[str, dict[str, Any]], skip_media_id: str = "") -> set[str]:
        occupied: set[str] = set()
        for state_key, item in state.items():
            if state_key == skip_media_id or not isinstance(item, dict):
                continue
            relative = item.get("pdf")
            if isinstance(relative, str) and relative:
                occupied.add(relative)
        return occupied

    def restore_original_filenames(self) -> dict[str, int]:
        records_by_key: dict[str, dict[str, Any]] = {}
        records_by_media: dict[str, dict[str, Any]] = {}
        for item in self.load_manifest():
            try:
                media_id = self.validate_media_id(item.get("media_id", ""))
                records_by_key[self.state_key(item)] = item
                records_by_media[media_id] = item
            except ValueError:
                continue
        state = self.load_state()
        occupied = self._occupied_pdfs(state)
        renamed = 0
        changed = False
        for state_key, item in list(state.items()):
            if not isinstance(item, dict):
                continue
            record = dict(records_by_key.get(state_key) or {})
            if not record:
                try:
                    media_id = self.validate_media_id(state_key)
                except ValueError:
                    continue
                record = dict(records_by_media.get(media_id) or {})
                record.setdefault("media_id", media_id)
            try:
                media_id = self.validate_media_id(record.get("media_id", ""))
            except ValueError:
                continue
            record.setdefault("name", item.get("name") or media_id)
            record.setdefault("day", item.get("day") or "unknown")
            current_rel = item.get("pdf")
            others = occupied - ({current_rel} if isinstance(current_rel, str) else set())
            current_pdf = self._find_existing_pdf(record, item, media_id, others)
            if current_pdf is None:
                continue
            try:
                desired = self.pdf_path(record, occupied=others)
            except ValueError:
                continue
            new_name = str(record.get("name") or item.get("name") or media_id)
            if desired == current_pdf:
                new_pdf = str(desired.relative_to(self.root))
                new_txt = str(desired.with_suffix(".txt").relative_to(self.root))
                if item.get("pdf") != new_pdf or item.get("txt") != new_txt or item.get("name") != new_name:
                    occupied.discard(str(current_rel or ""))
                    occupied.add(new_pdf)
                    item["pdf"] = new_pdf
                    item["txt"] = new_txt
                    item["name"] = new_name
                    changed = True
                continue
            if self._path_is_file(desired):
                continue
            current_txt = self._state_path(item.get("txt")) or current_pdf.with_suffix(".txt")
            desired_txt = desired.with_suffix(".txt")
            desired.parent.mkdir(parents=True, exist_ok=True)
            if desired.parent.is_symlink():
                continue
            os.replace(current_pdf, desired)
            if current_txt.is_file() and current_txt != desired_txt:
                os.replace(current_txt, desired_txt)
            new_pdf = str(desired.relative_to(self.root))
            occupied.discard(str(current_rel or ""))
            occupied.add(new_pdf)
            item["pdf"] = new_pdf
            item["txt"] = str(desired_txt.relative_to(self.root))
            item["name"] = new_name
            renamed += 1
            changed = True
            if renamed % 25 == 0:
                self.save_state(state)
        if changed:
            self.save_state(state)
        return {"renamed": renamed}

    def _load(self, path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return default

    def _remember_groups(self, groups: tuple[ImaGroupConfig, ...] | None) -> None:
        for group in groups or ():
            self._group_metadata[group.id] = (group.name, group.id)
            if group.id == IMA_LEGACY_GROUP_ID or group.id.startswith("legacy:"):
                self._legacy_group_id = group.id

    def _normalize_manifest_records(
        self,
        records: list[dict[str, Any]],
        groups: tuple[ImaGroupConfig, ...] | None = None,
    ) -> list[dict[str, Any]]:
        self._remember_groups(groups)
        metadata = dict(self._group_metadata)
        for group in groups or ():
            metadata[group.id] = (group.name, group.id)
        output = []
        for record in records:
            item = dict(record)
            group_id = str(item.get("group_id") or "")
            if not group_id and self._legacy_group_id:
                group_id = self._legacy_group_id
                item["group_id"] = group_id
            if (
                group_id == IMA_LEGACY_GROUP_ID or group_id.startswith("legacy:")
            ) and not item.get("group_name"):
                item["group_name"] = metadata.get(group_id, (IMA_LEGACY_GROUP_NAME, group_id))[0]
            elif group_id in metadata and not item.get("group_name"):
                item["group_name"] = metadata[group_id][0]
            output.append(item)
        return output

    def load_manifest(self, groups: tuple[ImaGroupConfig, ...] | None = None) -> list[dict[str, Any]]:
        value = self._load(self.manifest_path, {})
        if isinstance(value, dict) and isinstance(value.get("files"), list):
            records = [item for item in value["files"] if isinstance(item, dict)]
        else:
            records = value if isinstance(value, list) else []
        return self._normalize_manifest_records(records, groups)

    def load_state(self) -> dict[str, dict[str, Any]]:
        value = self._load(self.state_path, {})
        return value if isinstance(value, dict) else {}

    def _save(self, path: Path, value: Any) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temp, path)

    def save_manifest(self, records: list[dict[str, Any]]) -> None:
        self._save(
            self.manifest_path,
            {"generated_at": datetime.now(UTC).isoformat(), "files": records},
        )

    def rebuild_manifest_from_state(self) -> int:
        if self.load_manifest():
            return 0
        records: list[dict[str, Any]] = []
        for key, item in self.load_state().items():
            if not isinstance(item, dict):
                continue
            media_id = str(item.get("media_id") or key)
            if "__" in media_id and not media_id.startswith("pdf_"):
                media_id = media_id.rsplit("__", 1)[-1]
            try:
                media_id = self.validate_media_id(media_id)
            except ValueError:
                continue
            pdf = self._state_path(item.get("pdf"))
            if pdf is None or not pdf.is_file():
                continue
            records.append(
                {
                    "media_id": media_id,
                    "name": str(item.get("name") or media_id),
                    "day": str(item.get("day") or "unknown"),
                    "size": item.get("size") or 0,
                    "md5": str(item.get("md5") or ""),
                    "ts": "",
                    "group_id": str(item.get("group_id") or self._legacy_group_id or IMA_LEGACY_GROUP_ID),
                    "group_name": str(item.get("group_name") or ""),
                }
            )
        if records:
            self.save_manifest(records)
        return len(records)

    def save_group_manifest(self, group_id: str, records: list[dict[str, Any]]) -> None:
        group_id = str(group_id)
        compatibility_group = group_id == IMA_LEGACY_GROUP_ID or group_id.startswith("legacy:")
        if compatibility_group:
            self._legacy_group_id = group_id
        current = self.load_manifest()
        kept = []
        for record in current:
            record_group = str(record.get("group_id") or "")
            if record_group == group_id or (compatibility_group and not record_group):
                continue
            kept.append(record)
        normalized = []
        for record in records:
            item = dict(record)
            if not item.get("group_id"):
                item["group_id"] = group_id
            if compatibility_group and not item.get("group_name"):
                item["group_name"] = self._group_metadata.get(
                    group_id, (IMA_LEGACY_GROUP_NAME, group_id)
                )[0]
            normalized.append(item)
        self.save_manifest(kept + normalized)

    def save_state(self, state: dict[str, dict[str, Any]]) -> None:
        with self._state_lock:
            disk = self._load(self.state_path, {})
            if not isinstance(disk, dict):
                disk = {}
            outgoing: dict[str, dict[str, Any]] = {}
            for key, item in state.items():
                merged = dict(item) if isinstance(item, dict) else {}
                existing = disk.get(key)
                if (
                    isinstance(existing, dict)
                    and not merged.get("abstract_zh")
                    and existing.get("abstract_zh")
                ):
                    merged["abstract_zh"] = existing["abstract_zh"]
                    merged["abstract_src_hash"] = existing.get("abstract_src_hash") or ""
                outgoing[key] = merged
            self._save(self.state_path, outgoing)

    def _state_path(self, relative: Any) -> Path | None:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            return None
        return self._safe_path(relative)

    @staticmethod
    def _tags(state_item: dict[str, Any]) -> list[str]:
        tags = state_item.get("tags")
        if isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
            return list(tags)
        return []

    @staticmethod
    def _file_size(state_item: dict[str, Any], record: dict[str, Any], pdf: Path | None) -> int:
        del pdf
        return int(state_item.get("size") or record.get("size") or 0)

    def is_complete(
        self,
        record: dict[str, Any],
        state: dict[str, dict[str, Any]] | None = None,
    ) -> bool:
        state = state if state is not None else self.load_state()
        item = self._state_item(state, record)
        pdf = self._state_path(item.get("pdf"))
        txt = self._state_path(item.get("txt"))
        return bool(pdf and txt and pdf.is_file() and txt.is_file())

    def catalog_entries(
        self,
        group_id: str = "",
        groups: tuple[ImaGroupConfig, ...] | None = None,
    ) -> list[dict[str, Any]]:
        self._remember_groups(groups)
        requested_group = str(group_id or "").strip()
        allowed_groups = {group.id for group in groups} if groups is not None else None
        output: list[dict[str, Any]] = []
        for record in self.load_manifest(groups):
            media_id = str(record.get("media_id") or "")
            try:
                media_id = self.validate_media_id(media_id)
            except ValueError:
                continue
            if not media_id:
                continue
            actual_group_id = self._record_group_id(record)
            if allowed_groups is not None and actual_group_id not in allowed_groups:
                continue
            if requested_group and actual_group_id != requested_group:
                continue
            output.append(
                {
                    "media_id": media_id,
                    "name": str(record.get("name") or media_id),
                    "day": str(record.get("day") or "unknown"),
                    "group_id": actual_group_id,
                }
            )
        return output

    def group_summary(self, groups: tuple[ImaGroupConfig, ...]) -> list[dict[str, Any]]:
        counts = {group.id: 0 for group in groups if group.enabled}
        for item in self.catalog_entries(groups=groups):
            group_id = str(item.get("group_id") or "")
            if group_id in counts:
                counts[group_id] += 1
        return [
            {"id": group.id, "name": group.name, "count": counts[group.id]}
            for group in groups
            if group.enabled
        ]

    def documents(
        self,
        query: str = "",
        day: str = "",
        group_id: str = "",
        group_name: str = "",
        groups: tuple[ImaGroupConfig, ...] | None = None,
        tag: str = "",
        include_body: bool = True,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self._remember_groups(groups)
        state = self.load_state()
        query = str(query or "").strip().casefold()
        day = str(day or "").strip()
        requested_tag = str(tag or "").strip()
        requested_group = str(group_id or "").strip()
        allowed_groups = {group.id for group in groups} if groups is not None else None
        output: list[dict[str, Any]] = []
        for record in self.load_manifest(groups):
            media_id = str(record.get("media_id") or "")
            try:
                media_id = self.validate_media_id(media_id)
            except ValueError:
                continue
            state_item = self._state_item(state, record)
            if not media_id:
                continue
            if day and str(record.get("day") or "") != day:
                continue
            haystack = f"{record.get('name', '')} {record.get('day', '')} {record.get('abstract', '')}".casefold()
            if query and query not in haystack:
                continue
            tags = self._tags(state_item)
            if requested_tag and requested_tag not in tags:
                continue
            actual_group_id = str(record.get("group_id") or state_item.get("group_id") or self._legacy_group_id or IMA_LEGACY_GROUP_ID)
            if allowed_groups is not None and actual_group_id not in allowed_groups:
                continue
            if requested_group and actual_group_id != requested_group:
                continue
            item = {
                "media_id": media_id,
                "name": str(record.get("name") or media_id),
                "day": str(record.get("day") or "unknown"),
                "size": self._file_size(state_item, record, None),
                "chars": int(state_item.get("chars") or 0),
                "downloaded_at": str(state_item.get("downloaded_at") or ""),
                "tags": tags,
                "has_pdf": bool(state_item.get("pdf")),
                "has_txt": bool(state_item.get("txt")),
            }
            if include_body:
                item["abstract"] = str(record.get("abstract") or "")
                item["cover_url"] = str(record.get("cover_url") or "")
            metadata_id = actual_group_id
            metadata_name = str(group_name or record.get("group_name") or state_item.get("group_name") or "")
            if metadata_id:
                item["group_id"] = metadata_id
            if metadata_name:
                item["group_name"] = metadata_name
            output.append(item)
        output.sort(key=lambda item: (item["day"], item["name"]), reverse=True)
        if limit is not None:
            return output[offset:offset + limit]
        return output

    def document_facets(
        self,
        query: str = "",
        group_id: str = "",
        groups: tuple[ImaGroupConfig, ...] | None = None,
    ) -> dict[str, list[str]]:
        del query
        state = self.load_state()
        days: list[str] = []
        seen_days: set[str] = set()
        tag_counts: dict[str, int] = {}
        document_count = 0
        for item in self.catalog_entries(group_id=group_id, groups=groups):
            document_count += 1
            day = str(item.get("day") or "")
            if day and day not in seen_days:
                seen_days.add(day)
                days.append(day)
            for tag in self._tags(self._state_item(state, item)):
                name = str(tag or "").strip()
                if name:
                    tag_counts[name] = tag_counts.get(name, 0) + 1
        days.sort(reverse=True)
        tags = sorted(tag_counts, key=lambda name: (-tag_counts[name], name))
        return {"days": days, "tags": tags, "tag_counts": tag_counts, "document_count": document_count}

    def document(
        self,
        media_id: str,
        group_id: str = "",
        group_name: str = "",
        groups: tuple[ImaGroupConfig, ...] | None = None,
    ) -> dict[str, Any] | None:
        self._remember_groups(groups)
        self.validate_media_id(media_id)
        state = self.load_state()
        requested_group = str(group_id or "").strip()
        allowed_groups = {group.id for group in groups} if groups is not None else None
        matches: list[dict[str, Any]] = []
        for record in self.load_manifest(groups):
            if str(record.get("media_id") or "") != media_id:
                continue
            state_item = self._state_item(state, record)
            actual_group_id = str(record.get("group_id") or state_item.get("group_id") or self._legacy_group_id or IMA_LEGACY_GROUP_ID)
            if allowed_groups is not None and actual_group_id not in allowed_groups:
                continue
            if requested_group and actual_group_id != requested_group:
                continue
            if not requested_group and allowed_groups is None and not self._is_legacy_group(actual_group_id):
                continue
            pdf = self._state_path(state_item.get("pdf"))
            txt = self._state_path(state_item.get("txt"))
            result = {
                "media_id": media_id,
                "name": str(record.get("name") or media_id),
                "day": str(record.get("day") or "unknown"),
                "pdf": pdf,
                "txt": txt,
                "size": self._file_size(state_item, record, pdf),
                "chars": int(state_item.get("chars") or 0),
                "downloaded_at": str(state_item.get("downloaded_at") or ""),
                "abstract": str(record.get("abstract") or ""),
                "cover_url": str(record.get("cover_url") or ""),
                "tags": self._tags(state_item),
                "has_pdf": bool(pdf and pdf.is_file()),
                "has_txt": bool(txt and txt.is_file()),
            }
            result.update(translation_fields(result["abstract"], state_item))
            metadata_id = str(requested_group or record.get("group_id") or state_item.get("group_id") or "")
            metadata_name = str(group_name or record.get("group_name") or state_item.get("group_name") or "")
            if metadata_id:
                result["group_id"] = metadata_id
            if metadata_name:
                result["group_name"] = metadata_name
            if requested_group:
                return result
            matches.append(result)
        return matches[0] if len(matches) == 1 else None

    def write_abstract_zh(
        self,
        media_id: str,
        group_id: str = "",
        groups: tuple[ImaGroupConfig, ...] | None = None,
        text_zh: str = "",
    ) -> None:
        self._remember_groups(groups)
        self.validate_media_id(media_id)
        state = self.load_state()
        requested_group = str(group_id or "").strip()
        allowed_groups = {group.id for group in groups} if groups is not None else None
        matches: list[dict[str, Any]] = []
        for record in self.load_manifest(groups):
            if str(record.get("media_id") or "") != media_id:
                continue
            state_item = self._state_item(state, record)
            actual_group_id = str(
                record.get("group_id") or state_item.get("group_id") or self._legacy_group_id or IMA_LEGACY_GROUP_ID
            )
            if allowed_groups is not None and actual_group_id not in allowed_groups:
                continue
            if requested_group and actual_group_id != requested_group:
                continue
            if not requested_group and allowed_groups is None and not self._is_legacy_group(actual_group_id):
                continue
            if requested_group:
                matches = [record]
                break
            matches.append(record)
        if len(matches) != 1:
            raise ValueError("document not found")
        record = matches[0]
        key = self.state_key(record)
        src_hash = abstract_src_hash(str(record.get("abstract") or ""))
        with self._state_lock:
            latest = self.load_state()
            item = dict(latest.get(key) or {})
            item["abstract_zh"] = text_zh
            item["abstract_src_hash"] = src_hash
            latest[key] = item
            self._save(self.state_path, latest)


def convert_pdf(pdf: Path, txt: Path) -> int:
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages)
    temp = txt.with_suffix(txt.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, txt)
    return len(text)


def _tag_document(db: Any, record: dict[str, Any], txt: Path | None) -> list[str]:
    from .stock_universe import aliases_for_tagging, names_for_plain_text_tagging
    from .tagging import tag_text

    body = str(record.get("abstract") or "")
    if txt is not None and txt.is_file():
        try:
            body = body + "\n" + txt.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    return tag_text(
        str(record.get("name") or ""),
        body,
        db.get_tag_vocabulary(),
        names_for_plain_text_tagging(db.get_stock_names(), db.get_stock_name_exclusions()),
        aliases_for_tagging(db.get_stock_aliases(), db.get_stock_name_exclusions()),
    )


def ima_kb_valid_tags(db: Any) -> set[str]:
    from .stock_universe import names_for_plain_text_tagging

    valid = {r["tag"] for r in db.get_tag_vocabulary()}
    valid.update(names_for_plain_text_tagging(db.get_stock_names(), db.get_stock_name_exclusions()))
    for alias in db.get_stock_aliases():
        if isinstance(alias, dict) and alias.get("stock"):
            valid.add(str(alias["stock"]))
    return valid


def purge_ima_document_tags(store: ImaDocumentStore, valid_tags: set[str]) -> int:
    state = store.load_state()
    changed = 0
    for item in state.values():
        if not isinstance(item, dict):
            continue
        tags = [t for t in (item.get("tags") or []) if isinstance(t, str)]
        kept = [t for t in tags if t in valid_tags]
        if kept != tags:
            item["tags"] = kept
            changed += 1
    if changed:
        store.save_state(state)
    return changed


class ImaDocumentService:
    def __init__(self, db: Any, archive_root: str | Path):
        self.db = db
        self.store = ImaDocumentStore(archive_root)
        self._stop = threading.Event()
        self._state_lock = threading.Lock()
        self._sync_lock = threading.Lock()
        self._scheduler_thread: threading.Thread | None = None
        self._worker_thread: threading.Thread | None = None
        self._running = False
        self._next_run_at = 0.0
        self._cancel_requested = False

    def config(self) -> ImaDocumentConfig:
        return ImaDocumentConfig.from_db(self.db)

    def status(self) -> dict[str, Any]:
        cfg = self.config()
        with self._state_lock:
            running = self._running
            next_run_at = self._next_run_at
        result = self.db.get_setting(IMA_PURE_LAST_RESULT_KEY) or ""
        try:
            last_result = json.loads(result) if result else None
        except json.JSONDecodeError:
            last_result = None
        return {
            "config": cfg.public(),
            "running": running,
            "next_run_at": int(next_run_at) if next_run_at else 0,
            "last_started_at": self.db.get_setting(IMA_PURE_LAST_STARTED_KEY) or "",
            "last_finished_at": self.db.get_setting(IMA_PURE_LAST_FINISHED_KEY) or "",
            "last_result": last_result,
            "documents": len(self.store.documents()),
        }

    def start(self) -> None:
        try:
            restored = self.store.restore_original_filenames()
            if restored.get("renamed"):
                logger.info("IMA restored %s original filenames", restored["renamed"])
        except Exception:
            logger.exception("IMA original filename restore failed")
        try:
            rebuilt = self.store.rebuild_manifest_from_state()
            if rebuilt:
                logger.info("IMA rebuilt %s manifest records from state", rebuilt)
        except Exception:
            logger.exception("IMA manifest rebuild from state failed")
        try:
            self.retag_all()
        except Exception:
            logger.exception("IMA document retag failed")
        with self._state_lock:
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                return
            self._stop.clear()
            self._scheduler_thread = threading.Thread(
                target=self._schedule_loop, name="ima-documents", daemon=True
            )
            self._scheduler_thread.start()

    def retag_all(self) -> dict[str, int]:
        records = self.store.load_manifest()
        state = self.store.load_state()
        processed = 0
        tagged = 0
        dirty = False
        for record in records:
            try:
                key = self.store.state_key(record)
            except ValueError:
                continue
            item = state.get(key)
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("tags"), list):
                continue
            txt = self.store._state_path(item.get("txt"))
            tags = _tag_document(self.db, record, txt)
            item["tags"] = tags
            state[key] = item
            processed += 1
            if tags:
                tagged += 1
            dirty = True
        if dirty:
            self.store.save_state(state)
        return {"processed": processed, "tagged": tagged}

    def stop(self) -> None:
        self._stop.set()
        self._cancel_requested = True
        scheduler = self._scheduler_thread
        if scheduler and scheduler.is_alive():
            scheduler.join()
        with self._state_lock:
            worker = self._worker_thread
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join()

    def _schedule_loop(self) -> None:
        while not self._stop.wait(30):
            if self._stop.is_set():
                break
            cfg = self.config()
            now = time.time()
            with self._state_lock:
                if not self._next_run_at:
                    self._next_run_at = now + cfg.interval_seconds
                due = now >= self._next_run_at
            if due:
                self.trigger(scheduled=True)

    def trigger(self, scheduled: bool = False) -> dict[str, Any]:
        cfg = self.config()
        if not cfg.configured:
            return {"status": "not_configured"}
        now = time.time()
        with self._state_lock:
            if self._stop.is_set():
                return {"status": "stopped"}
            if self._running:
                return {"status": "already_running"}
            last = self.db.get_setting(IMA_PURE_LAST_STARTED_KEY) or "0"
            try:
                last_started = float(last)
            except ValueError:
                last_started = 0.0
            if not scheduled and last_started and now - last_started < cfg.interval_seconds:
                return {"status": "too_soon", "retry_at": int(last_started + cfg.interval_seconds)}
            self._running = True
            self._cancel_requested = False
            self._next_run_at = now + cfg.interval_seconds
            self._worker_thread = threading.Thread(
                target=self._worker, name="ima-document-sync", daemon=True
            )
            self._worker_thread.start()
        return {"status": "started"}

    def _worker(self) -> None:
        try:
            self.sync_once()
        except Exception as exc:  # noqa: BLE001 - worker must release its lock
            error = _safe_error(exc)
            logger.error("IMA document sync failed error=%s", error)
            self.db.set_setting(
                IMA_PURE_LAST_RESULT_KEY,
                json.dumps({"failed": 1, "last_error": "sync failed"}, ensure_ascii=False),
            )
        finally:
            with self._state_lock:
                self._running = False

    def _sync_group(
        self,
        cfg: ImaDocumentConfig,
        group: ImaGroupConfig,
        state: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            client = ImaPureClient(cfg, group=group)
        except TypeError as exc:
            # Keep third-party/test clients with the original constructor usable.
            if "group" not in str(exc):
                raise
            client = ImaPureClient(cfg)
        records = [
            {
                **record,
                "group_id": str(record.get("group_id") or group.id),
                "group_name": str(record.get("group_name") or group.name),
            }
            for record in client.manifest()
        ]
        if not records:
            existing = [
                record
                for record in self.store.load_manifest()
                if str(record.get("group_id") or IMA_LEGACY_GROUP_ID) == group.id
            ]
            if existing:
                logger.warning("IMA group listing empty, keep existing manifest group=%s", group.id[:64])
                records = existing
            else:
                self.store.save_group_manifest(group.id, records)
        else:
            self.store.save_group_manifest(group.id, records)
        self.store.restore_original_filenames()
        state.clear()
        state.update(self.store.load_state())
        pending = [record for record in records if not self.store.is_complete(record, state)]
        downloaded = 0
        failures = 0
        last_error = ""
        for record in pending:
            if self._cancel_requested:
                break
            media_id = str(record["media_id"])
            state_key = self.store.state_key(record)
            occupied = self.store._occupied_pdfs(state, skip_media_id=state_key)
            pdf = self.store.pdf_path(record, occupied=occupied)
            txt = self.store.txt_path(record, occupied=occupied)
            try:
                pdf.parent.mkdir(parents=True, exist_ok=True)
                if pdf.parent.is_symlink():
                    raise ValueError("archive directory must not be a symlink")
                if pdf.is_file():
                    size, md5 = client._pdf_info(pdf)
                    if record.get("size") and size != int(record["size"]):
                        pdf.unlink(missing_ok=True)
                if not pdf.is_file():
                    media = client.get_media(media_id)
                    result = client.download(media, pdf, int(record.get("size") or 0))
                    size, md5 = result["size"], result["md5"]
                else:
                    size, md5 = client._pdf_info(pdf)
                chars = convert_pdf(pdf, txt)
                key = self.store.state_key(record)
                state[key] = {
                    "group_id": group.id,
                    "group_name": group.name,
                    "day": record.get("day") or "unknown",
                    "name": record.get("name") or media_id,
                    "pdf": str(pdf.relative_to(self.store.root)),
                    "txt": str(txt.relative_to(self.store.root)),
                    "size": size,
                    "md5": md5,
                    "chars": chars,
                    "downloaded_at": datetime.now(UTC).isoformat(),
                }
                try:
                    state[key]["tags"] = _tag_document(self.db, record, txt)
                except Exception:
                    logger.exception("IMA document tag failed media=%s", media_id[:32])
                self.store.save_state(state)
                downloaded += 1
            except Exception as exc:  # noqa: BLE001 - isolate one bad file
                failures += 1
                last_error = _safe_error(exc)
                logger.warning("IMA document failed media=%s error=%s", media_id[:32], last_error)
        return {
            "group_id": group.id,
            "group_name": group.name,
            "total": len(records),
            "pending": len(pending),
            "downloaded": downloaded,
            "failed": failures,
            "last_error": last_error,
        }

    def sync_once(self) -> dict[str, Any]:
        if not self._sync_lock.acquire(blocking=False):
            return {"status": "already_running"}
        try:
            cfg = self.config()
            if not cfg.configured:
                return {"status": "not_configured"}
            started = time.time()
            self.db.set_setting(IMA_PURE_LAST_STARTED_KEY, str(int(started)))
            discovery_error = ""
            discovery_client = ImaPureClient(cfg)
            try:
                discover = getattr(discovery_client, "discover_groups", None)
                discovered = tuple(discover()) if discover else ()
            except Exception as exc:  # noqa: BLE001 - discovery is optional
                discovered = ()
                discovery_error = _safe_error(exc)
                logger.warning("IMA group discovery failed error=%s", discovery_error)
            merged_groups = merge_groups(cfg.groups, discovered)
            self.db.set_setting(
                IMA_PURE_GROUPS_KEY,
                json.dumps([group.public() for group in merged_groups], ensure_ascii=False),
            )
            state = self.store.load_state()
            enabled_groups = [group for group in merged_groups if group.enabled]
            total = pending = downloaded = failures = 0
            failed_groups: list[str] = []
            group_errors: dict[str, str] = {}
            last_error = discovery_error
            succeeded_groups = 0
            for group in enabled_groups:
                try:
                    group_result = self._sync_group(cfg, group, state)
                    succeeded_groups += 1
                    total += group_result["total"]
                    pending += group_result["pending"]
                    downloaded += group_result["downloaded"]
                    failures += group_result["failed"]
                    if group_result["last_error"]:
                        group_errors[group.id] = group_result["last_error"]
                        if not last_error:
                            last_error = group_result["last_error"]
                except Exception as exc:  # noqa: BLE001 - isolate one group
                    failed_groups.append(group.id)
                    failures += 1
                    group_error = _safe_error(exc)
                    group_errors[group.id] = group_error
                    if not last_error:
                        last_error = group_error
                    logger.warning("IMA group failed group=%s error=%s", group.id[:64], group_error)
            result = {
                "groups": len(enabled_groups),
                "succeeded_groups": succeeded_groups,
                "failed_groups": failed_groups,
                "discovery_error": discovery_error,
                "group_errors": group_errors,
                "total": total,
                "pending": pending,
                "downloaded": downloaded,
                "failed": failures,
                "last_error": last_error,
            }
            self.db.set_setting(IMA_PURE_LAST_FINISHED_KEY, str(int(time.time())))
            self.db.set_setting(IMA_PURE_LAST_RESULT_KEY, json.dumps(result, ensure_ascii=False))
            return {"status": "finished", **result}
        finally:
            self._sync_lock.release()
