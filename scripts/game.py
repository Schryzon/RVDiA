import discord
import asyncio
from datetime import datetime
from discord.ext import commands
from scripts.main import connectdb
from cogs.Handler import AccountIncompatible

default_data = {
    '_id':12345,
    'name':'asdf',
    'level':1,
    'exp':0,
    'next_exp':50,
    'last_login':datetime.now(),
    'coins':100,
    'karma':10,             # Luck points
    'attack':10,
    'defense':7,
    'agility':8,
    'items':[],
    'equipments':[],        # Push it to here also
    'guild':None
    # Add more here
}

async def level_up(ctx):
    database = await connectdb('Game')
    if isinstance(ctx, discord.Member):
        data = await database.find_one({'_id':ctx.id})
    else:
        data = await database.find_one({'_id':ctx.author.id})
    current_exp = data['exp']
    next_exp = data['next_exp']
    user_level = data['level']


    if current_exp >= next_exp:
        calculated_exp = round(50 * (1.2**(user_level-1)))     # new exp = base exp * (factor ^ (current level - 1))
        if isinstance(ctx, discord.Member):
            await database.find_one_and_update({'_id':ctx.id}, {'$set':{'exp':0, 'next_exp':calculated_exp, 'level':user_level+1}, 
                                                          '$inc':{'attack':2, 'defense':2, 'agility':2}})
        else:
            await database.find_one_and_update({'_id':ctx.author.id}, {'$set':{'exp':0, 'next_exp':calculated_exp, 'level':user_level+1}})
        return True
    
    return False

async def send_level_up_msg(ctx:commands.Context, user:discord.Member = None):
    database = await connectdb('Game')
    if user is None:
        data = await database.find_one({'_id':ctx.author.id})
    else:
        data = await database.find_one({'_id':user.id})
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
    database = await connectdb('Game')
    await database.find_one_and_update(
        {'_id':user.id},
        {'$inc':{'exp':exp, 'coins':coins, 'karma':karma}}
    )
    level_uped = await level_up(user)
    if level_uped:
        return await send_level_up_msg(ctx, user)
    
def check_compatible():
    """
    Check Re:Volution account compatibility
    """
    async def predicate(ctx:commands.Context):
        default_keys = len(default_data)
        database = await connectdb('Game')
        data = await database.find_one({'_id':ctx.author.id})
        user_keys = len(data)
        if default_keys != user_keys:
            raise AccountIncompatible("User's account is incompatible!")
        return True
    return commands.check(predicate)