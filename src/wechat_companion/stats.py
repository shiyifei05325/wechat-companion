# -*- coding: utf-8 -*-
"""
运行统计（SQLite，本地 data/runtime.db）：
记录收发消息、回复成败、耗时与错误，供控制台数据看板展示，
并以 WAL 模式支持伴侣进程与控制台并发访问。
"""
import datetime as dt
import os
import sqlite3
import threading

from .config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "runtime.db")
_lock = threading.Lock()


def _connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return conn


def init_db():
    with _lock, _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,
                latency_ms INTEGER DEFAULT 0,
                text_len INTEGER DEFAULT 0
            )"""
        )


def _record(kind: str, latency_ms: int = 0, text_len: int = 0) -> None:
    try:
        init_db()
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT INTO events(ts,kind,latency_ms,text_len) VALUES(?,?,?,?)",
                (dt.datetime.now().isoformat(timespec="seconds"),
                 kind, int(latency_ms), int(text_len)),
            )
    except Exception:
        # 统计失败永远不影响主流程
        pass


def record_recv(text_len: int = 0) -> None:
    _record("recv", text_len=text_len)


def record_self(text_len: int = 0) -> None:
    _record("self", text_len=text_len)


def record_reply(ok: bool, latency_ms: float = 0, text_len: int = 0) -> None:
    _record("reply_ok" if ok else "reply_fail", latency_ms, text_len)


def record_error(where: str = "") -> None:
    _record("error", text_len=len(where))


def _counts(conn, since: str = None):
    q = "SELECT kind, COUNT(*) FROM events"
    args = ()
    if since:
        q += " WHERE ts >= ?"
        args = (since,)
    q += " GROUP BY kind"
    return {r[0]: r[1] for r in conn.execute(q, args)}


def _avg_latency(conn, since: str = None):
    q = "SELECT AVG(latency_ms) FROM events WHERE kind='reply_ok' AND latency_ms>0"
    if since:
        q += " AND ts >= ?"
    row = conn.execute(q, (since,) if since else ()).fetchone()
    return round(row[0]) if row and row[0] else 0


def _success_rate(c):
    total = c.get("reply_ok", 0) + c.get("reply_fail", 0)
    return round(100 * c.get("reply_ok", 0) / total, 1) if total else 100.0


def summary():
    """控制台看板数据：今日/累计计数 + 近 7 天序列"""
    init_db()
    today = dt.datetime.now().replace(hour=0, minute=0, second=0).isoformat()
    with _connect() as conn:
        allc = _counts(conn)
        todayc = _counts(conn, today)
        avg_all = _avg_latency(conn)
        avg_today = _avg_latency(conn, today)
        series = []
        for i in range(6, -1, -1):
            day = (dt.datetime.now() - dt.timedelta(days=i)).date()
            start = dt.datetime.combine(day, dt.time()).isoformat()
            end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time()).isoformat()
            r = conn.execute(
                "SELECT SUM(kind='recv'), SUM(kind='reply_ok') "
                "FROM events WHERE ts>=? AND ts<?",
                (start, end),
            ).fetchone()
            series.append({"date": day.strftime("%m-%d"),
                           "recv": r[0] or 0, "reply": r[1] or 0})
    return {
        "today": {
            "recv": todayc.get("recv", 0),
            "self": todayc.get("self", 0),
            "reply_ok": todayc.get("reply_ok", 0),
            "reply_fail": todayc.get("reply_fail", 0),
            "errors": todayc.get("error", 0),
            "avg_latency": avg_today,
            "success_rate": _success_rate(todayc),
        },
        "all": {
            "recv": allc.get("recv", 0),
            "self": allc.get("self", 0),
            "reply_ok": allc.get("reply_ok", 0),
            "reply_fail": allc.get("reply_fail", 0),
            "errors": allc.get("error", 0),
            "avg_latency": avg_all,
            "success_rate": _success_rate(allc),
        },
        "series": series,
    }


def reset() -> None:
    """清空统计数据"""
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM events")
