"""
Schryzon (Widiyasa Jayananda)
G-Tech Re'sman Programming Division
RVDiA (Revolutionary Virtual Discord Assistant)
Feel free to modify and do other stuff.
Contributions are welcome.
Licensed under the MIT LICENSE.
* Note: Now that RVDiA is verified, I own the rights to the name.
        Making public clones of her under the same name is a big no no, okay sweetie?
"""

import asyncio
import discord
import os
import aiohttp
import logging
from google import genai
from google.genai import types
import traceback
import pytz
from time import time
from dotenv import load_dotenv
from pkgutil import iter_modules
from scripts.help_menu.help import Help
from cogs.Conversation import Regenerate_Answer_Button
from discord.ext import commands, tasks
from random import choice as rand
from contextlib import suppress
from datetime import datetime
from scripts.main import titlecase, check_vote, db
from scripts.memory import memory_manager
from scripts.error_logger import format_error_report
load_dotenv() # Loads the .env file from python-dotenv pack

class RVDIA(commands.AutoShardedBot):
  """
  A subclass of commands.AutoShardedBot; RVDiA herself.
  This is in order to make her attributes easier to maintain.
  (Nah, I'm just lazy tbh.)
  """
  def __init__(self, **kwargs):
    self.synced = False
    self.__version__ = "Rebirth v2.0.0"
    self.event_mode = True
    self.color = 0x86273d
    self.runtime = time() # UNIX float
    self.coin_emoji = "<:rvdia_coin:1121004598962954300>"
    self.coin_emoji_anim = "<a:rvdia_coin_anim:1121004592033955860>"
    self.rvdia_emoji = '<:rvdia:1140812479883128862>'
    self.rvdia_emoji_happy = '<:rvdia_happy:1121412270220660803>'
    self.cyron_emoji = '<:cyron:1082789553263349851>' # Join up!!!

    super().__init__(
      command_prefix=commands.when_mentioned, 
      case_insensitive=True, 
      strip_after_prefix=False, 
      intents=discord.Intents.default(), # Finally got to this stage.

      help_command=Help(
            no_category = "Tak tergolongkan", 
            color = self.color,
            active_time = 60,
            image_url = os.getenv('bannerhelp') if not self.event_mode else os.getenv('bannerevent'),
            index_title = "Kategori Command",
            timeout=20,
            case_insensitive = True
        ),
      **kwargs
    )

  async def setup_hook(self):
    from scripts.main import db
    from scripts.web_server import start_web_server
    await db.connect()
    logging.info("Prisma Database connected.")
    
    # Start the Web Server
    self.loop.create_task(start_web_server(self))
    logging.info("Web Server task created.")



rvdia = RVDIA() # Must create instance

cogs_list = [cogs.name for cogs in iter_modules(['cogs'], prefix='cogs.')] # iter_modules() for easier task

@rvdia.event
async def on_connect():
    logging.info("RVDiA has connected.")

@rvdia.event
async def on_ready():
    """
    Detect when RVDiA is ready (not connected to Discord).
    """
    await rvdia.wait_until_ready() # So I "don't" get rate limited
    
    # Dynamically find cogs to pick up new files
    current_cogs = [c.name for c in iter_modules(['cogs'], prefix='cogs.')]
    for cog in current_cogs:
      if not cog == 'cogs.__init__':
          try:
              await rvdia.load_extension(cog)
          except commands.ExtensionAlreadyLoaded:
              pass
          except Exception as e:
              logging.error(f"Could not load cog {cog}: {e}")
    logging.info('Internal cogs loaded!')
    
    if not rvdia.synced:
      synced_commands = await rvdia.tree.sync() # Global slash commands sync, also returns a list of commands.
      await asyncio.sleep(1.5) # Avoid rate limit
      await rvdia.tree.sync(guild=discord.Object(int(os.getenv("gtechguild")))) # Wonder if it fixes with this??
      rvdia.synced = [True, len(synced_commands)]
      logging.info('Slash Commands synced to global!')

    if not change_status.is_running():
      change_status.start()
      logging.info('change_status() starting!')

    update_guild_status.start()

    logging.info("RVDiA is ready.")


