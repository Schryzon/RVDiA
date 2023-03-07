import asyncio
import random
import aiohttp
import discord
from discord.ext import commands
from PIL import Image
from io import BytesIO

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(aliases = ['bandoriwaifu'])
    async def bdwaifu(self, ctx):
        async with aiohttp.ClientSession() as session:
            bdinit = await session.get(f"https://bandori.party/api/members/{random.randint(6, 40)}/")
            bdwifu = await bdinit.json()
            we = discord.Embed(title = f"{bdwifu['name']} [{bdwifu['japanese_name']}]", description = f"From {bdwifu['i_band']}", color = ctx.author.colour)
            we.set_thumbnail(url = bdwifu['square_image'])
            we.set_author(name = "Your BanG Dream! Waifu:", icon_url=bdwifu['square_image'])
            we.add_field(name = "School", value = f"{bdwifu['school']}, {bdwifu['i_school_year']} Year", inline = False)
            we.add_field(name = "Instrument", value = bdwifu['instrument'], inline = False)
            we.add_field(name = "Birthday", value = bdwifu['birthday'])
            we.add_field(name = "Astrological Sign", value = bdwifu['i_astrological_sign'])
            we.add_field(name = "Voice Actor", value = f"{bdwifu['romaji_CV']} [{bdwifu['CV']}]", inline = False)
            we.add_field(name = "Liked Foods", value = bdwifu['food_like'])
            we.add_field(name = "Disliked Foods", value = bdwifu['food_dislike'])
            we.add_field(name = f"About {bdwifu['name']}:", value=bdwifu['description'], inline = False)
            we.set_footer(text = f"Requested by: {ctx.author}", icon_url=ctx.author.avatar.url)
            await ctx.send(embed = we)

    @commands.command()
    async def guess(self, ctx):
        count = 5
        hints = 3
        number = random.randint(1, 20)
        num_store = None
        await ctx.send(":grey_exclamation: **You will need to guess a number between 1 and 20, try to guess the number I chose!**")
        await asyncio.sleep(2.5)
        while count != 0:
            if count < 5 and count != 1:
                await ctx.send(f"**You have `{count}` attempts left. Type `hint` to get a hint.\nHints left: `{hints}` | End the game by typing `end`.**")
            elif count == 1:
                await ctx.send(f"**You have `{count}` attempt left!\nHints left: `{hints}` | End the game by typing `end`.**")
            else:
                await ctx.send(f"**You have `{count}` attempts, try to guess my number.\nTo end the game, type `end`.**")
            try:
                r1 = await self.bot.wait_for('message', check = lambda r: r.author == ctx.author and r.channel == ctx.channel, timeout = 20.0)
            except asyncio.TimeoutError:
                await ctx.channel.send(f"**You ignored me.. well, let me know if you wanna play again.**")
                return
            if r1.content == str(number):
                await ctx.channel.send(f"**Yay, you're right! The number was {number}!**")
                return
            elif r1.content.isdigit() == False and r1.content.lower() != "hint" and r1.content.lower() != "end" and r1.content.lower() != "end.":
                await ctx.channel.send(f":negative_squared_cross_mark: **You can only guess by using integer numbers!**")
                await asyncio.sleep(1.0)
            elif r1.content.lower() == "end" or r1.content.lower() == "end.":
                await ctx.channel.send(":no_entry: **Ended the game.**")
                return
            elif r1.content.lower() == "hint":
                if num_store == None:
                    await ctx.channel.send(":negative_squared_cross_mark: **You haven't guessed a number!**")
                    await asyncio.sleep(1.0)
                elif hints == 0:
                    await ctx.channel.send(":negative_squared_cross_mark: **You are out of hints!**")
                    await asyncio.sleep(1.0)
                elif number > num_store:
                    await ctx.channel.send(f":grey_question: Hint: **Your last number, `{num_store}` was lower than mine.**")
                    hints -= 1
                    await asyncio.sleep(1.0)
                elif number < num_store:
                    await ctx.channel.send(f":grey_question: Hint: **Your last number, `{num_store}` was higher than mine.**")
                    hints -= 1
                    await asyncio.sleep(1.0)
            else:
                if int(r1.content) > 20:
                    await ctx.channel.send(f":negative_squared_cross_mark: **Your number is higher than 20!**")
                    await asyncio.sleep(1.0)
                else:
                    count -= 1
                    await ctx.channel.send(f":x: **Whoops, the number you guessed was wrong.**")
                    num_store = int(r1.content)
                    await asyncio.sleep(1.0)
        if count == 0:
            await ctx.send(f":exclamation: **You have ran out of attempts!\nThe number was {number}.**")

    @commands.command(aliases = ['battle'])
    @commands.guild_only()
    async def fight(self, ctx, *, member: commands.MemberConverter = None):
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
        
    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ship(self, ctx, member1: commands.MemberConverter = None, member2: commands.MemberConverter=None):
        if member1 == None:
            await ctx.send(":negative_squared_cross_mark: **Please provide the user that you want to be shipped with or the user that you want to ship with another!**")
            return
        if member1 == ctx.author and member2 == None:
            await ctx.send(":negative_squared_cross_mark: **I can't ship you with yourself!**")
            return

        elif member2 == None:
            member2 = member1
            member1 = ctx.author
        
        success = random.randint(1, 100)
        if success == 100:
            ss = f"__Match made in Heaven!__ The perfect ship. {member1.name} and {member2.name}! ❤️"
            sus = Image.open("./src/ship.jpg")
        elif success >= 90:
            ss = f"It's __true love!__ {member1.name} fits perfectly with {member2.name}! ❤️"
            sus = Image.open("./src/ship.jpg")
        elif success >= 80:
            ss = f"{member1.name} __loves__ {member2.name} and {member2.name} thinks the same! ❤️"
            sus = Image.open("./src/ship.jpg")
        elif success >= 70:
            ss = f"{member1.name} will be a __great bestie__ for {member2.name}! <:hug:857104180892401694>"
            sus = Image.open("./src/fship.jpg")
        elif success >= 50:
            ss = f"Surprisingly, {member1.name} __fits kinda well__ with {member2.name}. 👍"
            sus = Image.open("./src/gship.jpg")
        elif success >= 25:
            ss = f"The relationship between {member1.name} and {member2.name} __will not be a happy one__. 👎"
            sus = Image.open("./src/bship.jpg")
        else:
            ss = f"{member1.name} and {member2.name} __will not have a good relationship__ and it's a bad idea to ship them! 💔"
            sus = Image.open("./src/shship.jpg")

        asset1 = member1.avatar.with_size(128)
        asset2 = member2.avatar.with_size(128)
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
        embed = discord.Embed(title="Ship Result", description = f"**Love percentage = {success}%**\n**Details:**\n{ss}\n**Ship name:** {member1.name[:L] + member2.name[LL:]}", color=ctx.author.colour)
        embed.set_footer(text=f"A ship between {member1.name} and {member2.name}", icon_url=ctx.author.avatar.url)
        file = discord.File("shipres.jpg")
        embed.set_image(url= "attachment://shipres.jpg")
        await ctx.send(file = file, embed = embed)

async def setup (bot):
    await bot.add_cog(Games(bot))