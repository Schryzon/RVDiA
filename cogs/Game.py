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
from os import getenv, listdir, path
from prisma import Json
from discord.ui import View, Button, button
from discord import app_commands
from discord.ext import commands
from scripts.main import db, has_registered, check_blacklist
from scripts.game import level_up, send_level_up_msg, split_reward_string, give_rewards, default_data, check_compatible

class FightView(View):
    def __init__(self):
        super().__init__(timeout=25.0)

    @button(label = 'Serang', custom_id='attack', style=discord.ButtonStyle.danger, emoji='💥')
    async def attack(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: 💥Serang")
        await asyncio.sleep(0.5)
        await interaction.message.delete(delay = 5)

    @button(label='Tahan', custom_id='defend', style=discord.ButtonStyle.blurple, emoji='🛡️')
    async def defend(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: 🛡️Tahan")
        await asyncio.sleep(0.5)
        await interaction.message.delete(delay=5)

    @button(label='Barang', custom_id='item', style=discord.ButtonStyle.green, emoji='👜')
    async def item(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: 👜Barang")
        await asyncio.sleep(0.5)
        await interaction.message.delete(delay=5)

    @button(label='Skill', custom_id='skill', style=discord.ButtonStyle.green, emoji='🔮')
    async def skill(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: 🔮Skill")
        await asyncio.sleep(0.5)
        await interaction.message.delete(delay=5)

    @button(label='Kabur', custom_id='end', style=discord.ButtonStyle.gray, emoji='🏃')
    async def flee(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: 🏃Kabur")
        await asyncio.sleep(0.5)
        await interaction.message.delete(delay=5)

    @button(label='Musuh', custom_id='check', style=discord.ButtonStyle.gray, emoji='❔', row=1)
    async def check(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: ❔Musuh")
        await asyncio.sleep(0.5)
        await interaction.message.delete(delay=5)

    @button(label='Lewati', custom_id='skip', style=discord.ButtonStyle.gray, emoji='⌚', row=1)
    async def skip(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: ⌚Lewati")
        await asyncio.sleep(0.5)
        await interaction.message.delete(delay=5)

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
        try:
            self.enemy_avatar = self.user2['avatar'] or getenv('defaultenemy')
        except:
            pass

    async def gather_data(self):
        def calc_skill_limit(level:int):
            if level < 10:
                return 3
            return 3*(math.floor(level/10))
        
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
                await self.ctx.reply(f'Waduh! Sepertinya <@{self.user2.id}> belum membuat akun Re:Volution!')
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
            self.p2_skill_limit = calc_skill_limit(stats2['level'])

        else:
            user2_stats = [self.user2['atk'], self.user2['def'], self.user2['agl']]
            # Enemies have karma based on tier
            tier_karma = {
                "LOW": 5, "NORMAL": 10, "HIGH": 20, "ELITE": 35, 
                "SUPER ELITE": 50, "BOSS": 75, "SUPER BOSS": 100,
                "FINAL BOSS": 200
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
        return [comp_data1, comp_data2]


    async def attack(self, dealer_stat:list, taker_stat:list, dealer_id:int, is_defending:bool, dealer_karma:int = 10, taker_karma:int = 10):
        user_1_atk, user_1_def, user_1_agl = dealer_stat[0], dealer_stat[1], dealer_stat[2]
        user_2_atk, user_2_def, user_2_agl = taker_stat[0], taker_stat[1], taker_stat[2]

        if is_defending:
            user_2_def += random.randint(8, 15)
            
        # Base Damage Calculation
        if dealer_id != 1 and self.ctx.command.name == "battle":
            scaling = max(self.user2_max_hp / 90, 1) if self.user2_max_hp > 500 else max(self.user2_max_hp / 10, 1) if self.user2_max_hp > 200 else self.user2_max_hp
            damage = round(max(0, user_1_atk * (random.randint(80, 100) - user_2_def) / scaling))
        else:
            damage = round(max(0, user_1_atk * (random.randint(80, 100) - user_2_def) / 100))
            
        # Luck Mechanics (Karma)
        # Critical Hit: Base 5% + (Karma / 20)%
        crit_chance = 5 + (dealer_karma / 20)
        is_crit = random.random() * 100 < crit_chance
        if is_crit:
            damage = round(damage * 1.5)
            
        # Miss Chance: (Agl Diff * 2) + 5. High Karma reduces miss chance.
        miss_chance = max(0, (user_2_agl - user_1_agl) * 2 + 5 - (dealer_karma / 50))
        
        # Miracle Dodge: If taker has high Karma, small chance to dodge anyway
        dodge_chance = taker_karma / 100
        is_miracle_dodge = random.random() * 100 < dodge_chance
        
        hit_chance = 100 - miss_chance
        attack_chance = random.randint(0, 100)

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
        view = ItemView(items, user1, type)
        if type == 'item':
            await self.ctx.channel.send(f"{user1.mention}, 10 detik untuk memilih item.", view=view, delete_after=15)
        else:
            await self.ctx.channel.send(f"{user1.mention}, 10 detik untuk menggunakan skill.", view=view, delete_after=15)

    async def func_converter(self, func:str, user1, user2):
        func = re.sub(r'\(|\)', '', func)
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
                        
                    if isinstance(user1, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} memulihkan `{amount}` HP!')
                    else:
                        await self.ctx.channel.send(f"{user1['name']} memulihkan `{amount}` HP!")

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
                    
                    if isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} memberikan `{amount}` Damage instan ke {user2.mention}!')
                    elif not isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f"{user1['name']} memberikan `{amount}` Damage instan ke {user2.mention}!")
                    else:
                        await self.ctx.channel.send(f"{user1.mention} memberikan `{amount}` Damage instan ke {user2['name']}!")

                case 'ATK':
                    if user1 == self.user1:
                        if not self.user1_stats[0] + int(func[1]) >= 100:
                            self.user1_stats[0] += int(func[1])
                        else:
                            self.user1_stats[0] = 100

                    else:
                        if not self.user2_stats[0] + int(func[1]) >= 100:
                            self.user2_stats[0] += int(func[1])
                        else:
                            self.user2_stats[0] = 100
                    
                    if isinstance(user1, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} menjadi lebih kuat!\n(+`{func[1]}` Attack)')
                    else:
                        await self.ctx.channel.send(f'{user1["name"]} menjadi lebih kuat!\n(+`{func[1]}` Attack)')

                case 'DEF':
                    if user1 == self.user1:
                        if not self.user1_stats[1] + int(func[1]) >= 100:
                            self.user1_stats[1] += int(func[1])
                        else:
                            self.user1_stats[1] = 100

                    else:
                        if not self.user2_stats[1] + int(func[1]) >= 100:
                            self.user2_stats[1] += int(func[1])
                        else:
                            self.user2_stats[1] = 100
                    
                    if isinstance(user1, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} menjadi lebih kuat!\n(+`{func[1]}` Defense)')
                    else:
                        await self.ctx.channel.send(f'{user1["name"]} menjadi lebih kuat!\n(+`{func[1]}` Defense)')

                case 'AGL':
                    if user1 == self.user1:
                        if not self.user1_stats[2] + int(func[1]) >= 100:
                            self.user1_stats[2] += int(func[1])
                        else:
                            self.user1_stats[2] = 100

                    else:
                        if not self.user2_stats[2] + int(func[1]) >= 100:
                            self.user2_stats[2] += int(func[1])
                        else:
                            self.user2_stats[2] = 100
                    
                    if isinstance(user1, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} menjadi lebih lincah!\n(+`{func[1]}` Agility)')
                    else:
                        await self.ctx.channel.send(f'{user1["name"]} menjadi lebih lincah!\n(+`{func[1]}` Agility)')
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

                    if isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} mengambil `{amount}` HP dari {user2.mention}!')
                    elif not isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f"{user1['name']} mengambil `{amount}` HP dari {user2.mention}!")
                    else:
                        await self.ctx.channel.send(f"{user1.mention} mengambil `{amount}` HP dari {user2['name']}!")

                case 'ATK':
                    if user1 == self.user1:
                        if not self.user2_stats[0] - int(func[1]) <= 1:
                            self.user2_stats[0] -= int(func[1])
                        else:
                            self.user2_stats[0] = 1

                    else:
                        if not self.user1_stats[0] - int(func[1]) <= 1:
                            self.user1_stats[0] -= int(func[1])
                        else:
                            self.user1_stats[0] = 1
                    
                    if isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} melemahkan serangan dari {user2.mention}!\n(-`{func[1]}` Attack)')
                    elif not isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1["name"]} melemahkan serangan dari {user2.mention}!\n(-`{func[1]}` Attack)')
                    else:
                        await self.ctx.channel.send(f'{user1.mention} melemahkan serangan dari {user2["name"]}!\n(-`{func[1]}` Attack)')

                case 'DEF':
                    if user1 == self.user1:
                        if not self.user2_stats[1] - int(func[1]) <= 1:
                            self.user2_stats[1] -= int(func[1])
                        else:
                            self.user2_stats[1] = 1

                    else:
                        if not self.user1_stats[1] - int(func[1]) <= 1:
                            self.user1_stats[1] -= int(func[1])
                        else:
                            self.user1_stats[1] = 1
                    
                    if isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} melemahkan pertahanan dari {user2.mention}!\n(-`{func[1]}` Defense)')
                    elif not isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1["name"]} melemahkan pertahanan dari {user2.mention}!\n(-`{func[1]}` Defense)')
                    else:
                        await self.ctx.channel.send(f'{user1.mention} melemahkan pertahanan dari {user2["name"]}!\n(-`{func[1]}` Defense)')

                case 'AGL':
                    if user1 == self.user1:
                        if not self.user2_stats[2] - int(func[1]) <= 1:
                            self.user2_stats[2] -= int(func[1])
                        else:
                            self.user2_stats[2] = 1

                    else:
                        if not self.user1_stats[2] - int(func[1]) <= 1:
                            self.user1_stats[2] -= int(func[1])
                        else:
                            self.user1_stats[2] = 1
                    
                    if isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} mengurangi kelincahan dari {user2.mention}!\n(-`{func[1]}` Agility)')
                    elif not isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1["name"]} mengurangi kelincahan dari {user2.mention}!\n(-`{func[1]}` Agility)')
                    else:
                        await self.ctx.channel.send(f'{user1.mention} mengurangi kelincahan dari {user2["name"]}!\n(-`{func[1]}` Agility)')

    async def ai_choose_skill(self, skill_set:list, ai, player):
        skill = random.choice(skill_set)
        skill_func = skill['func'].upper()
        await self.ctx.channel.send(f"{self.user2['name']} menggunakan skill:\n# {skill['name']}!")
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
            await self.ctx.reply(f'⚔️ Perang dimulai!\nLawan: {self.user2.mention}') # I'll just use this for now
        else:
            await self.ctx.reply(f"⚔️ Perang dimulai!\nMusuh: **`{self.user2['name']}`**\nLevel: **``{self.user2['tier']}``**")
        await asyncio.sleep(2.7)
        turns = 1

        while self.user1_hp > 0 and self.user2_hp > 0:
            fight_view1 = FightView()
            await self.ctx.channel.send(f'<@{self.user1.id}> Giliranmu!', view=fight_view1)

            try:
                res_1:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and r.content.startswith('Opsi terpilih: '), timeout = 25.0) # Detect a message from RVDiA

            except asyncio.TimeoutError:
                return await self.ctx.channel.send(f"🏃{self.user1.mention} kabur dari perang!")

            match res_1.content:
                case "Opsi terpilih: 💥Serang":
                    damage_info = await self.attack(self.user1_stats, self.user2_stats, self.user1.id, self.user2_defend, self.p1_karma, self.p2_karma)
                    damage, is_crit, is_dodge = damage_info[0], damage_info[1], damage_info[2]
                    
                    title = f"💥 {self.user1.display_name} Menyerang!"
                    if is_crit: title = f"✨ CRITICAL HIT! ✨"
                    if is_dodge: title = f"💫 MIRACLE DODGE! 💫"
                    
                    embed = discord.Embed(title=title, color=self.user1.color if not is_crit else discord.Color.gold())
                    
                    if is_dodge:
                        embed.description = f"**{self.user2.display_name if isinstance(self.user2, discord.Member) else self.user2['name']}** berhasil menghindari serangan secara ajaib!"
                    elif damage > 0:
                        if isinstance(self.user2, discord.Member):
                            embed.description = f"**`{damage}` Damage!**\nHP <@{self.user2.id}> tersisa `{self.user2_hp}` HP!"
                        else:
                            embed.description = f"**`{damage}` Damage!**\nHP {self.user2['name']} tersisa `{self.user2_hp}` HP!"
                    else:
                        embed.description = f"Serangan {self.user1.display_name} meleset!"
                        
                    embed.set_thumbnail(url=self.user1.display_avatar.url)
                    await self.ctx.channel.send(embed=embed)

                case "Opsi terpilih: 🛡️Tahan":
                    self.defend(self.user1)
                    embed = discord.Embed(title=f'🛡️{self.user1.display_name} Melindungi Diri!', color=self.user1.color)
                    embed.description = f"**Defense bertambah untuk serangan selanjutnya!**"
                    embed.set_thumbnail(url=self.user1.display_avatar.url)
                    await self.ctx.channel.send(embed=embed)

                case "Opsi terpilih: 👜Barang":
                    await self.use(self.user1, 'item')
                    try:
                        res_use:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and " menggunakan " in r.content, timeout = 10)
                        func = res_use.content.split('\n')[2] # Dear god hope this works
                        await self.func_converter(func, self.user1, self.user2)
                    except asyncio.TimeoutError:
                        await self.ctx.channel.send(f"{self.user1.mention}, giliranmu dilewatkan karena tidak menggunakan item!")

                case "Opsi terpilih: 🔮Skill":
                    if p1_skills_used >= self.p1_skill_limit:
                        await self.ctx.channel.send(f"{self.user1.mention}, kamu terbatas **`{self.p1_skill_limit}`** kali menggunakan skill untuk levelmu saat ini!")
                    else:
                        await self.use(self.user1, 'skill')
                        try:
                            res_use:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and " menggunakan " in r.content, timeout = 10)
                            func = res_use.content.split('\n')[2] # Dear god hope this works
                            await self.func_converter(func, self.user1, self.user2)
                            p1_skills_used += 1
                        except asyncio.TimeoutError:
                            await self.ctx.channel.send(f"{self.user1.mention}, giliranmu dilewatkan karena tidak menggunakan skill!")

                case "Opsi terpilih: ❔Musuh":
                    stats = self.user2_stats
                    if isinstance(self.user2, discord.Member):
                        embed = discord.Embed(title=self.user2.display_name, color=self.user2.color)
                        embed.set_thumbnail(url=self.user2.display_avatar.url)
                        embed.description = f"HP: `{self.user2_hp}`/`100`\nBertahan? `{'TIDAK' if self.user2_defend is False else 'YA'}`"
                        embed.add_field(
                            name="Statisik Tempur",
                            value=f"Attack: `{stats[0]}`\nDefense: `{stats[1]}`\nAgility: `{stats[2]}`",
                            inline=False
                        )
                        embed.set_author(name='Info Lawan:')
                    
                    else:
                        embed = discord.Embed(title=self.user2['name'], color=0xff0000)
                        embed.description = f"\"{self.user2['desc']}\"\nHP: `{self.user2_hp}`/`{datas[1]['hp']}`\nBertahan? `{'TIDAK' if self.user2_defend is False else 'YA'}`"
                        embed.add_field(
                            name="Statisik Tempur",
                            value=f"Attack: `{stats[0]}`\nDefense: `{stats[1]}`\nAgility: `{stats[2]}`",
                            inline=False
                        )
                        embed.set_author(name='Info Musuh:')
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass

                    await self.ctx.channel.send(embed = embed)

                case "Opsi terpilih: 🏃Kabur":
                    await self.ctx.channel.send(f'⛔ <@{self.user1.id}>  mengakhiri perang.')
                    return
                
                case "Opsi terpilih: ⌚Lewati":
                    await self.ctx.channel.send(f'{self.user1.mention} melewati gilirannya!')

                case _:
                    await self.ctx.channel.send("Opsi tidak valid, giliran dilewatkan.") # This was actually possible, now it's an easter egg!

            if self.user2_hp <= 0:
                await asyncio.sleep(2.5)
                break

            await asyncio.sleep(2.5)

            if isinstance(self.user2, discord.Member):
                fight_view2 = FightView()
                await self.ctx.channel.send(f'<@{self.user2.id}> Giliranmu!', view=fight_view2)

                try:
                    res_2 = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel, timeout = 25.0)

                except asyncio.TimeoutError:
                    return await self.ctx.channel.send(f"🏃{self.user2.mention} kabur dari perang!")
            
                match res_2.content:
                    case "Opsi terpilih: 💥Serang":
                        damage_info = await self.attack(datas[1]['stats'], datas[0]['stats'], self.user2.id, self.user1_defend, self.p2_karma, self.p1_karma)
                        damage, is_crit, is_dodge = damage_info[0], damage_info[1], damage_info[2]
                        
                        title = f"💥 {self.user2.display_name} Menyerang!"
                        if is_crit: title = f"✨ CRITICAL HIT! ✨"
                        if is_dodge: title = f"💫 MIRACLE DODGE! 💫"
                        
                        embed = discord.Embed(title=title, color=self.user2.color if not is_crit else discord.Color.gold())
                        
                        if is_dodge:
                            embed.description = f"**{self.user1.display_name}** berhasil menghindari serangan secara ajaib!"
                        elif damage > 0:
                            embed.description = f"**`{damage}` Damage!**\nHP <@{self.user1.id}> tersisa `{self.user1_hp}` HP!"
                        else:
                            embed.description = f"Serangan {self.user2.display_name} meleset!"
                            
                        embed.set_thumbnail(url=self.user2.display_avatar.url)
                        await self.ctx.channel.send(embed=embed)

                    case "Opsi terpilih: 🛡️Tahan":
                        self.defend(self.user2)
                        embed = discord.Embed(title=f'🛡️{self.user2.display_name} Melindungi Diri!', color=self.user2.color)
                        embed.description = f"**Defense bertambah untuk serangan selanjutnya!**"
                        embed.set_thumbnail(url=self.user2.display_avatar.url)
                        await self.ctx.channel.send(embed=embed)

                    case "Opsi terpilih: ❔Musuh":
                        stats = self.user1_stats
                        embed = discord.Embed(title=self.user1.display_name, color=self.user1.color)
                        embed.set_thumbnail(url=self.user1.display_avatar.url)
                        embed.description = f"HP: `{self.user1_hp}`/`100`\nBertahan? `{'TIDAK' if self.user1_defend is False else 'YA'}`"
                        embed.add_field(
                            name="Statisik Tempur",
                            value=f"Attack: `{stats[0]}`\nDefense: `{stats[1]}`\nAgility: `{stats[2]}`",
                            inline=False
                        )
                        embed.set_author(name='Info Lawan:')
                        await self.ctx.channel.send(embed = embed)

                    case "Opsi terpilih: 👜Barang":
                        await self.use(self.user2, 'item')
                        try:
                            res_use:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and " menggunakan " in r.content, timeout = 10)
                            func = res_use.content.split('\n')[2] # Dear god hope this works
                            await asyncio.sleep(1.2)
                            await self.func_converter(func, self.user2, self.user1)
                        except asyncio.TimeoutError:
                            await self.ctx.channel.send(f"{self.user2.mention}, giliranmu dilewatkan karena tidak menggunakan item!")

                    case "Opsi terpilih: 🔮Skill":
                        if p2_skills_used > self.p2_skill_limit:
                            await self.ctx.channel.send(f"{self.user2.mention}, kamu terbatas **`{self.p2_skill_limit}`** kali menggunakan skill untuk levelmu saat ini!")
                        else:
                            await self.use(self.user2, 'skill')
                            try:
                                res_use:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and " menggunakan " in r.content, timeout = 10)
                                func = res_use.content.split('\n')[2] # Dear god hope this works
                                await asyncio.sleep(1.2)
                                await self.func_converter(func, self.user2, self.user1)
                                p2_skills_used += 1
                            except asyncio.TimeoutError:
                                await self.ctx.channel.send(f"{self.user2.mention}, giliranmu dilewatkan karena tidak menggunakan skill!")

                    case "Opsi terpilih: 🏃Kabur":
                        await self.ctx.channel.send(f'⛔ <@{self.user2.id}>  mengakhiri perang.')
                        return
                    
                    case "Opsi terpilih: ⌚Lewati":
                        await self.ctx.channel.send(f'{self.user2.mention} melewati gilirannya!')

                    case _:
                        await self.ctx.channel.send("Opsi tidak valid, giliran dilewatkan.")

            else:
                ai = AI(self, turns)
                choice = await ai.decide()
                match choice:
                    case "attack":
                        damage_info = await self.attack(self.user2_stats, self.user1_stats, 1, self.user1_defend, self.p2_karma, self.p1_karma)
                        damage, is_crit, is_dodge = damage_info[0], damage_info[1], damage_info[2]
                        
                        title = f"💥 {self.user2['name']} Menyerang!"
                        if is_crit: title = f"✨ CRITICAL HIT! ✨"
                        if is_dodge: title = f"💫 MIRACLE DODGE! 💫"
                        
                        embed = discord.Embed(title=title, color=0xff0000 if not is_crit else discord.Color.gold())
                        
                        if is_dodge:
                            embed.description = f"**{self.user1.display_name}** berhasil menghindari serangan secara ajaib!"
                        elif damage > 0:
                            embed.description = f"**`{damage}` Damage!**\nHP <@{self.user1.id}> tersisa `{self.user1_hp}` HP!"
                        else:
                            embed.description = f"Serangan {self.user2['name']} meleset!"
                            
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        await self.ctx.channel.send(embed=embed)

                    case "defend":
                        self.defend(self.user2)
                        embed = discord.Embed(title=f'🛡️{self.user2["name"]} Melindungi Diri!', color=0xff0000)
                        embed.description = f"**Defense bertambah untuk serangan selanjutnya!**"
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        await self.ctx.channel.send(embed=embed)

                    case "skill":
                        await self.ai_choose_skill(self.user2['skills'], self.user2, self.user1)

                    case "check":
                        self.ai_knows_user = True
                        embed = discord.Embed(title=f"🔍 {self.user2['name']} sedang memperhatikanmu...", color=0x3498db)
                        embed.description = (
                            f"**{self.user2['name']}** sedang membaca alur seranganmu!\n"
                            f"\"Hmm... jadi ini kemampuanmu yang sebenarnya?\"\n\n"
                            f"📊 **Analisa Target:**\n"
                            f"• HP: `{self.user1_hp}`/`100`\n"
                            f"• Attack: `{self.user1_stats[0]}`\n"
                            f"• Defense: `{self.user1_stats[1]}`\n"
                            f"• Agility: `{self.user1_stats[2]}`"
                        )
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        await self.ctx.channel.send(embed=embed)

                    case "skip":
                        self.defend(self.user2) # Skipping turn gives a minor defense boost
                        embed = discord.Embed(title=f"⌚ {self.user2['name']} Menunggu...", color=0x95a5a6)
                        embed.description = f"**{self.user2['name']}** tidak melakukan apa-apa dan beralih ke posisi siaga."
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        await self.ctx.channel.send(embed=embed)

                    case "run":
                        embed = discord.Embed(title=f'🏃{self.user2["name"]} Kabur!', color=0xff0000)
                        embed.description = f"**Sayang sekali!\nCoba lagi nanti!**"
                        embed.set_footer(text="Tidak ada hadiah ketika musuh kabur!")
                        try:
                            embed.set_thumbnail(url = self.enemy_avatar)
                        except:
                            pass
                        return await self.ctx.channel.send(embed=embed)
                    
            turns += 1

            await asyncio.sleep(2.5)

        if self.user1_hp > self.user2_hp:
            embed = discord.Embed(title=f"{self.user1.display_name} Menang!", color=0xffff00)
            embed.description = f"Dengan `{self.user1_hp}` HP tersisa!"
            if not isinstance(self.user2, discord.Member):
                rewards = self.user2['reward']
                rewards = split_reward_string(rewards)
                if len(rewards) == 3:
                    embed.add_field(
                        name = "Kamu Memperoleh:",
                        value= f"⬆️ `{rewards[0]}` EXP\n{self.bot.coin_emoji_anim} `{rewards[1]}` Koin\n👹 `{rewards[2]}` Karma",
                        inline=False
                    )
                    await give_rewards(self.ctx, self.user1, rewards[0], rewards[1], rewards[2])
                else:
                    embed.add_field(
                        name="Kamu Memperoleh:",
                        value= f"⬆️ `{rewards[0]}` EXP\n{self.bot.coin_emoji_anim} `{rewards[1]}` Koin",
                        inline=False
                    )
                    await give_rewards(self.ctx, self.user1, rewards[0], rewards[1])
            else:
                embed.add_field(
                        name="Kamu Memperoleh:",
                        value= f"{self.bot.coin_emoji_anim} `15` Koin\n👹 `5` Karma",
                        inline=False
                    )
                await give_rewards(self.ctx, self.user1, 0, 15, 5)
            await asyncio.sleep(0.7)
            embed.set_thumbnail(url = self.user1.display_avatar.url)
            await self.ctx.channel.send(embed=embed)

        else:
            if isinstance(self.user2, discord.Member):
                embed = discord.Embed(title=f"{self.user2.display_name} Menang!", color=0xffff00)
                embed.description = f"Dengan `{self.user2_hp}` HP tersisa!"
                embed.add_field(
                        name="Kamu Memperoleh:",
                        value= f"{self.bot.coin_emoji_anim} `15` Koin\n 👹 `5` Karma",
                        inline=False
                    )
                await give_rewards(self.ctx, self.user2, 0, 15, 5)
                embed.set_thumbnail(url = self.user2.display_avatar.url)
                await self.ctx.channel.send(embed=embed)

            else:
                tips = ['Gunakan item dan skill spesial yang kamu miliki!',
                        'Jika terlalu susah, kembali ke yang lebih mudah!',
                        'Skill musuh muncul setelah 3 giliran pertama!',
                        'Kunjungi Xaneria untuk meningkatkan peralatan dan skillmu!',
                        'Selalu ingat untuk memeriksa status musuhmu!'
                        ]
                tips = random.choice(tips)
                embed = discord.Embed(title=f"Kamu Kalah!", color=0xff0000)
                embed.description = f"{self.user2['name']} menang dengan `{self.user2_hp}` HP tersisa!"
                embed.set_footer(text=f'Tip: {tips}')
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
        
        # Persistence: AI remembers if it has checked your stats
        if not hasattr(self.instance, 'ai_knows_user'):
            self.instance.ai_knows_user = False
            
        self.actions = ["attack", "defend", "skip"]
        if self.turns > 0 and not self.instance.ai_knows_user:
            self.actions.append("check")
            
        if self.turns > 3:
            try:
                skills = self.user2['skills']
                if skills:
                    self.actions.append("skill")
            except:
                pass
        if self.turns > 6:
            self.actions.append("run")
    
    async def decide(self):
        user1_stats = self.user1_stats
        user2_stats = self.user2_stats
        user_1_atk, user_1_def, user_1_agl = user1_stats[0], user1_stats[1], user1_stats[2]
        user_2_atk, user_2_def, user_2_agl = user2_stats[0], user2_stats[1], user2_stats[2]

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
        else:
            # Chance to check stats increases significantly as turns go by
            self.check_mood += (self.turns * 12)

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
    def __init__(self, items:list, user1, type) -> None:
        options = []
        for item in items:
            if '0-' in item['_id'] and item['usefor'] == 'battle' and not item['owned'] <= 0 and type == 'item':
                options.append(discord.SelectOption(
                    label=f"{item['name']}",
                    value=item['_id'],
                    description=f"{item['desc']} ({item['func'].upper()})"
                ))
            elif '2-' in item['_id'] and item['usefor'] == 'battle' and not item['owned'] <= 0 and type == 'skill':
                options.append(discord.SelectOption(
                    label=f"{item['name']}",
                    value=item['_id'],
                    description=f"{item['desc']} ({item['func'].upper()})"
                ))
        if options == [] or options == None:
            options.append(discord.SelectOption(
                    label=f"Tidak ada item/skill!",
                    value="none",
                    description=f"Kamu harus membelinya dulu di /game shop!"
                )
            )
        super().__init__(custom_id="itemdrop", placeholder='Pilih yang ingin kamu gunakan!', min_values=1, max_values=1, options=options)
        self.user1 = user1
        self.items = items
        self.types = type

    async def callback(self, interaction:discord.Interaction):
        if interaction.message.mentions[0].id != interaction.user.id:
            return await interaction.response.send_message(f"Hey! Kamu tidak diizinkan untuk memilih!", ephemeral=True)
        if self.values[0] == 'none' and self.types == 'item':
            return await interaction.response.send_message("Kamu tidak memiliki item apapun!", ephemeral=True)
        elif self.values[0] == 'none' and self.types == 'skill':
            return await interaction.response.send_message("Kamu tidak memiliki skill apapun!", ephemeral=True)
        
        user_record = await db.user.find_unique(where={'id': self.user1.id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            return await interaction.response.send_message("Akun bermasalah!", ephemeral=True)
            
        inventory = user_record.inventory
        used_item = None
        
        if self.types == 'item':
            user_items = inventory.items if isinstance(inventory.items, list) else []
            for item in user_items:
                if item['_id'] == self.values[0] and item.get('owned', 0) > 0:
                    item['owned'] -= 1
                    used_item = [item['name'], item['func']]
                    break
            
            if used_item:
                await db.inventory.update(
                    where={'userId': self.user1.id},
                    data={'items': Json(user_items)}
                )
        else:
            # Skill usage (doesn't consume)
            user_skills = inventory.skills if isinstance(inventory.skills, list) else []
            for item in user_skills:
                if item['_id'] == self.values[0] and item.get('owned', 0) > 0:
                    used_item = [item['name'], item['func']]
                    break

        if used_item is None:
            return await interaction.response.send_message("Item tidak ditemukan atau sudah habis!", ephemeral=True)
            
        if self.types == 'item':
            await interaction.response.send_message(f"{interaction.user.mention} menggunakan item:\n# {used_item[0]}!\n({used_item[1].upper()})")
        else:
            await interaction.response.send_message(f"{interaction.user.mention} menggunakan skill:\n# {used_item[0]}!\n({used_item[1].upper()})")


class ItemView(View):
    def __init__(self, items:list, user1, type):
        super().__init__(timeout=20)
        self.add_item(ItemDropdown(items, user1, type))
    
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
    def __init__(self, number:int, attempt:int, hint:int, level:str) -> None:
        self.number = number
        self.attempt = attempt
        self.hints = hint
        self.level = level
        num_amount = guess_level_convert(level)
        options = []
        for i in range(1, num_amount+1):
            options.append(discord.SelectOption(
                label=str(i),
                value=i
            ))
        super().__init__(custom_id='guessdrop', placeholder='Pilih angka yang tepat!', min_values=1, max_values=1, options=options)

    async def callback(self, interaction:discord.Interaction):
        if self.attempt > 0:
            if int(self.values[0]) == self.number:
                await interaction.response.send_message(f"Benar! Angkanya `{self.number}`!")
                self.disabled =True
                return
            else:
                self.attempt -= 1
                await interaction.response.send_message(f"Salah! Angkanya bukan `{self.values[0]}`!\nSisa attempt: {self.attempt}", view=GuessGameView(self.number, self.attempt, self.hints, self.level, int(self.values[0])))
        else:
            return await interaction.response.send_message('Attempt-mu sudah habis! Terima kasih karena telah bermain bersama RVDiA!', ephemeral=True)

class GuessGameView(View):
    """
    Buttons and stuff
    """
    def __init__(self, number:int, attempt:int, hint_left:int, level:str, last_number:int=None):
        super().__init__(timeout=None) # Maybe None prevents it from timing out too soon.
        self.hints = hint_left
        self.last = last_number
        self.number = number
        self.attempt = attempt
        self.level = level
        self.add_item(GuessDropdown(self.number, self.attempt, self.hints, self.level))

    @button(label='Hint', custom_id='hint', style=discord.ButtonStyle.blurple, emoji='❔')
    async def give_hint(self, interaction:discord.Interaction, button:Button):
        if self.last == None:
            await interaction.response.send_message("Kamu belum menebak! Coba tebak dulu angka yang ku pilih!", ephemeral=True)
            return
        if self.hints != 0:
            self.hints -= 1
            if self.last < self.number:
                await interaction.response.send_message(f"Angka terakhirmu, `{self.last}` **lebih kecil** dari angka yang ku pilih.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Angka terakhirmu, `{self.last}` **lebih besar** dari angka yang ku pilih.", ephemeral=True)
        else:
            await interaction.response.send_message('Hint-mu telah habis terpakai! Coba tebak semampumu sekarang!', ephemeral=True)

        button.disabled = True

class GuessGame():
    """
    The guessing number game
    Using the power of class chain reaction
    """
    def __init__(self, ctx:commands.Context, level:str) -> None:
        self.ctx = ctx
        self.level = level

    async def start(self):
        num_limit = guess_level_convert(self.level)
        number = random.randint(1, num_limit)
        game_view = GuessGameView(number, 5, 3, self.level)
        await self.ctx.reply(f"Coba tebak angka yang ku pilih!\nLevel: `{self.level}`", view=game_view)
        
class ResignButton(View):
    def __init__(self, ctx:commands.Context):
        super().__init__(timeout=20)
        self.ctx = ctx
        self.value = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    @button(label='Hapus Akun', style=discord.ButtonStyle.danger, custom_id='delacc')
    async def delete_account(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Kamu tidak diperbolehkan berinteraksi dengan tombol ini!", ephemeral=True)
            return
        
        user_record = await db.user.find_unique(where={'id': interaction.user.id})
        name = user_record.data['name'] if user_record else "Unknown"
        await db.user.delete(where={'id': interaction.user.id})
        await interaction.response.send_message(f'Aku telah menghapus akunmu.\nSampai jumpa, `{name}`, di Re:Volution!')
        self.value = True
        self.stop()

    @button(label='Batalkan', style=discord.ButtonStyle.green, custom_id='canceldel')
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Kamu tidak diperbolehkan berinteraksi dengan tombol ini!", ephemeral=True)
            return
        await interaction.response.send_message('Penghapusan akun dibatalkan.', ephemeral=True)
        self.value = False
        self.stop()

class ShopDropdown(discord.ui.Select):
    """
    Buy feature
    """
    def __init__(self, page:int):
        self.page = page

        with open('./src/game/shop.json') as file:
            content = file.read()
            items = json.loads(content)

        options = []
        start_index = (self.page - 1) * 5
        end_index = self.page * 5
        for index, item in enumerate(items[start_index:end_index]):
            options.append(discord.SelectOption(
                            label = f"{index + start_index + 1}. {item['name']}", 
                            description=f"Harga: {item['cost']} {item['paywith']}", 
                            value=item['_id']
                            )
                        )

        super().__init__(custom_id="shopdrop", placeholder="Mau beli apa?", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        with open('./src/game/shop.json') as file:
            content = file.read()
            items = json.loads(content)

        item_id = self.values[0]
        user_record = await db.user.find_unique(where={'id': interaction.user.id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            return await interaction.response.send_message("Akunmu bermasalah, silahkan hubungi developer.", ephemeral=True)
            
        data = user_record.data
        inventory = user_record.inventory
        db_dict = {item['_id']: item for item in items}
        
        matched_item = db_dict[item_id]
        currency_key = 'coins' if matched_item['paywith'] == "Koin" else 'karma'
        current_money = data[currency_key]
        
        if current_money < matched_item['cost']:
            return await interaction.response.send_message(f"Waduh!\n{matched_item['paywith']}mu tidak cukup untuk membeli barang ini!", ephemeral=True)

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
                return await interaction.response.send_message("Kamu hanya bisa membeli equipment sekali saja!", ephemeral=True)
            if '2-' in item_id:
                return await interaction.response.send_message("Kamu hanya bisa memelajari skill sekali saja!", ephemeral=True)
            
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

        await interaction.response.send_message(f"Pembelian berhasil!\nKamu telah membeli `{matched_item['name']}`", ephemeral=True)

class PaginatedEnemyView(View):
    def __init__(self, ctx):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.tiers = ['boss', 'elite', 'high', 'normal', 'low']
        self.current_tier_index = 0
        self.enemies = []

    async def get_embed(self):
        tier = self.tiers[self.current_tier_index]
        enemy_path = path.join(path.dirname(__file__), '..', 'src', 'game', 'enemies', f'{tier}.json')
        with open(enemy_path, 'r') as file:
            self.enemies = json.load(file)
        
        strongest = max(self.enemies, key=lambda x: x['hp'] + x['atk'] + x['def'] + x['agl'])
        
        embed = discord.Embed(title=f"📖 Bestiary: {tier.title()}", color=0xff0000 if tier == 'boss' else 0x3498db)
        embed.description = f"Menampilkan musuh tingkat **{tier.upper()}**\n\n"
        
        for index, enemy in enumerate(self.enemies):
            embed.add_field(
                name=f"{index+1}. {enemy['name']} ({enemy['tier']})",
                value=f"**HP**: `{enemy['hp']}` | **Stats**: `{enemy['atk']}/{enemy['def']}/{enemy['agl']}`",
                inline=False
            )
            
        if strongest.get('avatar'):
            embed.set_thumbnail(url=strongest['avatar'])
            
        embed.set_footer(text=f"Halaman {self.current_tier_index + 1}/{len(self.tiers)} • Pilih musuh untuk detail!")
        
        self.clear_items()
        self.add_item(self.prev_page)
        self.add_item(self.destroy)
        self.add_item(self.next_page)
        self.add_item(SpecificEnemyDropdown(self.enemies))
        
        return embed

    @discord.ui.button(label='◀', style=discord.ButtonStyle.blurple)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Hanya yang memanggil command ini yang bisa menggunakannya!", ephemeral=True)
        self.current_tier_index = (self.current_tier_index - 1) % len(self.tiers)
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='▶', style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Hanya yang memanggil command ini yang bisa menggunakannya!", ephemeral=True)
        self.current_tier_index = (self.current_tier_index + 1) % len(self.tiers)
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='✖', style=discord.ButtonStyle.danger)
    async def destroy(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Hanya yang memanggil command ini yang bisa menggunakannya!", ephemeral=True)
        await interaction.message.delete()

class EnemyDropdown(discord.ui.Select):
    def __init__(self):
        options = []
        # Using this cause for loops randomizes the texts
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
                label='Low',
                value='low'
            ))
        super().__init__(custom_id="enemydrop", placeholder="Level Musuh", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        enemy_path = path.join(path.dirname(__file__), '..', 'src', 'game', 'enemies', f'{self.values[0]}.json')
        with open(enemy_path, 'r') as file:
            enemies = json.load(file)
        
        # Find the strongest enemy (highest total stats + HP)
        strongest = max(enemies, key=lambda x: x['hp'] + x['atk'] + x['def'] + x['agl'])
        
        embed = discord.Embed(title=f"Bestiary: {self.values[0].title()}", color=interaction.user.color)
        for index, enemy in enumerate(enemies):
            embed.add_field(
                name=f"{index+1}. {enemy['name']} ({enemy['tier']})",
                value=f"**HP**: `{enemy['hp']}` | **Stats**: `{enemy['atk']}/{enemy['def']}/{enemy['agl']}`",
                inline=False
                )
        
        if strongest.get('avatar'):
            embed.set_thumbnail(url=strongest['avatar'])
        else:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
        embed.set_footer(text="Pilih musuh dari dropdown di bawah untuk melihat detail!")
        await interaction.response.edit_message(content='', embed=embed, view=EnemyView(enemies))

class SpecificEnemyDropdown(discord.ui.Select):
    def __init__(self, enemies: list):
        options = []
        for index, enemy in enumerate(enemies):
            options.append(discord.SelectOption(
                label=f"{enemy['name']}",
                value=str(index),
                description=f"{enemy['tier']} - HP: {enemy['hp']}",
                emoji="👹"
            ))
        super().__init__(placeholder="Pilih musuh untuk detail...", min_values=1, max_values=1, options=options)
        self.enemies = enemies

    async def callback(self, interaction: discord.Interaction):
        enemy = self.enemies[int(self.values[0])]
        
        embed = discord.Embed(title=f"Detail Musuh: {enemy['name']}", description=f"*{enemy['desc']}*", color=0xff0000)
        embed.add_field(name="Tier", value=f"`{enemy['tier']}`", inline=True)
        embed.add_field(name="HP", value=f"`{enemy['hp']}`", inline=True)
        embed.add_field(name="Stats (A/D/Ag)", value=f"`{enemy['atk']}/{enemy['def']}/{enemy['agl']}`", inline=True)
        
        if enemy.get('skills'):
            skill_list = "\n".join([f"✨ **{s['name']}**: `{s['func']}`" for s in enemy['skills']])
            embed.add_field(name="Kemampuan Spesial", value=skill_list, inline=False)
            
        if enemy.get('reward'):
            rewards = ", ".join(enemy['reward'])
            embed.add_field(name="Potensi Hadiah", value=f"`{rewards}`", inline=False)
            
        if enemy.get('avatar'):
            embed.set_thumbnail(url=enemy['avatar'])
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

class EnemyView(View):
    def __init__(self, enemies: list = None):
        super().__init__(timeout=120)
        if enemies:
            self.add_item(SpecificEnemyDropdown(enemies))
        else:
            self.add_item(EnemyDropdown())
        
class ShopView(View):
    """
    Currently not up to write DRY code
    """
    def __init__(self, ctx, items, data):
        self.current_page = 1
        super().__init__(timeout=40)
        self.ctx = ctx
        self.items = items
        self.data = data
        self.owned = []
        self.add_item(ShopDropdown(self.current_page))

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
                    return "YA" if count > 0 else "TIDAK"
                return str(count)
                
        if item['type'] == 'Skill' or item['type'] == 'Equipment':
            return "TIDAK"
        return "0"

    async def update_embed(self, last_page):
        embed = discord.Embed(title='Toko Xaneria', color=0xFFFF00)
        embed.description = '"Hey, hey! Selamat datang. Silahkan, mau beli apa?"'
        embed.set_footer(text='Untuk membeli sebuah item, klik di bawah ini! v')
        embed.set_thumbnail(url=getenv('xaneria'))

        self.owned.clear()
        start_index = (self.current_page - 1) * 5
        end_index = start_index + 5

        def generate_embed_field(index, item, owned_count):
            embed.add_field(
                name=f"{index}. {item['name']}",
                value=f"**`{item['desc']}`**\n({item['func']})\n**Tipe:** {item['type']}\n**Harga:** {item['cost']} {item['paywith']}\n**Dimiliki:** {owned_count}",
                inline=False
            )
        
        for index, item in enumerate(self.items[start_index:end_index], start=start_index + 1):
            owned_display = self.get_owned_display(item)
            self.owned.append(owned_display)
            embed.add_field(
                name=f"{index}. {item['name']}",
                value=f"**`{item['desc']}`**\n({item['func']})\n**Tipe:** {item['type']}\n**Harga:** {item['cost']} {item['paywith']}\n**Dimiliki:** {owned_display}",
                inline=False
            )

        self.clear_items() # Fuck this
        self.add_item(self.back)
        self.add_item(self._delete)
        self.add_item(self.next)
        self.add_item(ShopDropdown(self.current_page)) # Dear god hope this works

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
    def __init__(self, items:list, ctx:commands.Context) -> None:
        options = []
        for index, item in enumerate(items, start=1):
            options.append(discord.SelectOption(
                label=f"{index}. {item['name']} ({item['usefor']})" if not item['usefor'] == 'free' else f"{index}. {item['name']}",
                description=f"{item['func'].upper()}",
                value = item['_id']
            ))
        if not options:
            options.append(discord.SelectOption(
                    label=f"Tidak ada apapun!",
                    value="none",
                    description=f"Kamu harus membelinya dulu di /game shop!"
                )
            )
        super().__init__(custom_id="usedrop", placeholder="Pilihlah barang yang ingin kamu pakai!", min_values=1, max_values=1, options=options)
        self.items = items
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
        # Click -> Check item_id and owned -> Add stats accordingly
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menggunakan dropdown ini!", ephemeral=True)
        if self.values[0] == 'none':
            return await interaction.response.send_message("Kamu tidak memiliki apapun!\nKamu harus membeli barang/skill di `/game shop`!", ephemeral=True)
        
        user_record = await db.user.find_unique(where={'id': interaction.user.id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            return await interaction.response.send_message("Akunmu bermasalah, silahkan hubungi developer.", ephemeral=True)
            
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
                await interaction.response.send_message(f"Kamu telah melepas `{item_to_unequip['name']}`!")
            
            else: # Equip
                all_items = inventory.items if isinstance(inventory.items, list) else []
                item_match = [x for x in all_items if x['_id'] == item_id]
                
                if not item_match:
                    return await interaction.response.send_message("Kamu tidak memiliki item tersebut!", ephemeral=True)
                
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
                await interaction.response.send_message(f"Kamu telah menggunakan `{item_to_equip['name']}`!")
        
        else:
            # Consumable or Skill
            all_items = inventory.items if isinstance(inventory.items, list) else []
            item_match = [x for x in all_items if x['_id'] == item_id]
            if not item_match:
                return await interaction.response.send_message("Kamu tidak memiliki item/skill tersebut!", ephemeral=True)
            
            item_to_use = item_match[0]
            await interaction.response.send_message(f"Kamu telah menggunakan `{item_to_use['name']}`!")
            
            game_inst = GameInstance(self.ctx, interaction.user, None, self.ctx.bot)
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
    def __init__(self, items:list, ctx:commands.Context):
        super().__init__(timeout=30)
        self.add_item(UseDropdown(items, ctx))

class LeaderboardView(View):
    def __init__(self, ctx, data: list, title: str, type: str = "player"):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.data = data
        self.title = title
        self.type = type
        self.current_page = 0
        self.items_per_page = 10
        self.max_pages = (len(data) - 1) // self.items_per_page + 1

    async def get_embed(self):
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        items = self.data[start_idx:end_idx]
        
        embed = discord.Embed(title=self.title, color=0xffd700) # Gold
        embed.description = f"Menampilkan peringkat **{start_idx + 1}** sampai **{min(end_idx, len(self.data))}** dari **{len(self.data)}**."
        
        for i, item in enumerate(items, start=start_idx + 1):
            if self.type == "player":
                name = item.data.get('name', 'Unknown')
                level = item.data.get('level', 1)
                karma = item.data.get('karma', 0)
                embed.add_field(
                    name=f"{i}. {name}",
                    value=f"🔰 Level: `{level}` | 👹 Karma: `{karma}`",
                    inline=False
                )
            else: # guild
                name = item.name
                member_count = len(item.members) if hasattr(item, 'members') else 0
                embed.add_field(
                    name=f"{i}. {name}",
                    value=f"👥 Anggota: `{member_count}` | 👑 Owner: <@{item.ownerId}>",
                    inline=False
                )
        
        embed.set_footer(text=f"Halaman {self.current_page + 1}/{self.max_pages}")
        return embed

    @discord.ui.button(label='◀', style=discord.ButtonStyle.blurple)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Bukan tombolmu, Sang Pemimpi!", ephemeral=True)
        self.current_page = (self.current_page - 1) % self.max_pages
        await interaction.response.edit_message(embed=await self.get_embed())

    @discord.ui.button(label='✖', style=discord.ButtonStyle.danger)
    async def destroy(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Hanya yang memanggil ini yang bisa menutupnya!", ephemeral=True)
        await interaction.message.delete()

    @discord.ui.button(label='▶', style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Bukan tombolmu, Sang Pemimpi!", ephemeral=True)
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
        user_data = await db.user.find_unique(where={'id': ctx.author.id})
        if user_data:
            return await ctx.reply('Kamu sudah terdaftar!')
            
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
        
        await ctx.reply(f'Akunmu sudah didaftarkan!\nSelamat datang di Re:Volution, **`{name}`**!')
        await asyncio.sleep(0.7)
        await self.account(ctx)
    
    @game.command(description="Tunjukkan siapa Sang Pemimpi terkuat saat ini!")
    @check_blacklist()
    async def leaderboard(self, ctx:commands.Context):
        """
        Lihat siapa yang terkuat di Re:Volution ~ The Dream World!
        """
        users = await db.user.find_many()
        if not users:
            return await ctx.reply("Belum ada pemain yang terdaftar!")
            
        # Sort by level DESC, then karma DESC
        sorted_users = sorted(users, key=lambda u: (u.data.get('level', 1), u.data.get('karma', 0)), reverse=True)
        top_100 = sorted_users[:100]
        
        view = LeaderboardView(ctx, top_100, "🏆 Papan Peringkat Re:Volution 🏆", type="player")
        embed = await view.get_embed()
        await ctx.reply(embed=embed, view=view)

    @game.command(description='Panduan bermain Re:Volution.')
    @check_blacklist()
    async def guide(self, ctx:commands.Context):
        """
        Panduan bermain Re:Volution ~ The Dream World!
        """
        embed = discord.Embed(title="✨ Panduan Re:Volution ✨", color=0x86273d)
        embed.description = (
            "Halo, Sang Pemimpi! 💫\n"
            "Selamat datang di **Re:Volution ~ The Dream World**. Aku akan memandumu memahami dunia ini!\n\n"
            "🛡️ **Memulai Petualangan**\n"
            "Gunakan `/game register` untuk membuat akunmu. Setelah itu, kamu bisa mulai menjelajah!\n\n"
            "⚔️ **Pertarungan (Combat)**\n"
            "• `/game battle`: Lawan monster untuk mendapatkan EXP, Koin, dan Karma.\n"
            "• `/game fight`: Tantang temanmu dalam pertarungan PvP yang sengit!\n"
            "• Selama bertarung, kamu bisa Menyerang (Attack), Bertahan (Defend), menggunakan Item, atau Skill.\n"
            "• **Karma**: Semakin tinggi Karma, semakin besar peluang Critical Hit dan Dodge!\n\n"
            "💰 **Ekonomi & Kekuatan**\n"
            "• `/game shop`: Beli item konsumsi, perlengkapan (Equipment), atau pelajari Skill baru.\n"
            "• `/game account`: Lihat statusmu, koin, dan karma.\n"
            "• `/game adventure`: Jalankan petualangan singkat untuk hadiah cepat.\n\n"
            "📜 **Tips dari RVDiA**\n"
            "*\"Jangan lupa untuk selalu melengkapi equipment terbaikmu sebelum melawan Boss! Jika merasa lelah, beristirahatlah sejenak di Xaneria.\"*"
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Semoga beruntung di dalam mimpi ini!")
        await ctx.reply(embed=embed)

    @game.command(description='Lihat catatan pembaruan terbaru Re:Volution!')
    @check_blacklist()
    async def changelog(self, ctx:commands.Context):
        """
        Catatan pembaruan Re:Volution ~ The Dream World!
        """
        embed = discord.Embed(title="📜 Catatan Pembaruan Re:Volution", color=0x86273d)
        embed.description = (
            "**Versi 2.0.0 - Rebirth & Rebalance**\n"
            "*\"Dunia mimpi ini telah berevolusi menjadi lebih menantang dan terstruktur.\"*\n\n"
            "🔰 **Sistem & Fitur Baru**\n"
            "• `/game leaderboard`: Pantau siapa Sang Pemimpi terkuat secara global.\n"
            "• `/game guide`: Panduan lengkap untuk memulai petualanganmu.\n"
            "• `/game fix_account`: Perbaiki dan migrasikan struktur datamu ke sistem terbaru.\n"
            "• `/game enemies`: Tampilan daftar musuh kini menggunakan sistem halaman (dimulai dari Boss).\n\n"
            "⚔️ **Keseimbangan & Konten**\n"
            "• **Global Rebalance**: Semua musuh telah disesuaikan stat dan HP-nya untuk pertempuran yang lebih adil.\n"
            "• **Final Boss Tier**: Schryzon & RVDiA kini berada di kasta tertinggi dengan kekuatan yang melampaui batas.\n"
            "• **New Bosses**: Selamat datang **Mira** (Adik Historia) dan **Victoria** (Kakak Historia) ke dalam Bestiary.\n"
            "• **Smarter AI**: Musuh kini lebih sering menganalisa statistikmu di tengah pertempuran.\n\n"
            "👜 **Perbaikan Toko**\n"
            "• Logika penyimpanan item kini lebih terorganisir antara Skill, Equipment, dan Item.\n"
            "• Status kepemilikan Skill kini ditampilkan secara biner (YA/TIDAK)."
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Terima kasih telah menjadi bagian dari Re:Volution!")
        await ctx.reply(embed=embed)

    @game.command(description="Menghapuskan akunmu dari Re:Volution.")
    @has_registered()
    @check_blacklist()
    async def resign(self, ctx:commands.Context):
        """
        Menghapuskan akunmu dari Re:Volution ~ The Dream World.
        """
        view = ResignButton(ctx)
        await ctx.reply('Apakah kamu yakin akan menghapus akunmu?\nKamu punya 20 detik untuk menentukan keputusanmu.', view=view)
        await view.wait()
        if view.value is None:
            await ctx.channel.send('Waktu habis, penghapusan akun dibatalkan.')
        elif view.value:
            await db.user.delete(where={'id': ctx.author.id})
            await ctx.reply('Akunmu telah dihapus. Sampai jumpa lagi!')

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

        if delta_time.total_seconds() <= 24*60*60:
            return await ctx.reply(f'Kamu sudah login hari ini!\nKamu bisa login lagi pada <t:{next_login_unix}:f>')
        
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
            
            embed = discord.Embed(title='Bonus Harianmu', color=0x00FF00, timestamp=next_login)
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            embed.add_field(
                name="Kamu Memperoleh:",
                value=f"{self.bot.coin_emoji_anim} `{new_coins}` Koin\n👹 `{new_karma}` Karma\n⬆️ `{new_exp}` EXP!",
                inline=False
            )
            embed.set_footer(text='Bonus selanjutnya pada ')
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
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'inventory': True})
        if not user_record:
            return await ctx.reply('Kamu belum terdaftar!')
            
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
        
        msg = f"✅ Akunmu telah diperbaiki!"
        if moved_skills > 0 or moved_equips > 0:
            msg += f"\n- Berhasil memindahkan `{moved_skills}` skill.\n- Berhasil memindahkan `{moved_equips}` perlengkapan."
        if updated_data:
            msg += "\n- Struktur data profil juga telah diperbarui."
        if moved_skills == 0 and moved_equips == 0 and not updated_data:
            msg = "✅ Akunmu sudah dalam kondisi terbaik! Tidak ada yang perlu diperbaiki."
            
        await ctx.reply(msg)

    async def account(self, ctx:commands.Context, *, user:discord.User=None):
        """
        Tampilkan informasi akun Re:Volution-mu!
        """
        target = user or ctx.author
        user_record = await db.user.find_unique(where={'id': target.id})
        
        if not user_record:
            return await ctx.reply('Waduh! Akun tersebut belum terdaftar di Re:Volution!')
        
        data = user_record.data
        
        # Premium Check
        is_p = user_record.premiumUntil and user_record.premiumUntil > datetime.now()
        title_prefix = "💎 " if is_p else ""
        
        embed = discord.Embed(title=f"{title_prefix}Profil Re:Volution ~ {data['name']}", color=0x86273d)
        embed.set_thumbnail(url=target.display_avatar.url)
        
        # Display HP and Max HP
        hp_str = f"❤️ `{user_record.hp}/{user_record.max_hp}` HP"
        
        embed.add_field(name='Level', value=f"🔰 `{data['level']}`", inline=True)
        embed.add_field(name='EXP', value=f"⬆️ `{data['exp']}/{data['next_exp']}`", inline=True)
        embed.add_field(name='Status', value=hp_str, inline=True)
        
        embed.add_field(name='Stats', value=f"⚔️ `{data['attack']}` Attack\n🛡️ `{data['defense']}` Defense\n💨 `{data['agility']}` Agility", inline=True)
        embed.add_field(name='Harta', value=f"{self.bot.coin_emoji} `{data['coins']}` Koin\n👹 `{data['karma']}` Karma", inline=True)
        
        await ctx.reply(embed=embed)

    @game.command(description="Beli item atau perlengkapan perang!")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def shop(self, ctx:commands.Context):
        """
        Beli item atau perlengkapan perang!
        """
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'inventory': True})
        if not user_record:
            return await ctx.reply('Kamu belum terdaftar!')
            
        data = user_record.data
        inventory = user_record.inventory
        
        with open('./src/game/shop.json') as file:
            items = json.load(file)

        embed = discord.Embed(title = 'Toko Xaneria', color=0xFFFF00)
        embed.description='"Hey, hey! Selamat datang. Silahkan, mau beli apa?"'
        embed.set_footer(text='Untuk membeli sebuah item, klik di bawah ini! v')
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
                        return "YA" if count > 0 else "TIDAK"
                    return str(count)
            
            if item['type'] == 'Skill' or item['type'] == 'Equipment':
                return "TIDAK"
            return "0"

        options_per_page = 5
        for index, item in enumerate(items[:options_per_page], start=1):
            owned_display = get_owned_display(item)
            embed.add_field(
                name=f"{index}. {item['name']}",
                value=f"**`{item['desc']}`**\n({item['func']})\n**Tipe:** {item['type']}\n**Harga:** {item['cost']} {item['paywith']}\n**Dimiliki:** {owned_display}",
                inline=False
            )

        view = ShopView(ctx, items, user_record.dict()) # Pass as dict for simplicity in View
        await ctx.reply(embed = embed, view=view)

    @game.command(description='Bertualang di Re:Volution!')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def adventure(self, ctx:commands.Context):
        """
        Bertualang di Re:Volution ~ The Dream World!
        """
        exp_gain = random.randint(10, 25)
        coin_gain = random.randint(15, 35)
        
        await give_rewards(ctx, ctx.author, exp_gain, coin_gain)
        await ctx.reply(f"Kamu bertualang di Dream World dan mendapatkan `{exp_gain}` EXP dan `{coin_gain}` Koin!")

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
        if member.bot:
            return await ctx.reply('Bot tidak bisa melakukan perlawanan!', ephemeral=True)
        game = GameInstance(ctx, ctx.author, member, self.bot)
        await game.start()


    @game.command(description='Lawan musuh-musuh yang ada di Re:Volution!')
    @app_commands.describe(enemy_tier='Musuh level berapa yang ingin kamu lawan?')
    @app_commands.rename(enemy_tier='level')
    @app_commands.describe(enemy_name='Nama musuh yang ingin kamu lawan?')
    @app_commands.rename(enemy_name = 'nama_musuh')
    @app_commands.choices(enemy_tier=[
        app_commands.Choice(name='BOSS', value='boss'),
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
        with open(f'./src/game/enemies/{enemy_tier.value}.json') as file:
            content = file.read()
            enemies = json.loads(content)
            
        enemy = None
        
        if enemy_name:
            for dict in enemies:
                if dict['name'].lower() == enemy_name.lower():
                    enemy = dict
                    break

            if enemy == None:
                return await ctx.reply(f"Aku tidak dapat menemukan musuh bernama **`{enemy_name}`** di level **`{enemy_tier.value.upper()}`**\nPastikan nama musuh dan/atau levelnya benar!", ephemeral=True)
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
        view = PaginatedEnemyView(ctx)
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
        current_acc_record = await db.user.find_unique(where={'id': ctx.author.id})
        old_acc_record = await db.user.find_unique(where={'id': old_acc.id})
        
        if not old_acc_record:
            return await ctx.reply("Akun Re:Volution tidak ditemukan!\nJika tidak yakin dengan ID akun Discord lamamu, silahkan hubungi langsung Schryzon!", ephemeral=True)
        
        if ctx.author.id == old_acc.id:
            return await ctx.reply("Hey! Akun yang kamu cantumkan sama dengan akun Discordmu saat ini!", ephemeral=True)
        
        embed = discord.Embed(title="Request Transfer Data Akun", color=ctx.author.color, timestamp=ctx.message.created_at)
        embed.add_field(
            name="Akun Lama",
            value=f"Nama: {old_acc_record.data['name']}\nID: {old_acc_record.id}",
            inline=False
        )

        embed.add_field(
            name="Akun Baru",
            value=f"Nama: {current_acc_record.data['name']}\nID: {current_acc_record.id}",
            inline=False
        )

        embed.add_field(
            name="Alasan",
            value=reason,
            inline=False
        )

        embed.set_author(name=ctx.author)
        embed.set_footer(text="Reply \"Approve\" jika disetujui\nReply \"Decline\" jika tidak disetujui")
        channel = self.bot.get_channel(1115422709585817710)
        await channel.send(embed=embed)
        await ctx.send("Aku telah mengirimkan request transfer data akun ke developer!\nMohon ditunggu persetujuannya ya!\nJangan lupa untuk mengaktifkan pesan DM dari aku karena nanti akan diberikan info apabila disetujui/ditolak.")


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
        game_instance = GuessGame(ctx, level.value)
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
        # Choose type -> Dropdown class
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'inventory': True})
        if not user_record or not user_record.inventory:
            return await ctx.reply("Kamu belum terdaftar atau akunmu bermasalah!", ephemeral=True)
            
        inventory = user_record.inventory
        user_items = inventory.items if isinstance(inventory.items, list) else []
        
        match type.value:
            case "item":
                things = [item for item in user_items if "0-" in item['_id'] and item.get('usefor') == "free"]
            
            case "equipment":
                things = [item for item in user_items if "1-" in item['_id']]

            case _:
                return await ctx.reply("Hey! Pilihlah salah satu dari opsi tersedia!", ephemeral=True)
            
        view = UseView(things, ctx)
        await ctx.reply(f'{ctx.author.mention}', view=view)

    @commands.hybrid_group(name="guild", description="Sistem Guild Re:Volution", fallback="info")
    @check_blacklist()
    async def guild(self, ctx: commands.Context):
        """
        Lihat informasi guild kamu atau guild orang lain.
        """
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            return await ctx.reply("Kamu belum bergabung dengan guild manapun! Gunakan `/guild create` untuk membuat guild baru.", ephemeral=True)
        
        guild = user_record.guild
        members_count = await db.user.count(where={'guildId': guild.id})
        
        embed = discord.Embed(title=guild.name, description=guild.tagline or "No tagline set.", color=ctx.author.color)
        if guild.iconUrl:
            embed.set_thumbnail(url=guild.iconUrl)
        
        embed.add_field(name="👑 Owner", value=f"<@{guild.ownerId}>")
        embed.add_field(name="👥 Anggota", value=f"{members_count} Anggota")
        embed.set_footer(text=f"ID Guild: {guild.id} | Dibuat pada {guild.createdAt.strftime('%d/%m/%Y')}")
        
        await ctx.reply(embed=embed)

    @guild.command(name="create", description="Buat guild baru! (Biaya: 5000 Koin)")
    @app_commands.describe(name="Nama guild impianmu")
    @check_blacklist()
    async def guild_create(self, ctx: commands.Context, name: str):
        """
        Buat guild baru untuk komunitasmu!
        """
        user_record = await db.user.find_unique(where={'id': ctx.author.id})
        if not user_record:
            return await ctx.reply("Kamu belum terdaftar di Re:Volution!", ephemeral=True)
        
        if user_record.guildId:
            return await ctx.reply("Kamu sudah berada di sebuah guild! Keluar dulu sebelum membuat yang baru.", ephemeral=True)
            
        # Check if user already owns a guild (Unique constraint check)
        existing_owned = await db.guild.find_unique(where={'ownerId': ctx.author.id})
        if existing_owned:
            return await ctx.reply(f"Kamu sudah memiliki guild bernama **{existing_owned.name}**! Kamu harus membubarkannya dulu sebelum membuat yang baru.", ephemeral=True)
        
        data = user_record.data
        if data['coins'] < 5000:
            return await ctx.reply(f"Koinmu tidak cukup! Dibutuhkan **5000** Koin, kamu hanya punya **{data['coins']}**.", ephemeral=True)
        
        # Check if name exists
        existing = await db.guild.find_unique(where={'name': name})
        if existing:
            return await ctx.reply(f"Nama guild `{name}` sudah diambil orang lain!", ephemeral=True)
        
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
        
        embed = discord.Embed(title="🏰 Guild Diciptakan!", description=f"Selamat! Guild **{name}** telah resmi didirikan.", color=discord.Color.gold())
        embed.add_field(name="Biaya", value="5000 Koin")
        embed.set_footer(text="Gunakan /guild edit untuk mengatur ikon dan tagline!")
        
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
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            return await ctx.reply("Kamu tidak berada dalam guild!", ephemeral=True)
        
        guild = user_record.guild
        if guild.ownerId != ctx.author.id:
            return await ctx.reply("Hanya Owner guild yang bisa mengubah pengaturan ini!", ephemeral=True)
        
        update_data = {}
        if name:
            existing = await db.guild.find_unique(where={'name': name})
            if existing and existing.id != guild.id:
                return await ctx.reply(f"Nama guild `{name}` sudah digunakan!", ephemeral=True)
            update_data['name'] = name
        if tagline:
            update_data['tagline'] = tagline
        if icon_url:
            if not icon_url.startswith("http"):
                return await ctx.reply("Ikon harus berupa URL gambar yang valid!", ephemeral=True)
            update_data['iconUrl'] = icon_url
            
        if not update_data:
            return await ctx.reply("Pilihl|ah apa yang ingin kamu ubah!", ephemeral=True)
            
        await db.guild.update(where={'id': guild.id}, data=update_data)
        await ctx.reply(f"✅ Detail guild **{guild.name}** berhasil diperbarui!")

    @guild.command(name="invite", description="Undang seseorang ke guildmu")
    @app_commands.describe(user="User yang ingin diundang")
    @check_blacklist()
    async def guild_invite(self, ctx: commands.Context, user: discord.Member):
        """
        Undang temanmu untuk bergabung dalam guild!
        """
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            return await ctx.reply("Kamu tidak berada dalam guild!", ephemeral=True)
        
        guild = user_record.guild
        if guild.ownerId != ctx.author.id:
            return await ctx.reply("Hanya Owner yang bisa mengundang orang baru untuk saat ini!", ephemeral=True)
            
        target_record = await db.user.find_unique(where={'id': user.id})
        if not target_record:
            return await ctx.reply("Orang tersebut belum terdaftar di Re:Volution!", ephemeral=True)
        
        if target_record.guildId:
            return await ctx.reply("Orang tersebut sudah memiliki guild!", ephemeral=True)
            
        # Sending invitation
        view = GuildInviteView(guild, user)
        await ctx.reply(f"💌 {user.mention}, kamu diundang untuk bergabung ke guild **{guild.name}**!", view=view)

    @guild.command(name="leave", description="Keluar dari guild saat ini")
    @check_blacklist()
    async def guild_leave(self, ctx: commands.Context):
        """
        Keluar dari guild. Jika kamu Owner, guild akan dibubarkan!
        """
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            return await ctx.reply("Kamu tidak berada dalam guild!", ephemeral=True)
            
        guild = user_record.guild
        if guild.ownerId == ctx.author.id:
            # Bubarkan guild
            await db.guild.delete(where={'id': guild.id})
            await ctx.reply(f"💥 Guild **{guild.name}** telah dibubarkan karena Owner keluar.")
        else:
            await db.user.update(where={'id': ctx.author.id}, data={'guild': {'disconnect': True}})
            await ctx.reply(f"👋 Kamu telah keluar dari guild **{guild.name}**.")

    @guild.command(name="leaderboard", aliases=["lb"], description="Lihat guild terkuat di Re:Volution!")
    @check_blacklist()
    async def guild_leaderboard(self, ctx: commands.Context):
        """
        Papan peringkat Guild berdasarkan jumlah anggota.
        """
        guilds = await db.guild.find_many(include={'members': True})
        if not guilds:
            return await ctx.reply("Belum ada guild yang terdaftar!")
            
        # Sort by member count DESC
        sorted_guilds = sorted(guilds, key=lambda g: len(g.members), reverse=True)
        top_100 = sorted_guilds[:100]
        
        view = LeaderboardView(ctx, top_100, "🏆 Papan Peringkat Guild 🏆", type="guild")
        embed = await view.get_embed()
        await ctx.reply(embed=embed, view=view)

    @guild.command(name="icon", description="Lihat atau ubah ikon guildmu!")
    @app_commands.describe(url="URL Gambar baru untuk ikon guild (Kosongkan untuk melihat ikon saat ini)")
    @check_blacklist()
    async def guild_icon(self, ctx: commands.Context, url: str = None):
        """
        Lihat atau ubah ikon guildmu agar terlihat lebih megah!
        """
        user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'guild': True})
        if not user_record or not user_record.guild:
            return await ctx.reply("Kamu tidak berada dalam guild!", ephemeral=True)
        
        guild = user_record.guild
        
        if url:
            if guild.ownerId != ctx.author.id:
                return await ctx.reply("Hanya Owner guild yang bisa mengubah ikon!", ephemeral=True)
            if not url.startswith("http"):
                return await ctx.reply("Ikon harus berupa URL gambar yang valid!", ephemeral=True)
            
            await db.guild.update(where={'id': guild.id}, data={'iconUrl': url})
            return await ctx.reply(f"✅ Ikon guild **{guild.name}** berhasil diperbarui!")
            
        if not guild.iconUrl:
            return await ctx.reply(f"Guild **{guild.name}** belum memiliki ikon!")
            
        embed = discord.Embed(title=f"Ikon Guild: {guild.name}", color=ctx.author.color)
        embed.set_image(url=guild.iconUrl)
        await ctx.reply(embed=embed)

    @commands.hybrid_group(name="premium", description="Fitur Premium Re:Volution", fallback="info")
    @check_blacklist()
    async def premium(self, ctx: commands.Context):
        """
        Lihat status dan keuntungan menjadi Dream Weaver.
        """
        user_record = await db.user.find_unique(where={'id': ctx.author.id})
        if not user_record:
            return await ctx.reply("Kamu belum terdaftar!")
            
        is_p = user_record.premiumUntil and user_record.premiumUntil > datetime.now()
        
        embed = discord.Embed(title="💎 Dream Weaver Premium 💎", color=0x00ffff)
        if is_p:
            embed.description = f"Status: **AKTIF**\nBerlaku sampai: <t:{int(user_record.premiumUntil.timestamp())}:F>"
        else:
            embed.description = "Status: **TIDAK AKTIF**\nJadilah Dream Weaver untuk mendapatkan berbagai keuntungan!"
            
        embed.add_field(name="✨ Keuntungan", value=(
            "• **2x EXP & Koin**: Petualangan jadi lebih cepat!\n"
            "• **💎 Badge Eksklusif**: Tampil beda di profil & leaderboard.\n"
            "• **🏰 Guild Prioritas**: Biaya pembuatan guild lebih murah (mendatang).\n"
            "• **💖 Dukungan**: Membantu pengembangan Re:Volution!"
        ), inline=False)
        
        embed.set_footer(text="Gunakan /premium buy untuk cara berlangganan.")
        await ctx.reply(embed=embed)

    @premium.command(name="buy", description="Cara menjadi Dream Weaver (15k IDR / 30 Hari)")
    @check_blacklist()
    async def premium_buy(self, ctx: commands.Context):
        """
        Instruksi berlangganan Premium.
        """
        saweria_link = getenv('SAWERIA_LINK', 'https://saweria.co/Schryzon')
        
        embed = discord.Embed(title="💎 Cara Menjadi Dream Weaver", color=0x00ffff)
        embed.description = (
            f"Dukung pengembangan bot ini hanya dengan **Rp 15.000 / 30 Hari**!\n\n"
            f"**Langkah-langkah:**\n"
            f"1. Buka link Saweria berikut: **[Klik di Sini]({saweria_link})**\n"
            f"2. Selesaikan pembayaran (nominal Rp 15.000).\n"
            f"3. Simpan/Screenshot bukti pembayaran berhasil.\n"
            f"4. Jalankan command `/premium claim` dan lampirkan screenshot tersebut.\n\n"
            f"*Status premium akan diaktifkan oleh admin segera setelah verifikasi.*"
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.reply(embed=embed)

    @premium.command(name="claim", description="Klaim status Premium dengan mengunggah bukti pembayaran!")
    @app_commands.describe(bukti="Screenshot bukti pembayaran Saweria-mu")
    @check_blacklist()
    async def premium_claim(self, ctx: commands.Context, bukti: discord.Attachment):
        """
        Kirim bukti pembayaranmu untuk diverifikasi oleh Xelvie!
        """
        staff_channel_id = getenv('STAFF_CHANNEL_ID')
        if not staff_channel_id:
            return await ctx.reply("Sistem klaim sedang tidak tersedia, silahkan hubungi admin secara langsung.", ephemeral=True)
            
        staff_channel = self.bot.get_channel(int(staff_channel_id))
        if not staff_channel:
            return await ctx.reply("Terjadi kesalahan konfigurasi, silahkan hubungi admin.", ephemeral=True)
            
        # Send raw notification for Xelvie to catch
        await staff_channel.send(f"[CLAIM_PREMIUM] {ctx.author.id} {bukti.url}")
        
        await ctx.reply("✅ Bukti pembayaranmu telah dikirim! Mohon tunggu verifikasi dari admin (Xelvie akan memberitahumu!).", ephemeral=True)

class GuildInviteView(View):
    def __init__(self, guild, target_user):
        super().__init__(timeout=60.0)
        self.guild = guild
        self.target_user = target_user

    @discord.ui.button(label="Terima", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            return await interaction.response.send_message("Undangan ini bukan untukmu!", ephemeral=True)
            
        # Re-check if guild still exists
        guild_exists = await db.guild.find_unique(where={'id': self.guild.id})
        if not guild_exists:
            return await interaction.response.send_message("Guild ini sudah tidak ada!", ephemeral=True)
            
        await db.user.update(where={'id': self.target_user.id}, data={'guild': {'connect': {'id': self.guild.id}}})
        await interaction.response.edit_message(content=f"✅ {self.target_user.mention} telah bergabung dengan guild **{self.guild.name}**!", view=None)

    @discord.ui.button(label="Tolak", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            return await interaction.response.send_message("Undangan ini bukan untukmu!", ephemeral=True)
        await interaction.response.edit_message(content=f"❌ {self.target_user.mention} menolak undangan.", view=None)

async def setup(bot):
    await bot.add_cog(Game(bot))