# -*- coding: utf-8 -*-
"""
统一启动器（用户唯一程序入口）

流程：环境检测 → 按需安装缺失依赖 → 启动本地后端控制台。
伴侣由人工在控制台页面内点击「启动伴侣」启动。
"""
import os
import sys

# 打包后：代码与资源在解包目录（_MEIPASS），用户数据/日志写在 exe 旁
if getattr(sys, "frozen", False):
    ROOT_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", ROOT_DIR)
    sys.path.insert(0, os.path.join(BUNDLE_DIR, "src"))
    sys.path.insert(0, BUNDLE_DIR)
else:
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(ROOT_DIR, "src"))
    sys.path.insert(0, ROOT_DIR)

from env_check import run_checks  # noqa: E402


def main():
    # 打包模式：exe --companion 直接运行伴侣（由控制台以子进程方式拉起）
    if "--companion" in sys.argv:
        from wechat_companion.companion import main as companion_main
        companion_main()
        return 0

    if not run_checks(auto_install=True):
        try:
            input("环境未就绪，按回车键退出...")
        except EOFError:
            pass
        return 1

    from control.server import main as server_main
    server_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
