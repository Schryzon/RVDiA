import asyncio
import re
import os
import discord
import random
import json
import time
from datetime import datetime, timedelta, timezone
from prisma import Json
from discord.ui import View, Button, button
from scripts.main import db, check_vote
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

PREDEFINED_TITLES = {
    "novice_adventurer": {
        "en": "Novice Adventurer",
        "id": "Petualang Pemula",
        "style": "default",
        "color": (150, 200, 255, 255),
        "bg_color": (150, 200, 255, 30),
        "border_color": (150, 200, 255, 100)
    },
    "true_dreamer": {
        "en": "The True Dreamer",
        "id": "Sang Pemimpi Sejati",
        "style": "rainbow",
        "color": (255, 255, 255, 255),
        "bg_color": (255, 255, 255, 20),
        "border_color": (255, 255, 255, 100)
    },
    "undying_survivor": {
        "en": "Undying Survivor",
        "id": "Penyintas Abadi",
        "style": "bloody_red",
        "color": (255, 50, 50, 255),
        "bg_color": (139, 0, 0, 50),
        "border_color": (139, 0, 0, 200)
    },
    "titan_slayer": {
        "en": "Titan Slayer",
        "id": "Pembantai Titan",
        "style": "gold_shiny",
        "color": (255, 215, 0, 255),
        "bg_color": (255, 215, 0, 30),
        "border_color": (255, 215, 0, 180)
    },
    "bonus_hunter": {
        "en": "Bonus Hunter",
        "id": "Pemburu Bonus",
        "style": "violet",
        "color": (155, 89, 182, 255),
        "bg_color": (155, 89, 182, 30),
        "border_color": (155, 89, 182, 180)
    },
    "rvdias_favorite": {
        "en": "RVDiA's Favorite",
        "id": "Kesayangan RVDiA",
        "style": "pink",
        "color": (255, 105, 180, 255),
        "bg_color": (255, 105, 180, 30),
        "border_color": (255, 105, 180, 180)
    },
    "class_master": {
        "en": "Class Master",
        "id": "Master Kelas",
        "style": "green",
        "color": (46, 204, 113, 255),
        "bg_color": (46, 204, 113, 30),
        "border_color": (46, 204, 113, 180)
    },
    "wealthy_merchant": {
        "en": "Wealthy Merchant",
        "id": "Saudagar Kaya",
        "style": "emerald",
        "color": (26, 188, 156, 255),
        "bg_color": (26, 188, 156, 30),
        "border_color": (26, 188, 156, 180)
    },
    "karma_saint": {
        "en": "Saint of Light",
        "id": "Orang Suci Cahaya",
        "style": "white",
        "color": (240, 240, 245, 255),
        "bg_color": (240, 240, 245, 30),
        "border_color": (240, 240, 245, 200)
    },
    "karma_bringer": {
        "en": "Chaos Bringer",
        "id": "Pembawa Kekacauan",
        "style": "dark_purple",
        "color": (100, 30, 150, 255),
        "bg_color": (50, 10, 80, 50),
        "border_color": (100, 30, 150, 200)
    },
    "godlike_ascendant": {
        "en": "Godlike Ascendant",
        "id": "Pewaris Dewata",
        "style": "glowing_gold",
        "color": (255, 255, 255, 255),
        "bg_color": (255, 215, 0, 40),
        "border_color": (255, 215, 0, 255)
    }
}

async def check_and_unlock_title(ctx, user_id: int, title_id: str, bot) -> bool:
    user_record = await db.user.find_unique(where={'id': user_id})
    if not user_record:
        return False
    data = user_record.data
    titles = data.get('titles', ['novice_adventurer'])
    if title_id in titles:
        return False
        
    titles.append(title_id)
    data['titles'] = titles
    
    await db.user.update(
        where={'id': user_id},
        data={'data': Json(data)}
    )
    
    lang = await get_user_lang(user_id)
    title_info = PREDEFINED_TITLES.get(title_id, {})
    title_name = title_info.get(lang, title_info.get("en", title_id))
    
    mention_str = ctx.author.mention if hasattr(ctx, 'author') else f'<@{user_id}>'
    is_tg = type(ctx).__name__ == "TelegramMockCtx"
    b_start = "<b>" if is_tg else "**"
    b_end = "</b>" if is_tg else "**"
    
    msg = (
        f"🏆 {b_start}New Title Unlocked!{b_end}\n"
        f"Congratulations, {mention_str}! You have unlocked the title: {b_start}\"{title_name}\"{b_end}!"
    ) if lang == "en" else (
        f"🏆 {b_start}Gelar Baru Terbuka!{b_end}\n"
        f"Selamat, {mention_str}! Kamu telah membuka gelar: {b_start}\"{title_name}\"{b_end}!"
    )
    
    if hasattr(ctx, 'reply'):
        await ctx.reply(msg)
    elif hasattr(ctx, 'channel'):
        await ctx.channel.send(msg)
    elif hasattr(ctx, 'send'):
        await ctx.send(msg)
    return True

