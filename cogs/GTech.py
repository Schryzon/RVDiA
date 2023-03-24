import discord
from discord.ext import commands
from scripts.main import connectdb, in_gtech_server, is_member_check, is_perangkat

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
    async def gtech_command(self, ctx:commands.Context) -> None:
        """
        Kumpulan command khusus untuk anggota G-Tech Re'sman.
        """
        pass

    async def send_news(self, channel_id:int):
        db = connectdb("Technews")
        news = db.find_one({'_id':1})
        channel = self.bot.get_channel(channel_id)
        embed = discord.Embed(title=news['title'], color = 0xff0000)
        embed.set_thumbnail(url = 'https://cdn.discordapp.com/attachments/872815705475666007/974638299081756702/Gtech.png')
        embed.add_field(name = "Author:", value=f'{news["author"]} ({news["kelas"]})', inline=False)
        embed.add_field(name = "Description:", value=news['desc'], inline=False)
        embed.set_author(name = "Latest News of G-Tech Resman")
        if news['attachments'] is not None:
            embed.set_image(url = news['attachments'])
        await channel.send("*Knock, knock!* Ada yang baru nih di G-Tech!", embed = embed)

    @gtech_command.command(aliases=['reg'], description="Tambahkan pengguna ke database.")
    @is_perangkat()
    @in_gtech_server()
    async def register(self, ctx, user:commands.MemberConverter, kelas, divisi, *, nama):
        """
        Tambahkan pengguna ke database.
        """
        db = connectdb('Gtech')
        data = db.find_one({'_id':user.id})
        if not data is None:
            return await ctx.reply('User already registered in database!')
        db.insert_one({'_id':user.id, 'kelas':kelas, 'divisi':divisi, 'nama':nama})
        await ctx.reply(f'User {user} has been registered to the G-Tech database.')

    @gtech_command.command(aliases=['gtechmember'], description="Lihat status anggota G-Tech dari database.")
    @in_gtech_server()
    @is_member_check()
    async def member(self, ctx, *, user:commands.MemberConverter = None):
        """
        Lihat status anggota G-Tech dari database.
        """
        user = user or ctx.author
        data = self.is_member(user.id)
        if data is None:
            return await ctx.reply('User is not in database yet!')
        nama = data['nama']
        kelas = data['kelas']
        divisi = data['divisi']
        e = discord.Embed(title="G-Tech Member Info", color=user.colour)
        e.set_thumbnail(url=user.avatar.url)
        e.description = f"Nama: {nama}\nKelas: {kelas}\nDivisi: {divisi}"
        await ctx.reply(embed = e)

    @gtech_command.command(aliases=['erreg', 'unreg', 'unregister'], description="Removes a registered user data.\nOnly G-Tech admins are allowed to use this command.")
    @is_perangkat()
    @in_gtech_server()
    async def erasemember(self, ctx, *, user:commands.MemberConverter = None):
        """
        Hapus data anggota dari database.
        """
        user = user or ctx.author
        db = connectdb('Gtech')
        data = db.find_one({'_id':user.id})
        if data is None:
            return await ctx.reply('User is not in database yet!')
        db.find_one_and_delete({'_id':user.id})
        await ctx.reply(f'{user} has been deleted from the G-Tech database.')


    @gtech_command.command(description="Post sesuatu yang menarik ke channel pengumuman!\n"+
                                "Format: Judul | Deskripsi"
    )
    @is_perangkat()
    @in_gtech_server()
    @is_member_check()
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
        await ctx.reply('Successfully posted a *new* news!')
        await self.send_news(997749511432712263)

    @gtech_command.command(description="Lihat berita terbaru tentang G-Tech!")
    @in_gtech_server()
    @is_member_check()
    async def news(self, ctx):
        """
        Lihat berita terbaru tentang G-Tech!
        """
        db = connectdb('Technews')
        news = db.find_one({'_id':1})
        if news is None:
            return await ctx.reply('There are currently no news for G-Tech Resman, please stay tuned.')
        embed = discord.Embed(title=news['title'], color = 0xff0000)
        embed.set_thumbnail(url = 'https://cdn.discordapp.com/attachments/872815705475666007/974638299081756702/Gtech.png')
        embed.add_field(name = "Author:", value=f'{news["author"]} ({news["kelas"]})', inline=False)
        embed.add_field(name = "Description:", value=news['desc'], inline=False)
        embed.set_author(name = "Latest News of G-Tech Resman")
        if news['attachments'] is not None:
            embed.set_image(url = news['attachments'])
        await ctx.reply(embed = embed)

    @gtech_command.command(aliases = ['rmnews'], description="Hapus berita terbaru dari database.")
    @is_perangkat()
    @in_gtech_server()
    async def deletenews(self, ctx):
        """
        Hapus berita terbaru dari database.
        """
        db = connectdb('Technews')
        data = self.is_member(ctx.author.id)
        if data is None:
            return await ctx.reply('Please register a G-Tech member account to remove news from the G-Tech API!')
        db.find_one_and_delete({'_id':1})
        await ctx.reply('The latest news has been deleted.')

async def setup(bot):
    await bot.add_cog(GTech(bot))