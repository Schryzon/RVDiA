import os
import asyncio
import logging
import random
import aiohttp
import io
import cv2
import numpy as np
from datetime import datetime, timedelta, timezone
from prisma import Json

from scripts.main import db
from scripts.ai.chat import chat_service
from scripts.game.game import level_up, give_rewards, send_level_up_msg
from scripts.utils.i18n import i18n
from scripts.image.processing import Image_Ops, Convolution
from scripts.utils.telegram import (
    telegram_client,
    TelegramMockMember,
    TelegramMockChannel,
    TelegramMockCtx,
    send_telegram_message,
    send_telegram_photo,
    send_telegram_photo_bytes
)

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

async def handle_class_command(chat_id, telegram_user_id, username, class_name, lang):
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
    
    # Retroactive points: 5 points per level beyond level 1
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

async def handle_allocate_command(chat_id, telegram_user_id, username, stat_name, amount_str, lang):
    virtual_id = -telegram_user_id
    user_record = await db.user.find_unique(where={'id': virtual_id})
    if not user_record:
        msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
        return await send_telegram_message(chat_id, f"⚠️ {msg}")

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

async def handle_worldboss_command(chat_id, telegram_user_id, lang):
    from scripts.game.worldboss import get_active_boss
    
    boss = await get_active_boss()
    
    # Get contributions
    contributions = await db.worldbosscontribution.find_many(
        where={"bossId": boss.id},
        order={"damage": "desc"},
        take=10
    )
    
    bar = ""
    if boss.maxHp > 0:
        ratio = boss.hp / boss.maxHp
        filled = round(ratio * 10)
        filled = max(0, min(10, filled))
        bar = "█" * filled + "░" * (10 - filled)
        
    pct = round((boss.hp / boss.maxHp) * 100, 1) if boss.maxHp > 0 else 0
    
    leaderboard_text = ""
    for idx, c in enumerate(contributions, 1):
        leaderboard_text += f"{idx}. <b>{c.username}</b>: <code>{c.damage}</code> DMG\n"
        
    if not leaderboard_text:
        leaderboard_text = "No contributions yet. Be the first to attack!" if lang == "en" else "Belum ada kontribusi. Jadilah yang pertama menyerang!"

    rewards_config = boss.rewards
    coins_lbl = "Coins" if lang == "en" else "Koin"
    rewards_text = f"💰 {rewards_config.get('coins')} {coins_lbl} | 🔰 {rewards_config.get('exp')} EXP"

    msg = (
        f"⚔️ <b>WORLD BOSS: {boss.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Tier: <b>{boss.tier}</b>\n"
        f"HP: <code>{boss.hp}/{boss.maxHp}</code> ({pct}%)\n"
        f"<code>[{bar}]</code>\n\n"
        f"🏆 <b>Top Contributors:</b>\n"
        f"{leaderboard_text}\n"
        f"🎁 <b>Defeat Rewards:</b>\n"
        f"{rewards_text}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Type /attack to deal damage to the boss!"
    ) if lang == "en" else (
        f"⚔️ <b>WORLD BOSS: {boss.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Tier: <b>{boss.tier}</b>\n"
        f"HP: <code>{boss.hp}/{boss.maxHp}</code> ({pct}%)\n"
        f"<code>[{bar}]</code>\n\n"
        f"🏆 <b>Kontributor Teratas:</b>\n"
        f"{leaderboard_text}\n"
        f"🎁 <b>Hadiah Mengalahkan:</b>\n"
        f"{rewards_text}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Ketik /attack untuk menyerang boss!"
    )
    await send_telegram_message(chat_id, msg)

