import os
import logging
import random
import asyncio
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from pyrogram.errors import UserNotParticipant, FloodWait
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
OWNER_ID = int(os.getenv("OWNER_ID", "6860316927"))
AUTH_CHANNEL = [int(ch) for ch in os.getenv("AUTH_CHANNEL", "-1002490575006").split()]
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "https://envs.sh/n9o.jpg")
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "20"))

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]

# 🔰 Prefetch Cache
video_cache = asyncio.Queue()

async def prefetch_videos():
    """Fetch random videos in the background to reduce delay."""
    while True:
        try:
            video_docs = list(collection.aggregate([{ "$sample": { "size": 5 } }]))  # Fetch 5 videos
            for video in video_docs:
                await video_cache.put(video)
        except Exception as e:
            logger.error(f"Prefetch error: {e}")
        await asyncio.sleep(10)  # Refresh cache every 10 seconds

async def send_random_video(client, chat_id):
    """Send a random video instantly with zero delay."""
    if video_cache.empty():
        await prefetch_videos()  # Fetch if cache is empty

    try:
        random_video = await video_cache.get()  # Get video from cache
        message = await client.get_messages(CHANNEL_ID, random_video["message_id"])
        if message and message.video:
            sent_msg = await client.send_video(
                chat_id=chat_id,
                video=message.video.file_id,
                caption="Thanks 😊"
            )
            asyncio.create_task(delete_after(sent_msg))  # Auto-delete in the background
    except FloodWait as e:
        logger.warning(f"FloodWait detected: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
        await send_random_video(client, chat_id)  # Retry after delay
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")

async def delete_after(message):
    """Auto-delete message after specified time."""
    await asyncio.sleep(AUTO_DELETE_TIME)
    await message.delete()

@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    """Handles the button click instantly without delay."""
    await callback_query.answer()
    asyncio.create_task(send_random_video(client, callback_query.message.chat.id))

@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    is_sub, invite_link = await is_subscribed(client, user_id)

    if not is_sub:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Join & Try Again", url=invite_link)]])
        await message.reply_text(
            f"👋 Hello {message.from_user.mention},\n\n"
            "You need to join our channel to use this bot! Click below 👇",
            reply_markup=keyboard
        )
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 Get Random Video", callback_data="get_random_video")],
    ])
    await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome to the Video Bot!", reply_markup=keyboard)

if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    asyncio.create_task(prefetch_videos())  # Start background prefetching
    bot.run()
