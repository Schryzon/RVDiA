"""
X-LV
Xtreme Log-out Vigilante
Used to detect RVDIA's status
WARNING: This is only a replica of what was written in replit.
         But feel free to configure it though.
"""

import discord
from os import getenv
from discord.ext import commands
# from keep_alive import keep_alive

# keep_alive()

xlv = commands.Bot(command_prefix="x-",
                   help_command=None,
                   intents=discord.Intents.all(),
                   activity=discord.Activity(type=discord.ActivityType.watching, name="RVDiA"))


@xlv.event
async def on_connect():
  print('XLV connected!')


@xlv.event
async def on_ready():
  await xlv.wait_until_ready()
  print('XLV is ready!')


@xlv.event
async def on_presence_update(before, after):
  if before.id == 957471338577166417 and after.id == 957471338577166417:
    channel = xlv.get_channel(883188578245562378)
    if str(before.status) == "idle" and str(after.status) == "offline" or str(after.status) == "invisible":
      await channel.send("<@877008612021661726>\n⚪ RVDIA is now **`OFFLINE`**!")

    elif str(before.status) == "offline" or str(before.status) == "invisible" and str(after.status) == "idle" or str(after.status) == 'online':
      await channel.send("<@877008612021661726>\n🟡 RVDIA is back **`ONLINE`**!")

  return


@xlv.event
async def on_message(message):
  return  # This bot doesn't need commands, just tell.


xlv.run(getenv('xlvtoken'))