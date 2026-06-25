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
import cv2
import numpy as np
import os
import json
import time
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from os import getenv
from dotenv import load_dotenv
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types
load_dotenv()


xlv = commands.Bot(command_prefix="x-",
                   help_command=None,
                   intents=discord.Intents.all(),
                   activity=discord.Activity(type=discord.ActivityType.watching, name="RVDiA"))




async def trigger_alert(url, reason):
    logging.warning(f"ALERT: {url} is down! Reason: {reason}")
    
    # NTFY Out-of-discord alert
    ntfy_topic = getenv("NTFY_TOPIC")
    if ntfy_topic:
        try:
            headers = {}
            ntfy_token = getenv("NTFY_TOKEN")
            if ntfy_token:
                headers["Authorization"] = f"Bearer {ntfy_token}"
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"https://ntfy.sh/{ntfy_topic}",
                    data=f"🚨 3Dex Alert 🚨\n{url} is DOWN!\nReason: {reason}".encode('utf-8'),
                    headers=headers
                )
        except Exception as e:
            logging.error(f"Failed to send NTFY alert: {e}")
        
    # Discord alert
    try:
        channel = xlv.get_channel(int(getenv("statuschannel")))
        if channel:
            await channel.send(f"<@{getenv('schryzonid')}>\n🚨 **URGENT**: `{url}` is down!\n**Reason:** {reason}")
    except:
        pass

@tasks.loop(minutes=15)
async def monitor_websites():
    # Store targets as (display_name/key, request_url) to avoid logging secrets (like Telegram Bot Tokens)
    telegram_token = (getenv("TELEGRAM_BOT_TOKEN") or "").strip('"')
    targets = [
        ("https://3dex.studio", "https://3dex.studio"),
        ("https://api.3dex.studio/health", "https://api.3dex.studio/health"),
        ("https://storage.3dex.studio/minio/health/live", "https://storage.3dex.studio/minio/health/live"),
        ("https://rvdia.up.railway.app", "https://rvdia.up.railway.app")
    ]
    if telegram_token:
        targets.append(("Zora (Telegram Bot API)", f"https://api.telegram.org/bot{telegram_token}/getMe"))
    else:
        logging.warning("⚠️ TELEGRAM_BOT_TOKEN not found in env. Skipping Zora monitor.")
    
    history_file = "uptime_history.json"
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history = json.load(f)
        except Exception:
            pass
            
    current_check = {
        "timestamp": datetime.now().isoformat(),
        "results": {}
    }
    
    async with aiohttp.ClientSession() as session:
        for name, url in targets:
            start_time = time.perf_counter()
            status = "down"
            latency = -1
            error_msg = ""
            try:
                # increased timeout to 30s to avoid classifying slow/no response as down
                async with session.get(url, timeout=30) as resp:
                    latency = int((time.perf_counter() - start_time) * 1000)
                    if resp.status == 200:
                        status = "up"
                    else:
                        error_msg = f"HTTP {resp.status}"
                        if name == "https://rvdia.up.railway.app":
                            logging.info("rvdia.up.railway.app returned non-200. Waiting 10 minutes to retry before alerting...")
                            await asyncio.sleep(600)
                            try:
                                async with session.get(url, timeout=30) as retry_resp:
                                    if retry_resp.status == 200:
                                        status = "up"
                                        error_msg = ""
                                    else:
                                        error_msg = f"HTTP {retry_resp.status} (Confirmed down after 10m cooldown)"
                                        await trigger_alert(name, error_msg)
                            except Exception as retry_err:
                                error_msg = f"{retry_err} (Confirmed down after 10m cooldown)"
                                await trigger_alert(name, error_msg)
                        else:
                            await trigger_alert(name, error_msg)
            except Exception as e:
                latency = int((time.perf_counter() - start_time) * 1000)
                error_msg = str(e)
                if name == "https://rvdia.up.railway.app":
                    logging.info(f"rvdia.up.railway.app request failed ({e}). Waiting 10 minutes to retry before alerting...")
                    await asyncio.sleep(600)
                    try:
                        async with session.get(url, timeout=30) as retry_resp:
                            if retry_resp.status == 200:
                                status = "up"
                                error_msg = ""
                            else:
                                error_msg = f"HTTP {retry_resp.status} (Confirmed down after 10m cooldown)"
                                await trigger_alert(name, error_msg)
                    except Exception as retry_err:
                        error_msg = f"{retry_err} (Confirmed down after 10m cooldown)"
                        await trigger_alert(name, error_msg)
                else:
                    await trigger_alert(name, error_msg)
                
            current_check["results"][name] = {
                "status": status,
                "latency": latency,
                "error": error_msg
            }
            
    history.append(current_check)
    history = history[-200:]
    try:
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save uptime history: {e}")

