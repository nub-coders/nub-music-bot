"""
Async MongoDB database handler for nub-music-bot
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGODB_URI", "mongodb+srv://nubcoders:nubcoders@music.8rxlsum.mongodb.net/?retryWrites=true&w=majority&appName=music")
DB_NAME = os.getenv("DB_NAME", "musicbot")

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

# Collections
user_sessions = db["user_sessions"]
collection = db["collection"]

async def update_one(collection, filter, update, upsert=False):
    return await collection.update_one(filter, update, upsert=upsert)

async def find_one(collection, filter):
    return await collection.find_one(filter)

async def push_to_array(collection, filter, field, value, upsert=False):
    return await collection.update_one(filter, {"$push": {field: value}}, upsert=upsert)

async def pull_from_array(collection, filter, field, value, upsert=False):
    return await collection.update_one(filter, {"$pull": {field: value}}, upsert=upsert)

async def set_fields(collection, filter, fields, upsert=False):
    return await collection.update_one(filter, {"$set": fields}, upsert=upsert)

# Add more helpers as needed
