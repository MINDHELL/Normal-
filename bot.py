import os
import logging
import asyncio
import threading
import time
import re
import random
from functools import lru_cache
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from redis import Redis  # Redis for caching (optional)
from pyrogram.errors import UserNotParticipant, FloodWait, QueryIdInvalid
from health_check import start_health_check

# 🔰 Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔰 Environment Variables
API_ID = int(os.getenv("API_ID", "27788368"))
API_HASH = os.getenv("API_HASH", "9df7e9ef3d7e4145270045e5e43e1081")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7692429836:AAHyUFP6os1A3Hirisl5TV1O5kArGAlAEuQ")
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://aarshhub:6L1PAPikOnAIHIRA@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002465297334"))
OWNER_ID = int(os.getenv("OWNER_ID", "YOUR_OWNER_ID"))
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "https://envs.sh/n9o.jpg")
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "20"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")  # Redis connection (optional)

# ✅ Initialize Redis Cache
try:
    redis_cache = Redis.from_url(REDIS_URL, decode_responses=True)
    redis_cache.ping()  # Test Redis connection
    logger.info("✅ Redis Cache Connected!")
except Exception:
    redis_cache = None
    logger.warning("⚠ Redis not found! Using local caching.")

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]

# ✅ **Cache Function to Store Random Videos**
def cache_random_videos():
    videos = list(collection.aggregate([{"$sample": {"size": 10}}]))
    video_ids = [video["message_id"] for video in videos]

    if redis_cache:
        redis_cache.setex("cached_videos", 300, ",".join(map(str, video_ids)))  # Cache for 5 mins
    return video_ids

# ✅ **Fetch Cached Videos or Refresh Cache**
def get_cached_videos():
    if redis_cache:
        cached_data = redis_cache.get("cached_videos")
        if cached_data:
            return list(map(int, cached_data.split(",")))

    return cache_random_videos()  # Refresh cache if no data found

# 🔰 **Fetch & Send Random Video**
async def send_random_video(client, chat_id):
    video_ids = get_cached_videos()
    if not video_ids:
        await client.send_message(chat_id, "⚠ No videos available. Try again later.")
        return

    video_id = random.choice(video_ids)  # Pick a random video
    try:
        message = await client.get_messages(CHANNEL_ID, video_id)
        if message and message.video:
            sent_msg = await client.send_video(chat_id, video=message.video.file_id, caption="Thanks 😊")

            if AUTO_DELETE_TIME > 0:
                await asyncio.sleep(AUTO_DELETE_TIME)
                await sent_msg.delete()

    except FloodWait as e:
        logger.warning(f"FloodWait detected: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
        await send_random_video(client, chat_id)
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")

# 🔰 **Callback for Getting Random Video**
@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    await callback_query.answer()
    await send_random_video(client, callback_query.message.chat.id)

# 🔰 **Start Command (Welcome)**
@bot.on_message(filters.command("start"))
async def start(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 Get Random Video", callback_data="get_random_video")],
    ])
    await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome to the Video Bot!", reply_markup=keyboard)

# 🔰 **Index Videos (Owner Only)**
@bot.on_message(filters.command("index") & filters.user(OWNER_ID))
async def index_videos(client, message):
    await message.reply_text("🔄 Indexing videos... Please wait.")

    video_entries = [{"message_id": msg.id} for msg in await client.get_chat_history(CHANNEL_ID, limit=500) if msg.video]

    if video_entries:
        collection.insert_many(video_entries, ordered=False)
        cache_random_videos()  # Refresh cache after indexing

    await message.reply_text(f"✅ Indexed {len(video_entries)} new videos!")

# 🔰 **Check Total Indexed Files**
@bot.on_message(filters.command("files") & filters.user(OWNER_ID))
async def check_files(client, message):
    total_videos = collection.count_documents({})
    await message.reply_text(f"📂 Total Indexed Videos: {total_videos}")

# 🔰 **Run the Bot**
if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    bot.run()

