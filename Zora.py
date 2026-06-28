import os
import random
import asyncio
import logging
import aiohttp
from scripts.main import db
from scripts.utils.telegram import (
    telegram_client,
    send_telegram_message,
    current_thread_id,
    _dynamic_callbacks,
    TelegramInteraction
)

class ZoraBot:
    def __init__(self, loop=None):
        self.loop = loop
        self.commands = {}
        self.chat_handler = None
        self.callback_handlers = {}  # prefix → handler
        self.username = None

    def command(self, names):
        def decorator(func):
            if isinstance(names, list):
                for name in names:
                    self.commands[name.lower().lstrip("/")] = func
            else:
                self.commands[names.lower().lstrip("/")] = func
            return func
        return decorator

    def callback_query(self, prefix):
        """Register a handler for callback queries whose data starts with prefix."""
        def decorator(func):
            self.callback_handlers[prefix] = func
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



async def _react_to(chat_id: int, message_id: int, message: dict = None):
    """React to a message: ❤️ normally, 🐳 or 👾 5% of the time (skipped in private chats)."""
    if not telegram_client or not message_id:
        return
    # Telegram does not support bot reactions in private chats (DMs)
    if message and message.get("chat", {}).get("type") == "private":
        return
    emoji = random.choice(["🐳", "👾"]) if random.random() < 0.05 else "❤️"
    await telegram_client.send_reaction(chat_id, message_id, emoji)

async def handle_callback_query(zora_bot, bot, callback_query):
    """Dispatch inline keyboard button presses to registered callback handlers."""
    from scripts.utils.telegram import telegram_client

    cq_id = callback_query["id"]
    data = callback_query.get("data", "")
    user = callback_query["from"]
    telegram_user_id = user["id"]
    username = user.get("username", "")
    full_name = user.get("first_name", "") + (" " + user.get("last_name", "") if user.get("last_name") else "")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    thread_id = message.get("message_thread_id")

    token = current_thread_id.set(thread_id)
    try:
        # Look up lang
        virtual_id = -telegram_user_id
        lang = "en"
        try:
            from scripts.main import db
            user_settings = await db.usersettings.find_unique(where={"userId": virtual_id})
            if user_settings:
                lang = user_settings.lang
        except Exception:
            pass

        # Check if callback is a registered dynamic button
        if data.startswith("dyn_") and data in _dynamic_callbacks:
            handler = _dynamic_callbacks[data]
            interaction = TelegramInteraction(zora_bot, chat_id, message_id, cq_id, telegram_user_id, username, full_name, data, lang)
            try:
                await handler(interaction)
            except Exception as e:
                logging.error(f"Error in dynamic callback handler: {e}", exc_info=True)
                if telegram_client:
                    await telegram_client.answer_callback_query(cq_id)
            return

        # Route to first matching handler by prefix
        handler = None
        for prefix, h in zora_bot.callback_handlers.items():
            if data.startswith(prefix):
                handler = h
                break

        if handler:
            try:
                await handler(zora_bot, chat_id, message_id, cq_id, telegram_user_id, username, full_name, data, lang)
            except Exception as e:
                logging.error(f"Error in callback handler: {e}", exc_info=True)
                if telegram_client:
                    await telegram_client.answer_callback_query(cq_id)
        else:
            # Acknowledge unknown buttons silently
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id)
    finally:
        current_thread_id.reset(token)

