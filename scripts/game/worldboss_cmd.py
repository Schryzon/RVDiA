import discord
import random
import time
from datetime import datetime, timedelta, timezone
from scripts.main import db
from scripts.utils.i18n import i18n
from scripts.game.worldboss import get_active_boss, attack_boss

async def get_user_lang(user_id: int) -> str:
    user_settings = await db.usersettings.find_unique(where={'userId': user_id})
    return user_settings.lang if user_settings else "en"

def make_progress_bar(current: int, maximum: int, size: int = 15) -> str:
    if maximum <= 0:
        return "[]"
    ratio = current / maximum
    filled = round(ratio * size)
    filled = max(0, min(size, filled))
    empty = size - filled
    return "█" * filled + "░" * empty

class RecruitHuntersView(discord.ui.View):
    def __init__(self, ctx, boss_name, lang):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.boss_name = boss_name
        self.lang = lang
        self.children[0].label = i18n.get(lang, "game.worldboss_recruit_btn", default="Recruit Hunters")

    @discord.ui.button(style=discord.ButtonStyle.primary, custom_id="recruit_hunters")
    async def recruit(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.edit_message(view=self)
        
        user_mention = interaction.user.mention
        msg_template = i18n.get(self.lang, "game.worldboss_recruit_msg", default="📢 {user} is recruiting hunters to defeat {boss}! Join the battle using `/game worldboss attack`!")
        announcement = msg_template.format(user=user_mention, boss=self.boss_name)
        await self.ctx.channel.send(announcement)
        
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

async def execute_worldboss_status(ctx):
    lang = await get_user_lang(ctx.author.id)
    boss = await get_active_boss()

    # Get contributions
    contributions = await db.worldbosscontribution.find_many(
        where={"bossId": boss.id},
        order={"damage": "desc"},
        take=10
    )

    title = i18n.get(lang, "game.worldboss_status_title", name=boss.name)
    embed = discord.Embed(title=title, color=0xff3366)
    
    # Progress Bar
    bar = make_progress_bar(boss.hp, boss.maxHp)
    pct = round((boss.hp / boss.maxHp) * 100, 1) if boss.maxHp > 0 else 0
    
    status_label = i18n.get(lang, "game.worldboss_status_hp")
    embed.description = f"**{boss.tier}**\n\n{status_label}: `{boss.hp}/{boss.maxHp}` ({pct}%)\n`[{bar}]`"

    # Leaderboard contributions
    leaderboard_text = ""
    for idx, c in enumerate(contributions, 1):
        leaderboard_text += f"{idx}. **{c.username}**: `{c.damage}` DMG\n"
        
    if not leaderboard_text:
        leaderboard_text = i18n.get(lang, "game.worldboss_no_contributions", default="No contributions yet. Be the first to attack!")

    leaderboard_label = i18n.get(lang, "game.worldboss_leaderboard_field")
    embed.add_field(name=leaderboard_label, value=leaderboard_text, inline=False)
    
    # Show potential rewards
    rewards_config = boss.rewards
    rewards_label = i18n.get(lang, "game.worldboss_rewards_field")
    rewards_text = f"🪙 {rewards_config.get('coins')} Coins\n🔰 {rewards_config.get('exp')} Exp"
    embed.add_field(name=rewards_label, value=rewards_text, inline=False)

    embed.set_footer(text=i18n.get(lang, "game.worldboss_status_footer"))
    
    view = RecruitHuntersView(ctx, boss.name, lang)
    view.message = await ctx.reply(embed=embed, view=view)

async def execute_worldboss_attack(ctx):
    lang = await get_user_lang(ctx.author.id)
    
    # Fetch player details
    player = await db.user.find_unique(where={"id": ctx.author.id})
    if not player:
        msg = i18n.get(lang, "game.profile_not_registered")
        return await ctx.reply(msg)

    # Stat/Level Requirement Check (Min Level 10)
    player_data = player.data
    level = player_data.get("level", 1)
    if level < 10:
        msg = i18n.get(lang, "game.worldboss_level_required", level=10)
        return await ctx.reply(msg)

    # HP Check
    if player.hp <= 0:
        msg = i18n.get(lang, "game.worldboss_knocked_out")
        return await ctx.reply(msg)

    boss = await get_active_boss()

    # Check cooldown using DB timestamp (15 minutes)
    contribution = await db.worldbosscontribution.find_unique(
        where={"bossId_userId": {"bossId": boss.id, "userId": ctx.author.id}}
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
            cooldown_msg = i18n.get(lang, "game.worldboss_cooldown_msg", min=minutes, sec=seconds)
            return await ctx.reply(cooldown_msg)

    # Roll damage based on stats
    atk = player_data.get("attack", 10)
    karma = player_data.get("karma", 10)

    # Calculate damage
    base_dmg = random.randint(atk - 2, atk + 5) + level
    base_dmg = max(5, base_dmg)

    # Crit check (Karma boosts crit chance)
    crit_chance = 5 + (karma / 20)
    is_crit = random.random() * 100 < crit_chance
    if is_crit:
        base_dmg = round(base_dmg * 1.5)

    # Miss check
    is_miss = random.random() * 100 < 5
    if is_miss:
        base_dmg = 0

    # Apply attack to boss
    result = await attack_boss(ctx.author.id, player_data.get("name", ctx.author.name), base_dmg)

    # Boss retaliation damage calculation
    is_instakill = random.random() * 100 < 20  # 20% chance of instakill
    if is_instakill:
        retaliation_dmg = player.hp
    else:
        retaliation_dmg = random.randint(15, 35)

    new_player_hp = max(0, player.hp - retaliation_dmg)

    # Deduct HP in database
    await db.user.update(
        where={"id": ctx.author.id},
        data={"hp": new_player_hp}
    )

    embed = discord.Embed(title=f"⚔️ World Boss Raid", color=0xcc0033)
    embed.set_author(name=player_data.get("name", ctx.author.name), icon_url=ctx.author.display_avatar.url)

    # Describe player's attack
    if is_miss:
        attack_desc = i18n.get(lang, "game.worldboss_attack_miss", boss=boss.name)
    else:
        crit_label = "💥 " if is_crit else ""
        hit_msg = i18n.get(lang, "game.worldboss_attack_hit", boss=boss.name, damage=base_dmg)
        attack_desc = f"{crit_label}{hit_msg}"

    # Describe boss's counter-attack
    if is_instakill:
        counter_desc = i18n.get(lang, "game.worldboss_retaliation_instakill", boss=boss.name)
    else:
        counter_desc = i18n.get(lang, "game.worldboss_retaliation_hit", boss=boss.name, damage=retaliation_dmg, hp=new_player_hp, max_hp=player.max_hp)

    embed.description = f"{attack_desc}\n\n{counter_desc}"

    if result["is_defeated"]:
        embed.title = "🎉 WORLD BOSS DEFEATED!"
        embed.color = 0x00ff66
        embed.description += f"\n\n**{boss.name}** " + i18n.get(lang, "game.worldboss_defeated_desc")

        # List reward shares
        shares_text = ""
        for share in result["rewards_distributed"][:15]:  # Show top 15 contributors
            shares_text += f"• **{share['username']}**: +`{share['coins']}` Coins, +`{share['exp']}` Exp ({share['share']}% share)\n"
        
        if shares_text:
            embed.add_field(name="🎁 Reward Distribution Summary", value=shares_text, inline=False)
    else:
        bar = make_progress_bar(result["boss_remaining_hp"], boss.maxHp)
        pct = round((result["boss_remaining_hp"] / boss.maxHp) * 100, 1)
        status_label = i18n.get(lang, "game.worldboss_status_hp")
        embed.add_field(
            name=f"{boss.name} Status",
            value=f"{status_label}: `{result['boss_remaining_hp']}/{boss.maxHp}` ({pct}%)\n`[{bar}]`",
            inline=False
        )

    await ctx.reply(embed=embed)
