# -*- coding: utf-8 -*-
"""
微信窗口管理：查找主窗口、固定位置、强激活前台、屏幕捕捉、布局标定
"""
import ctypes
import time
from ctypes import wintypes
from typing import List, Tuple

import mss
import numpy as np

from .exceptions import ActionError, WindowNotFoundError
from .logging_setup import get_logger

logger = get_logger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 进程 DPI 感知，保证坐标与物理像素一致
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_RESTORE = 9
SWP_NOZORDER = 0x0004
WM_CLOSE = 0x0010

# 微信进程 PID 缓存（短时间内多次枚举窗口时避免反复全量遍历进程表）
_pids_cache_ts = 0.0
_pids_cache = set()
_PIDS_TTL = 5.0


def _wx_pids():
    """返回微信进程 PID 集合（兼容 4.0 Weixin.exe 与旧版 WeChat.exe）"""
    global _pids_cache_ts, _pids_cache
    now = time.monotonic()
    if now - _pids_cache_ts < _PIDS_TTL:
        return _pids_cache
    import psutil
    pids = set()
    for p in psutil.process_iter(["name"]):
        n = (p.info["name"] or "").lower()
        if n in ("weixin.exe", "wechat.exe"):
            pids.add(p.pid)
    _pids_cache_ts, _pids_cache = now, pids
    return pids


def enum_wx_windows(include_hidden: bool = False) -> List[Tuple[int, str, wintypes.RECT]]:
    """
    枚举微信 Qt 窗口，返回 [(hwnd, title, rect)]。
    默认只列可见窗口；include_hidden=True 时同时返回隐藏窗口（如托盘态主窗口）。
    托盘图标消息窗口（WxTrayIconMessageWindowClass）始终排除。
    """
    pids = _wx_pids()
    out = []

    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lparam):
        if not include_hidden and not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if not cls.value.startswith("Qt") or "TrayIcon" in cls.value:
            return True
        rc = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        out.append((hwnd, title.value, rc))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out


def find_main_window() -> int:
    """
    找到微信主窗口。
    主窗口 = 可见 Qt 窗口中面积最大的那个（聊天独立小窗口面积更小）。
    没有可见窗口时，微信可能只是关闭到托盘：枚举隐藏窗口并激活恢复。
    返回 hwnd；找不到时抛 WindowNotFoundError。
    """
    wins = enum_wx_windows()
    if not wins:
        hidden = enum_wx_windows(include_hidden=True)
        if hidden:
            hidden.sort(key=lambda item: _rect_area(item[2]), reverse=True)
            hwnd = hidden[0][0]
            if show_and_activate(hwnd):
                logger.info("微信主窗口在托盘中，已恢复并前置，窗口句柄=%s", hwnd)
                wins = enum_wx_windows()
            else:
                raise WindowNotFoundError(
                    "微信正在后台运行，但无法自动恢复窗口，请点击系统托盘图标打开。"
                )
        if not wins:
            raise WindowNotFoundError("没有找到微信窗口，请先登录并打开 PC 微信。")

    wins.sort(key=lambda item: _rect_area(item[2]), reverse=True)
    hwnd = wins[0][0]
    logger.debug("主窗口句柄=%s，候选窗口 %d 个", hwnd, len(wins))
    return hwnd


def find_chat_window(target_name: str):
    """
    按联系人昵称找到“独立聊天窗口”（双击聊天后单独弹出的窗口）。
    独立窗口的标题就是联系人显示名称；找不到时返回 None。
    """
    if not target_name:
        return None
    for hwnd, title, _rc in enum_wx_windows():
        if title == target_name:
            return hwnd
    return None


def _rect_area(rc):
    return max(0, rc.right - rc.left) * max(0, rc.bottom - rc.top)


def get_rect(hwnd: int) -> Tuple[int, int, int, int]:
    rc = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    return rc.left, rc.top, rc.right, rc.bottom


