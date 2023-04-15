"""
X-LV
Xtreme Log-out Vigilante
Used to detect RVDIA's status
"""

import discord
from os import getenv
from dotenv import load_dotenv
from RVDIA import rvdia
from discord.ext import commands
load_dotenv('./secrets.env')

xlv = commands.Bot(command_prefix="x-", help_command=None, intents=discord.Intents.all(), status=discord.Game('and monitoring RVDIA...'))

@xlv.event
async def on_connect():
    print('XLV connected!')

@xlv.event
async def on_ready():
    await xlv.wait_until_ready()
    print('XLV is ready!')

@xlv.event
async def on_presence_update(before, after):
    if before.id == rvdia.user.id and after.id == rvdia.user.id:
        channel = xlv.get_channel(883188578245562378)
        if before.status == "idle" and after.status == "offline" or after.status == "invisible":
            await channel.send(f"<@{xlv.owner_id}>\n⚪ RVDIA is now **`OFFLINE`**!")

        else:
            await channel.send(f"<@{xlv.owner_id}>\n🟡 RVDIA is back **`ONLINE`**!")
        
    return

@xlv.event
async def on_message(message):
    return # This bot doesn't need commands, just tell.

xlv.run(getenv('xlvtoken'))