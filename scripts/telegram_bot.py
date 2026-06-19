import os
import asyncio
import logging
import random
import aiohttp
from datetime import datetime, timedelta
from prisma import Json

from scripts.main import db
from scripts.ai.chat import chat_service
from scripts.game.game import level_up, give_rewards, send_level_up_msg
from scripts.utils.i18n import i18n

class TelegramMockMember:
    def __init__(self, id_val, mention_str):
        self.id = id_val
        self.mention = mention_str

class TelegramMockChannel:
    def __init__(self, chat_id):
        self.chat_id = chat_id

    async def send(self, content):
        await send_telegram_message(self.chat_id, content)

class TelegramMockCtx:
    def __init__(self, user_id, chat_id, mention_str):
        self.author = TelegramMockMember(user_id, mention_str)
        self.channel = TelegramMockChannel(chat_id)

async def send_telegram_message(chat_id, text, parse_mode="HTML"):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logging.error(f"Failed to send Telegram message: {resp.status} - {await resp.text()}")
        except Exception as e:
            logging.error(f"Error sending Telegram message: {e}")

async def send_telegram_photo(chat_id, photo_url, caption="", parse_mode="HTML"):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": parse_mode
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logging.error(f"Failed to send Telegram photo: {resp.status} - {await resp.text()}")
        except Exception as e:
            logging.error(f"Error sending Telegram photo: {e}")

async def register_telegram_user(telegram_user_id, username, lang):
    virtual_id = -telegram_user_id
    user_record = await db.user.find_unique(where={'id': virtual_id})
    if user_record:
        return False, user_record

    from scripts.game.game import default_data
    data_to_save = {**default_data}
    data_to_save['name'] = username

    user = await db.user.create(data={
        'id': virtual_id,
        'hp': 100,
        'max_hp': 100,
        'data': Json(data_to_save),
        'inventory': {
            'create': {
                'items': Json([]),
                'skills': Json([]),
                'equipments': Json([])
            }
        }
    })
    
    await db.usersettings.upsert(
        where={'userId': virtual_id},
        data={
            'create': {'userId': virtual_id, 'lang': lang},
            'update': {'lang': lang}
        }
    )
    return True, user

async def handle_register_command(chat_id, telegram_user_id, username, lang):
    success, user = await register_telegram_user(telegram_user_id, username, lang)
    if success:
        msg = (
            f"🎉 <b>Registration Successful!</b>\n"
            f"Welcome to Re:Volution dream world, Hunter <b>{username}</b>!\n"
            f"Use /profile to check your initial stats."
        ) if lang == "en" else (
            f"🎉 <b>Pendaftaran Berhasil!</b>\n"
            f"Selamat datang di dunia mimpi Re:Volution, Hunter <b>{username}</b>!\n"
            f"Gunakan /profile untuk melihat statistik awal Anda."
        )
    else:
        msg = (
            f"⚠️ You are already registered."
        ) if lang == "en" else (
            f"⚠️ Akun Anda sudah terdaftar."
        )
    await send_telegram_message(chat_id, msg)

async def handle_profile_command(chat_id, telegram_user_id, username, lang):
    virtual_id = -telegram_user_id
    user_record = await db.user.find_unique(where={'id': virtual_id})
    if not user_record:
        msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
        return await send_telegram_message(chat_id, f"⚠️ {msg}")

    p = user_record.data
    level = p.get("level", 1)
    exp = p.get("exp", 0)
    next_exp = p.get("next_exp", 50)
    coins = p.get("coins", 0)
    karma = p.get("karma", 0)
    attack = p.get("attack", 10)
    defense = p.get("defense", 7)
    agility = p.get("agility", 8)
    hp = user_record.hp
    max_hp = user_record.max_hp
    name = p.get("name", username)

    profile_msg = (
        f"⚔️ <b>RPG PROFILE: {name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Lv. {level} | EXP: {exp}/{next_exp}\n"
        f"❤️ HP: {hp}/{max_hp}\n"
        f"💰 Coins: {coins} | ✨ Karma: {karma}\n\n"
        f"📈 <b>Stats:</b>\n"
        f"🗡️ ATK: {attack} | 🛡️ DEF: {defense} | 💨 AGI: {agility}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Type /adventure to explore or /daily for rewards!"
    ) if lang == "en" else (
        f"⚔️ <b>PROFIL RPG: {name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Lv. {level} | EXP: {exp}/{next_exp}\n"
        f"❤️ HP: {hp}/{max_hp}\n"
        f"💰 Koin: {coins} | ✨ Karma: {karma}\n\n"
        f"📈 <b>Statistik:</b>\n"
        f"🗡️ ATK: {attack} | 🛡️ DEF: {defense} | 💨 AGI: {agility}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Ketik /adventure untuk berpetualang atau /daily untuk hadiah harian!"
    )
    await send_telegram_message(chat_id, profile_msg)

