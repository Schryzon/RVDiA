import io
import discord
from PIL import Image
from pypdf import PdfReader

async def parse_pdf(attachment: discord.Attachment) -> str:
    """Downloads and extracts text from a PDF attachment (limit 15 pages or ~10000 chars to avoid token bloating)."""
    try:
        file_bytes = await attachment.read()
        pdf_file = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_file)
        text = ""
        # Limit pages to prevent massive documents from flooding
        max_pages = min(len(reader.pages), 15)
        for i in range(max_pages):
            page = reader.pages[i]
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        # Limit total characters to 10000
        if len(text) > 10000:
            text = text[:9997] + "..."
        return text.strip()
    except Exception as e:
        return f"[Gagal mengekstrak teks dari PDF: {str(e)}]"

async def process_image_for_gemini(attachment: discord.Attachment) -> bytes:
    """Downloads, downscales, and compresses an image attachment to save bandwidth/tokens."""
    file_bytes = await attachment.read()
    image = Image.open(io.BytesIO(file_bytes))
    
    # Downscale image to max 512x512
    image.thumbnail((512, 512))
    
    # Convert RGBA to RGB for JPEG compatibility
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
        
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=70)
    return output.getvalue()

async def handle_attachment(attachment: discord.Attachment) -> dict:
    """Processes an attachment, returning text context or image bytes.
    
    Returns:
        dict: {
            "text": str,          # Text context to append to LLM prompt
            "image_bytes": bytes, # Resized JPEG bytes if image, else None
            "mime_type": str,     # "image/jpeg" if image, else None
            "filename": str       # Original filename
        }
    """
    result = {
        "text": "",
        "image_bytes": None,
        "mime_type": None,
        "filename": attachment.filename
    }
    
    content_type = attachment.content_type or ""
    filename_lower = attachment.filename.lower()
    
    # Check for PDF
    if content_type == "application/pdf" or filename_lower.endswith(".pdf"):
        text = await parse_pdf(attachment)
        result["text"] = f"\n[Lampiran PDF: {attachment.filename}]\n---\n{text}\n---\n"
        
    # Check for Image
    elif content_type.startswith("image/") or filename_lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        try:
            image_bytes = await process_image_for_gemini(attachment)
            result["image_bytes"] = image_bytes
            result["mime_type"] = "image/jpeg"
        except Exception as e:
            result["text"] = f"\n[Gagal memproses gambar {attachment.filename}: {str(e)}]\n"
            
    # Check for Text files
    elif content_type.startswith("text/") or filename_lower.endswith((".txt", ".log", ".json", ".xml", ".yaml", ".yml", ".py", ".js")):
        try:
            file_bytes = await attachment.read()
            # Try decoding as utf-8, fallback to latin-1
            try:
                text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = file_bytes.decode("latin-1")
                
            if len(text) > 8000:
                text = text[:7997] + "..."
            result["text"] = f"\n[Lampiran Teks: {attachment.filename}]\n---\n{text}\n---\n"
        except Exception as e:
            result["text"] = f"\n[Gagal membaca file teks {attachment.filename}: {str(e)}]\n"
            
    return result
