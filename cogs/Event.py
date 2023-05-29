import discord
import os
from discord.ext import commands
from scripts.main import check_blacklist, event_available

class Event(commands.Cog):
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

    @commands.hybrid_group(name='event')
    @event_available()
    @check_blacklist()
    async def event(self, ctx) -> None:
        """
        Kumpulan command untuk event (ajang) yang sedang berlangsung. [GROUP]
        """
        await self.info(ctx)
        pass

    @event.command(name='info', description = 'Lihat info event yang sedang berlangsung!')
    @event_available()
    @check_blacklist()
    async def info(self, ctx:commands.Context) -> None:
        """
        Lihat info event yang sedang berlangsung!
        """
        embed = discord.Embed(title="RVDiA Rebrand", color=0xff4df0, url='https://drive.google.com/file/d/1EssMN38BXaA31O51mjr2vI4g20_cN3Kb/view?usp=drive_link')
        embed.set_author(name='Event Berlangsung:')
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.description = "Bot yang sebelumnya bernama RVDIA (Revolutionary Virtual Independent Discord Application), telah mengalami perubahan agar namanya lebih simpel dan mudah diingat oleh pengguna.\n\nMulai dari hari ini (<t:1685350330:D>), RVDiA (Revolutionary Virtual Discord Assistant) akan membantumu dalam menyelesaikan segala permasalahan, kecuali yang sangat pribadi yah.\n\nUntuk informasi mengenai fitur Game, akan saya coba implementasikan sebisa mungkin, berhubung jadwal saya yang cukup padat. Saya akan terus mencoba untuk memenuhi tujuan dari Project RVDiA, kebahagiaan, kemampuan, dan pengetahuan.\n\n-Schryzon"
        embed.set_image(url=os.getenv('bannerevent'))
        embed.set_footer(text='Revolusioner, Virtual, Independen; Aktif, Ceria, Menggemaskan.')
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(Event(bot))