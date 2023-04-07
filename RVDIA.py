"""
Schryzon/Jayananda (11)
G-Tech Re'sman Programming Division
RVDIA (Revolutionary Virtual Independent Discord Application)
Inspired by Haruna Sakurai from Ongeki!
"""

import asyncio
import discord
import os
import openai
import topgg
from time import time
from dotenv import load_dotenv
from pkgutil import iter_modules
from scripts.help_menu.help import Help
from discord.ext import commands, tasks
from random import choice as rand
from contextlib import suppress
from scripts.suburl import SurblChecker, DomainInexistentException
from scripts.main import connectdb, titlecase
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

def get_prefix(client, message):
  """
  Gain prefix from database
  """
  try:
    s = connectdb('Prefixes')
    f = s.find_one({'_id': message.guild.id})
    if f is None:
      s.insert_one(({'_id':message.guild.id, 'prefix':['R-', 'r-', 'rvd ', 'Rvd ', 'RVD ']}))
      new = s.find_one({'_id': message.guild.id})
      return new['prefix']
    else:
      return f['prefix']
  except:
    return ['R-', 'r-', 'rvd ', 'Rvd ', 'RVD ']

def when_mentioned_or_function(func):
    """
    Add @RVDIA as a prefix, along with the obtained prefixes from DB.
    """
    def inner(bot, message):
        r = func(bot, message)
        if isinstance(r, str):
           r = [r]
        r = commands.when_mentioned(bot, message) + r
        return r
    return inner

intents = discord.Intents.all() # Might change my mind in the near future.
rvdia = commands.AutoShardedBot(
  command_prefix = when_mentioned_or_function(get_prefix), case_insensitive = True, strip_after_prefix = False, 
  intents=intents, help_command=helper
)
rvdia.topgg = topgg.DBLClient(rvdia, os.getenv('topggtoken'))
rvdia.synced = False
rvdia.__version__ = "ベタ [Beta] v2"
rvdia.event_mode = False
rvdia.runtime = time() # UNIX float

cogs_list = [cogs.name for cogs in iter_modules(['cogs'], prefix='cogs.')] # iter_modules() for easier task

@rvdia.event
async def on_connect():
    print("RVDIA has connected.")

@rvdia.event
async def on_ready():
    await rvdia.wait_until_ready() # So I "don't" get rate limited
    for cog in cogs_list:
      if not cog == 'cogs.__init__':
          await rvdia.load_extension(cog)
    print('Internal cogs loaded!')
    
    if not rvdia.synced:
      await rvdia.tree.sync() # Global sync
      rvdia.synced = True
      print('Slash Commands up for syncing!')

    if not change_status.is_running():
      change_status.start()
      print('Change status starting!')

    update_guild_stats.start()

    print("RVDIA is ready.")

