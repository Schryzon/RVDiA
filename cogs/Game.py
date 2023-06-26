"""
The most STRESSFUL file I've ever made
Like, what the hell have I typed all this time?!
Do all of these even make sense???
"""

import asyncio
import re
import discord
import datetime
import time
import random
import json
from os import getenv, listdir, path
from discord.ui import View, Button, button
from discord import app_commands
from discord.ext import commands
from scripts.main import connectdb, check_blacklist, has_registered
from scripts.game import level_up, send_level_up_msg, split_reward_string, give_rewards

class FightView(View):
    def __init__(self):
        super().__init__(timeout=25.0)

    @button(label = 'Serang', custom_id='attack', style=discord.ButtonStyle.danger, emoji='💥')
    async def attack(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: 💥Serang")
        await asyncio.sleep(0.5)

    @button(label='Tahan', custom_id='defend', style=discord.ButtonStyle.blurple, emoji='🛡️')
    async def defend(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: 🛡️Tahan")
        await asyncio.sleep(0.5)

    @button(label='Barang', custom_id='item', style=discord.ButtonStyle.green, emoji='👜')
    async def item(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: 👜Barang")
        await asyncio.sleep(0.5)

    @button(label='Musuh', custom_id='check', style=discord.ButtonStyle.gray, emoji='❔')
    async def check(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: ❔Musuh")
        await asyncio.sleep(0.5)

    @button(label='Kabur', custom_id='end', style=discord.ButtonStyle.gray, emoji='🏃')
    async def flee(self, interaction:discord.Interaction, button:Button):
        if interaction.message.mentions[0] != interaction.user:
            return await interaction.response.send_message("Kamu tidak diizinkan untuk menekan tombol ini!", ephemeral=True)
        await interaction.response.send_message("Opsi terpilih: 🏃Kabur")
        await asyncio.sleep(0.5)

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

    async def gather_data(self):
        database = connectdb('Game')
        user1_data = database.find_one({'_id':self.user1.id})
        user1_stats = [user1_data['attack'], user1_data['defense'], user1_data['agility']]
        comp_data1 = {
            'stats': user1_stats,
            'hp': self.user1_hp
        }

        if self.command_name == "fight":
            # Fight = PvP
            user2_data = database.find_one({'_id':self.user2.id})
            if user2_data is None:
                await self.ctx.reply(f'Waduh! Sepertinya <@{self.user2.id}> belum membuat akun Re:Volution!')
                raise Exception('Rival has no account!')
            
            user2_stats = [user2_data['attack'], user2_data['defense'], user2_data['agility']]
            comp_data2 = {
                'stats': user2_stats,
                'hp': self.user2_hp
            }

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
            damage = round(max(0, user_1_atk*(random.randint(80, 100) - user_2_def)/user_2_max_hp))
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
    
    async def use(self, user1):
        database = connectdb('Game')
        user1_data = database.find_one({'_id':user1.id})
        items = user1_data['items']
        view = ItemView(items, user1)
        await self.ctx.channel.send(f"{user1.mention}, 10 detik untuk memilih item.", view=view)

    async def func_converter(self, func:str, user1, user2):
        func = re.sub(r'\(|\)', '', func)
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
                
                if isinstance(user1, discord.Member):
                    await self.ctx.channel.send(f'{user1.mention} memberikan `{func[1]}` Damage instan ke {user2.mention}!')
                else:
                    await self.ctx.channel.send(f"{user1['name']} memberikan `{func[1]}` Damage instan ke {user2.mention}!")

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
                    await self.ctx.channel.send(f'{user1.mention} menjadi lebih kuat!\n(+`{func[1]}` Agility)')
                else:
                    await self.ctx.channel.send(f'{user1["name"]} menjadi lebih kuat!\n(+`{func[1]}` Agility)')

    async def ai_choose_skill(self, skill_set:list, ai, player):
        skill = random.choice(skill_set)
        skill_func = skill['func'].upper()
        await self.ctx.channel.send(f"{self.user2['name']} menggunakan skill:\n## {skill['name']}!")
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
                res_1 = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and r.content.startswith('Opsi terpilih: '), timeout = 25.0) # Detect a message from RVDiA

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
                    await self.use(self.user1)
                    try:
                        res_use:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and " menggunakan " in r.content, timeout = 10)
                        func = res_use.content.split('\n')[1] # Dear god hope this works
                        await self.func_converter(func, self.user1, self.user2)
                    except asyncio.TimeoutError:
                        await self.ctx.channel.send(f"{self.user1.mention}, giliranmu diskip karena tidak menggunakan item!")

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
                            embed.set_thumbnail(url = self.user2['avatar'])
                        except:
                            pass

                    await self.ctx.channel.send(embed = embed)

                case "Opsi terpilih: 🏃Kabur":
                    await self.ctx.channel.send(f'⛔ <@{self.user1.id}>  mengakhiri perang.')
                    return

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
                        await self.use(self.user2)
                        try:
                            res_use:discord.Message = await self.bot.wait_for('message', check = lambda r: r.author == self.bot.user and r.channel == self.ctx.channel and " menggunakan " in r.content, timeout = 10)
                            func = res_use.content.split('\n')[1] # Dear god hope this works
                            await self.func_converter(func, self.user2, self.user1)
                        except asyncio.TimeoutError:
                            await self.ctx.channel.send(f"{self.user2.mention}, giliranmu diskip karena tidak menggunakan item!")

                    case "Opsi terpilih: 🏃Kabur":
                        await self.ctx.channel.send(f'⛔ <@{self.user2.id}>  mengakhiri perang.')
                        return

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
                            embed.set_thumbnail(url = self.user2['avatar'])
                        except:
                            pass
                        await self.ctx.channel.send(embed=embed)

                    case "defend":
                        self.defend(self.user2)
                        embed = discord.Embed(title=f'🛡️{self.user2["name"]} Melindungi Diri!', color=0xff0000)
                        embed.description = f"**Defense bertambah untuk serangan selanjutnya!**"
                        try:
                            embed.set_thumbnail(url = self.user2['avatar'])
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
                            embed.set_thumbnail(url = self.user2['avatar'])
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
                embed = discord.Embed(title=f"Kamu Kalah!", color=0xff0000)
                embed.description = f"{self.user2['name']} menang dengan `{self.user2_hp}` HP tersisa!"
                embed.set_footer(text='Tip: Gunakan item dan skill spesial yang kamu miliki!')
                try:
                    embed.set_thumbnail(url = self.user2['avatar'])
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
    # TO DO: HANDLE SPELLS & ITEMS
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
                if self.ai_skill_usage >= 3:
                    self.actions.remove("skill")
                    self.traits.remove(self.skill_mood)

            case "HIGH":
                self.escape_mood = 5
                if self.ai_skill_usage >= 2:
                    self.actions.remove("skill")
                    self.traits.remove(self.skill_mood)

            case "SUPER NORMAL":
                if self.ai_skill_usage >= 3:
                    self.actions.remove("skill")
                    self.traits.remove(self.skill_mood)

            case "NORMAL":
                if self.ai_skill_usage >= 2:
                    self.actions.remove("skill")
                    self.traits.remove(self.skill_mood)

            case "SUPER LOW":
                if self.ai_skill_usage >= 2:
                    self.actions.remove("skill")
                    self.traits.remove(self.skill_mood)

            case "LOW":
                if self.ai_skill_usage >= 1:
                    self.actions.remove("skill")
                    self.traits.remove(self.skill_mood)

        sorted_traits = sorted(self.traits, reverse=True)
        if random.randint(0, 100) < 20:
            action = random.choice(self.actions)
        else:
            action = random.choice([action for trait, action in zip(self.traits, self.actions) if trait == sorted_traits[0]])

        return action
    
class ItemDropdown(discord.ui.Select):
    def __init__(self, items:list, user1) -> None:
        self.user1 = user1
        self.items = items
        options = []
        for index, item in enumerate(items):
            index += 1
            if '0-' in item['_id'] and item['usefor'] == 'battle' and not item['owned'] <= 0:
                options.append(discord.SelectOption(
                    label=f"{index}. {item['name']}",
                    value=item['_id'],
                    description=f"{item['desc']} ({item['func'].upper()})"
                ))
        if options == [] or options == None:
            options.append(discord.SelectOption(
                    label=f"Tidak ada item!",
                    value="none",
                    description=f"Kamu harus membelinya dulu di /game shop!"
                )
            )
        super().__init__(custom_id="itemdrop", placeholder='Pilih item yang ingin kamu pakai!', min_values=1, max_values=1, options=options)

    async def callback(self, interaction:discord.Interaction):
        if interaction.message.mentions[0].id != interaction.user.id:
            return await interaction.response.send_message(f"Hey! Kamu tidak diizinkan untuk memilih!", ephemeral=True) #Does this even work
        if self.values[0] == 'none':
            return await interaction.response.send_message("Kamu tidak memiliki item apapun!", ephemeral=True)
        database = connectdb('Game')
        data = database.find_one({'_id':self.user1.id})
        db_items = data['items']
        used_item = None
        if db_items == self.items:
            for item in self.items:
                if item['_id'] == self.values[0] and not item['owned'] <= 0:
                    database.find_one_and_update(
                        {'_id':self.user1.id, 'items._id':self.values[0]},
                        {'$inc':{'items.$.owned':-1}}
                        )
                    used_item = [item['name'], item['func']]
                    break

        if used_item is None:
            raise Exception("The Item Dropdown callback is behaving wierdly!")
        await interaction.response.send_message(f"{interaction.user.mention} menggunakan {used_item[0]}\n({used_item[1].upper()})")


class ItemView(View):
    def __init__(self, items:list, user1):
        super().__init__(timeout=20)
        self.add_item(ItemDropdown(items, user1))
    
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

    @button(label='Hapus Akun', style=discord.ButtonStyle.danger, custom_id='delacc')
    async def delete_account(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Kamu tidak diperbolehkan berinteraksi dengan tombol ini!", ephemeral=True)
            return
        database = connectdb('Game')
        data = database.find_one({'_id':interaction.user.id})
        database.find_one_and_delete({'_id':interaction.user.id})
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
    TO DO: TREAT BUYING ITEMS DIFFERENT FROM EQUIPMENTS
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
        database = connectdb('Game')
        data = database.find_one({'_id':interaction.user.id})
        db_dict = {item['_id']: item for item in items}
        mongo_dict = {item['_id']: item for item in data['items']}

        matched_dict = db_dict[item_id]
        current_money = data['coins'] if matched_dict['paywith'] == "Koin" else data['karma']
        if current_money < matched_dict['cost']:
            return await interaction.response.send_message(f"Waduh!\n{matched_dict['paywith']}mu tidak cukup untuk membeli barang ini!")

        if item_id in db_dict and item_id in mongo_dict: # User already bought this item in the past

            filter_ = {'_id': interaction.user.id, 'items._id': item_id}
            update_ = {'$inc': {'items.$.owned': 1}}
            database.update_one(filter=filter_, update=update_)

            currency = 'coins' if matched_dict['paywith'] == "Koin" else 'karma'
            cost = matched_dict['cost']
            update_ = {'$inc': {currency: cost*-1}}
            database.update_one(filter=filter_, update=update_)

            await interaction.response.send_message(f"Pembelian berhasil!\nKamu telah membeli `{matched_dict['name']}`", ephemeral=True)

        else:
            currency = 'coins' if matched_dict['paywith'] == "Koin" else 'karma'
            cost = matched_dict['cost']
            del matched_dict['cost']
            del matched_dict['paywith']
            matched_dict['owned'] = 1
            database.update_one({'_id': interaction.user.id},
                                {'$push':{'items':matched_dict}})
            
            database.update_one({'_id': interaction.user.id}, {'$inc':{currency: cost*-1}}) # Second update, avoiding conflict

            await interaction.response.send_message(f"Pembelian berhasil!\nKamu telah membeli `{matched_dict['name']}`", ephemeral=True)

class EnemyDropdown(discord.ui.Select):
    def __init__(self):
        options = []
        json_files = [file for file in listdir('./src/game/enemies') if file.endswith('.json')]
        json_files.remove('low.json')
        for file in json_files:
            name = path.splitext(file)[0]
            options.append(discord.SelectOption(
                label=name.title(),
                value=name
            ))
        # Too much kelazzz, the jsons are stored alphabetically
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
        super().__init__(timeout=30)
        self.add_item(EnemyDropdown())
        
class ShopView(View):
    """
    Currently not up to write DRY code
    """
    def __init__(self, ctx, items, data):
        self.current_page = 1
        super().__init__(timeout=20)
        self.ctx = ctx
        self.items = items
        self.data = data
        self.owned = []
        self.add_item(ShopDropdown(self.current_page))
        
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

class Game(commands.GroupCog, group_name = 'game'):
    """
    Kumpulan command game RPG RVDIA (Re:Volution).
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(aliases=['reg'], description='Daftarkan akunmu ke Re:Volution!')
    @app_commands.describe(name='Nama apa yang ingin kamu pakai di dalam gamenya?')
    @check_blacklist()
    async def register(self, ctx:commands.Context, *, name:str=None):
        """
        Daftarkan akunmu ke Re:Volution!
        """
        name=name or ctx.author.name
        database = connectdb('Game')
        data = database.find_one({'_id':ctx.author.id})
        if data: return await ctx.reply('Kamu sudah memiliki akun game!')
        database.insert_one({
            '_id':ctx.author.id,
            'name':name,
            'level':1,
            'exp':0,
            'next_exp':50,
            'last_login':datetime.datetime.now(),
            'coins':100,
            'karma':10,             # Luck points
            'attack':10,
            'defense':7,
            'agility':8,
            'special_skills':[],    # Push JSON to here
            'items':[],
            'equipments':[]         # Push it to here also
        })
        await ctx.reply(f'Akunmu sudah didaftarkan!\nSelamat datang di Re:Volution, **`{name}`**!')
        await asyncio.sleep(0.7)
        await self.account(ctx)
    
    @commands.hybrid_command(description='Menghapuskan akunmu dari Re:Volution.')
    @has_registered()
    @check_blacklist()
    async def resign(self, ctx:commands.Context):
        """
        Menghapuskan akunmu dari Re:Volution.
        """
        view = ResignButton(ctx)
        await ctx.reply('Apakah kamu yakin akan menghapus akunmu?\nKamu punya 20 detik untuk menentukan keputusanmu.', view=view)
        await view.wait()
        if view.value is None:
            await ctx.channel.send('Waktu habis, penghapusan akun dibatalkan.')

    @commands.hybrid_command(aliases=['login'], description='Dapatkan bonus login harian!')
    @has_registered()
    @check_blacklist()
    async def daily(self, ctx:commands.Context):
        """
        Dapatkan bonus login harian!
        """
        database = connectdb('Game')
        data = database.find_one({'_id':ctx.author.id})
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
            database.find_one_and_update(
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

            if level_up(ctx):
                return await send_level_up_msg(ctx)
            
    @commands.hybrid_command(description='Lihat profil pengguna di Re:Volution!')
    @app_commands.describe(user='Pengguna mana yang ingin dilihat akunnya?')
    @app_commands.rename(user='pengguna')
    @has_registered()
    @check_blacklist()
    async def account(self, ctx:commands.Context, *, user:discord.User=None):
        """
        Lihat profil pengguna di Re:Volution!
        """
        # Plans: PIL profile pic, equipment & items should be seperate commands
        user = user or ctx.author
        database = connectdb('Game')
        data = database.find_one({'_id':user.id})

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
        special_skills = data['special_skills']

        embed = discord.Embed(title=player_name, timestamp=last_login, color=ctx.author.color)
        embed.set_author(name='Info Akun Re:Volution:')
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
            name='Skill Spesial',
            value=', '.join(special_skills) if not special_skills == [] else "Belum ada dikuasai.",
            inline=False
        )
        
        embed.set_footer(text='Login harian terakhir ')
        await ctx.reply(embed = embed)

    @commands.hybrid_command(description="Beli item atau perlengkapan perang!")
    @has_registered()
    @check_blacklist()
    async def shop(self, ctx:commands.Context):
        """
        Beli item atau perlengkapan perang!
        """
        # Plans: show details and make a paginator or something
        database = connectdb('Game')
        data = database.find_one({'_id':ctx.author.id})
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

    @commands.hybrid_command(description='Tantang seseorang ke sebuah duel!')
    @app_commands.describe(member='Siapa yang ingin kamu lawan?')
    @app_commands.rename(member='pengguna')
    @has_registered()
    @check_blacklist()
    async def fight(self, ctx:commands.Context, *, member:discord.Member):
        """
        Tantang seseorang ke sebuah duel!
        """
        if member.bot:
            return await ctx.reply('Bot tidak bisa melakukan perlawanan!', ephemeral=True)
        game = GameInstance(ctx, ctx.author, member, self.bot)
        await game.start()


    @commands.hybrid_command(description='Lawan musuh-musuh yang ada di Re:Volution!')
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
    @check_blacklist()
    async def battle(self, ctx:commands.Context, enemy_tier:app_commands.Choice[str], enemy_name:str=None): # Choice[value_type]
        """
        Lawan musuh-musuh yang ada di Re:Volution!
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


    @commands.hybrid_command(description='Lihat daftar musuh yang muncul di Re:Volution!', aliases=['enemy'])
    @has_registered()
    @check_blacklist()
    async def enemies(self, ctx:commands.Context):
        """
        Lihat daftar musuh yang muncul di Re:Volution!
        """
        view = EnemyView()
        async with ctx.typing():
            await ctx.reply(f"Untuk melihat daftar musuh, silahkan tekan di bawah ini ↓", view=view)


    @commands.hybrid_command(description='Request untuk pemindahan data akun.')
    @app_commands.describe(old_acc = "Akun Discord lamamu atau ID akun Discord lamamu.")
    @app_commands.describe(reason = "Alasan request pemindahan data akun.")
    @app_commands.rename(reason = "alasan")
    @app_commands.rename(old_acc = "akun_lama")
    @has_registered()
    @check_blacklist()
    async def transfer(self, ctx:commands.Context, old_acc:discord.User, *, reason:str):
        """
        Request untuk pemindahan data akun.
        """
        database = connectdb('Game')
        current_acc_data = database.find_one({'_id':ctx.author.id})
        old_acc_data = database.find_one({'_id':old_acc.id})
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


    @commands.hybrid_command(description='Ayo main tebak angka bersamaku!')
    @app_commands.describe(level='Tingkat kesulitan mana yang akan kamu pilih?')
    @app_commands.choices(level=[
        app_commands.Choice(name='SUPER', value='SUPER'),
        app_commands.Choice(name='HARD', value='HARD'),
        app_commands.Choice(name="NORMAL", value='NORMAL'),
        app_commands.Choice(name='EASY', value='EASY')
    ])
    @has_registered()
    @check_blacklist()
    async def guess(self, ctx:commands.Context, level:app_commands.Choice[str]):
        """
        Ayo main tebak angka bersamaku!
        """
        game_instance = GuessGame(ctx, level.value)
        await game_instance.start()

async def setup(bot):
    await bot.add_cog(Game(bot))