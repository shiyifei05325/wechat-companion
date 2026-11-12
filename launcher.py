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

# 打包态下这些参数只可能来自错误的自我调用（历史 fork 炸弹根因），一律拒绝
_FORBIDDEN_ARGS = {"-m", "pip", "ensurepip", "install"}


def main():
    # 打包模式：exe --companion 直接运行伴侣（由控制台以子进程方式拉起）
    # 子进程不参与单实例互斥锁
    if "--companion" in sys.argv:
        from wechat_companion.companion import main as companion_main
        companion_main()
        return 0

    # 熔断：任何危险的自我调用参数直接拒绝，不继续执行
    if any(a in _FORBIDDEN_ARGS for a in sys.argv[1:]):
        print("检测到不支持的启动参数，已拒绝（程序不支持以 pip/模块方式自我调用）。")
        return 2

    # 全局单实例：已有一个控制台在运行时直接退出，从机制上杜绝重复启动
    import single_instance
    if not single_instance.acquire():
        print("程序已经在运行中，请勿重复启动。")
        print("如需打开控制台，请在浏览器访问：http://127.0.0.1:5005")
        try:
            input("按回车键退出...")
        except EOFError:
            pass
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
