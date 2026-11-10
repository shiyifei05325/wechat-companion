# -*- coding: utf-8 -*-
"""
DeepSeek 虚拟伴侣大脑：人设 + 多轮上下文记忆 + 调用接口
"""
import datetime
import os
import random
import time

import requests

from .logging_setup import get_logger

logger = get_logger(__name__)


class DeepSeekCompanion:
    def __init__(self, cfg):
        self.cfg = cfg
        if not cfg.DEEPSEEK_API_KEY:
            raise RuntimeError(
                "未配置 DEEPSEEK_API_KEY：请在 config.py 中填写，或用环境变量 DEEPSEEK_API_KEY 覆盖。"
            )
        self.url = cfg.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"
        # 连接复用：同一 Session 内保持 TCP/TLS 长连接，省去每次握手开销
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "Authorization": f"Bearer {cfg.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        })
        # 对话历史：[{"role": "user"/"assistant", "content": ...}]
        self.history = []
        self._log_day = None
        self.log_path = None
        self._init_log()

    def close(self):
        """释放连接池"""
        try:
            self.session.close()
        except Exception:
            pass

    def prewarm(self):
        """
        预热连接：对服务根地址发起一次轻量请求，完成 DNS/TCP/TLS 握手并
        放入连接池，首条消息不再承担握手延迟（失败不影响运行）。
        """
        try:
            self.session.get(self.cfg.DEEPSEEK_BASE_URL, timeout=5)
            logger.info("接口连接已预热")
        except Exception:
            logger.debug("连接预热未完成（首条消息时自动重试）")

    # ---------------- 对话 ----------------
    def reply(self, user_text):
        """
        收到用户消息，返回伴侣回复文本。
        多轮上下文自动携带；全部重试失败时返回 None（并撤回该条用户消息）。
        """
        self.history.append({"role": "user", "content": user_text})
        self._trim_history()

        messages = [{"role": "system", "content": self.cfg.SYSTEM_PROMPT}] + self.history

        payload = {
            "model": self.cfg.DEEPSEEK_MODEL,
            "messages": messages,
            "stream": False,
            "temperature": self.cfg.DEEPSEEK_TEMPERATURE,
        }

        data = None
        answer = None
        last_err = ""
        total_attempts = self.cfg.DEEPSEEK_MAX_RETRIES + 1
        for attempt in range(total_attempts):
            try:
                t0 = time.monotonic()
                r = self.session.post(
                    self.url,
                    json=payload,
                    timeout=self.cfg.DEEPSEEK_TIMEOUT,
                )
                api_ms = (time.monotonic() - t0) * 1000
                if r.status_code == 200:
                    data = r.json()
                    content = (
                        (data.get("choices") or [{}])[0]
                        .get("message", {})
                        .get("content")
                        or ""
                    )
                    answer = content.strip()
                    if answer:
                        logger.info("DeepSeek 响应 %.0fms（第 %d 次尝试）",
                                    api_ms, attempt + 1)
                        break
                    # 偶发空内容：按失败处理，继续重试
                    last_err = "接口返回空内容"
                    logger.warning("DeepSeek 返回空内容（第 %d 次，%.0fms），将重试",
                                   attempt + 1, api_ms)
                    data = None
                else:
                    last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                    logger.warning("DeepSeek 返回非 200（第 %d 次，%.0fms）：%s",
                                   attempt + 1, api_ms, last_err)
            except requests.RequestException as e:
                last_err = str(e)
                logger.warning("DeepSeek 请求异常（第 %d 次）：%s", attempt + 1, e)
            if attempt < total_attempts - 1:
                # 指数退避 + 抖动，避免故障时密集重试
                delay = min(8.0, 0.8 * (2 ** attempt)) + random.uniform(0, 0.4)
                time.sleep(delay)

        if data is None or answer is None:
            logger.error("DeepSeek 调用失败：%s", last_err)
            # 从历史中撤掉这条用户消息，等下次消息到来时重新进入上下文
            self.history.pop()
            return None

        usage = data.get("usage", {})
        self.history.append({"role": "assistant", "content": answer})
        self._trim_history()

        self._log(user_text, answer, usage)
        return answer

    def _trim_history(self):
        """只保留最近 KEEP_ROUNDS*2 条消息"""
        keep = self.cfg.KEEP_ROUNDS * 2
        if len(self.history) > keep:
            self.history = self.history[-keep:]

    # ---------------- 对话记录（业务日志） ----------------
    def _init_log(self):
        os.makedirs(self.cfg.LOG_DIR, exist_ok=True)
        day = datetime.datetime.now().strftime("%Y%m%d")
        self._log_day = day
        self.log_path = os.path.join(self.cfg.LOG_DIR, f"companion_{day}.log")

    def _roll_log_if_needed(self):
        """跨零点运行时长驻进程，日志按当天日期滚动"""
        day = datetime.datetime.now().strftime("%Y%m%d")
        if day != self._log_day:
            self._log_day = day
            self.log_path = os.path.join(self.cfg.LOG_DIR, f"companion_{day}.log")

    def _log(self, user_text, answer, usage):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = (
            f"[{ts}] 用户: {user_text}\n"
            f"[{ts}] {self.cfg.COMPANION_NAME}: {answer}\n"
            f"        tokens={usage.get('total_tokens')}\n"
        )
        self._roll_log_if_needed()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        logger.info("用户: %s", user_text)
        logger.info("%s: %s", self.cfg.COMPANION_NAME, answer)
