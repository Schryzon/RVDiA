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
        if not user:
            embed = discord.Embed(title=f'{ctx.author.display_name} {action}!', color=ctx.author.color)
        else:
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
        """
        Peluk seseorang!
        """
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
        """
        Cium seseorang!
        """
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
        """
        Tampar seseorang!
        """
        get_request = await self.nekos_get('slap')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx, user, gif_url, anime_name, 'Menampar')
    
    @roleplay.command(description='Ungkapkan ekspresi tertawamu!')
    @check_blacklist()
    @has_voted()
    async def laugh(self, ctx:commands.Context):
        """
        Ungkapkan ekspresi tertawamu!
        """
        get_request = await self.nekos_get('laugh')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx=ctx, url=gif_url, source=anime_name, action='Tertawa')
    
    @roleplay.command(description='Ungkapkan ekspresi bahagiamu!')
    @check_blacklist()
    @has_voted()
    async def happy(self, ctx:commands.Context):
        """
        Ungkapkan ekspresi bahagiamu!
        """
        get_request = await self.nekos_get('happy')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx=ctx, url=gif_url, source=anime_name, action='Merasa Bahagia')
    
    @roleplay.command(description='Ungkapkan ekspresi berpikirmu!')
    @check_blacklist()
    @has_voted()
    async def think(self, ctx:commands.Context):
        """
        Ungkapkan ekspresi berpikirmu!
        """
        get_request = await self.nekos_get('think')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx=ctx, url=gif_url, source=anime_name, action='Sedang Berpikir')
    
    @roleplay.command(description='Ungkapkan ekspresi malumu!')
    @check_blacklist()
    @has_voted()
    async def blush(self, ctx:commands.Context):
        """
        Ungkapkan ekspresi malumu!
        """
        get_request = await self.nekos_get('blush')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx=ctx, url=gif_url, source=anime_name, action='Merasa Malu')
    
    @roleplay.command(description='Ungkapkan ekspresi sedihmu!')
    @check_blacklist()
    @has_voted()
    async def cry(self, ctx:commands.Context):
        """
        Ungkapkan ekspresi sedihmu!
        """
        get_request = await self.nekos_get('cry')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx=ctx, url=gif_url, source=anime_name, action='Menangis')

    @roleplay.command(description='Ungkapkan ekspresi setujumu!')
    @check_blacklist()
    @has_voted()
    async def agree(self, ctx:commands.Context):
        """
        Ungkapkan ekspresi setujumu!
        """
        get_request = await self.nekos_get('thumbsup')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx=ctx, url=gif_url, source=anime_name, action='Setuju')
    
    @roleplay.command(description='Elus kepala seseorang!')
    @app_commands.describe(user='Siapa yang ingin kamu elus kepalanya?')
    @app_commands.rename(user='pengguna')
    @check_blacklist()
    @has_voted()
    async def pat(self, ctx:commands.Context, *, user:discord.Member):
        """
        Tampar seseorang!
        """
        get_request = await self.nekos_get('slap')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx, user, gif_url, anime_name, 'Mengelus Kepala')
    
    @roleplay.command(description='Ungkapkan ekspresi kebosananmu!')
    @check_blacklist()
    @has_voted()
    async def agree(self, ctx:commands.Context):
        """
        Ungkapkan ekspresi kebosananmu!
        """
        get_request = await self.nekos_get('bored')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(ctx=ctx, url=gif_url, source=anime_name, action='Merasa Bosan')

async def setup(bot):
    await bot.add_cog(Roleplay(bot))