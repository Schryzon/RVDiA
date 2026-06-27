import os
import io
import re
import random
import logging
from datetime import datetime, timezone
from aiohttp import ClientSession
from PIL import Image
from google import genai
from google.genai import types
from pypdf import PdfReader

from scripts.main import db, heading
from scripts.utils.telegram import (
    send_telegram_message, send_telegram_photo, send_telegram_photo_bytes,
    send_telegram_location, telegram_client
)
from scripts.utils.i18n import i18n
from scripts.utils.search import search_web
from cogs.Reminder import parse_duration

async def get_telegram_file_bytes(message, telegram_user_id) -> tuple[bytes, str, str]:
    if not telegram_client:
        raise ValueError("Telegram client not initialized!")

    photo = message.get("photo")
    document = message.get("document")
    reply_to = message.get("reply_to_message")
    
    file_id = None
    filename = "file"
    mime_type = "application/octet-stream"

    if photo:
        file_id = photo[-1]["file_id"]
        filename = "photo.png"
        mime_type = "image/png"
    elif document:
        file_id = document["file_id"]
        filename = document.get("file_name", "document.pdf")
        mime_type = document.get("mime_type", "application/pdf")
    elif reply_to:
        if reply_to.get("photo"):
            file_id = reply_to["photo"][-1]["file_id"]
            filename = "photo.png"
            mime_type = "image/png"
        elif reply_to.get("document"):
            r_doc = reply_to["document"]
            file_id = r_doc["file_id"]
            filename = r_doc.get("file_name", "document.pdf")
            mime_type = r_doc.get("mime_type", "application/pdf")

    if not file_id:
        file_id = await telegram_client.get_user_profile_photo_file_id(telegram_user_id)
        filename = "profile.png"
        mime_type = "image/png"

    if not file_id:
        raise ValueError("No attachment or profile photo found!")

    file_bytes = await telegram_client.get_file_bytes(file_id)
    return file_bytes, filename, mime_type

async def nekos_get(category: str):
    async with ClientSession() as session:
        initial_connection = await session.get(f'https://nekos.best/api/v2/{category}')
        data = await initial_connection.json()
        data_list = data['results'][0]
        return [data_list['url'], data_list['anime_name']]


day_of_week = {
    '1': "Senin",
    '2': "Selasa",
    '3': "Rabu",
    '4': "Kamis",
    '5': "Jumat",
    '6': "Sabtu",
    '0': "Minggu"
}


