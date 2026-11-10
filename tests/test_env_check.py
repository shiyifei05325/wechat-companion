# -*- coding: utf-8 -*-
"""环境检测与按需安装模块测试"""
import types

import env_check as ec


def test_check_os_is_windows():
    assert ec.check_os() is True


def test_check_python_version():
    assert ec.check_python() is True
    assert ec.python_version_text()


def test_version_comparison():
    assert ec._version_lt("1.0", "2.0") is True
    assert ec._version_lt("2.31.0", "2.31") is False
    assert ec._version_lt("3.0.1", "3.0.0") is False
    assert ec._version_lt("10.0", "9.0") is False
    assert ec._version_lt("0.9.53", "0.9.54") is True


def test_missing_packages_returns_list():
    missing = ec.missing_packages()
    assert isinstance(missing, list)
    # 当前测试环境依赖已安装，应无缺失
    assert missing == []


def test_detect_wechat_returns_list():
    pids = ec.detect_wechat()
    assert isinstance(pids, list)


def test_install_empty_specs_is_noop():
    assert ec.install_packages([]) is True


def test_install_packages_invokes_pip(monkeypatch):
    calls = []

    class _Result:
        returncode = 0

    def _fake_run(cmd, *a, **k):
        calls.append(cmd)
        return _Result()

    monkeypatch.setattr(ec.subprocess, "run", _fake_run)
    ok = ec.install_packages(["flask>=3.0"])
    assert ok is True
    assert len(calls) >= 2  # 先确认 pip，再执行安装
    install_call = calls[-1]
    assert "install" in install_call
    assert "flask>=3.0" in install_call


def test_install_failure_returns_false(monkeypatch):
    class _Result:
        returncode = 1

    monkeypatch.setattr(ec.subprocess, "run", lambda *a, **k: _Result())
    assert ec.install_packages(["nope>=1.0"]) is False


def test_ensure_pip_falls_back_to_ensurepip(monkeypatch):
    def _fake_run(cmd, *a, **k):
        if "ensurepip" in cmd:
            return types.SimpleNamespace(returncode=0)
        raise OSError("no pip")

    monkeypatch.setattr(ec.subprocess, "run", _fake_run)
    assert ec.ensure_pip() is True


def test_missing_detection_for_absent_module(monkeypatch):
    monkeypatch.setattr(ec, "_module_available", lambda name: name != "flask")
    missing = ec.missing_packages()
    assert "flask>=3.0" in missing
