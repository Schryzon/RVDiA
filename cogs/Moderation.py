import discord
from discord import app_commands
from scripts.main import db, check_blacklist
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
            await ctx.reply(embed=embed)

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
            if not embed.description or embed.description == '':
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
        if ctx.author == member:
            return await ctx.reply("Kamu tidak bisa memberikan pelanggaran kepada dirimu!", ephemeral=True)
        if member.bot:
            return await ctx.reply("Uh... sepertinya memberikan pelanggaran kepada bot itu kurang berguna.", ephemeral=True)
        
        reason = reason or "Tidak ada alasan dispesifikasi."

        # Create warning record
        await db.warning.create(data={
            'guildId': ctx.guild.id,
            'userId': member.id,
            'reason': reason
        })

        # Count total warnings for this user in this guild
        warnqty = await db.warning.count(where={
            'guildId': ctx.guild.id,
            'userId': member.id
        })

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
    async def warnhistory(self, ctx:commands.Context, member:discord.Member=None):
            """Lihat riwayat pelanggaran pengguna."""
            member = member or ctx.author
            warns = await db.warning.find_many(where={
                'guildId': ctx.guild.id,
                'userId': member.id
            }, order={'createdAt': 'desc'})
            
            if not warns:
                return await ctx.reply(f"**`{member}`** saat ini belum memiliki pelanggaran!", ephemeral=True)
            
            warn_count = len(warns)
            reasons = [w.reason for w in warns]
            emb = discord.Embed(title = f"Riwayat pelanggaran {member}", color = member.colour)
            emb.add_field(name= "Jumlah Pelanggaran", value=str(warn_count), inline=False)
            
            reasons_text = "\n".join([f"{i+1}. {r}" for i, r in enumerate(reasons)])
            if warn_count > 1:
                emb.add_field(name=f"Alasan (dari terbaru)", value=f"*{reasons_text}*")
            else:
                emb.add_field(name=f"Alasan", value=f"*{reasons_text}*")
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
        deleted = await db.warning.delete_many(where={
            'guildId': ctx.guild.id,
            'userId': member.id
        })
        
        if deleted == 0:
            return await ctx.reply(f"`{member}` belum pernah diberikan pelanggaran!")
        
        await ctx.reply(f"Semua pelanggaran untuk {member.mention} di server ini telah dihapus.")

    @warn.command(name='list', description = 'Memperlihatkan semua pengguna yang memiliki pelanggaran di server ini.')
    @commands.has_permissions(manage_messages=True)
    @check_blacklist()
    async def warnlist(self, ctx:commands.Context):
        """
        Memperlihatkan semua pengguna yang memiliki pelanggaran di server ini.
        """
        # Get unique user IDs with warnings in this guild
        # Prisma Python doesn't have groupBy yet in some versions, but we can use distinct if supported
        # Or just get all and process in Python
        warns = await db.warning.find_many(where={'guildId': ctx.guild.id})
        if not warns:
            return await ctx.reply(f'Belum ada orang yang diberikan pelanggaran di server ini!')
        
        user_warns = {}
        for w in warns:
            user_warns[w.userId] = user_warns.get(w.userId, 0) + 1
            
        text = []
        for user_id, count in user_warns.items():
            try:
                user = await self.bot.fetch_user(user_id)
                text.append(f'**`{user}`** | Jumlah: `{count}` pelanggaran')
            except:
                text.append(f'**`Unknown User ({user_id})`** | Jumlah: `{count}` pelanggaran')
        
        embed = discord.Embed(title=f'Daftar Pelanggaran di {ctx.guild.name}', color=ctx.author.color, timestamp=ctx.message.created_at)
        embed.description = '\n'.join(text)
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else getenv('normalpfp'))
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
        return await ctx.channel.send(f"Aku telah menghapus {amount} pesan from {channel.mention}.", delete_after = 5.0)

async def setup(bot):
    await bot.add_cog(Moderation(bot))