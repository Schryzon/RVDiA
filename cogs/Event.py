import discord
import os
from discord import app_commands
from discord.ext import commands
from scripts.main import db, check_blacklist, event_available
from scripts.utils.i18n import i18n

class Event(commands.GroupCog, group_name = 'event'):
    """
    Commands for ongoing events.
    """

    def __init__(self, bot) -> None:
        super().__init__()
        self.bot = bot

    def check_event(self, bot):
        match self.bot.event_mode:
            case True: return True
            case False: return False
            case _: return False

    @app_commands.command(name='info', description = 'View information about the ongoing event!')
    @event_available()
    @check_blacklist()
    async def info(self, interaction:discord.Interaction) -> None:
        """
        View information about the ongoing event!
        """
        user_settings = await db.usersettings.find_unique(where={'userId': interaction.user.id})
        lang = user_settings.lang if user_settings else "en"

        embed = discord.Embed(title="Rebirth v2.0.0", color=0xff4df0)
        embed.set_author(name=i18n.get(lang, "event.info_author"))
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.description = i18n.get(lang, "event.info_desc")
        embed.set_image(url=os.getenv('bannerevent'))
        embed.set_footer(text=i18n.get(lang, "event.info_footer"))
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Event(bot))