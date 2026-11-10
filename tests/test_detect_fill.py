# -*- coding: utf-8 -*-
"""气泡填充识别（收发判定）与自我对话防护测试"""
import types

import numpy as np

from wechat_companion import companion as comp_mod
from wechat_companion import wx_detect as detect

# 合成画面常量（BGRA）
BG = (237, 237, 237, 255)        # 经典聊天背景灰（RGB 237）
GREEN = (105, 236, 149, 255)     # 自己绿色气泡（RGB 149,236,105）
WHITE = (255, 255, 255, 255)     # 对方白色气泡（经典配色）
# 新版配色（微信 4.x 新主题）：白底、对方灰气泡、自己浅绿气泡
BG_NEW = (250, 250, 250, 255)                       # RGB 250
GRAY_BUBBLE_NEW = (240, 238, 238, 255)               # RGB 238,238,240
GREEN_NEW = (159, 242, 157, 255)                     # RGB 157,242,159

LAYOUT = types.SimpleNamespace(
    w=1180, h=900, nav_w=79, list_r=285, input_top=782,
    message_area=(292, 60, 1120, 762),
)


def _blank():
    img = np.zeros((900, 1180, 4), dtype=np.uint8)
    img[:, :] = BG
    return img


def _rect(img, x0, y0, x1, y1, color):
    img[y0:y1, x0:x1] = color


def test_self_green_bubble_right():
    img = _blank()
    _rect(img, 800, 500, 1050, 560, GREEN)
    r = detect.find_bottom_bubble(img, LAYOUT)
    assert r["side"] == "self"
    px, py = r["point"]
    assert 800 <= px <= 1050 and 500 <= py <= 560


def test_other_white_bubble_left():
    img = _blank()
    _rect(img, 320, 500, 560, 560, WHITE)
    r = detect.find_bottom_bubble(img, LAYOUT)
    assert r["side"] == "other"
    px, py = r["point"]
    assert 320 <= px <= 560 and 500 <= py <= 560


def test_lowest_bubble_wins_and_is_self():
    img = _blank()
    _rect(img, 320, 380, 560, 430, WHITE)
    _rect(img, 800, 600, 1050, 660, GREEN)
    r = detect.find_bottom_bubble(img, LAYOUT)
    assert r["side"] == "self"
    assert r["point"][1] >= 600


def test_no_bubble_returns_none():
    r = detect.find_bottom_bubble(_blank(), LAYOUT)
    assert r["side"] is None
    assert r["point"] is None


def test_fill_detection_without_avatars():
    """即使头像完全不存在（纯色头像漏检），气泡填充仍能判定收发"""
    img = _blank()
    _rect(img, 800, 500, 1050, 560, GREEN)
    r = detect.find_bottom_bubble(img, LAYOUT)  # 不依赖任何头像
    assert r["side"] == "self"


def test_recent_self_guards_against_misclassification(monkeypatch):
    """识别误判为对方、但文本是自己最近发的：必须忽略，不触发回复"""
    img = _blank()
    _rect(img, 320, 500, 560, 560, WHITE)  # 画面上看似对方白气泡
    monkeypatch.setattr(
        comp_mod.actions, "read_message_at",
        lambda hwnd, point, dry: "我刚发的回复",
    )
    responded = []
    monkeypatch.setattr(
        comp_mod.CompanionRunner, "_respond",
        lambda self, text: responded.append(text),
    )
    runner = comp_mod.CompanionRunner()
    runner.hwnd = 1
    runner.layout = LAYOUT
    runner.recent_self = ["我刚发的回复"]
    runner._handle_new(img)
    assert responded == []


def test_other_message_triggers_respond(monkeypatch):
    img = _blank()
    _rect(img, 320, 500, 560, 560, WHITE)
    monkeypatch.setattr(
        comp_mod.actions, "read_message_at",
        lambda hwnd, point, dry: "你好呀",
    )
    responded = []
    monkeypatch.setattr(
        comp_mod.CompanionRunner, "_respond",
        lambda self, text: responded.append(text),
    )
    runner = comp_mod.CompanionRunner()
    runner.hwnd = 1
    runner.layout = LAYOUT
    runner._handle_new(img)
    assert responded == ["你好呀"]


# -------- 新版配色（白底 + 灰气泡 + 浅绿气泡） --------
def _blank_new():
    img = np.zeros((900, 1180, 4), dtype=np.uint8)
    img[:, :] = BG_NEW
    return img


def test_new_theme_other_gray_bubble():
    img = _blank_new()
    _rect(img, 350, 500, 560, 560, GRAY_BUBBLE_NEW)
    r = detect.find_bottom_bubble(img, LAYOUT)
    assert r["side"] == "other"
    px, py = r["point"]
    assert 350 <= px <= 560 and 500 <= py <= 560


def test_new_theme_self_light_green_bubble():
    img = _blank_new()
    _rect(img, 800, 600, 1050, 660, GREEN_NEW)
    r = detect.find_bottom_bubble(img, LAYOUT)
    assert r["side"] == "self"
    px, py = r["point"]
    assert 800 <= px <= 1050 and 600 <= py <= 660


def test_new_theme_lowest_bubble_wins():
    img = _blank_new()
    _rect(img, 350, 380, 560, 430, GRAY_BUBBLE_NEW)
    _rect(img, 800, 600, 1050, 660, GREEN_NEW)
    r = detect.find_bottom_bubble(img, LAYOUT)
    assert r["side"] == "self"
    assert r["point"][1] >= 600


def test_other_point_not_pulled_by_right_avatar_noise():
    """右侧头像列杂色不得把对方气泡点击点拉偏"""
    img = _blank_new()
    _rect(img, 350, 500, 500, 560, GRAY_BUBBLE_NEW)
    # 右侧自己头像列放杂色块（模拟头像），与气泡同 y
    _rect(img, 1128, 500, 1166, 560, (40, 60, 200, 255))
    r = detect.find_bottom_bubble(img, LAYOUT)
    assert r["side"] == "other"
    px, py = r["point"]
    assert 350 <= px <= 510


def test_new_theme_other_gray_triggers_respond(monkeypatch):
    img = _blank_new()
    _rect(img, 350, 500, 560, 560, GRAY_BUBBLE_NEW)
    monkeypatch.setattr(
        comp_mod.actions, "read_message_at",
        lambda hwnd, point, dry: "你吃饭了吗",
    )
    responded = []
    monkeypatch.setattr(
        comp_mod.CompanionRunner, "_respond",
        lambda self, text: responded.append(text),
    )
    runner = comp_mod.CompanionRunner()
    runner.hwnd = 1
    runner.layout = LAYOUT
    runner._handle_new(img)
    assert responded == ["你吃饭了吗"]
