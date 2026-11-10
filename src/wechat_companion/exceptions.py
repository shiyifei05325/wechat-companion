# -*- coding: utf-8 -*-
"""
统一异常体系

层级：
    CompanionError                    所有业务异常的基类
    ├── ConfigValidationError         启动配置校验失败
    ├── WindowNotFoundError           找不到微信主窗口
    ├── WindowClosedError             运行期间微信主窗口被关闭
    ├── ClipboardError                剪贴板持续不可用
    ├── ActionError                   键鼠/界面动作失败
    └── BrainError                    AI 大脑调用失败（调用方通常按可恢复处理）
"""


class CompanionError(Exception):
    """微信虚拟伴侣业务异常基类"""


class ConfigValidationError(CompanionError):
    """配置校验失败：errors 为逐条问题描述"""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("配置校验失败：" + "；".join(self.errors))


class WindowNotFoundError(CompanionError):
    """找不到微信主窗口（未登录/未打开）"""


class WindowClosedError(CompanionError):
    """运行期间微信主窗口被用户关闭"""


class ClipboardError(CompanionError):
    """剪贴板持续被占用或不可用"""


class ActionError(CompanionError):
    """键鼠模拟或界面动作失败"""


class BrainError(CompanionError):
    """AI 接口调用失败（可恢复，调用方可继续监听）"""
