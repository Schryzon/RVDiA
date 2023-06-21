import discord
import asyncio
from discord.ext import commands
from scripts.main import connectdb

def level_up(ctx):
    database = connectdb('Game')
    if isinstance(ctx, discord.Member):
        data = database.find_one({'_id':ctx.id})
    else:
        data = database.find_one({'_id':ctx.author.id})
    current_exp = data['exp']
    next_exp = data['next_exp']
    user_level = data['level']


    if current_exp >= next_exp:
        calculated_exp = 50 * (1.2**(user_level-1))     # new exp = base exp * (factor ^ (current level - 1))
        if isinstance(ctx, discord.Member):
            database.find_one_and_update({'_id':ctx.id}, {'$set':{'exp':0, 'next_exp':calculated_exp, 'level':user_level+1}})
        else:
            database.find_one_and_update({'_id':ctx.author.id}, {'$set':{'exp':0, 'next_exp':calculated_exp, 'level':user_level+1}})
        return True
    
    return False

async def send_level_up_msg(ctx:commands.Context, user:discord.Member = None):
    database = connectdb('Game')
    if user is None:
        data = database.find_one({'_id':ctx.author.id})
    else:
        data = database.find_one({'_id':user.id})
    next_exp = data['next_exp']
    user_level = data['level']
    if user:
        return await ctx.channel.send(f'Selamat, {user.mention}!\nKamu telah naik ke level `{user_level}`!\nEXP selanjutnya: `{next_exp}`')
    else:
        return await ctx.channel.send(f'Selamat, {ctx.author.mention}!\nKamu telah naik ke level `{user_level}`!\nEXP selanjutnya: `{next_exp}`')

    

def split_reward_string(rewards:list):
    array = []
    for reward in rewards:
        array.append(int(reward.split('+')[1]))
    return array

async def give_rewards(ctx:commands.Context, user:discord.Member, exp:int, coins:int, karma:int=0):
    database = connectdb('Game')
    database.find_one_and_update(
        {'_id':user.id},
        {'$inc':{'exp':exp, 'coins':coins, 'karma':karma}}
    )
    await asyncio.sleep(1.5)
    if level_up(user):
        return await send_level_up_msg(ctx, user)