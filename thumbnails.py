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

        # Handle case when thumbnail is None or doesn't exist
        if thumbnail is None:
            thumbnail = "thumbnail.png"

        # Check if thumbnail is a local file path
        if os.path.exists(thumbnail):
            image_path = thumbnail
            # If no title provided and it's a local file, use default
            if not title:
                title = "Telegram Local Stream"
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
        background = image2.filter(filter=ImageFilter.BoxBlur(20))
        enhancer = ImageEnhance.Brightness(background)
        background = enhancer.enhance(0.6)

        start_gradient_color = random_color()
        end_gradient_color = random_color()
        gradient_image = generate_gradient(1280, 720, start_gradient_color, end_gradient_color)
        background = Image.blend(background, gradient_image, alpha=0.2)

        draw = ImageDraw.Draw(background)
        arial = ImageFont.truetype("font2.ttf", 30)
        font = ImageFont.truetype("font.ttf", 30)
        title_font = ImageFont.truetype("font3.ttf", 45)

        circle_thumbnail = crop_center_circle(youtube, 400, 20, start_gradient_color)
        circle_thumbnail = circle_thumbnail.resize((400, 400))
        circle_position = (120, 160)
        background.paste(circle_thumbnail, circle_position, circle_thumbnail)

        text_x_position = 565
        title1 = truncate(title)
        draw_text_with_shadow(background, draw, (text_x_position, 180), title1[0], title_font, (255, 255, 255))
        draw_text_with_shadow(background, draw, (text_x_position, 230), title1[1], title_font, (255, 255, 255))
        draw_text_with_shadow(background, draw, (text_x_position, 320), f"{channel}  |  {views[:23]}", arial, (255, 255, 255))

        line_length = 580
        line_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

        if duration != "Live":
            color_line_percentage = random.uniform(0.15, 0.85)
            color_line_length = int(line_length * color_line_percentage)
            white_line_length = line_length - color_line_length

            start_point_color = (text_x_position, 380)
            end_point_color = (text_x_position + color_line_length, 380)
            draw.line([start_point_color, end_point_color], fill=line_color, width=9)

            start_point_white = (text_x_position + color_line_length, 380)
            end_point_white = (text_x_position + line_length, 380)
            draw.line([start_point_white, end_point_white], fill="white", width=8)

            circle_radius = 10
            circle_position = (end_point_color[0], end_point_color[1])
            draw.ellipse([circle_position[0] - circle_radius, circle_position[1] - circle_radius,
                          circle_position[0] + circle_radius, circle_position[1] + circle_radius], fill=line_color)

        else:
            line_color = (255, 0, 0)
            start_point_color = (text_x_position, 380)
            end_point_color = (text_x_position + line_length, 380)
            draw.line([start_point_color, end_point_color], fill=line_color, width=9)

            circle_radius = 10
            circle_position = (end_point_color[0], end_point_color[1])
            draw.ellipse([circle_position[0] - circle_radius, circle_position[1] - circle_radius,
                          circle_position[0] + circle_radius, circle_position[1] + circle_radius], fill=line_color)

        draw_text_with_shadow(background, draw, (text_x_position, 400), "00:00", arial, (255, 255, 255))
        draw_text_with_shadow(background, draw, (1080, 400), duration, arial, (255, 255, 255))

        play_icons = Image.open("play_icons.png")
        play_icons = play_icons.resize((580, 62))
        background.paste(play_icons, (text_x_position, 450), play_icons)

        # Create output file with random ID
        background_path = f"cache/{random_id}_{videoid}_v4.png"
        background.save(background_path)
        
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
