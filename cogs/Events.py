import discord
import logging
import aiohttp
from os import getenv
from discord.ext import commands, tasks
from datetime import datetime

class Events(commands.Cog):
    """
    Events handler, including server joins/leaves and Top.gg stats reporting.
    """
    def __init__(self, bot):
        self.bot = bot
        self.update_guild_status.start()

    def cog_unload(self):
        self.update_guild_status.cancel()

    @tasks.loop(hours=1)
    async def update_guild_status(self):
        """
        Sends data regarding shard and server count to Top.gg
        """
        try:
            token = getenv('topggtoken')
            if not token:
                logging.warning("No topggtoken found in environment variables.")
                return
            token = token.strip('"')
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            payload = {
                'data': [
                    {
                        'metrics': {
                            'server_count': len(self.bot.guilds),
                            'shard_count': self.bot.shard_count or 0
                        }
                    }
                ]
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post('https://top.gg/api/v1/projects/@me/metrics/batch', json=payload) as response:
                    if response.status == 204:
                        logging.info('Posted server updates to Top.gg!')
                    else:
                        resp_text = await response.text()
                        logging.error(f'Failed to post updates to Top.gg! Status: {response.status}, Response: {resp_text}')

        except Exception as error:
            logging.error(f'Error sending server count update!\n{error.__class__.__name__}: {error}')

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        channel = self.bot.get_channel(int(getenv("joinlogs"))) #join-logs
        embed = discord.Embed(title='Joined a new Server!', color=0x03ac13, timestamp=datetime.now())
        embed.add_field(name='Name', value=guild.name, inline=False)
        embed.add_field(name='Members', value=guild.member_count, inline=False)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        channel = self.bot.get_channel(int(getenv("joinlogs"))) #join-logs
        embed = discord.Embed(title='Left a Server!', color=0xff0000, timestamp=datetime.now())
        embed.add_field(name='Name', value=guild.name, inline=False)
        embed.add_field(name='Members', value=guild.member_count, inline=False)
        await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Events(bot))