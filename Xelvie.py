"""
X-LV
Xtreme Log-out Vigilante
Used to detect RVDIA's status
"""

import discord
import random
import logging
import asyncio
import re
import aiohttp
from os import getenv
from dotenv import load_dotenv
from discord.ext import commands
from datetime import datetime, timedelta
from prisma import Prisma, Json

load_dotenv()
db = Prisma()

xlv = commands.Bot(command_prefix="x-",
                   help_command=None,
                   intents=discord.Intents.all(),
                   activity=discord.Activity(type=discord.ActivityType.watching, name="RVDiA"))


class PremiumApprovalView(discord.ui.View):
    def __init__(self, user_id, bukti_url):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.bukti_url = bukti_url

    @discord.ui.button(label="Setujui (30 Hari)", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Hanya admin yang bisa menyetujui klaim!", ephemeral=True)
            
        user = await db.user.find_unique(where={'id': self.user_id})
        if not user:
            return await interaction.response.send_message("User tidak ditemukan di database!", ephemeral=True)
            
        now = datetime.now()
        if user.premiumUntil and user.premiumUntil > now:
            new_expiry = user.premiumUntil + timedelta(days=30)
        else:
            new_expiry = now + timedelta(days=30)
            
        await db.user.update(where={'id': self.user_id}, data={'premiumUntil': new_expiry})
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "💎 Klaim Premium DISETUJUI ✅"
        embed.set_footer(text=f"Disetujui oleh {interaction.user.name}")
        
        await interaction.response.edit_message(embed=embed, view=None)
        
        try:
            target_user = await interaction.client.fetch_user(self.user_id)
            await target_user.send(f"💎 **Klaim Premium Berhasil!** Selamat, kamu telah menjadi Dream Weaver selama 30 hari!\nBerlaku sampai: <t:{int(new_expiry.timestamp())}:F>")
        except:
            # Relay via RVDiA Bridge
            await self.relay_dm(self.user_id, f"💎 **Klaim Premium Berhasil!** Selamat, kamu telah menjadi Dream Weaver selama 30 hari!\nBerlaku sampai: <t:{int(new_expiry.timestamp())}:F>")

    @discord.ui.button(label="Tolak", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Hanya admin yang bisa menolak klaim!", ephemeral=True)
            
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "💎 Klaim Premium DITOLAK ❌"
        embed.set_footer(text=f"Ditolak oleh {interaction.user.name}")
        
        await interaction.response.edit_message(embed=embed, view=None)
        
        try:
            target_user = await interaction.client.fetch_user(self.user_id)
            await target_user.send("❌ **Klaim Premium Ditolak.** Bukti pembayaran tidak valid atau tidak sesuai. Silahkan hubungi admin jika ada kesalahan.")
        except:
            # Relay via RVDiA Bridge
            await self.relay_dm(self.user_id, "❌ **Klaim Premium Ditolak.** Bukti pembayaran tidak valid atau tidak sesuai. Silahkan hubungi admin jika ada kesalahan.")

    async def relay_dm(self, user_id, message):
        async with aiohttp.ClientSession() as session:
            port = int(getenv("PORT", 8080))
            url = f"http://127.0.0.1:{port}/internal/dm"
            payload = {'user_id': user_id, 'message': message}
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logging.error(f"Relay DM failed with status {resp.status}")
            except Exception as e:
                logging.error(f"Failed to connect to relay: {e}")

@xlv.event
async def on_connect():
    if not db.is_connected():
        await db.connect()
    logging.info('XLV connected!')

@xlv.event
async def on_ready():
  await xlv.wait_until_ready()
  logging.info('XLV is ready!')

@xlv.event
async def on_presence_update(before, after):
  if before.id == int(getenv("rvdiaid")) and after.id == int(getenv("rvdiaid")):
    channel = xlv.get_channel(int(getenv("statuschannel")))
    if str(after.status) == "offline" or str(after.status) == "invisible":
      await channel.send(f"<@{getenv('schryzonid')}>\n⚪ RVDIA is now **`OFFLINE`**!")

@xlv.event
async def on_message(message):
    if message.author.bot and message.author.id == int(getenv("rvdiaid")):
        # Detect claim notification from RVDiA
        if "[CLAIM_PREMIUM]" in message.content:
            try:
                # Format: [CLAIM_PREMIUM] {user_id} {bukti_url}
                parts = message.content.split()
                user_id = int(parts[1])
                bukti_url = parts[2]
                
                await message.delete()
                
                user = await xlv.fetch_user(user_id)
                embed = discord.Embed(title="💎 Klaim Premium Baru!", color=0x00ffff)
                embed.set_author(name=user.name, icon_url=user.display_avatar.url)
                embed.add_field(name="User ID", value=f"`{user_id}`", inline=True)
                embed.add_field(name="User Mention", value=user.mention, inline=True)
                embed.set_image(url=bukti_url)
                embed.set_footer(text="Gunakan tombol di bawah untuk menyetujui atau menolak.")
                
                view = PremiumApprovalView(user_id, bukti_url)
                await message.channel.send(embed=embed, view=view)
            except Exception as e:
                logging.error(f"Error processing claim: {e}")
    
    await xlv.process_commands(message)

greetings = ["Hello there,", "Greetings,", "Welcome to CyroN,", "Why hello there,", "Thanks for joining,", "Heya hee ho,", 
    "Welcome,", "A new member joined,", "Yokoso,", "Hi~", "Konnichiwa,", "Heya,", "Helloooo~,"
    ]
ending = [". I hope you have a fantastic day at CyroN!", ". I sure hope you brought me some food... just kidding!",
    ". I hope you get along with the others!", ". Don't forget to read the rules, okay?", ". Enjoy your stay!",
    ". Don't cause any ruckus, alrighty?", ". I bet Xefnir is happy to see another member! :D", ". Please don't cause any trouble, sweetie.",
    ". I'm so glad you joined!", "? Sorry, I'm kind of sleepy right now but anyways, welcome."
    ]
left = ["Did they do something bad?", "Were you feeling uncomfortable? :(", "See you on the other side!",
    "I'll miss you...", "I hope the best for them.", "\n...", "One member lost.", "Goodbye!", "I'll never forget this day...",
    r"*Sobbing intensifies*", r"*Sigh*"
    ]

@xlv.event
async def on_member_join(user:discord.Member):
    if user.bot is True: return
    if user.guild.id == int(getenv("cyronguild")):
        channel = user.guild.get_channel(int(getenv("welcomechannel"))) #hello-bye
        await channel.send(f"{random.choice(greetings)} **`{user}`**{random.choice(ending)}")
    else: return

@xlv.event
async def on_member_remove(user:discord.Member):
    if user.bot is True: return
    if user.guild.id == int(getenv("cyronguild")):
        channel = user.guild.get_channel(int(getenv("welcomechannel")))
        await channel.send(f"**`{user}`** has left CyroN. {random.choice(left)}")
    else: return


xlv.run(token=str(getenv('xlvtoken')))