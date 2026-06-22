import logging
from scripts.main import db
from scripts.ai.chat import chat_service
from scripts.utils.telegram import send_telegram_message, send_telegram_photo, telegram_client
from scripts.utils.i18n import i18n

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
        'data': {
            'level': 1,
            'exp': 0,
            'next_exp': 50,
            'coins': 100,
            'karma': 10,
            'class': 'None',
            'stat_points': 0,
            'attack': 10,
            'defense': 7,
            'agility': 8,
            'name': username
        },
        'inventory': {
            'create': {
                'items': [],
                'skills': [],
                'equipments': []
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

def setup(zora):
    @zora.command(["/start", "/register"])
    async def handle_register(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
        success, user = await register_telegram_user(telegram_user_id, full_name, lang)
        if success:
            msg = (
                f"🎉 <b>Registration Successful!</b>\n"
                f"Welcome to Re:Volution dream world, Hunter <b>{full_name}</b>!\n"
                f"Use /profile to check your initial stats."
            ) if lang == "en" else (
                f"🎉 <b>Pendaftaran Berhasil!</b>\n"
                f"Selamat datang di dunia mimpi Re:Volution, Hunter <b>{full_name}</b>!\n"
                f"Gunakan /profile untuk melihat statistik awal Anda."
            )
        else:
            msg = (
                f"⚠️ You are already registered."
            ) if lang == "en" else (
                f"⚠️ Akun Anda sudah terdaftar."
            )
        await send_telegram_message(chat_id, msg)

    @zora.command("/profile")
    async def handle_profile(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
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
        name = p.get("name", full_name)
        class_selected = p.get("class", "None")
        stat_points = p.get("stat_points", 0)

        class_text = (
            f"🛡️ <b>Class:</b> {class_selected}"
        ) if class_selected != "None" else (
            f"🛡️ <b>Class:</b> None (Use /class to select)" if lang == "en" else f"🛡️ <b>Kelas:</b> None (Gunakan /class untuk memilih)"
        )

        stat_points_text = ""
        if stat_points > 0:
            stat_points_text = (
                f"✨ <b>Available Points:</b> {stat_points} (Use /allocate to spend)\n"
            ) if lang == "en" else (
                f"✨ <b>Poin Tersedia:</b> {stat_points} (Gunakan /allocate untuk memakai)\n"
            )

        profile_msg = (
            f"⚔️ <b>RPG PROFILE: {name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{class_text}\n"
            f"Lv. {level} | EXP: {exp}/{next_exp}\n"
            f"❤️ HP: {hp}/{max_hp}\n"
            f"💰 Coins: {coins} | ✨ Karma: {karma}\n"
            f"{stat_points_text}"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Stats:</b>\n"
            f"🗡️ ATK: {attack} | 🛡️ DEF: {defense} | 💨 AGI: {agility}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Type /adventure to explore or /daily for rewards!"
        ) if lang == "en" else (
            f"⚔️ <b>PROFIL RPG: {name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{class_text}\n"
            f"Lv. {level} | EXP: {exp}/{next_exp}\n"
            f"❤️ HP: {hp}/{max_hp}\n"
            f"💰 Koin: {coins} | ✨ Karma: {karma}\n"
            f"{stat_points_text}"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Statistik:</b>\n"
            f"🗡️ ATK: {attack} | 🛡️ DEF: {defense} | 💨 AGI: {agility}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Ketik /adventure untuk berpetualang atau /daily untuk hadiah harian!"
        )
        await send_telegram_message(chat_id, profile_msg)

    @zora.command("/lang")
    async def handle_lang(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id})
        if not user_record:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}")

        lang_choice = args[0] if args else None
        if not lang_choice:
            msg = (
                f"⚠️ Please specify a language (en / id)!\n"
                f"Usage: <code>/lang [en|id]</code>"
            ) if lang == "en" else (
                f"⚠️ Harap tentukan bahasa (en / id)!\n"
                f"Penggunaan: <code>/lang [en|id]</code>"
            )
            return await send_telegram_message(chat_id, msg)

        lang_choice_lower = lang_choice.lower()
        if lang_choice_lower not in ["en", "id"]:
            msg = (
                f"⚠️ Invalid language! Choose <b>en</b> (English) or <b>id</b> (Indonesian)."
            ) if lang == "en" else (
                f"⚠️ Bahasa tidak valid! Pilih <b>en</b> (Inggris) atau <b>id</b> (Indonesia)."
            )
            return await send_telegram_message(chat_id, msg)

        await db.usersettings.upsert(
            where={'userId': virtual_id},
            data={
                'create': {'userId': virtual_id, 'lang': lang_choice_lower},
                'update': {'lang': lang_choice_lower}
            }
        )

        success_msg = (
            f"🇬🇧 Language changed to <b>English</b>!"
        ) if lang_choice_lower == "en" else (
            f"🇮🇩 Bahasa diubah ke <b>Bahasa Indonesia</b>!"
        )
        await send_telegram_message(chat_id, success_msg)

    @zora.command("/help")
    async def handle_help(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
        help_msg = (
            f"🤖 <b>RVDiA Zora Telegram Command Bot:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 <b>RPG SYSTEM:</b>\n"
            f"• /register - Create your RPG account\n"
            f"• /profile  - View stats, level, coins, class\n"
            f"• /class    - Choose a class (Warrior/Mage/Rogue)\n"
            f"• /allocate - Allocate stat points (e.g. /allocate ATK 5)\n"
            f"• /daily    - Claim daily coins and EXP\n"
            f"• /adventure - Explore and earn rewards\n"
            f"• /battle   - Fast-simulation combat with standard PVE enemies\n"
            f"• /worldboss - View active World Boss status\n"
            f"• /attack   - Attack the active World Boss\n"
            f"• /lang     - Change language settings (en/id)\n\n"
            f"🎨 <b>IMAGE FILTERS (Use as photo caption):</b>\n"
            f"• /grayscale, /invert, /circle, /sepia, /sharpen, /emboss\n"
            f"• /blur [strength] - Apply box blur\n"
            f"• /pixelate [size] - Apply retro pixel block effect\n"
            f"• /vignette [sigma] - Apply vignette shading\n"
            f"• /gamma [val] - Apply gamma correction\n"
            f"• /flip [h/v] - Flip image horizontally or vertically\n"
            f"• /rotate [angle] [cw/ccw] - Rotate image\n"
            f"• /adjust [bright] [contrast] - Adjust brightness/contrast\n"
            f"• /edge [method] - Canny/Sobel/Laplacian/Prewitt/Roberts/Scharr\n"
            f"• /noise [type] - Add noise (salt_pepper/gaussian/poisson)\n"
            f"• /equalize [method] - Histogram equalize (global/clahe/adaptive)\n"
            f"• /threshold [val] [binary/otsu] - Convert to binary image\n\n"
            f"✨ <b>ARTISTIC FILTERS:</b>\n"
            f"• /posterize [levels] - Color quantization\n"
            f"• /solarize [threshold] - Solarization effect\n"
            f"• /sketch [ksize] - Realistic pencil sketch\n\n"
            f"🔬 <b>MORPHOLOGY & FOURIER:</b>\n"
            f"• /erode [iter] [ksize] - Morphological erosion\n"
            f"• /dilate [iter] [ksize] - Morphological dilation\n"
            f"• /skeleton - Extract topological skeleton\n"
            f"• /lpf [cutoff] [style] - Low-pass filter (ideal/butterworth/gaussian)\n"
            f"• /hpf [cutoff] [style] - High-pass filter\n"
            f"• /homomorphic [gl] [gh] [cutoff] - Illumination balancing\n"
            f"• /fourier_modulate [freq] [angle] - Fourier modulation theorem visualization\n"
            f"• /fft - Show log-scaled FFT magnitude spectrum\n"
            f"• /dct - Show log-scaled DCT magnitude spectrum\n\n"
            f"⛓️ <b>EVALUATION PIPELINE:</b>\n"
            f"• /image_eval [pipeline] - Sequential processing\n"
            f"  <i>Example: /image_eval grayscale,invert,blur:5</i>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Send any text to chat with me! ✨"
        ) if lang == "en" else (
            f"🤖 <b>Command Bot Telegram RVDiA Zora:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 <b>SISTEM RPG:</b>\n"
            f"• /register - Daftar akun RPG Re:Volution\n"
            f"• /profile  - Lihat info level, koin, kelas, & status\n"
            f"• /class    - Pilih kelas (Warrior/Mage/Rogue)\n"
            f"• /allocate - Alokasi poin status (misal: /allocate ATK 5)\n"
            f"• /daily    - Klaim koin harian gratis dan EXP\n"
            f"• /adventure - Berpetualang untuk hadiah\n"
            f"• /battle   - Pertempuran simulasi cepat melawan musuh PVE\n"
            f"• /worldboss - Lihat status World Boss aktif\n"
            f"• /attack   - Serang World Boss yang sedang aktif\n"
            f"• /lang     - Ganti pengaturan bahasa (en/id)\n\n"
            f"🎨 <b>FILTER GAMBAR (Gunakan sebagai caption foto):</b>\n"
            f"• /grayscale, /invert, /circle, /sepia, /sharpen, /emboss\n"
            f"• /blur [strength] - Terapkan efek box blur\n"
            f"• /pixelate [size] - Terapkan efek retro pixel block\n"
            f"• /vignette [sigma] - Terapkan bayangan vignette\n"
            f"• /gamma [val] - Terapkan koreksi gamma\n"
            f"• /flip [h/v] - Balikkan gambar secara horizontal/vertikal\n"
            f"• /rotate [angle] [cw/ccw] - Putar gambar\n"
            f"• /adjust [bright] [contrast] - Atur kecerahan/kontras\n"
            f"• /edge [method] - Canny/Sobel/Laplacian/Prewitt/Roberts/Scharr\n"
            f"• /noise [type] - Tambah noise (salt_pepper/gaussian/poisson)\n"
            f"• /equalize [method] - Ekualisasi histogram (global/clahe/adaptive)\n"
            f"• /threshold [val] [binary/otsu] - Konversi ke citra biner\n\n"
            f"✨ <b>FILTER ARTISTIK:</b>\n"
            f"• /posterize [levels] - Kuantisasi warna\n"
            f"• /solarize [threshold] - Efek solarisasi\n"
            f"• /sketch [ksize] - Sketsa pensil realistis\n\n"
            f"🔬 <b>MORFOLOGI & FOURIER:</b>\n"
            f"• /erode [iter] [ksize] - Erosi morfologis\n"
            f"• /dilate [iter] [ksize] - Dilatasi morfologis\n"
            f"• /skeleton - Ekstrak kerangka topologi\n"
            f"• /lpf [cutoff] [style] - Low-pass filter (ideal/butterworth/gaussian)\n"
            f"• /hpf [cutoff] [style] - High-pass filter\n"
            f"• /homomorphic [gl] [gh] [cutoff] - Keseimbangan pencahayaan\n"
            f"• /fourier_modulate [freq] [angle] - Visualisasi teorema modulasi Fourier\n"
            f"• /fft - Tampilkan spektrum magnitudo FFT skala log\n"
            f"• /dct - Tampilkan spektrum magnitudo DCT skala log\n\n"
            f"⛓️ <b>EVALUASI PIPELINE:</b>\n"
            f"• /image_eval [pipeline] - Pemrosesan sekuensial\n"
            f"  <i>Contoh: /image_eval grayscale,invert,blur:5</i>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Kirim pesan apapun untuk ngobrol denganku! ✨"
        )
        await send_telegram_message(chat_id, help_msg)

    @zora.default_chat()
    async def handle_default_chat(zora_bot, chat_id, telegram_user_id, username, full_name, text, lang):
        virtual_id = -telegram_user_id
        if telegram_client:
            await telegram_client.send_chat_action(chat_id, "typing")

        try:
            result = await chat_service.generate_chat_response(
                user_id=virtual_id,
                user_name=full_name,
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
