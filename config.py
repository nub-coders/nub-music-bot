import random
import string
import os
from os import getenv
import time
import pymongo
from telethon import TelegramClient, events, Button
from pyrogram import Client, filters
from thumbnails import *
from fonts import *

# Use getenv for all sensitive/configurable values
API_ID = os.getenv("API_ID","2040")
API_HASH = os.getenv("API_HASH", "b18441a1ff607e10a989891a5462e627")
STRING_SESSION = os.getenv("STRING_SESSION", "")
GROUP = os.getenv("GROUP", "nub_coder_s")
CHANNEL = os.getenv("CHANNEL", "nub_coders")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", 6076474757))
LOGGER_ID = os.getenv("LOGGER_ID", None)
mongodb = os.getenv("MONGODB_URI", "mongodb+srv://nubcoders:nubcoders@music.8rxlsum.mongodb.net/?retryWrites=true&w=majority&appName=music")
# Working directory
ggg = os.getcwd()

# Initialize data structures
# Track start time
StartTime = time.time()

# Set up MongoDB connection
mongo_client = pymongo.MongoClient(mongodb)
db = mongo_client['voice']
user_sessions = db['user_sessions']
collection = db["users"]
