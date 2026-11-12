# -*- coding: utf-8 -*-
"""
会话历史持久化（SQLite，本地 data/runtime.db）。

把对话历史（user/assistant 消息）落库，进程重启后自动恢复上下文，
避免重启丢失多轮记忆（参考 chatgpt-on-wechat 的会话持久化设计）。

设计原则：
- 运行期内存中的 brain.history 仍是权威来源，本模块只做“尽力而为”的镜像；
- 任何读写异常都被吞掉并返回安全默认值，绝不影响主对话流程。
"""
import sqlite3
import threading

from .config import DATA_DIR
from .stats import DB_PATH

_lock = threading.Lock()


def _connect():
    import os
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return conn


def _ensure_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chat_history(
            seq INTEGER PRIMARY KEY,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )"""
    )


def save_history(history):
    """
    用当前历史整体覆盖落库（同事务内清空再写入，保证顺序一致）。
    失败静默：调用方无需处理。
    """
    if not isinstance(history, (list, tuple)):
        return
    try:
        with _lock, _connect() as conn:
            _ensure_table(conn)
            conn.execute("DELETE FROM chat_history")
            conn.executemany(
                "INSERT INTO chat_history(seq, role, content) VALUES(?, ?, ?)",
                [(i, str(m.get("role", "")), str(m.get("content", "")))
                 for i, m in enumerate(history)
                 if m.get("role") in ("user", "assistant")],
            )
            conn.commit()
    except Exception:
        pass


def load_history(limit=200):
    """按顺序读取最近落库的历史；无数据或异常时返回空列表。"""
    try:
        with _lock, _connect() as conn:
            _ensure_table(conn)
            rows = conn.execute(
                "SELECT role, content FROM chat_history ORDER BY seq DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    except Exception:
        return []


def clear_history():
    """清空持久化的历史（保留表结构）。"""
    try:
        with _lock, _connect() as conn:
            _ensure_table(conn)
            conn.execute("DELETE FROM chat_history")
            conn.commit()
    except Exception:
        pass
