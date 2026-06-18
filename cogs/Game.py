"""
Commands and features for her game.
Re:Volution ~ The Dream World.
An unnecessarily large file.
It doesn't need to be here, but it is.
"""

import asyncio
import re
import discord
from datetime import datetime, timedelta
import time
import random
import json
import math
import difflib
from os import getenv, listdir, path
from prisma import Json
from discord.ui import View, Button, button
from discord import app_commands
from discord.ext import commands
from scripts.main import db, has_registered, check_blacklist
from scripts.game import level_up, send_level_up_msg, split_reward_string, give_rewards, default_data, check_compatible
from scripts.i18n import i18n

async def get_user_lang(user_id: int) -> str:
    user_settings = await db.usersettings.find_unique(where={'userId': user_id})
    return user_settings.lang if user_settings else "en"

def to_key(name: str) -> str:
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s_]', '', name)
    name = re.sub(r'[\s_]+', '_', name)
    return name

class FightView(View):
    def __init__(self, lang="en"):
        super().__init__(timeout=25.0)
        self.lang = lang
        for child in self.children:
            if isinstance(child, Button):
                if child.custom_id == 'attack':
                    child.label = 'Serang' if lang == 'id' else 'Attack'
                elif child.custom_id == 'defend':
                    child.label = 'Tahan' if lang == 'id' else 'Defend'
                elif child.custom_id == 'item':
                    child.label = 'Barang' if lang == 'id' else 'Item'
                elif child.custom_id == 'skill':
                    child.label = 'Skill' if lang == 'id' else 'Skill'
                elif child.custom_id == 'self':
                    child.label = 'Diri' if lang == 'id' else 'Self'
                elif child.custom_id == 'end':
                    child.label = 'Kabur' if lang == 'id' else 'Flee'
                elif child.custom_id == 'check':
                    child.label = 'Musuh' if lang == 'id' else 'Enemy'
                elif child.custom_id == 'skip':
                    child.label = 'Lewati' if lang == 'id' else 'Skip'

    async def _handle_click(self, interaction: discord.Interaction, button: Button):
        if interaction.message.mentions[0] != interaction.user:
            msg = i18n.get(self.lang, "game.resign_button_not_allowed")
            return await interaction.response.send_message(msg, ephemeral=True)
        prefix = "Option selected: " if self.lang == "en" else "Opsi terpilih: "
        await interaction.response.send_message(f"{prefix}{button.emoji}{button.label}")
        await asyncio.sleep(0.5)
        await interaction.message.delete(delay=5)

    @button(label='Serang', custom_id='attack', style=discord.ButtonStyle.danger, emoji='💥')
    async def attack(self, interaction:discord.Interaction, button:Button):
        await self._handle_click(interaction, button)

    @button(label='Tahan', custom_id='defend', style=discord.ButtonStyle.blurple, emoji='🛡️')
    async def defend(self, interaction:discord.Interaction, button:Button):
        await self._handle_click(interaction, button)

    @button(label='Barang', custom_id='item', style=discord.ButtonStyle.green, emoji='👜')
    async def item(self, interaction:discord.Interaction, button:Button):
        await self._handle_click(interaction, button)

    @button(label='Skill', custom_id='skill', style=discord.ButtonStyle.green, emoji='🔮')
    async def skill(self, interaction:discord.Interaction, button:Button):
        await self._handle_click(interaction, button)

    @button(label='Diri', custom_id='self', style=discord.ButtonStyle.gray, emoji='👤')
    async def self_check(self, interaction:discord.Interaction, button:Button):
        await self._handle_click(interaction, button)

    @button(label='Kabur', custom_id='end', style=discord.ButtonStyle.gray, emoji='🏃')
    async def flee(self, interaction:discord.Interaction, button:Button):
        await self._handle_click(interaction, button)

    @button(label='Musuh', custom_id='check', style=discord.ButtonStyle.gray, emoji='❔', row=1)
    async def check(self, interaction:discord.Interaction, button:Button):
        await self._handle_click(interaction, button)

    @button(label='Lewati', custom_id='skip', style=discord.ButtonStyle.gray, emoji='⌚', row=1)
    async def skip(self, interaction:discord.Interaction, button:Button):
        await self._handle_click(interaction, button)

