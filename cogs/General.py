import base64
import os
import discord
import openai
import requests
from os import getenv
from scripts.main import heading, Url_Buttons, has_pfp
from discord import app_commands
from discord.ext import commands
from scripts.main import client, connectdb, check_blacklist
import aiohttp
from io import BytesIO

def status_converter(status):
    if status == "dnd":
        return "🔴 Jangan Ganggu"
    elif status == "idle":
        return "🟡 AFK"
    elif status == "online":
        return "🟢 Online"
    else:
        return "⚪ Offline"
    
day_of_week = {
    '1':"Senin",
    '2':"Selasa",
    '3':"Rabu",
    '4':"Kamis",
    '5':"Jumat",
    '6':"Sabtu",
    '7':"Minggu"
}

class General(commands.Cog):
    """
    Kumpulan command umum.
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name='rvdia')
    async def rvdia_command(self, ctx:commands.Context) -> None:
        """
        Kumpulan command khusus untuk RVDIA.
        [COMMAND GROUP]
        """
        pass

    @commands.hybrid_group(name='user')
    async def user_command(self, ctx:commands.Context) -> None:
        """
        Kumpulan command khusus untuk mengetahui info pengguna.
        [COMMAND GROUP]
        """
        pass

    @commands.hybrid_group(name='avatar')
    async def avatar_command(self, ctx:commands.Context) -> None:
        """
        Kumpulan command khusus yang berkaitan dengan avatar pengguna.
        [COMMAND GROUP]
        """
        pass

    @rvdia_command.command(name="about", aliases=['intro', 'bot', 'botinfo'])
    @check_blacklist()
    async def rvdia(self, ctx:commands.Context) -> None:
        """
        Memperlihatkan segalanya tentang aku!
        """
        m = 0
        for k in self.bot.guilds:
            m += k.member_count -1
        embed = discord.Embed(title="Tentang RVDIA", color=0xff4df0)
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_image(url=getenv('banner'))
        embed.add_field(name = "Versi", value = f"{self.bot.__version__}", inline=False)
        embed.add_field(name = "Pencipta", value = f"<@877008612021661726> (Jayananda)", inline=False)
        embed.add_field(name = "Prefix", value = f"`r-` | `rvd` | `/`")
        embed.add_field(name = "Library", value = f"discord.py ({discord.__version__})", inline = False)
        embed.add_field(name = "Tipe Bot", value="General, Utilitas, Humor, Anime, Moderasi, Khusus, Slash", inline=False)
        embed.add_field(name = "Nyala Sejak", value = f"<t:{round(self.bot.runtime)}>\n(<t:{round(self.bot.runtime)}:R>)", inline = False)
        embed.add_field(name = "Jumlah Server", value = f"{len(self.bot.guilds)} Server")
        embed.add_field(name = "Jumlah Pengguna", value = f"{m} Pengguna")
        embed.set_footer(text="Jangan lupa tambahkan aku ke servermu! ❤️")
        await ctx.send(embed=embed, view=Url_Buttons())
    
    @rvdia_command.command(name="ping",
        description = "Menampilkan latency ke Discord API dan MongoDB Atlas."
        )
    @check_blacklist()
    async def ping(self, ctx:commands.Context) -> None:
        """
        Menampilkan latency ke Discord API dan MongoDB Atlas.
        """
        mongoping = client.admin.command('ping')
        if mongoping['ok'] == 1:
            mongoping = 'GOOD - STATUS CODE 1'
        else:
            mongoping = 'ERROR - STATUS CODE 0'
        embed= discord.Embed(title= "Ping--Pong!", color=0x964b00, timestamp=ctx.message.created_at)
        embed.description = f"**Discord API:** `{round(self.bot.latency*1000)} ms`\n**MongoDB:** `{mongoping}`"
        await ctx.reply(embed=embed)

    @rvdia_command.command(name='prefix', description='Ganti prefix dari RVDIA.', aliases=['changeprefix'])
    @commands.has_permissions(manage_guild=True)
    @check_blacklist()
    async def prefix(self, ctx:commands.Context, *, prefix:str):
        """
        Ganti message prefix RVDIA.
        """
        current_prefix = connectdb('Prefixes')
        check_prefix = current_prefix.find_one({'_id': ctx.guild.id})
        if check_prefix is None:
            current_prefix.insert_one({'_id':ctx.guild.id, 'prefix':prefix})

        else:
            if prefix.lower() == 'reset' or prefix.lower() == 'restart' or prefix.lower() == 'return':
                current_prefix.find_one_and_update({'_id':ctx.guild.id}, {'$set':{'prefix':['r-', 'R-', 'rvd ', 'Rvd ', 'RVD ']}})
                return await ctx.reply('Prefix telah kembali seperti semula!')
            else:
                current_prefix.find_one_and_update({'_id':ctx.guild.id}, {'$set':{'prefix':prefix}})

        await ctx.reply(f'Message prefix telah diganti ke **`{prefix}`**')

    @user_command.command(description="Memperlihatkan avatar pengguna Discord.")
    @app_commands.rename(global_user='pengguna')
    @app_commands.describe(global_user='Pengguna yang ingin diambil foto profilnya')
    @has_pfp()
    @check_blacklist()
    async def avatar(self, ctx, *, global_user: discord.User = None):
        """
        Memperlihatkan avatar pengguna Discord.
        Support: (ID, @Mention, username, name#tag)
        """
        global_user = global_user or ctx.author
        if global_user.avatar is None:
            return await ctx.reply(f'{global_user} tidak memiliki foto profil!')
        png = global_user.avatar.with_format("png").url
        jpg = global_user.avatar.with_format("jpg").url
        webp = global_user.avatar.with_format("webp").url
        embed=discord.Embed(title=f"{global_user}'s Avatar", url = global_user.avatar.with_format("png").url, color= 0xff4df0)
        if global_user.avatar.is_animated():
            gif = global_user.avatar.with_format("gif").url
            embed.set_image(url = global_user.avatar.with_format("gif").url)
            embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp}) | [gif]({gif})"
        else:
            embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp})"
            embed.set_image(url = global_user.avatar.with_format("png").url)
        embed.set_footer(text=f"{ctx.author}", icon_url=ctx.author.avatar.url)
        await ctx.reply(embed=embed)

    @user_command.command(name='info', aliases = ['whois'], description="Lihat info tentang seseorang di server ini.")
    @app_commands.rename(member='pengguna')
    @commands.guild_only()
    @check_blacklist()
    async def userinfo(self, ctx, *, member:discord.Member = None):
        """
        Lihat info tentang seseorang di server ini.
        Support: (ID, @Mention, username, name#tag)
        """
        member = member or ctx.author
        avatar_url = member.avatar.url if not member.avatar is None else getenv('normalpfp')
        bot = member.bot

        if bot == True:
            avatar_url = "https://emoji.gg/assets/emoji/bottag.png"
        roles = [role.mention for role in member.roles][::-1][:-1] or ["None"]
        if roles[0] == "None":
            role_length = 0
        else:
            role_length = len(roles)
        nick = member.display_name
        if nick == member.name:
            nick = "None"

        perm_list = [perm[0] for perm in member.guild_permissions if perm[1]]
        perm_len = len(perm_list)
        lel = [kol.replace('_', ' ') for kol in perm_list]
        lol = [what.title() for what in lel]

        status = status_converter(str(member.status)) #Status
        embed=discord.Embed(title=member, color=member.colour, timestamp=ctx.message.created_at)
        embed.set_author(name="User Info:")
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="Nama Panggilan", value=nick, inline=False)
        embed.add_field(name="Status", value=status, inline=False)
        embed.add_field(name="Akun Dibuat", value=member.created_at.strftime("%a, %d %B %Y"))
        embed.add_field(name="Bergabung Pada", value=member.joined_at.strftime("%a, %d %B %Y"))
        embed.add_field(name="Role tertinggi", value=member.top_role.mention, inline=False)
        if role_length > 10:
            embed.add_field(name=f"Roles [{str(role_length)}]", value=" ".join(roles[:10]) + "\n(__First 10 roles__)", inline=False)
        else:
            embed.add_field(name=f"Roles [{str(role_length)}]", value=" ".join(roles), inline=False)
        embed.add_field(name=f"Permissions [{str(perm_len)}]", value="`"+", ".join(lol)+"`", inline=False)
        owner = await self.bot.fetch_user(ctx.guild.owner_id)
        ack = None
        match member.id: # First use of match case wowwwww
            case 877008612021661726:
                ack = "Pencipta Bot"
            case 957471338577166417:
                ack = "The One True Love"
            case 865429287691878430:
                ack = "Yassalam Bro"

        if ack is None:
            if member.bot == True:
                ack = "Server Bot"
            elif member.id == 498414156723126283 or member.id == 840569855337300018 or member.id == 744109318554648616:
                ack = "That Funny Dude"
            elif owner.id == member.id:
                ack = "Pemilik Server"
            elif member.guild_permissions.administrator == True:
                ack = "Server Admin"
            else:
                ack = "Anggota Server"
        embed.add_field(name = "Dikenal Sebagai", value = ack)
        embed.set_footer(text=f"ID: {member.id}", icon_url=avatar_url)
        await ctx.reply(embed=embed)

    @commands.command(description = "View the server's info, not that it matters anyway.", hidden=True)
    @commands.guild_only()
    @check_blacklist()
    async def serverinfo(self, ctx):
        """
        View the server's info.
        """
        owner = await self.bot.fetch_user(ctx.guild.owner_id)
        """roles = [role.mention for role in ctx.guild.roles][::-1][:-1] or ['None']
        if roles[0] == "None":
            role_length = 0
        else:
            role_length = len(roles)
        desc = ctx.guild.description
        if desc == None:
            desc = "No description was made for this server."""
        embed = discord.Embed(title=f'{ctx.guild.name}', color=ctx.author.colour, timestamp = ctx.message.created_at)
        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.set_author(name = "Server Info:", icon_url = ctx.guild.icon_url)
        embed.add_field(name="Owner", value=f"{owner.mention} ({owner})", inline = False)
        embed.add_field(name="Creation Date", value=ctx.guild.created_at.strftime("%a, %d %B %Y"), inline = False)
        embed.add_field(name="Members", value=f"{ctx.guild.member_count} members", inline = False)
        embed.set_footer(text=f"ID: {ctx.guild.id}", icon_url=ctx.guild.icon_url)
        embed.set_image(url = ctx.guild.banner_url)
        await ctx.reply(embed=embed)

    """@commands.command(aliases=['math'], description="Calculate mathematical expressions, refer to Python operators.")
    async def calc(self, ctx, *, calcs):
        "Low-level calculating system"
        await ctx.reply(f'Result: {eval(calcs)}') #Lazy coding"""

    @avatar_command.command(aliases=['grayscale'], description="Ubah foto profil menjadi grayscale (hitam putih).")
    @app_commands.rename(user='pengguna')
    @has_pfp()
    @check_blacklist()
    async def greyscale(self, ctx, *, user:discord.User = None):
        """Ubah foto profil menjadi grayscale."""
        user = user or ctx.author
        avatar = user.avatar.with_format("png").url if not user.avatar is None else getenv('normalpfp')
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://some-random-api.ml/canvas/greyscale?avatar={avatar}') as data:
                image = BytesIO(await data.read())
                await session.close()
                await ctx.reply(file=discord.File(image, 'Grayscale.png'))

    @avatar_command.command(description="Ubah foto profil menjadi inverted (warna terbalik).")
    @app_commands.rename(user='pengguna')
    @has_pfp()
    @check_blacklist()
    async def invert(self, ctx, *, user:discord.User = None):
        """Ubah foto profil menjadi inverted."""
        user = user or ctx.author
        avatar = user.avatar.with_format("png").url if not user.avatar is None else getenv('normalpfp')
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://some-random-api.ml/canvas/invert?avatar={avatar}') as data:
                image = BytesIO(await data.read())
                await session.close()
                await ctx.reply(file=discord.File(image, 'Inverted.png'))


class Utilities(commands.Cog):
    """
    Kategori command berupa alat-alat dan fitur bermanfaat.
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(aliases = ['cuaca'], description="Lihat info tentang cuaca di suatu kota atau daerah!")
    @app_commands.rename(location='lokasi')
    @check_blacklist()
    async def weather(self, ctx, *, location:str):
        """
        Lihat info tentang keadaan cuaca di suatu kota atau daerah! (Realtime)
        """
        try:
            # Need to decode geocode consisting of latitude and longitude
            data = requests.get(f'http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={getenv("openweatherkey")}').json()
            geocode = [data[0]['lat'], data[0]['lon']]
            result = requests.get(f"https://api.openweathermap.org/data/2.5/weather?lat={geocode[0]}&lon={geocode[1]}&lang=id&units=metric&appid={getenv('openweatherkey')}").json()
            icon = f"http://openweathermap.org/img/wn/{result['weather'][0]['icon']}@4x.png"
            embed = discord.Embed(title=f"Cuaca di {result['name']}", description=f"__{result['weather'][0]['description'].title()}__")
            embed.color = 0x00ffff
            embed.set_thumbnail(url=icon)
            temp = result['main']
            embed.add_field(
                    name=f"Suhu ({temp['temp']}°C)",
                    value = 
                    f"**Terasa seperti:** ``{temp['feels_like']}°C``\n**Minimum:** ``{temp['temp_min']}°C``\n**Maksimum:** ``{temp['temp_max']}°C``\n"+
                    f"**Tekanan Atmosfir:** ``{temp['pressure']} hPa``\n**Kelembaban:** ``{temp['humidity']}%``\n**Persentase Awan:** ``{result['clouds']['all']}%``",
                    inline=False
                    )
            wind = result['wind']
            embed.add_field(
                name = "Angin",
                value = f"""**Kecepatan:** ``{wind['speed']} m/s``\n**Arah:** ``{wind['deg']}° ({heading(wind['deg'])})``
                """, inline=False
            )
            embed.add_field(
                name="Sunrise",
                value=f"<t:{result['sys']['sunrise']}:R>", inline=False
            )
            embed.add_field(
                name="Sunset",
                value=f"<t:{result['sys']['sunset']}:R>"
            )
            embed.set_footer(text=f"{ctx.author}", icon_url=ctx.author.avatar.url)
            await ctx.send(embed=embed)

        except(IndexError):
            await ctx.send('Aku tidak bisa menemukan lokasi itu!')

    @commands.hybrid_command(description="Lihat info tentang waktu di suatu kota atau daerah!")
    @app_commands.rename(location='lokasi')
    @check_blacklist()
    async def time(self, ctx, *, location:str):
        """
        Lihat info tentang waktu di suatu kota atau daerah! (Realtime)
        """
        check_timezone = requests.get(f'http://worldtimeapi.org/api/timezone').json()
        area = []
        for elements in check_timezone:
            match = elements.split("/") # Split karena formatnya Continent/Area
            if location.title() in match:
                area = match

        if area == []:
            await ctx.send('Aku tidak bisa menemukan daerah itu!')
            return
        
        req_data = "/".join(area)
        data = requests.get(f'http://worldtimeapi.org/api/timezone/{req_data}').json()
        day = str(data['day_of_week'])
        day = day_of_week[day]
        embed = discord.Embed(title=f"Waktu di {area[1]}", description=f"UTC{data['utc_offset']}", color=0x00ffff)
        embed.add_field(name="Akronim Timezone", value=data['abbreviation'], inline=False)
        embed.add_field(name="Hari di Lokasi", value=day, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
            aliases = ['ask', 'chatbot', 'tanya'],
            description = 'Tanyakan atau perhintahkan aku untuk melakukan sesuatu!'
        )
    @app_commands.rename(message='pesan')
    @app_commands.describe(message='Apa yang ingin kamu tanyakan?')
    @commands.cooldown(type=commands.BucketType.user, per=2, rate=1)
    @check_blacklist()
    async def chat(self, ctx:commands.Context, *, message:str):
        """
        Tanyakan atau perhintahkan aku untuk melakukan sesuatu!
        """
        async with ctx.typing():
            openai.api_key = os.getenv('openaikey')
            result = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                temperature=1.2,
                messages=[
                {"role":'system', 'content':getenv('rolesys')},
                {"role": "user", "content": message}
                ]
            )
            embed = discord.Embed(
                title=' '.join((word.title() if not word.isupper() else word for word in message.split(' '))), 
                color=ctx.author.color, 
                timestamp=ctx.message.created_at
                )
            embed.description = result['choices'][0]['message']['content'] # Might improve for >4096 chrs
        await ctx.reply(embed=embed)

    @commands.hybrid_command(
            aliases = ['image', 'create'],
            description = 'Ciptakan sebuah karya seni!'
        )
    @app_commands.describe(prompt='Apa yang ingin diciptakan?')
    @commands.cooldown(type=commands.BucketType.user, per=2, rate=1)
    @check_blacklist()
    async def generate(self, ctx:commands.Context, *, prompt:str):
        """
        Ciptakan sebuah karya seni dua dimensi dengan perintah!
        """
        async with ctx.typing():
            openai.api_key = os.getenv('openaikey')
            result = await openai.Image.acreate(
                prompt=prompt,
                size='1024x1024',
                response_format='b64_json',
                n=1
            )
            b64_data = result['data'][0]['b64_json']
            decoded_data = base64.b64decode(b64_data)
            image=open('generated.png', 'wb')
            image.write(decoded_data)
            image.close()

            embed = discord.Embed(title='Karya Terciptakan', color=ctx.author.colour, timestamp=ctx.message.created_at)
            embed.description = f'Prompt: `{prompt}`'
            file = discord.File("generated.png")
            embed.set_image(url= "attachment://generated.png")
        
        await ctx.reply(file=file, embed=embed)

async def setup(bot:commands.Bot):
    await bot.add_cog(General(bot))
    await bot.add_cog(Utilities(bot))