import asyncio
import discord
import yt_dlp
import re
import time
import random
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

async def extract_info(query: str, process: bool = True) -> dict:
    """
    Extract video/audio metadata using yt-dlp in a separate thread.
    """
    return await asyncio.to_thread(ytdl.extract_info, query, download=False, process=process)


async def extract_spotify_metadata(url: str) -> dict:
    """
    Extract track metadata (title, artist, duration) from a Spotify track URL.
    """
    match = re.search(r'track/([a-zA-Z0-9]+)', url)
    if not match:
        raise ValueError("Invalid Spotify track URL")
    
    track_id = match.group(1)
    embed_url = f"https://open.spotify.com/embed/track/{track_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    
    def fetch():
        import urllib.request
        import json
        req = urllib.request.Request(embed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
        
        script_match = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not script_match:
            raise ValueError("Failed to extract Spotify metadata from embed page")
            
        data = json.loads(script_match.group(1))
        props = data.get('props', {}).get('pageProps', {})
        state = props.get('state', {})
        entity = state.get('data', {}).get('entity', {})
        if not entity or entity.get('type') != 'track':
            raise ValueError("Track not found or restricted")
            
        title = entity.get('name')
        artists = [a.get('name') for a in entity.get('artists', []) if a.get('name')]
        duration_ms = entity.get('duration', 0)
        
        return {
            'title': title,
            'artists': artists,
            'duration': duration_ms / 1000.0
        }
        
    return await asyncio.to_thread(fetch)


def parse_time_string(time_str: str) -> int:
    """
    Parses a time string like '1m30s', '2m', '45s', '1:30', or raw seconds '90' into integer seconds.
    """
    time_str = time_str.strip().lower()
    
    if ':' in time_str:
        parts = time_str.split(':')
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            pass
            
    pattern = re.compile(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?')
    match = pattern.match(time_str)
    if match and any(match.groups()):
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
        return hours * 3600 + minutes * 60 + seconds
        
    try:
        return int(time_str)
    except ValueError:
        raise ValueError("Invalid time format. Use '30s', '2m', '1:30', or plain seconds.")



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
        self.empty_check_task = None
        self.seeking = False
        self.seek_position = 0.0
        self.elapsed_time = 0.0
        self.last_resume_time = 0.0
        self.is_paused = False
        self.loop_mode = "off"  # "off", "single", "all"
        self.skip_requested = False

    def start_loop(self):
        if not self.play_loop_task or self.play_loop_task.done():
            self.play_loop_task = asyncio.create_task(self.play_loop())

    async def play_loop(self):
        if not self.empty_check_task or self.empty_check_task.done():
            self.empty_check_task = asyncio.create_task(self.channel_empty_loop())

        try:
            while self.voice_client and self.voice_client.is_connected():
                self.play_next_event.clear()
                
                if not self.queue and not self.seeking and not (self.loop_mode == "single" and self.current_track):
                    try:
                        # Disconnect if idle for 5 minutes
                        await asyncio.wait_for(self.wait_for_queue(), timeout=300.0)
                    except asyncio.TimeoutError:
                        await self.disconnect()
                        break

                if not self.voice_client or not self.voice_client.is_connected():
                    break

                if not self.seeking and not (self.loop_mode == "single" and self.current_track) and not self.queue:
                    continue

                new_track_loaded = False
                if self.seeking:
                    self.seeking = False
                elif self.loop_mode == "single" and self.current_track and not self.skip_requested:
                    self.seek_position = 0.0
                    self.elapsed_time = 0.0
                    self.last_resume_time = time.time()
                    self.is_paused = False
                else:
                    if self.skip_requested:
                        self.skip_requested = False
                    if self.loop_mode == "all" and self.current_track:
                        self.queue.append(self.current_track)
                    self.current_track = self.queue.pop(0) if self.queue else None
                    self.seek_position = 0.0
                    self.elapsed_time = 0.0
                    self.last_resume_time = time.time()
                    self.is_paused = False
                    new_track_loaded = True

                if not self.current_track:
                    continue
                
                try:
                    url_to_play = self.current_track['url']
                    # Resolve streaming URL lazily if it's not a direct streaming URL
                    if "soundcloud.com" in url_to_play or "api.soundcloud.com" in url_to_play:
                        track_info = await extract_info(url_to_play, process=True)
                        url_to_play = track_info['url']

                    options = FFMPEG_OPTIONS.copy()
                    if self.seek_position > 0:
                        options['before_options'] = f"{options['before_options']} -ss {int(self.seek_position)}"

                    source = discord.FFmpegPCMAudio(url_to_play, **options)
                    transformer = discord.PCMVolumeTransformer(source)
                    
                    self.last_resume_time = time.time()
                    # Set up thread-safe callback to trigger the next song when current finishes
                    self.voice_client.play(
                        transformer, 
                        after=lambda e: self.bot.loop.call_soon_threadsafe(self.play_next_event.set)
                    )
                    
                    # Send Now Playing embed to the requesting channel
                    if new_track_loaded:
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
        finally:
            await self.disconnect()

    def is_channel_empty(self) -> bool:
        if not self.voice_client or not self.voice_client.channel:
            return True
        non_bot_members = [m for m in self.voice_client.channel.members if not m.bot]
        return len(non_bot_members) == 0

    async def channel_empty_loop(self):
        await asyncio.sleep(10.0)
        alone_time = 0
        while self.voice_client and self.voice_client.is_connected():
            if self.is_channel_empty():
                alone_time += 10
                if alone_time >= 60:
                    await self.disconnect()
                    break
            else:
                alone_time = 0
            await asyncio.sleep(10.0)

    async def wait_for_queue(self):
        while not self.queue and self.voice_client and self.voice_client.is_connected():
            await asyncio.sleep(1.0)

    def pause_playback(self):
        if self.voice_client and self.voice_client.is_playing() and not self.is_paused:
            self.elapsed_time += time.time() - self.last_resume_time
            self.is_paused = True
            self.voice_client.pause()

    def resume_playback(self):
        if self.voice_client and self.voice_client.is_paused():
            self.last_resume_time = time.time()
            self.is_paused = False
            self.voice_client.resume()

    def get_current_time(self) -> float:
        if not self.current_track:
            return 0.0
        current_time = self.elapsed_time
        if self.voice_client and self.voice_client.is_playing() and not self.is_paused:
            current_time += time.time() - self.last_resume_time
        return current_time

    async def seek(self, target_time: float):
        if not self.current_track or not self.voice_client:
            return
        
        dur = self.current_track.get('duration', 0)
        if dur:
            target_time = max(0.0, min(float(dur), target_time))
        else:
            target_time = max(0.0, target_time)
            
        self.seeking = True
        self.seek_position = target_time
        self.elapsed_time = target_time
        self.last_resume_time = time.time()
        self.is_paused = False
        
        self.voice_client.stop()

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

        current_task = asyncio.current_task()
        if self.play_loop_task and self.play_loop_task != current_task:
            self.play_loop_task.cancel()
        self.play_loop_task = None

        if self.empty_check_task and self.empty_check_task != current_task:
            self.empty_check_task.cancel()
        self.empty_check_task = None

        self.queue.clear()
        self.current_track = None
        self.seeking = False
        self.seek_position = 0.0
        self.elapsed_time = 0.0
        self.last_resume_time = 0.0
        self.is_paused = False



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
        voice_client = ctx.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            if state.connecting:
                for _ in range(10):
                    voice_client = ctx.guild.voice_client
                    if voice_client and voice_client.is_connected():
                        break
                    await asyncio.sleep(0.5)

            voice_client = ctx.guild.voice_client
            if not voice_client or not voice_client.is_connected():
                state.connecting = True
                try:
                    if voice_client:
                        try:
                            await voice_client.disconnect(force=True)
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

            # Check if it is a Spotify track link
            is_spotify = re.search(r'spotify\.com/track/', query_or_url, re.IGNORECASE)
            spotify_url = None
            spotify_duration = 0
            
            if is_spotify:
                spotify_url = query_or_url
                try:
                    meta = await extract_spotify_metadata(query_or_url)
                    title = meta['title']
                    artists_str = ", ".join(meta['artists'])
                    search_query = f"{title} {artists_str}".strip()
                    spotify_duration = int(meta['duration'])
                    is_url = False
                    query_or_url = search_query
                    auto_select_first = True
                except Exception as e:
                    return await ctx.reply(f"❌ Failed to resolve Spotify link: `{str(e)}`")
            else:
                is_url = query_or_url.startswith('http://') or query_or_url.startswith('https://')
                auto_select_first = False

            search_query = query_or_url if is_url else (f"scsearch5:{query_or_url}" if auto_select_first else f"scsearch10:{query_or_url}")

            try:
                # Query SoundCloud
                info = await extract_info(search_query, process=(is_url or auto_select_first))
                if not info:
                    msg = i18n.get(lang, "music.no_results") or "No results found on SoundCloud!"
                    return await ctx.reply(f"❌ {msg}")

                if 'entries' in info and not is_url and not auto_select_first:
                    entries = info['entries']
                    if not isinstance(entries, list):
                        entries = list(entries)
                    entries = entries[:10]
                    if not entries:
                        msg = i18n.get(lang, "music.no_results") or "No results found on SoundCloud!"
                        return await ctx.reply(f"❌ {msg}")

                    embed = discord.Embed(
                        title=i18n.get(lang, "music.search_results_title") or "SoundCloud Search Results",
                        description=i18n.get(lang, "music.search_results_desc") or "Please select one or more songs from the dropdown menu to queue them:",
                        color=self.bot.color
                    )

                    for idx, entry in enumerate(entries, start=1):
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

                    view = SoundCloudSelectView(ctx, ctx.author.id, entries, state, lang)
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
                        'original_url': spotify_url or info.get('webpage_url', query_or_url),
                        'duration': spotify_duration or info.get('duration', 0),
                        'requester': str(ctx.author),
                        'requester_id': ctx.author.id,
                        'channel': ctx.channel
                    }
            except Exception as e:
                return await ctx.reply(f"❌ Failed to load audio: `{str(e)}`")

        if track:
            # Deafen RVDiA upon entry
            voice_client = ctx.guild.voice_client
            if not voice_client or not voice_client.is_connected():
                if state.connecting:
                    for _ in range(10):
                        voice_client = ctx.guild.voice_client
                        if voice_client and voice_client.is_connected():
                            break
                        await asyncio.sleep(0.5)

                voice_client = ctx.guild.voice_client
                if not voice_client or not voice_client.is_connected():
                    state.connecting = True
                    try:
                        if voice_client:
                            try:
                                await voice_client.disconnect(force=True)
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

        state.skip_requested = True
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

        state.pause_playback()
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

        state.resume_playback()
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

    @commands.hybrid_command(
        name="seek",
        description="Seek to a specific timestamp in the current song."
    )
    @app_commands.describe(position="Target timestamp (e.g. '1:30', '45s', '90')")
    @check_blacklist()
    async def seek(self, ctx: commands.Context, position: str):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.current_track or not state.voice_client:
            msg = i18n.get(lang, "music.not_playing") or "Not currently playing any music!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        try:
            target_seconds = parse_time_string(position)
        except ValueError as e:
            return await ctx.reply(f"❌ {str(e)}", ephemeral=True)

        await state.seek(target_seconds)
        
        mins, secs = divmod(target_seconds, 60)
        formatted_time = f"{mins:02d}:{secs:02d}"
        msg = f"Seeked to `{formatted_time}`!"
        await ctx.reply(f"🔍 {msg}")

    @commands.hybrid_command(
        name="forward",
        description="Fast forward the current song by a duration."
    )
    @app_commands.describe(duration="Time to skip forward (e.g. '30s', '1m', '15')")
    @check_blacklist()
    async def forward(self, ctx: commands.Context, duration: str = "15s"):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.current_track or not state.voice_client:
            msg = i18n.get(lang, "music.not_playing") or "Not currently playing any music!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        try:
            offset = parse_time_string(duration)
        except ValueError as e:
            return await ctx.reply(f"❌ {str(e)}", ephemeral=True)

        current_time = state.get_current_time()
        target_time = current_time + offset

        await state.seek(target_time)
        msg = f"Fast forwarded by `{duration}`!"
        await ctx.reply(f"⏩ {msg}")

    @commands.hybrid_command(
        name="rewind",
        description="Rewind the current song by a duration."
    )
    @app_commands.describe(duration="Time to rewind (e.g. '30s', '1m', '15')")
    @check_blacklist()
    async def rewind(self, ctx: commands.Context, duration: str = "15s"):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.current_track or not state.voice_client:
            msg = i18n.get(lang, "music.not_playing") or "Not currently playing any music!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        try:
            offset = parse_time_string(duration)
        except ValueError as e:
            return await ctx.reply(f"❌ {str(e)}", ephemeral=True)

        current_time = state.get_current_time()
        target_time = max(0.0, current_time - offset)

        await state.seek(target_time)
        msg = f"Rewound by `{duration}`!"
        await ctx.reply(f"⏪ {msg}")

    @commands.hybrid_command(
        name="loop",
        description="Set the loop/repeat mode."
    )
    @app_commands.describe(mode="Repeat mode ('off', 'single', 'all')")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Repeat One (Single)", value="single"),
        app_commands.Choice(name="Repeat All (Queue)", value="all")
    ])
    @check_blacklist()
    async def loop(self, ctx: commands.Context, mode: str = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        
        if not mode:
            current = state.loop_mode
            if current == "off":
                mode = "single"
            elif current == "single":
                mode = "all"
            else:
                mode = "off"

        state.loop_mode = mode
        
        mode_icons = {
            "off": "❌",
            "single": "🔂",
            "all": "🔁"
        }
        
        mode_names = {
            "off": i18n.get(lang, "music.loop_off") or "Loop Off",
            "single": i18n.get(lang, "music.loop_single") or "Repeat One",
            "all": i18n.get(lang, "music.loop_all") or "Repeat All"
        }
        
        await ctx.reply(f"{mode_icons[mode]} Loop mode set to: **{mode_names[mode]}**")

    @commands.hybrid_command(
        name="shuffle",
        description="Shuffle the current music queue."
    )
    @check_blacklist()
    async def shuffle(self, ctx: commands.Context):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        state = self.get_state(ctx.guild.id)
        if not state.queue:
            return await ctx.reply("❌ The queue is empty, nothing to shuffle.")

        random.shuffle(state.queue)
        await ctx.reply("🔀 Shuffled the queue!")

    @commands.hybrid_command(
        name="surprise",
        description="Queue random tracks based on a genre or tag!"
    )
    @app_commands.describe(
        genre="Selected genre (e.g. lofi, pop, rock, jazz, edm, anime) or custom tag"
    )
    @app_commands.choices(genre=[
        app_commands.Choice(name="Lofi / Chill", value="lofi"),
        app_commands.Choice(name="Pop", value="pop"),
        app_commands.Choice(name="EDM / Electronic", value="edm"),
        app_commands.Choice(name="Rock", value="rock"),
        app_commands.Choice(name="Jazz", value="jazz"),
        app_commands.Choice(name="Anime", value="anime"),
        app_commands.Choice(name="Gaming", value="gaming")
    ])
    @check_blacklist()
    async def surprise(self, ctx: commands.Context, genre: str):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if not ctx.author.voice:
            msg = i18n.get(lang, "music.no_voice_channel") or "You must be in a voice channel to use this command!"
            return await ctx.reply(f"⚠️ {msg}", ephemeral=True)

        await ctx.defer()
        state = self.get_state(ctx.guild.id)
        
        search_query = f"scsearch15:{genre}"
        try:
            info = await extract_info(search_query, process=True)
            if not info or 'entries' not in info or not info['entries']:
                return await ctx.reply("❌ No songs found for that genre!")
                
            entries = info['entries']
            selected_entries = random.sample(entries, min(len(entries), 5))
            
            voice_client = ctx.guild.voice_client
            if not voice_client or not voice_client.is_connected():
                state.connecting = True
                try:
                    if voice_client:
                        try:
                            await voice_client.disconnect(force=True)
                        except Exception:
                            pass
                    state.voice_client = None
                    state.voice_client = await ctx.author.voice.channel.connect(self_deaf=True)
                    state.start_loop()
                finally:
                    state.connecting = False
            
            queued_songs = []
            for entry in selected_entries:
                track = {
                    'title': entry.get('title', 'SoundCloud Track'),
                    'url': entry['url'],
                    'original_url': entry.get('webpage_url'),
                    'duration': entry.get('duration', 0),
                    'requester': str(ctx.author),
                    'requester_id': ctx.author.id,
                    'channel': ctx.channel
                }
                state.queue.append(track)
                queued_songs.append(track['title'])
                
            state.start_loop()
            
            titles_str = "\n".join(f"• **{title}**" for title in queued_songs)
            embed = discord.Embed(
                title=f"🎲 Surprise Me: {genre.capitalize()}",
                description=f"Queued {len(queued_songs)} random songs:\n{titles_str}",
                color=self.bot.color
            )
            await ctx.reply(embed=embed)
            
        except Exception as e:
            return await ctx.reply(f"❌ Surprise failed: `{str(e)}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
