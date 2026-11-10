# -*- coding: utf-8 -*-
"""
微信虚拟伴侣 · 后端控制台服务器

启动：python launcher.py（环境检测通过后自动启动本服务器）
功能：
  - 网页可视化编辑：指定联系人、性格人设、DeepSeek、节奏、安全开关
  - 配置保存到 local_config.json（已被 .gitignore 排除，不改写源码）
  - 启动 / 停止 / 重启伴侣进程（单实例保护）
  - 实时查看运行日志、健康检查

本地专用（强制）：
  - 仅绑定回环地址 127.0.0.1，不监听任何外部网卡；
  - 对来源地址非回环的请求一律拒绝（403）。
"""
import atexit
import ctypes
import datetime
import importlib
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser

from flask import Flask, g, jsonify, request, send_file

# 本文件位于 <根>/control/server.py，根目录需上溯一级；
# 打包后：根目录为 exe 所在目录，静态资源在解包目录（sys._MEIPASS）
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    _BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
    STATIC_DIR = os.path.join(_BUNDLE_DIR, "control", "static")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    STATIC_DIR = os.path.join(BASE_DIR, "control", "static")
LOG_DIR = os.path.join(BASE_DIR, "logs")
OVERRIDE_PATH = os.path.join(BASE_DIR, "local_config.json")
RUN_PATH = os.path.join(BASE_DIR, "run.py")
PID_PATH = os.path.join(BASE_DIR, "companion.pid")
LOCK_PATH = os.path.join(BASE_DIR, "companion.lock")
STOP_PATH = os.path.join(BASE_DIR, "companion.stop")
HEARTBEAT_PATH = os.path.join(BASE_DIR, "companion.heartbeat")

# 应用包位于标准 src 布局
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from wechat_companion import __version__  # noqa: E402
from wechat_companion.logging_setup import configure_logging, get_logger  # noqa: E402

configure_logging(LOG_DIR)
logger = get_logger("control_server")
SERVER_STARTED = time.monotonic()

# 仅本地运行：绑定地址与允许的来源地址
HOST = "127.0.0.1"
LOOPBACK_ADDRS = {"127.0.0.1", "::1"}


