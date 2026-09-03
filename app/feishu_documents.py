"""Feishu Wiki/Docx collection, OAuth, and timeline normalization."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlencode, urlparse

import httpx

from .config import FeishuDocumentsConfig
from .ima_documents import ImaGroupConfig, archive_lock

logger = logging.getLogger(__name__)

FEISHU_API = "https://open.feishu.cn/open-apis"
FEISHU_AUTHORIZE = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
MAX_MEDIA_BYTES = 50 * 1024 * 1024
MAX_DOCUMENT_MEDIA_BYTES = 250 * 1024 * 1024
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_TIME_RE = re.compile(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s+(\d{1,2}):(\d{2})(?!\d)")
_SPEAKER_RE = re.compile(r"^([^：:\n]{1,40}?)(?:\s+回复\s+([^：:\n]{1,40}?))?[：:]\s*(.*)$", re.S)
_SUPPORTED_HOSTS = ("feishu.cn", "larksuite.com")


class FeishuDocumentError(RuntimeError):
    def __init__(self, message: str, *, code: int = 0, auth_required: bool = False):
        super().__init__(message)
        self.code = int(code or 0)
        self.auth_required = bool(auth_required)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def parse_feishu_document_url(url: str) -> dict[str, str]:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not any(host == suffix or host.endswith("." + suffix) for suffix in _SUPPORTED_HOSTS):
        raise ValueError("只支持飞书或 Lark 的 HTTPS 文档链接")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0] not in {"wiki", "docx"} or not _TOKEN_RE.fullmatch(parts[1]):
        raise ValueError("链接必须是 /wiki/{token} 或 /docx/{token}")
    source_type, token = parts
    canonical = f"https://{host}/{source_type}/{token}"
    source_key = f"{host}:{source_type}:{token}"
    digest = hashlib.sha256(source_key.encode()).hexdigest()[:20]
    return {
        "host": host,
        "source_type": source_type,
        "source_token": token,
        "canonical_url": canonical,
        "source_key": source_key,
        "group_id": f"feishu-{digest}",
        "media_id": f"fs{digest}",
    }


def _walk_values(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def block_text(block: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in _walk_values(block):
        text_run = item.get("text_run")
        if isinstance(text_run, dict) and text_run.get("content"):
            parts.append(str(text_run["content"]))
            continue
        equation = item.get("equation")
        if isinstance(equation, dict) and equation.get("content"):
            parts.append(str(equation["content"]))
    if parts:
        return "".join(parts).strip()
    # API shapes for title/file/callout blocks do not always use text_run.
    for key in ("content", "title", "name"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def block_asset_tokens(block: dict[str, Any]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in _walk_values(block):
        for field, kind in (("image", "image"), ("file", "file"), ("media", "file")):
            media = item.get(field)
            if not isinstance(media, dict):
                continue
            token = str(media.get("token") or media.get("file_token") or "").strip()
            if not token or token in seen or not _TOKEN_RE.fullmatch(token):
                continue
            seen.add(token)
            output.append({
                "token": token,
                "name": str(media.get("name") or media.get("file_name") or "").strip()[:200],
                "kind": kind,
            })
    return output


def _table_item(
    block: dict[str, Any], blocks_by_id: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any] | None, set[str]]:
    table = block.get("table")
    if not isinstance(table, dict):
        return None, set()
    prop = table.get("property") if isinstance(table.get("property"), dict) else {}
    try:
        rows = int(prop.get("row_size") or 0)
        columns = int(prop.get("column_size") or 0)
    except (TypeError, ValueError):
        return None, set()
    cell_ids = [str(item) for item in table.get("cells") or [] if str(item)]
    if rows <= 0 or columns <= 0 or rows * columns != len(cell_ids):
        return None, set()

    consumed = set(cell_ids)
    cells: list[list[dict[str, Any]]] = []
    for row_index in range(rows):
        row: list[dict[str, Any]] = []
        for cell_id in cell_ids[row_index * columns:(row_index + 1) * columns]:
            cell = blocks_by_id.get(cell_id) or {}
            child_ids = [str(item) for item in cell.get("children") or [] if str(item)]
            consumed.update(child_ids)
            children = [blocks_by_id[item] for item in child_ids if item in blocks_by_id]
            text = "\n".join(filter(None, (block_text(item) for item in children)))
            if not text:
                text = block_text(cell)
            assets = [asset for item in (children or [cell]) for asset in block_asset_tokens(item)]
            value: dict[str, Any] = {"text": text}
            if assets:
                value["assets"] = assets
            row.append(value)
        cells.append(row)
    return {
        "type": "table",
        "block_id": str(block.get("block_id") or ""),
        "rows": cells,
        "columns": columns,
    }, consumed


def normalize_timeline(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    notices: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    blocks_by_id = {
        str(block.get("block_id")): block
        for block in blocks
        if isinstance(block, dict) and block.get("block_id")
    }
    consumed_table_blocks: set[str] = set()

    for position, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("block_id") or "")
        if block_id in consumed_table_blocks:
            continue
        table_item, consumed = _table_item(block, blocks_by_id)
        if table_item is not None:
            consumed_table_blocks.update(consumed)
            if current is None:
                notices.append(table_item)
            else:
                current["blocks"].append(table_item)
            continue
        text = block_text(block)
        assets = block_asset_tokens(block)
        match = _TIME_RE.search(text)
        if match:
            year, month, day, hour, minute = (int(part) for part in match.groups())
            timestamp = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+08:00"
            stable = block_id or hashlib.sha256(f"{position}:{timestamp}:{text}".encode()).hexdigest()[:20]
            current = {
                "id": stable,
                "timestamp": timestamp,
                "day": timestamp[:10],
                "time": timestamp[11:16],
                "blocks": [],
            }
            entries.append(current)
            remainder = (text[:match.start()] + text[match.end():]).strip()
            if remainder or assets:
                item: dict[str, Any] = {
                    "type": "text" if remainder else "asset",
                    "text": remainder,
                    "block_id": block_id,
                }
                if assets:
                    item["assets"] = assets
                current["blocks"].append(item)
            continue

        item: dict[str, Any] = {
            "type": "text" if text else "asset",
            "text": text,
            "block_id": block_id,
            "block_type": int(block.get("block_type") or 0),
        }
        if assets:
            item["assets"] = assets
        speaker = _SPEAKER_RE.match(text)
        if speaker:
            item["speaker"] = speaker.group(1).strip()
            item["reply_to"] = (speaker.group(2) or "").strip()
            item["text"] = speaker.group(3).strip()
        if not text and not assets:
            continue
        if current is None:
            notices.append(item)
        else:
            current["blocks"].append(item)

    return {"notices": notices, "entries": entries}


def source_display_title(source: dict[str, Any], fallback: str = "飞书文档") -> str:
    """展示名优先：管理员自定义 display_name > 飞书标题 > fallback。"""
    return (
        str(source.get("display_name") or "").strip()
        or str(source.get("title") or "").strip()
        or fallback
    )


def timeline_plain_text(title: str, timeline: dict[str, Any]) -> str:
    lines = [str(title or "").strip()]
    for item in timeline.get("notices") or []:
        if item.get("text"):
            lines.append(str(item["text"]))
    for entry in timeline.get("entries") or []:
        lines.append(str(entry.get("timestamp") or ""))
        for item in entry.get("blocks") or []:
            if item.get("type") == "table":
                for row in item.get("rows") or []:
                    lines.append("\t".join(str(cell.get("text") or "") for cell in row))
                continue
            prefix = str(item.get("speaker") or "")
            if item.get("reply_to"):
                prefix += f" 回复 {item['reply_to']}"
            text = str(item.get("text") or "")
            lines.append(f"{prefix}：{text}" if prefix else text)
    return "\n".join(line for line in lines if line).strip() + "\n"


class FeishuDocumentClient:
    def __init__(self, app_id: str, app_secret: str, redirect_uri: str, scopes: str, client: httpx.Client | None = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.client = client or httpx.Client(timeout=20)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def authorization_url(self, state: str, code_challenge: str = "") -> str:
        params = {
            "client_id": self.app_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state,
        }
        if code_challenge:
            params.update({
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            })
        return FEISHU_AUTHORIZE + "?" + urlencode(params)

    def exchange_code(self, code: str, code_verifier: str = "") -> dict[str, Any]:
        body = {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri}
        if code_verifier:
            body["code_verifier"] = code_verifier
        return self._token(body)

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        return self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def _token(self, body: dict[str, str]) -> dict[str, Any]:
        payload = {"client_id": self.app_id, "client_secret": self.app_secret, **body}
        response = self.client.post(f"{FEISHU_API}/authen/v2/oauth/token", json=payload)
        data = self._json(response)
        if response.status_code >= 400 or data.get("code") not in (None, 0):
            detail = str(data.get("error_description") or data.get("error") or "")[:160]
            raise FeishuDocumentError(
                f"飞书授权失败（{data.get('code') or response.status_code}: {detail}）",
                code=int(data.get("code") or response.status_code),
                auth_required=True,
            )
        return data.get("data") if isinstance(data.get("data"), dict) else data

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise FeishuDocumentError("飞书返回了无效数据", code=response.status_code) from exc
        return data if isinstance(data, dict) else {}

    def get(
        self,
        path: str,
        access_token: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(3):
            response = self.client.get(
                f"{FEISHU_API}{path}",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            data = self._json(response)
            code = int(data.get("code") or 0)
            if response.status_code != 429 and code not in {99991400, 99991401}:
                break
            if attempt == 2:
                raise FeishuDocumentError("飞书请求过于频繁", code=code or 429)
            retry_after = response.headers.get("retry-after", "")
            try:
                delay = min(max(float(retry_after), 0.5), 4.0)
            except ValueError:
                delay = float(2**attempt)
            time.sleep(delay)
        if response.status_code == 401 or code in {99991661, 99991663, 99991668}:
            raise FeishuDocumentError(
                "飞书授权已失效", code=code or response.status_code, auth_required=True
            )
        if response.status_code >= 400 or code:
            message = "飞书资源无访问权限" if response.status_code == 403 else "飞书文档读取失败"
            raise FeishuDocumentError(message, code=code or response.status_code)
        return data.get("data") if isinstance(data.get("data"), dict) else data

    def resolve_document(self, source: dict[str, Any], access_token: str) -> str:
        if source["source_type"] == "docx":
            return str(source["source_token"])
        data = self.get("/wiki/v2/spaces/get_node", access_token, {"token": source["source_token"]})
        node = data.get("node") if isinstance(data.get("node"), dict) else data
        if str(node.get("obj_type") or "") != "docx":
            raise FeishuDocumentError("当前仅支持飞书新版文档")
        token = str(node.get("obj_token") or "")
        if not token:
            raise FeishuDocumentError("Wiki 节点没有对应文档")
        return token

    def document_meta(self, document_id: str, access_token: str) -> dict[str, Any]:
        data = self.get(f"/docx/v1/documents/{document_id}", access_token)
        document = data.get("document") if isinstance(data.get("document"), dict) else data
        return {
            "document_id": document_id,
            "title": str(document.get("title") or "飞书文档").strip()[:200],
            "revision_id": str(document.get("revision_id") or "-1"),
        }

    def blocks(self, document_id: str, revision_id: str, access_token: str) -> list[dict[str, Any]]:
        # 飞书对显式历史 revision 返回 403/1770032（forBidden），只能读最新版；
        # revision 仅用于变更检测，读取瞬间文档又更新时下一轮同步自愈收敛。
        output: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self.get(f"/docx/v1/documents/{document_id}/blocks", access_token, params)
            output.extend(item for item in data.get("items") or [] if isinstance(item, dict))
            if not data.get("has_more"):
                return output
            page_token = str(data.get("page_token") or "")
            if not page_token:
                raise FeishuDocumentError("飞书文档分页游标缺失")

    def download_media(self, token: str, access_token: str) -> tuple[bytes, str, str]:
        response = self.client.get(
            f"{FEISHU_API}/drive/v1/medias/{token}/download",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise FeishuDocumentError(
                "飞书媒体下载失败",
                code=response.status_code,
                auth_required=response.status_code == 401,
            )
        try:
            declared = int(response.headers.get("content-length") or 0)
        except ValueError:
            declared = 0
        if declared > MAX_MEDIA_BYTES or len(response.content) > MAX_MEDIA_BYTES:
            raise FeishuDocumentError("飞书媒体文件超过 50 MB 限制")
        mime = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
        disposition = response.headers.get("content-disposition", "")
        return response.content, mime, disposition


class FeishuDocumentSyncService:
    def __init__(self, db, config, archive_root: Path, ima_documents=None, client: FeishuDocumentClient | None = None):
        self.db = db
        self.base_config = config
        self.archive_root = Path(archive_root)
        self.ima_documents = ima_documents
        self._owns_client = client is None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sync_lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self.config = self._merged_config()
        self.client = client or FeishuDocumentClient(
            self.config.app_id, self.config.app_secret,
            self.config.redirect_uri, self.config.scopes,
        )

    def _merged_config(self) -> FeishuDocumentsConfig:
        """DB 设置（设置页保存）优先于环境变量；密钥解密后合并。"""
        stored: dict[str, str] = {}
        getter = getattr(self.db, "get_feishu_docs_settings", None)
        if callable(getter):
            try:
                stored = getter()
            except Exception:
                logger.exception("Feishu docs settings load failed")
        try:
            interval = int(stored.get("interval_seconds") or 0)
        except (TypeError, ValueError):
            interval = 0
        base = self.base_config
        return FeishuDocumentsConfig(
            app_id=str(stored.get("app_id") or "").strip() or base.app_id,
            app_secret=str(stored.get("app_secret") or "").strip() or base.app_secret,
            redirect_uri=str(stored.get("redirect_uri") or "").strip() or base.redirect_uri,
            scopes=str(stored.get("scopes") or "").strip() or base.scopes,
            interval_seconds=interval if interval >= 15 else base.interval_seconds,
        )

    def reload_config(self) -> None:
        self.config = self._merged_config()
        self.client.app_id = self.config.app_id
        self.client.app_secret = self.config.app_secret
        self.client.redirect_uri = self.config.redirect_uri
        self.client.scopes = self.config.scopes

    @property
    def configured(self) -> bool:
        return bool(self.config.app_id and self.config.app_secret and self.config.redirect_uri and self.db.credential_key)

    def start(self) -> None:
        if not self.configured or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="feishu-documents")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        if self._owns_client:
            self.client.close()

    def _run(self) -> None:
        try:
            self.recover_read_models()
        except Exception:
            logger.exception("Feishu document read model recovery failed")
        while not self._stop.is_set():
            try:
                self.sync_all()
            except Exception:
                logger.exception("Feishu document sync loop failed")
            self._stop.wait(max(int(self.config.interval_seconds), 15))

    def oauth_start(self, user_id: int) -> str:
        if not self.configured:
            raise FeishuDocumentError("飞书文档应用尚未配置")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode("ascii")
        self.db.create_feishu_oauth_session(
            hashlib.sha256(state.encode()).hexdigest(),
            user_id,
            int(time.time()) + 600,
            verifier,
        )
        return self.client.authorization_url(state, challenge)

    def oauth_callback(self, state: str, code: str) -> int:
        session = self.db.consume_feishu_oauth_session(hashlib.sha256(state.encode()).hexdigest(), int(time.time()))
        if session is None:
            raise FeishuDocumentError("飞书授权请求已过期或已使用")
        admin = self.db.get_user(int(session["user_id"]))
        if admin is None or not admin.get("is_admin"):
            raise FeishuDocumentError("授权发起账号不是管理员")
        token = self.client.exchange_code(code, str(session.get("code_verifier") or ""))
        self.db.save_feishu_oauth_credential(token)
        return int(session["user_id"])

    def _access_token(self, *, force_refresh: bool = False) -> str:
        credential = self.db.get_feishu_oauth_credential(decrypt=True)
        if not credential:
            raise FeishuDocumentError("请先授权飞书文档", auth_required=True)
        if not force_refresh and int(credential.get("expires_at") or 0) > int(time.time()) + 60:
            return str(credential["access_token"])
        with self._refresh_lock:
            credential = self.db.get_feishu_oauth_credential(decrypt=True)
            if not force_refresh and int(credential.get("expires_at") or 0) > int(time.time()) + 60:
                return str(credential["access_token"])
            refresh_token = str(credential.get("refresh_token") or "")
            if not refresh_token or (
                int(credential.get("refresh_expires_at") or 0)
                and int(credential.get("refresh_expires_at") or 0) <= int(time.time())
            ):
                raise FeishuDocumentError("飞书授权已过期，请重新授权", auth_required=True)
            token = self.client.refresh(refresh_token)
            self.db.save_feishu_oauth_credential(token)
            access_token = str(token.get("access_token") or "")
            if not access_token:
                raise FeishuDocumentError("飞书授权返回缺少访问令牌", auth_required=True)
            return access_token

    def _read_document(
        self, source: dict[str, Any], access_token: str
    ) -> tuple[str, dict[str, Any]]:
        document_id = self.client.resolve_document(source, access_token)
        return document_id, self.client.document_meta(document_id, access_token)

    def preview_document_url(self, url: str) -> dict[str, Any]:
        """读取文档元数据供管理员确认，不创建来源或发布读模型。"""
        try:
            source = parse_feishu_document_url(url)
        except ValueError as exc:
            raise FeishuDocumentError(str(exc)) from exc
        if not self.configured:
            raise FeishuDocumentError("飞书文档应用尚未配置")
        access_token = self._access_token()
        try:
            _document_id, meta = self._read_document(source, access_token)
        except FeishuDocumentError as exc:
            if not exc.auth_required:
                raise
            access_token = self._access_token(force_refresh=True)
            _document_id, meta = self._read_document(source, access_token)
        return {
            "source_type": source["source_type"],
            "title": str(meta.get("title") or "飞书文档")[:200],
            "revision_id": str(meta.get("revision_id") or "-1"),
            "ready": True,
        }

    def recover_read_models(self) -> dict[str, int]:
        if self.ima_documents is None or not self.ima_documents.store.archive_readable():
            return {"recovered": 0, "failed": 0}
        recovered = failed = 0
        with self._sync_lock:
            for source in self.db.list_feishu_document_sources(active_only=True):
                if not source.get("timeline_path") or self._read_model_current(source):
                    continue
                try:
                    self._republish_archived(
                        source,
                        {
                            "document_id": str(source.get("document_id") or ""),
                            "title": str(source.get("title") or "飞书文档"),
                            "revision_id": str(source.get("revision_id") or ""),
                        },
                    )
                    recovered += 1
                except Exception:
                    failed += 1
                    logger.exception(
                        "Feishu document read model recovery failed source_id=%s",
                        source.get("id"),
                    )
        return {"recovered": recovered, "failed": failed}

    def sync_all(self) -> dict[str, int]:
        sources = self.db.list_feishu_document_sources(active_only=True)
        if not sources:
            return {"succeeded": 0, "failed": 0}
        if not self._sync_lock.acquire(blocking=False):
            return {"succeeded": 0, "failed": 0}
        succeeded = failed = 0
        try:
            for source in sources:
                try:
                    self.sync_source(int(source["id"]))
                    succeeded += 1
                except Exception:
                    failed += 1
            return {"succeeded": succeeded, "failed": failed}
        finally:
            self._sync_lock.release()

    def sync_source(self, source_id: int, force: bool = False) -> dict[str, Any]:
        with self._sync_lock:
            return self._sync_source_locked(source_id, force)

    def _sync_source_locked(self, source_id: int, force: bool = False) -> dict[str, Any]:
        source = self.db.get_feishu_document_source(source_id)
        if not source or source.get("deleted_at"):
            raise FeishuDocumentError("飞书文档来源不存在")
        self.db.update_feishu_document_source(source_id, sync_status="running", last_checked_at=utc_now(), last_error="")
        try:
            access_token = self._access_token()
            try:
                document_id, meta = self._read_document(source, access_token)
            except FeishuDocumentError as exc:
                if not exc.auth_required:
                    raise
                access_token = self._access_token(force_refresh=True)
                document_id, meta = self._read_document(source, access_token)
            if not force and str(source.get("revision_id") or "") == meta["revision_id"] and source.get("timeline_path"):
                if not self._read_model_current(source):
                    self._republish_archived(source, meta)
                self.db.update_feishu_document_source(source_id, sync_status="succeeded", last_checked_at=utc_now())
                return {"status": "unchanged", **meta}
            try:
                blocks = self.client.blocks(document_id, meta["revision_id"], access_token)
            except FeishuDocumentError as exc:
                if not exc.auth_required:
                    raise
                access_token = self._access_token(force_refresh=True)
                document_id, meta = self._read_document(source, access_token)
                blocks = self.client.blocks(document_id, meta["revision_id"], access_token)
            timeline = normalize_timeline(blocks)
            result = self._publish(source, meta, blocks, timeline, access_token)
            return {"status": "updated", **meta, **result}
        except FeishuDocumentError as exc:
            status = "authorization_required" if exc.auth_required else "failed"
            self.db.update_feishu_document_source(source_id, sync_status=status, last_error=str(exc)[:300], last_checked_at=utc_now())
            raise
        except Exception as exc:
            self.db.update_feishu_document_source(source_id, sync_status="failed", last_error=f"{type(exc).__name__}: {exc}"[:300], last_checked_at=utc_now())
            raise

    def _read_model_current(self, source: dict[str, Any]) -> bool:
        if self.ima_documents is None:
            return False
        group_id = str(source.get("group_id") or "")
        media_id = str(source.get("media_id") or "")
        txt_path = str(source.get("txt_path") or "")
        if not group_id or not media_id or not txt_path:
            return False
        return self.ima_documents.external_document_current(
            group_id, media_id, txt_path
        )

    def _publication_payload(
        self,
        source: dict[str, Any],
        title: str,
        timeline: dict[str, Any],
        plain: str,
        txt_path: str,
        downloaded_at: str,
    ) -> tuple[ImaGroupConfig, dict[str, Any], dict[str, Any]]:
        latest_entry = (timeline.get("entries") or [{}])[-1]
        pub_date = str(latest_entry.get("day") or downloaded_at[:10])
        day = pub_date.replace("-", "")[4:] or "unknown"
        group = ImaGroupConfig(
            id=str(source["group_id"]),
            name=title,
            knowledge_base_id="",
            root_folder_id="",
        )
        record = {
            "group_id": source["group_id"],
            "media_id": source["media_id"],
            "day": day,
            "pub_date": pub_date,
            "name": title,
            "group_name": title,
            "abstract": "",
            "cover_url": "",
            "size": len(plain.encode()),
        }
        state_item = {
            "group_id": source["group_id"],
            "group_name": title,
            "pub_date": pub_date,
            "tags": ["飞书文档"],
            "size": len(plain.encode()),
            "chars": len(plain),
            "pdf": "",
            "txt": txt_path,
            "downloaded_at": downloaded_at,
        }
        return group, record, state_item

    def _republish_archived(
        self, source: dict[str, Any], meta: dict[str, str]
    ) -> None:
        if self.ima_documents is None:
            raise FeishuDocumentError("知识库文档服务未启用")
        if not self.ima_documents.store.archive_readable():
            raise FeishuDocumentError("知识库存储暂不可用")
        timeline = self.timeline(source)
        txt_path = str(source.get("txt_path") or "")
        path = (self.archive_root / txt_path).resolve()
        if (
            not txt_path
            or not path.is_relative_to(self.archive_root.resolve())
            or not path.is_file()
        ):
            raise FeishuDocumentError("飞书文档归档不完整")
        plain = path.read_text(encoding="utf-8")
        group, record, state_item = self._publication_payload(
            source,
            source_display_title(source, str(meta.get("title") or "飞书文档")),
            timeline,
            plain,
            txt_path,
            str(source.get("last_success_at") or utc_now()),
        )
        self.ima_documents.publish_external_document(group, record, state_item)
        if not self.ima_documents.external_document_current(
            str(source["group_id"]), str(source["media_id"]), txt_path
        ):
            raise FeishuDocumentError("飞书文档读模型恢复失败")

    def republish_from_archive(self, source_id: int) -> None:
        """管理员改展示名后从归档重建读模型（不重新抓取飞书）。"""
        source = self.db.get_feishu_document_source(int(source_id))
        if source is None or source.get("deleted_at") or not source.get("txt_path"):
            return
        self._republish_archived(
            source,
            {
                "document_id": str(source.get("document_id") or ""),
                "title": str(source.get("title") or "飞书文档"),
                "revision_id": str(source.get("revision_id") or ""),
            },
        )

    def _rollback_read_model(self, source: dict[str, Any]) -> None:
        if self.ima_documents is None:
            return
        try:
            record = json.loads(str(source.get("published_record_json") or ""))
            state_item = json.loads(str(source.get("published_state_json") or ""))
            if isinstance(record, dict) and isinstance(state_item, dict):
                group = ImaGroupConfig(
                    id=str(source["group_id"]),
                    name=source_display_title(source),
                    knowledge_base_id="",
                    root_folder_id="",
                )
                self.ima_documents.publish_external_document(group, record, state_item)
                return
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        self.ima_documents.remove_external_document(
            str(source["group_id"]), str(source["media_id"])
        )

    def _publish(self, source: dict[str, Any], meta: dict[str, str], blocks: list[dict[str, Any]], timeline: dict[str, Any], access_token: str) -> dict[str, Any]:
        if self.ima_documents is None:
            raise FeishuDocumentError("知识库文档服务未启用")
        if not self.ima_documents.store.archive_writable():
            raise FeishuDocumentError("知识库存储当前不可写")
        plain = timeline_plain_text(meta["title"], timeline)
        digest = hashlib.sha256(json.dumps({"title": meta["title"], "timeline": timeline}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        source_root = self.archive_root / "feishu-documents" / str(source["source_key_hash"])
        versions_root = source_root / "versions"
        version = versions_root / digest
        temp = versions_root / f".{digest}.{secrets.token_hex(4)}.tmp"
        assets: dict[str, dict[str, str]] = {}
        versions_root.mkdir(parents=True, exist_ok=True)
        try:
            with archive_lock(self.archive_root):
                if not version.exists():
                    temp.mkdir(parents=True, exist_ok=False)
                    (temp / "assets").mkdir()
                    total_media_bytes = 0
                    for block in blocks:
                        for asset in block_asset_tokens(block):
                            token = asset["token"]
                            if token in assets:
                                continue
                            try:
                                payload, mime, disposition = self.client.download_media(token, access_token)
                            except FeishuDocumentError as exc:
                                if exc.auth_required:
                                    raise  # 令牌失效走上层刷新重试，不能把媒体标成不可用
                                # 作者关闭下载权限等上游限制：标记跳过，不让整个版本失败
                                assets[token] = {**asset, "id": "", "unavailable": True}
                                continue
                            total_media_bytes += len(payload)
                            if total_media_bytes > MAX_DOCUMENT_MEDIA_BYTES:
                                raise FeishuDocumentError("飞书文档媒体总量超过 250 MB 限制")
                            extension = mimetypes.guess_extension(mime) or ""
                            asset_hash = hashlib.sha256(payload).hexdigest()
                            filename = asset_hash + extension
                            (temp / "assets" / filename).write_bytes(payload)
                            raw_name = ""
                            filename_match = re.search(
                                r"filename\*?=(?:UTF-8''|\")?([^\";]+)",
                                disposition,
                                re.I,
                            )
                            if filename_match:
                                raw_name = unquote(filename_match.group(1).strip().strip('"'))
                            assets[token] = {
                                **asset,
                                "id": asset_hash,
                                "path": f"assets/{filename}",
                                "mime": mime,
                                "name": asset.get("name") or raw_name[:200],
                            }
                    for item in _walk_values(timeline):
                        for asset in item.get("assets") or []:
                            if isinstance(asset, dict):
                                asset.update(assets.get(asset.get("token")) or {})
                    (temp / "blocks.json").write_text(
                        json.dumps(blocks, ensure_ascii=False), encoding="utf-8"
                    )
                    (temp / "timeline.json").write_text(
                        json.dumps(timeline, ensure_ascii=False), encoding="utf-8"
                    )
                    (temp / "content.txt").write_text(plain, encoding="utf-8")
                    (temp / "assets.json").write_text(
                        json.dumps(assets, ensure_ascii=False), encoding="utf-8"
                    )
                    os.replace(temp, version)
                else:
                    timeline = json.loads((version / "timeline.json").read_text(encoding="utf-8"))
        except Exception:
            shutil.rmtree(temp, ignore_errors=True)
            raise

        rel = version.relative_to(self.archive_root)
        now = utc_now()
        timeline_path = str(rel / "timeline.json")
        txt_path = str(rel / "content.txt")
        group, record, state_item = self._publication_payload(
            source, source_display_title(source, str(meta["title"])), timeline, plain, txt_path, now
        )
        self.ima_documents.publish_external_document(group, record, state_item)
        if not self.ima_documents.external_document_current(
            str(source["group_id"]), str(source["media_id"]), txt_path
        ):
            self._rollback_read_model(source)
            raise FeishuDocumentError("飞书文档读模型发布失败")
        try:
            self.db.publish_feishu_document_source(
                int(source["id"]),
                document_id=meta["document_id"],
                title=meta["title"],
                revision_id=meta["revision_id"],
                content_hash=digest,
                timeline_path=timeline_path,
                txt_path=txt_path,
                asset_root=str(rel / "assets"),
                entry_count=len(timeline.get("entries") or []),
                published_record_json=json.dumps(record, ensure_ascii=False),
                published_state_json=json.dumps(state_item, ensure_ascii=False),
                last_success_at=now,
            )
        except Exception:
            self._rollback_read_model(source)
            raise
        return {
            "content_hash": digest,
            "entry_count": len(timeline.get("entries") or []),
        }

    # ponytail: in-process parsed-JSON cache keyed by timeline_path+mtime; timelines only change on new doc version (new path/mtime), no TTL needed
    _timeline_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def warm_timeline_cache(self) -> int:
        """启动预热：把各源 timeline.json 预解析进内存，首击不再冷读。失败逐个跳过。"""
        warmed = 0
        try:
            sources = self.db.list_feishu_document_sources(active_only=True)
        except Exception:
            logger.exception("Feishu timeline warmup list failed")
            return 0
        for source in sources:
            try:
                self.timeline(source)
            except Exception:
                continue
            else:
                warmed += 1
        return warmed

    def timeline(self, source: dict[str, Any]) -> dict[str, Any]:
        raw = str(source.get("timeline_path") or "")
        if not raw:
            raise FileNotFoundError
        path = (self.archive_root / raw).resolve()
        root = self.archive_root.resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FileNotFoundError
        mtime = path.stat().st_mtime
        cached = self._timeline_cache.get(raw)
        if cached and cached[0] == mtime:
            return cached[1]
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("invalid timeline")
        if len(self._timeline_cache) > 32:
            self._timeline_cache.clear()
        self._timeline_cache[raw] = (mtime, data)
        return data

    def asset(self, source: dict[str, Any], asset_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{64}", asset_id):
            raise FileNotFoundError
        raw = str(source.get("asset_root") or "")
        root = (self.archive_root / raw).resolve()
        archive = self.archive_root.resolve()
        if not root.is_relative_to(archive) or not root.is_dir():
            raise FileNotFoundError
        matches = list(root.glob(asset_id + ".*"))
        if len(matches) != 1 or not matches[0].resolve().is_relative_to(root):
            raise FileNotFoundError
        return matches[0]