async def handle_attack_command(chat_id, telegram_user_id, username, lang):
    from scripts.game.worldboss import get_active_boss, attack_boss
    
    virtual_id = -telegram_user_id
    player = await db.user.find_unique(where={"id": virtual_id})
    if not player:
        msg = i18n.get(lang, "game.register_first") or "Please register first using /register."
        return await send_telegram_message(chat_id, f"⚠️ {msg}")

    player_data = player.data
    level = player_data.get("level", 1)
    if level < 10:
        msg = (
            f"⚠️ World Boss attacks require level 10! Current level: <b>{level}</b>."
        ) if lang == "en" else (
            f"⚠️ Penyerangan World Boss membutuhkan level 10! Level sekarang: <b>{level}</b>."
        )
        return await send_telegram_message(chat_id, msg)

    if player.hp <= 0:
        msg = (
            f"⚠️ You are knocked out (HP: 0)! Please rest or level up to restore HP."
        ) if lang == "en" else (
            f"⚠️ Anda sedang pingsan (HP: 0)! Harap istirahat atau naik level untuk memulihkan HP."
        )
        return await send_telegram_message(chat_id, msg)

    boss = await get_active_boss()

    # Check cooldown using DB timestamp (15 minutes)
    contribution = await db.worldbosscontribution.find_unique(
        where={"bossId_userId": {"bossId": boss.id, "userId": virtual_id}}
    )

    if contribution:
        cooldown_limit = contribution.lastHitTime + timedelta(minutes=15)
        now = datetime.now(timezone.utc)
        if now < cooldown_limit:
            remaining = int((cooldown_limit - now).total_seconds())
            minutes = remaining // 60
            seconds = remaining % 60
            cooldown_msg = (
                f"⏳ Cooldown! You can attack again in {minutes}m {seconds}s."
            ) if lang == "en" else (
                f"⏳ Cooldown! Anda bisa menyerang lagi dalam {minutes} menit {seconds} detik."
            )
            return await send_telegram_message(chat_id, cooldown_msg)

    # Roll damage based on stats
    atk = player_data.get("attack", 10)
    karma = player_data.get("karma", 10)

    base_dmg = random.randint(atk - 2, atk + 5) + level
    base_dmg = max(5, base_dmg)

    crit_chance = 5 + (karma / 20)
    is_crit = random.random() * 100 < crit_chance
    if is_crit:
        base_dmg = round(base_dmg * 1.5)

    is_miss = random.random() * 100 < 5
    if is_miss:
        base_dmg = 0

    result = await attack_boss(virtual_id, player_data.get("name", username), base_dmg)

    # Boss retaliation damage calculation
    is_instakill = random.random() * 100 < 20
    if is_instakill:
        retaliation_dmg = player.hp
    else:
        retaliation_dmg = random.randint(15, 35)

    new_player_hp = max(0, player.hp - retaliation_dmg)

    # Deduct HP in database
    await db.user.update(
        where={"id": virtual_id},
        data={"hp": new_player_hp}
    )

    # Format result text
    if is_miss:
        attack_desc = (
            f"❌ You swung at <b>{boss.name}</b> and missed!"
        ) if lang == "en" else (
            f"❌ Seranganmu ke <b>{boss.name}</b> meleset!"
        )
    else:
        crit_label = "💥 " if is_crit else ""
        attack_desc = (
            f"{crit_label}You attacked <b>{boss.name}</b> and dealt <code>{base_dmg}</code> DMG!"
        ) if lang == "en" else (
            f"{crit_label}Anda menyerang <b>{boss.name}</b> dan memberikan <code>{base_dmg}</code> DMG!"
        )

    if is_instakill:
        counter_desc = (
            f"💀 <b>{boss.name}</b> counter-attacked with a fatal blow! You are knocked out!"
        ) if lang == "en" else (
            f"💀 <b>{boss.name}</b> membalas dengan serangan fatal! Anda pingsan!"
        )
    else:
        counter_desc = (
            f"💥 <b>{boss.name}</b> retaliated and dealt <code>{retaliation_dmg}</code> DMG! "
            f"(HP: <code>{new_player_hp}/{player.max_hp}</code>)"
        ) if lang == "en" else (
            f"💥 <b>{boss.name}</b> membalas dengan <code>{retaliation_dmg}</code> DMG! "
            f"(HP: <code>{new_player_hp}/{player.max_hp}</code>)"
        )

    msg = (
        f"⚔️ <b>WORLD BOSS RAID RESULT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{attack_desc}\n"
        f"{counter_desc}\n"
    )

    if result["is_defeated"]:
        msg += (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎉 <b>{boss.name} HAS BEEN DEFEATED!</b> 🎉\n\n"
            f"🎁 <b>Top Rewards:</b>\n"
        )
        for share in result["rewards_distributed"][:10]:
            msg += f"• <b>{share['username']}</b>: +<code>{share['coins']}</code> Koin, +<code>{share['exp']}</code> EXP ({share['share']}%)\n"
    else:
        bar = ""
        rem_hp = result["boss_remaining_hp"]
        if boss.maxHp > 0:
            ratio = rem_hp / boss.maxHp
            filled = round(ratio * 10)
            filled = max(0, min(10, filled))
            bar = "█" * filled + "░" * (10 - filled)
            
        pct = round((rem_hp / boss.maxHp) * 100, 1) if boss.maxHp > 0 else 0
        msg += (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Boss HP: <code>{rem_hp}/{boss.maxHp}</code> ({pct}%)\n"
            f"<code>[{bar}]</code>"
        )

    await send_telegram_message(chat_id, msg)

