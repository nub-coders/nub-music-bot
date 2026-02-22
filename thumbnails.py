import random
import os
import re
import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from youtubesearchpython.__future__ import VideosSearch

import logging
from pyrogram import Client, filters
logger = logging.getLogger("pyrogram")
def changeImageSize(maxWidth, maxHeight, image):
    widthRatio = maxWidth / image.size[0]
    heightRatio = maxHeight / image.size[1]
    newWidth = int(widthRatio * image.size[0])
    newHeight = int(heightRatio * image.size[1])
    newImage = image.resize((newWidth, newHeight))
    return newImage

def truncate(text):
    list = text.split(" ")
    text1 = ""
    text2 = ""    
    for i in list:
        if len(text1) + len(i) < 30:        
            text1 += " " + i
        elif len(text2) + len(i) < 30:       
            text2 += " " + i

    text1 = text1.strip()
    text2 = text2.strip()     
    return [text1,text2]

def random_color():
    return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

def generate_gradient(width, height, start_color, end_color):
    base = Image.new('RGBA', (width, height), start_color)
    top = Image.new('RGBA', (width, height), end_color)
    mask = Image.new('L', (width, height))
    mask_data = []
    for y in range(height):
        mask_data.extend([int(60 * (y / height))] * width)
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base

def add_border(image, border_width, border_color):
    width, height = image.size
    new_width = width + 2 * border_width
    new_height = height + 2 * border_width
    new_image = Image.new("RGBA", (new_width, new_height), border_color)
    new_image.paste(image, (border_width, border_width))
    return new_image

def crop_center_circle(img, output_size, border, border_color, crop_scale=1.5):
    half_the_width = img.size[0] / 2
    half_the_height = img.size[1] / 2
    larger_size = int(output_size * crop_scale)
    img = img.crop(
        (
            half_the_width - larger_size/2,
            half_the_height - larger_size/2,
            half_the_width + larger_size/2,
            half_the_height + larger_size/2
        )
    )
    
    img = img.resize((output_size - 2*border, output_size - 2*border))
    
    
    final_img = Image.new("RGBA", (output_size, output_size), border_color)
    
    
    mask_main = Image.new("L", (output_size - 2*border, output_size - 2*border), 0)
    draw_main = ImageDraw.Draw(mask_main)
    draw_main.ellipse((0, 0, output_size - 2*border, output_size - 2*border), fill=255)
    
    final_img.paste(img, (border, border), mask_main)
    
    
    mask_border = Image.new("L", (output_size, output_size), 0)
    draw_border = ImageDraw.Draw(mask_border)
    draw_border.ellipse((0, 0, output_size, output_size), fill=255)
    
    result = Image.composite(final_img, Image.new("RGBA", final_img.size, (0, 0, 0, 0)), mask_border)
    
    return result

