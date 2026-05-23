"""
X-LV
Xtreme Log-out Vigilante
Used to detect RVDIA's status
"""

import discord
import random
import logging
import asyncio
import re
import aiohttp
from os import getenv
from dotenv import load_dotenv
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from datetime import datetime, timedelta
load_dotenv()

xlv = commands.Bot(command_prefix="x-",
                   help_command=None,
                   intents=discord.Intents.all(),
                   activity=discord.Activity(type=discord.ActivityType.watching, name="RVDiA"))




async def trigger_alert(url, reason):
    logging.warning(f"ALERT: {url} is down! Reason: {reason}")
    
    # NTFY Out-of-discord alert
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                "https://ntfy.sh/schryzon_3dex_alerts",
                data=f"🚨 3Dex Alert 🚨\n{url} is DOWN!\nReason: {reason}".encode('utf-8')
            )
    except:
        pass
        
    # Discord alert
    try:
        channel = xlv.get_channel(int(getenv("statuschannel")))
        if channel:
            await channel.send(f"<@{getenv('schryzonid')}>\n🚨 **URGENT**: `{url}` is down!\n**Reason:** {reason}")
    except:
        pass

@tasks.loop(minutes=5)
async def monitor_websites():
    targets = [
        "https://3dex.studio",
        "https://api.3dex.studio",
        "https://storage.3dex.studio",
        "https://rvdia.up.railway.app" # REPLACE THIS with actual RVDIA domain if different
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in targets:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        await trigger_alert(url, f"HTTP {resp.status}")
            except Exception as e:
                # Optimistic error handling: if it dies, just alert
                await trigger_alert(url, str(e))

@xlv.event
async def on_ready():
  await xlv.wait_until_ready()
  logging.info('XLV is ready!')
  if not monitor_websites.is_running():
      monitor_websites.start()

@xlv.event
async def on_presence_update(before, after):
  if before.id == int(getenv("rvdiaid")) and after.id == int(getenv("rvdiaid")):
    channel = xlv.get_channel(int(getenv("statuschannel")))
    if str(after.status) == "offline" or str(after.status) == "invisible":
      await channel.send(f"<@{getenv('schryzonid')}>\n⚪ RVDIA is now **`OFFLINE`**!")

@xlv.event
async def on_message(message):
    await xlv.process_commands(message)

greetings = ["Hello there,", "Greetings,", "Welcome to CyroN,", "Why hello there,", "Thanks for joining,", "Heya hee ho,", 
    "Welcome,", "A new member joined,", "Yokoso,", "Hi~", "Konnichiwa,", "Heya,", "Helloooo~,"
    ]
ending = [". I hope you have a fantastic day at CyroN!", ". I sure hope you brought me some food... just kidding!",
    ". I hope you get along with the others!", ". Don't forget to read the rules, okay?", ". Enjoy your stay!",
    ". Don't cause any ruckus, alrighty?", ". I bet Xefnir is happy to see another member! :D", ". Please don't cause any trouble, sweetie.",
    ". I'm so glad you joined!", "? Sorry, I'm kind of sleepy right now but anyways, welcome."
    ]
left = ["Did they do something bad?", "Were you feeling uncomfortable? :(", "See you on the other side!",
    "I'll miss you...", "I hope the best for them.", "\n...", "One member lost.", "Goodbye!", "I'll never forget this day...",
    r"*Sobbing intensifies*", r"*Sigh*"
    ]

@xlv.event
async def on_member_join(user:discord.Member):
    if user.bot is True: return
    if user.guild.id == int(getenv("cyronguild")):
        channel = user.guild.get_channel(int(getenv("welcomechannel"))) #hello-bye
        await channel.send(f"{random.choice(greetings)} **`{user}`**{random.choice(ending)}")
    else: return

@xlv.event
async def on_member_remove(user:discord.Member):
    if user.bot is True: return
    if user.guild.id == int(getenv("cyronguild")):
        channel = user.guild.get_channel(int(getenv("welcomechannel")))
        await channel.send(f"**`{user}`** has left CyroN. {random.choice(left)}")
    else: return


xlv.run(token=str(getenv('xlvtoken')))