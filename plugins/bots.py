
import asyncio
import base64
import datetime
import logging
import os
import random
import re
import requests
import time
from functools import wraps

from pyrogram import Client, filters, enums
from pyrogram.enums import ChatType, ChatMemberStatus
from pyrogram.errors import (
    StickersetInvalid,
    YouBlockedUser,
    FloodWait,
    InviteHashExpired,
    ChannelPrivate,
    UserBlocked,
    PeerIdInvalid,
    MessageDeleteForbidden
)
from pyrogram.raw.functions.messages import GetStickerSet
from pyrogram.enums import MessageEntityType
from pyrogram.raw.types import InputStickerSetShortName
from pyrogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from pytgcalls.exceptions import NotInCallError, NoActiveGroupCall
from pytgcalls.types import AudioQuality, MediaStream, VideoQuality

from config import *
from fonts import *
from tools import *
from youtube import handle_youtube, extract_video_id, format_duration
from tools import trim_title
from database import find_one, push_to_array, pull_from_array, set_fields, collection, user_sessions

async def end(client, update):
    """Handle stream end event"""
    chat_id = update.chat_id
    logger.info(f"Stream ended in chat {chat_id}")
    await dend(clients['bot'], type('obj', (object,), {'chat': type('obj', (object,), {'id': chat_id})})(), chat_id)

async def hd_stream_closed_kicked(client, update):
    """Handle voice chat closed or kicked events"""
    chat_id = update.chat_id
    logger.info(f"Voice chat closed or kicked in chat {chat_id}")
    await remove_active_chat(clients['bot'], chat_id)
    if chat_id in playing:
        playing[chat_id].clear()
    if chat_id in queues:
        queues[chat_id].clear()

# Clients will be passed as parameter instead of imported
# Get the logger
logger = logging.getLogger("pyrogram")
session = clients["session"]
call_py = clients["call_py"]






def admin_only():
    def decorator(func):
        @wraps(func)
        async def wrapper(client, update):
            try:
                logger.debug(f"Admin check initiated for {func.__name__}")

                # Handle both callback query and regular message
                if isinstance(update, CallbackQuery):
                    chat_id = update.message.chat.id
                    reply_id = update.message.id
                    user_id = update.from_user.id if update.from_user else None
                    command = update.data
                    logger.debug(f"Callback query from user {user_id} in chat {chat_id}")
                else:
                    chat_id = update.chat.id
                    reply_id = update.id
                    user_id = update.from_user.id if update.from_user else None
                    command = update.command[0].lower()
                    logger.debug(f"Message command '{command}' from user {user_id} in chat {chat_id}")

                if not user_id:
                    linked_chat = await client.get_chat(chat_id)
                    if linked_chat.linked_chat and update.sender_chat.id == linked_chat.linked_chat.id:
                        logger.debug("Message from linked channel, allowing access")
                        return await func(client, update)
                    logger.warning("Cannot verify admin status from unknown user")
                    if isinstance(update, CallbackQuery):
                        await update.answer("⚠️ Cannot verify admin status from unknown user.", show_alert=True)
                    else:
                        await update.reply("⚠️ Cannot verify admin status from unknown user.", reply_to_message_id=reply_id)
                    return

                logger.debug("Performing admin check")

                # Check admin status
                is_admin = False
                admin_file = f"{ggg}/admin.txt"
                if os.path.exists(admin_file):
                    with open(admin_file, "r") as file:
                        admin_ids = [int(line.strip()) for line in file.readlines()]
                        is_admin = user_id in admin_ids
                        if is_admin:
                            logger.debug(f"User {user_id} is in admin list")

                # Check permissions using global variables
                is_auth_user = False
                if str(chat_id) in AUTH:
                    is_auth_user = user_id in AUTH[str(chat_id)]
                    if is_auth_user:
                        logger.debug(f"User {user_id} is authorized for chat {chat_id}")

                if not isinstance(update, CallbackQuery):
                    if command and str(command).endswith('del'):
                        is_auth_user = False
                        logger.debug("Command ends with 'del', auth_user status reset")

                is_authorized = (
                    is_admin or str(OWNER_ID) == str(user_id) or user_id in SUDO or is_auth_user)

                # Get chat member status
                chat_member = await client.get_chat_member(chat_id, user_id)
                is_chat_admin = chat_member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)

                # Check if user is trying to skip their own song (only for skip commands)
                is_song_owner_skip = False
                if command in ["skip", "cskip"]:
                    if isinstance(update, CallbackQuery):
                        if update.message.chat.id in playing and playing[update.message.chat.id]:
                            current_song = playing[update.message.chat.id]
                            if current_song["by"].id == user_id:
                                is_song_owner_skip = True
                                logger.debug(f"User {user_id} is song owner for skip command")
                    else:
                        if update.chat.id in playing and playing[update.chat.id]:
                            current_song = playing[update.chat.id]
                            if current_song["by"].id == user_id:
                                is_song_owner_skip = True
                                logger.debug(f"User {user_id} is song owner for skip command")

                # Allow access if user is admin OR (for skip commands only) if they own the song
                if not (is_chat_admin or is_authorized or is_song_owner_skip):
                    logger.warning(f"User {user_id} not authorized for command {command}")
                    if isinstance(update, CallbackQuery):
                        await update.answer("⚠️ This action is restricted to admins only.", show_alert=True)
                    else:
                        await update.reply("⚠️ This command is restricted to admins only.", reply_to_message_id=reply_id)
                    return

                logger.info(f"User {user_id} authorized for {func.__name__}")
                return await func(client, update)

            except Exception as e:
                error_msg = f"Error checking admin status: {str(e)}"
                logger.error(error_msg)
                if isinstance(update, CallbackQuery):
                    await update.answer("⚠️ Authorization check failed.", show_alert=True)
                else:
                    await update.reply("⚠️ Authorization check failed.")
                return
        return wrapper
    return decorator



# Define the main bot client (app)
create_custom_filter = filters.create(lambda _, __, message: any(m.is_self for m in (message.new_chat_members if message.new_chat_members else [])))

# Auth handler

from PIL import Image, ImageDraw, ImageFont
# Add /queue command to show up to 20 items in queue as a photo with brown background
@Client.on_message(filters.command("queue"))
async def queue_command(client, message):
    chat_id = message.chat.id
    queue_list = queues.get(chat_id, [])
    items = queue_list[:20]
    if not items:
        return await message.reply("Queue is empty.")

    # Prepare text for queue
    text_lines = [f"Queue for this chat (max 20):\n"]
    for idx, item in enumerate(items, 1):
        title = item.get("title", "Unknown")
        duration = item.get("duration", "-")
        text_lines.append(f"{idx}. {title} | {duration}")
    text = "\n".join(text_lines)

    # Create brown background image
    width, height = 800, 600
    img = Image.new("RGB", (width, height), (150, 75, 0))  # brown
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except:
        font = ImageFont.load_default()
    draw.multiline_text((40, 40), text, fill="white", font=font, spacing=8)

    # Save to bytes
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    await message.reply_photo(photo=buf, caption="Current Queue")


from functools import wraps
from typing import Tuple, Optional

# Example usage:
async def is_active_chat(client,chat_id):
    if chat_id not in active:
        return False
    else:
        return True


async def add_active_chat(client,chat_id):
    if chat_id not in active:
        active.append(chat_id)



@Client.on_message(filters.command("ac"))
async def active_chats(client, message):
    admin_file = f"{ggg}/admin.txt"
    user_id = message.from_user.id

    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    # Check permissions using global SUDO variable
    is_authorized = (
        is_admin or
        str(OWNER_ID) == str(user_id) or
        user_id in SUDO
    )

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS OWNER/SUDOER'S COMMAND...**")

    # Use PyTgCalls.calls to get active calls directly
    active_calls = await call_py.calls
    
    if active_calls:
        titles = []
        for chat_id in active_calls.keys():
            try:
                chat = await client.get_chat(chat_id)
                title = f"• {chat.title}"
            except Exception as e:
                title = f"• [ID: {chat_id}] (Failed to fetch title)"
            titles.append(title)

        titles_str = '\n'.join(titles)
        reply_text = (
            f"<b>Active group calls:</b>\n"
            f"<blockquote expandable>{titles_str}</blockquote>\n"
            f"<b>Total:</b> {len(active_calls)}"
        )
    else:
        reply_text = "<b>Active Voice Chats:</b>\n<blockquote>No active group calls</blockquote>"

    await message.reply_text(reply_text)


async def remove_active_chat(client, chat_id):
    if chat_id in active:
        active.remove(chat_id)
    chat_dir = f"{ggg}/user_{client.me.id}/{chat_id}"
    os.makedirs(chat_dir, exist_ok=True)
    clear_directory(chat_dir)



@Client.on_message(filters.command("tagall") & filters.group)
@admin_only()
async def mentionall(client, message):
    await message.delete()
    chat_id = message.chat.id
    direp = message.reply_to_message
    args = get_arg(message)

    # If no message or reply provided, use random message from TAGALL
    if not direp and not args:
        import random
        from tools import TAGALL
        args = random.choice(TAGALL)

    spam_chats.append(chat_id)
    usrnum = 0
    usrtxt = ""
    async for usr in client.get_chat_members(chat_id):
        if not chat_id in spam_chats:
            break
        usrnum += 1
        usrtxt += f"{usr.user.mention()}, "
        if usrnum == 5:
            if args:
                txt = f"<blockquote>{args}\n\n{usrtxt}</blockquote>"
                await client.send_message(chat_id, txt)
            elif direp:
                await direp.reply(f"<blockquote>{usrtxt}</blockquote>")
            await asyncio.sleep(5)
            usrnum = 0
            usrtxt = ""
    try:
        spam_chats.remove(chat_id)
    except:
        pass


@Client.on_message(filters.command(["seek", "seekback"]))
@admin_only()
async def seek_handler_func(client, message):
    try:
        await message.delete()
    except:
        pass
    # Check if user is banned using global variable
    if message.from_user.id in BLOCK:
        return

    try:
        # Get seek value from command
        command_parts = message.text.split()
        if len(command_parts) != 2:
            await client.send_message(
                message.chat.id,
                "❌ Please specify the seek time in seconds.\nUsage: /seek (seconds)"
            )
            return

        try:
            seek_value = int(command_parts[1])
            if seek_value < 0:
                await client.send_message(
                    message.chat.id,
                    f"{upper_mono('❌ Seek time cannot be negative!')}"
                )
                return
        except ValueError:
            await client.send_message(
                message.chat.id,
                f"{upper_mono('❌ Please provide a valid number of seconds!')}"
            )
            return

        # Check if there's a song playing
        if message.chat.id in playing and playing[message.chat.id]:
            current_song = playing[message.chat.id]
            duration_str = str(current_song['duration'])

            # Convert HH:MM:SS to total seconds
            duration_seconds = sum(
                int(x) * 60 ** i
                for i, x in enumerate(reversed(duration_str.split(":")))
            )

            # Get call client from main.py

            # Check if bot is actually streaming by fetching elapsed time
            if message.chat.id not in played:
                await client.send_message(
                    message.chat.id,
                    f"{upper_mono('Assistant is not streaming anything!')}"
                )
                return

            played_in_seconds = int(time.time() - played[message.chat.id])

            # Check seek boundaries based on command
            command = command_parts[0].lower()
            if command == "/seek":
                # Check if seeking forward would exceed remaining duration
                remaining_duration = duration_seconds - played_in_seconds
                if seek_value > remaining_duration:
                    await client.send_message(
                        message.chat.id,
                        f"{upper_mono('❌ Cannot seek beyond the remaining duration!')}"
                    )
                    return
                total_seek = seek_value + played_in_seconds
            else:  # seekback
                # Check if seeking back would exceed played duration
                if seek_value > played_in_seconds:
                    await client.send_message(
                        message.chat.id,
                        f"{upper_mono('❌ Cannot seek back more than the played duration!')}"
                    )
                    return
                total_seek = played_in_seconds - seek_value

            # Set audio flags based on mode
            mode = current_song['mode']
            audio_flags = MediaStream.Flags.IGNORE if mode == "audio" else None

            # Seek to specified position
            to_seek = format_duration(total_seek)
            yt_link = current_song['yt_link']
            
            # Get stream URL (optimized - returns input if not YouTube)
            stream_url = get_stream_url(yt_link)
            if not stream_url:
                stream_url = yt_link  # Fallback to original link
            
            await call_py.play(
                message.chat.id,
                MediaStream(
                    stream_url,
                    AudioQuality.STUDIO,
                    VideoQuality.HD_720p,
                    video_flags=audio_flags,
                    ffmpeg_parameters=f"-ss {to_seek} -to {duration_str}"
                ),
            )

            # Update played time based on command
            if command == "/seek":
                played[message.chat.id] -= seek_value
            else:  # seekback
                played[message.chat.id] += seek_value

            await client.send_message(
                message.chat.id,
                f"{upper_mono('Seeked to {to_seek}!')}\n\nʙʏ: {message.from_user.mention()}"
            )
        else:
            await client.send_message(
                message.chat.id,
                f"{upper_mono('Assistant is not streaming anything!')}"
            )
    except Exception as e:
        await client.send_message(
            message.chat.id,
            f"{upper_mono('❌ An error occurred:')} {str(e)}"
        )


@Client.on_message(filters.command("cancel") & filters.group)
@admin_only()
async def cancel_spam(client, message):
    if not message.chat.id in spam_chats:
        return await message.reply("**Looks like there is no tagall here.**")
    else:
        try:
            spam_chats.remove(message.chat.id)
        except:
            pass
        return await message.reply("**Dismissing Mention.**")

@Client.on_message(filters.command("del") & filters.group)
@admin_only()
async def delete_message_handler(client, message):
    # Check if the message is a reply
    if message.reply_to_message:
        try:
            # Delete the replied message
            await message.reply_to_message.delete()
            # Optionally, delete the command message as well
            await message.delete()
        except MessageDeleteForbidden:
              pass
        except Exception as e:
            await message.reply(f"Error deleting message: {str(e)}")
    else:
        await message.reply("**Please reply to a message to delete it.**")


@Client.on_message(filters.command("auth") & filters.group)
@admin_only()
async def auth_user(client, message):
    admin_file = f"{ggg}/admin.txt"
    user_id = message.from_user.id

    chat_id = message.chat.id

    # Use global AUTH variable and ensure chat exists
    if str(chat_id) not in AUTH:
        AUTH[str(chat_id)] = []

    if message.reply_to_message:
        replied_message = message.reply_to_message
        if replied_message.from_user:
            replied_user_id = replied_message.from_user.id

            # Check if replied user is admin
            if os.path.exists(admin_file):
                with open(admin_file, "r") as file:
                    admin_ids = [int(line.strip()) for line in file.readlines()]
                    if replied_user_id in admin_ids:
                        return await message.reply(f"**Owner is already authorized everywhere.**")

            # Check if user can be authorized
            if (replied_user_id != message.chat.id and
                not replied_message.from_user.is_self and
                not OWNER_ID == replied_user_id):

                # Check if user is already authorized in this chat using global AUTH
                if replied_user_id not in AUTH[str(chat_id)]:
                    AUTH[str(chat_id)].append(replied_user_id)
                    # Update database to maintain persistence
                    await user_sessions.update_one(
                        {"bot_id": client.me.id},
                        {"$set": {'auth_users': AUTH}},
                        upsert=True
                    )
                    await message.reply(f"User {replied_user_id} has been authorized in this chat.")
                else:
                    await message.reply(f"User {replied_user_id} is already authorized in this chat.")
            else:
                await message.reply("You cannot authorize yourself or an anonymous user.")
        else:
            await message.reply("The replied message is not from a user.")
    else:
        # If not a reply, check if a user ID is provided in the command
        command_parts = message.text.split()
        if len(command_parts) > 1:
            try:
                user_id_to_auth = int(command_parts[1])
                # Check if user is already authorized in this chat using global AUTH
                if user_id_to_auth not in AUTH[str(chat_id)]:
                    AUTH[str(chat_id)].append(user_id_to_auth)
                    # Update database to maintain persistence
                    await user_sessions.update_one(
                        {"bot_id": client.me.id},
                        {"$set": {'auth_users': AUTH}},
                        upsert=True
                    )
                    await message.reply(f"User {user_id_to_auth} has been authorized in this chat.")
                else:
                    await message.reply(f"User {user_id_to_auth} is already authorized in this chat.")
            except ValueError:
                await message.reply("Please provide a valid user ID.")
        else:
            await message.reply("You need to reply to a message or provide a user ID.")

