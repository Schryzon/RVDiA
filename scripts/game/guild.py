import discord
from discord.ui import View, Button, button
from prisma import Json
from scripts.main import db
from scripts.utils.i18n import i18n
from scripts.game.profile import get_user_lang, LeaderboardView


class GuildInviteView(View):
    def __init__(self, guild, target_user, lang="en"):
        super().__init__(timeout=60.0)
        self.guild = guild
        self.target_user = target_user
        self.lang = lang
        for child in self.children:
            if isinstance(child, Button):
                if child.custom_id == 'accept_invite':
                    child.label = 'Terima' if lang == 'id' else 'Accept'
                elif child.custom_id == 'decline_invite':
                    child.label = 'Tolak' if lang == 'id' else 'Decline'

    @discord.ui.button(label="Terima", style=discord.ButtonStyle.success, emoji="✅", custom_id="accept_invite")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            msg = i18n.get(self.lang, "game.invite_view_not_for_you")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        # Re-check if guild still exists
        guild_exists = await db.guild.find_unique(where={'id': self.guild.id})
        if not guild_exists:
            msg = i18n.get(self.lang, "game.invite_view_guild_gone")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        await db.user.update(where={'id': self.target_user.id}, data={'guild': {'connect': {'id': self.guild.id}}})
        msg = i18n.get(self.lang, "game.invite_view_accepted", mention=self.target_user.mention, name=self.guild.name)
        await interaction.response.edit_message(content=msg, view=None)

    @discord.ui.button(label="Tolak", style=discord.ButtonStyle.danger, emoji="❌", custom_id="decline_invite")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            msg = i18n.get(self.lang, "game.invite_view_not_for_you")
            return await interaction.response.send_message(msg, ephemeral=True)
        msg = i18n.get(self.lang, "game.invite_view_declined", mention=self.target_user.mention)
        await interaction.response.edit_message(content=msg, view=None)


# ── Command Executors ────────────────────────────────────────

async def execute_guild_info(ctx):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
    if not user_record or not user_record.guild:
        msg = i18n.get(lang, "game.guild_not_member")
        return await ctx.reply(msg, ephemeral=True)
    
    guild = user_record.guild
    members_count = await db.user.count(where={'guildId': guild.id})
    
    tagline_empty = i18n.get(lang, "game.guild_info_tagline_empty")
    embed = discord.Embed(title=guild.name, description=guild.tagline or tagline_empty, color=ctx.author.color)
    if guild.iconUrl:
        embed.set_thumbnail(url=guild.iconUrl)
    
    owner_name = i18n.get(lang, "game.guild_info_owner")
    embed.add_field(name=owner_name, value=f"<@{guild.ownerId}>")
    
    members_name = i18n.get(lang, "game.guild_info_members")
    members_value = i18n.get(lang, "game.guild_info_members_value", count=members_count)
    embed.add_field(name=members_name, value=members_value)
    
    date_str = guild.createdAt.strftime('%d/%m/%Y')
    footer_text = i18n.get(lang, "game.guild_info_footer", id=guild.id, date=date_str)
    embed.set_footer(text=footer_text)
    
    await ctx.reply(embed=embed)

async def execute_guild_create(ctx, name: str):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id})
    if not user_record:
        msg = i18n.get(lang, "game.guild_not_registered")
        return await ctx.reply(msg, ephemeral=True)
    
    if user_record.guildId:
        msg = i18n.get(lang, "game.guild_already_member")
        return await ctx.reply(msg, ephemeral=True)
        
    existing_owned = await db.guild.find_unique(where={'ownerId': ctx.author.id})
    if existing_owned:
        msg = i18n.get(lang, "game.guild_already_owns", name=existing_owned.name)
        return await ctx.reply(msg, ephemeral=True)
    
    data = user_record.data
    if data['coins'] < 5000:
        msg = i18n.get(lang, "game.guild_insufficient_coins", coins=data['coins'])
        return await ctx.reply(msg, ephemeral=True)
    
    existing = await db.guild.find_unique(where={'name': name})
    if existing:
        msg = i18n.get(lang, "game.guild_name_taken", name=name)
        return await ctx.reply(msg, ephemeral=True)
    
    new_guild = await db.guild.create(data={
        'name': name,
        'ownerId': ctx.author.id,
    })
    
    data['coins'] -= 5000
    await db.user.update(
        where={'id': ctx.author.id},
        data={
            'guild': {'connect': {'id': new_guild.id}},
            'data': Json(data)
        }
    )
    
    title_lbl = i18n.get(lang, "game.guild_created_title")
    desc_lbl = i18n.get(lang, "game.guild_created_desc", name=name)
    embed = discord.Embed(title=title_lbl, description=desc_lbl, color=discord.Color.gold())
    
    fee_lbl = i18n.get(lang, "game.guild_created_fee")
    embed.add_field(name="Biaya" if lang == "id" else "Cost", value=fee_lbl)
    
    footer_lbl = i18n.get(lang, "game.guild_created_footer")
    embed.set_footer(text=footer_lbl)
    
    await ctx.reply(embed=embed)

