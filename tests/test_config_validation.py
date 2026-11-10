# -*- coding: utf-8 -*-
"""启动配置校验测试"""
import types

import pytest

from wechat_companion import config
from wechat_companion.exceptions import ConfigValidationError
from wechat_companion.validation import validate, validate_or_raise


def _with_required_fields():
    """
    复制当前配置，仅补齐“必须由使用者填写”的字段。

    公开仓库里 TARGET_WXID / DEEPSEEK_API_KEY 默认为空，目的是不把任何
    真实账号写进代码；校验逻辑本身仍应能用一组示例值跑通，因此这里只
    在缺失时填示例值，其余参数沿用配置里的默认值。
    """
    cfg = types.SimpleNamespace()
    for name in dir(config):
        if name.isupper():
            setattr(cfg, name, getattr(config, name))
    if not str(cfg.TARGET_WXID).strip():
        cfg.TARGET_WXID = "wxid_example"
    if not str(cfg.TARGET_NAME).strip():
        cfg.TARGET_NAME = "示例联系人"
    if not str(cfg.DEEPSEEK_API_KEY).strip():
        cfg.DEEPSEEK_API_KEY = "sk-" + "0" * 32
    return cfg


def test_shipped_defaults_are_valid_with_required_fields():
    """默认参数结构必须能通过校验（不依赖本机 local_config.json）"""
    cfg = _with_required_fields()
    assert validate(cfg) == []
    validate_or_raise(cfg)


class _BadConfig:
    TARGET_WXID = ""
    COMPANION_NAME = ""
    SYSTEM_PROMPT = ""
    DEEPSEEK_API_KEY = ""
    DEEPSEEK_BASE_URL = "ftp://x"
    DEEPSEEK_MODEL = ""
    DEEPSEEK_TIMEOUT = 0
    DEEPSEEK_TEMPERATURE = 5
    DEEPSEEK_MAX_RETRIES = -1
    KEEP_ROUNDS = 0
    POLL_INTERVAL = 0.1
    STABLE_CHECKS = 0
    REPLY_COOLDOWN = -1
    TYPE_THINK_DELAY = (3, 1)
    HUMANIZE_DELAY = (1,)
    WINDOW_WIDTH = 10
    WINDOW_HEIGHT = 10
    STOP_VK = "x"
    DRY_RUN = "no"


def test_bad_config_collects_all_errors():
    errors = validate(_BadConfig)
    joined = " ".join(errors)
    for key in (
        "TARGET_WXID", "DEEPSEEK_API_KEY", "KEEP_ROUNDS", "POLL_INTERVAL",
        "STABLE_CHECKS", "TYPE_THINK_DELAY", "STOP_VK", "DRY_RUN",
    ):
        assert key in joined
    with pytest.raises(ConfigValidationError):
        validate_or_raise(_BadConfig)
