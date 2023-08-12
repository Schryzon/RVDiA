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
        embed.description = "RVDiA, bot yang sebelumnya hanya untuk sekedar hobi dan tugas G-Tech Re'sman, sekarang telah terverifikasi (diakui) oleh Discord. Saya berterima kasih atas dukungan yang teman-teman telah berikan kepada saya, Schryzon, seorang programmer muda. Dengan terverifikasinya RVDiA, saya mendapatkan lebih banyak pengalaman dan kemampuan sebagai Solo Developer.\n\nRVDiA akan terus mendapatkan update, improvement, bug fix, dan tambahan fitur lainnya. Mohon maaf sebesar-besarnya bila saya kurang aktif dalam mengadakan update. Saya akan mencoba untuk menerapkan segala perbaikan pada waktu luang saya.\n\nTerima kasih banyak!\n-Schryzon, 06/08/2023"
        embed.set_image(url=os.getenv('bannerevent'))
        embed.set_footer(text='Revolusioner, Virtual, Independen.')
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Event(bot))