def to_key(name: str) -> str:
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s_]', '', name)
    name = re.sub(r'[\s_]+', '_', name)
    return name

class ResignButton(View):
    def __init__(self, ctx, lang="en"):
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
        
        if user_record.guild and user_record.guild.ownerId == interaction.user.id:
            guild = user_record.guild
            members = await db.user.find_many(where={
                'guildId': guild.id,
                'NOT': {'id': interaction.user.id}
            })
            
            if members:
                new_owner = sorted(members, key=lambda u: (u.data.get('level', 1), u.data.get('karma', 0)), reverse=True)[0]
                new_owner_name = new_owner.data.get('name', 'Seseorang')
                await db.guild.update(
                    where={'id': guild.id},
                    data={'ownerId': new_owner.id}
                )
                msg = i18n.get(self.lang, "game.resign_guild_transfer", name=name, guild=guild.name, new_owner=new_owner_name)
                await interaction.channel.send(msg)
            else:
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
    def __init__(self, page: int, lang="en"):
        self.page = page
        self.lang = lang

        with open('./src/game/shop.json', 'r', encoding='utf-8') as file:
            items = json.load(file)

        options = []
        start_index = (self.page - 1) * 5
        end_index = self.page * 5
        for index, item in enumerate(items[start_index:end_index]):
            item_name = i18n.get(self.lang, f"game.item_{item['_id']}_name", default=item['name'])
            currency = i18n.get(self.lang, "game.paywith_koin") if item['paywith'] == "Koin" else i18n.get(self.lang, "game.paywith_karma")
            desc_text = f"Harga: {item['cost']} {currency}" if self.lang == "id" else f"Price: {item['cost']} {currency}"
            
            options.append(discord.SelectOption(
                label=f"{index + start_index + 1}. {item_name}", 
                description=desc_text, 
                value=item['_id']
            ))

        placeholder_text = i18n.get(self.lang, "game.shop_select_item")
        super().__init__(custom_id="shopdrop", placeholder=placeholder_text, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        with open('./src/game/shop.json', 'r', encoding='utf-8') as file:
            items = json.load(file)

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
            msg = f"Oops!\nYour {paywith_name.lower()} are not enough to buy this item!" if self.lang == "en" else f"Waduh!\n{paywith_name}mu tidak cukup untuk membeli barang ini!"
            return await interaction.response.send_message(msg, ephemeral=True)

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

        data[currency_key] -= matched_item['cost']
        
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

class ShopView(View):
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
        embed.set_thumbnail(url=os.getenv('xaneria'))

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
            item_desc = i18n.get(self.lang, f"game.item_{item['_id']}_desc", default=item.get('desc', ''))
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

    @button(label='◀', custom_id='back', style=discord.ButtonStyle.blurple)
    async def back(self, interaction: discord.Interaction, button: Button):
        max_page = (len(self.items) - 1) // 5 + 1
        last_page = self.current_page
        self.current_page = self.current_page - 1 if self.current_page > 1 else max_page
        embed = await self.update_embed(last_page)
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label='✖', style=discord.ButtonStyle.danger, custom_id='delete')
    async def _delete(self, interaction: discord.Interaction, button: Button):
        await interaction.message.delete()

    @button(label='▶', custom_id='next', style=discord.ButtonStyle.blurple)
    async def next(self, interaction: discord.Interaction, button: Button):
        max_page = (len(self.items) - 1) // 5 + 1
        last_page = self.current_page
        self.current_page = self.current_page + 1 if self.current_page < max_page else 1
        embed = await self.update_embed(last_page)
        await interaction.response.edit_message(embed=embed, view=self)

