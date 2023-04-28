
import discord
from discord.ui import View, Button
from discord.ext import commands
from pymongo.errors import ConnectionFailure

"""
Error handlers, it's where the ifs and elifs go crazy!
"""

class NotGTechMember(commands.CommandError):
  """Raised when command is not being run by a G-Tech Resman member"""
  pass

class NotInGTechServer(commands.CommandError):
  """Raised when the command was not executed in a G-Tech server"""
  pass

class NotGTechAdmin(commands.CommandError):
  """Raised when the command was not executed by a G-Tech Admin, replaces is_owner()"""
  pass

class NoProfilePicture(commands.CommandError):
  """Raised when the user doesn't have a profile picture (automatically aborts command)"""
  pass

class Blacklisted(commands.CommandError):
    """Raised if user is blacklisted."""
    pass

class NoEventAvailable(commands.CommandError):
  """Raised when no events are currently ongoing"""
  pass

class NotVoted(commands.CommandError):
  """Raised when user hasn't voted on Top.gg"""
  pass

class NoGameAccount(commands.CommandError):
  """Raised when user hasn't created a game account yet"""
  pass

class Support_Button(View):
        def __init__(self):
            super().__init__(timeout=None)

            support_server = Button(
                label= "Support Server",
                emoji = '<:cyron:1082789553263349851>',
                style = discord.ButtonStyle.blurple,
                url = 'https://discord.gg/QqWCnk6zxw'
            )
            self.add_item(support_server)

