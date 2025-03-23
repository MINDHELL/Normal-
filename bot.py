import os
import logging
import random
import asyncio
import threading
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from pyrogram.errors import UserNotParticipant, FloodWait, RPCError
from health_check import start_health_check

# 🔰 Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 🔰 Environment Variables
API_ID = int(os.getenv("API_ID", "27788368"))
API_HASH = os.getenv("API_HASH", "9df7e9ef3d7e4145270045e5e43e1081")
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL", "YOUR_MONGO_URL")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002465297334"))
OWNER_ID = int(os.getenv("OWNER_ID", "27788368"))
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "https://envs.sh/n9o.jpg")
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "20"))

# 🔰 AUTH_CHANNEL Parsing
id_pattern = re.compile(r'^.\d+$')
AUTH_CHANNEL = [int(ch) if id_pattern.search(ch) else ch for ch in os.getenv("AUTH_CHANNEL", "-1002490575006").split()]

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]

# 🔰 Prefetch Video Cache
video_cache = asyncio.Queue()

async def prefetch_videos():
    """Fetch random videos in the background to reduce delay."""
    while True:
        try:
            video_docs = list(collection.aggregate([{ "$sample": { "size": 5 } }]))  # Fetch 5 random videos
            for video in video_docs:
                await video_cache.put(video)
            logger.info("✅ Video cache updated.")
            await asyncio.sleep(10)  # Refresh cache every 10 seconds
        except Exception as e:
            logger.error(f"⚠ Prefetch error: {e}", exc_info=True)
            await asyncio.sleep(30)  # Retry after delay

async def send_random_video(client, chat_id):
    """Send a random video instantly from cache."""
    try:
        if video_cache.empty():
            await prefetch_videos()  # Fetch if cache is empty

        random_video = await video_cache.get()
        message = await client.get_messages(CHANNEL_ID, random_video["message_id"])

        if message and message.video:
            sent_msg = await client.send_video(
                chat_id=chat_id,
                video=message.video.file_id,
                caption="🎥 Enjoy your video!\n\nThanks 😊"
            )
            logger.info(f"✅ Sent video to {chat_id}.")
            asyncio.create_task(delete_after(sent_msg))
        else:
            await client.send_message(chat_id, "⚠ Video not found. Please try again.")
            logger.warning(f"⚠ Video not found for user {chat_id}.")
    except FloodWait as e:
        logger.warning(f"⚠ FloodWait detected: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
        await send_random_video(client, chat_id)  # Retry after delay
    except Exception as e:
        logger.error(f"⚠ Error sending video: {e}", exc_info=True)
        await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")

async def delete_after(message):
    """Auto-delete message after specified time."""
    try:
        await asyncio.sleep(AUTO_DELETE_TIME)
        await message.delete()
        logger.info(f"🗑 Deleted message {message.message_id}.")
    except Exception as e:
        logger.error(f"⚠ Error deleting message: {e}", exc_info=True)

async def is_subscribed(bot, query, channel):
    """Check if the user is subscribed to all required channels."""
    btn = []
    for id in channel:
        try:
            chat = await bot.get_chat(int(id))
            await bot.get_chat_member(id, query.from_user.id)  # Check membership
        except UserNotParticipant:
            btn.append([InlineKeyboardButton(f'Join {chat.title}', url=chat.invite_link)])
        except Exception as e:
            logger.error(f"⚠ Subscription check error: {e}", exc_info=True)
    return btn

@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    """Handles the button click instantly without delay."""
    try:
        btn = await is_subscribed(client, callback_query, AUTH_CHANNEL)
        if btn:
            btn.append([InlineKeyboardButton("♻️ Try Again ♻️", callback_data="get_random_video")])
            await callback_query.message.reply_text(
                "<b>👋 Please join all required channels first, then click Try Again.</b>",
                reply_markup=InlineKeyboardMarkup(btn)
            )
            return

        await callback_query.answer("⏳ Fetching video...", show_alert=False)
        asyncio.create_task(send_random_video(client, callback_query.message.chat.id))
    except RPCError as e:
        logger.error(f"⚠ Telegram API Error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"⚠ Callback error: {e}", exc_info=True)

@bot.on_message(filters.command("start"))
async def start(client, message):
    """Handles /start command."""
    try:
        user_id = message.from_user.id
        btn = await is_subscribed(client, message, AUTH_CHANNEL)

        if btn:
            username = (await client.get_me()).username
            if len(message.command) > 1:
                btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start={message.command[1]}")])
            else:
                btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start=true")])

            await message.reply_text(
                f"<b>👋 Hello {message.from_user.mention},\n\nPlease join all required channels, then click Try Again. 😇</b>",
                reply_markup=InlineKeyboardMarkup(btn)
            )
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 Get Random Video", callback_data="get_random_video")],
        ])
        await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome to the Video Bot!", reply_markup=keyboard)
        logger.info(f"✅ User {user_id} started the bot.")
    except Exception as e:
        logger.error(f"⚠ Start command error: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        # Start background video prefetching inside the event loop
        loop = asyncio.get_event_loop()
        loop.create_task(prefetch_videos())

        # Start health check service in a separate thread
        threading.Thread(target=start_health_check, daemon=True).start()

        # Run the bot
        bot.run()
    except Exception as e:
        logger.critical(f"❌ Bot startup failed: {e}", exc_info=True)
