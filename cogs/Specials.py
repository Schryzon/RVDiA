import discord
from discord.ext import commands
from os import getenv

# Commands only for special occasions
class Specials(commands.Cog):
    def __init__(self, bot) -> None:
        super().__init__()
        self.bot = bot

    @commands.command(hidden=True)
    @commands.is_owner()
    async def hbd_yoga(self, ctx):
        """
        Come on man, why are you looking at this?!
        """
        embed = discord.Embed(title="❤️ Happy Birthday, Kak Yoga!", color=0xff4df0)
        embed.set_author(name='Pesan dari RVDIA', url=self.bot.user.avatar.url)
        embed.set_thumbnail(url=getenv('yoga'))
        embed.description="Semoga panjang umur, sehat, dan sukses selalu.\nSemoga menjadi lebih kaya lagi biar bisa terus bisa membiayai programming journey Nanda dan buat beliin sarung tangan maimai.\nSekian dan terima kasih, mohon maaf bila ada salah kata saya tutup dengan parama santhi.\nOm Santhi, Santhi, Santhi Om."
        embed.set_image(url='https://t3.ftcdn.net/jpg/01/10/26/34/240_F_110263419_6d9oWmooHp0tLqQrG6ypqQk7KRqxIkSE.jpg')
        embed.set_footer(text="On behalf of Jayananda.", icon_url=ctx.author.avatar.url)
        await ctx.send(embed=embed)

async def setup(bot:commands.Bot):
    await bot.add_cog(Specials(bot))