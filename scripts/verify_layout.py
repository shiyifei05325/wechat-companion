# -*- coding: utf-8 -*-
"""在当前微信画面上验证布局标定与气泡检测，输出标注图到 assets/"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from PIL import Image, ImageDraw
from wechat_companion import wx_window as winm
from wechat_companion import wx_detect as detect

hwnd = winm.find_main_window()
img, origin = winm.grab(hwnd)
layout = winm.calibrate(img)
print(layout)

found = detect.find_bottom_bubble(img, layout)
print("bottom bubble:", found["side"], found["point"], found["band"])

# 画标注图
pil = Image.fromarray(img[:, :, :3][:, :, ::-1])  # BGR->RGB
d = ImageDraw.Draw(pil)

# 消息区域
x0, y0, x1, y1 = layout.message_area
d.rectangle([x0, y0, x1, y1], outline=(0, 160, 255), width=2)
# 分隔线
d.line([layout.nav_w, 60, layout.nav_w, 880], fill=(255, 0, 255), width=2)
d.line([layout.list_r, 60, layout.list_r, 880], fill=(255, 0, 255), width=2)
# 输入面板顶部
d.line([layout.list_r, layout.input_top, pil.width - 10, layout.input_top], fill=(0, 200, 0), width=2)
# 搜索图标 / 结果行 / 输入点击 / 发送按钮
for (px, py), c in [(layout.search_icon, (255, 0, 0)),
                    (layout.search_result_row, (255, 128, 0)),
                    (layout.input_click, (0, 0, 255)),
                    (layout.send_button, (0, 0, 255)),
                    (layout.toolbar_check, (128, 0, 255))]:
    d.ellipse([px - 8, py - 8, px + 8, py + 8], outline=c, width=3)
# 检测到的气泡
if found["side"]:
    bx0, by0, bx1, by1 = found["band"]
    d.rectangle([bx0, by0, bx1, by1], outline=(255, 0, 0), width=3)
    px, py = found["point"]
    d.ellipse([px - 6, py - 6, px + 6, py + 6], fill=(255, 0, 0))

out = os.path.join(_ROOT, "assets", "calibration_overlay.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
pil.save(out)
print("saved", out)
