#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cron: 0 5 8 * * *
new Env('iKuuu签到')

青龙面板部署版：
  - 从 IKUUU_COOKIES / IKUUU_COOKIE 读取登录 Cookie
  - 支持多账号，每天签到
  - 支持企业微信群机器人、Server酱、PushPlus、青龙自带 notify.py 通知
"""

from __future__ import annotations

import argparse
import base64
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

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
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{level}] {message}", flush=True)


def normalize_domain(value: str) -> str:
    domain = (value or "").strip().strip("\"'")
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
    has_email_input = 'name="email"' in lower or 'id="email"' in lower
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
    response = session.get(f"{base}/user", timeout=timeout, allow_redirects=True)
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
    """Return (status, message), status is success/already/unauth/error."""
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
                            data.get("msg") or data.get("message") or ""
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


def decode_origin_body(html: str) -> str:
    match = re.search(r'var originBody = "([^"]+)"', html)
    if not match:
        return html
    try:
        return base64.b64decode(match.group(1)).decode("utf-8", "replace")
    except Exception:
        return html


def extract_remaining_flow(html: str) -> str:
    """Best-effort parse of the remaining traffic text; empty when unknown."""
    decoded = decode_origin_body(html)
    text = re.sub(r"<[^>]+>", " ", decoded)
    text = re.sub(r"\s+", " ", text)
    patterns = [
        r"(?:剩余流量|可用流量|流量余额)[^0-9]{0,80}(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB|PB)",
        r"(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB|PB)[^0-9]{0,80}(?:剩余流量|可用流量|流量余额)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return f"{match.group(1)} {match.group(2).upper()}"
    return ""


def fetch_flow(session: requests.Session, base: str, timeout: int) -> str:
    try:
        response = session.get(f"{base}/user", timeout=timeout)
        if response.status_code == 200:
            return extract_remaining_flow(response.text)
    except requests.RequestException:
        pass
    return ""


def process_account(account: dict, domain: str, timeout: int) -> dict:
    result = {
        "name": account["name"],
        "status": "error",
        "message": "未知错误",
        "domain": domain,
        "flow": "",
    }

    domains = []
    for item in [domain, *DEFAULT_DOMAINS]:
        if item not in domains:
            domains.append(item)

    session = build_session(account["cookie"])
    network_failures = 0

    for index, current in enumerate(domains):
        base = f"https://{current}"
        log(f"[{result['name']}] 检查域名: {current}")

        try:
            state, response = probe_user(session, base, timeout)
        except requests.Timeout:
            network_failures += 1
            log(f"[{result['name']}] {current} 连接超时，尝试下一个域名", "WARN")
            continue
        except requests.RequestException as exc:
            network_failures += 1
            log(
                f"[{result['name']}] {current} 无法连接"
                f"（{exc.__class__.__name__}），尝试下一个域名",
                "WARN",
            )
            continue

        if state == "unauth":
            result.update(
                status="cookie_invalid",
                message="Cookie 无效或已过期，请重新登录后更新环境变量",
                domain=current,
            )
            return result

        if state == "blocked":
            network_failures += 1
            log(
                f"[{result['name']}] {current} 被站点或 CDN 拦截"
                f"（HTTP {response.status_code}）",
                "WARN",
            )
            continue

        if state in ("server", "http"):
            network_failures += 1
            log(
                f"[{result['name']}] {current} 返回 HTTP {response.status_code}，"
                "尝试下一个域名",
                "WARN",
            )
            continue

        log(f"[{result['name']}] {current} 登录状态有效，开始签到")
        status, message = checkin(session, base, timeout)

        if status in ("success", "already"):
            result.update(
                status=status,
                message=message,
                domain=current,
                flow=fetch_flow(session, base, timeout),
            )
            return result

        if status == "unauth":
            result.update(
                status="cookie_invalid",
                message="Cookie 无效或已过期，请重新登录后更新环境变量",
                domain=current,
            )
            return result

        result.update(status="error", message=message, domain=current)
        if index + 1 < len(domains):
            log(f"[{result['name']}] {current} 签到失败，尝试下一个域名", "WARN")

    if network_failures:
        result["message"] = "所有域名都无法完成签到，请检查青龙容器网络或代理"
    return result


def parse_accounts() -> list:
    raw = os.environ.get("IKUUU_COOKIES", "") or os.environ.get(
        "IKUUU_COOKIE", ""
    )
    accounts = []
    for index, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        name = f"账号{index}"
        cookie = line
        if "|" in line:
            name, cookie = line.split("|", 1)
            name = name.strip() or f"账号{index}"

        cookie = normalize_cookie(cookie)
        if cookie in COOKIE_PLACEHOLDERS or "=" not in cookie:
            log(f"忽略第 {index} 行：Cookie 格式不正确", "WARN")
            continue

        accounts.append({"name": name, "cookie": cookie})
    return accounts


def truncate_for_wechat(text: str, limit_bytes: int = 3800) -> str:
    data = text.encode("utf-8")
    if len(data) <= limit_bytes:
        return text
    suffix = "\n...（内容过长已截断）"
    cut = data[: limit_bytes - len(suffix.encode("utf-8"))]
    return cut.decode("utf-8", "ignore") + suffix


def send_wecom(webhook: str, title: str, content: str) -> None:
    if not webhook.lower().startswith("http"):
        webhook = (
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key="
            + quote(webhook, safe="")
        )
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": truncate_for_wechat(f"**{title}**\n\n{content}")},
    }
    try:
        response = requests.post(webhook, json=payload, timeout=15)
    except requests.RequestException as exc:
        # Do not include the webhook URL/key in the log.
        raise RuntimeError(f"企业微信请求失败: {exc.__class__.__name__}") from None

    if response.status_code != 200:
        raise RuntimeError(f"企业微信 HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError("企业微信返回的不是 JSON") from None
    if data.get("errcode") != 0:
        raise RuntimeError(
            f"企业微信返回错误: {data.get('errcode')} {data.get('errmsg', '')}"
        )


def send_serverchan(sendkey: str, title: str, content: str) -> None:
    try:
        response = requests.post(
            f"https://sctapi.ftqq.com/{sendkey}.send",
            data={"title": title, "desp": content},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Server酱请求失败: {exc.__class__.__name__}") from None

    if response.status_code != 200:
        raise RuntimeError(f"Server酱 HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError("Server酱返回的不是 JSON") from None
    if data.get("code") not in (0, 200):
        raise RuntimeError(f"Server酱返回错误码: {data.get('code')}")


def send_pushplus(token: str, title: str, content: str) -> None:
    try:
        response = requests.post(
            "https://www.pushplus.plus/send",
            json={
                "token": token,
                "title": title,
                "content": content,
                "template": "markdown",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"PushPlus请求失败: {exc.__class__.__name__}") from None

    if response.status_code != 200:
        raise RuntimeError(f"PushPlus HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError("PushPlus返回的不是 JSON") from None
    if data.get("code") != 200:
        raise RuntimeError(f"PushPlus返回错误码: {data.get('code')}")


def send_qinglong(title: str, content: str) -> None:
    for path in (
        "/ql/scripts",
        "/ql/data/scripts",
        os.path.dirname(os.path.abspath(__file__)),
    ):
        if path not in sys.path:
            sys.path.append(path)
    from notify import send  # type: ignore

    send(title, content)


def has_qinglong_notify() -> bool:
    for path in (
        "/ql/scripts",
        "/ql/data/scripts",
        os.path.dirname(os.path.abspath(__file__)),
    ):
        if Path(path, "notify.py").is_file():
            return True
    return False


def notification_channel():
    webhook = (
        os.environ.get("WECHAT_WEBHOOK")
        or os.environ.get("WECHAT_BOT_WEBHOOK")
        or os.environ.get("QYWX_WEBHOOK")
        or os.environ.get("QYWX_KEY")
        or ""
    ).strip().strip("\"'")
    if webhook:
        return "wecom", webhook

    serverchan = os.environ.get("SERVERCHAN_SENDKEY", "").strip().strip("\"'")
    if serverchan:
        return "serverchan", serverchan

    pushplus = os.environ.get("PUSHPLUS_TOKEN", "").strip().strip("\"'")
    if pushplus:
        return "pushplus", pushplus

    return "qinglong", ""


def notify(title: str, content: str) -> bool:
    channel, token = notification_channel()
    if channel == "qinglong" and not has_qinglong_notify():
        log(
            "未配置微信通知。请设置 WECHAT_WEBHOOK（企业微信群机器人），"
            "或在青龙面板配置通知后重试。",
            "WARN",
        )
        return False

    try:
        if channel == "wecom":
            send_wecom(token, title, content)
        elif channel == "serverchan":
            send_serverchan(token, title, content)
        elif channel == "pushplus":
            send_pushplus(token, title, content)
        else:
            send_qinglong(title, content)
    except Exception as exc:
        log(f"通知发送失败（{channel}）: {exc}", "WARN")
        return False

    log(f"通知已发送（{channel}）")
    return True


def build_message(results: list, domain: str) -> tuple:
    success = sum(1 for item in results if item["status"] in ("success", "already"))
    failed = len(results) - success
    title = "iKuuu 签到成功" if failed == 0 else "iKuuu 签到结果"

    lines = [
        f"时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"域名：{domain}",
        f"结果：成功 {success}，失败 {failed}",
        "",
    ]

    for index, item in enumerate(results, 1):
        if item["status"] == "success":
            icon = "✅"
        elif item["status"] == "already":
            icon = "🟡"
        else:
            icon = "❌"

        lines.append(f"{index}. {item['name']}")
        lines.append(f"   状态：{icon} {item['message']}")
        if item.get("domain") and item["domain"] != domain:
            lines.append(f"   域名：{item['domain']}")
        if item.get("flow"):
            lines.append(f"   剩余流量：{item['flow']}")
        lines.append("")

    return title, "\n".join(lines).strip()


def parse_args():
    parser = argparse.ArgumentParser(description="iKuuu 青龙面板自动签到")
    parser.add_argument("--no-notify", action="store_true", help="只签到，不发通知")
    parser.add_argument("--test-notify", action="store_true", help="只发送一条测试通知")
    parser.add_argument("--domain", default="", help="临时覆盖 IKUUU_DOMAIN")
    parser.add_argument("--timeout", type=int, default=0, help="请求超时秒数")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.test_notify:
        ok = notify(
            "iKuuu 通知测试",
            f"这是一条测试消息。\n\n时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        )
        return 0 if ok else 1

    log("iKuuu 青龙面板签到开始")

    try:
        domain = normalize_domain(
            args.domain or os.environ.get("IKUUU_DOMAIN", "") or DEFAULT_DOMAINS[0]
        )
        timeout = args.timeout or int(os.environ.get("IKUUU_TIMEOUT", "20"))
        timeout = max(5, min(60, timeout))
    except (TypeError, ValueError) as exc:
        log(f"配置错误: {exc}", "ERROR")
        return 2

    accounts = parse_accounts()
    if not accounts:
        message = (
            "没有读取到 Cookie。请在青龙面板添加环境变量 IKUUU_COOKIES，"
            "格式：备注|PHPSESSID=...; uid=...; key=..."
        )
        log(message, "ERROR")
        if not args.no_notify:
            notify("iKuuu 签到失败", message)
        return 2

    log(f"账号数量: {len(accounts)}，首选域名: {domain}")
    results = []
    for index, account in enumerate(accounts, 1):
        log(f"处理账号 {index}/{len(accounts)}: {account['name']}")
        result = process_account(account, domain, timeout)
        results.append(result)

        if result["status"] == "success":
            log(f"[{account['name']}] 签到成功: {result['message']}", "INFO")
        elif result["status"] == "already":
            log(f"[{account['name']}] 今天已经签到过了: {result['message']}", "INFO")
        else:
            log(f"[{account['name']}] 失败: {result['message']}", "ERROR")

        if index < len(accounts):
            time.sleep(2)

    title, content = build_message(results, domain)
    if not args.no_notify:
        notify(title, content)

    failed = sum(
        1 for item in results if item["status"] not in ("success", "already")
    )
    log(f"签到完成：成功 {len(results) - failed}，失败 {failed}")
    if failed == 0:
        return 0
    if all(item["status"] == "cookie_invalid" for item in results):
        return 2
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("用户中断", "WARN")
        sys.exit(130)
