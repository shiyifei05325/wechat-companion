# -*- coding: utf-8 -*-
"""会话历史 SQLite 持久化测试（使用临时数据库，不触碰真实 runtime.db）"""
from wechat_companion import memory_store as ms


def _patch_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ms, "DB_PATH", str(tmp_path / "test_history.db"))


def _msg(role, content):
    return {"role": role, "content": content}


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    history = [
        _msg("user", "在吗"),
        _msg("assistant", "在呢"),
        _msg("user", "吃饭了吗"),
    ]
    ms.save_history(history)
    loaded = ms.load_history()
    assert loaded == history


def test_save_overwrites_previous(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    ms.save_history([_msg("user", "旧消息")])
    ms.save_history([_msg("assistant", "新消息")])
    loaded = ms.load_history()
    assert loaded == [_msg("assistant", "新消息")]


def test_load_respects_limit(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    history = [_msg("user", f"消息{i}") for i in range(6)]
    ms.save_history(history)
    loaded = ms.load_history(limit=2)
    # 取最近 2 条，且按正序返回
    assert loaded == history[-2:]


def test_filters_invalid_role_and_non_list(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    ms.save_history("not-a-list")  # 非列表直接忽略，不报错
    assert ms.load_history() == []
    ms.save_history([
        _msg("user", "有效"),
        {"role": "system", "content": "应被过滤"},
        {"role": "user"},  # 缺 content，str(None) 兜底不报错
    ])
    loaded = ms.load_history()
    assert all(m["role"] in ("user", "assistant") for m in loaded)
    assert any(m["content"] == "有效" for m in loaded)


def test_clear_history(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    ms.save_history([_msg("user", "待清除")])
    ms.clear_history()
    assert ms.load_history() == []