@tasks.loop(minutes=7)
async def change_status():
  """
  Looping status, rate = 7 minute
  """
  is_event = 'Event mode ON!' if rvdia.event_mode == True else 'Standard mode'
  users = 0
  for guilds in rvdia.guilds:
    users += guilds.member_count -1
  user_count_status = f'{users} users'
  all_status=['in my room', 'in G-Tech Server', '"How to be cute"', 'you', 'G-Tech members',
                  'Ephotech 2024', user_count_status, f'{rvdia.__version__}',
                  '/help', 'in my dream world', 'Add me!', is_event, '~♪',
                  'Re:Volution', 'Now on WhatsApp!'
                ]
  status = rand(all_status)
  # Just count, I'm trying to save space!
  if status == all_status[2] or status == all_status[4] or status == user_count_status:
    type = discord.Activity(type=discord.ActivityType.watching, name=status)
  elif status == all_status[3]:
    type = discord.Activity(type=discord.ActivityType.listening, name=status)
  elif status == all_status[6]:
    type = discord.Activity(name = status, type = 5)
  else:
    type = discord.Game(status)
  await rvdia.change_presence(status = discord.Status.idle, activity=type)


@tasks.loop(hours=1)
async def update_guild_status():
    """
    Sends data regarding shard and server count to Top.gg
    """
    try:
      headers = {'Authorization': os.getenv('topggtoken')}
      async with aiohttp.ClientSession(headers=headers) as session:
          await session.post(f'https://top.gg/api/bots/{rvdia.user.id}/stats', data={
              'server_count':len(rvdia.guilds),
              'shard_count':rvdia.shard_count
          })
          logging.info(f'Posted server updates to Top.gg!')

    except Exception as error:
       logging.error(f'Error sending server count update!\n{error.__class__.__name__}: {error}')


@rvdia.command(aliases = ['on', 'enable'], hidden=True)
@commands.is_owner()
async def load(ctx, ext):
  """
  Manually load cogs
  """
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
  """
  Manually unload cogs
  """
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

@rvdia.command(hidden=True)
@commands.is_owner()
async def sync(ctx):
    """
    Sync slash commands
    """
    synced = await rvdia.tree.sync()
    await ctx.send(f"Synced {len(synced)} commands.")

@rvdia.command(hidden = True)
@commands.is_owner()
async def cogs(ctx):
    """
    Cogs list
    """
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
  dynamic_cogs = [c.name for c in iter_modules(['cogs'], prefix='cogs.')]
  results = []
  for cog in dynamic_cogs:
    if not cog == 'cogs.__init__':
        try:
            with suppress(commands.ExtensionNotLoaded):
                await rvdia.unload_extension(cog)
            await rvdia.load_extension(cog)
            results.append(f"✅ `{cog}`")
        except Exception as e:
            results.append(f"❌ `{cog}`: {str(e)[:50]}")
            logging.error(f"Failed to load cog {cog}: {e}")
            
  embed = discord.Embed(title="Cogs Refresh Status", description="\n".join(results), color=rvdia.color)
  await ctx.reply(embed=embed)

@rvdia.command(hidden=True)
@commands.is_owner()
async def restart(ctx:commands.Context): # In case for timeout
   await ctx.send('Restarting...')
   channel = ctx.channel
   await rvdia.close()
   await asyncio.sleep(2)
   rvdia.run(token=os.getenv('token'))
   await rvdia.wait_until_ready()
   logging.warning('RVDIA has been remotely restarted!')
   await channel.send("RVDiA telah direstart!")

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
      
   check_blacklist = await db.blacklist.find_unique(where={'id': user.id})
   if not check_blacklist:
      await db.blacklist.create(data={'id': user.id, 'reason': reason})
      embed = discord.Embed(title='‼️ BLACKLISTED ‼️', timestamp=ctx.message.created_at, color=0xff0000)
      embed.description = f'**`{user}`** telah diblacklist dari menggunakan RVDIA!'
      embed.set_thumbnail(url=user.avatar.url if not user.avatar is None else os.getenv('normalpfp'))
      embed.add_field(name='Alasan:', value=reason, inline=False)
      return await ctx.reply(embed=embed)
   
   await ctx.reply(f'`{user}` telah diblacklist!')