def show_and_activate(hwnd: int, retries: int = 4) -> bool:
    """
    显示并激活窗口，尽量减少对输入队列的干扰（防止微信界面卡顿/无响应）：
    - 窗口已在前台时直接返回，不做任何操作，避免反复挂接输入队列；
    - 先用轻量方式前置（不挂接其他线程），失败再用 AttachThreadInput 兜底；
    - 所有线程挂接都在 finally 中保证解除，避免输入队列残留导致窗口卡死。
    返回窗口是否最终处于前台。
    """
    for _ in range(retries):
        # 已在前台：零干预直接返回（最常见路径，不 Attach、不 ShowWindow）
        try:
            if user32.GetForegroundWindow() == hwnd:
                return True
        except Exception:
            pass

        # 仅在最小化时还原，正常窗口只做 SHOW，避免对正常窗口反复 SW_RESTORE
        try:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            else:
                user32.ShowWindow(hwnd, SW_SHOW)
        except Exception:
            pass

        # 先尝试轻量前置（不挂接输入队列，绝大多数情况下足够）
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.2)
        try:
            if user32.GetForegroundWindow() == hwnd:
                return True
        except Exception:
            pass

        # 轻量方式被前台锁挡住：才用 AttachThreadInput 兜底一次
        attached = []
        try:
            fg = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(fg, None)
            cur_tid = kernel32.GetCurrentThreadId()
            tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)
            if fg_tid and user32.AttachThreadInput(fg_tid, cur_tid, True):
                attached.append((fg_tid, cur_tid))
            if user32.AttachThreadInput(cur_tid, tgt_tid, True):
                attached.append((cur_tid, tgt_tid))
            user32.BringWindowToTop(hwnd)
            user32.ShowWindow(hwnd, SW_SHOW)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        finally:
            for a, b in reversed(attached):
                try:
                    user32.AttachThreadInput(a, b, False)
                except Exception:
                    pass
        time.sleep(0.3)
        try:
            if user32.GetForegroundWindow() == hwnd:
                return True
        except Exception:
            pass
    return False


def force_foreground(hwnd: int, retries: int = 4) -> bool:
    """
    可靠地把窗口提到前台（保留旧调用名，内部走 show_and_activate，
    保证 AttachThreadInput 异常时也能解除挂接）。
    """
    return show_and_activate(hwnd, retries=retries)


def normalize_window(hwnd: int, left: int, top: int, width: int, height: int):
    """把窗口移动/缩放到指定位置尺寸"""
    user32.ShowWindow(hwnd, SW_RESTORE)
    time.sleep(0.15)
    user32.SetWindowPos(hwnd, 0, left, top, width, height, SWP_NOZORDER)
    time.sleep(0.25)
    user32.SetWindowPos(hwnd, 0, left, top, width, height, SWP_NOZORDER)
    return get_rect(hwnd)


_sct = None


def _get_mss():
    """复用一个 mss 实例（避免每帧都重新构造，减少轮询开销）"""
    global _sct
    if _sct is None:
        _sct = mss.MSS()
    return _sct


def grab(hwnd: int) -> Tuple[np.ndarray, Tuple[int, int]]:
    """
    截取窗口画面。
    返回 (img, (left,top))：img 为 BGRA numpy 数组（shape: H,W,4）
    窗口已关闭/最小化导致区域无效时抛 ActionError，由调用方决定退出或等待。
    """
    left, top, right, bottom = get_rect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise ActionError(f"窗口区域无效：{width}x{height}（窗口可能已关闭或最小化）")
    shot = _get_mss().grab({"left": left, "top": top, "width": width, "height": height})
    img = np.array(shot)
    return img, (left, top)


def grab_region(hwnd: int, win_rect) -> np.ndarray:
    """
    只截取窗口内的一个子区域（窗口相对坐标 win_rect=(x0,y0,x1,y1)），
    用于空闲轮询/签名比对，避免整窗拷贝。返回该区域的 BGRA 数组。
    """
    left, top, right, bottom = get_rect(hwnd)
    win_w = max(1, right - left)
    win_h = max(1, bottom - top)
    x0, y0, x1, y1 = win_rect
    x0 = max(0, int(x0))
    y0 = max(0, int(y0))
    # 下界保证至少 1 像素，上界钳到窗口真实宽高，避免窗口缩放/标定偏差时
    # mss 抓到窗口外像素而引发签名误判
    x1 = min(win_w, max(x0 + 1, int(x1)))
    y1 = min(win_h, max(y0 + 1, int(y1)))
    shot = _get_mss().grab({
        "left": left + x0, "top": top + y0,
        "width": x1 - x0, "height": y1 - y0,
    })
    return np.array(shot)


