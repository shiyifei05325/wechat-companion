# -*- coding: utf-8 -*-
"""
本地授权框架（机器绑定 + HMAC 签名许可）：
- 机器码：Windows 机器标识 + CPU + 系统盘卷序列号的哈希；
- 许可证 data/license.dat：绑定机器码的签名 JSON，可含有效期与套餐；
- 无许可证时为「本地试用」状态。

说明：HMAC 密钥内置于代码，属于轻量防君子机制；商业分发时可改为在线激活。
"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import platform
import subprocess

from .config import DATA_DIR

LICENSE_PATH = os.path.join(DATA_DIR, "license.dat")
_SECRET = b"wechat-companion-local-license-v1"


def _machine_guid():
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
        ) as k:
            return winreg.QueryValueEx(k, "MachineGuid")[0]
    except Exception:
        return ""


def _cpu_id():
    try:
        out = subprocess.run(
            ["wmic", "cpu", "get", "ProcessorId"],
            capture_output=True, text=True, timeout=8,
        ).stdout
        return "".join(out.split()[1:])
    except Exception:
        return platform.processor() or ""


def _volume_serial():
    try:
        out = subprocess.run(
            "vol C:", capture_output=True, text=True,
            shell=True, timeout=8,
        ).stdout
        parts = out.strip().split()
        return parts[-1] if parts else ""
    except Exception:
        return ""


def machine_fingerprint():
    raw = "|".join([_machine_guid(), _cpu_id(), _volume_serial()])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def machine_code():
    h = hashlib.sha1(machine_fingerprint().encode("utf-8")).hexdigest().upper()
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def activation_code():
    mac = hmac.new(
        _SECRET, machine_fingerprint().encode("utf-8"), hashlib.sha256
    ).hexdigest().upper()
    return "-".join(mac[i:i + 4] for i in range(0, 16, 4))


def _sign(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    sig = hmac.new(_SECRET, body.encode("utf-8"), hashlib.sha256).hexdigest()
    blob = json.dumps({"payload": payload, "sig": sig}, ensure_ascii=False)
    return base64.b64encode(blob.encode("utf-8")).decode()


def _verify(blob: str):
    data = json.loads(base64.b64decode(blob).decode("utf-8"))
    payload = data["payload"]
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    expect = hmac.new(_SECRET, body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, data["sig"]):
        return None
    return payload


def write_license(expires: str = None, plan: str = "local"):
    """生成绑定当前机器的许可证（管理工具/激活成功时调用）"""
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {
        "machine": machine_fingerprint(),
        "machine_code": machine_code(),
        "issued": dt.date.today().isoformat(),
        "expires": expires,
        "plan": plan,
    }
    with open(LICENSE_PATH, "w", encoding="utf-8") as f:
        f.write(_sign(payload))
    return payload


def activate(code: str) -> bool:
    """用激活码激活（激活码与机器绑定）"""
    if code.strip().upper() != activation_code():
        return False
    write_license()
    return True


def status():
    """返回授权状态：trial / licensed / invalid / wrong_machine / expired"""
    base = {
        "machine_code": machine_code(),
        "activation_code": activation_code(),
        "valid": False,
        "state": "trial",
        "plan": "trial",
        "expires": None,
        "issued": None,
    }
    if not os.path.exists(LICENSE_PATH):
        return base
    try:
        with open(LICENSE_PATH, "r", encoding="utf-8") as f:
            payload = _verify(f.read().strip())
    except Exception:
        base["state"] = "invalid"
        return base
    if not payload:
        base["state"] = "invalid"
        return base
    if payload.get("machine") != machine_fingerprint():
        base["state"] = "wrong_machine"
        base["plan"] = payload.get("plan", "local")
        return base
    if payload.get("expires"):
        try:
            if dt.date.fromisoformat(payload["expires"]) < dt.date.today():
                base.update(state="expired", plan=payload.get("plan", "local"),
                            expires=payload.get("expires"))
                return base
        except Exception:
            pass
    base.update(
        valid=True,
        state="licensed",
        plan=payload.get("plan", "local"),
        expires=payload.get("expires"),
        issued=payload.get("issued"),
    )
    return base