class GameInstance():
    def __init__(self, ctx:commands.Context, user1:discord.Member, user2, bot):
        # user2 is discord.Member if PvP, dict if PvE.
        self.user1 = user1
        self.user2 = user2
        self.user1_hp = 100
        try:
            self.user2_hp = self.user2['hp']

        except:
            self.user2_hp = 100

        self.user1_max_hp = 100
        self.user2_max_hp = 100
        self.running = False
        self.ctx = ctx
        self.bot = bot
        self.command_name = ctx.command.name
        self.user1_defend = False
        self.user2_defend = False
        self.user1_stats = None
        self.user2_stats = None
        self.ai_skill_usage = 0
        self.p1_skill_limit = 0
        self.p2_skill_limit = 0
        self.ai_miss_count = 0
        self.ai_consecutive_misses = 0
        self.turns = 0
        self.p1_karma = 10
        self.p2_karma = 10
        self.lang = "en"
        try:
            self.enemy_avatar = self.user2['avatar'] or getenv('defaultenemy')
        except:
            pass

    async def gather_data(self):
        def calc_skill_limit(level:int):
            if level < 10:
                return 3
            return 3*(math.floor(level/10))
        
        self.lang = await get_user_lang(self.user1.id)
        user1_data = await db.user.find_unique(where={'id': self.user1.id})
        stats1 = user1_data.data
        self.user1_hp = user1_data.hp # Dynamic HP!
        self.user1_max_hp = user1_data.max_hp
        
        user1_stats = [stats1['attack'], stats1['defense'], stats1['agility']]
        comp_data1 = {
            'stats': user1_stats,
            'hp': self.user1_hp,
            'max_hp': self.user1_max_hp
        }
        self.p1_karma = stats1.get('karma', 10)
        self.p1_skill_limit = calc_skill_limit(stats1['level'])

        if self.command_name == "fight":
            # Fight = PvP
            user2_data = await db.user.find_unique(where={'id': self.user2.id})
            if user2_data is None:
                msg = i18n.get(self.lang, "game.profile_not_registered")
                await self.ctx.reply(msg)
                raise Exception('Rival has no account!')
            
            stats2 = user2_data.data
            self.user2_hp = user2_data.hp
            self.user2_max_hp = user2_data.max_hp
            self.p2_karma = stats2.get('karma', 10)
            
            user2_stats = [stats2['attack'], stats2['defense'], stats2['agility']]
            comp_data2 = {
                'stats': user2_stats,
                'hp': self.user2_hp,
                'max_hp': self.user2_max_hp,
                'karma': self.p2_karma
            }
            self.p2_karma = stats2.get('karma', 10)
            self.p2_skill_limit = calc_skill_limit(stats2['level'])

        else:
            user2_stats = [self.user2['atk'], self.user2['def'], self.user2['agl']]
            # Enemies have karma based on tier
            tier_karma = {
                "LOW": 5, "NORMAL": 10, "HIGH": 20, "ELITE": 35, 
                "SUPER ELITE": 50, "BOSS": 75, "SUPER BOSS": 100,
                "BONUS ENEMY": 150, "FINAL BOSS": 200
            }
            self.p2_karma = tier_karma.get(self.user2.get('tier'), 10)
            self.user2_max_hp = self.user2_hp
            
            comp_data2 = {
                'stats':user2_stats,
                'hp':self.user2_hp,
                'max_hp': self.user2_hp,
                'karma': self.p2_karma
            }

        comp_data1['karma'] = self.p1_karma
        self.p1_karma = self.p1_karma # Ensure instance attribute is updated
        self.p2_karma = self.p2_karma # Ensure instance attribute is updated
        return [comp_data1, comp_data2]


    async def attack(self, dealer_stat:list, taker_stat:list, dealer_id:int, is_defending:bool, dealer_karma:int = 10, taker_karma:int = 10):
        user_1_atk, user_1_def, user_1_agl = dealer_stat[0], dealer_stat[1], dealer_stat[2]
        user_2_atk, user_2_def, user_2_agl = taker_stat[0], taker_stat[1], taker_stat[2]

        if is_defending:
            user_2_def += random.randint(8, 15)
            
        # Unified Improved Formula for both PvE (Battle) and PvP (Fight)
        # Ratio-based damage calculation ensures scaling for late-game/uncapped stats
        base_atk = user_1_atk * (random.randint(85, 115) / 100)
        
        damage = round(base_atk * (120 / (120 + user_2_def)))
        damage = max(damage, round(user_1_atk * 0.10)) # Min damage 10% of Atk
        
        miss_chance = min(40, max(0, (user_2_agl - user_1_agl) * 1.5 + 5 - (dealer_karma / 50)))
        dodge_chance = min(12, taker_karma / 120)
        
        # Luck Mechanics (Karma)
        # Critical Hit: Base 5% + (Karma / 20)%
        crit_chance = 5 + (dealer_karma / 20)
        is_crit = random.random() * 100 < crit_chance
        if is_crit:
            damage = round(damage * 1.5)
            
        hit_chance = 100 - miss_chance
        attack_chance = random.randint(0, 100)

        is_miracle_dodge = random.random() * 100 < dodge_chance

        if is_miracle_dodge:
            return [0, False, True] # Damage, IsCrit, IsMiracle

        try:
            if dealer_id == self.user1.id and is_defending:
                self.user2_defend = False
            elif dealer_id == self.user2.id and is_defending:
                self.user1_defend = False
            
        except:
            if dealer_id == 1 and is_defending:
                self.user1_defend = False

        if hit_chance >= attack_chance:
            if dealer_id == self.user1.id: # Might work
                self.user2_hp = self.user2_hp - damage
            else:
                self.user1_hp = self.user1_hp - damage
                if damage > 0:
                    self.ai_consecutive_misses = 0

            return [damage, is_crit, False]
        
        else:
            return [0, False, False]
        
    def defend(self, user):
        if user == self.user1:
            self.user1_defend = True
        else:
            self.user2_defend = True
    
    async def use(self, user1, type):
        inv_data = await db.inventory.find_unique(where={'userId': user1.id})
        items = inv_data.items if type == 'item' else inv_data.skills
        view = ItemView(items, user1, type, lang=self.lang)
        if type == 'item':
            msg = f"{user1.mention}, 10 detik untuk memilih item." if self.lang == 'id' else f"{user1.mention}, 10 seconds to choose an item."
            await self.ctx.channel.send(msg, view=view, delete_after=15)
        else:
            msg = f"{user1.mention}, 10 detik untuk menggunakan skill." if self.lang == 'id' else f"{user1.mention}, 10 seconds to use a skill."
            await self.ctx.channel.send(msg, view=view, delete_after=15)

    async def func_converter(self, func: str, user1, user2):
        func = func.upper()
        func = re.sub(r'\(|\)', '', func)
        
        def get_name(u):
            if isinstance(u, (discord.Member, discord.User)):
                return u.mention
            if isinstance(u, dict) and 'name' in u:
                return i18n.get(self.lang, f"game.enemy_{to_key(u['name'])}_name", default=u['name'])
            return "Seseorang" if self.lang == 'id' else "Someone"

        name1 = get_name(user1)
        name2 = get_name(user2)

        if '+' in func:
            func = func.split('+')
            match func[0]:
                case 'HP':
                    val = func[1]
                    is_percent = val.endswith('%')
                    if is_percent:
                        pct = int(val[:-1])
                        amount = round((self.user1_max_hp if user1 == self.user1 else self.user2_max_hp) * (pct / 100))
                    else:
                        amount = int(val)

                    if user1 == self.user1:
                        self.user1_hp += amount
                        if self.user1_hp > self.user1_max_hp: self.user1_hp = self.user1_max_hp
                    else:
                        self.user2_hp += amount
                        if self.user2_hp > self.user2_max_hp: self.user2_hp = self.user2_max_hp
                        
                    msg = i18n.get(self.lang, "game.func_hp_heal", name=name1, amount=amount)
                    await self.ctx.channel.send(msg)

                case 'DMG':
                    val = func[1]
                    is_percent = val.endswith('%')
                    if is_percent:
                        pct = int(val[:-1])
                        amount = round((self.user2_max_hp if user1 == self.user1 else self.user1_max_hp) * (pct / 100))
                    else:
                        amount = int(val)

                    if user1 == self.user1:
                        self.user2_hp -= amount
                    else:
                        self.user1_hp -= amount
                    
                    msg = i18n.get(self.lang, "game.func_instant_dmg", name=name1, amount=amount, target=name2)
                    await self.ctx.channel.send(msg)

                case 'ATK':
                    val_stat = int(func[1])
                    if user1 == self.user1:
                        self.user1_stats[0] += val_stat
                    else:
                        self.user2_stats[0] += val_stat
                    
                    msg = i18n.get(self.lang, "game.func_atk_buff", name=name1, amount=val_stat)
                    await self.ctx.channel.send(msg)

                case 'DEF':
                    val_stat = int(func[1])
                    if user1 == self.user1:
                        self.user1_stats[1] += val_stat
                    else:
                        self.user2_stats[1] += val_stat
                    
                    msg = i18n.get(self.lang, "game.func_def_buff", name=name1, amount=val_stat)
                    await self.ctx.channel.send(msg)

                case 'AGL':
                    val_stat = int(func[1])
                    if user1 == self.user1:
                        self.user1_stats[2] += val_stat
                    else:
                        self.user2_stats[2] += val_stat
                    
                    msg = i18n.get(self.lang, "game.func_agl_buff", name=name1, amount=val_stat)
                    await self.ctx.channel.send(msg)
                
                case 'ALL':
                    val_str = func[1]
                    is_percent = val_str.endswith('%')
                    
                    if user1 == self.user1:
                        target_stats = self.user1_stats
                        max_hp = self.user1_max_hp
                    else:
                        target_stats = self.user2_stats
                        max_hp = self.user2_max_hp

                    if is_percent:
                        pct = int(val_str[:-1])
                        val = round(max_hp * (pct / 100))
                    else:
                        val = int(val_str)

                    for i in range(3): target_stats[i] += val
                    
                    msg = i18n.get(self.lang, "game.func_all_buff", name=name1, amount=val)
                    await self.ctx.channel.send(msg)
        else:
            func = func.split('-')
            match func[0]:
                case 'HP':
                    val = func[1]
                    is_percent = val.endswith('%')
                    if is_percent:
                        pct = int(val[:-1])
                        amount = round((self.user2_max_hp if user1 == self.user1 else self.user1_max_hp) * (pct / 100))
                    else:
                        amount = int(val)

                    if user1 == self.user1:
                        self.user2_hp -= amount
                        self.user1_hp += amount
                        if self.user1_hp > self.user1_max_hp: self.user1_hp = self.user1_max_hp
                    else:
                        self.user1_hp -= amount
                        self.user2_hp += amount
                        if self.user2_hp > self.user2_max_hp: self.user2_hp = self.user2_max_hp

                    msg = i18n.get(self.lang, "game.func_hp_steal", name=name1, amount=amount, target=name2)
                    await self.ctx.channel.send(msg)

                case 'ATK':
                    val_stat = int(func[1])
                    if user1 == self.user1:
                        self.user2_stats[0] = max(1, self.user2_stats[0] - val_stat)
                    else:
                        self.user1_stats[0] = max(1, self.user1_stats[0] - val_stat)
                    
                    msg = i18n.get(self.lang, "game.func_atk_debuff", name=name1, target=name2, amount=val_stat)
                    await self.ctx.channel.send(msg)

                case 'DEF':
                    val_stat = int(func[1])
                    if user1 == self.user1:
                        self.user2_stats[1] = max(1, self.user2_stats[1] - val_stat)
                    else:
                        self.user1_stats[1] = max(1, self.user1_stats[1] - val_stat)
                    
                    msg = i18n.get(self.lang, "game.func_def_debuff", name=name1, target=name2, amount=val_stat)
                    await self.ctx.channel.send(msg)

                case 'AGL':
                    val_stat = int(func[1])
                    if user1 == self.user1:
                        self.user2_stats[2] = max(1, self.user2_stats[2] - val_stat)
                    else:
                        self.user1_stats[2] = max(1, self.user1_stats[2] - val_stat)
                    
                    msg = i18n.get(self.lang, "game.func_agl_debuff", name=name1, target=name2, amount=val_stat)
                    await self.ctx.channel.send(msg)
                
                case 'ALL':
                    val_str = func[1]
                    is_percent = val_str.endswith('%')
                    
                    target_stats = self.user2_stats if user1 == self.user1 else self.user1_stats
                    max_hp = self.user2_max_hp if user1 == self.user1 else self.user1_max_hp

                    if is_percent:
                        pct = int(val_str[:-1])
                        val = round(max_hp * (pct / 100))
                    else:
                        val = int(val_str)

                    for i in range(3):
                        target_stats[i] = max(1, target_stats[i] - val)
                    
                    msg = i18n.get(self.lang, "game.func_all_debuff", name=name1, target=name2, amount=val)
                    await self.ctx.channel.send(msg)

    async def ai_choose_skill(self, skill_set:list, ai, player):
        # Filter skills based on turn and situation
        turn = self.turns
        ai_missed_a_lot = self.ai_miss_count > 3 or self.ai_consecutive_misses >= 1
        
        def is_finisher(func):
            func = func.upper()
            return "HP-100%" in func or "DMG+100%" in func or "DMG+50%" in func

        def get_cat(func):
            func = func.upper()
            if any(x in func for x in ["DMG", "ATK+", "DEF-", "HP-", "AGL-"]): return "OFFENSIVE"
            return "DEFENSIVE"

        # 1. Filter out finishers if turn is too early
        # Exception: BONUS ENEMY (especially Mysterious Figure) has no mercy.
        is_bonus = self.user2.get('tier') == "BONUS ENEMY"
        available_skills = [s for s in skill_set if is_bonus or not (is_finisher(s['func']) and turn < 10)]
        
        # 2. If no skills left (all are finishers), just pick one anyway if it's turn > 5
        if not available_skills and turn > 5:
            available_skills = skill_set

        # 3. If missing often, prioritize offensive skills
        if ai_missed_a_lot:
            offensive = [s for s in available_skills if get_cat(s['func']) == "OFFENSIVE"]
            if offensive:
                available_skills = offensive

        if not available_skills:
            available_skills = skill_set # Fallback

        skill = random.choice(available_skills)
        skill_func = skill['func'].upper()
        
        enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(self.user2['name'])}_name", default=self.user2['name'])
        # Find index in original skill_set
        skill_idx = skill_set.index(skill)
        skill_name = i18n.get(self.lang, f"game.enemy_skill_{to_key(self.user2['name'])}_{skill_idx}_name", default=skill['name'])
        msg = i18n.get(self.lang, "game.use_skill_success", user=enemy_name, skill=skill_name, func=skill_func)
        await self.ctx.channel.send(msg)
        await asyncio.sleep(1)
        await self.func_converter(skill_func, ai, player)
        self.ai_skill_usage += 1


    async def start(self):
        # Start -> Create Thread -> While loop (this is for later zzz)
        # How do I check if other game instances are runnin tho
        self.running = True
        datas = await self.gather_data()
        self.user1_stats = datas[0]['stats']
        self.user2_stats = datas[1]['stats']
        p1_skills_used = 0
        p2_skills_used = 0
        if isinstance(self.user2, discord.Member):
            msg = i18n.get(self.lang, "game.combat_started_pvp", mention=self.user2.mention)
            await self.ctx.reply(msg)
        else:
            enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(self.user2['name'])}_name", default=self.user2['name'])
            msg = i18n.get(self.lang, "game.combat_started_pve", name=enemy_name, tier=self.user2['tier'])
            await self.ctx.reply(msg)
        await asyncio.sleep(2.7)
        self.turns = 1

        while self.user1_hp > 0 and self.user2_hp > 0:
            fight_view1 = FightView(lang=self.lang)
            turn_msg = i18n.get(self.lang, "game.combat_turn_prompt", user=self.user1.id)
            await self.ctx.channel.send(turn_msg, view=fight_view1)

            try:
                res_1:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and (r.content.startswith('Opsi terpilih: ') or r.content.startswith('Option selected: ')), timeout = 25.0)

            except asyncio.TimeoutError:
                fled_msg = i18n.get(self.lang, "game.combat_fled", mention=self.user1.mention)
                return await self.ctx.channel.send(fled_msg)

            action = res_1.content.replace("Opsi terpilih: ", "").replace("Option selected: ", "")
            match action:
                case "💥Serang" | "💥Attack":
                    damage_info = await self.attack(self.user1_stats, self.user2_stats, self.user1.id, self.user2_defend, self.p1_karma, self.p2_karma)
                    damage, is_crit, is_dodge = damage_info[0], damage_info[1], damage_info[2]
                    
                    title = i18n.get(self.lang, "game.combat_attack_title", name=self.user1.display_name)
                    if is_crit: title = i18n.get(self.lang, "game.combat_attack_crit")
                    if is_dodge: title = i18n.get(self.lang, "game.combat_attack_dodge")
                    
                    embed = discord.Embed(title=title, color=self.user1.color if not is_crit else discord.Color.gold())
                    
                    if is_dodge:
                        target_name = self.user2.display_name if isinstance(self.user2, discord.Member) else i18n.get(self.lang, f"game.enemy_{to_key(self.user2['name'])}_name", default=self.user2['name'])
                        embed.description = i18n.get(self.lang, "game.combat_miracle_dodge_desc", name=target_name)
                    elif damage > 0:
                        if isinstance(self.user2, discord.Member):
                            embed.description = i18n.get(self.lang, "game.combat_damage_desc_pvp", user=self.user2.id, damage=damage, hp=self.user2_hp)
                        else:
                            enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(self.user2['name'])}_name", default=self.user2['name'])
                            embed.description = i18n.get(self.lang, "game.combat_damage_desc_pve", name=enemy_name, damage=damage, hp=self.user2_hp)
                    else:
                        embed.description = i18n.get(self.lang, "game.combat_missed_desc", name=self.user1.display_name)
                        
                    embed.set_thumbnail(url=self.user1.display_avatar.url)
                    await self.ctx.channel.send(embed=embed)

                case "🛡️Tahan" | "🛡️Defend":
                    self.defend(self.user1)
                    title = i18n.get(self.lang, "game.combat_defend_title", name=self.user1.display_name)
                    embed = discord.Embed(title=title, color=self.user1.color)
                    embed.description = i18n.get(self.lang, "game.combat_defend_desc")
                    embed.set_thumbnail(url=self.user1.display_avatar.url)
                    await self.ctx.channel.send(embed=embed)

                case "👜Barang" | "👜Item":
                    await self.use(self.user1, 'item')
                    try:
                        res_use:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and (" menggunakan " in r.content or " used " in r.content) and "\n(" in r.content, timeout = 10)
                        func_lines = res_use.content.split('\n')
                        if len(func_lines) >= 3:
                            func = func_lines[2]
                            await self.func_converter(func, self.user1, self.user2)
                        else:
                            msg = i18n.get(self.lang, "game.combat_item_invalid")
                            await self.ctx.channel.send(msg)
                    except asyncio.TimeoutError:
                        msg = i18n.get(self.lang, "game.combat_item_timeout", mention=self.user1.mention)
                        await self.ctx.channel.send(msg)

                case "🔮Skill" | "🔮Skill":
                    if p1_skills_used >= self.p1_skill_limit:
                        msg = i18n.get(self.lang, "game.combat_skill_limit_reached", mention=self.user1.mention, limit=self.p1_skill_limit)
                        await self.ctx.channel.send(msg)
                    else:
                        await self.use(self.user1, 'skill')
                        try:
                            res_use:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and (" menggunakan " in r.content or " used " in r.content) and "\n(" in r.content, timeout = 10)
                            func_lines = res_use.content.split('\n')
                            if len(func_lines) >= 3:
                                func = func_lines[2]
                                await self.func_converter(func, self.user1, self.user2)
                                p1_skills_used += 1
                            else:
                                msg = i18n.get(self.lang, "game.combat_skill_invalid")
                                await self.ctx.channel.send(msg)
                        except asyncio.TimeoutError:
                            msg = i18n.get(self.lang, "game.combat_skill_timeout", mention=self.user1.mention)
                            await self.ctx.channel.send(msg)

                case "❔Musuh" | "❔Enemy":
                    stats = self.user2_stats
                    defending_val = i18n.get(self.lang, "game.combat_status_yes") if self.user2_defend else i18n.get(self.lang, "game.combat_status_no")
                    if isinstance(self.user2, discord.Member):
                        embed = discord.Embed(title=self.user2.display_name, color=self.user2.color)
                        embed.set_thumbnail(url=self.user2.display_avatar.url)
                        embed.description = i18n.get(self.lang, "game.combat_hp_status_enemy", hp=self.user2_hp, max_hp=100, defending=defending_val)
                        embed.add_field(
                            name=i18n.get(self.lang, "game.combat_stats_field"),
                            value=f"Attack: `{stats[0]}`\nDefense: `{stats[1]}`\nAgility: `{stats[2]}`",
                            inline=False
                        )
                        embed.set_author(name=i18n.get(self.lang, "game.combat_opponent_info_header"))
                    
                    else:
                        enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(self.user2['name'])}_name", default=self.user2['name'])
                        enemy_desc = i18n.get(self.lang, f"game.enemy_{to_key(self.user2['name'])}_desc", default=self.user2['desc'])
                        embed = discord.Embed(title=enemy_name, color=discord.Color.from_str(self.user2.get('color', '#ff0000')))
                        embed.description = f"\"{enemy_desc}\"\n" + i18n.get(self.lang, "game.combat_hp_status_enemy", hp=self.user2_hp, max_hp=datas[1]['hp'], defending=defending_val)
                        embed.add_field(
                            name=i18n.get(self.lang, "game.combat_stats_field"),
                            value=f"Attack: `{stats[0]}`\nDefense: `{stats[1]}`\nAgility: `{stats[2]}`",
                            inline=True
                        )
                        
                        # Show Enemy Skills
                        skills_text = ""
                        for idx, s in enumerate(self.user2.get('skills', [])):
                            skill_name = i18n.get(self.lang, f"game.enemy_skill_{to_key(self.user2['name'])}_{idx}_name", default=s['name'])
                            skills_text += f"• **{skill_name}**\n"
                        if not skills_text: skills_text = i18n.get(self.lang, "game.combat_no_skills")
                        embed.add_field(name=i18n.get(self.lang, "game.combat_enemy_skills_field"), value=skills_text, inline=False)
                        
                        # Show Player Consumables (Items)
                        inv_data = await db.inventory.find_unique(where={'userId': self.user1.id})
                        if inv_data and inv_data.items:
                            items_text = ""
                            for item in inv_data.items:
                                item_name = i18n.get(self.lang, f"game.item_{item['_id']}_name", default=item.get('name'))
                                items_text += f"• **{item_name}** x{item.get('owned', 0)}\n"
                            embed.add_field(name=i18n.get(self.lang, "game.combat_your_items_field"), value=items_text or i18n.get(self.lang, "game.combat_no_items"), inline=False)
                        
                        embed.set_author(name=i18n.get(self.lang, "game.combat_enemy_info_header"))
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass

                    await self.ctx.channel.send(embed = embed)

                case "Opsi terpilih: 👤Diri" | "👤Self":
                    stats = self.user1_stats
                    defending_val = i18n.get(self.lang, "game.combat_status_yes") if self.user1_defend else i18n.get(self.lang, "game.combat_status_no")
                    embed = discord.Embed(title=self.user1.display_name, color=self.user1.color)
                    embed.set_thumbnail(url=self.user1.display_avatar.url)
                    embed.description = i18n.get(self.lang, "game.combat_hp_status", hp=self.user1_hp, max_hp=self.user1_max_hp, defending=defending_val)
                    embed.add_field(
                        name=i18n.get(self.lang, "game.combat_current_stats_field"),
                        value=f"Attack: `{stats[0]}`\nDefense: `{stats[1]}`\nAgility: `{stats[2]}`",
                        inline=False
                    )
                    embed.set_author(name=i18n.get(self.lang, "game.combat_self_info_header"))
                    await self.ctx.channel.send(embed=embed)

                case "Opsi terpilih: 🏃Kabur" | "🏃Flee":
                    msg = i18n.get(self.lang, "game.combat_ended", user=self.user1.id)
                    await self.ctx.channel.send(msg)
                    return
                
                case "Opsi terpilih: ⌚Lewati" | "⌚Skip":
                    msg = i18n.get(self.lang, "game.combat_skipped", mention=self.user1.mention)
                    await self.ctx.channel.send(msg)

                case _:
                    msg = i18n.get(self.lang, "game.combat_invalid_option")
                    await self.ctx.channel.send(msg) # This was actually possible, now it's an easter egg!

            if self.user2_hp <= 0:
                await asyncio.sleep(2.5)
                break

            await asyncio.sleep(2.5)

            if isinstance(self.user2, discord.Member):
                fight_view2 = FightView(lang=self.lang)
                turn_msg = i18n.get(self.lang, "game.combat_turn_prompt", user=self.user2.id)
                await self.ctx.channel.send(turn_msg, view=fight_view2)

                try:
                    res_2 = await self.bot.wait_for(
                        'message',
                        check=lambda r: r.author == self.bot.user 
                        and r.channel == self.ctx.channel 
                        and (r.content.startswith('Opsi terpilih: ') or r.content.startswith('Option selected: ')),
                        timeout=25.0
                    )

                except asyncio.TimeoutError:
                    fled_msg = i18n.get(self.lang, "game.combat_fled", mention=self.user2.mention)
                    return await self.ctx.channel.send(fled_msg)
            
                action = res_2.content.replace("Opsi terpilih: ", "").replace("Option selected: ", "")
                match action:
                    case "💥Serang" | "💥Attack":
                        damage_info = await self.attack(datas[1]['stats'], datas[0]['stats'], self.user2.id, self.user1_defend, self.p2_karma, self.p1_karma)
                        damage, is_crit, is_dodge = damage_info[0], damage_info[1], damage_info[2]
                        
                        title = i18n.get(self.lang, "game.combat_attack_title", name=self.user2.display_name)
                        if is_crit: title = i18n.get(self.lang, "game.combat_attack_crit")
                        if is_dodge: title = i18n.get(self.lang, "game.combat_attack_dodge")
                        
                        embed = discord.Embed(title=title, color=self.user2.color if not is_crit else discord.Color.gold())
                        
                        if is_dodge:
                            embed.description = i18n.get(self.lang, "game.combat_miracle_dodge_desc", name=self.user1.display_name)
                        elif damage > 0:
                            embed.description = i18n.get(self.lang, "game.combat_damage_desc_pvp", user=self.user1.id, damage=damage, hp=self.user1_hp)
                        else:
                            embed.description = i18n.get(self.lang, "game.combat_missed_desc", name=self.user2.display_name)
                            
                        embed.set_thumbnail(url=self.user2.display_avatar.url)
                        await self.ctx.channel.send(embed=embed)

                    case "🛡️Tahan" | "🛡️Defend":
                        self.defend(self.user2)
                        title = i18n.get(self.lang, "game.combat_defend_title", name=self.user2.display_name)
                        embed = discord.Embed(title=title, color=self.user2.color)
                        embed.description = i18n.get(self.lang, "game.combat_defend_desc")
                        embed.set_thumbnail(url=self.user2.display_avatar.url)
                        await self.ctx.channel.send(embed=embed)

                    case "❔Musuh" | "❔Enemy":
                        stats = self.user1_stats
                        defending_val = i18n.get(self.lang, "game.combat_status_yes") if self.user1_defend else i18n.get(self.lang, "game.combat_status_no")
                        embed = discord.Embed(title=self.user1.display_name, color=self.user1.color)
                        embed.set_thumbnail(url=self.user1.display_avatar.url)
                        embed.description = i18n.get(self.lang, "game.combat_hp_status_enemy", hp=self.user1_hp, max_hp=self.user1_max_hp, defending=defending_val)
                        embed.add_field(
                            name=i18n.get(self.lang, "game.combat_stats_field"),
                            value=f"Attack: `{stats[0]}`\nDefense: `{stats[1]}`\nAgility: `{stats[2]}`",
                            inline=False
                        )
                        
                        # Show Rival Items
                        inv_data = await db.inventory.find_unique(where={'userId': self.user2.id})
                        if inv_data and inv_data.items:
                            items_text = ""
                            for item in inv_data.items:
                                item_name = i18n.get(self.lang, f"game.item_{item['_id']}_name", default=item.get('name'))
                                items_text += f"• **{item_name}** x{item.get('owned', 0)}\n"
                            embed.add_field(name=i18n.get(self.lang, "game.combat_your_items_field"), value=items_text or i18n.get(self.lang, "game.combat_no_items"), inline=False)
                            
                        embed.set_author(name=i18n.get(self.lang, "game.combat_opponent_info_header"))
                        await self.ctx.channel.send(embed=embed)

                    case "👤Diri" | "👤Self":
                        stats = self.user2_stats
                        defending_val = i18n.get(self.lang, "game.combat_status_yes") if self.user2_defend else i18n.get(self.lang, "game.combat_status_no")
                        embed = discord.Embed(title=self.user2.display_name, color=self.user2.color)
                        embed.set_thumbnail(url=self.user2.display_avatar.url)
                        embed.description = i18n.get(self.lang, "game.combat_hp_status", hp=self.user2_hp, max_hp=self.user2_max_hp, defending=defending_val)
                        embed.add_field(
                            name=i18n.get(self.lang, "game.combat_current_stats_field"),
                            value=f"Attack: `{stats[0]}`\nDefense: `{stats[1]}`\nAgility: `{stats[2]}`",
                            inline=False
                        )
                        embed.set_author(name=i18n.get(self.lang, "game.combat_self_info_header"))
                        await self.ctx.channel.send(embed=embed)

                    case "👜Barang" | "👜Item":
                        await self.use(self.user2, 'item')
                        try:
                            res_use:discord.Message = await self.bot.wait_for(
                                'message',
                                check=lambda r: r.author == self.bot.user 
                                and r.channel == self.ctx.channel 
                                and (" menggunakan " in r.content or " used " in r.content) 
                                and "\n(" in r.content,
                                timeout=10
                            )
                            func_lines = res_use.content.split('\n')
                            if len(func_lines) >= 3:
                                func = func_lines[2]
                                await asyncio.sleep(1.2)
                                await self.func_converter(func, self.user2, self.user1)
                            else:
                                msg = i18n.get(self.lang, "game.combat_item_invalid")
                                await self.ctx.channel.send(msg)
                        except asyncio.TimeoutError:
                            msg = i18n.get(self.lang, "game.combat_item_timeout", mention=self.user2.mention)
                            await self.ctx.channel.send(msg)

                    case "🔮Skill":
                        if p2_skills_used >= self.p2_skill_limit:
                            msg = i18n.get(self.lang, "game.combat_skill_limit_reached", mention=self.user2.mention, limit=self.p2_skill_limit)
                            await self.ctx.channel.send(msg)
                        else:
                            await self.use(self.user2, 'skill')
                            try:
                                res_use:discord.Message = await self.bot.wait_for(
                                    'message',
                                    check=lambda r: r.author == self.bot.user 
                                    and r.channel == self.ctx.channel 
                                    and (" menggunakan " in r.content or " used " in r.content) 
                                    and "\n(" in r.content,
                                    timeout=10
                                )
                                func_lines = res_use.content.split('\n')
                                if len(func_lines) >= 3:
                                    func = func_lines[2]
                                    await asyncio.sleep(1.2)
                                    await self.func_converter(func, self.user2, self.user1)
                                    p2_skills_used += 1
                                else:
                                    msg = i18n.get(self.lang, "game.combat_skill_invalid")
                                    await self.ctx.channel.send(msg)
                            except asyncio.TimeoutError:
                                msg = i18n.get(self.lang, "game.combat_skill_timeout", mention=self.user2.mention)
                                await self.ctx.channel.send(msg)

                    case "🏃Kabur" | "🏃Flee":
                        msg = i18n.get(self.lang, "game.combat_ended", user=self.user2.id)
                        await self.ctx.channel.send(msg)
                        return
                    
                    case "⌚Lewati" | "⌚Skip":
                        msg = i18n.get(self.lang, "game.combat_skipped", mention=self.user2.mention)
                        await self.ctx.channel.send(msg)

                    case _:
                        msg = i18n.get(self.lang, "game.combat_invalid_option")
                        await self.ctx.channel.send(msg)

            else:
                ai = AI(self, self.turns)
                choice = await ai.decide()
                enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(self.user2['name'])}_name", default=self.user2['name'])
                
                match choice:
                    case "attack":
                        damage_info = await self.attack(self.user2_stats, self.user1_stats, 1, self.user1_defend, self.p2_karma, self.p1_karma)
                        damage, is_crit, is_dodge = damage_info[0], damage_info[1], damage_info[2]
                        
                        title = i18n.get(self.lang, "game.combat_attack_title", name=enemy_name)
                        if is_crit: title = i18n.get(self.lang, "game.combat_attack_crit")
                        if is_dodge: title = i18n.get(self.lang, "game.combat_attack_dodge")
                        
                        embed = discord.Embed(title=title, color=discord.Color.from_str(self.user2.get('color', '#ff0000')) if not is_crit else discord.Color.gold())
                        
                        if is_dodge:
                            embed.description = i18n.get(self.lang, "game.combat_miracle_dodge_desc", name=self.user1.display_name)
                        elif damage > 0:
                            embed.description = i18n.get(self.lang, "game.combat_damage_desc_pvp", user=self.user1.id, damage=damage, hp=self.user1_hp)
                        else:
                            embed.description = i18n.get(self.lang, "game.combat_missed_desc", name=enemy_name)
                            self.ai_miss_count += 1
                            self.ai_consecutive_misses += 1
                            
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        await self.ctx.channel.send(embed=embed)

                    case "defend":
                        self.defend(self.user2)
                        title = i18n.get(self.lang, "game.combat_defend_title", name=enemy_name)
                        embed = discord.Embed(title=title, color=discord.Color.from_str(self.user2.get('color', '#ff0000')))
                        embed.description = i18n.get(self.lang, "game.combat_defend_desc")
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        await self.ctx.channel.send(embed=embed)

                    case "skill":
                        await self.ai_choose_skill(self.user2['skills'], self.user2, self.user1)

                    case "check":
                        self.ai_knows_user = True
                        title = i18n.get(self.lang, "game.combat_ai_check_title", name=enemy_name)
                        desc = i18n.get(
                            self.lang,
                            "game.combat_ai_check_desc",
                            name=enemy_name,
                            hp=self.user1_hp,
                            max_hp=self.user1_max_hp,
                            atk=self.user1_stats[0],
                            def_=self.user1_stats[1],
                            agl=self.user1_stats[2]
                        )
                        embed = discord.Embed(title=title, color=discord.Color.from_str(self.user2.get('color', '#3498db')))
                        embed.description = desc
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        await self.ctx.channel.send(embed=embed)

                    case "skip":
                        self.defend(self.user2) # Skipping turn gives a minor defense boost
                        title = i18n.get(self.lang, "game.combat_ai_skip_title", name=enemy_name)
                        desc = i18n.get(self.lang, "game.combat_ai_skip_desc", name=enemy_name)
                        embed = discord.Embed(title=title, color=discord.Color.from_str(self.user2.get('color', '#95a5a6')))
                        embed.description = desc
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        await self.ctx.channel.send(embed=embed)

                    case "run":
                        title = i18n.get(self.lang, "game.combat_ai_run_title", name=enemy_name)
                        desc = i18n.get(self.lang, "game.combat_ai_run_desc", name=enemy_name)
                        footer = i18n.get(self.lang, "game.combat_ai_run_footer")
                        embed = discord.Embed(title=title, color=discord.Color.from_str(self.user2.get('color', '#ff0000')))
                        embed.description = desc
                        embed.set_footer(text=footer)
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        return await self.ctx.channel.send(embed=embed)
                    
            self.turns += 1

            await asyncio.sleep(2.5)

        if self.user1_hp > self.user2_hp:
            title = i18n.get(self.lang, "game.combat_win_title", name=self.user1.display_name)
            desc = i18n.get(self.lang, "game.combat_win_desc", hp=self.user1_hp)
            embed = discord.Embed(title=title, color=0xffff00)
            embed.description = desc
            
            reward_title = i18n.get(self.lang, "game.combat_reward_title")
            
            if not isinstance(self.user2, discord.Member):
                rewards = self.user2['reward']
                rewards = split_reward_string(rewards)
                if len(rewards) == 3:
                    reward_exp = i18n.get(self.lang, "game.combat_reward_exp", amount=rewards[0])
                    reward_coins = i18n.get(self.lang, "game.combat_reward_coins", emoji=self.bot.coin_emoji_anim, amount=rewards[1])
                    reward_karma = i18n.get(self.lang, "game.combat_reward_karma", amount=rewards[2])
                    embed.add_field(
                        name=reward_title,
                        value=f"{reward_exp}\n{reward_coins}\n{reward_karma}",
                        inline=False
                    )
                    await give_rewards(self.ctx, self.user1, rewards[0], rewards[1], rewards[2])
                else:
                    reward_exp = i18n.get(self.lang, "game.combat_reward_exp", amount=rewards[0])
                    reward_coins = i18n.get(self.lang, "game.combat_reward_coins", emoji=self.bot.coin_emoji_anim, amount=rewards[1])
                    embed.add_field(
                        name=reward_title,
                        value=f"{reward_exp}\n{reward_coins}",
                        inline=False
                    )
                    await give_rewards(self.ctx, self.user1, rewards[0], rewards[1])
            else:
                reward_coins = i18n.get(self.lang, "game.combat_reward_coins", emoji=self.bot.coin_emoji_anim, amount=15)
                reward_karma = i18n.get(self.lang, "game.combat_reward_karma", amount=5)
                embed.add_field(
                    name=reward_title,
                    value=f"{reward_coins}\n{reward_karma}",
                    inline=False
                )
                await give_rewards(self.ctx, self.user1, 0, 15, 5)
            await asyncio.sleep(0.7)
            embed.set_thumbnail(url = self.user1.display_avatar.url)
            await self.ctx.channel.send(embed=embed)

        else:
            if isinstance(self.user2, discord.Member):
                title = i18n.get(self.lang, "game.combat_win_title", name=self.user2.display_name)
                desc = i18n.get(self.lang, "game.combat_win_desc", hp=self.user2_hp)
                embed = discord.Embed(title=title, color=0xffff00)
                embed.description = desc
                
                reward_title = i18n.get(self.lang, "game.combat_reward_title")
                reward_coins = i18n.get(self.lang, "game.combat_reward_coins", emoji=self.bot.coin_emoji_anim, amount=15)
                reward_karma = i18n.get(self.lang, "game.combat_reward_karma", amount=5)
                embed.add_field(
                    name=reward_title,
                    value=f"{reward_coins}\n{reward_karma}",
                    inline=False
                )
                await give_rewards(self.ctx, self.user2, 0, 15, 5)
                embed.set_thumbnail(url = self.user2.display_avatar.url)
                await self.ctx.channel.send(embed=embed)

            else:
                tip_keys = [
                    "game.combat_tip_1",
                    "game.combat_tip_2",
                    "game.combat_tip_3",
                    "game.combat_tip_4",
                    "game.combat_tip_5"
                ]
                selected_tip_key = random.choice(tip_keys)
                tip_text = i18n.get(self.lang, selected_tip_key)
                
                title = i18n.get(self.lang, "game.combat_loss_title")
                enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(self.user2['name'])}_name", default=self.user2['name'])
                desc = i18n.get(self.lang, "game.combat_loss_desc", name=enemy_name, hp=self.user2_hp)
                footer = i18n.get(self.lang, "game.combat_loss_tip", tip=tip_text)
                
                embed = discord.Embed(title=title, color=discord.Color.from_str(self.user2.get('color', '#ff0000')))
                embed.description = desc
                embed.set_footer(text=footer)
                try:
                    embed.set_thumbnail(url = self.enemy_avatar)
                except:
                    pass
                await self.ctx.channel.send(embed=embed)

        return
    
