# -*- coding: utf-8 -*-
"""
启动环境检测与按需安装

仅使用 Python 标准库编写，保证在任何第三方依赖缺失时都能运行：
- 检测操作系统（仅支持 Windows）与 Python 版本（>= 3.9）；
- 检测运行时依赖是否已安装、版本是否达标，仅对缺失/过旧的包执行 pip 安装；
- 检测 PC 微信是否在运行（给出提示，不强制）；
- pip 缺失时尝试 ensurepip 引导。
"""
import importlib.util
import os
import re
import subprocess
import sys

MIN_PYTHON = (3, 9)

# 是否为 PyInstaller 打包态：打包后依赖已内置，禁止任何 pip/自安装行为
# （历史教训：打包态误判依赖缺失后用 sys.executable 自我拉起，形成 fork 炸弹）
FROZEN = getattr(sys, "frozen", False)

# 导入名 -> (pip 发行版名, 最低版本)
REQUIRED_PACKAGES = {
    "pyautogui": ("pyautogui", "0.9.54"),
    "pyperclip": ("pyperclip", "1.8"),
    "mss": ("mss", "9.0"),
    "PIL": ("pillow", "10.0"),
    "numpy": ("numpy", "1.26"),
    "requests": ("requests", "2.31"),
    "psutil": ("psutil", "5.9"),
    "flask": ("flask", "3.0"),
    # 全局热键（pynput）与 Windows 内置 OCR 兜底（winocr），均为 Windows 专用
    "pynput": ("pynput", "1.7"),
    "winocr": ("winocr", "0.0.15"),
}


# ---------------- 基础环境 ----------------
def check_python():
    """Python 版本是否达标"""
    return sys.version_info >= MIN_PYTHON


def check_os():
    """是否为 Windows 环境"""
    return sys.platform.startswith("win")


def python_version_text():
    return ".".join(str(x) for x in sys.version_info[:3])


# ---------------- 依赖检测 ----------------
def _parse_version(text):
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3])


def _version_lt(actual, required):
    a = _parse_version(actual)
    b = _parse_version(required)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a < b


def _module_available(import_name):
    try:
        return importlib.util.find_spec(import_name) is not None
    except Exception:
        return False


def frozen_import_smoke():
    """
    打包态专用：真正 import 每个内置模块，确认能加载。
    只验证“能否导入”，不查版本（打包态没有安装元数据）。
    返回失败的导入名列表；全部成功返回空列表。
    """
    failed = []
    for import_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except Exception:
            failed.append(import_name)
    return failed


def _installed_version(dist_name):
    try:
        import importlib.metadata as metadata
        return metadata.version(dist_name)
    except Exception:
        return None


def missing_packages():
    """
    返回需要安装的 pip 需求规格（如 'flask>=3.0'）。
    已安装且版本达标的包不再出现在结果中。
    """
    missing = []
    for import_name, (dist_name, min_version) in REQUIRED_PACKAGES.items():
        if _module_available(import_name):
            version = _installed_version(dist_name)
            if version is None or _version_lt(version, min_version):
                missing.append(f"{dist_name}>={min_version}")
        else:
            missing.append(f"{dist_name}>={min_version}")
    return missing


# ---------------- pip 与安装 ----------------
def ensure_pip():
    """确认 pip 可用；打包态永远不允许引导 pip"""
    if FROZEN:
        return False
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True, capture_output=True,
        )
        return True
    except Exception:
        pass
    try:
        subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            check=True, capture_output=True,
        )
        return True
    except Exception:
        return False


def install_packages(specs):
    """安装指定需求规格；成功返回 True。打包态直接拒绝（防止自我拉起）"""
    if FROZEN:
        print("打包态不支持在线安装，依赖已内置；跳过安装。")
        return False
    if not specs:
        return True
    if not ensure_pip():
        print("无法引导 pip，请手动安装 pip 后重试。")
        return False
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check",
        *specs,
    ]
    print("执行安装：", " ".join(specs))
    completed = subprocess.run(cmd)
    return completed.returncode == 0


# ---------------- 微信检测 ----------------
def detect_wechat():
    """返回正在运行的微信 pid 列表（依赖 psutil；不可用时返回空列表）"""
    try:
        import psutil
    except Exception:
        return []
    pids = []
    for proc in psutil.process_iter(["name"]):
        name = (proc.info["name"] or "").lower()
        if name in ("weixin.exe", "wechat.exe"):
            pids.append(proc.pid)
    return pids


# ---------------- 完整检测入口 ----------------
def run_checks(auto_install=True):
    """
    执行完整环境检测；auto_install=True 时对缺失依赖自动按需安装。
    全部就绪返回 True，否则 False。
    """
    print("=" * 56)
    print("环境检测")
    print("=" * 56)
    print(f"操作系统：{sys.platform}（仅支持 Windows）")
    print(f"Python：{python_version_text()}（要求 >= {'.'.join(map(str, MIN_PYTHON))}）")

    if not check_os():
        print("本程序仅支持 Windows，当前系统不满足，退出。")
        return False
    if not check_python():
        print("Python 版本过低，请升级后重试。")
        return False

    if FROZEN:
        # 打包态：依赖已内置，只做导入冒烟；失败直接退出，绝不安装/自我拉起
        print("打包运行模式：依赖已内置，执行导入冒烟检查...")
        failed = frozen_import_smoke()
        if failed:
            print("内置模块加载失败：" + ", ".join(failed))
            print("发布包可能损坏，请重新获取完整程序目录。")
            return False
        print("内置模块全部可正常加载。")
    else:
        missing = missing_packages()
        if missing:
            print(f"缺失或过旧的依赖（{len(missing)} 个）：{', '.join(missing)}")
            if auto_install:
                if not install_packages(missing):
                    print("依赖安装失败，请检查网络或手动执行 pip install。")
                    return False
                missing = missing_packages()
                if missing:
                    print(f"安装后仍缺失：{', '.join(missing)}")
                    return False
                print("依赖安装完成。")
        else:
            print("运行时依赖：全部已安装且版本达标。")

    wechat_pids = detect_wechat()
    if wechat_pids:
        print(f"检测到 PC 微信正在运行（{len(wechat_pids)} 个进程）。")
    else:
        print("提示：未检测到 PC 微信，请先登录并打开微信（伴侣启动时会再次检查）。")

    print("环境检测通过。\n")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_checks(auto_install=True) else 1)
