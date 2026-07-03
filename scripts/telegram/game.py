import random
import json
import difflib
import math
from os import path
from datetime import datetime, timedelta, timezone
from prisma import Json
from scripts.main import db
from scripts.game.game import level_up, give_rewards, send_level_up_msg, split_reward_string
from scripts.utils.telegram import TelegramMockCtx, TelegramMockMember, send_telegram_message, send_telegram_photo, telegram_client
from scripts.utils.i18n import i18n

def to_key(name: str) -> str:
    import re
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s_]', '', name)
    name = re.sub(r'[\s_]+', '_', name)
    return name


SHOP_PAGE_SIZE = 5


def _load_shop_items() -> list:
    shop_path = path.join(path.dirname(__file__), '..', '..', 'src', 'game', 'shop.json')
    with open(shop_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def _item_name(lang: str, item: dict) -> str:
    return i18n.get(lang, f"game.item_{item['_id']}_name", default=item.get('name', item.get('_id', 'Item')))


def _item_desc(lang: str, item: dict) -> str:
    return i18n.get(lang, f"game.item_{item['_id']}_desc", default=item.get('desc', 'No description.'))


def _currency_name(lang: str, paywith: str) -> str:
    if paywith == "Koin":
        return "Coins" if lang == "en" else "Koin"
    return "Karma"


def _find_shop_item(items: list, query: str) -> dict | None:
    if not query:
        return None

    query_norm = query.strip().lower()
    if not query_norm:
        return None

    for item in items:
        if item.get('_id', '').lower() == query_norm or item.get('name', '').lower() == query_norm:
            return item

    for item in items:
        if query_norm in item.get('_id', '').lower() or query_norm in item.get('name', '').lower():
            return item

    item_names = [item.get('name', '') for item in items]
    matches = difflib.get_close_matches(query, item_names, n=1, cutoff=0.45)
    if matches:
        for item in items:
            if item.get('name') == matches[0]:
                return item

    return None


def _parse_amount(args: list, default: int = 1) -> tuple[str | None, int]:
    if not args:
        return None, default

    amount = default
    query_args = list(args)
    if len(query_args) > 1 and query_args[-1].isdigit():
        amount = max(1, int(query_args.pop()))

    return " ".join(query_args).strip(), amount


def _owned_item_lookup(inventory_items: list, item_id: str) -> tuple[int, dict | None]:
    for idx, item in enumerate(inventory_items):
        if item.get('_id') == item_id and item.get('owned', 0) > 0:
            return idx, item
    return -1, None


def _apply_func_to_player(data: dict, hp: int, max_hp: int, func: str, scale: int = 1) -> tuple[dict, int, str]:
    parsed = func.lower().replace(" ", "")
    if not parsed:
        return data, hp, "ok"

    if "+" in parsed:
        key, raw_val = parsed.split("+", 1)
        sign = 1
    elif "-" in parsed:
        key, raw_val = parsed.split("-", 1)
        sign = -1
    else:
        return data, hp, "unsupported"

    is_percent = raw_val.endswith("%")
    amount = raw_val[:-1] if is_percent else raw_val
    try:
        value = int(amount)
    except ValueError:
        return data, hp, "unsupported"

    delta = scale * sign * value
    if is_percent:
        delta = scale * sign * round(max_hp * (value / 100))

    if key == "atk":
        data["attack"] = data.get("attack", 10) + delta
    elif key == "def":
        data["defense"] = data.get("defense", 7) + delta
    elif key == "agl":
        data["agility"] = data.get("agility", 8) + delta
    elif key == "all":
        data["attack"] = data.get("attack", 10) + delta
        data["defense"] = data.get("defense", 7) + delta
        data["agility"] = data.get("agility", 8) + delta
    elif key == "hp":
        hp = max(0, min(max_hp, hp + delta))
    elif key == "exp":
        data["exp"] = data.get("exp", 0) + delta
    else:
        return data, hp, "unsupported"

    return data, hp, "ok"


def _format_shop_entry(index: int, item: dict, lang: str) -> str:
    name = _item_name(lang, item)
    desc = _item_desc(lang, item)
    currency = _currency_name(lang, item.get('paywith', 'Koin'))
    return (
        f"{index}. <b>{name}</b>\n"
        f"   <i>{desc}</i>\n"
        f"   {item.get('type', 'Item')} • {item.get('func', '???')} • {item.get('cost', 0)} {currency}"
    )


def _format_inventory_entry(index: int, item: dict, lang: str, equipped: bool = False) -> str:
    name = _item_name(lang, item)
    qty = item.get('owned', 1)
    func = item.get('func', '???')
    type_name = item.get('type', 'Item')
    slot = item.get('usefor', '')
    suffix = f" • {slot}" if slot else ""
    if equipped:
        suffix += " • Equipped" if lang == "en" else " • Dipakai"
    return f"{index}. <b>{name}</b> x{qty}\n   <i>{type_name}</i>{suffix}\n   <code>{func}</code>"


def _inventory_matches(user_items: list, user_skills: list, user_equipments: list, item_id: str) -> tuple[str | None, int, dict | None]:
    for idx, item in enumerate(user_items):
        if item.get('_id') == item_id and item.get('owned', 0) > 0:
            return "items", idx, item
    for idx, item in enumerate(user_skills):
        if item.get('_id') == item_id and item.get('owned', 0) > 0:
            return "skills", idx, item
    for idx, item in enumerate(user_equipments):
        if item.get('_id') == item_id and item.get('owned', 0) > 0:
            return "equipments", idx, item
    return None, -1, None

def setup(zora):
    @zora.command("/daily")
    async def handle_daily(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id})
        if not user_record:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

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
            return await send_telegram_message(chat_id, cooldown_msg, thread_id=thread_id)

        new_coins = random.randint(15, 25)
        new_karma = random.randint(1, 5)
        new_exp = random.randint(10, 20)

        is_premium = user_record.premiumUntil and user_record.premiumUntil > datetime.now(timezone.utc)
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
        await send_telegram_message(chat_id, success_msg, thread_id=thread_id)

    @zora.command("/adventure")
    async def handle_adventure(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id})
        if not user_record:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

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
        await send_telegram_message(chat_id, success_msg, thread_id=thread_id)

    @zora.command("/class")
    async def handle_class(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id})
        if not user_record:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        data = user_record.data
        current_class = data.get('class', 'None')
        if current_class != 'None':
            msg = (
                f"⚠️ You have already selected a class: <b>{current_class}</b>!"
            ) if lang == "en" else (
                f"⚠️ Anda sudah memilih kelas: <b>{current_class}</b>!"
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        class_name = args[0] if args else None
        if not class_name:
            msg = (
                f"⚠️ Please specify a class!\n"
                f"Usage: <code>/class [warrior|mage|rogue]</code>"
            ) if lang == "en" else (
                f"⚠️ Harap tentukan kelas!\n"
                f"Penggunaan: <code>/class [warrior|mage|rogue]</code>"
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        class_name_lower = class_name.lower()
        if class_name_lower not in ["warrior", "mage", "rogue"]:
            msg = (
                f"⚠️ Invalid class! Choose between: <b>Warrior</b>, <b>Mage</b>, or <b>Rogue</b>."
            ) if lang == "en" else (
                f"⚠️ Kelas tidak valid! Pilih antara: <b>Warrior</b>, <b>Mage</b>, atau <b>Rogue</b>."
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        hp_adjustment = 0
        atk_adjustment = 0
        def_adjustment = 0
        agl_adjustment = 0
        
        if class_name_lower == "warrior":
            hp_adjustment = 30
            atk_adjustment = 5
            def_adjustment = 3
            class_display = "Warrior"
        elif class_name_lower == "mage":
            hp_adjustment = -10
            atk_adjustment = 10
            agl_adjustment = 2
            class_display = "Mage"
        elif class_name_lower == "rogue":
            hp_adjustment = 10
            atk_adjustment = 3
            agl_adjustment = 8
            class_display = "Rogue"
            
        data['class'] = class_display
        data['attack'] = data.get('attack', 10) + atk_adjustment
        data['defense'] = data.get('defense', 7) + def_adjustment
        data['agility'] = data.get('agility', 8) + agl_adjustment
        
        level = data.get('level', 1)
        retroactive_points = (level - 1) * 5
        data['stat_points'] = data.get('stat_points', 0) + retroactive_points
        
        new_max_hp = user_record.max_hp + hp_adjustment
        new_hp = min(user_record.hp, new_max_hp)
        
        await db.user.update(
            where={'id': virtual_id},
            data={
                'max_hp': new_max_hp,
                'hp': new_hp,
                'data': Json(data)
            }
        )
        
        msg = (
            f"🎉 <b>Class Selection Successful!</b>\n"
            f"Welcome to the path of the <b>{class_display}</b>!\n\n"
            f"📈 <b>Stat Adjustments:</b>\n"
            f"• Max HP: {hp_adjustment:+}\n"
            f"• ATK: {atk_adjustment:+}\n"
            f"• DEF: {def_adjustment:+}\n"
            f"• AGI: {agl_adjustment:+}\n\n"
            f"✨ Retroactive stat points granted: <b>{retroactive_points}</b>\n"
            f"Use /profile to check your updated stats!"
        ) if lang == "en" else (
            f"🎉 <b>Pemilihan Kelas Berhasil!</b>\n"
            f"Selamat datang di jalur <b>{class_display}</b>!\n\n"
            f"📈 <b>Penyesuaian Status:</b>\n"
            f"• Max HP: {hp_adjustment:+}\n"
            f"• ATK: {atk_adjustment:+}\n"
            f"• DEF: {def_adjustment:+}\n"
            f"• AGI: {agl_adjustment:+}\n\n"
            f"✨ Poin status retroaktif diberikan: <b>{retroactive_points}</b>\n"
            f"Gunakan /profile untuk melihat status terbaru Anda!"
        )
        await send_telegram_message(chat_id, msg, thread_id=thread_id)

    @zora.command("/allocate")
    async def handle_allocate(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id})
        if not user_record:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        stat_name = args[0] if args else None
        amount_str = args[1] if len(args) > 1 else "1"

        if not stat_name:
            msg = (
                f"⚠️ Please specify a stat type (ATK, DEF, AGL)!\n"
                f"Usage: <code>/allocate [ATK|DEF|AGL] [amount]</code>"
            ) if lang == "en" else (
                f"⚠️ Harap tentukan tipe status (ATK, DEF, AGL)!\n"
                f"Penggunaan: <code>/allocate [ATK|DEF|AGL] [jumlah]</code>"
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        stat_str = stat_name.upper()
        if stat_str not in ["ATK", "DEF", "AGL"]:
            msg = (
                f"⚠️ Invalid stat type! Choose between: <b>ATK</b>, <b>DEF</b>, or <b>AGL</b>."
            ) if lang == "en" else (
                f"⚠️ Tipe status tidak valid! Pilih antara: <b>ATK</b>, <b>DEF</b>, atau <b>AGL</b>."
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        try:
            amount = int(amount_str)
        except ValueError:
            amount = 1

        if amount <= 0:
            msg = (
                f"⚠️ Amount must be greater than 0!"
            ) if lang == "en" else (
                f"⚠️ Jumlah alokasi harus lebih dari 0!"
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        data = user_record.data
        available_points = data.get('stat_points', 0)
        if available_points < amount:
            msg = (
                f"⚠️ Insufficient stat points! You have <b>{available_points}</b> points available."
            ) if lang == "en" else (
                f"⚠️ Poin status tidak cukup! Anda hanya memiliki <b>{available_points}</b> poin."
            )
            return await send_telegram_message(chat_id, msg)

        if stat_str == "ATK":
            data['attack'] = data.get('attack', 10) + amount
            stat_display = "ATK"
        elif stat_str == "DEF":
            data['defense'] = data.get('defense', 7) + amount
            stat_display = "DEF"
        elif stat_str == "AGL":
            data['agility'] = data.get('agility', 8) + amount
            stat_display = "AGI"

        data['stat_points'] = available_points - amount

        await db.user.update(
            where={'id': virtual_id},
            data={'data': Json(data)}
        )

        msg = (
            f"✅ Allocated <b>{amount}</b> points to <b>{stat_display}</b>!\n"
            f"Remaining unspent points: <b>{data['stat_points']}</b>"
        ) if lang == "en" else (
            f"✅ Mengalokasikan <b>{amount}</b> poin ke <b>{stat_display}</b>!\n"
            f"Sisa poin status: <b>{data['stat_points']}</b>"
        )
        await send_telegram_message(chat_id, msg, thread_id=thread_id)

    @zora.command(["/shop", "/store", "/toko"])
    async def handle_shop(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        page = 1
        if args and args[0].isdigit():
            page = max(1, int(args[0]))

        items = _load_shop_items()
        total_pages = max(1, (len(items) - 1) // SHOP_PAGE_SIZE + 1)
        page = min(page, total_pages)
        start = (page - 1) * SHOP_PAGE_SIZE
        page_items = items[start:start + SHOP_PAGE_SIZE]

        header = "🛍️ <b>Xaneria Shop</b>" if lang == "en" else "🛍️ <b>Toko Xaneria</b>"
        lines = [
            header,
            "━━━━━━━━━━━━━━━━━━━",
            i18n.get(lang, "game.shop_desc"),
            "",
        ]

        for idx, item in enumerate(page_items, start=start + 1):
            lines.append(_format_shop_entry(idx, item, lang))

        footer = (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Page {page}/{total_pages}\n"
            f"Use <code>/buy [item name]</code> to purchase."
        ) if lang == "en" else (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Halaman {page}/{total_pages}\n"
            f"Gunakan <code>/buy [nama item]</code> untuk membeli."
        )
        lines.append(footer)
        await send_telegram_message(chat_id, "\n".join(lines), thread_id=thread_id)

    @zora.command(["/buy", "/beli"])
    async def handle_buy(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            msg = i18n.get(lang, "game.use_not_registered")
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        item_query, amount = _parse_amount(args, default=1)
        if not item_query:
            msg = "Use <code>/buy [item name]</code>." if lang == "en" else "Gunakan <code>/buy [nama item]</code>."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        items = _load_shop_items()
        matched = _find_shop_item(items, item_query)
        if not matched:
            msg = "Item not found in shop!" if lang == "en" else "Item tidak ditemukan di toko!"
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        if matched.get('type') in {"Skill", "Equipment"}:
            amount = 1

        data = user_record.data
        currency_key = 'coins' if matched.get('paywith') == "Koin" else 'karma'
        total_cost = matched.get('cost', 0) * amount
        if data.get(currency_key, 0) < total_cost:
            currency = _currency_name(lang, matched.get('paywith', 'Koin'))
            msg = (
                f"⚠️ You don't have enough {currency.lower()} to buy this item."
                if lang == "en"
                else f"⚠️ Koin/Karma-mu tidak cukup untuk membeli item ini."
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        inventory = user_record.inventory
        user_items = inventory.items if isinstance(inventory.items, list) else []
        user_skills = inventory.skills if isinstance(inventory.skills, list) else []
        user_equipments = inventory.equipments if isinstance(inventory.equipments, list) else []

        item_id = matched['_id']
        item_name = _item_name(lang, matched)

        if matched.get('type') == "Skill":
            _, _, already_owned = _inventory_matches(user_items, user_skills, user_equipments, item_id)
            if already_owned:
                msg = i18n.get(lang, "game.shop_skill_learned")
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            new_item = dict(matched)
            new_item['owned'] = 1
            user_skills.append(new_item)
            inventory_update = {'skills': Json(user_skills)}

        else:
            _, _, already_owned = _inventory_matches(user_items, user_skills, user_equipments, item_id)
            if matched.get('type') == "Equipment" and already_owned:
                msg = i18n.get(lang, "game.shop_equipment_bought")
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            if matched.get('type') == "Equipment":
                new_item = dict(matched)
                new_item['owned'] = 1
                user_items.append(new_item)
                inventory_update = {'items': Json(user_items)}
            else:
                item_index, current_item = _owned_item_lookup(user_items, item_id)
                if current_item:
                    user_items[item_index]['owned'] = current_item.get('owned', 0) + amount
                else:
                    new_item = dict(matched)
                    new_item['owned'] = amount
                    user_items.append(new_item)
                inventory_update = {'items': Json(user_items)}

        data[currency_key] = data.get(currency_key, 0) - total_cost
        await db.user.update(
            where={'id': virtual_id},
            data={
                'data': Json(data),
                'inventory': {'update': inventory_update}
            }
        )

        currency = _currency_name(lang, matched.get('paywith', 'Koin'))
        success_msg = (
            f"✅ Purchase successful!\nBought <b>{item_name}</b> x{amount} for <code>{total_cost}</code> {currency}."
            if lang == "en" else
            f"✅ Pembelian berhasil!\nKamu membeli <b>{item_name}</b> x{amount} seharga <code>{total_cost}</code> {currency}."
        )
        await send_telegram_message(chat_id, success_msg, thread_id=thread_id)

    @zora.command(["/inventory", "/inv", "/items"])
    async def handle_inventory(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            msg = i18n.get(lang, "game.use_not_registered")
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        page = 1
        if args and args[0].isdigit():
            page = max(1, int(args[0]))

        inventory = user_record.inventory
        user_items = inventory.items if isinstance(inventory.items, list) else []
        user_skills = inventory.skills if isinstance(inventory.skills, list) else []
        user_equipments = inventory.equipments if isinstance(inventory.equipments, list) else []

        entries = []
        for item in user_items:
            if item.get('owned', 0) > 0:
                entries.append((item, False))
        for item in user_skills:
            if item.get('owned', 0) > 0:
                entries.append((item, False))
        for item in user_equipments:
            if item.get('owned', 0) > 0:
                entries.append((item, True))

        if not entries:
            msg = "🎒 Your inventory is empty." if lang == "en" else "🎒 Inventorimu kosong."
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        total_pages = max(1, (len(entries) - 1) // 10 + 1)
        page = min(page, total_pages)
        start = (page - 1) * 10
        page_entries = entries[start:start + 10]

        title = "🎒 <b>Your Inventory</b>" if lang == "en" else "🎒 <b>Inventorimu</b>"
        lines = [title, "━━━━━━━━━━━━━━━━━━━"]
        for idx, (item, equipped) in enumerate(page_entries, start=start + 1):
            lines.append(_format_inventory_entry(idx, item, lang, equipped=equipped))

        footer = (
            f"━━━━━━━━━━━━━━━━━━━\nPage {page}/{total_pages}\n"
            f"Use <code>/use [item name]</code> or <code>/sell [item name]</code>."
        ) if lang == "en" else (
            f"━━━━━━━━━━━━━━━━━━━\nHalaman {page}/{total_pages}\n"
            f"Gunakan <code>/use [nama item]</code> atau <code>/sell [nama item]</code>."
        )
        lines.append(footer)
        await send_telegram_message(chat_id, "\n".join(lines), thread_id=thread_id)

    @zora.command(["/use", "/pakai"])
    async def handle_use_item(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            msg = i18n.get(lang, "game.use_not_registered")
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        item_query = " ".join(args).strip()
        if not item_query:
            msg = "Use <code>/inventory</code> first, then <code>/use [item name]</code>." if lang == "en" else "Gunakan <code>/inventory</code> dulu, lalu <code>/use [nama item]</code>."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        items = _load_shop_items()
        matched = _find_shop_item(items, item_query)
        if not matched:
            msg = "Item not found in your shop list." if lang == "en" else "Item tidak ditemukan di daftar toko."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        inventory = user_record.inventory
        user_items = inventory.items if isinstance(inventory.items, list) else []
        user_skills = inventory.skills if isinstance(inventory.skills, list) else []
        user_equipments = inventory.equipments if isinstance(inventory.equipments, list) else []

        item_id = matched['_id']
        item_type = matched.get('type', 'Consumable')
        data = user_record.data
        hp = user_record.hp
        max_hp = user_record.max_hp

        if item_type == "Equipment":
            equipped_index = next((idx for idx, item in enumerate(user_equipments) if item.get('_id') == item_id), -1)
            if equipped_index >= 0:
                equipped_item = user_equipments.pop(equipped_index)
                data, hp, status = _apply_func_to_player(data, hp, max_hp, equipped_item.get('func', ''), scale=-1)
                if status != "ok":
                    msg = "This equipment cannot be unequipped here." if lang == "en" else "Equipment ini tidak bisa dilepas di sini."
                    return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

                user_items.append(equipped_item)
                await db.user.update(
                    where={'id': virtual_id},
                    data={'hp': hp, 'data': Json(data)}
                )
                await db.inventory.update(
                    where={'userId': virtual_id},
                    data={'items': Json(user_items), 'equipments': Json(user_equipments)}
                )
                item_name = _item_name(lang, matched)
                msg = i18n.get(lang, "game.use_unequip_success", name=item_name)
                return await send_telegram_message(chat_id, msg, thread_id=thread_id)

            item_index, owned_item = _owned_item_lookup(user_items, item_id)
            if not owned_item:
                msg = i18n.get(lang, "game.use_not_found")
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            slot = matched.get('usefor')
            replaced_index = next(
                (idx for idx, item in enumerate(user_equipments) if item.get('usefor') == slot),
                -1
            )
            if replaced_index >= 0:
                replaced_item = user_equipments.pop(replaced_index)
                data, hp, status = _apply_func_to_player(data, hp, max_hp, replaced_item.get('func', ''), scale=-1)
                if status != "ok":
                    msg = "This equipment cannot be equipped here." if lang == "en" else "Equipment ini tidak bisa dipakai di sini."
                    return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)
                user_items.append(replaced_item)

            equipped_item = dict(owned_item)
            user_items.pop(item_index)
            user_equipments.append(equipped_item)
            data, hp, status = _apply_func_to_player(data, hp, max_hp, equipped_item.get('func', ''), scale=1)
            if status != "ok":
                msg = "This equipment cannot be equipped here." if lang == "en" else "Equipment ini tidak bisa dipakai di sini."
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            await db.user.update(
                where={'id': virtual_id},
                data={'hp': hp, 'data': Json(data)}
            )
            await db.inventory.update(
                where={'userId': virtual_id},
                data={'items': Json(user_items), 'equipments': Json(user_equipments)}
            )

            item_name = _item_name(lang, matched)
            msg = i18n.get(lang, "game.use_equip_success", name=item_name)
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        if item_type == "Skill":
            item_index, owned_item = _inventory_matches(user_items, user_skills, user_equipments, item_id)[1:]
            if owned_item is None:
                msg = i18n.get(lang, "game.use_not_found")
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            func = owned_item.get('func', '')
            if func.startswith("dmg"):
                msg = "Battle-only skill. Use it during /battle." if lang == "en" else "Skill ini hanya bisa dipakai saat battle. Gunakan saat /battle."
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            data, hp, status = _apply_func_to_player(data, hp, max_hp, func)
            if status != "ok":
                msg = "This skill cannot be used here." if lang == "en" else "Skill ini tidak bisa dipakai di sini."
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            if owned_item.get('owned', 0) > 1:
                user_skills[item_index]['owned'] -= 1
            else:
                user_skills.pop(item_index)

            await db.user.update(
                where={'id': virtual_id},
                data={'hp': hp, 'data': Json(data)}
            )
            await db.inventory.update(
                where={'userId': virtual_id},
                data={'skills': Json(user_skills)}
            )

            item_name = _item_name(lang, matched)
            msg = i18n.get(lang, "game.use_skill_success", user=f"@{username}" if username else full_name, skill=item_name, func=func.upper())
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        item_index, owned_item = _owned_item_lookup(user_items, item_id)
        if not owned_item:
            msg = i18n.get(lang, "game.use_not_found")
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        data, hp, status = _apply_func_to_player(data, hp, max_hp, owned_item.get('func', ''))
        if status != "ok":
            msg = "This item cannot be used here." if lang == "en" else "Item ini tidak bisa dipakai di sini."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        if owned_item.get('owned', 0) > 1:
            user_items[item_index]['owned'] -= 1
        else:
            user_items.pop(item_index)

        await db.user.update(
            where={'id': virtual_id},
            data={'hp': hp, 'data': Json(data)}
        )
        await db.inventory.update(
            where={'userId': virtual_id},
            data={'items': Json(user_items)}
        )

        item_name = _item_name(lang, matched)
        msg = i18n.get(lang, "game.use_item_success", user=f"@{username}" if username else full_name, item=item_name, func=owned_item.get('func', '').upper())
        await send_telegram_message(chat_id, msg, thread_id=thread_id)

    @zora.command(["/sell", "/jual"])
    async def handle_sell_item(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            msg = i18n.get(lang, "game.use_not_registered")
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        item_query = " ".join(args).strip()
        if not item_query:
            msg = "Use <code>/sell [item name]</code>." if lang == "en" else "Gunakan <code>/sell [nama item]</code>."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        items = _load_shop_items()
        matched = _find_shop_item(items, item_query)
        if not matched:
            msg = "Item not found in your inventory." if lang == "en" else "Item tidak ditemukan di inventarimu."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        if matched.get('type') == "Skill":
            msg = "Skills cannot be sold here." if lang == "en" else "Skill tidak bisa dijual di sini."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        inventory = user_record.inventory
        user_items = inventory.items if isinstance(inventory.items, list) else []
        user_equipments = inventory.equipments if isinstance(inventory.equipments, list) else []

        item_id = matched['_id']
        item_index = -1
        target_item = None
        source = "items"
        for idx, item in enumerate(user_items):
            if item.get('_id') == item_id and item.get('owned', 0) > 0:
                item_index = idx
                target_item = item
                source = "items"
                break
        if item_index < 0:
            for idx, item in enumerate(user_equipments):
                if item.get('_id') == item_id and item.get('owned', 0) > 0:
                    item_index = idx
                    target_item = item
                    source = "equipments"
                    break

        if not target_item:
            msg = i18n.get(lang, "game.use_not_found")
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        sale_value = max(1, round(matched.get('cost', 0) * 0.5))
        data = user_record.data
        hp = user_record.hp
        data['coins'] = data.get('coins', 0) + sale_value

        if source == "equipments":
            data, hp, status = _apply_func_to_player(data, hp, user_record.max_hp, target_item.get('func', ''), scale=-1)
            if status != "ok":
                msg = "This equipment cannot be sold here." if lang == "en" else "Equipment ini tidak bisa dijual di sini."
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        if target_item.get('owned', 0) > 1 and source == "items":
            user_items[item_index]['owned'] -= 1
        else:
            if source == "items":
                user_items = [item for item in user_items if item.get('_id') != item_id]
            else:
                user_equipments = [item for item in user_equipments if item.get('_id') != item_id]

        await db.user.update(
            where={'id': virtual_id},
            data={'hp': hp, 'data': Json(data)}
        )
        await db.inventory.update(
            where={'userId': virtual_id},
            data={'items': Json(user_items), 'equipments': Json(user_equipments)}
        )

        item_name = _item_name(lang, matched)
        msg = i18n.get(lang, "game.sell_success", name=item_name, amount=sale_value)
        await send_telegram_message(chat_id, msg, thread_id=thread_id)

    @zora.command("/battle")
    async def handle_battle(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id
        player = await db.user.find_unique(where={'id': virtual_id})
        if not player:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

        if player.hp <= 0:
            msg = (
                "❌ You are knocked out! Rest or claim daily rewards to heal first."
            ) if lang == "en" else (
                "❌ Anda sedang pingsan! Istirahat atau klaim hadiah harian untuk memulihkan HP."
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        tier_choice = args[0].lower() if args else None
        enemy_query = " ".join(args[1:]) if len(args) > 1 else None

        valid_tiers = ["boss", "bonus", "elite", "high", "normal", "low"]
        if not tier_choice or tier_choice not in valid_tiers:
            msg = (
                f"⚠️ Please specify a valid enemy tier!\n"
                f"Usage: <code>/battle [low|normal|high|elite|bonus|boss] [enemy_name_optional]</code>"
            ) if lang == "en" else (
                f"⚠️ Harap tentukan tier musuh yang valid!\n"
                f"Penggunaan: <code>/battle [low|normal|high|elite|bonus|boss] [nama_musuh_opsional]</code>"
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        # Load enemies file
        try:
            with open(f'./src/game/enemies/{tier_choice}.json', "r", encoding="utf-8") as file:
                enemies = json.load(file)
        except Exception:
            return await send_telegram_message(chat_id, "❌ Failed to load enemies file!")

        enemy = None
        if enemy_query:
            query = enemy_query.lower()
            # 1. Try exact match
            for e in enemies:
                if e['name'].lower() == query:
                    enemy = e
                    break
            # 2. Try substring match
            if not enemy:
                for e in enemies:
                    if query in e['name'].lower():
                        enemy = e
                        break
            # 3. Try fuzzy matching
            if not enemy:
                enemy_names = [e['name'] for e in enemies]
                matches = difflib.get_close_matches(enemy_query, enemy_names, n=1, cutoff=0.4)
                if matches:
                    for e in enemies:
                        if e['name'] == matches[0]:
                            enemy = e
                            break

            if not enemy:
                msg = i18n.get(lang, "game.battle_enemy_not_found", name=enemy_query, tier=tier_choice.upper())
                return await send_telegram_message(chat_id, f"❌ {msg}", thread_id=thread_id)
        else:
            enemy = random.choice(enemies)

        player_data = player.data
        p_hp = player.hp
        p_max_hp = player.max_hp
        p_atk = player_data.get('attack', 10)
        p_def = player_data.get('defense', 7)
        p_agl = player_data.get('agility', 8)
        p_karma = player_data.get('karma', 10)

        e_hp = enemy['hp']
        e_max_hp = enemy['hp']
        e_atk = enemy['atk']
        e_def = enemy['def']
        e_agl = enemy['agl']
        
        tier_karma = {
            "LOW": 5, "NORMAL": 10, "HIGH": 20, "ELITE": 35, 
            "SUPER ELITE": 50, "BOSS": 75, "SUPER BOSS": 100,
            "BONUS ENEMY": 150, "FINAL BOSS": 200
        }
        e_karma = tier_karma.get(enemy.get('tier', '').upper(), 10)

        enemy_display_name = i18n.get(lang, f"game.enemy_{to_key(enemy['name'])}_name", default=enemy['name'])
        
        battle_log = []
        battle_log.append(f"⚔️ <b>BATTLE: {player_data.get('name', full_name)} vs {enemy_display_name}</b>")
        battle_log.append(f"❤️ Your HP: {p_hp}/{p_max_hp} | 🖤 Enemy HP: {e_hp}/{e_max_hp}\n")

        # Combat Simulation Loop (Max 15 turns for Telegram summary size constraints)
        winner = None
        for turn in range(1, 16):
            # 1. Player attack
            base_atk = p_atk * (random.randint(85, 115) / 100)
            damage = round(base_atk * (120 / (120 + e_def)))
            damage = max(damage, round(p_atk * 0.10))
            
            crit_chance = 5 + (p_karma / 20)
            is_crit = random.random() * 100 < crit_chance
            if is_crit:
                damage = round(damage * 1.5)
                
            miss_chance = min(40, max(0, (e_agl - p_agl) * 1.5 + 5 - (p_karma / 50)))
            is_miss = random.random() * 100 < miss_chance
            if is_miss:
                damage = 0

            e_hp -= damage
            e_hp = max(0, e_hp)

            # Player turn logs
            if damage > 0:
                crit_text = " 💥<b>CRITICAL!</b>" if is_crit else ""
                p_act = f"• <b>Turn {turn}:</b> You dealt <code>{damage}</code> DMG{crit_text}."
            else:
                p_act = f"• <b>Turn {turn}:</b> Your attack missed!"
            
            if e_hp <= 0:
                battle_log.append(f"{p_act} ({enemy_display_name} HP: 0)")
                winner = "player"
                break

            # 2. Enemy attack
            base_atk_e = e_atk * (random.randint(85, 115) / 100)
            damage_e = round(base_atk_e * (120 / (120 + p_def)))
            damage_e = max(damage_e, round(e_atk * 0.10))
            
            crit_chance_e = 5 + (e_karma / 20)
            is_crit_e = random.random() * 100 < crit_chance_e
            if is_crit_e:
                damage_e = round(damage_e * 1.5)
                
            miss_chance_e = min(40, max(0, (p_agl - e_agl) * 1.5 + 5 - (e_karma / 50)))
            is_miss_e = random.random() * 100 < miss_chance_e
            if is_miss_e:
                damage_e = 0

            p_hp -= damage_e
            p_hp = max(0, p_hp)

            # Enemy turn logs
            if damage_e > 0:
                crit_text_e = " 💥<b>CRITICAL!</b>" if is_crit_e else ""
                e_act = f"They dealt <code>{damage_e}</code> DMG{crit_text_e} to you. (Your HP: {p_hp})"
            else:
                e_act = "Their attack missed!"
            
            battle_log.append(f"{p_act} {e_act}")

            if p_hp <= 0:
                winner = "enemy"
                break
        else:
            winner = "draw"

        # Apply rewards or update database
        final_msg = ""
        if winner == "player":
            # Victory! Award EXP and coins
            reward_list = enemy.get('reward', ["exp+10", "cns+5", "krm+0"])
            rewards = split_reward_string(reward_list)
            exp_reward = rewards[0]
            coin_reward = rewards[1]
            karma_reward = rewards[2]

            player_data['coins'] = player_data.get('coins', 0) + coin_reward
            player_data['exp'] = player_data.get('exp', 0) + exp_reward
            player_data['karma'] = player_data.get('karma', 10) + karma_reward

            await db.user.update(
                where={'id': virtual_id},
                data={
                    'hp': p_hp,
                    'data': Json(player_data)
                }
            )

            # Handle level up check
            mention_str = f"@{username}" if username else "Dreamer"
            mock_ctx = TelegramMockCtx(virtual_id, chat_id, mention_str)
            mock_user = TelegramMockMember(virtual_id, mention_str)
            leveled_up = await level_up(mock_user)
            if leveled_up:
                await send_level_up_msg(mock_ctx, mock_user)

            final_msg = (
                f"\n🏆 <b>VICTORY!</b>\n"
                f"You defeated {enemy_display_name}!\n"
                f"Rewards gained: +<code>{coin_reward}</code> Coins | +<code>{exp_reward}</code> EXP\n"
                f"Remaining HP: {p_hp}/{p_max_hp}"
            ) if lang == "en" else (
                f"\n🏆 <b>KEMENANGAN!</b>\n"
                f"Anda mengalahkan {enemy_display_name}!\n"
                f"Hadiah didapatkan: +<code>{coin_reward}</code> Koin | +<code>{exp_reward}</code> EXP\n"
                f"Sisa HP Anda: {p_hp}/{p_max_hp}"
            )

        elif winner == "enemy":
            # Defeat! Set HP to 0
            await db.user.update(
                where={'id': virtual_id},
                data={'hp': 0}
            )
            final_msg = (
                f"\n💀 <b>DEFEAT!</b>\n"
                f"You were knocked out by {enemy_display_name}!\n"
                f"Heal up before challenging again."
            ) if lang == "en" else (
                f"\n💀 <b>KEKALAHAN!</b>\n"
                f"Anda pingsan dikalahkan oleh {enemy_display_name}!\n"
                f"Pulihkan HP Anda sebelum menantang musuh kembali."
            )

        else: # Draw
            await db.user.update(
                where={'id': virtual_id},
                data={'hp': p_hp}
            )
            final_msg = (
                f"\n⏳ <b>DRAW!</b>\n"
                f"The battle exceeded turn limits!\n"
                f"Remaining HP: {p_hp}/{p_max_hp}"
            ) if lang == "en" else (
                f"\n⏳ <b>SERI!</b>\n"
                f"Pertempuran melebihi batas ronde!\n"
                f"Sisa HP Anda: {p_hp}/{p_max_hp}"
            )

        battle_log.append(final_msg)
        await send_telegram_message(chat_id, "\n".join(battle_log), thread_id=thread_id)

    # ── Enemies Bestiary ─────────────────────────────────────

    ENEMY_TIERS = ["boss", "bonus", "elite", "high", "normal", "low"]

    def _enemies_load(tier):
        enemy_path = path.join(path.dirname(__file__), '..', '..', 'src', 'game', 'enemies', f'{tier}.json')
        with open(enemy_path, 'r') as f:
            return json.load(f)

    def _enemies_page_text(tier, lang):
        enemies = _enemies_load(tier)
        tier_label = tier.upper()
        strongest = max(enemies, key=lambda x: x['hp'] + x['atk'] + x['def'] + x['agl'])
        image_source = max(
            (enemy for enemy in enemies if enemy.get('avatar')),
            key=lambda x: x['hp'] + x['atk'] + x['def'] + x['agl'],
            default=strongest
        )
        enemy_image = image_source.get('avatar')
        strongest_name = i18n.get(lang, f"game.enemy_{to_key(strongest['name'])}_name", default=strongest['name'])

        lines = [
            f"⚔️ <b>BESTIARY — {tier_label} TIER</b>",
            f"━━━━━━━━━━━━━━━━━━━",
        ]
        for idx, enemy in enumerate(enemies):
            name = i18n.get(lang, f"game.enemy_{to_key(enemy['name'])}_name", default=enemy['name'])
            lines.append(
                f"<b>{idx+1}. {name}</b> ({enemy['tier']})\n"
                f"   HP: <code>{enemy['hp']}</code> | ATK/DEF/AGL: <code>{enemy['atk']}/{enemy['def']}/{enemy['agl']}</code>"
            )
        lines.append(f"━━━━━━━━━━━━━━━━━━━")
        page_idx = ENEMY_TIERS.index(tier)
        footer = f"Page {page_idx+1}/{len(ENEMY_TIERS)} • Tap a number to see enemy details" if lang == "en" else f"Halaman {page_idx+1}/{len(ENEMY_TIERS)} • Ketuk angka untuk detail musuh"
        lines.append(f"<i>{footer}</i>")
        caption = "\n".join(lines)
        if len(caption) > 900:
            caption = caption[:885] + "\n<i>[truncated]</i>"
        return caption, enemies, enemy_image, strongest_name

    def _enemies_markup(tier, enemies, lang):
        page_idx = ENEMY_TIERS.index(tier)
        # Navigation row
        nav_row = []
        if page_idx > 0:
            nav_row.append({"text": "◀ " + ENEMY_TIERS[page_idx-1].title(), "callback_data": f"enemies_page:{ENEMY_TIERS[page_idx-1]}"})
        if page_idx < len(ENEMY_TIERS) - 1:
            nav_row.append({"text": ENEMY_TIERS[page_idx+1].title() + " ▶", "callback_data": f"enemies_page:{ENEMY_TIERS[page_idx+1]}"})
        # Number buttons (up to 10 per row, max 2 rows)
        num_buttons = []
        for idx in range(len(enemies)):
            num_buttons.append({"text": str(idx+1), "callback_data": f"enemies_detail:{tier}:{idx}"})
        # Group numbers into rows of 5
        num_rows = [num_buttons[i:i+5] for i in range(0, len(num_buttons), 5)]
        keyboard = ([nav_row] if nav_row else []) + num_rows
        return {"inline_keyboard": keyboard}

    @zora.command(["/enemies", "/enemy"])
    async def handle_enemies(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        tier = "boss"  # start at boss tier
        text, enemies, enemy_image, strongest_name = _enemies_page_text(tier, lang)
        markup = _enemies_markup(tier, enemies, lang)
        if enemy_image:
            photo_caption = (
                f"👹 <b>{strongest_name}</b>\n"
                f"<i>{tier.upper()} preview</i>"
            ) if lang == "en" else (
                f"👹 <b>{strongest_name}</b>\n"
                f"<i>Pratinjau {tier.upper()}</i>"
            )
            await send_telegram_photo(chat_id, enemy_image, caption=photo_caption, thread_id=thread_id, reply_markup=markup)
        else:
            await send_telegram_message(chat_id, text, thread_id=thread_id, reply_markup=markup)

    @zora.callback_query("enemies_page:")
    async def handle_enemies_page(zora_bot, chat_id, message_id, cq_id, telegram_user_id, username, full_name, data, lang):
        # data = "enemies_page:boss"
        tier = data.split(":", 1)[1]
        if tier not in ENEMY_TIERS:
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id, text="Unknown tier!")
            return
        text, enemies, enemy_image, strongest_name = _enemies_page_text(tier, lang)
        markup = _enemies_markup(tier, enemies, lang)
        if telegram_client:
            if enemy_image:
                await telegram_client.edit_message_media(chat_id, message_id, enemy_image, text, reply_markup=markup)
            else:
                await telegram_client.edit_message_text(chat_id, message_id, text, reply_markup=markup)
            await telegram_client.answer_callback_query(cq_id)

    @zora.callback_query("enemies_detail:")
    async def handle_enemies_detail(zora_bot, chat_id, message_id, cq_id, telegram_user_id, username, full_name, data, lang):
        # data = "enemies_detail:boss:0"
        parts = data.split(":")
        if len(parts) < 3:
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id)
            return
        tier = parts[1]
        idx = int(parts[2])
        enemies = _enemies_load(tier)
        if idx >= len(enemies):
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id, text="Not found!")
            return
        enemy = enemies[idx]
        name = i18n.get(lang, f"game.enemy_{to_key(enemy['name'])}_name", default=enemy['name'])
        desc = i18n.get(lang, f"game.enemy_{to_key(enemy['name'])}_desc", default=enemy.get('desc', ''))
        reward_str = ", ".join(enemy.get('reward', [])) if enemy.get('reward') else "N/A"
        skills_text = ""
        if enemy.get('skills'):
            skill_lines = []
            for s_idx, s in enumerate(enemy['skills']):
                s_name = i18n.get(lang, f"game.enemy_skill_{to_key(enemy['name'])}_{s_idx}_name", default=s['name'])
                skill_lines.append(f"✨ <b>{s_name}</b>: <code>{s['func']}</code>")
            skills_text = "\n⚙️ <b>Skills:</b>\n" + "\n".join(skill_lines)
        detail = (
            f"👹 <b>{name}</b> ({enemy['tier']})\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<i>{desc}</i>\n"
            f"❤️ HP: <code>{enemy['hp']}</code>\n"
            f"⚔️ ATK: <code>{enemy['atk']}</code> | 🛡️ DEF: <code>{enemy['def']}</code> | 💨 AGL: <code>{enemy['agl']}</code>\n"
            f"🎁 Reward: <code>{reward_str}</code>"
            f"{skills_text}"
        )
        if telegram_client:
            await telegram_client.answer_callback_query(cq_id, text=f"👹 {name}")
            avatar = enemy.get('avatar')
            if avatar:
                caption = (
                    f"👹 <b>{name}</b>\n"
                    f"Tier: <b>{enemy['tier']}</b>\n"
                    f"❤️ HP: <code>{enemy['hp']}</code>\n"
                    f"⚔️ ATK: <code>{enemy['atk']}</code> | 🛡️ DEF: <code>{enemy['def']}</code> | 💨 AGL: <code>{enemy['agl']}</code>"
                )
                await send_telegram_photo(chat_id, avatar, caption=caption, thread_id=None)
                if skills_text or desc or reward_str:
                    await send_telegram_message(chat_id, detail)
            else:
                await send_telegram_message(chat_id, detail)

