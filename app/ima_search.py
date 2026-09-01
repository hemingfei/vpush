"""Independent SQLite FTS5 index for selected IMA document bodies."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_QUERY_CHARS = 256

_EMPTY_COUNTS = {
    "indexed": 0,
    "updated": 0,
    "skipped": 0,
    "removed": 0,
    "missing": 0,
}
_SOURCE_FIELDS = (
    "group_id",
    "media_id",
    "name",
    "group_name",
    "metadata_folded",
    "abstract",
    "tags_json",
    "txt_path",
    "downloaded_at",
    "chars",
)


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: str) -> str:
    parser = _PlainTextParser()
    try:
        parser.feed(value)
        parser.close()
        value = " ".join(parser.parts)
    except (ValueError, TypeError):
        pass
    return " ".join(str(value or "").split())


def _source_hash(row: dict[str, Any]) -> str:
    payload = [row.get(field) for field in _SOURCE_FIELDS]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class ImaSearchIndex:
    def __init__(
        self, path: Path, archive_root: Path, group_ids: tuple[str, ...]
    ) -> None:
        self.path = Path(path)
        self.archive_root = Path(archive_root).resolve()
        self.group_ids = tuple(dict.fromkeys(str(item).strip() for item in group_ids if str(item).strip()))
        self._sync_lock = threading.Lock()
        self._ready = False
        self._documents = 0
        self._last_sync_at = ""
        self._error = ""
        if self.enabled and self.path.is_file():
            self._load_status()

    @property
    def enabled(self) -> bool:
        return bool(self.group_ids)

    def _connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            uri = self.path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=5)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        if not readonly:
            connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                group_id TEXT NOT NULL,
                media_id TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                UNIQUE(group_id, media_id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                name,
                metadata,
                body,
                content='documents',
                content_rowid='id',
                tokenize='trigram'
            );
            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, name, metadata, body)
                VALUES (new.id, new.name, new.metadata, new.body);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, name, metadata, body)
                VALUES ('delete', old.id, old.name, old.metadata, old.body);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, name, metadata, body)
                VALUES ('delete', old.id, old.name, old.metadata, old.body);
                INSERT INTO documents_fts(rowid, name, metadata, body)
                VALUES (new.id, new.name, new.metadata, new.body);
            END;
            CREATE TABLE IF NOT EXISTS search_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                ready INTEGER NOT NULL DEFAULT 0,
                last_sync_at TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            );
            """
        )

    def _safe_path(self, raw: Any) -> Path | None:
        text = str(raw or "").strip()
        if not text:
            return None
        relative = Path(text)
        if relative.is_absolute():
            return None
        candidate = (self.archive_root / relative).resolve()
        if candidate == self.archive_root or not candidate.is_relative_to(self.archive_root):
            return None
        return candidate

    def _load_status(self) -> None:
        try:
            with self._connect(readonly=True) as connection:
                row = connection.execute(
                    "SELECT ready, last_sync_at, error FROM search_meta WHERE id = 1"
                ).fetchone()
                placeholders = ",".join("?" for _ in self.group_ids)
                count = connection.execute(
                    f"SELECT COUNT(*) FROM documents WHERE group_id IN ({placeholders})",
                    self.group_ids,
                ).fetchone()[0]
            if row:
                self._ready = bool(row["ready"])
                self._last_sync_at = str(row["last_sync_at"] or "")
                self._error = str(row["error"] or "")
            self._documents = int(count)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._error = self._error_detail(exc)

    @staticmethod
    def _error_detail(exc: BaseException) -> str:
        detail = " ".join(str(exc or "").split()) or "unknown error"
        return f"{type(exc).__name__}: {detail}"[:300]

    def sync(self, rows: list[dict]) -> dict[str, int]:
        if not self.enabled:
            return dict(_EMPTY_COUNTS)
        with self._sync_lock:
            try:
                return self._sync(rows)
            except Exception as exc:  # noqa: BLE001 - preserve last good index
                self._error = self._error_detail(exc)
                return {
                    "indexed": self._documents,
                    "updated": 0,
                    "skipped": 0,
                    "removed": 0,
                    "missing": 0,
                }

    def _sync(self, rows: list[dict]) -> dict[str, int]:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            configured = set(self.group_ids)
            existing = {
                (row["group_id"], row["media_id"]): row["source_hash"]
                for row in connection.execute(
                    "SELECT group_id, media_id, source_hash FROM documents"
                )
                if row["group_id"] in configured
            }
            present: set[tuple[str, str]] = set()
            prepared: list[tuple[str, str, str, str, str, str]] = []
            skipped = 0
            missing = 0
            for source in rows:
                group_id = str(source.get("group_id") or "").strip()
                if group_id not in configured:
                    skipped += 1
                    continue
                media_id = str(source.get("media_id") or "").strip()
                if not media_id:
                    missing += 1
                    continue
                key = (group_id, media_id)
                if key in present:
                    skipped += 1
                    continue
                present.add(key)
                digest = _source_hash(source)
                if existing.get(key) == digest:
                    skipped += 1
                    continue
                path = self._safe_path(source.get("txt_path"))
                if path is None or not path.is_file():
                    missing += 1
                    continue
                try:
                    with path.open("rb") as stream:
                        raw_body = stream.read(MAX_BODY_BYTES + 1)
                    body = _plain_text(
                        raw_body[:MAX_BODY_BYTES].decode("utf-8", errors="ignore")
                    )
                except OSError:
                    missing += 1
                    continue
                metadata = " ".join(
                    str(source.get(field) or "")
                    for field in ("group_name", "metadata_folded", "abstract", "tags_json")
                )
                prepared.append(
                    (
                        group_id,
                        media_id,
                        digest,
                        _plain_text(str(source.get("name") or "")),
                        _plain_text(metadata),
                        body,
                    )
                )

            removed_keys = set(existing) - present
            placeholders = ",".join("?" for _ in configured)
            now = datetime.now(UTC).isoformat()
            with connection:
                for group_id, media_id in removed_keys:
                    connection.execute(
                        "DELETE FROM documents WHERE group_id = ? AND media_id = ?",
                        (group_id, media_id),
                    )
                connection.executemany(
                    "INSERT INTO documents "
                    "(group_id, media_id, source_hash, name, metadata, body) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(group_id, media_id) DO UPDATE SET "
                    "source_hash=excluded.source_hash, name=excluded.name, "
                    "metadata=excluded.metadata, body=excluded.body",
                    prepared,
                )
                count = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM documents WHERE group_id IN ({placeholders})",
                        tuple(configured),
                    ).fetchone()[0]
                )
                connection.execute(
                    "INSERT INTO search_meta (id, ready, last_sync_at, error) "
                    "VALUES (1, 1, ?, '') ON CONFLICT(id) DO UPDATE SET "
                    "ready=1, last_sync_at=excluded.last_sync_at, error=''",
                    (now,),
                )
            self._ready = True
            self._documents = count
            self._last_sync_at = now
            self._error = ""
            return {
                "indexed": count,
                "updated": len(prepared),
                "skipped": skipped,
                "removed": len(removed_keys),
                "missing": missing,
            }
        finally:
            connection.close()

    def search(
        self, query: str, readable_group_ids: list[str], limit: int
    ) -> list[dict]:
        text = " ".join(str(query or "").split())[:MAX_QUERY_CHARS]
        if (
            not self.enabled
            or not self.path.is_file()
            or len("".join(text.split())) < 3
            or int(limit) <= 0
        ):
            return []
        allowed = [
            group_id
            for group_id in self.group_ids
            if group_id in set(str(item) for item in readable_group_ids)
        ]
        if not allowed:
            return []
        phrase = '"' + text.replace('"', '""') + '"'
        placeholders = ",".join("?" for _ in allowed)
        try:
            with self._connect(readonly=True) as connection:
                rows = connection.execute(
                    "SELECT d.group_id, d.media_id, "
                    "bm25(documents_fts, 8.0, 3.0, 1.0) AS score, "
                    "snippet(documents_fts, 2, '[', ']', ' … ', 32) AS search_snippet "
                    "FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
                    f"WHERE documents_fts MATCH ? AND d.group_id IN ({placeholders}) "
                    "ORDER BY score, d.group_id, d.media_id LIMIT ?",
                    (phrase, *allowed, min(int(limit), 200)),
                ).fetchall()
            return [
                {
                    "group_id": str(row["group_id"]),
                    "media_id": str(row["media_id"]),
                    "score": float(row["score"]),
                    "search_snippet": _plain_text(str(row["search_snippet"] or ""))[:240],
                }
                for row in rows
            ]
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            self._error = self._error_detail(exc)
            return []

    def status(self) -> dict:
        if not self.enabled:
            return {
                "enabled": False,
                "ready": False,
                "documents": 0,
                "last_sync_at": "",
                "error": "",
            }
        if self.path.is_file() and not self._ready and not self._error:
            self._load_status()
        return {
            "enabled": True,
            "ready": self._ready,
            "documents": self._documents,
            "last_sync_at": self._last_sync_at,
            "error": self._error,
        }
