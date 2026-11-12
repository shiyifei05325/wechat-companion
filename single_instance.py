# -*- coding: utf-8 -*-
"""
全局单实例保护（Windows 命名 Mutex，仅用标准库 ctypes）。

主程序（控制台服务器）启动时调用 acquire()：
- 若已有一个实例在运行，返回 False；
- 否则持有互斥锁并返回 True。锁随进程生命周期存在，进程结束自动释放。

注意：伴侣子进程（exe --companion）不调用本函数，避免被误判为重复实例。
"""
import ctypes
import sys

ERROR_ALREADY_EXISTS = 183

# 固定名称：同一用户会话内所有实例共享；不使用 Global 前缀以免需要管理员权限
_MUTEX_NAME = "Local\\WeChatCompanion_SingleInstance_Mutex"
_handle = None


def acquire():
    """尝试创建命名互斥锁；成功（本进程为首个实例）返回 True"""
    global _handle
    if not sys.platform.startswith("win"):
        return True
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    _handle = kernel32.CreateMutexW(None, 0, _MUTEX_NAME)
    # 若互斥锁已存在，GetLastError 返回 ERROR_ALREADY_EXISTS
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
