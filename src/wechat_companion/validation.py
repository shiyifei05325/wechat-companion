# -*- coding: utf-8 -*-
"""
启动配置校验：fail-fast，配置不合法时给出逐条可操作的问题描述，
避免程序带着错误配置运行到一半才以难以排查的方式失败。
"""
from collections.abc import Sequence

from .exceptions import ConfigValidationError


def _check_pair(value, name, errors):
    if not isinstance(value, Sequence) or len(value) != 2:
        errors.append(f"{name} 必须是两个数值")
        return
    try:
        a, b = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        errors.append(f"{name} 必须是数值")
        return
    if a < 0 or b < 0 or a > b:
        errors.append(f"{name} 数值范围不合法（需非负且下限≤上限）")


def _to_float(value, name, errors):
    """安全转 float：失败时记一条错误并返回 None，绝不抛出中断整个校验"""
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{name} 必须是数值")
        return None


def _to_int(value, name, errors):
    """安全转 int：失败时记一条错误并返回 None，绝不抛出中断整个校验"""
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{name} 必须是整数")
        return None


def validate(cfg):
    """
    校验配置模块/对象，返回问题描述列表（空列表表示通过）。
    只读取、不抛异常，便于一次性展示全部问题。
    """
    errors = []

    def g(name, default=None):
        return getattr(cfg, name, default)

    # 目标用户 / 人设
    if not str(g("TARGET_WXID", "")).strip():
        errors.append("TARGET_WXID 不能为空（要监听的微信号）")
    if not str(g("COMPANION_NAME", "")).strip():
        errors.append("COMPANION_NAME 不能为空")
    if not str(g("SYSTEM_PROMPT", "")).strip():
        errors.append("SYSTEM_PROMPT 不能为空")

    # DeepSeek
    if not str(g("DEEPSEEK_API_KEY", "")).strip():
        errors.append("DEEPSEEK_API_KEY 不能为空（config.py 或环境变量）")
    base_url = str(g("DEEPSEEK_BASE_URL", ""))
    if not base_url.startswith(("http://", "https://")):
        errors.append("DEEPSEEK_BASE_URL 必须以 http:// 或 https:// 开头")
    if not str(g("DEEPSEEK_MODEL", "")).strip():
        errors.append("DEEPSEEK_MODEL 不能为空")
    timeout = _to_float(g("DEEPSEEK_TIMEOUT", 0), "DEEPSEEK_TIMEOUT", errors)
    if timeout is not None and timeout <= 0:
        errors.append("DEEPSEEK_TIMEOUT 必须为正数")
    temp = _to_float(g("DEEPSEEK_TEMPERATURE", 1.0), "DEEPSEEK_TEMPERATURE", errors)
    if temp is not None and not 0 <= temp <= 2:
        errors.append("DEEPSEEK_TEMPERATURE 建议在 0~2 之间")
    max_retries = _to_int(g("DEEPSEEK_MAX_RETRIES", 0), "DEEPSEEK_MAX_RETRIES", errors)
    if max_retries is not None and max_retries < 0:
        errors.append("DEEPSEEK_MAX_RETRIES 不能为负")

    # 记忆 / 节奏
    keep_rounds = _to_int(g("KEEP_ROUNDS", 0), "KEEP_ROUNDS", errors)
    if keep_rounds is not None and keep_rounds < 1:
        errors.append("KEEP_ROUNDS 至少为 1")
    max_tokens = _to_int(g("MAX_HISTORY_TOKENS", 0), "MAX_HISTORY_TOKENS", errors)
    if max_tokens is not None and max_tokens < 100:
        errors.append("MAX_HISTORY_TOKENS 不建议小于 100")
    if not isinstance(g("HISTORY_PERSIST"), bool):
        errors.append("HISTORY_PERSIST 必须是布尔值")
    if not str(g("OCR_LANG", "")).strip():
        errors.append("OCR_LANG 不能为空")
    if not isinstance(g("OCR_FALLBACK_ENABLED"), bool):
        errors.append("OCR_FALLBACK_ENABLED 必须是布尔值")
    poll = _to_float(g("POLL_INTERVAL", 0), "POLL_INTERVAL", errors)
    if poll is not None and poll < 0.3:
        errors.append("POLL_INTERVAL 不建议小于 0.3 秒（避免高频截图造成卡顿）")
    stable = _to_int(g("STABLE_CHECKS", 0), "STABLE_CHECKS", errors)
    if stable is not None and stable < 1:
        errors.append("STABLE_CHECKS 至少为 1")
    cooldown = _to_float(g("REPLY_COOLDOWN", 0), "REPLY_COOLDOWN", errors)
    if cooldown is not None and cooldown < 0:
        errors.append("REPLY_COOLDOWN 不能为负")
    _check_pair(g("TYPE_THINK_DELAY"), "TYPE_THINK_DELAY", errors)
    _check_pair(g("HUMANIZE_DELAY"), "HUMANIZE_DELAY", errors)

    # 窗口
    win_w = _to_int(g("WINDOW_WIDTH", 0), "WINDOW_WIDTH", errors)
    win_h = _to_int(g("WINDOW_HEIGHT", 0), "WINDOW_HEIGHT", errors)
    if (win_w is not None and win_w < 200) or (win_h is not None and win_h < 200):
        errors.append("窗口宽高过小（至少 200px）")

    # 安全
    if not isinstance(g("STOP_VK"), int):
        errors.append("STOP_VK 必须是整数虚拟键码")
    if not isinstance(g("DRY_RUN"), bool):
        errors.append("DRY_RUN 必须是布尔值")

    return errors


def validate_or_raise(cfg):
    """校验失败时抛 ConfigValidationError；通过时返回 None"""
    errors = validate(cfg)
    if errors:
        raise ConfigValidationError(errors)
    return None
