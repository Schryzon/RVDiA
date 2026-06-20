import os
import aiohttp
from io import BytesIO
import discord
from PIL import Image, ImageDraw, ImageFont

def get_font(font_name: str, size: int):
    # Try typical paths on Windows, then fall back to default
    paths = [
        f"C:\\Windows\\Fonts\\{font_name}",
        f"C:\\Windows\\Fonts\\{font_name.lower()}",
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "arial.ttf"
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()

async def fetch_avatar(url: str) -> Image.Image:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return Image.open(BytesIO(await resp.read()))
    except Exception:
        pass
    # Return placeholder avatar if fetch fails
    img = Image.new("RGBA", (140, 140), (100, 100, 100, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((10, 10, 130, 130), fill=(150, 150, 150, 255))
    return img

def draw_crest(draw: ImageDraw.Draw, class_name: str, x: int, y: int, size: int = 40):
    """Draws a procedural class crest outline."""
    color = (255, 255, 255, 200)
    class_lower = class_name.lower()
    
    if class_lower == "warrior":
        # Draw a shield
        points = [
            (x, y - size // 2),
            (x + size // 2, y - size // 2),
            (x + size // 2, y),
            (x, y + size // 2),
            (x - size // 2, y),
            (x - size // 2, y - size // 2)
        ]
        draw.polygon(points, outline=color, fill=(255, 75, 75, 40), width=2)
        # Inner cross
        draw.line([(x, y - size // 2), (x, y + size // 2)], fill=color, width=2)
        draw.line([(x - size // 2, y), (x + size // 2, y)], fill=color, width=2)
        
    elif class_lower == "mage":
        # Draw a star/diamond staff crest
        points = [
            (x, y - size // 2),
            (x + size // 3, y - size // 6),
            (x + size // 2, y),
            (x + size // 3, y + size // 6),
            (x, y + size // 2),
            (x - size // 3, y + size // 6),
            (x - size // 2, y),
            (x - size // 3, y - size // 6)
        ]
        draw.polygon(points, outline=color, fill=(30, 144, 255, 40), width=2)
        # Draw small inner circle
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), outline=color, fill=(0, 255, 255, 150))
        
    elif class_lower == "rogue":
        # Draw two crossed daggers (lines)
        draw.line([(x - size // 2, y - size // 2), (x + size // 2, y + size // 2)], fill=color, width=3)
        draw.line([(x + size // 2, y - size // 2), (x - size // 2, y + size // 2)], fill=color, width=3)
        # Dagger hilts
        draw.line([(x - size // 2, y - size // 4), (x - size // 4, y - size // 2)], fill=(255, 215, 0, 255), width=2)
        draw.line([(x + size // 2, y - size // 4), (x + size // 4, y - size // 2)], fill=(255, 215, 0, 255), width=2)
        
    else:
        # Default simple ring for None
        draw.ellipse((x - size // 2, y - size // 2, x + size // 2, y + size // 2), outline=(150, 150, 150, 200), width=2)

async def generate_profile_card(user: discord.Member, user_record, is_premium: bool) -> discord.File:
    # 1. Create dark canvas with horizontal gradient
    im = Image.new("RGBA", (800, 450))
    draw = ImageDraw.Draw(im)
    
    # Gradient: Very dark violet (23, 21, 35) to sleek dark blue (30, 35, 55)
    for x in range(800):
        r = int(23 + (30 - 23) * (x / 800))
        g = int(21 + (35 - 21) * (x / 800))
        b = int(35 + (55 - 35) * (x / 800))
        draw.line([(x, 0), (x, 450)], fill=(r, g, b, 255))
        
    # Get fonts
    font_title = get_font("Segoeui.ttf", 34)
    font_sub = get_font("Segoeui.ttf", 22)
    font_stat = get_font("Segoeui.ttf", 18)
    font_stat_val = get_font("Segoeuib.ttf", 18)
    font_badge = get_font("Segoeuib.ttf", 14)
    
    # 2. Retrieve and draw Avatar
    avatar_img = await fetch_avatar(user.display_avatar.url)
    avatar_size = (130, 130)
    avatar_resized = avatar_img.resize(avatar_size).convert("RGBA")
    
    # Circle mask for avatar
    mask = Image.new("L", avatar_size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, avatar_size[0], avatar_size[1]), fill=255)
    
    # Paste avatar at (50, 50)
    im.paste(avatar_resized, (50, 50), mask)
    
    # Draw avatar border (Gold for premium, Indigo for normal)
    border_color = (255, 215, 0, 255) if is_premium else (114, 137, 218, 255)
    draw.ellipse((48, 48, 50 + avatar_size[0], 50 + avatar_size[1]), outline=border_color, width=3)
    
    # 3. Draw Player Info
    data = user_record.data
    name = data.get('name', user.name)
    player_class = data.get('class', 'None')
    level = data.get('level', 1)
    
    # Draw Name
    name_y = 48
    draw.text((205, name_y), name, fill=(255, 255, 255, 255), font=font_title)
    
    # Draw Premium Badge if applicable
    name_width = draw.textlength(name, font=font_title)
    if is_premium:
        badge_x = int(205 + name_width + 12)
        badge_y = name_y + 12
        # Badge background
        draw.rounded_rectangle(
            (badge_x, badge_y, badge_x + 105, badge_y + 22), 
            radius=5, 
            fill=(255, 215, 0, 50), 
            outline=(255, 215, 0, 200), 
            width=1
        )
        draw.text((badge_x + 8, badge_y + 2), "DREAM WEAVER", fill=(255, 215, 0, 255), font=font_badge)
        
    # Draw Class Crest
    draw_crest(draw, player_class, 225, 125, size=30)
    
    # Draw Class text next to crest
    class_text = f"Class: {player_class}"
    draw.text((250, 112), class_text, fill=(200, 200, 220, 255), font=font_sub)
    
    # Draw Level
    level_text = f"Level: {level}"
    draw.text((205, 148), level_text, fill=(138, 220, 138, 255), font=font_sub)
    
    # 4. Draw Wealth Details (Top Right Area)
    coins = data.get('coins', 0)
    karma = data.get('karma', 0)
    
    wealth_start_x = 560
    # Coins row
    draw.ellipse((wealth_start_x, 56, wealth_start_x + 16, 72), fill=(255, 215, 0, 255))
    draw.text((wealth_start_x + 24, 51), f"{coins} Coins", fill=(255, 230, 150, 255), font=font_stat)
    
    # Karma row
    draw.ellipse((wealth_start_x, 86, wealth_start_x + 16, 102), fill=(180, 100, 255, 255))
    draw.text((wealth_start_x + 24, 81), f"{karma} Karma", fill=(210, 170, 255, 255), font=font_stat)
    
    # Unspent Stat Points Alert
    stat_points = data.get('stat_points', 0)
    if stat_points > 0:
        alert_y = 120
        draw.rounded_rectangle(
            (wealth_start_x - 10, alert_y, wealth_start_x + 180, alert_y + 26), 
            radius=6, 
            fill=(46, 204, 113, 40), 
            outline=(46, 204, 113, 200), 
            width=1
        )
        draw.text((wealth_start_x + 8, alert_y + 4), f"+{stat_points} Stat Points Available", fill=(46, 204, 113, 255), font=font_badge)
        
    # 5. EXP Progress Bar (Full Width across info column)
    exp = data.get('exp', 0)
    next_exp = data.get('next_exp', 50)
    exp_ratio = min(1.0, max(0.0, exp / next_exp)) if next_exp > 0 else 0.0
    
    bar_x = 205
    bar_y = 200
    bar_w = 540
    bar_h = 14
    
    # EXP Label
    draw.text((bar_x, bar_y - 22), "Experience (EXP)", fill=(180, 180, 200, 255), font=font_stat)
    exp_progress_text = f"{exp} / {next_exp} XP"
    progress_text_w = draw.textlength(exp_progress_text, font=font_stat)
    draw.text((bar_x + bar_w - progress_text_w, bar_y - 22), exp_progress_text, fill=(220, 220, 220, 255), font=font_stat)
    
    # Bar Track
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=6, fill=(40, 40, 50, 255))
    # Bar Fill
    if exp_ratio > 0:
        draw.rounded_rectangle((bar_x, bar_y, bar_x + int(bar_w * exp_ratio), bar_y + bar_h), radius=6, fill=(114, 137, 218, 255))
        
    # 6. Combat Stats Layout (Lower Panel)
    # Column 1: HP & ATK
    # Column 2: DEF & AGL
    col1_x = 50
    col2_x = 430
    col_w = 320
    
    hp_val = user_record.hp
    max_hp = user_record.max_hp
    hp_ratio = min(1.0, max(0.0, hp_val / max_hp)) if max_hp > 0 else 0.0
    
    # HP Bar
    hp_y = 280
    draw.text((col1_x, hp_y - 22), "Health Points (HP)", fill=(230, 230, 230, 255), font=font_stat)
    hp_text = f"{hp_val} / {max_hp}"
    hp_text_w = draw.textlength(hp_text, font=font_stat_val)
    draw.text((col1_x + col_w - hp_text_w, hp_y - 22), hp_text, fill=(255, 75, 75, 255), font=font_stat_val)
    # Track
    draw.rounded_rectangle((col1_x, hp_y, col1_x + col_w, hp_y + 10), radius=5, fill=(40, 40, 50, 255))
    if hp_ratio > 0:
        draw.rounded_rectangle((col1_x, hp_y, col1_x + int(col_w * hp_ratio), hp_y + 10), radius=5, fill=(255, 75, 75, 255))
        
    # ATK Bar
    atk_val = data.get('attack', 10)
    # Normalise against max stat limit of 200
    atk_ratio = min(1.0, atk_val / 200.0)
    atk_y = 350
    draw.text((col1_x, atk_y - 22), "Attack (ATK)", fill=(230, 230, 230, 255), font=font_stat)
    atk_text = str(atk_val)
    atk_text_w = draw.textlength(atk_text, font=font_stat_val)
    draw.text((col1_x + col_w - atk_text_w, atk_y - 22), atk_text, fill=(255, 127, 80, 255), font=font_stat_val)
    # Track
    draw.rounded_rectangle((col1_x, atk_y, col1_x + col_w, atk_y + 10), radius=5, fill=(40, 40, 50, 255))
    if atk_ratio > 0:
        draw.rounded_rectangle((col1_x, atk_y, col1_x + int(col_w * atk_ratio), atk_y + 10), radius=5, fill=(255, 127, 80, 255))
        
    # DEF Bar
    def_val = data.get('defense', 7)
    def_ratio = min(1.0, def_val / 200.0)
    def_y = 280
    draw.text((col2_x, def_y - 22), "Defense (DEF)", fill=(230, 230, 230, 255), font=font_stat)
    def_text = str(def_val)
    def_text_w = draw.textlength(def_text, font=font_stat_val)
    draw.text((col2_x + col_w - def_text_w, def_y - 22), def_text, fill=(30, 144, 255, 255), font=font_stat_val)
    # Track
    draw.rounded_rectangle((col2_x, def_y, col2_x + col_w, def_y + 10), radius=5, fill=(40, 40, 50, 255))
    if def_ratio > 0:
        draw.rounded_rectangle((col2_x, def_y, col2_x + int(col_w * def_ratio), def_y + 10), radius=5, fill=(30, 144, 255, 255))
        
    # AGL Bar
    agl_val = data.get('agility', 8)
    agl_ratio = min(1.0, agl_val / 200.0)
    agl_y = 350
    draw.text((col2_x, agl_y - 22), "Agility (AGL)", fill=(230, 230, 230, 255), font=font_stat)
    agl_text = str(agl_val)
    agl_text_w = draw.textlength(agl_text, font=font_stat_val)
    draw.text((col2_x + col_w - agl_text_w, agl_y - 22), agl_text, fill=(46, 204, 113, 255), font=font_stat_val)
    # Track
    draw.rounded_rectangle((col2_x, agl_y, col2_x + col_w, agl_y + 10), radius=5, fill=(40, 40, 50, 255))
    if agl_ratio > 0:
        draw.rounded_rectangle((col2_x, agl_y, col2_x + int(col_w * agl_ratio), agl_y + 10), radius=5, fill=(46, 204, 113, 255))
        
    # Save image to bytes and wrap in discord.File
    buffer = BytesIO()
    im.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(fp=buffer, filename=f"profile_{user.id}.png")
