# -*- coding: utf-8 -*-
"""pytest 公共配置：把项目根与 src 布局加入导入路径"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (_ROOT, os.path.join(_ROOT, "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)