class UseDropdown(discord.ui.Select):
    def __init__(self, items: list, ctx, lang="en") -> None:
        self.lang = lang
        options = []
        for index, item in enumerate(items, start=1):
            item_name = i18n.get(self.lang, f"game.item_{item['_id']}_name", default=item['name'])
            options.append(discord.SelectOption(
                label=f"{index}. {item_name} ({item['usefor']})" if not item['usefor'] == 'free' else f"{index}. {item_name}",
                description=f"{item['func'].upper()}",
                value=item['_id']
            ))
        if not options:
            options.append(discord.SelectOption(
                label=i18n.get(self.lang, "game.use_no_items"),
                value="none",
                description=i18n.get(self.lang, "game.use_no_items_shop")
            ))
        placeholder_text = i18n.get(self.lang, "game.use_placeholder")
        super().__init__(custom_id="usedrop", placeholder=placeholder_text, min_values=1, max_values=1, options=options)
        self.items = items
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
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
        
        if '1-' in item_id:
            equipments = inventory.equipments if isinstance(inventory.equipments, list) else []
            matching = [x for x in equipments if x['_id'] == item_id]
            
            if matching:
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
            
            else:
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
            all_items = inventory.items if isinstance(inventory.items, list) else []
            item_match = [x for x in all_items if x['_id'] == item_id]
            if not item_match:
                msg = i18n.get(self.lang, "game.use_not_found")
                return await interaction.response.send_message(msg, ephemeral=True)
            
            item_to_use = item_match[0]
            item_name = i18n.get(self.lang, f"game.item_{item_to_use['_id']}_name", default=item_to_use['name'])
            msg = i18n.get(self.lang, "game.use_equip_success", name=item_name)
            await interaction.response.send_message(msg)
            
            from scripts.game.fight import GameInstance
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
    def __init__(self, items: list, ctx, lang="en"):
        super().__init__(timeout=30)
        self.add_item(UseDropdown(items, ctx, lang=lang))

