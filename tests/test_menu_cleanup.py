# -*- coding: utf-8 -*-
"""读图流程菜单清理测试（防止右键菜单堆叠卡死页面）"""
import types

import numpy as np

from wechat_companion import wx_actions as act
from wechat_companion import wx_window as winm


def _blank():
    img = np.zeros((900, 1180, 4), dtype=np.uint8)
    img[:, :] = (237, 237, 237, 255)
    return img


def test_read_message_always_dismisses_menus(monkeypatch):
    img = _blank()
    monkeypatch.setattr(winm, "force_foreground", lambda hwnd: True)
    monkeypatch.setattr(winm, "grab", lambda hwnd: (img, (0, 0)))

    pressed = []
    monkeypatch.setattr(act.pyautogui, "rightClick", lambda *a, **k: None)
    monkeypatch.setattr(act.pyautogui, "press", lambda key: pressed.append(key))

    # 剪贴板模拟：copy 记录，paste 回传（哨兵写入后 paste 仍是哨兵 → 非文本）
    state = {"clip": ""}
    monkeypatch.setattr(act.pyperclip, "copy",
                        lambda s: state.__setitem__("clip", s))
    monkeypatch.setattr(act.pyperclip, "paste", lambda: state["clip"])

    out = act.read_message_at(1, (400, 530), dry=False)
    assert out == ""
    # 右键前 1 次 + 读取后 2 次，共至少 3 次 Esc，确保无菜单残留
    assert pressed.count("escape") >= 3


def test_read_message_dry_run(monkeypatch):
    img = _blank()
    monkeypatch.setattr(winm, "force_foreground", lambda hwnd: True)
    monkeypatch.setattr(winm, "grab", lambda hwnd: (img, (0, 0)))
    assert act.read_message_at(1, (400, 530), dry=True) == ""
