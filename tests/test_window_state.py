# -*- coding: utf-8 -*-
"""窗口状态判定测试（假 user32，不触碰真实微信）"""
import pytest


class FakeUser32:
    def __init__(self, is_window=1, iconic=0, visible=1):
        self._is_window = is_window
        self._iconic = iconic
        self._visible = visible
        self.shown = 0
        self.repositioned = 0

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
    assert runner._window_state() == "idle"
    assert fake.shown == 1


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
