# -*- coding: utf-8 -*-
"""独立聊天窗口标定稳健性测试（不触碰真实微信）"""
import numpy as np

from wechat_companion import wx_window as winm

BG = (250, 250, 250, 255)          # 独立窗口背景 RGB 250
GREEN = (159, 242, 157, 255)       # 自己绿色气泡 RGB 157,242,159（BGRA）
DARK = (80, 80, 80, 255)           # 气泡内深色文字
TOOL = (60, 60, 60, 255)           # 工具栏深色图标


def _indep_with_text_bubble():
    img = np.zeros((900, 1180, 4), dtype=np.uint8)
    img[:, :] = BG
    # 干扰项：消息区中下部的绿色气泡，内含深色文字（旧 argmin 会被吸引到这里）
    img[636:696, 300:900] = GREEN
    img[648:656, 320:700] = DARK
    # 工具栏图标：底部左侧深色像素聚集（新算法的锚点）
    img[845:861, 40:120] = TOOL
    return img


def test_input_top_not_fooled_by_bubble_text():
    """有深色文字气泡干扰时，input_top 仍应定位在真实上沿 ~717，而非气泡处 ~650。"""
    img = _indep_with_text_bubble()
    layout = winm.calibrate_independent(img)
    assert 710 <= layout.input_top <= 725
    assert 845 <= layout.toolbar_y <= 860


def test_calibration_fallback_ratio():
    """检测不到工具栏时，按实测比例兜底，input_top 仍落在合理区间。"""
    img = np.zeros((900, 1180, 4), dtype=np.uint8)
    img[:, :] = BG
    layout = winm.calibrate_independent(img)
    assert 700 <= layout.input_top <= 730
    assert 840 <= layout.toolbar_y <= 865
