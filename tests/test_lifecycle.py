# -*- coding: utf-8 -*-
"""单实例锁 / 停止标记 / 父进程监护测试（用假 psutil，不启动真实伴侣）"""
import types

import pytest


@pytest.fixture
def runtime_paths(tmp_path, monkeypatch):
    from wechat_companion import companion as comp
    monkeypatch.setattr(comp, "LOCK_PATH", str(tmp_path / "companion.lock"))
    monkeypatch.setattr(comp, "STOP_PATH", str(tmp_path / "companion.stop"))
    return comp


@pytest.fixture
def fake_psutil(monkeypatch):
    """注入假 psutil：只有 live 集合中的 pid 算存活，cmdline 一律含 run.py"""
    mod = types.ModuleType("psutil")
    state = {"live": set()}
    mod.pid_exists = lambda pid: pid in state["live"]

    class _FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def cmdline(self):
            return ["python.exe", "-u", "run.py"]

    mod.Process = _FakeProcess
    monkeypatch.setitem(__import__("sys").modules, "psutil", mod)
    return state


def test_lock_acquire_and_release(runtime_paths):
    comp = runtime_paths
    comp._release_lock()
    assert comp._acquire_lock() is True
    with open(comp.LOCK_PATH, encoding="utf-8") as f:
        assert f.read().strip()
    comp._release_lock()
    import os
    assert not os.path.exists(comp.LOCK_PATH)


def test_lock_refuses_when_instance_live(runtime_paths, fake_psutil):
    comp = runtime_paths
    fake_psutil["live"].add(4242)
    with open(comp.LOCK_PATH, "w", encoding="utf-8") as f:
        f.write("4242")
    assert comp._lock_held_by_live_instance() is True
    assert comp._acquire_lock() is False


def test_stale_lock_with_dead_pid_is_overwritten(runtime_paths, fake_psutil):
    comp = runtime_paths
    with open(comp.LOCK_PATH, "w", encoding="utf-8") as f:
        f.write("9999")  # 不在 live 集合
    assert comp._lock_held_by_live_instance() is False
    assert comp._acquire_lock() is True


def test_stop_sentinel(runtime_paths):
    comp = runtime_paths
    assert comp._stop_file_requested() is False
    with open(comp.STOP_PATH, "w", encoding="utf-8") as f:
        f.write("1")
    assert comp._stop_file_requested() is True


def test_parent_alive_detection(runtime_paths, fake_psutil, monkeypatch):
    comp = runtime_paths
    monkeypatch.delenv("COMPANION_PARENT_PID", raising=False)
    assert comp._parent_alive() is True
    monkeypatch.setenv("COMPANION_PARENT_PID", "5151")
    assert comp._parent_alive() is False
    fake_psutil["live"].add(5151)
    assert comp._parent_alive() is True
