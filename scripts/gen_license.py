# -*- coding: utf-8 -*-
"""
生成绑定当前机器的许可证（管理工具）：
    C:\\Python313\\python.exe scripts/gen_license.py
    C:\\Python313\\python.exe scripts/gen_license.py --days 365 --plan standard

生成后写入 data/license.dat，控制台「授权与关于」将显示已授权。
商业分发时：让用户提供机器码，用对应私钥/在线服务生成激活码或许可证。
"""
import argparse
import os
import sys

# 允许直接运行：把 src 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from wechat_companion import license as lic  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="生成本机许可证")
    parser.add_argument("--days", type=int, default=0,
                        help="有效天数（0 表示永久）")
    parser.add_argument("--plan", type=str, default="local",
                        help="套餐名称（如 local / standard / pro）")
    args = parser.parse_args()

    import datetime as dt
    expires = None
    if args.days > 0:
        expires = (dt.date.today() + dt.timedelta(days=args.days)).isoformat()

    print("本机机器码：", lic.machine_code())
    payload = lic.write_license(expires=expires, plan=args.plan)
    print("许可证已生成：", lic.LICENSE_PATH)
    print("套餐：", payload["plan"], "| 到期：", payload["expires"] or "永久")
    print("当前授权状态：", lic.status()["state"])


if __name__ == "__main__":
    main()
