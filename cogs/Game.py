import discord
import datetime
import time
import random
from os import getenv
from discord.ui import View, Button
from discord import app_commands
from discord.ext import commands
from scripts.main import connectdb, check_blacklist, has_registered, level_up, send_level_up_msg

class ResignButton(View):
    def __init__(self, ctx):
        super().__init__(timeout=20)

        delete_account = Button(
            style=discord.ButtonStyle.danger,
            label='Hapus Akun',
            custom_id='delacc'
        )
        cancel = Button(
            style=discord.ButtonStyle.green,
            label='Batalkan',
            custom_id='canceldel'
        )
        self.add_item(delete_account)
        self.add_item(cancel)
        self.ctx = ctx

    async def check_interaction(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Kamu tidak diperbolehkan berinteraksi dengan tombol ini!", ephemeral=True)
            return False
        
        return True
    
    async def on_button_click(self, interaction: discord.Interaction, view):
        try:
            custom_id = interaction.data['custom_id']
            match custom_id:
                case 'delacc':
                    database = connectdb('Game')
                    data = database.find_one({'_id':interaction.user.id})
                    database.find_one_and_delete({'_id':interaction.user.id})
                    await interaction.response.send_message(f'Aku telah menghapus akunmu.\nSampai jumpa, `{data["name"]}`, di Land of Revolution!')

                case 'canceldel':
                    await interaction.response.send_message('Penghapusan akun dibatalkan.')

                case _:
                    pass

            for item in interaction.message.components:
                for button in item.children:
                    button.disabled=True

            await interaction.message.edit(view=view)\
            
        except Exception as e:
            print(e)

class Game(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name='game')
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
        try:
            view = ResignButton(ctx)
            await ctx.send('Apakah kamu yakin akan menghapus akunmu?\nKamu punya 20 detik untuk menentukan keputusanmu.', view=view)
            interaction = await self.bot.wait_for("button_click", check=view.check_interaction)
            await view.on_button_click(interaction, view)

        except Exception as e:
            print(e)

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
            embed.set_footer('Bonus selanjutnya pada: ')
            await ctx.reply(embed=embed)

            if level_up(ctx):
                return await send_level_up_msg(ctx)
            
    @game.command(description='Lihat profil pengguna di Land of Revolution! (UNFINISHED)')
    @app_commands.describe(user='Pengguna mana yang ingin dilihat akunnya?')
    @app_commands.rename(user='pengguna')
    @has_registered()
    @check_blacklist()
    async def account(self, ctx:commands.Context, *, user:discord.User=None):
        """
        Lihat profil pengguna di Land of Revolution! (UNFINISHED)
        """
        await ctx.send('Command ini masih dalam proses pembuatan! Mohon ditunggu ya!')


async def setup(bot):
    await bot.add_cog(Game(bot))