async def handle_daily_command(chat_id, telegram_user_id, username, lang):
    virtual_id = -telegram_user_id
    user_record = await db.user.find_unique(where={'id': virtual_id})
    if not user_record:
        msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
        return await send_telegram_message(chat_id, f"⚠️ {msg}")

    data = user_record.data
    last_login_raw = data.get('last_login')
    if not last_login_raw:
        last_login = datetime.now() - timedelta(days=1)
    elif isinstance(last_login_raw, str):
        last_login = datetime.fromisoformat(last_login_raw)
    else:
        last_login = last_login_raw

    current_time = datetime.now()
    delta_time = current_time - last_login

    if delta_time.total_seconds() <= 24 * 60 * 60:
        next_login = last_login + timedelta(hours=24)
        time_diff = next_login - current_time
        hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        
        cooldown_msg = f"⏳ Cooldown! Try again in {hours}h {minutes}m." if lang == "en" else f"⏳ Cooldown! Coba lagi dalam {hours} jam {minutes} menit."
        return await send_telegram_message(chat_id, cooldown_msg)

    new_coins = random.randint(15, 25)
    new_karma = random.randint(1, 5)
    new_exp = random.randint(10, 20)

    is_premium = user_record.premiumUntil and user_record.premiumUntil > datetime.now()
    if is_premium:
        new_coins *= 2
        new_exp *= 2

    data['coins'] += new_coins
    data['karma'] += new_karma
    data['exp'] += new_exp
    data['last_login'] = current_time.isoformat()

    await db.user.update(
        where={'id': virtual_id},
        data={'data': Json(data)}
    )

    mention_str = f"@{username}" if username else "Dreamer"
    mock_ctx = TelegramMockCtx(virtual_id, chat_id, mention_str)
    mock_user = TelegramMockMember(virtual_id, mention_str)

    leveled_up = await level_up(mock_user)
    if leveled_up:
        await send_level_up_msg(mock_ctx, mock_user)

    success_msg = (
        f"🎁 <b>Daily Claimed!</b>\n"
        f"Received +{new_coins} Coins, +{new_karma} Karma, and +{new_exp} EXP!"
    ) if lang == "en" else (
        f"🎁 <b>Hadiah Harian Diklaim!</b>\n"
        f"Mendapatkan +{new_coins} Koin, +{new_karma} Karma, dan +{new_exp} EXP!"
    )
    await send_telegram_message(chat_id, success_msg)

async def handle_adventure_command(chat_id, telegram_user_id, username, lang):
    virtual_id = -telegram_user_id
    user_record = await db.user.find_unique(where={'id': virtual_id})
    if not user_record:
        msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
        return await send_telegram_message(chat_id, f"⚠️ {msg}")

    exp_gain = random.randint(10, 25)
    coin_gain = random.randint(15, 35)

    mention_str = f"@{username}" if username else "Dreamer"
    mock_ctx = TelegramMockCtx(virtual_id, chat_id, mention_str)
    mock_user = TelegramMockMember(virtual_id, mention_str)

    await give_rewards(mock_ctx, mock_user, exp_gain, coin_gain)

    success_msg = (
        f"🧭 <b>Adventure Successful!</b>\n"
        f"Gained +{coin_gain} Coins and +{exp_gain} EXP!"
    ) if lang == "en" else (
        f"🧭 <b>Petualangan Berhasil!</b>\n"
        f"Mendapatkan +{coin_gain} Koin dan +{exp_gain} EXP!"
    )
    await send_telegram_message(chat_id, success_msg)