class TitlesDropdown(discord.ui.Select):
    def __init__(self, unlocked_titles: list, active_title: str, lang="en"):
        self.lang = lang
        options = []
        for t_id in unlocked_titles:
            title_info = PREDEFINED_TITLES.get(t_id)
            if not title_info:
                continue
            name = title_info.get(lang, title_info.get("en", t_id))
            style = title_info.get("style", "default")
            is_active = (t_id == active_title)
            
            label_suffix = " (Equipped)" if is_active else ""
            options.append(discord.SelectOption(
                label=f"{name}{label_suffix}",
                value=t_id,
                description=f"Style: {style}",
                default=is_active
            ))
            
        placeholder_text = "Choose a title to equip..." if lang == "en" else "Pilih gelar untuk dipasang..."
        super().__init__(custom_id="titlesdrop", placeholder=placeholder_text, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.message.mentions or interaction.message.mentions[0] != interaction.user:
            msg = "Not your menu!" if self.lang == "en" else "Bukan menumu!"
            return await interaction.response.send_message(msg, ephemeral=True)
            
        selected_title = self.values[0]
        user_record = await db.user.find_unique(where={'id': interaction.user.id})
        if not user_record:
            msg = i18n.get(self.lang, "game.profile_not_registered")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        data = user_record.data
        unlocked_titles = data.get('titles', ['novice_adventurer'])
        
        if selected_title not in unlocked_titles:
            msg = "You haven't unlocked this title yet!" if self.lang == "en" else "Kamu belum membuka gelar ini!"
            return await interaction.response.send_message(msg, ephemeral=True)
            
        data['active_title'] = selected_title
        await db.user.update(
            where={'id': interaction.user.id},
            data={'data': Json(data)}
        )
        
        title_info = PREDEFINED_TITLES.get(selected_title, {})
        title_name = title_info.get(self.lang, title_info.get("en", selected_title))
        
        msg = f"Title **\"{title_name}\"** equipped successfully!" if self.lang == "en" else f"Gelar **\"{title_name}\"** berhasil dipasang!"
        await interaction.response.send_message(msg)
        
        # Disable dropdown after selection
        self.disabled = True
        await interaction.message.edit(view=self.view)

class TitlesView(View):
    def __init__(self, unlocked_titles: list, active_title: str, lang="en"):
        super().__init__(timeout=30)
        self.add_item(TitlesDropdown(unlocked_titles, active_title, lang=lang))

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
        
        embed = discord.Embed(title=self.title, color=0xffd700)
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
                embed.add_field(name=f"{i}. {name}", value=field_val, inline=False)
            else:
                name = item.name
                member_count = len(item.members) if hasattr(item, 'members') else 0
                field_val = i18n.get(self.lang, "game.leaderboard_guild_field", count=member_count, owner=item.ownerId)
                embed.add_field(name=f"{i}. {name}", value=field_val, inline=False)
        
        page_lbl = "Halaman" if self.lang == "id" else "Page"
        embed.set_footer(text=f"{page_lbl} {self.current_page + 1}/{self.max_pages}")
        return embed

    @button(label='◀', style=discord.ButtonStyle.blurple)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = "Bukan tombolmu, Sang Pemimpi!" if self.lang == "id" else "Not your button, Dreamer!"
            return await interaction.response.send_message(msg, ephemeral=True)
        self.current_page = (self.current_page - 1) % self.max_pages
        await interaction.response.edit_message(embed=await self.get_embed())

    @button(label='✖', style=discord.ButtonStyle.danger)
    async def destroy(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = "Hanya yang memanggil ini yang bisa menutupnya!" if self.lang == "id" else "Only the caller can close this!"
            return await interaction.response.send_message(msg, ephemeral=True)
        await interaction.message.delete()

    @button(label='▶', style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            msg = "Bukan tombolmu, Sang Pemimpi!" if self.lang == "id" else "Not your button, Dreamer!"
            return await interaction.response.send_message(msg, ephemeral=True)
        self.current_page = (self.current_page + 1) % self.max_pages
        await interaction.response.edit_message(embed=await self.get_embed())

# ── Command Executors ────────────────────────────────────────

async def execute_register(ctx, name=None):
    name = name or ctx.author.name
    lang = await get_user_lang(ctx.author.id)
    user_data = await db.user.find_unique(where={'id': ctx.author.id})
    if user_data:
        msg = i18n.get(lang, "game.register_already")
        return await ctx.reply(msg)
        
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
    await execute_profile(ctx, ctx.bot)

async def execute_leaderboard(ctx):
    lang = await get_user_lang(ctx.author.id)
    users = await db.user.find_many()
    if not users:
        msg = i18n.get(lang, "game.leaderboard_empty")
        return await ctx.reply(msg)
        
    sorted_users = sorted(users, key=lambda u: (u.data.get('level', 1), u.data.get('karma', 0)), reverse=True)
    top_100 = sorted_users[:100]
    
    title = i18n.get(lang, "game.leaderboard_title")
    view = LeaderboardView(ctx, top_100, title, type="player", lang=lang)
    embed = await view.get_embed()
    await ctx.reply(embed=embed, view=view)

async def execute_guide(ctx, bot):
    lang = await get_user_lang(ctx.author.id)
    title = i18n.get(lang, "game.guide_title")
    desc = i18n.get(lang, "game.guide_desc")
    footer = i18n.get(lang, "game.guide_footer")
    
    embed = discord.Embed(title=title, color=0x86273d)
    embed.description = desc
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text=footer)
    await ctx.reply(embed=embed)

async def execute_changelog(ctx, bot):
    lang = await get_user_lang(ctx.author.id)
    title = i18n.get(lang, "game.changelog_title")
    desc = i18n.get(lang, "game.changelog_desc")
    footer = i18n.get(lang, "game.changelog_footer")
    
    embed = discord.Embed(title=title, color=0x86273d)
    embed.description = desc
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text=footer)
    await ctx.reply(embed=embed)

async def execute_resign(ctx):
    lang = await get_user_lang(ctx.author.id)
    view = ResignButton(ctx, lang=lang)
    prompt = i18n.get(lang, "game.resign_prompt")
    await ctx.reply(prompt, view=view)
    await view.wait()
    if view.value is None:
        timeout_msg = i18n.get(lang, "game.resign_timeout")
        await ctx.channel.send(timeout_msg)

async def execute_daily(ctx, bot):
    user_record = await db.user.find_unique(where={'id': ctx.author.id})
    data = user_record.data
    
    last_login_raw = data.get('last_login')
    if not last_login_raw:
        streak = 1
    else:
        if isinstance(last_login_raw, str):
            last_login = datetime.fromisoformat(last_login_raw)
        else:
            last_login = last_login_raw
            
        current_time = datetime.now()
        delta_time = current_time - last_login
        
        lang = await get_user_lang(ctx.author.id)
        if delta_time.total_seconds() <= 24*60*60:
            next_login = last_login + timedelta(hours=24)
            next_login_unix = int(time.mktime(next_login.timetuple()))
            msg = i18n.get(lang, "game.daily_already", timestamp=next_login_unix)
            return await ctx.reply(msg)
        elif delta_time.total_seconds() <= 48*60*60:
            streak = data.get('daily_streak', 1) + 1
        else:
            streak = 1

    lang = await get_user_lang(ctx.author.id)
    current_time = datetime.now()
    next_login = current_time + timedelta(hours=24)
    
    base_coins = random.randint(15, 25)
    base_karma = random.randint(1, 5)
    base_exp = random.randint(10, 20)
    
    streak_bonus = min(streak, 5) * 0.1
    multiplier = 1.0 + streak_bonus
    
    # check top.gg vote status
    voted = await check_vote(ctx.author.id, bot.user.id)
    vote_multiplier = 2 if voted else 1
    
    final_coins = int(base_coins * multiplier * vote_multiplier)
    final_karma = int(base_karma * multiplier * vote_multiplier)
    final_exp = int(base_exp * multiplier * vote_multiplier)
    
    data['coins'] += final_coins
    data['karma'] += final_karma
    data['exp'] += final_exp
    data['daily_streak'] = streak
    data['last_login'] = current_time.isoformat()
    
    await db.user.update(
        where={'id': ctx.author.id},
        data={'data': Json(data)}
    )
    
    title = i18n.get(lang, "game.daily_success_title")
    footer_text = i18n.get(lang, "game.daily_footer")
    
    embed = discord.Embed(title=title, color=0x00FF00, timestamp=next_login)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    
    # multiplier status field
    multipliers_title = i18n.get(lang, "game.daily_multipliers_title", default="Multiplier Status")
    streak_bonus_pct = int(streak_bonus * 100)
    streak_info = i18n.get(lang, "game.daily_streak_info", streak=streak, bonus=streak_bonus_pct)
    info_value = f"{streak_info}"
    if voted:
        vote_info = i18n.get(lang, "game.daily_vote_info")
        info_value += f"\n{vote_info}"
    embed.add_field(name=multipliers_title, value=info_value, inline=False)
    
    reward_title = i18n.get(lang, "game.combat_reward_title")
    coins_lbl = i18n.get(lang, "game.paywith_koin") if lang == "en" else "Koin"
    reward_coins = f"{bot.coin_emoji_anim} `{final_coins}` {coins_lbl}"
    reward_karma = i18n.get(lang, "game.combat_reward_karma", amount=final_karma)
    reward_exp = i18n.get(lang, "game.combat_reward_exp", amount=final_exp)
    
    embed.add_field(name=reward_title, value=f"{reward_coins}\n{reward_karma}\n{reward_exp}!", inline=False)
    embed.set_footer(text=footer_text)
    await ctx.reply(embed=embed)
    level_uped = await level_up(ctx)
    if level_uped:
        return await send_level_up_msg(ctx)

async def check_passive_titles(ctx, user_id: int, data: dict, bot) -> bool:
    unlocked_any = False
    
    # 1. class_master: reach Level 50+
    if data.get('level', 1) >= 50:
        if await check_and_unlock_title(ctx, user_id, "class_master", bot):
            unlocked_any = True
            
    # 2. wealthy_merchant: accumulate 10,000+ coins
    if data.get('coins', 0) >= 10000:
        if await check_and_unlock_title(ctx, user_id, "wealthy_merchant", bot):
            unlocked_any = True
            
    # 3. karma_saint: accumulate +100+ karma
    if data.get('karma', 0) >= 100:
        if await check_and_unlock_title(ctx, user_id, "karma_saint", bot):
            unlocked_any = True
            
    # 4. karma_bringer: accumulate -100 or less karma
    if data.get('karma', 0) <= -100:
        if await check_and_unlock_title(ctx, user_id, "karma_bringer", bot):
            unlocked_any = True
            
    # 5. godlike_ascendant: ATK + DEF + AGL >= 300
    total_stats = data.get('attack', 0) + data.get('defense', 0) + data.get('agility', 0)
    if total_stats >= 300:
        if await check_and_unlock_title(ctx, user_id, "godlike_ascendant", bot):
            unlocked_any = True
            
    return unlocked_any

async def execute_profile(ctx, bot, user=None):
    lang = await get_user_lang(ctx.author.id)
    target = user or ctx.author
    user_record = await db.user.find_unique(where={'id': target.id})
    
    if not user_record:
        msg = i18n.get(lang, "game.profile_not_registered")
        return await ctx.reply(msg)
    
    try:
        await ctx.defer()
    except Exception:
        pass
        
    # Check passive titles for target player
    unlocked = await check_passive_titles(ctx, target.id, user_record.data, bot)
    if unlocked:
        user_record = await db.user.find_unique(where={'id': target.id})
        
    from scripts.image.card_generator import generate_profile_card
    premium_time = user_record.premiumUntil
    if premium_time and premium_time.tzinfo is None:
        premium_time = premium_time.replace(tzinfo=timezone.utc)
    is_p = bool(premium_time and premium_time > datetime.now(timezone.utc))
    card_file = await generate_profile_card(target, user_record, is_p, lang)
    await ctx.reply(file=card_file)

async def execute_fix_account(ctx):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'inventory': True})
    if not user_record:
        msg = i18n.get(lang, "game.profile_not_registered")
        return await ctx.reply(msg)
        
    data = user_record.data
    updated_data = False
    for key, value in default_data.items():
        if key not in data:
            data[key] = value
            updated_data = True
    
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
    
    if updated_data:
        await db.user.update(where={'id': ctx.author.id}, data={'data': Json(data)})
        
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

