import discord
from discord import app_commands
from scripts.main import check_blacklist, connectdb
from os import getenv
from discord.ext import commands

class Moderation(commands.Cog):
    """
    Command untuk moderasi server.
    """

    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_group(name='server')
    @check_blacklist()
    async def server(self, ctx:commands.Context) -> None:
        await self.info(ctx)
        pass

    @server.command(description='Lihat info server ini!')
    @check_blacklist()
    async def info(self, ctx:commands.Context):
        """
        Lihat info server ini!
        """
        owner = await self.bot.fetch_user(ctx.guild.owner_id)
        """roles = [role.mention for role in ctx.guild.roles][::-1][:-1] or ['None']
        if roles[0] == "None":
            role_length = 0
        else:
            role_length = len(roles)
        desc = ctx.guild.description
        if desc == None:
            desc = "No description was made for this server."""
        embed = discord.Embed(title=f'{ctx.guild.name}', color=ctx.author.colour, timestamp = ctx.message.created_at)
        embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.set_author(name = "Server Info:")
        embed.add_field(name="Pemilik", value=f"{owner.mention} ({owner})", inline = False)
        embed.add_field(name="Tanggal Dibuat", value=f'{ctx.guild.created_at.strftime("%a, %d %B %Y")}', inline = False)
        embed.add_field(name="Jumlah Pengguna", value=f"{ctx.guild.member_count} members", inline = False)
        embed.set_footer(text=f"ID: {ctx.guild.id}", icon_url=ctx.guild.icon.url)
        #embed.set_image(url = ctx.guild.banner.url)
        await ctx.reply(embed=embed)

    @server.command(description = 'Lihat daftar invite server ini!')
    @commands.bot_has_permissions(manage_guild=True)
    @check_blacklist()
    async def invite(self, ctx:commands.Context):
        """
        Lihat daftar invite server ini!
        """
        invites = await ctx.guild.invites()
        invite_urls = [v.url for v in invites]
        invite_authors = [v.inviter for v in invites]
        invite_expire = [v.expires_at for v in invites]
        invite_list = []

        for i, j, k in zip(invite_urls, invite_authors, invite_expire):
            text = f'{i} | Dibuat oleh: {j} | Expire: {k}'
            invite_list.append(text)

        embed = discord.Embed(title=f'Daftar Invite {ctx.guild.name}', color=ctx.author.color, timestamp=ctx.message.created_at)
        embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.description = '\n'.join(invite_list)
        await ctx.reply(embed=embed)

    @commands.hybrid_command(
        description="Memberikan pelanggaran kepada pengguna. (Harus berada di server ini)"
        )
    @app_commands.describe(
        member = 'Pengguna yang melanggar',
        reason = 'Mengapa memberikan pelanggaran?'
    )
    @app_commands.rename(
        member='pengguna',
        reason='alasan'
    )
    @commands.has_permissions(kick_members = True)
    @check_blacklist()
    async def warn(self, ctx:commands.Context, member:discord.Member, *, reason = None):
        """
        Memberikan pelanggaran kepada pengguna.
        """
        if ctx.author == member:
            return await ctx.reply("Kamu tidak bisa memberikan pelanggaran kepada dirimu!")
        if member.bot:
            return await ctx.reply("Uh... sepertinya memberikan pelanggaran kepada bot itu kurang berguna.")
        db = connectdb("Warns")
        reason = reason or "Tidak ada alasan dispesifikasi."
        warns = db.find_one({"_id":member.id})
        warnqty = 0 #Gee
        if warns is None:
            db.insert_one({"_id":member.id, "warns":1, "reason":[reason]})
            warnqty = 1
        else:
            db.update_one({"_id":member.id}, {'$inc':{"warns":1}, '$push':{"reason":reason}})
            warnqty = warns['warns']+1
        em = discord.Embed(title=f"Pelanggaran ❗", description = f"{member.mention} telah diberikan pelanggaran.\nDia sekarang telah diberikan **`{warnqty}`** pelanggaran.",
        color = member.colour
        )
        em.add_field(name="Reason", value=reason, inline=False)
        em.set_thumbnail(url = member.avatar.url if not member.avatar.url is None else getenv('normalpfp'))
        em.set_footer(text=f"Pelanggaran diberikan oleh {ctx.author} | ID:{ctx.author.id}", icon_url=ctx.author.avatar.url)
        await ctx.reply(embed = em)

    @commands.hybrid_command(
        aliases=['wnhistory'], 
        description="Lihat riwayat pelanggaran pengguna di server ini.",
    )
    @commands.has_permissions(kick_members = True)
    @check_blacklist()
    async def warnhistory(self, ctx, member:discord.Member = None):
            """Lihat riwayat pelanggaran pengguna."""
            member = member or ctx.author
            db = connectdb("Warns")
            doc = db.find_one({'_id':member.id})
            if doc is None:
                return await ctx.reply(f"**`{member}`** saat ini belum memiliki pelanggaran.")
            reasons = doc['reason']
            emb = discord.Embed(title = f"Riwayat pelanggaran {member}", color = member.colour)
            emb.add_field(name= "Jumlah Pelanggaran", value=doc['warns'], inline=False)
            if doc['warns'] > 1:
                emb.add_field(name=f"Alasan (dari pelanggaran #1 to #{doc['warns']})", value="*"+"\n".join(reasons)+"*")
            else:
                emb.add_field(name=f"Reason", value="*"+"\n".join(reasons)+"*")
            emb.set_thumbnail(url = member.avatar.url if not member.avatar.url is None else getenv('normalpfp'))
            await ctx.reply(embed = emb)

    @commands.hybrid_command(aliases=["rmwarn"], description="Menghilangkan segala data pelanggaran pengguna.")
    @commands.has_permissions(kick_members=True)
    @check_blacklist()
    async def removewarn(self, ctx, member:discord.Member):
        """
        Menghilangkan segala data pelanggaran pengguna.
        """
        db = connectdb("Warns")
        doc = db.find_one({"_id":member.id})
        if doc is None:
            return await ctx.reply(f"`{member}` belum pernah diberikan pelanggaran!")
        db.find_one_and_delete({"_id":member.id})
        await ctx.reply(f"Semua pelanggaran untuk {member.mention} telah dihapus.")

    """@commands.command(aliases=['wnlist'])
    @commands.has_permissions(ban_members=True)
    async def warnlist(self, ctx):
        db = connectdb('Warns')
        docs = db.find({})
        print(docs)""" #Unused for the moment.

    @commands.hybrid_command(name='ultban', description="Ban pengguna dari server, walaupun dia di luar server ini.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @check_blacklist()
    async def ultban(self, ctx:commands.Context, user:discord.User, *, reason = None):
        """
        Ban pengguna dari server
        """
        reason = reason or "Tidak ada alasan dispesifikasi."
        await ctx.guild.ban(user)
        embed = discord.Embed(title="Ultimate Ban ❗", color = ctx.author.colour)
        embed.description = f"**`{user}`** telah diban!"
        embed.add_field(name = "Alasan", value = reason, inline = False)
        embed.set_thumbnail(url = user.avatar.url if not user.avatar.url is None else getenv('normalpfp'))
        embed.set_footer(text=f"Dieksekusi oleh {ctx.author} | ID:{ctx.author.id}", icon_url=ctx.author.avatar.url)
        await ctx.reply(embed = embed)

    @commands.hybrid_command(description="Unban seseorang yang telah diban sebelumnya.")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(manage_guild=True)
    @check_blacklist()
    async def unban(self, ctx, user: discord.User):
        """
        Unban pengguna yang telah diban.
        """
        try:
            await ctx.guild.unban(user)
            await ctx.send(f"{user} telah diunban.")
            return
        except:
            await ctx.send(f"Aku tidak bisa menemukan {user} di ban list!")
            return

    @commands.hybrid_command(aliases = ['clean', 'purge', 'delete', 'hapus'], 
                      description="Menghilangkan pesan berdasarkan jumlah yang diinginkan (amount -> integer), (channel : opsional)")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @check_blacklist()
    async def clear(self, ctx:commands.Context, amount:int, channel:commands.TextChannelConverter = None):
        """
        Menghilangkan pesan berdasarkan jumlah yang diinginkan.
        """
        channel = channel or ctx.channel
        if amount <= 0:
            return await ctx.reply("Aku tidak bisa menghapus `0` pesan!")
        amount = amount or 5
        await channel.purge(limit = amount+1 if channel == ctx.channel else amount)
        await ctx.send(f"Aku telah menghapus {amount} pesan dari {channel.mention}.", delete_after = 5.0)

async def setup(bot):
    await bot.add_cog(Moderation(bot))