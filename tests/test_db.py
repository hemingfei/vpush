"""DB 层单元测试：迁移、唯一性与事务一致性。"""
import sqlite3

import pytest

from app.db import DB


def test_set_settings_atomic_writes_multiple_values(tmp_path):
    db = DB(str(tmp_path / "settings.db"))
    db.set_settings_atomic({"ima_one": "value-one", "ima_two": "value-two"})
    assert db.get_setting("ima_one") == "value-one"
    assert db.get_setting("ima_two") == "value-two"


def test_set_settings_atomic_rolls_back_all_values_on_sql_error(tmp_path):
    db = DB(str(tmp_path / "settings-rollback.db"))
    db.set_setting("ima_one", "old-one")
    db.set_setting("ima_two", "old-two")
    real_connection = db._conn

    class FailingConnection:
        def __init__(self, connection):
            self.connection = connection
            self.setting_writes = 0

        def execute(self, sql, params=()):
            if sql.startswith("INSERT INTO settings"):
                self.setting_writes += 1
                if self.setting_writes == 2:
                    raise sqlite3.OperationalError("controlled settings failure")
            return self.connection.execute(sql, params)

        def commit(self):
            return self.connection.commit()

        def rollback(self):
            return self.connection.rollback()

    failing = FailingConnection(real_connection)
    db._conn = failing
    try:
        with pytest.raises(sqlite3.OperationalError, match="controlled settings failure"):
            db.set_settings_atomic({"ima_one": "new-one", "ima_two": "new-two"})
    finally:
        db._conn = real_connection

    assert db.get_setting("ima_one") == "old-one"
    assert db.get_setting("ima_two") == "old-two"


