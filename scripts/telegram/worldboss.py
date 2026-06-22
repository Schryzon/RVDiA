import random
import logging
from datetime import datetime, timedelta, timezone

from scripts.main import db
from scripts.game.worldboss import get_active_boss, attack_boss
from scripts.utils.telegram import send_telegram_message
from scripts.utils.i18n import i18n

def setup(zora):
    @zora.command("/worldboss")
    async def handle_worldboss(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
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

    @zora.command("/attack")
    async def handle_attack(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
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
            hit_time = contribution.lastHitTime
            if hit_time.tzinfo is None:
                hit_time = hit_time.replace(tzinfo=timezone.utc)
            cooldown_limit = hit_time + timedelta(minutes=15)
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
