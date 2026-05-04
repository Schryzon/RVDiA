import discord
import os
import asyncio
import pytz
from google import genai
from google.genai import types
from datetime import datetime
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, button
from PIL import Image
from scripts.main import titlecase, check_blacklist, AIClient, db
from scripts.memory import memory_manager

class Regenerate_Answer_Button(View):
    def __init__(self, user_id: int, last_question: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.last_question = last_question
        
        vote_me = Button(
            label='Suka RVDiA? Vote!', 
            emoji='<:rvdia:1140812479883128862>',
            style=discord.ButtonStyle.green, 
            url='https://top.gg/bot/957471338577166417/vote'
        )
        self.add_item(vote_me)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'message'):
            await self.message.edit(view=self)

    @button(label="Jawab Ulang", custom_id='regenerate', style=discord.ButtonStyle.blurple, emoji='🔁')
    async def regenerate(self, interaction: discord.Interaction, button: Button):
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
                result = await client.aio.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=message,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_inst,
                        tools=[types.Tool(google_search=types.GoogleSearch())]
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
                break
        
        # 3. Save the new AI response to memory (Optimized: skips embedding)
        await memory_manager.add_memory(user_id, "model", AI_response)
        
        display_message = message
        if len(display_message) > 256:
            display_message = display_message[:253] + '...'

        embed = discord.Embed(
            title=' '.join((titlecase(word) for word in display_message.split(' '))), 
            color=interaction.user.color, 
            timestamp=interaction.message.created_at
        )
        embed.description = AI_response
        embed.set_author(name=interaction.user)
        embed.set_footer(text='Jika ada yang ingin ditanyakan, bisa langsung direply!')
        
        return await interaction.message.edit(embed=embed, view=self)

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
                    result = await client.aio.models.generate_content(
                        model='gemini-1.5-flash',
                        contents=message,
                        config=types.GenerateContentConfig(
                            system_instruction=sys_inst,
                            tools=[types.Tool(google_search=types.GoogleSearch())]
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
            
            regenerate_button = Regenerate_Answer_Button(user_id, message)
            return await ctx.reply(embed=embed, view=regenerate_button)

    @commands.hybrid_command(
        aliases=['generate', 'create'],
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
