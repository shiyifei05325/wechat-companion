# -*- coding: utf-8 -*-
"""
键鼠动作（pyautogui）：
- 打开指定微信号的聊天（点搜索图标 -> 粘贴 -> 点结果）
- 点击气泡并 Ctrl+C 读取文本
- 在输入框粘贴文本并回车发送（带剪贴板校验与发送结果校验）
"""
import time
from typing import Tuple

import pyautogui
import pyperclip

from . import wx_detect as detect
from . import wx_ocr
from . import wx_window as winm
from .logging_setup import get_logger

logger = get_logger(__name__)

pyautogui.FAILSAFE = True   # 鼠标甩到左上角可紧急中止
pyautogui.PAUSE = 0.04      # 每个动作后的基础停顿，尽量小以减少累积延迟


def _to_screen(origin: Tuple[int, int], point: Tuple[int, int]) -> Tuple[int, int]:
    left, top = origin
    return left + point[0], top + point[1]


def _move_to(x: int, y: int) -> None:
    """先用系统 API 把鼠标移到目标点，再让 pyautogui 接管。

    pyautogui 每次动作前会检查鼠标是否在屏幕角落（fail-safe），若上一步
    残留位置恰好在角落会误抛 FailSafeException；这里先直接定位到目标点，
    既保留“甩到角落紧急中止”，又避免正常流程被误触发。
    """
    winm.user32.SetCursorPos(int(x), int(y))


def _click_screen(x: int, y: int, button: str = "left",
                  clicks: int = 1) -> None:
    _move_to(x, y)
    pyautogui.click(x, y, button=button, clicks=clicks)


def _click(origin: Tuple[int, int], point: Tuple[int, int],
           dry: bool = False, clicks: int = 1) -> None:
    x, y = _to_screen(origin, point)
    if dry:
        logger.info("[演练] 点击 (%s,%s)", x, y)
        return
    _click_screen(x, y, clicks=clicks)


def set_clipboard_verified(text: str, tries: int = 6) -> bool:
    """
    把文本写入剪贴板并回读校验（剪贴板可能被云剪贴板/其他程序短暂锁定）。
    """
    for i in range(tries):
        try:
            pyperclip.copy(text)
            time.sleep(0.12 + 0.05 * i)
            if pyperclip.paste() == text:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def open_chat_by_wxid(hwnd: int, wxid: str, dry: bool = False):
    """
    通过搜索打开指定微信号的聊天窗口（在主窗口内）。
    成功后返回新标定的 Layout；失败返回 None。
    """
    if not winm.force_foreground(hwnd):
        logger.warning("无法把微信置前")
        return None

    img, origin = winm.grab(hwnd)
    layout = winm.calibrate(img)

    # 1) 点击放大镜
    _click(origin, layout.search_icon, dry)
    time.sleep(0.8)

    # 2) 粘贴微信号（绕过中文输入法）
    if not dry:
        if not set_clipboard_verified(wxid):
            logger.warning("剪贴板不可用，搜索取消")
            return None
        pyautogui.hotkey("ctrl", "v")
        time.sleep(1.8)
    else:
        logger.info("[演练] 粘贴搜索微信号 %s", wxid)

    # 3) 点击联系人第一行
    img, origin = winm.grab(hwnd)
    _click(origin, layout.search_result_row, dry)
    time.sleep(1.2)

    # 4) 点击消息区空白处，确保搜索下拉框关闭
    img, origin = winm.grab(hwnd)
    _click(origin, (700, 500), dry)
    time.sleep(0.6)

    # 5) 验证输入面板是否出现
    img, origin = winm.grab(hwnd)
    new_layout = winm.calibrate(img)
    if _input_panel_exists(img, new_layout):
        return new_layout

    # 备用：重新搜索并点击第二行位置（联系人行高约 66）
    if not dry:
        logger.info("第一行点击未打开聊天，尝试备用位置...")
        _click_screen(*_to_screen(origin, layout.search_icon))
        time.sleep(0.8)
        set_clipboard_verified(wxid)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(1.6)
        _click_screen(*_to_screen(origin, (layout.search_result_row[0], 258)))
        time.sleep(1.2)
        _click_screen(*_to_screen(origin, (700, 500)))
        time.sleep(0.6)
        img, origin = winm.grab(hwnd)
        new_layout = winm.calibrate(img)
        if _input_panel_exists(img, new_layout):
            return new_layout
    return None


# 搜索结果下拉框中“联系人第一行”的中心 y（窗口固定 1180x900 实测值）
_RESULT_ROW_Y = 167
# 独立窗口标题 OCR 区域
_TITLE_BAND = (0, 40, 300, 100)


