import discord
from discord.ext import commands
from scripts.main import connectdb

def level_up(ctx:commands.Context):
    database = connectdb('Game')
    data = database.find_one({'_id':ctx.author.id})
    current_exp = data['exp']
    next_exp = data['next_exp']
    user_level = data['level']


    if current_exp >= next_exp:
        calculated_exp = 50 * (1.2**(user_level-1))     # new exp = base exp * (factor ^ (current level - 1))
        database.find_one_and_update({'_id':ctx.author.id}, {'$set':{'exp':0, 'next_exp':calculated_exp, 'level':user_level+1}})
        return True
    
    return False

async def send_level_up_msg(ctx:commands.Context):
    database = connectdb('Game')
    data = database.find_one({'_id':ctx.author.id})
    next_exp = data['next_exp']
    user_level = data['level']
    return await ctx.channel.send(f'Selamat, {ctx.author.mention}!\nKamu telah naik ke level `{user_level}`! (EXP: `{next_exp}`)')