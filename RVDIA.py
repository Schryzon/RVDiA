"""
Schryzon/Jayananda (11)
G-Tech Re'sman Programming Division
RVDIA (Revolutionary Virtual Independent Discord Application)
Inspired by Haruna Sakurai from Ongeki!
"""

import asyncio
import discord
from time import time
import os
from dotenv import load_dotenv
import openai
from scripts.help_menu.help import Help
from discord.ext import commands, tasks
from random import choice as rand
from contextlib import suppress
from scripts.suburl import SurblChecker, DomainInexistentException
load_dotenv('./secrets.env') # Loads the .env file from python-dotenv pack

helper = Help(
  no_category = "Tak tergolongkan", 
  color = 0xff4df0,
  active_time = 60,
  image_url = os.getenv('bannerhelp'),
  index_title = "Kategori Command",
  timeout=20,
  case_insensitive = True
  )

intents = discord.Intents.all()
rvdia = commands.AutoShardedBot(
  command_prefix = ["r-","R-","rvd ", "RVD ", "Rvd "], case_insensitive = True, strip_after_prefix = False, 
  intents=intents, help_command=helper
)
rvdia.synced = False
rvdia.__version__ = "アルファ [Alpha] v3"
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
      await rvdia.tree.sync()
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
  all_status=['in my room', 'in G-Tech Server', 'my code', 'trance music', 'r-help', 'G-Tech members',
                  'Ephotech Competition', user_count_status, 'maimai DX', 'with Jay', 'github.com/Schryzon/rvdia'
                ]
  status = rand(all_status)
  # Just count, I'm trying to save space!
  if status == all_status[2] or status == all_status[5] or status == user_count_status:
    type = discord.Activity(type=discord.ActivityType.watching, name=status)
  elif status == all_status[3]:
    type = discord.Activity(type=discord.ActivityType.listening, name=status)
  elif status == all_status[6]:
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

# Temporary Spy Command
@rvdia.command(hidden = True)
@commands.is_owner()
async def serverlist(ctx):
    await ctx.send('\n'.join(guild.name for guild in rvdia.guilds))
    with suppress(discord.Forbidden):
       list = []
       for guild in rvdia.guilds:
          invites = await guild.invites()
          url = [invite.url for invite in invites]
          list.append(url)
       await ctx.send('\n'.join(url))

@rvdia.command(hidden=True)
@commands.is_owner()
async def restart(ctx:commands.Context): # In case for timeout
   message = await ctx.send('Restarting...')
   await rvdia.close()
   await asyncio.sleep(2)
   await rvdia.start(token=os.getenv('token'))
   await message.edit(content='✅ Restart complete!')

@rvdia.command(hidden=True)
@commands.is_owner()
async def status(ctx:commands.Context, *, status):
   change_status.cancel()
   await rvdia.change_presence(status = discord.Status.idle, activity=discord.Game(status))
   await ctx.reply('Changed my status!')

@rvdia.event
async def on_message(msg:discord.Message):
    if not msg.guild:
        return
    await rvdia.process_commands(msg)
    if msg.author.bot == True:
        return
    if msg.content == "RVDIA":
        await msg.reply(f"Haii, {msg.author.name}! Silahkan tambahkan prefix `r-` atau `/` untuk menggunakan command!")

    # Chat command, I wanna make something cool here
    if msg.content.lower().startswith('rvdia, ') and msg.content.endswith('?') or msg.content.endswith('!'):
        try:
          async with msg.channel.typing():
            openai.api_key = os.getenv('openaikey')
            message = msg.content.lower().lstrip('rvdia,')
            result = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                temperature=1.2,
                messages=[
                {"role":'system', 'content':os.getenv('rolesys')},
                {"role": "user", "content": message}
                ]
            )
            embed = discord.Embed(
              title=' '.join((word.title() if not word.isupper() else word for word in message.split(' '))), 
              color=msg.author.color, 
              timestamp=msg.created_at
              )
            embed.description = result['choices'][0]['message']['content']
          await msg.channel.send(embed=embed)
          return
        
        except Exception as e:
           await msg.channel.send('Ada yang bermasalah dengan fitur ini, aku sudah mengirimkan laporan ke developer!')
           channel = rvdia.get_channel(906123251997089792)
           await channel.send(f'`{e}` Untuk Chat-GPT feature!')
           print(e)
    
    # Took me 2 hours to figure this out.
    if msg.content.startswith("http://") or msg.content.startswith("https://") or msg.content.startswith('www.'):
      checker = SurblChecker()
      with suppress(DomainInexistentException):
        check = checker.is_spam(msg.content)
        if check is True:
          await msg.delete()
          await msg.channel.send(f'{msg.author.mention} Spam website terdeteksi. Apabila ini sebuah kesalahan, mohon beri tahu pembuat bot.')

rvdia.run(token=os.getenv('token'))