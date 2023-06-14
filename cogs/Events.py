import discord
import random
from discord.ext import commands
from datetime import datetime
from scripts.main import connectdb

class Events(commands.Cog):
    """
    Events handler, duh.
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild:discord.Guild):
        channel = self.bot.get_channel(1094157780606267502) #join-logs
        embed = discord.Embed(title='Joined a new Server!', color=0x03ac13, timestamp=datetime.now())
        embed.add_field(name='Name', value=guild.name, inline=False)
        embed.add_field(name='Members', value=guild.member_count, inline=False)
        embed.add_field(name='ID', value=guild.id, inline=False)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild:discord.Guild):
        channel = self.bot.get_channel(1094157780606267502) #join-logs
        embed = discord.Embed(title='Left a Server!', color=0xff0000, timestamp=datetime.now())
        embed.add_field(name='Name', value=guild.name, inline=False)
        embed.add_field(name='Members', value=guild.member_count, inline=False)
        embed.add_field(name='ID', value=guild.id, inline=False)
        await channel.send(embed=embed)
        database = connectdb('Prefixes')
        try:
            database.find_one_and_delete({'_id': guild.id})
        except:
            return

    
async def setup(bot):
    await bot.add_cog(Events(bot))