async def execute_shop(ctx):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'inventory': True})
    if not user_record:
        msg = i18n.get(lang, "game.profile_not_registered")
        return await ctx.reply(msg)
        
    data = user_record.data
    inventory = user_record.inventory
    
    with open('./src/game/shop.json', 'r', encoding='utf-8') as file:
        items = json.load(file)

    title = i18n.get(lang, "game.shop_title")
    desc = i18n.get(lang, "game.shop_desc")
    footer = i18n.get(lang, "game.shop_footer")

    embed = discord.Embed(title=title, color=0xFFFF00)
    embed.description = desc
    embed.set_footer(text=footer)
    embed.set_thumbnail(url=os.getenv('xaneria'))

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
        item_desc = i18n.get(lang, f"game.item_{item['_id']}_desc", default=item.get('desc', ''))
        item_type_label = i18n.get(lang, f"game.type_{to_key(item['type'])}")
        currency_label = i18n.get(lang, "game.paywith_koin") if item['paywith'] == "Koin" else i18n.get(lang, "game.paywith_karma")
        
        embed.add_field(
            name=f"{index}. {item_name}",
            value=f"**`{item_desc}`**\n({item['func']})\n**{type_text}:** {item_type_label}\n**{price_text}:** {item['cost']} {currency_label}\n**{owned_text}:** {owned_display}",
            inline=False
        )

    view = ShopView(ctx, items, user_record, lang=lang)
    msg_sent = await ctx.reply(embed=embed, view=view)
    view.message = msg_sent