@Client.on_message(filters.command("unauth") & filters.group)
@admin_only()
async def unauth_user(client, message):
    admin_file = f"{ggg}/admin.txt"
    chat_id = message.chat.id

    # Ensure chat exists in global AUTH
    if str(chat_id) not in AUTH:
        AUTH[str(chat_id)] = []

    if message.reply_to_message:
        replied_message = message.reply_to_message
        if replied_message.from_user:
            replied_user_id = replied_message.from_user.id

            # Check if replied user is admin
            if os.path.exists(admin_file):
                with open(admin_file, "r") as file:
                    admin_ids = [int(line.strip()) for line in file.readlines()]
                    if replied_user_id in admin_ids:
                        return await message.reply(f"**You can't remove authorization from owner.**")

            # Check if user can be unauthorized using global AUTH
            if replied_user_id in AUTH[str(chat_id)]:
                AUTH[str(chat_id)].remove(replied_user_id)
                # Update database to maintain persistence
                await user_sessions.update_one(
                    {"bot_id": client.me.id},
                    {"$set": {'auth_users': AUTH}},
                    upsert=True
                )
                await message.reply(f"User {replied_user_id} has been removed from authorized users in this chat.")
            else:
                await message.reply(f"User {replied_user_id} is not authorized in this chat.")
        else:
            await message.reply("The replied message is not from a user.")
    else:
        # If not a reply, check if a user ID is provided in the command
        command_parts = message.text.split()
        if len(command_parts) > 1:
            try:
                user_id_to_unauth = int(command_parts[1])
                # Check if user is authorized in this chat using global AUTH
                if user_id_to_unauth in AUTH[str(chat_id)]:
                    AUTH[str(chat_id)].remove(user_id_to_unauth)
                    # Update database to maintain persistence
                    await user_sessions.update_one(
                        {"bot_id": client.me.id},
                        {"$set": {'auth_users': AUTH}},
                        upsert=True
                    )
                    await message.reply(f"User {user_id_to_unauth} has been removed from authorized users in this chat.")
                else:
                    await message.reply(f"User {user_id_to_unauth} is not authorized in this chat.")
            except ValueError:
                await message.reply("Please provide a valid user ID.")
        else:
            await message.reply("You need to reply to a message or provide a user ID.")

@Client.on_message(filters.command("block"))
async def block_user(client, message):
    admin_file = f"{ggg}/admin.txt"
    user_id = message.from_user.id

    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    # Check permissions using global SUDO variable
    is_authorized = (
        is_admin or
        str(OWNER_ID) == str(user_id) or
        user_id in SUDO
    )

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS OWNER/SUDOER'S COMMAND...**")

    # Check if the message is a reply
    if message.reply_to_message:
        replied_message = message.reply_to_message
        # If the replied message is from a user (and not from the bot itself)
        if replied_message.from_user:
            replied_user_id = replied_message.from_user.id
            admin_file = f"{ggg}/admin.txt"
            if os.path.exists(admin_file):
               with open(admin_file, "r") as file:
                 admin_ids = [int(line.strip()) for line in file.readlines()]
                 if replied_user_id in admin_ids:
                     return await message.reply(f"**MF\n\nYou can't block my owner.**")
            # Check if the replied user is the same as the current chat (group) id
            if replied_user_id != message.chat.id and not replied_message.from_user.is_self and not OWNER_ID == replied_user_id:
                if replied_user_id not in BLOCK:
                    BLOCK.append(replied_user_id)
                    # Update database to maintain persistence
                    collection.update_one({"bot_id": client.me.id},
                                        {"$push": {'busers': replied_user_id}},
                                        upsert=True)
                    await message.reply(f"User {replied_user_id} has been added to blocklist.")
                else:
                   return await message.reply(f"User {replied_user_id} already in the blocklist.")

            else:
                await message.reply("You cannot block yourself or a anonymous user")
        else:
            await message.reply("The replied message is not from a user.")
    else:
        # If not a reply, check if a user ID is provided in the command
        command_parts = message.text.split()
        if len(command_parts) > 1:
            try:
                user_id_to_block = int(command_parts[1])
                # Block the user with the provided user ID using global BLOCK
                if user_id_to_block not in BLOCK:
                    BLOCK.append(user_id_to_block)
                    # Update database to maintain persistence
                    collection.update_one({"bot_id": client.me.id},
                                        {"$push": {'busers': user_id_to_block}},
                                        upsert=True
                                    )
                    await message.reply(f"User {user_id_to_block} has been added to blocklist.")
                else:
                   return await message.reply(f"User {user_id_to_block} already in the blocklist.")
            except ValueError:
                await message.reply("Please provide a valid user ID.")
        else:
            await message.reply("You need to reply to a message or provide a user ID.")

@Client.on_message(filters.command("reboot") & filters.private)
async def reboot_handler(client: Client, message: Message):
    user_id = message.from_user.id
    admin_file = f"{ggg}/admin.txt"

    # Admin file check
    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    # Authorization check using global SUDO variable
    is_authorized = (
        is_admin or
        str(OWNER_ID) == str(user_id) or
        user_id in SUDO
    )

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS OWNER/SUDOER'S COMMAND...**")

    # Authorized: Reboot process
    await message.reply("**Admin command received. Rebooting...**")
    os.system(f"kill -9 {os.getpid()}")  # Hard kill (optional after client.stop())

@Client.on_message(filters.command("unblock"))
async def unblock_user(client, message):
    admin_file = f"{ggg}/admin.txt"
    user_id = message.from_user.id

    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    # Check permissions using global SUDO variable
    is_authorized = (
        is_admin or
        str(OWNER_ID) == str(user_id) or
        user_id in SUDO
    )

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS OWNER/SUDOER'S COMMAND...**")

    if message.reply_to_message:
        replied_message = message.reply_to_message
        replied_user_id = replied_message.from_user.id

        # Check if user is in blocklist using global BLOCK
        if replied_user_id in BLOCK:
            BLOCK.remove(replied_user_id)
            # Update database to maintain persistence
            collection.update_one({"bot_id": client.me.id},
                                {"$pull": {'busers': replied_user_id}},
                                upsert=True)
            await message.reply(f"User {replied_user_id} has been removed from blocklist.")
        else:
            return await message.reply(f"User {replied_user_id} not in the blocklist.")

    else:
        # If not a reply, check if a user ID is provided in the command
        command_parts = message.text.split()
        if len(command_parts) > 1:
            try:
                target_user_id = int(command_parts[1])

                # Check if user is in blocklist using global BLOCK
                if target_user_id in BLOCK:
                    BLOCK.remove(target_user_id)
                    # Update database to maintain persistence
                    collection.update_one({"bot_id": client.me.id},
                                        {"$pull": {'busers': target_user_id}},
                                        upsert=True)
                    await message.reply(f"User {target_user_id} has been removed from blocklist.")
                else:
                    return await message.reply(f"User {target_user_id} not in the blocklist.")
            except ValueError:
                await message.reply("Please provide a valid user ID.")
        else:
            await message.reply("You need to reply to a message or provide a user ID.")


@Client.on_message(filters.command("sudolist"))
async def show_sudo_list(client, message):
    # Check admin permissions
    admin_file = f"{ggg}/admin.txt"
    user_id = message.from_user.id
    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    # Check permissions
    is_authorized = is_admin or str(OWNER_ID) == str(user_id)

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS PAID OWNER'S COMMAND...**")
    try:
        # Get all users who have SUDOERS field
        users_data = await find_one(user_sessions, {"bot_id": client.me.id})
        sudo_users = users_data.get("SUDOERS", []) if users_data else []

        if not sudo_users:
            return await message.reply("No sudo users found in the database.")

        # Build the sudo list message
        sudo_list = ["**🔱 SUDO USERS LIST:**\n"]
        number = 1

        for user_id in sudo_users:
                try:
                    # Try to get user info from Telegram
                    user_info = await client.get_users(user_id)
                    user_mention = f"@{user_info.username}" if user_info.username else user_info.first_name
                    sudo_list.append(f"**{number}➤** {user_mention} [`{user_id}`]")
                except Exception:
                    # If can't get user info, just show the ID
                    sudo_list.append(f"**{number}➤** Unknown User [`{user_id}`]")
                number += 1

        # Add count at the bottom
        sudo_list.append(f"\n**Total SUDO Users:** `{number-1}`")

        # Send the message
        await message.reply("\n".join(sudo_list))

    except Exception as e:
        await message.reply(f"An error occurred while fetching sudo list: {str(e)}")


@Client.on_message(filters.command("addsudo"))
async def add_to_sudo(client, message):
    # Check admin permissions
    admin_file = f"{ggg}/admin.txt"
    user_id = message.from_user.id

    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    is_authorized = is_admin or str(OWNER_ID) == str(user_id)

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS OWNER'S COMMAND...**")

    if message.reply_to_message:
        replied_message = message.reply_to_message
        if replied_message.from_user:
            replied_user_id = replied_message.from_user.id

            # Check if target user is already admin
            if os.path.exists(admin_file):
                with open(admin_file, "r") as file:
                    admin_ids = [int(line.strip()) for line in file.readlines()]
                    if replied_user_id in admin_ids:
                        return await message.reply(f"**This user is already an owner!**")

            # Check if trying to add self or bot
            if replied_user_id != message.chat.id and not replied_message.from_user.is_self:
                # Get current sudo users
                users_data = await find_one(user_sessions, {"bot_id": client.me.id})
                sudoers = users_data.get("SUDOERS", []) if users_data else []
                if replied_user_id not in sudoers:
                    asyncio.create_task(push_to_array(user_sessions, {"bot_id": client.me.id}, "SUDOERS", replied_user_id, upsert=True))
                    await message.reply(f"User {replied_user_id} has been added to sudoers list.")
                    SUDO.append(replied_user_id)
                else:
                    await message.reply(f"User {replied_user_id} is already in sudoers list.")
            else:
                await message.reply("You cannot add yourself or the bot to sudoers.")
        else:
            await message.reply("The replied message is not from a user.")
    else:
        # Handle command with user ID
        command_parts = message.text.split()
        if len(command_parts) > 1:
            try:
                target_user_id = int(command_parts[1])

                # Check if target user is already admin
                if os.path.exists(admin_file):
                    with open(admin_file, "r") as file:
                        admin_ids = [int(line.strip()) for line in file.readlines()]
                        if target_user_id in admin_ids:
                            return await message.reply(f"**This user is already an owner!**")

                # Get current sudo users
                users_data = await find_one(user_sessions, {"bot_id": client.me.id})
                sudoers = users_data.get("SUDOERS", []) if users_data else []
                if target_user_id not in sudoers:
                    asyncio.create_task(push_to_array(user_sessions, {"bot_id": client.me.id}, "SUDOERS", target_user_id, upsert=True))
                    await message.reply(f"User {target_user_id} has been added to sudoers list.")
                    SUDO.append(target_user_id)
                else:
                    await message.reply(f"User {target_user_id} is already in sudoers list.")
            except ValueError:
                await message.reply("Please provide a valid user ID.")
        else:
            await message.reply("You need to reply to a message or provide a user ID.")

@Client.on_message(filters.command("rmsudo"))
async def remove_from_sudo(client, message):
    # Check admin permissions
    admin_file = f"{ggg}/admin.txt"
    user_id = message.from_user.id

    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    # Check permissions - only admin or verified users can remove from sudo
    is_authorized = is_admin or (user_id == OWNER_ID)

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS OWNER'S COMMAND...**")

    # Handle reply to message
    if message.reply_to_message:
        replied_message = message.reply_to_message
        if replied_message.from_user:
            replied_user_id = replied_message.from_user.id

            # Check if target user is an admin
            if os.path.exists(admin_file):
                with open(admin_file, "r") as file:
                    admin_ids = [int(line.strip()) for line in file.readlines()]
                    if replied_user_id in admin_ids:
                        return await message.reply(f"**Cannot remove an owner from sudo list!**")

            # Check if trying to remove self or bot
            if replied_user_id != message.chat.id and not replied_message.from_user.is_self:
                # Get current sudo users
                users_data = await find_one(user_sessions, {"bot_id": client.me.id})
                if not users_data:
                    return await message.reply(f"User {replied_user_id} is not in the database.")
                sudoers = users_data.get("SUDOERS", []) if users_data else []
                if replied_user_id in sudoers:
                    asyncio.create_task(pull_from_array(user_sessions, {"bot_id": client.me.id}, "SUDOERS", replied_user_id))
                    await message.reply(f"User {replied_user_id} has been removed from sudoers list.")
                    SUDO.remove(replied_user_id)
                else:
                    await message.reply(f"User {replied_user_id} is not in sudoers list.")
            else:
                await message.reply("You cannot remove yourself or the bot from sudoers.")
        else:
            await message.reply("The replied message is not from a user.")
    else:
        # Handle command with user ID
        command_parts = message.text.split()
        if len(command_parts) > 1:
            try:
                target_user_id = int(command_parts[1])

                # Check if target user is an admin
                if os.path.exists(admin_file):
                    with open(admin_file, "r") as file:
                        admin_ids = [int(line.strip()) for line in file.readlines()]
                        if target_user_id in admin_ids:
                            return await message.reply(f"**Cannot remove an owner from sudo list!**")

                # Get current sudo users
                users_data = await find_one(user_sessions, {"bot_id": client.me.id})
                if not users_data:
                    return await message.reply(f"User {target_user_id} is not in the database.")
                sudoers = users_data.get("SUDOERS", []) if users_data else []
                if target_user_id in sudoers:
                    asyncio.create_task(pull_from_array(user_sessions, {"bot_id": client.me.id}, "SUDOERS", target_user_id))
                    await message.reply(f"User {target_user_id} has been removed from sudoers list.")
                    SUDO.remove(target_user_id)
                else:
                    await message.reply(f"User {target_user_id} is not in sudoers list.")
            except ValueError:
                await message.reply("Please provide a valid user ID.")
        else:
            await message.reply("You need to reply to a message or provide a user ID.")






from pyrogram.types import Chat
from pyrogram.errors import ChatAdminRequired

async def get_chat_member_count(client, chat_id):
    try:
        return await client.get_chat_members_count(chat_id)
    except:
        return "Unknown"

