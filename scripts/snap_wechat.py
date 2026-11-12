# -*- coding: utf-8 -*-
"""截取微信主窗口当前画面，用于布局分析（调试辅助脚本，需要 uiautomation）"""
import os
import psutil, ctypes
from ctypes import wintypes
import mss
try:
    import uiautomation as ua
except ImportError:
    raise SystemExit(
        "该调试脚本需要可选依赖 uiautomation（不随主程序安装）。\n"
        r"如需运行：C:\Python313\python.exe -m pip install uiautomation"
    )

# 1) 找到微信主窗口（属于 Weixin.exe 的可见 Qt 窗口，面积最大）
wx_pids = set()
for p in psutil.process_iter(["name", "pid"]):
    if p.info["name"] and p.info["name"].lower() in ("weixin.exe", "wechat.exe"):
        wx_pids.add(p.info["pid"])

root = ua.GetRootControl()
best = None
best_area = 0
for c in root.GetChildren():
    if c.ProcessId in wx_pids:
        r = c.BoundingRectangle
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > best_area:
            best = c
            best_area = area

if best is None:
    raise SystemExit("未找到微信主窗口：请确认 PC 微信已登录、主窗口可见后重试。")

r = best.BoundingRectangle
print("rect:", r.left, r.top, r.right, r.bottom, "title:", best.Name, "class:", best.ClassName)

with mss.mss() as sct:
    shot = sct.grab({"left": r.left, "top": r.top, "width": r.right - r.left, "height": r.bottom - r.top})
    img = mss.tools.to_png(shot.rgb, shot.size)
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(_ROOT, "assets", "wx_layout.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "wb") as f:
    f.write(img)
print("saved", out)
