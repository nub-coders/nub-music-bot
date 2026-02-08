"""
Font Reference Guide - Quick Examples
======================================

Import the fonts module:
    from fonts import *

PREMIUM FONTS:
--------------

1. bold_sans - Modern Bold Sans-Serif
   Input: bold_sans("Hello World")
   Output: 𝗛𝗲𝗹𝗹𝗼 𝗪𝗼𝗿𝗹𝗱

2. italic_sans - Modern Italic Sans-Serif
   Input: italic_sans("Hello World")
   Output: 𝘏𝘦𝘭𝘭𝘰 𝘞𝘰𝘳𝘭𝘥

3. bold_italic_sans - Bold Italic Combination
   Input: bold_italic_sans("Hello World")
   Output: 𝙃𝙚𝙡𝙡𝙤 𝙒𝙤𝙧𝙡𝙙

4. fancy_bold - Serif Bold Style
   Input: fancy_bold("Hello World")
   Output: 𝐇𝐞𝐥𝐥𝐨 𝐖𝐨𝐫𝐥𝐝

5. neon - Neon Squared Effect
   Input: neon("Hello")
   Output: 🄷🄴🄻🄻🄾

6. sparkle - Add Sparkles
   Input: sparkle("Success")
   Output: ✨ Success ✨

7. fire - Fire Effect
   Input: fire("Hot")
   Output: 🔥 Hot 🔥

EXISTING FONTS (Still Available):
----------------------------------

- typewriter("text") → 𝚝𝚎𝚡𝚝
- upper_mono("text") → ᴛᴇxᴛ
- outline("text") → 𝕥𝕖𝕩𝕥
- serief("text") → 𝐭𝐞𝐱𝐭
- script("text") → 𝓽𝓮𝓍𝓽
- bold_script("text") → 𝓽𝓮𝔁𝓽
- smallcap("text") → ᴛᴇxᴛ
- cool("text") → 𝑡𝑒𝑥𝑡
- bold_cool("text") → 𝒕𝒆𝒙𝒕
- tiny("text") → ᵗᵉˣᵗ
- comic("text") → ᵀᗴ᙭ᵀ
- san("text") → 𝘁𝗲𝘅𝘁
- slant("text" → text with italics
- circles("text") → ⓣⓔⓧⓣ
- dark_circle("text") → 🅣🅔🅧🅣
- gothic("text") → 𝔱𝔢𝔵𝔱
- bold_gothic("text") → 𝖙𝖊𝖝𝖙
- square("text") → 🅃🄴🅇🅃
- dark_square("text") → 🆃🅴🆇🆃
- strikethrough("text") → t̶e̶x̶t̶
- superscript("text") → ᵗᵉˣᵗ
- underline("text") → t̲e̲x̲t̲
- frozen("text") → t༙e༙x༙t༙

USAGE IN BOT MESSAGES:
----------------------

Example 1: Status Message
    message = f"✅ {bold_sans('SUCCESS')}\\n{italic_sans('Action completed')}"

Example 2: Error Message
    message = f"❌ {bold_sans('ERROR')}\\n{italic_sans('Something went wrong')}"

Example 3: Information
    message = f"ℹ️ {bold_sans('INFO')}\\n{italic_sans('Processing your request')}"

Example 4: With Box Drawing
    message = f"{bold_sans('PLAYING')}\\n╭──────╮\\n│ 🎵 Song\\n╰──────╯"

EMOJI COMBINATIONS:
-------------------

Status:
✅ Success
❌ Error
⚠️ Warning
ℹ️ Info
🚫 Blocked
👑 Owner
💎 Premium

Music:
🎵 Music
🎧 Headphones
⏸️ Pause
▶️ Play
⏭️ Skip
🔄 Loop
📡 Streaming
🎶 Notes

Users:
👤 User
👥 Group
🔓 Unlocked
🔒 Locked
📦 Package
💬 Message

BOX DRAWING CHARACTERS:
-----------------------

Simple Box:
╭──────╮
│ Text │
╰──────╯

Double Line:
╔══════╗
║ Text ║
╚══════╝

Mixed:
┌──────┐
├──────┤
└──────┘

BEST PRACTICES:
---------------

1. Use bold_sans() for titles and headers
2. Use italic_sans() for descriptions and details
3. Combine emojis with text for visual appeal
4. Use box drawing for structured layouts
5. Keep messages concise and readable
6. Test in Telegram to ensure rendering

COMPLETE MESSAGE EXAMPLE:
-------------------------

await message.reply(
    f"🎵 {bold_sans('NOW PLAYING')}\\n"
    f"╭─────────────────╮\\n"
    f"│ 🎧 {italic_sans('Song Title')}\\n"
    f"│ ⏱️ {italic_sans('Duration: 3:45')}\\n"
    f"│ 👤 {italic_sans('Requested by: User')}\\n"
    f"╰─────────────────╯\\n"
    f"✨ {sparkle('Enjoy!')}"
)

"""