def _lock_pid():
    """锁文件中的 pid；无法读取返回 None"""
    try:
        with open(LOCK_PATH, "r", encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except Exception:
        return None


def _is_live_companion(pid):
    """pid 是否对应一个存活的伴侣进程（开发态 run.py / 打包态 --companion）"""
    if not pid:
        return False
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        cmdline = " ".join(psutil.Process(pid).cmdline())
        return "run.py" in cmdline or "--companion" in cmdline
    except Exception:
        return False


# 控制台启动时清理上一轮残留：过期锁、遗留停止标记（否则新伴侣会被立即停止）
if not _is_live_companion(_lock_pid()) and os.path.exists(LOCK_PATH):
    try:
        os.remove(LOCK_PATH)
    except Exception:
        pass
if os.path.exists(STOP_PATH):
    try:
        os.remove(STOP_PATH)
    except Exception:
        pass

app = Flask(__name__, static_folder=None)

# 配置字段定义（含校验类型）：str / int / float / bool / float2
FIELD_TYPES = {
    "TARGET_WXID": "str",
    "TARGET_NAME": "str",
    "COMPANION_NAME": "str",
    "SYSTEM_PROMPT": "str",
    "DEEPSEEK_API_KEY": "str",
    "DEEPSEEK_MODEL": "str",
    "DEEPSEEK_TEMPERATURE": "float",
    "KEEP_ROUNDS": "int",
    "POLL_INTERVAL": "float",
    "IDLE_POLL_INTERVAL": "float",
    "TYPE_THINK_DELAY": "float2",
    "REPLY_COOLDOWN": "float",
    "DRY_RUN": "bool",
    "RESTORE_WINDOW_ON_EXIT": "bool",
    "AUTO_RESTART_ON_CRASH": "bool",
}


def _coerce(name, raw):
    """按字段类型把前端值转换为可写入 JSON 的 Python 值；失败抛 ValueError"""
    t = FIELD_TYPES[name]
    if t == "str":
        return str(raw if raw is not None else "").strip()
    if t == "bool":
        return bool(raw)
    if t == "int":
        return int(float(raw))
    if t == "float":
        return float(raw)
    if t == "float2":
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise ValueError(f"{name} 需要两个数值")
        a, b = float(raw[0]), float(raw[1])
        if a < 0 or b < 0 or a > b:
            raise ValueError(f"{name} 数值范围不合法")
        return [a, b]
    raise ValueError(f"未知字段 {name}")


def _effective_config():
    """重新加载 config 模块，返回当前生效的配置值"""
    from wechat_companion import config
    importlib.reload(config)
    out = {k: getattr(config, k) for k in FIELD_TYPES}
    # tuple 转 list，方便 JSON 序列化
    if isinstance(out["TYPE_THINK_DELAY"], tuple):
        out["TYPE_THINK_DELAY"] = list(out["TYPE_THINK_DELAY"])
    return out


# ---------------- 配置持久化（local_config.json） ----------------
SECRET_FIELDS = {"DEEPSEEK_API_KEY"}


def _read_overrides():
    """读取已有覆盖配置；文件缺失或损坏时返回空字典"""
    try:
        with open(OVERRIDE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_overrides(values):
    """
    把配置原子写入 local_config.json（不含 API 密钥）。
    该文件已被 .gitignore 排除：保存配置不会改写源码，也不会进提交记录。
    保留用户手工添加的扩展字段（如 DEEPSEEK_BASE_URL），但剔除密钥。
    """
    data = {k: v for k, v in _read_overrides().items() if k not in SECRET_FIELDS}
    data.update({k: values[k] for k in FIELD_TYPES if k not in SECRET_FIELDS})
    tmp = OVERRIDE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, OVERRIDE_PATH)


# ---------------- 进程管理 ----------------
CREATE_NO_WINDOW = 0x08000000
VK_F9 = 0x78
KEYEVENTF_KEYUP = 0x0002


class CompanionProcess:
    def __init__(self):
        self.proc = None
        self.log_fh = None

    def _console_log_path(self):
        day = datetime.datetime.now().strftime("%Y%m%d")
        return os.path.join(LOG_DIR, f"console_{day}.log")

    def is_running(self):
        if self.proc is not None and self.proc.poll() is None:
            return True
        # 服务器重启后，尝试通过 pid 文件认领仍在运行的伴侣
        pid = self._read_pid()
        if pid and self._pid_is_companion(pid):
            return True
        return False

    def _pid_is_companion(self, pid):
        try:
            import psutil
            if not psutil.pid_exists(pid):
                return False
            cmdline = " ".join(psutil.Process(pid).cmdline())
            return "run.py" in cmdline or "--companion" in cmdline
        except Exception:
            return False

    def _read_pid(self):
        try:
            with open(PID_PATH, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return None

    def start(self):
        if self.is_running():
            return True, "伴侣已在运行"
        # 单实例保护：其他控制台/手动启动的伴侣仍在运行时，不重复拉起
        if _is_live_companion(_lock_pid()):
            return False, "已有一个伴侣在运行（单实例限制），请先停止再启动"
        os.makedirs(LOG_DIR, exist_ok=True)
        log_path = self._console_log_path()
        self.log_fh = open(log_path, "a", encoding="utf-8")
        self.log_fh.write(
            f"\n===== 控制台启动于 {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n"
        )
        self.log_fh.flush()
        # 让伴侣知道由哪个控制台启动；控制台关闭后伴侣自动停止，不留隐藏进程
        child_env = os.environ.copy()
        child_env["COMPANION_PARENT_PID"] = str(os.getpid())
        # 打包态：exe --companion；开发态：python -u run.py
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--companion"]
        else:
            cmd = [sys.executable, "-u", RUN_PATH]
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=BASE_DIR,
                env=child_env,
                stdout=self.log_fh,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as e:
            self.log_fh.close()
            return False, f"启动失败：{e}"
        with open(PID_PATH, "w", encoding="utf-8") as f:
            f.write(str(self.proc.pid))
        # 早期崩溃检测
        try:
            rc = self.proc.wait(time=1.8)
            return False, f"伴侣启动后很快退出（退出码 {rc}），请查看日志"
        except subprocess.TimeoutExpired:
            return True, "已启动"

    def stop(self):
        pid = None
        if self.proc is not None and self.proc.poll() is None:
            pid = self.proc.pid
        else:
            p = self._read_pid()
            if p and self._pid_is_companion(p):
                pid = p
            elif _is_live_companion(_lock_pid()):
                pid = _lock_pid()
        if not pid:
            self._cleanup()
            return True, "伴侣当前未运行"

        # 1) 写入停止标记：伴侣主循环/回复前检查到立即优雅退出（会恢复窗口）
        try:
            with open(STOP_PATH, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

        # 2) F9 热键兜底（按住约 1.5 秒）
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_F9, 0, 0, 0)
        for _ in range(3):
            if not _is_live_companion(pid):
                break
            ctypes.windll.kernel32.Sleep(500)
        user32.keybd_event(VK_F9, 0, KEYEVENTF_KEYUP, 0)

        # 3) 等待优雅退出（最多 8 秒）
        for _ in range(16):
            if not _is_live_companion(pid):
                self._cleanup()
                return True, "已优雅停止"
            ctypes.windll.kernel32.Sleep(500)

        # 4) 兜底：优先用本进程持有的子进程句柄终止，其次 taskkill 进程树
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                pass
        if _is_live_companion(pid):
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, timeout=10,
                )
            except Exception:
                pass
        self._cleanup()
        return True, "优雅停止超时，已强制结束（窗口位置可能未恢复）"

    def force_stop(self):
        """不等待优雅退出，直接终止伴侣（控制台关闭/atexit 场景使用）"""
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=3)
            except Exception:
                pass
        pid = self._read_pid()
        if pid and self._pid_is_companion(pid):
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, timeout=8,
                )
            except Exception:
                pass
        self._cleanup()

    def _cleanup(self):
        for path in (PID_PATH, STOP_PATH, LOCK_PATH):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        try:
            if self.log_fh and not self.log_fh.closed:
                self.log_fh.close()
        except Exception:
            pass


