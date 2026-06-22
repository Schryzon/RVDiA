import discord
from datetime import datetime, timedelta, timezone
from os import getenv
from scripts.main import db
from scripts.utils.i18n import i18n
from scripts.game.profile import get_user_lang

# ── Command Executors ────────────────────────────────────────

async def execute_premium_info(ctx):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id})
    if not user_record:
        msg = i18n.get(lang, "game.premium_not_registered")
        return await ctx.reply(msg)
        
    premium_time = user_record.premiumUntil
    if premium_time and premium_time.tzinfo is None:
        premium_time = premium_time.replace(tzinfo=timezone.utc)
    is_p = bool(premium_time and premium_time > datetime.now(timezone.utc))
    
    embed = discord.Embed(title="💎 Dream Weaver Premium 💎", color=0x00ffff)
    if is_p:
        embed.description = i18n.get(lang, "game.premium_active_desc", timestamp=int(user_record.premiumUntil.timestamp()))
    else:
        embed.description = i18n.get(lang, "game.premium_inactive_desc")
        
    benefits_title = i18n.get(lang, "game.premium_benefits_title")
    benefits_desc = i18n.get(lang, "game.premium_benefits_desc")
    embed.add_field(name=benefits_title, value=benefits_desc, inline=False)
    
    footer_text = i18n.get(lang, "game.premium_footer")
    embed.set_footer(text=footer_text)
    await ctx.reply(embed=embed)

async def execute_premium_buy(ctx, bot):
    lang = await get_user_lang(ctx.author.id)
    saweria_link = getenv('SAWERIA_LINK', 'https://saweria.co/Schryzon')
    
    title_text = "💎 How to Become a Dream Weaver" if lang == "en" else "💎 Cara Menjadi Dream Weaver"
    embed = discord.Embed(title=title_text, color=0x00ffff)
    embed.description = i18n.get(lang, "game.premium_buy_desc", saweria_link=saweria_link)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.reply(embed=embed)

async def execute_premium_claim(ctx, bot, bukti: discord.Attachment):
    lang = await get_user_lang(ctx.author.id)
    staff_channel_id = getenv('STAFF_CHANNEL_ID')
    if not staff_channel_id:
        msg = i18n.get(lang, "game.premium_claim_no_channel")
        return await ctx.reply(msg, ephemeral=True)
        
    staff_channel = bot.get_channel(int(staff_channel_id))
    if not staff_channel:
        msg = i18n.get(lang, "game.premium_claim_config_error")
        return await ctx.reply(msg, ephemeral=True)
        
    embed = discord.Embed(title="💎 Klaim Premium Baru!", color=0x00ffff)
    embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
    embed.add_field(name="User ID", value=f"`{ctx.author.id}`", inline=True)
    embed.add_field(name="User Mention", value=ctx.author.mention, inline=True)
    embed.set_image(url=bukti.url)
    embed.set_footer(text=f"Gunakan approve_premium {ctx.author.id} untuk menyetujui.")
    await staff_channel.send(embed=embed)
    
    success_msg = i18n.get(lang, "game.premium_claim_success")
    await ctx.reply(success_msg, ephemeral=True)

async def execute_approve_premium(ctx, user: discord.User):
    staff_lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': user.id})
    if not user_record:
        msg = i18n.get(staff_lang, "game.premium_approve_not_found")
        return await ctx.reply(msg)
        
    now = datetime.now(timezone.utc)
    premium_time = user_record.premiumUntil
    if premium_time and premium_time.tzinfo is None:
        premium_time = premium_time.replace(tzinfo=timezone.utc)
        
    if premium_time and premium_time > now:
        new_expiry = premium_time + timedelta(days=30)
    else:
        new_expiry = now + timedelta(days=30)
        
    await db.user.update(where={'id': user.id}, data={'premiumUntil': new_expiry})
    
    success_msg = i18n.get(staff_lang, "game.premium_approve_success", name=user.name, timestamp=int(new_expiry.timestamp()))
    await ctx.reply(success_msg)
    
    try:
        user_lang = await get_user_lang(user.id)
        dm_msg = i18n.get(user_lang, "game.premium_dm_success", timestamp=int(new_expiry.timestamp()))
        await user.send(dm_msg)
    except:
        pass
