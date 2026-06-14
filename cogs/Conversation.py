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
from discord.ext import commands
from discord.ui import View, Button, button
from PIL import Image
from scripts.main import smart_title_case, check_blacklist, AIClient, db
from scripts.memory import memory_manager
from scripts.error_logger import format_error_report
from scripts.search import search_web, search_images, format_search_results

class Regenerate_Answer_Button(View):
    def __init__(self, user_id: int, last_question: str, initial_response: str, image_bytes: bytes = None, mime_type: str = None):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.last_question = last_question
        self.responses = [initial_response]
        self.image_bytes = image_bytes
        self.mime_type = mime_type
        self.current_page = 0
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
        regen_btn = Button(
            label="Jawab Ulang", 
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
        embed.set_footer(text=f'Halaman {self.current_page + 1}/{len(self.responses)} • Jika ingin tanya lagi, silakan reply!')
        
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
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_view(interaction)
        else:
            await interaction.response.defer()

    async def next_page(self, interaction: discord.Interaction):
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
        try:
            await interaction.response.defer()
        except discord.NotFound:
            pass
        
        async with interaction.channel.typing():
            user_id = interaction.user.id
            message = self.last_question
            
            # 1. Retrieve context
            context = await memory_manager.get_context(user_id, message)
            
            # 2. We don't save the question again here since it's a regeneration
            # but we use the embedding for the AI response if needed (though we skip model embeddings)
            
            currentTime = datetime.now(pytz.utc).astimezone(pytz.timezone("Asia/Jakarta"))
            date = currentTime.strftime("%d/%m/%Y")
            hour = currentTime.strftime("%H:%M:%S")
            
            client = genai.Client(api_key=os.getenv("googlekey"))
            
            # Construct dynamic prompt
            sys_inst = (
                os.getenv('rolesys') + 
                f"\n\nContext Information:\n"
                f"Currently chatting with: {interaction.user}\n"
                f"Current Date: {date}, Time: {hour} WITA\n"
                f"\nRecent Conversation History:\n{context['history']}\n"
                f"\nRelevant Past Memories:\n{context['memories']}\n"
                f"\nRemember to be stay in character as RVDiA (loving, cute, informal)."
            )
            
            AI_response = None
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    # We'll use a manual check for search for now, 
                    # or we could use Gemini's function calling.
                    # To keep it simple and "implemented ourselves", 
                    # we'll look for keywords or just always provide a "search" option.
                    
                    # Check if the query might need search or game lore
                    search_context = ""
                    needs_search = any(kw in message.lower() for kw in ["kapan", "siapa", "dimana", "berita", "terbaru", "harga", "cek", "apa itu", "kenapa", "bagaimana", "tutorial", "cara", "rekomendasi", "info", "lokasi", "jadwal", "skor", "cuaca", "trending", "viral", "cari", "search"])
                    
                    game_keywords = ["revolution", "re:volution", "rpg", "stats", "boss", "enemy", "musuh", "skill", "karma", "fight", "battle", "combat system"]
                    needs_game_lore = any(kw in message.lower() for kw in game_keywords)
                    
                    if needs_game_lore:
                        try:
                            with open("game_manual.md", "r", encoding="utf-8") as f:
                                lore = f.read()
                            search_context += f"\n[Game Manual Reference:\n{lore}]\n"
                        except Exception as ex:
                            logging.error(f"Failed to load game manual: {ex}")
                    
                    image_url = None
                    needs_image = any(kw in message.lower() for kw in ["tunjukkan gambar", "lihat foto", "show me", "cari gambar", "lihatkan foto", "lihatkan gambar"])
                    
                    if needs_search or needs_image:
                        if needs_image:
                            img_results = await search_images(message)
                            if img_results:
                                image_url = img_results[0]['image']
                                search_context += f"\n[Found Image: {image_url}]\n"
                        
                        results = await search_web(message)
                        search_context += format_search_results(results)

                    # Update system instruction with search context
                    current_sys_inst = sys_inst
                    if search_context:
                        current_sys_inst += f"\n\nAdditional Search Context:\n{search_context}"

                    # Construct contents list if image parts are present
                    image_parts = []
                    if self.image_bytes and self.mime_type:
                        image_parts.append(
                            types.Part.from_bytes(
                                data=self.image_bytes,
                                mime_type=self.mime_type
                            )
                        )

                    if image_parts:
                        contents_payload = image_parts + [message]
                    else:
                        contents_payload = message

                    result = await client.aio.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=contents_payload,
                        config=types.GenerateContentConfig(
                            system_instruction=current_sys_inst
                        )
                    )
                    AI_response = result.text
                    
                    # Append image URL to response if found but not included by AI
                    if image_url and image_url not in AI_response:
                        AI_response += f"\n\n{image_url}"
                        
                    break
                except Exception as e:
                    error_str = str(e)
                    if any(err in error_str for err in ["429", "ResourceExhausted", "503", "ServiceUnavailable", "UNAVAILABLE"]) and attempt < max_retries:
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    
                    if any(err in error_str for err in ["429", "ResourceExhausted", "503", "ServiceUnavailable", "UNAVAILABLE"]):
                        AI_response = "Aduuh! Sepertinya aku lagi kecapekan nih... Banyak banget yang nanya. Tunggu sebentar ya, nanti tanya lagi! 🌸"
                    elif "safety" in str(e).lower():
                        AI_response = "Umm... sepertinya itu pertanyaan yang kurang pantas. Aku gak bisa jawab kalau soal itu ya! ❌"
                    else:
                        AI_response = "Waduh, otakku tiba-tiba nge-blank... Coba tanya lagi nanti ya! 💫"
                        # Log the error and send to developer
                        logging.error(f"Error in Regenerate_Answer_Button: {e}")
                        try:
                            error_channel = interaction.client.get_channel(int(os.getenv("errorchannel")))
                            if error_channel:
                                embed = format_error_report(e, context=f"Regenerate Chat (User: {interaction.user})")
                                await error_channel.send(embed=embed)
                        except Exception as log_e:
                            logging.error(f"Failed to send error report: {log_e}")
                    break
            
            if AI_response and AI_response not in self.responses:
                self.responses.append(AI_response)
                self.current_page = len(self.responses) - 1
            
            # 3. Save the new AI response to memory (Optimized: skips embedding)
            await memory_manager.add_memory(user_id, "model", AI_response)
            
            await self.update_view(interaction)

