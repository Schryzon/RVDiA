"""
Commands and features for her game.
Re:Volution ~ The Dream World.
An unnecessarily large file.
It doesn't need to be here, but it is.
"""

import asyncio
import re
import discord
import datetime
import time
import random
import json
import math
from os import getenv, listdir, path
from discord.ui import View, Button, button
from discord import app_commands
from discord.ext import commands
from scripts.main import connectdb, has_registered, check_blacklist
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
        
        database = await connectdb('Game')
        user1_data = await database.find_one({'_id':self.user1.id})
        user1_stats = [user1_data['attack'], user1_data['defense'], user1_data['agility']]
        comp_data1 = {
            'stats': user1_stats,
            'hp': self.user1_hp
        }
        self.p1_skill_limit = calc_skill_limit(user1_data['level'])

        if self.command_name == "fight":
            # Fight = PvP
            user2_data = await database.find_one({'_id':self.user2.id})
            if user2_data is None:
                await self.ctx.reply(f'Waduh! Sepertinya <@{self.user2.id}> belum membuat akun Re:Volution!')
                raise Exception('Rival has no account!')
            
            user2_stats = [user2_data['attack'], user2_data['defense'], user2_data['agility']]
            comp_data2 = {
                'stats': user2_stats,
                'hp': self.user2_hp
            }
            self.p2_skill_limit = calc_skill_limit(user2_data['level'])

        else:
            user2_stats = [self.user2['atk'], self.user2['def'], self.user2['agl']]
            comp_data2 = {
                'stats':user2_stats,
                'hp':self.user2_hp
            }

        return [comp_data1, comp_data2] # List containing dict, feeling stressful


    async def attack(self, dealer_stat:list, taker_stat:list, dealer_id:int, is_defending:bool):
        try:
            if not isinstance(self.user2, discord.Member):
                user_2_max_hp = self.user2['hp']
        except AttributeError: # Ignore on Attr Error
            pass
        user_1_atk, user_1_def, user_1_agl = dealer_stat[0], dealer_stat[1], dealer_stat[2]
        user_2_atk, user_2_def, user_2_agl = taker_stat[0], taker_stat[1], taker_stat[2]

        if is_defending:
            user_2_def += random.randint(8, 15)
        if dealer_id != 1 and self.ctx.command.name == "battle":
            if user_2_max_hp > 500:
                scaling = user_2_max_hp/90
            elif user_2_max_hp > 200:
                scaling = user_2_max_hp/10
            else:
                scaling = user_2_max_hp

            damage = round(max(0, user_1_atk*(random.randint(80, 100) - user_2_def)/scaling))
        else:
            damage = round(max(0, user_1_atk*(random.randint(80, 100) - user_2_def)/100))
        miss_chance = (user_2_agl - user_1_agl)*2 + 5
        hit_chance = 100 - miss_chance
        attack_chance = random.randint(0, 100)

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

            return damage
        
        else:
            return 0
        
    def defend(self, user):
        if user == self.user1:
            self.user1_defend = True
        else:
            self.user2_defend = True
    
    async def use(self, user1, type):
        database = await connectdb('Game')
        user1_data = await database.find_one({'_id':user1.id})
        items = user1_data['items']
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
                    if user1 == self.user1:
                        self.user1_hp += int(func[1])

                    else:
                        self.user2_hp += int(func[1])
                    if isinstance(user1, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} memulihkan `{func[1]}` HP!')
                    else:
                        await self.ctx.channel.send(f"{user1['name']} memulihkan `{func[1]}` HP!")

                case 'DMG':
                    if user1 == self.user1:
                        self.user2_hp -= int(func[1])

                    else:
                        self.user1_hp -= int(func[1])
                    
                    if isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} memberikan `{func[1]}` Damage instan ke {user2.mention}!')
                    elif not isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f"{user1['name']} memberikan `{func[1]}` Damage instan ke {user2.mention}!")
                    else:
                        await self.ctx.channel.send(f"{user1.mention} memberikan `{func[1]}` Damage instan ke {user2['name']}!")

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
                    if user1 == self.user1:
                        self.user2_hp -= int(func[1])
                        self.user1_hp += int(func[1])

                    else:
                        self.user1_hp -= int(func[1])
                        self.user2_hp += int(func[1])
                    if isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f'{user1.mention} mengambil `{func[1]}` HP dari {user2.mention}!')
                    elif not isinstance(user1, discord.Member) and isinstance(user2, discord.Member):
                        await self.ctx.channel.send(f"{user1['name']} mengambil `{func[1]}` HP dari {user2.mention}!")
                    else:
                        await self.ctx.channel.send(f"{user1.mention} mengambil `{func[1]}` HP dari {user2['name']}!")

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
                    damage = await self.attack(self.user1_stats, self.user2_stats, self.user1.id, self.user2_defend)
                    embed = discord.Embed(title=f'💥{self.user1.display_name} Menyerang!', color=self.user1.color)
                    if isinstance(self.user2, discord.Member):
                        embed.description = f"**`{damage}` Damage!**\nHP <@{self.user2.id}> tersisa `{self.user2_hp}` HP!"
                    else:
                        embed.description = f"**`{damage}` Damage!**\nHP {self.user2['name']} tersisa `{self.user2_hp}` HP!"
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
                        damage = await self.attack(datas[1]['stats'], datas[0]['stats'], self.user2.id, self.user1_defend)
                        embed = discord.Embed(title=f'💥{self.user2.display_name} Menyerang!', color=self.user2.color)
                        embed.description = f"**`{damage}` Damage!**\nHP <@{self.user1.id}> tersisa `{self.user1_hp}` HP!"
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
                        damage = await self.attack(self.user2_stats, self.user1_stats, 1, self.user1_defend)
                        embed = discord.Embed(title=f'💥{self.user2["name"]} Menyerang!', color=0xff0000)
                        embed.description = f"**`{damage}` Damage!**\nHP <@{self.user1.id}> tersisa `{self.user1_hp}` HP!"
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
        self.turns = turns
        self.user1_stats = instance.user1_stats
        self.user2_stats = instance.user2_stats
        self.ai_skill_usage = instance.ai_skill_usage
        self.traits = [self.attack_mood, self.defend_mood, self.skill_mood, self.escape_mood]
        self.actions = ["attack", "defend"]
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

        # Defining escape moods based on level. (Does not apply to LOW - SUPER NORMAL & BONUS ENEMY)
        tier = self.user2['tier']
        match tier:
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

        sorted_traits = sorted(self.traits, reverse=True)
        if random.randint(0, 100) < 10:
            action = random.choice(self.actions)
        else:
            action = random.choice([action for trait, action in zip(self.traits, self.actions) if trait == sorted_traits[0]])

        return action
    
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
            return await interaction.response.send_message(f"Hey! Kamu tidak diizinkan untuk memilih!", ephemeral=True) #Does this even work
        if self.values[0] == 'none' and self.types == 'item':
            return await interaction.response.send_message("Kamu tidak memiliki item apapun!", ephemeral=True)
        elif self.values[0] == 'none' and self.types == 'skill':
            return await interaction.response.send_message("Kamu tidak memiliki skill apapun!", ephemeral=True)
        
        database = await connectdb('Game')
        data = await database.find_one({'_id':self.user1.id})
        db_items = data['items']
        used_item = None
        if db_items == self.items:
            for item in self.items:
                if item['_id'] == self.values[0] and not item['owned'] <= 0 and self.types == 'item':
                    await database.find_one_and_update(
                        {'_id':self.user1.id, 'items._id':self.values[0]},
                        {'$inc':{'items.$.owned':-1}}
                        )
                    used_item = [item['name'], item['func']]
                    break

                elif item['_id'] == self.values[0] and not item['owned'] <= 0 and self.types == 'skill':
                    used_item = [item['name'], item['func']]
                    break

        if used_item is None:
            raise Exception("The Item Dropdown callback is behaving wierdly!")
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
        database = await connectdb('Game')
        data = await database.find_one({'_id':interaction.user.id})
        await database.find_one_and_delete({'_id':interaction.user.id})
        await interaction.response.send_message(f'Aku telah menghapus akunmu.\nSampai jumpa, `{data["name"]}`, di Re:Volution!')
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
        database = await connectdb('Game')
        data = await database.find_one({'_id':interaction.user.id})
        db_dict = {item['_id']: item for item in items}
        mongo_dict = {item['_id']: item for item in data['items']}

        matched_dict = db_dict[item_id]
        current_money = data['coins'] if matched_dict['paywith'] == "Koin" else data['karma']
        if current_money < matched_dict['cost']:
            return await interaction.response.send_message(f"Waduh!\n{matched_dict['paywith']}mu tidak cukup untuk membeli barang ini!", ephemeral=True)

        if item_id in db_dict and item_id in mongo_dict: # User already bought this item in the past
            if '1-' in item_id:
                return await interaction.response.send_message("Kamu hanya bisa membeli equipment sekali saja!", ephemeral=True)
            if '2-' in item_id:
                return await interaction.response.send_message("Kamu hanya bisa memelajari skill sekali saja!", ephemeral=True)
            filter_ = {'_id': interaction.user.id, 'items._id': item_id}
            update_ = {'$inc': {'items.$.owned': 1}}
            await database.update_one(filter=filter_, update=update_)

            currency = 'coins' if matched_dict['paywith'] == "Koin" else 'karma'
            cost = matched_dict['cost']
            update_ = {'$inc': {currency: cost*-1}}
            await database.update_one(filter=filter_, update=update_)

            await interaction.response.send_message(f"Pembelian berhasil!\nKamu telah membeli `{matched_dict['name']}`", ephemeral=True)

        else:
            currency = 'coins' if matched_dict['paywith'] == "Koin" else 'karma'
            cost = matched_dict['cost']
            del matched_dict['cost']
            del matched_dict['paywith']
            matched_dict['owned'] = 1
            await database.update_one({'_id': interaction.user.id},
                                {'$push':{'items':matched_dict}})
            
            await database.update_one({'_id': interaction.user.id}, {'$inc':{currency: cost*-1}}) # Second update, avoiding conflict

            await interaction.response.send_message(f"Pembelian berhasil!\nKamu telah membeli `{matched_dict['name']}`", ephemeral=True)

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
        with open(f'./src/game/enemies/{self.values[0]}.json') as file:
            content = file.read()
            enemies = json.loads(content)
        
        embed = discord.Embed(title=f"Daftar Musuh", color=interaction.user.color)
        for index, enemy in enumerate(enemies):
            embed.add_field(
                name=f"{index+1}. {enemy['name']} ({enemy['tier']})",
                value=f"\"{enemy['desc']}\"\n**HP**: `{enemy['hp']}`\n**Attack**: `{enemy['atk']}`\n**Defense**: `{enemy['def']}`\n**Agility**: `{enemy['agl']}`\n",
                inline=False
                )
        embed.set_thumbnail(url = interaction.user.display_avatar.url) # Lazy, might add a placeholder later
        embed.set_footer(text="Kamu bisa melawan salah satu dari mereka dengan command battle!")
        await interaction.response.edit_message(content='', embed=embed, view=EnemyView())