async def handle_telegram_update(zora_bot, bot, update):
    message = update.get("message")
    if not message:
        return

    text = (message.get("text") or message.get("caption") or "").strip()
    if not text:
        return

    chat = message["chat"]
    chat_id = chat["id"]
    thread_id = message.get("message_thread_id")
    from_user = message.get("from", {})
    telegram_user_id = from_user.get("id")
    
    first_name = from_user.get("first_name", "Dreamer")
    last_name = from_user.get("last_name", "")
    username = from_user.get("username", first_name)
    full_name = f"{first_name} {last_name}".strip()

    tg_lang = from_user.get("language_code", "en")
    lang = "id" if tg_lang.startswith("id") else "en"

    virtual_id = -telegram_user_id
    user_settings = await db.usersettings.find_unique(where={'userId': virtual_id})
    if user_settings:
        lang = user_settings.lang

    parts = text.split()
    raw_command = parts[0].lower() if parts else ""
    args = parts[1:] if len(parts) > 1 else []

    is_command = raw_command.startswith("/")
    is_at_mention = raw_command.startswith("@") and zora_bot.username and raw_command.lstrip("@") == zora_bot.username

    # Normalise: @botname [cmd_or_text] → shift args into command slot
    if is_at_mention:
        if args and args[0].startswith("/"):
            # @botname /command args...
            raw_command = args[0].lower()
            args = args[1:]
            is_command = True
        elif args and args[0].lower().lstrip("/") in zora_bot.commands:
            # @botname help  →  treat as /help (Discord-style, no slash needed)
            raw_command = f"/{args[0].lower().lstrip('/')}"
            args = args[1:]
            is_command = True
        elif args:
            # @botname some unknown text → AI chat
            clean_text = " ".join(args)
            if zora_bot.chat_handler:
                async def run_at_chat():
                    token = current_thread_id.set(thread_id)
                    try:
                        await zora_bot.chat_handler(zora_bot, chat_id, telegram_user_id, username, full_name, clean_text, lang, thread_id)
                    except Exception as e:
                        logging.error(f"Error in chat handler: {e}", exc_info=True)
                    finally:
                        current_thread_id.reset(token)
                bot.loop.create_task(run_at_chat())
            return
        else:
            # bare @botname with no args → ignore
            return

    cmd_name = raw_command[1:] if is_command else raw_command
    if "@" in cmd_name:
        cmd_name, target_bot = cmd_name.split("@", 1)
        is_directed = (zora_bot.username and target_bot.lower() == zora_bot.username)
    else:
        is_directed = True  # slash commands always directed at us

    # --- Route: known command ---
    if is_command:
        if not is_directed:
            return  # aimed at another bot, ignore
        if cmd_name in zora_bot.commands:
            handler = zora_bot.commands[cmd_name]
            message_id = message.get("message_id")
            async def run_command_handler():
                token = current_thread_id.set(thread_id)
                try:
                    await _react_to(chat_id, message_id, message)
                    await handler(zora_bot, chat_id, telegram_user_id, username, full_name, cmd_name, args, message, lang, thread_id=thread_id, via_mention=is_at_mention)
                except Exception as e:
                    logging.error(f"Error in command {cmd_name}: {e}", exc_info=True)
                finally:
                    current_thread_id.reset(token)
            bot.loop.create_task(run_command_handler())
            return
        else:
            # Unknown command — Discord-style: fall through to AI chat
            if zora_bot.chat_handler:
                message_id = message.get("message_id")
                async def run_cmd_fallthrough():
                    token = current_thread_id.set(thread_id)
                    try:
                        await _react_to(chat_id, message_id, message)
                        await zora_bot.chat_handler(zora_bot, chat_id, telegram_user_id, username, full_name, text, lang, thread_id)
                    except Exception as e:
                        logging.error(f"Error in chat fallthrough: {e}", exc_info=True)
                    finally:
                        current_thread_id.reset(token)
                bot.loop.create_task(run_cmd_fallthrough())
            return

    # --- Route: plain text / mentions / replies ---
    if zora_bot.chat_handler:
        is_reply_to_us = (
            message.get("reply_to_message", {}).get("from", {}).get("username", "").lower()
            == zora_bot.username
        )
        is_mention = zora_bot.username and f"@{zora_bot.username}" in text.lower()

        if chat["type"] == "private" or is_reply_to_us or is_mention:
            import re
            clean_text = re.sub(rf"@{zora_bot.username}\b", "", text, flags=re.IGNORECASE).strip() if is_mention else text
            
            # Grok-like context retrieval: if replying to another message, embed its context
            reply_to = message.get("reply_to_message")
            if reply_to:
                parent_sender = reply_to.get("from", {})
                parent_name = parent_sender.get("first_name", "User")
                parent_text = reply_to.get("text") or reply_to.get("caption") or ""
                if parent_text:
                    # Construct a combined prompt mimicking Grok's reference context
                    clean_text = (
                        f"[Context: User {parent_name} said: \"{parent_text}\"]\n"
                        f"Question/Reply: {clean_text}"
                    )

            message_id = message.get("message_id")
            async def run_chat_handler():
                token = current_thread_id.set(thread_id)
                try:
                    await _react_to(chat_id, message_id, message)
                    await zora_bot.chat_handler(zora_bot, chat_id, telegram_user_id, username, full_name, clean_text, lang, thread_id)
                except Exception as e:
                    logging.error(f"Error in chat handler: {e}", exc_info=True)
                finally:
                    current_thread_id.reset(token)
            bot.loop.create_task(run_chat_handler())

async def start_zora(bot):
    raw_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not raw_token:
        logging.warning("TELEGRAM_BOT_TOKEN is not set in environment variables. Telegram adapter disabled.")
        return
    token = raw_token.strip('"')

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
                                    if result.get("callback_query"):
                                        bot.loop.create_task(handle_callback_query(zora_bot, bot, result["callback_query"]))
                                    else:
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
