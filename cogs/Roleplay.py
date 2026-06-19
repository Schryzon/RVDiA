"""
Just a damn filler
All commands require you to vote
"""

import discord
from aiohttp import ClientSession
from discord import app_commands
from discord.ext import commands
from scripts.main import db, has_voted, check_blacklist
from scripts.utils.i18n import i18n

class Roleplay(commands.GroupCog, group_name = 'roleplay'):
    """
    User interaction commands (hug, kiss, slap, etc.).
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
            action_key:str,
            user:discord.Member = None, 
            ):
        await interaction.response.defer()
        user_settings = await db.usersettings.find_unique(where={'userId': interaction.user.id})
        lang = user_settings.lang if user_settings else "en"
        action = i18n.get(lang, action_key)
        
        if not user:
            embed = discord.Embed(title=f'{interaction.user.display_name} {action}!', color=interaction.user.color)
        else:
            embed = discord.Embed(title=f'{interaction.user.display_name} {action} {user.display_name}!', color=interaction.user.color)
        embed.set_image(url=url)
        embed.set_footer(text=f'Source: {source}')
        await interaction.followup.send(embed=embed)

    @app_commands.command(description='Hug someone!')
    @app_commands.describe(user='Who do you want to hug?')
    @has_voted()
    @check_blacklist()
    async def hug(self, interaction:discord.Interaction, *, user:discord.Member):
        """
        Hug someone!
        """
        get_request = await self.nekos_get('hug')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_hug', user)
    
    @app_commands.command(description='Kiss someone!')
    @app_commands.describe(user='Who do you want to kiss?')
    @has_voted()
    @check_blacklist()
    async def kiss(self, interaction:discord.Interaction, *, user:discord.Member):
        """
        Kiss someone!
        """
        get_request = await self.nekos_get('kiss')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_kiss', user)
    
    @app_commands.command(description='Slap someone!')
    @app_commands.describe(user='Who do you want to slap?')
    @has_voted()
    @check_blacklist()
    async def slap(self, interaction:discord.Interaction, *, user:discord.Member):
        """
        Slap someone!
        """
        get_request = await self.nekos_get('slap')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_slap', user)
    
    @app_commands.command(description='Express your laughter!')
    @has_voted()
    @check_blacklist()
    async def laugh(self, interaction:discord.Interaction):
        """
        Express your laughter!
        """
        get_request = await self.nekos_get('laugh')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_laugh')
    
    @app_commands.command(description='Express your happiness!')
    @has_voted()
    @check_blacklist()
    async def happy(self, interaction:discord.Interaction):
        """
        Express your happiness!
        """
        get_request = await self.nekos_get('happy')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_happy')
    
    @app_commands.command(description='Express your thinking!')
    @has_voted()
    @check_blacklist()
    async def think(self, interaction:discord.Interaction):
        """
        Express your thinking!
        """
        get_request = await self.nekos_get('think')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_think')
    
    @app_commands.command(description='Express your blushing!')
    @has_voted()
    @check_blacklist()
    async def blush(self, interaction:discord.Interaction):
        """
        Express your blushing!
        """
        get_request = await self.nekos_get('blush')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_blush')
    
    @app_commands.command(description='Express your sadness!')
    @has_voted()
    @check_blacklist()
    async def cry(self, interaction:discord.Interaction):
        """
        Express your sadness!
        """
        get_request = await self.nekos_get('cry')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_cry')

    @app_commands.command(description='Express your agreement!')
    @has_voted()
    @check_blacklist()
    async def agree(self, interaction:discord.Interaction):
        """
        Express your agreement!
        """
        get_request = await self.nekos_get('thumbsup')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_agree')
    
    @app_commands.command(description='Pat someone on the head!')
    @app_commands.describe(user='Who do you want to pat?')
    @has_voted()
    @check_blacklist()
    async def pat(self, interaction:discord.Interaction, *, user:discord.Member):
        """
        Pat someone on the head!
        """
        get_request = await self.nekos_get('pat')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_pat', user)
    
    @app_commands.command(description='Express your boredom!')
    @has_voted()
    @check_blacklist()
    async def bored(self, interaction:discord.Interaction):
        """
        Express your boredom!
        """
        get_request = await self.nekos_get('bored')
        gif_url = get_request[0]
        anime_name = get_request[1]
        return await self.create_embed_and_sendGIF(interaction, gif_url, anime_name, 'roleplay.action_bored')

async def setup(bot):
    await bot.add_cog(Roleplay(bot))