import discord
import asyncio
from datetime import datetime
from discord.ext import commands
from prisma import Json
from scripts.main import db
from scripts.errors import AccountIncompatible

default_data = {
    'name':'Player',
    'level':1,
    'exp':0,
    'next_exp':50,
    'last_login': datetime.now().isoformat(),
    'coins':100,
    'karma':10,             # Luck points
    'attack':10,
    'defense':7,
    'agility':8,
    'items':{},
    'special_skills':[],
    'equipments':[]
}

async def level_up(ctx):
    user_id = ctx.id if isinstance(ctx, discord.Member) else ctx.author.id
    user = await db.user.find_unique(where={'id': user_id})
    if not user:
        return False
        
    data = user.data
    current_exp = data['exp']
    next_exp = data['next_exp']
    user_level = data['level']

    if current_exp >= next_exp:
        user_level += 1
        new_next_exp = round(50 * (1.2**(user_level-1)))
        
        data['exp'] = 0
        data['next_exp'] = new_next_exp
        data['level'] = user_level
        data['attack'] += 2
        data['defense'] += 2
        data['agility'] += 2
        
        # Also increase HP and Max HP
        new_hp = user.max_hp + 20
        
        await db.user.update(
            where={'id': user_id},
            data={
                'data': Json(data),
                'hp': new_hp,
                'max_hp': new_hp
            }
        )
        return True
    
    return False

async def send_level_up_msg(ctx:commands.Context, user:discord.Member = None):
    user_id = user.id if user else ctx.author.id
    user_data = await db.user.find_unique(where={'id': user_id})
    
    next_exp = user_data.data['next_exp']
    user_level = user_data.data['level']
    
    target = user if user else ctx.author
    return await ctx.channel.send(f'Selamat, {target.mention}!\nKamu telah naik ke level `{user_level}`!\nEXP selanjutnya: `{next_exp}`')

def split_reward_string(rewards:list):
    array = []
    for reward in rewards:
        array.append(int(reward.split('+')[1]))
    return array

async def give_rewards(ctx:commands.Context, user:discord.Member, exp:int, coins:int, karma:int=0):
    user_record = await db.user.find_unique(where={'id': user.id})
    if not user_record:
        return
        
    data = user_record.data
    data['exp'] += exp
    data['coins'] += coins
    data['karma'] += karma
    
    await db.user.update(
        where={'id': user.id},
        data={'data': Json(data)}
    )
    
    level_uped = await level_up(user)
    if level_uped:
        return await send_level_up_msg(ctx, user)
    
def check_compatible():
    async def predicate(ctx:commands.Context):
        # With Prisma and JSONB, we are more flexible, but we can still check for keys if needed.
        # For now, let's just ensure the account exists.
        user = await db.user.find_unique(where={'id': ctx.author.id})
        if not user:
            return False
        return True
    return commands.check(predicate)