def open_chat_in_new_window(main_hwnd, wxid, target_name, dry=False):
    """
    自动打开独立聊天窗口的完整流程：
      主窗口搜索微信号 -> 单击结果打开聊天 -> 双击高亮行弹出独立窗口
      -> 前置并用 OCR 识别标题，确认进入正确窗口。
    返回 (chat_hwnd, chat_layout)；任一步失败返回 (None, None)。
    """
    if not winm.force_foreground(main_hwnd):
        logger.warning("无法把微信置前")
        return None, None

    img, origin = winm.grab(main_hwnd)
    layout = winm.calibrate(img)

    # 1) 点击搜索图标
    _click(origin, layout.search_icon, dry)
    time.sleep(0.9)

    # 2) 粘贴微信号（绕过中文输入法）
    if dry:
        logger.info("[演练] 搜索微信号 %s", wxid)
    else:
        if not set_clipboard_verified(wxid):
            logger.warning("剪贴板不可用，搜索取消")
            return None, None
        pyautogui.hotkey("ctrl", "v")
        time.sleep(2.0)

    # 3) 单击联系人第一行，在主窗口打开聊天
    result_point = (layout.search_result_row[0], _RESULT_ROW_Y)
    if dry:
        logger.info("[演练] 单击搜索结果 %s", result_point)
    else:
        _click_screen(*_to_screen(origin, result_point))
        time.sleep(1.6)

    # 4) 定位绿色高亮行，先单击再双击，弹出独立窗口
    img2, _ = winm.grab(main_hwnd)
    selected = detect.find_selected_row(img2, layout)
    if selected is None:
        logger.warning("未找到选中的联系人行，无法打开独立窗口")
        return None, None
    if dry:
        logger.info("[演练] 双击高亮行 %s 打开独立窗口", selected)
        return None, None

    _click_screen(*_to_screen(origin, selected))
    time.sleep(0.4)
    _click_screen(*_to_screen(origin, selected), clicks=2)
    time.sleep(2.0)

    # 5) 找到独立窗口
    chat_hwnd = winm.find_chat_window(target_name)
    if chat_hwnd is None:
        logger.warning("独立聊天窗口未出现")
        return None, None

    # 6) 前置并 OCR 验证标题确实是目标联系人
    winm.force_foreground(chat_hwnd)
    time.sleep(0.6)
    cimg, _ = winm.grab(chat_hwnd)
    title = wx_ocr.recognize_bubble(cimg, band=_TITLE_BAND)
    if not title or target_name not in title:
        logger.warning("独立窗口标题 OCR 校验失败（识别为 %r，期望含 %s）",
                       title, target_name)
        return None, None
    chat_layout = winm.calibrate_independent(cimg)
    logger.info("已进入独立窗口并通过 OCR 校验：%s", title)
    return chat_hwnd, chat_layout


def _input_panel_exists(img, layout):
    """工具栏表情图标位置是否有深色像素（判断聊天是否已打开）"""
    x, y = layout.toolbar_check
    patch = img[max(0, y - 12):y + 12, max(0, x - 12):x + 12, :3].mean(axis=2)
    return float((patch < 180).mean()) > 0.02


def read_message_at(hwnd: int, point: Tuple[int, int], dry: bool = False,
                    independent: bool = False) -> str:
    """
    读取某条消息气泡的文本（微信4.0方式）：
    右键气泡 -> 上下文菜单首项“复制” -> 按 Down 选中、Enter 激活。
    返回文本（空字符串表示非文本消息或读取失败）。
    用“唯一哨兵写入剪贴板”保证读到的确实是本次复制内容。

    independent=True（独立聊天窗口）时全程不按 Esc：独立窗口里 Esc 会
    直接关闭窗口；改用点击空白处清理残留，复制后菜单会自动关闭。
    """
    if not winm.force_foreground(hwnd):
        return ""
    _img, origin = winm.grab(hwnd)

    old_clip = ""
    if not dry:
        try:
            old_clip = pyperclip.paste()
        except Exception:
            old_clip = ""

    if dry:
        logger.info("[演练] 在 %s 右键并复制", point)
        return ""

    # 清掉可能残留的菜单：独立窗口点空白（Esc 会关窗口），主窗口按 Esc
    if independent:
        _click_screen(*_to_screen(origin, (800, 250)))
    else:
        pyautogui.press("escape")
    time.sleep(0.15)

    sentinel = _write_sentinel()
    if sentinel is None:
        logger.warning("剪贴板不可用，读取取消")
        try:
            pyperclip.copy(old_clip)
        except Exception:
            pass
        return ""

    txt = ""
    try:
        # 右键气泡（必须落在气泡上）
        x, y = _to_screen(origin, point)
        _click_screen(x, y, button="right")
        time.sleep(0.6)

        # 菜单首项即“复制”：Down 选中、Enter 激活
        pyautogui.press("down")
        time.sleep(0.15)
        pyautogui.press("enter")
        time.sleep(0.4)

        try:
            now = pyperclip.paste() or ""
        except Exception:
            now = ""
        txt = "" if (not now or now == sentinel) else now

        # 复制后菜单自动关闭；主窗口仍按 Esc 兜底，独立窗口不按
        if not independent:
            pyautogui.press("escape")
            time.sleep(0.12)
            pyautogui.press("escape")
        if not txt:
            # 非文本消息：恢复窗口显示并前置
            time.sleep(0.12)
            winm.show_and_activate(hwnd)
    finally:
        # 兜底关闭残留菜单：主窗口按 Esc；独立窗口点空白（Esc 会关掉窗口）
        if independent:
            try:
                _click_screen(*_to_screen(origin, (800, 250)))
            except Exception:
                pass
        else:
            try:
                pyautogui.press("escape")
            except Exception:
                pass
        # 无论成功、失败还是中途异常，都还原用户剪贴板，不留下哨兵/消息文本
        try:
            pyperclip.copy(old_clip)
        except Exception:
            pass

    logger.debug("读取消息 @ %s，结果 %r", point, txt)
    return txt.strip()


