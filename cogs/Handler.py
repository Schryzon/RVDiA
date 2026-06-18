
import discord
from discord.ui import View, Button
from discord.ext import commands
import os
import traceback
import sys
import logging
from scripts.i18n import i18n

"""
Error handlers, it's where the ifs and elifs go crazy!
"""

from scripts.errors import (
    NoProfilePicture,
    Blacklisted, NoEventAvailable, NotVoted, NoGameAccount, AccountIncompatible,
    ArtistOffline, GenerationDeclined, GenerationFailed, NSFWBlocked, GenerationTimeout
)
from scripts.error_logger import format_error_report

class Support_Button(View):
        def __init__(self):
            super().__init__(timeout=None)

            support_server = Button(
                label= "Support Server",
                emoji = '<:cyron:1082789553263349851>',
                style = discord.ButtonStyle.blurple,
                url = 'https://discord.gg/QqWCnk6zxw'
            )
            self.add_item(support_server)

class Error(commands.Cog):
  """
  An error handler class, what else do I have to say?
  """
  def __init__ (self, historia:commands.AutoShardedBot):
    self.historia = historia

  @commands.Cog.listener()
  async def on_command_error(self, ctx:commands.Context, error):
    # For error handling
    exc_info = sys.exc_info()

    try:
      if ctx.command.has_error_handler():
        return
    except:
      pass

    # Robustly unwrap errors (e.g. CommandInvokeError, HybridCommandError)
    while hasattr(error, "original"):
      error = error.original

    def format_permissions(error: commands.BotMissingPermissions):
      permlist = [req_perms.replace('_', ' ') for req_perms in error.missing_permissions]
      perms = [missing_perms.title() for missing_perms in permlist]
      return perms

    user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
    lang = user_settings.lang if user_settings else "en"

    if isinstance(error, commands.MissingRequiredArgument):
      msg = i18n.get(lang, "errors.missing_argument", param=error.param)
      await ctx.reply(msg)

    elif isinstance(error, Blacklisted):
      msg = i18n.get(lang, "errors.blacklisted")
      await ctx.reply(msg)

    elif isinstance(error, commands.CommandNotFound):
      msg = i18n.get(lang, "errors.command_not_found", prefix=ctx.clean_prefix)
      await ctx.reply(msg)

    elif isinstance(error, commands.NoPrivateMessage):
      msg = i18n.get(lang, "errors.no_private_message")
      await ctx.reply(msg)
      
    elif isinstance(error, commands.MemberNotFound):
      msg = i18n.get(lang, "errors.member_not_found")
      await ctx.reply(msg)
      
    elif isinstance(error, commands.TooManyArguments):
      msg = i18n.get(lang, "errors.too_many_arguments")
      await ctx.reply(msg)

    elif isinstance(error, commands.UserNotFound):
      msg = i18n.get(lang, "errors.user_not_found")
      await ctx.reply(msg)

    elif isinstance(error, commands.NSFWChannelRequired):
      msg = i18n.get(lang, "errors.nsfw_channel_required")
      await ctx.reply(msg)

    elif isinstance(error, commands.MissingRole):
      msg = i18n.get(lang, "errors.missing_role")
      await ctx.reply(msg)

    elif isinstance(error, commands.ChannelNotFound):
      msg = i18n.get(lang, "errors.channel_not_found")
      await ctx.reply(msg)

    elif isinstance(error, commands.CommandOnCooldown):
      msg = i18n.get(lang, "errors.command_on_cooldown", seconds=round(error.retry_after))
      await ctx.reply(msg)

    elif isinstance(error, commands.RoleNotFound):
      msg = i18n.get(lang, "errors.role_not_found")
      await ctx.reply(msg)

    elif isinstance(error, commands.NotOwner):
      msg = i18n.get(lang, "errors.not_owner")
      await ctx.reply(msg)

    elif isinstance(error, NoProfilePicture):
      msg = i18n.get(lang, "errors.no_pfp")
      await ctx.reply(msg)

    elif isinstance(error, commands.BotMissingPermissions):
      perms = format_permissions(error)
      msg = i18n.get(lang, "errors.bot_missing_permissions", perms=",".join(perms))
      await ctx.reply(msg)

    elif isinstance(error, commands.MissingPermissions):
      perms = format_permissions(error)
      msg = i18n.get(lang, "errors.missing_permissions", perms=",".join(perms))
      await ctx.reply(msg)

    elif isinstance(error, discord.Forbidden) or "Forbidden" in str(error):
      msg = i18n.get(lang, "errors.forbidden")
      await ctx.reply(msg)

    elif "Invalid base64-encoded string" in str(error) or "Incorrect padding" in str(error):
      msg = i18n.get(lang, "errors.invalid_base64")
      await ctx.reply(msg)

    elif "Your prompt may contain text that is not allowed by our safety system." in str(error):
      msg = i18n.get(lang, "errors.prompt_blocked")
      await ctx.reply(msg)

    elif "Uploaded image must be a PNG and less than 4 MB." in str(error):
      msg = i18n.get(lang, "errors.image_upload_error")
      await ctx.reply(msg)

    elif "cannot identify image file" in str(error):
      msg = i18n.get(lang, "errors.image_identify_error")
      await ctx.reply(msg)

    elif isinstance(error, NoEventAvailable):
      msg = i18n.get(lang, "errors.no_event_available")
      await ctx.reply(msg)

    elif "missing an attachment." in str(error):
      msg = i18n.get(lang, "errors.missing_attachment")
      await ctx.reply(msg)

    elif "Your input image may contain content that is not allowed by our safety system." in str(error):
      msg = i18n.get(lang, "errors.image_safety_blocked")
      await ctx.reply(msg)

    elif "currently overloaded with other requests." in str(error):
      msg = i18n.get(lang, "errors.overloaded")
      await ctx.reply(msg)

    elif "Rate limit reached for" in str(error):
      msg = i18n.get(lang, "errors.rate_limited")
      await ctx.reply(msg)

    elif isinstance(error, NotVoted):
      class Vote_Button(View):
        def __init__(self):
            super().__init__(timeout=None)
            label_text = i18n.get(lang, "errors.not_voted_label")
            vote_me = Button(
                    label=label_text, 
                    emoji='<:rvdia:1082789733001875518>',
                    style=discord.ButtonStyle.green, 
                    url='https://top.gg/bot/957471338577166417/vote'
                    )
            self.add_item(vote_me)
      msg = i18n.get(lang, "errors.not_voted")
      await ctx.reply(msg, view=Vote_Button())

    elif isinstance(error, NoGameAccount):
      msg = i18n.get(lang, "errors.no_game_account", prefix=ctx.clean_prefix)
      await ctx.reply(msg)

    elif isinstance(error, ConnectionResetError) or "reset by peer" in str(error) or "Can't reach database" in str(error):
      msg = i18n.get(lang, "errors.database_connection_reset")
      await ctx.reply(msg, view=Support_Button())

    elif "Invalid Form Body In message_reference: Unknown message" in str(error):
      msg = i18n.get(lang, "errors.message_reference_unknown")
      await ctx.reply(msg)

    elif "Rival has no account!" in str(error):
      msg = i18n.get(lang, "errors.rival_no_account")
      await ctx.reply(msg)

    elif isinstance(error, AccountIncompatible):
      msg = i18n.get(lang, "errors.account_incompatible", prefix=ctx.clean_prefix)
      await ctx.reply(msg)

    elif isinstance(error, ArtistOffline):
      msg = i18n.get(lang, "errors.artist_offline")
      await ctx.reply(msg)

    elif isinstance(error, GenerationDeclined):
      msg = i18n.get(lang, "errors.generation_declined")
      await ctx.reply(msg)

    elif isinstance(error, GenerationFailed):
      error_msg = str(error) if str(error) else i18n.get(lang, "errors.unhandled_error")
      await ctx.reply(error_msg)

    elif isinstance(error, NSFWBlocked):
      msg = i18n.get(lang, "errors.nsfw_blocked")
      await ctx.reply(msg)

    elif isinstance(error, GenerationTimeout):
      msg = i18n.get(lang, "errors.generation_timeout")
      await ctx.reply(msg)

    else:
      error_channel_id = os.getenv("errorchannel")
      if error_channel_id:
          channel = self.historia.get_channel(int(error_channel_id))
          embed = format_error_report(error, context=f"Command: {ctx.command}")
          
          if channel:
              owner_id = os.getenv("schryzonid")
              await channel.send(f"<@{owner_id}> **Error from console!**", embed=embed)
      
      msg = i18n.get(lang, "errors.unhandled_error")
      await ctx.reply(msg, view=Support_Button(), ephemeral=True)
      logging.error(f"Error in command {ctx.command}: {str(error)}")

async def setup(pandora):
  await pandora.add_cog(Error(pandora))