# iKuuu 青龙面板版 + 微信机器人通知

这是给青龙面板（Qinglong）用的独立脚本，不依赖 Windows 计划任务或 `config.json`。
所有配置都通过青龙的**环境变量**传入，脚本可以直接放在 `/ql/scripts` 下运行。

> 目录里的 `ikuuu_checkin.py` 是完整单文件脚本，复制到青龙即可。
> 如果你只需要 Windows 本地版，用上一级的 `checkin.py`。

## 为什么还是用 Cookie

iKuuu 登录页现在强制 Geetest 滑块，直接 POST 邮箱密码会返回 `captcha_failed`。
所以脚本不保存密码，而是使用浏览器登录后的 Cookie。Cookie 等同于登录凭证，
只放在青龙环境变量里，不要写进脚本或提交到 Git。

## 一、部署到青龙

### 1. 添加脚本

青龙面板 → **脚本管理** → 新建脚本，文件名填 `ikuuu_checkin.py`，
把本目录的 `ikuuu_checkin.py` 内容完整粘贴进去并保存。

也可以直接把文件上传到青龙容器的 `/ql/scripts/` 目录。

### 2. 安装依赖

青龙面板 → **依赖管理** → **Python** → 新增依赖：

```text
requests
```

或者进入容器执行：

```bash
pip3 install requests
```

### 3. 添加环境变量

青龙面板 → **环境变量** → 新建：

| 变量名 | 必填 | 示例 / 说明 |
| --- | --- | --- |
| `IKUUU_COOKIES` | 是 | `主号\|PHPSESSID=...; uid=...; key=...; email=...` |
| `WECHAT_WEBHOOK` | 否 | 企业微信群机器人完整 Webhook |
| `QYWX_KEY` | 否 | 只填企业微信机器人 key，和 `WECHAT_WEBHOOK` 二选一 |
| `IKUUU_DOMAIN` | 否 | 默认 `ikuuu.org`；如果你登录的是别的域名就改这里 |
| `IKUUU_TIMEOUT` | 否 | 请求超时秒数，默认 `20` |

`IKUUU_COOKIES` 支持多账号，每行一个，`备注|Cookie`：

```text
主号|PHPSESSID=aaaa; uid=123; key=xxxx; email=daomingchen889@gmail.com
小号|PHPSESSID=bbbb; uid=456; key=yyyy; email=other@example.com
```

只有一个账号也可以直接使用 `IKUUU_COOKIE`（单数），格式为完整 Cookie。

### 4. 获取 Cookie

1. 浏览器登录 <https://ikuuu.org/auth/login>，完成滑块验证。
2. 建议勾选 **Remember Me**，Cookie 能保持更久。
3. `F12` → **Network** → 访问 <https://ikuuu.org/user>。
4. 点 `user` 请求 → **Request Headers** → 复制 `Cookie:` 后面完整的一行。
5. 粘贴到青龙环境变量 `IKUUU_COOKIES`，格式为 `备注|Cookie`。

> 如果你登录的是 `ikuuu.top`，就把 `IKUUU_DOMAIN` 设为 `ikuuu.top`，
> 并且 Cookie 也要从 `ikuuu.top` 获取。Cookie 和域名要对应。

### 5. 添加定时任务

青龙面板 → **定时任务** → 新建：

- 名称：`iKuuu签到`
- 命令：`python3 ikuuu_checkin.py`
- 定时规则：`0 5 8 * * *`（每天 08:05）

如果你的青龙只接受 5 段 cron，就用：

```text
5 8 * * *
```

保存后点“运行一次”，查看日志。看到类似下面的内容即成功：

```text
[2026-11-09 11:20:00] [INFO] 账号数量: 1，首选域名: ikuuu.org
[2026-11-09 11:20:02] [INFO] [主号] 签到成功: 签到成功，获得 1024 MB
[2026-11-09 11:20:03] [INFO] 通知已发送（wecom）
[2026-11-09 11:20:03] [INFO] 签到完成：成功 1，失败 0
```

## 二、微信机器人通知

### 方案 A：企业微信群机器人（推荐，最简单）

1. 在企业微信里打开一个群（可以只有你自己）。
2. 群设置 → **群机器人** → **添加机器人** → 起名并创建。
3. 复制它的 **Webhook 地址**，形如：

   ```text
   https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx-xxxx-xxxx
   ```

4. 在青龙环境变量里新增：

   ```text
   WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
   ```

