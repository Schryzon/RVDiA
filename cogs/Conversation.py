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
from scripts.main import titlecase, check_blacklist, AIClient, db
from scripts.memory import memory_manager
from scripts.error_logger import format_error_report
from scripts.search import search_web, format_search_results

class Regenerate_Answer_Button(View):
    def __init__(self, user_id: int, last_question: str, initial_response: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.last_question = last_question
        self.responses = [initial_response]
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
            title=' '.join((titlecase(word) for word in display_message.split(' '))), 
            color=interaction.user.color, 
            timestamp=interaction.message.created_at
        )
        embed.description = self.responses[self.current_page]
        embed.set_author(name=interaction.user)
        embed.set_footer(text=f'Halaman {self.current_page + 1}/{len(self.responses)} • Jika ingin tanya lagi, silakan reply!')
        
        await interaction.message.edit(embed=embed, view=self)

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
        await interaction.response.defer()
        await interaction.channel.typing()
        
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
                
                # Check if the query might need search
                search_context = ""
                needs_search = any(kw in message.lower() for kw in ["kapan", "siapa", "dimana", "berita", "terbaru", "harga", "cek"])
                if needs_search:
                    results = await search_web(message)
                    search_context = format_search_results(results)

                # Update system instruction with search context
                current_sys_inst = sys_inst
                if search_context:
                    current_sys_inst += f"\n\nAdditional Search Context:\n{search_context}"

                result = await client.aio.models.generate_content(
                    model='gemini-3-flash-preview',
                    contents=message,
                    config=types.GenerateContentConfig(
                        system_instruction=current_sys_inst
                    )
                )
                AI_response = result.text
                break
            except Exception as e:
                if ("429" in str(e) or "ResourceExhausted" in str(e)) and attempt < max_retries:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                
                if "429" in str(e) or "ResourceExhausted" in str(e):
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
    @app_commands.rename(message='pesan')
    @app_commands.describe(message='Apa yang ingin kamu tanyakan?')
    @commands.cooldown(type=commands.BucketType.user, per=2, rate=1)
    @check_blacklist()
    async def chat(self, ctx: commands.Context, *, message: str):
        """
        Tanyakan atau perhintahkan aku untuk melakukan sesuatu!
        """
        async with ctx.typing():
            user_id = ctx.author.id
            
            # 1. Retrieve context (generates query embedding)
            context = await memory_manager.get_context(user_id, message)
            
            # 2. Save user message to memory, REUSING embedding
            await memory_manager.add_memory(user_id, "user", message, embedding=context['embedding'])
            
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
                # Check if the query might need search
                search_context = ""
                needs_search = any(kw in message.lower() for kw in ["kapan", "siapa", "dimana", "berita", "terbaru", "harga", "cek"])
                if needs_search:
                    results = await search_web(message)
                    search_context = format_search_results(results)

                # Update system instruction with search context
                current_sys_inst = sys_inst
                if search_context:
                    current_sys_inst += f"\n\nAdditional Search Context:\n{search_context}"

                result = await client.aio.models.generate_content(
                    model='gemini-3-flash-preview',
                    contents=message,
                    config=types.GenerateContentConfig(
                        system_instruction=current_sys_inst
                    )
                )
                    AI_response = result.text
                    break # Success!
                except Exception as e:
                    if ("429" in str(e) or "ResourceExhausted" in str(e)) and attempt < max_retries:
                        await asyncio.sleep(3 * (attempt + 1)) # Wait 3s, then 6s
                        continue
                    
                    if "429" in str(e) or "ResourceExhausted" in str(e):
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
            
            display_message = message
            if len(display_message) > 256:
                display_message = display_message[:253] + '...'

            embed = discord.Embed(
                title=' '.join((titlecase(word) for word in display_message.split(' '))), 
                color=ctx.author.color, 
                timestamp=ctx.message.created_at
            )
            embed.description = AI_response
            embed.set_author(name=ctx.author)
            embed.set_footer(text='Jika ada yang ingin ditanyakan, bisa langsung direply!')
            
            regenerate_button = Regenerate_Answer_Button(user_id, message, AI_response)
            return await ctx.reply(embed=embed, view=regenerate_button)

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
        from scripts.main import disable_command
        return await disable_command(ctx)
        # (Implementation omitted for brevity, keeping existing logic)

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
            cropped.save(img_path[2:])

async def setup(bot: commands.Bot):
    await bot.add_cog(Conversation(bot))
