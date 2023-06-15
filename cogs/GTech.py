"""
Experimental Cog, for the future.
"""
from os import getenv
import discord
from discord import app_commands
from discord.ext import commands
from scripts.main import connectdb, in_gtech_server, is_member_check, is_perangkat, check_blacklist

class GTech(commands.GroupCog, group_name='gtech'):
    """
    Kategori khusus bagi anggota G-Tech Re'sman
    """
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    def is_member(self, id:int): #Used for gaining data only
        db = connectdb("Gtech")
        data = db.find_one({'_id':id})
        return data

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

    @app_commands.command(description="Tambahkan pengguna ke database.")
    @app_commands.describe(user='Akun Discord anggota',
                           kelas='Kelas (Contoh: XI IPA 5)',
                           divisi = 'Divisi (Contoh: Word, Programming, Desain)',
                           nama='Nama lengkap anggota'
                        )
    @in_gtech_server()
    @check_blacklist()
    async def register(self, interaction:discord.Interaction, user:discord.Member, nama:str, kelas:str, divisi:str):
        """
        Tambahkan pengguna ke database.
        """
        db = connectdb('Gtech')
        data = db.find_one({'_id':user.id})
        if not data is None:
            return await interaction.response.send_message('Pengguna sudah ada di database!', ephemeral=True)
        db.insert_one({'_id':user.id, 'kelas':kelas, 'divisi':divisi, 'nama':nama})
        await interaction.response.send_message(f'`{user}` telah didaftarkan ke database G-Tech.')

    @app_commands.command(description="Lihat info anggota G-Tech dari database.")
    @app_commands.describe(user='Anggota yang mana?')
    @app_commands.rename(user='anggota')
    @in_gtech_server()
    @is_member_check()
    @check_blacklist()
    async def member(self, interaction:discord.Interaction, user:discord.Member):
        """
        Lihat info anggota G-Tech dari database.
        """
        data = self.is_member(user.id)
        if data is None:
            return await interaction.response.send_message(f'{user} belum ada di database!', ephemeral=True)
        nama = data['nama']
        kelas = data['kelas']
        divisi = data['divisi']
        e = discord.Embed(title="Info Anggota G-Tech", color=user.colour)
        e.set_thumbnail(url=user.display_avatar.url)
        e.description = f"**Nama:** {nama}\n**Kelas:** {kelas}\n**Divisi:** {divisi}"
        await interaction.response.send_message(embed = e)

    @app_commands.command(description="Hapus data anggota dari database.")
    @app_commands.describe(user='Pengguna yang ingin dihapus datanya.')
    @is_perangkat()
    @in_gtech_server()
    @check_blacklist()
    async def erasemember(self, interaction:discord.Interaction, *, user:discord.Member):
        """
        Hapus data anggota dari database.
        """
        db = connectdb('Gtech')
        data = db.find_one({'_id':user.id})
        if data is None:
            return await interaction.response.send_message('Pengguna belum ada di database!', ephemeral=True)
        db.find_one_and_delete({'_id':user.id})
        await interaction.response.send_message(f'{user} telah dihapus dari database G-Tech.')


    @app_commands.command(description="Post sesuatu yang menarik ke channel pengumuman!")
    @app_commands.describe(title="Apa judul dari beritanya?")
    @app_commands.describe(content="Apa yang ingin disampaikan?")
    @app_commands.describe(attachment="Apakah ada gambar sebagai lampiran?")
    @app_commands.rename(title='judul')
    @app_commands.rename(content='isi')
    @app_commands.rename(attachment='lampiran')
    @is_perangkat()
    @in_gtech_server()
    @is_member_check()
    @check_blacklist()
    async def post(self, interaction:discord.Interaction, title:str, content:str, attachment:discord.Attachment=None):
        """
        Post sesuatu yang menarik ke channel pengumuman!
        """
        db = connectdb('Technews')
        oldnews = db.find_one({'_id':1})
        if attachment is not None:
            attachment = attachment.url
        data = self.is_member(interaction.user.id)
        if oldnews is None:
            db.insert_one({'_id':1, 'author':data["nama"], 'kelas':data["kelas"], 'title':title, 'desc':content, 'attachments':attachment})
        else:
            db.find_one_and_replace({'_id':1}, {'author':data["nama"], 'kelas':data["kelas"], 'title':title, 'desc':content, 'attachments':attachment})
        await interaction.response.send_message('Berita baru telah diposting!', ephemeral=True)
        await self.send_news(997749511432712263)

    @app_commands.command(description="Lihat berita terbaru tentang G-Tech!")
    @in_gtech_server()
    @is_member_check()
    @check_blacklist()
    async def news(self, interaction:discord.Interaction):
        """
        Lihat berita terbaru tentang G-Tech!
        """
        db = connectdb('Technews')
        news = db.find_one({'_id':1})
        if news is None:
            return await interaction.response.send_message('Saat ini belum ada berita baru untuk G-Tech Re\'sman, stay tuned!', ephemeral=True)
        embed = discord.Embed(title=news['title'], color = 0xff0000)
        embed.set_thumbnail(url = getenv('gtechlogo'))
        embed.add_field(name = "Author:", value=f'{news["author"]} ({news["kelas"]})', inline=False)
        embed.add_field(name = "Deskripsi:", value=news['desc'], inline=False)
        embed.set_author(name = "Berita Terbaru G-Tech Re'sman")
        if news['attachments'] is not None:
            embed.set_image(url = news['attachments'])
        await interaction.response.send_message(embed = embed)

    @app_commands.command(description="Hapus berita terbaru dari database.")
    @is_perangkat()
    @is_member_check()
    @in_gtech_server()
    @check_blacklist()
    async def deletenews(self, interaction:discord.Interaction):
        """
        Hapus berita terbaru dari database.
        """
        db = connectdb('Technews')
        data = self.is_member(interaction.user.id)
        if data is None:
            return await interaction.response.send_message('Tolong daftarkan akun Discordmu ke database terlebih dahulu!')
        db.find_one_and_delete({'_id':1})
        await interaction.response.send_message('Berita terakhir telah dihapus.', ephemeral=True)

async def setup(bot:commands.Bot):
    await bot.add_cog(GTech(bot, guilds=[
        discord.Object(872815705450483732), # AKT 16
        discord.Object(997500206511833128) # AKT 17
        # Reserved for AKT 18!
    ]))