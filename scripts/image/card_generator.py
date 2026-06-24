import os
import aiohttp
from io import BytesIO
import discord
from PIL import Image, ImageDraw, ImageFont

def get_font(font_name: str, size: int):
    # Map to local premium Roboto fonts first
    is_bold = "b.ttf" in font_name.lower() or "bold" in font_name.lower()
    local_font = "assets/fonts/Roboto-Bold.ttf" if is_bold else "assets/fonts/Roboto-Regular.ttf"
    
    try:
        if os.path.exists(local_font):
            return ImageFont.truetype(local_font, size)
    except OSError:
        pass

    # Fallbacks for Windows and other systems
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

def draw_crest(draw: ImageDraw.Draw, class_name: str, x: int, y: int, size: int = 40, scale: int = 1):
    """Draws a procedural class crest outline."""
    color = (255, 255, 255, 200)
    class_lower = class_name.lower()
    w_2 = 2 * scale
    w_3 = 3 * scale
    
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
        draw.polygon(points, outline=color, fill=(255, 75, 75, 40), width=w_2)
        # Inner cross
        draw.line([(x, y - size // 2), (x, y + size // 2)], fill=color, width=w_2)
        draw.line([(x - size // 2, y), (x + size // 2, y)], fill=color, width=w_2)
        
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
        draw.polygon(points, outline=color, fill=(30, 144, 255, 40), width=w_2)
        # Draw small inner circle
        r_inner = 3 * scale
        draw.ellipse((x - r_inner, y - r_inner, x + r_inner, y + r_inner), outline=color, fill=(0, 255, 255, 150), width=1 * scale)
        
    elif class_lower == "rogue":
        # Draw two crossed daggers (lines)
        draw.line([(x - size // 2, y - size // 2), (x + size // 2, y + size // 2)], fill=color, width=w_3)
        draw.line([(x + size // 2, y - size // 2), (x - size // 2, y + size // 2)], fill=color, width=w_3)
        # Dagger hilts
        draw.line([(x - size // 2, y - size // 4), (x - size // 4, y - size // 2)], fill=(255, 215, 0, 255), width=w_2)
        draw.line([(x + size // 2, y - size // 4), (x + size // 4, y - size // 2)], fill=(255, 215, 0, 255), width=w_2)
        
    else:
        # Default simple ring for None
        draw.ellipse((x - size // 2, y - size // 2, x + size // 2, y + size // 2), outline=(150, 150, 150, 200), width=w_2)

async def generate_profile_card(user: discord.Member, user_record, is_premium: bool, lang: str = "en") -> discord.File:
    # Scale multiplier for high-res output (2x = 1600x900)
    scale = 2
    
    # 1. Create base canvas and measure context
    im = Image.new("RGBA", (800 * scale, 450 * scale))
    draw_base = ImageDraw.Draw(im)
    
    # Gradient: Very dark violet (23, 21, 35) to sleek dark blue (30, 35, 55)
    for x in range(800 * scale):
        r = int(23 + (30 - 23) * (x / (800 * scale)))
        g = int(21 + (35 - 21) * (x / (800 * scale)))
        b = int(35 + (55 - 35) * (x / (800 * scale)))
        draw_base.line([(x, 0), (x, 450 * scale)], fill=(r, g, b, 255))

    # Initialize fonts (using high-res Roboto fonts)
    font_title = get_font("Segoeui.ttf", 32 * scale)
    font_sub = get_font("Segoeui.ttf", 20 * scale)
    font_stat = get_font("Segoeui.ttf", 18 * scale)
    font_stat_val = get_font("Segoeuib.ttf", 18 * scale)
    font_badge = get_font("Segoeuib.ttf", 14 * scale)
    font_title_badge = get_font("Segoeuib.ttf", 12 * scale)
    font_exp_label = get_font("Segoeui.ttf", 16 * scale)
    font_exp_val = get_font("Segoeuib.ttf", 16 * scale)
    
    # 2. Retrieve Player Info & calculate dimensions
    data = user_record.data
    name = data.get('name', user.name)
    player_class = data.get('class', 'None')
    level = data.get('level', 1)
    
    # Dynamic font scaling for player name
    max_name_width = 330 * scale
    font_size = 32
    font_title_scaled = get_font("Segoeui.ttf", font_size * scale)
    name_width = draw_base.textlength(name, font=font_title_scaled)
    
    while name_width > max_name_width and font_size > 22:
        font_size -= 2
        font_title_scaled = get_font("Segoeui.ttf", font_size * scale)
        name_width = draw_base.textlength(name, font=font_title_scaled)
        
    display_name = name
    while name_width > max_name_width and len(display_name) > 3:
        display_name = display_name[:-4] + "..."
        name_width = draw_base.textlength(display_name, font=font_title_scaled)

    # 3. Calculate Predefined Title Badge dimensions
    active_title = data.get('active_title', 'novice_adventurer')
    titles_list = data.get('titles', ['novice_adventurer'])
    if active_title not in titles_list:
        active_title = 'novice_adventurer'
        
    from scripts.game.profile import PREDEFINED_TITLES
    title_info = PREDEFINED_TITLES.get(active_title, PREDEFINED_TITLES['novice_adventurer'])
    title_name = title_info.get(lang, title_info.get("en", active_title))
    
    text_w = draw_base.textlength(title_name, font=font_title_badge)
    badge_x = 205 * scale
    badge_y = 84 * scale
    badge_h = 22 * scale
    badge_w = int(text_w + 16 * scale)
    
    bg_color = title_info.get("bg_color", (150, 200, 255, 30))
    border_color = title_info.get("border_color", (150, 200, 255, 100))
    text_color = title_info.get("color", (150, 200, 255, 255))
    style = title_info.get("style", "default")
    
    # 4. Calculate Premium Badge dimensions
    p_badge_w = 0
    if is_premium:
        badge_text = "DREAM WEAVER"
        badge_text_w = draw_base.textlength(badge_text, font=font_title_badge)
        p_badge_w = int(badge_text_w + 16 * scale)
        p_badge_x = badge_x + badge_w + 10 * scale
        p_badge_y = 84 * scale

    # 5. Draw transparent elements on separate overlay to ensure correct alpha compositing
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    
    # Premium card border
    if is_premium:
        overlay_draw.rectangle((0, 0, 800 * scale - 1, 450 * scale - 1), outline=(255, 215, 0, 150), width=4 * scale)
        
    # Glassmorphism panels (blend smoothly with base gradient)
    # Upper panel
    overlay_draw.rounded_rectangle((30 * scale, 30 * scale, 770 * scale, 230 * scale), radius=12 * scale, fill=(10, 10, 20, 120), outline=(255, 255, 255, 20), width=scale)
    # Lower panel
    overlay_draw.rounded_rectangle((30 * scale, 245 * scale, 770 * scale, 420 * scale), radius=12 * scale, fill=(10, 10, 20, 120), outline=(255, 255, 255, 20), width=scale)
    
    # Title badge glows
    if style in ["glowing_gold", "gold_shiny"]:
        glow_color = (255, 215, 0, 80) if style == "glowing_gold" else (255, 215, 0, 40)
        overlay_draw.rounded_rectangle((badge_x - 2 * scale, badge_y - 2 * scale, badge_x + badge_w + 2 * scale, badge_y + badge_h + 2 * scale), radius=6 * scale, fill=None, outline=glow_color, width=2 * scale)
        glow_color2 = (255, 215, 0, 30) if style == "glowing_gold" else (255, 215, 0, 15)
        overlay_draw.rounded_rectangle((badge_x - 4 * scale, badge_y - 4 * scale, badge_x + badge_w + 4 * scale, badge_y + badge_h + 4 * scale), radius=7 * scale, fill=None, outline=glow_color2, width=scale)
    elif style == "bloody_red":
        glow_color = (139, 0, 0, 80)
        overlay_draw.rounded_rectangle((badge_x - 2 * scale, badge_y - 2 * scale, badge_x + badge_w + 2 * scale, badge_y + badge_h + 2 * scale), radius=6 * scale, fill=None, outline=glow_color, width=2 * scale)
    elif style == "rainbow":
        glow_color = (255, 255, 255, 40)
        overlay_draw.rounded_rectangle((badge_x - 2 * scale, badge_y - 2 * scale, badge_x + badge_w + 2 * scale, badge_y + badge_h + 2 * scale), radius=6 * scale, fill=None, outline=glow_color, width=2 * scale)
        
    # Title badge background
    overlay_draw.rounded_rectangle(
        (badge_x, badge_y, badge_x + badge_w, badge_y + badge_h),
        radius=5 * scale,
        fill=bg_color,
        outline=border_color,
        width=scale
    )
    
    # Premium Badge background
    if is_premium:
        overlay_draw.rounded_rectangle(
            (p_badge_x, p_badge_y, p_badge_x + p_badge_w, p_badge_y + badge_h), 
            radius=5 * scale, 
            fill=(255, 215, 0, 40), 
            outline=(255, 215, 0, 200), 
            width=scale
        )
        
    # Class Crest
    draw_crest(overlay_draw, player_class, 225 * scale, 125 * scale, size=24 * scale, scale=scale)
    
    # Unspent Stat Points Alert
    stat_points = data.get('stat_points', 0)
    wealth_start_x = 560 * scale
    if stat_points > 0:
        alert_y = 126 * scale
        overlay_draw.rounded_rectangle(
            (wealth_start_x - 10 * scale, alert_y, wealth_start_x + 190 * scale, alert_y + 28 * scale), 
            radius=6 * scale, 
            fill=(46, 204, 113, 40), 
            outline=(46, 204, 113, 200), 
            width=scale
        )

    # Composite overlays onto gradient base
    im = Image.alpha_composite(im, overlay)
    draw = ImageDraw.Draw(im)

    # 6. Retrieve and draw Avatar
    avatar_img = await fetch_avatar(user.display_avatar.url)
    avatar_size = (130 * scale, 130 * scale)
    avatar_resized = avatar_img.resize(avatar_size).convert("RGBA")
    
    mask = Image.new("L", avatar_size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, avatar_size[0], avatar_size[1]), fill=255)
    im.paste(avatar_resized, (50 * scale, 50 * scale), mask)
    
    border_color = (255, 215, 0, 255) if is_premium else (114, 137, 218, 255)
    draw.ellipse((48 * scale, 48 * scale, 50 * scale + avatar_size[0], 50 * scale + avatar_size[1]), outline=border_color, width=3 * scale)

    # 7. Draw Texts (Opaque, solid alpha=255)
    name_y = 40 * scale
    draw.text((205 * scale, name_y), display_name, fill=(255, 255, 255, 255), font=font_title_scaled)
    
    # Title badge text
    text_x = badge_x + 8 * scale
    text_y = badge_y + 3 * scale
    if style == "rainbow":
        import colorsys
        current_x = text_x
        n = len(title_name)
        for i, char in enumerate(title_name):
            hue = i / max(1, n)
            r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 1.0)
            color = (int(r * 255), int(g * 255), int(b * 255), 255)
            draw.text((current_x, text_y), char, fill=color, font=font_title_badge)
            char_w = draw.textlength(char, font=font_title_badge)
            current_x += char_w
    else:
        draw.text((text_x, text_y), title_name, fill=text_color, font=font_title_badge)
        
    # Premium Badge text
    if is_premium:
        draw.text((p_badge_x + 8 * scale, p_badge_y + 3 * scale), "DREAM WEAVER", fill=(255, 215, 0, 255), font=font_title_badge)
        
    # Class text next to crest
    class_text = f"Class: {player_class}"
    draw.text((250 * scale, 112 * scale), class_text, fill=(200, 200, 220, 255), font=font_sub)
    
    # Level text
    level_text = f"Level: {level}"
    draw.text((205 * scale, 142 * scale), level_text, fill=(138, 220, 138, 255), font=font_sub)
    
    # Wealth Details
    coins = data.get('coins', 0)
    karma = data.get('karma', 0)
    
    # Coins row
    draw.ellipse((wealth_start_x, 55 * scale, wealth_start_x + 18 * scale, 73 * scale), fill=(255, 215, 0, 255))
    draw.text((wealth_start_x + 26 * scale, 50 * scale), f"{coins} Coins", fill=(255, 230, 150, 255), font=font_sub)
    
    # Karma row
    draw.ellipse((wealth_start_x, 87 * scale, wealth_start_x + 18 * scale, 105 * scale), fill=(180, 100, 255, 255))
    draw.text((wealth_start_x + 26 * scale, 82 * scale), f"{karma} Karma", fill=(210, 170, 255, 255), font=font_sub)
    
    # Unspent Stat Points Alert text
    if stat_points > 0:
        alert_y = 126 * scale
        draw.text((wealth_start_x + 8 * scale, alert_y + 4 * scale), f"+{stat_points} Stat Points Available", fill=(46, 204, 113, 255), font=font_title_badge)
        
    # 8. EXP Progress Bar
    exp = data.get('exp', 0)
    next_exp = data.get('next_exp', 50)
    exp_ratio = min(1.0, max(0.0, exp / next_exp)) if next_exp > 0 else 0.0
    
    bar_x = 205 * scale
    bar_y = 196 * scale
    bar_w = 540 * scale
    bar_h = 10 * scale
    
    # EXP labels
    draw.text((bar_x, bar_y - 24 * scale), "Experience (EXP)", fill=(180, 180, 200, 255), font=font_exp_label)
    exp_progress_text = f"{exp} / {next_exp} XP"
    progress_text_w = draw.textlength(exp_progress_text, font=font_exp_val)
    draw.text((bar_x + bar_w - progress_text_w, bar_y - 24 * scale), exp_progress_text, fill=(220, 220, 220, 255), font=font_exp_val)
    
    # EXP Bar tracks and fills
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=5 * scale, fill=(40, 40, 50, 255))
    if exp_ratio > 0:
        draw.rounded_rectangle((bar_x, bar_y, bar_x + int(bar_w * exp_ratio), bar_y + bar_h), radius=5 * scale, fill=(114, 137, 218, 255))
        
    # 9. Combat Stats Layout (Lower Panel)
    col1_x = 60 * scale
    col2_x = 430 * scale
    col_w = 310 * scale
    
    hp_val = user_record.hp
    max_hp = user_record.max_hp
    hp_ratio = min(1.0, max(0.0, hp_val / max_hp)) if max_hp > 0 else 0.0
    
    # HP Bar
    hp_y = 304 * scale
    draw.text((col1_x, hp_y - 25 * scale), "Health Points (HP)", fill=(230, 230, 230, 255), font=font_stat)
    hp_text = f"{hp_val} / {max_hp}"
    hp_text_w = draw.textlength(hp_text, font=font_stat_val)
    draw.text((col1_x + col_w - hp_text_w, hp_y - 25 * scale), hp_text, fill=(255, 75, 75, 255), font=font_stat_val)
    
    draw.rounded_rectangle((col1_x, hp_y, col1_x + col_w, hp_y + 10 * scale), radius=5 * scale, fill=(40, 40, 50, 255))
    if hp_ratio > 0:
        draw.rounded_rectangle((col1_x, hp_y, col1_x + int(col_w * hp_ratio), hp_y + 10 * scale), radius=5 * scale, fill=(255, 75, 75, 255))
        
    # ATK Bar
    atk_val = data.get('attack', 10)
    atk_ratio = min(1.0, atk_val / 200.0)
    atk_y = 374 * scale
    draw.text((col1_x, atk_y - 25 * scale), "Attack (ATK)", fill=(230, 230, 230, 255), font=font_stat)
    atk_text = str(atk_val)
    atk_text_w = draw.textlength(atk_text, font=font_stat_val)
    draw.text((col1_x + col_w - atk_text_w, atk_y - 25 * scale), atk_text, fill=(255, 127, 80, 255), font=font_stat_val)
    
    draw.rounded_rectangle((col1_x, atk_y, col1_x + col_w, atk_y + 10 * scale), radius=5 * scale, fill=(40, 40, 50, 255))
    if atk_ratio > 0:
        draw.rounded_rectangle((col1_x, atk_y, col1_x + int(col_w * atk_ratio), atk_y + 10 * scale), radius=5 * scale, fill=(255, 127, 80, 255))
        
    # DEF Bar
    def_val = data.get('defense', 7)
    def_ratio = min(1.0, def_val / 200.0)
    def_y = 304 * scale
    draw.text((col2_x, def_y - 25 * scale), "Defense (DEF)", fill=(230, 230, 230, 255), font=font_stat)
    def_text = str(def_val)
    def_text_w = draw.textlength(def_text, font=font_stat_val)
    draw.text((col2_x + col_w - def_text_w, def_y - 25 * scale), def_text, fill=(30, 144, 255, 255), font=font_stat_val)
    
    draw.rounded_rectangle((col2_x, def_y, col2_x + col_w, def_y + 10 * scale), radius=5 * scale, fill=(40, 40, 50, 255))
    if def_ratio > 0:
        draw.rounded_rectangle((col2_x, def_y, col2_x + int(col_w * def_ratio), def_y + 10 * scale), radius=5 * scale, fill=(30, 144, 255, 255))
        
    # AGL Bar
    agl_val = data.get('agility', 8)
    agl_ratio = min(1.0, agl_val / 200.0)
    agl_y = 374 * scale
    draw.text((col2_x, agl_y - 25 * scale), "Agility (AGL)", fill=(230, 230, 230, 255), font=font_stat)
    agl_text = str(agl_val)
    agl_text_w = draw.textlength(agl_text, font=font_stat_val)
    draw.text((col2_x + col_w - agl_text_w, agl_y - 25 * scale), agl_text, fill=(46, 204, 113, 255), font=font_stat_val)
    
    draw.rounded_rectangle((col2_x, agl_y, col2_x + col_w, agl_y + 10 * scale), radius=5 * scale, fill=(40, 40, 50, 255))
    if agl_ratio > 0:
        draw.rounded_rectangle((col2_x, agl_y, col2_x + int(col_w * agl_ratio), agl_y + 10 * scale), radius=5 * scale, fill=(46, 204, 113, 255))
        
    # Ensure final output is fully opaque to avoid transparent holes
    final_im = Image.new("RGB", im.size)
    final_im.paste(im, (0, 0), im)
    
    # Save image to bytes and wrap in discord.File
    buffer = BytesIO()
    final_im.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(fp=buffer, filename=f"profile_{user.id}.png")
