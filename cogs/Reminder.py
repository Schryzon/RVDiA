import discord
import re
import logging
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks
from discord import app_commands
from scripts.main import db, check_blacklist
from scripts.utils.i18n import i18n

def parse_duration(time_str: str) -> timedelta:
    # 1. Parse absolute HH:MM format
    abs_match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if abs_match:
        hours = int(abs_match.group(1))
        minutes = int(abs_match.group(2))
        if hours >= 24 or minutes >= 60:
            raise ValueError("Invalid time format!")
        now_local = datetime.now()
        target = now_local.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        if target <= now_local:
            target += timedelta(days=1)
        return target - now_local

    # 2. Parse relative duration like 1d2h30m10s
    pattern = re.compile(r'^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$', re.IGNORECASE)
    match = pattern.match(time_str)
    if not match or not any(match.groups()):
        raise ValueError("Invalid duration format!")
        
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_reminders_task.start()

    def cog_unload(self):
        self.check_reminders_task.cancel()

    @tasks.loop(seconds=30)
    async def check_reminders_task(self):
        try:
            now = datetime.now(timezone.utc)
            expired = await db.reminder.find_many(
                where={'targetTime': {'lte': now}},
                order={'targetTime': 'asc'}
            )
            
            if not expired:
                return

            for rem in expired:
                user_id = int(rem.userId)
                channel_id = int(rem.channelId)
                message = rem.message

                try:
                    user_settings = await db.usersettings.find_unique(where={'userId': user_id})
                    lang = user_settings.lang if user_settings else "en"
                except Exception:
                    lang = "en"

                # Check if Telegram User
                if user_id < 0:
                    from scripts.utils.telegram import send_telegram_message
                    alert_text = (
                        f"🔔 <b>Reminder:</b> {message}"
                    ) if lang == "en" else (
                        f"🔔 <b>Pengingat:</b> {message}"
                    )
                    try:
                        await send_telegram_message(channel_id, alert_text)
                    except Exception as e:
                        logging.error(f"Failed to send Telegram reminder: {e}")
                    await db.reminder.delete(where={'id': rem.id})
                    continue

                channel = self.bot.get_channel(channel_id)
                user = self.bot.get_user(user_id)
                    
                alert_text = (
                    f"🔔 <@{user_id}> **Reminder:** {message}"
                ) if lang == "en" else (
                    f"🔔 <@{user_id}> **Pengingat:** {message}"
                )

                sent = False
                if channel:
                    try:
                        await channel.send(alert_text)
                        sent = True
                    except Exception:
                        pass
                
                if not sent and user:
                    try:
                        await user.send(alert_text)
                    except Exception:
                        pass

                await db.reminder.delete(where={'id': rem.id})
                
        except Exception as e:
            logging.error(f"Error in check_reminders_task: {e}", exc_info=True)

    @check_reminders_task.before_loop
    async def before_check_reminders_task(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(
        name="remind",
        description="Set a background reminder."
    )
    @app_commands.describe(
        time_str="Time duration (e.g. 10m, 2h, 1d30m) or absolute time (e.g. 15:30)",
        message="The reminder message"
    )
    @check_blacklist()
    async def remind(self, ctx: commands.Context, time_str: str, *, message: str):
        """Set a background reminder."""
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        try:
            duration = parse_duration(time_str)
        except ValueError:
            err_msg = (
                "❌ Invalid time format! Use formats like `30s`, `10m`, `2h`, `1d`, or absolute time like `15:30`."
            ) if lang == "en" else (
                "❌ Format waktu tidak valid! Gunakan format seperti `30s`, `10m`, `2h`, `1d`, atau waktu absolut seperti `15:30`."
            )
            return await ctx.reply(err_msg)

        if duration.total_seconds() <= 0:
            err_msg = (
                "❌ Reminder time must be in the future!"
            ) if lang == "en" else (
                "❌ Waktu pengingat harus berada di masa depan!"
            )
            return await ctx.reply(err_msg)

        if duration.total_seconds() > 30 * 24 * 60 * 60:
            err_msg = (
                "❌ Reminder duration cannot exceed 30 days!"
            ) if lang == "en" else (
                "❌ Durasi pengingat tidak boleh lebih dari 30 hari!"
            )
            return await ctx.reply(err_msg)

        target_time = datetime.now(timezone.utc) + duration
        target_timestamp = int(target_time.timestamp())

        await db.reminder.create(data={
            'userId': ctx.author.id,
            'channelId': ctx.channel.id,
            'message': message,
            'targetTime': target_time
        })

        success_msg = (
            f"✅ Reminder set! I will remind you on <t:{target_timestamp}:F> (<t:{target_timestamp}:R>)."
        ) if lang == "en" else (
            f"✅ Pengingat diatur! Aku akan mengingatkanmu pada <t:{target_timestamp}:F> (<t:{target_timestamp}:R>)."
        )
        await ctx.reply(success_msg)

async def setup(bot):
    await bot.add_cog(Reminder(bot))
