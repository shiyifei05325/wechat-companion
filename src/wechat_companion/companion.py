# -*- coding: utf-8 -*-
"""
主控：监听微信消息 -> DeepSeek 虚拟伴侣思考 -> 键鼠模拟自动回复

运行保障：
- 启动配置校验（validation），不合法即 fail-fast；
- 单实例锁 companion.lock：同一时刻只允许一个伴侣运行；
- 停止标记 companion.stop：控制台写入后主循环立即优雅退出；
- 控制台（父进程）关闭后伴侣自动停止，不留隐藏后台进程；
- 微信主窗口被关闭/最小化时不复活、不抢窗口：关闭即退出、最小化即等待；
- 主循环逐轮异常隔离 + 退避自愈，单次错误不会导致进程崩溃；
- 心跳文件 companion.heartbeat：可供外部确认进程存活。

性能设计：
- 自适应轮询：活跃期快速轮询，空闲期自动放慢（省 CPU）；
- 变化检测只看消息区下半部；
- 画面稳定确认改为 0.25s 级快速轮询（连续 2 次一致即稳定）；
- 读图失败时在气泡内换点重试一次；
- 思考停顿按回复长度自适应，并与接口调用并行；
- 接口连接启动时预热 TLS。
"""
import ctypes
import datetime
import hashlib
import os
import signal
import threading
import time

from . import config as cfg
from . import stats, wx_ocr
from . import wx_actions as actions
from . import wx_detect as detect
from . import wx_window as winm
from .brain import DeepSeekCompanion
from .exceptions import (
    ActionError,
    CompanionError,
    ConfigValidationError,
    WindowClosedError,
    WindowNotFoundError,
)
from .logging_setup import configure_logging, get_logger
from .validation import validate_or_raise

# 全局停止热键：优先用 pynput 做事件监听（无需轮询），缺失时回退 GetAsyncKeyState
try:
    from pynput import keyboard as _pynput_kb
    _PYNPUT_OK = True
except Exception:  # pragma: no cover - 依赖缺失时降级
    _pynput_kb = None
    _PYNPUT_OK = False

user32 = ctypes.windll.user32

# 运行时文件统一锚定到项目根目录（由 config 暴露）
LOCK_PATH = os.path.join(cfg.BASE_DIR, "companion.lock")
STOP_PATH = os.path.join(cfg.BASE_DIR, "companion.stop")
HEARTBEAT_PATH = os.path.join(cfg.BASE_DIR, "companion.heartbeat")

# 活跃窗口：最近多少秒内有画面变化，按快速节奏轮询
ACTIVE_WINDOW = 30.0
# 画面稳定确认参数
SETTLE_POLL = 0.25
SETTLE_DEADLINE = 4.0
# 处理完一条消息后的抑制时长（秒）：期间画面变化只更新基线，不重复处理
SUPPRESS_SECONDS = 0.8
# 连续消息合并：连续多少秒没有新消息，就认为对方这波连发结束
BURST_GATHER_IDLE = 1.5
# 一批最多收集多少条（防止异常情况下无限收集）
BURST_MAX = 30
# 心跳写入最小间隔
HEARTBEAT_INTERVAL = 2.0

logger = get_logger(__name__)


# ---------------- 单实例锁 ----------------
def _lock_held_by_live_instance():
    """锁文件中的 pid 仍是一个运行中的伴侣进程时返回 True（run.py / --companion）"""
    try:
        import psutil
        with open(LOCK_PATH, encoding="utf-8") as f:
            old = int(f.read().strip() or 0)
        if old and psutil.pid_exists(old):
            cmdline = " ".join(psutil.Process(old).cmdline())
            return "run.py" in cmdline or "--companion" in cmdline
    except Exception:
        pass
    return False


