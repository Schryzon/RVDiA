"""
Exclusive commands
For Re:Volution ~ The Dream World
"""

import discord
import asyncio
from discord.ext import commands
from discord.ui import View, Button
from scripts.main import connectdb, check_blacklist

class Guild(commands.Cog):
    """
    Command khusus untuk fitur guild Re:Volution.
    """
    def __init__(self, bot:commands.AutoShardedBot):
        self.bot = bot
    
    @commands.hybrid_group(name="guild")
    @check_blacklist()
    async def guild(self, ctx:commands.Context) -> None:
        return
    
    

async def setup(bot):
    await bot.add_cog(Guild(bot))