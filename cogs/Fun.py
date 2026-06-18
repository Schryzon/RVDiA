from os import remove
import random
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image
from io import BytesIO
from scripts.main import db, has_voted, check_blacklist
from scripts.i18n import i18n

class Fun(commands.Cog):
    """
    Command khusus untuk bersenang-senang
    """
    def __init__(self, bot):
        self.bot = bot
               
    @commands.hybrid_command(aliases=['jodohkan', 'jodoh'], description="Jodohkan seseorang denganmu atau orang lain!")
    @app_commands.rename(member1='pengguna_1', member2='pengguna_2')
    @app_commands.describe(member1='Siapa yang nembak nih?', member2='Siapa pasangannya?')
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_voted()
    @check_blacklist()
    async def ship(self, ctx:commands.Context, member1: discord.Member, member2:discord.Member):
        """
        Jodohkan seorang teman atau orang lain dengan pengguna lainnya!
        """
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            if member1 == ctx.author and member2 == ctx.author:
                await ctx.send(i18n.get(lang, "fun.ship_self_error"))
                return
            
            success = random.randint(1, 100)
            ship_map = [
                (100, "fun.ship_range_100", "./src/ships/ship.png"),
                (90, "fun.ship_range_90", "./src/ships/ship.png"),
                (80, "fun.ship_range_80", "./src/ships/ship.png"),
                (70, "fun.ship_range_70", "./src/ships/fship.png"),
                (50, "fun.ship_range_50", "./src/ships/gship.png"),
                (25, "fun.ship_range_25", "./src/ships/bship.png"),
                (0, "fun.ship_range_0", "./src/ships/shship.png")
            ]

            for threshold, key, image_path in ship_map:
                if success >= threshold:
                    ss = i18n.get(lang, key, member1=member1.name, member2=member2.name)
                    sus = Image.open(image_path)
                    break

            asset1 = member1.display_avatar.with_format('png').with_size(128)
            asset2 = member2.display_avatar.with_format('png').with_size(128)
            data1 = BytesIO(await asset1.read())
            data2 = BytesIO(await asset2.read())
            pfp1 = Image.open(data1)
            pfp1 = pfp1.resize((420, 420))
            sus.paste(pfp1, (90, 28))
            pfp2 = Image.open(data2)
            pfp2 = pfp2.resize((420, 420))
            sus.paste(pfp2, (1024, 28))
            res_filename = f'shipres_{ctx.author.id}.png'
            sus.save(res_filename)

            L = len(member1.name)//2
            LL = len(member2.name)//2
            
            title_text = i18n.get(lang, "fun.ship_title")
            ship_name_label = i18n.get(lang, "fun.ship_name_prefix")
            embed = discord.Embed(
                title=title_text,
                description=f"❤️ **{success}%** ❤️\n{ss}\n**{ship_name_label}:** {member1.name[:L] + member2.name[LL:]}",
                color=ctx.author.colour
            )
            embed.set_footer(text=f"{member1.name} & {member2.name}")
            file = discord.File(res_filename)
            embed.set_image(url=f"attachment://{res_filename}")
            await ctx.send(file=file, embed=embed)
            
            sus.close()
            remove(res_filename)

async def setup (bot):
    await bot.add_cog(Fun(bot))