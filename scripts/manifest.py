#!/usr/bin/env python3
"""SQLite manifest (lab.sqlite) — authoritative local index for scale.

status: staging | uploading | uploaded | failed | hot
Never logs cookies/secrets.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from lab_common import ensure_cache_dirs, iso_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY,
  rel_path TEXT NOT NULL UNIQUE,
  sha1 TEXT,
  size INTEGER,
  status TEXT NOT NULL,
  remote_cid TEXT,
  remote_pickcode TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  uploaded_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_sha1 ON files(sha1);
"""

_STATUSES = frozenset({"staging", "uploading", "uploaded", "failed", "hot"})
_local = threading.local()


def db_path(root: Path | None = None) -> Path:
    return ensure_cache_dirs(root)["manifest"] / "lab.sqlite"


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=60.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def get_conn(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    key = str(path or db_path())
    store = getattr(_local, "conns", None)
    if store is None:
        store = {}
        _local.conns = store
    conn = store.get(key)
    if conn is None:
        conn = connect(Path(key) if path else None)
        store[key] = conn
    yield conn


def upsert_file(
    rel_path: str,
    *,
    sha1: str | None = None,
    size: int | None = None,
    status: str = "staging",
    remote_cid: str | None = None,
    remote_pickcode: str | None = None,
    attempts: int | None = None,
    last_error: str | None = None,
    uploaded_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    if status not in _STATUSES:
        raise ValueError(f"invalid status: {status}")
    rel = rel_path.lstrip("/")
    now = iso_now()

    def _do(c: sqlite3.Connection) -> int:
        row = c.execute("SELECT id FROM files WHERE rel_path=?", (rel,)).fetchone()
        if row is None:
            cur = c.execute(
                """
                INSERT INTO files (
                  rel_path, sha1, size, status, remote_cid, remote_pickcode,
                  attempts, last_error, created_at, updated_at, uploaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel, sha1, size, status, remote_cid, remote_pickcode,
                    0 if attempts is None else attempts, last_error, now, now, uploaded_at,
                ),
            )
            return int(cur.lastrowid)
        sets = ["updated_at=?", "status=?"]
        vals: list[Any] = [now, status]
        if sha1 is not None:
            sets.append("sha1=?"); vals.append(sha1)
        if size is not None:
            sets.append("size=?"); vals.append(size)
        if remote_cid is not None:
            sets.append("remote_cid=?"); vals.append(remote_cid)
        if remote_pickcode is not None:
            sets.append("remote_pickcode=?"); vals.append(remote_pickcode)
        if attempts is not None:
            sets.append("attempts=?"); vals.append(attempts)
        if last_error is not None:
            sets.append("last_error=?"); vals.append(last_error)
        if uploaded_at is not None:
            sets.append("uploaded_at=?"); vals.append(uploaded_at)
        vals.append(rel)
        c.execute(f"UPDATE files SET {', '.join(sets)} WHERE rel_path=?", vals)
        return int(row["id"])

    if conn is not None:
        return _do(conn)
    with get_conn() as c:
        return _do(c)


def mark_uploading(rel_path: str, conn: sqlite3.Connection | None = None) -> None:
    rel = rel_path.lstrip("/")
    now = iso_now()

    def _do(c: sqlite3.Connection) -> None:
        c.execute(
            "UPDATE files SET status='uploading', updated_at=?, attempts=attempts+1 WHERE rel_path=?",
            (now, rel),
        )

    if conn is not None:
        _do(conn)
    else:
        with get_conn() as c:
            _do(c)


def mark_uploaded(
    rel_path: str,
    *,
    remote_cid: str | None = None,
    remote_pickcode: str | None = None,
    sha1: str | None = None,
    size: int | None = None,
    keep_hot: bool = True,
    conn: sqlite3.Connection | None = None,
) -> None:
    upsert_file(
        rel_path,
        sha1=sha1,
        size=size,
        status="hot" if keep_hot else "uploaded",
        remote_cid=remote_cid,
        remote_pickcode=remote_pickcode,
        last_error="",
        uploaded_at=iso_now(),
        conn=conn,
    )


def mark_failed(
    rel_path: str,
    error: str,
    *,
    attempts: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    kwargs: dict[str, Any] = {"status": "failed", "last_error": (error or "")[:800]}
    if attempts is not None:
        kwargs["attempts"] = attempts
    upsert_file(rel_path, **kwargs, conn=conn)


def get_by_rel(rel_path: str, conn: sqlite3.Connection | None = None) -> dict | None:
    rel = rel_path.lstrip("/")

    def _do(c: sqlite3.Connection) -> dict | None:
        row = c.execute("SELECT * FROM files WHERE rel_path=?", (rel,)).fetchone()
        return dict(row) if row else None

    if conn is not None:
        return _do(conn)
    with get_conn() as c:
        return _do(c)


def is_done(rel_path: str, sha1: str | None = None, conn: sqlite3.Connection | None = None) -> bool:
    row = get_by_rel(rel_path, conn=conn)
    if row and row["status"] in ("uploaded", "hot"):
        if sha1 and row.get("sha1") and row["sha1"] != sha1:
            return False
        return True
    if sha1:
        def _by_sha(c: sqlite3.Connection) -> bool:
            r = c.execute(
                "SELECT 1 FROM files WHERE sha1=? AND status IN ('uploaded','hot') LIMIT 1",
                (sha1,),
            ).fetchone()
            return bool(r)

        if conn is not None:
            return _by_sha(conn)
        with get_conn() as c:
            return _by_sha(c)
    return False


def list_pending(
    *,
    statuses: tuple[str, ...] = ("staging", "failed"),
    limit: int = 20,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    ph = ",".join("?" * len(statuses))

    def _do(c: sqlite3.Connection) -> list[dict]:
        rows = c.execute(
            f"SELECT * FROM files WHERE status IN ({ph}) ORDER BY created_at ASC, id ASC LIMIT ?",
            (*statuses, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    if conn is not None:
        return _do(conn)
    with get_conn() as c:
        return _do(c)


def claim_batch(
    *,
    batch_size: int = 20,
    statuses: tuple[str, ...] = ("staging",),
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    now = iso_now()
    ph = ",".join("?" * len(statuses))

    def _do(c: sqlite3.Connection) -> list[dict]:
        c.execute("BEGIN IMMEDIATE")
        try:
            rows = c.execute(
                f"SELECT * FROM files WHERE status IN ({ph}) ORDER BY created_at ASC, id ASC LIMIT ?",
                (*statuses, batch_size),
            ).fetchall()
            out: list[dict] = []
            for row in rows:
                c.execute(
                    f"UPDATE files SET status='uploading', updated_at=?, attempts=attempts+1 "
                    f"WHERE id=? AND status IN ({ph})",
                    (now, row["id"], *statuses),
                )
                if c.execute("SELECT changes()").fetchone()[0]:
                    d = dict(row)
                    d["status"] = "uploading"
                    d["attempts"] = int(row["attempts"] or 0) + 1
                    d["updated_at"] = now
                    out.append(d)
            c.execute("COMMIT")
            return out
        except Exception:
            c.execute("ROLLBACK")
            raise

    if conn is not None:
        return _do(conn)
    with get_conn() as c:
        return _do(c)


def counts_by_status(conn: sqlite3.Connection | None = None) -> dict[str, int]:
    def _do(c: sqlite3.Connection) -> dict[str, int]:
        rows = c.execute("SELECT status, COUNT(*) AS n FROM files GROUP BY status").fetchall()
        out = {s: 0 for s in sorted(_STATUSES)}
        for r in rows:
            out[str(r["status"])] = int(r["n"])
        out["total"] = sum(v for k, v in out.items() if k != "total")
        return out

    if conn is not None:
        return _do(conn)
    with get_conn() as c:
        return _do(c)


def ensure_inbox(root: Path | None = None) -> Path:
    inbox = ensure_cache_dirs(root)["manifest"] / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox
