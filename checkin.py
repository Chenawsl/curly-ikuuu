#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iKuuu 每日自动签到。

使用浏览器登录后保存的 Cookie 签到，不保存账号密码。
站点目前登录页带 Geetest 验证码，因此密码无法可靠地全自动登录。
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_FILE = BASE_DIR / "checkin.log"

DEFAULT_DOMAINS = [
    "ikuuu.org",
    "ikuuu.top",
    "ikuuu.win",
    "ikuuu.fyi",
    "ikuuu.pw",
    "ikuuu.one",
    "ikuuu.me",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

COOKIE_PLACEHOLDERS = {
    "",
    "请把浏览器里的 Cookie 粘贴到这里",
    "PASTE_YOUR_COOKIE_HERE",
}


def log(message: str, level: str = "INFO") -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{level}] {message}"
    try:
        print(line, flush=True)
    except (AttributeError, OSError, ValueError):
        # pythonw.exe (Task Scheduler) may not have a stdout stream.
        pass
    try:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def rotate_log() -> None:
    """Keep the log small without needing an external logging config."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2 * 1024 * 1024:
            backup = LOG_FILE.with_suffix(".log.1")
            backup.unlink(missing_ok=True)
            LOG_FILE.replace(backup)
    except OSError:
        pass


def fail(message: str, code: int) -> int:
    log(message, "ERROR")
    return code


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(CONFIG_FILE)

    with CONFIG_FILE.open("r", encoding="utf-8-sig") as handle:
        config = json.load(handle)

    if not isinstance(config, dict):
        raise ValueError("config.json 的顶层必须是一个 JSON 对象")
    return config


def normalize_domain(value: str) -> str:
    domain = (value or "").strip()
    domain = re.sub(r"^https?://", "", domain, flags=re.IGNORECASE)
    domain = domain.split("/", 1)[0].strip().rstrip(".")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain):
        raise ValueError(f"域名格式不正确: {value!r}")
    return domain.lower()


def normalize_cookie(value: str) -> str:
    cookie = (value or "").strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie[7:].strip()
    cookie = cookie.replace("\r", "").replace("\n", "").strip()
    if len(cookie) >= 2 and cookie[0] == cookie[-1] and cookie[0] in "\"'":
        cookie = cookie[1:-1].strip()
    return cookie


def parse_cookie(cookie: str) -> dict:
    jar = {}
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            jar[name] = value.strip()
    return jar


def is_login_page(text: str) -> bool:
    lower = text.lower()
    has_email_input = 'name="email"' in lower or "id=\"email\"" in lower
    has_password_input = 'name="passwd"' in lower or 'id="password"' in lower
    has_login_path = "/auth/login" in lower
    return has_email_input and has_password_input and (
        has_login_path or "login" in lower
    )


def build_session(cookie: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
    for name, value in parse_cookie(cookie).items():
        session.cookies.set(name, value)
    return session


def probe_user(session: requests.Session, base: str, timeout: int):
    response = session.get(
        f"{base}/user",
        timeout=timeout,
        allow_redirects=True,
    )
    if response.status_code in (403, 429):
        return "blocked", response
    if "/auth/login" in response.url:
        return "unauth", response
    if response.status_code >= 500:
        return "server", response
    if response.status_code != 200:
        return "http", response
    if is_login_page(response.text):
        return "unauth", response
    return "ok", response


def checkin(session: requests.Session, base: str, timeout: int):
    """Return (status, message), where status is success/already/unauth/error."""
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{base}/user",
        "Origin": base,
    }

    last_error = "未知错误"
    for attempt in range(1, 3):
        try:
            response = session.post(
                f"{base}/user/checkin",
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
            )

            location = response.headers.get("Location", "")
            if response.status_code == 302 or "/auth/login" in location:
                return "unauth", "登录状态已失效"
            if response.status_code == 429:
                return "error", "请求过于频繁（HTTP 429）"
            if response.status_code >= 500:
                last_error = f"服务器错误（HTTP {response.status_code}）"
            elif response.status_code != 200:
                last_error = f"HTTP {response.status_code}"
            else:
                try:
                    data = response.json()
                except ValueError:
                    if is_login_page(response.text):
                        return "unauth", "返回了登录页，Cookie 已失效"
                    last_error = "签到接口返回的不是 JSON"
                else:
                    if not isinstance(data, dict):
                        last_error = "签到接口返回格式异常"
                    else:
                        ret = data.get("ret", data.get("code"))
                        message = str(
                            data.get("msg")
                            or data.get("message")
                            or ""
                        ).strip()

                        if ret in (1, "1", True):
                            return "success", message or "签到成功"
                        if ret in (0, "0", False):
                            if any(
                                word in message
                                for word in ("已签到", "已经签到", "已签", "重复", "already")
                            ):
                                return "already", message or "今天已经签到过了"
                            return "error", message or "签到失败"

                        last_error = message or f"未知返回: {data!r}"

        except requests.Timeout:
            last_error = f"请求超时（第 {attempt}/2 次）"
        except requests.RequestException as exc:
            last_error = f"网络错误: {exc.__class__.__name__}"

        if attempt < 2:
            time.sleep(2 + random.random())

    return "error", last_error


def main() -> int:
    rotate_log()
    log("iKuuu 自动签到开始")

    try:
        config = load_config()
    except FileNotFoundError:
        return fail(
            "没有找到 config.json。请复制 config.example.json 为 config.json 并填入 Cookie。",
            2,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return fail(f"读取 config.json 失败: {exc}", 2)

    cookie = normalize_cookie(
        os.environ.get("IKUUU_COOKIE", "") or str(config.get("cookie", ""))
    )
    if cookie in COOKIE_PLACEHOLDERS or "=" not in cookie:
        return fail(
            "还没有配置 Cookie。请先登录 https://ikuuu.org/ ，"
            "按 README 的说明把浏览器请求头里的 Cookie 粘贴到 config.json。",
            2,
        )

    try:
        configured_domain = normalize_domain(
            str(config.get("domain") or DEFAULT_DOMAINS[0])
        )
        timeout = max(5, min(60, int(config.get("timeout", 20))))
    except (ValueError, TypeError) as exc:
        return fail(f"config.json 配置有误: {exc}", 2)

    account = str(config.get("account") or "").strip()
    log(f"账号: {account or '未填写（不影响签到）'}")
    log(f"首选域名: {configured_domain}")

    domains = []
    for domain in [configured_domain, *DEFAULT_DOMAINS]:
        if domain not in domains:
            domains.append(domain)

    session = build_session(cookie)
    network_failures = 0

    for index, domain in enumerate(domains):
        base = f"https://{domain}"
        log(f"检查域名: {domain}")

        try:
            state, response = probe_user(session, base, timeout)
        except requests.Timeout:
            network_failures += 1
            log(f"{domain} 连接超时，尝试下一个域名", "WARN")
            continue
        except requests.RequestException as exc:
            network_failures += 1
            log(
                f"{domain} 无法连接（{exc.__class__.__name__}），尝试下一个域名",
                "WARN",
            )
            continue

        if state == "unauth":
            log(
                "Cookie 无效或已过期。请重新登录后复制新的 Cookie 到 config.json。",
                "ERROR",
            )
            return 2

        if state == "blocked":
            network_failures += 1
            log(f"{domain} 被站点或 CDN 拦截（HTTP {response.status_code}）", "WARN")
            continue

        if state in ("server", "http"):
            network_failures += 1
            log(f"{domain} 返回 HTTP {response.status_code}，尝试下一个域名", "WARN")
            continue

        log(f"{domain} 登录状态有效，开始签到")

        status, message = checkin(session, base, timeout)
        if status == "success":
            log(f"签到成功: {message}")
            return 0
        if status == "already":
            log(f"今天已经签到过了: {message}")
            return 0
        if status == "unauth":
            log("Cookie 无效或已过期，请重新获取 Cookie。", "ERROR")
            return 2

        log(f"{domain} 签到失败: {message}", "ERROR")
        if index + 1 < len(domains):
            log("尝试下一个域名", "WARN")

    if network_failures:
        return fail(
            "所有域名都无法完成签到。请检查网络、代理或域名是否仍然有效。",
            3,
        )
    return fail("签到没有成功，请查看上面的日志。", 4)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("用户中断", "WARN")
        sys.exit(130)