async def send_log_message(client, log_group_id, message, is_private):
    try:
        if is_private:
            user = message.from_user
            log_text = (
                "📥 **New User Started Bot**\n\n"
                f"**User Details:**\n"
                f"• Name: {user.first_name}\n"
                f"• Username: @{user.username if user.username else 'None'}\n"
                f"• User ID: `{user.id}`\n"
                f"• Is Premium: {'Yes' if user.is_premium else 'No'}\n"
                f"• DC ID: {user.dc_id if user.dc_id else 'Unknown'}\n"
                f"• Language: {user.language_code if user.language_code else 'Unknown'}\n"
                f"• Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            try: invite_link = client.export_chat_invite_link(chat.id)
            except (TimeoutError, exceptions.bad_request_400.ChatAdminRequired, AttributeError): invite_link = "Don't have invite right"
            except Exception: invite_link = "Error while generating invite link"
            chat = message.chat
            members_count = await get_chat_member_count(client, chat.id)
            log_text = (
                "📥 **Bot Added to New Group**\n\n"
                f"**Group Details:**\n"
                f"• Name: {chat.title}\n"
                f"• Chat ID: `{chat.id}`\n"
                f"• Type: {chat.type}\n"
                f"• Members: {members_count}\n"
                f"• Username: @{chat.username if chat.username else invite_link}\n"
                f"• Added By: {message.from_user.mention if message.from_user else 'Unknown'}\n"
                f"• Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        await asyncio.sleep(2)
        await client.send_message(
            chat_id=int(log_group_id),
            text=log_text,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.info(f"Error sending log message: {str(e)}")



@Client.on_message(filters.command("start") | (filters.group & create_custom_filter))
async def user_client_start_handler(client, message):
    user_id = message.chat.id
    user_data = await find_one(collection, {"bot_id": client.me.id})
    is_private = message.chat.type == enums.ChatType.PRIVATE
    should_log = False
    if user_data:
        users = user_data.get('users', {})
        if not user_id in users:
            asyncio.create_task(push_to_array(collection, {"bot_id": client.me.id}, 'users', user_id, upsert=True))
            should_log = True
    else:
        asyncio.create_task(set_fields(collection, {"bot_id": client.me.id}, {'users': [user_id]}, upsert=True))
        should_log = True
    if should_log:
        log_group = LOGGER_ID

        if log_group:
          try:
            await send_log_message(
                client=client,
                log_group_id=log_group,
                message=message,
                is_private=is_private
            )
          except Exception as e:
             logger.info(e)

    # Process video ID if provided in start command
    command_args = message.text.split() if message.text else "hh".split()
    if len(command_args) > 1 and '_' in command_args[1]:
        try:
            loading = await message.reply("Getting stream info! Please wait...")
            # Split the argument using underscore and get the video ID
            _, video_id = command_args[1].split('_', 1)

            # Get video details
            video_info = get_video_details(video_id)

            if isinstance(video_info, dict):
                # Format numbers
                views = format_number(video_info['view_count'])

                # Create formatted message
                logger.info(video_info['thumbnail'])
                await loading.delete()
                caption = (
                    f"📝 **Title:** {video_info['title']}\n\n"
                    f"⏱ **Duration:** {video_info['duration']}\n"
                    f"👁 **Views:** {views}\n"
                    f"📺 **Channel:** {video_info['channel_name']}\n"
                )

                # Create inline keyboard with YouTube button
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "🎬 Stream on YouTube",
                        url=video_info['video_url']
                    )]
                ])

                # Send thumbnail as photo with caption and keyboard
                try:
                    return await message.reply_photo(
                        photo=video_info['thumbnail'],
                        caption=caption,
                        reply_markup=keyboard,
                        reply_to_message_id=message.id
                    )
                except Exception as e:
                    return await message.reply_text(
                        f"❌ Failed to send photo: {str(e)}\n\n{caption}",
                        reply_markup=keyboard,
                        reply_to_message_id=message.id
                    )
            else:
                return await message.reply_text(
                    f"❌ Error: {video_info}",
                    reply_to_message_id=message.id
                )

        except Exception as e:
            return await message.reply_text(
                f"❌ Error processing video ID: {str(e)}",
                reply_to_message_id=message.id
            )

    # Handle logging

    session_name = f'user_{client.me.id}'
    user_dir = f"{ggg}/{session_name}"
    os.makedirs(user_dir, exist_ok=True)
    editing = await message.reply("⚡")
    owner = await client.get_users(OWNER_ID)
    ow_id = owner.id if owner.username else None

    buttons = [
   [InlineKeyboardButton("Aᴅᴅ ᴍᴇ ᴛᴏ ɢʀᴏᴜᴘ", url=f"https://t.me/{client.me.username}?startgroup=true")],
   [InlineKeyboardButton("Hᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅꜱ", callback_data="commands_all")],
   [
       InlineKeyboardButton(
           "Cʀᴇᴀᴛᴏʀ",
           user_id=OWNER_ID
       ) if ow_id else InlineKeyboardButton(
           "Cʀᴇᴀᴛᴏʀ",
           url="https://t.me/NubDockerbot"
       ),
       InlineKeyboardButton("Sᴜᴘᴘᴏʀᴛ ᴄʜᴀᴛ", url = f"https://t.me/{GROUP}")
   ],
]
    import psutil
    from random import choice
    uptime = await get_readable_time((time.time() - StartTime))
    start = datetime.datetime.now()



    # Get system resources
    try:
        cpu_cores = psutil.cpu_count() or "N/A"
        ram = psutil.virtual_memory()
        ram_total = f"{ram.total / (1024**3):.2f} GB"
        disk = psutil.disk_usage('/')
        disk_total = f"{disk.total / (1024**3):.2f} GB"
    except Exception as e:
        cpu_cores = "N/A"
        ram_total = "N/A"
        disk_total = "N/A"
    try:
       photu = None
       async for photo in client.get_chat_photos(client.me.id):
           photu = photo.file_id

       # First try to get logo from user_dir
       logo_path_jpg = f"{user_dir}/logo.jpg"
       logo_path_mp4 = f"{user_dir}/logo.mp4"
       logo = None

       if os.path.exists(logo_path_mp4):
           logo = logo_path_mp4
       elif os.path.exists(logo_path_jpg):
           logo = logo_path_jpg
       else:
           logo = await gvarstatus(client.me.id, "LOGO") or (await client.download_media(client.me.photo.big_file_id, logo_path_jpg) if client.me.photo else "music.jpg")

       alive_logo = logo
       if type(logo) is bytes:
           alive_logo = logo_path_jpg
           with open(alive_logo, "wb") as fimage:
               fimage.write(base64.b64decode(logo))
           if 'video' in mime.from_file(alive_logo):
               alive_logo = rename_file(alive_logo, logo_path_mp4)




       greet_message = await gvarstatus(client.me.id, "WELCOME") or """
🌟 𝖂𝖊𝖑𝖈𝖔𝖒𝖊, {name}! 🌟

🎶 Your **musical journey** begins with {botname}!

✨ Enjoy _crystal-clear_ audio and a vast library of sounds.

🚀 Get ready for an *unparalleled* musical adventure!
"""

       send = client.send_video if alive_logo.endswith(".mp4") else client.send_photo
       await editing.delete()
       await send(
                user_id ,
                alive_logo,
                caption=await format_welcome_message(client, greet_message, user_id, message.from_user.mention() if message.chat.type == enums.ChatType.PRIVATE else (message.chat.title or ""))
,reply_markup=InlineKeyboardMarkup(buttons)
            )
    except Exception as e:
      logger.info(e)

# Create an instance of the Update class
async def format_welcome_message(client, text, chat_id, user_or_chat_name):
    """Helper function to format welcome message with real data"""
    try:
        # Ensure user_or_chat_name is a string, even if None is passed
        user_or_chat_name = str(user_or_chat_name) if user_or_chat_name is not None else ""
        formatted_text = text
        formatted_text = formatted_text.replace("{name}", user_or_chat_name)
        formatted_text = formatted_text.replace("{id}", str(chat_id))
        formatted_text = formatted_text.replace("{botname}", client.me.mention())
        return formatted_text
    except Exception as e:
        logging.error(f"Error formatting welcome message: {str(e)}")
        return text  # Return original text if formatting fails