5. 测试通知：

   ```bash
   python3 ikuuu_checkin.py --test-notify
   ```

   企业微信群会收到一条“iKuuu 通知测试”。

也支持只填 key，变量名用 `QYWX_KEY`：

```text
QYWX_KEY=xxxxxxxx-xxxx-xxxx
```

脚本会自动拼成企业微信 Webhook 地址。

### 方案 B：Server酱（推到微信服务号）

在 [Server酱](https://sct.ftqq.com/) 获取 SendKey，然后添加：

```text
SERVERCHAN_SENDKEY=SCTxxxxxxxx
```

### 方案 C：PushPlus（推到微信公众号）

在 [PushPlus](https://www.pushplus.plus/) 获取 token，然后添加：

```text
PUSHPLUS_TOKEN=xxxxxxxx
```

### 方案 D：青龙自带通知

如果青龙面板里已经配置了通知渠道（企业微信应用、钉钉、飞书、Telegram 等），
并且容器内存在 `notify.py`，不填 `WECHAT_WEBHOOK` 时脚本会自动调用：

```python
from notify import send
send(title, content)
```

通知渠道优先级：

```text
企业微信机器人 > Server酱 > PushPlus > 青龙 notify.py
```

只使用第一个检测到的渠道，不会重复发送。

通知失败只会在日志里记一条警告，不会把已经成功的签到判为失败。
`--test-notify` 是例外：通知发不出去时它返回非 0，方便你排查配置。

### 通知内容示例

```text
iKuuu 签到成功

时间：2026-11-09 11:20:03
域名：ikuuu.org
结果：成功 1，失败 0

1. 主号
   状态：✅ 签到成功，获得 1024 MB
   剩余流量：12.34 GB
```

## 三、常用命令

```bash
# 正常签到并通知
python3 ikuuu_checkin.py

# 只签到，不发通知
python3 ikuuu_checkin.py --no-notify

# 只测试通知渠道，不签到
python3 ikuuu_checkin.py --test-notify

# 临时指定域名
python3 ikuuu_checkin.py --domain ikuuu.org

# 临时指定超时
python3 ikuuu_checkin.py --timeout 30
```

退出码：

| 退出码 | 含义 |
| --- | --- |
| `0` | 所有账号签到成功或今天已签到 |
| `1` | 至少一个账号签到失败（网络、接口或部分 Cookie 失效） |
| `2` | 没有配置 Cookie，或全部账号的 Cookie 都失效 |

## 四、常见问题

**Q：日志提示 `Cookie 无效或已过期`？**
重新在浏览器登录，复制新的 Cookie，更新青龙环境变量。Cookie 会过期，这是正常的。

**Q：日志提示 `所有域名都无法完成签到`？**
青龙容器可能无法访问 iKuuu 域名，检查容器网络、DNS 或代理。也可以手动设置
`IKUUU_DOMAIN` 为当前能访问的域名。

**Q：`ikuuu.top` 打不开？**
当前网络下 `ikuuu.top` 可能被重置连接，`ikuuu.org` 可以正常访问。
用 `ikuuu.org` 登录并获取 Cookie，同时保持 `IKUUU_DOMAIN=ikuuu.org`。

**Q：没有收到微信通知？**
确认环境变量名是 `WECHAT_WEBHOOK`，值以 `https://qyapi.weixin.qq.com/` 开头；
再运行 `python3 ikuuu_checkin.py --test-notify` 看日志。企业微信群机器人有频率限制，
不要短时间反复测试。

**Q：这是个人微信机器人吗？**
不是。这里用的是**企业微信群机器人 Webhook**，也是青龙里最稳定的微信通知方式。
如果你要的是个人微信机器人（Wechaty、wxauto、hook 等），需要额外的机器人服务和协议，
请告诉我你用的是哪一种，我再单独适配。

## 五、安全提醒

- Cookie 等同于登录凭证，泄露后别人可以操作你的账号；不要发到群里或截图。
- 企业微信 Webhook 的 key 也等于发消息权限，泄露后可能被用来发广告；不要公开。
- 不要把 Cookie 写进脚本；放在青龙环境变量里，必要时使用青龙的变量权限控制。
- 脚本不保存账号密码。密码如果已在聊天中出现过，建议修改。
- 站点更换域名后，重新登录获取 Cookie，并同步修改 `IKUUU_DOMAIN`。
