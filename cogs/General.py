import base64
import re
import os
import discord
import openai
import requests
import aiohttp
import pytz
from google import genai
from google.genai import types
from datetime import datetime
from sys import version as pyver
from os import getenv
from cogs.Event import Event
from discord import app_commands
from discord.ext import commands
from time import time
from PIL import Image
from io import BytesIO
from discord.ui import View, Button, button
from scripts.main import heading, Url_Buttons, has_pfp, AIClient
from scripts.main import event_available, titlecase, check_blacklist, check_vote, smart_title_case
    
day_of_week = {
    '1':"Senin",
    '2':"Selasa",
    '3':"Rabu",
    '4':"Kamis",
    '5':"Jumat",
    '6':"Sabtu",
    '0':"Minggu"
}


class WebSearchView(discord.ui.View):
    """
    View for paginated web search results.
    """
    def __init__(self, query: str, results: list, author_id: int):
        super().__init__(timeout=60)
        self.query = query
        self.results = results
        self.author_id = author_id
        self.current_index = 0

    def create_embed(self):
        data = self.results[self.current_index]
        title = smart_title_case(self.query)
        res_title = data['title']
        snippet = data['snippet']
        link = data['link']
        
        # Truncate title if too long
        if len(res_title) > 256:
            res_title = res_title[:253] + "..."
            
        # Truncate snippet if too long to prevent embed limits
        if len(snippet) > 1000:
            snippet = snippet[:997] + "..."
            
        embed = discord.Embed(
            title=f"Hasil Pencarian: {title}",
            color=0x34a853
        )
        embed.description = f"### [{res_title}]({link})\n{snippet}"
        embed.set_footer(text=f"Hasil {self.current_index + 1}/{len(self.results)}")
        return embed

    @discord.ui.button(label="Sebelumnya", style=discord.ButtonStyle.gray, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Hey! Ini bukan sesi pencarianmu!", ephemeral=True)
        
        self.current_index = (self.current_index - 1) % len(self.results)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Selanjutnya", style=discord.ButtonStyle.gray, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Hey! Ini bukan sesi pencarianmu!", ephemeral=True)
        
        self.current_index = (self.current_index + 1) % len(self.results)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class General(commands.Cog):
    """
    Kumpulan command umum.
    """
    def __init__(self, bot:commands.AutoShardedBot):
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
        """
        Mengulangi apapun yang kamu katakan!
        """
        async with ctx.typing():
            if attachment:
                import tempfile
                # Securely get and clean the extension
                _, ext = os.path.splitext(attachment.filename)
                ext = re.sub(r'[^a-zA-Z0-9.]', '', ext)
                
                # Create a secure temp file in the system temp directory
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    tmp_name = tmp.name
                
                try:
                    await attachment.save(tmp_name)
                    # Sanitize filename for Discord attachment presentation
                    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', attachment.filename)
                    file = discord.File(tmp_name, filename=safe_filename)
                    if teks:
                        await ctx.send(teks, file=file)
                    else:
                        await ctx.send(file=file)
                finally:
                    if os.path.exists(tmp_name):
                        os.remove(tmp_name)
            
            else:
                await ctx.send(teks) if teks else await ctx.send("Aku gak tau harus berkata apa ¯\_(ツ)_/¯")

    @rvdia_command.command(name="about", aliases=['intro', 'bot', 'botinfo'])
    @check_blacklist()
    async def rvdia(self, ctx:commands.Context) -> None:
        """
        Memperlihatkan segalanya tentang aku!
        """
        async with ctx.typing():
            m = 0
            for k in self.bot.guilds:
                m += k.member_count -1
            embed = discord.Embed(title="Tentang RVDiA", color=self.bot.color)
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_image(url=getenv('banner') if not self.bot.event_mode else getenv('bannerevent'))
            embed.add_field(name = "Versi", value = f"{self.bot.__version__}", inline=False)
            embed.add_field(name = "Mode", value = f"Event Mode" if self.bot.event_mode else "Standard Mode", inline=False)
            embed.add_field(name = "Pencipta", value = f"<@{getenv('schryzonid')}> (Jayananda)", inline=False) # self.bot.owner_id did nothing here.
            embed.add_field(name = "Prefix", value = '@RVDIA | / (slash)')
            embed.add_field(name = "Bahasa Pemrograman", value=f"Python ({pyver[:6]})\ndiscord.py ({discord.__version__})", inline=False)
            embed.add_field(name = "Nyala Sejak", value = f"<t:{round(self.bot.runtime)}>\n(<t:{round(self.bot.runtime)}:R>)", inline = False)
            embed.add_field(name = "Jumlah Server", value = f"{len(self.bot.guilds)} Server")
            embed.add_field(name = "Jumlah Pengguna", value = f"{m} Pengguna")
            embed.add_field(name = "Jumlah Command Group", value = f"Semua: `{len(self.bot.commands)}`\nGlobal: `{self.bot.synced[1]}`", inline=False)
            embed.set_footer(text="Jangan lupa tambahkan aku ke servermu! ❤️")
            await ctx.send(embed=embed, view=Url_Buttons())
    
    @rvdia_command.command(name="ping",
        description = "Menampilkan latency ke Discord API."
        )
    @check_blacklist()
    async def ping(self, ctx:commands.Context) -> None:
        """
        Menampilkan latency ke Discord API
        """
        start_typing = time()
        await ctx.typing()
        end_typing = time()
        delta_typing = end_typing - start_typing
        timestamp = ctx.message.created_at if ctx.message else ctx.interaction.created_at
        embed= discord.Embed(title= "Ping--Pong!", color=self.bot.color, timestamp=timestamp)
        embed.description = f"**Discord API:** `{round(self.bot.latency*1000)} ms`\n**Typing:** `{round(delta_typing*1000, 2)} ms`"
        await ctx.reply(embed=embed)

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
        async with ctx.typing():
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
            embed.set_footer(text=f"{ctx.author}", icon_url=ctx.author.display_avatar.url)
            await ctx.reply(embed=embed)

    @user_command.command(name='info', aliases = ['whois'], description="Lihat info tentang seseorang di server ini.")
    @app_commands.rename(member='pengguna')
    @app_commands.describe(
        member = 'Siapa yang ingin diketahui infonya?'
    )
    @check_blacklist()
    async def userinfo(self, ctx:commands.Context, *, member:discord.Member = None):
        """
        Lihat info tentang seseorang di server ini.
        Support: (ID, @Mention, username, name#tag)
        """
        async with ctx.typing():
            member = member or ctx.author
            avatar_url = member.display_avatar.url # Avoids returning None
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
            change1 = [underscore.replace('_', ' ') for underscore in perm_list]
            permissions_fixed = [permissions.title() for permissions in change1]

            timestamp = ctx.message.created_at if ctx.message else ctx.interaction.created_at
            embed=discord.Embed(title=member, color=member.colour, timestamp=timestamp)
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
            embed.add_field(name=f"Permissions [{str(perm_len)}]", value="`"+", ".join(permissions_fixed)+"`", inline=False)
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
    async def weather(self, ctx:commands.Context, *, location:str):
        """
        Lihat info tentang keadaan cuaca di suatu kota atau daerah!
        """
        try:
            await ctx.defer()
        except discord.NotFound:
            pass
            
        async with ctx.channel.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    # Need to decode geocode consisting of latitude and longitude
                    async with session.get(f'http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={getenv("openweatherkey")}') as resp:
                        data = await resp.json()
                    
                    if not data:
                        return await ctx.send('Aku tidak bisa menemukan lokasi itu!')
                        
                    geocode = [data[0]['lat'], data[0]['lon']]
                    async with session.get(f"https://api.openweathermap.org/data/2.5/weather?lat={geocode[0]}&lon={geocode[1]}&lang=id&units=metric&appid={getenv('openweatherkey')}") as resp:
                        result = await resp.json()
                        
                    icon = f"http://openweathermap.org/img/wn/{result['weather'][0]['icon']}@4x.png"
                    embed = discord.Embed(title=f"Cuaca di {result['name']}", description=f"__{result['weather'][0]['description'].title()}__")
                    embed.color = 0x00ffff
                    embed.set_thumbnail(url=icon)
                    temp = result['main']
                    embed.add_field(
                            name=f"Suhu ({temp['temp']}°C)",
                            value = 
                            f"**Terasa seperti:** ``{temp['feels_like']}°C``\n**Minimum:** ``{temp['temp_min']}°C``\n**Maksimum:** ``{temp['temp_max']}°C``\n"+
                            f"**Tekanan Atmosfer:** ``{temp['pressure']} hPa``\n**Kelembaban:** ``{temp['humidity']}%``\n**Persentase Awan:** ``{result['clouds']['all']}%``",
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
                    embed.set_footer(text=f"{ctx.author}", icon_url=ctx.author.display_avatar.url)
                    await ctx.send(embed=embed)

            except Exception as e:
                import logging
                logging.error(f"Error in weather command: {e}", exc_info=True)
                await ctx.send('Terjadi kesalahan internal saat mengambil data cuaca.')

    @commands.hybrid_command(description="Lihat info tentang waktu di suatu kota atau daerah!")
    @app_commands.describe(location='Daerah mana yang ingin kamu ketahui?')
    @app_commands.rename(location='lokasi')
    @check_blacklist()
    async def time(self, ctx:commands.Context, *, location:str): # Does not conflict with the package "time"
        """
        Lihat info tentang waktu di suatu kota atau daerah!
        """
        async with ctx.typing():
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


    @commands.hybrid_command(description="Memperlihatkan warna dari nilai hexadecimal.")
    @app_commands.describe(hex='Kode hexadecimal (Contoh: FF0000).')
    @has_pfp()
    @check_blacklist()
    async def hex(self, ctx:commands.Context, hex:str):
        """Memperlihatkan warna dari nilai hexadecimal."""
        if "#" in hex:
            hex = hex.split('#')[1]

        async def validate_hex(hex_str:str):
            pattern = r'^[0-9A-Fa-f]+$'  # Regular expression pattern for hexadecimal string
            if not re.match(pattern, hex_str):
                raise ValueError("Invalid hex!")
            
        try:
            await validate_hex(hex)
        except: # Malas
            return await ctx.reply(f"`{hex}` bukan merupakan kode heksadesimal yang valid!", ephemeral=True)
        
        hex_code = int(hex, 16)
        red = (hex_code >> 16) & 0xff # Bitwise right shift
        green = (hex_code >> 8) & 0xff
        blue = hex_code & 0xff
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://singlecolorimage.com/get/{hex}/500x500') as data:
                image = BytesIO(await data.read())
                await session.close()
                await ctx.reply(content=f"Hex: #{hex.upper()}\nRGB: ({red}, {green}, {blue})", file=discord.File(image, f'{hex.upper()}.png'))

    @commands.hybrid_command(description="Memperlihatkan warna dari nilai RGB.")
    @app_commands.describe(
        red='Warna merah (0 - 255)',
        green='Warna hijau (0 - 255)',
        blue='Warna biru (0 - 255)'
        )
    @has_pfp()
    @check_blacklist()
    async def rgb(self, ctx:commands.Context, red:int, green:int, blue:int):
        """Memperlihatkan warna dari nilai RGB."""
        rgb = [red, green, blue]
        if any(color > 255 for color in rgb):
            return await ctx.reply("Salah satu nilai dari warna RGB melebihi 255!\nPastikan nilai RGB valid!", ephemeral=True)
        hex_value = '{:02x}{:02x}{:02x}'.format(red, green, blue)
        await self.hex(ctx, hex_value) # Cheat

    @commands.hybrid_command(aliases=['search'], description="Cari info/website di internet menggunakan DuckDuckGo.")
    @app_commands.describe(query="Kata kunci yang ingin dicari")
    @check_blacklist()
    async def google(self, ctx: commands.Context, *, query: str):
        """Cari info/website di internet menggunakan DuckDuckGo."""
        async with ctx.typing():
            try:
                from scripts.search import search_web
                
                # Enable NSFW results only if the channel is NSFW
                is_nsfw = False
                channel = ctx.channel
                if ctx.guild and not hasattr(channel, 'is_nsfw'):
                    cached_channel = ctx.guild.get_channel(channel.id)
                    if cached_channel:
                        channel = cached_channel
                
                if hasattr(channel, 'is_nsfw') and callable(channel.is_nsfw):
                    is_nsfw = channel.is_nsfw()
                elif hasattr(channel, 'nsfw'):
                    is_nsfw = bool(channel.nsfw)
                safesearch = 'off' if is_nsfw else 'on'
                
                # Fetch up to 10 results for pagination
                results = await search_web(query, max_results=10, safesearch=safesearch)
                if not results:
                    return await ctx.reply("Waduh! Tidak ada hasil pencarian yang ditemukan.")
                
                view = WebSearchView(query, results, ctx.author.id)
                await ctx.reply(embed=view.create_embed(), view=view)
            except Exception as e:
                await ctx.reply(f"Terjadi kesalahan saat mencari: `{str(e)}`")

class Support(commands.GroupCog, group_name='support'):
    """
    Kumpulan command khusus untuk memperoleh bantuan dan pemberian saran/kritik.
    """
    def __init__(self, bot):
        self.bot = bot
    
    class Support_Button(View):
        def __init__(self):
            super().__init__(timeout=None)

            support_server = Button(
                label= "Support Server",
                emoji = '<:cyron:1082789553263349851>',
                style = discord.ButtonStyle.blurple,
                url = 'https://discord.gg/QqWCnk6zxw'
            )
            self.add_item(support_server)

    class Donate_Button(View):
        def __init__(self):
            super().__init__(timeout=None)

            donate = Button(
                label= "Saweria Link",
                emoji = '<:rvdia_happy:1121412270220660803>',
                style = discord.ButtonStyle.blurple,
                url = 'https://saweria.co/schryzon'
            )
            self.add_item(donate)

    @app_commands.command(description = 'Mengirimkan link untuk server supportku!')
    async def guild(self, interaction:discord.Interaction):
        """
        Mengirimkan link untuk server supportku!
        """
        await interaction.response.send_message(f"Untuk join serverku agar dapat mengetahui lebih banyak tentang RVDiA, silahkan tekan link di bawah!\nhttps://discord.gg/QqWCnk6zxw\nAtau tekan tombol abu-abu di bawah ini.", view=self.Support_Button())

    @app_commands.command(description = 'Dukung RVDiA melalui Saweria!')
    async def donate(self, interaction:discord.Interaction):
        """
        Dukung RVDiA melalui Saweria!
        """
        await interaction.response.send_message(f"Untuk mendukung RVDiA secara finansial, tekan link di bawah ini!\nhttps://saweria.co/schryzon\nAtau tekan tombol abu-abu di bawah ini. Terima kasih!", view=self.Donate_Button())

    @app_commands.command(description = 'Berikan aku saran untuk perbaikan atau penambahan fitur!')
    @app_commands.rename(text='saran')
    @app_commands.rename(attachment='lampiran')
    @app_commands.describe(text='Apa yang ingin kamu sampaikan?')
    @app_commands.describe(attachment='Apakah ada contoh gambarnya? (Opsional)')
    @check_blacklist()
    async def suggest(self, interaction:discord.Interaction, text:str, attachment:discord.Attachment = None):
        """
        Berikan aku saran untuk perbaikan atau penambahan fitur!
        """
        suggestion_channel_id = os.getenv('suggestionchannel')
        if not suggestion_channel_id:
            return await interaction.response.send_message("Fitur saran belum dikonfigurasi! ❌", ephemeral=True)
            
        channel = self.bot.get_channel(int(suggestion_channel_id))
        embed = discord.Embed(title="Saran Baru!", color=interaction.user.color, timestamp=interaction.created_at)
        embed.set_author(name=f"Dari {interaction.user}")
        if attachment:
            embed.set_image(url = attachment.url)
        embed.description = text
        embed.set_thumbnail(url = interaction.user.display_avatar.url) # New knowledge get!
        await channel.send(embed=embed)
        await interaction.response.send_message(f"Terima kasih atas sarannya!\nSemoga RVDiA akan selalu bisa memenuhi ekspektasimu!")

async def setup(bot:commands.Bot):
    await bot.add_cog(General(bot))
    await bot.add_cog(Utilities(bot))
    await bot.add_cog(Support(bot))