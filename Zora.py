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
    command = parts[0].lower() if parts else ""
    args = parts[1:] if len(parts) > 1 else []

    # Route command to handlers
    if command in zora_bot.commands:
        handler = zora_bot.commands[command]
        async def run_command_handler():
            try:
                await handler(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang)
            except Exception as e:
                logging.error(f"Error running Telegram command {command}: {e}", exc_info=True)
                raise e
        bot.loop.create_task(run_command_handler())
    elif command.startswith("/"):
        unknown_msg = f"⚠️ Unknown command. Type /help to see all commands." if lang == "en" else f"⚠️ Command tidak dikenal. Ketik /help untuk melihat menu bantuan."
        bot.loop.create_task(send_telegram_message(chat_id, unknown_msg))
    else:
        if zora_bot.chat_handler:
            async def run_chat_handler():
                try:
                    await zora_bot.chat_handler(zora_bot, chat_id, telegram_user_id, username, full_name, text, lang)
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
