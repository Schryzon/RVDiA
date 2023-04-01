import discord
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
        Kumpulan command untuk event (ajang) yang sedang berlangsung.
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
        embed = discord.Embed(title="April Fools!", color=0xff4df0)
        embed.set_author(name='Event Berlangsung:')
        embed.set_thumbnail(url='https://st.depositphotos.com/3246347/4454/i/950/depositphotos_44540065-stock-photo-calendar-1-april.jpg')
        embed.description = "April Mop, dikenal dengan April Fools' Day dalam bahasa Inggris, diperingati setiap tanggal 1 April setiap tahun. Pada hari itu, orang dianggap boleh berbohong atau memberi lelucon kepada orang lain tanpa dianggap bersalah. Hari ini ditandai dengan tipu-menipu dan lelucon lainnya terhadap keluarga, musuh, teman bahkan tetangga dengan tujuan mempermalukan orang-orang yang mudah ditipu. Di beberapa negara seperti Inggris dan Australia serta Afrika Selatan, lelucon hanya boleh dilakukan sampai siang atau sebelum siang hari.[1] Seseorang yang memainkan trik setelah tengah hari disebut sebagai \"April Mop\".[2] Namun di tempat lain seperti Kanada, Prancis, Irlandia, Italia, Rusia, Belanda, dan Amerika Serikat lelucon bebas dimainkan sepanjang hari. Hari itu juga banyak diperingati di Internet.\n April Fool's Day BBC"
        embed.set_image(url='https://i.ppy.sh/3269e52fe018f5c90c7a9cdd4ef6c3a3872ef3af/68747470733a2f2f6769746875622e636f6d2f4d696c6b697469632f4d696c6b697469632f626c6f622f6d61737465722f31653361653766366632663961306131666261326537326361393433636133622e3634307834383078312e6a70673f7261773d74727565')
        embed.set_footer(text='Give me 20 dolaz giv me 20 dolaz give mem 20 dolas no wifi in da club ay')
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(Event(bot))