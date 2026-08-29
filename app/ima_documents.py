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
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import IncompleteRead
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .fetchers.base import CN_TZ
from .fetchers.ima_inspect import item_cover, item_text
from .ima_storage import ImaStorageStatus

logger = logging.getLogger(__name__)
IMA_DOWNLOAD_WORKERS = 4
IMA_LIST_WORKERS = 3
IMA_FOLDER_LIST_MAX_PAGES = 20
IMA_DOWNLOAD_RETRY_DELAYS = (2, 8)
IMA_INDEX_VERSION = 1
IMA_STATE_FLUSH_COUNT = 20
IMA_STATE_FLUSH_SECONDS = 2.0

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
IMA_PURE_DISCOVERY_KEY = "ima_pure_discovery"
IMA_PURE_GROUP_RUNTIME_KEY = "ima_pure_group_runtime"
IMA_LEGACY_GROUP_ID = "legacy"
IMA_LEGACY_GROUP_NAME = "IMA 文档"
IMA_PURE_UID_DEFAULT = "001aa361168019ef"
IMA_PURE_KB_ID_DEFAULT = "7464369361259867"
IMA_PURE_ROOT_FOLDER_DEFAULT = "folder_7489327974078249"
IMA_PURE_INTERVAL_DEFAULT = 3600
IMA_PURE_INTERVAL_MIN = 1800
IMA_PURE_INTERVAL_MAX = 604800
IMA_MOUNT_FOLDER_ID_MAX = 256
IMA_MAX_FOLDER_DEPTH = 32
IMA_MAX_FOLDER_NODES = 10000

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


def _truncate_safe_error(text: str) -> str:
    limit = 240
    markers = list(re.finditer(r"<(?:redacted|url)>", text))
    for marker_match in markers:
        start, end = marker_match.span()
        if start <= limit < end:
            marker = marker_match.group()
            prefix_end = limit - len(marker)
            while True:
                partial = next(
                    (
                        candidate
                        for candidate in markers
                        if candidate.start() < prefix_end < candidate.end()
                    ),
                    None,
                )
                if partial is None:
                    break
                prefix_end = partial.start()
            return text[:prefix_end] + marker
    return text[:limit]


def _safe_error(exc: BaseException) -> str:
    text = (str(exc).splitlines() or [""])[0]
    text = re.sub(r"(?i)(?<![A-Za-z0-9_.-])(set-cookie|cookie)(\s*:\s*)[^\r\n]*", r"\1\2<redacted>", text)
    text = re.sub(r"https?://\S+", "<url>", text)
    text = re.sub(
        r"(?i)(?<![A-Za-z0-9_.-])(authorization\s*[:=]\s*(?:basic|bearer)\s+)[^\s,;&]+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(
        r"""(?i)((?<![A-Za-z0-9_.-])(?P<key_quote>["'])?(?:ima-token|token|refresh_token|access_token|authorization|signature|sig|sign|q-sign|x-ima-cookie|set-cookie|cookie)(?(key_quote)(?P=key_quote))\s*[:=]\s*)(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;&]+)""",
        r"\1<redacted>",
        text,
    )
    def redact_scheme(match: re.Match[str]) -> str:
        prefix = text[: match.start()]
        if re.search(r"(?i)authorization\s*[:=]\s*$", prefix):
            return match.group(0)
        return f"{match.group(1)}<redacted>"

    text = re.sub(
        r"(?i)((?<![A-Za-z0-9_.-])(?:\bbasic|\bbearer)\s+)[^\s,;&]+",
        redact_scheme,
        text,
    )
    return _truncate_safe_error(text)


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


IMA_GROUP_INTERVALS = (3600, 21600, 86400)


def _clamp_group_interval(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 3600
    if number < 10800:
        return 3600
    if number < 43200:
        return 21600
    return 86400


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
    # None means the pre-folder_ids configuration and falls back to root_folder_id.
    folder_ids: tuple[str, ...] | None = None
    interval_seconds: int = 3600

    @property
    def mount_folder_ids(self) -> tuple[str, ...]:
        if self.folder_ids is None:
            return (self.root_folder_id,) if self.enabled and self.root_folder_id else ()
        return self.folder_ids

    def public(self) -> dict[str, Any]:
        folder_ids = list(self.mount_folder_ids)
        return {
            "id": self.id,
            "name": self.name,
            "knowledge_base_id": self.knowledge_base_id,
            "root_folder_id": self.root_folder_id,
            "folder_ids": folder_ids,
            "mounted_folder_count": len(folder_ids),
            "enabled": bool(self.enabled and folder_ids),
            "source": self.source,
            "interval_seconds": self.interval_seconds,
        }


def _normalize_stored_folder_ids(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list) or len(value) > IMA_MOUNT_FOLDER_ID_MAX:
        return None
    output: list[str] = []
    seen: set[str] = set()
    for folder_id in value:
        if not isinstance(folder_id, str):
            return None
        folder_id = folder_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9_:-]{1,128}", folder_id):
            return None
        if folder_id not in seen:
            seen.add(folder_id)
            output.append(folder_id)
    return tuple(output)


_FOLDER_ID_RE = re.compile(r"[A-Za-z0-9_:-]{1,128}")


def _folder_id_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return text if _FOLDER_ID_RE.fullmatch(text) else ""


def ima_folder_id(item: dict[str, Any]) -> str:
    info = item.get("folder_info")
    candidates = (
        info.get("folder_id") if isinstance(info, dict) else None,
        item.get("folder_id"),
        item.get("media_id") if str(item.get("media_id") or "").startswith("folder_") else None,
    )
    for candidate in candidates:
        folder_id = _folder_id_value(candidate)
        if folder_id:
            return folder_id
    return ""


def ima_folder_name(item: dict[str, Any], folder_id: str) -> str:
    info = item.get("folder_info")
    candidates = (
        info.get("name") if isinstance(info, dict) else None,
        item.get("name"),
        item.get("title"),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:200]
    return folder_id