def _write_sentinel():
    """写入唯一哨兵并回读确认，返回哨兵字符串；失败返回 None"""
    import uuid
    sentinel = "@@SENTINEL_" + uuid.uuid4().hex + "@@"
    for _ in range(4):
        try:
            pyperclip.copy(sentinel)
            time.sleep(0.15)
            if pyperclip.paste() == sentinel:
                return sentinel
        except Exception:
            pass
        time.sleep(0.25)
    return None


def _input_text_content(layout, focus_point=None):
    """
    读取输入框当前文本：点击编辑器 -> Ctrl+A 全选 -> Ctrl+C。
    内部重试 3 轮；调用后文本仍在输入框中（全选状态）。
    """
    for _ in range(3):
        sentinel = _write_sentinel()
        if sentinel is None:
            time.sleep(0.3)
            continue
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.3)
        now = pyperclip.paste() or ""
        if now != sentinel:
            return now
        time.sleep(0.35)
    return None


def _clear_editor():
    """清空输入框全部内容"""
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.12)
    pyautogui.press("backspace")
    time.sleep(0.25)


def send_message(hwnd: int, layout, text: str, dry: bool = False) -> bool:
    """
    在当前聊天输入框粘贴文本并发送。
    流程：聚焦编辑器 -> 清空残留 -> 粘贴 -> 回读校验（内部重试）
          -> 重新粘贴为未选中状态 -> Enter / Ctrl+Enter / 发送按钮；
    任何失败都会清空编辑器，避免文本残留污染后续消息。
    """
    if not winm.force_foreground(hwnd):
        logger.warning("无法把微信置前，发送取消")
        return False

    _img, origin = winm.grab(hwnd)
    _click(origin, layout.input_click, dry)
    time.sleep(0.4)

    if dry:
        logger.info("[演练] 粘贴并发送：%s", text)
        return True

    # 1) 清空编辑器残留
    _clear_editor()

    # 2) 粘贴并回读校验（最多 3 轮；每轮失败都清空后重来，绝不追加）
    got = None
    for i in range(3):
        if not set_clipboard_verified(text):
            continue
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.35)
        got = _input_text_content(layout)
        if got == text:
            break
        _click(origin, layout.input_click)
        time.sleep(0.25)
        _clear_editor()

    if got != text:
        logger.warning("输入框未能可靠写入文本，发送取消")
        _clear_editor()
        return False

    # 3) 重新粘贴为“未选中”状态（Ctrl+A -> 粘贴覆盖），光标在末尾
    if not set_clipboard_verified(text):
        _clear_editor()
        return False
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.12)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)

    before_img, _ = winm.grab(hwnd)
    before_sig = detect.area_signature(before_img, layout.message_area)

    # 4) 依次尝试三种发送方式（事件轮询确认，成功即返回，避免重复发送）
    pyautogui.press("enter")
    if _wait_send_result(hwnd, layout, before_sig):
        return True

    pyautogui.hotkey("ctrl", "enter")
    if _wait_send_result(hwnd, layout, before_sig):
        return True

    logger.info("快捷键未触发发送，尝试点击发送按钮...")
    _click(origin, layout.send_button)
    if _wait_send_result(hwnd, layout, before_sig):
        return True

    _clear_editor()
    return False


def _wait_send_result(hwnd, layout, before_sig, timeout: float = 1.6) -> bool:
    """
    发送后轮询确认：每 0.2s 检查一次输入框是否清空，
    通常 0.2~0.4s 即可确认，比固定等待更快；超时仍未确认才返回 False。
    """
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if _send_succeeded(hwnd, layout, before_sig):
            return True
        time.sleep(0.2)
    return False


def _send_succeeded(hwnd, layout, before_sig):
    """
    发送结果判定：输入框已清空即视为发送成功（防止因签名延迟误判而重复发送）。
    """
    if not winm.user32.IsWindow(hwnd):
        return False
    img, _ = winm.grab(hwnd)
    ix, iy = layout.input_click
    patch = img[iy - 14:iy + 14, ix - 60:ix + 60, :3].mean(axis=2)
    return float((patch < 200).mean()) < 0.01
