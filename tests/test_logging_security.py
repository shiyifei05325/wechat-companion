# -*- coding: utf-8 -*-
"""日志设施与密钥脱敏测试"""
import logging

from wechat_companion.logging_setup import configure_logging, redact


def test_redact_api_key():
    raw = "密钥是 sk-demo0000000000000000000000000000，别泄露"
    out = redact(raw)
    assert "demo00000000" not in out
    assert "REDACTED" in out


def test_redact_bearer_token():
    raw = "Authorization: Bearer abcdef1234567890ABCDEF"
    out = redact(raw)
    assert "abcdef1234" not in out
    assert "REDACTED" in out


def test_redact_non_string_passthrough():
    assert redact(123) == 123
    assert redact(None) is None


def test_log_file_redacts_secrets(tmp_path):
    """文件处理器 + 脱敏过滤器：密钥不得落盘"""
    import logging
    from logging.handlers import RotatingFileHandler

    from wechat_companion.logging_setup import _RedactionFilter

    log_path = tmp_path / "app.log"
    logger = logging.getLogger("redaction_test_" + tmp_path.name)
    handler = RotatingFileHandler(log_path, encoding="utf-8")
    handler.addFilter(_RedactionFilter())
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info("调用密钥 sk-demo0000000000000000000000000000 进行请求")
    handler.flush()

    content = log_path.read_text(encoding="utf-8")
    assert "demo00000000" not in content
    assert "REDACTED" in content


def test_configure_logging_is_idempotent(tmp_path):
    log = configure_logging(str(tmp_path), console=False)
    before = len(log.handlers)
    configure_logging(str(tmp_path), console=False)
    assert len(log.handlers) == before
