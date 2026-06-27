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
from scripts.main import heading, Url_Buttons, has_pfp, AIClient, db
from scripts.main import event_available, titlecase, check_blacklist, check_vote, smart_title_case
from scripts.utils.i18n import i18n
    
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
    def __init__(self, query: str, results: list, author_id: int, lang: str = "en"):
        super().__init__(timeout=60)
        self.query = query
        self.results = results
        self.author_id = author_id
        self.current_index = 0
        self.lang = lang
        self.prev_button.label = i18n.get(lang, "general.prev_page")
        self.next_button.label = i18n.get(lang, "general.next_page")

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
            
        embed_title = i18n.get(self.lang, "general.search_results", query=title)
        embed = discord.Embed(
            title=embed_title,
            color=0x34a853
        )
        embed.description = f"### [{res_title}]({link})\n{snippet}"
        footer_text = i18n.get(self.lang, "general.search_page_footer", current=self.current_index + 1, total=len(self.results))
        embed.set_footer(text=footer_text)
        return embed

    @discord.ui.button(style=discord.ButtonStyle.gray, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            msg = i18n.get(self.lang, "general.search_not_yours")
            return await interaction.response.send_message(msg, ephemeral=True)
        
        self.current_index = (self.current_index - 1) % len(self.results)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(style=discord.ButtonStyle.gray, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            msg = i18n.get(self.lang, "general.search_not_yours")
            return await interaction.response.send_message(msg, ephemeral=True)
        
        self.current_index = (self.current_index + 1) % len(self.results)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class General(commands.Cog):
    """
    General purpose commands.
    """
    def __init__(self, bot:commands.AutoShardedBot):
        self.bot = bot

    @commands.hybrid_group(name='rvdia')
    @check_blacklist()
    async def rvdia_command(self, ctx:commands.Context) -> None:
        """
        Special commands for RVDiA.
        """
        await self.rvdia(ctx)
        pass

    @commands.hybrid_group(name='user')
    @check_blacklist()
    async def user_command(self, ctx:commands.Context, member:discord.Member=None) -> None:
        """
        Commands for checking user information.
        """
        member = member or ctx.author
        await self.userinfo(ctx, member=member)
        pass

    @commands.hybrid_group(name='avatar')
    @check_blacklist()
    async def avatar_command(self, ctx:commands.Context, *, member:discord.User=None) -> None:
        """
        Commands related to user avatars.
        """
        member = member or ctx.author
        await self.avatar(ctx, global_user=member)
        pass

    @commands.hybrid_command(description='Repeats whatever you say!')
    @app_commands.describe(
        teks='What do you want me to say?',
        attachment='Attach an image, if you want.'
        )
    @check_blacklist()
    async def say(self, ctx:commands.Context, attachment:discord.Attachment=None, *, teks:str=None):
        """
        Repeats whatever you say!
        """
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            if attachment:
                import tempfile
                _, ext = os.path.splitext(attachment.filename)
                ext = re.sub(r'[^a-zA-Z0-9.]', '', ext)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    tmp_name = tmp.name
                
                try:
                    await attachment.save(tmp_name)
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
                not_sure_msg = i18n.get(lang, "general.say_not_sure")
                await ctx.send(teks) if teks else await ctx.send(not_sure_msg)

    @rvdia_command.command(name="about", aliases=['intro', 'bot', 'botinfo'])
    @check_blacklist()
    async def rvdia(self, ctx:commands.Context) -> None:
        """
        Shows everything about me!
        """
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            m = 0
            for k in self.bot.guilds:
                m += k.member_count -1
            
            embed_title = i18n.get(lang, "general.about_title")
            embed = discord.Embed(title=embed_title, color=self.bot.color)
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_image(url=getenv('banner') if not self.bot.event_mode else getenv('bannerevent'))
            
            mode_val = i18n.get(lang, "general.about_event_mode") if self.bot.event_mode else i18n.get(lang, "general.about_standard_mode")
            cmd_val = i18n.get(lang, "general.about_commands_value", all=len(self.bot.commands), glob=self.bot.synced[1])

            embed.add_field(name=i18n.get(lang, "general.about_version"), value=f"{self.bot.__version__}", inline=False)
            embed.add_field(name=i18n.get(lang, "general.about_mode"), value=mode_val, inline=False)
            embed.add_field(name=i18n.get(lang, "general.about_creator"), value=f"<@{getenv('schryzonid')}> (Jayananda)", inline=False)
            embed.add_field(name=i18n.get(lang, "general.about_prefix"), value='@RVDIA | / (slash)')
            embed.add_field(name=i18n.get(lang, "general.about_language"), value=f"Python ({pyver[:6]})\ndiscord.py ({discord.__version__})", inline=False)
            embed.add_field(name=i18n.get(lang, "general.about_uptime"), value=f"<t:{round(self.bot.runtime)}>\n(<t:{round(self.bot.runtime)}:R>)", inline=False)
            embed.add_field(name=i18n.get(lang, "general.about_servers"), value=f"{len(self.bot.guilds)} Server")
            embed.add_field(name=i18n.get(lang, "general.about_users"), value=f"{m} {i18n.get(lang, 'general.about_users')}")
            embed.add_field(name=i18n.get(lang, "general.about_commands"), value=cmd_val, inline=False)
            embed.set_footer(text=i18n.get(lang, "general.about_footer"))
            await ctx.send(embed=embed, view=Url_Buttons())
    
    @rvdia_command.command(name="ping",
        description = "Shows the latency to the Discord API."
        )
    @check_blacklist()
    async def ping(self, ctx:commands.Context) -> None:
        """
        Shows the latency to the Discord API.
        """
        start_typing = time()
        await ctx.typing()
        end_typing = time()
        delta_typing = end_typing - start_typing

        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        timestamp = ctx.message.created_at if ctx.message else ctx.interaction.created_at
        embed= discord.Embed(title=i18n.get(lang, "general.ping_title"), color=self.bot.color, timestamp=timestamp)
        embed.description = f"**{i18n.get(lang, 'general.ping_api')}:** `{round(self.bot.latency*1000)} ms`\n**{i18n.get(lang, 'general.ping_typing')}:** `{round(delta_typing*1000, 2)} ms`"
        await ctx.reply(embed=embed)

    @user_command.command(description="Shows the avatar of a Discord user.")
    @app_commands.describe(global_user='User whose profile picture you want to view')
    @has_pfp()
    @check_blacklist()
    async def avatar(self, ctx, *, global_user: discord.User = None):
        """
        Shows the avatar of a Discord user.
        Support: (ID, @Mention, username, name#tag)
        """
        async with ctx.typing():
            global_user = global_user or ctx.author
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            if global_user.avatar is None:
                no_pfp_msg = i18n.get(lang, "general.avatar_no_pfp", user=str(global_user))
                return await ctx.reply(no_pfp_msg)
            png = global_user.avatar.with_format("png").url
            jpg = global_user.avatar.with_format("jpg").url
            webp = global_user.avatar.with_format("webp").url

            title_txt = i18n.get(lang, "general.avatar_title", user=str(global_user))
            embed=discord.Embed(title=title_txt, url = png, color= 0xff4df0)

            if global_user.avatar.is_animated():
                gif = global_user.avatar.with_format("gif").url
                embed.set_image(url = gif)
                embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp}) | [gif]({gif})"

            else:
                embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp})"
                embed.set_image(url = png)
            embed.set_footer(text=f"{ctx.author}", icon_url=ctx.author.display_avatar.url)
            await ctx.reply(embed=embed)

    @user_command.command(name='info', aliases = ['whois'], description="Show information about someone in this server.")
    @app_commands.rename(member='user')
    @app_commands.describe(
        member = 'User whose information you want to view'
    )
    @check_blacklist()
    async def userinfo(self, ctx:commands.Context, *, member:discord.Member = None):
        """
        Show information about someone in this server.
        Support: (ID, @Mention, username, name#tag)
        """
        async with ctx.typing():
            member = member or ctx.author
            avatar_url = member.display_avatar.url
            bot = member.bot
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

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
            embed.set_author(name=i18n.get(lang, "general.userinfo_header"))
            embed.set_thumbnail(url=avatar_url)
            embed.add_field(name=i18n.get(lang, "general.userinfo_nickname"), value=nick, inline=False)
            embed.add_field(name=i18n.get(lang, "general.userinfo_created"), value=member.created_at.strftime("%a, %d %B %Y"))
            embed.add_field(name=i18n.get(lang, "general.userinfo_joined"), value=member.joined_at.strftime("%a, %d %B %Y"))
            embed.add_field(name=i18n.get(lang, "general.userinfo_top_role"), value=member.top_role.mention, inline=False)
            
            roles_title = i18n.get(lang, "general.userinfo_roles", count=role_length)
            if role_length > 10:
                embed.add_field(name=roles_title, value=" ".join(roles[:10]) + f"\n({i18n.get(lang, 'general.first_10_roles')})", inline=False)
            else:
                embed.add_field(name=roles_title, value=" ".join(roles), inline=False)
            
            perms_title = i18n.get(lang, "general.userinfo_permissions", count=perm_len)
            embed.add_field(name=perms_title, value="`"+", ".join(permissions_fixed)+"`", inline=False)
            owner = await self.bot.fetch_user(ctx.guild.owner_id)
            ack = None
            match member.id:
                case self.bot.owner_id:
                    ack = i18n.get(lang, "general.userinfo_known_creator")
                case self.bot.user.id:
                    ack = i18n.get(lang, "general.userinfo_known_love")

            if ack == None:
                if member.bot == True:
                    ack = i18n.get(lang, "general.userinfo_known_bot")
                elif owner.id == member.id:
                    ack = i18n.get(lang, "general.userinfo_known_owner")
                elif member.guild_permissions.administrator == True:
                    ack = i18n.get(lang, "general.userinfo_known_admin")
                else:
                    ack = i18n.get(lang, "general.userinfo_known_member")

            embed.add_field(name=i18n.get(lang, "general.userinfo_known_title"), value = ack)
            embed.set_footer(text=f"ID: {member.id}", icon_url=avatar_url)
            await ctx.reply(embed=embed)





