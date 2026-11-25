# Member Cloud V2

Independent rebuild of the existing Member Cloud application.

## Stack
- Python 3.11
- Pyrogram 2.x
- PostgreSQL via `DATABASE_URL`
- aiohttp health endpoint
- Docker deployment

## Safety rules
- This repository is separate from `mmnihm/-6` and `mmnihm/Cangku`.
- Preserve the original member, catalog, scan, copy, audit, and admin behavior.
- Never clear production tables, catalog rows, scan checkpoints, or audit records as part of deployment.
- Scanner session values are credentials. Do not commit them to GitHub or print them in logs.
- Verify scanner login, PostgreSQL persistence read-back, and reconnect after restart before declaring deployment complete.

## Required environment
`BOT_TOKEN`, `API_ID`, `API_HASH`, `ADMIN_ID`, and PostgreSQL `DATABASE_URL`.
Optional: `DATABASE_PATH`, `LOG_LEVEL`, `PORT` / `WEB_PORT`.

## Run
Build and run the included Dockerfile with a persistent volume mounted at `/app/data` and the required environment variables supplied by the host. PostgreSQL remains authoritative when `DATABASE_URL` is configured.


## 扫描账号二维码登录

管理员可在机器人私聊发送 `/scanqr`，机器人会生成 Telegram 登录二维码。请使用已经登录的个人 Telegram 手机客户端，在“设置 → 设备 → 连接桌面设备”中扫描并确认。二维码会自动刷新；若账号启用了两步验证，按机器人提示输入密码。登录成功后会把 Pyrogram 会话验证并保存到项目本地 SQLite 数据库，Docker 数据卷会保留该数据。也可继续使用原有的 `/scanlogin` 手机验证码登录方式。

**安全提醒：** 只扫描自己刚刚发起的登录二维码，不要转发或分享二维码；二维码相当于账号登录授权。