def draw_text_with_shadow(background, draw, position, text, font, fill, shadow_offset=(3, 3), shadow_blur=5):
    
    shadow = Image.new('RGBA', background.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    
    
    shadow_draw.text(position, text, font=font, fill="black")
    
    
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    
    
    background.paste(shadow, shadow_offset, shadow)
    
    
    draw.text(position, text, font=font, fill=fill)


async def get_thumb(title, duration, thumbnail, channel=None, views=None, videoid=None):
    try:
        # Generate a random string to use in filenames
        import uuid
        random_id = str(uuid.uuid4())[:8]
        temp_files_to_delete = []
        
        # Sanitize videoid to remove invalid path characters
        if videoid:
            videoid = str(videoid).replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
        else:
            videoid = "unknown"

        # Handle case when thumbnail is None or doesn't exist
        if thumbnail is None:
            thumbnail = "thumbnail.png"

        # Check if thumbnail is a local file path
        if os.path.exists(thumbnail):
            image_path = thumbnail
            # If no title provided and it's a local file, use default
            if not title:
                title = "Now Playing"
        else:
            # Download thumbnail from URL
            async with aiohttp.ClientSession() as session:
                async with session.get(thumbnail) as resp:
                    if resp.status == 200:
                        # Ensure cache directory exists
                        os.makedirs("cache", exist_ok=True)
                        # Use random ID in filename to avoid conflicts
                        temp_thumb_path = f"cache/thumb_{random_id}_{videoid}.png"
                        f = await aiofiles.open(temp_thumb_path, mode="wb")
                        await f.write(await resp.read())
                        await f.close()
                        image_path = temp_thumb_path
                        # Add to list of files to delete
                        temp_files_to_delete.append(temp_thumb_path)
                    else:
                        # Fallback to default thumbnail if download fails
                        image_path = "thumbnail.png"

        # Default values for channel and views if None
        channel = channel or "Telegram"
        views = views or "1M"

        youtube = Image.open(image_path)
        image1 = changeImageSize(1280, 720, youtube)
        image2 = image1.convert("RGBA")
        
        # Create premium multi-gradient background
        background = image2.filter(filter=ImageFilter.GaussianBlur(30))
        enhancer = ImageEnhance.Brightness(background)
        background = enhancer.enhance(0.3)
        
        # Create sophisticated tri-color gradient
        gradient_colors = [
            (138, 43, 226),   # Blue-Violet
            (220, 20, 60),    # Crimson
            (255, 140, 0),    # Dark Orange
            (0, 191, 255),    # Deep Sky Blue
            (255, 20, 147),   # Deep Pink
            (50, 205, 50)     # Lime Green
        ]
        
        primary_color = random.choice(gradient_colors)
        gradient_colors.remove(primary_color)
        secondary_color = random.choice(gradient_colors)
        
        # Create dynamic gradient overlay
        gradient = Image.new('RGBA', (1280, 720), primary_color + (0,))
        for y in range(720):
            alpha = int(180 * (y / 720))
            r = int(primary_color[0] + (secondary_color[0] - primary_color[0]) * (y / 720))
            g = int(primary_color[1] + (secondary_color[1] - primary_color[1]) * (y / 720))
            b = int(primary_color[2] + (secondary_color[2] - primary_color[2]) * (y / 720))
            for x in range(1280):
                gradient.putpixel((x, y), (r, g, b, alpha))
        
        background = Image.alpha_composite(background, gradient)
        
        # Add noise texture for premium feel
        noise = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
        noise_pixels = []
        for y in range(720):
            for x in range(1280):
                if random.random() > 0.97:
                    noise_pixels.append(((x, y), (255, 255, 255, random.randint(10, 30))))
        for pixel in noise_pixels:
            noise.putpixel(pixel[0], pixel[1])
        background = Image.alpha_composite(background, noise)

        draw = ImageDraw.Draw(background)
        
        # Modern font setup with better fallbacks
        try:
            title_font = ImageFont.truetype("font3.ttf", 52)
        except:
            try:
                title_font = ImageFont.truetype("font.ttf", 52)
            except:
                title_font = ImageFont.load_default()
        
        try:
            subtitle_font = ImageFont.truetype("font.ttf", 28)
        except:
            subtitle_font = ImageFont.load_default()
        
        try:
            info_font = ImageFont.truetype("font2.ttf", 24)
        except:
            info_font = ImageFont.load_default()
        
        try:
            time_font = ImageFont.truetype("font.ttf", 26)
        except:
            time_font = ImageFont.load_default()

        # Create glassmorphism card for content
        card_x, card_y = 80, 80
        card_width, card_height = 1120, 560
        
        # Glassmorphism background
        glass_card = Image.new('RGBA', (card_width, card_height), (255, 255, 255, 0))
        glass_draw = ImageDraw.Draw(glass_card)
        
        # Rounded rectangle with gradient
        corner_radius = 30
        glass_draw.rounded_rectangle(
            [(0, 0), (card_width, card_height)],
            radius=corner_radius,
            fill=(255, 255, 255, 25),
            outline=(255, 255, 255, 80),
            width=2
        )
        
        # Apply blur to glass card for frosted effect
        glass_card = glass_card.filter(ImageFilter.GaussianBlur(2))
        background.paste(glass_card, (card_x, card_y), glass_card)
        
        # Create premium circular album art with neon glow
        album_size = 340
        album_border = 8
        neon_glow_color = primary_color
        
        # Create multiple glow layers for neon effect
        for glow_layer in range(3, 0, -1):
            glow_size = album_size + (glow_layer * 20)
            glow = Image.new('RGBA', (glow_size, glow_size), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow)
            glow_alpha = max(10, 50 - (glow_layer * 15))
            glow_draw.ellipse(
                [(0, 0), (glow_size, glow_size)],
                fill=neon_glow_color + (glow_alpha,)
            )
            glow = glow.filter(ImageFilter.GaussianBlur(15 + glow_layer * 5))
            glow_pos = (
                card_x + 60 - (glow_size - album_size) // 2,
                card_y + (card_height - glow_size) // 2
            )
            background.paste(glow, glow_pos, glow)
        
        # Album art circle
        circle_thumbnail = crop_center_circle(youtube, album_size, album_border, (255, 255, 255), crop_scale=1.3)
        album_position = (card_x + 60, card_y + (card_height - album_size) // 2)
        background.paste(circle_thumbnail, album_position, circle_thumbnail)
        
        # Text content area
        text_x = card_x + album_size + 120
        text_area_width = card_width - album_size - 180
        
        # Title with gradient effect
        title1 = truncate(title)
        title_y = card_y + 100
        
        # Draw "NOW PLAYING" label
        label_text = "NOW PLAYING"
        draw_text_with_shadow(
            background, draw, 
            (text_x, title_y - 45), 
            label_text, 
            info_font, 
            neon_glow_color,
            shadow_offset=(2, 2),
            shadow_blur=3
        )
        
        # Song title - line 1
        draw_text_with_shadow(
            background, draw,
            (text_x, title_y),
            title1[0],
            title_font,
            (255, 255, 255),
            shadow_offset=(3, 3),
            shadow_blur=6
        )
        
        # Song title - line 2
        if title1[1]:
            draw_text_with_shadow(
                background, draw,
                (text_x, title_y + 60),
                title1[1],
                title_font,
                (255, 255, 255),
                shadow_offset=(3, 3),
                shadow_blur=6
            )
        
        # Artist/Channel info with icon
        artist_y = title_y + 140
        artist_text = f"{channel}"
        draw_text_with_shadow(
            background, draw,
            (text_x, artist_y),
            artist_text,
            subtitle_font,
            (220, 220, 255),
            shadow_offset=(2, 2),
            shadow_blur=4
        )
        
        # Views count
        views_text = f"{views[:23]} views"
        draw_text_with_shadow(
            background, draw,
            (text_x, artist_y + 40),
            views_text,
            info_font,
            (200, 200, 230),
            shadow_offset=(2, 2),
            shadow_blur=3
        )
        
        # Modern progress bar
        progress_y = card_y + card_height - 140
        progress_x = text_x
        progress_width = text_area_width - 20
        progress_height = 6
        
        # Progress bar background (track)
        track_bg = Image.new('RGBA', (progress_width, progress_height + 20), (0, 0, 0, 0))
        track_draw = ImageDraw.Draw(track_bg)
        track_draw.rounded_rectangle(
            [(0, 10), (progress_width, 10 + progress_height)],
            radius=progress_height // 2,
            fill=(255, 255, 255, 60)
        )
        background.paste(track_bg, (progress_x, progress_y), track_bg)
        
        # Progress bar fill
        if duration != "Live":
            progress_percentage = random.uniform(0.15, 0.85)
            filled_width = int(progress_width * progress_percentage)
            
            # Create gradient progress bar
            progress_bar = Image.new('RGBA', (filled_width, progress_height + 20), (0, 0, 0, 0))
            progress_draw = ImageDraw.Draw(progress_bar)
            
            # Gradient from primary to secondary color
            for x in range(filled_width):
                progress_ratio = x / filled_width
                r = int(primary_color[0] + (secondary_color[0] - primary_color[0]) * progress_ratio)
                g = int(primary_color[1] + (secondary_color[1] - primary_color[1]) * progress_ratio)
                b = int(primary_color[2] + (secondary_color[2] - primary_color[2]) * progress_ratio)
                progress_draw.line([(x, 10), (x, 10 + progress_height)], fill=(r, g, b, 255), width=1)
            
            # Add glow to progress bar
            progress_bar = progress_bar.filter(ImageFilter.GaussianBlur(1))
            background.paste(progress_bar, (progress_x, progress_y), progress_bar)
            
            # Progress indicator (circle)
            indicator_x = progress_x + filled_width
            indicator_y = progress_y + 13
            indicator_radius = 10
            
            # Glow for indicator
            for glow in range(3, 0, -1):
                glow_radius = indicator_radius + glow * 3
                draw.ellipse(
                    [indicator_x - glow_radius, indicator_y - glow_radius,
                     indicator_x + glow_radius, indicator_y + glow_radius],
                    fill=primary_color + (30,)
                )
            
            # Actual indicator
            draw.ellipse(
                [indicator_x - indicator_radius, indicator_y - indicator_radius,
                 indicator_x + indicator_radius, indicator_y + indicator_radius],
                fill=(255, 255, 255, 255)
            )
        else:
            # LIVE indicator with pulsing effect
            live_bar = Image.new('RGBA', (progress_width, progress_height + 20), (0, 0, 0, 0))
            live_draw = ImageDraw.Draw(live_bar)
            live_draw.rounded_rectangle(
                [(0, 10), (progress_width, 10 + progress_height)],
                radius=progress_height // 2,
                fill=(255, 40, 40, 220)
            )
            live_bar = live_bar.filter(ImageFilter.GaussianBlur(1))
            background.paste(live_bar, (progress_x, progress_y), live_bar)
            
            # Pulsing circle for LIVE
            pulse_x = progress_x + progress_width - 20
            pulse_y = progress_y + 13
            for pulse in range(2, 0, -1):
                pulse_radius = 8 + pulse * 4
                draw.ellipse(
                    [pulse_x - pulse_radius, pulse_y - pulse_radius,
                     pulse_x + pulse_radius, pulse_y + pulse_radius],
                    fill=(255, 40, 40, 100 - pulse * 30)
                )
        
        # Time stamps
        time_y = progress_y + 30
        draw_text_with_shadow(
            background, draw,
            (progress_x, time_y),
            "00:00",
            time_font,
            (200, 200, 240),
            shadow_offset=(1, 1),
            shadow_blur=2
        )
        
        duration_display = "LIVE" if duration == "Live" else duration
        duration_color = (255, 80, 80) if duration == "Live" else (200, 200, 240)
        draw_text_with_shadow(
            background, draw,
            (progress_x + progress_width - 80, time_y),
            duration_display,
            time_font,
            duration_color,
            shadow_offset=(1, 1),
            shadow_blur=2
        )
        
        # Control icons (if play_icons exists)
        try:
            play_icons = Image.open("play_icons.png")
            # Resize and adjust transparency
            icon_width = min(520, text_area_width - 40)
            play_icons = play_icons.resize((icon_width, int(62 * icon_width / 580)))
            
            # Add subtle glow to icons
            icons_with_glow = Image.new('RGBA', play_icons.size, (0, 0, 0, 0))
            icons_with_glow.paste(play_icons, (0, 0), play_icons)
            
            icons_position = (progress_x + (progress_width - icon_width) // 2, time_y + 50)
            background.paste(icons_with_glow, icons_position, icons_with_glow)
        except:
            # If play_icons.png doesn't exist, create simple play button
            play_y = time_y + 60
            play_x = progress_x + progress_width // 2
            
            # Play button circle
            draw.ellipse(
                [play_x - 30, play_y - 30, play_x + 30, play_y + 30],
                fill=(255, 255, 255, 200),
                outline=primary_color + (255,),
                width=3
            )
            
            # Play triangle
            draw.polygon(
                [(play_x - 10, play_y - 15), (play_x - 10, play_y + 15), (play_x + 15, play_y)],
                fill=primary_color + (255,)
            )

        # Create output file with random ID
        background = background.convert("RGB")
        background_path = f"cache/{random_id}_{videoid}_premium.png"
        background.save(background_path, quality=95, optimize=True)
        
        # Clean up all temporary files
        for temp_file in temp_files_to_delete:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return background_path

    except Exception as e:
        print(f"Error generating thumbnail for video {videoid}: {e}")
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating thumbnail for video {videoid}: {type(e).__name__} - {e}", exc_info=True)
        return None
