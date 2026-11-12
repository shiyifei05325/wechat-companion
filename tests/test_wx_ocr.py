# -*- coding: utf-8 -*-
"""OCR 兜底模块测试：空格清理、识别成功/失败降级（winocr 全程 mock）"""
import numpy as np

from wechat_companion import wx_ocr


def test_clean_spaces_removes_cjk_gaps_keeps_english():
    out = wx_ocr._clean_spaces("你 好 呀 在 干 嘛 呢 hello world")
    assert out == "你好呀在干嘛呢 hello world"


def test_clean_spaces_handles_punctuation():
    assert wx_ocr._clean_spaces("你 好 ， 世 界 ！") == "你好，世界！"


def test_clean_spaces_empty_and_english_only():
    assert wx_ocr._clean_spaces("") == ""
    assert wx_ocr._clean_spaces("hello   world") == "hello world"


def test_recognize_bubble_success(monkeypatch):
    monkeypatch.setattr(wx_ocr, "_WINOCR_OK", True)
    monkeypatch.setattr(
        wx_ocr, "recognize_pil_sync",
        lambda pil, lang: {"text": "你 好 呀", "lines": []},
    )
    img = np.zeros((100, 120, 4), dtype=np.uint8)
    assert wx_ocr.recognize_bubble(img, band=(10, 10, 90, 80)) == "你好呀"


def test_recognize_bubble_none_image_and_disabled(monkeypatch):
    monkeypatch.setattr(wx_ocr, "_WINOCR_OK", True)
    assert wx_ocr.recognize_bubble(None) == ""
    monkeypatch.setattr(wx_ocr, "_WINOCR_OK", False)
    img = np.zeros((40, 40, 4), dtype=np.uint8)
    assert wx_ocr.recognize_bubble(img) == ""


def test_recognize_bubble_swallows_exception(monkeypatch):
    monkeypatch.setattr(wx_ocr, "_WINOCR_OK", True)

    def _boom(pil, lang):
        raise RuntimeError("ocr engine error")

    monkeypatch.setattr(wx_ocr, "recognize_pil_sync", _boom)
    img = np.zeros((40, 40, 4), dtype=np.uint8)
    assert wx_ocr.recognize_bubble(img) == ""


def test_to_pil_crops_band():
    img = np.zeros((100, 120, 4), dtype=np.uint8)
    pil = wx_ocr._to_pil(img, (10, 20, 90, 80))
    # 裁剪后宽=80、高=60
    assert pil.size == (80, 60)
