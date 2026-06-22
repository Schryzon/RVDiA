from os import remove
import random
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image
from io import BytesIO
from scripts.main import db, has_voted, check_blacklist
from scripts.utils.i18n import i18n

class Fun(commands.Cog):
    """
    Command khusus untuk bersenang-senang
    """
    def __init__(self, bot):
        self.bot = bot
               
    @commands.hybrid_command(aliases=['jodohkan', 'jodoh'], description="Match/ship two people together and check their love compatibility!")
    @app_commands.describe(member1='First person to ship', member2='Second person to ship')
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_voted()
    @check_blacklist()
    async def ship(self, ctx:commands.Context, member1: discord.Member, member2:discord.Member):
        """
        Match/ship two people together and check their love compatibility!
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

    @commands.hybrid_command(name="guess", description="Let's play a number guessing game with me!")
    @app_commands.describe(level='Which difficulty level will you choose?')
    @app_commands.choices(level=[
        app_commands.Choice(name='SUPER', value='SUPER'),
        app_commands.Choice(name='HARD', value='HARD'),
        app_commands.Choice(name="NORMAL", value='NORMAL'),
        app_commands.Choice(name='EASY', value='EASY')
    ])
    @check_blacklist()
    async def guess(self, ctx: commands.Context, level: app_commands.Choice[str]):
        """
        Let's play a number guessing game with me!
        """
        from scripts.game.fight import execute_guess
        await execute_guess(ctx, level.value)

    @commands.hybrid_command(name="8ball", description="Ask the Magic 8-Ball a question!")
    @app_commands.describe(question="The question to ask.")
    @check_blacklist()
    async def eightball(self, ctx: commands.Context, *, question: str):
        """Ask the Magic 8-Ball a question!"""
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        lang_data = i18n.locales.get(lang, i18n.locales.get("en", {}))
        responses = lang_data.get("fun", {}).get("8ball_responses", [])
        if not responses:
            responses = [
                "It is certain. 🟢", "Reply hazy, try again. 🟡", "My reply is no. 🔴"
            ]
        
        answer = random.choice(responses)
        title = i18n.get(lang, "fun.8ball_title")
        q_label = i18n.get(lang, "fun.8ball_question")
        a_label = i18n.get(lang, "fun.8ball_answer")

        embed = discord.Embed(title=title, color=0x34495e)
        embed.add_field(name=f"❓ {q_label}", value=question, inline=False)
        embed.add_field(name=f"✨ {a_label}", value=answer, inline=False)
        embed.set_footer(text=ctx.author.name, icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="roll", description="Roll some dice (e.g. 1d6, 2d20).")
    @app_commands.describe(dice="Dice notation (e.g. 1d6, 2d20). Default is 1d6.")
    @check_blacklist()
    async def roll(self, ctx: commands.Context, dice: str = "1d6"):
        """Roll some dice!"""
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        import re
        match = re.match(r'^(?:(\d+))?d(\d+)$', dice.lower().strip())
        if not match:
            err_msg = i18n.get(lang, "fun.roll_invalid")
            return await ctx.reply(err_msg)

        count = int(match.group(1) or 1)
        sides = int(match.group(2))

        if count <= 0 or count > 50 or sides <= 1 or sides > 1000:
            err_msg = i18n.get(lang, "fun.roll_invalid")
            return await ctx.reply(err_msg)

        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)

        title = i18n.get(lang, "fun.roll_title")
        rolls_str = ", ".join(f"`{r}`" for r in rolls)
        result_desc = i18n.get(lang, "fun.roll_result", rolls=rolls_str, total=total)

        embed = discord.Embed(title=title, description=result_desc, color=ctx.author.color)
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="coinflip", description="Flip a coin!")
    @check_blacklist()
    async def coinflip(self, ctx: commands.Context):
        """Flip a coin!"""
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        is_heads = random.choice([True, False])
        title = i18n.get(lang, "fun.coin_title")

        if is_heads:
            res_label = i18n.get(lang, "fun.coin_heads")
            res_desc = i18n.get(lang, "fun.coin_heads_desc")
        else:
            res_label = i18n.get(lang, "fun.coin_tails")
            res_desc = i18n.get(lang, "fun.coin_tails_desc")

        embed = discord.Embed(title=title, description=f"🪙 **{res_label}**\n\n{res_desc}", color=0xf1c40f)
        embed.set_footer(text=ctx.author.name, icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)

async def setup (bot):
    await bot.add_cog(Fun(bot))