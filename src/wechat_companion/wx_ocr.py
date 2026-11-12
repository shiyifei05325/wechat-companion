# -*- coding: utf-8 -*-
"""
OCR 文字识别兜底（Windows 内置 OCR，经 winocr 调用）。

右键复制读消息失败（菜单未弹出、剪贴板被占用、非标准控件等）时，
直接对气泡区域做 OCR，得到消息文本，提升消息读取成功率。

特点：
- 使用 Windows 自带识别引擎，无需下载 PyTorch/大模型，体积小；
- 全程同步封装、异常自吞，任何失败都返回空串，绝不打断主流程；
- 清理 Windows OCR 在中文之间插入的空格。
"""
import re

from .logging_setup import get_logger

logger = get_logger(__name__)

_DEFAULT_LANG = "zh-Hans-CN"
_CJK = r"\u3400-\u9fff"
_CJK_PUNCT = r"，。！？、：；…—“”‘’（）《》「」『』"

try:
    from winocr import recognize_pil_sync
    _WINOCR_OK = True
except Exception:  # pragma: no cover - 依赖缺失时的降级
    recognize_pil_sync = None
    _WINOCR_OK = False


def is_available():
    """OCR 依赖是否可用。"""
    return _WINOCR_OK


def _clean_spaces(text):
    """
    清理 Windows OCR 在中文里插入的空格，同时保留英文单词之间的空格。
    """
    if not text:
        return ""
    prev = None
    # 两个中文字符之间的空格，反复处理直到稳定
    while prev != text:
        prev = text
        text = re.sub(rf"([{_CJK}])\s+([{_CJK}])", r"\1\2", text)
    # 中文与中文标点之间的空格
    text = re.sub(rf"([{_CJK}])\s+([{_CJK_PUNCT}])", r"\1\2", text)
    text = re.sub(rf"([{_CJK_PUNCT}])\s+([{_CJK}])", r"\1\2", text)
    # 连续空格收敛为一个
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _to_pil(img, band):
    """把 BGR(A) numpy 画面（可按气泡 band 裁剪）转成 RGB PIL 图像。"""
    from PIL import Image
    h, w = img.shape[:2]
    if band and len(band) == 4:
        x0, y0, x1, y1 = band
        x0 = max(0, min(int(x0), w - 1))
        y0 = max(0, min(int(y0), h - 1))
        x1 = max(x0 + 1, min(int(x1), w))
        y1 = max(y0 + 1, min(int(y1), h))
        crop = img[y0:y1, x0:x1]
    else:
        crop = img
    bgr = crop[:, :, :3]
    rgb = bgr[:, :, ::-1]
    return Image.fromarray(rgb)


def recognize_bubble(img, band=None, lang=_DEFAULT_LANG):
    """
    识别气泡区域文字。
    :param img: BGR/BGRA numpy 画面
    :param band: 气泡边界 (x0,y0,x1,y1)，为 None 时识别整幅画面
    :param lang: OCR 语言标签
    :return: 识别文本；失败或无结果返回空串
    """
    if not _WINOCR_OK or img is None:
        return ""
    try:
        pil = _to_pil(img, band)
        result = recognize_pil_sync(pil, lang or _DEFAULT_LANG)
        raw = result.get("text", "") if isinstance(result, dict) else getattr(result, "text", "")
        text = _clean_spaces(raw)
        if text:
            logger.debug("OCR 识别结果：%s", text)
        return text
    except Exception as e:
        logger.warning("OCR 识别失败，已降级：%s", e)
        return ""
