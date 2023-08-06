import discord
import os
from discord import app_commands
from discord.ext import commands
from scripts.main import check_blacklist, event_available

class Event(commands.GroupCog, group_name = 'event'):
    """
    Kumpulan command untuk event (ajang) yang sedang berlangsung.
    """

    def __init__(self, bot) -> None:
        super().__init__()
        self.bot = bot

    def check_event(self, bot):
        match self.bot.event_mode:
            case True: return True
            case False: return False
            case _: return False

    @app_commands.command(name='info', description = 'Lihat info event yang sedang berlangsung!')
    @event_available()
    @check_blacklist()
    async def info(self, interaction:discord.Interaction) -> None:
        """
        Lihat info event yang sedang berlangsung!
        """
        embed = discord.Embed(title="Verified Bot", color=0xff4df0)
        embed.set_author(name='Event Berlangsung:')
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.description = os.getenv('eventnews')
        embed.set_image(url=os.getenv('bannerevent'))
        embed.set_footer(text='Revolusioner, Virtual, Independen.')
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Event(bot))