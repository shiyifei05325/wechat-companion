# -*- coding: utf-8 -*-
"""配置持久化测试：控制台只写 local_config.json，不修改源码"""
import json

from control import server as cs


def test_source_rewriting_removed():
    """源码改写逻辑应已删除，避免保存配置污染代码仓库"""
    assert not hasattr(cs, "_render_config_py")
    assert not hasattr(cs, "_sync_to_config_py")


def test_write_overrides_excludes_api_key(tmp_path, monkeypatch):
    target = tmp_path / "local_config.json"
    monkeypatch.setattr(cs, "OVERRIDE_PATH", str(target))

    values = cs._effective_config()
    values["DEEPSEEK_API_KEY"] = "sk-should-not-be-written"
    values["TARGET_WXID"] = "wxid_for_test"
    values["TYPE_THINK_DELAY"] = [1.0, 2.0]

    cs._write_overrides(values)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert "DEEPSEEK_API_KEY" not in data
    assert data["TARGET_WXID"] == "wxid_for_test"
    assert data["TYPE_THINK_DELAY"] == [1.0, 2.0]
    assert set(data) == set(cs.FIELD_TYPES) - cs.SECRET_FIELDS


def test_write_overrides_merges_and_drops_secret(tmp_path, monkeypatch):
    target = tmp_path / "local_config.json"
    target.write_text(
        json.dumps({
            "TARGET_WXID": "old",
            "DEEPSEEK_BASE_URL": "https://proxy.example.com",
            "DEEPSEEK_API_KEY": "sk-legacy",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(cs, "OVERRIDE_PATH", str(target))

    values = cs._effective_config()
    values["TARGET_WXID"] = "new"
    cs._write_overrides(values)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["TARGET_WXID"] == "new"
    # 用户手工添加的扩展字段保留，历史密钥必须剔除
    assert data["DEEPSEEK_BASE_URL"] == "https://proxy.example.com"
    assert "DEEPSEEK_API_KEY" not in data


def test_write_overrides_is_atomic(tmp_path, monkeypatch):
    target = tmp_path / "local_config.json"
    monkeypatch.setattr(cs, "OVERRIDE_PATH", str(target))
    values = cs._effective_config()
    cs._write_overrides(values)

    assert target.exists()
    assert not (tmp_path / "local_config.json.tmp").exists()
    json.loads(target.read_text(encoding="utf-8"))  # 必须是合法 JSON
