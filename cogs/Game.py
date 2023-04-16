import discord
import datetime
import time
import random
import json
from os import getenv
from discord.ui import View, Button, button
from discord import app_commands
from discord.ext import commands
from scripts.main import connectdb, check_blacklist, has_registered, level_up, send_level_up_msg

class ResignButton(View):
    def __init__(self, ctx:commands.Context):
        super().__init__(timeout=20)
        self.ctx = ctx
        self.value = None

    @button(label='Hapus Akun', style=discord.ButtonStyle.danger, custom_id='delacc')
    async def delete_account(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Kamu tidak diperbolehkan berinteraksi dengan tombol ini!", ephemeral=True)
            return
        database = connectdb('Game')
        data = database.find_one({'_id':interaction.user.id})
        database.find_one_and_delete({'_id':interaction.user.id})
        await interaction.response.send_message(f'Aku telah menghapus akunmu.\nSampai jumpa, `{data["name"]}`, di Land of Revolution!')
        self.value = True
        self.stop()

    @button(label='Batalkan', style=discord.ButtonStyle.green, custom_id='canceldel')
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Kamu tidak diperbolehkan berinteraksi dengan tombol ini!", ephemeral=True)
            return
        await interaction.response.send_message('Penghapusan akun dibatalkan.')
        self.value = False
        self.stop()

class ShopDropdown(discord.ui.Select):
    def __init__(self, ctx:commands.Context, page:int):
        self.ctx = ctx
        self.page = page

        with open('./src/game/shop.json') as file:
            content = file.read()
            items = json.loads(content)

        options = []
        for index, item in enumerate(items):
            if not index > 5:
                options.append(discord.SelectOption(
                                label = f"{index}. {item['name']}", 
                                description=f"Harga: {item['cost']} {item['paywith']}", 
                                value=item['_id']
                                )
                            )

        super().__init__(custom_id="shopdrop", placeholder="Mau beli apa?", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        with open('./src/game/shop.json') as file:
            content = file.read()
            items = json.loads(content)

        item_id = self.values[0]
        database = connectdb('Game')
        data = database.find_one({'_id':interaction.user.id})
        db_dict = {item['_id']: item for item in items}
        mongo_dict = {item['_id']: item for item in data['items']}
        if item_id in db_dict and item_id in mongo_dict: # User already bought this item in the past
            matched_dict = db_dict[item_id]
            currency = 'items.$.coins' if matched_dict['paywith'] == "Koin" else 'items.$.karma'
            cost = matched_dict['cost']
            filter_ = {'_id': interaction.user.id, 'items': {'$elemMatch': {'_id': item_id}}}
            update_ = {'$inc': {'items.$.owned': 1, currency: cost*-1}}
            database.find_one_and_update(filter=filter_, update=update_)
            await interaction.response.send_message(f"Pembelian berhasil!\nKamu telah membeli `{matched_dict['name']}`")

        else:
            matched_dict = db_dict[item_id]
            currency = 'items.$.coins' if matched_dict['paywith'] == "Koin" else 'items.$.karma'
            cost = matched_dict['cost']
            del matched_dict['cost']
            del matched_dict['paywith']
            matched_dict['owned'] = 1
            database.find_one_and_update({'_id': interaction.user.id}, {'$push':{'items':matched_dict}, '$inc':{currency: cost*-1}})
            await interaction.response.send_message(f"Pembelian berhasil!\nKamu telah membeli `{matched_dict['name']}`")

class ShopView(View):
    def __init__(self, ctx, page):
        self.ctx = ctx
        self.page = page
        super().__init__(timeout=20)
        self.add_item(ShopDropdown(self.ctx, self.page))

class Game(commands.Cog):
    """
    Kumpulan command game RPG RVDIA (Land of Revolution).
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name='game')
    @has_registered()
    @check_blacklist()
    async def game(self, ctx:commands.Context, *, user:discord.User=None):
        """
        Kumpulan command game RPG RVDIA. [GROUP]
        """
        user = user or ctx.author
        await self.account(ctx, user=user)
        pass

    @game.command(aliases=['reg'], description='Daftarkan akunmu ke Land of Revolution!')
    @app_commands.describe(name='Nama apa yang ingin kamu pakai di dalam gamenya?')
    @check_blacklist()
    async def register(self, ctx:commands.Context, *, name:str=None):
        """
        Daftarkan akunmu ke Land of Revolution!
        """
        name=name or ctx.author.name
        database = connectdb('Game')
        data = database.find_one({'_id':ctx.author.id})
        if data: return await ctx.reply('Kamu sudah memiliki akun game!')
        database.insert_one({
            '_id':ctx.author.id,
            'name':name,
            'level':1,
            'exp':0,
            'next_exp':50,
            'last_login':datetime.datetime.now(),
            'coins':100,
            'karma':10,             # Luck points
            'attack':50,
            'defense':20,
            'agility':20,
            'special_skills':[],    # Push JSON to here
            'items':[],
            'equipments':[]         # Push it to here also
        })
        await ctx.reply(f'Akunmu sudah didaftarkan!\nSelamat datang di Land of Revolution, **`{name}`**!')
    
    @game.command(description='Menghapuskan akunmu dari Land of Revolution.')
    @has_registered()
    @check_blacklist()
    async def resign(self, ctx:commands.Context):
        """
        Menghapuskan akunmu dari Land of Revolution.
        """
        view = ResignButton(ctx)
        await ctx.reply('Apakah kamu yakin akan menghapus akunmu?\nKamu punya 20 detik untuk menentukan keputusanmu.', view=view)
        await view.wait()
        if view.value is None:
            await ctx.channel.send('Waktu habis, penghapusan akun dibatalkan.')

    @game.command(aliases=['login'], description='Dapatkan bonus login harian!')
    @has_registered()
    @check_blacklist()
    async def daily(self, ctx:commands.Context):
        """
        Dapatkan bonus login harian!
        """
        database = connectdb('Game')
        data = database.find_one({'_id':ctx.author.id})
        last_login = data['last_login']
        current_time = datetime.datetime.now()
        delta_time = current_time - last_login

        next_login = last_login + datetime.timedelta(hours=24)
        next_login_unix = int(time.mktime(next_login.timetuple()))

        if delta_time.total_seconds() <= 24*60*60:
            return await ctx.reply(f'Kamu sudah login hari ini!\nKamu bisa login lagi pada <t:{next_login_unix}:f>')
        
        else:
            new_coins = random.randint(15, 25)
            new_karma = random.randint(1, 5)
            new_exp = random.randint(10, 20)
            database.find_one_and_update(
                {'_id':ctx.author.id},
                {'$inc':{'coins':new_coins, 'karma':new_karma, 'exp':new_exp}, '$set':{'last_login':datetime.datetime.now()}}
            )
            embed = discord.Embed(title='Bonus Harianmu', color=0x00FF00, timestamp=next_login)
            embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else getenv('normalpfp'))
            embed.description = f'Kamu mendapatkan:\n`{new_coins}` koin;\n`{new_karma}` karma;\n`{new_exp}` EXP!'
            embed.set_footer(text='Bonus selanjutnya pada ')
            await ctx.reply(embed=embed)

            if level_up(ctx):
                return await send_level_up_msg(ctx)
            
    @game.command(description='Lihat profil pengguna di Land of Revolution!')
    @app_commands.describe(user='Pengguna mana yang ingin dilihat akunnya?')
    @app_commands.rename(user='pengguna')
    @has_registered()
    @check_blacklist()
    async def account(self, ctx:commands.Context, *, user:discord.User=None):
        """
        Lihat profil pengguna di Land of Revolution!
        """
        # Plans: PIL profile pic, equipment & items should be seperate commands
        user = user or ctx.author
        database = connectdb('Game')
        data = database.find_one({'_id':user.id})

        # General data
        player_name = data['name']
        level = data['level']
        exp, next_exp = data['exp'], data['next_exp']
        last_login = data['last_login']

        # Stats & economy
        coins = data['coins']
        karma = data['karma']

        # Battle stats
        attack, defense, agility = data['attack'], data['defense'], data['agility']
        special_skills = data['special_skills']

        embed = discord.Embed(title=player_name, timestamp=last_login)
        embed.set_author(name='Info Akun Land of Revolution:')
        embed.description = f'Alias: {user}'
        embed.set_thumbnail(url=user.avatar.url if user.avatar else getenv('normalpfp'))

        embed.add_field(
            name=f'Level {level}', 
            value=f'EXP: `{exp}`/`{next_exp}`', 
            inline=False
            )

        embed.add_field(
            name=f'Status Keuangan',
            value=f'Koin: `{coins}`\nKarma: `{karma}`', 
            inline=False
            )

        embed.add_field(
            name=f'Statistik Tempur', 
            value=f'Attack: `{attack}`\nDefense: `{defense}`\nAgility: `{agility}`', 
            inline=False
            )
        
        embed.add_field(
            name='Skill Spesial',
            value=', '.join(special_skills) if not special_skills == [] else "Belum ada dikuasai.",
            inline=False
        )
        
        embed.set_footer(text='Login harian terakhir ')
        await ctx.reply(embed = embed)

    @game.command(description="Beli item atau perlengkapan perang! (ON PROGRESS)")
    @has_registered()
    @check_blacklist()
    async def shop(self, ctx:commands.Context):
        """
        Beli item atau perlengkapan perang! (ON PROGRESS)
        """
        # Plans: show details and make a paginator or something
        database = connectdb('Game')
        data = database.find_one({'_id':ctx.author.id})
        with open('./src/game/shop.json') as file:
            content = file.read()
            items = json.loads(content)

        embed = discord.Embed(title = 'Selamat datang di toko Xaneria', color=0xFFFF00)
        embed.description='"Belilah apa saja, tapi jangan sampai kau jadi miskin."'
        embed.set_footer(text='Untuk membeli sebuah item, klik di bawah ini! v')
        iix = []
        for index, item in enumerate(items):
            index = index+1
            if not index > 5:
                try:
                    for key in data:
                        if key['id'] == item['id']:
                            owned = key['owned']
                except:
                    owned = 0

                embed.add_field(
                    name=f"{index}. {item['name']}", 
                    value=f"**`{item['desc']}`**\nTipe: {item['type']}\nHarga: {item['cost']} {item['paywith']}\nDimiliki: {owned}",
                    inline=False
                )
                iix.append(index)
        
        match max(iix):
            case 5:
                page = 1

            case _:
                page = 1

        view = ShopView(ctx, page)
        await ctx.reply(embed = embed, view=view)


async def setup(bot):
    await bot.add_cog(Game(bot))