@xlv.event
async def on_ready():
  await xlv.wait_until_ready()
  logging.info('XLV is ready!')
  if not monitor_websites.is_running():
      monitor_websites.start()

@xlv.event
async def on_presence_update(before, after):
  if before.id == int(getenv("rvdiaid")) and after.id == int(getenv("rvdiaid")):
    channel = xlv.get_channel(int(getenv("statuschannel")))
    if str(after.status) == "offline" or str(after.status) == "invisible":
      await channel.send(f"<@{getenv('schryzonid')}>\n⚪ RVDIA is now **`OFFLINE`**!")

# Match domains that look like discord but are misspelled or contain nitro scam strings
scam_domain_regex = re.compile(
    r'https?://[^\s]*('
    r'dlscord|discorcl|disc0rd|disccord|discord-gif|nitro-gif|free-nitro|'
    r'gift-nitro|nitro-claim|discord-claim|discord-app|discord-free'
    r')[^\s]*',
    re.IGNORECASE
)

async def handle_auto_ban(message, reason_type, detail):
    try:
        await message.delete()
    except Exception as e:
        logging.error(f"Failed to delete scam message: {e}")
        
    try:
        await message.author.ban(reason=f"Auto-Mod (Smart Vigilante): Sent {reason_type} ({detail})")
        
        status_chan_id = getenv("statuschannel")
        if status_chan_id:
            channel = xlv.get_channel(int(status_chan_id))
            if channel:
                embed = discord.Embed(
                    title="🛡️ Auto-Ban Smart Alert", 
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
                embed.add_field(name="Trigger", value=reason_type, inline=True)
                embed.add_field(name="Details", value=f"`{detail}`", inline=False)
                embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                await channel.send(embed=embed)
    except Exception as e:
        logging.error(f"Failed to auto-ban user: {e}")

@xlv.event
async def on_message(message):
    await xlv.process_commands(message)

    # Bypass checks for bots, DMs, or admins/mods
    if message.author.bot or message.guild is None:
        return
    if message.author.guild_permissions.manage_messages or message.author.guild_permissions.administrator:
        return

    content = message.content

    # 1. Invite Link Check
    invite_match = re.search(r'(?:discord\.gg|discord(?:app)?\.com/invite)/([a-zA-Z0-9-]+)', content, re.IGNORECASE)
    if invite_match:
        invite_code = invite_match.group(1)
        is_external = True
        try:
            inv = await xlv.fetch_invite(invite_code)
            if inv.guild and inv.guild.id == message.guild.id:
                is_external = False
        except Exception:
            pass
            
        if is_external:
            await handle_auto_ban(message, "Discord Invite Link", invite_match.group(0))
            return

    # 2. Scam/Typosquatting Link Check
    scam_match = scam_domain_regex.search(content)
    if scam_match:
        await handle_auto_ban(message, "Suspicious/Scam Link", scam_match.group(0))
        return

    # 3. Nitro Scam Phrase Check
    nitro_gift_match = re.search(r'(?:free|gift|promo|claim|get)\s*(?:discord\s*)?nitro|nitro\s*(?:free|gift|promo|claim|airdrop)', content, re.IGNORECASE)
    if nitro_gift_match and ("http://" in content or "https://" in content):
        await handle_auto_ban(message, "Nitro Gift Scam Pattern", content[:200])
        return

    # 3b. Crypto/NFT Scam Pattern (Mr. Beast / Elon Musk Giveaway)
    crypto_scam_pattern = re.compile(
        r'(?:mr\s*beast|mrbeast|elon\s*musk|tesla)\s+(?:giveaway|crypto|eth|btc|sol|airdrop|promo|gift|free)|'
        r'(?:double\s*your|get\s*free)\s*(?:crypto|btc|eth|sol|bitcoin|ethereum|money|nft)|'
        r'send\s*(?:btc|eth|sol|crypto)\s+to\s+get|'
        r'official\s*(?:crypto|eth|btc|solana|nft)\s*giveaway',
        re.IGNORECASE
    )
    if crypto_scam_pattern.search(content) and ("http://" in content or "https://" in content or scam_domain_regex.search(content)):
        await handle_auto_ban(message, "Crypto/NFT Giveaway Scam Pattern", content[:200])
        return

    # 4. Attachment Scam Scan (Local QR code + Advanced GenAI image scan for new accounts)
    if message.attachments:
        google_key = getenv("googlekey")
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                try:
                    image_bytes = await attachment.read()
                    
                    # A. Local QR code detection (instant, offline)
                    nparr = np.frombuffer(image_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        detector = cv2.QRCodeDetector()
                        val, pts, qr_code = detector.detectAndDecode(img)
                        if val:
                            if "discord.com/ra/" in val or "discordapp.com/ra/" in val:
                                await handle_auto_ban(message, "Discord QR Code Login Hijack", val)
                                return
                            elif "discord.gg/" in val or "discord.com/invite/" in val:
                                await handle_auto_ban(message, "QR Code Discord Invite", val)
                                return
                                
                    # B. Advanced GenAI image scan (restricted to new/suspicious users to optimize API usage)
                    if google_key:
                        # Calculate account/joined duration (ensure both are timezone-aware using UTC)
                        now_utc = datetime.now(timezone.utc)
                        joined_at = message.author.joined_at
                        created_at = message.author.created_at
                        
                        # If joined_at or created_at is naive, make it aware (should be aware in discord.py)
                        if joined_at and joined_at.tzinfo is None:
                           joined_at = joined_at.replace(tzinfo=timezone.utc)
                        if created_at and created_at.tzinfo is None:
                           created_at = created_at.replace(tzinfo=timezone.utc)
                           
                        joined_ago = now_utc - joined_at if joined_at else timedelta(days=999)
                        created_ago = now_utc - created_at if created_at else timedelta(days=999)
                        
                        # Suspicious: joined server < 24 hours ago OR account created < 7 days ago
                        is_suspicious = (joined_ago < timedelta(days=1)) or (created_ago < timedelta(days=7))
                        
                        if is_suspicious:
                            client = genai.Client(api_key=google_key)
                            prompt = (
                                "Analyze this image carefully. Does it contain a cryptocurrency giveaway, a classic Mr. Beast or "
                                "Elon Musk or Tesla money/crypto giveaway scam, an NFT minting promo, a scan-to-login QR code phishing scam, "
                                "or any other fake financial/gift distribution promotion? "
                                "Respond with 'YES' on the first line if it is a scam/giveaway image, or 'NO' on the first line if it is a normal, non-scam image. "
                                "On the second line, provide a brief, one-sentence explanation of why it is or isn't a scam."
                            )
                            
                            mime_type = attachment.content_type or "image/png"
                            part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type if "image" in mime_type else "image/png")
                            
                            result = await client.aio.models.generate_content(
                                model='gemini-3-flash-preview',
                                contents=[part, prompt]
                            )
                            
                            resp_text = result.text.strip() if result.text else ""
                            lines = resp_text.splitlines()
                            if lines:
                                verdict = lines[0].strip().upper()
                                explanation = lines[1].strip() if len(lines) > 1 else resp_text
                                
                                if "YES" in verdict:
                                    await handle_auto_ban(message, "AI Scam Image Detection", explanation)
                                    return
                                    
                except Exception as e:
                    logging.error(f"Error scanning attachment {attachment.filename} for scams: {e}")


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
@xlv.command(aliases=['purgeuser', 'cleanuser'])
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True, read_message_history=True)
async def clearuser(ctx: commands.Context, user_id: str, limit: int = 100):
    try:
        target_id = int(user_id)
    except ValueError:
        return await ctx.reply("ID Pengguna tidak valid! Pastikan berupa deretan angka ID Discord.")

    if limit <= 0 or limit > 2000:
        return await ctx.reply("Batas jumlah pesan yang diperiksa harus di antara 1 dan 2000!")

    # Delete the command message to keep channel clean
    try:
        await ctx.message.delete()
    except:
        pass

    async with ctx.channel.typing():
        def check(message):
            return message.author.id == target_id

        try:
            # Purge messages matching the check
            deleted = await ctx.channel.purge(limit=limit, check=check)
            
            # Fetch username if possible
            user_display = f"User ID `{target_id}`"
            try:
                user = await xlv.fetch_user(target_id)
                user_display = f"**`{user}`** (`{target_id}`)"
            except:
                pass
                
            await ctx.send(f"✅ Berhasil menghapus {len(deleted)} pesan dari {user_display} di channel ini.", delete_after=10.0)
        except Exception as e:
            await ctx.send(f"❌ Gagal menghapus pesan: `{str(e)}`", delete_after=10.0)


