"""
Somewhat unimportant
Discord is developing their own features so...
I don't think this will hold up
"""

import discord
from discord import app_commands
from scripts.main import connectdb, check_blacklist
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
        """
        Kumpulan command mengenai server ini. [GROUP]
        """
        await self.info(ctx)
        pass

    @server.command(description='Lihat info server ini!')
    @check_blacklist()
    async def info(self, ctx:commands.Context):
        """
        Lihat info server ini!
        """
        async with ctx.typing():
            owner = await self.bot.fetch_user(ctx.guild.owner_id)
            guild_icon = ctx.guild.icon.url if not ctx.guild.icon is None else getenv('normalpfp')
            embed = discord.Embed(title=f'{ctx.guild.name}', color=ctx.author.colour, timestamp = ctx.message.created_at)
            embed.set_thumbnail(url=guild_icon)
            embed.set_author(name = "Server Info:")
            embed.add_field(name="Pemilik", value=f"{owner.mention} ({owner})", inline = False)
            embed.add_field(name="Tanggal Dibuat", value=f'{ctx.guild.created_at.strftime("%a, %d %B %Y")}', inline = False)
            embed.add_field(name="Jumlah Pengguna", value=f"{ctx.guild.member_count} members", inline = False)
            embed.set_footer(text=f"ID: {ctx.guild.id}", icon_url=guild_icon)
            #embed.set_image(url = ctx.guild.banner.url)
            await ctx.reply(embed=embed)

    # Basically, avatar command
    @server.command(description="Memperlihatkan gambar icon server ini.")
    @check_blacklist()
    async def icon(self, ctx:commands.Context):
        """
        Memperlihatkan gambar icon server ini.
        """
        async with ctx.typing():
            guild = ctx.guild

            if guild.icon is None:
                return await ctx.reply(f'Server ini tidak memiliki icon!')
            png = guild.icon.with_format("png").url
            jpg = guild.icon.with_format("jpg").url
            webp = guild.icon.with_format("webp").url

            embed=discord.Embed(title=f"Icon {guild.name}", url = guild.icon.with_format("png").url, color=self.bot.color)

            if guild.icon.is_animated():
                gif = guild.icon.with_format("gif").url
                embed.set_image(url = guild.icon.with_format("gif").url)
                embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp}) | [gif]({gif})"

            else:
                embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp})"
                embed.set_image(url = guild.icon.with_format("png").url)
            embed.set_footer(text=f"{ctx.author}", icon_url=ctx.author.display_avatar.url)
            await ctx.reply(embed=embed)

    @commands.hybrid_group(name='invite')
    @commands.bot_has_permissions(manage_guild=True)
    @check_blacklist()
    async def invite(self, ctx:commands.Context) -> None:
        """
        Kumpulan command menyangkut invite server. [GROUP]
        """
        await self.invites(ctx)
        pass

    @invite.command(name='create', description='Buat invite instan!')
    @commands.bot_has_permissions(manage_guild=True)
    @app_commands.describe(
        expire = 'Berapa lama invite ini akan kadaluwarsa? (dalam detik, default: tak hingga)',
        max_use = 'Berapa banyak orang yang bisa join lewat invite ini? (default: tak hingga)'
        )
    @app_commands.rename(max_use = 'maksimal_pengguna')
    @check_blacklist()
    async def create(self, ctx:commands.Context, expire:int=0, max_use:int=0):
        """
        Buat invite instan!
        """
        created_invite = await ctx.channel.create_invite(
            reason=f'Created using /invite create command by {ctx.author}.', 
            max_age=expire,
            max_uses=max_use
            )
        
        await ctx.reply(f'**Invite siap!**\n{created_invite}')

    @invite.command(name='view', description = 'Lihat daftar invite server ini!')
    @commands.bot_has_permissions(manage_guild=True)
    @check_blacklist()
    async def invites(self, ctx:commands.Context):
        """
        Lihat daftar invite server ini!
        """
        try:
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
            if embed.description == '\n' or None:
                return await ctx.reply("Sepertinya server ini belum membuat invite apapun!")
            await ctx.reply(embed=embed)

        except AttributeError:
            await ctx.reply('Sepertinya server ini belum membuat invite sama sekali!')

    @commands.hybrid_group(name='warn')
    @commands.has_permissions(manage_messages= True)
    @check_blacklist()
    async def warn(self, ctx:commands.Context, member:discord.Member, *, reason = None):
        """
        Kumpulan command berkaitan dengan pemberian pelanggaran. [GROUP]
        """
        await self.warn_add(ctx, member, reason=reason)
        pass
        
    @warn.command(
        name = 'add',
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
    @commands.has_permissions(manage_messages= True)
    @check_blacklist()
    async def warn_add(self, ctx:commands.Context, member:discord.Member, *, reason = None):
        """
        Memberikan pelanggaran kepada pengguna.
        """
        # Uses a guild-grouping mechanic that I thought was pretty neat
        if ctx.author == member:
            return await ctx.reply("Kamu tidak bisa memberikan pelanggaran kepada dirimu!", ephemeral=True)
        if member.bot:
            return await ctx.reply("Uh... sepertinya memberikan pelanggaran kepada bot itu kurang berguna.", ephemeral=True)
        db = await connectdb("Warns")
        reason = reason or "Tidak ada alasan dispesifikasi."

        is_generated = await db.find_one({"_id":ctx.guild.id})
        if is_generated:
            # Don't do anything
            pass

        else:
            await db.insert_one({"_id":ctx.guild.id, "members":[]})

        # Find matching user
        warns = await db.find_one({"_id":ctx.guild.id, "members._id":member.id})
        if warns is None:
            await db.update_one({"_id":ctx.guild.id}, {"$push":{"members":{"_id":member.id, "warns":1, "reason":[reason]}}})
            warnqty = 1
        else:
            await db.update_one({"_id":ctx.guild.id, "members._id":member.id}, {"$push":{"members.$.reason":reason}, "$inc":{"members.$.warns":1}})
            warned_fella = next(m for m in warns['members'] if m['_id'] == member.id)
            warnqty = warned_fella['warns']+1

        em = discord.Embed(title=f"Pelanggaran Diberikan❗", description = f"{member.mention} telah diberikan pelanggaran.\nDia sekarang telah diberikan **`{warnqty}`** pelanggaran.",
        color = member.colour
        )
        em.add_field(name="Alasan", value=reason, inline=False)
        em.set_thumbnail(url = member.display_avatar.url)
        em.set_footer(text=f"Pelanggaran diberikan oleh {ctx.author} | ID:{ctx.author.id}", icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed = em)


    @warn.command(
        name='history',
        description="Lihat riwayat pelanggaran pengguna di server ini.",
    )
    @app_commands.describe(
        member = 'Pengguna di server ini.'
    )
    @app_commands.rename(member = 'pengguna')
    @commands.has_permissions(manage_messages = True)
    @check_blacklist()
    async def warnhistory(self, ctx:commands.Context, member:discord.Member):
            """Lihat riwayat pelanggaran pengguna."""
            member = member or ctx.author
            db = await connectdb("Warns")
            doc = await db.find_one({'_id':ctx.guild.id, "members._id":member.id})
            if doc is None:
                return await ctx.reply(f"**`{member}`** saat ini belum memiliki pelanggaran!", ephemeral=True)
            
            warned_member = next(m for m in doc['members'] if m['_id'] == member.id)
            reasons = warned_member['reason']
            emb = discord.Embed(title = f"Riwayat pelanggaran {member}", color = member.colour)
            emb.add_field(name= "Jumlah Pelanggaran", value=warned_member['warns'], inline=False)
            if warned_member['warns'] > 1:
                emb.add_field(name=f"Alasan (dari pelanggaran #1 sampai #{warned_member['warns']})", value="*"+"\n".join(reasons)+"*")
            else:
                emb.add_field(name=f"Alasan", value="*"+"\n".join(reasons)+"*")
            emb.set_thumbnail(url = member.display_avatar.url)
            await ctx.reply(embed = emb)

    @warn.command(name='remove', description="Menghilangkan segala data pelanggaran pengguna.")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(
        member = 'Pengguna yang ingin dihilangkan riwayat pelanggarannya.'
    )
    @app_commands.rename(
        member = 'pengguna'
    )
    @check_blacklist()
    async def removewarn(self, ctx:commands.Context, member:discord.Member):
        """
        Menghilangkan segala data pelanggaran pengguna.
        """
        db = await connectdb("Warns")
        doc = await db.find_one({"_id":ctx.guild.id, "members._id":member.id})
        if doc is None:
            return await ctx.reply(f"`{member}` belum pernah diberikan pelanggaran!")
        
        await db.update_one({"_id":ctx.guild.id, "members._id":member.id}, {"$pull": {"members": {"_id": member.id}}})
        await ctx.reply(f"Semua pelanggaran untuk {member.mention} di server ini telah dihapus.")

    @warn.command(name='list', description = 'Memperlihatkan semua pengguna yang memiliki pelanggaran di server ini.')
    @commands.has_permissions(manage_messages=True)
    @check_blacklist()
    async def warnlist(self, ctx:commands.Context):
        """
        Memperlihatkan semua pengguna yang memiliki pelanggaran di server ini.
        """
        db = await connectdb('Warns')
        docs = await db.find_one({'_id':ctx.guild.id})
        if docs is None:
            return await ctx.reply(f'Belum ada orang yang diberikan pelanggaran di server ini!')
        
        members = docs['members']
        text = []
        for data in members:
            user = await self.bot.fetch_user(data['_id'])
            text.append(f'**`{user}`** | Jumlah: `{data["warns"]}` pelanggaran')
        
        embed = discord.Embed(title=f'Daftar Pelanggaran di {ctx.guild.name}', color=ctx.author.color, timestamp=ctx.message.created_at)
        embed.description = '\n'.join(text)
        embed.set_thumbnail(url=ctx.guild.icon.url if not ctx.guild.icon is None else getenv('normalpfp'))
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name='ultban', description="Ban pengguna dari server, walaupun dia di luar server ini.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        user = 'Pengguna yang ingin diban (Support ID & name#tag)',
        reason = 'Alasan mengapa diban?'
    )
    @app_commands.rename(
        user = 'pengguna',
        reason = 'alasan'
    )
    @check_blacklist()
    async def ultban(self, ctx:commands.Context, user:discord.User, *, reason = None):
        """
        Ban pengguna dari server
        """
        reason = reason or "Tidak ada alasan dispesifikasi."
        await ctx.guild.ban(user)
        embed = discord.Embed(title="❗Ultimate Ban❗", color = ctx.author.colour)
        embed.description = f"**`{user}`** telah diban!"
        embed.add_field(name = "Alasan", value = reason, inline = False)
        embed.set_thumbnail(url = user.display_avatar.url)
        embed.set_footer(text=f"Dieksekusi oleh {ctx.author} | ID:{ctx.author.id}", icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed = embed)

    @commands.hybrid_command(description="Unban seseorang yang telah diban sebelumnya.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        user = 'Pengguna yang ingin di unban (Support ID & name#tag)'
    )
    @app_commands.rename(
        user = 'pengguna'
    )
    @check_blacklist()
    async def unban(self, ctx:commands.Context, user: discord.User):
        """
        Unban pengguna yang telah diban.
        """
        async with ctx.typing():
            try:
                await ctx.guild.unban(user)
                await ctx.send(f"{user} telah diunban.")
                return
            except:
                await ctx.send(f"Aku tidak bisa menemukan {user} di ban list!")
                return

    @commands.hybrid_command(aliases = ['clean', 'purge', 'delete', 'hapus'], 
                      description="Menghilangkan pesan berdasarkan jumlah yang diinginkan.")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @app_commands.describe(
        amount = 'Jumlah pesan yang ingin dihapus?',
        channel = 'Channel manakah yang ingin dihapus pesannya?'
    )
    @app_commands.rename(
        amount = 'jumlah'
    )
    @check_blacklist()
    async def clear(self, ctx:commands.Context, amount:int, channel:discord.TextChannel = None):
        """
        Menghilangkan pesan berdasarkan jumlah yang diinginkan.
        """

        channel = channel or ctx.channel
        if amount <= 0:
            return await ctx.reply("Aku tidak bisa menghapus `0` pesan!", ephemeral=True)
        elif amount >= 100:
            return await ctx.reply("Aku mempunyai batas untuk menghapus `99` pesan!", ephemeral=True)
        
        match channel:
            case ctx.channel:
                await ctx.reply(f"Menghapus **`{amount}`** pesan...")
            case _:
                await ctx.reply(f"Menghapus **`{amount}`** pesan di {channel.mention}...", delete_after=10.0)

        async with ctx.channel.typing():
            await channel.purge(limit = amount+1 if channel == ctx.channel else amount)
        return await ctx.channel.send(f"Aku telah menghapus {amount} pesan dari {channel.mention}.", delete_after = 5.0)

async def setup(bot):
    await bot.add_cog(Moderation(bot))