# -*- coding: utf-8 -*-
"""
统一日志设施

- 控制台 + 轮转文件双输出（logs/app.log，单文件 5MB，保留 5 份）
- 自动脱敏：sk- 开头的 API 密钥、Bearer 令牌不会落盘
- 级别可用环境变量 LOG_LEVEL 控制（DEBUG/INFO/WARNING/ERROR）
- configure_logging 可重复调用，不会重复挂载处理器
"""
import logging
import os
import re
from logging.handlers import RotatingFileHandler

_PACKAGE_LOGGER = "wechat_companion"
_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# sk- 密钥、Bearer 令牌
_SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{6,}[A-Za-z0-9]"), "sk-***REDACTED***"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{6,}"), r"\1***REDACTED***"),
]


def redact(text):
    """把文本中的密钥/令牌替换为脱敏占位"""
    if not isinstance(text, str):
        return text
    out = text
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out


class _RedactionFilter(logging.Filter):
    def filter(self, record):
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact(v) for k, v in record.args.items()}
                else:
                    record.args = tuple(redact(a) for a in record.args)
        except Exception:
            # 脱敏逻辑本身绝不能影响日志输出
            pass
        return True


def configure_logging(log_dir, level=None, console=True):
    """
    配置包日志器。
    log_dir: 日志目录；level: 显式级别（默认取环境变量 LOG_LEVEL，再默认 INFO）；
    console: 是否同时输出到标准错误（控制台/父进程重定向日志）。
    返回配置好的 Logger。
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if isinstance(level, str):
        level = getattr(logging, level, logging.INFO)

    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(_PACKAGE_LOGGER)
    logger.setLevel(level)

    redaction = _RedactionFilter()
    formatter = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DATE_FORMAT)

    # 标记已有处理器，保证重复调用幂等
    if not any(getattr(h, "_companion_file", False) for h in logger.handlers):
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler._companion_file = True
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redaction)
        logger.addHandler(file_handler)

    if console and not any(getattr(h, "_companion_console", False) for h in logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler._companion_console = True
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(redaction)
        logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def get_logger(name):
    """获取统一命名的子日志器（传入 __name__ 或模块名均可）"""
    if not name.startswith(_PACKAGE_LOGGER):
        name = f"{_PACKAGE_LOGGER}.{name.split('.')[-1]}" if name else _PACKAGE_LOGGER
    return logging.getLogger(name)