@tasks.loop(minutes=1)
async def change_status():
  """
  Looping status, rate = 1 minute
  """
  is_event = 'Event mode ON!' if rvdia.event_mode == True else 'Standard mode'
  users = 0
  for guilds in rvdia.guilds:
    users += guilds.member_count -1
  user_count_status = f'{users} users'
  all_status=['in my room', 'in G-Tech Server', 'someone doing ABFB!', 'my music ❤️', 'r-help', 'G-Tech members',
                  'Ephotech Competition', user_count_status, 'with Schryzon', f'{rvdia.__version__}',
                  '/help', 'What should I do today?', 'Add me!', is_event, 'Ongeki!bright Memory', '~♪'
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

@tasks.loop(minutes=20)
async def update_guild_stats():
    """Update Top.gg server count every 20 minutes."""
    try:
        await rvdia.topgg.post_guild_count()
        print(f"Posted server count ({rvdia.topgg.guild_count})")
    except Exception as e:
        print(f"Failed to post server count\n{e.__class__.__name__}: {e}")

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
    embed = discord.Embed(title = "RVDIA Cog List", description = "\n".join(cogs_list), color = ctx.author.colour)
    embed.set_thumbnail(url = rvdia.user.avatar)
    embed.set_footer(text = "Cogs were taken from \".RVDIA/cogs\"")
    await ctx.send(embed=embed)

@rvdia.command(hidden=True)
@commands.is_owner()
async def refresh(ctx):
  """
  In case something went horribly wrong
  """
  with suppress(commands.ExtensionNotLoaded):
    for cog in cogs_list:
      if not cog == 'cogs.__init__':
          await rvdia.unload_extension(cog)
          await rvdia.load_extension(cog)
  await ctx.reply('Cogs refreshed.')

# This allows me to decide when to bail out of a server when it reaches 100 servers
@rvdia.command(hidden = True)
@commands.is_owner()
async def serverlist(ctx):
    with suppress(discord.Forbidden):
       guild_name = [guild.name for guild in rvdia.guilds]
       guild_members = [guild.member_count for guild in rvdia.guilds]
       guild_id = [guild.id for guild in rvdia.guilds]
       list = []
       for name, member, gid in zip(guild_name, guild_members, guild_id):
          list.append(f"`{name}` | `{member}` members | ID: `{gid}`")
       await ctx.send("\n".join(list))

@rvdia.command(hidden = True)
@commands.is_owner()
async def leave(ctx:commands.Context, guild_id:discord.Guild):
   await guild_id.leave()
   await ctx.send(f'Left `{guild_id.name}` that has `{guild_id.member_count}` members!')

@rvdia.command(hidden=True)
@commands.is_owner()
async def restart(ctx:commands.Context): # In case for timeout
   await ctx.send('Restarting...')
   print('!!RESTART DETECTED!!')
   await rvdia.close()
   await asyncio.sleep(2)
   rvdia.run(token=os.getenv('token'))
   await ctx.channel.send('RVDIA has restarted!')

@rvdia.command(hidden=True)
@commands.is_owner()
async def status(ctx:commands.Context, *, status):
   if status.lower() == 'restart' or status.lower() == 'reset':
      if not change_status.is_running:
         return change_status.start()
   change_status.cancel()
   await rvdia.change_presence(status = discord.Status.idle, activity=discord.Game(status))
   await ctx.reply('Changed my status!')

@rvdia.command(hidden=True)
@commands.is_owner()
async def blacklist(ctx:commands.Context, user:discord.User, *, reason:str=None):
   match user.id:
      case rvdia.owner_id:
         return await ctx.reply('Tidak bisa blacklist owner!')
      case rvdia.user.id:
         return await ctx.reply('Tidak bisa blacklist diriku sendiri!')
      case _:
         pass
      
   blacklisted = connectdb('Blacklist')
   check_blacklist = blacklisted.find_one({'_id':user.id})
   if not check_blacklist:
      blacklisted.insert_one({'_id':user.id, 'reason':reason})
      embed = discord.Embed(title='‼️ BLACKLISTED ‼️', timestamp=ctx.message.created_at, color=0xff0000)
      embed.description = f'**`{user}`** telah diblacklist dari menggunakan RVDIA!'
      embed.set_thumbnail(url=user.avatar.url if not user.avatar is None else os.getenv('normalpfp'))
      embed.add_field(name='Alasan:', value=reason, inline=False)
      return await ctx.reply(embed=embed)
   
   await ctx.reply(f'`{user}` telah diblacklist!')

@rvdia.command(hidden=True)
@commands.is_owner()
async def whitelist(ctx:commands.Context, user:discord.User):
   blacklisted = connectdb('Blacklist')
   check_blacklist = blacklisted.find_one({'_id':user.id})
   if not check_blacklist:
      return await ctx.reply(f'**`{user}`** tidak diblacklist dari menggunakan RVDIA!')
   
   blacklisted.find_one_and_delete({'_id':user.id})
   await ctx.reply(f'`{user}` telah diwhitelist!')


sentence_enders = ['!', '?', '.']

@rvdia.event
async def on_message(msg:discord.Message):
    if not msg.guild:
        return
    
    await rvdia.process_commands(msg)

    if msg.author.bot == True:
        return
    
    if msg.content == "RVDIA":
        await msg.reply(f"Haii, {msg.author.name}! Silahkan tambahkan prefix-ku untuk menggunakan command!")

    # Chat command, I wanna make something cool here
    if msg.content.lower().startswith('rvdia, ') and any(msg.content.endswith(suffix) for suffix in sentence_enders):
        try:
          async with msg.channel.typing():
            openai.api_key = os.getenv('openaikey')
            message = msg.content.lower().lstrip('rvdia,')
            if len(message) > 256:
               return await msg.channel.send('Pesanmu terlalu panjang untuk aku cerna, aku hanya bisa membaca maksimal 256 huruf dari pesanmu!')
            result = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                temperature=1.2,
                messages=[
                {"role":'system', 'content':os.getenv('rolesys')},
                {"role":'assistant', 'content':f"You are currently talking to {msg.author}"}, # Doesn't really work
                {"role": "user", "content": message}
                ]
            )
            embed = discord.Embed(
              title=' '.join((titlecase(word) for word in message.split(' '))), 
              color=msg.author.color, 
              timestamp=msg.created_at
              )
            embed.description = result['choices'][0]['message']['content']
            embed.set_author(name=msg.author)
            embed.set_footer(text='Jika ada yang ingin ditanyakan, bisa langsung direply!')
          await msg.channel.send(embed=embed)
          return
        
        except Exception as e:
           if "That model is currently overloaded with other requests." in str(e):
              return await msg.channel.send('Maaf, fitur ini sedang dalam gangguan. Mohon dicoba nanti!')
           await msg.channel.send('Ada yang bermasalah dengan fitur ini, aku sudah mengirimkan laporan ke developer!')
           channel = rvdia.get_channel(906123251997089792)
           await channel.send(f'`{e}` Untuk fitur GPT-3.5 Turbo!')
           print(e)

    if msg.reference:
        try:
          fetched_message = await msg.channel.fetch_message(msg.reference.message_id)
          match fetched_message.author.id:
              case rvdia.user.id:
                  pass
              case _:
                  return
          
          if fetched_message.embeds and fetched_message.embeds[0] and fetched_message.embeds[0].footer:
              message_embed = fetched_message.embeds[0]
          else:
              return
          
          if message_embed.footer.text == 'Jika ada yang ingin ditanyakan, bisa langsung direply!':
              pass
          else:
              return
          
          async with msg.channel.typing():
            embed_desc = message_embed.description
            embed_title = message_embed.title
            author = message_embed.author.name
            openai.api_key = os.getenv('openaikey')
            message = msg.content
            if len(message) > 256:
               return await msg.channel.send('Pesanmu terlalu panjang untuk aku cerna, aku hanya bisa membaca maksimal 256 huruf dari pesanmu!')
            result = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                temperature=1.2,
                messages=[
                {"role":'system', 'content':os.getenv('rolesys')},
                {"role":"assistant", 'content':f'{author} said: {embed_title} | Your response was: {embed_desc} | The user replying is {msg.author}'},
                {"role": "user", "content": message}
                ]
            )
            embed = discord.Embed(
              title=' '.join((titlecase(word) for word in message.split(' '))), 
              color=msg.author.color, 
              timestamp=msg.created_at
              )
            embed.description = result['choices'][0]['message']['content']
            embed.set_author(name=msg.author)
            embed.set_footer(text='Jika ada yang ingin ditanyakan, bisa langsung direply!')
          await msg.channel.send(embed=embed)
          return
        
        except Exception as e:
           if "That model is currently overloaded with other requests." in str(e):
              return await msg.channel.send('Maaf, fitur ini sedang dalam gangguan. Mohon dicoba nanti!')
           await msg.channel.send('Ada yang bermasalah dengan fitur ini, aku sudah mengirimkan laporan ke developer!')
           channel = rvdia.get_channel(906123251997089792)
           await channel.send(f'`{e}` Untuk fitur balasan GPT-3.5 Turbo!')
           print(e)

    # Took me 2 hours to figure this out.
    website_prefixes = ['http://', 'https://', 'www.']
    if any(msg.content.startswith(prefix) for prefix in website_prefixes):
      checker = SurblChecker()
      with suppress(DomainInexistentException):
        check = checker.is_spam(msg.content)
        if check is True:
          try:
            await msg.delete()
            await msg.channel.send(f'{msg.author.mention} Spam website terdeteksi. Apabila ini sebuah kesalahan, mohon beri tahu pembuat bot.')

          except discord.Forbidden:
             return

rvdia.run(token=os.getenv('token'))