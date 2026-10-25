from atlas.core.observability.logging import REDACTED, redact_mapping, redact_value


def test_sensitive_keys_redacted():
    out = redact_mapping(
        {"api_key": "abc", "password": "p", "nested": {"Authorization": "x"}, "ok": 1}
    )
    assert out["api_key"] == REDACTED and out["password"] == REDACTED
    assert out["nested"]["Authorization"] == REDACTED and out["ok"] == 1


def test_secret_like_values_redacted_under_any_key():
    msg = (
        "key PKABCDEFGHIJKLMNOPQR and sk-ant-api03-abcdefghijk and "
        "Bearer eyJhbGciOi.eyJzdWIi.sig and 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
    )
    out = redact_value(msg)
    assert "PKABCDEFGHIJKLMNOPQR" not in out
    assert "sk-ant-api03" not in out
    assert "eyJhbGciOi" not in out
    assert "ABCdefGHIjkl" not in out


def test_lists_redacted():
    assert redact_value(["PKABCDEFGHIJKLMNOPQR"]) == [REDACTED]


def test_telegram_url_token_redacted():
    out = redact_value("POST https://api.telegram.org/bot123456:secretTOKEN/sendMessage")
    assert "secretTOKEN" not in out


def test_stdlib_filter_keeps_formatting_and_redacts():
    import logging

    from atlas.core.observability.logging import _RedactingFilter

    rec = logging.LogRecord(
        "x", logging.INFO, "f", 1, "status %d key %s", (200, "PKABCDEFGHIJKLMNOPQR"), None
    )
    _RedactingFilter().filter(rec)
    assert rec.getMessage() == f"status 200 key {REDACTED}"
