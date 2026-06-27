import os
import json
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select
from prisma import Json

from scripts.main import db, check_blacklist
from scripts.ai.relationship import relationship_service
from scripts.utils.i18n import i18n

class GiftDropdown(Select):
    def __init__(self, items_options, user_id, lang):
        self.user_id = user_id
        self.lang = lang
        options = []
        for it in items_options[:25]: # Max 25 select options
            options.append(discord.SelectOption(
                label=f"{it['name']} (x{it['owned']})",
                value=it['_id'],
                description=f"Type: {it.get('usefor', 'Consumable')}"
            ))
        super().__init__(
            placeholder="Pilih item untuk dihadiahkan... 🎁" if lang == "id" else "Choose an item to gift... 🎁",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            msg = "Ini bukan interaksi Anda! ❌" if self.lang == "id" else "This is not your interaction! ❌"
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer()
        item_id = self.values[0]

        # Load shop.json to check cost
        try:
            shop_path = os.path.join(os.path.dirname(__file__), "../src/game/shop.json")
            with open(shop_path, 'r', encoding='utf-8') as f:
                shop_items = json.load(f)
        except Exception:
            msg = "Gagal memproses data toko! ❌" if self.lang == "id" else "Failed to process shop data! ❌"
            return await interaction.followup.send(msg, ephemeral=True)

        matched = next((item for item in shop_items if item["_id"] == item_id), None)
        if not matched:
            msg = "Item tidak valid! ❌" if self.lang == "id" else "Invalid item! ❌"
            return await interaction.followup.send(msg, ephemeral=True)

        # Retrieve inventory
        inventory = await db.inventory.find_unique(where={'userId': self.user_id})
        if not inventory:
            msg = "Inventaris tidak ditemukan! ❌" if self.lang == "id" else "Inventory not found! ❌"
            return await interaction.followup.send(msg, ephemeral=True)

        user_items = inventory.items if isinstance(inventory.items, list) else []
        item_index = -1
        for idx, it in enumerate(user_items):
            if it.get('_id') == item_id:
                item_index = idx
                break

        if item_index == -1 or user_items[item_index].get('owned', 0) <= 0:
            msg = "Kamu tidak memiliki item ini! ❌" if self.lang == "id" else "You don't own this item! ❌"
            return await interaction.followup.send(msg, ephemeral=True)

        # Decrement quantity
        user_items[item_index]['owned'] -= 1
        if user_items[item_index]['owned'] <= 0:
            user_items.pop(item_index)

        # Save inventory
        await db.inventory.update(
            where={'userId': self.user_id},
            data={'items': Json(user_items)}
        )

        # Calculate affinity reward based on cost
        cost = matched.get('cost', 0)
        if cost <= 100:
            affinity_gain = 8
        elif cost <= 500:
            affinity_gain = 18
        else:
            affinity_gain = 35

        # If user paid with Karma, let's treat it as a valuable item
        if matched.get('paywith') == "Karma":
            affinity_gain = matched.get('cost', 0) * 2

        new_affinity, new_stage, shifted = await relationship_service.add_affinity(self.user_id, affinity_gain)

        # Cute response messages
        if self.lang == "id":
            embed_title = "🎁 Hadiah untuk RVDiA"
            embed_desc = (
                f"RVDiA tersenyum lebar saat kamu memberikan **{matched['name']}**.\n"
                f"*\"Aaaaah! Makasih banyak ya, sayangku! Aku suka banget hadiahnya!~\"*\n\n"
                f"📈 **+{affinity_gain} Affinity** (Total: `{new_affinity}/1000`)"
            )
            if shifted:
                embed_desc += f"\n\n🌸 **Hubungan meningkat!** Tingkat saat ini: **{relationship_service.get_stage_label(new_stage, 'id')}**"
        else:
            embed_title = "🎁 Gift for RVDiA"
            embed_desc = (
                f"RVDiA smiles brightly as you hand her the **{matched['name']}**.\n"
                f"*\"Aaaaah! Thank you so much, sweetie! I absolutely love this gift!~\"*\n\n"
                f"📈 **+{affinity_gain} Affinity** (Total: `{new_affinity}/1000`)"
            )
            if shifted:
                embed_desc += f"\n\n🌸 **Relationship stage upgraded!** Current Stage: **{relationship_service.get_stage_label(new_stage, 'en')}**"

        embed = discord.Embed(
            title=embed_title,
            description=embed_desc,
            color=interaction.user.color or 0x86273d
        )
        if interaction.client.user.avatar:
            embed.set_thumbnail(url=interaction.client.user.avatar.url)

        # Update message
        await interaction.message.edit(embed=embed, view=None)


class Relationship(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="bond", description="Kelola hubungan dan kedekatanmu dengan RVDiA.", fallback="info")
    @check_blacklist()
    async def bond(self, ctx: commands.Context):
        """Displays your relationship status, affinity progress bar, and active nicknames."""
        await self.execute_bond_info(ctx)

    async def execute_bond_info(self, ctx: commands.Context):
        user_id = ctx.author.id
        user_settings = await db.usersettings.find_unique(where={'userId': user_id})
        lang = user_settings.lang if user_settings else "en"

        rel = await relationship_service.get_relationship(user_id)
        if not rel:
            title = "💖 Hubungan dengan RVDiA" if lang == "id" else "💖 Bond with RVDiA"
            desc = (
                "Kamu belum memulai hubungan dengan RVDiA!\n"
                "Ketik `/bond start` untuk mulai mengobrol dekat dan menjalin ikatan dengannya! 🌸"
            ) if lang == "id" else (
                "You haven't started your bond with RVDiA yet!\n"
                "Type `/bond start` to begin chatting closely and building a bond with her! 🌸"
            )
            embed = discord.Embed(title=title, description=desc, color=0xff73a1)
            return await ctx.reply(embed=embed)

        affinity = rel.affinity
        stage = rel.stage
        stage_label = relationship_service.get_stage_label(stage, lang)
        stage_desc = relationship_service.get_stage_description(stage, lang)
        bar, threshold = relationship_service.get_progress_bar(affinity, stage)

        title = f"💝 Hubunganmu dengan RVDiA" if lang == "id" else f"💝 Your Bond with RVDiA"
        embed = discord.Embed(title=title, color=ctx.author.color or 0x86273d, timestamp=ctx.message.created_at if ctx.message else None)
        
        # Display nameplate / nicknames
        user_nick = rel.userNickname or ctx.author.display_name
        rvdia_nick = rel.rvdiaNickname or "RVDiA"

        # Construct status fields
        status_info = (
            f"**Tingkat Hubungan:** {stage_label}\n"
            f"**Affinity:** `{affinity}/{threshold}`\n"
            f"{bar}\n\n"
            f"*{stage_desc}*"
        ) if lang == "id" else (
            f"**Relationship Stage:** {stage_label}\n"
            f"**Affinity:** `{affinity}/{threshold}`\n"
            f"{bar}\n\n"
            f"*{stage_desc}*"
        )
        embed.description = status_info

        # Nickname fields
        embed.add_field(
            name="🗣️ Panggilan" if lang == "id" else "🗣️ Nicknames",
            value=(
                f"• Panggilanmu untuk dia: **{rvdia_nick}**\n"
                f"• Panggilan dia untukmu: **{user_nick}**"
            ),
            inline=False
        )

        # Anniversary field for lovers
        if stage == "lover" and rel.anniversary:
            anniv_str = rel.anniversary.strftime("%d %B %Y")
            embed.add_field(
                name="💍 Hari Jadi" if lang == "id" else "💍 Anniversary",
                value=f"Kalian resmi menjadi sepasang kekasih pada **{anniv_str}**! 💕" if lang == "id" else f"You officially became lovers on **{anniv_str}**! 💕",
                inline=False
            )

        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)

        await ctx.reply(embed=embed)

    @bond.command(name="start", description="Mulai menjalin ikatan dan hubungan dengan RVDiA.")
    @check_blacklist()
    async def start(self, ctx: commands.Context):
        user_id = ctx.author.id
        user_settings = await db.usersettings.find_unique(where={'userId': user_id})
        lang = user_settings.lang if user_settings else "en"

        existing = await relationship_service.get_relationship(user_id)
        if existing:
            msg = "Kamu sudah memulai hubungan dengan RVDiA! ❤️" if lang == "id" else "You have already started your bond with RVDiA! ❤️"
            return await ctx.reply(msg, ephemeral=True)

        success = await relationship_service.start_relationship(user_id)
        if not success:
            msg = "Gagal memulai hubungan. Silakan coba beberapa saat lagi!" if lang == "id" else "Failed to start relationship. Please try again later!"
            return await ctx.reply(msg, ephemeral=True)

        # Give small starter affinity
        await relationship_service.add_affinity(user_id, 10)

        title = "🌸 Ikatan Dimulai!" if lang == "id" else "🌸 Bond Initiated!"
        desc = (
            "Kamu telah resmi menjalin ikatan dengan RVDiA!\n"
            "Dia tersenyum manis ke arahmu.\n"
            "*\"Halo manis! Mari kita saling mengenal satu sama lain lebih dekat ya~\"* 💖"
        ) if lang == "id" else (
            "You have officially started a bond with RVDiA!\n"
            "She smiles warmly at you.\n"
            "*\"Hello cutie! Let's get to know each other much better from now on~\"* 💖"
        )
        
        embed = discord.Embed(title=title, description=desc, color=0xff73a1)
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        await ctx.reply(embed=embed)

    @bond.command(name="nickname", description="Ubah panggilan RVDiA untukmu atau panggilanmu untuknya.")
    @app_commands.describe(
        target="Siapa yang panggilannya ingin diubah?",
        nickname="Nama panggilan baru (Max 15 karakter)"
    )
    @app_commands.choices(target=[
        app_commands.Choice(name="Diriku (Panggilan RVDiA untukmu)", value="user"),
        app_commands.Choice(name="RVDiA (Panggilanmu untuk dia)", value="rvdia")
    ])
    @check_blacklist()
    async def nickname(self, ctx: commands.Context, target: app_commands.Choice[str], nickname: str):
        user_id = ctx.author.id
        user_settings = await db.usersettings.find_unique(where={'userId': user_id})
        lang = user_settings.lang if user_settings else "en"

        rel = await relationship_service.get_relationship(user_id)
        if not rel:
            msg = "Kamu harus memulai hubungan dengan `/bond start` terlebih dahulu! 🌸" if lang == "id" else "You must start your bond with `/bond start` first! 🌸"
            return await ctx.reply(msg, ephemeral=True)

        if len(nickname) > 15:
            msg = "Nama panggilan maksimal 15 karakter! ❌" if lang == "id" else "Nickname cannot exceed 15 characters! ❌"
            return await ctx.reply(msg, ephemeral=True)

        # Update in database
        update_field = 'userNickname' if target.value == "user" else 'rvdiaNickname'
        await db.relationship.update(
            where={'userId': user_id},
            data={update_field: nickname}
        )

        msg = (
            f"✅ Nama panggilan berhasil diubah! Sekarang aku akan memanggilmu **{nickname}**." 
            if target.value == "user" else 
            f"✅ Nama panggilan berhasil diubah! Panggilanmu untukku sekarang adalah **{nickname}**."
        ) if lang == "id" else (
            f"✅ Nickname updated! I will now call you **{nickname}**."
            if target.value == "user" else
            f"✅ Nickname updated! Your nickname for me is now **{nickname}**."
        )

        await ctx.reply(msg)

    @bond.command(name="gift", description="Berikan hadiah dari inventarismu kepada RVDiA untuk menaikkan affinity.")
    @check_blacklist()
    async def gift(self, ctx: commands.Context):
        user_id = ctx.author.id
        user_settings = await db.usersettings.find_unique(where={'userId': user_id})
        lang = user_settings.lang if user_settings else "en"

        rel = await relationship_service.get_relationship(user_id)
        if not rel:
            msg = "Kamu harus memulai hubungan dengan `/bond start` terlebih dahulu! 🌸" if lang == "id" else "You must start your bond with `/bond start` first! 🌸"
            return await ctx.reply(msg, ephemeral=True)

        # Retrieve inventory
        inventory = await db.inventory.find_unique(where={'userId': user_id})
        if not inventory:
            msg = "Kamu tidak memiliki item di inventarismu! Beli beberapa barang di `/game shop` dahulu! 🎒" if lang == "id" else "You don't have any items in your inventory! Buy some items in `/game shop` first! 🎒"
            return await ctx.reply(msg, ephemeral=True)

        user_items = inventory.items if isinstance(inventory.items, list) else []
        
        # Filter for Consumables with quantity > 0
        consumables = [it for it in user_items if it.get('type') == 'Consumable' and it.get('owned', 0) > 0]

        if not consumables:
            msg = "Kamu tidak memiliki barang konsumsi (Consumable) untuk dihadiahkan! 🎒" if lang == "id" else "You don't have any consumable items to gift! 🎒"
            return await ctx.reply(msg, ephemeral=True)

        # Show Select Menu
        view = View(timeout=60)
        dropdown = GiftDropdown(consumables, user_id, lang)
        view.add_item(dropdown)

        prompt_msg = "Pilih item dari inventarismu untuk dihadiahkan kepada RVDiA:" if lang == "id" else "Select an item from your inventory to gift to RVDiA:"
        await ctx.reply(prompt_msg, view=view)

    @bond.command(name="reset", description="Reset hubunganmu dengan RVDiA kembali ke awal.")
    @check_blacklist()
    async def reset(self, ctx: commands.Context):
        user_id = ctx.author.id
        user_settings = await db.usersettings.find_unique(where={'userId': user_id})
        lang = user_settings.lang if user_settings else "en"

        rel = await relationship_service.get_relationship(user_id)
        if not rel:
            msg = "Kamu belum memulai hubungan dengan RVDiA! 🌸" if lang == "id" else "You haven't started your bond with RVDiA yet! 🌸"
            return await ctx.reply(msg, ephemeral=True)

        confirm_view = View(timeout=30)
        
        async def confirm_callback(interaction: discord.Interaction):
            if interaction.user.id != user_id:
                err_msg = "Bukan tombol Anda! ❌" if lang == "id" else "Not your button! ❌"
                return await interaction.response.send_message(err_msg, ephemeral=True)
            
            await interaction.response.defer()
            try:
                await db.relationship.delete(where={'userId': user_id})
                success_msg = (
                    "✅ Hubunganmu dengan RVDiA telah direset. "
                    "Kalian kembali menjadi orang asing... 🥺"
                ) if lang == "id" else (
                    "✅ Your bond with RVDiA has been reset. "
                    "You are strangers once again... 🥺"
                )
                await interaction.followup.send(success_msg)
                await interaction.message.delete()
            except Exception as e:
                err_res = f"❌ Gagal me-reset: {e}" if lang == "id" else f"❌ Failed to reset: {e}"
                await interaction.followup.send(err_res, ephemeral=True)

        async def cancel_callback(interaction: discord.Interaction):
            if interaction.user.id != user_id:
                err_msg = "Bukan tombol Anda! ❌" if lang == "id" else "Not your button! ❌"
                return await interaction.response.send_message(err_msg, ephemeral=True)
            
            await interaction.response.defer()
            cancel_msg = "Pembatalan dilakukan." if lang == "id" else "Reset cancelled."
            await interaction.followup.send(cancel_msg, ephemeral=True)
            await interaction.message.delete()

        btn_confirm = Button(
            label="Ya, Reset Hubungan" if lang == "id" else "Yes, Reset Relationship", 
            style=discord.ButtonStyle.danger
        )
        btn_confirm.callback = confirm_callback

        btn_cancel = Button(
            label="Batal" if lang == "id" else "Cancel", 
            style=discord.ButtonStyle.secondary
        )
        btn_cancel.callback = cancel_callback

        confirm_view.add_item(btn_confirm)
        confirm_view.add_item(btn_cancel)

        prompt_msg = (
            "Apakah kamu yakin ingin me-reset hubungan dengan RVDiA?\n"
            "Tingkat hubungan dan kedekatanmu dengannya akan dihapus secara permanen! (Chat log RPG tidak terpengaruh) 🥺"
        ) if lang == "id" else (
            "Are you sure you want to reset your relationship with RVDiA?\n"
            "Your stage and affinity progress will be permanently deleted! (Chat memory will not be affected) 🥺"
        )

        await ctx.reply(prompt_msg, view=confirm_view)


async def setup(bot):
    await bot.add_cog(Relationship(bot))