async def execute_guild_edit(ctx, name: str = None, tagline: str = None, icon_url: str = None):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
    if not user_record or not user_record.guild:
        msg = i18n.get(lang, "game.guild_edit_not_member")
        return await ctx.reply(msg, ephemeral=True)
    
    guild = user_record.guild
    if guild.ownerId != ctx.author.id:
        msg = i18n.get(lang, "game.guild_edit_not_owner")
        return await ctx.reply(msg, ephemeral=True)
    
    update_data = {}
    if name:
        existing = await db.guild.find_unique(where={'name': name})
        if existing and existing.id != guild.id:
            msg = i18n.get(lang, "game.guild_edit_name_taken", name=name)
            return await ctx.reply(msg, ephemeral=True)
        update_data['name'] = name
    if tagline:
        update_data['tagline'] = tagline
    if icon_url:
        if not icon_url.startswith("http"):
            msg = i18n.get(lang, "game.guild_edit_invalid_icon")
            return await ctx.reply(msg, ephemeral=True)
        update_data['iconUrl'] = icon_url
        
    if not update_data:
        msg = i18n.get(lang, "game.guild_edit_no_choices")
        return await ctx.reply(msg, ephemeral=True)
        
    await db.guild.update(where={'id': guild.id}, data=update_data)
    success_msg = i18n.get(lang, "game.guild_edit_success", name=name or guild.name)
    await ctx.reply(success_msg)

async def execute_guild_invite(ctx, user: discord.Member):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
    if not user_record or not user_record.guild:
        msg = i18n.get(lang, "game.guild_edit_not_member")
        return await ctx.reply(msg, ephemeral=True)
    
    guild = user_record.guild
    if guild.ownerId != ctx.author.id:
        msg = i18n.get(lang, "game.guild_invite_not_owner")
        return await ctx.reply(msg, ephemeral=True)
        
    target_record = await db.user.find_unique(where={'id': user.id})
    if not target_record:
        msg = i18n.get(lang, "game.guild_invite_target_not_registered")
        return await ctx.reply(msg, ephemeral=True)
    
    if target_record.guildId:
        msg = i18n.get(lang, "game.guild_invite_target_has_guild")
        return await ctx.reply(msg, ephemeral=True)
        
    view = GuildInviteView(guild, user, lang=lang)
    prompt_msg = i18n.get(lang, "game.guild_invite_prompt", mention=user.mention, name=guild.name)
    await ctx.reply(prompt_msg, view=view)

async def execute_guild_leave(ctx):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
    if not user_record or not user_record.guild:
        msg = i18n.get(lang, "game.guild_edit_not_member")
        return await ctx.reply(msg, ephemeral=True)
        
    guild = user_record.guild
    if guild.ownerId == ctx.author.id:
        await db.guild.delete(where={'id': guild.id})
        msg = i18n.get(lang, "game.guild_leave_disbanded", name=guild.name)
        await ctx.reply(msg)
    else:
        await db.user.update(where={'id': ctx.author.id}, data={'guild': {'disconnect': True}})
        msg = i18n.get(lang, "game.guild_leave_success", name=guild.name)
        await ctx.reply(msg)

async def execute_guild_leaderboard(ctx):
    lang = await get_user_lang(ctx.author.id)
    guilds = await db.guild.find_many(include={'members': True})
    if not guilds:
        msg = i18n.get(lang, "game.guild_lb_empty")
        return await ctx.reply(msg)
        
    sorted_guilds = sorted(guilds, key=lambda g: len(g.members), reverse=True)
    top_100 = sorted_guilds[:100]
    
    title_lbl = i18n.get(lang, "game.guild_leaderboard_title")
    view = LeaderboardView(ctx, top_100, title_lbl, type="guild", lang=lang)
    embed = await view.get_embed()
    await ctx.reply(embed=embed, view=view)

async def execute_guild_icon(ctx, url: str = None):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
    if not user_record or not user_record.guild:
        msg = i18n.get(lang, "game.guild_edit_not_member")
        return await ctx.reply(msg, ephemeral=True)
    
    guild = user_record.guild
    
    if url:
        if guild.ownerId != ctx.author.id:
            msg = i18n.get(lang, "game.guild_icon_owner_only")
            return await ctx.reply(msg, ephemeral=True)
        if not url.startswith("http"):
            msg = i18n.get(lang, "game.guild_edit_invalid_icon")
            return await ctx.reply(msg, ephemeral=True)
        
        await db.guild.update(where={'id': guild.id}, data={'iconUrl': url})
        msg = i18n.get(lang, "game.guild_icon_updated", name=guild.name)
        return await ctx.reply(msg)
        
    if not guild.iconUrl:
        msg = i18n.get(lang, "game.guild_icon_empty", name=guild.name)
        return await ctx.reply(msg)
        
    title_text = f"Guild Icon: {guild.name}" if lang == "en" else f"Ikon Guild: {guild.name}"
    embed = discord.Embed(title=title_text, color=ctx.author.color)
    embed.set_image(url=guild.iconUrl)
    await ctx.reply(embed=embed)
