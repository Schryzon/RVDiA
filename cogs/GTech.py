from os import getenv
import discord
from discord import app_commands
from discord.ext import commands
from scripts.main import connectdb, in_gtech_server, is_member_check, is_perangkat, check_blacklist

class GTech(commands.Cog):
    """
    Kategori khusus bagi anggota G-Tech Re'sman
    """
    def __init__(self, bot):
        self.bot = bot

    def is_member(self, id:int): #Used for gaining data only
        db = connectdb("Gtech")
        data = db.find_one({'_id':id})
        return data
    
    @commands.hybrid_group(name='gtech')
    @in_gtech_server()
    @is_member_check()
    @check_blacklist()
    async def gtech_command(self, ctx:commands.Context) -> None:
        """
        Kumpulan command khusus untuk anggota G-Tech Re'sman. [GROUP]
        """
        await self.news(ctx)
        pass

    async def send_news(self, channel_id:int):
        db = connectdb("Technews")
        news = db.find_one({'_id':1})
        channel = self.bot.get_channel(channel_id)
        embed = discord.Embed(title=news['title'], color = 0xff0000)
        embed.set_thumbnail(url = 'https://cdn.discordapp.com/attachments/872815705475666007/974638299081756702/Gtech.png')
        embed.add_field(name = "Author:", value=f'{news["author"]} ({news["kelas"]})', inline=False)
        embed.add_field(name = "Deskripsi:", value=news['desc'], inline=False)
        embed.set_author(name = "Berita Terbaru G-Tech Re'sman")
        if news['attachments'] is not None:
            embed.set_image(url = news['attachments'])
        await channel.send("*Knock, knock!* Ada yang baru nih di G-Tech!", embed = embed)

    @gtech_command.command(aliases=['reg'], description="Tambahkan pengguna ke database.")
    @app_commands.describe(user='Akun Discord anggota',
                           kelas='Kelas (Contoh: XI IPA 5)',
                           divisi = 'Divisi (Contoh: Word, Programming, Desain)',
                           nama='Nama lengkap anggota'
                        )
    @in_gtech_server()
    @check_blacklist()
    async def register(self, ctx, user:discord.Member, kelas, divisi, *, nama):
        """
        Tambahkan pengguna ke database.
        """
        db = connectdb('Gtech')
        data = db.find_one({'_id':user.id})
        if not data is None:
            return await ctx.reply('Pengguna sudah ada di database!')
        db.insert_one({'_id':user.id, 'kelas':kelas, 'divisi':divisi, 'nama':nama})
        await ctx.reply(f'`{user}` telah didaftarkan ke database G-Tech.')

    @gtech_command.command(aliases=['gtechmember'], description="Lihat info anggota G-Tech dari database.")
    @app_commands.describe(user='Anggota yang mana?')
    @app_commands.rename(user='anggota')
    @in_gtech_server()
    @is_member_check()
    @check_blacklist()
    async def member(self, ctx, *, user:discord.Member = None):
        """
        Lihat info anggota G-Tech dari database.
        """
        user = user or ctx.author
        data = self.is_member(user.id)
        if data is None:
            return await ctx.reply('Pengguna belum ada di database!')
        nama = data['nama']
        kelas = data['kelas']
        divisi = data['divisi']
        e = discord.Embed(title="G-Tech Member Info", color=user.colour)
        e.set_thumbnail(url=user.display_avatar.url)
        e.description = f"**Nama:** {nama}\n**Kelas:** {kelas}\n**Divisi:** {divisi}"
        await ctx.reply(embed = e)

    @gtech_command.command(aliases=['erreg', 'unreg', 'unregister'], description="Hapus data anggota dari database.")
    @app_commands.describe(user='Pengguna yang ingin dihapus datanya.')
    @is_perangkat()
    @in_gtech_server()
    @check_blacklist()
    async def erasemember(self, ctx:commands.Context, *, user:discord.Member = None):
        """
        Hapus data anggota dari database.
        """
        user = user or ctx.author
        db = connectdb('Gtech')
        data = db.find_one({'_id':user.id})
        if data is None:
            return await ctx.reply('Pengguna belum ada di database!')
        db.find_one_and_delete({'_id':user.id})
        await ctx.reply(f'{user} telah dihapus dari database G-Tech.')


    @gtech_command.command(description="Post sesuatu yang menarik ke channel pengumuman! "+
                                "Format: Judul | Deskripsi"
    )
    @app_commands.describe(content="Apa yang ingin disampaikan? Format: Judul | Deskripsi")
    @is_perangkat()
    @in_gtech_server()
    @is_member_check()
    @check_blacklist()
    async def post(self, ctx, *, content:str):
        """
        Post sesuatu yang menarik ke channel pengumuman!
        """
        db = connectdb('Technews')
        oldnews = db.find_one({'_id':1})
        attachment = ctx.message.attachments or None
        if attachment is not None:
            attachment = attachment[0].url
        data = self.is_member(ctx.author.id)
        texts = content.split(' | ')
        title = texts[0]
        desc = texts[1]
        if oldnews is None:
            db.insert_one({'_id':1, 'author':data["nama"], 'kelas':data["kelas"], 'title':title, 'desc':desc, 'attachments':attachment})
        else:
            db.find_one_and_replace({'_id':1}, {'author':data["nama"], 'kelas':data["kelas"], 'title':title, 'desc':desc, 'attachments':attachment})
        await ctx.reply('Berita baru telah diposting!')
        await self.send_news(997749511432712263)

    @gtech_command.command(description="Lihat berita terbaru tentang G-Tech!")
    @in_gtech_server()
    @is_member_check()
    @check_blacklist()
    async def news(self, ctx:commands.Context):
        """
        Lihat berita terbaru tentang G-Tech!
        """
        db = connectdb('Technews')
        news = db.find_one({'_id':1})
        if news is None:
            return await ctx.reply('Saat ini belum ada berita baru untuk G-Tech Re\'sman, stay tuned!')
        embed = discord.Embed(title=news['title'], color = 0xff0000)
        embed.set_thumbnail(url = getenv('gtechlogo'))
        embed.add_field(name = "Author:", value=f'{news["author"]} ({news["kelas"]})', inline=False)
        embed.add_field(name = "Deskripsi:", value=news['desc'], inline=False)
        embed.set_author(name = "Berita Terbaru G-Tech Re'sman")
        if news['attachments'] is not None:
            embed.set_image(url = news['attachments'])
        await ctx.reply(embed = embed)

    @gtech_command.command(aliases = ['rmnews'], description="Hapus berita terbaru dari database.")
    @is_perangkat()
    @in_gtech_server()
    @check_blacklist()
    async def deletenews(self, ctx:commands.Context):
        """
        Hapus berita terbaru dari database.
        """
        db = connectdb('Technews')
        data = self.is_member(ctx.author.id)
        if data is None:
            return await ctx.reply('Tolong daftarkan akun Discordmu ke database terlebih dahulu!')
        db.find_one_and_delete({'_id':1})
        await ctx.reply('Berita terakhir telah dihapus.')

async def setup(bot):
    await bot.add_cog(GTech(bot))