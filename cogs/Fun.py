import asyncio
from os import getenv, remove
import random
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image
from io import BytesIO
from scripts.main import check_blacklist

class Fun(commands.Cog):
    """
    Command khusus untuk bersenang-senang
    """
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(aliases = ['bandoriwaifu'], description='Temukan karakter BanG Dream yang cocok denganmu!')
    @check_blacklist()
    async def bdwaifu(self, ctx):
        """
        Temukan karakter BanG Dream yang cocok denganmu!
        """
        async with aiohttp.ClientSession() as session:
            bdinit = await session.get(f"https://bandori.party/api/members/{random.randint(6, 40)}/")
            bdwifu = await bdinit.json()
            we = discord.Embed(title = f"{bdwifu['name']} [{bdwifu['japanese_name']}]", description = f"From {bdwifu['i_band']}", color = ctx.author.colour)
            we.set_thumbnail(url = bdwifu['square_image'])
            we.set_author(name = "Waifu BanG Dream! kamu:", icon_url=bdwifu['square_image'])
            we.add_field(name = "Sekolah", value = f"{bdwifu['school']}, {bdwifu['i_school_year']} Year", inline = False)
            we.add_field(name = "Instrumen", value = bdwifu['instrument'], inline = False)
            we.add_field(name = "Ulang Tahun", value = bdwifu['birthday'])
            we.add_field(name = "Zodiak", value = bdwifu['i_astrological_sign'])
            we.add_field(name = "VA", value = f"{bdwifu['romaji_CV']} [{bdwifu['CV']}]", inline = False)
            we.add_field(name = "Menyukai", value = bdwifu['food_like'])
            we.add_field(name = "Tidak Menyukai", value = bdwifu['food_dislike'])
            we.add_field(name = f"Tentang {bdwifu['name']}:", value=bdwifu['description'], inline = False)
            await ctx.reply(embed = we)

    @commands.hybrid_command(aliases=['tebak'], description='Ayo main tebak angka bersamaku!')
    @check_blacklist()
    async def guess(self, ctx:commands.Context):
        """
        Ayo main tebak angka bersamaku!
        """
        count = 5
        hints = 3
        number = random.randint(1, 20)
        num_store = None
        await ctx.send(":grey_exclamation: **Kamu harus menebak angka yang aku pikirkan dari `1-20`!**")
        await asyncio.sleep(2.5)
        while count != 0:
            if count < 5 and count != 1:
                await ctx.send(f"**Kamu punya `{count}` attempt. Ketik `hint` jika butuh bantuan.\nHint tersisa: `{hints}` | Akhiri game dengan mengetik `end`.**")
            elif count == 1:
                await ctx.send(f"**Kamu punya `{count}` attempt tersisa!\nHint tersisa: `{hints}` | Akhiri game dengan mengetik `end`.**")
            else:
                await ctx.send(f"**Kamu punya `{count}` attempt, ayo coba tebak angka yang kupilih!\nAkhiri game dengan mengetik `end`.**")
            try:
                r1 = await self.bot.wait_for('message', check = lambda r: r.author == ctx.author and r.channel == ctx.channel, timeout = 20.0)

            except asyncio.TimeoutError:
                await ctx.channel.send(f"**Yah, dikacangin dong :(**")
                return
            
            if r1.content == str(number):
                await ctx.channel.send(f"**Tepat sekali, angkanya yaitu `{number}`!**")
                return
            
            elif r1.content.isdigit() == False and r1.content.lower() != "hint" and r1.content.lower() != "end" and r1.content.lower() != "end.":
                await ctx.channel.send(f":negative_squared_cross_mark: **Hey, kamu hanya bisa menjawab dengan angka bilangan bulat saja!**", delete_after=2.0)
                await asyncio.sleep(1.5)

            elif r1.content.lower() == "end" or r1.content.lower() == "end.":
                await ctx.channel.send(":no_entry: **Game diakhiri.**")
                return
            
            elif r1.content.lower() == "hint":
                if num_store == None:
                    await ctx.channel.send(":negative_squared_cross_mark: **Kamu belum ada menebak, tebak dulu baru bisa dikasi hint!**", delete_after=2.0)
                    await asyncio.sleep(1.5)

                elif hints == 0:
                    await ctx.channel.send(":negative_squared_cross_mark: **Kamu kehabisan hint!**", delete_after=2.0)
                    await asyncio.sleep(1.5)

                elif number > num_store:
                    await ctx.channel.send(f":grey_question: Hint: **Angka terakhirmu, `{num_store}` lebih kecil dari yang kupilih.**", delete_after=2.5)
                    hints -= 1
                    await asyncio.sleep(2.0)

                elif number < num_store:
                    await ctx.channel.send(f":grey_question: Hint: **Angka terakhirmu, `{num_store}` lebih besar dari yang kupilih.**", delete_after=2.5)
                    hints -= 1
                    await asyncio.sleep(2.0)
            else:
                if int(r1.content) > 20:
                    await ctx.channel.send(f":negative_squared_cross_mark: **Angkamu lebih tinggi dari 20!**", delete_after=2.0)
                    await asyncio.sleep(1.5)

                else:
                    count -= 1
                    await ctx.channel.send(f":x: **Salah!**")
                    num_store = int(r1.content)
                    await asyncio.sleep(1.5)
                    
        if count == 0:
            await ctx.send(f":exclamation: **Kamu kehabisan attempt!\nAngka yang kupilih yaitu `{number}`!**")

    @commands.command(aliases = ['battle'], hidden=True)
    @commands.guild_only()
    @check_blacklist()
    async def fight(self, ctx, *, member: discord.Member = None):
        if member == None:
            await ctx.send(":negative_squared_cross_mark: **Please specify the user that you want to fight!**")
            return
        if member == ctx.author:
            await ctx.send(":negative_squared_cross_mark: **You can't fight yourself!**")
            return
        if member == self.bot.user:
            await ctx.send(":negative_squared_cross_mark: **You can't fight me! Why would you do it anyways?!**")
            return
        if member.bot == True:
            await ctx.send(":negative_squared_cross_mark: **Hey, you can't fight other bots!**")
            return
        quotes = [
            'punches', 
            'performed a dive kick on', 
            'picked up a knife and slashed', 
            'kicks',
            'jumpscares',
            'found a gun and shot',
            'used Master Spark on',
            'flipped a table on',
            'confessed their love to',
            'fired ofuda bullets to',
            'used the Evil Sealing Circle on',
            'jump kicks',
            'used the Hakurouken and slashed',
            'used the Roukanken and slashed',
            'threw a Touhou Fumo to',
            "borrowed Yuyuko's fan and slapped",
            "threw Xaneria's desktop to",
            "performed Patchouli's magic on",
            "used a baseball bat and bonked",
            "performed a really neat kickflip on",
            "stomps on",
            "roasts",
            "tells a funny joke to",
            "sussed",
            "fired a laser beam to",
            "told a scary story to"
        ]
        member1hp = 100
        member2hp = 100
        used = 0
        await ctx.send(f":crossed_swords: {ctx.author.mention} **has started a fight with** {member.mention}!")
        await asyncio.sleep(3.0)
        while member1hp > 0 or member2hp > 0 or member1hp != 0 or member2hp != 0:
            if used != 0:
                await ctx.send(f"{ctx.author.mention}**, it's your turn. `fight`, `defend`, or `run`?\nType your choice in the chat!**")
            else:
                await ctx.send(f"{ctx.author.mention}**, you go first. You can pick `fight`, `defend`, or `run`\nType your choice in the chat!**")
                spoint = 0
                used += 1
            try:
                r1 = await self.bot.wait_for('message', check = lambda r: r.author == ctx.author and r.channel == ctx.channel, timeout = 30.0)
            except asyncio.TimeoutError:
                await ctx.channel.send(f":person_walking: {ctx.author.mention} **has left the battle.**\n{member.mention} **wins by default.**")
                return
            if r1.content.lower() == "fight":
                if spoint == 0:
                    dmgs = random.randint(0, 75)
                    dmg = dmgs
                    member2hp -= dmg
                    if dmg >70:
                        await ctx.channel.send(f"**SMAAAAASH!\n{ctx.author.name} {random.choice(quotes)} {member.name}, dealing {dmg} damage!**")
                    if dmg == 0:
                        await ctx.channel.send(f"**{ctx.author.name} {random.choice(quotes)} {member.name} and missed.**")
                    else:
                        if dmg != 0 and dmg <= 70:
                            await ctx.channel.send(f"**{ctx.author.name} {random.choice(quotes)} {member.name}, dealing {dmg} damage!**")
                        else:
                            pass
                else:
                    dmgs3 = random.randint(0, 25)
                    dmg3 = dmgs3
                    member2hp -= dmg3
                    if dmg3 == 0:
                        await ctx.channel.send(f"**{ctx.author.name} tried to punch through {member.name}'s defense, but it failed.**")
                    else:
                        await ctx.channel.send(f"**{ctx.author.name} {random.choice(quotes)} {member.name}, dealing {dmg3} damage!**")
                    spoint = 0
            elif r1.content.lower() == "defend":
                await ctx.channel.send(f"**:shield: {ctx.author.name} puts up a defense!**")
            elif r1.content.lower() == "run":
                await ctx.channel.send(f"**:person_running: {ctx.author.name} ran away from the fight!\n:no_entry: Game Ended.**")
                return
            else:
                await ctx.channel.send(f":negative_squared_cross_mark: **You can only pick `fight`, `defend`, or `run`!\nYour turn has been skipped.**")
            if 0 > member2hp or member2hp == 0 or member1hp == 0 or 0 > member1hp:
                break
            await asyncio.sleep(3.0)
            await ctx.send(f"{member.mention}**, it's your turn. `fight`, `defend`, or `run`?\nType your choice in the chat!**")
            try:
                r2 = await self.bot.wait_for('message', check = lambda r: r.author == member and r.channel == ctx.channel, timeout = 30.0)
            except asyncio.TimeoutError:
                await ctx.channel.send(f":person_walking: {member.mention} **has left the battle.**\n{ctx.author.mention} **wins by default.**")
                return
            if r2.content.lower() == "fight":
                if r1.content.lower() == "defend":
                    dmgs2 = random.randint(0, 25)
                    dmg2 = dmgs2
                    member1hp -= dmg2
                    if dmg2 == 0:
                        await ctx.channel.send(f"**{member.name} tried to punch through {ctx.author.name}'s defense, but it failed.**")
                    else:
                        await ctx.channel.send(f"**{member.name} {random.choice(quotes)} {ctx.author.name}, dealing {dmg2} damage!**")
                else:
                    dmgs4 = random.randint(0, 75)
                    dmg4 = dmgs4
                    member1hp -= dmg4
                    if dmg4 > 70:
                        await ctx.channel.send(f"**SMAAAAASH!\n{member.name} {random.choice(quotes)} {ctx.author.name}, dealing {dmg4} damage!**")
                    elif dmg4 == 0:
                        await ctx.channel.send(f"**{member.name} {random.choice(quotes)} {ctx.author.name} and missed.**")
                    else:
                        if dmg4 != 0 and dmg4 <= 70:
                            await ctx.channel.send(f"**{member.name} {random.choice(quotes)} {ctx.author.name}, dealing {dmg4} damage!**")
                        else:
                            pass
                spoint = 0
            elif r2.content.lower() == "defend":
                await ctx.channel.send(f"**:shield: {member.name} puts up a defense!**")
                spoint = 1
            elif r2.content.lower() == "run":
                await ctx.channel.send(f"**:person_running: {member.name} ran away from the fight!\n:no_entry: Game Ended.**")
                return
            else:
                await ctx.channel.send(f":negative_squared_cross_mark: **You can only pick `fight`, `defend`, or `run`!\nYour turn has been skipped.**")
            if 0 > member1hp or member1hp == 0 or member2hp == 0 or 0 > member2hp:
                break
            await asyncio.sleep(3.0)
        if member1hp > member2hp:
            await ctx.send(f":trophy: **Congratulations {ctx.author.mention}, you won the fight!**")
        elif member2hp > member1hp:
            await ctx.send(f":trophy: **Congratulations {member.mention}, you won the fight!**")
        else:
            return
    
    @commands.hybrid_command(aliases=['jodohkan', 'jodoh'], description="Jodohkan seseorang denganmu atau orang lain!")
    @app_commands.rename(member1='pengguna_1', member2='pengguna_2')
    @commands.cooldown(1, 5, commands.BucketType.user)
    @check_blacklist()
    async def ship(self, ctx:commands.Context, member1: discord.Member = None, member2:discord.Member=None):
        """
        Jodohkan seorang teman atau orang lain dengan pengguna lainnya!
        """
        try:
            if member1 == None:
                await ctx.send("Kamu harus mention orang yang ingin dijodohkan!")
                return
            if member1 == ctx.author and member2 == None:
                await ctx.send("Aku tidak bisa menjodohkanmu dengan dirimu sendiri! TwT")
                return

            elif member2 == None:
                member2 = member1
                member1 = ctx.author
            
            success = random.randint(1, 100)
            if success == 100:
                ss = f"__Match made in Heaven!__\n{member1.name} dan {member2.name} akan menjadi pasangan terbaik! ❤️"
                sus = Image.open("./src/ship.jpg")
            elif success >= 90:
                ss = f"It's __true love!__\n{member1.name} sangat cocok berpasangan dengan {member2.name}! ❤️"
                sus = Image.open("./src/ship.jpg")
            elif success >= 80:
                ss = f"__Lovey, dovey!__\n{member1.name} dan {member2.name} akan menjalin hubungan yang dekat! ❤️"
                sus = Image.open("./src/ship.jpg")
            elif success >= 70:
                ss = f" __Besties for life!__\n{member1.name} akan menjadi sahabat setia untuk {member2.name}! <:hug:1084251318073438289>"
                sus = Image.open("./src/fship.jpg")
            elif success >= 50:
                ss = f"__They somehow fit together.__\n{member1.name} cocok menjadi temannya {member2.name}. 👍"
                sus = Image.open("./src/gship.jpg")
            elif success >= 25:
                ss = f"__Not good!__\n{member1.name} dan {member2.name} tidak akan berbahagia saat berpasangan. 👎"
                sus = Image.open("./src/bship.jpg")
            else:
                ss = f"__This is bad!__\n{member1.name} dan {member2.name} merupakan pasangan yang tidak cocok! 💔"
                sus = Image.open("./src/shship.jpg")

            asset1 = member1.avatar.with_format('png').with_size(128)
            asset2 = member2.avatar.with_format('png').with_size(128)
            data1 = BytesIO(await asset1.read())
            data2 = BytesIO(await asset2.read())
            pfp1 = Image.open(data1)
            pfp1 = pfp1.resize((420, 420))
            sus.paste(pfp1, (90, 28))
            pfp2 = Image.open(data2)
            pfp2 = pfp2.resize((420, 420))
            sus.paste(pfp2, (1024, 28))
            sus.save('shipres.jpg')

            L = len(member1.name)//2
            LL = len(member2.name)//2
            embed = discord.Embed(title="Hasil Penjodohan", description = f"❤️ **{success}%** ❤️\n{ss}\n**Nama ship:** {member1.name[:L] + member2.name[LL:]}", color=ctx.author.colour)
            embed.set_footer(text=f"{member1.name} dan {member2.name}")
            file = discord.File("shipres.jpg")
            embed.set_image(url= "attachment://shipres.jpg")
            await ctx.send(file = file, embed = embed)
            remove('./shipres.jpg')

        except:
            await ctx.reply('Sepertinya ada salah satu pengguna yang belum memakai foto profil, ayo pakai dong, kan mau dijodohin...')

async def setup (bot):
    await bot.add_cog(Fun(bot))