import os
import logging
import aiohttp

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

class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self._session = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        # let it crash or log normally - we want control
        session = await self.get_session()
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                logging.error(f"Failed to send Telegram message: {resp.status} - {await resp.text()}")
                return False
            return True

    async def send_photo(self, chat_id: int, photo_url: str, caption: str = "", parse_mode: str = "HTML") -> bool:
        url = f"{self.base_url}/sendPhoto"
        payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": parse_mode
        }
        
        session = await self.get_session()
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                logging.error(f"Failed to send Telegram photo: {resp.status} - {await resp.text()}")
                return False
            return True

    async def send_photo_bytes(self, chat_id: int, photo_bytes: bytes, filename: str = "processed.png", caption: str = "") -> bool:
        url = f"{self.base_url}/sendPhoto"
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        data.add_field("photo", photo_bytes, filename=filename, content_type="image/png")
        if caption:
            data.add_field("caption", caption)
            data.add_field("parse_mode", "HTML")
            
        session = await self.get_session()
        async with session.post(url, data=data) as resp:
            if resp.status != 200:
                logging.error(f"Failed to send Telegram photo bytes: {resp.status} - {await resp.text()}")
                return False
            return True

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> bool:
        url = f"{self.base_url}/sendChatAction"
        payload = {
            "chat_id": chat_id,
            "action": action
        }
        
        session = await self.get_session()
        async with session.post(url, json=payload) as resp:
            return resp.status == 200

    async def get_file_bytes(self, file_id: str) -> bytes:
        url = f"{self.base_url}/getFile"
        params = {"file_id": file_id}
        
        session = await self.get_session()
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise ValueError(f"getFile returned status {resp.status}")
            data = await resp.json()
            if not data.get("ok"):
                raise ValueError(f"getFile returned ok=False: {data}")
            file_path = data["result"]["file_path"]

        download_url = f"{self.file_url}/{file_path}"
        async with session.get(download_url) as resp:
            if resp.status != 200:
                raise ValueError(f"Download file returned status {resp.status}")
            return await resp.read()

    async def get_user_profile_photo_file_id(self, user_id: int) -> str | None:
        url = f"{self.base_url}/getUserProfilePhotos"
        params = {"user_id": user_id, "limit": 1}
        
        try:
            session = await self.get_session()
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok") and data["result"]["photos"]:
                        return data["result"]["photos"][0][-1]["file_id"]
        except Exception as e:
            logging.error(f"Error getting user profile photos: {e}")
        return None

# Global client wrapper instance for system-wide access
telegram_client = None
token = os.getenv("TELEGRAM_BOT_TOKEN")
if token:
    telegram_client = TelegramClient(token)

async def send_telegram_message(chat_id, text, parse_mode="HTML"):
    if telegram_client:
        await telegram_client.send_message(chat_id, text, parse_mode)

async def send_telegram_photo(chat_id, photo_url, caption="", parse_mode="HTML"):
    if telegram_client:
        await telegram_client.send_photo(chat_id, photo_url, caption, parse_mode)

async def send_telegram_photo_bytes(chat_id, photo_bytes, filename="processed.png", caption=""):
    if telegram_client:
        await telegram_client.send_photo_bytes(chat_id, photo_bytes, filename, caption)
