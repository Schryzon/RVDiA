
import discord
from discord.ext import commands

class NotGTechMember(commands.CommandError):
  """Raised when command is not being run by a G-Tech Resman member"""
  pass

class NotInGTechServer(commands.CommandError):
  """Raised when the command was not executed in a G-Tech server"""
  pass

class NotGTechAdmin(commands.CommandError):
  """Raised when the command was not executed by a G-Tech Admin, replaces is_owner()"""
  pass

class Error(commands.Cog):
  """
  An error handler class, what else do I have to say?
  """
  def __init__ (self, historia):
    self.historia = historia

  @commands.Cog.listener()
  async def on_command_error(self, ctx, error):
    try:
      if ctx.command.has_error_handler():
        return
    except:
      pass

    error = getattr(error, "original", error)

    if isinstance(error, commands.MissingRequiredArgument):
      await ctx.reply(f"Ada beberapa bagian yang belum kamu isi!\nDibutuhkan: **`{error.param}`**")

    elif isinstance(error, NotGTechMember):
      await ctx.reply('Akun Discordmu harus didaftarkan dulu ke data G-Tech sebelum menjalankan command ini!')

    elif isinstance(error, NotInGTechServer):
      await ctx.reply('Command ini hanya bisa dijalankan di G-Tech server!')

    elif isinstance(error, NotGTechAdmin):
      await ctx.reply('Command ini hanya bisa dijalankan oleh admin database G-Tech!')

    elif isinstance(error, commands.CommandNotFound):
      await ctx.reply(f"Tidak dapat menemukan command! Cari command yang ada dengan `r-help`")

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
      await ctx.reply(f"Command sedang dalam cooldown!\nKamu bisa menjalankannya lagi setelah {round(error.retry_after)} detik.**")

    elif isinstance(error, commands.RoleNotFound):
      await ctx.reply("Tidak dapat menemukan role tersebut di dalam server ini!")

    elif isinstance(error, commands.NotOwner):
      await ctx.reply("Hanya Jayananda yang memiliki akses ke command ini!")

    elif isinstance(error, commands.BotMissingPermissions):
      lel = [kol.replace('_', ' ') for kol in error.missing_perms]
      lol = [what.title() for what in lel]
      await ctx.reply("Saya kekurangan `permissions` untuk menjalankan command! (**"
      + "`" + ",".join(lol) + "`**)"
      )

    elif isinstance(error, commands.MissingPermissions):
      lel = [kol.replace('_', ' ') for kol in error.missing_perms]
      lol = [what.title() for what in lel]
      await ctx.reply("Kamu kekurangan `permissions` untuk menjalankan command! (**"
      + "`" + ",".join(lol) + "`**)"
      )

    elif "Forbidden" in str(error):
      await ctx.reply("Kode error: `Forbidden`, mungkin `Role` saya terlalu rendah, atau saya kekurangan `Permissions`!")

    elif "Invalid base64-encoded string" in str(error) or "Incorrect padding" in str(error):
      await ctx.reply("Sepertinya itu bukan Base64, tolong berikan teks dalam format Base64!")

    #I wonder why I made this loll
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
      except AttributeError:
        em.add_field(name=f"Command Name",value=ctx.command,inline=False)
        em.add_field(name=f"Invoked By",value=ctx.message.content,inline=False)
        em.add_field(name=f"Args",value=ctx.args,inline=False)
        em.add_field(name=f"Kwargs",value=ctx.kwargs,inline=False)
        em.add_field(name=f"Error Message",value=error,inline=False)
      finally:
          em.set_footer(text = "Please fix the error immediately!", icon_url = self.historia.user.avatar.url)
          await channel.send(f"<@877008612021661726> **Error from console!**", embed = em)
          await ctx.reply("Ada yang bermasalah dengan command ini, aku sudah memberikan laporan ke developer!")
          print(error)

async def setup(pandora):
  await pandora.add_cog(Error(pandora))