"""
Just a damn filler
I'm sick, tired, and all that
But still, I'm gonna try...
All commands require you to vote
"""

import discord
from aiohttp import ClientSession
from discord import app_commands
from discord.ext import commands
from scripts.main import check_blacklist, has_voted

class Roleplay(commands.Cog):
    """
    Kumpulan command interaksi antar pengguna.
    """
    def __init__(self, bot:commands.AutoShardedBot):
        self.bot=bot

    async def nekos_get(self, category:str):
        """
        Instead of making a ton of calls later,
        why not here instead?
        """
        async with ClientSession() as session:
            initial_connection = await session.get(f'https://nekos.best/api/v2/{category}')
            data = await initial_connection.json()
            data_list = data['results'][0]
            return [data_list['url'], data_list['anime_name']]
        
    async def create_embed_and_sendGIF(
            self, 
            ctx:commands.Context, 
            user:discord.Member, 
            url:str,
            source:str,
            action:str,
            ):
        """
        Lazy me lol
        """
        embed = discord.Embed(title=f'{ctx.author.display_name} {action} {user.display_name}!', color=ctx.author.color)
        embed.set_image(url=url)
        embed.set_footer(text=f'Source: {source}')
        await ctx.send(embed=embed)

    @commands.hybrid_group(name='roleplay', aliases=['rp'])
    async def roleplay(self, ctx:commands.Context):
        """
        Kumpulan command interaksi antar pengguna. [GROUP]
        """
        # Execute a random command here idk
        pass

    @roleplay.command(description='Peluk seseorang!')
    @app_commands.describe(user='Siapa yang ingin kamu peluk?')
    @app_commands.rename(user='pengguna')
    @check_blacklist()
    @has_voted()
    async def hug(self, ctx:commands.Context, *, user:discord.Member):
        get_request = await self.nekos_get('hug')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx, user, gif_url, anime_name, 'Memeluk')
    
    @roleplay.command(description='Cium seseorang!')
    @app_commands.describe(user='Siapa yang ingin kamu cium?')
    @app_commands.rename(user='pengguna')
    @check_blacklist()
    @has_voted()
    async def kiss(self, ctx:commands.Context, *, user:discord.Member):
        get_request = await self.nekos_get('kiss')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx, user, gif_url, anime_name, 'Mencium')
    
    @roleplay.command(description='Tampar seseorang!')
    @app_commands.describe(user='Siapa yang ingin kamu tampar?')
    @app_commands.rename(user='pengguna')
    @check_blacklist()
    @has_voted()
    async def slap(self, ctx:commands.Context, *, user:discord.Member):
        get_request = await self.nekos_get('slap')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx, user, gif_url, anime_name, 'Menampar')

async def setup(bot):
    await bot.add_cog(Roleplay(bot))