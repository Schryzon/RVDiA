import discord
from discord.ext import commands
from os import getenv

# Commands only for special occasions
class Specials(commands.Cog):
    def __init__(self, bot) -> None:
        super().__init__()
        self.bot = bot

async def setup(bot:commands.Bot):
    await bot.add_cog(Specials(bot))