@Client.on_callback_query(filters.regex(r"commands_(.*)"))
async def commands_handler(client, callback_query):
    data = callback_query.data.split("_", 1)[1]          # Extract page name
    user_id = callback_query.from_user.id
    admin_file = f"{ggg}/admin.txt"

    # --- Permission check (owner / admin / sudo) ---
    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            if user_id in admin_ids or str(OWNER_ID) == str(user_id):
                is_admin = True
    owner = await client.get_users(OWNER_ID)
    ow_id = owner.id if owner.username else None

    # ---------- Command pages (text blocks) ----------
    playback_commands = """**🎵 PLAYBACK COMMANDS**
<blockquote>
◾ /play  /vplay        – queue YouTube audio/video
◾ /queue               – show current queue (up to 20 items)
◾ /playforce /vplayforce – force play (skip current)
◾ /cplay /cvplay       – play in linked channel
◾ /pause               – pause stream
◾ /resume              – resume stream
◾ /skip  /cskip        – next track
◾ /end  /cend          – stop & clear queue
◾ /seek <sec>          – jump forward
◾ /seekback <sec>      – jump backward
◾ /loop <1-20>         – repeat current song
</blockquote>"""

    auth_commands = """**🔐 AUTHORIZATION COMMANDS**
<blockquote>
◾ /auth <reply|id>   – allow user to use player
◾ /unauth <reply|id> – remove that permission
◾ /authlist          – list authorized users
</blockquote>"""

    blocklist_commands = """**🚫 BLOCKLIST COMMANDS**
<blockquote>
◾ /block <reply|id>   – block user from bot
◾ /unblock <reply|id> – unblock user
◾ /blocklist          – view blocked list
</blockquote>"""

    sudo_commands = """**🔑 SUDO COMMANDS**
<blockquote>
◾ /addsudo <reply|id> – add sudo user
◾ /rmsudo <reply|id>  – remove sudo user
◾ /sudolist           – list sudo users
</blockquote>"""

    broadcast_commands = """**📢 BROADCAST COMMANDS**
<blockquote>
◾ /broadcast   – copy a message to all dialogs
◾ /fbroadcast  – forward a message to all dialogs
</blockquote>"""

    tools_commands = """**🛠️ TOOLS COMMANDS**
<blockquote>
◾ /del        – delete replied message
◾ /tagall     – mention all members
◾ /cancel     – abort running tagall
◾ /powers     – show bot permissions
</blockquote>"""

    kang_commands = """**🎨 STICKER & MEME COMMANDS**
<blockquote>
◾ /kang       – clone sticker/photo to your pack
◾ /mmf <text> – write text on image/sticker
◾ /qt <text>  – create fake quote sticker
</blockquote>"""

    status_commands = """**📊 STATUS & INFO COMMANDS**
<blockquote>
◾ /ping       – latency & uptime
◾ /stats      – bot usage stats
◾ /ac         – active voice chats
◾ /about      – user / group / channel info
</blockquote>"""

    owner_commands = """**⚙️ OWNER COMMANDS**
<blockquote>
◾ /reboot     – restart the bot
◾ /setwelcome – set custom /start message
◾ /resetwelcome – Reset the welcome message and logo.
</blockquote>"""

    # ---------- Navigation buttons ----------
    category_buttons = [
        [
            InlineKeyboardButton("🎵 Playback",   callback_data="commands_playback"),
            InlineKeyboardButton("🔐 Auth",       callback_data="commands_auth"),
        ],
        [
            InlineKeyboardButton("🚫 Blocklist",  callback_data="commands_blocklist"),
            InlineKeyboardButton("🔑 Sudo",       callback_data="commands_sudo"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast",  callback_data="commands_broadcast"),
            InlineKeyboardButton("🛠️ Tools",     callback_data="commands_tools"),
        ],
        [
            InlineKeyboardButton("🎨 Kang/Meme",  callback_data="commands_kang"),
            InlineKeyboardButton("📊 Status",     callback_data="commands_status"),
        ],
        [
            InlineKeyboardButton("⚙️ Owner",      callback_data="commands_owner"),
        ],
        [InlineKeyboardButton("🏠 Home",         callback_data="commands_back")],
    ]

    back_button = [[InlineKeyboardButton("🔙 Back", callback_data="commands_all")]]

    # ---------- Routing ----------
    if data == "all":
        await callback_query.message.edit_caption(
            caption="**📜 SELECT A COMMAND CATEGORY**",
            reply_markup=InlineKeyboardMarkup(category_buttons),
        )
    elif data == "playback":
        await callback_query.message.edit_caption(caption=playback_commands, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "auth":
        await callback_query.message.edit_caption(caption=auth_commands, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "blocklist":
        await callback_query.message.edit_caption(caption=blocklist_commands, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "sudo":
        await callback_query.message.edit_caption(caption=sudo_commands, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "broadcast":
        await callback_query.message.edit_caption(caption=broadcast_commands, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "tools":
        await callback_query.message.edit_caption(caption=tools_commands, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "kang":
        await callback_query.message.edit_caption(caption=kang_commands, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "status":
        await callback_query.message.edit_caption(caption=status_commands, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "owner":
        await callback_query.message.edit_caption(caption=owner_commands, reply_markup=InlineKeyboardMarkup(back_button))
    elif data == "back":
            name = callback_query.from_user.mention()
            botname = client.me.mention()
            greet_message = await gvarstatus(client.me.id, "WELCOME") or """
🌟 𝖂𝖊𝖑𝖈𝖔𝖒𝖊, {name}! 🌟

🎶 Your **musical journey** begins with {botname}!

✨ Enjoy _crystal-clear_ audio and a vast library of sounds.

🚀 Get ready for an *unparalleled* musical adventure!
"""
            greet_message = await format_welcome_message(client, greet_message, user_id, callback_query.from_user.mention())
            buttons = [
                [InlineKeyboardButton("Aᴅᴅ ᴍᴇ ᴛᴏ ɢʀᴏᴜᴘ", url=f"https://t.me/{client.me.username}?startgroup=true")],
                [InlineKeyboardButton("Hᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅꜱ", callback_data="commands_all")],
                [
                    InlineKeyboardButton(
                        "Cʀᴇᴀᴛᴏʀ",
                        user_id=OWNER_ID
                    ) if ow_id else InlineKeyboardButton(
                        "Cʀᴇᴀᴛᴏʀ",
                        url="https://t.me/NubDockerbot"
                    ),
                    InlineKeyboardButton("Sᴜᴘᴘᴏʀᴛ ᴄʜᴀᴛ", url = f"https://t.me/{GROUP}")
                ],
            ]
            await callback_query.message.edit_caption(
                caption=greet_message,
                reply_markup=InlineKeyboardMarkup(buttons),
            )



@Client.on_message(filters.command("blocklist"))
async def blocklist_handler(client, message):
    admin_file = f"{ggg}/admin.txt"
    user_id = message.from_user.id
    users_data = await find_one(user_sessions, {"bot_id": client.me.id})
    sudoers = users_data.get("SUDOERS", []) if users_data else []

    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    # Check permissions
    is_authorized = (
        is_admin or
        str(OWNER_ID) == str(user_id) or
        user_id in sudoers
    )

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS OWNER/SUDOER'S COMMAND...**")

    # Check for admin or owner


    # Fetch blocklist from the database
    user_data = await find_one(collection, {"bot_id": client.me.id})
    if not user_data:
        return await message.reply("No blocklist found.")

    blocked_users = user_data.get('busers', [])
    if not blocked_users:
        return await message.reply("No users are currently blocked.")

    blocklist_text = "Blocked Users:\n" + "\n".join([f"- `{user_id}`" for user_id in blocked_users])
    await message.reply_text(blocklist_text)


from pytgcalls import filters as call_filters

def currently_playing(client, message):
    try:
        if len(queues[message.chat.id]) <=1:
           return False
        return True
    except KeyError:
        True



# Import join_call function from tools.py

async def dend(client, update, channel_id= None):
    # Enhanced input validation
    try:
        chat_id = int(channel_id or update.chat.id)
        logger.debug(f"Dend processing - Validated chat_id: {chat_id} (type: {type(chat_id)})")
    except (TypeError, ValueError, AttributeError) as e:
        logger.error(f"Invalid chat_id: {e}. channel_id: {channel_id}, update.chat.id: {getattr(update.chat, 'id', 'N/A')}")
        return
    try:
        chat_id = int(channel_id or update.chat.id)  # Ensure integer chat_id
        if chat_id in queues and queues[chat_id]:
            next_song = queues[chat_id].pop(0)
            playing[chat_id] = next_song
            await join_call(
                next_song['message'],
                next_song['title'],
                next_song['yt_link'],
                next_song['chat'],
                next_song['by'],
                next_song['duration'],
                next_song['mode'],
                next_song['thumb'],
                next_song.get('stream_url')
            )
        else:
            logger.info(f"Song queue for chat {chat_id} is empty.")
            await client.leave_call(chat_id)
            await remove_active_chat(client, chat_id)
            if chat_id in playing:
                playing[chat_id].clear()
    except Exception as e:
        logger.error(f"Error in dend function: {e}")


from PIL import Image
import imageio
import cv2
from pyrogram.raw.types import DocumentAttributeVideo, DocumentAttributeAudio


def generate_thumbnail(video_path, thumb_path):
    try:
        reader = imageio.get_reader(video_path)
        frame = reader.get_data(0)
        image = Image.fromarray(frame)
        image.thumbnail((320, 320))
        image.save(thumb_path, "JPEG")
        return thumb_path
    except Exception as e:
        # Fallback to black thumbnail
        Image.new('RGB', (320, 320), (0, 0, 0)).save(thumb_path, "JPEG")
        return thumb_path
# Play handler function




# Modified media download with progress
async def download_media_with_progress(client, msg, media_msg, type_of):
    start_time = time.time()
    filename = getattr(media_msg, 'file_name', 'file')
    session_name = f'user_{client.me.id}'
    user_dir = f"{ggg}/{session_name}/{msg.chat.id}"
    os.makedirs(user_dir, exist_ok=True)
    try:
        file_path = await client.download_media(media_msg,file_name=f"{user_dir}/",
            progress=progress_bar,
            progress_args=(client, msg, type_of, filename, start_time))
        return file_path
    except Exception as e:
        print(f"Download error: {e}")
        return None


# Modified progress bar with error handling
async def progress_bar(current, total, client, msg, type_of, filename, start_time):
    if total == 0:
        return

    try:
            progress_percent = current * 100 / total
            progress_message = f"{type_of} {filename}: {progress_percent:.2f}%\n"

            # Progress bar calculation
            progress_bar_length = 20
            num_ticks = int(progress_percent / (100 / progress_bar_length))
            progress_bar_text = '█' * num_ticks + '░' * (progress_bar_length - num_ticks)

            # Speed calculation
            elapsed_time = time.time() - start_time
            speed = current / (elapsed_time * 1024 * 1024) if elapsed_time > 0 else 0

            # Time remaining calculation
            time_left = (total - current) / (speed * 1024 * 1024) if speed > 0 else 0

            # Format message
            progress_message += (
                f"Speed: {speed:.2f} MB/s\n"
                f"Time left: {time_left:.2f}s\n"
                f"Size: {current/1024/1024:.2f}MB / {total/1024/1024:.2f}MB\n"
                f"[{progress_bar_text}]"
            )

            # Edit message with exponential backoff
            try:
              if random.choices([True, False], weights=[1, 20])[0]:
                await msg.edit(progress_message)
            except Exception as e:
                print(f"Progress update error: {e}")

    except Exception as e:
        print(f"Progress bar error: {e}")


import os
import cv2
from mutagen import File
from mutagen import MutagenError

def with_opencv(filename):
    # List of common audio file extensions
    audio_extensions = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.mp4', '.wma']
    file_ext = os.path.splitext(filename)[1].lower()

    # Handle audio files with mutagen
    if file_ext in audio_extensions:
        try:
            audio = File(filename)
            if audio is not None and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                duration = audio.info.length
                return int(duration)
            else:
                return 0
        except MutagenError:
            return 0
    # Handle video files with OpenCV
    else:
        video = cv2.VideoCapture(filename)
        fps = video.get(cv2.CAP_PROP_FPS)
        frame_count = video.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fps if fps else 0
        video.release()
        return int(duration)
# Example usage
# duration = get_media_duration('path/to/your/media/file.ogg')
@Client.on_message(filters.command(["play", "vplay", "playforce", "vplayforce", "cplay", "cvplay", "cplayforce", "cvplayforce"]))
async def play_handler_func(client, message):
    session_name = f'user_{client.me.id}'
    user_dir = f"{ggg}/{session_name}"
    os.makedirs(user_dir, exist_ok=True)
    by = message.from_user
    try:
        await message.delete()
    except:
        pass

    # Check if user is banned using global BLOCK variable
    if message.from_user.id in BLOCK:
        return

    command = message.command[0].lower()
    mode = "video" if command.startswith("v") or command.startswith("cv") else "audio"
    force_play = command.endswith("force")
    channel_mode = command.startswith("c")

    # Check if the command is sent in a group
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.reply("The play commands can only be used in group chats.")
        return

    # Get the bot username and retrieve the session client ID from connector
    youtube_link = None
    input_text = message.text.split(" ", 1)
    d_ata = await find_one(collection, {"bot_id": client.me.id})

    act_calls = len(active)

    # Determine if we need channel mode
    chat = message.chat
    target_chat_id = message.chat.id
    # For channel commands, check for linked channel
    if channel_mode:
        linked_chat = (await client.get_chat(message.chat.id)).linked_chat
        if not linked_chat:
            await message.reply("This group doesn't have a linked channel.")
            return
        target_chat_id = linked_chat.id

    # Check queue for the target chat
    current_queue = len(queues.get(target_chat_id, [])) if queues else 0

    massage = await message.reply("⚡")

    # Set target chat as active based on channel mode or not
    is_active = await is_active_chat(client, target_chat_id)
    await add_active_chat(client, target_chat_id)

    youtube_link = None
    media_info = {}
    
    # Initialize title with a safe default to prevent unbound variable issues
    title = trim_title("Unknown Media")

    # Check if replied to media message
    if message.reply_to_message and message.reply_to_message.media:
        media_msg = message.reply_to_message
        media_type = None
        duration = 0
        thumbnail = None

        # Video handling
        if media_msg.video:
            media = media_msg.video
            media_type = "video"
            title = trim_title(media.file_name or "Telegram Video")
            duration = media.duration
            if media.thumbs:
                thumbnail = await client.download_media(media.thumbs[0].file_id)

        # Audio handling
        elif media_msg.audio:
            media = media_msg.audio
            media_type = "audio"
            title = trim_title(media.title or "Telegram Audio")
            duration = media.duration
            if media.thumbs:
                thumbnail = await client.download_media(media.thumbs[0].file_id)

        # Voice message handling
        elif media_msg.voice:
            media = media_msg.voice
            media_type = "voice"
            title = trim_title("Voice Message")
            duration = media.duration

        # Video note handling
        elif media_msg.video_note:
            media = media_msg.video_note
            media_type = "video_note"
            title = trim_title("Video Note")
            duration = media.duration
            if media.thumbs:
                thumbnail = await client.download_media(media.thumbs[0].file_id)
        elif media_msg.document:
            doc = media_msg.document
            media = media_msg.document
    # In Pyrogram, check the mime_type directly
            if doc.mime_type:
                if doc.mime_type.startswith("video/"):
                    media_type = "video"
                    title = trim_title(doc.file_name or "Telegram Video")
                    duration = getattr(doc, 'duration', 0)  # duration might not always be available
            elif doc.mime_type.startswith("audio/"):
                     media_type = "audio"
                     title = trim_title(doc.file_name or "Telegram Audio")
                     duration = getattr(doc, 'duration', 0)


            if media_type and doc.thumbs:
                thumbnail = await client.download_media(doc.thumbs[0].file_id,f"{user_dir}/")
        else:
            await massage.edit(f"{upper_mono('❌ Unsupported media type')}")
            return await remove_active_chat(client, target_chat_id)
        if not media_type:
            await massage.edit(f"{upper_mono('❌ Unsupported media type')}")
            return await remove_active_chat(client, target_chat_id)
        # For media messages
        youtube_link = await download_media_with_progress(
            client,
            massage,
            message.reply_to_message,
            "Media"
        )
        stream_url = None

        # Generate thumbnail if missing
        if not thumbnail and media_type in ["video", "video_note"]:
            try:
                thumbnail = generate_thumbnail(youtube_link, f'{user_dir}/thumb.png')
            except Exception as e:
                print(e)
                thumbnail = None
        # Format duration
        if not duration or duration <=0:
            duration = with_opencv(youtube_link)
        duration = format_duration(int(duration))
        media_info = {
            'title': title,
            'duration': duration,
            'thumbnail': thumbnail,
            'file_id': media.file_id,
            'media_type': media_type,
            'url': youtube_link
        }
    elif len(input_text) == 2:
        search_query = input_text[1]

        title, duration, youtube_link, thumbnail, channel_name, views, video_id, stream_url = await handle_youtube(search_query)
        title = trim_title(title)
        if not youtube_link:
            try:
                await massage.edit(f"{upper_mono('No matching query found, please retry!')}")
                return await remove_active_chat(client, target_chat_id)
            except:
                return await remove_active_chat(client, target_chat_id)
    else:
        try:
            await massage.edit(f"{upper_mono('No query provided, please provide one')}\n`/play query`")
            return await remove_active_chat(client, target_chat_id)
        except:
            return

    # Get thumb based on media type
    if media_info:
        thumb = await get_thumb(
            media_info['title'],
            media_info['duration'],
            media_info['thumbnail'],
            None,  # channel_name
            None,  # views
            None   # video_id
        )
        # Add your media playback logic here using media_info
    else:
        # Existing YouTube handling
        thumb = await get_thumb(title, str(duration), thumbnail, channel_name, str(views), video_id)

    bot_username = client.me.username

    # Retrieve the session client from the clients dictionary

    # Join the group (same for both regular and channel mode)
    if message.chat.username:
        # Public group
        try:
            try:
                joined_chat = await session.get_chat(message.chat.username)
            except:
                joined_chat = await session.join_chat(message.chat.username)
        except (InviteHashExpired, ChannelPrivate):
            await massage.edit(f"Assistant is banned in this chat.\n\nPlease unban {session.me.username or session.me.id}")
            return await remove_active_chat(client, target_chat_id)
        except Exception as e:
            await massage.edit(f"Failed to join the group. Error: {e}")
            return await remove_active_chat(client, target_chat_id)
    else:
        # Private group
        bot_member = await client.get_chat_member(message.chat.id, client.me.id)

        if bot_member.status == ChatMemberStatus.ADMINISTRATOR and bot_member.privileges.can_invite_users:
            try:
                invite_link = await client.export_chat_invite_link(message.chat.id)
                try:
                    joined_chat = await session.get_chat(message.chat.id)
                except:
                    joined_chat = await session.join_chat(invite_link)
            except (InviteHashExpired, ChannelPrivate):
                await massage.edit(f"Assistant is banned in this chat.\n\nPlease unban {session.me.mention()}\nuser id: {session.me.id}")
                return await remove_active_chat(client, target_chat_id)
            except Exception as e:
                await massage.edit(f"Failed to join the group. Error: {e}")
                return await remove_active_chat(client, target_chat_id)
        else:
            await massage.edit("I need 'Invite Users via Link' permission to join this private group. Please grant me this permission.")
            return await remove_active_chat(client, target_chat_id)


    # Set the target chat based on whether it's channel mode or not
    target_chat = None
    if channel_mode:
        # For channel mode, use the linked chat
        target_chat = (await session.get_chat(message.chat.id)).linked_chat
        if not target_chat:
            await massage.edit("Failed to access the linked channel. Please make sure the group has a linked channel.")
            return await remove_active_chat(client, target_chat_id)
    else:
        # For regular mode, use the joined chat
        target_chat = joined_chat

    await put_queue(
        massage,
        trim_title(title),
        client,
        youtube_link,
        target_chat,
        by,
        duration,
        mode,
        thumb,
        force_play,
        stream_url
    )
    if is_active and not force_play:
                position = len(queues.get(message.chat.id)) if queues.get(target_chat.id) else 1
                keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▷", callback_data=f"{'c' if channel_mode else ''}resume"),
                InlineKeyboardButton("II", callback_data=f"{'c' if channel_mode else ''}pause"),
                InlineKeyboardButton("‣‣I", callback_data=f"{'c' if channel_mode else ''}skip"),
                InlineKeyboardButton("▢", callback_data=f"{'c' if channel_mode else ''}end"),
            ],
        [
            InlineKeyboardButton(
                text="✖ Close",
                callback_data="close"
            )
        ],
        ])
                await client.send_message(message.chat.id, queue_styles[int(11)].format(lightyagami(mode), f"[{lightyagami(trim_title(title))}](https://t.me/{client.me.username}?start=vidid_{extract_video_id(youtube_link)})" if not os.path.exists(youtube_link) else  lightyagami(trim_title(title)), lightyagami(duration), position), reply_markup=keyboard,disable_web_page_preview=True)
                try:
                   await message.delete()
                except:
                   pass


    else:
      await dend(client, massage, target_chat.id if channel_mode else None)
    await message.delete()



from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# YouTube functions removed - using imports from youtube.py module



async def put_queue(
    message,
    title,
    client,
    yt_link,
    chat,
    by,
    duration,
audio_flags,
thumb,
forceplay = False,
stream_url = None):
    try:
        duration_in_seconds = time_to_seconds(duration) - 3
    except:
        duration_in_seconds = 0
    put = {
        "message": message,
        "title": trim_title(title),
        "duration": duration,
        "mode": audio_flags,
        "yt_link": yt_link,
        "chat": chat,
        "by": by,
        "session":client,
        "thumb":thumb,
        "stream_url": stream_url
    }
    if forceplay:
        check = queues.get(chat.id)
        if check:
            queues[chat.id].insert(0, put)
        else:
            queues[chat.id] = []
            queues[chat.id].append(put)
    else:
        check = queues.get(chat.id)

        if not check:
           queues[chat.id] = []
        queues[chat.id].append(put)

async def set_gvar(user_id, key, value):
    await set_user_data(user_id, key, value)

async def get_user_data(user_id, key):
    user_data = await user_sessions.find_one({"bot_id": user_id})
    if user_data and key in user_data:
        return user_data[key]
    return None

async def set_user_data(user_id, key, value):
    await user_sessions.update_one({"bot_id": user_id}, {"$set": {key: value}}, upsert=True)

async def gvarstatus(user_id, key):
    return await get_user_data(user_id, key)

async def unset_user_data(user_id, key):
     await user_sessions.update_one({"bot_id": user_id}, {"$unset": {key: ''}}, upsert=True)


def rename_file(old_name, new_name):
    try:
        # Rename the file
        os.rename(old_name, new_name)

        # Get the absolute path of the renamed file
        new_file_path = os.path.abspath(new_name)
        logger.info(f'File renamed from {old_name} to {new_name}')
        return new_file_path  # Return the new file location
    except FileNotFoundError:
        logger.info(f'The file {old_name} does not exist.')
    except FileExistsError:
        logger.info(f'The file {new_name} already exists.')
    except Exception as e:
        logger.info(f'An error occurred: {e}')
import magic

mime = magic.Magic(mime=True)


import psutil
import os
StartTime = time.time()
async def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]

    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)

    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += time_list.pop() + ", "

    time_list.reverse()
    up_time += ":".join(time_list)
    return up_time








async def get_chat_type(client, chat_id):
  try:
    chat = await client.get_chat(chat_id)
    return chat.type
  except FloodWait as e:
        logger.info(f"Rate limited! Sleeping for {e.value} seconds.")
        await asyncio.sleep(e.value)
  except Exception as e:
    logger.info(f"Error getting chat type for {chat_id}: {e}")
    return None



async def status(client, message):
    """Handles the /status command with song statistics"""
    Man = await message.reply_text("Collecting stats...")
    start = datetime.datetime.now()
    u = g = sg = c = a_chat = play_count = 0
    user_data = await find_one(collection, {"bot_id": client.me.id})

    if user_data:
        # Clean old song entries and get count
        time_threshold = datetime.datetime.now() - datetime.timedelta(hours=24)
        collection.update_one(
            {"bot_id": client.me.id},
            {"$pull": {"dates": {"$lt": time_threshold}}}
        )
        updated_data = await find_one(collection, {"bot_id": client.me.id})
        play_count = len(updated_data.get('dates', [])) if updated_data else 0

        users = user_data.get('users', [])
        total_users = len(users)

        # Process chats in batches for better performance
        for i, chat_id in enumerate(users):
            try:
                chat_type = await get_chat_type(client, chat_id)

                if chat_type == enums.ChatType.PRIVATE:
                    u += 1
                elif chat_type == enums.ChatType.GROUP:
                    g += 1
                elif chat_type == enums.ChatType.SUPERGROUP:
                    sg += 1
                    try:
                        user_status = await client.get_chat_member(chat_id, client.me.id)
                        if user_status.status in (enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR):
                            a_chat += 1
                    except Exception as e:
                        logger.info(f"Admin check error: {e}")
                elif chat_type == enums.ChatType.CHANNEL:
                    c += 1

                # Update progress every 10 chats
                if i % 10 == 0 or i == total_users - 1:
                    progress_msg = f"""
<b>🔍 Collecting Stats ({min(i+1, total_users)}/{total_users})</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━</b>
✦ <b>Private:</b> <code>{u}</code>
✦ <b>Groups:</b> <code>{g}</code>
✦ <b>Super Groups:</b> <code>{sg}</code>
✦ <b>Channels:</b> <code>{c}</code>
✦ <b>Admin Positions:</b> <code>{a_chat}</code>
✦ <b>Songs Played (24h):</b> <code>{play_count}</code>
"""
                    await Man.edit_text(progress_msg)

            except Exception as e:
                logger.info(f"Error processing chat {chat_id}: {e}")

        end = datetime.datetime.now()
        ms = (end - start).seconds

        final_stats = f"""
<b>📊 Comprehensive Bot Statistics</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━</b>
⏱ <b>Processed in:</b> <code>{ms}s</code>

✦ <b>Private Chats:</b> <code>{u}</code>
✦ <b>Groups:</b> <code>{g}</code>
✦ <b>Super Groups:</b> <code>{sg}</code>
✦ <b>Channels:</b> <code>{c}</code>
✦ <b>Admin Privileges:</b> <code>{a_chat}</code>
✦ <b>Songs Played (24h):</b> <code>{play_count}</code>

<b>━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎶 @{client.me.username} Performance Summary</b>
"""
        await Man.edit_text(final_stats)

    else:
        await Man.edit_text("❌ No operational data found for this bot")


@Client.on_callback_query(filters.regex("^(end|cend)$"))
@admin_only()
async def button_end_handler(client: Client, callback_query: CallbackQuery):
    # Check if user is banned using global BLOCK variable
    if callback_query.from_user.id in BLOCK:
        await callback_query.answer("You do not have permission to end the session!", show_alert=True)
        return

    try:
        bot_username = client.me.username

        # Determine the chat_id based on whether "cend" is used
        chat_id = (
            (await session.get_chat(callback_query.message.chat.id)).linked_chat.id
            if callback_query.data == "cend"
            else callback_query.message.chat.id
        )

        is_active = await is_active_chat(client, chat_id)
        if is_active:
            # Clear the song queue and end the session
            await remove_active_chat(client, chat_id)
            if chat_id in queues:
                queues[chat_id].clear()
            try:
                await call_py.leave_call(chat_id)
            except Exception as e:
                logger.warning(f"Error leaving call: {e}")
            
            await callback_query.message.reply(
                f"✅ 𝗤𝗨𝗘𝗨𝗘 𝗖𝗟𝗘𝗔𝗥𝗘𝗗!\n┏━━━━━━━━━━━━━━\n┣ 𝗦𝘁𝗿𝗲𝗮𝗺𝗶𝗻𝗴 𝘀𝘁𝗼𝗽𝗽𝗲𝗱\n┗ 👤 {callback_query.from_user.mention()}"
            )
            try:
                await callback_query.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete message: {e}")
            
            if chat_id in playing:
                playing[chat_id].clear()
            
            await callback_query.answer("✅ Stream ended successfully", show_alert=False)
        else:
            await remove_active_chat(client, chat_id)
            try:
                await call_py.leave_call(chat_id)
            except Exception as e:
                logger.warning(f"Error leaving call: {e}")
            
            await callback_query.message.reply(
                f"🚫 𝗡𝗢 𝗦𝗧𝗥𝗘𝗔𝗠!\n┏━━━━━━━━━━━━━━\n┣ 𝗔𝘀𝘀𝗶𝘀𝘁𝗮𝗻𝘁 𝗶𝗱𝗹𝗲\n┗ 🎧 𝗡𝗼𝘁𝗵𝗶𝗻𝗴 𝗽𝗹𝗮𝘆𝗶𝗻𝗴!"
            )
            if chat_id in playing:
                playing[chat_id].clear()
            
            await callback_query.answer("ℹ️ No active stream found", show_alert=False)
    except NotInCallError:
        await remove_active_chat(client, chat_id)
        if chat_id in playing:
            playing[chat_id].clear()
        await callback_query.answer("✅ Stream ended (not in call)", show_alert=False)
    except Exception as e:
        logger.error(f"Error in end button handler: {e}")
        await callback_query.answer(f"❌ Error: {str(e)[:100]}", show_alert=True)


@Client.on_message(filters.command("end"))
@admin_only()
async def end_handler_func(client, message):
  try:
         await message.delete()
  except:
         pass
  user_data = await find_one(collection, {"bot_id": client.me.id})
  busers = user_data.get('busers', [])
  if message.from_user.id in busers:
       return
  try:
   bot_username = client.me.username
   is_active = await is_active_chat(client, message.chat.id)
   if is_active:
       await remove_active_chat(client, message.chat.id)
       queues[message.chat.id].clear()
       await client.send_message(message.chat.id,
f"✅ 𝗤𝗨𝗘𝗨𝗘 𝗖𝗟𝗘𝗔𝗥𝗘𝗗!\n┏━━━━━━━━━━━━━━\n┣ 𝗦𝘁𝗿𝗲𝗮𝗺𝗶𝗻𝗴 𝘀𝘁𝗼𝗽𝗽𝗲𝗱\n┗ 👤 {message.from_user.mention()}"
            )
       await call_py.leave_call(message.chat.id)
       playing[message.chat.id].clear()
   else:
     await client.send_message(message.chat.id, f"🚫 𝗡𝗢 𝗦𝗧𝗥𝗘𝗔𝗠!\n┏━━━━━━━━━━━━━━\n┣ 𝗔𝘀𝘀𝗶𝘀𝘁𝗮𝗻𝘁 𝗶𝗱𝗹𝗲\n┗ 🎧 𝗡𝗼𝘁𝗵𝗶𝗻𝗴 𝗽𝗹𝗮𝘆𝗶𝗻𝗴!"
)
     await remove_active_chat(client, message.chat.id)
     await call_py.leave_call(message.chat.id)
     playing[message.chat.id].clear()
  except NotInCallError:
     await client.send_message(message.chat.id, f"🚫 𝗡𝗢 𝗦𝗧𝗥𝗘𝗔𝗠!\n┏━━━━━━━━━━━━━━\n┣ 𝗔𝘀𝘀𝗶𝘀𝘁𝗮𝗻𝘁 𝗶𝗱𝗹𝗲\n┗ 🎧 𝗡𝗼𝘁𝗵𝗶𝗻𝗴 𝗽𝗹𝗮𝘆𝗶𝗻𝗴!"
)
     playing[message.chat.id].clear()



from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton




@Client.on_callback_query(filters.regex(r"^(skip|cskip)$"))
@admin_only()
async def button_skip_handler(client: Client, callback_query: CallbackQuery):
    user_data = await find_one(collection, {"bot_id": client.me.id})
    busers = user_data.get('busers', [])

    if callback_query.from_user.id in busers:
        await callback_query.answer("You don't have permission to skip!", show_alert=True)
        return

    try:
        bot_username = client.me.username

        chat_id = (
            (await session.get_chat(callback_query.message.chat.id)).linked_chat.id
            if callback_query.data == "cskip"
            else callback_query.message.chat.id
        )

        if chat_id in queues and len(queues[chat_id]) > 0:
            # There's a next song in queue
            next_song = queues[chat_id].pop(0)
            await callback_query.message.reply(f"⏭️ 𝗦𝗞𝗜𝗣𝗣𝗜𝗡𝗚!\n┏━━━━━━━━━━━━━━\n┣ 𝗡𝗲𝘅𝘁 𝘁𝗿𝗮𝗰𝗸 𝗹𝗼𝗮𝗱𝗶𝗻𝗴...\n┗ 👤 {callback_query.from_user.mention()}")
            
            try:
                await clients['call_py'].pause(chat_id)
            except Exception as e:
                logger.warning(f"Could not pause before skip: {e}")
            
            await join_call(
                next_song['message'],
                next_song['title'], 
                next_song['yt_link'], 
                next_song['chat'], 
                next_song['by'], 
                next_song['duration'], 
                next_song['mode'], 
                next_song['thumb'], 
                next_song.get('stream_url')
            )
            await callback_query.answer("⏭️ Skipped to next track", show_alert=False)
        else:
            # No more songs in queue
            try:
                await clients['call_py'].leave_call(chat_id)
            except Exception as e:
                logger.warning(f"Error leaving call: {e}")
            
            await remove_active_chat(client, chat_id)
            
            if chat_id in playing:
                playing[chat_id].clear()
            
            await callback_query.message.reply(f"🚫 𝗦𝗞𝗜𝗣𝗣𝗘𝗗!\n┏━━━━━━━━━━━━━━\n┣ 𝗤𝘂𝗲𝘂𝗲 𝗶𝘀 𝗻𝗼𝘄 𝗲𝗺𝗽𝘁𝘆!\n┗ 👤 {callback_query.from_user.mention()}")
            
            try:
                await callback_query.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete message: {e}")
            
            await callback_query.answer("⏭️ Queue empty, stream ended", show_alert=False)
            
    except NotInCallError:
        await remove_active_chat(client, chat_id)
        if chat_id in playing:
            playing[chat_id].clear()
        await callback_query.answer("✅ Stream ended (not in call)", show_alert=False)
    except Exception as e:
        logger.error(f"Error in skip button handler: {e}")
        await callback_query.answer(f"❌ Error: {str(e)[:100]}", show_alert=True)

@Client.on_message(filters.command("loop"))
@admin_only()
async def loop_handler_func(client, message):
    try:
        await message.delete()
    except:
        pass

    # Check if user is banned
    user_data = await find_one(collection, {"bot_id": client.me.id})
    busers = user_data.get('busers', [])
    if message.from_user.id in busers:
        return

    try:
        # Get loop count from command
        command_parts = message.text.split()
        if len(command_parts) != 2:
            await client.send_message(
                message.chat.id,
                "❌ Please specify the number of loops.\nUsage: /loop <number>"
            )
            return

        try:
            loop_count = int(command_parts[1])
            if loop_count <= 0 or loop_count > 20:
                await client.send_message(
                    message.chat.id,
                    "❌ Loop count must be from 0-20!"
                )
                return
        except ValueError:
            await client.send_message(
                message.chat.id,
                "❌ Please provide a valid number for loops!"
            )
            return

        # Check if there's a song playing
        if message.chat.id in playing and playing[message.chat.id]:
            current_song = playing[message.chat.id]

            # Initialize queue for this chat if it doesn't exist
            if message.chat.id not in queues:
                queues[message.chat.id] = []

            # Add the current song to queue multiple times
            for _ in range(loop_count):
                queues[message.chat.id].insert(0, current_song)

            await client.send_message(
                message.chat.id,
                f"{upper_mono('Current song will be repeated {loop_count} times!')}\n\nʙʏ: {message.from_user.mention()}"
            )
        else:
            await client.send_message(
                message.chat.id,
                f"{upper_mono('Assistant is not streaming anything!')}"
            )

    except Exception as e:
        await client.send_message(
            message.chat.id,
            f"❌ An error occurred: {str(e)}"
        )

@Client.on_message(filters.command("skip"))
@admin_only()
async def skip_handler_func(client, message):
  try:
         await message.delete()
  except:
         pass
  user_data = await find_one(collection, {"bot_id": client.me.id})
  busers = user_data.get('busers', [])
  if message.from_user.id in busers:
       return
  try:
   bot_username = client.me.username
   if message.chat.id in queues:
    if len(queues[message.chat.id]) >0:
       next = queues[message.chat.id].pop(0)
       await client.send_message(message.chat.id, f"⏭️ 𝗦𝗞𝗜𝗣𝗣𝗜𝗡𝗚!\n┏━━━━━━━━━━━━━━\n┣ 𝗡𝗲𝘅𝘁 𝘁𝗿𝗮𝗰𝗸 𝗹𝗼𝗮𝗱𝗶𝗻𝗴...\n┗ 👤 {message.from_user.mention()}")
       playing[message.chat.id] = next
       try:
          await call_py.pause(message.chat.id)
       except:
          pass
       await join_call(next['message'], next['title'], next['yt_link'], next['chat'], next['by'], next['duration'], next['mode'], next['thumb'], next.get('stream_url'))
    else:
       await call_py.leave_call(message.chat.id)
       await remove_active_chat(client, message.chat.id)
       await client.send_message(message.chat.id, f"🚫 𝗦𝗞𝗜𝗣𝗣𝗘𝗗!\n┏━━━━━━━━━━━━━━\n┣ 𝗤𝘂𝗲𝘂𝗲 𝗶𝘀 𝗻𝗼𝘄 𝗲𝗺𝗽𝘁𝘆!\n┗ 👤 {message.from_user.mention()}")
       playing[message.chat.id].clear()
   else:
       await call_py.leave_call(message.chat.id)
       await remove_active_chat(client, message.chat.id)
       await client.send_message(message.chat.id,
              f"🚫 𝗦𝗞𝗜𝗣𝗣𝗘𝗗!\n┏━━━━━━━━━━━━━━\n┣ 𝗤𝘂𝗲𝘂𝗲 𝗶𝘀 𝗻𝗼𝘄 𝗲𝗺𝗽𝘁𝘆!\n┗ 👤 {message.from_user.mention()}")
       playing[message.chat.id].clear()
  except NotInCallError:
     await client.send_message(message.chat.id, f"🚫 𝗡𝗢 𝗦𝗧𝗥𝗘𝗔𝗠!\n┏━━━━━━━━━━━━━━\n┣ 𝗔𝘀𝘀𝗶𝘀𝘁𝗮𝗻𝘁 𝗶𝗱𝗹𝗲\n┗ 🎧 𝗡𝗼𝘁𝗵𝗶𝗻𝗴 𝗽𝗹𝗮𝘆𝗶𝗻𝗴!"
)
     playing[message.chat.id].clear()



@Client.on_callback_query(filters.regex("^(resume|cresume)$"))
@admin_only()
async def button_resume_handler(client: Client, callback_query: CallbackQuery):
    user_data = await find_one(collection, {"bot_id": client.me.id})
    busers = user_data.get('busers', [])

    if callback_query.from_user.id in busers:
        await callback_query.answer("You don't have permission to resume!", show_alert=True)
        return

    try:
        bot_username = client.me.username

        chat_id = (
            (await session.get_chat(callback_query.message.chat.id)).linked_chat.id
            if callback_query.data == "cresume"
            else callback_query.message.chat.id
        )

        if await is_active_chat(client, chat_id):
            await call_py.resume(chat_id)
            await callback_query.message.reply(
                f"Song resumed. Use the Pause button to pause again.\n\nʙʏ: {callback_query.from_user.mention()}"
            )
        else:
            await callback_query.answer("Assistant is not streaming anything!")
    except NotInCallError:
        await callback_query.answer("Assistant is not streaming anything!", show_alert=True)


@Client.on_callback_query(filters.regex("^(pause|cpause)$"))
@admin_only()
async def button_pause_handler(client: Client, callback_query: CallbackQuery):
    user_data = await find_one(collection, {"bot_id": client.me.id})
    busers = user_data.get('busers', [])

    if callback_query.from_user.id in busers:
        await callback_query.answer("You don't have permission to pause!", show_alert=True)
        return

    try:
        bot_username = client.me.username
        chat_id = (
            (await session.get_chat(callback_query.message.chat.id)).linked_chat.id
            if callback_query.data == "cpause"
            else callback_query.message.chat.id
        )

        if await is_active_chat(client, chat_id):
            await call_py.pause(chat_id)
            await callback_query.message.reply(
                f"Song paused. Use the Resume button to continue.\n\nʙʏ: {callback_query.from_user.mention()}"
            )
        else:
            await callback_query.answer("Assistant is not streaming anything!")
    except NotInCallError:
        await callback_query.answer("Assistant is not streaming anything!", show_alert=True)

@Client.on_message(filters.command("resume"))
@admin_only()
async def resume_handler_func(client, message):
  user_data = await find_one(collection, {"bot_id": client.me.id})
  busers = user_data.get('busers', [])
  if message.from_user.id in busers:
       return
  try:
   bot_username = client.me.username
   if  await is_active_chat(client, message.chat.id):
       await call_py.resume(message.chat.id)
       await client.send_message(message.chat.id, f"▶️ 𝗥𝗘𝗦𝗨𝗠𝗘𝗗!\n┏━━━━━━━━━━━━━━\n┣ 𝗨𝘀𝗲 /𝗽𝗮𝘂𝘀𝗲 𝘁𝗼 𝘀𝘁𝗼𝗽\n┗ 👤 {message.from_user.mention()}")
   else: await client.send_message(message.chat.id, f"🚫 𝗡𝗢 𝗦𝗧𝗥𝗘𝗔𝗠!\n┏━━━━━━━━━━━━━━\n┣ 𝗔𝘀𝘀𝗶𝘀𝘁𝗮𝗻𝘁 𝗶𝗱𝗹𝗲\n┗ 🎧 𝗡𝗼𝘁𝗵𝗶𝗻𝗴 𝗽𝗹𝗮𝘆𝗶𝗻𝗴!")
  except NotInCallError:
     await client.send_message(message.chat.id, f"🚫 𝗡𝗢 𝗦𝗧𝗥𝗘𝗔𝗠!\n┏━━━━━━━━━━━━━━\n┣ 𝗔𝘀𝘀𝗶𝘀𝘁𝗮𝗻𝘁 𝗶𝗱𝗹𝗲\n┗ 🎧 𝗡𝗼𝘁𝗵𝗶𝗻𝗴 𝗽𝗹𝗮𝘆𝗶𝗻𝗴!")


@Client.on_message(filters.command("pause"))
@admin_only()
async def pause_handler_func(client, message):
  user_data = await find_one(collection, {"bot_id": client.me.id})
  busers = user_data.get('busers', [])
  if message.from_user.id in busers:
       return
  try:
   bot_username = client.me.username
   if  await is_active_chat(client, message.chat.id):
       await call_py.pause(message.chat.id)
       await client.send_message(message.chat.id, f"⏸️ 𝗣𝗔𝗨𝗦𝗘𝗗!\n┏━━━━━━━━━━━━━━\n┣ 𝗨𝘀𝗲 /𝗿𝗲𝘀𝘂𝗺𝗲 𝘁𝗼 𝗰𝗼𝗻𝘁𝗶𝗻𝘂𝗲\n┗ 👤 {message.from_user.mention()}"
)
   else:
       await client.send_message(message.chat.id,  f"🚫 𝗡𝗢 𝗦𝗧𝗥𝗘𝗔𝗠!\n┏━━━━━━━━━━━━━━\n┣ 𝗔𝘀𝘀𝗶𝘀𝘁𝗮𝗻𝘁 𝗶𝗱𝗹𝗲\n┗ 🎧 𝗡𝗼𝘁𝗵𝗶𝗻𝗴 𝗽𝗹𝗮𝘆𝗶𝗻𝗴!")
  except NotInCallError:
     await client.send_message(message.chat.id, f"🚫 𝗡𝗢 𝗦𝗧𝗥𝗘𝗔𝗠!\n┏━━━━━━━━━━━━━━\n┣ 𝗔𝘀𝘀𝗶𝘀𝘁𝗮𝗻𝘁 𝗶𝗱𝗹𝗲\n┗ 🎧 𝗡𝗼𝘁𝗵𝗶𝗻𝗴 𝗽𝗹𝗮𝘆𝗶𝗻𝗴!")

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


@Client.on_callback_query(filters.regex("broadcast"))
async def broadcast_callback_handler(client, callback_query):
    # Fetch user data for the callback query
    user_data = await user_sessions.find_one({"bot_id": client.me.id})
    if not user_data:
        return await callback_query.answer("User data not found. Please log in first.", show_alert=True)
    group = user_data.get('group')
    private = user_data.get('private')
    ugroup = user_data.get('ugroup')
    uprivate = user_data.get('uprivate')
    bot = user_data.get('bot')
    userbot = user_data.get('userbot')
    pin = user_data.get('pin')
    await callback_query.message.delete()
    # Fetch bot data
    bot_data = await find_one(collection, {"bot_id": client.me.id})
    message_to_broadcast, forwarding = broadcast_message.get(client.me.id)
    if bot_data and bot:
        X = await callback_query.message.reply("Starting broadcast from bot")
        users = bot_data.get('users', [])
        progress_msg = ""
        u, g, sg, a_chat = 0, 0, 0, 0

        # Use asyncio.gather for efficient parallel processing
        chat_types = await asyncio.gather(
            *[get_chat_type(client, chat_id) for chat_id in users]
        )

        # Prepare message for broadcast
        if not message_to_broadcast:
            return await callback_query.answer("No message ready for broadcast.", show_alert=True)

        for i, chat_type in enumerate(chat_types):
            if not chat_type:
                continue  # Skip if chat type could not be fetched

            # Handle the chat based on its type and flags
            try:
                if chat_type == enums.ChatType.PRIVATE and private:
                    await message_to_broadcast.copy(users[i])  if not forwarding else await message_to_broadcast.forward(users[i])
                    u+=1

                elif chat_type in (enums.ChatType.SUPERGROUP, enums.ChatType.GROUP) and group:
                    # Handle supergroup-specific actions
                    sent_message = await message_to_broadcast.copy(users[i]) if not forwarding else await message_to_broadcast.forward(users[i])
                    if chat_type == enums.ChatType.SUPERGROUP:
                        sg+=1
                    else:
                        g+=1
                    if pin:
                      try:
                        user_s = await client.get_chat_member(users[i], client.me.id)
                        if user_s.status in (enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR):
                            await sent_message.pin()
                            a_chat += 1
                      except FloodWait as e:
                              await asyncio.sleep(e.value)
                      except Exception as e:
                        logger.info(f"Error getting chat member status for {users[i]}: {e}")
                else:
                       continue

                # Update progress for each broadcast action (optional)
                progress_msg = f"Broadcasting to {u} private, {g} groups, {sg} supergroups, and {a_chat} pinned messages"
                await X.edit(progress_msg)
            except Exception as e:
                logger.info(f"Error in broadcasting to {users[i]}: {e}")
        await X.edit(f"Broadcasted to {u} private, {g} groups, {sg} supergroups, and {a_chat} pinned messages from bot")
    bot_username = client.me.username


    if userbot and session:
        XX = await callback_query.message.reply("Starting broadcast from assistant")
        uu, ug, usg, ua_chat = 0, 0, 0, 0
        try:
            # Ensure communication with the bot
            try:
                await session.get_chat(client.me.id)
            except PeerIdInvalid:
                await session.send_message(bot_username, "/start")
            except UserBlocked:
                await session.unblock_user(bot_username)
            await asyncio.sleep(1)

            # Copy the message to session and fetch history
            copied_message = await message_to_broadcast.copy(session.me.id) if not forwarding else await message_to_broadcast.forward(session.me.id)
            await asyncio.sleep(2)

            msg = await compare_message(copied_message, client, session)
            if not msg:
             raise Exception("broadcast msg not found")
            # Broadcast to all dialogs
            async for dialog in session.get_dialogs():
                chat_id = dialog.chat.id
                chat_type = dialog.chat.type
                if str(chat_id) == str(-1001806816712):
                      continue
                try:
                    if chat_type == enums.ChatType.PRIVATE and uprivate:
                        await msg.copy(chat_id)
                        uu += 1

                    elif chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP) and ugroup:
                        sent_message = await msg.copy(chat_id)  if not forwarding else await message_to_broadcast.forward(users[i])
                        if chat_type == enums.ChatType.SUPERGROUP:
                            usg += 1
                        else:
                            ug += 1

                    else:
                       continue
                    # Update progress
                    progress_text = (
                        f"Broadcasting via assistant...\n\n"
                        f"Private Chats: {uu}\n"
                        f"Groups: {ug}\n"
                        f"Supergroups: {usg}\n"
                    )
                    await XX.edit(progress_text)
                except FloodWait as e:
                               await asyncio.sleep(e.value)
                except Exception as e:
                    logger.info(f"Error broadcasting to {chat_id}: {e}")

        except Exception as e:
            logger.info(f"Error with session broadcast: {e}")
            await XX.reply(f"An error occurred during userbot broadcasting.{e}")

    # Finalize broadcast summary
        await XX.edit(
        f"Broadcast completed!\n\n"
        f"Private Chats: {uu}\n"
        f"Groups: {ug}\n"
        f"Supergroups: {usg}\n"
    )



async def get_status(client):
  bot_username = client.me.username

  start = datetime.datetime.now()
  u = g = sg = a_chat =  0 # Initialize counters
  user_data = await find_one(collection, {"bot_id": client.me.id})
  mess=""

  if user_data:
    users = user_data.get('users', [])
    progress_msg = ""


    # Use asyncio.gather for efficient parallel processing
    chat_types = await asyncio.gather(
      *[get_chat_type(client, chat_id) for chat_id in users]
    )
    for i, chat_type in enumerate(chat_types):
      if chat_type is None:
        continue # Skip if chat type could not be fetched

      if chat_type == enums.ChatType.PRIVATE:
        u += 1
      elif chat_type ==  enums.ChatType.GROUP:
        g += 1
      elif chat_type == enums.ChatType.SUPERGROUP:
        sg += 1
        try:
          user_s = await client.get_chat_member(users[i], int(client.me.id))
          if user_s.status in (
            enums.ChatMemberStatus.OWNER,
                enums.ChatMemberStatus.ADMINISTRATOR,
          ):
            a_chat += 1
        except Exception as e:
          logger.info(f"Error getting chat member status for {users[i]}: {e}")
    mess += (
        f"""<b>BOT STATS:</b>
<blockquote><b>`Private chats = {u}</b>`
<b>`Groups = {g}`
<b>`Super Groups = {sg}`<b>
<b>`Admin in Chats = {a_chat}`</b></blockquote>""")

      #Update the progress message every 10 iterations.
    uu = ug = usg  = ua_chat =0
    async for dialog in session.get_dialogs():
      try:
        if dialog.chat.type == enums.ChatType.PRIVATE:
            uu += 1
        elif dialog.chat.type == enums.ChatType.GROUP:
            ug += 1
        elif dialog.chat.type == enums.ChatType.SUPERGROUP:
            usg += 1
            user_s = await dialog.chat.get_member(int(session.me.id))
            if user_s.status in (
                enums.ChatMemberStatus.OWNER,
                enums.ChatMemberStatus.ADMINISTRATOR,
            ):
                ua_chat += 1
      except:
        pass
        # Count blocked users from the blocklist
    # Final message with stats

    mess += (
        f"""\n\n<b>ASSISTANT STATS:</b>
<blockquote><b>`Private Messages = {uu}`
<b>`Groups = {ug}`
<b>`Super Groups = {usg}`<b>
<b>`Admin in Chats = {ua_chat}`</b></blockquote>"""
    )
    mess += (f"\n\n<blockquote><b>CHOOSE THE OPTIONS BELOW⬇️⬇️ FOR BRODCASTING</b></blockquote>")
    broadcasts[client.me.id] = mess
    return mess
  else:
    return

async def compare_message(mess, client, session):
    async for msg in session.get_chat_history(chat_id=client.me.id, limit=2):
        # Compare text messages
        if mess.text and msg.text == mess.text:
            return msg

        # Compare media messages
        elif mess.media and msg.media:
            try:
                # Get the media type (photo, video, etc.)
                mess_media_type = mess.media.value
                msg_media_type = msg.media.value

                # Check if both messages have the same media type
                if mess_media_type == msg_media_type:
                    # Get file unique IDs for comparison
                    mess_file_id = getattr(mess, mess_media_type).file_unique_id
                    msg_file_id = getattr(msg, msg_media_type).file_unique_id

                    # Compare file IDs
                    if mess_file_id and msg_file_id and mess_file_id == msg_file_id:
                        return msg
            except AttributeError:
                # Skip if media attributes are not accessible
                continue

    # Return None if no matching message is found
    return None

@Client.on_callback_query(filters.regex(r"toggle_(.*)"))
async def toggle_setting(client, callback_query):
    sender_id = client.me.id

    user_data = await user_sessions.find_one({"bot_id": sender_id})
    if not user_data:
        return await callback_query.answer("User data not found. Please log in first.", show_alert=True)
    setting_to_toggle = callback_query.data.split("_", 1)[1]
    current_value = user_data.get(setting_to_toggle)
    new_value = not current_value
    await user_sessions.update_one(
        {"bot_id": sender_id},
        {"$set": {setting_to_toggle: new_value}}
    )
    await broadcast_command_handler(client, callback_query)


@Client.on_message(filters.command("stats"))
async def status_command_handler(client, message):
    user_id = message.from_user.id
    admin_file = f"{ggg}/admin.txt"

    # Get user data and permissions
    users_data = await find_one(user_sessions, {"bot_id": client.me.id})
    sudoers = users_data.get("SUDOERS", []) if users_data else []

    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    # Check permissions
    is_authorized = (
        is_admin or
        str(OWNER_ID) == str(user_id) or
        user_id in sudoers
    )

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS OWNER/SUDOER'S COMMAND...**")

    await status(client, message)



@Client.on_message(filters.command(["broadcast", "fbroadcast"]) & filters.private)
async def broadcast_command_handler(client, message):
    user_id = message.from_user.id
    admin_file = f"{ggg}/admin.txt"
    users_data = await find_one(user_sessions, {"bot_id": client.me.id})
    sudoers = users_data.get("SUDOERS", []) if users_data else []

    is_admin = False
    if os.path.exists(admin_file):
        with open(admin_file, "r") as file:
            admin_ids = [int(line.strip()) for line in file.readlines()]
            is_admin = user_id in admin_ids

    # Check permissions
    is_authorized = (
        is_admin or
        str(OWNER_ID) == str(user_id) or
        user_id in sudoers
    )

    if not is_authorized:
        return await message.reply("**MF\n\nTHIS IS OWNER/SUDOER'S COMMAND...**")

    sender_id = client.me.id
    user_data = await user_sessions.find_one({"bot_id": sender_id})
    if not user_data:
        return await message.reply("User data not found. Please log in first.")
    if not isinstance(message, CallbackQuery):
      if not message.reply_to_message:
        return await message.reply("please reply to any message to brodcaste")
      broadcast_message[client.me.id] = [message.reply_to_message]
      broadcast_message[client.me.id].append(True if message.command[0].lower().startswith("f") else None)
    group = user_data.get('group')
    private = user_data.get('private')
    ugroup = user_data.get('ugroup')
    uprivate = user_data.get('uprivate')
    bot = user_data.get('bot')
    userbot = user_data.get('userbot')
    pin = user_data.get('pin')
    for_bot =[
            InlineKeyboardButton(f"Gʀᴏᴜᴘ {'✅' if group else '❌'}", callback_data="toggle_group"),
            InlineKeyboardButton(f"Pʀɪᴠᴀᴛᴇ {'✅' if private else '❌'}", callback_data="toggle_private"),
            InlineKeyboardButton(f"📌Pɪɴ {'✅' if pin else '❌'}", callback_data="toggle_pin"),]

    for_userbot = [
            InlineKeyboardButton(f"Gʀᴏᴜᴘ {'✅' if ugroup else '❌'}", callback_data="toggle_ugroup"),
            InlineKeyboardButton(f"Pʀɪᴠᴀᴛᴇ {'✅' if uprivate else '❌'}", callback_data="toggle_uprivate"),]
    buttons = [
            [InlineKeyboardButton(f"Fʀᴏᴍ ʙᴏᴛ {'⬇️' if bot else '❌'}", callback_data="toggle_bot"),], for_bot if bot else [],
        [
            InlineKeyboardButton(f"Fʀᴏᴍ ᴜꜱᴇʀʙᴏᴛ {'⬇️' if userbot else '❌'}", callback_data="toggle_userbot"),], for_userbot if userbot else [],
    ]


    buttons.append([InlineKeyboardButton("BROADCAST🚀🚀", callback_data="broadcast")])
    if isinstance(message, CallbackQuery):  # If it's a button click (CallbackQuery)
        if not client.me.id in broadcasts:
           await get_status(client)
        await message.edit_message_text(
            broadcasts[client.me.id],
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:  # If it's a normal command message
        mess = await message.reply("Getting all chats, please wait...")
        await get_status(client)
        if broadcasts[client.me.id]:
           await mess.edit(
            broadcasts[client.me.id],
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        else:
           await message.reply("No data found")



@Client.on_message(filters.command("powers") & filters.group)
@admin_only()
async def handle_power_command(client, message):
    try:
        # Get bot's permissions in the group
        bot_member = await client.get_chat_member(
            chat_id=message.chat.id,
            user_id=client.me.id if not message.reply_to_message else message.reply_to_message.from_user.id
        )

        # Get chat info
        chat = await client.get_chat(message.chat.id)

        # Create permission status message
        power_message = (
            f"🤖 **{'Bot' if not message.reply_to_message else message.reply_to_message.from_user.mention()} Permissions in {chat.title}**\n\n"
            "📋 **Basic Powers:**\n"
        )

        # Basic permissions
        permissions = {
            "can_delete_messages": "Delete Messages",
            "can_restrict_members": "Restrict Members",
            "can_promote_members": "Promote Members",
            "can_change_info": "Change Group Info",
            "can_invite_users": "Invite Users",
            "can_pin_messages": "Pin Messages",
            "can_manage_video_chats": "Manage Video Chats",
            "can_manage_chat": "Manage Chat",
            "can_manage_topics": "Manage Topics"
        }

        # Add permission statuses
        for perm, display_name in permissions.items():
            status = getattr(bot_member.privileges, perm, False)
            emoji = "✅" if status else "❌"
            power_message += f"{emoji} {display_name}\n"

        # Add administrative status
        power_message += "\n📊 **Status:**\n"
        if bot_member.status == enums.ChatMemberStatus.ADMINISTRATOR:
            power_message += "✨ Bot is an **Administrator**"
        elif bot_member.status == enums.ChatMemberStatus.MEMBER:
            power_message += "👤 Bot is a **Regular Member**"
        else:
            power_message += "❓ Bot Status: " + str(bot_member.status).title()

        # Add anonymous admin status if applicable
        if hasattr(bot_member.privileges, "is_anonymous"):
            anon_status = "✅" if bot_member.privileges.is_anonymous else "❌"
            power_message += f"\n{anon_status} Anonymous Admin"

        # Add custom title if exists
        if hasattr(bot_member, "custom_title") and bot_member.custom_title:
            power_message += f"\n👑 Custom Title: **{bot_member.custom_title}**"

        # Create inline buttons for refresh and support
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_power_{message.chat.id}"),
            ]
        ])

        await message.reply(
            power_message,
            #reply_markup=buttons
        )

    except Exception as e:
        logger.error(f"Power check error: {e}")
        await message.reply("❌ Failed to check bot permissions!")




@Client.on_message(filters.command("ping"))
async def pingme(client, message):
    # Calculate uptime
    from random import choice
    uptime = await get_readable_time((time.time() - StartTime))
    start = datetime.datetime.now()
    owner = await client.get_users(OWNER_ID)
    ow_id = owner.id if owner.username else None
    # Fun emoji animations for loading
    loading_emojis = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]
    ping_frames = [
        "█▒▒▒▒▒▒▒▒▒▒ 10%",
        "███▒▒▒▒▒▒▒ 30%",
        "█████▒▒▒▒▒ 50%",
        "███████▒▒▒ 70%",
        "█████████▒ 90%",
        "██████████ 100%"
    ]

    # Animated loading sequence
    msg = await message.reply_text("🏓 **Pinging...**")

    for frame in ping_frames:
        await msg.edit(f"```\n{frame}\n```{choice(loading_emojis)}")
        await asyncio.sleep(0.3)  # Smooth animation delay

    end = datetime.datetime.now()
    ping_duration = (end - start).microseconds / 1000

    # Status indicators based on ping speed
    if ping_duration < 100:
        status = "EXCELLENT 🟢"
    elif ping_duration < 200:
        status = "GOOD 🟡"
    else:
        status = "MODERATE 🔴"

    # Fancy formatted response
    response = f"""
╭──────────────────
│   PONG! 🏓
├──────────────────
│ ⌚ Speed: {ping_duration:.2f}ms
│ 📊 Status: {status}
│ ⏱️ Uptime: {uptime}
│ 👑 Owner: {owner.mention()}
╰──────────────────
"""

    # Add random motivational messages
    quotes = [
        "Blazing fast! ⚡",
        "Speed demon! 🔥",
        "Lightning quick! ⚡",
        "Sonic boom! 💨"
    ]

    await msg.edit(
        response + f"\n<b>{choice(quotes)}</b>"
    )

from pyrogram import Client, enums, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

@Client.on_message(filters.command("about"))
async def info_command(client: Client, message: Message):
    chat = message.chat
    replied = message.reply_to_message

    # Setup user directory
    session_name = f'user_{client.me.id}'
    user_dir = f"{ggg}/{session_name}"
    os.makedirs(user_dir, exist_ok=True)
    photo_path = f"{user_dir}/logo.jpg"

    def create_copy_markup(text: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Copy Info", copy_text=text)
        ]])

    # Handle second argument if provided
    target_user = None
    sender_id = message.from_user.id
    if not sender_id == OWNER_ID:
        return await message.reply_text("Only bot owner is allowed to perform this command")

    if len(message.command) >= 2:
        user_input = message.command[1]
        try:
            # Try to get user by ID first
            if user_input.isdigit():
                target_user = await client.get_users(int(user_input))
            else:
                # If not ID, try username (with or without @ symbol)
                username = user_input.strip('@')
                target_user = await client.get_users(username)
        except Exception:
            await message.reply("❌ User not found. Please provide a valid username or ID.")
            return

    if target_user:
        # Handle user specified by argument
        user = target_user
        response = (
            "👤 **User Info**\n"
            f"🆔 **ID**: `{user.id}`\n"
            f"📛 **Name**: {user.first_name}"
        )
        if user.last_name:
            response += f" {user.last_name}\n"
        else:
            response += "\n"

        if user.username:
            response += f"🌐 **Username**: @{user.username}\n"

        # Add restriction, scam, and fake flags
        if user.is_restricted:
            response += "⚠️ **Account Restricted**: Yes\n"
            if user.restriction_reason:
                response += f"📝 **Restriction Reason**: {user.restriction_reason}\n"
        if user.is_scam:
            response += "🚫 **Scam Account**: Yes\n"
        if user.is_fake:
            response += "🎭 **Impersonator**: Yes\n"

        # Add status and join date for group queries
        if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            try:
                member = await client.get_chat_member(chat.id, user.id)
                status_map = {
                    enums.ChatMemberStatus.OWNER: "👑 Owner",
                    enums.ChatMemberStatus.ADMINISTRATOR: "🔧 Admin",
                    enums.ChatMemberStatus.MEMBER: "👤 Member"
                }
                response += f"🎚 **Status**: {status_map.get(member.status, 'Unknown')}\n"

                if member.joined_date:
                    join_date = member.joined_date.strftime("%Y-%m-%d %H:%M:%S UTC")
                    response += f"📅 **Joined**: {join_date}\n"
                else:
                    response += "📅 **Joined**: Unknown\n"
            except Exception:
                response += "🎚 **Status**: ❌ Not in group\n"

        # Handle profile photo
        if user.photo:
            try:
                await client.download_media(user.photo.big_file_id, photo_path)
                await message.reply_photo(
                    photo_path,
                    caption=response,
                    reply_markup=create_copy_markup(response)
                )
            except Exception:
                await message.reply(
                    response,
                    reply_markup=create_copy_markup(response)
                )
        else:
            await message.reply(
                response,
                reply_markup=create_copy_markup(response)
            )
        return

    # Rest of the original code for replied messages and chat info remains the same
    if replied:
        if replied.sender_chat:
            sender_chat = replied.sender_chat
            if sender_chat.id == chat.id:
                response = (
                    "👤 **Anonymous Group Admin**\n"
                    f"🏷 **Title**: {sender_chat.title}\n"
                    f"🆔 **Chat ID**: `{sender_chat.id}`"
                )
            else:
                response = (
                    "📢 **Channel Info**\n"
                    f"🏷 **Title**: {sender_chat.title}\n"
                    f"🆔 **ID**: `{sender_chat.id}`\n"
                )
                if sender_chat.username:
                    response += f"🌐 **Username**: @{sender_chat.username}\n"
                if sender_chat.description:
                    response += f"📄 **Description**: {sender_chat.description[:300]}..."

            await message.reply(
                response,
                reply_markup=create_copy_markup(response)
            )

        else:
            user = await client.get_users(replied.from_user.id)

            response = (
                "👤 **User Info**\n"
                f"🆔 **ID**: `{user.id}`\n"
                f"📛 **Name**: {user.first_name}"
            )
            if user.last_name:
                response += f" {user.last_name}\n"
            else:
                response += "\n"

            if user.username:
                response += f"🌐 **Username**: @{user.username}\n"

            if user.is_restricted:
                response += "⚠️ **Account Restricted**: Yes\n"
                if user.restriction_reason:
                    response += f"📝 **Restriction Reason**: {user.restriction_reason}\n"
            if user.is_scam:
                response += "🚫 **Scam Account**: Yes\n"
            if user.is_fake:
                response += "🎭 **Impersonator**: Yes\n"

            if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
                try:
                    member = await client.get_chat_member(chat.id, user.id)
                    status_map = {
                        enums.ChatMemberStatus.OWNER: "👑 Owner",
                        enums.ChatMemberStatus.ADMINISTRATOR: "🔧 Admin",
                        enums.ChatMemberStatus.MEMBER: "👤 Member"
                    }
                    response += f"🎚 **Status**: {status_map.get(member.status, 'Unknown')}\n"

                    if member.joined_date:
                        join_date = member.joined_date.strftime("%Y-%m-%d %H:%M:%S UTC")
                        response += f"📅 **Joined**: {join_date}\n"
                    else:
                        response += "📅 **Joined**: Unknown\n"
                except Exception:
                    response += "🎚 **Status**: ❌ Not in group\n"

            if user.photo:
                try:
                    await client.download_media(user.photo.big_file_id, photo_path)
                    await message.reply_photo(
                        photo_path,
                        caption=response,
                        reply_markup=create_copy_markup(response)
                    )
                except Exception:
                    await message.reply(
                        response,
                        reply_markup=create_copy_markup(response)
                    )
            else:
                await message.reply(
                    response,
                    reply_markup=create_copy_markup(response)
                )

    else:
        if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            full_chat = await client.get_chat(chat.id)

            admin_count = 0
            async for member in client.get_chat_members(
                chat.id,
                filter=enums.ChatMembersFilter.ADMINISTRATORS
            ):
                admin_count += 1

            response = (
                "👥 **Group Info**\n"
                f"🏷 **Title**: {full_chat.title}\n"
                f"🆔 **ID**: `{full_chat.id}`\n"
            )

            if full_chat.username:
                response += f"🌐 **Username**: @{full_chat.username}\n"
            response += (
                f"👥 **Members**: {full_chat.members_count}\n"
                f"🔧 **Admins**: {admin_count}\n"
            )

            await message.reply(
                response,
                reply_markup=create_copy_markup(response)
            )

        else:
            user = await client.get_users(chat.id)

            response = (
                "👤 **User Info**\n"
                f"🆔 **ID**: `{user.id}`\n"
                f"📛 **Name**: {user.first_name}"
            )
            if user.last_name:
                response += f" {user.last_name}\n"
            else:
                response += "\n"

            if user.username:
                response += f"🌐 **Username**: @{user.username}\n"

            if user.is_restricted:
                response += "⚠️ **Account Restricted**: Yes\n"
                if user.restriction_reason:
                    response += f"📝 **Restriction Reason**: {user.restriction_reason}\n"

            if user.is_scam:
                response += "🚫 **Scam Account**: Yes\n"

            if user.is_fake:
                response += "🎭 **Impersonator**: Yes\n"

            if user.photo:
                try:
                    await client.download_media(user.photo.big_file_id, photo_path)
                    await message.reply_photo(
                        photo_path,
                        caption=response,
                        reply_markup=create_copy_markup(response)
                    )
                except Exception:
                    await message.reply(
                        response,
                        reply_markup=create_copy_markup(response)
                    )
            else:
                await message.reply(
                    response,
                    reply_markup=create_copy_markup(response)
                )


