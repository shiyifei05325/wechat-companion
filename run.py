# -*- coding: utf-8 -*-
"""
命令行备用入口：
    python run.py
停止：F9 热键，或 Ctrl+C，或把鼠标甩到屏幕左上角。

正常使用请双击「一键启动.bat」（环境检测 + 可视化控制台）。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from wechat_companion.companion import main  # noqa: E402

if __name__ == "__main__":
    main()