class EnemyView(View):
    def __init__(self):
        super().__init__(timeout=120)
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
        
    def get_owned_count(self, item_id):
        try:
            for key in self.data.get('items', []):
                if key['_id'] == item_id:
                    return key.get('owned', 0)
        except:
            pass
        return 0

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
            owned_count = self.get_owned_count(item['_id'])
            self.owned.append(owned_count)
            generate_embed_field(index, item, owned_count)

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
        if options == [] or options == None:
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
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menggunakan dropdown ini!")
        if self.values[0] == 'none':
            return await interaction.response.send_message("Kamu tidak memiliki apapun!\nKamu harus membeli barang/skill di `/game shop`!", ephemeral=True)
        database = await connectdb('Game')
        data = await database.find_one({'_id':interaction.user.id})
        item = self.values[0]
        if '1-' in item:
            matching = [x for x in data['equipments'] if x['_id'] == item]
            if matching: # Uneqip
                func = matching[0]['func'].split('+')
                func = convert_to_db_stat(func)
                await database.update_one({'_id':interaction.user.id}, {'$pull':{'equipments':{'_id':item}}})
                await database.update_one({'_id':interaction.user.id}, {'$inc':{func[0]:int(func[1])*-1}})
                await interaction.response.send_message(f"Kamu telah melepas `{matching[0]['name']}`!")
            
            else:
                item = await database.find_one({'_id':interaction.user.id, 'items._id':item})
                matching = [x for x in item['items'] if x['_id'] == self.values[0]]
                func = matching[0]['func'].split('+')
                func = convert_to_db_stat(func)

                same_type = [x for x in data['equipments'] if x['usefor'] == matching[0]['usefor']]
                if same_type:
                    func_2 = same_type[0]['func'].split('+')
                    func_2 = convert_to_db_stat(func_2)
                    await database.update_one({'_id':interaction.user.id}, {'$pull':{'equipments':{'_id':same_type[0]['_id']}}})
                    await database.update_one({'_id':interaction.user.id}, {'$inc':{func_2[0]:int(func_2[1])*-1}})

                await database.update_one({'_id':interaction.user.id}, {'$push':{'equipments':matching[0]}})
                await database.update_one({'_id':interaction.user.id}, {'$inc':{func[0]:int(func[1])}})
                await interaction.response.send_message(f"Kamu telah menggunakan `{matching[0]['name']}`!")

        else:
            item = await database.find_one({'_id':interaction.user.id, 'items._id':item})
            matching = [x for x in item['items'] if x['_id'] == self.values[0]]
            func = matching[0]['func'].split('+')
            func = convert_to_db_stat(func)
            await database.update_one({'_id':interaction.user.id, 'items._id':self.values[0]}, {'$inc':{'items.$.owned':-1}})
            await database.update_one({'_id':interaction.user.id}, {'$inc':{func[0]:int(func[1])}})
            await interaction.response.send_message(f"Kamu telah menggunakan `{matching[0]['name']}`!")
            await asyncio.sleep(1)
            level_uped = await level_up(self.ctx)
            if level_uped:
                await send_level_up_msg(self.ctx)

    
