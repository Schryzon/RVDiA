"""
Just a damn filler
All commands require you to vote
"""

import discord
from aiohttp import ClientSession
from discord import app_commands
from discord.ext import commands
from scripts.main import has_voted, check_blacklist

class Roleplay(commands.GroupCog, group_name = 'roleplay'):
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
            interaction:discord.Interaction, 
            url:str,
            source:str,
            action:str,
            user:discord.Member = None, 
            ):
        """
        Lazy me lol
        """
        await interaction.response.defer()
        if not user:
            embed = discord.Embed(title=f'{interaction.user.display_name} {action}!', color=interaction.user.color)
        else:
            embed = discord.Embed(title=f'{interaction.user.display_name} {action} {user.display_name}!', color=interaction.user.color)
        embed.set_image(url=url)
        embed.set_footer(text=f'Source: {source}')
        await interaction.followup.send(embed=embed)

    @app_commands.command(description='Peluk seseorang!')
    @app_commands.describe(user='Siapa yang ingin kamu peluk?')
    @app_commands.rename(user='pengguna')
    @has_voted()
    @check_blacklist()
    async def hug(self, interaction:discord.Interaction, *, user:discord.Member):
        """
        Peluk seseorang!
        """
        get_request = await self.nekos_get('hug')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Memeluk', user)
    
    @app_commands.command(description='Cium seseorang!')
    @app_commands.describe(user='Siapa yang ingin kamu cium?')
    @app_commands.rename(user='pengguna')
    @has_voted()
    @check_blacklist()
    async def kiss(self, interaction:discord.Interaction, *, user:discord.Member):
        """
        Cium seseorang!
        """
        get_request = await self.nekos_get('kiss')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Mencium', user)
    
    @app_commands.command(description='Tampar seseorang!')
    @app_commands.describe(user='Siapa yang ingin kamu tampar?')
    @app_commands.rename(user='pengguna')
    @has_voted()
    @check_blacklist()
    async def slap(self, interaction:discord.Interaction, *, user:discord.Member):
        """
        Tampar seseorang!
        """
        get_request = await self.nekos_get('slap')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Menampar', user)
    
    @app_commands.command(description='Ungkapkan ekspresi tertawamu!')
    @has_voted()
    @check_blacklist()
    async def laugh(self, interaction:discord.Interaction):
        """
        Ungkapkan ekspresi tertawamu!
        """
        get_request = await self.nekos_get('laugh')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Tertawa')
    
    @app_commands.command(description='Ungkapkan ekspresi bahagiamu!')
    @has_voted()
    @check_blacklist()
    async def happy(self, interaction:discord.Interaction):
        """
        Ungkapkan ekspresi bahagiamu!
        """
        get_request = await self.nekos_get('happy')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Merasa Bahagia')
    
    @app_commands.command(description='Ungkapkan ekspresi berpikirmu!')
    @has_voted()
    @check_blacklist()
    async def think(self, interaction:discord.Interaction):
        """
        Ungkapkan ekspresi berpikirmu!
        """
        get_request = await self.nekos_get('think')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Sedang Berpikir')
    
    @app_commands.command(description='Ungkapkan ekspresi malumu!')
    @has_voted()
    @check_blacklist()
    async def blush(self, interaction:discord.Interaction):
        """
        Ungkapkan ekspresi malumu!
        """
        get_request = await self.nekos_get('blush')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Merasa Malu')
    
    @app_commands.command(description='Ungkapkan ekspresi sedihmu!')
    @has_voted()
    @check_blacklist()
    async def cry(self, interaction:discord.Interaction):
        """
        Ungkapkan ekspresi sedihmu!
        """
        get_request = await self.nekos_get('cry')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Menangis')

    @app_commands.command(description='Ungkapkan ekspresi setujumu!')
    @has_voted()
    @check_blacklist()
    async def agree(self, interaction:discord.Interaction):
        """
        Ungkapkan ekspresi setujumu!
        """
        get_request = await self.nekos_get('thumbsup')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Setuju')
    
    @app_commands.command(description='Elus kepala seseorang!')
    @app_commands.describe(user='Siapa yang ingin kamu elus kepalanya?')
    @app_commands.rename(user='pengguna')
    @has_voted()
    @check_blacklist()
    async def pat(self, interaction:discord.Interaction, *, user:discord.Member):
        """
        Tampar seseorang!
        """
        get_request = await self.nekos_get('slap')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Mengelus Kepala', user)
    
    @app_commands.command(description='Ungkapkan ekspresi kebosananmu!')
    @has_voted()
    @check_blacklist()
    async def bored(self, interaction:discord.Interaction):
        """
        Ungkapkan ekspresi kebosananmu!
        """
        get_request = await self.nekos_get('bored')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'Merasa Bosan')

async def setup(bot):
    await bot.add_cog(Roleplay(bot))