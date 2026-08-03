"""SQLite 持久化：KOL、帖子（去重）、推送日志。"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS kols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    name TEXT NOT NULL,
    external_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    kol_id INTEGER NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (platform, external_id)
);
CREATE TABLE IF NOT EXISTS push_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

ALLOWED_PLATFORMS = {"xueqiu", "weibo", "twitter"}


class DB:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    def close(self):
        with self._lock:
            self._conn.close()

    def _rows(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def _execute(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.lastrowid

    # ---- KOL ----
    def add_kol(self, platform: str, name: str, external_id: str) -> int:
        if platform not in ALLOWED_PLATFORMS:
            raise ValueError(f"不支持的平台: {platform}")
        return self._execute(
            "INSERT INTO kols (platform, name, external_id) VALUES (?, ?, ?)",
            (platform, name, external_id),
        )

    def get_kol(self, kol_id: int) -> dict | None:
        rows = self._rows("SELECT * FROM kols WHERE id = ?", (kol_id,))
        return rows[0] if rows else None

    def list_kols(self, platform: str | None = None) -> list[dict]:
        if platform:
            return self._rows("SELECT * FROM kols WHERE platform = ? ORDER BY id", (platform,))
        return self._rows("SELECT * FROM kols ORDER BY id")

    def update_kol(self, kol_id: int, name=None, external_id=None, enabled=None):
        sets, params = [], []
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if external_id is not None:
            sets.append("external_id = ?")
            params.append(external_id)
        if enabled is not None:
            sets.append("enabled = ?")
            params.append(1 if enabled else 0)
        if not sets:
            return
        params.append(kol_id)
        self._execute(f"UPDATE kols SET {', '.join(sets)} WHERE id = ?", params)

    def delete_kol(self, kol_id: int):
        self._execute("DELETE FROM kols WHERE id = ?", (kol_id,))

    # ---- Post ----
    def post_exists(self, platform: str, external_id: str) -> bool:
        rows = self._rows(
            "SELECT id FROM posts WHERE platform = ? AND external_id = ?",
            (platform, external_id),
        )
        return bool(rows)

    def insert_post(self, platform, kol_id, external_id, title, content, url, published_at) -> int | None:
        if self.post_exists(platform, external_id):
            return None
        return self._execute(
            "INSERT INTO posts (platform, kol_id, external_id, title, content, url, published_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (platform, kol_id, external_id, title, content, url, published_at),
        )

    def list_posts(self, limit: int = 100, platform: str | None = None, kol_id: int | None = None) -> list[dict]:
        sql = "SELECT p.*, k.name AS kol_name FROM posts p JOIN kols k ON k.id = p.kol_id"
        conds, params = [], []
        if platform:
            conds.append("p.platform = ?")
            params.append(platform)
        if kol_id:
            conds.append("p.kol_id = ?")
            params.append(kol_id)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY p.id DESC LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    # ---- Push log ----
    def add_push_log(self, post_id: int, channel: str, status: str, error: str = "") -> int:
        return self._execute(
            "INSERT INTO push_logs (post_id, channel, status, error) VALUES (?, ?, ?, ?)",
            (post_id, channel, status, error),
        )

    def list_push_logs(self, limit: int = 100) -> list[dict]:
        return self._rows(
            "SELECT l.*, p.title, k.name AS kol_name FROM push_logs l "
            "JOIN posts p ON p.id = l.post_id "
            "JOIN kols k ON k.id = p.kol_id "
            "ORDER BY l.id DESC LIMIT ?",
            (limit,),
        )
