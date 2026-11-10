# -*- coding: utf-8 -*-
"""性能优化专项：默认节奏、思考/接口并行、检测吞吐"""
import threading
import time

import numpy as np

from wechat_companion import companion as comp_mod
from wechat_companion import config as cfg
from wechat_companion import wx_detect as detect


def test_optimized_default_timings():
    assert cfg.POLL_INTERVAL <= 1.2
    assert cfg.REPLY_COOLDOWN <= 0.8
    assert cfg.TYPE_THINK_DELAY[0] <= 0.8
    assert cfg.TYPE_THINK_DELAY[1] <= 2.2
    assert cfg.HUMANIZE_DELAY[1] <= 0.5


def test_signature_computation_is_fast():
    img = np.random.randint(0, 255, (900, 1180, 4), dtype=np.uint8)
    t0 = time.monotonic()
    for _ in range(10):
        detect.area_signature(img, (290, 60, 1120, 760))
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5  # 单次签名远低于轮询间隔，CPU 占用可忽略


class _SlowBrain:
    """模拟耗时 0.25 秒的真实接口（用 Event.wait，不受 time.sleep patch 影响）"""
    def reply(self, text):
        threading.Event().wait(0.25)
        return "回复内容"


def test_respond_overlaps_think_delay_with_api(monkeypatch):
    monkeypatch.setattr(comp_mod, "_stop_file_requested", lambda: False)
    monkeypatch.setattr(comp_mod, "_parent_alive", lambda: True)
    monkeypatch.setattr(cfg, "TYPE_THINK_DELAY", (0.3, 0.3))
    monkeypatch.setattr(cfg, "REPLY_COOLDOWN", 0.0)
    sent = {}
    monkeypatch.setattr(
        comp_mod.actions, "send_message",
        lambda hwnd, layout, text, dry: sent.__setitem__("text", text) or True,
    )

    runner = comp_mod.CompanionRunner()
    runner.brain = _SlowBrain()
    t0 = time.monotonic()
    runner._respond("在吗")
    elapsed = time.monotonic() - t0

    # 并行：max(思考0.3, 接口0.25) ≈ 0.3；串行将是 0.55
    assert elapsed < 0.45
    assert sent.get("text") == "回复内容"


def test_respond_not_sent_when_stopped(monkeypatch):
    monkeypatch.setattr(comp_mod, "_stop_file_requested", lambda: True)
    sent = {}
    monkeypatch.setattr(
        comp_mod.actions, "send_message",
        lambda hwnd, layout, text, dry: sent.__setitem__("text", text) or True,
    )
    runner = comp_mod.CompanionRunner()
    runner.brain = _SlowBrain()
    runner._respond("在吗")
    assert "text" not in sent