@Client.on_callback_query(filters.regex("^close$"))
async def close_message(client, query):
    try:
        # Delete the original message
        await query.message.delete()
        # Send confirmation with mention
        await client.send_message(
            query.message.chat.id,
            f"🗑 Message closed by {query.from_user.mention}"
        )
    except Exception as e:
        print(f"Error closing message: {e}")




@Client.on_message(filters.command("kang"))
async def kang(client, message):
    bot_username = client.me.username
    client = clients['session']
    user = message.from_user
    if not user:
       return await message.reply_text("Use this command as user")
    replied = message.reply_to_message
    Man = await message.reply_text("`It's also possible that the sticker is colong ahh...`")
    media_ = None
    emoji_ = None
    is_anim = False
    is_video = False
    resize = False
    ff_vid = False
    if replied and replied.media:
        if replied.photo:
            resize = True
        elif replied.document and "image" in replied.document.mime_type:
            resize = True
            replied.document.file_name
        elif replied.document and "tgsticker" in replied.document.mime_type:
            is_anim = True
            replied.document.file_name
        elif replied.document and "video" in replied.document.mime_type:
            resize = True
            is_video = True
            ff_vid = True
        elif replied.animation:
            resize = True
            is_video = True
            ff_vid = True
        elif replied.video:
            resize = True
            is_video = True
            ff_vid = True
        elif replied.sticker:
            if not replied.sticker.file_name:
                await Man.edit("**Sticker has no Name!**")
                return
            emoji_ = replied.sticker.emoji
            is_anim = replied.sticker.is_animated
            is_video = replied.sticker.is_video
            if not (
                replied.sticker.file_name.endswith(".tgs")
                or replied.sticker.file_name.endswith(".webm")
            ):
                resize = True
                ff_vid = True
        else:
            await Man.edit("**Unsupported File**")
            return
        media_ = await client.download_media(replied, file_name=f"{ggg}/user_{client.me.id}/")
    else:
        await Man.edit("**Please Reply to Photo/GIF/Sticker Media!**")
        return
    if media_:
        args = get_arg(message)
        pack = 1
        if len(args) == 2:
            emoji_, pack = args
        elif len(args) == 1:
            if args[0].isnumeric():
                pack = int(args[0])
            else:
                emoji_ = args[0]

        if emoji_ and emoji_ not in (
            getattr(emoji, _) for _ in dir(emoji) if not _.startswith("_")
        ):
            emoji_ = None
        if not emoji_:
            emoji_ = "✨"

        u_name = user.username
        u_name = "@" + u_name if u_name else user.first_name or user.id
        packname = f"Sticker_u{user.id}_v{pack}"
        custom_packnick = f"{u_name} Sticker Pack"
        packnick = f"{custom_packnick} Vol.{pack}"
        cmd = "/newpack"
        if resize:
            media_ = await resize_media(media_, is_video, ff_vid)
        if is_anim:
            packname += "_animated"
            packnick += " (Animated)"
            cmd = "/newanimated"
        if is_video:
            packname += "_video"
            packnick += " (Video)"
            cmd = "/newvideo"
        exist = False
        while True:
            try:
                exist = await client.invoke(
                    GetStickerSet(
                        stickerset=InputStickerSetShortName(short_name=packname), hash=0
                    )
                )
            except StickersetInvalid:
                exist = False
                break
            limit = 50 if (is_video or is_anim) else 120
            if exist.set.count >= limit:
                pack += 1
                packname = f"a{user.id}_by_userge_{pack}"
                packnick = f"{custom_packnick} Vol.{pack}"
                if is_anim:
                    packname += f"_anim{pack}"
                    packnick += f" (Animated){pack}"
                if is_video:
                    packname += f"_video{pack}"
                    packnick += f" (Video){pack}"
                await Man.edit(
                    f"`Create a New Sticker Pack {pack} Because the Sticker Pack is Full`"
                )
                continue
            break
        if exist is not False:
            try:
                await client.send_message("stickers", "/addsticker")
            except YouBlockedUser:
                await client.unblock_user("stickers")
                await client.send_message("stickers", "/addsticker")
            except Exception as e:
                return await Man.edit(f"**ERROR:** `{e}`")
            await asyncio.sleep(2)
            await client.send_message("stickers", packname)
            await asyncio.sleep(2)
            limit = "50" if is_anim else "120"
            while limit in await get_response(message, client):
                pack += 1
                packname = f"a{user.id}_by_{user.username}_{pack}"
                packnick = f"{custom_packnick} vol.{pack}"
                if is_anim:
                    packname += f"_anim"
                    packnick += " (Animated)"
                if is_video:
                    packname += "_video"
                    packnick += " (Video)"
                    await Man.edit(
                    f"`Creating a New Sticker Pack {pack} Because the Sticker Pack is Full`"
                )
                await client.send_message("stickers", packname)
                await asyncio.sleep(2)
                if await get_response(message, client) == "Invalid pack selected.":
                    await client.send_message("stickers", cmd)
                    await asyncio.sleep(2)
                    await client.send_message("stickers", packnick)
                    await asyncio.sleep(2)
                    await client.send_document("stickers", media_)
                    await asyncio.sleep(2)
                    await client.send_message("Stickers", emoji_)
                    await asyncio.sleep(2)
                    await client.send_message("Stickers", "/publish")
                    await asyncio.sleep(2)
                    if is_anim:
                        await client.send_message(
                            "Stickers", f"<{packnick}>", parse_mode=ParseMode.MARKDOWN
                        )
                        await asyncio.sleep(2)
                    await client.send_message("Stickers", "/skip")
                    await asyncio.sleep(2)
                    await client.send_message("Stickers", packname)
                    await asyncio.sleep(2)
                    await Man.edit(
                        f"**Sticker Added Successfully!**\n 🔥 **[CLICK HERE](https://t.me/addstickers/{packname})** 🔥\n**To Use Stickers**"
                    )
            await client.send_document("stickers", media_)
            await asyncio.sleep(2)
            if (
                await get_response(message, client)
                == "Sorry, the file type is invalid."
            ):
                await Man.edit(
                    "**Failed to Add Sticker, Use @Stickers Bot to Add Your Sticker.**"
                )
                return
            await client.send_message("Stickers", emoji_)
            await asyncio.sleep(2)
            await client.send_message("Stickers", "/done")
        else:
            await Man.edit("`Creating a New Sticker Pack`")
            try:
                await client.send_message("Stickers", cmd)
            except YouBlockedUser:
                await client.unblock_user("stickers")
                await client.send_message("stickers", "/addsticker")
            await asyncio.sleep(2)
            await client.send_message("Stickers", packnick)
            await asyncio.sleep(2)
            await client.send_document("stickers", media_)
            await asyncio.sleep(2)
            if (
                await get_response(message, client)
                == "Sorry, the file type is invalid."
            ):
                await Man.edit(
                    "**Failed to Add Sticker, Use @Stickers Bot to Add Your Sticker.**"
                )
                return
            await client.send_message("Stickers", emoji_)
            await asyncio.sleep(2)
            await client.send_message("Stickers", "/publish")
            await asyncio.sleep(2)
            if is_anim:
                await client.send_message("Stickers", f"<{packnick}>")
                await asyncio.sleep(2)
            await client.send_message("Stickers", "/skip")
            await asyncio.sleep(2)
            await client.send_message("Stickers", packname)
            await asyncio.sleep(2)
        await Man.edit(
            f"**Sticker Added Successfully!**\n 🔥 **[CLICK HERE](https://t.me/addstickers/{packname})** 🔥\n**To Use Stickers**"
        )
        if os.path.exists(str(media_)):
            os.remove(media_)