async def handle_help_command(chat_id, lang):
    help_msg = (
        f"🤖 <b>RVDiA Telegram Bot Commands:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"/register - Create your Re:Volution RPG account\n"
        f"/profile  - View stats, coins, karma, and level\n"
        f"/daily    - Claim your daily coins and EXP\n"
        f"/adventure - Explore the dream world and gain rewards\n"
        f"/help     - Show this help command menu\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Send any text to chat with me! ✨"
    ) if lang == "en" else (
        f"🤖 <b>Command Bot Telegram RVDiA:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"/register - Daftar akun RPG Re:Volution baru\n"
        f"/profile  - Lihat info level, koin, karma, & statistik\n"
        f"/daily    - Klaim koin harian gratis dan EXP\n"
        f"/adventure - Berpetualang di dunia mimpi untuk hadiah\n"
        f"/help     - Tampilkan menu bantuan ini\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Kirim pesan apapun untuk ngobrol denganku! ✨"
    )
    await send_telegram_message(chat_id, help_msg)

async def handle_chat_message(chat_id, telegram_user_id, username, text, lang):
    virtual_id = -telegram_user_id
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        async with aiohttp.ClientSession() as session:
            await session.post(f"https://api.telegram.org/bot{token}/sendChatAction", json={
                "chat_id": chat_id,
                "action": "typing"
            })

    try:
        result = await chat_service.generate_chat_response(
            user_id=virtual_id,
            user_name=username,
            message=text,
            lang=lang
        )
        response_text = result["response"]
        image_url = result.get("image_url")

        if image_url:
            await send_telegram_photo(chat_id, image_url, caption=response_text)
        else:
            await send_telegram_message(chat_id, response_text)
    except Exception as e:
        logging.error(f"Error generating Gemini response for Telegram: {e}", exc_info=True)
        err_msg = "⚠️ Apologies, I encountered an error in the dream world." if lang == "en" else "⚠️ Waduh, terjadi kesalahan saat mengakses dunia mimpi."
        await send_telegram_message(chat_id, err_msg)

async def handle_telegram_update(bot, update):
    message = update.get("message")
    if not message or "text" not in message:
        return

    chat = message["chat"]
    chat_id = chat["id"]
    from_user = message["from"]
    telegram_user_id = from_user["id"]
    
    first_name = from_user.get("first_name", "Dreamer")
    last_name = from_user.get("last_name", "")
    username = from_user.get("username", first_name)
    full_name = f"{first_name} {last_name}".strip()

    tg_lang = from_user.get("language_code", "en")
    lang = "id" if tg_lang.startswith("id") else "en"

    # Override language if they have registered settings
    virtual_id = -telegram_user_id
    user_settings = await db.usersettings.find_unique(where={'userId': virtual_id})
    if user_settings:
        lang = user_settings.lang

    text = message["text"].strip()
    command = text.split()[0].lower() if text else ""

    if command == "/start" or command == "/register":
        await handle_register_command(chat_id, telegram_user_id, full_name, lang)
    elif command == "/profile":
        await handle_profile_command(chat_id, telegram_user_id, full_name, lang)
    elif command == "/daily":
        await handle_daily_command(chat_id, telegram_user_id, username, lang)
    elif command == "/adventure":
        await handle_adventure_command(chat_id, telegram_user_id, username, lang)
    elif command == "/help":
        await handle_help_command(chat_id, lang)
    elif text.startswith("/"):
        unknown_msg = f"⚠️ Unknown command. Type /help to see all commands." if lang == "en" else f"⚠️ Command tidak dikenal. Ketik /help untuk melihat menu bantuan."
        await send_telegram_message(chat_id, unknown_msg)
    else:
        await handle_chat_message(chat_id, telegram_user_id, full_name, text, lang)

async def start_telegram_bot(bot):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logging.warning("TELEGRAM_BOT_TOKEN is not set in environment variables. Telegram adapter disabled.")
        return

    url = f"https://api.telegram.org/bot{token}"
    offset = 0
    logging.info("🚀 Telegram Bot Polling Adapter starting up...")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # getUpdates call with long polling timeout
                async with session.get(f"{url}/getUpdates", params={"offset": offset, "timeout": 30}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            for result in data.get("result", []):
                                update_id = result["update_id"]
                                offset = update_id + 1
                                # Process update
                                bot.loop.create_task(handle_telegram_update(bot, result))
                    else:
                        logging.warning(f"Telegram API getUpdates returned status {resp.status}")
                        await asyncio.sleep(5)
            except asyncio.CancelledError:
                logging.info("Telegram Bot Adapter long polling task cancelled.")
                break
            except Exception as e:
                logging.error(f"Error in Telegram polling loop: {e}")
                await asyncio.sleep(5)
