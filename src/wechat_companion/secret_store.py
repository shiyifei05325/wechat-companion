# -*- coding: utf-8 -*-
"""
敏感信息本地保护（Windows DPAPI）：
- 控制台保存的 API 密钥以当前 Windows 用户绑定的密文落盘（data/.apikey），
  其他用户、其他机器无法解密；源码中不再明文烘焙密钥；
- 非 Windows 或 DPAPI 不可用时降级为带标记的明文（仅作兜底）。
"""
import ctypes
import ctypes.wintypes as wt
import os

from .config import DATA_DIR

SECRET_PATH = os.path.join(DATA_DIR, ".apikey")


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wt.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _crypt_protect(data: bytes) -> bytes:
    blob_in = _DATA_BLOB(
        len(data), ctypes.cast(ctypes.c_char_p(data), ctypes.POINTER(ctypes.c_char))
    )
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _crypt_unprotect(blob: bytes) -> bytes:
    blob_in = _DATA_BLOB(
        len(blob), ctypes.cast(ctypes.c_char_p(blob), ctypes.POINTER(ctypes.c_char))
    )
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def save_api_key(key: str) -> None:
    """保存（DPAPI 加密）；传入空串则删除已存密钥"""
    if not key:
        try:
            if os.path.exists(SECRET_PATH):
                os.remove(SECRET_PATH)
        except OSError:
            pass
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        raw = _crypt_protect(key.encode("utf-8"))
    except Exception:
        raw = b"PLAIN:" + key.encode("utf-8")
    tmp = SECRET_PATH + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, SECRET_PATH)


def load_api_key() -> str:
    """读取并解密；不存在/无法解密时返回空串"""
    if not os.path.exists(SECRET_PATH):
        return ""
    with open(SECRET_PATH, "rb") as f:
        raw = f.read()
    if raw.startswith(b"PLAIN:"):
        return raw[6:].decode("utf-8", "replace")
    try:
        return _crypt_unprotect(raw).decode("utf-8", "replace")
    except Exception:
        return ""