# --------------------------------------------------------------------------
# 布局标定：通过像素扫描确定各面板边界，分辨率/尺寸变化也能自适应
# --------------------------------------------------------------------------
AVATAR_EDGE = 38       # 头像边长（像素）


class Layout:
    """
    微信窗口布局坐标（均为窗口内相对坐标）。
    independent=True 表示独立聊天窗口（无左侧导航栏/联系人列表）。
    """

    def __init__(self, width, height, nav_w, list_r, input_top,
                 toolbar_y=None, independent: bool = False):
        self.w = width
        self.h = height
        self.nav_w = nav_w          # 左侧导航栏右边界（独立窗口为 0）
        self.list_r = list_r        # 聊天列表面板右边界（独立窗口为 0）
        self.input_top = input_top  # 输入面板顶部 y
        self.independent = independent
        # 工具栏图标行中心 y（未提供时按面板顶部推算）
        self.toolbar_y = toolbar_y if toolbar_y is not None else input_top + 68

    # 头像列（独立窗口与主窗口位置不同）-----------------------------------
    @property
    def other_avatar(self):
        """对方头像列 (x0,x1)"""
        if self.independent:
            return 34, 72
        x0 = self.list_r + 14
        return x0, x0 + AVATAR_EDGE

    @property
    def self_avatar(self):
        """自己头像列 (x0,x1)"""
        x1 = self.w - 30 if self.independent else self.w - 14
        return x1 - AVATAR_EDGE, x1

    @property
    def content_left(self):
        """对方内容区左边界参考（独立窗口为 0，主窗口为列表右边界）"""
        return 0 if self.independent else self.list_r

    # 常用点位 -------------------------------------------------------------
    @property
    def search_icon(self):
        # 聊天列表头部的放大镜（仅主窗口使用）
        x = int(self.nav_w + (self.list_r - self.nav_w) * 0.60)
        return x, 78

    @property
    def search_result_row(self):
        # 搜索下拉框中“联系人”第一行的点击位置（仅主窗口使用）
        x = self.nav_w + 230
        return x, 212

    @property
    def message_area(self):
        # 消息展示区域 (x0,y0,x1,y1)
        if self.independent:
            return 12, 100, self.w - 12, self.input_top - 8
        return self.list_r + 2, 108, self.w - 12, self.input_top - 8

    @property
    def input_click(self):
        # 编辑器文字行点击位置
        if self.independent:
            return self.w // 2, self.input_top + 45
        x = (self.list_r + self.w) // 2
        y = self.toolbar_y - 43
        return x, y

    @property
    def send_button(self):
        offset = 64 if self.independent else 62
        return self.w - offset, self.toolbar_y + 1

    @property
    def toolbar_check(self):
        # 输入框工具栏第一个表情图标的位置（判断输入面板是否存在）
        if self.independent:
            return 40, self.toolbar_y + 1
        return self.list_r + 38, self.toolbar_y + 1

    def __repr__(self):
        kind = "独立窗口" if self.independent else "主窗口"
        return (f"Layout({kind}, w={self.w}, h={self.h}, nav_w={self.nav_w}, "
                f"list_r={self.list_r}, input_top={self.input_top}, "
                f"toolbar_y={self.toolbar_y})")


def _detect_vertical_edges(gray):
    """
    通过列灰度剖面找两条面板分隔线。
    分隔线在整个纵向范围上都比右侧面板暗（局部图标只在少数行暗），
    用“逐行都偏暗的比例”作为边缘强度，避免误判头像/图标。
    """
    y0, y1 = 120, min(700, gray.shape[0])
    _h, w = gray.shape
    strength = np.zeros(w)
    for x in range(30, w - 20):
        col = gray[y0:y1, x]
        # 分隔线整列恒定；头像/图标列方差大，直接排除
        if col.std() > 3.5:
            continue
        # 两侧面板“基色”：取 90 分位，排除深色头像
        right = np.percentile(gray[y0:y1, x + 4:x + 18], 90)
        left = np.percentile(gray[y0:y1, max(0, x - 18):max(1, x - 4)], 90)
        strength[x] = max(left - col.mean(), right - col.mean())
    edges = []
    # 导航栏边界范围与聊天列表边界范围（按宽度比例门控）
    ranges = [(int(w * 0.03), int(w * 0.15), 3.0),
              (int(w * 0.16), int(w * 0.40), 6.0)]
    for a, b, cutoff in ranges:
        seg = strength[a:b]
        if seg.size and seg.max() > cutoff:
            edges.append(a + int(seg.argmax()))
    return edges


