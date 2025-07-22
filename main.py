import asyncio
from pyrogram import idle
import os
import logging
# Third-party libraries
from pytgcalls import filters as call_filters
from pytgcalls import PyTgCalls
from pytgcalls.types import ChatUpdate
from pyrogram import Client
from pyrogram.errors.exceptions import SessionRevoked, UserDeactivatedBan, AuthKeyInvalid, \
    AuthKeyUnregistered, AuthTokenExpired, AuthKeyDuplicated, AccessTokenExpired, UserDeactivated
# Local modules
from tools import *
from config import *

# Initialize clients dictionary
# Configure logging
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
# Cache directory setup
cache_dir = f"{ggg}/cache"
os.makedirs(cache_dir, exist_ok=True)
# This should be wrapped in an async function
# Global clients dictionary

async def main():
    logger.info("Starting bot initialization...")
    # Create and start the bot client
    try:
        bot = Client("bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins"),
            in_memory=True,
            sleep_threshold=32,
        )
        
        # Initialize and store session client
        session = Client("session",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=STRING_SESSION,
            in_memory=True,
            #no_updates=True,
            sleep_threshold=32
        )
        
        call_py = PyTgCalls(session)
        call_py.add_handler(end, call_filters.stream_end())
        call_py.add_handler(hd_stream_closed_kicked,
            call_filters.chat_update(ChatUpdate.Status.CLOSED_VOICE_CHAT) | 
            call_filters.chat_update(ChatUpdate.Status.KICKED)
        )
        
        
        clients["session"] = session
        clients["call_py"] = call_py
        clients["bot"] = bot
        user_data = user_sessions.find_one({"bot_id": client.me.id})
        SUDO = users_data.get("SUDOERS", [])
        AUTH = user_data.get('auth_users', {})
        BLOCK = user_data.get('busers', {})
        await call_py.start()
        await bot.start()
        client_name = f"{bot.me.first_name} {bot.me.last_name or ''}".strip()
        logger.info(f"Bot authorized successfully! 🎉 Authorized as: {client_name}")
        user_sessions.update_one(
    {"bot_id": bot.me.id},                 # search filter
    {"$setOnInsert": {"bot_id": bot.me.id}},  # insert this only if not found
    upsert=True
)
    except Exception as e:
        logger.error(f"Failed to initialize bot client: {str(e)}")
        raise
    logger.info("Bot initialization completed successfully")
    await idle()
# Run the main function
asyncio.run(main())
