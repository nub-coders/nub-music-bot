
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import random

def example_queue_handler():
    # Simulate 20 random queue items
    items = [
        {"title": f"Song {i+1} - {random.choice(['Love', 'Dance', 'Chill', 'Rock', 'Pop'])}", "duration": f"{random.randint(1,5)}:{random.randint(0,59):02d}"}
        for i in range(20)
    ]
    text_lines = [f"Queue for this chat (max 20):\n"]
    for idx, item in enumerate(items, 1):
        title = item.get("title", "Unknown")
        duration = item.get("duration", "-")
        text_lines.append(f"{idx}. {title} | {duration}")
    text = "\n".join(text_lines)

    width, height = 800, 600
    # create a slightly textured / gradient background for better visuals
    img = Image.new("RGBA", (width, height), (40, 40, 40, 255))
    draw = ImageDraw.Draw(img)

    # optional subtle vertical gradient
    for y in range(height):
        shade = int(30 + (y / height) * 30)  # 30 -> 60
        draw.line([(0, y), (width, y)], fill=(shade, shade, shade, 255))
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except:
        font = ImageFont.load_default()
    # Draw the text onto a separate layer so we can composite a dark overlay beneath it
    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)
    text_draw.multiline_text((40, 40), text, fill=(255, 255, 255, 255), font=font, spacing=8)

    # Create a semi-transparent black overlay to darken the background and improve readability
    darkness = 150  # 0 (no dark) .. 255 (completely black)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, darkness))

    # Composite: background -> overlay -> text
    composed = Image.alpha_composite(img, overlay)
    composed = Image.alpha_composite(composed, text_layer)

    # Save the final image as RGB
    composed.convert("RGB").save("queue_example.png")
    print("queue_example.png generated with random queue items.")

if __name__ == "__main__":
    example_queue_handler()
