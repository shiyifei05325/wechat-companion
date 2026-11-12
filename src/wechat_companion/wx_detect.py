# -*- coding: utf-8 -*-
"""
消息检测（纯图像）：
- 变化检测：只监测消息区下半部（watch_rect），新消息只出现在底部；
- 定位最新一条消息并区分收发方：
  * 主判据：自己的绿色气泡（右半区）vs 对方气泡（左半区），
    动态采样背景，按填充差异判定，兼容经典（灰底白气泡）与新版（白底灰气泡）；
  * 系统消息（时间分隔条/居中提示）自动识别并跳过；
  * 兜底：两侧头像列（贴图/表情等无气泡内容）。
"""
from typing import Dict, List, Optional, Tuple

import numpy as np

from .logging_setup import get_logger

logger = get_logger(__name__)


def _rgb(img: np.ndarray):
    """BGRA -> R,G,B"""
    return img[:, :, 2], img[:, :, 1], img[:, :, 0]


def green_mask(img: np.ndarray) -> np.ndarray:
    """自己发送的绿色气泡（兼容经典 149,236,105 与新版浅绿 157,242,159）"""
    r, g, b = _rgb(img)
    return (g > 190) & (r > 110) & (r < 215) & (b < 180) & (g > r + 30)


def _chat_background(img: np.ndarray, layout) -> float:
    """
    动态采样聊天背景灰度（取消息区顶部与右侧边缘条的中位数，
    即使个别位置有气泡也稳健）。
    """
    x0, y0, x1, y1 = layout.message_area
    strips = [
        img[y0:y0 + 8, x0:x1, :3],
        img[y0:y1, x1 - 8:x1, :3],
    ]
    vals = np.concatenate([s.reshape(-1, 3) for s in strips], axis=0)
    return float(np.median(vals.mean(axis=1)))


def other_bubble_mask(img: np.ndarray, bg_gray: float) -> np.ndarray:
    """
    对方文本气泡：填充灰度与背景差异明显（白气泡在灰底、灰气泡在白底均可），
    并排除绿色（自己）气泡。
    """
    gray = img[:, :, :3].mean(axis=2)
    diff = np.abs(gray - bg_gray)
    return (diff > 7) & ~green_mask(img)


def watch_rect(layout) -> Tuple[int, int, int, int]:
    """
    变化检测区域：消息区下 55%。
    新消息只出现在底部，监测下半区既减少计算量，也避免滚动旧内容误触发。
    """
    x0, y0, x1, y1 = layout.message_area
    return x0, y0 + int((y1 - y0) * 0.45), x1, y1


