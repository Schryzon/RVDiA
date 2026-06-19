import asyncio
import re
import discord
from discord.ext import commands
import random
import json
import time
import math
import difflib
import os
from os import path
from datetime import datetime
from prisma import Json
from discord.ui import View, Button, button
from scripts.main import db
from scripts.game.game import (
    level_up,
    send_level_up_msg,
    split_reward_string,
    give_rewards,
    default_data,
    check_compatible
)
from scripts.utils.i18n import i18n

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
                        enemy_desc = i18n.get(self.lang, f"game.enemy_{to_key(self.user2['name'])}_desc", default=self.user2.get('desc', ''))
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
        enemy_desc = i18n.get(self.lang, f"game.enemy_{to_key(enemy['name'])}_desc", default=enemy.get('desc', ''))
        
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


# ── Command Executors ────────────────────────────────────────

async def execute_fight(ctx, bot, member):
    lang = await get_user_lang(ctx.author.id)
    if member.bot:
        msg = i18n.get(lang, "game.fight_bot_cannot_fight")
        return await ctx.reply(msg, ephemeral=True)
        
    rival_record = await db.user.find_unique(where={'id': member.id})
    if not rival_record:
        msg = i18n.get(lang, "errors.rival_no_account")
        return await ctx.reply(msg)
        
    game = GameInstance(ctx, ctx.author, member, bot)
    await game.start()

async def execute_battle(ctx, bot, enemy_tier_val, enemy_name=None):
    lang = await get_user_lang(ctx.author.id)
    with open(f'./src/game/enemies/{enemy_tier_val}.json') as file:
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
            msg = i18n.get(lang, "game.battle_enemy_not_found", name=enemy_name, tier=enemy_tier_val.upper())
            return await ctx.reply(msg, ephemeral=True)
    else:
        enemy = random.choice(enemies)

    game = GameInstance(ctx, ctx.author, enemy, bot)
    await game.start()

async def execute_enemies(ctx):
    lang = await get_user_lang(ctx.author.id)
    view = PaginatedEnemyView(ctx, lang=lang)
    embed = await view.get_embed()
    await ctx.reply(embed=embed, view=view)

async def execute_guess(ctx, level_choice_val):
    lang = await get_user_lang(ctx.author.id)
    game_instance = GuessGame(ctx, level_choice_val, lang=lang)
    await game_instance.start()