class Utilities(commands.Cog):
    """
    Utility commands (weather, time, web search, etc.).
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(aliases = ['cuaca'], description="Check the weather in a city or area!")
    @app_commands.describe(
        location = 'City or area to search weather for'
    )
    @check_blacklist()
    async def weather(self, ctx:commands.Context, *, location:str):
        """
        Check the weather in a city or area!
        """
        try:
            await ctx.defer()
        except discord.NotFound:
            pass
            
        async with ctx.channel.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f'http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={getenv("openweatherkey")}') as resp:
                        data = await resp.json()
                    
                    if not data:
                        return await ctx.send(i18n.get(lang, "general.weather_not_found"))
                        
                    geocode = [data[0]['lat'], data[0]['lon']]
                    async with session.get(f"https://api.openweathermap.org/data/2.5/weather?lat={geocode[0]}&lon={geocode[1]}&lang={lang}&units=metric&appid={getenv('openweatherkey')}") as resp:
                        result = await resp.json()
                        
                    icon = f"http://openweathermap.org/img/wn/{result['weather'][0]['icon']}@4x.png"
                    embed_title = i18n.get(lang, "general.weather_title", location=result['name'])
                    embed = discord.Embed(title=embed_title, description=f"__{result['weather'][0]['description'].title()}__")
                    embed.color = 0x00ffff
                    embed.set_thumbnail(url=icon)
                    
                    temp = result['main']
                    temp_title = i18n.get(lang, "general.weather_temp_title", temp=temp['temp'])
                    temp_details = i18n.get(
                        lang,
                        "general.weather_temp_details",
                        feels=temp['feels_like'],
                        min=temp['temp_min'],
                        max=temp['temp_max'],
                        press=temp['pressure'],
                        humid=temp['humidity'],
                        clouds=result['clouds']['all']
                    )
                    embed.add_field(name=temp_title, value=temp_details, inline=False)
                    
                    wind = result['wind']
                    wind_title = i18n.get(lang, "general.weather_wind_title")
                    
                    deg_dir = heading(wind['deg'])
                    if lang == "en":
                        deg_dir_map = {
                            "Utara": "North", "Timur Laut": "Northeast", "Timur": "East", "Tenggara": "Southeast",
                            "Selatan": "South", "Barat Daya": "Southwest", "Barat": "West", "Barat Laut": "Northwest"
                        }
                        deg_dir = deg_dir_map.get(deg_dir, deg_dir)

                    wind_details = i18n.get(lang, "general.weather_wind_details", speed=wind['speed'], deg=wind['deg'], dir=deg_dir)
                    embed.add_field(name=wind_title, value=wind_details, inline=False)
                    
                    embed.add_field(name="Sunrise", value=f"<t:{result['sys']['sunrise']}:R>", inline=False)
                    embed.add_field(name="Sunset", value=f"<t:{result['sys']['sunset']}:R>")
                    embed.set_footer(text=f"{ctx.author}", icon_url=ctx.author.display_avatar.url)
                    await ctx.send(embed=embed)

            except Exception as e:
                import logging
                logging.error(f"Error in weather command: {e}", exc_info=True)
                await ctx.send(i18n.get(lang, "general.weather_error"))

    @commands.hybrid_command(description="Check the current time in a city or area!")
    @app_commands.describe(location='City or area to search time for')
    @check_blacklist()
    async def time(self, ctx:commands.Context, *, location:str):
        """
        Check the current time in a city or area!
        """
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            check_timezone = requests.get(f'http://worldtimeapi.org/api/timezone').json()
            area = []
            for elements in check_timezone:
                match = elements.split("/")
                if location.title() in match:
                    area = match

            if area == []:
                return await ctx.send(i18n.get(lang, "general.time_not_found"))
            
            req_data = "/".join(area)
            data = requests.get(f'http://worldtimeapi.org/api/timezone/{req_data}').json()
            day = str(data['day_of_week'])
            
            day_name = day_of_week[day]
            if lang == "en":
                day_name_map = {
                    "Senin": "Monday", "Selasa": "Tuesday", "Rabu": "Wednesday", "Kamis": "Thursday",
                    "Jumat": "Friday", "Sabtu": "Saturday", "Minggu": "Sunday"
                }
                day_name = day_name_map.get(day_name, day_name)

            local_datetimestr = data['datetime']
            utc_datetimestr = data['utc_datetime']
            local_datetimeobj = datetime.fromisoformat(local_datetimestr)
            utc_datetimeobj = datetime.fromisoformat(utc_datetimestr)

            local_time = local_datetimeobj.strftime('%H:%M:%S')
            utc_time = utc_datetimeobj.strftime('%H:%M:%S')

            embed = discord.Embed(title=i18n.get(lang, "general.time_title", location=area[1]), description=f"UTC{data['utc_offset']}", color=0x00ffff)
            embed.add_field(name="Timezone Abbreviation", value=data['abbreviation'], inline=False)
            
            comparison_val = i18n.get(
                lang,
                "general.time_comparison_val",
                local=local_time,
                utc=utc_time,
                ts=round(ctx.message.created_at.timestamp() if ctx.message else datetime.now().timestamp())
            )
            embed.add_field(name=i18n.get(lang, "general.time_comparison"), value=comparison_val, inline=False)
            embed.add_field(name=i18n.get(lang, "general.time_day"), value=i18n.get(lang, "general.time_day_val", day=day_name, doy=data['day_of_year']), inline=False)
            await ctx.send(embed=embed)

    @commands.hybrid_command(description="Show the color of a hexadecimal value.")
    @app_commands.describe(hex='Hexadecimal code (e.g., FF0000).')
    @has_pfp()
    @check_blacklist()
    async def hex(self, ctx:commands.Context, hex:str):
        """Show the color of a hexadecimal value."""
        if "#" in hex:
            hex = hex.split('#')[1]

        async def validate_hex(hex_str:str):
            pattern = r'^[0-9A-Fa-f]+$'
            if not re.match(pattern, hex_str):
                raise ValueError("Invalid hex!")
            
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        try:
            await validate_hex(hex)
        except:
            return await ctx.reply(i18n.get(lang, "general.hex_invalid", hex=hex), ephemeral=True)
        
        hex_code = int(hex, 16)
        red = (hex_code >> 16) & 0xff
        green = (hex_code >> 8) & 0xff
        blue = hex_code & 0xff

        from PIL import Image
        from io import BytesIO
        try:
            color_img = Image.new("RGB", (500, 500), (red, green, blue))
            image = BytesIO()
            color_img.save(image, format="PNG")
            image.seek(0)
            await ctx.reply(content=f"Hex: #{hex.upper()}\nRGB: ({red}, {green}, {blue})", file=discord.File(image, f'{hex.upper()}.png'))
        except Exception as e:
            logging.error(f"Error generating local hex image: {e}")
            await ctx.reply("❌ Error generating color image.", ephemeral=True)

    @commands.hybrid_command(description="Show the color of an RGB value.")
    @app_commands.describe(
        red='Red value (0 - 255)',
        green='Green value (0 - 255)',
        blue='Blue value (0 - 255)'
        )
    @has_pfp()
    @check_blacklist()
    async def rgb(self, ctx:commands.Context, red:int, green:int, blue:int):
        """Show the color of an RGB value."""
        rgb = [red, green, blue]
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if any(color > 255 for color in rgb):
            return await ctx.reply(i18n.get(lang, "general.rgb_invalid"), ephemeral=True)
        hex_value = '{:02x}{:02x}{:02x}'.format(red, green, blue)
        await self.hex(ctx, hex_value)

    @commands.hybrid_command(description="Search for a location and get a Google Maps link.")
    @app_commands.describe(location="The city or area to find.")
    @check_blacklist()
    async def map(self, ctx: commands.Context, *, location: str):
        """Search for a location and get a Google Maps link."""
        try:
            await ctx.defer()
        except discord.NotFound:
            pass

        async with ctx.channel.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            api_key = os.getenv("openweatherkey")
            if not api_key:
                return await ctx.send("⚠️ OpenWeather API key is not configured.")

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f'http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={api_key}') as resp:
                        data = await resp.json()

                    if not data:
                        err = i18n.get(lang, "general.weather_not_found")
                        return await ctx.send(f"⚠️ {err}")

                    lat = data[0]['lat']
                    lon = data[0]['lon']
                    name = data[0]['name']
                    country = data[0].get('country', '')

                    maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                    
                    title = "🗺️ Google Maps Location" if lang == "en" else "🗺️ Lokasi Google Maps"
                    embed = discord.Embed(title=f"{title}: {name}, {country}", color=0x34a853)
                    embed.add_field(name="📍 Coordinates" if lang == "en" else "📍 Koordinat", value=f"`{lat}, {lon}`", inline=False)
                    embed.add_field(name="🔗 Google Maps Link" if lang == "en" else "🔗 Link Google Maps", value=f"[Click here to view / Klik di sini untuk melihat]({maps_url})", inline=False)
                    
                    static_map_url = f"https://static-maps.yandex.ru/1.x/?ll={lon},{lat}&z=12&l=map&size=600,450"
                    embed.set_image(url=static_map_url)
                    
                    embed.set_footer(text=f"Requested by {ctx.author.name}")
                    await ctx.reply(embed=embed)
            except Exception as e:
                logging.error(f"Error in map command: {e}")
                err_msg = "❌ Failed to fetch location coordinates." if lang == "en" else "❌ Gagal mengambil koordinat lokasi."
                await ctx.reply(err_msg)

    @commands.hybrid_command(aliases=['search'], description="Search the web using DuckDuckGo.")
    @app_commands.describe(query="Search keyword")
    @check_blacklist()
    async def google(self, ctx: commands.Context, *, query: str):
        """Search the web using DuckDuckGo."""
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            try:
                from scripts.utils.search import search_web
                
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
                
                results = await search_web(query, max_results=10, safesearch=safesearch)
                if not results:
                    return await ctx.reply(i18n.get(lang, "general.search_no_results"))
                
                view = WebSearchView(query, results, ctx.author.id, lang=lang)
                await ctx.reply(embed=view.create_embed(), view=view)
            except Exception as e:
                await ctx.reply(i18n.get(lang, "general.search_error", error=str(e)))

class Support(commands.GroupCog, group_name='support'):
    """
    Commands to get support or submit suggestions.
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
        def __init__(self, lang="en"):
            super().__init__(timeout=None)

            if lang == "en":
                label = "GitHub Sponsors"
                url = "https://github.com/sponsors/Schryzon"
            else:
                label = "Saweria Link"
                url = "https://saweria.co/schryzon"

            donate = Button(
                label=label,
                emoji = '<:rvdia_happy:1121412270220660803>',
                style = discord.ButtonStyle.blurple,
                url = url
            )
            self.add_item(donate)

    @app_commands.command(description = 'Send the link to my support server!')
    async def guild(self, interaction:discord.Interaction):
        """
        Send the link to my support server!
        """
        user_settings = await db.usersettings.find_unique(where={'userId': interaction.user.id})
        lang = user_settings.lang if user_settings else "en"
        msg = i18n.get(lang, "general.support_guild")
        await interaction.response.send_message(msg, view=self.Support_Button())

    @app_commands.command(description = "Support RVDiA's development!")
    async def donate(self, interaction:discord.Interaction):
        """
        Support RVDiA's development!
        """
        user_settings = await db.usersettings.find_unique(where={'userId': interaction.user.id})
        lang = user_settings.lang if user_settings else "en"
        msg = i18n.get(lang, "general.support_donate")
        await interaction.response.send_message(msg, view=self.Donate_Button(lang))

    @app_commands.command(description = 'Give me suggestions for improvements or new features!')
    @app_commands.describe(text='What suggestions or feedback do you want to submit?')
    @app_commands.describe(attachment='An optional screenshot or image of the suggestion')
    @check_blacklist()
    async def suggest(self, interaction:discord.Interaction, text:str, attachment:discord.Attachment = None):
        """
        Give me suggestions for improvements or new features!
        """
        user_settings = await db.usersettings.find_unique(where={'userId': interaction.user.id})
        lang = user_settings.lang if user_settings else "en"

        suggestion_channel_id = os.getenv('suggestionchannel')
        if not suggestion_channel_id:
            msg = i18n.get(lang, "general.suggest_not_configured")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        channel = self.bot.get_channel(int(suggestion_channel_id))
        title = i18n.get(lang, "general.suggest_title")
        embed = discord.Embed(title=title, color=interaction.user.color, timestamp=interaction.created_at)
        author_val = i18n.get(lang, "general.suggest_author", user=str(interaction.user))
        embed.set_author(name=author_val)
        if attachment:
            embed.set_image(url = attachment.url)
        embed.description = text
        embed.set_thumbnail(url = interaction.user.display_avatar.url) # New knowledge get!
        await channel.send(embed=embed)
        success_msg = i18n.get(lang, "general.suggest_success")
        await interaction.response.send_message(success_msg)

async def setup(bot:commands.Bot):
    await bot.add_cog(General(bot))
    await bot.add_cog(Utilities(bot))
    await bot.add_cog(Support(bot))