class AI():
    """
    Generic AI class for fight & battle commands
    Using mood system cause it's the best one I could think of
    So yeah, like, share, and subscribe
    """
    def __init__(self, instance:GameInstance, turns:int) -> None:
        self.instance = instance
        self.user1 = instance.user1
        self.user2 = instance.user2
        self.user1_hp = instance.user1_hp
        self.user2_hp = instance.user2_hp
        self.user1_defend = instance.user1_defend
        self.user2_defend = instance.user2_defend
        self.attack_mood = 0
        self.defend_mood = 0
        self.escape_mood = 0
        self.skill_mood = 0
        self.check_mood = 0
        self.skip_mood = 0
        
        self.turns = turns
        self.user1_stats = instance.user1_stats
        self.user2_stats = instance.user2_stats
        self.ai_skill_usage = instance.ai_skill_usage
        self.ai_miss_count = instance.ai_miss_count
        self.ai_consecutive_misses = instance.ai_consecutive_misses
        self.p1_karma = instance.p1_karma
        self.p2_karma = instance.p2_karma
        
        # Persistence: AI remembers if it has checked your stats
        if not hasattr(self.instance, 'ai_knows_user'):
            self.instance.ai_knows_user = False
            
        self.actions = ["attack", "defend", "skip"]
        if self.turns > 0 and not self.instance.ai_knows_user:
            self.actions.append("check")
            
        if self.turns > 1: # AI can use skills earlier now
            try:
                skills = self.user2['skills']
                if skills:
                    self.actions.append("skill")
            except:
                pass
        if self.turns > 8: # Running away is harder for AI now
            self.actions.append("run")
    
    async def decide(self):
        user1_stats = self.user1_stats
        user2_stats = self.user2_stats
        user_1_atk, user_1_def, user_1_agl = user1_stats[0], user1_stats[1], user1_stats[2]
        user_2_atk, user_2_def, user_2_agl = user2_stats[0], user2_stats[1], user2_stats[2]

        # Puny Attack Detection: If basic attacks are too weak, force skills
        expected_damage = round(user_2_atk * (120 / (120 + user_1_def)))
        if expected_damage < 30 and "skill" in self.actions:
            if "attack" in self.actions:
                self.actions.remove("attack")
            self.skill_mood += 100

        # Psychological Scaling if AI knows the user
        if self.instance.ai_knows_user:
            atk_diff = user_2_atk - user_1_def
            p_atk_diff = user_1_atk - user_2_def
            
            if atk_diff > 20: # AI is confident
                self.attack_mood += 25
                self.skill_mood += 15
            elif p_atk_diff > 20: # AI is scared
                self.defend_mood += 30
                self.skip_mood += 10
                self.escape_mood += 15
            
            if self.user1_hp < 30: # Finisher instinct
                self.attack_mood += 40

            # Danger Analysis: If AI misses too often, it gets aggressive
            if self.ai_miss_count > 3 or self.ai_consecutive_misses >= 1:
                # User's logic: resort to offensive skills and abandon regular attacks
                if 'skill' in self.actions:
                    self.skill_mood += 100
                    if 'attack' in self.actions:
                        self.actions.remove("attack")
                else:
                    # If no skills available, just get more aggressive with what's left
                    self.attack_mood += 25
                
                self.escape_mood = max(0, self.escape_mood - 15) # AI won't run if it's frustrated
            
            # Karma Awareness: If player has high karma, they are hard to hit with regular attacks
            if self.p1_karma > 50:
                self.skill_mood += 30
                self.check_mood += 10
            
            # If AI has high karma, it feels more confident using skills
            if self.p2_karma > 50:
                self.skill_mood += 15
                self.attack_mood += 10
        else:
            # Chance to check stats increases significantly as turns go by
            self.check_mood += (self.turns * 12)
        
        # Battle Duration Analysis
        if self.turns > 12:
            self.skill_mood += 20 # Resort to skills to end the drag
            self.attack_mood += 10
        if self.turns > 20:
            self.skill_mood += 40 # Desperation

        if self.user1_hp > self.user2_hp:
            self.attack_mood += 12
            self.defend_mood += 14
            self.escape_mood += 6
            self.skill_mood += 10
            if self.user1_defend:
                self.defend_mood += 8
                self.skill_mood += 2

            if self.user2_defend:
                self.defend_mood += 8
                self.attack_mood += 7
                self.skill_mood += 1

        else:
            self.attack_mood += 20
            self.defend_mood += 10
            self.skill_mood += 6
            if self.user2_defend:
                self.attack_mood += 8
                self.skill_mood += 1

            if self.user1_defend:
                self.defend_mood += 8
                self.skill_mood += 3

        if user_1_atk >= user_2_def:
            self.attack_mood += 5
            self.defend_mood += 12
            self.escape_mood += 3
            self.skill_mood += 6

        else:
            self.defend_mood += 6
            self.attack_mood += 10
            self.skill_mood += 2

        if user_2_agl >= user_1_agl:
            self.escape_mood += 3
        else:
            self.skip_mood += 5

        # Skip logic: AI bides time if it's high HP but user is defending
        if self.user1_defend and self.user2_hp > 50:
            self.skip_mood += 15

        # Defining escape moods based on level. (Does not apply to LOW - SUPER NORMAL & BONUS ENEMY)
        tier = self.user2['tier']
        match tier:
            case "FINAL BOSS":
                self.escape_mood = 0

            case "SUPER BOSS":
                self.escape_mood = 0

            case "BOSS":
                self.escape_mood = 0

            case "SUPER ELITE":
                self.escape_mood = 1

            case "ELITE":
                self.escape_mood = 2

            case "SUPER HIGH":
                self.escape_mood = 4
                if self.ai_skill_usage >= 3 and 'skill' in self.actions:
                    self.actions.remove("skill")

            case "HIGH":
                self.escape_mood = 5
                if self.ai_skill_usage >= 2 and 'skill' in self.actions:
                    self.actions.remove("skill")

            case "SUPER NORMAL":
                if self.ai_skill_usage >= 3 and 'skill' in self.actions:
                    self.actions.remove("skill")

            case "NORMAL":
                if self.ai_skill_usage >= 2 and 'skill' in self.actions:
                    self.actions.remove("skill")

            case "SUPER LOW":
                if self.ai_skill_usage >= 2 and 'skill' in self.actions:
                    self.actions.remove("skill")

            case "LOW":
                if self.ai_skill_usage >= 1 and 'skill' in self.actions:
                    self.actions.remove("skill")

        # Compile final weights
        moods = {
            "attack": self.attack_mood,
            "defend": self.defend_mood,
            "skill": self.skill_mood,
            "run": self.escape_mood,
            "check": self.check_mood,
            "skip": self.skip_mood
        }
        
        # Filter available actions
        available_moods = {k: v for k, v in moods.items() if k in self.actions}
        
        # Pick the best action with a bit of randomness
        chosen_action = max(available_moods, key=lambda k: available_moods[k] + random.randint(0, 10))
        return chosen_action
    
