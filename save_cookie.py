#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把浏览器里的 iKuuu Cookie 保存到 config.json，并先验证是否有效。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

import checkin

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"


def main() -> int:
    print("=" * 56)
    print("iKuuu Cookie 保存向导")
    print("=" * 56)
    print("请先在浏览器登录 https://ikuuu.org/auth/login")
    print("完成滑块验证后，从开发者工具 Network 的 /user 请求头中复制 Cookie。")
    print("")

    try:
        config = checkin.load_config()
    except FileNotFoundError:
        config = {
            "account": "",
            "domain": checkin.DEFAULT_DOMAINS[0],
            "cookie": "",
            "timeout": 20,
        }
    except Exception as exc:
        print(f"读取 config.json 失败: {exc}")
        return 2

    domain = checkin.normalize_domain(
        str(config.get("domain") or checkin.DEFAULT_DOMAINS[0])
    )
    print(f"当前域名: {domain}")
    print("")

    try:
        raw = input("粘贴完整 Cookie 后按回车（不会写入日志）: ")
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return 130

    cookie = checkin.normalize_cookie(raw)
    if "=" not in cookie:
        print("这看起来不是有效的 Cookie，至少应包含 name=value。")
        return 2

    session = checkin.build_session(cookie)
    timeout = max(5, min(60, int(config.get("timeout", 20))))
    try:
        state, response = checkin.probe_user(session, f"https://{domain}", timeout)
    except requests.RequestException as exc:
        print(f"无法连接 {domain}: {exc.__class__.__name__}")
        print("请检查网络/代理，或确认域名是否仍然有效。")
        return 3

    if state != "ok":
        print(f"Cookie 验证失败（{state}，HTTP {response.status_code}）。")
        print("请确认：已登录、复制的是 /user 请求的完整 Cookie、域名与登录时一致。")
        return 2

    config["domain"] = domain
    config["cookie"] = cookie
    config.setdefault("timeout", 20)
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("")
    print("Cookie 有效，已保存到 config.json。")
    print(f"Cookie 长度: {len(cookie)} 字符（内容不会显示）")
    print("下一步: python checkin.py")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