companion_proc = CompanionProcess()


def _exit_cleanup():
    """控制台进程退出时尽力清掉子进程，杜绝隐藏孤儿"""
    try:
        if companion_proc.is_running():
            companion_proc.force_stop()
    except Exception:
        pass


atexit.register(_exit_cleanup)


# ---------------- 看门狗：崩溃/卡死监测（可选自动重启） ----------------
class Watchdog:
    """
    监测伴侣进程：
    - 非手动停止却退出 → 标记 crashed（默认仅提示，不自动重启）；
    - 进程在但心跳超过 20 秒未更新 → 判定卡死；
    - AUTO_RESTART_ON_CRASH 开启时自动重启（冷却 60s，每小时最多 5 次）。
    """

    HEARTBEAT_STALE = 20.0
    RESTART_COOLDOWN = 60.0
    MAX_RESTARTS_PER_HOUR = 5

    def __init__(self):
        self.was_running = False
        self.manual_stop = False
        self.crashed = False
        self.message = ""
        self._restarts = []
        self._last_restart = 0.0

    def _auto_enabled(self):
        try:
            return bool(_effective_config().get("AUTO_RESTART_ON_CRASH"))
        except Exception:
            return False

    def _can_restart(self):
        now = time.monotonic()
        self._restarts = [t for t in self._restarts if now - t < 3600]
        if (now - self._last_restart < self.RESTART_COOLDOWN
                or len(self._restarts) >= self.MAX_RESTARTS_PER_HOUR):
            return False
        return True

    def _do_restart(self):
        if not self._can_restart():
            return
        self._last_restart = time.monotonic()
        self._restarts.append(self._last_restart)
        logger.warning("看门狗自动重启伴侣")
        self.manual_stop = False
        companion_proc.stop()
        companion_proc.start()

    def check(self):
        running = companion_proc.is_running()
        if self.was_running and not running and not self.manual_stop:
            self.crashed = True
            self.message = "伴侣异常退出（非手动停止）"
            logger.warning(self.message)
            if self._auto_enabled():
                self._do_restart()
        if running:
            try:
                age = time.time() - os.path.getmtime(HEARTBEAT_PATH)
            except OSError:
                age = 0.0
            if age > self.HEARTBEAT_STALE:
                self.crashed = True
                self.message = f"伴侣心跳已 {age:.0f} 秒未更新，疑似卡死"
                logger.warning(self.message)
                if self._auto_enabled():
                    self._do_restart()
            else:
                self.crashed = False
                self.message = ""
        self.was_running = running

    def run_forever(self):
        while True:
            time.sleep(5)
            try:
                self.check()
            except Exception:
                pass


