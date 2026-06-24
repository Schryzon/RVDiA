import os
import asyncio
import logging
import aiohttp
from scripts.main import db
from scripts.utils.telegram import telegram_client, send_telegram_message

class ZoraBot:
    def __init__(self, loop=None):
        self.loop = loop
        self.commands = {}
        self.chat_handler = None
        self.username = None

    def command(self, names):
        def decorator(func):
            if isinstance(names, list):
                for name in names:
                    self.commands[name.lower()] = func
            else:
                self.commands[names.lower()] = func
            return func
        return decorator

    def default_chat(self):
        def decorator(func):
            self.chat_handler = func
            return func
        return decorator

    def load_cogs(self):
        import importlib
        import pkgutil
        import scripts.telegram as telegram_module
        
        logging.info("🚀 Loading Zora handlers...")
        for _, module_name, _ in pkgutil.iter_modules(telegram_module.__path__):
            try:
                module = importlib.import_module(f"scripts.telegram.{module_name}")
                if hasattr(module, "setup"):
                    module.setup(self)
                    logging.info(f"✅ Loaded Telegram module: {module_name}")
            except Exception as e:
                logging.error(f"❌ Failed to load Telegram module {module_name}: {e}", exc_info=True)

async def handle_telegram_update(zora_bot, bot, update):
    message = update.get("message")
    if not message:
        return

    text = (message.get("text") or message.get("caption") or "").strip()
    if not text:
        return

    chat = message["chat"]
    chat_id = chat["id"]
    chat_type = chat.get("type", "private")  # private, group, supergroup, channel
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

    parts = text.split()
    raw_command = parts[0].lower() if parts else ""
    args = parts[1:] if len(parts) > 1 else []

    # Parse potential group command suffixes (e.g. /help@RVDiA_Official_bot)
    command = raw_command
    directed_to_us = False
    has_mention = "@" in command

    if has_mention:
        cmd_part, bot_part = command.split("@", 1)
        command = cmd_part
        if zora_bot.username and bot_part == zora_bot.username:
            directed_to_us = True
    else:
        if chat_type == "private":
            directed_to_us = True

    # Route command to handlers
    if command in zora_bot.commands:
        # Ignore command if it has a mention pointing to another bot
        if has_mention and not directed_to_us:
            return

        handler = zora_bot.commands[command]
        async def run_command_handler():
            try:
                await handler(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang)
            except Exception as e:
                logging.error(f"Error running Telegram command {command}: {e}", exc_info=True)
                raise e
        bot.loop.create_task(run_command_handler())
    elif command.startswith("/"):
        # Reply with unknown command ONLY if in private DMs or explicitly directed to us in a group
        if chat_type == "private" or directed_to_us:
            unknown_msg = f"⚠️ Unknown command. Type /help to see all commands." if lang == "en" else f"⚠️ Command tidak dikenal. Ketik /help untuk melihat menu bantuan."
            bot.loop.create_task(send_telegram_message(chat_id, unknown_msg))
    else:
        if zora_bot.chat_handler:
            # Check if we should reply to general chat in group chats
            should_reply = False
            clean_text = text

            if chat_type == "private":
                should_reply = True
            else:
                # 1. Mention check: e.g. "@botname hello"
                mentioned_us = False
                if zora_bot.username:
                    mentioned_us = f"@{zora_bot.username}" in text.lower()
                    if mentioned_us:
                        import re
                        clean_text = re.sub(rf"@{zora_bot.username}\b", "", text, flags=re.IGNORECASE).strip()

                # 2. Reply check: is reply to one of our own bot messages
                is_reply_to_us = False
                reply_to = message.get("reply_to_message")
                if reply_to and reply_to.get("from"):
                    from_bot = reply_to["from"]
                    if from_bot.get("is_bot") and zora_bot.username and from_bot.get("username", "").lower() == zora_bot.username:
                        is_reply_to_us = True

                if mentioned_us or is_reply_to_us:
                    should_reply = True

            if should_reply:
                async def run_chat_handler():
                    try:
                        await zora_bot.chat_handler(zora_bot, chat_id, telegram_user_id, username, full_name, clean_text, lang)
                    except Exception as e:
                        logging.error(f"Error running Telegram chat handler: {e}", exc_info=True)
                        raise e
                bot.loop.create_task(run_chat_handler())

async def start_zora(bot):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logging.warning("TELEGRAM_BOT_TOKEN is not set in environment variables. Telegram adapter disabled.")
        return

    # Create ZoraBot instance and load cogs
    zora_bot = ZoraBot(loop=bot.loop)
    zora_bot.load_cogs()

    url = f"https://api.telegram.org/bot{token}"
    offset = 0
    logging.info("🚀 Telegram Bot Polling Adapter (RVDiA Zora) starting up...")

    async with aiohttp.ClientSession() as session:
        try:
            # Fetch bot details from Telegram to store the username
            async with session.get(f"{url}/getMe") as resp:
                if resp.status == 200:
                    me_data = await resp.json()
                    if me_data.get("ok"):
                        zora_bot.username = me_data["result"]["username"].lower()
                        logging.info(f"🤖 Connected as Telegram Bot: @{zora_bot.username}")
                else:
                    logging.warning(f"Failed to fetch Telegram bot info (/getMe returned status {resp.status})")
        except Exception as e:
            logging.error(f"Failed to fetch Telegram bot info: {e}")

        try:
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
                                    bot.loop.create_task(handle_telegram_update(zora_bot, bot, result))
                        else:
                            logging.warning(f"Telegram API getUpdates returned status {resp.status}")
                            await asyncio.sleep(5)
                except asyncio.CancelledError:
                    logging.info("Telegram Bot Adapter long polling task cancelled.")
                    break
                except Exception as e:
                    logging.error(f"Error in Telegram polling loop: {e}")
                    await asyncio.sleep(5)
        finally:
            if telegram_client:
                await telegram_client.close()