async def handle_lang_command(chat_id, telegram_user_id, lang_choice, current_lang):
    virtual_id = -telegram_user_id
    user_record = await db.user.find_unique(where={'id': virtual_id})
    if not user_record:
        msg = i18n.get(current_lang, "game.register_first") or "Please register first using /register."
        return await send_telegram_message(chat_id, f"⚠️ {msg}")

    if not lang_choice:
        msg = (
            f"⚠️ Please specify a language (en / id)!\n"
            f"Usage: <code>/lang [en|id]</code>"
        ) if current_lang == "en" else (
            f"⚠️ Harap tentukan bahasa (en / id)!\n"
            f"Penggunaan: <code>/lang [en|id]</code>"
        )
        return await send_telegram_message(chat_id, msg)

    lang_choice_lower = lang_choice.lower()
    if lang_choice_lower not in ["en", "id"]:
        msg = (
            f"⚠️ Invalid language! Choose <b>en</b> (English) or <b>id</b> (Indonesian)."
        ) if current_lang == "en" else (
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

async def get_telegram_image_bytes(message, telegram_user_id) -> tuple[bytes, str]:
    if not telegram_client:
        raise ValueError("Telegram client not initialized!")

    photo = message.get("photo")
    if photo:
        file_id = photo[-1]["file_id"]
        filename = "input.png"
    else:
        file_id = await telegram_client.get_user_profile_photo_file_id(telegram_user_id)
        filename = "profile.png"
                        
    if not file_id:
        raise ValueError("No photo attachment or profile photo found!")

    img_bytes = await telegram_client.get_file_bytes(file_id)
    return img_bytes, filename

async def send_telegram_photo_bytes(chat_id, photo_bytes, filename="processed.png", caption=""):
    if telegram_client:
        await telegram_client.send_photo_bytes(chat_id, photo_bytes, filename, caption)

async def process_and_send_telegram_image(chat_id, message, telegram_user_id, lang, process_func, filename="processed.png", caption="", *args, **kwargs):
    try:
        if telegram_client:
            await telegram_client.send_chat_action(chat_id, "upload_photo")

        # 1. Download image bytes
        try:
            image_bytes, origin_filename = await get_telegram_image_bytes(message, telegram_user_id)
        except Exception as e:
            err_msg = (
                f"⚠️ No photo attachment or profile photo found!\n"
                f"Please upload a photo and use the command as a caption, or make sure you have a public profile photo."
            ) if lang == "en" else (
                f"⚠️ Tidak ada lampiran foto atau foto profil ditemukan!\n"
                f"Silahkan unggah foto dan gunakan command sebagai caption, atau pastikan foto profil Anda publik."
            )
            return await send_telegram_message(chat_id, err_msg)

        # 2. Convert to OpenCV formats
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            err_msg = "❌ Failed to read the image file." if lang == "en" else "❌ Gagal membaca file gambar."
            return await send_telegram_message(chat_id, err_msg)

        # Convert BGR to RGB for scripts.image.processing
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 3. Process image
        result = process_func(img_rgb, *args, **kwargs)

        # Convert RGB back to BGR for saving
        if result.ndim == 3:
            if result.shape[2] == 3:
                result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
            else:
                result_bgr = result[..., :3]
        else:
            result_bgr = result

        # Encode BGR back to bytes
        _, buffer = cv2.imencode('.png', result_bgr)
        processed_bytes = buffer.tobytes()

        # 4. Send photo
        await send_telegram_photo_bytes(chat_id, processed_bytes, filename=filename, caption=caption)

    except Exception as e:
        logging.error(f"Error processing Telegram image: {e}", exc_info=True)
        err_msg = f"❌ Error processing image: {str(e)}" if lang == "en" else f"❌ Terjadi kesalahan saat memproses gambar: {str(e)}"
        await send_telegram_message(chat_id, err_msg)

async def handle_image_filter_command(chat_id, telegram_user_id, command, message, lang):
    cmd_name = command.lstrip("/")
    
    # Map command to the appropriate function
    if cmd_name == "grayscale":
        func = Image_Ops.to_grayscale
        filename = "grayscale.png"
        caption = "🎨 Grayscale Filter Applied!" if lang == "en" else "🎨 Filter Grayscale Diterapkan!"
    elif cmd_name == "invert":
        func = Image_Ops.invert
        filename = "invert.png"
        caption = "🎨 Colors Inverted!" if lang == "en" else "🎨 Warna Dibalik!"
    elif cmd_name == "circle":
        func = Image_Ops.crop_circle
        filename = "circle.png"
        caption = "🎨 Circular Crop Applied!" if lang == "en" else "🎨 Potongan Lingkaran Diterapkan!"
    elif cmd_name == "sepia":
        def apply_sepia(img):
            img_f = img.astype(np.float32)
            sepia_matrix = np.array([[0.393, 0.769, 0.189],
                                     [0.349, 0.686, 0.168],
                                     [0.272, 0.534, 0.131]])
            sepia_img = cv2.transform(img_f, sepia_matrix)
            return np.clip(sepia_img, 0, 255).astype(np.uint8)
        func = apply_sepia
        filename = "sepia.png"
        caption = "🎨 Warm Sepia Tone Applied!" if lang == "en" else "🎨 Nada Sepia Hangat Diterapkan!"
    elif cmd_name == "blur":
        def apply_blur(img):
            kernel = Convolution.Kernels.box_blur(5)
            return Convolution.apply(img, kernel)
        func = apply_blur
        filename = "blur.png"
        caption = "🎨 Blur Filter Applied!" if lang == "en" else "🎨 Filter Blur Diterapkan!"
    elif cmd_name == "sharpen":
        def apply_sharpen(img):
            kernel = Convolution.Kernels.sharpen()
            return Convolution.apply(img, kernel)
        func = apply_sharpen
        filename = "sharpen.png"
        caption = "🎨 Image Details Sharpened!" if lang == "en" else "🎨 Detail Gambar Ditajamkan!"
    elif cmd_name == "emboss":
        def apply_emboss(img):
            return Convolution.apply(img, Convolution.Kernels.emboss())
        func = apply_emboss
        filename = "emboss.png"
        caption = "🎨 3D Emboss Filter Applied!" if lang == "en" else "🎨 Filter Emboss 3D Diterapkan!"
    else:
        return

    await process_and_send_telegram_image(chat_id, message, telegram_user_id, lang, func, filename=filename, caption=caption)

async def handle_help_command(chat_id, lang):
    help_msg = (
        f"🤖 <b>RVDiA Zora Commands:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"/register - Create your Re:Volution RPG account\n"
        f"/profile  - View stats, class, coins, and level\n"
        f"/class    - Choose your class (Warrior/Mage/Rogue)\n"
        f"/allocate - Spend stat points (e.g., /allocate ATK 5)\n"
        f"/daily    - Claim your daily coins and EXP\n"
        f"/adventure - Explore the dream world and gain rewards\n"
        f"/worldboss - View active World Boss status & leaderboard\n"
        f"/attack   - Attack the active World Boss\n"
        f"/lang     - Change language settings (en/id)\n\n"
        f"🎨 <b>Image Filters (Upload photo and use command as caption):</b>\n"
        f"/grayscale - Convert photo to grayscale\n"
        f"/invert    - Invert photo colors\n"
        f"/circle    - Crop photo into a circle\n"
        f"/sepia     - Apply a warm sepia tone\n"
        f"/blur      - Apply a box blur\n"
        f"/sharpen   - Sharpen details\n"
        f"/emboss    - Apply a 3D emboss filter\n"
        f"/help      - Show this help command menu\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Send any text to chat with me! ✨"
    ) if lang == "en" else (
        f"🤖 <b>Command Bot Telegram RVDiA Zora:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"/register - Daftar akun RPG Re:Volution baru\n"
        f"/profile  - Lihat info level, koin, kelas, & statistik\n"
        f"/class    - Pilih kelas Anda (Warrior/Mage/Rogue)\n"
        f"/allocate - Gunakan poin status (misal: /allocate ATK 5)\n"
        f"/daily    - Klaim koin harian gratis dan EXP\n"
        f"/adventure - Berpetualang di dunia mimpi untuk hadiah\n"
        f"/worldboss - Lihat status World Boss aktif & leaderboard\n"
        f"/attack   - Serang World Boss yang sedang aktif\n"
        f"/lang     - Ganti pengaturan bahasa (en/id)\n\n"
        f"🎨 <b>Filter Gambar (Kirim foto dan gunakan command sebagai caption):</b>\n"
        f"/grayscale - Ubah foto menjadi hitam putih\n"
        f"/invert    - Balikkan warna foto\n"
        f"/circle    - Potong foto menjadi bulat\n"
        f"/sepia     - Terapkan efek sepia hangat\n"
        f"/blur      - Terapkan efek box blur\n"
        f"/sharpen   - Pertajam detail gambar\n"
        f"/emboss    - Terapkan filter timbul 3D\n"
        f"/help      - Tampilkan menu bantuan ini\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Kirim pesan apapun untuk ngobrol denganku! ✨"
    )
    await send_telegram_message(chat_id, help_msg)

async def handle_chat_message(chat_id, telegram_user_id, username, text, lang):
    virtual_id = -telegram_user_id
    if telegram_client:
        await telegram_client.send_chat_action(chat_id, "typing")

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

    if command == "/start" or command == "/register":
        await handle_register_command(chat_id, telegram_user_id, full_name, lang)
    elif command == "/profile":
        await handle_profile_command(chat_id, telegram_user_id, full_name, lang)
    elif command == "/daily":
        await handle_daily_command(chat_id, telegram_user_id, username, lang)
    elif command == "/adventure":
        await handle_adventure_command(chat_id, telegram_user_id, username, lang)
    elif command == "/class":
        class_name = args[0] if args else None
        await handle_class_command(chat_id, telegram_user_id, full_name, class_name, lang)
    elif command == "/allocate":
        stat_name = args[0] if args else None
        amount_str = args[1] if len(args) > 1 else "1"
        await handle_allocate_command(chat_id, telegram_user_id, full_name, stat_name, amount_str, lang)
    elif command == "/worldboss":
        await handle_worldboss_command(chat_id, telegram_user_id, lang)
    elif command == "/attack":
        await handle_attack_command(chat_id, telegram_user_id, username, lang)
    elif command == "/lang":
        new_lang = args[0] if args else None
        await handle_lang_command(chat_id, telegram_user_id, new_lang, lang)
    elif command in ["/grayscale", "/invert", "/circle", "/sepia", "/blur", "/sharpen", "/emboss"]:
        await handle_image_filter_command(chat_id, telegram_user_id, command, message, lang)
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
        finally:
            if telegram_client:
                await telegram_client.close()
