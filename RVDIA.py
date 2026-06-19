"""
Schryzon (Widiyasa Jayananda)
G-Tech Re'sman Programming Division
University of Mataram Informatics
RVDiA (Revolutionary Virtual Digital Assistant)
Feel free to modify and do other stuff.
Contributions are welcome.
Licensed under the AGPL-3.0 License.
* Note: Now that RVDiA is verified, 
        making public clones of her under the same name (especially for fraudulent purposes) 
        is a big no no, okay sweetie?
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
from scripts.ai.chat import chat_service
from scripts.utils.i18n import i18n
from discord.ext import commands, tasks
from random import choice as rand
from contextlib import suppress
from datetime import datetime
from scripts.main import titlecase, check_vote, db, get_commands_context, clean_truncate
from scripts.ai.memory import memory_manager
from scripts.utils.error_logger import format_error_report
load_dotenv() # Loads the .env file from python-dotenv pack

class RVDIA(commands.AutoShardedBot):
  """
  A subclass of commands.AutoShardedBot; RVDiA herself.
  This is in order to make her attributes easier to maintain.
  (Nah, I'm just lazy tbh.)
  """
  def __init__(self, **kwargs):
    self.synced = False
    self.__version__ = "[EARLY] Rebirth v3.0.0"
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
    from scripts.api.web_server import start_web_server
    await db.connect()
    logging.info("Prisma Database connected.")
    
    # Start the Web Server
    self.loop.create_task(start_web_server(self))
    logging.info("Web Server task created.")

    # Start the Telegram Bot Polling Adapter
    from scripts.telegram_bot import start_telegram_bot
    self.loop.create_task(start_telegram_bot(self))
    logging.info("Telegram Bot task created.")



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
      rvdia.synced = [True, len(synced_commands)]
      logging.info('Slash Commands synced to global!')

    if not change_status.is_running():
      change_status.start()
      logging.info('change_status() starting!')

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
  all_status=['in my room', 'in front of a mirror', '"How to be cute"', 'you', 'everyone!',
                  '@RVDiA', f"{user_count_status}", f'{rvdia.__version__}',
                  '/help', 'in my dream world', 'Add me!', is_event, '~♪',
                  'Re:Volution'
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


# Handler variable
fitur = "Unknown"

async def send_reply_message(msg:discord.Message, message_embed:discord.Embed):
  global fitur
  fitur = "Balasan"
  try:
      async with msg.channel.typing():
        embed_desc = message_embed.description
        embed_title = message_embed.title
        author = message_embed.author.name
        message = msg.content
        user_id = msg.author.id
        
        # Query language settings
        user_settings = await db.usersettings.find_unique(where={'userId': user_id})
        lang = user_settings.lang if user_settings else "en"
        
        # Parse attachments if any
        from scripts.image.attachment import handle_attachment
        attachment_text = ""
        image_raw_bytes = None
        image_mime_type = None
        for att in msg.attachments:
            att_res = await handle_attachment(att)
            if att_res["text"]:
                attachment_text += att_res["text"]
            if att_res["image_bytes"]:
                image_raw_bytes = att_res["image_bytes"]
                image_mime_type = att_res["mime_type"]

        full_message = message
        if attachment_text:
            full_message = f"{attachment_text}\nUser message: {message}"

        cmd_ctx = get_commands_context(rvdia)
        res = await chat_service.generate_chat_response(
            user_id=user_id,
            user_name=str(msg.author),
            message=full_message,
            lang=lang,
            image_bytes=image_raw_bytes,
            mime_type=image_mime_type,
            bot_commands_context=cmd_ctx,
            previous_embed_title=embed_title,
            previous_embed_desc=embed_desc,
            author_name=author
        )
        AI_response = res["response"]

        if len(message) > 256:
          message = message[:253] + '...'

        embed = discord.Embed(
          title=' '.join((titlecase(word) for word in message.split(' '))), 
          color=msg.author.color, 
          timestamp=msg.created_at
          )
        embed.description = AI_response
        embed.set_author(name=msg.author)
        
        footer_text = chat_service.get_translation(lang, "help_suggest_reply")
        embed.set_footer(text=footer_text)
        
        # Check if response has an image link
        import re
        img_match = re.search(r'https?://\S+\.(?:jpg|jpeg|png|gif|webp)', AI_response)
        if img_match:
            embed.set_image(url=img_match.group(0))

        regenerate_button = Regenerate_Answer_Button(user_id, message, AI_response, image_raw_bytes, image_mime_type, lang=lang)
        await msg.channel.send(embed=embed, view=regenerate_button)

  except Exception as e:
    error_codes = ["500", "503", "104", 'blocked', '429', 'ResourceExhausted']
    if any(codes in str(e) for codes in error_codes):
        retries = 0
        max_retries = 3
        while retries < max_retries:
            retries += 1
            try:
                await asyncio.sleep(2 * retries)
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

    if msg.author.bot == True:
        return

    if not msg.guild:
        return

    # Check if the message starts with the bot mention
    mention = f"<@{rvdia.user.id}>"
    mention_nick = f"<@!{rvdia.user.id}>"
    starts_with_mention = msg.content.startswith(mention) or msg.content.startswith(mention_nick)
    
    if starts_with_mention:
        # Extract content after prefix mention
        content_after = msg.content[len(mention):].strip() if msg.content.startswith(mention) else msg.content[len(mention_nick):].strip()
        
        parts = content_after.split()
        potential_cmd = parts[0].lower() if parts else None
        
        is_cmd = False
        if potential_cmd:
            is_cmd = rvdia.get_command(potential_cmd) is not None
            
        if not is_cmd:
            # Rewrite message content to run "chat" command
            msg.content = f"<@{rvdia.user.id}> chat {content_after}".strip()
            
    await rvdia.process_commands(msg) # Execute commands from here

    if msg.reference:
        try:
          fetched_message = None
          for attempt in range(3):
              try:
                  fetched_message = await msg.channel.fetch_message(msg.reference.message_id)
                  break
              except discord.DiscordServerError as dse:
                  if attempt < 2:
                      await asyncio.sleep(1 + attempt)
                      continue
                  raise dse
              except discord.HTTPException as he:
                  if he.status in (502, 503, 504) and attempt < 2:
                      await asyncio.sleep(1 + attempt)
                      continue
                  raise he

          match fetched_message.author.id:
              case rvdia.user.id:
                  pass
              case _:
                  return
          
          if fetched_message.embeds and fetched_message.embeds[0] and fetched_message.embeds[0].footer:
              message_embed = fetched_message.embeds[0]
          else:
              return
          
          is_chat_reply = message_embed.footer.text in (
              chat_service.get_translation("id", "help_suggest_reply"),
              chat_service.get_translation("en", "help_suggest_reply")
          )
          is_transfer_request = message_embed.footer.text in (
              i18n.get("id", "game.transfer_embed_footer"),
              i18n.get("en", "game.transfer_embed_footer")
          )

          if is_chat_reply:
            await send_reply_message(msg, message_embed)
          
          elif is_transfer_request:
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

          elif any(err in str(e).lower() for err in ["502", "503", "504", "service unavailable", "upstream connect error", "disconnect/reset"]):
            # Handle temporary Discord API/Gateway issues without spamming logs
            logging.warning(f"Discord temporary server error caught in on_message: {e}")
            return await msg.channel.send("Aduh, sepertinya koneksi ke Discord sedang mengalami gangguan. Silakan coba lagi sebentar lagi! 🌐", delete_after=5.0)
                 
          await msg.channel.send('Ada yang bermasalah dengan fitur ini, aku sudah mengirimkan laporan ke developer!')
          channel = rvdia.get_channel(int(os.getenv("errorchannel")))
          embed = format_error_report(e, context=f"Fitur: {fitur}")
          await channel.send(embed=embed)
          logging.error(f"Error in on_message: {str(e)}")

# Didn't know I'd use this, but pretty coolio
if __name__ == "__main__":
  rvdia.run(token=os.getenv('token'))