watchdog = Watchdog()
_wd_thread = threading.Thread(target=watchdog.run_forever, name="watchdog",
                              daemon=True)
_wd_thread.start()


# ---------------- 中间件：本地专用 / 访问日志 ----------------
@app.before_request
def _before_request():
    # 仅允许回环来源：任何非本机地址直接拒绝
    if request.remote_addr not in LOOPBACK_ADDRS:
        logger.warning("拒绝非本机请求：%s %s 来源 %s",
                       request.method, request.path, request.remote_addr)
        return jsonify(error="仅允许本机访问"), 403
    g._started = time.monotonic()


@app.after_request
def _after_request(resp):
    started = getattr(g, "_started", None)
    elapsed = (time.monotonic() - started) * 1000 if started else 0.0
    logger.info("%s %s -> %s (%.0fms)",
                request.method, request.path, resp.status_code, elapsed)
    return resp


@app.errorhandler(400)
def _bad_request(_e):
    return jsonify(error="请求参数有误"), 400


@app.errorhandler(404)
def _not_found(_e):
    return jsonify(error="资源不存在"), 404


@app.errorhandler(405)
def _method_not_allowed(_e):
    return jsonify(error="不支持该请求方法"), 405


@app.errorhandler(Exception)
def _unhandled(e):
    # 业务代码未预期的异常统一返回 JSON，避免向前端暴露 HTML 调试页
    logger.exception("未处理异常：%s", e)
    return jsonify(error=f"服务器内部错误：{e}"), 500


@app.route("/")
def index():
    return send_file(os.path.join(STATIC_DIR, "index.html"))


@app.route("/api/health", methods=["GET"])
def api_health():
    """健康检查：版本、pid、已运行时长、伴侣状态、本地绑定信息"""
    return jsonify(
        ok=True,
        version=__version__,
        pid=os.getpid(),
        host=HOST,
        local_only=True,
        uptime=round(time.monotonic() - SERVER_STARTED, 1),
        running=companion_proc.is_running(),
    )


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(_effective_config())


@app.route("/api/config", methods=["POST"])
def save_config():
    body = request.get_json(silent=True) or {}
    # 以当前生效值为底（含环境变量/JSON 覆盖），叠加本次提交
    values = _effective_config()
    try:
        for name, raw in body.items():
            if name not in FIELD_TYPES:
                continue
            values[name] = _coerce(name, raw)
    except (ValueError, TypeError) as e:
        return jsonify(error=f"配置校验失败：{e}"), 400
    try:
        _persist_values(values)
    except Exception as e:
        return jsonify(error=f"保存配置失败：{e}"), 500
    # 回读代码文件校验
    after = _effective_config()
    for k in FIELD_TYPES:
        if after[k] != values[k]:
            return jsonify(error=f"配置保存后校验不一致：{k}"), 500
    return jsonify(ok=True, config=after)


def _persist_values(values):
    """密钥写入 DPAPI 保护存储，其余配置写入 local_config.json"""
    from wechat_companion import secret_store
    secret_store.save_api_key(values.get("DEEPSEEK_API_KEY", ""))
    _write_overrides(values)


@app.route("/api/start", methods=["POST"])
def api_start():
    watchdog.manual_stop = False
    ok, msg = companion_proc.start()
    return jsonify(ok=ok, message=msg, running=companion_proc.is_running()), (200 if ok else 500)


@app.route("/api/stop", methods=["POST"])
def api_stop():
    watchdog.manual_stop = True
    ok, msg = companion_proc.stop()
    return jsonify(ok=ok, message=msg, running=companion_proc.is_running())