async def get_response(message, client):
    return [x async for x in client.get_chat_history("Stickers", limit=1)][0].text


@Client.on_message(filters.command("mmf"))
async def memify(client, message):
    if not message.reply_to_message_id:
        await message.reply_text("**Reply to any photo or sticker!**")
        return
    reply_message = message.reply_to_message
    if not reply_message.media:
        await message.reply_text( "**Reply to any photo or sticker!**")
        return
    file = await client.download_media(reply_message)
    Man = await message.reply_text( "`Processing . . .`")
    text = get_arg(message)
    if len(text) < 1:
        return await Man.edit(f"Please use `/mmf <text>`")
    meme = await add_text_img(file, text)
    await asyncio.gather(
        Man.delete(),
        client.send_sticker(
            message.chat.id,                                                                                          sticker=meme,
            reply_to_message_id=reply_message.id,                                                                 ),
    )
    os.remove(meme)
    await message.delete()


import subprocess
import os
from pyrogram import Client, filters



@Client.on_message(filters.command("setwelcome") & filters.private)
async def set_welcome_handler(client, message):
    sender_id = message.from_user.id
    session_name = f'user_{client.me.id}'
    user_dir = f"{ggg}/{session_name}"
    try:
        if not sender_id == OWNER_ID:
           return await message.reply_text("Only bot owner is allowed to perform this command")

        replied_msg = message.reply_to_message
        if not replied_msg:
            usage_text = (
                "Please reply to a message to set it as welcome message.\n\n"
                "You can set:\n"
                "• Text message\n"
                "• Media (photo/video/gif/sticker)\n"
                "• Media with caption\n\n"
                "Available placeholders:\n"
                "• {name} - User's name\n"
                "• {id} - User's ID\n"
                "• {botname} - Bot's username\n\n"
                "Size limits:\n"
                "• Text: Maximum 4096 characters\n"
                "• Media: Maximum 5MB\n\n"
                "Example usage:\n"
                "• 'Welcome {name}! Your ID is {id}'\n"
                "• Reply to a photo/video with caption 'Welcome to {botname}!'"
            )
            return await message.reply_text(usage_text)

        updates = []

        # Handle text if present
        if replied_msg.text or replied_msg.caption:
            welcome_text = (replied_msg.text or replied_msg.caption).strip()
            if len(welcome_text) > 4096:
                return await message.reply_text("Welcome message too long. Maximum 4096 characters allowed.")

            entities = sorted(
                (replied_msg.entities or replied_msg.caption_entities or []),
                key=lambda x: (x.offset, -x.length)
            )

            ENTITY_TO_HTML = {
                MessageEntityType.BOLD: ('b', 'b'),
                MessageEntityType.ITALIC: ('i', 'i'),
                MessageEntityType.UNDERLINE: ('u', 'u'),
                MessageEntityType.STRIKETHROUGH: ('s', 's'),
                MessageEntityType.SPOILER: ('spoiler', 'spoiler'),
                MessageEntityType.CODE: ('code', 'code'),
                MessageEntityType.PRE: ('pre', 'pre'),
                MessageEntityType.BLOCKQUOTE: ('blockquote', 'blockquote')
            }

            def convert_to_html(text, msg_entities):
                tag_positions = []

                for entity in msg_entities:
                    if entity.type in ENTITY_TO_HTML:
                        start_tag, end_tag = ENTITY_TO_HTML[entity.type]

                        if entity.type == MessageEntityType.PRE and getattr(entity, 'language', None):
                            tag_positions.append((entity.offset, f'<pre language="{entity.language}">', True))
                        else:
                            tag_positions.append((entity.offset, f'<{start_tag}>', True))

                        tag_positions.append((entity.offset + entity.length, f'</{end_tag}>', False))

                tag_positions.sort(key=lambda x: (x[0], x[2]))

                result = []
                current_pos = 0

                for pos, tag, _ in tag_positions:
                    if pos > current_pos:
                        result.append(text[current_pos:pos])
                    result.append(tag)
                    current_pos = pos

                if current_pos < len(text):
                    result.append(text[current_pos:])

                return ''.join(result)

            processed_text = convert_to_html(welcome_text, entities)

            # Validate placeholders
            ALLOWED_PLACEHOLDERS = {"{name}", "{id}", "{botname}"}
            placeholder_regex = r'\{([^{}]+)\}'
            found_placeholders = set(re.findall(placeholder_regex, processed_text))

            invalid_placeholders = [f"{{{p}}}" for p in found_placeholders
                                  if f"{{{p}}}" not in ALLOWED_PLACEHOLDERS]

            if invalid_placeholders:
                error_msg = "❌ Invalid placeholders found:\n"
                error_msg += "\n".join(f"• {p}" for p in invalid_placeholders)
                error_msg += "\n\nAllowed placeholders:\n"
                error_msg += "\n".join(f"• {p}" for p in sorted(ALLOWED_PLACEHOLDERS))
                error_msg += "\n\nExample usage:\n"
                error_msg += "• Welcome {name}!\n"
                error_msg += "• Your ID: {id}\n"
                error_msg += "• Welcome to {botname}!"
                return await message.reply_text(error_msg)

            set_gvar(client.me.id, "WELCOME", processed_text)
            updates.append("welcome message")

        # Handle media if present
        if replied_msg.media:
            m_d = None
            try:
                # Check if media type is allowed
                if not (replied_msg.photo or replied_msg.video or
                       replied_msg.sticker or replied_msg.animation):
                    return await message.reply_text("Only photos, videos, GIFs, and stickers are allowed.")

                # Check file size (5MB = 5 * 1024 * 1024 bytes)
                file_size = getattr(replied_msg, 'file_size', 0)
                if file_size > 5242880:  # 5MB in bytes
                    return await message.reply_text("Media size cannot exceed 5MB.")

                # First try to save to user_dir
                logo_path_jpg = f"{user_dir}/logo.jpg"
                logo_path_mp4 = f"{user_dir}/logo.mp4"

                # Process media based on type
                if replied_msg.sticker:
                    m_d = await convert_to_image(replied_msg)
                else:
                    m_d = await replied_msg.download()

                if m_d:
                    # Save to appropriate path based on media type
                    if replied_msg.video:
                        target_path = logo_path_mp4
                    else:
                        target_path = logo_path_jpg

                    os.rename(m_d, target_path)
                    updates.append(f"logo (saved to {target_path})")

            except Exception as e:
                if m_d and os.path.exists(m_d):
                    os.remove(m_d)
                return await message.reply_text(f"Error processing media: {str(e)}")

        if not updates:
            return await message.reply_text("Nothing to update. Message must contain text and/or media.")

        # Send confirmation and preview
        success_msg = f"✅ Updated {' and '.join(updates)}!"
        await client.send_message(message.chat.id, success_msg + "\n\nPreview:")

        # Show preview
        try:
            # First check user_dir for existing logos
            logo_path_jpg = f"{user_dir}/logo.jpg"
            logo_path_mp4 = f"{user_dir}/logo.mp4"
            logo = None

            if os.path.exists(logo_path_mp4):
                logo = logo_path_mp4
            elif os.path.exists(logo_path_jpg):
                logo = logo_path_jpg
            else:
                # Fallback to old methods
                logo = await gvarstatus(sender_id, "LOGO")
                if not logo and client.me.photo:
                    photos = await client.get_profile_photos("me")
                    if photos:
                        logo = await client.download_media(photos[0].file_id, logo_path_jpg)
                if not logo:
                    logo = "music.jpg"

            alive_logo = logo
            if isinstance(logo, bytes):
                alive_logo = logo_path_jpg
                with open(alive_logo, "wb") as fimage:
                    fimage.write(base64.b64decode(logo))
                if 'video' in mime.from_file(alive_logo):
                    alive_logo = rename_file(alive_logo, logo_path_mp4)

            welcome_text = await gvarstatus(sender_id, "WELCOME") or f"""
🌟 𝖂𝖊𝖑𝖈𝖔𝖒𝖊, {name}! 🌟

🎶 Your **musical journey** begins with {botname}!

✨ Enjoy _crystal-clear_ audio and a vast library of sounds.

🚀 Get ready for an *unparalleled* musical adventure!
"""
            if alive_logo.endswith(".mp4"):
                await client.send_video(
                    message.chat.id,
                    alive_logo,
                    caption=welcome_text,
                )
            else:
                await client.send_photo(
                    message.chat.id,
                    alive_logo,
                    caption=welcome_text,
                )

        except Exception as e:
            logger.info(f"Error showing preview: {str(e)}")
            welcome_text = await gvarstatus(sender_id, "WELCOME")
            if welcome_text:
                await client.send_message(
                    message.chat.id,
                    welcome_text,
                )
    except Exception as e:
        error_msg = f"❌ Error: `{str(e)}`"
        logger.info(f"Error for user {message.from_user.id}: {str(e)}")
        return await message.reply_text(error_msg)

@Client.on_message(filters.command(["resetwelcome", "rwelcome"]))
async def resetwelcome(client: Client, message: Message):
    sender_id = message.from_user.id
    if not sender_id == OWNER_ID:
        return await message.reply_text("Only bot owner is allowed to perform this command")

    set_gvar(client.me.id, "WELCOME", None)
    set_gvar(client.me.id, "LOGO", None)
    await message.reply_text("Welcome message and logo have been reset.")
