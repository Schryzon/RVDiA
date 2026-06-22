import random
import json
import difflib
import math
from datetime import datetime, timedelta, timezone
from prisma import Json
from scripts.main import db
from scripts.game.game import level_up, give_rewards, send_level_up_msg, split_reward_string
from scripts.utils.telegram import TelegramMockCtx, TelegramMockMember, send_telegram_message
from scripts.utils.i18n import i18n

def to_key(name: str) -> str:
    import re
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s_]', '', name)
    name = re.sub(r'[\s_]+', '_', name)
    return name

def setup(zora):
    @zora.command("/daily")
    async def handle_daily(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
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
        await send_telegram_message(chat_id, success_msg)

    @zora.command("/adventure")
    async def handle_adventure(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
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

    @zora.command("/class")
    async def handle_class(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id})
        if not user_record:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}")

        data = user_record.data
        current_class = data.get('class', 'None')
        if current_class != 'None':
            msg = (
                f"⚠️ You have already selected a class: <b>{current_class}</b>!"
            ) if lang == "en" else (
                f"⚠️ Anda sudah memilih kelas: <b>{current_class}</b>!"
            )
            return await send_telegram_message(chat_id, msg)

        class_name = args[0] if args else None
        if not class_name:
            msg = (
                f"⚠️ Please specify a class!\n"
                f"Usage: <code>/class [warrior|mage|rogue]</code>"
            ) if lang == "en" else (
                f"⚠️ Harap tentukan kelas!\n"
                f"Penggunaan: <code>/class [warrior|mage|rogue]</code>"
            )
            return await send_telegram_message(chat_id, msg)

        class_name_lower = class_name.lower()
        if class_name_lower not in ["warrior", "mage", "rogue"]:
            msg = (
                f"⚠️ Invalid class! Choose between: <b>Warrior</b>, <b>Mage</b>, or <b>Rogue</b>."
            ) if lang == "en" else (
                f"⚠️ Kelas tidak valid! Pilih antara: <b>Warrior</b>, <b>Mage</b>, atau <b>Rogue</b>."
            )
            return await send_telegram_message(chat_id, msg)

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
        await send_telegram_message(chat_id, msg)

    @zora.command("/allocate")
    async def handle_allocate(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
        virtual_id = -telegram_user_id
        user_record = await db.user.find_unique(where={'id': virtual_id})
        if not user_record:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}")

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
            return await send_telegram_message(chat_id, msg)

        stat_str = stat_name.upper()
        if stat_str not in ["ATK", "DEF", "AGL"]:
            msg = (
                f"⚠️ Invalid stat type! Choose between: <b>ATK</b>, <b>DEF</b>, or <b>AGL</b>."
            ) if lang == "en" else (
                f"⚠️ Tipe status tidak valid! Pilih antara: <b>ATK</b>, <b>DEF</b>, atau <b>AGL</b>."
            )
            return await send_telegram_message(chat_id, msg)

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
            return await send_telegram_message(chat_id, msg)

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
        await send_telegram_message(chat_id, msg)

    @zora.command("/battle")
    async def handle_battle(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
        virtual_id = -telegram_user_id
        player = await db.user.find_unique(where={'id': virtual_id})
        if not player:
            msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
            return await send_telegram_message(chat_id, f"⚠️ {msg}")

        if player.hp <= 0:
            msg = (
                "❌ You are knocked out! Rest or claim daily rewards to heal first."
            ) if lang == "en" else (
                "❌ Anda sedang pingsan! Istirahat atau klaim hadiah harian untuk memulihkan HP."
            )
            return await send_telegram_message(chat_id, msg)

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
            return await send_telegram_message(chat_id, msg)

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
                return await send_telegram_message(chat_id, f"❌ {msg}")
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
        await send_telegram_message(chat_id, "\n".join(battle_log))