@app.route("/api/restart", methods=["POST"])
def api_restart():
    watchdog.manual_stop = False
    companion_proc.stop()
    ok, msg = companion_proc.start()
    return jsonify(ok=ok, message=msg, running=companion_proc.is_running()), (200 if ok else 500)


@app.route("/api/status", methods=["GET"])
def api_status():
    try:
        hb_age = round(time.time() - os.path.getmtime(HEARTBEAT_PATH), 1)
    except OSError:
        hb_age = None
    return jsonify(
        running=companion_proc.is_running(),
        dry_run=_effective_config().get("DRY_RUN"),
        crashed=watchdog.crashed,
        crash_message=watchdog.message,
        heartbeat_age=hb_age,
        local_only=True,
    )


@app.route("/api/logs", methods=["GET"])
def api_logs():
    """增量读取控制台日志：?offset=字节偏移，返回新增内容与新偏移"""
    offset = int(request.args.get("offset", 0))
    path = companion_proc._console_log_path()
    if not os.path.exists(path):
        # 控制台日志不存在时，退回当天的对话日志
        day = datetime.datetime.now().strftime("%Y%m%d")
        alt = os.path.join(LOG_DIR, f"companion_{day}.log")
        path = alt if os.path.exists(alt) else None
    if not path:
        return jsonify(data="", offset=0, size=0)
    size = os.path.getsize(path)
    if offset > size:
        offset = 0  # 文件被重建/轮转
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read(200_000)
    text = chunk.decode("utf-8", errors="replace")
    return jsonify(data=text, offset=size, size=size)


def _open_browser(url):
    webbrowser.open(url)


# ---------------- 运行统计 ----------------
@app.route("/api/stats", methods=["GET"])
def api_stats():
    from wechat_companion import stats
    return jsonify(stats.summary())


@app.route("/api/stats/reset", methods=["POST"])
def api_stats_reset():
    from wechat_companion import stats
    stats.reset()
    return jsonify(ok=True)


# ---------------- 授权 ----------------
@app.route("/api/license", methods=["GET"])
def api_license():
    from wechat_companion import license as lic
    return jsonify(lic.status())


@app.route("/api/license/activate", methods=["POST"])
def api_license_activate():
    from wechat_companion import license as lic
    body = request.get_json(silent=True) or {}
    code = str(body.get("code", ""))
    if not code.strip():
        return jsonify(ok=False, error="请输入激活码"), 400
    if lic.activate(code):
        return jsonify(ok=True, license=lic.status())
    return jsonify(ok=False, error="激活码无效（需与本机机器码绑定）"), 400


# ---------------- 配置备份 / 恢复 ----------------
@app.route("/api/config/export", methods=["GET"])
def api_config_export():
    import io
    data = json.dumps(_effective_config(), ensure_ascii=False, indent=2)
    day = datetime.datetime.now().strftime("%Y%m%d")
    return send_file(
        io.BytesIO(data.encode("utf-8")),
        as_attachment=True,
        download_name=f"wechat_companion_config_{day}.json",
        mimetype="application/json",
    )


@app.route("/api/config/import", methods=["POST"])
def api_config_import():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="需要提交配置 JSON 对象"), 400
    values = _effective_config()
    try:
        for name, raw in body.items():
            if name in FIELD_TYPES:
                values[name] = _coerce(name, raw)
    except (ValueError, TypeError) as e:
        return jsonify(error=f"配置校验失败：{e}"), 400
    try:
        _persist_values(values)
    except Exception as e:
        return jsonify(error=f"保存配置失败：{e}"), 500
    return jsonify(ok=True, config=_effective_config())


def main():
    port = 5005
    url = f"http://{HOST}:{port}"
    logger.info("=" * 50)
    logger.info("微信虚拟伴侣 · 后端控制台 v%s", __version__)
    logger.info("访问地址：%s（仅本机可访问）", url)
    logger.info("请在控制台页面内手动点击「启动伴侣」；停止、重启也都在控制台操作")
    logger.info("关闭本窗口：控制台停止，伴侣也会随之自动退出（不留后台进程）")
    logger.info("=" * 50)
    threading.Timer(1.2, _open_browser, args=(url,)).start()
    app.run(host=HOST, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
