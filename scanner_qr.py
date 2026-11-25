import asyncio
import base64
import io
import logging
import struct

import qrcode
from pyrogram import filters, StopPropagation
from pyrogram.types import InputMediaPhoto
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PasswordHashInvalidError
from telethon.sessions import StringSession

log = logging.getLogger("member-cloud.qr-login")
SESSION_SETTING_KEY = "scanner_session_string_v1"


def _qr_image(url):
    image = qrcode.make(url)
    buffer = io.BytesIO()
    buffer.name = "scanner-login-qr.png"
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def register_qr_login_handlers(app, *, config, db, is_admin, reply_admin_only,
                                get_scanner, set_scanner):
    states = {}
    clients = {}
    tasks = {}

    async def activate_session(user_id, telethon_client, reply_target):
        candidate = None
        try:
            me = await telethon_client.get_me()
            auth_key = getattr(telethon_client.session, "auth_key", None)
            auth_key_bytes = getattr(auth_key, "key", None)
            dc_id = getattr(telethon_client.session, "dc_id", None)
            if not auth_key_bytes or len(auth_key_bytes) != 256 or not dc_id:
                raise RuntimeError("Telethon QR login did not produce a valid MTProto auth key")
            # Pyrogram's documented session-string storage layout. The auth key,
            # DC and user ID are transferred; the two clients never share storage.
            packed = struct.pack(
                ">BI?256sQ?",
                int(dc_id), int(config.API_ID), False,
                auth_key_bytes, int(me.id), False,
            )
            session_string = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
            # Avoid keeping the same MTProto auth key active in both libraries.
            await telethon_client.disconnect()
            candidate = __import__("pyrogram").Client(
                "member_cloud_scanner",
                api_id=config.API_ID,
                api_hash=config.API_HASH,
                session_string=session_string,
            )
            await candidate.start()
            scanner_me = await candidate.get_me()
            if scanner_me.is_bot or int(scanner_me.id) != int(me.id):
                raise RuntimeError("Converted Pyrogram session identity check failed")
            await db.set_setting(SESSION_SETTING_KEY, session_string)
            stored = await db.get_setting(SESSION_SETTING_KEY)
            if stored != session_string:
                raise RuntimeError("Scanner session SQLite write/read verification failed")
            set_scanner(candidate)
            candidate = None
            log.info("Scanner QR login session persisted for user %s", scanner_me.id)
            await reply_target.reply_text(
                "✅ 二维码登录成功！\n"
                f"扫描账号 ID：{scanner_me.id}\n"
                "登录会话已验证并保存到本地 SQLite，重启后会自动恢复。\n"
                "现在可以发送 /scan 开始扫描。"
            )
        except Exception:
            log.exception("Could not activate scanner from QR login")
            await reply_target.reply_text(
                "❌ 二维码已确认，但扫描会话转换或保存验证失败。"
                "现有数据库没有被清空，请把部署日志发给我排查。"
            )
        finally:
            if candidate is not None:
                try:
                    await candidate.stop()
                except Exception:
                    pass
            try:
                await telethon_client.disconnect()
            except Exception:
                pass
            clients.pop(user_id, None)
            states.pop(user_id, None)
            tasks.pop(user_id, None)

    async def qr_waiter(user_id, telethon_client, qr_login, qr_message):
        try:
            while True:
                try:
                    await qr_login.wait()
                    await activate_session(user_id, telethon_client, qr_message)
                    return
                except asyncio.TimeoutError:
                    await qr_login.recreate()
                    photo = _qr_image(qr_login.url)
                    caption = (
                        "🔐 扫描账号二维码登录\n"
                        "二维码已自动刷新，请使用个人 Telegram 手机客户端扫描并确认。\n"
                        "只扫描你自己刚刚发起的登录二维码。"
                    )
                    try:
                        await qr_message.edit_media(InputMediaPhoto(media=photo, caption=caption))
                    except Exception:
                        qr_message = await qr_message.reply_photo(photo, caption=caption)
                except SessionPasswordNeededError:
                    states[user_id] = {
                        "step": "password",
                        "client": telethon_client,
                        "message": qr_message,
                    }
                    await qr_message.reply_text(
                        "🔒 这个 Telegram 账号开启了两步验证。\n"
                        "请在这里发送两步验证密码；处理后会尝试立即删除这条密码消息。"
                    )
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scanner QR login failed")
            try:
                await qr_message.reply_text(
                    "❌ 二维码登录失败。请稍后重新发送 /scanqr，并把部署日志发给我。"
                )
            except Exception:
                pass
            try:
                await telethon_client.disconnect()
            except Exception:
                pass
            clients.pop(user_id, None)
            states.pop(user_id, None)
            tasks.pop(user_id, None)

    async def begin_qr_login(user, message):
        scanner = get_scanner()
        if scanner is not None and scanner.is_connected:
            await message.reply_text("✅ 扫描账号已经登录，无需再次授权。")
            return
        old_task = tasks.pop(user.id, None)
        if old_task and not old_task.done():
            old_task.cancel()
        old_client = clients.pop(user.id, None)
        if old_client:
            try:
                await old_client.disconnect()
            except Exception:
                pass
        try:
            telethon_client = TelegramClient(
                StringSession(), int(config.API_ID), config.API_HASH,
                device_model="Member Cloud QR Login",
                system_version="Linux",
                app_version="1.0",
            )
            await telethon_client.connect()
            qr_login = await telethon_client.qr_login()
            photo = _qr_image(qr_login.url)
            qr_message = await message.reply_photo(
                photo,
                caption=(
                    "🔐 扫描账号二维码登录\n"
                    "请用已经登录个人账号的 Telegram 手机客户端：设置 → 设备 → 连接桌面设备，"
                    "扫描此二维码并确认登录。\n"
                    "二维码会自动刷新。不要把二维码转发给任何人。"
                ),
            )
            clients[user.id] = telethon_client
            states[user.id] = {
                "step": "qr",
                "client": telethon_client,
                "message": qr_message,
            }
            tasks[user.id] = asyncio.create_task(
                qr_waiter(user.id, telethon_client, qr_login, qr_message)
            )
        except Exception:
            log.exception("Could not start scanner QR login")
            await message.reply_text("❌ 无法生成登录二维码，请检查部署日志。")

    @app.on_message(filters.private & filters.command("scanqr"))
    async def scanner_qr_start(client, message):
        user = message.from_user
        if not user or not await is_admin(user.id):
            await reply_admin_only(message)
            return
        await begin_qr_login(user, message)

    @app.on_callback_query(filters.regex(r"^mc:scannerloginqr$"))
    async def scanner_qr_menu_callback(client, query):
        user = query.from_user
        if not user or not await is_admin(user.id):
            await query.answer("无管理员权限", show_alert=True)
            raise StopPropagation
        await query.answer()
        await begin_qr_login(user, query.message)
        raise StopPropagation

    @app.on_message(
        filters.private & filters.text & ~filters.regex(r"^/"),
        group=-99,
    )
    async def scanner_qr_password_input(client, message):
        user = message.from_user
        if not user or not await is_admin(user.id):
            return
        state = states.get(user.id)
        if not state or state.get("step") != "password":
            return
        value = (message.text or "").strip()
        if not value:
            raise StopPropagation
        telethon_client = state["client"]
        try:
            await telethon_client.sign_in(password=value)
        except PasswordHashInvalidError:
            try:
                await message.delete()
            except Exception:
                pass
            await message.reply_text("❌ 两步验证密码不正确，请重新输入，或发送 /scancancel 取消。")
            raise StopPropagation
        except Exception:
            log.exception("Scanner QR two-step verification failed")
            try:
                await message.delete()
            except Exception:
                pass
            await message.reply_text("❌ 两步验证未完成，请检查日志或重新登录。")
            raise StopPropagation
        try:
            await message.delete()
        except Exception:
            pass
        await activate_session(user.id, telethon_client, message)
        raise StopPropagation

    @app.on_message(filters.private & filters.command("scancancel"), group=-99)
    async def scanner_qr_cancel(client, message):
        user = message.from_user
        if not user or not await is_admin(user.id):
            return
        if user.id not in clients and user.id not in states:
            return
        task = tasks.pop(user.id, None)
        if task and not task.done():
            task.cancel()
        telethon_client = clients.pop(user.id, None)
        states.pop(user.id, None)
        if telethon_client:
            try:
                await telethon_client.disconnect()
            except Exception:
                pass
        await message.reply_text("✅ 已取消二维码登录流程。")
        raise StopPropagation