class Error(commands.Cog):
  """
  An error handler class, what else do I have to say?
  """
  def __init__ (self, historia):
    self.historia = historia

  @commands.Cog.listener()
  async def on_command_error(self, ctx:commands.Context, error):
    try:
      if ctx.command.has_error_handler():
        return
    except:
      pass

    error = getattr(error, "original", error)

    if isinstance(error, commands.MissingRequiredArgument):
      await ctx.reply(f"Ada beberapa bagian yang belum kamu isi!\nDibutuhkan: **`{error.param}`**")

  # Hack-ish, I'm still figuring out why it didnt work
    elif 'Not a G-Tech member!' in str(error):
      await ctx.reply('Akun Discordmu harus didaftarkan dulu ke data G-Tech sebelum menjalankan command ini!')

    elif 'Not in the G-Tech server!' in str(error):
      await ctx.reply('Command ini hanya bisa dijalankan di G-Tech server!')

    elif 'Not a G-Tech admin!' in str(error):
      await ctx.reply('Command ini hanya bisa dijalankan oleh admin database G-Tech!')

    elif 'User is blacklisted!' in str(error):
      await ctx.reply('Maaf, kamu telah diblacklist dari menggunakan RVDIA!')

    elif isinstance(error, commands.CommandNotFound):
      await ctx.reply(f"Tidak dapat menemukan command! Cari command yang ada dengan `{ctx.clean_prefix}help`")

    elif isinstance(error, commands.NoPrivateMessage):
      await ctx.reply("Command ini tidak bisa dijalankan melalui DM.")
      
    elif isinstance(error, commands.MemberNotFound):
      await ctx.reply("Tidak dapat menemukan pengguna, pastikan dia ada di server ini!")
      
    elif isinstance(error, commands.TooManyArguments):
      await ctx.reply("Bagian yang kamu berlebihan, silahkan lihat help command untuk mengetahui berapa banyak yang ku butuhkan!")

    elif isinstance(error, commands.UserNotFound):
      await ctx.reply("Tidak dapat menemukan pengguna di database Discord!")

    elif isinstance(error, commands.NSFWChannelRequired):
      await ctx.reply("Command ini hanya bisa digunakan di channel NSFW!")

    elif isinstance(error, commands.MissingRole):
      await ctx.reply("`Role` kamu tidak cukup untuk menjalankan command ini!")

    elif isinstance(error, commands.ChannelNotFound):
      await ctx.reply("Tidak dapat menemukan channel itu!")

    elif isinstance(error, commands.CommandOnCooldown):
      await ctx.reply(f"Command sedang dalam cooldown!\nKamu bisa menjalankannya lagi setelah **`{round(error.retry_after)}`** detik.")

    elif isinstance(error, commands.RoleNotFound):
      await ctx.reply("Tidak dapat menemukan role tersebut di dalam server ini!")

    elif isinstance(error, commands.NotOwner):
      await ctx.reply("Hanya Jayananda yang memiliki akses ke command ini!")

    elif 'No profile picture!' in str(error):
      await ctx.reply('Kamu harus memasang foto profil untuk menjalankan command ini!') # Maybe add a note in github somewhere

    elif isinstance(error, commands.BotMissingPermissions):
      permlist = [req_perms.replace('_', ' ') for req_perms in error.missing_permissions]
      perms = [missing_perms.title() for missing_perms in permlist]
      await ctx.reply("Saya kekurangan `permissions` untuk menjalankan command! (**"
      + "`" + ",".join(perms) + "`**)"
      )

    elif isinstance(error, commands.MissingPermissions):
      permlist = [req_perms.replace('_', ' ') for req_perms in error.missing_permissions]
      perms = [missing_perms.title() for missing_perms in permlist]
      await ctx.reply("Kamu kekurangan `permissions` untuk menjalankan command! (**"
      + "`" + ",".join(perms) + "`**)"
      )

    elif "Forbidden" in str(error):
      await ctx.reply("Kode error: `Forbidden`, mungkin `Role`ku atau kamu terlalu rendah/setara, atau kekurangan `Permissions`!")

    elif "Invalid base64-encoded string" in str(error) or "Incorrect padding" in str(error):
      await ctx.reply("Sepertinya itu bukan Base64, tolong berikan teks dalam format Base64!")

    elif "Your prompt may contain text that is not allowed by our safety system." in str(error):
      await ctx.reply('Prompt yang diberikan kurang pantas untuk ditampilkan!')

    elif "Uploaded image must be a PNG and less than 4 MB." in str(error):
      await ctx.reply('Format gambar tidak disupport RVDIA atau lebih dari 4MB! (hanya `.jpg` & `.png`)')

    elif "cannot identify image file" in str(error):
      await ctx.reply('Aku tidak bisa mendeteksi file tersebut! Apakah kamu yakin itu file gambar?')

    elif "No event available!" in str(error):
      await ctx.reply('Maaf, saat ini tidak ada event yang berlangsung!')

    elif "attachment is a required argument that is missing an attachment." in str(error):
      await ctx.reply('Kamu belum melampirkan gambar! Command ini memerlukan lampiran!')

    elif "Your input image may contain content that is not allowed by our safety system." in str(error):
      await ctx.reply('Gambar yang dilampirkan berisi konten yang tidak pantas!')

    elif "currently overloaded with other requests." in str(error):
      await ctx.reply('Maaf, saat ini fitur tersebut sedang dalam gangguan. Mohon dicoba lagi nanti!')

    elif "Rate limit reached for" in str(error):
      await ctx.reply("Maaf, command ini sedang dalam *forced-cooldown*\nSilahkan coba lagi setelah 20 detik.")

    elif 'User has not voted yet!' in str(error):
      # Man why doesnt it work tho
      class Vote_Button(View):
        def __init__(self):
            super().__init__(timeout=None)

            vote_me = Button(
                    label='Vote Aku!', 
                    emoji='<:rvdia:1082789733001875518>',
                    style=discord.ButtonStyle.green, 
                    url='https://top.gg/bot/957471338577166417/vote'
                    )
        
            self.add_item(vote_me)
      await ctx.reply('Kamu belum vote aku!\nVote aku di Top.gg untuk bisa menggunakan command ini!', view=Vote_Button())

    elif 'User has no game account!' in str(error):
      await ctx.reply(f'Kamu belum mendaftarkan akunmu ke Land of Revolution!\nDaftarkan akunmu dengan `{ctx.clean_prefix}game register`')

    elif isinstance(error, ConnectionResetError) or isinstance(error, ConnectionFailure) or "reset by peer" in str(error):
      await ctx.reply("Wah, sepertinya aku ada gangguan nyambung ke database, mohon dicoba lagi sebentar.\nJika error terus muncul, silahkan laporkan ke Support Server!", view=Support_Button())

    elif "Invalid Form Body In message_reference: Unknown message" in str(error):
      await ctx.reply("Hah?!\nSepertinya aku sedang mengalami masalah menemukan pesan yang kamu reply!")

    # If all else fails (get it?)
    else:
      channel = self.historia.get_channel(906123251997089792)
      em = discord.Embed(title = "An Error Occurred!", color = 0xff4df0, timestamp = ctx.message.created_at)
      try:
        em.add_field(name=f"Command Name",value=ctx.command,inline=False)
        em.add_field(name=f"Invoked By",value=ctx.message.content,inline=False)
        em.add_field(name=f"Command Cog",value=ctx.cog.qualified_name,inline=False)
        em.add_field(name=f"Args",value=ctx.args,inline=False)
        em.add_field(name=f"Kwargs",value=ctx.kwargs,inline=False)
        em.add_field(name=f"Error Message",value=error,inline=False)

      except AttributeError: # If not invoked within a cog
        em.add_field(name=f"Command Name",value=ctx.command,inline=False)
        em.add_field(name=f"Invoked By",value=ctx.message.content,inline=False)
        em.add_field(name=f"Args",value=ctx.args,inline=False)
        em.add_field(name=f"Kwargs",value=ctx.kwargs,inline=False)
        em.add_field(name=f"Error Message",value=error,inline=False)

      finally:
          em.set_footer(text = "Please fix the error immediately!", icon_url = self.historia.user.avatar.url)
          await channel.send(f"<@877008612021661726> **Error from console!**", embed = em)
          await ctx.reply("Ada yang bermasalah dengan command ini, aku sudah memberikan laporan ke developer!\nJoin support serverku untuk mendapat info lebih lanjut!", view=Support_Button())
          print(error)

async def setup(pandora):
  await pandora.add_cog(Error(pandora))