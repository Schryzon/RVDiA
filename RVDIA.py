import discord
from time import time
import os
from dotenv import load_dotenv
from pretty_help import PrettyHelp
from discord.ext import commands, tasks
from random import choice as rand
from contextlib import suppress
from scripts.suburl import SurblChecker, DomainInexistentException
load_dotenv('./secrets.env') # Loads the .env file from python-dotenv pack

helper = PrettyHelp(
  no_category = "Tak tergolongkan", 
  color = 0xff4df0,
  active_time = 60,
  ending_note = "Untuk info lebih lanjut mengenai sebuah command,\nr-help (command/kategori)",
  image_url = os.getenv('bannerhelp'),
  index_title = "Kategori Command"
  )

intents = discord.Intents.all()
rvdia = commands.AutoShardedBot(
  command_prefix = ["r-","R-","rvd ", "RVD ", "Rvd "], case_insensitive = True, strip_after_prefix = False, 
  intents=intents, help_command=helper
)
rvdia.synced = False
rvdia.__version__ = "In-Development Stage 2"
rvdia.runtime = time()

@rvdia.event
async def on_connect():
    print("RVDIA has connected.")

@rvdia.event
async def on_ready():
    await rvdia.wait_until_ready()
    for cog in os.listdir("./cogs"):
      if cog.endswith(".py") and not cog == "__init__.py":
          await rvdia.load_extension(f"cogs.{cog[:-3]}")
    print('Internal cogs loaded!')
    
    if not rvdia.synced:
      await rvdia.tree.sync(guild = discord.Object(id=997500206511833128))
      rvdia.synced = True
      print('Slash Commands up for syncing!')

    if not change_status.is_running():
      change_status.start()
      print('Change status starting!')

    print("RVDIA is ready.")

@tasks.loop(minutes=1)
async def change_status():
  users = 0
  for guilds in rvdia.guilds:
    users += guilds.member_count -1
  user_count_status = f'{users} users'
  status = rand(['in my room', 'in G-Tech Server', 'my code', 'trance music', 'r- help', 'G-Tech members',
                  'Ephotech Competition', user_count_status, 'maimai DX'
                ])
  if status == "my code" or status == "G-Tech members" or status == user_count_status:
    type = discord.Activity(type=discord.ActivityType.watching, name=status)
  elif status == "trance music":
    type = discord.Activity(type=discord.ActivityType.listening, name=status)
  elif status == "Ephotech Competition":
    type = discord.Activity(name = status, type = 5)
  else:
    type = discord.Game(status)
  await rvdia.change_presence(status = discord.Status.idle, activity=type)

@rvdia.command(aliases = ['on', 'enable'], hidden=True)
@commands.is_owner()
async def load(ctx, ext):
  if ext == "__init__":
    await ctx.send(f"Stupid.")
    return
  try:
    rvdia.load_extension(f"cogs.{ext}")
    await ctx.send(f"Cog `{ext}.py` sekarang aktif!")
  except commands.ExtensionAlreadyLoaded:
    await ctx.send(f"Cog `{ext}.py` sudah diaktifkan!")
  except commands.ExtensionNotFound:
    await ctx.send(f"Cog `{ext}.py` tidak ditemukan!")

@rvdia.command(aliases = ['off', 'disable'], hidden=True)
@commands.is_owner()
async def unload(ctx, ext):
  if ext == "__init__":
    await ctx.send(f"Stupid.")
    return
  try:
    rvdia.unload_extension(f"cogs.{ext}")
    await ctx.send(f"Cog `{ext}.py` sekarang tidak aktif!")
  except commands.ExtensionNotFound:
    await ctx.send(f"Cog `{ext}.py` tidak ditemukan!")
  except commands.ExtensionNotLoaded:
    await ctx.send(f"Cog `{ext}.py` sudah dimatikan!")

@rvdia.command(hidden = True)
@commands.is_owner()
async def cogs(ctx):
    ls = []
    for cog in os.listdir("./cogs"):
        if cog.endswith(".py") and not cog == "__init__.py":
            ls.append(cog)
    embed = discord.Embed(title = "RVDIA Cog List", description = "\n".join(ls), color = ctx.author.colour)
    embed.set_thumbnail(url = rvdia.user.avatar)
    embed.set_footer(text = "Cogs were taken from \"Project RVDIA/cogs\"")
    await ctx.send(embed=embed)

@rvdia.command(hidden=True)
@commands.is_owner()
async def refresh(ctx):
  with suppress(commands.ExtensionNotLoaded):
    for cog in os.listdir("./cogs"):
      if cog.endswith(".py") and not cog == "__init__.py":
        rvdia.unload_extension(f"cogs.{cog[:-3]}")
        rvdia.load_extension(f"cogs.{cog[:-3]}")
  await ctx.reply('Cogs refreshed.')

@rvdia.event
async def on_message(msg):
    await rvdia.process_commands(msg)
    if msg.author.bot == True:
        return
    if not msg.guild:
        return
    if msg.content == "RVDIA":
        await msg.reply(f"Haii, {msg.author.name}! Silahkan tambahkan prefix `r-` atau `rvd` untuk menggunakan command!")
    
    # Took me 2 hours to figure this out.
    if msg.content.startswith("http://") or msg.content.startswith("https://") or msg.content.startswith('www.'):
      checker = SurblChecker()
      with suppress(DomainInexistentException):
        check = checker.is_spam(msg.content)
        if check is True:
          await msg.delete()
          await msg.channel.send(f'{msg.author.mention} Spam website terdeteksi. Apabila ini sebuah kesalahan, mohon beri tahu pembuat bot.')

rvdia.run(os.getenv('token'))