class UseView(View):
    def __init__(self, items:list, ctx:commands.Context):
        super().__init__(timeout=30)
        self.add_item(UseDropdown(items, ctx))

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
        name=name or ctx.author.name
        database = await connectdb('Game')
        data = await database.find_one({'_id':ctx.author.id})
        if data:
            expected_fields = set(default_data.keys())
            unexpected_fields = set(data.keys()) - expected_fields
            for field in unexpected_fields:
                del data[field] # Remove useless keys

            for key, value in default_data.items():
                data.setdefault(key, value)
            await database.replace_one({'_id':ctx.author.id}, data)
            return await ctx.reply('Akunmu sudah diperbarui!')
        
        new_data = {
            **default_data,
            '_id':ctx.author.id,
            'name':name
        }

        await database.insert_one(new_data)
        await ctx.reply(f'Akunmu sudah didaftarkan!\nSelamat datang di Re:Volution, **`{name}`**!')
        await asyncio.sleep(0.7)
        await self.account(ctx)
    
    @game.command(description='Menghapuskan akunmu dari Re:Volution.')
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

    @game.command(aliases=['login'], description='Dapatkan bonus login harian!')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def daily(self, ctx:commands.Context):
        """
        Dapatkan bonus login harian!
        """
        database = await connectdb('Game')
        data = await database.find_one({'_id':ctx.author.id})
        last_login = data['last_login']
        current_time = datetime.datetime.now()
        delta_time = current_time - last_login

        next_login = last_login + datetime.timedelta(hours=24)
        next_login_unix = int(time.mktime(next_login.timetuple()))

        if delta_time.total_seconds() <= 24*60*60:
            return await ctx.reply(f'Kamu sudah login hari ini!\nKamu bisa login lagi pada <t:{next_login_unix}:f>')
        
        else:
            new_coins = random.randint(15, 25)
            new_karma = random.randint(1, 5)
            new_exp = random.randint(10, 20)
            await database.find_one_and_update(
                {'_id':ctx.author.id},
                {'$inc':{'coins':new_coins, 'karma':new_karma, 'exp':new_exp}, '$set':{'last_login':datetime.datetime.now()}}
            )
            embed = discord.Embed(title='Bonus Harianmu', color=0x00FF00, timestamp=next_login)
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            embed.add_field(
                name="Kamu Memperoleh:",
                value=f"{self.bot.coin_emoji_anim} `{new_coins}` Koin\n👹 `{new_karma}` Karma\n⬆️ `{new_exp}` EXP!'",
                inline=False
            )
            embed.set_footer(text='Bonus selanjutnya pada ')
            await ctx.reply(embed=embed)
            level_uped = await level_up(ctx)
            if level_uped:
                return await send_level_up_msg(ctx)
            
    @game.command(description='Lihat profil pengguna di Re:Volution!')
    @app_commands.describe(user='Pengguna mana yang ingin dilihat akunnya?')
    @app_commands.rename(user='pengguna')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def account(self, ctx:commands.Context, *, user:discord.User=None):
        """
        Lihat profil pengguna di Re:Volution ~ The Dream World!
        """
        # Plans: PIL profile pic, equipment & items should be seperate commands
        user = user or ctx.author
        database = await connectdb('Game')
        data = await database.find_one({'_id':user.id})

        # General data
        player_name = data['name']
        level = data['level']
        exp, next_exp = data['exp'], data['next_exp']
        last_login = data['last_login']

        # Stats & economy
        coins = data['coins']
        karma = data['karma']

        # Battle stats
        attack, defense, agility = data['attack'], data['defense'], data['agility']
        items = [x for x in data['items'] if x['owned'] > 0 and x['type'] != 'Skill']
        skills = [x for x in data['items'] if x['owned'] > 0 and x['type'] == 'Skill']
        equipments = [x['name'] for x in data['equipments']]
        equipment_string = '\n'.join(equipments)
        if equipment_string == '' or equipment_string == '\n':
            equipment_string = 'Tidak menggunakan equipment apapun.'


        embed = discord.Embed(title=player_name, timestamp=last_login, color=ctx.author.color)
        embed.set_author(name='Info Akun Re:Volution ~ The Dream World')
        embed.description = f'Alias: {user}'
        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(
            name=f'Level {level}', 
            value=f'⬆️ EXP: `{exp}`/`{next_exp}`', 
            inline=False
            )

        embed.add_field(
            name=f'Status Keuangan',
            value=f'{self.bot.coin_emoji} Koin: `{coins}`\n👹 Karma: `{karma}`', 
            inline=False
            )

        embed.add_field(
            name=f'Statistik Tempur', 
            value=f'💥 Attack: `{attack}`\n🛡️ Defense: `{defense}`\n👟 Agility: `{agility}`', 
            inline=False
            )
        
        embed.add_field(
            name=f'Barang & Skill', 
            value=f'👜 Barang: `{len(items)}`\n🔮 Skill: `{len(skills)}`', 
            inline=False
            )
        
        embed.add_field(
            name=f'Equipment Terpakai', 
            value=f'**`{equipment_string}`**', 
            inline=False
            )
        
        embed.set_footer(text='Login harian terakhir ')
        await ctx.reply(embed = embed)

    @game.command(description="Beli item atau perlengkapan perang!")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def shop(self, ctx:commands.Context):
        """
        Beli item atau perlengkapan perang!
        """
        # Plans: show details and make a paginator or something
        database = await connectdb('Game')
        data = await database.find_one({'_id':ctx.author.id})
        with open('./src/game/shop.json') as file:
            content = file.read()
            items = json.loads(content)

        embed = discord.Embed(title = 'Toko Xaneria', color=0xFFFF00)
        embed.description='"Hey, hey! Selamat datang. Silahkan, mau beli apa?"'
        embed.set_footer(text='Untuk membeli sebuah item, klik di bawah ini! v')
        embed.set_thumbnail(url=getenv('xaneria'))

        def get_owned_count(item_id):
            try:
                for key in data.get('items', []):
                    if key['_id'] == item_id:
                        return key.get('owned', 0)
            except:
                pass
            return 0

        def generate_embed_field(index, item, owned_count):
            embed.add_field(
                name=f"{index}. {item['name']}",
                value=f"**`{item['desc']}`**\n({item['func']})\n**Tipe:** {item['type']}\n**Harga:** {item['cost']} {item['paywith']}\n**Dimiliki:** {owned_count}",
                inline=False
            )

        options_per_page = 5
        owned = []
        for index, item in enumerate(items, start=1):
            if index > options_per_page:
                break

            owned_count = get_owned_count(item['_id'])
            owned.append(owned_count)
            generate_embed_field(index, item, owned_count)

        view = ShopView(ctx, items, data)
        await ctx.reply(embed = embed, view=view)

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
        view = EnemyView()
        async with ctx.typing():
            await ctx.reply(f"Untuk melihat daftar musuh, silahkan tekan di bawah ini ↓", view=view)


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
        database = await connectdb('Game')
        current_acc_data = await database.find_one({'_id':ctx.author.id})
        old_acc_data = await database.find_one({'_id':old_acc.id})
        if not old_acc_data:
            return await ctx.reply("Akun Re:Volution tidak ditemukan!\nJika tidak yakin dengan ID akun Discord lamamu, silahkan hubungi langsung Schryzon!", ephemeral=True)
        
        if ctx.author.id == old_acc_data['_id']:
            return await ctx.reply("Hey! Akun yang kamu cantumkan sama dengan akun Discordmu saat ini!", ephemeral=True)
        
        embed = discord.Embed(title="Request Transfer Data Akun", color=ctx.author.color, timestamp=ctx.message.created_at)
        embed.add_field(
            name="Akun Lama",
            value=f"Nama: {old_acc_data['name']}\nID: {old_acc_data['_id']}",
            inline=False
        )

        embed.add_field(
            name="Akun Baru",
            value=f"Nama: {current_acc_data['name']}\nID: {current_acc_data['_id']}",
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
        database = await connectdb('Game')
        data = await database.find_one({'_id':ctx.author.id})
        match type.value:
            case "item":
                things = [item for item in data['items'] if "0-" in item['_id'] and item['usefor'] == "free"]
            
            case "equipment":
                things = [item for item in data['items'] if "1-" in item['_id']]

            case _:
                return await ctx.reply("Hey! Pilihlah salah satu dari opsi tersedia!", ephemeral=True)
            
        view = UseView(things, ctx)
        await ctx.reply(f'{ctx.author.mention}', view=view)

async def setup(bot):
    await bot.add_cog(Game(bot))