@rvdia.command(hidden=True)
@commands.is_owner()
async def whitelist(ctx:commands.Context, user:discord.User):
   check_blacklist = await db.blacklist.find_unique(where={'id': user.id})
   if not check_blacklist:
      return await ctx.reply(f'**`{user}`** tidak diblacklist dari menggunakan RVDIA!')
   
   await db.blacklist.delete(where={'id': user.id})
   await ctx.reply(f'`{user}` telah diwhitelist!')

# Handler variable
fitur = "Unknown"

async def send_reply_message(msg:discord.Message, message_embed:discord.Embed):
  # Nyambung ke yg di atas
  global fitur
  fitur = "Balasan"
  try:
      async with msg.channel.typing():
        embed_desc = message_embed.description
        embed_title = message_embed.title
        author = message_embed.author.name
        message = msg.content
        user_id = msg.author.id
        
        # 1. Retrieve context (this also generates the query embedding)
        context = await memory_manager.get_context(user_id, message)
        
        # 2. Save user message to memory, REUSING the embedding from context
        await memory_manager.add_memory(user_id, "user", message, embedding=context['embedding'])
        
        currentTime = datetime.now(pytz.utc).astimezone(pytz.timezone("Asia/Jakarta"))
        date = currentTime.strftime("%d/%m/%Y")
        hour = currentTime.strftime("%H:%M:%S")
        client = genai.Client(api_key=os.getenv("googlekey"))
        
        # Construct dynamic prompt
        sys_inst = (
            os.getenv('rolesys') + 
            f"\n\nContext Information:\n"
            f"Currently chatting with: {msg.author}\n"
            f"Current Date: {date}, Time: {hour} WITA\n"
            f"\nRecent Conversation History:\n{context['history']}\n"
            f"\nRelevant Past Memories:\n{context['memories']}\n"
            f"| {author} said: {embed_title} | Your previous response was: {embed_desc}\n"
            f"\nRemember to stay in character as RVDiA (a talented digital artist and gamer, loving, cute, informal)."
        )
        
        result = await client.aio.models.generate_content(
            model='gemini-3-flash-preview',
            contents=message,
            config=types.GenerateContentConfig(
                system_instruction=sys_inst
            )
        )
        AI_response = result.text
        
        # 3. Save AI response to memory (Optimized: skips embedding for model role)
        await memory_manager.add_memory(user_id, "model", AI_response)

        if len(message) > 256:
          message = message[:253] + '...' #Adding ... from 253rd character, ignoring other characters.

        embed = discord.Embed(
          title=' '.join((titlecase(word) for word in message.split(' '))), 
          color=msg.author.color, 
          timestamp=msg.created_at
          )
        embed.description = AI_response
        embed.set_author(name=msg.author)
        embed.set_footer(text='Jika ada yang ingin ditanyakan, bisa langsung direply!')
        regenerate_button = Regenerate_Answer_Button(user_id, message, AI_response)
        await msg.channel.send(embed=embed, view=regenerate_button)

  except Exception as e:
    error_codes = ["500", "503", "104", 'blocked', '429', 'ResourceExhausted']
    if any(codes in str(e) for codes in error_codes):
        retries = 0
        max_retries = 3
        while retries < max_retries:
            retries += 1
            try:
                await asyncio.sleep(2 * retries) # Exponential backoff
                return await send_reply_message(msg, message_embed)
            except Exception as retry_e:
                if retries >= max_retries:
                    raise retry_e
    raise e