def _grid_signature(gray: np.ndarray, gy: int = 24, gx: int = 8) -> np.ndarray:
    """
    对单通道灰度图计算网格均值签名（每格均值量化到 //4）。
    供 area_signature / region_signature 复用，保证两者结果一致。
    """
    h, w = gray.shape
    if h < gy or w < gx:
        return np.zeros(gx * gy, dtype=np.uint8)
    ys = np.linspace(0, h, gy + 1, dtype=int)
    xs = np.linspace(0, w, gx + 1, dtype=int)
    cells = []
    for i in range(gy):
        for j in range(gx):
            block = gray[ys[i]:ys[i + 1], xs[j]:xs[j + 1]]
            cells.append(int(block.mean()) if block.size else 0)
    return (np.array(cells) // 4).astype(np.uint8)


def area_signature(img: np.ndarray, rect: Tuple[int, int, int, int],
                    gy: int = 24, gx: int = 8) -> np.ndarray:
    """
    计算指定区域的灰度网格签名（检测画面是否变化）。
    rect: (x0,y0,x1,y1) 窗口相对坐标
    """
    x0, y0, x1, y1 = rect
    gray = img[y0:y1, x0:x1, :3].mean(axis=2)
    return _grid_signature(gray, gy, gx)


def region_signature(region_img: np.ndarray, gy: int = 24,
                      gx: int = 8) -> np.ndarray:
    """
    对“已按 watch 区域裁剪好的画面”直接计算网格签名，
    结果与 area_signature(整窗, watch) 一致，省去整窗拷贝。
    """
    gray = region_img[:, :, :3].mean(axis=2)
    return _grid_signature(gray, gy, gx)


# --------------------------------------------------------------------------
# 气泡填充带扫描（主判据）
# --------------------------------------------------------------------------
def _band_kind(green: np.ndarray, other: np.ndarray,
               start: int, end: int, mid_local: int) -> str:
    """
    判定一个填充带的类型：'self' / 'other' / 'system'
    system：无绿色、命中窄且水平居中（时间分隔条/系统提示）。
    """
    gs = int(green[start:end + 1].sum())
    os_ = int(other[start:end + 1].sum())
    if gs >= os_:
        return "self"
    cols = np.where(other[start:end + 1].sum(axis=0) > 2)[0]
    if len(cols):
        width = int(cols[-1] - cols[0])
        cx = (int(cols[0]) + int(cols[-1])) / 2
        if width < 120 and cx > mid_local - 70:
            return "system"
    return "other"


def _fill_bands(img: np.ndarray, layout,
                min_width: int = 25, gap: int = 14):
    """
    按行扫描消息区域内的气泡填充，返回 (bands, gfull, ofull, bg_gray)：
    bands: [(top,bottom,side)]，按 top 排序；
    gfull/ofull 为整窗口掩码（供后续取气泡范围复用，避免重复计算）。
    """
    x0, y0, x1, y1 = layout.message_area
    mid = (x0 + x1) // 2
    mid_local = mid - x0
    bg_gray = _chat_background(img, layout)
    gfull = green_mask(img)
    ofull = other_bubble_mask(img, bg_gray)

    # 半区限定：绿色只在右半区统计，对方只在左半区统计，杜绝跨侧污染
    green = gfull[y0:y1, x0:x1].copy()
    other = ofull[y0:y1, x0:x1].copy()
    green[:, :mid_local] = 0
    other[:, mid_local:] = 0
    grow = green.sum(axis=1)
    orow = other.sum(axis=1)
    content = (grow > min_width) | (orow > min_width)

    bands = []
    n = len(content)
    i = 0
    while i < n:
        if not content[i]:
            i += 1
            continue
        start = i
        end = i
        j = i + 1
        while j < n:
            if content[j]:
                end = j
                j += 1
                continue
            # 跨行小间隙（多行气泡行距）：gap 行内若还有内容则并入同一带
            k = j
            while k < n and (k - j) < gap and not content[k]:
                k += 1
            if k < n and content[k]:
                j = k
            else:
                break
        kind = _band_kind(green, other, start, end, mid_local)
        bands.append((y0 + start, y0 + end + 1, kind))
        i = end + 1
    return bands, gfull, ofull, bg_gray


def _mask_extents(mask: np.ndarray, top: int, bottom: int,
                  x_min: int = 0, x_max: int = 10 ** 6):
    """
    取命中列中最长的连续段（容忍 6px 间隙），避免远处零散杂色
    （如头像/阴影）把气泡中心拉偏。
    """
    rows = mask[top:bottom, x_min:x_max]
    cols = (rows.sum(axis=0) > 2).astype(np.uint8)
    n = len(cols)
    best = None
    i = 0
    while i < n:
        if not cols[i]:
            i += 1
            continue
        start = i
        end = i
        j = i + 1
        while j < n:
            if cols[j]:
                end = j
                j += 1
                continue
            k = j
            while k < n and (k - j) <= 6 and not cols[k]:
                k += 1
            if k < n and cols[k]:
                j = k
            else:
                break
        if best is None or (end - start) > (best[1] - best[0]):
            best = (start, end)
        i = end + 1
    if best is not None:
        return int(best[0]) + x_min, int(best[1]) + x_min
    return None


# --------------------------------------------------------------------------
# 头像列扫描（兜底：贴图/表情等无填充气泡的消息）
# --------------------------------------------------------------------------
AVATAR_SIZE = 38       # 头像边长
SLIDE_H = 30           # 滑动窗口高度
STD_THRESHOLD = 22     # 头像区域灰度标准差阈值（照片通常 >25）


def _avatar_columns(layout):
    """返回 (对方头像列x0,x1, 自己头像列x0,x1)"""
    inc_x0 = layout.list_r + 14
    inc_x1 = inc_x0 + AVATAR_SIZE
    own_x1 = layout.w - 14
    own_x0 = own_x1 - AVATAR_SIZE
    return inc_x0, inc_x1, own_x0, own_x1


def _avatar_bands(img, x0, x1, y_start, y_end):
    """在指定头像列中找头像带，返回 [(top,bottom)]"""
    gray = img[:, :, :3].mean(axis=2)
    hits = []
    for cy in range(y_start, y_end, 6):
        patch = gray[cy:cy + SLIDE_H, x0:x1]
        if patch.size and patch.std() > STD_THRESHOLD:
            hits.append(cy)
    if not hits:
        return []
    bands = []
    cur = [hits[0], hits[0]]
    for cy in hits[1:]:
        if cy - cur[1] <= 12:
            cur[1] = cy
        else:
            bands.append(tuple(cur))
            cur = [cy, cy]
    bands.append(tuple(cur))
    return [(t, b + SLIDE_H) for t, b in bands]


def _avatar_fallback(img, layout, gfull=None):
    _x0, y0, _x1, _y1 = layout.message_area
    y_end = layout.input_top - 6
    inc_x0, inc_x1, own_x0, own_x1 = _avatar_columns(layout)
    inc_bands = _avatar_bands(img, inc_x0, inc_x1, y0, y_end)
    own_bands = _avatar_bands(img, own_x0, own_x1, y0, y_end)
    candidates = []
    if inc_bands:
        candidates.append(("other", inc_bands[-1]))
    if own_bands:
        candidates.append(("self", own_bands[-1]))
    if not candidates:
        return {"side": None, "point": None, "band": None, "source": "avatar"}
    side, (top, bottom) = max(candidates, key=lambda c: c[1][1])
    cy = (top + bottom) // 2
    if side == "other":
        cx = inc_x1 + 45
        band_rect = (inc_x0, top, inc_x1 + 260, bottom)
    else:
        gfull = gfull if gfull is not None else green_mask(img)
        ext = _mask_extents(gfull, top, bottom)
        if ext:
            cx = (ext[0] + ext[1]) // 2
            band_rect = (ext[0], top, ext[1], bottom)
        else:
            cx = own_x0 - 90
            band_rect = (own_x0 - 220, top, own_x1, bottom)
    cx = min(max(cx, layout.list_r + 30), layout.w - 20)
    return {"side": side, "point": (cx, cy), "band": band_rect,
            "source": "avatar"}


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def find_bottom_bubble(img: np.ndarray, layout) -> Dict[str, Optional[object]]:
    """
    定位最新一条消息。返回 dict:
      side: 'self' / 'other' / None
      point: (x,y) 气泡点击点（窗口相对坐标）
      band: (x0,y0,x1,y1) 消息行范围
      source: 'fill'（文本气泡）/ 'avatar'（兜底）
    """
    y_end = layout.input_top - 6
    x0, _, x1, _ = layout.message_area
    mid = (x0 + x1) // 2

    # 主判据：气泡填充带（掩码只算一次）；跳过系统消息，取最靠下的一条
    fill, gfull, ofull, bg_gray = _fill_bands(img, layout)
    for top, bottom, side in reversed(fill):
        if bottom >= y_end or side == "system":
            continue
        cy = (top + bottom) // 2
        if side == "self":
            ext = _mask_extents(gfull, top, bottom, x_min=mid, x_max=x1)
            if ext:
                cx = (ext[0] + ext[1]) // 2
                band_rect = (ext[0], top, ext[1], bottom)
            else:
                cx = layout.w - 260
                band_rect = (layout.w - 480, top, layout.w - 24, bottom)
        else:
            # 对方气泡只在左半区取中心（长气泡跨中线时中心点仍在气泡内）
            ext = _mask_extents(
                ofull, top, bottom,
                x_min=layout.list_r + 60, x_max=mid,
            )
            if ext:
                cx = (ext[0] + ext[1]) // 2
                band_rect = (ext[0], top, ext[1], bottom)
            else:
                _ix0, inc_x1, _, _ = _avatar_columns(layout)
                cx = inc_x1 + 45
                band_rect = (layout.list_r + 14, top, inc_x1 + 260, bottom)
        cx = min(max(cx, layout.list_r + 30), layout.w - 20)
        return {"side": side, "point": (cx, cy), "band": band_rect,
                "source": "fill"}

    # 无文本气泡（贴图/大表情）：头像列兜底（复用已算好的绿色掩码）
    return _avatar_fallback(img, layout, gfull)