class MemoryManagerView(View):
    def __init__(self, user_id: int, memories: list):
        super().__init__(timeout=60)
        self.user_id = user_id
        
        # Add Select Menu
        options = []
        for i, mem in enumerate(memories[:25]): # Max 25 options
            # Shorten content for label
            label = mem.content[:90] + "..." if len(mem.content) > 90 else mem.content
            options.append(discord.SelectOption(
                label=f"{i+1}. {label}",
                value=str(mem.id),
                # Memory model doesn't have a 'role' field, but it only stores user messages.
                description=f"Type: Memory | {mem.createdAt.strftime('%d/%m/%Y')}"
            ))
            
        self.select = discord.ui.Select(
            placeholder="Pilih memori untuk dihapus (Bisa pilih banyak)",
            min_values=1,
            max_values=len(options),
            options=options
        )
        self.select.callback = self.delete_memories
        self.add_item(self.select)

    async def delete_memories(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Ini bukan memorimu! ❌", ephemeral=True)
            
        await interaction.response.defer()
        selected_ids = self.select.values
        
        try:
            # Delete from DB
            await db.memory.delete_many(where={'id': {'in': [int(sid) for sid in selected_ids]}})
            await interaction.followup.send(f"✅ Berhasil menghapus {len(selected_ids)} memori pilihanmu!", ephemeral=True)
            # Remove message
            await interaction.message.delete()
        except Exception as e:
            await interaction.followup.send(f"❌ Gagal menghapus memori: {e}", ephemeral=True)

class Conversation(commands.Cog):
    """
    Kategori khusus untuk mengobrol dengan RVDiA.
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        aliases=['ask', 'chatbot', 'tanya'],
        description='Tanyakan atau perhintahkan aku untuk melakukan sesuatu!'
    )
    @app_commands.rename(message='pesan', attachment='lampiran')
    @app_commands.describe(message='Apa yang ingin kamu tanyakan?', attachment='Lampirkan file (PDF, gambar, atau teks)')
    @commands.cooldown(type=commands.BucketType.user, per=2, rate=1)
    @check_blacklist()
    async def chat(self, ctx: commands.Context, message: str = "", attachment: discord.Attachment = None):
        """
        Tanyakan atau perhintahkan aku untuk melakukan sesuatu!
        """
        try:
            await ctx.defer()
        except discord.NotFound:
            pass
            
        async with ctx.channel.typing():
            user_id = ctx.author.id
            
            # Resolve attachment (slash command arg or prefix message attachment)
            target_attachment = attachment
            if not target_attachment and ctx.message and ctx.message.attachments:
                target_attachment = ctx.message.attachments[0]
                
            if not message and not target_attachment:
                try:
                    return await ctx.reply("Ada yang bisa kubantu? Silakan ketik pesan atau lampirkan file ya! 🌸")
                except discord.HTTPException:
                    return await ctx.send("Ada yang bisa kubantu? Silakan ketik pesan atau lampirkan file ya! 🌸")

            # Resolve DB message placeholder for memory database
            db_message = message if message else f"[Mengirim file: {target_attachment.filename}]"

            # 1. Retrieve context (generates query embedding)
            context = await memory_manager.get_context(user_id, db_message)
            
            # 2. Save user message to memory, REUSING embedding
            await memory_manager.add_memory(user_id, "user", db_message, embedding=context['embedding'])
            
            # Parse attachments
            attachment_text = ""
            image_parts = []
            image_raw_bytes = None
            image_mime_type = None
            
            if target_attachment:
                from scripts.attachment_handler import handle_attachment
                att_res = await handle_attachment(target_attachment)
                if att_res["text"]:
                    attachment_text = att_res["text"]
                if att_res["image_bytes"]:
                    image_raw_bytes = att_res["image_bytes"]
                    image_mime_type = att_res["mime_type"]
                    image_parts.append(
                        types.Part.from_bytes(
                            data=image_raw_bytes,
                            mime_type=image_mime_type
                        )
                    )

            full_message = message
            if attachment_text:
                full_message = f"{attachment_text}\nUser message: {message}"

            currentTime = datetime.now(pytz.utc).astimezone(pytz.timezone("Asia/Jakarta"))
            date = currentTime.strftime("%d/%m/%Y")
            hour = currentTime.strftime("%H:%M:%S")
            
            client = genai.Client(api_key=os.getenv("googlekey"))
            
            # Construct dynamic prompt
            sys_inst = (
                os.getenv('rolesys') + 
                f"\n\nContext Information:\n"
                f"Currently chatting with: {ctx.author}\n"
                f"Current Date: {date}, Time: {hour} WITA\n"
                f"\nRecent Conversation History:\n{context['history']}\n"
                f"\nRelevant Past Memories:\n{context['memories']}\n"
                f"\nRemember to be stay in character as RVDiA (loving, cute, informal)."
            )
            
            AI_response = None
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    # Expanded Casual Vocabulary Detection (English & Indonesian)
                    search_keywords = ["kapan", "siapa", "dimana", "berita", "terbaru", "harga", "cek", "apa itu", "kenapa", "bagaimana", "tutorial", "cara", "rekomendasi", "info", "lokasi", "jadwal", "skor", "cuaca", "trending", "viral", "cari", "carikan", "search", "jelasin", "ceritain", "apaan", "gimana", "mana", "dong", "google", "googling", "who", "what", "where", "when", "why", "how", "news", "update", "latest", "price", "explain", "tutorial", "recommend", "location", "schedule", "score", "weather", "find out", "tell me about"]
                    image_keywords = ["tunjukkan gambar", "lihat foto", "cari gambar", "lihatkan", "mana gambar", "mana foto", "liat dong", "spill", "pap", "poto", "gambar dari", "kek gimana", "show me", "pics", "photos", "image", "look like", "picture of", "let me see", "can i see", "send me", "view"]

                    search_context = ""
                    needs_search = False
                    if message:
                        needs_search = any(kw in message.lower() for kw in search_keywords)
                    
                    game_keywords = ["revolution", "re:volution", "rpg", "stats", "boss", "enemy", "musuh", "skill", "karma", "fight", "battle"]
                    needs_game_lore = False
                    if message:
                        needs_game_lore = any(kw in message.lower() for kw in game_keywords)
                    
                    if needs_game_lore:
                        try:
                            with open("game_manual.md", "r", encoding="utf-8") as f:
                                lore = f.read()
                            search_context += f"\n[Game Manual Reference:\n{lore}]\n"
                        except Exception as ex:
                            logging.error(f"Failed to load game manual: {ex}")
                    image_url = None
                    needs_image = False
                    if message:
                        needs_image = any(kw in message.lower() for kw in image_keywords)
                    
                    if needs_search or needs_image:
                        if needs_image:
                            img_results = await search_images(message)
                            if img_results:
                                image_url = img_results[0]['image']
                                search_context += f"\n[Found Image: {image_url}]\n"
                        
                        results = await search_web(message)
                        search_context += format_search_results(results)

                    # Update system instruction with search context
                    current_sys_inst = sys_inst
                    if search_context:
                        current_sys_inst += f"\n\nAdditional Search Context:\n{search_context}"

                    # Construct contents list if image parts are present
                    if image_parts:
                        contents_payload = image_parts + [full_message]
                    else:
                        contents_payload = full_message

                    result = await client.aio.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=contents_payload,
                        config=types.GenerateContentConfig(
                            system_instruction=current_sys_inst
                        )
                    )
                    AI_response = result.text
                    
                    # Append image URL to response if found but not included by AI
                    if image_url and image_url not in AI_response:
                        AI_response += f"\n\n{image_url}"
                    break # Success!
                except Exception as e:
                    error_str = str(e)
                    if any(err in error_str for err in ["429", "ResourceExhausted", "503", "ServiceUnavailable", "UNAVAILABLE"]) and attempt < max_retries:
                        await asyncio.sleep(3 * (attempt + 1)) # Wait 3s, then 6s
                        continue
                    
                    if any(err in error_str for err in ["429", "ResourceExhausted", "503", "ServiceUnavailable", "UNAVAILABLE"]):
                        AI_response = "Aduuh! Sepertinya aku lagi kecapekan nih... Hunter lain banyak banget yang nanya. Tunggu sebentar ya, nanti tanya lagi! 🌸"
                    elif "safety" in str(e).lower():
                        AI_response = "Umm... sepertinya itu pertanyaan yang kurang pantas. Aku gak bisa jawab kalau soal itu ya! ❌"
                    else:
                        AI_response = "Waduh, otakku tiba-tiba nge-blank... Coba tanya lagi nanti ya! 💫"
                        # Log the error and send to developer
                        logging.error(f"Error in chat command: {e}")
                        try:
                            error_channel = ctx.bot.get_channel(int(os.getenv("errorchannel")))
                            if error_channel:
                                embed = format_error_report(e, context=f"Chat Command (User: {ctx.author})")
                                await error_channel.send(embed=embed)
                        except Exception as log_e:
                            logging.error(f"Failed to send error report: {log_e}")
                    break
            
            # 3. Save AI response to memory (Optimized: skips embedding)
            await memory_manager.add_memory(user_id, "model", AI_response)
            
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
            embed.set_footer(text='Jika ada yang ingin ditanyakan, bisa langsung direply!')
            
            # Check if response has an image link
            import re
            img_match = re.search(r'https?://\S+\.(?:jpg|jpeg|png|gif|webp)', AI_response)
            if img_match:
                embed.set_image(url=img_match.group(0))
 
            regenerate_button = Regenerate_Answer_Button(user_id, full_message, AI_response, image_raw_bytes, image_mime_type)
            try:
                return await ctx.reply(embed=embed, view=regenerate_button)
            except discord.HTTPException as e:
                # If webhook token is invalid or unauthorized, fall back to channel send
                if e.code == 50027 or e.status == 401:
                    return await ctx.send(embed=embed, view=regenerate_button)
                raise e

    @commands.hybrid_group(
        name="memory",
        aliases=["memori", "history"],
        description="Kelola memori chat-mu dengan RVDiA."
    )
    @check_blacklist()
    async def memory(self, ctx: commands.Context):
        """
        Kelola memori chat-mu dengan RVDiA.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send("Gunakan `/memory clear` atau `/memory manage` untuk mengelola memorimu! 🌸")

    @memory.command(name="clear", description="Hapus seluruh riwayat percakapanmu.")
    async def memory_clear(self, ctx: commands.Context):
        """
        Hapus seluruh riwayat percakapanmu.
        """
        confirm_view = View(timeout=30)
        
        async def confirm_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("Bukan tombolmu! ❌", ephemeral=True)
            
            await interaction.response.defer()
            await db.memory.delete_many(where={'userId': ctx.author.id})
            await interaction.followup.send("✅ Seluruh memorimu telah dihapus! Kita mulai dari awal lagi ya? 🌸")
            await interaction.message.delete()

        confirm_btn = Button(label="Ya, Hapus Semua", style=discord.ButtonStyle.danger)
        confirm_btn.callback = confirm_callback
        confirm_view.add_item(confirm_btn)
        
        await ctx.send("Apakah kamu yakin ingin menghapus **seluruh** memorimu? Aku tidak akan mengingat percakapan kita sebelumnya lagi... 🥺", view=confirm_view)

    @memory.command(name="manage", description="Pilih memori tertentu untuk dihapus.")
    async def memory_manage(self, ctx: commands.Context):
        """
        Pilih memori tertentu untuk dihapus.
        """
        memories = await db.memory.find_many(
            where={'userId': ctx.author.id},
            order={'createdAt': 'desc'},
            take=25
        )
        
        if not memories:
            return await ctx.send("Kamu belum punya memori denganku! Ayo ngobrol dulu! 🌸")
            
        view = MemoryManagerView(ctx.author.id, memories)
        await ctx.send("Berikut adalah 25 memori terakhirmu. Pilih yang ingin kamu hapus:", view=view)

    @commands.hybrid_command(
        aliases=['create'],
        description='Ciptakan sebuah karya seni!'
    )
    @app_commands.describe(prompt='Apa yang ingin diciptakan?')
    @commands.cooldown(type=commands.BucketType.default, per=60, rate=4)
    @check_blacklist()
    async def generate(self, ctx: commands.Context, *, prompt: str):
        """
        Ciptakan sebuah karya seni dua dimensi dengan perintah!
        """
        import io
        import aiohttp
        from scripts.errors import ArtistOffline, GenerationDeclined, GenerationFailed, NSFWBlocked, GenerationTimeout
        
        api_url = os.getenv("LAPTOP_API_URL")
        api_key = os.getenv("LAPTOP_API_KEY")
        
        if not api_url or not api_key:
            return await ctx.reply("Aduh, maaf ya, fiturnya belum terkonfigurasi dengan benar oleh developermu! 🛠️")
            
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
                "username": str(ctx.author),
                "is_nsfw": ctx.channel.nsfw if hasattr(ctx.channel, "nsfw") else False
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
                        raise GenerationFailed("Gagal membuat permintaan ke laptop!")
                    data = await resp.json()
                    request_id = data.get("request_id")
            except Exception as e:
                if isinstance(e, (NSFWBlocked, GenerationFailed)):
                    raise e
                raise GenerationFailed(f"Gagal mengirim permintaan ke laptop: {str(e)}")
                
            # 3. Polling loop
            status = "pending"
            msg = await ctx.reply("Mengirim permintaan ke laptop... 🖥️")
            
            last_status = None
            max_loops = 48  # 120 seconds max (48 * 2.5)
            for i in range(max_loops):
                await asyncio.sleep(2.5)
                try:
                    async with session.get(f"{api_url}/status/{request_id}", timeout=3.0) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            status = data.get("status")
                        else:
                            continue
                except Exception:
                    continue
                    
                if status == "pending" and last_status != "pending":
                    await msg.edit(content="Menunggu persetujuan pada laptop senimanku... (Tolong klik Approve di Toast ya! 🌸)")
                    last_status = "pending"
                elif status == "generating" and last_status != "generating":
                    await msg.edit(content="Permintaan disetujui! Sedang menggambar menggunakan GPU (AnythingV5)... 🎨")
                    last_status = "generating"
                elif status == "completed":
                    await msg.edit(content="Selesai! Mengambil gambar... 📥")
                    try:
                        async with session.get(f"{api_url}/image/{request_id}", timeout=15.0) as resp:
                            if resp.status == 200:
                                img_bytes = await resp.read()
                                file = discord.File(io.BytesIO(img_bytes), filename="generated.png")
                                embed = discord.Embed(title=f"🎨 {prompt}", color=ctx.author.color, timestamp=datetime.now())
                                embed.set_image(url="attachment://generated.png")
                                embed.set_footer(text=f"Requested by {ctx.author} | Powered by AnythingV5")
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
                                raise GenerationFailed("Gagal mengambil gambar yang dihasilkan!")
                    except Exception as e:
                        try:
                            await msg.delete()
                        except:
                            pass
                        if isinstance(e, GenerationFailed):
                            raise e
                        raise GenerationFailed(f"Gagal mengunduh gambar: {str(e)}")
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
                    raise GenerationFailed()
            
            try:
                await msg.delete()
            except:
                pass
            raise GenerationTimeout()

    @commands.hybrid_command(
        aliases=['edit', 'imageedit'],
        description='Ciptakan variasi dari gambar yang diberikan!'
    )
    @app_commands.describe(attachment='Lampirkan gambar!')
    @commands.cooldown(type=commands.BucketType.default, per=60, rate=4)
    @check_blacklist()
    async def variation(self, ctx: commands.Context, attachment: discord.Attachment):
        """
        Ciptakan variasi dari gambar yang diberikan!
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