def test_db_migrates_secondary_column(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    cols = {r["name"] for r in db._rows("PRAGMA table_info(kols)")}
    assert "secondary" in cols


def test_add_kol_with_secondary(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    kid = db.add_kol("xueqiu", "测试", "999", priority=False, secondary=True)
    kol = db.get_kol(kid)
    assert kol["secondary"] == 1
    assert kol["priority"] == 0


def test_update_kol_secondary_and_mutex(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    kid = db.add_kol("xueqiu", "测试", "999", priority=True)
    # 设 secondary 必须自动清 priority（互斥）
    db.update_kol(kid, secondary=True)
    kol = db.get_kol(kid)
    assert kol["secondary"] == 1 and kol["priority"] == 0
    # 设 priority 必须自动清 secondary
    db.update_kol(kid, priority=True)
    kol = db.get_kol(kid)
    assert kol["priority"] == 1 and kol["secondary"] == 0


def test_set_kols_flag_priority_secondary_mutex(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    kids = [db.add_kol("xueqiu", f"批量{i}", f"bf{i}", priority=True) for i in range(2)]
    db.set_kols_flag(kids, "secondary", True)
    for kid in kids:
        kol = db.get_kol(kid)
        assert kol["secondary"] == 1 and kol["priority"] == 0
    db.set_kols_flag(kids, "priority", True)
    for kid in kids:
        kol = db.get_kol(kid)
        assert kol["priority"] == 1 and kol["secondary"] == 0
    db.set_kols_flag(kids, "priority", False)
    for kid in kids:
        kol = db.get_kol(kid)
        assert kol["priority"] == 0 and kol["secondary"] == 0


def test_add_kol_priority_wins_over_secondary(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    kid = db.add_kol("xueqiu", "测试", "999", priority=True, secondary=True)
    kol = db.get_kol(kid)
    assert kol["priority"] == 1
    assert kol["secondary"] == 0


def test_db_migrates_subscription_secondary_column(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    cols = {r["name"] for r in db._rows("PRAGMA table_info(subscriptions)")}
    assert "secondary" in cols


def test_db_migrates_subscription_hide_images_column(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kol_id INTEGER NOT NULL,
            type TEXT NOT NULL DEFAULT 'post',
            favorite INTEGER NOT NULL DEFAULT 0,
            secondary INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (user_id, kol_id)
        );
        """
    )
    conn.close()

    db = DB(str(path))
    columns = {r["name"]: r for r in db._rows("PRAGMA table_info(subscriptions)")}
    assert columns["hide_images"]["notnull"] == 1
    assert columns["hide_images"]["dflt_value"] == "0"


def test_set_subscription_secondary(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    uid = db.add_user("u", "h", telegram_chat_id="111")
    kid = db.add_kol("xueqiu", "A", "1")
    db.add_subscription(uid, kid)
    assert db.set_subscription_secondary(uid, kid, True)
    assert kid in db.subscribed_secondary_ids(uid)
    db.set_subscription_secondary(uid, kid, False)
    assert kid not in db.subscribed_secondary_ids(uid)


def test_subscribers_of_kol_includes_secondary(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    uid = db.add_user("u", "h", telegram_chat_id="111")
    kid = db.add_kol("xueqiu", "A", "1")
    db.add_subscription(uid, kid)
    db.set_subscription_secondary(uid, kid, True)
    subs = db.subscribers_of_kol(kid)
    assert subs and subs[0]["secondary"] == 1


def test_list_subscriptions_returns_personal_secondary(tmp_path):
    """list_subscriptions 的 secondary 必须是订阅关系（个人）的，而非 kols 全局列。

    kols 表也有 secondary（全局次要）列，SELECT k.* 与其同名冲突时
    dict(row) 会取到全局值导致个人状态丢失（刷新后铃铛复位）。
    """
    db = DB(str(tmp_path / "t.db"))
    uid = db.add_user("u", "h", telegram_chat_id="111")
    kid = db.add_kol("xueqiu", "A", "1")  # kols.secondary = 0
    db.add_subscription(uid, kid)
    db.set_subscription_secondary(uid, kid, True)  # subscriptions.secondary = 1
    subs = db.list_subscriptions(uid)
    assert subs and subs[0]["secondary"] == 1


def test_subscription_hide_images_defaults_toggles_and_is_user_scoped(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    first_uid = db.add_user("first", "h", telegram_chat_id="111")
    second_uid = db.add_user("second", "h", telegram_chat_id="222")
    kid = db.add_kol("xueqiu", "A", "hide-images")
    db.add_subscription(first_uid, kid)
    db.add_subscription(second_uid, kid)

    assert db.get_subscription(first_uid, kid)["hide_images"] == 0
    assert db.list_subscriptions(first_uid)[0]["hide_images"] == 0
    assert {
        row["id"]: row["hide_images"] for row in db.subscribers_of_kol(kid)
    } == {first_uid: 0, second_uid: 0}

    assert db.set_subscription_hide_images(first_uid, kid, True)
    assert db.get_subscription(first_uid, kid)["hide_images"] == 1
    assert db.get_subscription(second_uid, kid)["hide_images"] == 0
    assert db.list_subscriptions(first_uid)[0]["hide_images"] == 1
    assert {
        row["id"]: row["hide_images"] for row in db.subscribers_of_kol(kid)
    } == {first_uid: 1, second_uid: 0}

    assert db.set_subscription_hide_images(first_uid, kid, False)
    assert db.get_subscription(first_uid, kid)["hide_images"] == 0
    assert not db.set_subscription_hide_images(first_uid, kid + 999, True)


def test_post_tag_state_distinguishes_pending_from_no_match(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    kid = db.add_kol("xueqiu", "测试", "tag-state")
    pending_id = db.insert_post("xueqiu", kid, "pending", "t", "c", "u", "")
    no_match_id = db.insert_post(
        "xueqiu", kid, "no-match", "t", "c", "u", "", tags=[]
    )
    assert pending_id is not None and no_match_id is not None
    pending_row = db.get_post(pending_id)
    no_match_row = db.get_post(no_match_id)
    assert pending_row is not None and no_match_row is not None

    assert pending_row["tags"] == ""
    assert no_match_row["tags"] == "[]"
    assert [p["external_id"] for p in db.list_posts(untagged_only=True)] == ["pending"]
    assert db.tag_stats() == {
        "total": 2,
        "processed": 1,
        "tagged": 0,
        "pending": 1,
    }


def test_duplicate_kol_migration_merges_subscription_flags(tmp_path):
    path = tmp_path / "legacy.db"
    db = DB(str(path))
    uid = db.add_user("merge", "h")
    other_uid = db.add_user("merge-other", "h")
    keep_id = db.add_kol("xueqiu", "A", "same")
    db.add_subscription(uid, keep_id, type="post")
    db.add_subscription(other_uid, keep_id, type="post")
    db.close()

    conn = sqlite3.connect(path)
    conn.execute("DROP INDEX uq_kols_platform_external")
    sub_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(subscriptions)").fetchall()
    }
    if "hide_images" not in sub_columns:
        conn.execute(
            "ALTER TABLE subscriptions "
            "ADD COLUMN hide_images INTEGER NOT NULL DEFAULT 0"
        )
    conn.execute(
        "UPDATE subscriptions SET hide_images = 1 "
        "WHERE user_id = ? AND kol_id = ?",
        (other_uid, keep_id),
    )
    duplicate_id = conn.execute(
        "INSERT INTO kols (platform, name, external_id) VALUES ('xueqiu', 'B', 'same')"
    ).lastrowid
    conn.executemany(
        "INSERT INTO subscriptions "
        "(user_id, kol_id, type, favorite, secondary, hide_images) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (uid, duplicate_id, "reply", 1, 1, 1),
            (other_uid, duplicate_id, "post", 0, 0, 0),
        ],
    )
    conn.commit()
    conn.close()

    migrated = DB(str(path))
    rows = migrated.list_subscriptions(uid)
    assert len(rows) == 1
    assert rows[0]["subscribe_type"] == "both"
    assert rows[0]["favorite"] == 1
    assert rows[0]["secondary"] == 1
    assert rows[0]["hide_images"] == 1
    assert migrated.list_subscriptions(other_uid)[0]["hide_images"] == 1


def test_transfer_subscriptions_ors_hide_images_and_secondary(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    columns = {r["name"] for r in db._rows("PRAGMA table_info(subscriptions)")}
    if "hide_images" not in columns:
        db._execute(
            "ALTER TABLE subscriptions "
            "ADD COLUMN hide_images INTEGER NOT NULL DEFAULT 0"
        )
    source_uid = db.add_user("source", "h")
    target_uid = db.add_user("target", "h")
    source_hidden = db.add_kol("xueqiu", "A", "source-hidden")
    target_hidden = db.add_kol("xueqiu", "B", "target-hidden")
    source_only = db.add_kol("xueqiu", "C", "source-only")
    for kid in (source_hidden, target_hidden):
        db.add_subscription(target_uid, kid)
    for kid in (source_hidden, target_hidden, source_only):
        db.add_subscription(source_uid, kid)
    db._execute(
        "UPDATE subscriptions SET hide_images = 1, secondary = 1 "
        "WHERE user_id = ? AND kol_id IN (?, ?)",
        (source_uid, source_hidden, source_only),
    )
    db._execute(
        "UPDATE subscriptions SET hide_images = 1, secondary = 1 "
        "WHERE user_id = ? AND kol_id = ?",
        (target_uid, target_hidden),
    )

    db.transfer_subscriptions(source_uid, target_uid)

    transferred = {
        row["kol_id"]: (row["hide_images"], row["secondary"])
        for row in db._rows(
            "SELECT kol_id, hide_images, secondary FROM subscriptions "
            "WHERE user_id = ?",
            (target_uid,),
        )
    }
    assert transferred == {
        source_hidden: (1, 1),
        target_hidden: (1, 1),
        source_only: (1, 1),
    }
    assert db.list_subscriptions(source_uid) == []


def test_kol_and_pending_request_unique_indexes(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    uid = db.add_user("unique", "h")
    db.add_kol("xueqiu", "A", "same")
    with pytest.raises(ValueError):
        db.add_kol("xueqiu", "B", "same")
    cid = db.add_category("宏观")
    db.add_kol_request("weibo", "same", uid, category_id=cid)
    with pytest.raises(ValueError):
        db.add_kol_request("weibo", "same", uid, category_id=cid)

    indexes = {r["name"] for r in db._rows("PRAGMA index_list(kols)")}
    assert "uq_kols_platform_external" in indexes
    request_indexes = {r["name"] for r in db._rows("PRAGMA index_list(kol_requests)")}
    assert "uq_kol_requests_pending" in request_indexes


def test_delete_kol_rolls_back_on_failure(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    uid = db.add_user("rollback", "h")
    kid = db.add_kol("xueqiu", "A", "rollback")
    db.add_subscription(uid, kid)
    post_id = db.insert_post("xueqiu", kid, "p1", "t", "c", "u", "")
    db.add_push_log(post_id, "telegram", "success", user_id=uid)
    db._execute(
        "CREATE TRIGGER fail_post_delete BEFORE DELETE ON posts "
        "BEGIN SELECT RAISE(ABORT, 'stop'); END"
    )

    with pytest.raises(sqlite3.IntegrityError):
        db.delete_kol(kid)

    assert db.get_kol(kid) is not None
    assert db.list_subscriptions(uid)
    assert db.list_push_logs(user_id=uid)


def test_delete_user_rolls_back_on_failure(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    uid = db.add_user("rollback", "h")
    kid = db.add_kol("xueqiu", "A", "rollback-user")
    db.add_subscription(uid, kid)
    db._execute(
        "CREATE TRIGGER fail_user_delete BEFORE DELETE ON users "
        "BEGIN SELECT RAISE(ABORT, 'stop'); END"
    )

    with pytest.raises(sqlite3.IntegrityError):
        db.delete_user(uid)

    assert db.get_user(uid) is not None
    assert db.list_subscriptions(uid)


def test_update_post_tags_empty_list_marks_post_processed(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    kid = db.add_kol("xueqiu", "测试", "tag-update")
    post_id = db.insert_post("xueqiu", kid, "p1", "t", "c", "u", "")
    assert post_id is not None

    db.update_post_tags(post_id, [])

    row = db.get_post(post_id)
    assert row is not None
    assert row["tags"] == "[]"
    assert db.tag_stats()["pending"] == 0


def test_insert_post_ignore_does_not_leave_open_txn(tmp_path):
    """IGNORE 命中唯一约束后不能留下悬空事务（否则下一个 BEGIN 报 nested transaction）。"""
    db = DB(str(tmp_path / "t.db"))
    kid = db.add_kol("xueqiu", "A", "txn-ignore")
    assert db.insert_post("xueqiu", kid, "p1", "t", "c", "u", "") is not None
    assert db.insert_post("xueqiu", kid, "p1", "t", "c", "u", "") is None  # IGNORE 命中
    assert db.insert_post("xueqiu", kid, "p2", "t", "c", "u", "") is not None
    # 悬空事务会在这里抛 sqlite3.OperationalError: cannot start a transaction within a transaction
    db._conn.execute("BEGIN")
    db._conn.execute("SELECT 1")
    db._conn.commit()


def test_register_codes_migrate_batch_columns(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE register_codes (
            code TEXT PRIMARY KEY,
            note TEXT NOT NULL DEFAULT '',
            used_by INTEGER,
            used_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute(
        "INSERT INTO register_codes (code, note) VALUES ('OLDCODE1', '朋友'), ('OLDCODE2', '内部')"
    )
    conn.commit()
    conn.close()

    db = DB(str(path))
    cols = {r["name"] for r in db._rows("PRAGMA table_info(register_codes)")}
    assert {"batch_id", "expires_at", "revoked_at", "created_by"} <= cols
    rows = db.list_register_codes()
    assert len(rows) == 2
    assert all(r["batch_id"] for r in rows)
    assert rows[0]["batch_id"] != rows[1]["batch_id"]
    assert all(r["expires_at"] in (None, "") for r in rows)
    assert all(r["revoked_at"] in (None, "") for r in rows)
    db.close()


def test_add_and_list_register_code_batch_fields(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    admin_id = db.add_user("admin01", "h", is_admin=True)
    db.add_register_code(
        "ABCD2345",
        note="朋友",
        batch_id="batch01",
        expires_at="2030-01-01 00:00:00",
        created_by=admin_id,
    )
    db.add_register_code("EFGH6789", note="朋友", batch_id="batch01")
    rows = [r for r in db.list_register_codes() if r["batch_id"] == "batch01"]
    assert {r["code"] for r in rows} == {"ABCD2345", "EFGH6789"}
    one = next(r for r in rows if r["code"] == "ABCD2345")
    assert one["created_by_name"] == "admin01"
    assert one["expires_at"] == "2030-01-01 00:00:00"
    db.close()


def test_register_with_code_rejects_revoked_and_expired(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    db.add_register_code("AVAIL001")
    uid = db.register_with_code("AVAIL001", "user01", "hash")
    assert uid > 0
    with pytest.raises(ValueError, match="无效或已被使用"):
        db.register_with_code("AVAIL001", "user02", "hash")

    db.add_register_code("REVOKED1")
    assert db.revoke_register_code("REVOKED1")
    with pytest.raises(ValueError, match="已作废"):
        db.register_with_code("REVOKED1", "user03", "hash")

    db.add_register_code("EXPIRED1")
    db._execute(
        "UPDATE register_codes SET expires_at = datetime('now', '-1 day') WHERE code = 'EXPIRED1'"
    )
    with pytest.raises(ValueError, match="已过期"):
        db.register_with_code("EXPIRED1", "user04", "hash")
    assert db.get_user_by_username_ci("user03") is None
    assert db.get_user_by_username_ci("user04") is None
    db.close()


def test_revoke_and_update_register_code_note(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    db.add_register_code("NOTE0001", note="朋友", batch_id="b1")
    db.add_register_code("NOTE0002", note="朋友", batch_id="b1")
    db.register_with_code("NOTE0001", "used01", "hash")
    assert db.revoke_register_code("NOTE0001") is False
    assert db.revoke_register_code("NOTE0002") is True
    row = db.get_register_code("NOTE0002")
    assert row["revoked_at"]
    assert db.revoke_unused_in_batch("b1") == 0
    db.add_register_code("NOTE0003", note="x", batch_id="b2")
    db.add_register_code("NOTE0004", note="x", batch_id="b2")
    db.register_with_code("NOTE0003", "used02", "hash")
    assert db.revoke_unused_in_batch("b2") == 1
    assert db.get_register_code("NOTE0003")["revoked_at"] in (None, "")
    assert db.get_register_code("NOTE0004")["revoked_at"]
    db.update_register_code_note("NOTE0003", "给张三")
    assert db.get_register_code("NOTE0003")["note"] == "给张三"
    db.close()


def _ima_row(group_id, media_id, *, name=None, tags=None, **kwargs):
    row = {
        "group_id": group_id,
        "media_id": media_id,
        "day": "20260826",
        "valid_day": "20260826",
        "name": name or media_id,
        "group_name": group_id,
        "name_folded": (name or media_id).casefold(),
        "metadata_folded": group_id.casefold(),
        "abstract": "abstract",
        "abstract_folded": "abstract",
        "abstract_zh": "",
        "abstract_src_hash": "hash",
        "cover_url": "",
        "tags_json": "[]",
        "size": 0,
        "chars": 8,
        "has_pdf": 1,
        "has_txt": 0,
        "pdf_path": f"{media_id}.pdf",
        "txt_path": "",
        "downloaded_at": "2026-08-26T00:00:00+00:00",
        "tags": tags or [],
    }
    row.update(kwargs)
    return row


def test_ima_document_index_schema_and_migration(tmp_path):
    db = DB(str(tmp_path / "ima-index.db"))
    tables = {
        row["name"]
        for row in db._rows(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "ima_document_index",
        "ima_document_tags",
        "ima_document_index_meta",
    } <= tables
    assert {
        "idx_ima_doc_latest",
        "idx_ima_doc_group_latest",
        "idx_ima_doc_tag_group",
        "idx_ima_doc_group_tag",
    } <= {
        row["name"]
        for table in (
            "ima_document_index",
            "ima_document_tags",
        )
        for row in db._rows(f"PRAGMA index_list({table})")
    }
    columns = {row["name"] for row in db._rows("PRAGMA table_info(ima_document_index)")}
    assert {
        "group_id",
        "media_id",
        "day",
        "valid_day",
        "name",
        "group_name",
        "name_folded",
        "metadata_folded",
        "abstract",
        "abstract_folded",
        "abstract_zh",
        "abstract_src_hash",
        "cover_url",
        "tags_json",
        "size",
        "chars",
        "has_pdf",
        "has_txt",
        "pdf_path",
        "txt_path",
        "downloaded_at",
    } <= columns
    assert db.ima_document_index_meta()["status"] == "fallback"
    db.reopen()
    assert db.ima_document_index_meta()["status"] == "fallback"


def test_ima_document_group_replace_is_scoped_and_atomic(tmp_path):
    db = DB(str(tmp_path / "ima-group.db"))
    db.replace_ima_document_index(
        [_ima_row("one", "old"), _ima_row("two", "keep")], "before", 10
    )
    db.replace_ima_document_group("one", [_ima_row("one", "new", tags=["new-tag"])])
    assert db._rows("SELECT media_id FROM ima_document_index WHERE group_id = 'one'") == [
        {"media_id": "new"}
    ]
    assert db._rows("SELECT media_id FROM ima_document_index WHERE group_id = 'two'") == [
        {"media_id": "keep"}
    ]
    assert db._rows("SELECT tag FROM ima_document_tags WHERE group_id = 'one'") == [
        {"tag": "new-tag"}
    ]

    db._execute(
        "CREATE TRIGGER ima_fail_group BEFORE INSERT ON ima_document_index "
        "WHEN NEW.media_id = 'bad' BEGIN SELECT RAISE(ABORT, 'controlled failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="controlled failure"):
        db.replace_ima_document_group(
            "one", [_ima_row("one", "replacement"), _ima_row("one", "bad")]
        )
    assert db._rows("SELECT media_id FROM ima_document_index WHERE group_id = 'one'") == [
        {"media_id": "new"}
    ]
    assert db._rows("SELECT media_id FROM ima_document_index WHERE group_id = 'two'") == [
        {"media_id": "keep"}
    ]


def test_ima_document_index_replace_and_batch_upsert(tmp_path):
    db = DB(str(tmp_path / "ima-batch.db"))
    first = _ima_row("one", "one", tags=["old"])
    db.replace_ima_document_index([first], "fp-1", 12)
    meta = db.ima_document_index_meta()
    assert meta["status"] == "ready"
    assert meta["version"] == 1
    assert meta["fingerprint"] == "fp-1"
    assert meta["duration_ms"] == 12
    assert meta["document_count"] == 1

    changed = _ima_row("one", "one", name="changed", tags=["new", "second"])
    added = _ima_row("two", "two", tags=["new"])
    assert db.update_ima_document_batch([changed, added], "fp-2") == 2
    assert db._rows(
        "SELECT name FROM ima_document_index WHERE group_id = 'one' AND media_id = 'one'"
    )[0]["name"] == "changed"
    assert db._rows("SELECT tag FROM ima_document_tags WHERE group_id = 'one'") == [
        {"tag": "new"},
        {"tag": "second"},
    ]
    assert db.ima_document_index_meta()["fingerprint"] == "fp-2"
    assert db.update_ima_document_batch([], "ignored") == 0
    assert db.ima_document_index_meta()["fingerprint"] == "fp-2"


def test_ima_document_index_meta_status_and_rollback(tmp_path):
    db = DB(str(tmp_path / "ima-meta.db"))
    db.replace_ima_document_index([_ima_row("one", "old")], "stable", 3)
    db.mark_ima_document_index("rebuilding")
    assert db.ima_document_index_meta()["status"] == "rebuilding"
    with pytest.raises(ValueError, match="invalid"):
        db.mark_ima_document_index("invalid")

    db._execute(
        "CREATE TRIGGER ima_fail_all BEFORE INSERT ON ima_document_index "
        "WHEN NEW.media_id = 'bad' BEGIN SELECT RAISE(ABORT, 'controlled failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="controlled failure"):
        db.replace_ima_document_index(
            [_ima_row("one", "new"), _ima_row("one", "bad")], "broken", 99
        )
    assert db._rows("SELECT media_id FROM ima_document_index") == [{"media_id": "old"}]
    meta = db.ima_document_index_meta()
    assert meta["status"] == "rebuilding"
    assert meta["fingerprint"] == "stable"
    assert meta["document_count"] == 1


def test_default_tag_rules_cover_market_topics():
    from app.db import DEFAULT_TAG_RULES
    from app.tagging import TAG_VOCABULARY_MAX

    names = {r["tag"] for r in DEFAULT_TAG_RULES}
    for name in ("宏观", "科技", "美股", "港股", "黄金", "大宗", "医药", "加密", "理念", "调仓"):
        assert name in names
    assert len(DEFAULT_TAG_RULES) <= TAG_VOCABULARY_MAX
    assert all(r.get("keywords") for r in DEFAULT_TAG_RULES)


def test_merge_default_stock_aliases_seeds_and_purges(tmp_path):
    from app.db import DB

    db = DB(str(tmp_path / "alias.db"))
    db.set_stock_aliases(
        [
            {"alias": "宁德", "stock": "宁德时代"},
            {"alias": "涂改液", "stock": "五粮液"},
        ]
    )
    result = db.merge_default_stock_aliases()
    aliases = {a["alias"]: a["stock"] for a in db.get_stock_aliases()}
    assert aliases["涂改液"] == "五粮液"
    assert aliases["宁王"] == "宁德时代"
    assert aliases["药茅"] == "恒瑞医药"
    assert "宁德" not in aliases
    assert any(a["alias"] == "宁德" for a in result["purged"])
    assert {a["alias"] for a in result["seeded"]} == {"宁王", "药茅"}
    db.close()


def test_merge_default_tag_vocabulary_adds_missing_keeps_custom(tmp_path):
    from app.db import DB, DEFAULT_TAG_RULES

    db = DB(str(tmp_path / "t.db"))
    db.set_tag_vocabulary([{"tag": "宏观", "keywords": ["只留央行"]}])
    added = db.merge_default_tag_vocabulary()
    assert added >= 1
    tags = {r["tag"]: r["keywords"] for r in db.get_tag_vocabulary()}
    assert tags["宏观"] == ["只留央行"]
    for rule in DEFAULT_TAG_RULES:
        assert rule["tag"] in tags
    db.close()
