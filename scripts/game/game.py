import discord
import asyncio
from datetime import datetime, timezone
from discord.ext import commands
from prisma import Json
from scripts.main import db
from scripts.utils.errors import AccountIncompatible, NoGameAccount, NoClassSelected

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
    'equipments':[],
    'class':'None',
    'stat_points':0
}

async def level_up(ctx):
    if hasattr(ctx, 'author'):
        user_id = ctx.author.id
    elif hasattr(ctx, 'user'):
        user_id = ctx.user.id
    elif hasattr(ctx, 'id'):
        user_id = ctx.id
    else:
        return False
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
        # Grant 5 stat points per level
        data['stat_points'] = data.get('stat_points', 0) + 5
        
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

def split_reward_string(rewards: list):
    """
    Parses a list of reward strings like ['exp+100', 'cns+50', 'krm-10']
    Returns a list of values: [exp, coins, karma]
    """
    res = {"exp": 0, "cns": 0, "krm": 0}
    for r in rewards:
        if '+' in r:
            parts = r.split('+')
            res[parts[0]] = int(parts[1])
        elif '-' in r:
            parts = r.split('-')
            res[parts[0]] = -int(parts[1])
    
    return [res["exp"], res["cns"], res["krm"]]

async def give_rewards(ctx:commands.Context, user:discord.Member, exp:int, coins:int, karma:int=0):
    user_record = await db.user.find_unique(where={'id': user.id})
    if not user_record:
        return
        
    # Premium Bonus (2x)
    is_premium = user_record.premiumUntil and user_record.premiumUntil > datetime.now(timezone.utc)
    if is_premium:
        exp *= 2
        coins *= 2
        
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
        user = await db.user.find_unique(where={'id': ctx.author.id})
        if not user:
            raise NoGameAccount('User has no game account!')
        
        data = user.data
        if not isinstance(data, dict):
            raise AccountIncompatible('Invalid account format!')
            
        level = data.get('level', 1)
        player_class = data.get('class', 'None')
        if level > 1 and player_class == 'None':
            raise NoClassSelected('User must choose a class!')
            
        return True
    return commands.check(predicate)