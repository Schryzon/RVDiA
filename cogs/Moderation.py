import discord
from discord import app_commands
from scripts.main import db, check_blacklist
from os import getenv
from discord.ext import commands
from scripts.utils.i18n import i18n

class Moderation(commands.Cog):
    """
    Commands for server moderation.
    """

    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_group(name='server')
    @commands.guild_only()
    @check_blacklist()
    async def server(self, ctx:commands.Context) -> None:
        """
        Server information commands.
        """
        await self.info(ctx)
        pass

    @server.command(description='View info about this server!')
    @check_blacklist()
    async def info(self, ctx:commands.Context):
        """
        View info about this server!
        """
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            owner = await self.bot.fetch_user(ctx.guild.owner_id)
            guild_icon = ctx.guild.icon.url if not ctx.guild.icon is None else getenv('normalpfp')
            timestamp = ctx.message.created_at if ctx.message else ctx.interaction.created_at
            embed = discord.Embed(title=f'{ctx.guild.name}', color=ctx.author.colour, timestamp = timestamp)
            embed.set_thumbnail(url=guild_icon)
            embed.set_author(name=i18n.get(lang, "moderation.info_header"))
            embed.add_field(name=i18n.get(lang, "moderation.info_owner"), value=f"{owner.mention} ({owner})", inline = False)
            embed.add_field(name=i18n.get(lang, "moderation.info_created"), value=f'{ctx.guild.created_at.strftime("%a, %d %B %Y")}', inline = False)
            
            members_val = i18n.get(lang, "moderation.info_members_val", count=ctx.guild.member_count)
            embed.add_field(name=i18n.get(lang, "moderation.info_members"), value=members_val, inline = False)
            embed.set_footer(text=f"ID: {ctx.guild.id}", icon_url=guild_icon)
            await ctx.reply(embed=embed)

    @server.command(description="Display the icon of this server.")
    @check_blacklist()
    async def icon(self, ctx:commands.Context):
        """
        Display the icon of this server.
        """
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"
            
            guild = ctx.guild

            if guild.icon is None:
                return await ctx.reply(i18n.get(lang, "moderation.icon_none"))
            png = guild.icon.with_format("png").url
            jpg = guild.icon.with_format("jpg").url
            webp = guild.icon.with_format("webp").url

            title_txt = i18n.get(lang, "moderation.icon_title", name=guild.name)
            embed=discord.Embed(title=title_txt, url = guild.icon.with_format("png").url, color=self.bot.color)

            if guild.icon.is_animated():
                gif = guild.icon.with_format("gif").url
                embed.set_image(url = guild.icon.with_format("gif").url)
                embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp}) | [gif]({gif})"

            else:
                embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp})"
                embed.set_image(url = guild.icon.with_format("png").url)
            embed.set_footer(text=f"{ctx.author}", icon_url=ctx.author.display_avatar.url)
            await ctx.reply(embed=embed)

    @commands.hybrid_group(name='invite')
    @commands.guild_only()
    @commands.bot_has_permissions(manage_guild=True)
    @check_blacklist()
    async def invite(self, ctx:commands.Context) -> None:
        """
        Invite link management commands.
        """
        await self.invites(ctx)
        pass

    @invite.command(name='create', description='Create an instant invite link!')
    @commands.bot_has_permissions(manage_guild=True)
    @app_commands.describe(
        expire = 'How long before this invite link expires? (seconds, default: never)',
        max_use = 'Max number of people who can use this invite? (default: unlimited)'
        )
    @check_blacklist()
    async def create(self, ctx:commands.Context, expire:int=0, max_use:int=0):
        """
        Create an instant invite link!
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        created_invite = await ctx.channel.create_invite(
            reason=f'Created using /invite create command by {ctx.author}.', 
            max_age=expire,
            max_uses=max_use
            )
        
        msg = i18n.get(lang, "moderation.invite_created", url=str(created_invite))
        await ctx.reply(msg)

    @invite.command(name='view', description='View the list of invite links for this server!')
    @commands.bot_has_permissions(manage_guild=True)
    @check_blacklist()
    async def invites(self, ctx:commands.Context):
        """
        View the list of invite links for this server!
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        try:
            invites = await ctx.guild.invites()
            invite_list = []

            for v in invites:
                text = i18n.get(
                    lang,
                    "moderation.invite_list_item",
                    url=v.url,
                    author=str(v.inviter),
                    expire=str(v.expires_at)
                )
                invite_list.append(text)

            timestamp = ctx.message.created_at if ctx.message else ctx.interaction.created_at
            title_txt = i18n.get(lang, "moderation.invite_list_title", name=ctx.guild.name)
            embed = discord.Embed(title=title_txt, color=ctx.author.color, timestamp=timestamp)
            embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else getenv('normalpfp'))
            embed.description = '\n'.join(invite_list)
            if not embed.description or embed.description == '':
                return await ctx.reply(i18n.get(lang, "moderation.invite_none"))
            await ctx.reply(embed=embed)

        except AttributeError:
            await ctx.reply(i18n.get(lang, "moderation.invite_none"))

    @commands.hybrid_group(name='warn')
    @commands.guild_only()
    @commands.has_permissions(manage_messages= True)
    @check_blacklist()
    async def warn(self, ctx:commands.Context, member:discord.Member, *, reason = None):
        """
        Warning system commands.
        """
        await self.warn_add(ctx, member, reason=reason)
        
    @warn.command(
        name = 'add',
        description="Issue a warning to a member in this server."
        )
    @app_commands.describe(
        member = 'The user who violated rules',
        reason = 'Reason for the warning'
    )
    @commands.has_permissions(manage_messages= True)
    @check_blacklist()
    async def warn_add(self, ctx:commands.Context, member:discord.Member, *, reason = None):
        """
        Issue a warning to a member.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if ctx.author == member:
            return await ctx.reply(i18n.get(lang, "moderation.warn_self_error"), ephemeral=True)
        if member.bot:
            return await ctx.reply(i18n.get(lang, "moderation.warn_bot_error"), ephemeral=True)
        
        default_reason = i18n.get(lang, "moderation.warn_no_reason")
        reason = reason or default_reason

        # Create warning record
        await db.warning.create(data={
            'guildId': ctx.guild.id,
            'userId': member.id,
            'reason': reason
        })

        # Count total warnings for this user in this guild
        warnqty = await db.warning.count(where={
            'guildId': ctx.guild.id,
            'userId': member.id
        })

        title_txt = i18n.get(lang, "moderation.warn_added_title")
        desc_txt = i18n.get(lang, "moderation.warn_added_desc", member=member.mention, count=warnqty)
        em = discord.Embed(title=title_txt, description=desc_txt, color = member.colour)
        
        em.add_field(name=i18n.get(lang, "moderation.warn_added_reason"), value=reason, inline=False)
        em.set_thumbnail(url = member.display_avatar.url)
        
        footer_txt = i18n.get(lang, "moderation.warn_added_footer", author=str(ctx.author), author_id=ctx.author.id)
        em.set_footer(text=footer_txt, icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed = em)

    @warn.command(
        name='history',
        description="View warning history of a member in this server.",
    )
    @app_commands.describe(
        member = 'The member to query'
    )
    @commands.has_permissions(manage_messages = True)
    @check_blacklist()
    async def warnhistory(self, ctx:commands.Context, member:discord.Member=None):
            """
            View warning history of a member.
            """
            member = member or ctx.author
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            warns = await db.warning.find_many(where={
                'guildId': ctx.guild.id,
                'userId': member.id
            }, order={'createdAt': 'desc'})
            
            if not warns:
                msg = i18n.get(lang, "moderation.warn_history_none", member=str(member))
                return await ctx.reply(msg, ephemeral=True)
            
            warn_count = len(warns)
            reasons = [w.reason for w in warns]
            
            title_txt = i18n.get(lang, "moderation.warn_history_title", member=str(member))
            emb = discord.Embed(title=title_txt, color=member.colour)
            emb.add_field(name=i18n.get(lang, "moderation.warn_history_count_label"), value=str(warn_count), inline=False)
            
            reasons_text = "\n".join([f"{i+1}. {r}" for i, r in enumerate(reasons)])
            if warn_count > 1:
                emb.add_field(name=i18n.get(lang, "moderation.warn_history_reasons_latest"), value=f"*{reasons_text}*")
            else:
                emb.add_field(name=i18n.get(lang, "moderation.warn_history_reasons_single"), value=f"*{reasons_text}*")
            emb.set_thumbnail(url = member.display_avatar.url)
            await ctx.reply(embed = emb)

    @warn.command(name='remove', description="Clear all warnings for a member.")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(
        member = 'The member whose warnings will be cleared'
    )
    @check_blacklist()
    async def removewarn(self, ctx:commands.Context, member:discord.Member):
        """
        Clear all warnings for a member.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        deleted = await db.warning.delete_many(where={
            'guildId': ctx.guild.id,
            'userId': member.id
        })
        
        if deleted == 0:
            msg = i18n.get(lang, "moderation.warn_remove_none", member=str(member))
            return await ctx.reply(msg)
        
        success_msg = i18n.get(lang, "moderation.warn_remove_success", member=member.mention)
        await ctx.reply(success_msg)

    @warn.command(name='list', description="List all users with warnings in this server.")
    @commands.has_permissions(manage_messages=True)
    @check_blacklist()
    async def warnlist(self, ctx:commands.Context):
        """
        List all users with warnings in this server.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        # Get unique user IDs with warnings in this guild
        warns = await db.warning.find_many(where={'guildId': ctx.guild.id})
        if not warns:
            return await ctx.reply(i18n.get(lang, "moderation.warn_list_none"))
        
        user_warns = {}
        for w in warns:
            user_warns[w.userId] = user_warns.get(w.userId, 0) + 1
            
        text = []
        for user_id, count in user_warns.items():
            try:
                user = await self.bot.fetch_user(user_id)
                text.append(i18n.get(lang, "moderation.warn_list_item", user=str(user), count=count))
            except:
                text.append(i18n.get(lang, "moderation.warn_list_item_unknown", user_id=user_id, count=count))
        
        timestamp = ctx.message.created_at if ctx.message else ctx.interaction.created_at
        title_txt = i18n.get(lang, "moderation.warn_list_title", guild=ctx.guild.name)
        embed = discord.Embed(title=title_txt, color=ctx.author.color, timestamp=timestamp)
        embed.description = '\n'.join(text)
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else getenv('normalpfp'))
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name='ultban', description="Ban a user from the server, even if they are not currently in it.")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        user = 'User to ban (ID or name#tag)',
        reason = 'Reason for the ban'
    )
    @check_blacklist()
    async def ultban(self, ctx:commands.Context, user:discord.User, *, reason = None):
        """
        Ban a user from the server.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        default_reason = i18n.get(lang, "moderation.warn_no_reason")
        reason = reason or default_reason

        await ctx.guild.ban(user)
        title_txt = i18n.get(lang, "moderation.ban_success_title")
        embed = discord.Embed(title=title_txt, color = ctx.author.colour)
        desc_txt = i18n.get(lang, "moderation.ban_success_desc", user=str(user))
        embed.description = desc_txt
        embed.add_field(name=i18n.get(lang, "moderation.ban_success_reason"), value = reason, inline = False)
        embed.set_thumbnail(url = user.display_avatar.url)
        footer_txt = i18n.get(lang, "moderation.ban_success_footer", author=str(ctx.author), author_id=ctx.author.id)
        embed.set_footer(text=footer_txt, icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed = embed)

    @commands.hybrid_command(description="Unban a previously banned user.")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        user = 'User to unban (ID or name#tag)'
    )
    @check_blacklist()
    async def unban(self, ctx:commands.Context, user: discord.User):
        """
        Unban a previously banned user.
        """
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            try:
                await ctx.guild.unban(user)
                await ctx.send(i18n.get(lang, "moderation.unban_success", user=str(user)))
                return
            except:
                await ctx.send(i18n.get(lang, "moderation.unban_not_found", user=str(user)))
                return

    @commands.hybrid_command(aliases = ['clean', 'purge', 'delete', 'hapus'], 
                      description="Bulk delete messages in a channel.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @app_commands.describe(
        amount = 'Number of messages to delete',
        channel = 'Target channel to clear (defaults to current channel)'
    )
    @check_blacklist()
    async def clear(self, ctx:commands.Context, amount:int, channel:discord.TextChannel = None):
        """
        Bulk delete messages in a channel.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        channel = channel or ctx.channel
        if amount <= 0:
            return await ctx.reply(i18n.get(lang, "moderation.clear_zero_error"), ephemeral=True)
        elif amount >= 100:
            return await ctx.reply(i18n.get(lang, "moderation.clear_limit_error"), ephemeral=True)
        
        match channel:
            case ctx.channel:
                msg = i18n.get(lang, "moderation.clear_deleting_here", amount=amount)
                await ctx.reply(msg)
            case _:
                msg = i18n.get(lang, "moderation.clear_deleting_there", amount=amount, channel=channel.mention)
                await ctx.reply(msg, delete_after=10.0)

        async with ctx.channel.typing():
            await channel.purge(limit = amount+1 if channel == ctx.channel else amount)
        
        success_msg = i18n.get(lang, "moderation.clear_success", amount=amount, channel=channel.mention)
        return await ctx.channel.send(success_msg, delete_after = 5.0)

    @commands.hybrid_group(name="automod", description="Manage Discord's native AutoMod rules.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @check_blacklist()
    async def automod(self, ctx: commands.Context):
        """
        Manage Discord's native AutoMod rules.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @automod.command(name="list", description="List all active Discord native AutoMod rules in the server.")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @check_blacklist()
    async def list(self, ctx: commands.Context):
        """
        List all active Discord native AutoMod rules in the server.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        try:
            rules = await ctx.guild.fetch_automod_rules()
            if not rules:
                return await ctx.reply(i18n.get(lang, "moderation.automod_list_empty"))

            lines = []
            for r in rules:
                trigger_name = r.trigger.type.name
                enabled_str = "YES" if r.enabled else "NO"
                lines.append(i18n.get(lang, "moderation.automod_rule_item", name=r.name, id=r.id, trigger=trigger_name, enabled=enabled_str))

            embed = discord.Embed(
                title=i18n.get(lang, "moderation.automod_list_title", name=ctx.guild.name),
                description="\n".join(lines),
                color=self.bot.color
            )
            await ctx.reply(embed=embed)
        except Exception as e:
            await ctx.reply(i18n.get(lang, "moderation.automod_error", error=str(e)))

    @automod.command(name="create_keyword", description="Create a keyword-based AutoMod rule to block specific words.")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @app_commands.describe(
        name="The unique name of the AutoMod rule.",
        words="Comma-separated words/phrases to block (e.g. hack, scam, *nitro*).",
        alert_channel="Optional channel to send alerts to when a word is blocked."
    )
    @check_blacklist()
    async def create_keyword(self, ctx: commands.Context, name: str, words: str, alert_channel: discord.TextChannel = None):
        """
        Create a keyword-based AutoMod rule to block specific words.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        words_list = [w.strip() for w in words.split(",") if w.strip()]
        if not words_list:
            return await ctx.reply("Please provide at least one valid word to block.", ephemeral=True)

        try:
            trigger = discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.keyword, keyword_filter=words_list)
            actions = [discord.AutoModRuleAction()]
            if alert_channel:
                actions.append(discord.AutoModRuleAction(channel_id=alert_channel.id))

            await ctx.guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=actions,
                enabled=True,
                reason=f"Created via RVDiA automod command by {ctx.author}"
            )
            await ctx.reply(i18n.get(lang, "moderation.automod_keyword_created", name=name))
        except Exception as e:
            await ctx.reply(i18n.get(lang, "moderation.automod_error", error=str(e)))

    @automod.command(name="create_spam", description="Create or enable a mention spam filter rule.")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @app_commands.describe(
        mention_limit="Max number of unique mentions allowed in a single message (default: 5)."
    )
    @check_blacklist()
    async def create_spam(self, ctx: commands.Context, mention_limit: int = 5):
        """
        Create or enable a mention spam filter rule.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        try:
            trigger = discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.mention_spam, mention_limit=mention_limit)
            actions = [discord.AutoModRuleAction()]

            await ctx.guild.create_automod_rule(
                name=f"RVDiA Mention Spam Filter ({mention_limit})",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=actions,
                enabled=True,
                reason=f"Created via RVDiA automod command by {ctx.author}"
            )
            await ctx.reply(i18n.get(lang, "moderation.automod_spam_created", limit=mention_limit))
        except Exception as e:
            await ctx.reply(i18n.get(lang, "moderation.automod_error", error=str(e)))

    @automod.command(name="create_preset", description="Enable a pre-configured keyword preset rule from Discord.")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @app_commands.describe(
        preset_type="The category preset to enable (profanity, sexual_content, slurs)."
    )
    @app_commands.choices(preset_type=[
        app_commands.Choice(name="Profanity", value="profanity"),
        app_commands.Choice(name="Sexual Content", value="sexual_content"),
        app_commands.Choice(name="Slurs", value="slurs")
    ])
    @check_blacklist()
    async def create_preset(self, ctx: commands.Context, preset_type: str):
        """
        Enable a pre-configured keyword preset rule from Discord.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        try:
            presets_object = discord.AutoModPresets.none()
            if preset_type == "profanity":
                presets_object.profanity = True
            elif preset_type == "sexual_content":
                presets_object.sexual_content = True
            elif preset_type == "slurs":
                presets_object.slurs = True

            trigger = discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.keyword_preset, presets=presets_object)
            actions = [discord.AutoModRuleAction()]

            rule_name = f"RVDiA Preset Filter - {preset_type.replace('_', ' ').title()}"
            await ctx.guild.create_automod_rule(
                name=rule_name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=actions,
                enabled=True,
                reason=f"Created via RVDiA automod command by {ctx.author}"
            )
            await ctx.reply(i18n.get(lang, "moderation.automod_preset_created", preset=preset_type.replace('_', ' ').title()))
        except Exception as e:
            await ctx.reply(i18n.get(lang, "moderation.automod_error", error=str(e)))

    @automod.command(name="delete", description="Delete a Discord native AutoMod rule by its name or ID.")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @app_commands.describe(
        rule_name_or_id="The name or ID of the AutoMod rule to delete."
    )
    @check_blacklist()
    async def delete(self, ctx: commands.Context, rule_name_or_id: str):
        """
        Delete a Discord native AutoMod rule by its name or ID.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        try:
            rules = await ctx.guild.fetch_automod_rules()
            target_rule = None
            for r in rules:
                if str(r.id) == rule_name_or_id or r.name.lower() == rule_name_or_id.lower():
                    target_rule = r
                    break

            if not target_rule:
                return await ctx.reply(i18n.get(lang, "moderation.automod_rule_not_found", query=rule_name_or_id))

            await target_rule.delete(reason=f"Deleted via RVDiA automod command by {ctx.author}")
            await ctx.reply(i18n.get(lang, "moderation.automod_deleted", name=target_rule.name))
        except Exception as e:
            await ctx.reply(i18n.get(lang, "moderation.automod_error", error=str(e)))

async def setup(bot):
    await bot.add_cog(Moderation(bot))