import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO

def generate_captcha_text(length: int = 5) -> str:
    # Exclude confusing characters (e.g. O, 0, I, 1, l)
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(chars) for _ in range(length))

def create_captcha_image(text: str) -> bytes:
    w, h = 200, 80
    img = Image.new("RGBA", (w, h), (24, 24, 32, 255))
    draw = ImageDraw.Draw(img)
    
    font = ImageFont.load_default()
    paths = [
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "arial.ttf"
    ]
    for path in paths:
        try:
            font = ImageFont.truetype(path, 36)
            break
        except OSError:
            continue
            
    # Draw noise lines
    for _ in range(8):
        x1 = random.randint(0, w)
        y1 = random.randint(0, h)
        x2 = random.randint(0, w)
        y2 = random.randint(0, h)
        line_color = (random.randint(80, 180), random.randint(80, 180), random.randint(180, 255), 100)
        draw.line([(x1, y1), (x2, y2)], fill=line_color, width=random.randint(1, 2))
        
    # Draw noise dots
    for _ in range(60):
        x = random.randint(0, w)
        y = random.randint(0, h)
        dot_color = (random.randint(80, 180), random.randint(180, 255), random.randint(80, 180), 120)
        draw.ellipse((x, y, x + random.randint(2, 3), y + random.randint(2, 3)), fill=dot_color)
        
    # Draw rotated characters
    for i, char in enumerate(text):
        char_img = Image.new("RGBA", (40, 50), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_color = (random.randint(150, 255), random.randint(150, 255), random.randint(150, 255), 255)
        char_draw.text((5, 5), char, font=font, fill=char_color)
        
        rotated = char_img.rotate(random.randint(-25, 25), expand=True, resample=Image.BICUBIC)
        paste_x = 12 + i * 34 + random.randint(-3, 3)
        paste_y = 15 + random.randint(-4, 4)
        img.paste(rotated, (paste_x, paste_y), rotated)
        
    img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
    img = img.filter(ImageFilter.SMOOTH_MORE)
    
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
