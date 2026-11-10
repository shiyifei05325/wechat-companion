# -*- coding: utf-8 -*-
"""DeepSeek 大脑调用测试（HTTP 全程 mock，不发真实网络请求）"""
import types

from wechat_companion.brain import DeepSeekCompanion


def _fake_cfg(tmp_path, retries=2, rounds=12):
    return types.SimpleNamespace(
        DEEPSEEK_API_KEY="sk-test",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
        DEEPSEEK_MODEL="deepseek-chat",
        DEEPSEEK_TIMEOUT=30,
        DEEPSEEK_TEMPERATURE=1.0,
        DEEPSEEK_MAX_RETRIES=retries,
        COMPANION_NAME="老头",
        SYSTEM_PROMPT="你是测试伴侣",
        KEEP_ROUNDS=rounds,
        LOG_DIR=str(tmp_path),
    )


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def _success_post(answer="在呢宝贝"):
    payload = {
        "choices": [{"message": {"content": answer}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    def _post(url, headers=None, json=None, timeout=None):
        return _FakeResponse(200, payload)

    return _post


def test_reply_success_updates_history(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    brain = DeepSeekCompanion(_fake_cfg(tmp_path))
    monkeypatch.setattr(brain.session, "post", _success_post())
    n0 = len(brain.history)
    out = brain.reply("在吗")
    assert out == "在呢宝贝"
    # 成功后保留用户与伴侣两条消息
    assert len(brain.history) == n0 + 2
    assert brain.history[-2]["content"] == "在吗"
    assert brain.history[-1]["content"] == "在呢宝贝"


def test_reply_failure_pops_user_message(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    def _fail(url, headers=None, json=None, timeout=None):
        return _FakeResponse(500, text="server error")

    brain = DeepSeekCompanion(_fake_cfg(tmp_path, retries=1))
    monkeypatch.setattr(brain.session, "post", _fail)
    n0 = len(brain.history)
    out = brain.reply("在吗")
    assert out is None
    # 失败后用户消息被回滚，上下文长度不变
    assert len(brain.history) == n0


def test_reply_retries_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def _flaky(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            return _FakeResponse(429, text="rate limited")
        return _FakeResponse(200, {
            "choices": [{"message": {"content": "来啦"}}],
            "usage": {"total_tokens": 1},
        })

    brain = DeepSeekCompanion(_fake_cfg(tmp_path, retries=3))
    monkeypatch.setattr(brain.session, "post", _flaky)
    assert brain.reply("在吗") == "来啦"
    assert calls["n"] == 2


def test_history_trimmed_to_keep_rounds(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    captured = {}

    def _capture(url, headers=None, json=None, timeout=None):
        captured["messages"] = json["messages"] if json else None
        return _FakeResponse(200, {
            "choices": [{"message": {"content": "嗯"}}],
            "usage": {"total_tokens": 1},
        })

    brain = DeepSeekCompanion(_fake_cfg(tmp_path, rounds=1))
    monkeypatch.setattr(brain.session, "post", _capture)
    for i in range(5):
        brain.reply(f"消息{i}")
    # 历史本身不含 system：1 轮 = 用户+伴侣 共 2 条
    assert len(brain.history) == 2
    # system 在每次请求时临时拼接在最前面（请求中共 3 条）
    msgs = captured["messages"]
    assert msgs[0]["role"] == "system"
    assert len(msgs) == 3


def test_brain_reuses_http_session(tmp_path):
    """构造时即建立可复用的连接 Session"""
    import requests
    brain = DeepSeekCompanion(_fake_cfg(tmp_path))
    assert isinstance(brain.session, requests.Session)
    assert brain.session.headers.get("Authorization", "").startswith("Bearer ")
    brain.close()
