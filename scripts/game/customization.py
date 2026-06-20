import discord
from enum import Enum
from prisma import Json
from scripts.main import db
from scripts.utils.i18n import i18n
from scripts.game.profile import get_user_lang

class StatType(str, Enum):
    ATK = "ATK"
    DEF = "DEF"
    AGL = "AGL"

async def execute_class_selection(ctx, class_name: str):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id})
    if not user_record:
        msg = i18n.get(lang, "game.profile_not_registered")
        return await ctx.reply(msg)
        
    data = user_record.data
    current_class = data.get('class', 'None')
    if current_class != 'None':
        msg = i18n.get(lang, "game.class_already_selected", class_name=current_class)
        return await ctx.reply(msg)
        
    class_name_lower = class_name.lower()
    if class_name_lower not in ["warrior", "mage", "rogue"]:
        msg = i18n.get(lang, "game.class_invalid")
        return await ctx.reply(msg)
        
    hp_adjustment = 0
    atk_adjustment = 0
    def_adjustment = 0
    agl_adjustment = 0
    
    if class_name_lower == "warrior":
        hp_adjustment = 30
        atk_adjustment = 5
        def_adjustment = 3
        class_display = "Warrior"
    elif class_name_lower == "mage":
        hp_adjustment = -10
        atk_adjustment = 10
        agl_adjustment = 2
        class_display = "Mage"
    elif class_name_lower == "rogue":
        hp_adjustment = 10
        atk_adjustment = 3
        agl_adjustment = 8
        class_display = "Rogue"
        
    data['class'] = class_display
    data['attack'] = data.get('attack', 10) + atk_adjustment
    data['defense'] = data.get('defense', 7) + def_adjustment
    data['agility'] = data.get('agility', 8) + agl_adjustment
    
    # Retroactive points: 5 points per level beyond level 1
    level = data.get('level', 1)
    retroactive_points = (level - 1) * 5
    data['stat_points'] = data.get('stat_points', 0) + retroactive_points
    
    new_max_hp = user_record.max_hp + hp_adjustment
    new_hp = min(user_record.hp, new_max_hp)
    
    await db.user.update(
        where={'id': ctx.author.id},
        data={
            'max_hp': new_max_hp,
            'hp': new_hp,
            'data': Json(data)
        }
    )
    
    msg = i18n.get(
        lang, 
        "game.class_select_success", 
        class_name=class_display, 
        points=retroactive_points,
        hp=hp_adjustment,
        atk=atk_adjustment,
        def_=def_adjustment,
        agl=agl_adjustment
    )
    await ctx.reply(msg)

async def execute_allocate_points(ctx, stat: StatType, amount: int):
    lang = await get_user_lang(ctx.author.id)
    if amount <= 0:
        msg = i18n.get(lang, "game.allocate_invalid_amount")
        return await ctx.reply(msg)
        
    user_record = await db.user.find_unique(where={'id': ctx.author.id})
    if not user_record:
        msg = i18n.get(lang, "game.profile_not_registered")
        return await ctx.reply(msg)
        
    data = user_record.data
    available_points = data.get('stat_points', 0)
    if available_points < amount:
        msg = i18n.get(lang, "game.allocate_insufficient_points", available=available_points)
        return await ctx.reply(msg)
        
    stat_str = stat.value.upper()
    if stat_str == "ATK":
        data['attack'] = data.get('attack', 10) + amount
        stat_name = "Attack"
    elif stat_str == "DEF":
        data['defense'] = data.get('defense', 7) + amount
        stat_name = "Defense"
    elif stat_str == "AGL":
        data['agility'] = data.get('agility', 8) + amount
        stat_name = "Agility"
    else:
        msg = i18n.get(lang, "game.allocate_invalid_stat")
        return await ctx.reply(msg)
        
    data['stat_points'] = available_points - amount
    
    await db.user.update(
        where={'id': ctx.author.id},
        data={'data': Json(data)}
    )
    
    msg = i18n.get(
        lang, 
        "game.allocate_success", 
        amount=amount, 
        stat=stat_name, 
        remaining=data['stat_points']
    )
    await ctx.reply(msg)