def setup(zora):
    # ── OCR Command ──────────────────────────────────────────
    @zora.command(["/ocr", "/bacateks"])
    async def handle_ocr(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        if telegram_client:
            await telegram_client.send_chat_action(chat_id, "typing", message_thread_id=thread_id)

        try:
            file_bytes, filename, mime_type = await get_telegram_file_bytes(message, telegram_user_id)
        except Exception:
            err = (
                "❌ No photo or PDF attachment found! Please upload an image/PDF or reply to one."
            ) if lang == "en" else (
                "❌ Lampiran foto atau PDF tidak ditemukan! Silahkan unggah foto/PDF atau balas salah satu pesan."
            )
            return await send_telegram_message(chat_id, err, thread_id=thread_id)

        filename = filename.lower()

        # Handle PDF
        if filename.endswith(".pdf") or mime_type == "application/pdf":
            try:
                pdf_file = io.BytesIO(file_bytes)
                reader = PdfReader(pdf_file)
                extracted_text = ""
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text:
                        extracted_text += f"--- Page {page_num + 1} ---\n{text}\n\n"
                extracted_text = extracted_text.strip()

                if not extracted_text:
                    scanned_msg = (
                        "⚠️ This PDF appears to be scanned or contains no text layers. "
                        "Please convert pages to images and try /ocr on them!"
                    ) if lang == "en" else (
                        "⚠️ PDF ini sepertinya adalah hasil scan atau tidak memiliki teks select. "
                        "Silakan konversi halaman menjadi gambar lalu coba /ocr!"
                    )
                    return await send_telegram_message(chat_id, scanned_msg, thread_id=thread_id)

                # Send extracted text
                if len(extracted_text) > 4000:
                    extracted_text = extracted_text[:3900] + "\n\n[Truncated...]"
                return await send_telegram_message(chat_id, f"<b>📝 Extracted PDF Text:</b>\n\n<code>{extracted_text}</code>", thread_id=thread_id)

            except Exception as ex:
                logging.error(f"Error parsing PDF: {ex}")
                err = "❌ Failed to read PDF document." if lang == "en" else "❌ Gagal membaca dokumen PDF."
                return await send_telegram_message(chat_id, err, thread_id=thread_id)

        # Handle Images
        try:
            google_key = os.getenv("googlekey")
            client = genai.Client(api_key=google_key)
            contents_payload = [
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                "Transcribe all text from this image accurately. Maintain layout if possible."
            ]
            res = await client.aio.models.generate_content(
                model='gemini-3-flash-preview',
                contents=contents_payload
            )
            text = res.text or "[No text found]"
            
            if len(text) > 4000:
                text = text[:3900] + "\n\n[Truncated...]"
                
            return await send_telegram_message(chat_id, f"<b>📝 Extracted Image Text:</b>\n\n<code>{text}</code>", thread_id=thread_id)
        except Exception as e:
            logging.error(f"Error executing Gemini OCR: {e}")
            err = "❌ Failed to perform OCR on image." if lang == "en" else "❌ Gagal melakukan pembacaan teks pada gambar."
            return await send_telegram_message(chat_id, err, thread_id=thread_id)

    # ── Reminder Command ──────────────────────────────────────
    @zora.command(["/remind", "/reminder", "/ingatkan"])
    async def handle_remind(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        if not args or len(args) < 2:
            usage = (
                "Format salah! Gunakan:\n"
                "• <code>/remind 1h beli kopi</code> (relatif)\n"
                "• <code>/remind 15:30 rapat kerja</code> (absolut jam)"
            ) if lang == "id" else (
                "Incorrect format! Use:\n"
                "• <code>/remind 1h buy coffee</code> (relative duration)\n"
                "• <code>/remind 15:30 work meeting</code> (absolute HH:MM)"
            )
            return await send_telegram_message(chat_id, usage, thread_id=thread_id)

        time_str = args[0]
        rem_msg = " ".join(args[1:])
        virtual_id = -telegram_user_id

        try:
            duration = parse_duration(time_str)
        except Exception:
            err = "Format durasi tidak valid! (Gunakan format 1d2h30m10s atau HH:MM)" if lang == "id" else "Invalid duration format! (Use 1d2h30m10s or HH:MM)"
            return await send_telegram_message(chat_id, f"⚠️ {err}", thread_id=thread_id)

        target_time = datetime.now(timezone.utc) + duration

        # Write to DB
        await db.reminder.create(data={
            'userId': virtual_id,
            'channelId': chat_id,
            'message': rem_msg,
            'targetTime': target_time
        })

        success_msg = (
            f"✅ Aku akan mengingatkanmu tentang **\"{rem_msg}\"** pada "
            f"WIB/WITA/WIT dalam waktu sekitar `{time_str}`!"
        ) if lang == "id" else (
            f"✅ I will remind you about **\"{rem_msg}\"** in about `{time_str}`!"
        )
        await send_telegram_message(chat_id, success_msg, thread_id=thread_id)

    # ── Fun Commands ──────────────────────────────────────────
    @zora.command(["/8ball"])
    async def handle_8ball(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        if not args:
            msg = "Ajukan pertanyaan terlebih dahulu! 🔮" if lang == "id" else "Please ask a question first! 🔮"
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        question = " ".join(args)
        lang_data = i18n.locales.get(lang, i18n.locales.get("en", {}))
        responses = lang_data.get("fun", {}).get("8ball_responses", [])
        if not responses:
            responses = ["It is certain. 🟢", "Reply hazy, try again. 🟡", "My reply is no. 🔴"]

        answer = random.choice(responses)
        title = i18n.get(lang, "fun.8ball_title")
        q_label = i18n.get(lang, "fun.8ball_question")
        a_label = i18n.get(lang, "fun.8ball_answer")

        text = (
            f"🔮 <b>{title}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"❓ <b>{q_label}:</b> {question}\n"
            f"✨ <b>{a_label}:</b> {answer}"
        )
        await send_telegram_message(chat_id, text, thread_id=thread_id)

    @zora.command(["/roll"])
    async def handle_roll(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        dice = args[0] if args else "1d6"
        match = re.match(r'^(?:(\d+))?d(\d+)$', dice.lower().strip())
        if not match:
            err_msg = i18n.get(lang, "fun.roll_invalid")
            return await send_telegram_message(chat_id, f"⚠️ {err_msg}", thread_id=thread_id)

        count = int(match.group(1) or 1)
        sides = int(match.group(2))

        if count <= 0 or count > 50 or sides <= 1 or sides > 1000:
            err_msg = i18n.get(lang, "fun.roll_invalid")
            return await send_telegram_message(chat_id, f"⚠️ {err_msg}", thread_id=thread_id)

        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)

        title = i18n.get(lang, "fun.roll_title")
        rolls_str = ", ".join(f"<code>{r}</code>" for r in rolls)
        result_desc = i18n.get(lang, "fun.roll_result", rolls=rolls_str, total=total)

        text = f"🎲 <b>{title}</b>\n━━━━━━━━━━━━━━━━━━━\n{result_desc}"
        await send_telegram_message(chat_id, text, thread_id=thread_id)

    @zora.command(["/coinflip", "/koin"])
    async def handle_coinflip(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        is_heads = random.choice([True, False])
        title = i18n.get(lang, "fun.coin_title")

        if is_heads:
            res_label = i18n.get(lang, "fun.coin_heads")
            res_desc = i18n.get(lang, "fun.coin_heads_desc")
        else:
            res_label = i18n.get(lang, "fun.coin_tails")
            res_desc = i18n.get(lang, "fun.coin_tails_desc")

        text = (
            f"🪙 <b>{title}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Hasil: <b>{res_label}</b>\n"
            f"<i>{res_desc}</i>"
        )
        await send_telegram_message(chat_id, text, thread_id=thread_id)

    @zora.command(["/ship", "/jodoh"])
    async def handle_ship(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        name1 = None
        name2 = None

        reply_to = message.get("reply_to_message")
        if reply_to:
            name1 = full_name
            name2 = reply_to.get("from", {}).get("first_name", "Dreamer")
        elif args:
            if len(args) >= 2:
                name1 = args[0]
                name2 = args[1]
            else:
                name1 = full_name
                name2 = args[0]

        if not name1 or not name2:
            msg = "Gunakan: <code>/ship [nama1] [nama2]</code> atau reply pesan seseorang!" if lang == "id" else "Use: <code>/ship [name1] [name2]</code> or reply to someone's message!"
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        if name1.lower() == name2.lower():
            err_msg = i18n.get(lang, "fun.ship_self_error")
            return await send_telegram_message(chat_id, f"⚠️ {err_msg}", thread_id=thread_id)

        success = random.randint(1, 100)
        ship_map = [
            (100, "fun.ship_range_100"),
            (90, "fun.ship_range_90"),
            (80, "fun.ship_range_80"),
            (70, "fun.ship_range_70"),
            (50, "fun.ship_range_50"),
            (25, "fun.ship_range_25"),
            (0, "fun.ship_range_0")
        ]

        ss_text = ""
        for threshold, key in ship_map:
            if success >= threshold:
                ss_text = i18n.get(lang, key, member1=name1, member2=name2)
                break

        # Blend names
        half1 = len(name1) // 2
        half2 = len(name2) // 2
        ship_name = name1[:half1] + name2[half2:]

        title_text = i18n.get(lang, "fun.ship_title")
        ship_name_label = i18n.get(lang, "fun.ship_name_prefix")

        # progress bar
        bars = int(success / 10)
        progress = "❤️" * bars + "🖤" * (10 - bars)

        res_text = (
            f"💝 <b>{title_text}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Compatibility: <b>{success}%</b>\n"
            f"<code>{progress}</code>\n\n"
            f"{ss_text}\n\n"
            f"👉 <b>{ship_name_label}:</b> <code>{ship_name}</code>"
        )
        await send_telegram_message(chat_id, res_text, thread_id=thread_id)

    # ── General Commands ──────────────────────────────────────
    @zora.command(["/weather", "/cuaca"])
    async def handle_weather(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        if not args:
            msg = "Masukkan nama kota/wilayah! 🏙️" if lang == "id" else "Please specify a city or area! 🏙️"
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        location = " ".join(args)
        api_key = os.getenv("openweatherkey")
        if not api_key:
            return await send_telegram_message(chat_id, "⚠️ OpenWeather API key is not configured.", thread_id=thread_id)

        async with ClientSession() as session:
            try:
                # 1. Geocoding API
                async with session.get(f'http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={api_key}') as resp:
                    geo_data = await resp.json()
                if not geo_data:
                    err = i18n.get(lang, "general.weather_not_found")
                    return await send_telegram_message(chat_id, f"⚠️ {err}", thread_id=thread_id)

                lat = geo_data[0]['lat']
                lon = geo_data[0]['lon']

                # 2. Current Weather API
                async with session.get(f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&lang={lang}&units=metric&appid={api_key}") as resp:
                    result = await resp.json()

                desc = result['weather'][0]['description'].title()
                temp = result['main']
                wind = result['wind']

                deg_dir = heading(wind['deg'])
                if lang == "en":
                    deg_dir_map = {
                        "Utara": "North", "Timur Laut": "Northeast", "Timur": "East", "Tenggara": "Southeast",
                        "Selatan": "South", "Barat Daya": "Southwest", "Barat": "West", "Barat Laut": "Northwest"
                    }
                    deg_dir = deg_dir_map.get(deg_dir, deg_dir)

                title = i18n.get(lang, "general.weather_title", location=result['name'])
                temp_title = i18n.get(lang, "general.weather_temp_title", temp=temp['temp'])
                temp_details = i18n.get(
                    lang,
                    "general.weather_temp_details",
                    feels=temp['feels_like'],
                    min=temp['temp_min'],
                    max=temp['temp_max'],
                    press=temp['pressure'],
                    humid=temp['humidity'],
                    clouds=result['clouds']['all']
                )
                wind_title = i18n.get(lang, "general.weather_wind_title")
                wind_details = i18n.get(lang, "general.weather_wind_details", speed=wind['speed'], deg=wind['deg'], dir=deg_dir)

                text = (
                    f"☀️ <b>{title}</b>\n"
                    f"<i>{desc}</i>\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🌡️ <b>{temp_title}</b>\n{temp_details}\n\n"
                    f"💨 <b>{wind_title}</b>\n{wind_details}"
                )
                await send_telegram_message(chat_id, text, thread_id=thread_id)

            except Exception as e:
                logging.error(f"Error in Telegram weather: {e}")
                err = i18n.get(lang, "general.weather_error")
                await send_telegram_message(chat_id, f"❌ {err}", thread_id=thread_id)

    @zora.command(["/time", "/waktu"])
    async def handle_time(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        if not args:
            msg = "Masukkan nama kota/wilayah! 🕒" if lang == "id" else "Please specify a city or area! 🕒"
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        location = args[0].title()

        async with ClientSession() as session:
            try:
                # 1. Fetch timezones
                async with session.get('http://worldtimeapi.org/api/timezone') as resp:
                    tz_list = await resp.json()

                area = []
                for tz in tz_list:
                    parts = tz.split("/")
                    if location in parts:
                        area = parts
                        break

                if not area:
                    err = i18n.get(lang, "general.time_not_found")
                    return await send_telegram_message(chat_id, f"⚠️ {err}", thread_id=thread_id)

                req_tz = "/".join(area)
                async with session.get(f'http://worldtimeapi.org/api/timezone/{req_tz}') as resp:
                    data = await resp.json()

                day = str(data['day_of_week'])
                day_name = day_of_week.get(day, "Hari")
                if lang == "en":
                    day_name_map = {
                        "Senin": "Monday", "Selasa": "Tuesday", "Rabu": "Wednesday", "Kamis": "Thursday",
                        "Jumat": "Friday", "Sabtu": "Saturday", "Minggu": "Sunday"
                    }
                    day_name = day_name_map.get(day_name, day_name)

                # Format date string
                dt = data['datetime'].split(".")[0]
                dt_obj = datetime.fromisoformat(dt)
                formatted_dt = dt_obj.strftime("%d %B %Y - %H:%M:%S")

                text = (
                    f"⏰ <b>Waktu Saat Ini: {location}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"Hari: <b>{day_name}</b>\n"
                    f"Waktu: <code>{formatted_dt}</code>\n"
                    f"Zona Waktu: <code>{data['abbreviation']} (UTC {data['utc_offset']})</code>"
                )
                await send_telegram_message(chat_id, text, thread_id=thread_id)

            except Exception as e:
                logging.error(f"Error in Telegram time: {e}")
                err = "Gagal memproses waktu." if lang == "id" else "Failed to get time."
                await send_telegram_message(chat_id, f"❌ {err}", thread_id=thread_id)

    @zora.command(["/hex"])
    async def handle_hex(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        if not args:
            msg = "Masukkan kode hex (contoh: FF0000)!" if lang == "id" else "Please specify a hex code (e.g. FF0000)!"
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        hex_str = args[0].replace("#", "").upper()
        pattern = r'^[0-9A-F]{6}$'
        if not re.match(pattern, hex_str):
            err = i18n.get(lang, "general.hex_invalid", hex=hex_str)
            return await send_telegram_message(chat_id, f"⚠️ {err}", thread_id=thread_id)

        hex_code = int(hex_str, 16)
        r = (hex_code >> 16) & 0xff
        g = (hex_code >> 8) & 0xff
        b = hex_code & 0xff

        # Local generation using Pillow
        try:
            color_img = Image.new("RGB", (500, 500), (r, g, b))
            bio = io.BytesIO()
            color_img.save(bio, format="PNG")
            photo_bytes = bio.getvalue()
        except Exception as e:
            logging.error(f"Error generating local hex image: {e}")
            return await send_telegram_message(chat_id, "❌ Error generating color image.", thread_id=thread_id)

        caption = f"🎨 <b>Color: #{hex_str}</b>\nRGB: <code>({r}, {g}, {b})</code>"
        await send_telegram_photo_bytes(chat_id, photo_bytes, filename=f"color_{hex_str}.png", caption=caption, thread_id=thread_id)

    @zora.command(["/rgb"])
    async def handle_rgb(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        if not args or len(args) < 3:
            msg = "Masukkan nilai RGB (contoh: 255 0 0)!" if lang == "id" else "Please specify RGB values (e.g. 255 0 0)!"
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        try:
            r, g, b = int(args[0]), int(args[1]), int(args[2])
            if any(val < 0 or val > 255 for val in [r, g, b]):
                raise ValueError()
        except Exception:
            err = i18n.get(lang, "general.rgb_invalid")
            return await send_telegram_message(chat_id, f"⚠️ {err}", thread_id=thread_id)

        hex_str = '{:02x}{:02x}{:02x}'.format(r, g, b).upper()
        # Local generation using Pillow
        try:
            color_img = Image.new("RGB", (500, 500), (r, g, b))
            bio = io.BytesIO()
            color_img.save(bio, format="PNG")
            photo_bytes = bio.getvalue()
        except Exception as e:
            logging.error(f"Error generating local rgb image: {e}")
            return await send_telegram_message(chat_id, "❌ Error generating color image.", thread_id=thread_id)

        caption = f"🎨 <b>Color: #{hex_str}</b>\nRGB: <code>({r}, {g}, {b})</code>"
        await send_telegram_photo_bytes(chat_id, photo_bytes, filename=f"color_{hex_str}.png", caption=caption, thread_id=thread_id)

    @zora.command(["/map", "/maps", "/peta"])
    async def handle_map(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        if not args:
            msg = "Masukkan nama tempat/kota! 🗺️" if lang == "id" else "Please specify a location or city! 🗺️"
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        location = " ".join(args)
        api_key = os.getenv("openweatherkey")
        if not api_key:
            return await send_telegram_message(chat_id, "⚠️ OpenWeather API key is not configured.", thread_id=thread_id)

        if telegram_client:
            await telegram_client.send_chat_action(chat_id, "typing", message_thread_id=thread_id)

        async with ClientSession() as session:
            try:
                # 1. Resolve address coordinates using direct geocoding
                async with session.get(f'http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={api_key}') as resp:
                    geo_data = await resp.json()
                if not geo_data:
                    err = i18n.get(lang, "general.weather_not_found")
                    return await send_telegram_message(chat_id, f"⚠️ {err}", thread_id=thread_id)

                lat = geo_data[0]['lat']
                lon = geo_data[0]['lon']
                name = geo_data[0]['name']
                country = geo_data[0].get('country', '')

                maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

                # Send native Telegram location map
                await send_telegram_location(chat_id, lat, lon, thread_id=thread_id)

                # Send formatted detail message
                title = "🗺️ Google Maps Location" if lang == "en" else "🗺️ Lokasi Google Maps"
                text = (
                    f"📍 <b>{title}: {name}, {country}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"Coordinates: <code>{lat}, {lon}</code>\n\n"
                    f"🔗 <a href=\"{maps_url}\"><b>Open in Google Maps</b></a>"
                )
                await send_telegram_message(chat_id, text, thread_id=thread_id)

            except Exception as e:
                logging.error(f"Error in Telegram map command: {e}")
                err = "Gagal mengambil data peta lokasi." if lang == "id" else "Failed to retrieve map coordinates."
                await send_telegram_message(chat_id, f"❌ {err}", thread_id=thread_id)

    @zora.command(["/search", "/google", "/cari"])
    async def handle_search(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        if not args:
            msg = "Masukkan kata kunci pencarian!" if lang == "id" else "Please specify search query!"
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        query = " ".join(args)
        if telegram_client:
            await telegram_client.send_chat_action(chat_id, "typing", message_thread_id=thread_id)

        try:
            results = await search_web(query, max_results=5, safesearch='on')
            if not results:
                err = i18n.get(lang, "general.search_no_results")
                return await send_telegram_message(chat_id, f"⚠️ {err}", thread_id=thread_id)

            lines = [
                f"🔍 <b>Search results for: \"{query}\"</b>",
                "━━━━━━━━━━━━━━━━━━━"
            ]
            for idx, res in enumerate(results):
                title = res.get("title", "Link")
                href = res.get("href", "#")
                body = res.get("body", "")
                lines.append(f"<b>{idx+1}. </b><a href=\"{href}\"><b>{title}</b></a>\n{body}\n")

            await send_telegram_message(chat_id, "\n".join(lines), thread_id=thread_id)

        except Exception as e:
            logging.error(f"Error in Telegram search: {e}")
            err = i18n.get(lang, "general.search_error", error=str(e))
            await send_telegram_message(chat_id, f"❌ {err}", thread_id=thread_id)

    # ── Roleplay Commands ─────────────────────────────────────
    roleplay_commands = [
        "hug", "kiss", "slap", "pat", "blush", "cry", "laugh", "happy", "think", "agree", "bored"
    ]

    async def handle_roleplay(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        cmd = command.lower().lstrip("/")
        
        # Determine target user
        target_name = None
        reply_to = message.get("reply_to_message")
        if reply_to:
            r_sender = reply_to.get("from", {})
            target_name = r_sender.get("first_name", "Dreamer")
        elif args:
            target_name = " ".join(args)

        # Get GIF from nekos.best
        category = cmd
        if cmd == "agree":
            category = "thumbsup"

        try:
            gif_url, anime_name = await nekos_get(category)
        except Exception as e:
            logging.error(f"Failed to fetch roleplay GIF: {e}")
            err = "❌ Gagal memuat animasi." if lang == "id" else "❌ Failed to fetch animation."
            return await send_telegram_message(chat_id, err, thread_id=thread_id)

        action_key = f"roleplay.action_{cmd}"
        action = i18n.get(lang, action_key, default=cmd)

        if not target_name:
            title = f"<b>{full_name}</b> {action}!"
        else:
            title = f"<b>{full_name}</b> {action} <b>{target_name}</b>!"

        caption = f"{title}\n\n<i>Anime: {anime_name}</i>"
        
        # Send GIF
        await send_telegram_photo(chat_id, gif_url, caption=caption, thread_id=thread_id)

    # Register each roleplay action
    for rc in roleplay_commands:
        zora.command(f"/{rc}")(handle_roleplay)
