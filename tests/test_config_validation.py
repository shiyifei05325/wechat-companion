# -*- coding: utf-8 -*-
"""启动配置校验测试"""
import pytest

from wechat_companion import config
from wechat_companion.exceptions import ConfigValidationError
from wechat_companion.validation import validate, validate_or_raise


def test_real_config_is_valid():
    """随仓库交付的配置必须通过校验"""
    assert validate(config) == []
    validate_or_raise(config)


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
