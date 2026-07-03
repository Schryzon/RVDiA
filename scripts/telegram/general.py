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
    async def handle_register(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        success, user = await register_telegram_user(telegram_user_id, full_name, lang)
        if success:
            msg = (
                f"🎉 <b>Registration Successful!</b>\n"
                f"Welcome to Re:Volution dream world, Dreamer <b>{full_name}</b>!\n"
                f"Use /profile to check your initial stats."
            ) if lang == "en" else (
                f"🎉 <b>Pendaftaran Berhasil!</b>\n"
                f"Selamat datang di dunia mimpi Re:Volution, Dreamer <b>{full_name}</b>!\n"
                f"Gunakan /profile untuk melihat statistik awal Anda."
            )
        else:
            msg = (
                f"⚠️ You are already registered."
            ) if lang == "en" else (
                f"⚠️ Akun Anda sudah terdaftar."
            )
        await send_telegram_message(chat_id, msg, thread_id=thread_id)

    @zora.command("/profile")
    async def handle_profile(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id})
        if not user_record:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

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
        await send_telegram_message(chat_id, profile_msg, thread_id=thread_id)

    @zora.command("/lang")
    async def handle_lang(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id})
        if not user_record:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        lang_choice = args[0] if args else None
        if not lang_choice:
            msg = (
                f"⚠️ Please specify a language (en / id)!\n"
                f"Usage: <code>/lang [en|id]</code>"
            ) if lang == "en" else (
                f"⚠️ Harap tentukan bahasa (en / id)!\n"
                f"Penggunaan: <code>/lang [en|id]</code>"
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        lang_choice_lower = lang_choice.lower()
        if lang_choice_lower not in ["en", "id"]:
            msg = (
                f"⚠️ Invalid language! Choose <b>en</b> (English) or <b>id</b> (Indonesian)."
            ) if lang == "en" else (
                f"⚠️ Bahasa tidak valid! Pilih <b>en</b> (Inggris) atau <b>id</b> (Indonesia)."
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

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
        await send_telegram_message(chat_id, success_msg, thread_id=thread_id)

    @zora.command("/help")
    async def handle_help(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, via_mention=False):
        # Build prefix: "@botname " when invoked via mention, "/" otherwise
        bot_name = zora_bot.username or "RVDiA_Official_bot"
        p = f"@{bot_name} " if via_mention else "/"

        help_msg = (
            f"🤖 <b>RVDiA Zora Telegram Command Bot:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 <b>RPG SYSTEM:</b>\n"
            f"• <code>{p}register</code> - Create your RPG account\n"
            f"• <code>{p}profile</code>  - View stats, level, coins, class\n"
            f"• <code>{p}class</code>    - Choose a class (Warrior/Mage/Rogue)\n"
            f"• <code>{p}allocate ATK 5</code> - Allocate stat points\n"
            f"• <code>{p}daily</code>    - Claim daily coins and EXP\n"
            f"• <code>{p}adventure</code> - Explore and earn rewards\n"
            f"• <code>{p}battle [tier]</code> - Fast-simulation PVE combat\n"
            f"• <code>{p}enemies</code>  - Browse enemy bestiary\n"
            f"• <code>{p}worldboss</code> - View active World Boss status\n"
            f"• <code>{p}attack</code>   - Attack the active World Boss\n"
            f"• <code>{p}shop [page]</code> - Browse shop items\n"
            f"• <code>{p}buy [item]</code> - Buy an item from the shop\n"
            f"• <code>{p}inventory [page]</code> - View owned items\n"
            f"• <code>{p}use [item]</code> - Use consumables or equip gear\n"
            f"• <code>{p}sell [item]</code> - Sell owned items\n"
            f"• <code>{p}bond</code>     - Manage your relationship status with RVDiA\n"
            f"  - <code>{p}bond start</code> - Start relationship\n"
            f"  - <code>{p}bond nickname [user/rvdia] [name]</code> - Set nicknames\n"
            f"  - <code>{p}bond gift</code> - Send gifts to increase affinity\n"
            f"  - <code>{p}bond reset</code> - Reset relationship status\n"
            f"• <code>{p}ocr</code>      - Read text from image or PDF document\n"
            f"• <code>{p}remind [time] [msg]</code> - Set a sleep/wake reminder\n"
            f"• <code>{p}lang [en|id]</code> - Change language settings\n\n"
            f"🔮 <b>FUN & UTILITY:</b>\n"
            f"• <code>{p}ship [name1] [name2]</code> - Test love compatibility\n"
            f"• <code>{p}8ball [question]</code> - Magic 8-Ball response\n"
            f"• <code>{p}roll [notation]</code> - Roll dice (e.g., 2d10)\n"
            f"• <code>{p}coinflip</code> - Flip a coin\n"
            f"• <code>{p}weather [location]</code> - Check current weather\n"
            f"• <code>{p}time [location]</code> - Check timezone time\n"
            f"• <code>{p}map [location]</code> - Show interactive Google Maps card\n"
            f"• <code>{p}hex [code]</code> / <code>{p}rgb [r g b]</code> - Preview a color\n"
            f"• <code>{p}search [query]</code> - Search DuckDuckGo\n\n"
            f"🎬 <b>ROLEPLAY ACTIONS:</b>\n"
            f"• <code>{p}hug</code>, <code>{p}kiss</code>, <code>{p}slap</code>, <code>{p}pat</code>, <code>{p}blush</code>, <code>{p}cry</code>, <code>{p}laugh</code>, <code>{p}happy</code>, <code>{p}think</code>, <code>{p}agree</code>, <code>{p}bored</code>\n\n"
            f"🎨 <b>IMAGE FILTERS (Use as photo caption):</b>\n"
            f"• <code>{p}grayscale</code>, <code>{p}invert</code>, <code>{p}circle</code>, <code>{p}sepia</code>, <code>{p}sharpen</code>, <code>{p}emboss</code>\n"
            f"• <code>{p}blur [strength]</code> - Apply box blur\n"
            f"• <code>{p}pixelate [size]</code> - Apply retro pixel block effect\n"
            f"• <code>{p}vignette [sigma]</code> - Apply vignette shading\n"
            f"• <code>{p}gamma [val]</code> - Apply gamma correction\n"
            f"• <code>{p}flip [h/v]</code> - Flip image horizontally or vertically\n"
            f"• <code>{p}rotate [angle] [cw/ccw]</code> - Rotate image\n"
            f"• <code>{p}adjust [bright] [contrast]</code> - Adjust brightness/contrast\n"
            f"• <code>{p}edge [method]</code> - Canny/Sobel/Laplacian/Prewitt/Roberts/Scharr\n"
            f"• <code>{p}noise [type]</code> - Add noise (salt_pepper/gaussian/poisson)\n"
            f"• <code>{p}equalize [method]</code> - Histogram equalize (global/clahe/adaptive)\n"
            f"• <code>{p}threshold [val] [binary/otsu]</code> - Convert to binary image\n\n"
            f"✨ <b>ARTISTIC FILTERS:</b>\n"
            f"• <code>{p}posterize [levels]</code> - Color quantization\n"
            f"• <code>{p}solarize [threshold]</code> - Solarization effect\n"
            f"• <code>{p}sketch [ksize]</code> - Realistic pencil sketch\n\n"
            f"🔬 <b>MORPHOLOGY & FOURIER:</b>\n"
            f"• <code>{p}erode [iter] [ksize]</code> - Morphological erosion\n"
            f"• <code>{p}dilate [iter] [ksize]</code> - Morphological dilation\n"
            f"• <code>{p}skeleton</code> - Extract topological skeleton\n"
            f"• <code>{p}lpf [cutoff] [style]</code> - Low-pass filter (ideal/butterworth/gaussian)\n"
            f"• <code>{p}hpf [cutoff] [style]</code> - High-pass filter\n"
            f"• <code>{p}homomorphic [gl] [gh] [cutoff]</code> - Illumination balancing\n"
            f"• <code>{p}fourier_modulate [freq] [angle]</code> - Fourier modulation theorem\n"
            f"• <code>{p}fft</code> - Show log-scaled FFT magnitude spectrum\n"
            f"• <code>{p}dct</code> - Show log-scaled DCT magnitude spectrum\n\n"
            f"⛓️ <b>EVALUATION PIPELINE:</b>\n"
            f"• <code>{p}image_eval [pipeline]</code> - Sequential processing\n"
            f"  <i>Example: {p}image_eval grayscale,invert,blur:5</i>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Send any text to chat with me! ✨"
        ) if lang == "en" else (
            f"🤖 <b>Command Bot Telegram RVDiA Zora:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 <b>SISTEM RPG:</b>\n"
            f"• <code>{p}register</code> - Daftar akun RPG Re:Volution\n"
            f"• <code>{p}profile</code>  - Lihat info level, koin, kelas, & status\n"
            f"• <code>{p}class</code>    - Pilih kelas (Warrior/Mage/Rogue)\n"
            f"• <code>{p}allocate ATK 5</code> - Alokasi poin status\n"
            f"• <code>{p}daily</code>    - Klaim koin harian gratis dan EXP\n"
            f"• <code>{p}adventure</code> - Berpetualang untuk hadiah\n"
            f"• <code>{p}battle [tier]</code> - Pertempuran simulasi cepat melawan musuh PVE\n"
            f"• <code>{p}enemies</code>  - Lihat bestiari musuh\n"
            f"• <code>{p}worldboss</code> - Lihat status World Boss aktif\n"
            f"• <code>{p}attack</code>   - Serang World Boss yang sedang aktif\n"
            f"• <code>{p}shop [page]</code> - Lihat item toko\n"
            f"• <code>{p}buy [item]</code> - Beli item dari toko\n"
            f"• <code>{p}inventory [page]</code> - Lihat item yang dimiliki\n"
            f"• <code>{p}use [item]</code> - Pakai consumable atau pasang gear\n"
            f"• <code>{p}sell [item]</code> - Jual item yang dimiliki\n"
            f"• <code>{p}bond</code>     - Kelola hubungan dan kedekatanmu dengan RVDiA\n"
            f"  - <code>{p}bond start</code> - Mulai hubungan kedekatan\n"
            f"  - <code>{p}bond nickname [user/rvdia] [nama]</code> - Ganti nama panggilan\n"
            f"  - <code>{p}bond gift</code> - Beri hadiah untuk meningkatkan kedekatan\n"
            f"  - <code>{p}bond reset</code> - Atur ulang status hubungan\n"
            f"• <code>{p}ocr</code>      - Ekstrak teks dari gambar atau dokumen PDF\n"
            f"• <code>{p}remind [time] [msg]</code> - Atur pengingat waktu tidur/bangun\n"
            f"• <code>{p}lang [en|id]</code> - Ganti pengaturan bahasa\n\n"
            f"🔮 <b>HIBURAN & UTILITAS:</b>\n"
            f"• <code>{p}ship [name1] [name2]</code> - Cek kecocokan cinta antarnama\n"
            f"• <code>{p}8ball [question]</code> - Jawaban dari bola ramalan 8-Ball\n"
            f"• <code>{p}roll [notation]</code> - Lempar dadu (contoh: 2d10)\n"
            f"• <code>{p}coinflip</code> - Lempar koin acak\n"
            f"• <code>{p}weather [location]</code> - Cek perkiraan cuaca saat ini\n"
            f"• <code>{p}time [location]</code> - Cek waktu di zona waktu tertentu\n"
            f"• <code>{p}map [location]</code> - Tampilkan kartu interaktif Google Maps\n"
            f"• <code>{p}hex [code]</code> / <code>{p}rgb [r g b]</code> - Pratinjau kode warna HEX atau RGB\n"
            f"• <code>{p}search [query]</code> - Cari informasi di DuckDuckGo\n\n"
            f"🎬 <b>AKSI ROLEPLAY:</b>\n"
            f"• <code>{p}hug</code>, <code>{p}kiss</code>, <code>{p}slap</code>, <code>{p}pat</code>, <code>{p}blush</code>, <code>{p}cry</code>, <code>{p}laugh</code>, <code>{p}happy</code>, <code>{p}think</code>, <code>{p}agree</code>, <code>{p}bored</code>\n\n"
            f"🎨 <b>FILTER GAMBAR (Gunakan sebagai caption foto):</b>\n"
            f"• <code>{p}grayscale</code>, <code>{p}invert</code>, <code>{p}circle</code>, <code>{p}sepia</code>, <code>{p}sharpen</code>, <code>{p}emboss</code>\n"
            f"• <code>{p}blur [strength]</code> - Terapkan efek box blur\n"
            f"• <code>{p}pixelate [size]</code> - Terapkan efek retro pixel block\n"
            f"• <code>{p}vignette [sigma]</code> - Terapkan bayangan vignette\n"
            f"• <code>{p}gamma [val]</code> - Terapkan koreksi gamma\n"
            f"• <code>{p}flip [h/v]</code> - Balikkan gambar secara horizontal/vertikal\n"
            f"• <code>{p}rotate [angle] [cw/ccw]</code> - Putar gambar\n"
            f"• <code>{p}adjust [bright] [contrast]</code> - Atur kecerahan/kontras\n"
            f"• <code>{p}edge [method]</code> - Deteksi tepi (Canny/Sobel/Laplacian/Prewitt/Roberts/Scharr)\n"
            f"• <code>{p}noise [type]</code> - Tambah noise (salt_pepper/gaussian/poisson)\n"
            f"• <code>{p}equalize [method]</code> - Ekualisasi histogram (global/clahe/adaptive)\n"
            f"• <code>{p}threshold [val] [binary/otsu]</code> - Konversi ke citra biner\n\n"
            f"✨ <b>FILTER ARTISTIK:</b>\n"
            f"• <code>{p}posterize [levels]</code> - Kuantisasi warna\n"
            f"• <code>{p}solarize [threshold]</code> - Efek solarisasi\n"
            f"• <code>{p}sketch [ksize]</code> - Sketsa pensil realistis\n\n"
            f"🔬 <b>MORFOLOGI & FOURIER:</b>\n"
            f"• <code>{p}erode [iter] [ksize]</code> - Erosi morfologis\n"
            f"• <code>{p}dilate [iter] [ksize]</code> - Dilatasi morfologis\n"
            f"• <code>{p}skeleton</code> - Ekstrak kerangka topologi\n"
            f"• <code>{p}lpf [cutoff] [style]</code> - Low-pass filter (ideal/butterworth/gaussian)\n"
            f"• <code>{p}hpf [cutoff] [style]</code> - High-pass filter\n"
            f"• <code>{p}homomorphic [gl] [gh] [cutoff]</code> - Keseimbangan pencahayaan\n"
            f"• <code>{p}fourier_modulate [freq] [angle]</code> - Visualisasi teorema modulasi Fourier\n"
            f"• <code>{p}fft</code> - Tampilkan spektrum magnitudo FFT skala log\n"
            f"• <code>{p}dct</code> - Tampilkan spektrum magnitudo DCT skala log\n\n"
            f"⛓️ <b>EVALUASI PIPELINE:</b>\n"
            f"• <code>{p}image_eval [pipeline]</code> - Pemrosesan sekuensial\n"
            f"  <i>Contoh: {p}image_eval grayscale,invert,blur:5</i>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Kirim pesan apapun untuk ngobrol denganku! ✨"
        )
        await send_telegram_message(chat_id, help_msg, thread_id=thread_id)


    @zora.default_chat()
    async def handle_default_chat(zora_bot, chat_id, telegram_user_id, username, full_name, text, lang, thread_id=None):
        virtual_id = -telegram_user_id
        if telegram_client:
            await telegram_client.send_chat_action(chat_id, "typing", message_thread_id=thread_id)

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
                await send_telegram_photo(chat_id, image_url, caption=response_text, thread_id=thread_id)
            else:
                await send_telegram_message(chat_id, response_text, thread_id=thread_id)
        except Exception as e:
            logging.error(f"Error generating Gemini response for Telegram: {e}", exc_info=True)
            err_msg = "⚠️ Apologies, I encountered an error in the dream world." if lang == "en" else "⚠️ Waduh, terjadi kesalahan saat mengakses dunia mimpi."
            await send_telegram_message(chat_id, err_msg, thread_id=thread_id)
