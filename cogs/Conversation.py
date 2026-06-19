import discord
import os
import asyncio
import pytz
import logging
import random
from google import genai
from google.genai import types
from datetime import datetime
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, button
from PIL import Image
from scripts.main import smart_title_case, check_blacklist, AIClient, db, get_commands_context, clean_truncate
from scripts.ai.memory import memory_manager
from scripts.ai.chat import chat_service
from scripts.utils.error_logger import format_error_report
from scripts.utils.search import search_web, search_images, format_search_results
from scripts.utils.i18n import i18n


class Regenerate_Answer_Button(View):
    def __init__(self, user_id: int, last_question: str, initial_response: str, image_bytes: bytes = None, mime_type: str = None, lang: str = "en"):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.last_question = last_question
        self.responses = [initial_response]
        self.image_bytes = image_bytes
        self.mime_type = mime_type
        self.current_page = 0
        self.lang = lang
        self.show_vote = random.random() < 0.1  # 10% chance to show vote button
        
        self.update_buttons()

    def update_buttons(self):
        # Clear existing buttons to rebuild with correct states
        self.clear_items()
        
        # 1. Back Button
        back_btn = Button(
            emoji='⬅️', 
            style=discord.ButtonStyle.gray, 
            disabled=(self.current_page == 0),
            custom_id="prev_page"
        )
        back_btn.callback = self.prev_page
        self.add_item(back_btn)
        
        # 2. Regenerate Button (Always in the middle)
        regen_label = chat_service.get_translation(self.lang, "button_regenerate")
        regen_btn = Button(
            label=regen_label, 
            emoji='🔁', 
            style=discord.ButtonStyle.blurple,
            custom_id="regenerate"
        )
        regen_btn.callback = self.regenerate
        self.add_item(regen_btn)
        
        # 3. Next Button
        next_btn = Button(
            emoji='➡️', 
            style=discord.ButtonStyle.gray, 
            disabled=(self.current_page == len(self.responses) - 1),
            custom_id="next_page"
        )
        next_btn.callback = self.next_page
        self.add_item(next_btn)
        
        # 4. Vote Button (Rare)
        if self.show_vote:
            vote_me = Button(
                label='Vote for RVDiA!', 
                emoji='<:rvdia:1140812479883128862>',
                style=discord.ButtonStyle.green, 
                url='https://top.gg/bot/957471338577166417/vote'
            )
            self.add_item(vote_me)

    async def update_view(self, interaction: discord.Interaction):
        self.update_buttons()
        
        display_message = self.last_question
        if len(display_message) > 256:
            display_message = display_message[:253] + '...'

        embed = discord.Embed(
            title=smart_title_case(display_message), 
            color=interaction.user.color, 
            timestamp=interaction.message.created_at
        )
        embed.description = self.responses[self.current_page]
        embed.set_author(name=interaction.user)
        
        footer_text = chat_service.get_translation(
            self.lang, 
            "page_footer_template", 
            current=self.current_page + 1, 
            total=len(self.responses)
        )
        embed.set_footer(text=footer_text)
        
        # Check if response has an image link
        import re
        img_match = re.search(r'https?://\S+\.(?:jpg|jpeg|png|gif|webp)', self.responses[self.current_page])
        if img_match:
            embed.set_image(url=img_match.group(0))

        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            err_msg = chat_service.get_translation(self.lang, "error_not_your_button")
            return await interaction.response.send_message(err_msg, ephemeral=True)
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_view(interaction)
        else:
            await interaction.response.defer()

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            err_msg = chat_service.get_translation(self.lang, "error_not_your_button")
            return await interaction.response.send_message(err_msg, ephemeral=True)
        if self.current_page < len(self.responses) - 1:
            self.current_page += 1
            await self.update_view(interaction)
        else:
            await interaction.response.defer()

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'message'):
            await self.message.edit(view=self)

    async def regenerate(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            err_msg = chat_service.get_translation(self.lang, "error_not_your_button")
            return await interaction.response.send_message(err_msg, ephemeral=True)
        try:
            await interaction.response.defer()
        except discord.NotFound:
            pass
        
        async with interaction.channel.typing():
            user_id = interaction.user.id
            
            try:
                cmd_ctx = get_commands_context(interaction.client)
                res = await chat_service.generate_chat_response(
                    user_id=self.user_id,
                    user_name=str(interaction.user),
                    message=self.last_question,
                    lang=self.lang,
                    image_bytes=self.image_bytes,
                    mime_type=self.mime_type,
                    bot_commands_context=cmd_ctx
                )
                
                AI_response = res["response"]
                
                if AI_response and AI_response not in self.responses:
                    self.responses.append(AI_response)
                    self.current_page = len(self.responses) - 1
                
                await self.update_view(interaction)
            except Exception as e:
                logging.error(f"Error in Regenerate_Answer_Button callback: {e}")
                fallback_msg = i18n.get(self.lang, "chat.regen_connection_error")
                await interaction.channel.send(fallback_msg)


class MemoryManagerView(View):
    def __init__(self, user_id: int, memories: list, lang: str = "en"):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.lang = lang
        
        # Add Select Menu
        options = []
        for i, mem in enumerate(memories[:25]): # Max 25 options
            label = mem.content[:90] + "..." if len(mem.content) > 90 else mem.content
            options.append(discord.SelectOption(
                label=f"{i+1}. {label}",
                value=str(mem.id),
                description=f"Type: Memory | {mem.createdAt.strftime('%d/%m/%Y')}"
            ))
            
        self.select = discord.ui.Select(
            placeholder=i18n.get(lang, "chat.memory_placeholder_delete"),
            min_values=1,
            max_values=len(options),
            options=options
        )
        self.select.callback = self.delete_memories
        self.add_item(self.select)

    async def delete_memories(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(i18n.get(self.lang, "chat.memory_not_yours"), ephemeral=True)
            
        await interaction.response.defer()
        selected_ids = self.select.values
        
        try:
            await db.memory.delete_many(where={
                'id': {'in': [int(sid) for sid in selected_ids]},
                'userId': self.user_id
            })
            msg = i18n.get(self.lang, "chat.memory_deleted_success", count=len(selected_ids))
            await interaction.followup.send(msg, ephemeral=True)
            await interaction.message.delete()
        except Exception as e:
            msg = i18n.get(self.lang, "chat.memory_delete_failed", error=str(e))
            await interaction.followup.send(msg, ephemeral=True)

class MemoryPersistenceView(View):
    def __init__(self, user_id: int, memories: list, lang: str = "en"):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.lang = lang
        
        # Add Select Menu
        options = []
        for i, mem in enumerate(memories[:25]): # Max 25 options
            prefix = "📌 " if getattr(mem, 'isPersistent', False) else "⏳ "
            label = mem.content[:90] + "..." if len(mem.content) > 90 else mem.content
            options.append(discord.SelectOption(
                label=f"{i+1}. {prefix}{label}",
                value=str(mem.id),
                description="Klik untuk toggle status Permanent/Temporary"
            ))
            
        self.select = discord.ui.Select(
            placeholder=i18n.get(lang, "chat.memory_placeholder_toggle"),
            min_values=1,
            max_values=len(options),
            options=options
        )
        self.select.callback = self.toggle_persistence
        self.add_item(self.select)

    async def toggle_persistence(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(i18n.get(self.lang, "chat.memory_not_yours"), ephemeral=True)
            
        await interaction.response.defer()
        selected_ids = self.select.values
        
        try:
            toggled_count = 0
            for sid in selected_ids:
                res = await memory_manager.toggle_memory_persistence(int(sid), self.user_id)
                if res is not False:
                    toggled_count += 1
                
            msg = i18n.get(self.lang, "chat.memory_toggle_success", count=toggled_count)
            await interaction.followup.send(msg, ephemeral=True)
            await interaction.message.delete()
        except Exception as e:
            msg = i18n.get(self.lang, "chat.memory_toggle_failed", error=str(e))
            await interaction.followup.send(msg, ephemeral=True)

class Conversation(commands.Cog):
    """
    Kategori khusus untuk mengobrol dengan RVDiA.
    """
    def __init__(self, bot):
        self.bot = bot
        self.wither_memories_task.start()

    def cog_unload(self):
        self.wither_memories_task.cancel()

    @tasks.loop(hours=24)
    async def wither_memories_task(self):
        """Background task to clean up withered (expired) memories every 24 hours."""
        try:
            deleted = await memory_manager.clean_withered_memories(days=7)
            logging.info(f"Memory Cleanup: Deleted {deleted} withered memories older than 7 days.")
        except Exception as e:
            logging.error(f"Error in wither_memories_task: {e}")

    @wither_memories_task.before_loop
    async def before_wither_memories_task(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(
        aliases=['ask', 'chatbot', 'tanya'],
        description='Ask me questions or command me to do something!'
    )
    @app_commands.describe(message='What do you want to ask?', attachment='Attach a file (PDF, image, or text)')
    @commands.cooldown(type=commands.BucketType.user, per=2, rate=1)
    @check_blacklist()
    async def chat(self, ctx: commands.Context, *, message: str = "", attachment: discord.Attachment = None):
        """
        Ask me questions or command me to do something!
        """
        try:
            await ctx.defer()
        except discord.NotFound:
            pass
            
        async with ctx.channel.typing():
            user_id = ctx.author.id
            
            # Resolve attachment
            target_attachment = attachment
            if not target_attachment and ctx.message and ctx.message.attachments:
                target_attachment = ctx.message.attachments[0]
                
            # Query language settings
            user_settings = await db.usersettings.find_unique(where={'userId': user_id})
            lang = user_settings.lang if user_settings else "en"

            if not message and not target_attachment:
                reply_msg = i18n.get(lang, "chat.chat_empty_prompt")
                try:
                    return await ctx.reply(reply_msg)
                except discord.HTTPException:
                    return await ctx.send(reply_msg)

            # Resolve DB message placeholder for memory database
            db_message = message if message else f"[Mengirim file: {target_attachment.filename}]"
            full_message = message

            # Parse attachments
            attachment_text = ""
            image_raw_bytes = None
            image_mime_type = None
            
            if target_attachment:
                from scripts.image.attachment import handle_attachment
                att_res = await handle_attachment(target_attachment)
                if att_res["text"]:
                    attachment_text = att_res["text"]
                if att_res["image_bytes"]:
                    image_raw_bytes = att_res["image_bytes"]
                    image_mime_type = att_res["mime_type"]

            if attachment_text:
                full_message = f"{attachment_text}\nUser message: {message}"

            try:
                cmd_ctx = get_commands_context(self.bot)
                res = await chat_service.generate_chat_response(
                    user_id=user_id,
                    user_name=str(ctx.author),
                    message=full_message if attachment_text else message,
                    lang=lang,
                    image_bytes=image_raw_bytes,
                    mime_type=image_mime_type,
                    bot_commands_context=cmd_ctx
                )
                
                AI_response = res["response"]
            except Exception as e:
                logging.error(f"Error in chat command: {e}")
                try:
                    error_channel = ctx.bot.get_channel(int(os.getenv("errorchannel")))
                    if error_channel:
                        embed = format_error_report(e, context=f"Chat Command (User: {ctx.author})")
                        await error_channel.send(embed=embed)
                except Exception as log_e:
                    logging.error(f"Failed to send error report: {log_e}")
                
                AI_response = i18n.get(lang, "chat.chat_fallback_error")
            
            display_message = db_message
            if len(display_message) > 256:
                display_message = display_message[:253] + '...'
 
            embed = discord.Embed(
                title=smart_title_case(display_message), 
                color=ctx.author.color, 
                timestamp=ctx.message.created_at
            )
            embed.description = AI_response
            embed.set_author(name=ctx.author)
            
            footer_text = chat_service.get_translation(lang, "help_suggest_reply")
            embed.set_footer(text=footer_text)
            
            # Check if response has an image link
            import re
            img_match = re.search(r'https?://\S+\.(?:jpg|jpeg|png|gif|webp)', AI_response)
            if img_match:
                embed.set_image(url=img_match.group(0))
 
            regenerate_button = Regenerate_Answer_Button(user_id, full_message, AI_response, image_raw_bytes, image_mime_type, lang=lang)
            try:
                return await ctx.reply(embed=embed, view=regenerate_button)
            except discord.HTTPException as e:
                if e.code == 50027 or e.status == 401:
                    return await ctx.send(embed=embed, view=regenerate_button)

    @commands.hybrid_group(
        name="memory",
        aliases=["memori", "history"],
        description="Manage your chat memories with RVDiA."
    )
    @check_blacklist()
    async def memory(self, ctx: commands.Context):
        """
        Manage your chat memories with RVDiA.
        """
        if ctx.invoked_subcommand is None:
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"
            await ctx.send(i18n.get(lang, "chat.memory_info_guide"))

    @memory.command(name="clear", description="Clear your entire chat memory history.")
    async def memory_clear(self, ctx: commands.Context):
        """
        Clear your entire chat memory history.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"
        confirm_view = View(timeout=30)
        
        async def confirm_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message(i18n.get(lang, "chat.memory_clear_not_author"), ephemeral=True)
            
            await interaction.response.defer()
            await db.memory.delete_many(where={'userId': ctx.author.id})
            await interaction.followup.send(i18n.get(lang, "chat.memory_clear_success"))
            await interaction.message.delete()

        confirm_btn = Button(label=i18n.get(lang, "chat.memory_clear_confirm_btn"), style=discord.ButtonStyle.danger)
        confirm_btn.callback = confirm_callback
        confirm_view.add_item(confirm_btn)
        
        await ctx.send(i18n.get(lang, "chat.memory_clear_prompt"), view=confirm_view)

    @memory.command(name="manage", description="Select specific memories to delete.")
    async def memory_manage(self, ctx: commands.Context):
        """
        Select specific memories to delete.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"
        memories = await db.memory.find_many(
            where={'userId': ctx.author.id},
            order={'createdAt': 'desc'},
            take=25
        )
        
        if not memories:
            return await ctx.send(i18n.get(lang, "chat.memory_manage_empty"))
            
        view = MemoryManagerView(ctx.author.id, memories, lang=lang)
        await ctx.send(i18n.get(lang, "chat.memory_manage_list"), view=view)

    @memory.command(name="persist", description="Select memories to keep permanently or let them wither over time.")
    async def memory_persist(self, ctx: commands.Context):
        """
        Select memories to keep permanently or let them wither over time.
        """
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"
        memories = await db.memory.find_many(
            where={'userId': ctx.author.id},
            order={'createdAt': 'desc'},
            take=25
        )
        
        if not memories:
            return await ctx.send(i18n.get(lang, "chat.memory_manage_empty"))
            
        view = MemoryPersistenceView(ctx.author.id, memories, lang=lang)
        await ctx.send(i18n.get(lang, "chat.memory_persist_list"), view=view)

    @commands.hybrid_group(
        name="settings",
        aliases=["setelan", "config"],
        description="Manage RVDiA settings."
    )
    @check_blacklist()
    async def settings(self, ctx: commands.Context):
        """
        Manage RVDiA settings.
        """
        if ctx.invoked_subcommand is None:
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"
            await ctx.send(i18n.get(lang, "chat.settings_info_guide"))

    @settings.command(name="language", description="Change chat language settings between Indonesian and English.")
    @app_commands.describe(lang="Select your preferred language")
    @app_commands.choices(lang=[
        app_commands.Choice(name="Indonesia 🇮🇩", value="id"),
        app_commands.Choice(name="English 🇺🇸", value="en")
    ])
    async def settings_language(self, ctx: commands.Context, lang: str):
        """
        Change chat language settings.
        """
        user_id = ctx.author.id
        await db.usersettings.upsert(
            where={'userId': user_id},
            data={
                'create': {'userId': user_id, 'lang': lang},
                'update': {'lang': lang}
            }
        )
        title = chat_service.get_translation(lang, "language_changed_title")
        desc = chat_service.get_translation(lang, "language_changed_desc")
        embed = discord.Embed(
            title=title,
            description=desc,
            color=ctx.author.color or 0x86273d,
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        aliases=['create'],
        description='Generate anime artwork using the MeinaMix V11 model!'
    )
    @app_commands.describe(
        prompt='Prompt to describe what to generate',
        aspect_ratio='Choose image aspect ratio (Default: 1:1)',
        steps='Number of inference steps (Default: Balanced)',
        cfg_scale='How closely the AI follows the prompt (Default: 7.0)',
        scheduler='Sampling scheduler method (Default: DPM++ 2M Karras)',
        upscale='Upscale resolution using Swin2SR 2x (Default: No)',
        negative_prompt='What to exclude from the image (Optional)'
    )
    @app_commands.choices(
        aspect_ratio=[
            app_commands.Choice(name="1:1 (Square)", value="1:1"),
            app_commands.Choice(name="3:2 (Landscape)", value="3:2"),
            app_commands.Choice(name="2:3 (Portrait)", value="2:3"),
            app_commands.Choice(name="16:9 (Widescreen)", value="16:9"),
            app_commands.Choice(name="9:16 (Vertical)", value="9:16")
        ],
        steps=[
            app_commands.Choice(name="Fast (15 steps)", value="15"),
            app_commands.Choice(name="Balanced (25 steps)", value="25"),
            app_commands.Choice(name="Quality (35 steps)", value="35"),
            app_commands.Choice(name="Premium (50 steps)", value="50")
        ],
        cfg_scale=[
            app_commands.Choice(name="Creative (5.0)", value="5.0"),
            app_commands.Choice(name="Default (7.0)", value="7.0"),
            app_commands.Choice(name="Strict (9.0)", value="9.0"),
            app_commands.Choice(name="Very Strict (12.0)", value="12.0")
        ],
        scheduler=[
            app_commands.Choice(name="DPM++ 2M Karras (Crisp/Detail)", value="dpm++_2m_karras"),
            app_commands.Choice(name="Euler a (Ancestral/Soft)", value="euler_a"),
            app_commands.Choice(name="DPM++ SDE Karras (Realistic/Rich)", value="dpm++_sde_karras"),
            app_commands.Choice(name="DDIM (Classic)", value="ddim")
        ],
        upscale=[
            app_commands.Choice(name="Yes (Swin2SR 2x)", value="yes"),
            app_commands.Choice(name="No", value="no")
        ]
    )
    @commands.cooldown(type=commands.BucketType.default, per=60, rate=4)
    @check_blacklist()
    async def generate(
        self, 
        ctx: commands.Context, 
        aspect_ratio: str = "1:1", 
        steps: str = "25", 
        cfg_scale: str = "7.0", 
        scheduler: str = "dpm++_2m_karras", 
        upscale: str = "no",
        negative_prompt: str = None, 
        *, 
        prompt: str
    ):
        """
        Generate anime artwork using the MeinaMix V11 model!
        """
        import io
        import aiohttp
        from scripts.utils.errors import ArtistOffline, GenerationDeclined, GenerationFailed, NSFWBlocked, GenerationTimeout
        
        # Reconstruct prompt for prefix command if choices parsing was bypassed
        if ctx.interaction is None:
            valid_ratios = ["1:1", "3:2", "2:3", "16:9", "9:16"]
            valid_steps = ["15", "25", "35", "50"]
            valid_cfgs = ["5.0", "7.0", "9.0", "12.0"]
            valid_schedulers = ["euler_a", "dpm++_2m_karras", "dpm++_sde_karras", "ddim"]
            valid_upscale = ["yes", "no"]
            
            if aspect_ratio in valid_ratios and steps in valid_steps and cfg_scale in valid_cfgs and scheduler in valid_schedulers and upscale in valid_upscale:
                pass
            else:
                parts = []
                if aspect_ratio: parts.append(aspect_ratio)
                if steps: parts.append(steps)
                if cfg_scale: parts.append(cfg_scale)
                if scheduler: parts.append(scheduler)
                if upscale: parts.append(upscale)
                if negative_prompt: parts.append(negative_prompt)
                if prompt: parts.append(prompt)
                prompt = " ".join(parts)
                aspect_ratio = "1:1"
                steps = "25"
                cfg_scale = "7.0"
                scheduler = "dpm++_2m_karras"
                upscale = "no"
                negative_prompt = None
                
        # Map aspect ratios keeping max dimension capped at 512px (divisible by 8)
        ratio_map = {
            "1:1": (512, 512),
            "3:2": (512, 344),
            "2:3": (344, 512),
            "16:9": (512, 288),
            "9:16": (288, 512)
        }
        width, height = ratio_map.get(aspect_ratio, (512, 512))
        
        api_url = os.getenv("LAPTOP_API_URL")
        api_key = os.getenv("LAPTOP_API_KEY")
        
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if not api_url or not api_key:
            return await ctx.reply(i18n.get(lang, "chat.generate_not_configured"))
            
        try:
            await ctx.defer()
        except discord.NotFound:
            pass
            
        headers = {
            "X-API-Key": api_key
        }
        
        # 1. Ping the server
        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(f"{api_url}/ping", timeout=3.0) as resp:
                    if resp.status != 200:
                        raise ArtistOffline()
            except Exception:
                raise ArtistOffline()
                
            # 2. Request generation
            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "username": str(ctx.author),
                "is_nsfw": ctx.channel.nsfw if hasattr(ctx.channel, "nsfw") else False,
                "width": width,
                "height": height,
                "steps": int(steps),
                "cfg_scale": float(cfg_scale),
                "scheduler": scheduler,
                "upscale": upscale == "yes"
            }
            try:
                async with session.post(f"{api_url}/generate", json=payload, timeout=5.0) as resp:
                    if resp.status == 400:
                        err_data = await resp.json()
                        err_msg = err_data.get('error', '')
                        if "nsfw" in err_msg.lower():
                            raise NSFWBlocked()
                        raise GenerationFailed(err_msg)
                    elif resp.status != 200:
                        raise GenerationFailed(i18n.get(lang, "chat.generate_failed_server"))
                    data = await resp.json()
                    request_id = data.get("request_id")
            except Exception as e:
                if isinstance(e, (NSFWBlocked, GenerationFailed)):
                    raise e
                raise GenerationFailed(i18n.get(lang, "chat.generate_failed_request", error=str(e)))
                
            # 3. Polling loop
            status = "pending"
            device_name = "MeinaMix V11"
            msg = await ctx.reply(i18n.get(lang, "chat.generate_sending"))
            
            last_status = None
            max_loops = 48  # 120 seconds max (48 * 2.5)
            for i in range(max_loops):
                await asyncio.sleep(2.5)
                try:
                    async with session.get(f"{api_url}/status/{request_id}", timeout=3.0) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            status = data.get("status")
                            if data.get("device"):
                                device_name = data.get("device")
                        else:
                            continue
                except Exception:
                    continue
                    
                if status == "pending" and last_status != "pending":
                    await msg.edit(content=i18n.get(lang, "chat.generate_waiting_approval"))
                    last_status = "pending"
                elif status == "generating" and last_status != "generating":
                    await msg.edit(content=i18n.get(lang, "chat.generate_approved"))
                    last_status = "generating"
                elif status == "completed":
                    await msg.edit(content=i18n.get(lang, "chat.generate_fetching"))
                    try:
                        async with session.get(f"{api_url}/image/{request_id}", timeout=15.0) as resp:
                            if resp.status == 200:
                                img_bytes = await resp.read()
                                file = discord.File(io.BytesIO(img_bytes), filename="generated.png")
                                prompt_display = prompt if len(prompt) <= 3900 else prompt[:3897] + "..."
                                embed = discord.Embed(
                                    title=i18n.get(lang, "chat.generate_title"),
                                    description=f"**Prompt:** {prompt_display}",
                                    color=ctx.author.color,
                                    timestamp=datetime.now()
                                )
                                embed.set_image(url="attachment://generated.png")
                                scheduler_display = {
                                    "dpm++_2m_karras": "DPM++ 2M Karras",
                                    "euler_a": "Euler a",
                                    "dpm++_sde_karras": "DPM++ SDE Karras",
                                    "ddim": "DDIM"
                                }.get(scheduler, scheduler)
                                footer_text = (
                                    f"Requested by {ctx.author} | Model: MeinaMix V11 | GPU: {device_name} | "
                                    f"Ratio: {aspect_ratio} ({width}x{height}) | Steps: {steps} | CFG: {cfg_scale} | Sampler: {scheduler_display}"
                                )
                                if upscale == "yes":
                                    footer_text += " | Upscaled: Swin2SR 2x"
                                embed.set_footer(text=footer_text)
                                await ctx.reply(embed=embed, file=file)
                                try:
                                    await msg.delete()
                                except:
                                    pass
                                return
                            else:
                                try:
                                    await msg.delete()
                                except:
                                    pass
                                raise GenerationFailed(i18n.get(lang, "chat.generate_failed_get"))
                    except Exception as e:
                        try:
                            await msg.delete()
                        except:
                            pass
                        if isinstance(e, GenerationFailed):
                            raise e
                        raise GenerationFailed(i18n.get(lang, "chat.generate_failed_download", error=str(e)))
                elif status == "declined":
                    try:
                        await msg.delete()
                    except:
                        pass
                    raise GenerationDeclined()
                elif status == "failed":
                    try:
                        await msg.delete()
                    except:
                        pass
                    
                    err_msg = None
                    try:
                        err_msg = data.get("error")
                    except Exception:
                        pass
                        
                    if err_msg:
                        raise GenerationFailed(err_msg)
                    else:
                        raise GenerationFailed()
            
            try:
                await msg.delete()
            except:
                pass
            raise GenerationTimeout()

    @commands.hybrid_command(
        aliases=['edit', 'imageedit'],
        description='Create variations of the provided image!'
    )
    @app_commands.describe(attachment='Attach an image to modify')
    @commands.cooldown(type=commands.BucketType.default, per=60, rate=4)
    @check_blacklist()
    async def variation(self, ctx: commands.Context, attachment: discord.Attachment):
        """
        Create variations of the provided image!
        """
        from scripts.main import disable_command
        return await disable_command(ctx)
        # (Implementation omitted for brevity, keeping existing logic)

    def crop_to_square(self, img_path):
        """
        Converts ANY aspect ratio to 1:1
        Thanks, RVDIA!
        """
        with Image.open(img_path) as img:
            width, height = img.size
            size = min(width, height)
            left = (width - size) // 2
            top = (height - size) // 2
            right = (width + size) // 2
            bottom = (height + size) // 2
            cropped = img.crop((left, top, right, bottom))
            cropped.save(img_path)

async def setup(bot: commands.Bot):
    await bot.add_cog(Conversation(bot))