def _acquire_lock():
    if _lock_held_by_live_instance():
        return False
    try:
        with open(LOCK_PATH, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False


def _release_lock():
    try:
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
    except Exception:
        pass


# ---------------- 停止信号 ----------------
def _stop_file_requested():
    return os.path.exists(STOP_PATH)


def _parent_alive():
    """启动它的控制台还在不在；未通过控制台启动时不限制"""
    ppid = os.environ.get("COMPANION_PARENT_PID")
    if not ppid:
        return True
    try:
        import psutil
        return psutil.pid_exists(int(ppid))
    except Exception:
        return True


def _write_heartbeat():
    """写入心跳（pid + 时间）；失败不影响主流程"""
    try:
        payload = f"{os.getpid()}|{datetime.datetime.now():%Y-%m-%d %H:%M:%S}"
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            f.write(payload)
    except Exception:
        pass


def _resolve_vk(key):
    """
    解析按键的虚拟键码：
    普通键为 KeyCode（直接有 .vk）；功能键为 Key 枚举（vk 在 .value.vk）。
    """
    vk = getattr(key, "vk", None)
    if vk is None:
        vk = getattr(getattr(key, "value", None), "vk", None)
    return vk


class CompanionRunner:
    def __init__(self):
        self.running = True
        self.hwnd = None
        self.main_hwnd = None        # 微信主窗口（用于搜索联系人）
        self.layout = None
        self.watch = None
        self.brain = None
        self.baseline = None
        self.independent = False      # 是否运行在独立聊天窗口
        self.suppress_until = 0.0     # 抑制期：此时间前画面变化只更新基线，不处理
        # 已处理消息跟踪（用于排空连续消息，避免重复/遗漏）
        self._seen_texts = []        # 已处理 (side,text) 有序列表，FIFO 修剪
        self._seen_keep = 60         # _seen_texts 最多保留条数
        # 气泡像素指纹 -> 文本缓存：同一条消息无论滚到哪里，气泡像素都相同，
        # 命中缓存就不再右键，避免每轮把历史消息全部重读一遍拖慢排空。
        self._text_cache = {}
        self.last_user = ("", 0.0)
        self.recent_self = []   # 最近自己发送的文本（防自回复）
        self.active_until = 0.0
        self._last_hb = 0.0
        self._hotkey_stop = False
        self._listener = None
        # 当前正在等待接口的后台线程：用于避免上一条还没处理完就并发再次调用
        self._api_worker = None

    # ---------------- 启动 ----------------
    def start(self):
        configure_logging(cfg.LOG_DIR)
        logger.info("=" * 50)
        logger.info("微信虚拟伴侣「%s」启动", cfg.COMPANION_NAME)
        logger.info("目标微信号: %s | 演练模式: %s", cfg.TARGET_WXID, cfg.DRY_RUN)
        logger.info("按 F9 停止；或把鼠标猛甩到屏幕左上角紧急中止")
        logger.info("=" * 50)

        # 1) 配置校验
        try:
            validate_or_raise(cfg)
        except ConfigValidationError as e:
            for problem in e.errors:
                logger.error("配置问题：%s", problem)
            logger.error("配置校验未通过，启动中止。")
            return

        # 2) 单实例锁
        if not _acquire_lock():
            logger.error("已有一个伴侣正在运行（单实例限制），本次不重复启动。")
            logger.error("如需重启，请先在控制台点击「停止」。")
            return

        # 清理上一轮可能残留的停止标记
        try:
            if os.path.exists(STOP_PATH):
                os.remove(STOP_PATH)
        except Exception:
            pass

        # 3) 定位微信主窗口（搜索联系人、打开独立窗口都需要主窗口）
        try:
            self.independent = cfg.WINDOW_MODE == "independent"
            self.main_hwnd = winm.find_main_window()
        except WindowNotFoundError as e:
            logger.error("%s", e)
            _release_lock()
            return
        self.hwnd = self.main_hwnd
        original_rect = winm.get_rect(self.main_hwnd)

        # 大脑在配置校验通过后再构造；后台预热接口连接
        self.brain = DeepSeekCompanion(cfg)
        threading.Thread(target=self.brain.prewarm, name="prewarm",
                         daemon=True).start()

        try:
            self.start_hotkey_listener()
            self._prepare()
            self._loop()
        finally:
            self._shutdown(original_rect)

    def _calibrate_now(self):
        """抓取当前画面并按窗口模式标定，返回 (img, layout)"""
        img, _ = winm.grab(self.hwnd)
        if self.independent:
            return img, winm.calibrate_independent(img)
        return img, winm.calibrate(img)

    def _prepare(self):
        # 先固定主窗口，保证搜索/列表坐标一致
        if not cfg.DRY_RUN:
            winm.normalize_window(
                self.main_hwnd,
                cfg.WINDOW_LEFT, cfg.WINDOW_TOP,
                cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT,
            )
        winm.force_foreground(self.main_hwnd)

        if self.independent:
            if cfg.DRY_RUN:
                # 演练：走一遍打开流程但不真正点击
                actions.open_chat_in_new_window(
                    self.main_hwnd, cfg.TARGET_WXID, cfg.TARGET_NAME, dry=True)
                img, self.layout = self._calibrate_now()
            else:
                # 已有独立窗口则直接复用（重启时避免重复搜索/开窗）
                chat_hwnd = winm.find_chat_window(cfg.TARGET_NAME)
                if chat_hwnd is None:
                    # 搜索微信号 -> 双击打开独立窗口 -> OCR 校验
                    chat_hwnd, _chat_layout = actions.open_chat_in_new_window(
                        self.main_hwnd, cfg.TARGET_WXID, cfg.TARGET_NAME)
                if chat_hwnd is None:
                    raise ActionError(
                        "没能打开独立聊天窗口，请确认微信号/昵称正确后重试。")
                self.hwnd = chat_hwnd
                # 固定独立窗口并重新标定
                winm.normalize_window(
                    chat_hwnd,
                    cfg.WINDOW_LEFT, cfg.WINDOW_TOP,
                    cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT,
                )
                img, self.layout = self._calibrate_now()
        elif cfg.DRY_RUN:
            img, _ = winm.grab(self.main_hwnd)
            self.layout = winm.calibrate(img)
        else:
            # 主窗口模式：搜索并打开目标聊天
            self.layout = actions.open_chat_by_wxid(self.main_hwnd, cfg.TARGET_WXID)
            if self.layout is None:
                raise ActionError(
                    "没能打开目标聊天，请确认微信号正确，或手动打开该聊天后重试。")
            winm.normalize_window(
                self.main_hwnd,
                cfg.WINDOW_LEFT, cfg.WINDOW_TOP,
                cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT,
            )
            img, self.layout = self._calibrate_now()

        logger.info("布局标定: %s", self.layout)
        # 稳定期：等待残余动画结束，再刷新基线
        time.sleep(1.2)
        img, self.layout = self._calibrate_now()
        self.watch = detect.watch_rect(self.layout)
        self.baseline = detect.area_signature(img, self.watch)
        # 启动基线：读取当前画面全部消息文本，标记为“已处理”。
        # 之后用 (side,text) 文本身份做增量对比，即使新消息导致画面滚动，
        # 也能靠文本而非绝对坐标识别新消息，同时不会把历史消息当成新消息。
        # 先用系统 API 把鼠标移到安全位置，避免启动时鼠标停在角落触发 fail-safe。
        winm.user32.SetCursorPos(400, 400)
        self._seen_texts = []
        self._text_cache = {}
        for b in detect.find_all_bubbles(img, self.layout):
            txt = self._bubble_text(b, img)
            self._seen_texts.append((b["side"], txt))
        logger.info("已标记启动画面 %d 条历史消息，等待新消息...",
                    len(self._seen_texts))

    # ---------------- 停止检测 ----------------
    def _stop_requested(self):
        if self._hotkey_stop or (not _PYNPUT_OK and self._stop_pressed()):
            logger.info("收到停止热键，退出中...")
            return True
        if _stop_file_requested():
            logger.info("收到控制台停止指令，退出中...")
            return True
        if not _parent_alive():
            logger.info("控制台已关闭，伴侣自动退出...")
            return True
        return False

    def start_hotkey_listener(self):
        """启动 pynput 全局热键监听；不可用时静默回退到轮询方式。"""
        if not _PYNPUT_OK:
            logger.warning("pynput 不可用，停止热键改用 GetAsyncKeyState 轮询")
            return
        target_vk = cfg.STOP_VK

        def _on_press(key):
            if _resolve_vk(key) == target_vk:
                self._hotkey_stop = True

        try:
            self._listener = _pynput_kb.Listener(on_press=_on_press)
            self._listener.daemon = True
            self._listener.start()
            logger.info("全局停止热键监听已启动（VK=%s）", target_vk)
        except Exception as e:
            logger.warning("热键监听启动失败，回退轮询：%s", e)
            self._listener = None

    def stop_hotkey_listener(self):
        """停止热键监听，释放底层线程。"""
        try:
            if self._listener is not None:
                self._listener.stop()
        except Exception:
            pass
        self._listener = None

    def _poll_interval(self):
        """自适应：活跃期快速，空闲期放慢"""
        return (cfg.POLL_INTERVAL if time.monotonic() < self.active_until
                else cfg.IDLE_POLL_INTERVAL)

    # ---------------- 主循环（逐轮异常隔离 + 退避自愈） ----------------
    def _loop(self):
        consecutive_errors = 0
        while self.running:
            self._maybe_heartbeat()
            try:
                if self._stop_requested():
                    self.running = False
                    break

                state = self._window_state()
                if state == "gone":
                    raise WindowClosedError("微信主窗口已被用户关闭")
                if state == "idle":
                    # 最小化/隐藏中：不截图、不动作，等待窗口恢复
                    time.sleep(cfg.POLL_INTERVAL)
                    continue

                region = winm.grab_region(self.hwnd, self.watch)
                sig = detect.region_signature(region)

                if not self._changed(sig):
                    consecutive_errors = 0
                    time.sleep(self._poll_interval())
                    continue

                # 抑制期内（刚处理完，右键/发送动画可能还在恢复）：
                # 画面变化只更新基线，不重复处理，防止反馈环路
                if time.monotonic() < self.suppress_until:
                    self.baseline = sig
                    time.sleep(self._poll_interval())
                    continue

                # 画面变化：进入活跃期，快速等待画面稳定
                self.active_until = time.monotonic() + ACTIVE_WINDOW
                stable_sig, status = self._wait_settled()
                if status == "stop":
                    self.running = False
                    break
                if status == "baseline":
                    # 瞬时闪烁后回到基线：基线本身正确，无需更新，直接进入下一轮
                    time.sleep(self._poll_interval())
                    continue
                if stable_sig is None:
                    # 超时仍在动画：按无变化处理
                    time.sleep(self._poll_interval())
                    continue

                # 收集这一波连续消息，合并通读后只回复一次（内部会重新抓取）
                self._handle_batch()
                # 键鼠操作改变了画面：等待重新稳定并重建基线，再设抑制期
                # （不能再用操作前的 stable_sig，否则会立刻被判定为“又有新消息”）
                self.baseline = self._rebuild_baseline()
                self.suppress_until = time.monotonic() + SUPPRESS_SECONDS
                self.active_until = time.monotonic() + ACTIVE_WINDOW
                consecutive_errors = 0
                time.sleep(cfg.POLL_INTERVAL)

            except WindowClosedError:
                logger.info("微信主窗口已被关闭，伴侣退出（不阻止关闭）。")
                self.running = False
            except CompanionError as e:
                consecutive_errors += 1
                stats.record_error("loop")
                backoff = min(30.0, 1.5 * (2 ** min(consecutive_errors - 1, 4)))
                logger.warning("本轮发生可恢复异常（连续第 %d 次）：%s；%.0f 秒后重试",
                               consecutive_errors, e, backoff)
                time.sleep(backoff)
            except Exception:
                consecutive_errors += 1
                stats.record_error("loop")
                backoff = min(30.0, 1.5 * (2 ** min(consecutive_errors - 1, 4)))
                logger.exception("本轮发生未预期异常（连续第 %d 次），已隔离；%.0f 秒后继续",
                                 consecutive_errors, backoff)
                time.sleep(backoff)

    def _wait_settled(self):
        """
        快速稳定确认：连续 2 次签名一致即稳定（先立即采样，再每 SETTLE_POLL 秒）。
        只抓 watch 区域，不整窗拷贝。
        返回 (sig, status)；status: 'ok'/'stop'/'baseline'/'timeout'
        """
        last_sig = None
        t0 = time.monotonic()
        while True:
            if self._stop_requested():
                return None, "stop"
            region = winm.grab_region(self.hwnd, self.watch)
            s = detect.region_signature(region)
            if not self._changed(s):
                return s, "baseline"
            if last_sig is not None and (s == last_sig).all():
                return s, "ok"
            last_sig = s
            if time.monotonic() - t0 >= SETTLE_DEADLINE:
                return None, "timeout"
            time.sleep(SETTLE_POLL)

    def _changed(self, sig):
        return self.baseline is None or not (sig == self.baseline).all()

    def _rebuild_baseline(self):
        """
        处理完一条消息后，等待 watch 区域重新稳定（连续两次签名一致），
        用最新签名作为新基线。这样右键菜单/发送动画关闭后的画面成为基线，
        不会被误判成“又来新消息”。超时则用最后一次签名兜底。
        """
        last = None
        t0 = time.monotonic()
        while time.monotonic() - t0 < SETTLE_DEADLINE:
            if self._stop_requested():
                break
            region = winm.grab_region(self.hwnd, self.watch)
            s = detect.region_signature(region)
            if last is not None and (s == last).all():
                return s
            last = s
            time.sleep(SETTLE_POLL)
        return last if last is not None else self.baseline

    def _maybe_heartbeat(self):
        now = time.monotonic()
        if now - self._last_hb >= HEARTBEAT_INTERVAL:
            self._last_hb = now
            _write_heartbeat()

    def _window_state(self):
        """
        窗口状态：
          'gone'  句柄已销毁（用户关闭了微信）→ 伴侣退出；
          'idle'  最小化或被隐藏 → 本轮不操作；
          'ok'    可见，必要时只做位置纠偏。
        """
        u = winm.user32
        if not u.IsWindow(self.hwnd):
            return "gone"
        if u.IsIconic(self.hwnd):
            return "idle"
        if not u.IsWindowVisible(self.hwnd):
            # 非最小化的隐藏窗口（关闭到托盘）：恢复并前置，避免只显示不激活
            winm.show_and_activate(self.hwnd)
            return "idle"

        # 位置纠偏：只在偏移明显时拉回，不与用户的正常操作抢焦点
        left, top, right, bottom = winm.get_rect(self.hwnd)
        if (abs(left - cfg.WINDOW_LEFT) > 12 or abs(top - cfg.WINDOW_TOP) > 12
                or abs((right - left) - cfg.WINDOW_WIDTH) > 14
                or abs((bottom - top) - cfg.WINDOW_HEIGHT) > 14):
            u.SetWindowPos(
                self.hwnd, 0,
                cfg.WINDOW_LEFT, cfg.WINDOW_TOP,
                cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT, 0x0004,
            )
            time.sleep(0.3)
        return "ok"

    # ---------------- 处理新消息 ----------------
    def _bubble_fingerprint(self, b, img):
        """气泡内容像素指纹：同一条消息滚动后像素不变，可作为跨帧稳定身份。"""
        x0, y0, x1, y1 = b["band"]
        crop = img[max(0, y0):y1, max(0, x0):x1]
        return hashlib.md5(crop.tobytes()).hexdigest()

    def _bubble_text(self, b, img):
        """带缓存的气泡文本：命中像素指纹缓存就直接返回，不再右键。"""
        fp = self._bubble_fingerprint(b, img)
        if fp in self._text_cache:
            return self._text_cache[fp]
        txt = self._read_bubble_text(b, img)
        self._text_cache[fp] = txt
        # 限制缓存大小，避免长时间运行后无限增长
        if len(self._text_cache) > 200:
            for k in list(self._text_cache)[:100]:
                self._text_cache.pop(k, None)
        return txt

    def _read_bubble_text(self, b, img):
        """读取单个气泡文本：右键复制 -> 换点重试 -> OCR 兜底；过滤搜索残留。"""
        point = b["point"]
        txt = actions.read_message_at(self.hwnd, point, cfg.DRY_RUN,
                                      independent=self.independent)

        # 文本气泡首次读空：在气泡内换点（纵向偏移）重试一次
        if not txt and b.get("source") == "fill" and not cfg.DRY_RUN:
            _bx0, by0, _bx1, by1 = b["band"]
            alt = (point[0], min(by1 - 10,
                                  point[1] + max(10, (by1 - by0) // 3)))
            logger.info("首次读图为空，换点 %s 重试", alt)
            txt = actions.read_message_at(self.hwnd, alt, cfg.DRY_RUN,
                                          independent=self.independent)

        # 右键复制仍失败：用 Windows OCR 兜底
        if not txt and cfg.OCR_FALLBACK_ENABLED and not cfg.DRY_RUN:
            txt = wx_ocr.recognize_bubble(img, b["band"], lang=cfg.OCR_LANG)
            if txt:
                logger.info("右键读消息失败，OCR 兜底识别：%s", txt)

        # 过滤搜索流程残留（搜索框里的微信号文本）
        if txt and txt.strip() == cfg.TARGET_WXID:
            return ""
        return (txt or "").strip()

    def _collect_new(self, img):
        """
        识别画面里最早一条尚未处理的新消息（文本身份增量，对滚动稳健），
        把它记入 _seen_texts 并返回 (side, text)；没有新消息返回 None。
        只收集、不回复，供批量合并使用。
        """
        from collections import Counter

        bubbles = detect.find_all_bubbles(img, self.layout)
        if not bubbles:
            return None

        seen = Counter(self._seen_texts)
        running = Counter()
        for b in bubbles:
            key = (b["side"], self._bubble_text(b, img))
            running[key] += 1
            # 当前画面里该消息出现次数 > 已处理次数：这是一条新消息
            if running[key] > seen.get(key, 0):
                self._seen_texts.append(key)
                if len(self._seen_texts) > self._seen_keep:
                    self._seen_texts = self._seen_texts[-self._seen_keep:]
                return key
        return None

    def _gather_batch(self):
        """
        收集这一波所有新消息（不回复）：每轮抓最新画面收集最早一条新消息；
        某轮没有新消息时，继续等待并复查，直到连续 BURST_GATHER_IDLE 秒
        都没有新消息，确认对方这波连发结束。
        返回 (对方文本列表, 自己文本列表)，按出现顺序，已过滤读取失败的空串。
        """
        other_texts = []
        self_texts = []
        collected = 0
        idle = 0.0
        while collected < BURST_MAX and not self._stop_requested():
            img, _ = winm.grab(self.hwnd)
            key = self._collect_new(img)
            if key is not None:
                side, txt = key
                if txt:
                    if side == "self":
                        self_texts.append(txt)
                    else:
                        other_texts.append(txt)
                collected += 1
                idle = 0.0
                continue
            # 暂无新消息：等待后复查，确认对方这波确实发完
            time.sleep(SETTLE_POLL)
            idle += SETTLE_POLL
            if idle >= BURST_GATHER_IDLE:
                break
        return other_texts, self_texts

    def _handle_batch(self):
        """收集一波连续消息，合并通读后只回复一次。"""
        other_texts, self_texts = self._gather_batch()

        # 用户手动/手机端发的消息：保持原有行为，作为用户输入处理
        for txt in self_texts:
            if txt not in self.recent_self and not self._is_duplicate(txt):
                stats.record_self(len(txt))
                self._respond(txt)

        # 对方消息：过滤掉自己刚发的内容（防自我对话），合并后一次回复
        incoming = [t for t in other_texts if t not in self.recent_self]
        if not incoming:
            return
        # 有序去重：连发里完全重复的内容只保留一次
        merged = "\n".join(dict.fromkeys(incoming))
        if self._is_duplicate(merged):
            return
        for t in incoming:
            stats.record_recv(len(t))
        logger.info("本波收到 %d 条消息，合并通读后一次回复", len(incoming))
        self._respond(merged)

    def _is_duplicate(self, txt):
        last_txt, last_t = self.last_user
        if txt == last_txt and time.time() - last_t < 30:
            return True
        self.last_user = (txt, time.time())
        return False

    def _respond(self, user_text):
        if _stop_file_requested() or not _parent_alive():
            return

        # 上一条消息的接口调用仍在进行时，跳过本次，避免两个线程并发读写对话记忆
        if self._api_worker is not None and self._api_worker.is_alive():
            logger.warning("上一条回复仍在生成中，跳过本次消息，避免并发冲突")
            stats.record_reply(False, 0, len(user_text))
            return

        # 接口调用与“真人思考停顿”并行
        result = {}
        t_start = time.monotonic()

        def _call_api():
            try:
                result["answer"] = self.brain.reply(user_text)
            except Exception:
                logger.exception("生成回复时发生异常，已隔离")
                result["answer"] = None

        worker = threading.Thread(target=_call_api, name="reply-api", daemon=True)
        self._api_worker = worker
        worker.start()

        lo, hi = cfg.TYPE_THINK_DELAY
        # 先保证下限停顿，再等接口（最多到上限）
        time.sleep(lo)
        worker.join(timeout=max(0.0, hi - lo))

        answer = result.get("answer")
        if answer is None:
            logger.warning("本次回复失败，跳过（下条消息到来时会继续）")
            stats.record_reply(False, (time.monotonic() - t_start) * 1000)
            return

        # 停顿按回复长度自适应：短回复更快发送，长回复更像真人
        elapsed = time.monotonic() - t_start
        target = min(hi, max(lo, 0.45 + 0.045 * len(answer)))
        if elapsed < target:
            time.sleep(target - elapsed)

        # 停顿/调用期间若收到停止或控制台已关闭，则不发送
        if _stop_file_requested() or not _parent_alive():
            return

        ok = actions.send_message(self.hwnd, self.layout, answer, cfg.DRY_RUN)
        total_ms = (time.monotonic() - t_start) * 1000
        stats.record_reply(ok, total_ms, len(answer))
        if ok:
            self.recent_self.append(answer)
            self.recent_self = self.recent_self[-20:]
            time.sleep(cfg.REPLY_COOLDOWN)

    # ---------------- 停止/清理 ----------------
    def _stop_pressed(self):
        return bool(user32.GetAsyncKeyState(cfg.STOP_VK) & 0x8000)

    def _shutdown(self, original_rect):
        logger.info("正在退出...")
        self.stop_hotkey_listener()
        try:
            if (cfg.RESTORE_WINDOW_ON_EXIT and not cfg.DRY_RUN
                    and winm.user32.IsWindow(self.hwnd)):
                left, top, right, bottom = original_rect
                winm.normalize_window(self.hwnd, left, top, right - left, bottom - top)
        except Exception:
            pass
        # 释放大脑连接池（关闭 HTTP 连接）
        try:
            if self.brain is not None:
                self.brain.close()
        except Exception:
            pass
        _release_lock()
        for path in (STOP_PATH, HEARTBEAT_PATH):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        logger.info("已停止，再见。")


def main():
    # Ctrl+C 优雅退出
    runner = CompanionRunner()

    def _sigint(_s, _f):
        runner.running = False

    signal.signal(signal.SIGINT, _sigint)
    runner.start()
