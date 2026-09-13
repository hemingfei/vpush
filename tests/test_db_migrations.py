"""有序 schema 迁移 runner：user_version 跟踪、一次性执行、失败回滚。"""
import sqlite3

import pytest

from app import db as db_module
from app.db import DB


def _user_version(path) -> int:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def test_migrations_tracked_by_user_version(tmp_path):
    db = DB(tmp_path / "m.sqlite")
    try:
        versions = [version for version, _, _ in db_module.SCHEMA_MIGRATIONS]
        expected = max(versions) if versions else 0
        assert db._rows("PRAGMA user_version")[0]["user_version"] == expected
    finally:
        db.close()


def test_new_migration_applied_once_on_open(tmp_path, monkeypatch):
    path = tmp_path / "m.sqlite"
    db = DB(path)
    baseline = db._rows("PRAGMA user_version")[0]["user_version"]
    db.close()

    migration = (
        baseline + 1,
        "测试迁移",
        ("ALTER TABLE users ADD COLUMN migration_probe TEXT NOT NULL DEFAULT ''",),
    )
    monkeypatch.setattr(db_module, "SCHEMA_MIGRATIONS", [migration])

    db2 = DB(path)
    try:
        cols = {row["name"] for row in db2._rows("PRAGMA table_info(users)")}
        assert "migration_probe" in cols
        assert db2._rows("PRAGMA user_version")[0]["user_version"] == baseline + 1
        # 已应用的高版本迁移在重复打开时不再执行（幂等）
        db3 = DB(path)
        try:
            assert db3._rows("PRAGMA user_version")[0]["user_version"] == baseline + 1
        finally:
            db3.close()
    finally:
        db2.close()


def test_failed_migration_rolls_back_and_blocks_open(tmp_path, monkeypatch):
    path = tmp_path / "m.sqlite"
    db = DB(path)
    baseline = db._rows("PRAGMA user_version")[0]["user_version"]
    db.close()

    bad = (baseline + 1, "坏迁移", "INSERT INTO no_such_table VALUES (1)")
    monkeypatch.setattr(db_module, "SCHEMA_MIGRATIONS", [bad])

    with pytest.raises(RuntimeError, match="坏迁移"):
        DB(path)

    assert _user_version(path) == baseline


def test_slow_query_warning_logged(tmp_path, monkeypatch):
    import logging

    db = DB(tmp_path / "slow.sqlite")
    try:
        records: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = Capture()
        logger = logging.getLogger("app.db")
        logger.addHandler(handler)
        monkeypatch.setattr(db_module, "_SLOW_QUERY_SECONDS", 0.0)
        try:
            db._rows("SELECT 1")
        finally:
            logger.removeHandler(handler)
        assert any("slow query" in record.getMessage() for record in records)
        # 参数不进入日志（可能含 Cookie/token）
        assert all("secret-value" not in record.getMessage() for record in records)
    finally:
        db.close()


def test_downloaded_at_index_migration_applied(tmp_path):
    db = DB(tmp_path / "idx.sqlite")
    try:
        latest = max(v for v, _, _ in db_module.SCHEMA_MIGRATIONS)
        assert db._rows("PRAGMA user_version")[0]["user_version"] == latest
        names = {row["name"] for row in db._rows("PRAGMA index_list(ima_document_index)")}
        assert "idx_ima_doc_downloaded" in names
        plan = db._read_only_rows(
            "EXPLAIN QUERY PLAN SELECT * FROM ima_document_index "
            "WHERE downloaded_at >= ? ORDER BY downloaded_at DESC LIMIT 10",
            ("2026-09-01",),
        )
        detail = " | ".join(row["detail"] for row in plan)
        assert "idx_ima_doc_downloaded" in detail
        assert "SCAN" not in detail
    finally:
        db.close()


def test_posts_published_at_index_migration_applied(tmp_path):
    """图片补缓存候选窗口（images LIKE + ORDER BY published_at）靠该索引消除全表排序。"""
    db = DB(tmp_path / "posts-idx.sqlite")
    try:
        names = {row["name"] for row in db._rows("PRAGMA index_list(posts)")}
        assert "idx_posts_published_at" in names
        plan = db._read_only_rows(
            "EXPLAIN QUERY PLAN SELECT platform, external_id, images FROM posts "
            "WHERE images LIKE '%http%' ORDER BY published_at DESC LIMIT 200",
            (),
        )
        detail = " | ".join(row["detail"] for row in plan)
        assert "idx_posts_published_at" in detail
    finally:
        db.close()


def test_journal_mode_env(tmp_path, monkeypatch):
    path = tmp_path / "journal.sqlite"
    monkeypatch.setenv("DB_JOURNAL_MODE", "wal")
    db = DB(path)
    try:
        assert db._rows("PRAGMA journal_mode")[0]["journal_mode"].lower() == "wal"
    finally:
        db.close()

    monkeypatch.setenv("DB_JOURNAL_MODE", "delete")
    db2 = DB(tmp_path / "journal2.sqlite")
    try:
        assert db2._rows("PRAGMA journal_mode")[0]["journal_mode"].lower() == "delete"
    finally:
        db2.close()

    # 非法值回落 delete
    monkeypatch.setenv("DB_JOURNAL_MODE", "bogus")
    db3 = DB(tmp_path / "journal3.sqlite")
    try:
        assert db3._rows("PRAGMA journal_mode")[0]["journal_mode"].lower() == "delete"
    finally:
        db3.close()
