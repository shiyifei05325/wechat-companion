# -*- coding: utf-8 -*-
"""brain 历史双约束裁剪测试（条数 + token 预算），不发网络请求"""
import types

from wechat_companion.brain import DeepSeekCompanion


def _fake_cfg(tmp_path, keep_rounds=12, max_tokens=0):
    return types.SimpleNamespace(
        DEEPSEEK_API_KEY="sk-test",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
        DEEPSEEK_MODEL="deepseek-chat",
        DEEPSEEK_TIMEOUT=30,
        DEEPSEEK_TEMPERATURE=1.0,
        DEEPSEEK_MAX_RETRIES=2,
        COMPANION_NAME="老头",
        SYSTEM_PROMPT="你是测试伴侣",
        KEEP_ROUNDS=keep_rounds,
        LOG_DIR=str(tmp_path),
        HISTORY_PERSIST=False,
        MAX_HISTORY_TOKENS=max_tokens,
    )


def _m(role, content):
    return {"role": role, "content": content}


def test_approx_tokens_cjk_and_english(tmp_path):
    brain = DeepSeekCompanion(_fake_cfg(tmp_path))
    # 非 CJK 部分有 max(1, ...) 兜底，纯 CJK 也会保守 +1
    assert brain._approx_tokens("你好") == 3          # 2 CJK + 兜底 1
    assert brain._approx_tokens("abcd") == 1          # 4 个英文字符按 1 token
    assert brain._approx_tokens("你好ab") == 3        # 2 CJK + 兜底 1
    brain.close()


def test_trim_by_count(tmp_path):
    brain = DeepSeekCompanion(_fake_cfg(tmp_path, keep_rounds=1))
    brain.history = [_m("user", f"消息{i}") for i in range(6)]
    brain._trim_history()
    assert len(brain.history) == 2
    assert brain.history[-1]["content"] == "消息5"
    brain.close()


def test_trim_by_token_budget(tmp_path):
    # 每条 10 个 CJK 字 ≈ 10 token；预算仅 10，至少保留 2 条
    brain = DeepSeekCompanion(_fake_cfg(tmp_path, keep_rounds=10, max_tokens=10))
    long_text = "字" * 10
    brain.history = [
        _m("user" if i % 2 == 0 else "assistant", f"{long_text}{i}")
        for i in range(8)
    ]
    brain._trim_history()
    # 从最旧成对删除，直到只剩 2 条（受 len>2 下限保护）
    assert len(brain.history) == 2
    assert brain.history[-1]["content"] == f"{long_text}7"
    brain.close()


def test_trim_keeps_when_under_budget(tmp_path):
    brain = DeepSeekCompanion(_fake_cfg(tmp_path, keep_rounds=10, max_tokens=1000))
    brain.history = [_m("user", "短"), _m("assistant", "嗯")]
    brain._trim_history()
    assert len(brain.history) == 2
    brain.close()
