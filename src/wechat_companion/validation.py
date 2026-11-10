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
    if float(g("DEEPSEEK_TIMEOUT", 0)) <= 0:
        errors.append("DEEPSEEK_TIMEOUT 必须为正数")
    temp = float(g("DEEPSEEK_TEMPERATURE", 1.0))
    if not 0 <= temp <= 2:
        errors.append("DEEPSEEK_TEMPERATURE 建议在 0~2 之间")
    if int(g("DEEPSEEK_MAX_RETRIES", 0)) < 0:
        errors.append("DEEPSEEK_MAX_RETRIES 不能为负")

    # 记忆 / 节奏
    if int(g("KEEP_ROUNDS", 0)) < 1:
        errors.append("KEEP_ROUNDS 至少为 1")
    if float(g("POLL_INTERVAL", 0)) < 0.3:
        errors.append("POLL_INTERVAL 不建议小于 0.3 秒（避免高频截图造成卡顿）")
    if int(g("STABLE_CHECKS", 0)) < 1:
        errors.append("STABLE_CHECKS 至少为 1")
    if float(g("REPLY_COOLDOWN", 0)) < 0:
        errors.append("REPLY_COOLDOWN 不能为负")
    _check_pair(g("TYPE_THINK_DELAY"), "TYPE_THINK_DELAY", errors)
    _check_pair(g("HUMANIZE_DELAY"), "HUMANIZE_DELAY", errors)

    # 窗口
    if int(g("WINDOW_WIDTH", 0)) < 200 or int(g("WINDOW_HEIGHT", 0)) < 200:
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
