# -*- coding: utf-8 -*-
"""
微信虚拟伴侣（基于屏幕捕捉 + 键鼠模拟，接入 DeepSeek）
配置文件：目标微信号、DeepSeek API、伴侣人设、运行参数

个人配置（目标微信号、人设、节奏等）保存在项目根目录的 local_config.json，
该文件已被 .gitignore 排除，不会随代码提交；本文件只保留可公开的默认值。

配置优先级：环境变量 > local_config.json > 本文件内置值

密钥安全：API 密钥不写入本文件，由 secret_store 以 Windows DPAPI 加密
（与当前用户/机器绑定）保存在 data/.apikey。
"""
import json
import os
import sys

# 项目根目录：本文件位于 <根>/src/wechat_companion/config.py，需上溯三级；
# 打包（frozen）后以可执行文件所在目录为根（数据/日志写在 exe 旁）
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 运行数据目录：统计数据库、密钥、许可证
DATA_DIR = os.path.join(BASE_DIR, "data")
_OVERRIDE_PATH = os.path.join(BASE_DIR, "local_config.json")


def _load_overrides():
    """读取 local_config.json 覆盖；文件缺失或损坏时静默忽略"""
    try:
        with open(_OVERRIDE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


_ov = _load_overrides()


def _v(key, default):
    """取覆盖值；覆盖中没有或为 None 时使用内置值"""
    val = _ov.get(key)
    return default if val is None else val


def _resolve_api_key():
    """
    密钥解析：环境变量 > DPAPI 保护存储（data/.apikey）> 内置默认（空）。
    """
    env = os.environ.get("DEEPSEEK_API_KEY")
    if env:
        return env
    try:
        from .secret_store import load_api_key
        key = load_api_key()
        if key:
            return key
    except Exception:
        pass
    return _v("DEEPSEEK_API_KEY", "")


# ============ 目标用户 ============
# 要监听/陪伴的微信号（搜索时使用）；首次使用请在控制台填写
TARGET_WXID = _v("TARGET_WXID", "")
# 搜索结果中该联系人显示的名称（仅用于日志校验，留空则不校验）
TARGET_NAME = _v("TARGET_NAME", "")

# ============ DeepSeek ============
DEEPSEEK_API_KEY = _resolve_api_key()
DEEPSEEK_BASE_URL = _v("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = _v("DEEPSEEK_MODEL", "deepseek-chat")  # 会自动路由到合适的对话模型
DEEPSEEK_TIMEOUT = 60                     # 单次请求超时(秒)
DEEPSEEK_TEMPERATURE = float(_v("DEEPSEEK_TEMPERATURE", 1.0))
DEEPSEEK_MAX_RETRIES = 2

# ============ 虚拟伴侣人设 ============
COMPANION_NAME = _v("COMPANION_NAME", "小伴")
SYSTEM_PROMPT = _v(
    "SYSTEM_PROMPT",
    "你是一个温柔、体贴、说话自然的聊天伙伴。不要暴露自己是 AI，"
    "不要用括号描述动作或表情，回复简短口语化，像真人聊天。",
)
# 上下文保留的最近对话轮数（一轮=用户+伴侣）
KEEP_ROUNDS = int(_v("KEEP_ROUNDS", 12))

# ============ 窗口与布局 ============
# 启动时把微信主窗口固定到该位置和尺寸（像素，物理分辨率）
WINDOW_LEFT, WINDOW_TOP = 0, 0
WINDOW_WIDTH, WINDOW_HEIGHT = 1180, 900
# 退出时是否恢复窗口原来的位置尺寸
RESTORE_WINDOW_ON_EXIT = bool(_v("RESTORE_WINDOW_ON_EXIT", False))

# ============ 监听与回复节奏 ============
# 活跃期（最近有消息）轮询间隔：越小响应越快
POLL_INTERVAL = float(_v("POLL_INTERVAL", 0.6))
# 空闲期自动放慢到该间隔（降低 CPU 占用）
IDLE_POLL_INTERVAL = float(_v("IDLE_POLL_INTERVAL", 2.0))
STABLE_CHECKS = 2              # 画面变化后连续确认次数（保留兼容）
HUMANIZE_DELAY = (0.2, 0.5)    # 模拟操作之间的随机停顿(秒)
REPLY_COOLDOWN = float(_v("REPLY_COOLDOWN", 0.8))  # 发送回复后冷却(秒)
# 思考停顿与接口调用并行（总耗时取较大值），并按回复长度自适应
TYPE_THINK_DELAY = tuple(float(x) for x in _v(
    "TYPE_THINK_DELAY", [0.5, 2.2]
))

# ============ 安全开关 ============
# 演练模式：True 时只记录“本来要做什么”，不真正点击/发送
DRY_RUN = bool(_v("DRY_RUN", False))
# 伴侣异常退出/卡死时，看门狗是否自动重启（默认关闭：仍由人工在控制台启动）
AUTO_RESTART_ON_CRASH = bool(_v("AUTO_RESTART_ON_CRASH", False))
# 紧急停止热键（虚拟键码：F9=0x78）。把鼠标猛甩到屏幕左上角也可触发 pyautogui FAILSAFE
STOP_VK = 0x78

# ============ 日志 ============
# 锚定到项目根目录下的 logs/，无论从哪里启动都不会散落
LOG_DIR = os.path.join(BASE_DIR, "logs")
