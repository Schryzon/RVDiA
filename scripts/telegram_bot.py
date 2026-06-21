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
from scripts.image.processing import (
    Image_Ops, Convolution, Enhancement, Edge_Detection,
    Equalization, Morphology, FreqFilter
)
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

async def handle_image_filter_command(chat_id, telegram_user_id, command, args, message, lang):
    cmd_name = command.lstrip("/")
    filename = "processed.png"
    caption = "🎨 Filter Applied!" if lang == "en" else "🎨 Filter Diterapkan!"
    func = None

    try:
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
            strength = 5
            if args:
                try: strength = int(args[0])
                except ValueError: pass
            def apply_blur(img, s=strength):
                kernel = Convolution.Kernels.box_blur(s)
                return Convolution.apply(img, kernel)
            func = apply_blur
            filename = "blur.png"
            caption = f"🎨 Blur Filter (strength={strength}) Applied!" if lang == "en" else f"🎨 Filter Blur (strength={strength}) Diterapkan!"
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
        elif cmd_name == "pixelate":
            size = 16
            if args:
                try: size = int(args[0])
                except ValueError: pass
            def apply_pixelate(img, sz=size):
                h, w = img.shape[:2]
                small = cv2.resize(img, (max(1, w // sz), max(1, h // sz)), interpolation=cv2.INTER_LINEAR)
                return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
            func = apply_pixelate
            filename = "pixelate.png"
            caption = f"🎨 Pixelated (size={size}) Applied!" if lang == "en" else f"🎨 Pixelated (size={size}) Diterapkan!"
        elif cmd_name == "vignette":
            sigma = 150
            if args:
                try: sigma = int(args[0])
                except ValueError: pass
            def apply_vignette(img, s=sigma):
                h, w = img.shape[:2]
                kernel_x = cv2.getGaussianKernel(w, s)
                kernel_y = cv2.getGaussianKernel(h, s)
                kernel = kernel_y * kernel_x.T
                mask = kernel / kernel.max()
                vignette_img = np.copy(img)
                for i in range(min(3, img.ndim)):
                    if img.ndim == 3:
                        vignette_img[:, :, i] = vignette_img[:, :, i] * mask
                    else:
                        vignette_img = vignette_img * mask
                return vignette_img.astype(np.uint8)
            func = apply_vignette
            filename = "vignette.png"
            caption = f"🎨 Vignette Filter (sigma={sigma}) Applied!" if lang == "en" else f"🎨 Filter Vignette (sigma={sigma}) Diterapkan!"
        elif cmd_name == "gamma":
            gamma_val = 1.5
            if args:
                try: gamma_val = float(args[0])
                except ValueError: pass
            func = lambda img: Enhancement.gamma_correction(img, gamma_val)
            filename = "gamma.png"
            caption = f"🎨 Gamma Correction (gamma={gamma_val}) Applied!" if lang == "en" else f"🎨 Koreksi Gamma (gamma={gamma_val}) Diterapkan!"
        elif cmd_name == "flip":
            axis = "horizontal"
            if args and args[0].lower() in ["horizontal", "vertical", "h", "v"]:
                axis = "vertical" if args[0].lower() in ["vertical", "v"] else "horizontal"
            func = lambda img: Image_Ops.flip(img, axis)
            filename = "flip.png"
            caption = f"🎨 Image Flipped ({axis})!" if lang == "en" else f"🎨 Gambar Dibalik ({axis})!"
        elif cmd_name == "rotate":
            angle = 90.0
            direction = "ccw"
            if args:
                try: angle = float(args[0])
                except ValueError: pass
                if len(args) > 1 and args[1].lower() in ["cw", "ccw"]:
                    direction = args[1].lower()
            func = lambda img: Image_Ops.rotate(img, angle, direction)
            filename = "rotate.png"
            caption = f"🎨 Rotated {angle}° {direction.upper()}!" if lang == "en" else f"🎨 Diputar {angle}° {direction.upper()}!"
        elif cmd_name == "adjust":
            brightness = 1.0
            contrast = 0
            if args:
                try: brightness = float(args[0])
                except ValueError: pass
                if len(args) > 1:
                    try: contrast = int(args[1])
                    except ValueError: pass
            func = lambda img: Enhancement.brightness_contrast(img, brightness, contrast)
            filename = "adjust.png"
            caption = f"🎨 Adjusted (brightness={brightness}, contrast={contrast})!" if lang == "en" else f"🎨 Disesuaikan (brightness={brightness}, contrast={contrast})!"
        elif cmd_name == "edge":
            method = "canny"
            if args and args[0].lower() in ["canny", "sobel", "laplacian", "prewitt", "roberts", "scharr"]:
                method = args[0].lower()
            def apply_edge(img):
                if method == "canny": res = Edge_Detection.canny(img)
                elif method == "sobel": res = Edge_Detection.sobel(img)
                elif method == "laplacian": res = Edge_Detection.laplacian(img)
                elif method == "prewitt": res = Edge_Detection.prewitt(img)
                elif method == "roberts": res = Edge_Detection.roberts(img)
                else: res = Edge_Detection.scharr(img)
                if res.ndim == 2:
                    return cv2.cvtColor(res, cv2.COLOR_GRAY2RGB)
                return res
            func = apply_edge
            filename = f"edge_{method}.png"
            caption = f"🎨 Edge Detection ({method.upper()}) Applied!" if lang == "en" else f"🎨 Deteksi Tepi ({method.upper()}) Diterapkan!"
        elif cmd_name == "noise":
            ntype = "salt_pepper"
            if args and args[0].lower() in ["salt_pepper", "gaussian", "poisson"]:
                ntype = args[0].lower()
            if ntype == "salt_pepper": func = Image_Ops.add_salt_pepper
            elif ntype == "gaussian": func = Enhancement.add_gaussian_noise
            else: func = Enhancement.add_poisson_noise
            filename = "noise.png"
            caption = f"🎨 Noise Added ({ntype})!" if lang == "en" else f"🎨 Kebisingan Ditambahkan ({ntype})!"
        elif cmd_name == "equalize":
            method = "global"
            if args and args[0].lower() in ["global", "clahe", "adaptive"]:
                method = args[0].lower()
            if method == "global": func = Equalization.equalize
            elif method == "clahe": func = Equalization.clahe
            else: func = Equalization.adaptive
            filename = "equalize.png"
            caption = f"🎨 Histogram Equalized ({method})!" if lang == "en" else f"🎨 Ekualisasi Histogram ({method})!"
        elif cmd_name == "threshold":
            val = 127
            method = "binary"
            if args:
                try: val = int(args[0])
                except ValueError: pass
            if len(args) > 1 and args[1].lower() in ["binary", "otsu"]:
                method = args[1].lower()
            func = lambda img: Image_Ops.threshold(img, val, method == "otsu")
            filename = "threshold.png"
            caption = f"🎨 Threshold Binarization ({method.upper()}, cutoff={val}) Applied!" if lang == "en" else f"🎨 Binarisasi Ambang Batas ({method.upper()}, cutoff={val}) Diterapkan!"
        elif cmd_name == "erode":
            iter_count = 1
            k_size = 3
            if args:
                try: iter_count = int(args[0])
                except ValueError: pass
                if len(args) > 1:
                    try: k_size = int(args[1])
                    except ValueError: pass
            func = lambda img: Morphology.erode(img, k_size, iter_count)
            filename = "erode.png"
            caption = f"🎨 Morphological Erosion (iterations={iter_count}, kernel={k_size})!" if lang == "en" else f"🎨 Erosi Morfologis (iterations={iter_count}, kernel={k_size})!"
        elif cmd_name == "dilate":
            iter_count = 1
            k_size = 3
            if args:
                try: iter_count = int(args[0])
                except ValueError: pass
                if len(args) > 1:
                    try: k_size = int(args[1])
                    except ValueError: pass
            func = lambda img: Morphology.dilate(img, k_size, iter_count)
            filename = "dilate.png"
            caption = f"🎨 Morphological Dilation (iterations={iter_count}, kernel={k_size})!" if lang == "en" else f"🎨 Dilatasi Morfologis (iterations={iter_count}, kernel={k_size})!"
        elif cmd_name == "skeleton":
            def apply_skeleton(img):
                if img.ndim == 3:
                    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                else:
                    gray = img
                _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                skel = Morphology.skeleton(binary)
                return cv2.cvtColor(skel, cv2.COLOR_GRAY2RGB)
            func = apply_skeleton
            filename = "skeleton.png"
            caption = "🎨 Topological Skeleton Extracted!" if lang == "en" else "🎨 Rangka Topologi Diekstrak!"
        elif cmd_name == "lpf":
            cutoff = 30.0
            ftype = "gaussian"
            order = 2
            if args:
                try: cutoff = float(args[0])
                except ValueError: pass
                if len(args) > 1 and args[1].lower() in ["ideal", "butterworth", "gaussian"]:
                    ftype = args[1].lower()
                if len(args) > 2:
                    try: order = int(args[2])
                    except ValueError: pass
            def apply_lpf(img):
                if ftype == "ideal": return FreqFilter.ideal_lpf(img, cutoff)
                elif ftype == "butterworth": return FreqFilter.butterworth_lpf(img, cutoff, order)
                return FreqFilter.gaussian_lpf(img, cutoff)
            func = apply_lpf
            filename = "lpf.png"
            caption = f"🎨 Frequency Low-Pass Filter ({ftype.upper()}, cutoff={cutoff}) Applied!" if lang == "en" else f"🎨 Filter Low-Pass Frekuensi ({ftype.upper()}, cutoff={cutoff}) Diterapkan!"
        elif cmd_name == "hpf":
            cutoff = 30.0
            ftype = "gaussian"
            order = 2
            if args:
                try: cutoff = float(args[0])
                except ValueError: pass
                if len(args) > 1 and args[1].lower() in ["ideal", "butterworth", "gaussian"]:
                    ftype = args[1].lower()
                if len(args) > 2:
                    try: order = int(args[2])
                    except ValueError: pass
            def apply_hpf(img):
                if ftype == "ideal": return FreqFilter.ideal_hpf(img, cutoff)
                elif ftype == "butterworth": return FreqFilter.butterworth_hpf(img, cutoff, order)
                return FreqFilter.gaussian_hpf(img, cutoff)
            func = apply_hpf
            filename = "hpf.png"
            caption = f"🎨 Frequency High-Pass Filter ({ftype.upper()}, cutoff={cutoff}) Applied!" if lang == "en" else f"🎨 Filter High-Pass Frekuensi ({ftype.upper()}, cutoff={cutoff}) Diterapkan!"
        elif cmd_name == "homomorphic":
            gamma_l = 0.5
            gamma_h = 2.0
            cutoff = 30.0
            if args:
                try: gamma_l = float(args[0])
                except ValueError: pass
                if len(args) > 1:
                    try: gamma_h = float(args[1])
                    except ValueError: pass
                if len(args) > 2:
                    try: cutoff = float(args[2])
                    except ValueError: pass
            func = lambda img: FreqFilter.homomorphic(img, gamma_l, gamma_h, cutoff)
            filename = "homomorphic.png"
            caption = f"🎨 Homomorphic Filter (gamma_l={gamma_l}, gamma_h={gamma_h}) Applied!" if lang == "en" else f"🎨 Filter Homomorfik (gamma_l={gamma_l}, gamma_h={gamma_h}) Diterapkan!"
        elif cmd_name == "fourier_modulate":
            frequency = 0.05
            angle = 45.0
            if args:
                try: frequency = float(args[0])
                except ValueError: pass
                if len(args) > 1:
                    try: angle = float(args[1])
                    except ValueError: pass
            func = lambda img: FreqFilter.modulate(img, frequency, angle)
            filename = "modulation_theorem.png"
            caption = f"📐 Fourier Modulation Theorem (frequency={frequency}, angle={angle}°)" if lang == "en" else f"📐 Teorema Modulasi Fourier (frequency={frequency}, angle={angle}°)"
        elif cmd_name == "posterize":
            levels = 4
            if args:
                try: levels = int(args[0])
                except ValueError: pass
            func = lambda img: Image_Ops.posterize(img, levels)
            filename = "posterize.png"
            caption = f"🎨 Posterize Filter (levels={levels}) Applied!" if lang == "en" else f"🎨 Filter Posterisasi (levels={levels}) Diterapkan!"
        elif cmd_name == "solarize":
            threshold = 128
            if args:
                try: threshold = int(args[0])
                except ValueError: pass
            func = lambda img: Image_Ops.solarize(img, threshold)
            filename = "solarize.png"
            caption = f"🎨 Solarization Filter (threshold={threshold}) Applied!" if lang == "en" else f"🎨 Filter Solarisasi (threshold={threshold}) Diterapkan!"
        elif cmd_name == "sketch":
            ksize = 21
            if args:
                try: ksize = int(args[0])
                except ValueError: pass
            func = lambda img: Image_Ops.pencil_sketch(img, ksize)
            filename = "sketch.png"
            caption = f"🎨 Pencil Sketch Filter (ksize={ksize}) Applied!" if lang == "en" else f"🎨 Filter Sketsa Pensil (ksize={ksize}) Diterapkan!"
        elif cmd_name in ["image_eval", "ieval"]:
            if not args:
                err_msg = "⚠️ Please specify a pipeline string (e.g. /image_eval grayscale,invert)" if lang == "en" else "⚠️ Harap tentukan string pipeline (misal: /image_eval grayscale,invert)"
                return await send_telegram_message(chat_id, err_msg)
            pipeline_str = args[0]
            
            reply_to = message.get("reply_to_message")
            img2_bytes = None
            if reply_to and reply_to.get("photo"):
                photo1 = reply_to["photo"]
                file_id1 = photo1[-1]["file_id"]
                img1_bytes = await telegram_client.get_file_bytes(file_id1)
                
                if message.get("photo"):
                    photo2 = message["photo"]
                    file_id2 = photo2[-1]["file_id"]
                    img2_bytes = await telegram_client.get_file_bytes(file_id2)
            else:
                if message.get("photo"):
                    photo1 = message["photo"]
                    file_id1 = photo1[-1]["file_id"]
                    img1_bytes = await telegram_client.get_file_bytes(file_id1)
                else:
                    file_id1 = await telegram_client.get_user_profile_photo_file_id(telegram_user_id)
                    if not file_id1:
                        err_msg = "⚠️ No photo attachment or profile photo found!" if lang == "en" else "⚠️ Tidak ada lampiran foto atau foto profil ditemukan!"
                        return await send_telegram_message(chat_id, err_msg)
                    img1_bytes = await telegram_client.get_file_bytes(file_id1)
                    
            img1 = cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR)
            if img1 is None:
                err_msg = "❌ Failed to read the image file." if lang == "en" else "❌ Gagal membaca file gambar."
                return await send_telegram_message(chat_id, err_msg)
            img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
            
            img2_rgb = None
            if img2_bytes:
                img2 = cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR)
                if img2 is not None:
                    img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)
                    
            func = lambda img: Image_Ops.eval_pipeline(img, pipeline_str, img2_rgb)
            filename = "eval.png"
            caption = "🎨 Pipeline Evaluation Completed!" if lang == "en" else "🎨 Evaluasi Pipeline Selesai!"

        if func is None:
            return

        await process_and_send_telegram_image(chat_id, message, telegram_user_id, lang, func, filename=filename, caption=caption)

    except Exception as e:
        logging.error(f"Error handling Telegram image command: {e}", exc_info=True)
        err_msg = f"❌ Error: {str(e)}"
        await send_telegram_message(chat_id, err_msg)

