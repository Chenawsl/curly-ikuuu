# iKuuu 每日自动签到

一个只依赖 `requests` 的 Python 签到脚本。每天自动请求 iKuuu 的
`/user/checkin` 接口，成功或“今天已签到”都会正常退出。

> 需要部署到**青龙面板**并加微信机器人通知？用 [`qinglong/ikuuu_checkin.py`](qinglong/ikuuu_checkin.py)，
> 部署步骤、企业微信 Webhook 配置和多账号格式见 [`qinglong/README.md`](qinglong/README.md)。

## 先说明一件事：为什么用 Cookie，而不是账号密码

iKuuu 现在的登录页接入了 Geetest 滑块验证码。直接 POST 邮箱和密码会返回：

```json
{"phase":"password","result":"captcha_failed"}
```

验证码不能也不应该由脚本绕过，所以“账号密码全自动登录”无法稳定实现。
正确做法是：**在浏览器里登录一次，把登录后的 Cookie 交给脚本**。
Cookie 等同于登录凭证，脚本不会保存你的密码。

> 当前网络下 `ikuuu.top`、`ikuuu.win` 等域名会被重置连接，`ikuuu.org` 可以正常访问。
> 因此 `config.json` 默认使用 `ikuuu.org`；如果你在别的域名登录，Cookie 也要从那个域名获取。

## 1. 安装依赖

需要 Python 3.8+。在本目录打开 PowerShell：

```powershell
python -m pip install -r requirements.txt
```

## 2. 获取 Cookie（只需做一次）

1. 用浏览器打开 <https://ikuuu.org/auth/login>，登录并完成滑块验证。
2. 建议勾选 **Remember Me**，这样 Cookie 能保持更久。
3. 按 `F12` 打开开发者工具，切到 **Network（网络）**。
4. 在地址栏访问 <https://ikuuu.org/user>，在网络列表里点第一个 `user` 请求。
5. 在 **Request Headers（请求头）** 中找到 `Cookie:`，复制冒号后面的完整内容。
   - 不要只复制 `PHPSESSID`，把 `uid`、`key`、`email` 等一起复制。
   - 不要带前面的 `Cookie:` 这几个字。
6. 把 Cookie 保存到配置，二选一：

   **方法 A（推荐，自动验证并写入）**：在脚本目录运行下面的命令，粘贴 Cookie 后回车：

   ```powershell
   python save_cookie.py
   ```

   看到“Cookie 有效，已保存”即可。

   **方法 B（手动编辑）**：打开 `config.json`，把 Cookie 粘贴到 `cookie` 字段（保持一行）：

   ```json
   {
     "account": "daomingchen889@gmail.com",
     "domain": "ikuuu.org",
     "cookie": "PHPSESSID=xxxx; uid=xxxx; key=xxxx; email=xxxx",
     "timeout": 20
   }
   ```

> 也可以在环境变量里设置 `IKUUU_COOKIE`，它的优先级高于 `config.json`。
> `config.json` 已加入 `.gitignore`，不要把它或 Cookie 发给别人。

## 3. 手动测试

```powershell
python checkin.py
```

常见结果：

| 输出 | 含义 |
| --- | --- |
| `签到成功` | 成功领取当日流量 |
| `今天已经签到过了` | 今天已签到，脚本正常结束 |
| `Cookie 无效或已过期` | 重新做第 2 步，换一个新 Cookie |
| `所有域名都无法完成签到` | 网络/代理问题，或域名全部失效 |

日志会追加写入 `checkin.log`。

## 4. 设置每天自动运行

以当前 Windows 用户注册计划任务（不需要管理员权限）：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_task.ps1
```

默认每天 **08:05** 运行。要改时间：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_task.ps1 -Time "09:30"
```

注册后立即测试一次：

```powershell
Start-ScheduledTask -TaskName "iKuuu-Daily-Checkin"
```

查看任务状态：

```powershell
Get-ScheduledTaskInfo -TaskName "iKuuu-Daily-Checkin"
```

删除任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_task.ps1
```

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `checkin.py` | 签到主程序，含域名切换、Cookie 失效检测、日志 |
| `save_cookie.py` | 一次性 Cookie 保存向导，会先验证再写入配置 |
| `config.json` | 你的域名和 Cookie（不要提交到 Git） |
| `config.example.json` | 配置模板 |
| `run.bat` | 双击手动运行，结束后暂停显示结果 |
| `install_task.ps1` | 注册每天运行的 Windows 计划任务 |
| `uninstall_task.ps1` | 删除计划任务 |
| `checkin.log` | 运行日志 |
| `qinglong/` | 青龙面板版脚本、依赖和部署说明 |
| `ikuuu-qinglong.zip` | 青龙版打包文件，方便上传/传输 |

## 安全提醒

- Cookie 就是登录态，泄露后别人可以操作你的账号；不要截图或发给他人。
- 密码没有写入任何文件。如果之前把密码发在聊天里，建议改密码。
- 站点更换域名后，用新域名重新登录并更新 `domain` 和 `cookie`。
