# -*- coding: utf-8 -*-
"""本轮 bug 修复的回归测试：并发保护、非法配置不崩溃、前台零干预"""
import types


def test_respond_skips_when_previous_worker_alive(monkeypatch):
    """上一条回复的后台线程还活着时，本次必须跳过，不能并发调用"""
    import wechat_companion.companion as comp_mod
    from wechat_companion.companion import CompanionRunner

    monkeypatch.setattr(comp_mod, "_stop_file_requested", lambda: False)
    monkeypatch.setattr(comp_mod, "_parent_alive", lambda: True)

    runner = CompanionRunner()

    class _AliveWorker:
        def is_alive(self):
            return True

    runner._api_worker = _AliveWorker()

    sent = {"called": False}
    monkeypatch.setattr(
        "wechat_companion.wx_actions.send_message",
        lambda *a, **k: sent.__setitem__("called", True),
    )

    runner._respond("你好")
    assert sent["called"] is False


def test_validate_does_not_crash_on_non_numeric_values():
    """数字字段被写成无法转换的文本时，校验收集错误而不是抛异常崩溃"""
    from wechat_companion.validation import validate

    cfg = types.SimpleNamespace(
        TARGET_WXID="wxid_x",
        COMPANION_NAME="小伴",
        SYSTEM_PROMPT="你是助手",
        DEEPSEEK_API_KEY="sk-1234567890abcdef",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
        DEEPSEEK_MODEL="deepseek-chat",
        DEEPSEEK_TIMEOUT="abc",
        DEEPSEEK_TEMPERATURE="xyz",
        DEEPSEEK_MAX_RETRIES="n/a",
        KEEP_ROUNDS="bad",
        MAX_HISTORY_TOKENS="bad",
        HISTORY_PERSIST=True,
        OCR_LANG="zh-Hans-CN",
        OCR_FALLBACK_ENABLED=True,
        POLL_INTERVAL="bad",
        STABLE_CHECKS="bad",
        REPLY_COOLDOWN="bad",
        TYPE_THINK_DELAY=(0.2, 0.5),
        HUMANIZE_DELAY=(0.2, 0.5),
        WINDOW_WIDTH="bad",
        WINDOW_HEIGHT="bad",
        STOP_VK=0x78,
        DRY_RUN=False,
    )

    errors = validate(cfg)
    assert isinstance(errors, list)
    joined = " ".join(errors)
    assert "DEEPSEEK_TIMEOUT" in joined
    assert "KEEP_ROUNDS" in joined
    assert "WINDOW_WIDTH" in joined


def test_show_activate_is_noop_when_already_foreground(monkeypatch):
    """窗口已在前台时直接返回，不调用 ShowWindow、不挂接输入队列"""
    from wechat_companion import wx_window as winm

    class _FakeUser32:
        def __init__(self):
            self.show_window = 0
            self.attach = 0

        def GetForegroundWindow(self):
            return 100

        def ShowWindow(self, hwnd, cmd):
            self.show_window += 1

        def AttachThreadInput(self, *a, **k):
            self.attach += 1
            return 1

    fake = _FakeUser32()
    monkeypatch.setattr(winm, "user32", fake)

    assert winm.show_and_activate(100) is True
    assert fake.show_window == 0
    assert fake.attach == 0