async def execute_adventure(ctx):
    lang = await get_user_lang(ctx.author.id)
    exp_gain = random.randint(10, 25)
    coin_gain = random.randint(15, 35)
    
    await give_rewards(ctx, ctx.author, exp_gain, coin_gain)
    msg = i18n.get(lang, "game.adventure_success", exp=exp_gain, coins=coin_gain)
    await ctx.reply(msg)

async def execute_transfer(ctx, bot, old_acc, reason):
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
    embed.add_field(name=reason_lbl, value=reason, inline=False)
    embed.set_author(name=ctx.author)
    
    footer_lbl = i18n.get(lang, "game.transfer_embed_footer")
    embed.set_footer(text=footer_lbl)
    
    channel = bot.get_channel(1115422709585817710)
    if channel:
        await channel.send(embed=embed)
    
    success_msg = i18n.get(lang, "game.transfer_request_success")
    await ctx.send(success_msg)

async def execute_use(ctx, type_val):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id}, include={'inventory': True})
    if not user_record or not user_record.inventory:
        msg = i18n.get(lang, "game.use_not_registered")
        return await ctx.reply(msg, ephemeral=True)
        
    inventory = user_record.inventory
    user_items = inventory.items if isinstance(inventory.items, list) else []
    
    match type_val:
        case "item":
            things = [item for item in user_items if "0-" in item['_id'] and item.get('usefor') == "free"]
        case "equipment":
            things = [item for item in user_items if "1-" in item['_id']]
        case _:
            msg = i18n.get(lang, "game.use_invalid_option")
            return await ctx.reply(msg, ephemeral=True)
        
    view = UseView(things, ctx, lang=lang)
    await ctx.reply(f'{ctx.author.mention}', view=view)