@xlv.command(aliases=['nukeuser', 'purgeuserall', 'clearuserall'])
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_messages=True, read_message_history=True)
async def clearuserglobal(ctx: commands.Context, user_id: str, limit_per_channel: int = 100):
    try:
        target_id = int(user_id)
    except ValueError:
        return await ctx.reply("ID Pengguna tidak valid! Pastikan berupa deretan angka ID Discord.")

    if limit_per_channel <= 0 or limit_per_channel > 1000:
        return await ctx.reply("Batas jumlah pesan per channel harus di antara 1 dan 1000!")

    try:
        await ctx.message.delete()
    except:
        pass

    user_display = f"User ID `{target_id}`"
    try:
        user = await xlv.fetch_user(target_id)
        user_display = f"**`{user}`** (`{target_id}`)"
    except:
        pass

    status_msg = await ctx.send(f"🛡️ Memulai pembersihan global pesan dari {user_display} di semua channel...")

    total_deleted = 0
    channels_purged = 0

    for channel in ctx.guild.text_channels:
        perms = channel.permissions_for(ctx.guild.me)
        if not (perms.read_messages and perms.read_message_history and perms.manage_messages):
            continue

        try:
            def check(m):
                return m.author.id == target_id
                
            deleted = await channel.purge(limit=limit_per_channel, check=check)
            if len(deleted) > 0:
                total_deleted += len(deleted)
                channels_purged += 1
        except Exception:
            pass

    await status_msg.edit(content=f"✅ Berhasil menghapus total **{total_deleted}** pesan dari {user_display} di **{channels_purged}** channel.")


