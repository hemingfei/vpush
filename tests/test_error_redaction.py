"""错误文本脱敏：凭据不得随异常原文进 push_logs / error_logs。"""
import logging

from app.db import DB
from app.logging_setup import (
    ErrorDbHandler,
    RedactingFormatter,
    RingBufferHandler,
    _ring,
    _ring_lock,
    recent_logs,
    redact_secrets,
    register_error_sink,
)


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


def test_redact_secrets_cookie_and_api_key_names():
    short = "short8"
    long = "long-secret-value-1234567890"
    text = (
        f"Cookie: auth_token={short}; ct0={long}; "
        f"ima-openapi-apikey={short}; api_key={long}"
    )
    out = redact_secrets(text)
    assert short not in out and long not in out
    assert out.count("<redacted>") == 4


def test_redact_secrets_does_not_match_prefixed_key_names():
    text = "my_api_key=ordinary-value api_key_suffix=ordinary-value"
    assert redact_secrets(text) == text


def test_redact_secrets_cookie_header_forms():
    text = "Cookie: SID=cookie-secret; Path=/ Set-Cookie: SID=set-cookie-secret; Path=/"

    out = redact_secrets(text)

    assert "cookie-secret" not in out
    assert "set-cookie-secret" not in out
    assert "Cookie: SID=<redacted>" in out
    assert "Set-Cookie: SID=<redacted>" in out


def test_error_db_handler_passes_redacted_copy_to_sink():
    captured = []
    register_error_sink(lambda record: captured.append(record))
    handler = ErrorDbHandler()
    secret = "Cookie: SID=cookie-secret Bearer bearer-secret-123456 api_key=api-secret"
    record = logging.LogRecord("test.sink", logging.WARNING, __file__, 1, "%s", (secret,), None)

    try:
        handler.emit(record)
    finally:
        register_error_sink(None)

    assert len(captured) == 1
    safe_record = captured[0]
    assert safe_record.levelno == logging.WARNING
    assert safe_record.name == "test.sink"
    assert safe_record.getMessage() != secret
    for value in ("cookie-secret", "bearer-secret-123456", "api-secret"):
        assert value not in safe_record.getMessage()
    assert record.getMessage() == secret


def test_redacting_formatter_removes_credentials_and_preserves_ordinary_text():
    formatter = RedactingFormatter("%(levelname)s %(message)s")
    secret = "Cookie: auth_token=short8; api_key=long-secret-value-1234567890 Bearer abcdefghijklmnop"
    record = logging.LogRecord("test", logging.WARNING, __file__, 1, "%s", (secret,), None)

    output = formatter.format(record)

    assert "short8" not in output
    assert "long-secret-value-1234567890" not in output
    assert "abcdefghijklmnop" not in output
    ordinary = logging.LogRecord("test", logging.INFO, __file__, 1, "ordinary text", (), None)
    assert formatter.format(ordinary) == "INFO ordinary text"


def test_ring_buffer_redacts_logged_credentials():
    with _ring_lock:
        _ring.clear()
    logger = logging.getLogger("test.redacting-ring")
    handler = RingBufferHandler()
    handler.setFormatter(RedactingFormatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        logger.warning("Cookie: auth_token=short8 api_key=long-secret-value-1234567890 Bearer abcdefghijklmnop")
        lines = recent_logs(limit=1)
    finally:
        logger.removeHandler(handler)

    assert len(lines) == 1
    assert "short8" not in lines[0]
    assert "long-secret-value-1234567890" not in lines[0]
    assert "abcdefghijklmnop" not in lines[0]
    assert "WARNING" in lines[0]


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
