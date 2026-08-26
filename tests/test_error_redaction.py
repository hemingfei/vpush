"""错误文本脱敏：凭据不得随异常原文进 push_logs / error_logs。"""
from app.db import DB
from app.logging_setup import redact_secrets


def test_redact_secrets_patterns():
    assert redact_secrets("https://api.telegram.org/bot123456:ABC-defGHI_jklmnopQRST/failed") == (
        "https://api.telegram.org/bot123456:<redacted>/failed"
    )
    assert "<redacted>" in redact_secrets("400 on send?key=abc123DEF456ghi789JKL")
    assert "<redacted>" in redact_secrets("GET https://api.day.app/AbCdEf123456789/body")
    assert "<redacted>" in redact_secrets("Authorization: Bearer sk-proj-abcdef1234567890abcdef")
    # 微博登录 META 响应里的账号线索
    out = redact_secrets("retcode=101 su=dXNlckBleGFtcGxlLmNvbQ== errcode=…")
    assert "dXNlckBleGFtcGxlLmNvbQ==" not in out
    assert "<redacted>" in out
    assert redact_secrets("") == ""
    assert redact_secrets(None) == ""


def test_db_persisted_errors_are_redacted(tmp_path):
    db = DB(str(tmp_path / "db.sqlite"))
    try:
        log_id = db.add_push_log(1, "telegram", "failed", "bot42:tOKEN_value_123456789012 hit 429")
        rows = db._rows("SELECT error FROM push_logs WHERE id=?", (log_id,))
        assert "tOKEN_value_123456789012" not in rows[0]["error"]

        db.record_error_log("WARNING", "test", "send failed with key=secretKEYvalue987654321")
        rows = db._rows("SELECT message FROM error_logs WHERE logger='test'")
        assert "secretKEYvalue987654321" not in rows[-1]["message"]
    finally:
        db.close()