async def execute_titles(ctx):
    lang = await get_user_lang(ctx.author.id)
    user_record = await db.user.find_unique(where={'id': ctx.author.id})
    if not user_record:
        msg = i18n.get(lang, "game.profile_not_registered")
        return await ctx.reply(msg)
        
    data = user_record.data
    
    # Check passive titles first
    unlocked_new = await check_passive_titles(ctx, ctx.author.id, data, ctx.bot)
    if unlocked_new:
        user_record = await db.user.find_unique(where={'id': ctx.author.id})
        data = user_record.data
        
    unlocked_titles = data.get('titles', ['novice_adventurer'])
    active_title = data.get('active_title', 'novice_adventurer')
    
    title_requirements = {
        "novice_adventurer": {
            "en": "Default title.",
            "id": "Gelar bawaan."
        },
        "true_dreamer": {
            "en": "Defeat Schryzon (Final Boss).",
            "id": "Kalahkan Schryzon (Final Boss)."
        },
        "undying_survivor": {
            "en": "Win a fight with 1 HP remaining, or defeat Young Xehanort.",
            "id": "Menang pertarungan dengan sisa 1 HP, atau kalahkan Young Xehanort."
        },
        "titan_slayer": {
            "en": "Defeat any FINAL BOSS.",
            "id": "Kalahkan FINAL BOSS apa saja."
        },
        "bonus_hunter": {
            "en": "Defeat any BONUS ENEMY.",
            "id": "Kalahkan BONUS ENEMY apa saja."
        },
        "rvdias_favorite": {
            "en": "Defeat RVDiA.",
            "id": "Kalahkan RVDiA."
        },
        "class_master": {
            "en": "Reach Level 50 or above.",
            "id": "Mencapai Level 50 atau lebih."
        },
        "wealthy_merchant": {
            "en": "Accumulate 10,000 or more Coins.",
            "id": "Kumpulkan 10.000 Koin atau lebih."
        },
        "karma_saint": {
            "en": "Accumulate +100 or more Karma.",
            "id": "Kumpulkan +100 Karma atau lebih."
        },
        "karma_bringer": {
            "en": "Accumulate -100 or less Karma.",
            "id": "Kumpulkan -100 Karma atau kurang."
        },
        "godlike_ascendant": {
            "en": "Accumulate total stats (ATK + DEF + AGL) of 300 or more.",
            "id": "Kumpulkan total status (ATK + DEF + AGL) 300 atau lebih."
        }
    }
    
    embed_title = "🏆 Dream Titles & Nameplates" if lang == "en" else "🏆 Gelar & Papan Nama Mimpi"
    embed_desc = (
        "Equip your earned titles to customize your profile card badge!\n\n"
        if lang == "en" else
        "Pasang gelar yang telah kamu dapatkan untuk menyesuaikan lencana kartu profilmu!\n\n"
    )
    
    embed = discord.Embed(title=embed_title, color=0x9b59b6, description=embed_desc)
    
    for t_id, t_info in PREDEFINED_TITLES.items():
        name = t_info.get(lang, t_info.get("en", t_id))
        is_unlocked = t_id in unlocked_titles
        is_active = t_id == active_title
        
        status_emoji = "🟢" if is_active else ("✅" if is_unlocked else "🔒")
        req_text = title_requirements.get(t_id, {}).get(lang, title_requirements.get(t_id, {}).get("en", ""))
        
        style = t_info.get("style", "default")
        
        field_value = (
            f"**Requirement:** {req_text}\n"
            f"**Style:** `{style}`"
        ) if lang == "en" else (
            f"**Syarat:** {req_text}\n"
            f"**Gaya:** `{style}`"
        )
        
        active_label = " [Equipped]" if is_active else ""
        embed.add_field(
            name=f"{status_emoji} {name}{active_label}",
            value=field_value,
            inline=False
        )
        
    view = TitlesView(unlocked_titles, active_title, lang=lang)
    await ctx.reply(f"{ctx.author.mention}", embed=embed, view=view)
