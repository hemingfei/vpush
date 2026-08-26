"""用户级推送凭据的 at-rest 加密：enc1: 前缀密文 + 明文哈希唯一性列。"""
import sqlite3

from cryptography.fernet import Fernet

from app.db import (
    SECRET_PREFIX,
    DB,
    _secret_hash,
    decrypt_stored_secret,
    user_plain_secret,
)

KEY = Fernet.generate_key().decode()


def _raw(db_path: str, uid_col_values: dict) -> None:
    conn = sqlite3.connect(db_path)
    try:
        for col, val in uid_col_values.items():
            conn.execute(f"UPDATE users SET {col}=? WHERE id=1", (val,))
        conn.commit()
    finally:
        conn.close()


def _raw_value(db_path: str, col: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT {col} FROM users WHERE id=1").fetchone()[0]
    finally:
        conn.close()


def test_write_encrypts_and_hash_allows_lookup(tmp_path):
    db = DB(str(tmp_path / "d.db"), credential_key=KEY)
    uid = db._execute(
        "INSERT INTO users (username, password_hash) VALUES ('u1', 'x')", ()
    )
    db.update_user_atomic(
        uid, {"bark_key": "AaBbCcDdEeFf1234567890", "llm_api_key": "sk-abc12345678"}
    )
    raw = _raw_value(str(tmp_path / "d.db"), "bark_key")
    assert raw.startswith(SECRET_PREFIX) and "AaBb" not in raw
    # 唯一性查找走明文哈希
    hit = db.get_user_by_bark_key("AaBbCcDdEeFf1234567890")
    assert hit is not None and hit["id"] == uid
    assert db.get_user_by_bark_key("different") is None
    # 解出明文
    assert user_plain_secret(db.get_user(uid), "bark_key", db) == "AaBbCcDdEeFf1234567890"
    db.close()


def test_migration_encrypts_legacy_plaintext_idempotent(tmp_path):
    db_path = str(tmp_path / "legacy.db")
    legacy_vals = {
        "telegram_bot_token": "111:AAAbbbCCCdddEEE",
        "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wc123",
        "bark_key": "BarkKey0987654321",
        "llm_api_key": "sk-legacy-000",
    }
    # 未配密钥的旧部署：明文写入
    db0 = DB(db_path)
    uid = db0._execute(
        "INSERT INTO users (username, password_hash) VALUES ('u1', 'x')", ()
    )
    _raw(db_path, legacy_vals)
    db0.close()

    # 升级到配置了密钥的版本：启动迁移应把四列全部收编为密文并补哈希
    db1 = DB(db_path, credential_key=KEY)
    for col, plain in legacy_vals.items():
        stored = _raw_value(db_path, col)
        assert stored.startswith(SECRET_PREFIX), col
        assert user_plain_secret(db1.get_user(uid), col, db1) == plain
    assert db1.get_user_by_wecom_webhook(legacy_vals["wecom_webhook"])["id"] == uid
    assert db1.get_user_by_bark_key(legacy_vals["bark_key"])["id"] == uid

    # 再次重启（同密钥）：幂等，不再改写
    before = {c: _raw_value(db_path, c) for c in legacy_vals}
    db2 = DB(db_path, credential_key=KEY)
    after = {c: _raw_value(db_path, c) for c in legacy_vals}
    assert before == after
    db1.close()
    db2.close()


def test_missing_key_degrades_to_empty_not_crash():
    cipher = SECRET_PREFIX + "gAAAAABmismatched"
    assert decrypt_stored_secret(cipher, "") == ""
    wrong = decrypt_stored_secret(cipher, Fernet.generate_key().decode())
    assert wrong == ""
    assert decrypt_stored_secret("plain-value", "") == "plain-value"


def test_clear_binding_resets_hash(tmp_path):
    db = DB(str(tmp_path / "clear.db"), credential_key=KEY)
    db._execute("INSERT INTO users (username, password_hash) VALUES ('u1', 'x')", ())
    uid = 1
    db.update_user_atomic(uid, {"bark_key": "AaBbCcDdEeFf1234567890"})
    assert db.get_user_by_bark_key("AaBbCcDdEeFf1234567890") is not None
    db.update_user_atomic(uid, {"bark_key": ""})
    assert db.get_user_by_bark_key("AaBbCcDdEeFf1234567890") is None
    row = db.get_user(uid)
    assert not row["bark_key"] and not row["bark_key_hash"]
    db.close()


def test_secret_hash_empty_is_empty():
    assert _secret_hash("") == ""
    assert _secret_hash(None) == ""