def is_ima_folder_item(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    info = item.get("folder_info")
    if isinstance(info, dict) and _folder_id_value(info.get("folder_id")):
        return True
    if item.get("media_type") == 99:
        return bool(ima_folder_id(item))
    media_id = item.get("media_id")
    if isinstance(media_id, str) and media_id.startswith("folder_"):
        return bool(ima_folder_id(item))
    return bool(ima_folder_id(item)) and not media_id and isinstance(info, (dict, type(None)))


def _count_value(item: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key not in item:
            continue
        value = _optional_int(item.get(key))
        if value is not None:
            return max(0, value)
    return None



def ima_folder_listing_hint(item: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    info = item.get("folder_info") if isinstance(item.get("folder_info"), dict) else {}
    merged = {**info, **item}
    files = _count_value(merged, ("file_number", "file_count"))
    folders = _count_value(merged, ("folder_number", "sub_folder_count", "children_count", "child_count"))
    mtime = _optional_int(merged.get("update_time") or merged.get("last_modify_time"))
    return files, folders, mtime


def _listing_cache_hit(node: dict[str, Any], hint: tuple[int | None, int | None, int | None]) -> bool:
    files, folders, mtime = hint
    if files is not None and folders is not None:
        return files == int(node.get("n_files") or 0) and folders == int(node.get("n_folders") or 0)
    if mtime is not None and node.get("mtime") is not None:
        return int(mtime) == int(node.get("mtime") or 0)
    return False

def ima_folder_children_hint(item: dict[str, Any]) -> bool | None:
    count = _count_value(item, ("folder_number", "sub_folder_count", "children_count", "child_count"))
    return None if count is None else count > 0


def normalize_ima_folder_item(item: dict[str, Any], parent_id: str) -> dict[str, Any] | None:
    if not is_ima_folder_item(item):
        return None
    folder_id = ima_folder_id(item)
    if not folder_id:
        return None
    normalized: dict[str, Any] = {
        "id": folder_id,
        "name": ima_folder_name(item, folder_id),
        "parent_id": parent_id,
        "has_children": ima_folder_children_hint(item),
    }
    folder_count = _count_value(item, ("folder_number", "sub_folder_count"))
    file_count = _count_value(item, ("file_number", "file_count"))
    if folder_count is not None:
        normalized["folder_count"] = folder_count
    if file_count is not None:
        normalized["file_count"] = file_count
    return normalized


def _legacy_group(kb: str, root: str) -> ImaGroupConfig:
    return ImaGroupConfig(
        id=IMA_LEGACY_GROUP_ID,
        name=IMA_LEGACY_GROUP_NAME,
        knowledge_base_id=kb,
        root_folder_id=root,
    )


def _ima_response_status(data: Any, context: str) -> Any:
    if not isinstance(data, dict):
        raise RuntimeError(f"{context} returned invalid response")
    if "code" in data:
        return data["code"]
    if "retcode" in data:
        return data["retcode"]
    raise RuntimeError(f"{context} returned invalid response")


def _ima_success_status(value: Any) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool) and value == 0) or value == "0"


def _discovery_payload(payload: Any) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    return data if isinstance(data, dict) else {}


_DISCOVERY_LIST_FIELDS = (
    "searched_knowledge_bases",
    "knowledge_base_list",
    "knowledge_list",
    "info_list",
)


def _discovery_has_known_shape(payload: Any) -> bool:
    data = _discovery_payload(payload)
    known = False
    for field in _DISCOVERY_LIST_FIELDS:
        if field not in data:
            continue
        known = True
        candidate = data[field]
        if not isinstance(candidate, list) or any(
            not isinstance(item, dict) for item in candidate
        ):
            return False
    if "results" in data:
        known = True
        results = data["results"]
        if not isinstance(results, list):
            return False
        if any(not isinstance(section, dict) for section in results):
            return False
        for section in results:
            if "knowledge_base_list" not in section:
                continue
            items = section["knowledge_base_list"]
            if not isinstance(items, list) or any(
                not isinstance(item, dict) for item in items
            ):
                return False
    return known


def _discovery_page_items(payload: Any) -> list[dict[str, Any]]:
    data = _discovery_payload(payload)
    items: list[dict[str, Any]] = []
    for field in _DISCOVERY_LIST_FIELDS:
        candidate = data.get(field)
        if isinstance(candidate, list) and candidate:
            items.extend(candidate)
            break
    if items:
        return items
    for section in data.get("results") or []:
        items.extend(section.get("knowledge_base_list") or [])
    return items


def _prepare_discovery_item(item: dict[str, Any]) -> dict[str, Any] | None:
    item_type = item.get("type")
    if item_type == 1 and not isinstance(item_type, bool):
        return None
    group_id_value = item.get("id") or item.get("knowledge_base_id")
    if not isinstance(group_id_value, str) or not group_id_value.strip():
        raise RuntimeError("IMA group discovery returned invalid item")
    group_id_value = group_id_value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", group_id_value):
        raise RuntimeError("IMA group discovery returned invalid item")
    basic = item.get("basic_info") if isinstance(item.get("basic_info"), dict) else {}
    name_value = item.get("name") or item.get("kb_name") or basic.get("name") or group_id_value
    root_value = item.get("root_folder_id") or item.get("folder_id") or group_id_value
    if not all(isinstance(value, str) and value.strip() for value in (name_value, root_value)):
        raise RuntimeError("IMA group discovery returned invalid item")
    root_value = root_value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_:-]{1,128}", root_value):
        raise RuntimeError("IMA group discovery returned invalid item")
    prepared = dict(item)
    prepared["id"] = group_id_value.strip()
    prepared["name"] = name_value.strip()
    prepared["root_folder_id"] = root_value.strip()
    return prepared


def normalize_discovered_groups(payload: Any) -> tuple[ImaGroupConfig, ...]:
    if not _discovery_has_known_shape(payload):
        raise RuntimeError("IMA group discovery returned invalid response")
    groups: list[ImaGroupConfig] = []
    for item in _discovery_page_items(payload):
        prepared = _prepare_discovery_item(item)
        if prepared is None:
            continue
        root_value = prepared["root_folder_id"]
        name_value = prepared["name"]
        group_id = prepared["id"]
        groups.append(
            ImaGroupConfig(
                id=group_id,
                name=name_value[:100],
                knowledge_base_id=group_id,
                root_folder_id=root_value,
                source="discovered",
            )
        )
    return tuple(groups)


def merge_groups(
    existing: tuple[ImaGroupConfig, ...],
    discovered: tuple[ImaGroupConfig, ...],
    *,
    discovery_complete: bool = False,
) -> tuple[ImaGroupConfig, ...]:
    by_id = {group.id: group for group in existing}
    kb_to_id = {group.knowledge_base_id: group.id for group in existing}
    discovered_ids: set[str] = set()
    for group in discovered:
        previous = by_id.get(group.id)
        if previous is None:
            previous = by_id.get(kb_to_id.get(group.knowledge_base_id, ""))
        manual = previous is not None and previous.source == "manual"
        target_id = previous.id if previous else group.id
        by_id[target_id] = ImaGroupConfig(
            id=target_id,
            name=previous.name if manual else group.name,
            knowledge_base_id=group.knowledge_base_id,
            root_folder_id=previous.root_folder_id if manual else group.root_folder_id,
            enabled=previous.enabled if previous else False,
            source=previous.source if manual else "discovered",
            folder_ids=previous.folder_ids if previous else (),
            interval_seconds=previous.interval_seconds if previous else 3600,
        )
        discovered_ids.add(target_id)
        kb_to_id[group.knowledge_base_id] = target_id
    if discovery_complete:
        return tuple(
            group
            for group in by_id.values()
            if group.source == "manual" or group.id in discovered_ids
        )
    return tuple(by_id.values())


