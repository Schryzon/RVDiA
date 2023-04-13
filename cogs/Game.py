import discord
import datetime
import time
from discord import app_commands
from discord.ext import commands
from scripts.main import connectdb, check_blacklist, has_registered

class Game(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name='game')
    @check_blacklist()
    async def game(self, ctx:commands.Context):
        """
        Kumpulan command game RPG RVDIA. [GROUP]
        """
        # Account info command here
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
            'last_login':datetime.datetime.now(),
            'coins':100,
            'karma':10,             # Luck points
            'attack':50,
            'defense':20,
            'agility':20,
            'special_skills':[],    # Push JSON to here
            'items':[]              # Push it to here also
        })
        await ctx.reply(f'Akunmu sudah didaftarkan!\nSelamat datang di Land of Revolution, **`{name}`**!')
    
    @game.command(description='Menghapus akunmu dari Land of Revolution.')
    @has_registered()
    @check_blacklist()
    async def resign(self, ctx:commands.Context):
        """
        Menghapus akunmu dari Land of Revolution.
        """
        # Maybe add a confirmation button soon.
        database = connectdb('Game')
        database.find_one_and_delete({'_id':ctx.author.id})
        await ctx.reply('Aku telah menghapus akunmu.\nSampai berjumpa lagi di Land of Revolution!')

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

        if delta_time.total_seconds() >= 24*60*60:
            next_login = last_login + datetime.timedelta(hours=24)
            next_login_unix = int(time.mktime(next_login.timetuple()))
            return await ctx.reply(f'Kamu sudah login hari ini!\nKamu bisa login lagi pada <t:{next_login_unix}:f>')
        
        else:
            database.find_one_and_update(
                {'_id':ctx.author.id},
                {'$inc':{'coins':20, 'karma':2}, '$set':{'last_login':datetime.datetime.now()}}
            )
            return await ctx.reply(f"Login berhasil!\nKamu mendapatkan `20` bonus koin dan `2` karma!\nSekarang kamu punya {data['coins']+20} koin dan {data['karma']+2} karma!")


async def setup(bot):
    await bot.add_cog(Game(bot))