@xlv.command(aliases=['statusgraph', 'uptimes', 'pingall'])
async def uptime(ctx: commands.Context):
    history_file = "uptime_history.json"
    if not os.path.exists(history_file):
        return await ctx.reply("Belum ada data history uptime yang terekam.")
        
    try:
        with open(history_file, "r") as f:
            history = json.load(f)
    except Exception as e:
        return await ctx.reply(f"Gagal membaca data history: `{e}`")
        
    if not history:
        return await ctx.reply("Data history uptime kosong.")

    urls = [
        "https://3dex.studio",
        "https://api.3dex.studio/health",
        "https://storage.3dex.studio/minio/health/live",
        "https://rvdia.up.railway.app",
        "Zora (Telegram Bot API)"
    ]
    
    dates = []
    data_series = {url: [] for url in urls}
    
    for entry in history:
        try:
            dt = datetime.fromisoformat(entry["timestamp"])
            dates.append(dt)
            for url in urls:
                res = entry["results"].get(url, {"status": "down", "latency": -1})
                lat = res.get("latency", -1)
                data_series[url].append(lat if lat >= 0 else 0)
        except Exception:
            continue

    if not dates:
        return await ctx.reply("Gagal memproses data timestamp history.")

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    
    fig.patch.set_facecolor('#181825')
    ax.set_facecolor('#1e1e2e')
    
    colors = {
        "https://3dex.studio": "#cba6f7",          # Lavender
        "https://api.3dex.studio/health": "#89b4fa",   # Blue
        "https://storage.3dex.studio/minio/health/live": "#a6e3a1", # Green
        "https://rvdia.up.railway.app": "#f38ba8",    # Red/Peach
        "Zora (Telegram Bot API)": "#f9e2af"          # Yellow (Zora Bot)
    }
    
    def clean_label(url):
        return url.replace("https://", "").replace("www.", "")

    for url in urls:
        y_data = data_series[url]
        ax.plot(dates, y_data, label=clean_label(url), color=colors[url], linewidth=2, marker='o', markersize=3, alpha=0.8)
        
        downtime_dates = []
        downtime_latencies = []
        for i, entry in enumerate(history):
            res = entry["results"].get(url, {"status": "down"})
            if res.get("status") == "down":
                downtime_dates.append(dates[i])
                downtime_latencies.append(0)
                
        if downtime_dates:
            ax.scatter(downtime_dates, downtime_latencies, color='#f38ba8', s=40, zorder=5, marker='x')

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    plt.xticks(rotation=30, ha='right')
    
    ax.grid(True, linestyle='--', alpha=0.2, color='#585b70')
    
    ax.set_title("🌐 Website Uptime & Latency History", fontsize=14, fontweight='bold', color='#cdd6f4', pad=15)
    ax.set_xlabel("Time (MM-DD HH:MM)", fontsize=11, color='#a6adc8', labelpad=10)
    ax.set_ylabel("Latency (ms)", fontsize=11, color='#a6adc8', labelpad=10)
    
    ax.legend(facecolor='#1e1e2e', edgecolor='#313244', loc='upper left', fontsize=9, labelcolor='#cdd6f4')
    
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_color('#313244')
        
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    buf.seek(0)
    plt.close()
    
    file = discord.File(buf, filename="uptime_graph.png")
    
    status_summary = "**🌐 Current Status Summary:**\n"
    latest_entry = history[-1]
    for url in urls:
        res = latest_entry["results"].get(url, {"status": "unknown", "latency": -1})
        status_emoji = "🟢" if res.get("status") == "up" else "🔴"
        latency_str = f"`{res.get('latency')}ms`" if res.get("status") == "up" else "`N/A`"
        status_summary += f"{status_emoji} **{clean_label(url)}**: {res.get('status').upper()} ({latency_str})\n"
        
    await ctx.reply(content=status_summary, file=file)