class ItemDropdown(discord.ui.Select):
    def __init__(self, items:list, user1, type, lang="en") -> None:
        options = []
        for item in items:
            name = i18n.get(lang, f"game.item_{item['_id']}_name", default=item.get('name'))
            desc = i18n.get(lang, f"game.item_{item['_id']}_desc", default=item.get('desc', 'No description.'))
            func = item.get('func', '???').upper()
            full_desc = f"{desc} ({func})"
            if len(full_desc) > 100:
                full_desc = full_desc[:97] + "..."

            if '0-' in item['_id'] and item['usefor'] == 'battle' and not item.get('owned', 0) <= 0 and type == 'item':
                options.append(discord.SelectOption(
                    label=name,
                    value=item['_id'],
                    description=full_desc
                ))
            elif '2-' in item['_id'] and item['usefor'] == 'battle' and not item.get('owned', 0) <= 0 and type == 'skill':
                options.append(discord.SelectOption(
                    label=name,
                    value=item['_id'],
                    description=full_desc
                ))
        
        if len(options) > 25:
            options = options[:25]

        if not options:
            no_item_lbl = i18n.get(lang, "game.use_no_items") if type == 'item' else i18n.get(lang, "game.use_no_skills")
            no_item_desc = i18n.get(lang, "game.combat_no_items") if type == 'item' else i18n.get(lang, "game.combat_no_skills")
            options.append(discord.SelectOption(
                    label=no_item_lbl,
                    value="none",
                    description=no_item_desc
                )
            )
        placeholder_text = i18n.get(lang, "game.shop_select_item")
        super().__init__(custom_id="itemdrop", placeholder=placeholder_text, min_values=1, max_values=1, options=options)
        self.user1 = user1
        self.items = items
        self.types = type
        self.lang = lang

    async def callback(self, interaction:discord.Interaction):
        if interaction.message.mentions[0].id != interaction.user.id:
            msg = i18n.get(self.lang, "game.invite_view_not_for_you")
            return await interaction.response.send_message(msg, ephemeral=True)
        if self.values[0] == 'none' and self.types == 'item':
            msg = i18n.get(self.lang, "game.use_no_items")
            return await interaction.response.send_message(msg, ephemeral=True)
        elif self.values[0] == 'none' and self.types == 'skill':
            msg = i18n.get(self.lang, "game.use_no_skills")
            return await interaction.response.send_message(msg, ephemeral=True)
        
        user_record = await db.user.find_unique(where={'id': self.user1.id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            msg = i18n.get(self.lang, "game.use_account_issue")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        inventory = user_record.inventory
        used_item = None
        
        if self.types == 'item':
            user_items = inventory.items if isinstance(inventory.items, list) else []
            for item in user_items:
                if item['_id'] == self.values[0] and item.get('owned', 0) > 0:
                    item['owned'] -= 1
                    item_name = i18n.get(self.lang, f"game.item_{item['_id']}_name", default=item['name'])
                    used_item = [item_name, item['func']]
                    break
            
            if used_item:
                await db.inventory.update(
                    where={'userId': self.user1.id},
                    data={'items': Json(user_items)}
                )
        else:
            user_skills = inventory.skills if isinstance(inventory.skills, list) else []
            for item in user_skills:
                if item['_id'] == self.values[0] and item.get('owned', 0) > 0:
                    item_name = i18n.get(self.lang, f"game.item_{item['_id']}_name", default=item['name'])
                    used_item = [item_name, item['func']]
                    break

        if used_item is None:
            msg = i18n.get(self.lang, "game.use_not_found")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        if self.types == 'item':
            msg = i18n.get(self.lang, "game.use_item_success", user=interaction.user.mention, item=used_item[0], func=used_item[1].upper())
            await interaction.response.send_message(msg)
        else:
            msg = i18n.get(self.lang, "game.use_skill_success", user=interaction.user.mention, skill=used_item[0], func=used_item[1].upper())
            await interaction.response.send_message(msg)


class ItemView(View):
    def __init__(self, items:list, user1, type, lang="en") -> None:
        super().__init__(timeout=20)
        self.add_item(ItemDropdown(items, user1, type, lang=lang))
    
def guess_level_convert(level:str):
    """
    Converts to n amount of numbers need to be guessed
    """
    match level:
        case 'EASY':
            return 5
        case 'NORMAL':
            return 10
        case 'HARD':
            return 20
        case 'SUPER':
            return 25

class GuessDropdown(discord.ui.Select):
    def __init__(self, number:int, attempt:int, hint:int, level:str, lang="en") -> None:
        self.number = number
        self.attempt = attempt
        self.hints = hint
        self.level = level
        self.lang = lang
        num_amount = guess_level_convert(level)
        options = []
        for i in range(1, num_amount+1):
            options.append(discord.SelectOption(
                label=str(i),
                value=i
            ))
        placeholder_text = "Pilih angka yang tepat!" if lang == "id" else "Select the correct number!"
        super().__init__(custom_id='guessdrop', placeholder=placeholder_text, min_values=1, max_values=1, options=options)

    async def callback(self, interaction:discord.Interaction):
        if self.attempt > 0:
            if int(self.values[0]) == self.number:
                msg = i18n.get(self.lang, "game.guess_correct", number=self.number)
                await interaction.response.send_message(msg)
                self.disabled = True
                return
            else:
                self.attempt -= 1
                msg = i18n.get(self.lang, "game.guess_incorrect", guess=self.values[0], attempt=self.attempt)
                await interaction.response.send_message(msg, view=GuessGameView(self.number, self.attempt, self.hints, self.level, int(self.values[0]), lang=self.lang))
        else:
            msg = i18n.get(self.lang, "game.guess_out_of_attempts")
            return await interaction.response.send_message(msg, ephemeral=True)

class GuessGameView(View):
    """
    Buttons and stuff
    """
    def __init__(self, number:int, attempt:int, hint_left:int, level:str, last_number:int=None, lang="en"):
        super().__init__(timeout=None) # Maybe None prevents it from timing out too soon.
        self.hints = hint_left
        self.last = last_number
        self.number = number
        self.attempt = attempt
        self.level = level
        self.lang = lang
        self.add_item(GuessDropdown(self.number, self.attempt, self.hints, self.level, lang=self.lang))

    @button(label='Hint', custom_id='hint', style=discord.ButtonStyle.blurple, emoji='❔')
    async def give_hint(self, interaction:discord.Interaction, button:Button):
        if self.last == None:
            msg = i18n.get(self.lang, "game.guess_not_guessed_yet")
            await interaction.response.send_message(msg, ephemeral=True)
            return
        if self.hints != 0:
            self.hints -= 1
            if self.last < self.number:
                msg = i18n.get(self.lang, "game.guess_hint_smaller", guess=self.last)
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                msg = i18n.get(self.lang, "game.guess_hint_larger", guess=self.last)
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            msg = i18n.get(self.lang, "game.guess_out_of_hints")
            await interaction.response.send_message(msg, ephemeral=True)

        button.disabled = True

class GuessGame():
    """
    The guessing number game
    Using the power of class chain reaction
    """
    def __init__(self, ctx:commands.Context, level:str, lang="en") -> None:
        self.ctx = ctx
        self.level = level
        self.lang = lang

    async def start(self):
        num_limit = guess_level_convert(self.level)
        number = random.randint(1, num_limit)
        game_view = GuessGameView(number, 5, 3, self.level, lang=self.lang)
        msg = i18n.get(self.lang, "game.guess_start_reply", level=self.level)
        await self.ctx.reply(msg, view=game_view)

class ResignButton(View):
    def __init__(self, ctx:commands.Context, lang="en"):
        super().__init__(timeout=20)
        self.ctx = ctx
        self.lang = lang
        self.value = None
        for child in self.children:
            if isinstance(child, Button):
                if child.custom_id == 'delacc':
                    child.label = i18n.get(self.lang, "game.resign_button_delete")
                elif child.custom_id == 'canceldel':
                    child.label = i18n.get(self.lang, "game.resign_button_cancel")

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    @button(label='Hapus Akun', style=discord.ButtonStyle.danger, custom_id='delacc')
    async def delete_account(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = i18n.get(self.lang, "game.resign_button_not_allowed")
            await interaction.response.send_message(msg, ephemeral=True)
            return
        
        user_record = await db.user.find_unique(where={'id': interaction.user.id}, include={'guild': True})
        if not user_record:
            msg = i18n.get(self.lang, "game.resign_not_found")
            return await interaction.response.send_message(msg, ephemeral=True)

        name = user_record.data['name']
        
        # Legacy Logic: Throne Transfer
        if user_record.guild and user_record.guild.ownerId == interaction.user.id:
            guild = user_record.guild
            # Find all members except the owner
            members = await db.user.find_many(where={
                'guildId': guild.id,
                'NOT': {'id': interaction.user.id}
            })
            
            if members:
                # Find the strongest member (highest level, then karma)
                new_owner = sorted(members, key=lambda u: (u.data.get('level', 1), u.data.get('karma', 0)), reverse=True)[0]
                new_owner_name = new_owner.data.get('name', 'Seseorang')
                
                await db.guild.update(
                    where={'id': guild.id},
                    data={'ownerId': new_owner.id}
                )
                msg = i18n.get(self.lang, "game.resign_guild_transfer", name=name, guild=guild.name, new_owner=new_owner_name)
                await interaction.channel.send(msg)
            else:
                # No one else in the guild, delete it
                await db.guild.delete(where={'id': guild.id})
                msg = i18n.get(self.lang, "game.resign_guild_disbanded", name=guild.name)
                await interaction.channel.send(msg)

        await db.user.delete(where={'id': interaction.user.id})
        msg = i18n.get(self.lang, "game.resign_success", name=name)
        await interaction.response.send_message(msg)
        self.value = True
        self.stop()

    @button(label='Batalkan', style=discord.ButtonStyle.green, custom_id='canceldel')
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = i18n.get(self.lang, "game.resign_button_not_allowed")
            await interaction.response.send_message(msg, ephemeral=True)
            return
        msg = i18n.get(self.lang, "game.resign_cancel")
        await interaction.response.send_message(msg, ephemeral=True)
        self.value = False
        self.stop()


class ShopDropdown(discord.ui.Select):
    """
    Buy feature
    """
    def __init__(self, page:int, lang="en"):
        self.page = page
        self.lang = lang

        with open('./src/game/shop.json') as file:
            content = file.read()
            items = json.loads(content)

        options = []
        start_index = (self.page - 1) * 5
        end_index = self.page * 5
        for index, item in enumerate(items[start_index:end_index]):
            item_name = i18n.get(self.lang, f"game.item_{item['_id']}_name", default=item['name'])
            currency = i18n.get(self.lang, "game.paywith_koin") if item['paywith'] == "Koin" else i18n.get(self.lang, "game.paywith_karma")
            desc_text = f"Harga: {item['cost']} {currency}" if self.lang == "id" else f"Price: {item['cost']} {currency}"
            
            options.append(discord.SelectOption(
                            label = f"{index + start_index + 1}. {item_name}", 
                            description=desc_text, 
                            value=item['_id']
                            )
                        )

        placeholder_text = i18n.get(self.lang, "game.shop_select_item")
        super().__init__(custom_id="shopdrop", placeholder=placeholder_text, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        with open('./src/game/shop.json') as file:
            content = file.read()
            items = json.loads(content)

        item_id = self.values[0]
        user_record = await db.user.find_unique(where={'id': interaction.user.id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            msg = i18n.get(self.lang, "game.use_account_issue")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        data = user_record.data
        inventory = user_record.inventory
        db_dict = {item['_id']: item for item in items}
        
        matched_item = db_dict[item_id]
        currency_key = 'coins' if matched_item['paywith'] == "Koin" else 'karma'
        current_money = data[currency_key]
        
        if current_money < matched_item['cost']:
            paywith_name = i18n.get(self.lang, "game.paywith_koin") if matched_item['paywith'] == "Koin" else i18n.get(self.lang, "game.paywith_karma")
            if self.lang == "en":
                msg = f"Oops!\nYour {paywith_name.lower()} are not enough to buy this item!"
            else:
                msg = f"Waduh!\n{paywith_name}mu tidak cukup untuk membeli barang ini!"
            return await interaction.response.send_message(msg, ephemeral=True)

        # Handle items, skills, and equipment correctly
        user_items = inventory.items if isinstance(inventory.items, list) else []
        user_skills = inventory.skills if isinstance(inventory.skills, list) else []
        user_equipments = inventory.equipments if isinstance(inventory.equipments, list) else []
        
        target_field = 'items'
        current_list = user_items
        
        if '1-' in item_id:
            target_field = 'equipments'
            current_list = user_equipments
        elif '2-' in item_id:
            target_field = 'skills'
            current_list = user_skills
            
        mongo_dict = {item['_id']: item for item in current_list}
        
        if item_id in mongo_dict:
            if '1-' in item_id:
                msg = i18n.get(self.lang, "game.shop_equipment_bought")
                return await interaction.response.send_message(msg, ephemeral=True)
            if '2-' in item_id:
                msg = i18n.get(self.lang, "game.shop_skill_learned")
                return await interaction.response.send_message(msg, ephemeral=True)
            
            for item in current_list:
                if item['_id'] == item_id:
                    item['owned'] = item.get('owned', 0) + 1
                    break
        else:
            new_item = matched_item.copy()
            new_item.pop('cost')
            new_item.pop('paywith')
            new_item['owned'] = 1
            current_list.append(new_item)

        # Deduct money
        data[currency_key] -= matched_item['cost']
        
        # Update DB
        await db.user.update(
            where={'id': interaction.user.id},
            data={
                'data': Json(data),
                'inventory': {
                    'update': {target_field: Json(current_list)}
                }
            }
        )

        item_name = i18n.get(self.lang, f"game.item_{item_id}_name", default=matched_item['name'])
        msg = i18n.get(self.lang, "game.shop_buy_success", name=item_name)
        await interaction.response.send_message(msg, ephemeral=True)

class PaginatedEnemyView(View):
    def __init__(self, ctx, lang="en"):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.lang = lang
        self.tiers = ['boss', 'bonus', 'elite', 'high', 'normal', 'low']
        self.current_tier_index = 0
        self.enemies = []

    async def get_embed(self):
        tier = self.tiers[self.current_tier_index]
        enemy_path = path.join(path.dirname(__file__), '..', 'src', 'game', 'enemies', f'{tier}.json')
        with open(enemy_path, 'r') as file:
            self.enemies = json.load(file)
        
        strongest = max(self.enemies, key=lambda x: x['hp'] + x['atk'] + x['def'] + x['agl'])
        
        title = i18n.get(self.lang, "game.bestiary_title", tier=tier.title())
        desc = i18n.get(self.lang, "game.bestiary_desc", tier=tier.upper())
        embed = discord.Embed(title=title, color=0xff0000 if tier == 'boss' else 0x3498db)
        embed.description = desc
        
        for index, enemy in enumerate(self.enemies):
            enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(enemy['name'])}_name", default=enemy['name'])
            embed.add_field(
                name=f"{index+1}. {enemy_name} ({enemy['tier']})",
                value=f"**HP**: `{enemy['hp']}` | **Stats**: `{enemy['atk']}/{enemy['def']}/{enemy['agl']}`",
                inline=False
            )
            
        if strongest.get('avatar'):
            embed.set_thumbnail(url=strongest['avatar'])
            
        footer_text = i18n.get(self.lang, "game.bestiary_footer", current=self.current_tier_index + 1, total=len(self.tiers))
        embed.set_footer(text=footer_text)
        
        self.clear_items()
        self.add_item(self.prev_page)
        self.add_item(self.destroy)
        self.add_item(self.next_page)
        self.add_item(SpecificEnemyDropdown(self.enemies, lang=self.lang))
        
        return embed

    @discord.ui.button(label='◀', style=discord.ButtonStyle.blurple)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = i18n.get(self.lang, "game.bestiary_not_owner")
            return await interaction.response.send_message(msg, ephemeral=True)
        self.current_tier_index = (self.current_tier_index - 1) % len(self.tiers)
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='▶', style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = i18n.get(self.lang, "game.bestiary_not_owner")
            return await interaction.response.send_message(msg, ephemeral=True)
        self.current_tier_index = (self.current_tier_index + 1) % len(self.tiers)
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='✖', style=discord.ButtonStyle.danger)
    async def destroy(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = i18n.get(self.lang, "game.bestiary_not_owner")
            return await interaction.response.send_message(msg, ephemeral=True)
        await interaction.message.delete()

class EnemyDropdown(discord.ui.Select):
    def __init__(self, lang="en"):
        self.lang = lang
        options = []
        options.append(discord.SelectOption(
                label='Boss',
                value='boss'
            ))
        options.append(discord.SelectOption(
                label='Elite',
                value='elite'
            ))
        options.append(discord.SelectOption(
                label='High',
                value='high'
            ))
        options.append(discord.SelectOption(
                label='Normal',
                value='normal'
            ))
        options.append(discord.SelectOption(
                label='Bonus',
                value='bonus'
            ))
        options.append(discord.SelectOption(
                label='Low',
                value='low'
            ))
        placeholder_lbl = "Level Musuh" if lang == "id" else "Enemy Tier"
        super().__init__(custom_id="enemydrop", placeholder=placeholder_lbl, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        enemy_path = path.join(path.dirname(__file__), '..', 'src', 'game', 'enemies', f'{self.values[0]}.json')
        with open(enemy_path, 'r') as file:
            enemies = json.load(file)
        
        # Find the strongest enemy (highest total stats + HP)
        strongest = max(enemies, key=lambda x: x['hp'] + x['atk'] + x['def'] + x['agl'])
        
        title_lbl = i18n.get(self.lang, "game.bestiary_title", tier=self.values[0].title())
        embed = discord.Embed(title=title_lbl, color=interaction.user.color)
        for index, enemy in enumerate(enemies):
            enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(enemy['name'])}_name", default=enemy['name'])
            embed.add_field(
                name=f"{index+1}. {enemy_name} ({enemy['tier']})",
                value=f"**HP**: `{enemy['hp']}` | **Stats**: `{enemy['atk']}/{enemy['def']}/{enemy['agl']}`",
                inline=False
                )
        
        if strongest.get('avatar'):
            embed.set_thumbnail(url=strongest['avatar'])
        else:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
        footer_text = "Pilih musuh dari dropdown di bawah untuk melihat detail!" if self.lang == "id" else "Choose enemy from the dropdown below for details!"
        embed.set_footer(text=footer_text)
        await interaction.response.edit_message(content='', embed=embed, view=EnemyView(enemies, lang=self.lang))

class SpecificEnemyDropdown(discord.ui.Select):
    def __init__(self, enemies: list, lang="en"):
        self.lang = lang
        options = []
        for index, enemy in enumerate(enemies):
            enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(enemy['name'])}_name", default=enemy['name'])
            options.append(discord.SelectOption(
                label=f"{enemy_name}",
                value=str(index),
                description=f"{enemy['tier']} - HP: {enemy['hp']}",
                emoji="👹"
            ))
        placeholder_lbl = i18n.get(self.lang, "game.bestiary_select_placeholder")
        super().__init__(placeholder=placeholder_lbl, min_values=1, max_values=1, options=options)
        self.enemies = enemies

    async def callback(self, interaction: discord.Interaction):
        enemy = self.enemies[int(self.values[0])]
        enemy_name = i18n.get(self.lang, f"game.enemy_{to_key(enemy['name'])}_name", default=enemy['name'])
        enemy_desc = i18n.get(self.lang, f"game.enemy_{to_key(enemy['name'])}_desc", default=enemy['desc'])
        
        detail_title = i18n.get(self.lang, "game.bestiary_detail_title", name=enemy_name)
        embed = discord.Embed(title=detail_title, description=f"*{enemy_desc}*", color=discord.Color.from_str(enemy.get('color', '#ff0000')))
        
        tier_lbl = i18n.get(self.lang, "game.bestiary_tier")
        embed.add_field(name=tier_lbl, value=f"`{enemy['tier']}`", inline=True)
        embed.add_field(name="HP", value=f"`{enemy['hp']}`", inline=True)
        embed.add_field(name="Stats (A/D/Ag)", value=f"`{enemy['atk']}/{enemy['def']}/{enemy['agl']}`", inline=True)
        
        if enemy.get('skills'):
            skills_lbl = i18n.get(self.lang, "game.bestiary_skills")
            skills_fmt = []
            for idx, s in enumerate(enemy['skills']):
                key = f"game.enemy_skill_{to_key(enemy['name'])}_{idx}_name"
                name_val = i18n.get(self.lang, key, default=s['name'])
                skills_fmt.append(f"✨ **{name_val}**: `{s['func']}`")
            skill_list = "\n".join(skills_fmt)
            embed.add_field(name=skills_lbl, value=skill_list, inline=False)
            
        if enemy.get('reward'):
            rewards_lbl = i18n.get(self.lang, "game.bestiary_rewards")
            rewards = ", ".join(enemy['reward'])
            embed.add_field(name=rewards_lbl, value=f"`{rewards}`", inline=False)
            
        if enemy.get('avatar'):
            embed.set_thumbnail(url=enemy['avatar'])
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

class EnemyView(View):
    def __init__(self, enemies: list = None, lang="en"):
        super().__init__(timeout=120)
        if enemies:
            self.add_item(SpecificEnemyDropdown(enemies, lang=lang))
        else:
            self.add_item(EnemyDropdown(lang=lang))
        
class ShopView(View):
    """
    Currently not up to write DRY code
    """
    def __init__(self, ctx, items, data, lang="en"):
        self.current_page = 1
        super().__init__(timeout=40)
        self.ctx = ctx
        self.items = items
        self.data = data
        self.owned = []
        self.lang = lang
        self.add_item(ShopDropdown(self.current_page, lang=self.lang))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)
        
    def get_owned_display(self, item):
        item_id = item['_id']
        inventory = self.data.get('inventory', {})
        
        check_list = []
        if '1-' in item_id: check_list = inventory.get('equipments', [])
        elif '2-' in item_id: check_list = inventory.get('skills', [])
        else: check_list = inventory.get('items', [])
        
        if not isinstance(check_list, list): check_list = []
        
        for owned_item in check_list:
            if owned_item['_id'] == item_id:
                count = owned_item.get('owned', 0)
                if item['type'] == 'Skill' or item['type'] == 'Equipment':
                    return i18n.get(self.lang, "game.shop_owned_yes")
                return str(count)
                
        if item['type'] == 'Skill' or item['type'] == 'Equipment':
            return i18n.get(self.lang, "game.shop_owned_no")
        return "0"

    async def update_embed(self, last_page):
        title = i18n.get(self.lang, "game.shop_title")
        desc = i18n.get(self.lang, "game.shop_desc")
        footer = i18n.get(self.lang, "game.shop_footer")
        
        embed = discord.Embed(title=title, color=0xFFFF00)
        embed.description = desc
        embed.set_footer(text=footer)
        embed.set_thumbnail(url=getenv('xaneria'))

        self.owned.clear()
        start_index = (self.current_page - 1) * 5
        end_index = start_index + 5

        type_text = "Type" if self.lang == "en" else "Tipe"
        price_text = "Price" if self.lang == "en" else "Harga"
        owned_text = "Owned" if self.lang == "en" else "Dimiliki"

        for index, item in enumerate(self.items[start_index:end_index], start=start_index + 1):
            owned_display = self.get_owned_display(item)
            self.owned.append(owned_display)
            
            item_name = i18n.get(self.lang, f"game.item_{item['_id']}_name", default=item['name'])
            item_desc = i18n.get(self.lang, f"game.item_{item['_id']}_desc", default=item['desc'])
            item_type_label = i18n.get(self.lang, f"game.type_{to_key(item['type'])}")
            currency_label = i18n.get(self.lang, "game.paywith_koin") if item['paywith'] == "Koin" else i18n.get(self.lang, "game.paywith_karma")
            
            embed.add_field(
                name=f"{index}. {item_name}",
                value=f"**`{item_desc}`**\n({item['func']})\n**{type_text}:** {item_type_label}\n**{price_text}:** {item['cost']} {currency_label}\n**{owned_text}:** {owned_display}",
                inline=False
            )

        self.clear_items()
        self.add_item(self.back)
        self.add_item(self._delete)
        self.add_item(self.next)
        self.add_item(ShopDropdown(self.current_page, lang=self.lang))

        return embed


    @discord.ui.button(label='◀', custom_id='back', style=discord.ButtonStyle.blurple)
    async def back(self, interaction: discord.Interaction, button:Button):
        max_page = (len(self.items) - 1) // 5 + 1
        last_page = self.current_page
        self.current_page = self.current_page - 1 if self.current_page > 1 else max_page
        embed=await self.update_embed(last_page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='✖', style=discord.ButtonStyle.danger, custom_id='delete')
    async def _delete(self, interaction: discord.Interaction, button:Button):
        await interaction.message.delete()

    @discord.ui.button(label='▶', custom_id='next', style=discord.ButtonStyle.blurple)
    async def next(self, interaction: discord.Interaction, button:Button):
        max_page = (len(self.items) - 1) // 5 + 1
        last_page = self.current_page
        self.current_page = self.current_page + 1 if self.current_page < max_page else 1
        embed = await self.update_embed(last_page)
        await interaction.response.edit_message(embed=embed, view=self)

def convert_to_db_stat(func:list):
    match func[0]:
        case "atk":
            func[0] = 'attack'
        case "def":
            func[0] = 'defense'
        case "agl":
            func[0] = 'agility'
    return func

class UseDropdown(discord.ui.Select):
    def __init__(self, items:list, ctx:commands.Context, lang="en") -> None:
        self.lang = lang
        options = []
        for index, item in enumerate(items, start=1):
            item_name = i18n.get(self.lang, f"game.item_{item['_id']}_name", default=item['name'])
            options.append(discord.SelectOption(
                label=f"{index}. {item_name} ({item['usefor']})" if not item['usefor'] == 'free' else f"{index}. {item_name}",
                description=f"{item['func'].upper()}",
                value = item['_id']
            ))
        if not options:
            options.append(discord.SelectOption(
                    label=i18n.get(self.lang, "game.use_no_items"),
                    value="none",
                    description=i18n.get(self.lang, "game.use_no_items_shop")
                )
            )
        placeholder_text = i18n.get(self.lang, "game.use_placeholder")
        super().__init__(custom_id="usedrop", placeholder=placeholder_text, min_values=1, max_values=1, options=options)
        self.items = items
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
        # Click -> Check item_id and owned -> Add stats accordingly
        if interaction.message.mentions[0] != interaction.user:
            msg = i18n.get(self.lang, "game.use_not_owner")
            return await interaction.response.send_message(msg, ephemeral=True)
        if self.values[0] == 'none':
            msg = i18n.get(self.lang, "game.use_no_items_shop")
            return await interaction.response.send_message(msg, ephemeral=True)
        
        user_record = await db.user.find_unique(where={'id': interaction.user.id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            msg = i18n.get(self.lang, "game.use_account_issue")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        data = user_record.data
        inventory = user_record.inventory
        item_id = self.values[0]
        
        # Check if it's an equipment (prefix '1-')
        if '1-' in item_id:
            equipments = inventory.equipments if isinstance(inventory.equipments, list) else []
            matching = [x for x in equipments if x['_id'] == item_id]
            
            if matching: # Unequip
                item_to_unequip = matching[0]
                func = item_to_unequip['func'].split('+')
                stat_key = self.convert_to_db_stat_key(func[0])
                stat_value = int(func[1])
                
                new_equipments = [x for x in equipments if x['_id'] != item_id]
                data[stat_key] -= stat_value
                
                await db.user.update(
                    where={'id': interaction.user.id},
                    data={
                        'data': Json(data),
                        'inventory': {
                            'update': {'equipments': Json(new_equipments)}
                        }
                    }
                )
                item_name = i18n.get(self.lang, f"game.item_{item_to_unequip['_id']}_name", default=item_to_unequip['name'])
                msg = i18n.get(self.lang, "game.use_unequip_success", name=item_name)
                await interaction.response.send_message(msg)
            
            else: # Equip
                all_items = inventory.items if isinstance(inventory.items, list) else []
                item_match = [x for x in all_items if x['_id'] == item_id]
                
                if not item_match:
                    msg = i18n.get(self.lang, "game.use_not_found")
                    return await interaction.response.send_message(msg, ephemeral=True)
                
                item_to_equip = item_match[0]
                func = item_to_equip['func'].split('+')
                stat_key = self.convert_to_db_stat_key(func[0])
                stat_value = int(func[1])
                
                same_type = [x for x in equipments if x.get('usefor') == item_to_equip.get('usefor')]
                if same_type:
                    old_item = same_type[0]
                    old_func = old_item['func'].split('+')
                    old_stat_key = self.convert_to_db_stat_key(old_func[0])
                    data[old_stat_key] -= int(old_func[1])
                    equipments = [x for x in equipments if x['_id'] != old_item['_id']]
                
                equipments.append(item_to_equip)
                data[stat_key] += stat_value
                
                await db.user.update(
                    where={'id': interaction.user.id},
                    data={
                        'data': Json(data),
                        'inventory': {
                            'update': {'equipments': Json(equipments)}
                        }
                    }
                )
                item_name = i18n.get(self.lang, f"game.item_{item_to_equip['_id']}_name", default=item_to_equip['name'])
                msg = i18n.get(self.lang, "game.use_equip_success", name=item_name)
                await interaction.response.send_message(msg)
        
        else:
            # Consumable or Skill
            all_items = inventory.items if isinstance(inventory.items, list) else []
            item_match = [x for x in all_items if x['_id'] == item_id]
            if not item_match:
                msg = i18n.get(self.lang, "game.use_not_found")
                return await interaction.response.send_message(msg, ephemeral=True)
            
            item_to_use = item_match[0]
            item_name = i18n.get(self.lang, f"game.item_{item_to_use['_id']}_name", default=item_to_use['name'])
            msg = i18n.get(self.lang, "game.use_equip_success", name=item_name)
            await interaction.response.send_message(msg)
            
            game_inst = GameInstance(self.ctx, interaction.user, None, self.ctx.bot)
            game_inst.lang = self.lang
            await game_inst.func_converter(item_to_use['func'], interaction.user, None)
            await asyncio.sleep(1)
            await level_up(self.ctx)

    def convert_to_db_stat_key(self, short_stat):
        mapping = {
            'ATK': 'attack',
            'DEF': 'defense',
            'AGL': 'agility',
            'HP': 'hp'
        }
        return mapping.get(short_stat.upper(), short_stat.lower())

    
class UseView(View):
    def __init__(self, items:list, ctx:commands.Context, lang="en"):
        super().__init__(timeout=30)
        self.add_item(UseDropdown(items, ctx, lang=lang))

class LeaderboardView(View):
    def __init__(self, ctx, data: list, title: str, type: str = "player", lang="en"):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.data = data
        self.title = title
        self.type = type
        self.lang = lang
        self.current_page = 0
        self.items_per_page = 10
        self.max_pages = (len(data) - 1) // self.items_per_page + 1

    async def get_embed(self):
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        items = self.data[start_idx:end_idx]
        
        embed = discord.Embed(title=self.title, color=0xffd700) # Gold
        embed.description = i18n.get(
            self.lang, 
            "game.leaderboard_desc", 
            start=start_idx + 1, 
            end=min(end_idx, len(self.data)), 
            total=len(self.data)
        )
        
        for i, item in enumerate(items, start=start_idx + 1):
            if self.type == "player":
                name = item.data.get('name', 'Unknown')
                level = item.data.get('level', 1)
                karma = item.data.get('karma', 0)
                field_val = i18n.get(self.lang, "game.leaderboard_member_field", level=level, karma=karma)
                embed.add_field(
                    name=f"{i}. {name}",
                    value=field_val,
                    inline=False
                )
            else: # guild
                name = item.name
                member_count = len(item.members) if hasattr(item, 'members') else 0
                field_val = i18n.get(self.lang, "game.leaderboard_guild_field", count=member_count, owner=item.ownerId)
                embed.add_field(
                    name=f"{i}. {name}",
                    value=field_val,
                    inline=False
                )
        
        page_lbl = "Halaman" if self.lang == "id" else "Page"
        embed.set_footer(text=f"{page_lbl} {self.current_page + 1}/{self.max_pages}")
        return embed

    @discord.ui.button(label='◀', style=discord.ButtonStyle.blurple)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = "Bukan tombolmu, Sang Pemimpi!" if self.lang == "id" else "Not your button, Dreamer!"
            return await interaction.response.send_message(msg, ephemeral=True)
        self.current_page = (self.current_page - 1) % self.max_pages
        await interaction.response.edit_message(embed=await self.get_embed())

    @discord.ui.button(label='✖', style=discord.ButtonStyle.danger)
    async def destroy(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = "Hanya yang memanggil ini yang bisa menutupnya!" if self.lang == "id" else "Only the caller can close this!"
            return await interaction.response.send_message(msg, ephemeral=True)
        await interaction.message.delete()

    @discord.ui.button(label='▶', style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = "Bukan tombolmu, Sang Pemimpi!" if self.lang == "id" else "Not your button, Dreamer!"
            return await interaction.response.send_message(msg, ephemeral=True)
        self.current_page = (self.current_page + 1) % self.max_pages
        await interaction.response.edit_message(embed=await self.get_embed())

class Game(commands.Cog):
    """
    Kumpulan command game RPG RVDiA (Re:Volution).
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name='game')
    @check_blacklist()
    async def game(self, ctx:commands.Context) -> None:
        """
        Kumpulan command khusus untuk RVDIA. [GROUP]
        """
        await self.account(ctx)
        pass

    @game.command(aliases=['reg'], description='Daftarkan akunmu ke Re:Volution!')
    @app_commands.describe(name='Nama apa yang ingin kamu pakai di dalam gamenya?')
    @check_blacklist()
    async def register(self, ctx:commands.Context, *, name:str=None):
        """
        Daftarkan akunmu ke Re:Volution ~ The Dream World!
        """
        name = name or ctx.author.name
        lang = await get_user_lang(ctx.author.id)
        user_data = await db.user.find_unique(where={'id': ctx.author.id})
        if user_data:
            msg = i18n.get(lang, "game.register_already")
            return await ctx.reply(msg)
            
        # Create User and Inventory together
        data_to_save = {**default_data}
        data_to_save['name'] = name
        
        await db.user.create(data={
            'id': ctx.author.id,
            'hp': 100,
            'max_hp': 100,
            'data': Json(data_to_save),
            'inventory': {
                'create': {
                    'items': Json([]),
                    'skills': Json([]),
                    'equipments': Json([])
                }
            }
        })
        
        msg = i18n.get(lang, "game.register_success", name=name)
        await ctx.reply(msg)
        await asyncio.sleep(0.7)
        await self.account(ctx)
    
    @game.command(description="Tunjukkan siapa Sang Pemimpi terkuat saat ini!")
    @check_blacklist()
    async def leaderboard(self, ctx:commands.Context):
        """
        Lihat siapa yang terkuat di Re:Volution ~ The Dream World!
        """
        lang = await get_user_lang(ctx.author.id)
        users = await db.user.find_many()
        if not users:
            msg = i18n.get(lang, "game.leaderboard_empty")
            return await ctx.reply(msg)
            
        # Sort by level DESC, then karma DESC
        sorted_users = sorted(users, key=lambda u: (u.data.get('level', 1), u.data.get('karma', 0)), reverse=True)
        top_100 = sorted_users[:100]
        
        title = i18n.get(lang, "game.leaderboard_title")
        view = LeaderboardView(ctx, top_100, title, type="player", lang=lang)
        embed = await view.get_embed()
        await ctx.reply(embed=embed, view=view)

    @game.command(description='Panduan bermain Re:Volution.')
    @check_blacklist()
    async def guide(self, ctx:commands.Context):
        """
        Panduan bermain Re:Volution ~ The Dream World!
        """
        lang = await get_user_lang(ctx.author.id)
        title = i18n.get(lang, "game.guide_title")
        desc = i18n.get(lang, "game.guide_desc")
        footer = i18n.get(lang, "game.guide_footer")
        
        embed = discord.Embed(title=title, color=0x86273d)
        embed.description = desc
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=footer)
        await ctx.reply(embed=embed)

    @game.command(description='Lihat catatan pembaruan terbaru Re:Volution!')
    @check_blacklist()
    async def changelog(self, ctx:commands.Context):
        """
        Catatan pembaruan Re:Volution ~ The Dream World!
        """
        lang = await get_user_lang(ctx.author.id)
        title = i18n.get(lang, "game.changelog_title")
        desc = i18n.get(lang, "game.changelog_desc")
        footer = i18n.get(lang, "game.changelog_footer")
        
        embed = discord.Embed(title=title, color=0x86273d)
        embed.description = desc
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=footer)
        await ctx.reply(embed=embed)

    @game.command(description="Menghapuskan akunmu dari Re:Volution.")
    @has_registered()
    @check_blacklist()
    async def resign(self, ctx:commands.Context):
        """
        Menghapuskan akunmu dari Re:Volution ~ The Dream World.
        """
        lang = await get_user_lang(ctx.author.id)
        view = ResignButton(ctx, lang=lang)
        prompt = i18n.get(lang, "game.resign_prompt")
        await ctx.reply(prompt, view=view)
        await view.wait()
        if view.value is None:
            timeout_msg = i18n.get(lang, "game.resign_timeout")
            await ctx.channel.send(timeout_msg)
        elif view.value:
            # Account deletion is handled inside the ResignButton view
            pass

    @game.command(aliases=['login'], description='Dapatkan bonus login harian!')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def daily(self, ctx:commands.Context):
        """
        Dapatkan bonus login harian!
        """
        user_record = await db.user.find_unique(where={'id': ctx.author.id})
        data = user_record.data
        
        last_login_raw = data.get('last_login')
        if not last_login_raw:
            last_login = datetime.now() - timedelta(days=1)
        elif isinstance(last_login_raw, str):
            last_login = datetime.fromisoformat(last_login_raw)
        else:
            last_login = last_login_raw # Fallback if it's already a datetime object
            
        current_time = datetime.now()
        delta_time = current_time - last_login

        next_login = last_login + timedelta(hours=24)
        next_login_unix = int(time.mktime(next_login.timetuple()))
        lang = await get_user_lang(ctx.author.id)

        if delta_time.total_seconds() <= 24*60*60:
            msg = i18n.get(lang, "game.daily_already", timestamp=next_login_unix)
            return await ctx.reply(msg)
        
        else:
            new_coins = random.randint(15, 25)
            new_karma = random.randint(1, 5)
            new_exp = random.randint(10, 20)
            
            data['coins'] += new_coins
            data['karma'] += new_karma
            data['exp'] += new_exp
            data['last_login'] = current_time.isoformat()
            
            await db.user.update(
                where={'id': ctx.author.id},
                data={'data': Json(data)}
            )
            
            title = i18n.get(lang, "game.daily_success_title")
            footer_text = i18n.get(lang, "game.daily_footer")
            
            embed = discord.Embed(title=title, color=0x00FF00, timestamp=next_login)
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            
            reward_title = i18n.get(lang, "game.combat_reward_title")
            coins_lbl = i18n.get(lang, "game.paywith_koin") if lang == "en" else "Koin"
            reward_coins = f"{self.bot.coin_emoji_anim} `{new_coins}` {coins_lbl}"
            reward_karma = i18n.get(lang, "game.combat_reward_karma", amount=new_karma)
            reward_exp = i18n.get(lang, "game.combat_reward_exp", amount=new_exp)
            
            embed.add_field(
                name=reward_title,
                value=f"{reward_coins}\n{reward_karma}\n{reward_exp}!",
                inline=False
            )
            embed.set_footer(text=footer_text)
            await ctx.reply(embed=embed)
            level_uped = await level_up(ctx)
            if level_uped:
                return await send_level_up_msg(ctx)
            
    @game.command(name='account', aliases=['profile'], description='Lihat profil pengguna di Re:Volution!')
    @app_commands.describe(user='Pengguna mana yang ingin dilihat akunnya?')
    @app_commands.rename(user='pengguna')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def profile(self, ctx:commands.Context, *, user:discord.User=None):
        """
        Lihat profil pengguna di Re:Volution ~ The Dream World!
        """
        await self.account(ctx, user=user)

    @game.command(description='Perbaiki struktur data akunmu.')
    @has_registered()
    @check_blacklist()
    async def fix_account(self, ctx:commands.Context):
        """
        Gunakan ini jika akunmu mengalami masalah struktur data atau item tidak muncul di tempatnya.
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'inventory': True})
        if not user_record:
            msg = i18n.get(lang, "game.profile_not_registered")
            return await ctx.reply(msg)
            
        # 1. Fix User.data
        data = user_record.data
        updated_data = False
        for key, value in default_data.items():
            if key not in data:
                data[key] = value
                updated_data = True
        
        # 2. Fix Inventory distribution
        inventory = user_record.inventory
        if not inventory:
             await db.inventory.create(data={
                 'userId': ctx.author.id,
                 'items': Json([]),
                 'skills': Json([]),
                 'equipments': Json([])
             })
             inventory = await db.inventory.find_unique(where={'userId': ctx.author.id})

        all_items = inventory.items if isinstance(inventory.items, list) else []
        skills = inventory.skills if isinstance(inventory.skills, list) else []
        equipments = inventory.equipments if isinstance(inventory.equipments, list) else []
        
        new_items = []
        new_skills = skills
        new_equipments = equipments
        
        moved_skills = 0
        moved_equips = 0
        
        for item in all_items:
            item_id = item.get('_id', '')
            if item_id.startswith('1-'):
                if not any(e['_id'] == item_id for e in new_equipments):
                    new_equipments.append(item)
                    moved_equips += 1
            elif item_id.startswith('2-'):
                if not any(s['_id'] == item_id for s in new_skills):
                    new_skills.append(item)
                    moved_skills += 1
            else:
                new_items.append(item)
        
        # Update User data if changed
        if updated_data:
            await db.user.update(where={'id': ctx.author.id}, data={'data': Json(data)})
            
        # Update Inventory
        await db.inventory.update(
            where={'userId': ctx.author.id},
            data={
                'items': Json(new_items),
                'skills': Json(new_skills),
                'equipments': Json(new_equipments)
            }
        )
        
        msg = i18n.get(lang, "game.fix_success")
        if moved_skills > 0 or moved_equips > 0:
            skills_lbl = i18n.get(lang, "game.fix_moved_skills", count=moved_skills)
            equips_lbl = i18n.get(lang, "game.fix_moved_equips", count=moved_equips)
            msg += f"\n{skills_lbl}\n{equips_lbl}"
        if updated_data:
            data_lbl = i18n.get(lang, "game.fix_updated_data")
            msg += f"\n{data_lbl}"
        if moved_skills == 0 and moved_equips == 0 and not updated_data:
            msg = i18n.get(lang, "game.fix_already_optimal")
            
        await ctx.reply(msg)

    async def account(self, ctx:commands.Context, *, user:discord.User=None):
        """
        Tampilkan informasi akun Re:Volution-mu!
        """
        lang = await get_user_lang(ctx.author.id)
        target = user or ctx.author
        user_record = await db.user.find_unique(where={'id': target.id})
        
        if not user_record:
            msg = i18n.get(lang, "game.profile_not_registered")
            return await ctx.reply(msg)
        
        data = user_record.data
        
        # Premium Check
        is_p = user_record.premiumUntil and user_record.premiumUntil > datetime.now()
        title_prefix = "💎 " if is_p else ""
        
        title_lbl = i18n.get(lang, "game.profile_title", name=data['name'])
        embed = discord.Embed(title=f"{title_prefix}{title_lbl}", color=0x86273d)
        embed.set_thumbnail(url=target.display_avatar.url)
        
        # Display HP and Max HP
        hp_str = f"❤️ `{user_record.hp}/{user_record.max_hp}` HP"
        
        level_lbl = i18n.get(lang, "game.profile_level")
        exp_lbl = i18n.get(lang, "game.profile_exp")
        status_lbl = i18n.get(lang, "game.profile_status")
        stats_lbl = i18n.get(lang, "game.profile_stats")
        stats_val = i18n.get(lang, "game.profile_stats_val", atk=data['attack'], def_=data['defense'], agl=data['agility'])
        wealth_lbl = i18n.get(lang, "game.profile_wealth")
        wealth_val = i18n.get(lang, "game.profile_wealth_val", emoji=self.bot.coin_emoji, coins=data['coins'], karma=data['karma'])
        
        embed.add_field(name=level_lbl, value=f"🔰 `{data['level']}`", inline=True)
        embed.add_field(name=exp_lbl, value=f"⬆️ `{data['exp']}/{data['next_exp']}`", inline=True)
        embed.add_field(name=status_lbl, value=hp_str, inline=True)
        
        embed.add_field(name=stats_lbl, value=stats_val, inline=True)
        embed.add_field(name=wealth_lbl, value=wealth_val, inline=True)
        
        await ctx.reply(embed=embed)

    @game.command(description="Beli item atau perlengkapan perang!")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def shop(self, ctx:commands.Context):
        """
        Beli item atau perlengkapan perang!
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'inventory': True})
        if not user_record:
            msg = i18n.get(lang, "game.profile_not_registered")
            return await ctx.reply(msg)
            
        data = user_record.data
        inventory = user_record.inventory
        
        with open('./src/game/shop.json') as file:
            items = json.load(file)

        title = i18n.get(lang, "game.shop_title")
        desc = i18n.get(lang, "game.shop_desc")
        footer = i18n.get(lang, "game.shop_footer")

        embed = discord.Embed(title=title, color=0xFFFF00)
        embed.description = desc
        embed.set_footer(text=footer)
        embed.set_thumbnail(url=getenv('xaneria'))

        user_items = inventory.items if isinstance(inventory.items, list) else []
        user_skills = inventory.skills if isinstance(inventory.skills, list) else []
        user_equipments = inventory.equipments if isinstance(inventory.equipments, list) else []

        def get_owned_display(item):
            item_id = item['_id']
            check_list = user_items
            if '1-' in item_id: check_list = user_equipments
            elif '2-' in item_id: check_list = user_skills
            
            for owned_item in check_list:
                if owned_item['_id'] == item_id:
                    count = owned_item.get('owned', 0)
                    if item['type'] == 'Skill' or item['type'] == 'Equipment':
                        return i18n.get(lang, "game.shop_owned_yes")
                    return str(count)
            
            if item['type'] == 'Skill' or item['type'] == 'Equipment':
                return i18n.get(lang, "game.shop_owned_no")
            return "0"

        options_per_page = 5
        type_text = "Type" if lang == "en" else "Tipe"
        price_text = "Price" if lang == "en" else "Harga"
        owned_text = "Owned" if lang == "en" else "Dimiliki"

        for index, item in enumerate(items[:options_per_page], start=1):
            owned_display = get_owned_display(item)
            item_name = i18n.get(lang, f"game.item_{item['_id']}_name", default=item['name'])
            item_desc = i18n.get(lang, f"game.item_{item['_id']}_desc", default=item['desc'])
            item_type_label = i18n.get(lang, f"game.type_{to_key(item['type'])}")
            currency_label = i18n.get(lang, "game.paywith_koin") if item['paywith'] == "Koin" else i18n.get(lang, "game.paywith_karma")
            
            embed.add_field(
                name=f"{index}. {item_name}",
                value=f"**`{item_desc}`**\n({item['func']})\n**{type_text}:** {item_type_label}\n**{price_text}:** {item['cost']} {currency_label}\n**{owned_text}:** {owned_display}",
                inline=False
            )    @game.command(description='Bertualang di Re:Volution!')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def adventure(self, ctx:commands.Context):
        """
        Bertualang di Re:Volution ~ The Dream World!
        """
        lang = await get_user_lang(ctx.author.id)
        exp_gain = random.randint(10, 25)
        coin_gain = random.randint(15, 35)
        
        await give_rewards(ctx, ctx.author, exp_gain, coin_gain)
        msg = i18n.get(lang, "game.adventure_success", exp=exp_gain, coins=coin_gain)
        await ctx.reply(msg)

    @game.command(description='Tantang seseorang ke sebuah duel!')
    @app_commands.describe(member='Siapa yang ingin kamu lawan?')
    @app_commands.rename(member='pengguna')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def fight(self, ctx:commands.Context, *, member:discord.Member):
        """
        Tantang seseorang ke sebuah duel!
        """
        lang = await get_user_lang(ctx.author.id)
        if member.bot:
            msg = i18n.get(lang, "game.fight_bot_cannot_fight")
            return await ctx.reply(msg, ephemeral=True)
            
        rival_record = await db.user.find_unique(where={'id': member.id})
        if not rival_record:
            msg = i18n.get(lang, "errors.rival_no_account")
            return await ctx.reply(msg)
            
        game = GameInstance(ctx, ctx.author, member, self.bot)
        await game.start()


    @game.command(description='Lawan musuh-musuh yang ada di Re:Volution!')
    @app_commands.describe(enemy_tier='Musuh level berapa yang ingin kamu lawan?')
    @app_commands.rename(enemy_tier='level')
    @app_commands.describe(enemy_name='Nama musuh yang ingin kamu lawan?')
    @app_commands.rename(enemy_name = 'nama_musuh')
    @app_commands.choices(enemy_tier=[
        app_commands.Choice(name='BOSS', value='boss'),
        app_commands.Choice(name='BONUS', value='bonus'),
        app_commands.Choice(name='ELITE', value='elite'),
        app_commands.Choice(name='High (Tinggi)', value='high'),
        app_commands.Choice(name="Normal (Sedang)", value='normal'),
        app_commands.Choice(name='Low (Rendah)', value='low')
    ])
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def battle(self, ctx:commands.Context, enemy_tier:app_commands.Choice[str], enemy_name:str=None): # Choice[value_type]
        """
        Lawan musuh-musuh yang ada di Re:Volution ~ The Dream World!
        """
        lang = await get_user_lang(ctx.author.id)
        with open(f'./src/game/enemies/{enemy_tier.value}.json') as file:
            content = file.read()
            enemies = json.loads(content)
            
        enemy = None
        
        if enemy_name:
            query = enemy_name.lower()
            # 1. Try exact match first
            for e in enemies:
                if e['name'].lower() == query:
                    enemy = e
                    break
            
            # 2. Substring matching
            if not enemy:
                for e in enemies:
                    if query in e['name'].lower():
                        enemy = e
                        break

            # 3. Fuzzy finder logic
            if not enemy:
                enemy_names = [e['name'] for e in enemies]
                matches = difflib.get_close_matches(enemy_name, enemy_names, n=1, cutoff=0.4)
                if matches:
                    matched_name = matches[0]
                    for e in enemies:
                        if e['name'] == matched_name:
                            enemy = e
                            break

            if enemy == None:
                msg = i18n.get(lang, "game.battle_enemy_not_found", name=enemy_name, tier=enemy_tier.value.upper())
                return await ctx.reply(msg, ephemeral=True)
        else:
            enemy = random.choice(enemies)

        game = GameInstance(ctx, ctx.author, enemy, self.bot)
        await game.start()


    @game.command(description='Lihat daftar musuh yang muncul di Re:Volution!', aliases=['enemy'])
    @has_registered()
    async def enemies(self, ctx:commands.Context):
        """
        Lihat daftar musuh yang muncul di Re:Volution ~ The Dream World!
        """
        lang = await get_user_lang(ctx.author.id)
        view = PaginatedEnemyView(ctx, lang=lang)
        embed = await view.get_embed()
        await ctx.reply(embed=embed, view=view)


    @game.command(description='Request untuk pemindahan data akun.')
    @app_commands.describe(old_acc = "Akun Discord lamamu atau ID akun Discord lamamu.")
    @app_commands.describe(reason = "Alasan request pemindahan data akun.")
    @app_commands.rename(reason = "alasan")
    @app_commands.rename(old_acc = "akun_lama")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def transfer(self, ctx:commands.Context, old_acc:discord.User, *, reason:str):
        """
        Request untuk pemindahan data akun.
        """
        lang = await get_user_lang(ctx.author.id)
        current_acc_record = await db.user.find_unique(where={'id': ctx.author.id})
        old_acc_record = await db.user.find_unique(where={'id': old_acc.id})
        
        if not old_acc_record:
            msg = i18n.get(lang, "game.transfer_not_found")
            return await ctx.reply(msg, ephemeral=True)
        
        if ctx.author.id == old_acc.id:
            msg = i18n.get(lang, "game.transfer_same_account")
            return await ctx.reply(msg, ephemeral=True)
        
        title_lbl = i18n.get(lang, "game.transfer_embed_title")
        embed = discord.Embed(title=title_lbl, color=ctx.author.color, timestamp=ctx.message.created_at)
        
        old_lbl = i18n.get(lang, "game.transfer_embed_old")
        embed.add_field(
            name=old_lbl,
            value=f"Nama: {old_acc_record.data['name']}\nID: {old_acc_record.id}",
            inline=False
        )

        new_lbl = i18n.get(lang, "game.transfer_embed_new")
        embed.add_field(
            name=new_lbl,
            value=f"Nama: {current_acc_record.data['name']}\nID: {current_acc_record.id}",
            inline=False
        )

        reason_lbl = i18n.get(lang, "game.transfer_embed_reason")
        embed.add_field(
            name=reason_lbl,
            value=reason,
            inline=False
        )

        embed.set_author(name=ctx.author)
        footer_lbl = i18n.get(lang, "game.transfer_embed_footer")
        embed.set_footer(text=footer_lbl)
        
        channel = self.bot.get_channel(1115422709585817710)
        if channel:
            await channel.send(embed=embed)
        
        success_msg = i18n.get(lang, "game.transfer_request_success")
        await ctx.send(success_msg)


    @game.command(description='Ayo main tebak angka bersamaku!')
    @app_commands.describe(level='Tingkat kesulitan mana yang akan kamu pilih?')
    @app_commands.choices(level=[
        app_commands.Choice(name='SUPER', value='SUPER'),
        app_commands.Choice(name='HARD', value='HARD'),
        app_commands.Choice(name="NORMAL", value='NORMAL'),
        app_commands.Choice(name='EASY', value='EASY')
    ])
    @check_blacklist()
    async def guess(self, ctx:commands.Context, level:app_commands.Choice[str]):
        """
        Ayo main tebak angka bersamaku!
        """
        lang = await get_user_lang(ctx.author.id)
        game_instance = GuessGame(ctx, level.value, lang=lang)
        await game_instance.start()

    @game.command(description = "Gunakan barang atau perlengkapan perang!")
    @app_commands.describe(type = 'Jenis barang yang ingin digunakan?')
    @app_commands.choices(type=[
        app_commands.Choice(name='Barang (Consumable)', value='item'),
        app_commands.Choice(name='Perlengkapan (Equipment)', value='equipment')
    ])
    @app_commands.rename(type = 'jenis')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def use(self, ctx:commands.Context, type:app_commands.Choice[str]):
        """
        Gunakan barang atau perlengkapan perang!
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            msg = i18n.get(lang, "game.use_not_registered")
            return await ctx.reply(msg, ephemeral=True)
            
        inventory = user_record.inventory
        user_items = inventory.items if isinstance(inventory.items, list) else []
        
        match type.value:
            case "item":
                things = [item for item in user_items if "0-" in item['_id'] and item.get('usefor') == "free"]
            
            case "equipment":
                things = [item for item in user_items if "1-" in item['_id']]

            case _:
                msg = i18n.get(lang, "game.use_invalid_option")
                return await ctx.reply(msg, ephemeral=True)
            
        view = UseView(things, ctx, lang=lang)
        await ctx.reply(f'{ctx.author.mention}', view=view)

    @commands.hybrid_group(name="guild", description="Sistem Guild Re:Volution", fallback="info")
    @check_blacklist()
    async def guild(self, ctx: commands.Context):
        """
        Lihat informasi guild kamu atau guild orang lain.
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            msg = i18n.get(lang, "game.guild_not_member")
            return await ctx.reply(msg, ephemeral=True)
        
        guild = user_record.guild
        members_count = await db.user.count(where={'guildId': guild.id})
        
        tagline_empty = i18n.get(lang, "game.guild_info_tagline_empty")
        embed = discord.Embed(title=guild.name, description=guild.tagline or tagline_empty, color=ctx.author.color)
        if guild.iconUrl:
            embed.set_thumbnail(url=guild.iconUrl)
        
        owner_name = i18n.get(lang, "game.guild_info_owner")
        embed.add_field(name=owner_name, value=f"<@{guild.ownerId}>")
        
        members_name = i18n.get(lang, "game.guild_info_members")
        members_value = i18n.get(lang, "game.guild_info_members_value", count=members_count)
        embed.add_field(name=members_name, value=members_value)
        
        date_str = guild.createdAt.strftime('%d/%m/%Y')
        footer_text = i18n.get(lang, "game.guild_info_footer", id=guild.id, date=date_str)
        embed.set_footer(text=footer_text)
        
        await ctx.reply(embed=embed)

    @guild.command(name="create", description="Buat guild baru! (Biaya: 5000 Koin)")
    @app_commands.describe(name="Nama guild impianmu")
    @check_blacklist()
    async def guild_create(self, ctx: commands.Context, name: str):
        """
        Buat guild baru untuk komunitasmu!
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id})
        if not user_record:
            msg = i18n.get(lang, "game.guild_not_registered")
            return await ctx.reply(msg, ephemeral=True)
        
        if user_record.guildId:
            msg = i18n.get(lang, "game.guild_already_member")
            return await ctx.reply(msg, ephemeral=True)
            
        # Check if user already owns a guild (Unique constraint check)
        existing_owned = await db.guild.find_unique(where={'ownerId': ctx.author.id})
        if existing_owned:
            msg = i18n.get(lang, "game.guild_already_owns", name=existing_owned.name)
            return await ctx.reply(msg, ephemeral=True)
        
        data = user_record.data
        if data['coins'] < 5000:
            msg = i18n.get(lang, "game.guild_insufficient_coins", coins=data['coins'])
            return await ctx.reply(msg, ephemeral=True)
        
        # Check if name exists
        existing = await db.guild.find_unique(where={'name': name})
        if existing:
            msg = i18n.get(lang, "game.guild_name_taken", name=name)
            return await ctx.reply(msg, ephemeral=True)
        
        # Create guild
        new_guild = await db.guild.create(data={
            'name': name,
            'ownerId': ctx.author.id,
        })
        
        # Update user
        data['coins'] -= 5000
        await db.user.update(
            where={'id': ctx.author.id},
            data={
                'guild': {'connect': {'id': new_guild.id}},
                'data': Json(data)
            }
        )
        
        title_lbl = i18n.get(lang, "game.guild_created_title")
        desc_lbl = i18n.get(lang, "game.guild_created_desc", name=name)
        embed = discord.Embed(title=title_lbl, description=desc_lbl, color=discord.Color.gold())
        
        fee_lbl = i18n.get(lang, "game.guild_created_fee")
        embed.add_field(name="Biaya" if lang == "id" else "Cost", value=fee_lbl)
        
        footer_lbl = i18n.get(lang, "game.guild_created_footer")
        embed.set_footer(text=footer_lbl)
        
        await ctx.reply(embed=embed)

    @guild.command(name="edit", description="Ubah identitas guildmu (Hanya Owner)")
    @app_commands.describe(
        name="Nama baru guild",
        tagline="Tagline keren guildmu",
        icon_url="URL Gambar untuk ikon guild"
    )
    @check_blacklist()
    async def guild_edit(self, ctx: commands.Context, name: str = None, tagline: str = None, icon_url: str = None):
        """
        Ubah detail guildmu agar terlihat lebih keren!
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            msg = i18n.get(lang, "game.guild_edit_not_member")
            return await ctx.reply(msg, ephemeral=True)
        
        guild = user_record.guild
        if guild.ownerId != ctx.author.id:
            msg = i18n.get(lang, "game.guild_edit_not_owner")
            return await ctx.reply(msg, ephemeral=True)
        
        update_data = {}
        if name:
            existing = await db.guild.find_unique(where={'name': name})
            if existing and existing.id != guild.id:
                msg = i18n.get(lang, "game.guild_edit_name_taken", name=name)
                return await ctx.reply(msg, ephemeral=True)
            update_data['name'] = name
        if tagline:
            update_data['tagline'] = tagline
        if icon_url:
            if not icon_url.startswith("http"):
                msg = i18n.get(lang, "game.guild_edit_invalid_icon")
                return await ctx.reply(msg, ephemeral=True)
            update_data['iconUrl'] = icon_url
            
        if not update_data:
            msg = i18n.get(lang, "game.guild_edit_no_choices")
            return await ctx.reply(msg, ephemeral=True)
            
        await db.guild.update(where={'id': guild.id}, data=update_data)
        success_msg = i18n.get(lang, "game.guild_edit_success", name=name or guild.name)
        await ctx.reply(success_msg)

    @guild.command(name="invite", description="Undang seseorang ke guildmu")
    @app_commands.describe(user="User yang ingin diundang")
    @check_blacklist()
    async def guild_invite(self, ctx: commands.Context, user: discord.Member):
        """
        Undang temanmu untuk bergabung dalam guild!
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            msg = i18n.get(lang, "game.guild_edit_not_member")
            return await ctx.reply(msg, ephemeral=True)
        
        guild = user_record.guild
        if guild.ownerId != ctx.author.id:
            msg = i18n.get(lang, "game.guild_invite_not_owner")
            return await ctx.reply(msg, ephemeral=True)
            
        target_record = await db.user.find_unique(where={'id': user.id})
        if not target_record:
            msg = i18n.get(lang, "game.guild_invite_target_not_registered")
            return await ctx.reply(msg, ephemeral=True)
        
        if target_record.guildId:
            msg = i18n.get(lang, "game.guild_invite_target_has_guild")
            return await ctx.reply(msg, ephemeral=True)
            
        # Sending invitation
        view = GuildInviteView(guild, user, lang=lang)
        prompt_msg = i18n.get(lang, "game.guild_invite_prompt", mention=user.mention, name=guild.name)
        await ctx.reply(prompt_msg, view=view)

    @guild.command(name="leave", description="Keluar dari guild saat ini")
    @check_blacklist()
    async def guild_leave(self, ctx: commands.Context):
        """
        Keluar dari guild. Jika kamu Owner, guild akan dibubarkan!
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            msg = i18n.get(lang, "game.guild_edit_not_member")
            return await ctx.reply(msg, ephemeral=True)
            
        guild = user_record.guild
        if guild.ownerId == ctx.author.id:
            # Bubarkan guild
            await db.guild.delete(where={'id': guild.id})
            msg = i18n.get(lang, "game.guild_leave_disbanded", name=guild.name)
            await ctx.reply(msg)
        else:
            await db.user.update(where={'id': ctx.author.id}, data={'guild': {'disconnect': True}})
            msg = i18n.get(lang, "game.guild_leave_success", name=guild.name)
            await ctx.reply(msg)

    @guild.command(name="leaderboard", aliases=["lb"], description="Lihat guild terkuat di Re:Volution!")
    @check_blacklist()
    async def guild_leaderboard(self, ctx: commands.Context):
        """
        Papan peringkat Guild berdasarkan jumlah anggota.
        """
        lang = await get_user_lang(ctx.author.id)
        guilds = await db.guild.find_many(include={'members': True})
        if not guilds:
            msg = i18n.get(lang, "game.guild_lb_empty")
            return await ctx.reply(msg)
            
        # Sort by member count DESC
        sorted_guilds = sorted(guilds, key=lambda g: len(g.members), reverse=True)
        top_100 = sorted_guilds[:100]
        
        title_lbl = i18n.get(lang, "game.guild_leaderboard_title")
        view = LeaderboardView(ctx, top_100, title_lbl, type="guild", lang=lang)
        embed = await view.get_embed()
        await ctx.reply(embed=embed, view=view)

    @guild.command(name="icon", description="Lihat atau ubah ikon guildmu!")
    @app_commands.describe(url="URL Gambar baru untuk ikon guild (Kosongkan untuk melihat ikon saat ini)")
    @check_blacklist()
    async def guild_icon(self, ctx: commands.Context, url: str = None):
        """
        Lihat atau ubah ikon guildmu agar terlihat lebih megah!
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            msg = i18n.get(lang, "game.guild_edit_not_member")
            return await ctx.reply(msg, ephemeral=True)
        
        guild = user_record.guild
        
        if url:
            if guild.ownerId != ctx.author.id:
                msg = i18n.get(lang, "game.guild_icon_owner_only")
                return await ctx.reply(msg, ephemeral=True)
            if not url.startswith("http"):
                msg = i18n.get(lang, "game.guild_edit_invalid_icon")
                return await ctx.reply(msg, ephemeral=True)
            
            await db.guild.update(where={'id': guild.id}, data={'iconUrl': url})
            msg = i18n.get(lang, "game.guild_icon_updated", name=guild.name)
            return await ctx.reply(msg)
            
        if not guild.iconUrl:
            msg = i18n.get(lang, "game.guild_icon_empty", name=guild.name)
            return await ctx.reply(msg)
            
        title_text = f"Guild Icon: {guild.name}" if lang == "en" else f"Ikon Guild: {guild.name}"
        embed = discord.Embed(title=title_text, color=ctx.author.color)
        embed.set_image(url=guild.iconUrl)
        await ctx.reply(embed=embed)

    @commands.hybrid_group(name="premium", description="Fitur Premium Re:Volution", fallback="info")
    @check_blacklist()
    async def premium(self, ctx: commands.Context):
        """
        Lihat status dan keuntungan menjadi Dream Weaver.
        """
        lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': ctx.author.id})
        if not user_record:
            msg = i18n.get(lang, "game.premium_not_registered")
            return await ctx.reply(msg)
            
        is_p = user_record.premiumUntil and user_record.premiumUntil > datetime.now()
        
        embed = discord.Embed(title="💎 Dream Weaver Premium 💎", color=0x00ffff)
        if is_p:
            embed.description = i18n.get(lang, "game.premium_active_desc", timestamp=int(user_record.premiumUntil.timestamp()))
        else:
            embed.description = i18n.get(lang, "game.premium_inactive_desc")
            
        benefits_title = i18n.get(lang, "game.premium_benefits_title")
        benefits_desc = i18n.get(lang, "game.premium_benefits_desc")
        embed.add_field(name=benefits_title, value=benefits_desc, inline=False)
        
        footer_text = i18n.get(lang, "game.premium_footer")
        embed.set_footer(text=footer_text)
        await ctx.reply(embed=embed)

    @premium.command(name="buy", description="Cara menjadi Dream Weaver (15k IDR / 30 Hari)")
    @check_blacklist()
    async def premium_buy(self, ctx: commands.Context):
        """
        Instruksi berlangganan Premium.
        """
        lang = await get_user_lang(ctx.author.id)
        saweria_link = getenv('SAWERIA_LINK', 'https://saweria.co/Schryzon')
        
        title_text = "💎 How to Become a Dream Weaver" if lang == "en" else "💎 Cara Menjadi Dream Weaver"
        embed = discord.Embed(title=title_text, color=0x00ffff)
        embed.description = i18n.get(lang, "game.premium_buy_desc", saweria_link=saweria_link)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.reply(embed=embed)

    @premium.command(name="claim", description="Klaim status Premium dengan mengunggah bukti pembayaran!")
    @app_commands.describe(bukti="Screenshot bukti pembayaran Saweria-mu")
    @check_blacklist()
    async def premium_claim(self, ctx: commands.Context, bukti: discord.Attachment):
        """
        Kirim bukti pembayaranmu untuk diverifikasi oleh admin!
        """
        lang = await get_user_lang(ctx.author.id)
        staff_channel_id = getenv('STAFF_CHANNEL_ID')
        if not staff_channel_id:
            msg = i18n.get(lang, "game.premium_claim_no_channel")
            return await ctx.reply(msg, ephemeral=True)
            
        staff_channel = self.bot.get_channel(int(staff_channel_id))
        if not staff_channel:
            msg = i18n.get(lang, "game.premium_claim_config_error")
            return await ctx.reply(msg, ephemeral=True)
            
        embed = discord.Embed(title="💎 Klaim Premium Baru!", color=0x00ffff)
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="User ID", value=f"`{ctx.author.id}`", inline=True)
        embed.add_field(name="User Mention", value=ctx.author.mention, inline=True)
        embed.set_image(url=bukti.url)
        embed.set_footer(text=f"Gunakan approve_premium {ctx.author.id} untuk menyetujui.")
        await staff_channel.send(embed=embed)
        
        success_msg = i18n.get(lang, "game.premium_claim_success")
        await ctx.reply(success_msg, ephemeral=True)

    @commands.command(name="approve_premium", description="[ADMIN] Setujui klaim premium seseorang")
    @commands.is_owner()
    async def approve_premium(self, ctx: commands.Context, user: discord.User):
        staff_lang = await get_user_lang(ctx.author.id)
        user_record = await db.user.find_unique(where={'id': user.id})
        if not user_record:
            msg = i18n.get(staff_lang, "game.premium_approve_not_found")
            return await ctx.reply(msg)
            
        now = datetime.now()
        if user_record.premiumUntil and user_record.premiumUntil > now:
            new_expiry = user_record.premiumUntil + timedelta(days=30)
        else:
            new_expiry = now + timedelta(days=30)
            
        await db.user.update(where={'id': user.id}, data={'premiumUntil': new_expiry})
        
        success_msg = i18n.get(staff_lang, "game.premium_approve_success", name=user.name, timestamp=int(new_expiry.timestamp()))
        await ctx.reply(success_msg)
        
        try:
            user_lang = await get_user_lang(user.id)
            dm_msg = i18n.get(user_lang, "game.premium_dm_success", timestamp=int(new_expiry.timestamp()))
            await user.send(dm_msg)
        except:
            pass

class GuildInviteView(View):
    def __init__(self, guild, target_user, lang="en"):
        super().__init__(timeout=60.0)
        self.guild = guild
        self.target_user = target_user
        self.lang = lang
        for child in self.children:
            if isinstance(child, Button):
                if child.custom_id == 'accept_invite':
                    child.label = 'Terima' if lang == 'id' else 'Accept'
                elif child.custom_id == 'decline_invite':
                    child.label = 'Tolak' if lang == 'id' else 'Decline'

    @discord.ui.button(label="Terima", style=discord.ButtonStyle.success, emoji="✅", custom_id="accept_invite")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            msg = i18n.get(self.lang, "game.invite_view_not_for_you")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        # Re-check if guild still exists
        guild_exists = await db.guild.find_unique(where={'id': self.guild.id})
        if not guild_exists:
            msg = i18n.get(self.lang, "game.invite_view_guild_gone")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        await db.user.update(where={'id': self.target_user.id}, data={'guild': {'connect': {'id': self.guild.id}}})
        msg = i18n.get(self.lang, "game.invite_view_accepted", mention=self.target_user.mention, name=self.guild.name)
        await interaction.response.edit_message(content=msg, view=None)

    @discord.ui.button(label="Tolak", style=discord.ButtonStyle.danger, emoji="❌", custom_id="decline_invite")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            msg = i18n.get(self.lang, "game.invite_view_not_for_you")
            return await interaction.response.send_message(msg, ephemeral=True)
        msg = i18n.get(self.lang, "game.invite_view_declined", mention=self.target_user.mention)
        await interaction.response.edit_message(content=msg, view=None)

async def setup(bot):
    await bot.add_cog(Game(bot))