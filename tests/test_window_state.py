# -*- coding: utf-8 -*-
"""窗口状态判定测试（假 user32，不触碰真实微信）"""
import types

import pytest


class FakeUser32:
    def __init__(self, is_window=1, iconic=0, visible=1):
        self._is_window = is_window
        self._iconic = iconic
        self._visible = visible
        self._foreground = 0
        self.shown = 0
        self.repositioned = 0
        self.foreground_calls = 0

    def IsWindow(self, hwnd):
        return self._is_window

    def IsIconic(self, hwnd):
        return self._iconic

    def IsWindowVisible(self, hwnd):
        return self._visible

    def ShowWindow(self, hwnd, cmd):
        self.shown += 1

    def SetWindowPos(self, *args, **kwargs):
        self.repositioned += 1

    def GetForegroundWindow(self):
        return self._foreground

    def GetWindowThreadProcessId(self, hwnd, out=None):
        return 1

    def AttachThreadInput(self, a, b, attach):
        return 1

    def BringWindowToTop(self, hwnd):
        return 1

    def SetForegroundWindow(self, hwnd):
        self._foreground = hwnd
        self.foreground_calls += 1


@pytest.fixture
def runner():
    from wechat_companion.companion import CompanionRunner
    return CompanionRunner()


def test_gone_when_handle_destroyed(runner, monkeypatch):
    from wechat_companion import wx_window as winm
    monkeypatch.setattr(winm, "user32", FakeUser32(is_window=0))
    assert runner._window_state() == "gone"


def test_idle_when_minimized_and_not_resurrected(runner, monkeypatch):
    from wechat_companion import wx_window as winm
    fake = FakeUser32(is_window=1, iconic=1)
    monkeypatch.setattr(winm, "user32", fake)
    assert runner._window_state() == "idle"
    assert fake.shown == 0


def test_hidden_non_iconic_window_is_shown(runner, monkeypatch):
    from wechat_companion import wx_window as winm
    fake = FakeUser32(is_window=1, iconic=0, visible=0)
    monkeypatch.setattr(winm, "user32", fake)
    monkeypatch.setattr(winm, "kernel32",
                        types.SimpleNamespace(GetCurrentThreadId=lambda: 1))
    assert runner._window_state() == "idle"
    # 至少执行一次还原显示，并尝试前置激活
    assert fake.shown >= 1
    assert fake.foreground_calls >= 1


def test_ok_when_visible_and_position_correct(runner, monkeypatch):
    from wechat_companion import wx_window as winm
    fake = FakeUser32(is_window=1, iconic=0, visible=1)
    monkeypatch.setattr(winm, "user32", fake)
    monkeypatch.setattr(winm, "get_rect", lambda hwnd: (0, 0, 1180, 900))
    assert runner._window_state() == "ok"
    assert fake.repositioned == 0


def test_position_corrected_when_drifted(runner, monkeypatch):
    from wechat_companion import wx_window as winm
    fake = FakeUser32(is_window=1, iconic=0, visible=1)
    monkeypatch.setattr(winm, "user32", fake)
    monkeypatch.setattr(winm, "get_rect", lambda hwnd: (400, 300, 1580, 1200))
    assert runner._window_state() == "ok"
    assert fake.repositioned == 1


def test_find_main_window_recovers_from_tray(monkeypatch):
    from ctypes import wintypes

    from wechat_companion import wx_window as winm
    rc = wintypes.RECT(0, 0, 620, 451)
    state = {"round": 0}

    def fake_enum(include_hidden=False):
        if include_hidden:
            return [(123, "微信", rc)]
        state["round"] += 1
        return [] if state["round"] == 1 else [(123, "微信", rc)]

    monkeypatch.setattr(winm, "enum_wx_windows", fake_enum)
    monkeypatch.setattr(winm, "show_and_activate", lambda hwnd: True)
    assert winm.find_main_window() == 123


def test_find_main_window_raises_when_no_window(monkeypatch):
    from wechat_companion import wx_window as winm
    from wechat_companion.exceptions import WindowNotFoundError
    monkeypatch.setattr(winm, "enum_wx_windows",
                        lambda include_hidden=False: [])
    with pytest.raises(WindowNotFoundError):
        winm.find_main_window()