async def handle_help_command(chat_id, lang):
    help_msg = (
        f"🤖 <b>RVDiA Zora Commands:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 <b>RPG SYSTEM:</b>\n"
        f"• /register - Create your RPG account\n"
        f"• /profile  - View stats, level, coins, class\n"
        f"• /class    - Choose a class (Warrior/Mage/Rogue)\n"
        f"• /allocate - Allocate stat points (e.g. /allocate ATK 5)\n"
        f"• /daily    - Claim daily coins and EXP\n"
        f"• /adventure - Explore and earn rewards\n"
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
        f"• /fourier_modulate [freq] [angle] - Fourier modulation theorem visualization\n\n"
        f"⛓️ <b>EVALUATION PIPELINE:</b>\n"
        f"• /image_eval [pipeline] - Sequential processing\n"
        f"• /ieval [pipeline] - Alias for /image_eval\n"
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
        f"• /fourier_modulate [freq] [angle] - Visualisasi teorema modulasi Fourier\n\n"
        f"⛓️ <b>EVALUASI PIPELINE:</b>\n"
        f"• /image_eval [pipeline] - Pemrosesan sekuensial\n"
        f"• /ieval [pipeline] - Alias dari /image_eval\n"
        f"  <i>Contoh: /image_eval grayscale,invert,blur:5</i>\n"
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
    elif command in [
        "/grayscale", "/invert", "/circle", "/sepia", "/blur", "/sharpen", "/emboss",
        "/pixelate", "/vignette", "/gamma", "/flip", "/rotate", "/adjust", "/edge",
        "/noise", "/equalize", "/threshold", "/erode", "/dilate", "/skeleton",
        "/lpf", "/hpf", "/homomorphic", "/fourier_modulate", "/posterize", "/solarize",
        "/sketch", "/image_eval", "/ieval"
    ]:
        await handle_image_filter_command(chat_id, telegram_user_id, command, args, message, lang)
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
