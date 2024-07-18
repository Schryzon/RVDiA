"""
X-LV
Xtreme Log-out Vigilante
Used to detect RVDIA's status
"""

import discord
import random
import logging
from os import getenv
from dotenv import load_dotenv
from discord.ext import commands
load_dotenv('./secrets.env')

xlv = commands.Bot(command_prefix="x-",
                   help_command=None,
                   intents=discord.Intents.all(),
                   activity=discord.Activity(type=discord.ActivityType.watching, name="RVDiA"))


@xlv.event
async def on_connect():
  logging.info('XLV connected!')


@xlv.event
async def on_ready():
  await xlv.wait_until_ready()
  logging.info('XLV is ready!')


@xlv.event
async def on_presence_update(before, after):
  if before.id == int(getenv("rvdiaid")) and after.id == int(getenv("rvdiaid")):
    channel = xlv.get_channel(int(getenv("statuschannel")))
    if str(after.status) == "offline" or str(after.status) == "invisible":
      await channel.send(f"<@{getenv('schryzonid')}>\n⚪ RVDIA is now **`OFFLINE`**!")

  return


@xlv.event
async def on_message(message):
  return  # This bot doesn't need commands, just tell.

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
    "\*Sobbing intensifies\*", "\*Sigh\*"
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