@rvdia.event
async def on_message(msg:discord.Message):
    """
    Replacing the available on_message event from Discord
    TO DO: Create check_blacklist() and only run it here.
    Configure RVDiA's class
    """
    global fitur

    if not msg.guild:
        return
    
    await rvdia.process_commands(msg) # Execute commands from here

    if msg.author.bot == True:
        return

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
            await send_reply_message(msg, message_embed)
          
          elif message_embed.footer.text == 'Reply \"Approve\" jika disetujui\nReply \"Decline\" jika tidak disetujui':
            fitur = "Transfer akun"
            old_acc_field = message_embed.fields[0].value
            old_acc_string = old_acc_field.split(': ')
            old_acc_id = int(old_acc_string[2].strip())

            new_acc_field = message_embed.fields[1].value
            new_acc_string = new_acc_field.split(': ')
            new_acc_id = int(new_acc_string[2].strip())
            user = await rvdia.fetch_user(new_acc_id)

            if msg.content.lower() == "approve" or msg.content.lower() == "accept":
                old_data = await db.user.find_unique(where={'id': old_acc_id}, include={'inventory': True})
                if not old_data:
                    return await msg.channel.send("❌ Data lama tidak ditemukan!")
                
                # Merge data into the new account
                # In Prisma, we use 'data' JSONB. 
                await db.user.update(
                    where={'id': new_acc_id},
                    data={
                        'data': old_data.data,
                        'hp': old_data.hp,
                        'max_hp': old_data.max_hp,
                        'inventory': {
                            'upsert': {
                                'create': {
                                    'items': old_data.inventory.items if old_data.inventory else {},
                                    'skills': old_data.inventory.skills if old_data.inventory else {}
                                },
                                'update': {
                                    'items': old_data.inventory.items if old_data.inventory else {},
                                    'skills': old_data.inventory.skills if old_data.inventory else {}
                                }
                            }
                        }
                    }
                )
                await db.user.delete(where={'id': old_acc_id})
                await msg.channel.send(f'✅ Transfer akun untuk {user} selesai!')
                try:
                   await user.send(f"✅ Request transfer akun Re:Volution-mu telah selesai!\nApproved by: `{msg.author}`")
                except:
                   return
                
            elif msg.content.lower() == "decline" or msg.content.lower() == "deny":
              await fetched_message.delete()
              await msg.channel.send(f"❌ Request transfer akun untuk {user} tidak disetujui")
              try:
                  await user.send(f"❌ Mohon maaf, request transfer data akun Re:Volutionmu tidak disetujui.\nUntuk informasi lebih lanjut, silahkan hubungi `{msg.author}` di https://discord.gg/QqWCnk6zxw")
              except:
                  return
        
        except Exception as e:
          if "rate limit" in str(e).lower():
            return await msg.channel.send("Aduh, maaf, otakku sedang kepanasan.\nTolong tanyakan lagi setelah 20 detik!")
           
          elif 'message_id: Value "None" is not snowflake.' in str(e) or "404 not found" in str(e).lower() or "Invalid Form Body In message_reference: Unknown message" in str(e):
            # Very ambiguous error
            logging.warning("Captured yet another Unknown Message error.")
            return await msg.channel.send("Hmm, aku menerima error 404, apa aku sedang halusinasi ya...?", delete_after=3.0)
           
          elif "403 Forbidden" in str(e) or "Missing Access" in str(e):
            try:
                return await msg.channel.send("Aku kekurangan `permission` untuk menjalankan fitur ini!\nPastikan aku bisa mengirim pesan dan embed di channel ini!")
            except:
                try:
                  return await msg.author.send("Aku kekurangan `permission` untuk menjalankan fitur ini!\nPastikan aku bisa mengirim pesan dan embed di channel itu!")
                except:
                  return
                 
          await msg.channel.send('Ada yang bermasalah dengan fitur ini, aku sudah mengirimkan laporan ke developer!')
          channel = rvdia.get_channel(int(os.getenv("errorchannel")))
          embed = format_error_report(e, context=f"Fitur: {fitur}")
          await channel.send(embed=embed)
          logging.error(f"Error in on_message: {str(e)}")

# Didn't know I'd use this, but pretty coolio
if __name__ == "__main__":
  rvdia.run(token=os.getenv('token'))