def _read_groups(db: Any, kb: str, root: str) -> tuple[ImaGroupConfig, ...]:
    raw = db.get_setting(IMA_PURE_GROUPS_KEY) if db is not None else None
    if raw is None:
        return (_legacy_group(kb, root),)
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    if not isinstance(payload, list):
        return ()
    groups: list[ImaGroupConfig] = []
    for item in payload:
        if not isinstance(item, dict):
            return ()
        required_fields = ("id", "name", "knowledge_base_id", "root_folder_id")
        if any(
            not isinstance(item.get(field), str) or not item[field].strip()
            for field in required_fields
        ):
            return ()
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            return ()
        source = item.get("source", "manual")
        if not isinstance(source, str):
            return ()
        folder_ids = None
        if "folder_ids" in item and item["folder_ids"] is not None:
            folder_ids = _normalize_stored_folder_ids(item["folder_ids"])
            if folder_ids is None:
                return ()
            if not enabled:
                folder_ids = ()
        groups.append(
            ImaGroupConfig(
                id=item["id"].strip(),
                name=item["name"].strip()[:100],
                knowledge_base_id=item["knowledge_base_id"].strip(),
                root_folder_id=item["root_folder_id"].strip(),
                enabled=enabled,
                source="discovered" if source == "discovered" else "manual",
                folder_ids=folder_ids,
                interval_seconds=_clamp_group_interval(item.get("interval_seconds")),
            )
        )
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
                folder_ids=group.folder_ids,
                interval_seconds=group.interval_seconds,
            )
        normalized_groups.append(group)
    return tuple(normalized_groups)


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
    def credentials_configured(self) -> bool:
        return bool(self.uid and self.refresh_token)

    @property
    def configured(self) -> bool:
        return bool(
            self.uid
            and self.refresh_token
            and any(
                group.enabled and group.knowledge_base_id and group.mount_folder_ids
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
        self._folder_paths: dict[str, list[str]] = {}

    @property
    def effective_knowledge_base_id(self) -> str:
        if self.group is not None:
            return self.group.knowledge_base_id
        for group in self.config.groups:
            if group.enabled and group.knowledge_base_id and group.mount_folder_ids:
                return group.knowledge_base_id
        return self.config.knowledge_base_id

    @property
    def effective_root_folder_id(self) -> str:
        if self.group is not None:
            return self.group.root_folder_id
        for group in self.config.groups:
            if group.enabled and group.knowledge_base_id and group.mount_folder_ids:
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
        lock = getattr(self, "_token_lock", None)
        if lock is None:
            lock = self._token_lock = threading.Lock()
        with lock:
            if self.token and time.time() - self.token_at < TOKEN_TTL:
                return self.token
            return self.refresh()

    @staticmethod
    def _payload(data: dict[str, Any]) -> dict[str, Any]:
        payload = data.get("data")
        return payload if isinstance(payload, dict) else data

    def _remember_folder_path(self, folder_id: str, payload: dict[str, Any]) -> None:
        current_path = payload.get("current_path")
        if not isinstance(current_path, list):
            return
        names: list[str] = []
        for item in current_path:
            if not isinstance(item, dict):
                continue
            path_folder_id = ima_folder_id(item)
            if not path_folder_id:
                continue
            names.append(ima_folder_name(item, path_folder_id))
            if path_folder_id == folder_id:
                self._folder_paths[folder_id] = names
                return

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
            code = _ima_response_status(data, "IMA group discovery")
            if not _ima_success_status(code):
                raise RuntimeError(f"IMA group discovery failed code={code}")
            payload = _discovery_payload(data)
            if not _discovery_has_known_shape(payload):
                raise RuntimeError("IMA group discovery returned invalid response")
            raw_items.extend(_discovery_page_items(payload))
            if payload.get("is_end") is True or not payload.get("next_cursor"):
                break
            next_cursor = str(payload["next_cursor"])
            if next_cursor in seen_cursors:
                raise RuntimeError("IMA group discovery pagination repeated cursor")
            cursor = next_cursor
        return normalize_discovered_groups({"knowledge_base_list": raw_items})

    def list_items(
        self,
        folder_id: str,
        *,
        folders_only: bool = False,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor = ""
        seen_cursors: set[str] = set()
        pages = 0
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
            status = None
            data = {}
            for attempt in range(4):
                data, _ = self._open_json(request)
                status = _ima_response_status(data, "IMA list")
                if _ima_success_status(status):
                    break
                if status not in (51, 429, 30005) or attempt == 3:
                    raise RuntimeError(f"IMA list failed code={status}")
                time.sleep(1.5 * (attempt + 1))
                request = urllib.request.Request(
                    BASE + "/knowledge_tab_reader/get_knowledge_list",
                    data=json.dumps(body, ensure_ascii=False).encode(),
                    method="POST",
                    headers=self._headers(self._token()),
                )
            payload = self._payload(data)
            if not isinstance(payload, dict):
                raise RuntimeError("IMA list returned invalid response")
            page_items = payload.get("knowledge_list")
            if not isinstance(page_items, list) or any(
                not isinstance(item, dict) for item in page_items
            ):
                raise RuntimeError("IMA list returned invalid response")
            self._remember_folder_path(folder_id, payload)
            if folders_only:
                page_folders = [item for item in page_items if is_ima_folder_item(item)]
                items.extend(page_folders)
                pages += 1
                if not page_folders:
                    return items
            else:
                items.extend(page_items)
                pages += 1
            if max_pages is not None and pages >= max_pages:
                return items
            if not payload.get("next_cursor"):
                return items
            next_cursor = str(payload["next_cursor"])
            if next_cursor in seen_cursors:
                return items
            cursor = next_cursor

    def manifest(self, listing_cache: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        roots = (
            self.group.mount_folder_ids
            if self.group is not None
            else ((self.effective_root_folder_id,) if self.effective_root_folder_id else ())
        )
        queue: list[str] = []
        selected_root_ids = {folder_id for folder_id in roots if folder_id}
        root_by_folder: dict[str, str] = {}
        path_by_folder: dict[str, list[str]] = {}
        depth_by_folder: dict[str, int] = {}
        for folder_id in roots:
            if folder_id and folder_id not in root_by_folder:
                root_by_folder[folder_id] = folder_id
                path_by_folder[folder_id] = []
                depth_by_folder[folder_id] = 0
                queue.append(folder_id)
        visited_folder_ids: set[str] = set()
        queued_folder_ids = set(queue)
        seen_media_ids: set[str] = set()
        queue_index = 0
        listing_cache = listing_cache if listing_cache is not None else {}
        always_list = {folder_id for folder_id in roots if folder_id}
        listing_hints: dict[str, tuple[int | None, int | None, int | None]] = {}
        folder_direct_records: dict[str, list[dict[str, Any]]] = {}
        folder_children: dict[str, list[str]] = {}

        def append_file(
            item: dict[str, Any],
            source_folder_id: str,
            source_root_folder_id: str,
            folder_path: list[str],
        ) -> None:
            if is_ima_folder_item(item):
                return
            media_type = item.get("media_type")
            if media_type is not None and (
                isinstance(media_type, bool) or not isinstance(media_type, int)
            ):
                return
            if media_type == 99:
                return
            media_id_value = item.get("media_id")
            if not isinstance(media_id_value, str) or not media_id_value.strip():
                return
            media_id = media_id_value.strip()
            try:
                media_id = ImaDocumentStore.validate_media_id(media_id)
            except ValueError:
                logger.warning("IMA ignored invalid media id")
                return
            if media_id in seen_media_ids:
                return
            name_value = item.get("name")
            if name_value is not None and not isinstance(name_value, str):
                return
            file_size = _optional_int(item.get("file_size"))
            if file_size is None:
                return
            md5_value = item.get("md5_sum")
            if md5_value is not None and not isinstance(md5_value, str):
                return
            ts_value = item.get("create_time")
            try:
                ts_ms = int(ts_value) if not isinstance(ts_value, bool) else 0
            except (TypeError, ValueError, OverflowError):
                ts_ms = 0
            name = item_display_name(item, media_id)
            if not (name.lower().endswith(".pdf") or media_id.lower().startswith("pdf_")):
                return
            seen_media_ids.add(media_id)
            day = next(
                (value for value in reversed(folder_path) if re.fullmatch(r"\d{4}", value)),
                "",
            )
            if not day and ts_ms > 0:
                try:
                    day = datetime.fromtimestamp(ts_ms / 1000, CN_TZ).strftime("%m%d")
                except (OSError, OverflowError, ValueError):
                    pass
            record = {
                "media_id": media_id,
                "name": name,
                "day": day or "unknown",
                "size": file_size or 0,
                "md5": md5_value or "",
                "ts": str(ts_ms) if ts_ms > 0 else "",
                "abstract": item_text(item)[:2000],
                "cover_url": item_cover(item)[:2000],
                "source_folder_id": source_folder_id,
                "source_root_folder_id": source_root_folder_id,
                "folder_path": list(folder_path),
            }
            if self.group is not None:
                record["group_id"] = self.group.id
                record["group_name"] = self.group.name
            records.append(record)
            folder_direct_records.setdefault(source_folder_id, []).append(record)

        def _ingest(folder_id: str, items: list[dict[str, Any]]) -> None:
            root_folder_id = root_by_folder[folder_id]
            folder_path = path_by_folder[folder_id]
            if not folder_path:
                folder_path = list(self._folder_paths.get(folder_id, folder_path))
                path_by_folder[folder_id] = folder_path
            for item in items:
                if not isinstance(item, dict):
                    continue
                if is_ima_folder_item(item):
                    child_id = ima_folder_id(item)
                    if child_id:
                        child_path = folder_path + [ima_folder_name(item, child_id)]
                        listing_hints[child_id] = ima_folder_listing_hint(item)
                        folder_children.setdefault(folder_id, []).append(child_id)
                        if child_id not in root_by_folder or child_id in selected_root_ids:
                            root_by_folder[child_id] = root_folder_id
                            path_by_folder[child_id] = child_path
                            depth_by_folder[child_id] = depth_by_folder[folder_id] + 1
                            selected_root_ids.discard(child_id)
                        if child_id not in visited_folder_ids and child_id not in queued_folder_ids:
                            queued_folder_ids.add(child_id)
                            queue.append(child_id)
                    continue
                append_file(item, folder_id, root_folder_id, folder_path)

        def _reuse_cached(folder_id: str) -> None:
            pending = [folder_id]
            while pending:
                fid = pending.pop()
                if fid in visited_folder_ids and fid != folder_id:
                    continue
                visited_folder_ids.add(fid)
                node = listing_cache.get(fid) or {}
                for record in node.get("records") or []:
                    if not isinstance(record, dict):
                        continue
                    media_id = str(record.get("media_id") or "")
                    if not media_id or media_id in seen_media_ids:
                        continue
                    seen_media_ids.add(media_id)
                    records.append(record)
                for child in node.get("children") or []:
                    if child not in visited_folder_ids:
                        pending.append(str(child))

        def _remember_listing(folder_id: str, items: list[dict[str, Any]]) -> None:
            n_folders = sum(1 for item in items if isinstance(item, dict) and is_ima_folder_item(item))
            n_files = sum(1 for item in items if isinstance(item, dict) and not is_ima_folder_item(item))
            hint = listing_hints.get(folder_id, (None, None, None))
            listing_cache[folder_id] = {
                "n_files": n_files,
                "n_folders": n_folders,
                "mtime": hint[2],
                "children": list(folder_children.get(folder_id) or []),
                "records": list(folder_direct_records.get(folder_id) or []),
            }

        while queue_index < len(queue):
            batch: list[str] = []
            while queue_index < len(queue) and len(batch) < IMA_LIST_WORKERS:
                folder_id = queue[queue_index]
                queue_index += 1
                if folder_id in visited_folder_ids:
                    continue
                if depth_by_folder[folder_id] > IMA_MAX_FOLDER_DEPTH:
                    raise RuntimeError("IMA folder tree exceeds maximum depth")
                if (
                    folder_id not in always_list
                    and folder_id in listing_cache
                    and _listing_cache_hit(listing_cache[folder_id], listing_hints.get(folder_id, (None, None, None)))
                ):
                    _reuse_cached(folder_id)
                    continue
                visited_folder_ids.add(folder_id)
                if len(visited_folder_ids) > IMA_MAX_FOLDER_NODES:
                    raise RuntimeError("IMA folder tree exceeds maximum size")
                batch.append(folder_id)
            if not batch:
                continue
            if len(batch) == 1:
                items = self.list_items(batch[0])
                _ingest(batch[0], items)
                _remember_listing(batch[0], items)
                continue
            with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                listed = list(pool.map(self.list_items, batch))
            for folder_id, items in zip(batch, listed):
                _ingest(folder_id, items)
                _remember_listing(folder_id, items)
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
        pull_url = os.environ.get("IMA_PULL_URL", "").strip()
        if pull_url:
            archive_root_text = os.environ.get("IMA_ARCHIVE_ROOT", "").strip()
            if not archive_root_text:
                raise RuntimeError("IMA_ARCHIVE_ROOT required when IMA_PULL_URL is set")
            archive_root = Path(archive_root_text).expanduser()
            dest = str(destination.resolve().relative_to(archive_root.resolve()))
            payload = json.dumps(
                {
                    "dest": dest,
                    "url": str(url),
                    "headers": headers,
                    "expected_size": int(expected_size or 0),
                },
                ensure_ascii=False,
            ).encode()
            request = urllib.request.Request(
                pull_url,
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + os.environ.get("IMA_PULL_TOKEN", "").strip(),
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    body = json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"IMA PDF HTTP {exc.code}") from exc
            return {
                "size": int(body.get("size") or 0),
                "md5": str(body.get("md5") or ""),
                "path": str(destination),
            }
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


def _retryable_download_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (TimeoutError, ConnectionError, IncompleteRead, urllib.error.URLError),
    ):
        return True
    text = str(exc)
    if any(
        marker in text
        for marker in (
            "size mismatch",
            "network response failed",
            "returned no signed URL",
            "signed URL missing",
        )
    ):
        return True
    match = re.search(r"HTTP (\d{3})", text)
    return bool(match and (int(match.group(1)) in (403, 408, 409, 425, 429) or int(match.group(1)) >= 500))


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
    _ARCHIVE_MARKER = ".vpush-ima-root"

    def __init__(
        self,
        root: str | Path,
        *,
        archive_root: str | Path | None = None,
        storage_status: ImaStorageStatus | None = None,
    ):
        raw_index = Path(root).expanduser()
        raw_archive = Path(archive_root).expanduser() if archive_root is not None else raw_index
        if raw_archive.exists() and raw_archive.is_symlink():
            raise ValueError("archive root must not be a symlink")
        self.root = raw_index.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.storage_status = storage_status or ImaStorageStatus(None, remote=False)
        self.archive_root = raw_archive.resolve()
        if not self.storage_status.remote:
            self.archive_root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self.state_path = self.root / "state.json"
        self._state_lock = threading.Lock()
        self._manifest_lock = threading.RLock()
        self._legacy_group_id = IMA_LEGACY_GROUP_ID
        self._group_metadata: dict[str, tuple[str, str]] = {
            IMA_LEGACY_GROUP_ID: (IMA_LEGACY_GROUP_NAME, IMA_LEGACY_GROUP_ID)
        }
        self._on_records_changed = None

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
        candidate = (self.archive_root / relative).resolve()
        if candidate == self.archive_root or not candidate.is_relative_to(self.archive_root):
            return None
        return candidate

    def _day_dir(self, day: str) -> Path:
        return self.archive_root / _safe_component(day)

    @staticmethod
    def _collision_token(media_id: str) -> str:
        return hashlib.sha256(media_id.encode("utf-8")).hexdigest()[:8]

    def _marker_present(self) -> bool:
        try:
            return (self.archive_root / self._ARCHIVE_MARKER).is_file()
        except OSError:
            return False

    def archive_readable(self) -> bool:
        if not self.storage_status.remote:
            return True
        return self.storage_status.can_read() and self._marker_present()

    def archive_writable(self) -> bool:
        if not self.storage_status.remote:
            return True
        return self.storage_status.can_write() and self._marker_present()

    def authorized_archive_file(self, relative: Any) -> Path | None:
        """Resolve a stored archive-relative path. Caller must gate on archive_readable()."""
        return self._state_path(relative)

    def _archive_path(self, relative: str) -> Path:
        day_path = self.archive_root / Path(relative).parent
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
                new_pdf = str(desired.relative_to(self.archive_root))
                new_txt = str(desired.with_suffix(".txt").relative_to(self.archive_root))
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
            new_pdf = str(desired.relative_to(self.archive_root))
            occupied.discard(str(current_rel or ""))
            occupied.add(new_pdf)
            item["pdf"] = new_pdf
            item["txt"] = str(desired_txt.relative_to(self.archive_root))
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
        with self._manifest_lock:
            self._save(
                self.manifest_path,
                {"generated_at": datetime.now(UTC).isoformat(), "files": records},
            )

    @property
    def listing_cache_path(self) -> Path:
        return self.root / "listing-cache.json"

    def load_listing_cache(self) -> dict[str, Any]:
        value = self._load(self.listing_cache_path, {})
        return value if isinstance(value, dict) else {}

    def save_listing_cache(self, value: dict[str, Any]) -> None:
        self._save(self.listing_cache_path, value)

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
        with self._manifest_lock:
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

    def _save_state_locked(self, state: dict[str, dict[str, Any]]) -> None:
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

    def save_state(self, state: dict[str, dict[str, Any]]) -> None:
        with self._state_lock:
            self._save_state_locked(state)

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
        *,
        verify_archive: bool = True,
    ) -> bool:
        state = state if state is not None else self.load_state()
        item = self._state_item(state, record)
        pdf_rel = item.get("pdf")
        if not (isinstance(pdf_rel, str) and pdf_rel):
            return False
        if not verify_archive:
            return True
        if not self.archive_readable():
            return True
        pdf = self._state_path(pdf_rel)
        return bool(pdf and pdf.is_file())

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
            name = str(record.get("name") or media_id)
            abstract = str(record.get("abstract") or "")
            tags = self._tags(state_item)
            actual_group_id = str(
                record.get("group_id")
                or state_item.get("group_id")
                or self._legacy_group_id
                or IMA_LEGACY_GROUP_ID
            )
            metadata_name = str(
                group_name
                or record.get("group_name")
                or state_item.get("group_name")
                or self._group_metadata.get(actual_group_id, ("", actual_group_id))[0]
            )
            name_folded = name.casefold()
            tag_text = " ".join(tags).casefold()
            metadata_folded = metadata_name.casefold()
            abstract_folded = abstract.casefold()
            haystack = " ".join((name_folded, str(record.get("day") or ""), tag_text, metadata_folded, abstract_folded))
            if query and query not in haystack:
                continue
            match_rank = 0
            if query:
                if query in name_folded:
                    match_rank = 3
                elif query in tag_text or query in metadata_folded:
                    match_rank = 2
                else:
                    match_rank = 1
            if requested_tag and requested_tag not in tags:
                continue
            if allowed_groups is not None and actual_group_id not in allowed_groups:
                continue
            if requested_group and actual_group_id != requested_group:
                continue
            item = {
                "media_id": media_id,
                "name": name,
                "day": str(record.get("day") or "unknown"),
                "size": self._file_size(state_item, record, None),
                "chars": int(state_item.get("chars") or 0),
                "downloaded_at": str(state_item.get("downloaded_at") or ""),
                "tags": tags,
                "has_pdf": bool(state_item.get("pdf")),
                "has_txt": bool(state_item.get("txt")),
                "_match_rank": match_rank,
            }
            if include_body:
                item["abstract"] = abstract
                item["cover_url"] = str(record.get("cover_url") or "")
            metadata_id = actual_group_id
            if metadata_id:
                item["group_id"] = metadata_id
            if metadata_name:
                item["group_name"] = metadata_name
            output.append(item)
        output.sort(
            key=lambda item: (
                int(item.get("_match_rank") or 0),
                item["day"] != "unknown",
                item["day"],
                item["name"],
            ),
            reverse=True,
        )
        for item in output:
            item.pop("_match_rank", None)
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
            # Remote archives must not be resolved/stat'd for metadata; local keeps Path for callers.
            if self.storage_status.remote:
                pdf = None
                txt = None
            else:
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
                "has_pdf": bool(state_item.get("pdf")),
                "has_txt": bool(state_item.get("txt")),
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
        hook = getattr(self, "_on_records_changed", None)
        if callable(hook):
            hook([record], latest)


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
    with store._state_lock:
        state = store.load_state()
        changed = 0
        changed_keys: list[str] = []
        for key, item in state.items():
            if not isinstance(item, dict):
                continue
            tags = [t for t in (item.get("tags") or []) if isinstance(t, str)]
            kept = [t for t in tags if t in valid_tags]
            if kept != tags:
                item["tags"] = kept
                changed += 1
                changed_keys.append(str(key))
        if changed:
            store._save_state_locked(state)
            hook = getattr(store, "_on_records_changed", None)
            if callable(hook):
                records = [
                    record
                    for record in store.load_manifest()
                    if store.state_key(record) in set(changed_keys)
                ]
                hook(records, state)
    return changed


class ImaDocumentService:
    def __init__(
        self,
        db: Any,
        index_root: str | Path,
        *,
        archive_root: str | Path | None = None,
        storage_status: ImaStorageStatus | None = None,
    ):
        self.db = db
        self.storage_status = storage_status or ImaStorageStatus(None, remote=False)
        self.store = ImaDocumentStore(
            index_root,
            archive_root=archive_root,
            storage_status=self.storage_status,
        )
        self.store._on_records_changed = self._update_index_rows
        self._stop = threading.Event()
        self._state_lock = threading.Lock()
        self._config_lock = threading.RLock()
        self._sync_lock = threading.Lock()
        self._discovery_lock = threading.Lock()
        self._scheduler_thread: threading.Thread | None = None
        self._worker_thread: threading.Thread | None = None
        self._running = False
        self._next_run_at = 0.0
        self._cancel_requested = False
        self._sync_group_id = ""
        self._sync_scheduled = False
        self._progress: dict[str, Any] | None = None

    def _set_progress(self, **fields: Any) -> None:
        with self._state_lock:
            current = dict(self._progress or {})
            current.update(fields)
            self._progress = current

    def _storage_block_status(self) -> str | None:
        if self.store.archive_writable():
            return None
        data = self.storage_status.load()
        status = str(data.get("status") or "")
        if status == "stale":
            return "storage_stale"
        if status == "readonly":
            return "storage_readonly"
        if status == "capacity_blocked":
            return "capacity_blocked"
        return "storage_unavailable"

    @property
    def config_lock(self) -> threading.RLock:
        return self._config_lock

    def config(self) -> ImaDocumentConfig:
        return ImaDocumentConfig.from_db(self.db)

    @staticmethod
    def _discovery_default() -> dict[str, str]:
        return {"status": "never", "at": "", "error": ""}

    def _discovery_status(self) -> dict[str, str]:
        raw = self.db.get_setting(IMA_PURE_DISCOVERY_KEY) or ""
        try:
            value = json.loads(raw) if raw else {}
        except (TypeError, json.JSONDecodeError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        default = self._discovery_default()
        return {
            "status": str(value.get("status") or default["status"]),
            "at": str(value.get("at") or ""),
            "error": str(value.get("error") or ""),
        }

    def _set_settings_atomic(self, values: dict[str, str]) -> None:
        setter = getattr(self.db, "set_settings_atomic", None)
        if callable(setter):
            setter(values)
            return
        for key, value in values.items():
            self.db.set_setting(key, value)

    def discover(self) -> dict[str, Any]:
        cfg = self.config()
        if not cfg.credentials_configured:
            return {
                "ok": False,
                "status": "not_configured",
                "config": cfg.public(),
                "discovery": self._discovery_status(),
            }
        with self._discovery_lock:
            cfg = self.config()
            try:
                client = ImaPureClient(cfg)
                discover = getattr(client, "discover_groups", None)
                discovery_complete = callable(discover)
                discovered = tuple(discover()) if discovery_complete else ()
            except Exception as exc:  # noqa: BLE001 - preserve the last good registry
                error = _safe_error(exc)
                discovery = {
                    "status": "failed",
                    "at": datetime.now(UTC).isoformat(),
                    "error": error,
                }
                with self._config_lock:
                    self.db.set_setting(
                        IMA_PURE_DISCOVERY_KEY,
                        json.dumps(discovery, ensure_ascii=False),
                    )
                return {
                    "ok": False,
                    "status": "failed",
                    "config": self.config().public(),
                    "discovery": discovery,
                }
            with self._config_lock:
                current = self.config()
                merged = merge_groups(
                    current.groups,
                    discovered,
                    discovery_complete=discovery_complete,
                )
                discovery = {
                    "status": "ok",
                    "at": datetime.now(UTC).isoformat(),
                    "error": "",
                }
                self._set_settings_atomic(
                    {
                        IMA_PURE_GROUPS_KEY: json.dumps(
                            [group.public() for group in merged], ensure_ascii=False
                        ),
                        IMA_PURE_DISCOVERY_KEY: json.dumps(discovery, ensure_ascii=False),
                    }
                )
            return {
                "ok": True,
                "status": "finished",
                "config": self.config().public(),
                "discovery": discovery,
            }

    def _source_fingerprint(self) -> str:
        parts = []
        for path in (self.store.manifest_path, self.store.state_path):
            try:
                stat = path.stat()
                parts.append((stat.st_mtime_ns, stat.st_size))
            except OSError:
                parts.append((0, 0))
        return json.dumps(
            {"version": IMA_INDEX_VERSION, "files": parts},
            separators=(",", ":"),
        )

    def _read_source_json(self, path: Path) -> Any:
        try:
            exists = path.is_file()
        except OSError as exc:
            raise RuntimeError(f"unreadable IMA source {path.name}") from exc
        if not exists:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"unreadable IMA source {path.name}") from exc

    def _load_rebuild_sources(
        self, groups: tuple[ImaGroupConfig, ...] | None
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        manifest_value = self._read_source_json(self.store.manifest_path)
        state_value = self._read_source_json(self.store.state_path)
        if isinstance(manifest_value, dict) and isinstance(manifest_value.get("files"), list):
            records = [item for item in manifest_value["files"] if isinstance(item, dict)]
        elif isinstance(manifest_value, list):
            records = [item for item in manifest_value if isinstance(item, dict)]
        else:
            records = []
        state = state_value if isinstance(state_value, dict) else {}
        return self.store._normalize_manifest_records(records, groups), state

    def _index_row(
        self, record: dict[str, Any], state: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        media_id = self.store.validate_media_id(str(record.get("media_id") or ""))
        state_item = self.store._state_item(state, record)
        group_id = self.store._record_group_id(record)
        group_name = str(
            record.get("group_name")
            or state_item.get("group_name")
            or self.store._group_metadata.get(group_id, ("", group_id))[0]
        )
        name = str(record.get("name") or media_id)
        day = str(record.get("day") or "unknown").strip() or "unknown"
        tags = self.store._tags(state_item)
        abstract = str(record.get("abstract") or "")
        pdf_path = str(state_item.get("pdf") or "")
        txt_path = str(state_item.get("txt") or "")
        return {
            "group_id": group_id,
            "media_id": media_id,
            "day": day,
            "valid_day": int(day.isdigit() and len(day) == 4),
            "name": name,
            "group_name": group_name,
            "name_folded": name.casefold(),
            "metadata_folded": f"{group_name} {' '.join(tags)}".casefold(),
            "abstract": abstract,
            "abstract_folded": abstract.casefold(),
            "abstract_zh": str(state_item.get("abstract_zh") or ""),
            "abstract_src_hash": str(state_item.get("abstract_src_hash") or ""),
            "cover_url": str(record.get("cover_url") or ""),
            "tags": tags,
            "size": self.store._file_size(state_item, record, None),
            "chars": int(state_item.get("chars") or 0),
            "has_pdf": int(bool(pdf_path)),
            "has_txt": int(bool(txt_path)),
            "pdf_path": pdf_path,
            "txt_path": txt_path,
            "downloaded_at": str(state_item.get("downloaded_at") or ""),
        }

    def _update_index_rows(
        self,
        records: list[dict[str, Any]],
        state: dict[str, dict[str, Any]],
    ) -> None:
        updater = getattr(self.db, "update_ima_document_batch", None)
        if not callable(updater) or not records:
            return
        rows = []
        for record in records:
            try:
                rows.append(self._index_row(record, state))
            except ValueError:
                continue
        if not rows:
            return
        try:
            updater(rows, self._source_fingerprint())
        except Exception as exc:  # noqa: BLE001
            marker = getattr(self.db, "mark_ima_document_index", None)
            if callable(marker):
                try:
                    marker("failed", error=_safe_error(exc))
                except Exception as mark_exc:  # noqa: BLE001
                    logger.warning(
                        "IMA index failed status write error=%s",
                        _safe_error(mark_exc),
                    )
            logger.warning("IMA index batch update failed error=%s", _safe_error(exc))

    def _replace_group_index(
        self,
        group_id: str,
        records: list[dict[str, Any]],
        state: dict[str, dict[str, Any]],
    ) -> None:
        replacer = getattr(self.db, "replace_ima_document_group", None)
        if not callable(replacer):
            return
        rows = []
        for record in records:
            try:
                rows.append(self._index_row(record, state))
            except ValueError:
                continue
        try:
            replacer(group_id, rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning("IMA index group replace failed error=%s", _safe_error(exc))

    def read_index_status(self) -> dict[str, Any]:
        getter = getattr(self.db, "ima_document_index_meta", None)
        if not callable(getter):
            return {
                "status": "fallback",
                "documents": 0,
                "rebuilt_at": "",
                "duration_ms": 0,
                "error": "",
            }
        meta = getter()
        return {
            "status": str(meta.get("status") or "fallback"),
            "documents": int(meta.get("document_count") or 0),
            "rebuilt_at": str(meta.get("rebuilt_at") or ""),
            "duration_ms": int(meta.get("duration_ms") or 0),
            "error": str(meta.get("error") or ""),
        }

    def _index_usable(self) -> bool:
        page = getattr(self.db, "ima_document_page", None)
        if not callable(page):
            return False
        status = self.read_index_status()
        if status["status"] == "ready":
            return True
        if status["status"] in {"rebuilding", "failed"}:
            counter = getattr(self.db, "ima_document_index_count", None)
            return callable(counter) and int(counter()) > 0
        return False

    def rebuild_read_index(
        self, groups: tuple[ImaGroupConfig, ...] | None = None
    ) -> dict[str, object]:
        started = time.perf_counter()
        marker = getattr(self.db, "mark_ima_document_index", None)
        replacer = getattr(self.db, "replace_ima_document_index", None)
        if not callable(replacer):
            return {
                "status": "fallback",
                "documents": 0,
                "duration_ms": 0,
                "error": "",
            }
        try:
            if groups is not None:
                self.store._remember_groups(groups)
            records, state = self._load_rebuild_sources(groups)
            prepared: dict[tuple[str, str], dict[str, Any]] = {}
            for record in records:
                try:
                    row = self._index_row(record, state)
                except ValueError:
                    continue
                prepared[(row["group_id"], row["media_id"])] = row
            rows = list(prepared.values())
            if callable(marker):
                marker("rebuilding")
            duration_ms = max(int((time.perf_counter() - started) * 1000), 0)
            replacer(rows, self._source_fingerprint(), duration_ms)
            status = self.read_index_status()
            return {
                "status": "ready",
                "documents": status["documents"],
                "duration_ms": status["duration_ms"],
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001 - keep serving the last good index
            error = _safe_error(exc)
            logger.warning("IMA index rebuild failed error=%s", error)
            if callable(marker):
                try:
                    marker("failed", error=error)
                except Exception as mark_exc:  # noqa: BLE001
                    logger.warning(
                        "IMA index failed status write error=%s",
                        _safe_error(mark_exc),
                    )
            return {
                "status": "failed",
                "documents": self.read_index_status()["documents"],
                "duration_ms": max(int((time.perf_counter() - started) * 1000), 0),
                "error": error,
            }

    def _rebuild_index_if_needed(self) -> None:
        getter = getattr(self.db, "ima_document_index_meta", None)
        if not callable(getter):
            return
        meta = getter()
        if (
            str(meta.get("status") or "") == "ready"
            and str(meta.get("fingerprint") or "") == self._source_fingerprint()
        ):
            return
        self.rebuild_read_index()

    def _document_from_index_row(
        self, row: dict[str, Any], group_name: str = ""
    ) -> dict[str, Any]:
        pdf = None
        txt = None
        if not self.storage_status.remote:
            pdf = self.store.authorized_archive_file(row.get("pdf_path"))
            txt = self.store.authorized_archive_file(row.get("txt_path"))
        result = {
            "media_id": row["media_id"],
            "name": row["name"],
            "day": row["day"],
            "pdf": pdf,
            "txt": txt,
            "size": row["size"],
            "chars": row["chars"],
            "downloaded_at": row["downloaded_at"],
            "abstract": row.get("abstract") or "",
            "cover_url": row.get("cover_url") or "",
            "tags": list(row.get("tags") or []),
            "has_pdf": bool(row.get("has_pdf")),
            "has_txt": bool(row.get("has_txt")),
            "group_id": row.get("group_id") or "",
            "group_name": group_name or row.get("group_name") or "",
            "pdf_path": row.get("pdf_path") or "",
            "txt_path": row.get("txt_path") or "",
        }
        result.update(
            translation_fields(
                result["abstract"],
                {
                    "abstract_zh": row.get("abstract_zh") or "",
                    "abstract_src_hash": row.get("abstract_src_hash") or "",
                },
            )
        )
        return result

    def list_documents(
        self,
        groups: tuple[ImaGroupConfig, ...],
        *,
        query: str = "",
        day: str = "",
        group: str = "",
        tag: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if self._index_usable():
            page = self.db.ima_document_page(
                [item.id for item in groups],
                group=group,
                query=query,
                day=day,
                tag=tag,
                limit=limit,
                offset=offset,
            )
            counts = page.get("group_counts") or {}
            page["groups"] = [
                {
                    "id": item.id,
                    "name": item.name,
                    "count": int(counts.get(item.id) or 0),
                }
                for item in groups
            ]
            return page
        page_limit = max(int(limit), 1)
        page_offset = max(int(offset), 0)
        items = self.store.documents(
            query=query,
            day=day,
            group_id=group,
            groups=groups,
            tag=tag,
            include_body=False,
            limit=page_limit + 1,
            offset=page_offset,
        )
        has_more = len(items) > page_limit
        items = items[:page_limit]
        facets = self.store.document_facets(group_id=group, groups=groups)
        summaries = self.store.group_summary(groups)
        return {
            "items": items,
            "days": facets["days"],
            "tags": facets["tags"],
            "tag_counts": facets["tag_counts"],
            "document_count": facets["document_count"],
            "day": str(day or "").strip(),
            "has_more": has_more,
            "offset": page_offset,
            "group_counts": {item["id"]: int(item["count"]) for item in summaries},
            "groups": summaries,
        }

    def catalog_stats(self, groups: tuple[ImaGroupConfig, ...]) -> dict[str, dict]:
        stats_fn = getattr(self.db, "ima_document_catalog_stats", None)
        if self._index_usable() and callable(stats_fn):
            return stats_fn([item.id for item in groups])
        stats: dict[str, dict] = {}
        for item in self.store.catalog_entries(groups=groups):
            group_id = str(item.get("group_id") or "")
            if not group_id:
                continue
            bucket = stats.setdefault(
                group_id,
                {
                    "document_count": 0,
                    "latest_day": "",
                    "latest_title": "",
                    "latest_media_id": "",
                },
            )
            bucket["document_count"] += 1
            day = str(item.get("day") or "")
            if day != "unknown" and day >= str(bucket["latest_day"] or ""):
                bucket["latest_day"] = day
                bucket["latest_title"] = str(item.get("name") or "")
                bucket["latest_media_id"] = str(item.get("media_id") or "")
        return stats

    def document(
        self,
        media_id: str,
        groups: tuple[ImaGroupConfig, ...],
        group: str = "",
        group_name: str = "",
    ) -> dict[str, Any] | None:
        if self._index_usable():
            row = self.db.ima_document_from_index(
                media_id, [item.id for item in groups], group
            )
            if row is None:
                return None
            return self._document_from_index_row(row, group_name)
        return self.store.document(
            media_id,
            group_id=group,
            group_name=group_name,
            groups=groups,
        )

    def status(self) -> dict[str, Any]:
        cfg = self.config()
        with self._state_lock:
            running = self._running
            next_run_at = self._next_run_at
            progress = dict(self._progress) if running and self._progress else None
        result = self.db.get_setting(IMA_PURE_LAST_RESULT_KEY) or ""
        try:
            last_result = json.loads(result) if result else None
        except json.JSONDecodeError:
            last_result = None
        index = self.read_index_status()
        counter = getattr(self.db, "ima_document_index_count", None)
        indexed = int(counter()) if callable(counter) else 0
        if indexed:
            document_count = indexed
        else:
            records = self.store.load_manifest()
            state = self.store.load_state()
            # Remote NFS is_file() over the whole archive blocks the single uvicorn
            # worker (and thus /api/stats, /admin/dashboard, /admin/stats). Trust
            # state paths there; local installs still verify files on disk.
            document_count = sum(
                1
                for record in records
                if self.store.is_complete(
                    record, state, verify_archive=not self.storage_status.remote
                )
            )
        return {
            "config": cfg.public(),
            "running": running,
            "next_run_at": int(next_run_at) if next_run_at else 0,
            "last_started_at": self.db.get_setting(IMA_PURE_LAST_STARTED_KEY) or "",
            "last_finished_at": self.db.get_setting(IMA_PURE_LAST_FINISHED_KEY) or "",
            "last_result": last_result,
            "discovery": self._discovery_status(),
            "documents": document_count,
            "progress": progress,
            "index": index,
        }

    def start(self) -> None:
        def _archive_maintenance() -> None:
            if self.store.archive_writable():
                try:
                    restored = self.store.restore_original_filenames()
                    if restored.get("renamed"):
                        logger.info("IMA restored %s original filenames", restored["renamed"])
                except Exception:
                    logger.exception("IMA original filename restore failed")
            elif self.storage_status.remote:
                logger.warning("IMA archive unavailable; skip filename restore")
            if self.store.archive_readable():
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
            elif self.storage_status.remote:
                logger.warning("IMA archive unavailable; skip manifest rebuild and retag")
            try:
                self._rebuild_index_if_needed()
            except Exception:
                logger.exception("IMA document index rebuild failed")

        # Remote NFS restore/retag can take minutes; do not block /healthz.
        if self.storage_status.remote:
            threading.Thread(
                target=_archive_maintenance, name="ima-archive-maintenance", daemon=True
            ).start()
        else:
            _archive_maintenance()
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
        changed_records: list[dict[str, Any]] = []
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
            changed_records.append(record)
        if dirty:
            self.store.save_state(state)
            self._update_index_rows(changed_records, state)
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
                    self._next_run_at = now + self._scheduled_delay(cfg)
                due = now >= self._next_run_at
            if due:
                self.trigger(scheduled=True)

    def _mounted_groups(self, cfg: ImaDocumentConfig | None = None) -> list[ImaGroupConfig]:
        groups = (cfg or self.config()).groups
        return [group for group in groups if group.enabled and group.mount_folder_ids]

    def _scheduled_delay(self, cfg: ImaDocumentConfig | None = None) -> int:
        mounted = self._mounted_groups(cfg)
        return max(1800, min((group.interval_seconds for group in mounted), default=3600))

    def _group_runtime(self) -> dict[str, Any]:
        raw = self.db.get_setting(IMA_PURE_GROUP_RUNTIME_KEY) or "{}"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _mark_group_runtime(self, group_id: str, *, started: bool) -> None:
        data = self._group_runtime()
        raw_item = data.get(group_id)
        item = dict(raw_item) if isinstance(raw_item, dict) else {}
        now = int(time.time())
        if started:
            item["last_started_at"] = now
        else:
            item["last_finished_at"] = now
        data[group_id] = item
        self.db.set_setting(IMA_PURE_GROUP_RUNTIME_KEY, json.dumps(data, ensure_ascii=False))

    def _group_due(self, group: ImaGroupConfig, now: float) -> bool:
        item = self._group_runtime().get(group.id) or {}
        if not isinstance(item, dict):
            item = {}
        try:
            last = float(item.get("last_started_at") or 0)
        except (TypeError, ValueError):
            last = 0.0
        return (now - last) >= _clamp_group_interval(group.interval_seconds)

    def trigger(self, scheduled: bool = False, group_id: str = "") -> dict[str, Any]:
        cfg = self.config()
        if not cfg.credentials_configured:
            return {"status": "not_configured"}
        blocked = self._storage_block_status()
        if blocked:
            return {"status": blocked}
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
            if (
                not group_id
                and not scheduled
                and last_started
                and now - last_started < cfg.interval_seconds
            ):
                return {"status": "too_soon", "retry_at": int(last_started + cfg.interval_seconds)}
            if scheduled:
                self._next_run_at = now + self._scheduled_delay(cfg)
                if not any(self._group_due(group, now) for group in self._mounted_groups(cfg)):
                    return {"status": "not_due"}
            else:
                self._next_run_at = now + cfg.interval_seconds
            self._running = True
            self._cancel_requested = False
            self._sync_group_id = group_id
            self._sync_scheduled = scheduled
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
                self._sync_group_id = ""
                self._sync_scheduled = False
                self._progress = None

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
        listing_all = self.store.load_listing_cache()
        listing_cache = dict(listing_all.get(group.id) or {})
        self._set_progress(
            group_id=group.id,
            group_name=group.name,
            phase="listing",
            listed=0,
            pending=0,
            downloaded=0,
            failed=0,
        )
        try:
            listed = client.manifest(listing_cache=listing_cache)
        except TypeError as exc:
            if "listing_cache" not in str(exc):
                raise
            listed = client.manifest()
        else:
            listing_all[group.id] = listing_cache
            self.store.save_listing_cache(listing_all)
        records = [
            {
                **record,
                "group_id": str(record.get("group_id") or group.id),
                "group_name": str(record.get("group_name") or group.name),
            }
            for record in listed
        ]
        with self._config_lock:
            current_group = next(
                (item for item in self.config().groups if item.id == group.id),
                None,
            )
            if current_group is None or (
                current_group.id,
                current_group.enabled,
                current_group.knowledge_base_id,
                current_group.root_folder_id,
                current_group.mount_folder_ids,
            ) != (
                group.id,
                group.enabled,
                group.knowledge_base_id,
                group.root_folder_id,
                group.mount_folder_ids,
            ):
                return {
                    "group_id": group.id,
                    "group_name": group.name,
                    "total": 0,
                    "pending": 0,
                    "downloaded": 0,
                    "failed": 0,
                    "last_error": "",
                    "skipped": True,
                }
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
        self._set_progress(
            group_id=group.id,
            group_name=group.name,
            phase="listing",
            listed=len(records),
            pending=0,
            downloaded=0,
            failed=0,
        )
        if not self.storage_status.remote:
            self.store.restore_original_filenames()
        state.clear()
        state.update(self.store.load_state())
        self._replace_group_index(group.id, records, state)
        pending = [
            record
            for record in records
            if not self.store.is_complete(
                record, state, verify_archive=not self.storage_status.remote
            )
        ]
        self._set_progress(phase="download", pending=len(pending), downloaded=0, failed=0)
        downloaded = 0
        failures = 0
        last_error = ""
        occupied = self.store._occupied_pdfs(state)
        jobs: list[tuple[dict[str, Any], Path]] = []
        for record in pending:
            pdf = self.store.pdf_path(record, occupied=occupied)
            jobs.append((record, pdf))
            occupied.add(str(pdf.relative_to(self.store.archive_root)))

        def _fetch(record: dict[str, Any], pdf: Path) -> tuple[dict[str, Any], Path, int, str]:
            if self._cancel_requested:
                raise RuntimeError("cancelled")
            blocked = self._storage_block_status()
            if blocked:
                raise RuntimeError(blocked)
            media_id = str(record["media_id"])
            pull_url = os.environ.get("IMA_PULL_URL", "").strip()
            if not pull_url:
                pdf.parent.mkdir(parents=True, exist_ok=True)
            if pdf.parent.is_symlink():
                raise ValueError("archive directory must not be a symlink")
            if (not pull_url) and pdf.is_file():
                size, md5 = client._pdf_info(pdf)
                if not record.get("size") or size == int(record["size"]):
                    return record, pdf, int(size), str(md5)
                pdf.unlink(missing_ok=True)
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    media = client.get_media(media_id)
                    result = client.download(media, pdf, int(record.get("size") or 0))
                    return record, pdf, int(result["size"]), str(result["md5"])
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    retryable = _retryable_download_error(exc)
                    if not retryable or attempt == 2:
                        logger.warning(
                            "IMA PDF failed media=%s group=%s attempt=%s/3 retryable=%s error=%s",
                            media_id[:64],
                            group.id[:64],
                            attempt + 1,
                            retryable,
                            _safe_error(exc),
                        )
                        raise
                    logger.warning(
                        "IMA PDF retry media=%s group=%s attempt=%s/3 error=%s",
                        media_id[:64],
                        group.id[:64],
                        attempt + 1,
                        _safe_error(exc),
                    )
                    time.sleep(IMA_DOWNLOAD_RETRY_DELAYS[attempt])
            raise last_error  # pragma: no cover - loop either returns or raises

        workers = 1 if len(jobs) < 2 else IMA_DOWNLOAD_WORKERS
        dirty_records: dict[str, dict[str, Any]] = {}
        last_flush = time.monotonic()

        def flush() -> None:
            nonlocal last_flush
            if not dirty_records:
                return
            self.store.save_state(state)
            self._update_index_rows(list(dirty_records.values()), state)
            dirty_records.clear()
            last_flush = time.monotonic()

        def should_flush() -> bool:
            return len(dirty_records) >= IMA_STATE_FLUSH_COUNT or (
                time.monotonic() - last_flush
            ) >= IMA_STATE_FLUSH_SECONDS

        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                pending_futures = {
                    pool.submit(_fetch, record, pdf) for record, pdf in jobs
                }
                while pending_futures:
                    if self._cancel_requested:
                        break
                    remaining = max(
                        0.0,
                        IMA_STATE_FLUSH_SECONDS - (time.monotonic() - last_flush),
                    )
                    done, pending_futures = wait(
                        pending_futures,
                        timeout=remaining,
                        return_when=FIRST_COMPLETED,
                    )
                    if not done:
                        if dirty_records:
                            flush()
                        else:
                            last_flush = time.monotonic()
                        continue
                    for future in done:
                        try:
                            record, pdf, size, md5 = future.result()
                            media_id = str(record["media_id"])
                            key = self.store.state_key(record)
                            state[key] = {
                                "group_id": group.id,
                                "group_name": group.name,
                                "day": record.get("day") or "unknown",
                                "name": record.get("name") or media_id,
                                "pdf": str(pdf.relative_to(self.store.archive_root)),
                                "txt": "",
                                "size": size,
                                "md5": md5,
                                "chars": 0,
                                "downloaded_at": datetime.now(UTC).isoformat(),
                            }
                            try:
                                state[key]["tags"] = _tag_document(self.db, record, None)
                            except Exception:
                                logger.exception(
                                    "IMA document tag failed media=%s", media_id[:32]
                                )
                            dirty_records[key] = record
                            downloaded += 1
                            self._set_progress(downloaded=downloaded)
                            if should_flush():
                                flush()
                        except Exception as exc:  # noqa: BLE001 - isolate one bad file
                            failures += 1
                            self._set_progress(failed=failures)
                            last_error = _safe_error(exc)
        finally:
            flush()
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
            requested = ""
            scheduled_flag = False
            with self._state_lock:
                requested = self._sync_group_id
                self._sync_group_id = ""
                scheduled_flag = self._sync_scheduled
                self._sync_scheduled = False
            cfg = self.config()
            if not cfg.credentials_configured:
                return {"status": "not_configured"}
            blocked = self._storage_block_status()
            if blocked:
                return {"status": blocked}
            started = time.time()
            self.db.set_setting(IMA_PURE_LAST_STARTED_KEY, str(int(started)))
            discovery_result = self.discover()
            discovery = discovery_result.get("discovery") or {}
            discovery_error = str(discovery.get("error") or "")
            cfg = self.config()
            state = self.store.load_state()
            enabled_groups = [
                group for group in cfg.groups if group.enabled and group.mount_folder_ids
            ]
            if requested:
                enabled_groups = [group for group in enabled_groups if group.id == requested]
            elif scheduled_flag:
                now = time.time()
                enabled_groups = [group for group in enabled_groups if self._group_due(group, now)]
            skipped_groups = [group.id for group in cfg.groups if group not in enabled_groups]
            total = pending = downloaded = failures = 0
            failed_groups: list[str] = []
            group_errors: dict[str, str] = {}
            last_error = discovery_error
            succeeded_groups = 0
            for group in enabled_groups:
                try:
                    self._mark_group_runtime(group.id, started=True)
                    try:
                        group_result = self._sync_group(cfg, group, state)
                    finally:
                        self._mark_group_runtime(group.id, started=False)
                    if group_result.get("skipped"):
                        skipped_groups.append(group.id)
                        continue
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
                "skipped_groups": skipped_groups,
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
