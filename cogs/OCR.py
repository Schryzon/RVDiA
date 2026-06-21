import discord
import os
import io
from discord.ext import commands
from discord import app_commands
from google import genai
from google.genai import types
from pypdf import PdfReader
from scripts.main import db, check_blacklist
from scripts.utils.i18n import i18n

class OCR(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.google_key = os.getenv("googlekey")

    async def _get_target_attachment(self, ctx: commands.Context, attachment: discord.Attachment = None):
        # 1. Check direct parameter
        if attachment:
            return attachment
            
        # 2. Check reply message
        if ctx.message and ctx.message.reference:
            try:
                msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if msg.attachments:
                    return msg.attachments[0]
            except Exception:
                pass
                
        # 3. Check current message attachments
        if ctx.message and ctx.message.attachments:
            return ctx.message.attachments[0]
            
        return None

    @commands.hybrid_command(
        name="ocr",
        description="Extract and transcribe text from images or PDF documents using AI."
    )
    @app_commands.describe(attachment="Upload an image (PNG, JPG, WebP) or PDF file")
    @check_blacklist()
    async def ocr(self, ctx: commands.Context, attachment: discord.Attachment = None):
        """Extract and transcribe text from images or PDF documents using AI."""
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        target = await self._get_target_attachment(ctx, attachment)
        
        try:
            await ctx.defer()
        except discord.NotFound:
            pass
            
        async with ctx.channel.typing():
            if not target:
                if ctx.author.avatar is None:
                    no_img_msg = (
                        "❌ No attachment or avatar found! Please upload an image or PDF."
                    ) if lang == "en" else (
                        "❌ Tidak ada lampiran atau avatar ditemukan! Silahkan unggah gambar atau PDF."
                    )
                    return await ctx.reply(no_img_msg)
                
                img_bytes = await ctx.author.display_avatar.with_format("png").read()
                filename = "avatar.png"
                mime_type = "image/png"
            else:
                filename = target.filename.lower()
                img_bytes = await target.read()
                mime_type = target.content_type or "application/octet-stream"

            # Process PDF
            if filename.endswith(".pdf") or mime_type == "application/pdf":
                try:
                    pdf_file = io.BytesIO(img_bytes)
                    reader = PdfReader(pdf_file)
                    extracted_text = ""
                    
                    for page_num, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text:
                            extracted_text += f"--- Page {page_num + 1} ---\n{text}\n\n"
                    
                    extracted_text = extracted_text.strip()
                    
                    if not extracted_text:
                        scanned_msg = (
                            "⚠️ This PDF appears to be scanned or contains no text layers. "
                            "Please convert the pages to images (PNG/JPG) and upload them to `/ocr` instead!"
                        ) if lang == "en" else (
                            "⚠️ PDF ini sepertinya adalah hasil scan atau tidak memiliki teks select. "
                            "Silahkan konversi halamannya menjadi gambar (PNG/JPG) lalu unggah ke `/ocr`!"
                        )
                        return await ctx.reply(scanned_msg)
                        
                    await self._send_transcription_result(ctx, extracted_text, "transcription.txt", lang)
                    
                except Exception as e:
                    err_msg = (
                        f"❌ Failed to parse PDF: {str(e)}"
                    ) if lang == "en" else (
                        f"❌ Gagal memproses PDF: {str(e)}"
                    )
                    await ctx.reply(err_msg)
            
            # Process Image
            else:
                valid_exts = [".png", ".jpg", ".jpeg", ".webp"]
                if not any(filename.endswith(ext) for ext in valid_exts) and target is not None:
                    invalid_msg = (
                        "❌ Invalid file format! Please upload a PDF or an image (PNG, JPG, JPEG, WebP)."
                    ) if lang == "en" else (
                        "❌ Format file tidak valid! Silahkan unggah PDF atau gambar (PNG, JPG, JPEG, WebP)."
                    )
                    return await ctx.reply(invalid_msg)

                try:
                    client = genai.Client(api_key=self.google_key)
                    
                    prompt = (
                        "Perform OCR on this image. Extract all text accurately, preserve original spacing and layout, "
                        "and present it inside a clean markdown codeblock or formatted text. "
                        "Return only the extracted text without any conversational preamble or pleasantries."
                    )
                    
                    part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type if "image" in mime_type else "image/png")
                    
                    result = await client.aio.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=[part, prompt]
                    )
                    
                    transcribed_text = result.text.strip() if result.text else ""
                    if not transcribed_text:
                        empty_msg = (
                            "🔍 No text could be found or transcribed from the image."
                        ) if lang == "en" else (
                            "🔍 Tidak ada teks yang ditemukan atau disalin dari gambar."
                        )
                        return await ctx.reply(empty_msg)
                        
                    await self._send_transcription_result(ctx, transcribed_text, "transcribed_text.txt", lang)
                    
                except Exception as e:
                    err_msg = (
                        f"❌ Failed to process image OCR: {str(e)}"
                    ) if lang == "en" else (
                        f"❌ Gagal memproses OCR gambar: {str(e)}"
                    )
                    await ctx.reply(err_msg)

    async def _send_transcription_result(self, ctx: commands.Context, text: str, filename: str, lang: str):
        # Strip potential markdown codeblock wrappers
        clean_text = text
        if clean_text.startswith("```") and clean_text.endswith("```"):
            lines = clean_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_text = "\n".join(lines)

        if len(clean_text) < 1900:
            await ctx.reply(f"```\n{clean_text}\n```")
        else:
            file_data = clean_text.encode("utf-8")
            text_file = discord.File(io.BytesIO(file_data), filename=filename)
            
            over_msg = (
                "📄 The transcribed text is too long for a Discord message, so I have compiled it into a text file!"
            ) if lang == "en" else (
                "📄 Teks salinan terlalu panjang untuk pesan Discord, jadi aku telah menyusunnya dalam file teks!"
            )
            await ctx.reply(content=over_msg, file=text_file)

async def setup(bot):
    await bot.add_cog(OCR(bot))