def _detect_input_top(img):
    """
    检测输入面板：
    在工具栏区域（约窗口 25% 处向右 280px 宽）内，自底向上找
    深色图标像素聚集的行（表情/附件等图标行），返回 (面板顶部 y, 工具栏行 y)。
    实测（1180x900）：工具栏行中心约 848，面板圆角顶部约 780。
    """
    h, w = img.shape[:2]
    gray = img[:, :, :3].mean(axis=2)
    x0 = int(w * 0.25)
    x1 = x0 + 280
    band = gray[:, x0:x1]
    dark = (band < 150).sum(axis=1)
    width = x1 - x0
    for y in range(h - 14, int(h * 0.80), -1):
        # 图标行：有一定数量深色像素；窗口阴影行几乎全暗，需排除
        if 8 < dark[y] < width * 0.5:
            # 自底向上先命中图标下沿，中心约在其上方 8px
            toolbar_y = y - 8
            return toolbar_y - 68, toolbar_y
    return int(h * 0.867), int(h * 0.942)


def calibrate(img):
    """
    根据窗口截图标定布局。
    img: BGRA 数组
    """
    h, w = img.shape[:2]
    gray = img[:, :, :3].mean(axis=2)

    edges = _detect_vertical_edges(gray)
    nav_f, list_f = int(w * 0.067), int(w * 0.242)
    if len(edges) >= 2:
        nav_w, list_r = edges[0], edges[1]
    elif len(edges) == 1:
        if edges[0] < w * 0.16:
            nav_w, list_r = edges[0], list_f
        else:
            nav_w, list_r = nav_f, edges[0]
    else:
        nav_w, list_r = nav_f, list_f

    input_top, toolbar_y = _detect_input_top(img)
    # 合理性约束
    if not (int(h * 0.80) < input_top < h - 60):
        input_top, toolbar_y = int(h * 0.867), int(h * 0.942)
    return Layout(w, h, nav_w, list_r, input_top, toolbar_y)


def _detect_independent_input(img):
    """
    独立聊天窗口的输入框检测：
    输入框上沿是极浅的边框，在灰度均值上几乎不可见，直接找最暗行还会被
    气泡内的深色文字吸引而误判。因此先定位特征很强、不受消息内容影响的
    工具栏图标行，再按输入框固定高度比例反推上沿。
    实测（1181x900）：工具栏行中心 853，输入框上沿 717，相差 136（0.151h）。
    """
    h = img.shape[0]
    gray = img[:, :, :3].mean(axis=2)

    # 工具栏行：底部左侧图标区域深色像素聚集（稳定可靠）
    dark = (gray[:, 20:260] < 150).sum(axis=1)
    t_lo, t_hi = int(h * 0.86), int(h * 0.98)
    icon_rows = [y for y in range(t_lo, t_hi) if dark[y] >= 8]
    if icon_rows:
        toolbar_y = int(np.median(icon_rows))
        input_top = toolbar_y - int(h * 0.151)
        return input_top, toolbar_y
    # 检测不到时兜底：按实测比例
    return int(h * 0.797), int(h * 0.947)


def calibrate_independent(img):
    """
    标定独立聊天窗口布局（无导航栏/联系人列表）。
    img: BGRA 数组
    """
    h, w = img.shape[:2]
    try:
        input_top, toolbar_y = _detect_independent_input(img)
        # 合理性约束，异常时回退到实测比例
        if not (int(h * 0.65) < input_top < int(h * 0.85)):
            input_top, toolbar_y = int(h * 0.797), int(h * 0.947)
    except Exception:
        input_top, toolbar_y = int(h * 0.797), int(h * 0.947)
    return Layout(w, h, 0, 0, input_top, toolbar_y, independent=True)
