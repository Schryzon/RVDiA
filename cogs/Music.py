import asyncio
import discord
import yt_dlp
import re
from discord import app_commands
from discord.ext import commands
from scripts.main import db, check_blacklist
from scripts.utils.i18n import i18n

# Safe YTDL configurations targeting SoundCloud
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

async def extract_info(query: str) -> dict:
    """
    Extract video/audio metadata using yt-dlp in a separate thread.
    """
    return await asyncio.to_thread(ytdl.extract_info, query, download=False)


class GuildMusicState:
    """
    Per-guild music player state and loop manager.
    """
    def __init__(self, bot, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.queue = []
        self.current_track = None
        self.voice_client = None
        self.play_next_event = asyncio.Event()
        self.play_loop_task = None
        self.connecting = False

    def start_loop(self):
        if not self.play_loop_task or self.play_loop_task.done():
            self.play_loop_task = asyncio.create_task(self.play_loop())

    async def play_loop(self):
        while self.voice_client and self.voice_client.is_connected():
            self.play_next_event.clear()
            
            if not self.queue:
                try:
                    # Disconnect if idle for 5 minutes
                    await asyncio.wait_for(self.wait_for_queue(), timeout=300.0)
                except asyncio.TimeoutError:
                    await self.disconnect()
                    break

            if not self.voice_client or not self.voice_client.is_connected():
                break

            if not self.queue:
                continue

            self.current_track = self.queue.pop(0)
            
            try:
                source = discord.FFmpegPCMAudio(self.current_track['url'], **FFMPEG_OPTIONS)
                transformer = discord.PCMVolumeTransformer(source)
                
                # Set up thread-safe callback to trigger the next song when current finishes
                self.voice_client.play(
                    transformer, 
                    after=lambda e: self.bot.loop.call_soon_threadsafe(self.play_next_event.set)
                )
                
                # Send Now Playing embed to the requesting channel
                channel = self.current_track.get('channel')
                if channel:
                    user_settings = await db.usersettings.find_unique(where={'userId': self.current_track['requester_id']})
                    lang = user_settings.lang if user_settings else "en"
                    
                    title = self.current_track['title']
                    requester = self.current_track['requester']
                    
                    embed = discord.Embed(
                        title=i18n.get(lang, "music.now_playing_title") or "Now Playing",
                        description=f"**[{title}]({self_url_fallback(self.current_track)})**",
                        color=self.bot.color
                    )
                    embed.add_field(
                        name=i18n.get(lang, "music.field_requester") or "Requested By", 
                        value=f"`{requester}`", 
                        inline=True
                    )
                    
                    dur = self.current_track.get('duration', 0)
                    if dur:
                        mins, secs = divmod(int(dur), 60)
                        duration_str = f"{mins:02d}:{secs:02d}"
                        embed.add_field(
                            name=i18n.get(lang, "music.field_duration") or "Duration", 
                            value=f"`{duration_str}`", 
                            inline=True
                        )
                    
                    embed.set_footer(text="RVDiA Music System • SoundCloud & Uploads")
                    await channel.send(embed=embed)
            except Exception as e:
                # In case of playback crash, log to channel if possible
                channel = self.current_track.get('channel')
                if channel:
                    await channel.send(f"❌ Error playing track: `{str(e)}`")
                self.bot.loop.call_soon_threadsafe(self.play_next_event.set)

            await self.play_next_event.wait()
            self.current_track = None

    async def wait_for_queue(self):
        while not self.queue and self.voice_client and self.voice_client.is_connected():
            await asyncio.sleep(1.0)

    async def disconnect(self):
        import logging
        import traceback
        logging.info("GuildMusicState.disconnect() called! Call stack:")
        for line in traceback.format_stack():
            logging.info(line.strip())

        if self.voice_client:
            try:
                await self.voice_client.disconnect(force=True)
            except Exception:
                pass
            self.voice_client = None
        if self.play_loop_task:
            self.play_loop_task.cancel()
            self.play_loop_task = None
        self.queue.clear()
        self.current_track = None


def self_url_fallback(track: dict) -> str:
    return track.get('original_url') or track['url']


class SoundCloudSelect(discord.ui.Select):
    def __init__(self, tracks: list, state, lang: str):
        self.tracks_data = tracks
        self.state = state
        self.lang = lang

        options = []
        for idx, track in enumerate(tracks):
            title = track.get('title', 'Unknown Title')
            # Truncate title to fit within select option limit (100 chars)
            title = title[:95]
            duration = track.get('duration', 0)
            duration_str = ""
            if duration:
                mins, secs = divmod(int(duration), 60)
                duration_str = f" ({mins:02d}:{secs:02d})"

            options.append(discord.SelectOption(
                label=title,
                value=str(idx),
                description=f"SoundCloud Track{duration_str}"
            ))

        super().__init__(
            placeholder=i18n.get(lang, "music.select_song_placeholder") or "Select songs to play...",
            min_values=1,
            max_values=len(tracks),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # Check if the user is the one who initiated the command
        if interaction.user.id != self.view.requester_id:
            msg = i18n.get(self.lang, "music.not_your_search") or "You cannot interact with this search menu!"
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

        await interaction.response.defer()

        # Re-check voice connection
        ctx = self.view.ctx
        state = self.state

        if not ctx.author.voice:
            msg = i18n.get(self.lang, "music.no_voice_channel") or "You must be in a voice channel to use this command!"
            return await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)

        # Deafen RVDiA upon entry
        if not state.voice_client or not state.voice_client.is_connected():
            if state.connecting:
                for _ in range(10):
                    if state.voice_client and state.voice_client.is_connected():
                        break
                    await asyncio.sleep(0.5)

            if not state.voice_client or not state.voice_client.is_connected():
                state.connecting = True
                try:
                    if state.voice_client:
                        try:
                            await state.voice_client.disconnect(force=True)
                        except Exception:
                            pass
                        state.voice_client = None

                    state.voice_client = await ctx.author.voice.channel.connect(self_deaf=True)
                    state.start_loop()
                finally:
                    state.connecting = False

        queued_titles = []
        for val in self.values:
            selected_idx = int(val)
            track_info = self.tracks_data[selected_idx]

            track = {
                'title': track_info.get('title', 'SoundCloud Track'),
                'url': track_info['url'],
                'original_url': track_info.get('webpage_url'),
                'duration': track_info.get('duration', 0),
                'requester': str(ctx.author),
                'requester_id': ctx.author.id,
                'channel': ctx.channel
            }

            state.queue.append(track)
            queued_titles.append(track['title'])

        state.start_loop()

        if len(queued_titles) == 1:
            msg = i18n.get(self.lang, "music.added_to_queue", title=queued_titles[0]) or f"Added **{queued_titles[0]}** to the queue!"
        else:
            titles_str = ", ".join(f"**{t}**" for t in queued_titles)
            msg = f"Added {len(queued_titles)} songs to the queue: {titles_str}"

        self.view.clear_items()
        await interaction.edit_original_response(content=f"➕ {msg}", embed=None, view=None)


class SoundCloudSelectView(discord.ui.View):
    def __init__(self, ctx, requester_id: int, tracks: list, state, lang: str):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.requester_id = requester_id
        self.message = None
        self.add_item(SoundCloudSelect(tracks, state, lang))

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass


class Music(commands.Cog):
    """
    Music player commands supporting SoundCloud and file uploads.
    """
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.states = {}

    def get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState(self.bot, guild_id)
        return self.states[guild_id]

    @commands.hybrid_command(
        name="play", 
        description="Play audio from SoundCloud or an uploaded file!"
    )
    @app_commands.describe(
        query_or_url="SoundCloud search query or URL",
        attachment="Upload an audio file (.mp3, .wav, .m4a, .ogg) to play directly"
    )
    @check_blacklist()
    async def play(self, ctx: commands.Context, query_or_url: str = None, attachment: discord.Attachment = None):
        """
        Play audio from SoundCloud or an uploaded file!
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if not ctx.author.voice:
            msg = i18n.get(lang, "music.no_voice_channel") or "You must be in a voice channel to use this command!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        if not query_or_url and not attachment:
            msg = i18n.get(lang, "music.missing_args") or "Please provide a search query/URL or upload an audio file!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        await ctx.defer()
        state = self.get_state(ctx.guild.id)

        track = None

        if attachment:
            # Check file extension safety
            allowed_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.aac', '.flac']
            has_valid_ext = any(attachment.filename.lower().endswith(ext) for ext in allowed_extensions)
            if not has_valid_ext:
                msg = i18n.get(lang, "music.invalid_file_format") or "Invalid file format! Allowed: .mp3, .wav, .m4a, .ogg, .aac, .flac"
                return await ctx.reply(f"❌ {msg}")
            
            # Use attachment URL directly for zero storage streaming
            track = {
                'title': attachment.filename,
                'url': attachment.url,
                'original_url': attachment.url,
                'duration': 0,
                'requester': str(ctx.author),
                'requester_id': ctx.author.id,
                'channel': ctx.channel
            }

        elif query_or_url:
            # YouTube check for safety / verified bot compliance
            is_youtube = re.search(r'(youtube\.com|youtu\.be)', query_or_url, re.IGNORECASE)
            if is_youtube:
                msg = i18n.get(lang, "music.youtube_blocked") or "For legal and platform safety compliance, YouTube links are not supported. Please use SoundCloud or upload an audio file directly! 🛡️"
                return await ctx.reply(f"🛡️ {msg}")

            is_url = query_or_url.startswith('http://') or query_or_url.startswith('https://')
            search_query = query_or_url if is_url else f"scsearch10:{query_or_url}"

            try:
                # Query SoundCloud
                info = await extract_info(search_query)
                if not info:
                    msg = i18n.get(lang, "music.no_results") or "No results found on SoundCloud!"
                    return await ctx.reply(f"❌ {msg}")

                if 'entries' in info and not is_url:
                    entries = info['entries']
                    if not entries:
                        msg = i18n.get(lang, "music.no_results") or "No results found on SoundCloud!"
                        return await ctx.reply(f"❌ {msg}")

                    embed = discord.Embed(
                        title=i18n.get(lang, "music.search_results_title") or "SoundCloud Search Results",
                        description=i18n.get(lang, "music.search_results_desc") or "Please select one or more songs from the dropdown menu to queue them:",
                        color=self.bot.color
                    )

                    for idx, entry in enumerate(entries[:10], start=1):
                        title = entry.get('title', 'SoundCloud Track')
                        url = entry.get('webpage_url') or entry.get('url')
                        duration = entry.get('duration', 0)
                        duration_str = ""
                        if duration:
                            mins, secs = divmod(int(duration), 60)
                            duration_str = f" `{mins:02d}:{secs:02d}`"

                        embed.add_field(
                            name=f"{idx}. {title}",
                            value=f"🔗 [Link]({url}){duration_str}",
                            inline=False
                        )

                    view = SoundCloudSelectView(ctx, ctx.author.id, entries[:10], state, lang)
                    msg_obj = await ctx.reply(embed=embed, view=view)
                    view.message = msg_obj
                    return

                else:
                    if 'entries' in info:
                        if not info['entries']:
                            msg = i18n.get(lang, "music.no_results") or "No results found on SoundCloud!"
                            return await ctx.reply(f"❌ {msg}")
                        info = info['entries'][0]

                    track = {
                        'title': info.get('title', 'SoundCloud Track'),
                        'url': info['url'],
                        'original_url': info.get('webpage_url', query_or_url),
                        'duration': info.get('duration', 0),
                        'requester': str(ctx.author),
                        'requester_id': ctx.author.id,
                        'channel': ctx.channel
                    }
            except Exception as e:
                return await ctx.reply(f"❌ Failed to load audio: `{str(e)}`")

        if track:
            # Deafen RVDiA upon entry
            if not state.voice_client or not state.voice_client.is_connected():
                if state.connecting:
                    for _ in range(10):
                        if state.voice_client and state.voice_client.is_connected():
                            break
                        await asyncio.sleep(0.5)

                if not state.voice_client or not state.voice_client.is_connected():
                    state.connecting = True
                    try:
                        if state.voice_client:
                            try:
                                await state.voice_client.disconnect(force=True)
                            except Exception:
                                pass
                            state.voice_client = None
                        
                        state.voice_client = await ctx.author.voice.channel.connect(self_deaf=True)
                        state.start_loop()
                    finally:
                        state.connecting = False

            state.queue.append(track)
            state.start_loop()
            
            # Send added to queue message
            msg = i18n.get(lang, "music.added_to_queue", title=track['title']) or f"Added **{track['title']}** to the queue!"
            await ctx.reply(f"➕ {msg}")

    @commands.hybrid_command(
        name="skip", 
        description="Skip the current playing track."
    )
    @check_blacklist()
    async def skip(self, ctx: commands.Context):
        """
        Skip the current playing track.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.voice_client or not state.voice_client.is_playing():
            msg = i18n.get(lang, "music.not_playing") or "Not currently playing any music!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        state.voice_client.stop()
        msg = i18n.get(lang, "music.skipped") or "Skipped the current track!"
        await ctx.reply(f"⏭️ {msg}")

    @commands.hybrid_command(
        name="pause", 
        description="Pause the current music playback."
    )
    @check_blacklist()
    async def pause(self, ctx: commands.Context):
        """
        Pause the current music playback.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.voice_client or not state.voice_client.is_playing():
            msg = i18n.get(lang, "music.not_playing") or "Not currently playing any music!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        if state.voice_client.is_paused():
            msg = i18n.get(lang, "music.already_paused") or "Music is already paused!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        state.voice_client.pause()
        msg = i18n.get(lang, "music.paused") or "Paused the music playback!"
        await ctx.reply(f"⏸️ {msg}")

    @commands.hybrid_command(
        name="resume", 
        description="Resume the paused music playback."
    )
    @check_blacklist()
    async def resume(self, ctx: commands.Context):
        """
        Resume the paused music playback.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.voice_client:
            msg = i18n.get(lang, "music.not_connected") or "I am not connected to a voice channel!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        if not state.voice_client.is_paused():
            msg = i18n.get(lang, "music.already_playing") or "Music is already playing!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        state.voice_client.resume()
        msg = i18n.get(lang, "music.resumed") or "Resumed the music playback!"
        await ctx.reply(f"▶️ {msg}")

    @commands.hybrid_command(
        name="stop", 
        aliases=["leave"], 
        description="Stop playing music, clear the queue, and disconnect."
    )
    @check_blacklist()
    async def stop(self, ctx: commands.Context):
        """
        Stop playing music, clear the queue, and disconnect.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.voice_client:
            msg = i18n.get(lang, "music.not_connected") or "I am not connected to a voice channel!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        await state.disconnect()
        msg = i18n.get(lang, "music.stopped") or "Stopped music, cleared queue, and disconnected from the voice channel!"
        await ctx.reply(f"🛑 {msg}")

    @commands.hybrid_command(
        name="nowplaying", 
        aliases=["np"], 
        description="Show information about the currently playing track."
    )
    @check_blacklist()
    async def nowplaying(self, ctx: commands.Context):
        """
        Show information about the currently playing track.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.current_track:
            msg = i18n.get(lang, "music.not_playing") or "Not currently playing any music!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        track = state.current_track
        embed = discord.Embed(
            title=i18n.get(lang, "music.now_playing_title") or "Now Playing",
            description=f"**[{track['title']}]({self_url_fallback(track)})**",
            color=self.bot.color
        )
        embed.add_field(
            name=i18n.get(lang, "music.field_requester") or "Requested By", 
            value=f"`{track['requester']}`", 
            inline=True
        )
        
        dur = track.get('duration', 0)
        if dur:
            mins, secs = divmod(int(dur), 60)
            duration_str = f"{mins:02d}:{secs:02d}"
            embed.add_field(
                name=i18n.get(lang, "music.field_duration") or "Duration", 
                value=f"`{duration_str}`", 
                inline=True
            )

        embed.set_footer(text="RVDiA Music System • SoundCloud & Uploads")
        await ctx.reply(embed=embed)

    @commands.hybrid_command(
        name="queue", 
        aliases=["q"], 
        description="Show the current music queue."
    )
    @check_blacklist()
    async def queue(self, ctx: commands.Context):
        """
        Show the current music queue.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.current_track and not state.queue:
            msg = i18n.get(lang, "music.queue_empty") or "The queue is currently empty!"
            return await ctx.reply(f"ℹ️ {msg}")

        embed = discord.Embed(
            title=i18n.get(lang, "music.queue_title") or "Music Queue",
            color=self.bot.color
        )

        # Current track
        if state.current_track:
            np_title = state.current_track['title']
            np_val = f"**[{np_title}]({self_url_fallback(state.current_track)})** (Requested by: `{state.current_track['requester']}`)"
            embed.add_field(
                name=f"▶️ {i18n.get(lang, 'music.now_playing_title') or 'Now Playing'}", 
                value=np_val, 
                inline=False
            )

        # Queue list
        if state.queue:
            queue_lines = []
            for idx, track in enumerate(state.queue[:10], start=1):
                queue_lines.append(f"{idx}. **[{track['title']}]({self_url_fallback(track)})** (Requested by: `{track['requester']}`)")
            
            if len(state.queue) > 10:
                more_tracks = len(state.queue) - 10
                queue_lines.append(f"\n*...and {more_tracks} more tracks in queue*")

            queue_title = i18n.get(lang, "music.field_upcoming") or "Upcoming Tracks"
            embed.add_field(name=f"📋 {queue_title}", value="\n".join(queue_lines), inline=False)
        else:
            embed.add_field(
                name="📋 Upcoming Tracks", 
                value=i18n.get(lang, "music.no_upcoming") or "No upcoming songs in the queue.", 
                inline=False
            )

        await ctx.reply(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id != self.bot.user.id:
            return

        state = self.states.get(member.guild.id)
        if not state:
            return

        # If the bot is actively trying to connect, ignore intermediate voice state changes
        if state.connecting:
            return

        # Bot disconnected from voice channel
        if before.channel and not after.channel:
            if state.voice_client and state.voice_client.is_connected():
                return
            await state.disconnect()


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
