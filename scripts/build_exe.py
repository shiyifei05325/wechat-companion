# -*- coding: utf-8 -*-
"""
打包脚本（PyInstaller，onedir 模式）：
    python scripts/build_exe.py

产物：dist/WeChatCompanion/WeChatCompanion.exe（双击即启动控制台；
伴侣由控制台以「exe --companion」方式拉起，无需用户另外安装 Python）。

说明：
- 打包前请确认已安装 pyinstaller：  python -m pip install pyinstaller
- onedir 模式启动更快、杀软误报更少，适合本地分发；
- 如需单文件可加 --onefile（启动会慢一些）。
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description="PyInstaller 打包")
    parser.add_argument("--onefile", action="store_true", help="单文件模式")
    parser.add_argument("--name", default="WeChatCompanion", help="产物名称")
    args = parser.parse_args()

    # 检查 pyinstaller 是否可用
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未检测到 pyinstaller，请先安装：")
        print("  python -m pip install pyinstaller")
        return 1

    sep = ";" if os.name == "nt" else ":"
    mode_flag = "--onefile" if args.onefile else "--onedir"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        mode_flag,
        "--noconfirm",
        "--clean",
        "--name", args.name,
        "--console",   # 保留控制台窗口（显示日志；关闭窗口即停止服务）
        # 数据资源
        f"--add-data=control{sep}control",
        f"--add-data=assets{sep}assets",
        # 隐式依赖（pyautogui / mss 的部分后端不会被自动追踪）
        "--hidden-import=mss.windows",
        "--hidden-import=pyautogui",
        "--collect-submodules=pyautogui",
        "--collect-submodules=pygetwindow",
        # 入口
        "launcher.py",
    ]

    print("执行：", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)

    mode = "onefile" if args.onefile else "onedir"
    if mode == "onefile":
        out = os.path.join(ROOT, "dist", args.name + ".exe")
    else:
        out = os.path.join(ROOT, "dist", args.name, args.name + ".exe")
    print("打包完成：", out)
    print("分发时请连同整个目录一起拷贝（onedir）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