@xlv.command(name='help')
async def xlv_help(ctx: commands.Context):
    embed = discord.Embed(
        title="🛡️ X-LV (Xtreme Log-out Vigilante) Help Menu",
        description="X-LV is RVDIA's status monitor and server security bot. Below is the list of available commands and active auto-moderation systems.",
        color=discord.Color.from_str("#cba6f7"),
        timestamp=datetime.now()
    )
    
    if xlv.user and xlv.user.avatar:
        embed.set_thumbnail(url=xlv.user.avatar.url)
        
    embed.add_field(
        name="💬 Moderation Commands",
        value=(
            "`x-clearuser <user_id> [limit]`\n"
            "↳ *Purges messages from the specified user in this channel. (Default limit: 100)*\n\n"
            "`x-clearuserglobal <user_id> [limit_per_channel]`\n"
            "↳ *Purges messages from the specified user across all guild channels. (Default limit: 100, Admin only)*"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🌐 Status Commands",
        value=(
            "`x-uptime` (aliases: `statusgraph`, `uptimes`, `pingall`)\n"
            "↳ *Displays the current health status of services and generates a 50-hour latency history chart.*"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🤖 Active Smart Auto-Mod Gating (Passive)",
        value=(
            "• **Invite Shield**: Deletes and bans external Discord invites (except local server invites).\n"
            "• **Typosquatting/Scam Link Shield**: Blocks domains mimicking Discord or Nitro offers.\n"
            "• **Local QR Decoder**: Detects QR code login hijacks locally from image attachments.\n"
            "• **AI Scam Vision**: Uses Gemini to analyze captionless Mr. Beast/Elon Musk crypto and NFT giveaway scam images posted by untrusted/new users."
        ),
        inline=False
    )
    
    footer_avatar = xlv.user.avatar.url if (xlv.user and xlv.user.avatar) else None
    embed.set_footer(text="Prefix: x- | Coded by Schryzon", icon_url=footer_avatar)
    
    await ctx.reply(embed=embed)


xlv.run(token=str(getenv('xlvtoken')))