import base64
import os
import discord
import openai
import requests
import aiohttp
from datetime import datetime
from sys import version as pyver
from os import getenv
from cogs.Event import Event
from scripts.main import heading, Url_Buttons, has_pfp
from discord import app_commands
from discord.ext import commands
from scripts.main import client, connectdb, check_blacklist, event_available, titlecase
from time import time
from PIL import Image
from io import BytesIO
    
day_of_week = {
    '1':"Senin",
    '2':"Selasa",
    '3':"Rabu",
    '4':"Kamis",
    '5':"Jumat",
    '6':"Sabtu",
    '0':"Minggu"
}

class General(commands.Cog):
    """
    Kumpulan command umum.
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name='rvdia')
    @check_blacklist()
    async def rvdia_command(self, ctx:commands.Context) -> None:
        """
        Kumpulan command khusus untuk RVDIA. [GROUP]
        """
        await self.rvdia(ctx)
        pass

    @commands.hybrid_group(name='user')
    @check_blacklist()
    async def user_command(self, ctx:commands.Context, member:discord.Member=None) -> None:
        """
        Kumpulan command khusus untuk mengetahui info pengguna. [GROUP]
        """
        member = member or ctx.author
        await self.userinfo(ctx, member=member)
        pass

    @commands.hybrid_group(name='avatar')
    @check_blacklist()
    async def avatar_command(self, ctx:commands.Context, *, member:discord.User=None) -> None:
        """
        Kumpulan command khusus yang berkaitan dengan avatar pengguna. [GROUP]
        """
        member = member or ctx.author
        await self.avatar(ctx, global_user=member)
        pass

    @commands.hybrid_command(description='Mengulangi apapun yang kamu katakan!')
    @app_commands.describe(
        teks='Apa yang kamu ingin aku katakan?',
        attachment='Lampirkan gambar, kalau mau.'
        )
    @check_blacklist()
    async def say(self, ctx:commands.Context, attachment:discord.Attachment=None, *, teks:str=None):
        if attachment:
            await attachment.save(attachment.filename)
            file = discord.File(attachment.filename)
            if teks:
                await ctx.send(teks, file=file)
            else:
                await ctx.send(file=file)
            
            os.remove(attachment.filename) # Haiyaa
        
        else:
            await ctx.send(teks) if teks else await ctx.send("Aku gak tau harus berkata apa ¯\_(ツ)_/¯")

    @rvdia_command.command(name="about", aliases=['intro', 'bot', 'botinfo'])
    @check_blacklist()
    async def rvdia(self, ctx:commands.Context) -> None:
        """
        Memperlihatkan segalanya tentang aku!
        """
        database = connectdb('Prefixes')
        prefix = database.find_one({'_id': ctx.guild.id})
        if prefix is None:
            prefix = ['@RVDIA', 'r-', 'rvd ']
        else:
            prefix = prefix['prefix']
        m = 0
        for k in self.bot.guilds:
            m += k.member_count -1
        embed = discord.Embed(title="Tentang RVDIA", color=0xff4df0)
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_image(url=getenv('banner') if not self.bot.event_mode else getenv('bannerevent'))
        embed.add_field(name = "Versi", value = f"{self.bot.__version__}", inline=False)
        embed.add_field(name = "Mode", value = f"Event Mode" if self.bot.event_mode else "Standard Mode", inline=False)
        embed.add_field(name = "Pencipta", value = f"<@877008612021661726> (Jayananda)", inline=False)
        embed.add_field(name = "Prefix", value = '@RVDIA | '+f" | ".join(prefix)+f' | / (slash)')
        embed.add_field(name = "Bahasa Pemrograman", value=f"Python ({pyver[:6]})\ndiscord.py ({discord.__version__})", inline=False)
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
    @app_commands.describe(prefix='Mau diganti awalan command jadi apa?')
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
            reset_prefix = ['restart', 'reset', 'return']
            if any(prefix.lower() == reset for reset in reset_prefix):
                current_prefix.find_one_and_update({'_id':ctx.guild.id}, {'$set':{'prefix':['r-', 'R-', 'rvd ', 'Rvd ', 'RVD ']}})
                return await ctx.reply('Prefix telah kembali seperti semula!')
            else:
                current_prefix.find_one_and_update({'_id':ctx.guild.id}, {'$set':{'prefix':prefix}})

        await ctx.reply(f'Message prefix telah diganti ke **`{prefix}`**\nUntuk mengembalikan prefix seperti semula, `{prefix}rvdia prefix reset`')

    @rvdia_command.command(description = 'Memperlihatkan informasi event yang berlangsung.')
    @check_blacklist()
    @event_available()
    async def event(self, ctx:commands.Context) -> None:
        """
        Memperlihatkan informasi event yang berlangsung.
        """
        event = Event(ctx.bot)
        await event.info(ctx, ctx) # What the fuck???

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

        embed=discord.Embed(title=f"Avatar {global_user}", url = global_user.avatar.with_format("png").url, color= 0xff4df0)

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
    @app_commands.describe(
        member = 'Siapa yang ingin diketahui infonya?'
    )
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

        embed=discord.Embed(title=member, color=member.colour, timestamp=ctx.message.created_at)
        embed.set_author(name="User Info:")
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="Nama Panggilan", value=nick, inline=False)
        embed.add_field(name="Akun Dibuat", value=member.created_at.strftime("%a, %d %B %Y"))
        embed.add_field(name="Bergabung Pada", value=member.joined_at.strftime("%a, %d %B %Y"))
        embed.add_field(name="Role tertinggi", value=member.top_role.mention, inline=False)
        if role_length > 10:
            embed.add_field(name=f"Roles [{str(role_length)}]", value=" ".join(roles[:10]) + "\n(__10 role pertama__)", inline=False)
        else:
            embed.add_field(name=f"Roles [{str(role_length)}]", value=" ".join(roles), inline=False)
        embed.add_field(name=f"Permissions [{str(perm_len)}]", value="`"+", ".join(lol)+"`", inline=False)
        owner = await self.bot.fetch_user(ctx.guild.owner_id)
        ack = None
        match member.id: # First use of match case wowwwww
            case self.bot.owner_id:
                ack = "Pencipta Bot"
            case self.bot.user.id:
                ack = "The One True Love"

        if ack == None:
            if member.bot == True:
                ack = "Server Bot"
            elif owner.id == member.id:
                ack = "Pemilik Server"
            elif member.guild_permissions.administrator == True:
                ack = "Server Admin"
            else:
                ack = "Anggota Server"

        embed.add_field(name = "Dikenal Sebagai", value = ack)
        embed.set_footer(text=f"ID: {member.id}", icon_url=avatar_url)
        await ctx.reply(embed=embed)

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
    @app_commands.describe(
        location = 'Lokasi mana yang ingin diketahui cuacanya?'
    )
    @check_blacklist()
    async def weather(self, ctx, *, location:str):
        """
        Lihat info tentang keadaan cuaca di suatu kota atau daerah!
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
    @app_commands.describe(location='Daerah mana yang ingin kamu ketahui?')
    @app_commands.rename(location='lokasi')
    @check_blacklist()
    async def time(self, ctx:commands.Context, *, location:str):
        """
        Lihat info tentang waktu di suatu kota atau daerah!
        """
        check_timezone = requests.get(f'http://worldtimeapi.org/api/timezone').json()
        area = []
        for elements in check_timezone:
            match = elements.split("/") # Split karena formatnya Continent/Area
            if location.title() in match:
                area = match

        if area == []:
            return await ctx.send('Aku tidak bisa menemukan daerah itu!\nLihat list daerah yang ada [click disini!](http://www.worldtimeapi.org/api/timezone)\nContoh: `r-time Makassar`')
        
        req_data = "/".join(area)
        data = requests.get(f'http://worldtimeapi.org/api/timezone/{req_data}').json()
        day = str(data['day_of_week'])
        day = day_of_week[day]

        local_datetimestr = data['datetime']
        utc_datetimestr = data['utc_datetime']
        local_datetimeobj = datetime.fromisoformat(local_datetimestr)
        utc_datetimeobj = datetime.fromisoformat(utc_datetimestr)

        local_time = local_datetimeobj.strftime('%H:%M:%S')
        utc_time = utc_datetimeobj.strftime('%H:%M:%S')

        embed = discord.Embed(title=f"Waktu di {area[1]}", description=f"UTC{data['utc_offset']}", color=0x00ffff)
        embed.add_field(name="Akronim Timezone", value=data['abbreviation'], inline=False)
        embed.add_field(name="Perbandingan Waktu:",
                        value=f"Waktu Lokal: {local_time}\nWaktu UTC: {utc_time}\nWaktu Anda: <t:{ctx.message.created_at}:T>",
                        inline=False
                        )
        embed.add_field(name="Hari di Lokasi", value=f"{day} (Hari ke-{data['day_of_year']})", inline=False)
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
        if ctx.message.reference:
            fetch_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            try:
                if fetch_message.embeds[0].footer.text == 'Jika ada yang ingin ditanyakan, bisa langsung direply!':
                    return  # If the reply feature is used whilst running this one, it'll cancel.
                            # This is so that it doesn't execute 2 requests to OpenAI at once, lowering usage.
            except:
                pass
        
        async with ctx.typing():
            openai.api_key = os.getenv('openaikey')
            result = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                temperature=1.2,
                messages=[
                {"role":'system', 'content':getenv('rolesys')+f' You are currently talking to {ctx.author}'},
                {"role":'assistant', 'content':f"You are currently talking to {ctx.author}"},
                {"role": "user", "content": message}
                ]
            )
            
            if len(message) > 256:
               message = message[:253] + '...' #Adding ... from 253rd character, ignoring other characters.

            embed = discord.Embed(
                title=' '.join((titlecase(word) for word in message.split(' '))), 
                color=ctx.author.color, 
                timestamp=ctx.message.created_at
                )
            embed.description = result['choices'][0]['message']['content'] # Might improve for >4096 chrs
            embed.set_author(name=ctx.author)
            embed.set_footer(text='Jika ada yang ingin ditanyakan, bisa langsung direply!')
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
            start=time()
            openai.api_key = os.getenv('openaikey')
            result = await openai.Image.acreate(
                prompt=prompt,
                size='1024x1024',
                response_format='b64_json',
                n=1
            )
            b64_data = result['data'][0]['b64_json']; end=time() # Finished generating and gained data
            decoded_data = base64.b64decode(b64_data)
            image=open('generated.png', 'wb')
            image.write(decoded_data)
            image.close()
            required_time=end-start

            embed = discord.Embed(title='Karya Diciptakan', color=ctx.author.colour, timestamp=ctx.message.created_at)
            embed.description = f'Prompt: `{prompt}`\nWaktu dibutuhkan: **`{round(required_time, 2)} detik`**'
            file = discord.File("generated.png")
            embed.set_image(url= "attachment://generated.png")
        
        await ctx.reply(file=file, embed=embed)
        os.remove('./generated.png')

    def crop_to_square(self, img_path):
        """
        Converts ANY aspect ratio to 1:1
        Thanks, RVDIA!
        """
        with Image.open(img_path) as img:
            width, height = img.size
            size = min(width, height)
            left = (width - size) // 2
            top = (height - size) // 2
            right = (width + size) // 2
            bottom = (height + size) // 2
            cropped = img.crop((left, top, right, bottom))
            cropped.save(img_path[2:])

    @commands.hybrid_command(
        aliases=['edit', 'imageedit'],
        description='Ciptakan variasi dari gambar yang diberikan!'
        )
    @app_commands.describe(attachment='Lampirkan gambar!')
    @commands.cooldown(type=commands.BucketType.user, per=2, rate=1)
    @check_blacklist()
    async def variation(self, ctx:commands.Context, attachment:discord.Attachment):
        """
        Ciptakan variasi dari gambar yang diberikan!
        """
        attachment = attachment or ctx.message.attachments[0]
        
        await attachment.save(attachment.filename)
        self.crop_to_square(f'./{attachment.filename}')
        selected_image=attachment.filename

        special_supported = ['.jpg', '.JPEG', '.jpeg']
        if any(attachment.filename.endswith(suffix) for suffix in special_supported):
            image = Image.open(attachment.filename)
            image.save(f'{attachment.filename[:-3]}.png' if attachment.filename.endswith('.jpg') else f'{attachment.filename[:-4]}.png')
            selected_image = f'{attachment.filename[:-3]}.png' if attachment.filename.endswith('.jpg') else f'{attachment.filename[:-4]}.png'

        async with ctx.typing():
            start=time()
            openai.api_key = os.getenv('openaikey')
            result = await openai.Image.acreate_variation(
                image = open(selected_image, 'rb'),
                size='1024x1024',
                response_format = 'b64_json',
                n=1
            )
            os.remove(f'./{selected_image}') # No longer need file
            b64_data = result['data'][0]['b64_json']; end=time()
            decoded_data = base64.b64decode(b64_data)
            image=open('variation.png', 'wb')
            image.write(decoded_data)
            image.close()
            required_time=end-start

            embed = discord.Embed(title='Variasi Diciptakan', color=ctx.author.colour, timestamp=ctx.message.created_at)
            embed.description = f'Waktu dibutuhkan: **`{round(required_time, 2)} detik`**'
            file = discord.File("variation.png")
            embed.set_image(url= "attachment://variation.png")
            embed.set_footer(text='Kesalahan pada gambar? Mungkin karena gambar aslinya tidak 1:1!')

        await ctx.reply(file=file, embed=embed)
        os.remove('./variation.png')


async def setup(bot:commands.Bot):
    await bot.add_cog(General(bot))
    await bot.add_cog(Utilities(bot))