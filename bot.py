
import os
import logging
import random
import threading
import asyncio
import time
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
BOT_TOKEN = os.getenv("BOT_TOKEN", "7692429836:AAHyUFP6oA3Hirisl5TV1O5kArGAlAEuQ")
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://aarshhub:6L1PAPikOnAIHIRA@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002465297334"))
OWNER_ID = int(os.getenv("OWNER_ID", "6860316927"))
AUTH_CHANNEL = [int(ch) for ch in os.getenv("AUTH_CHANNEL", "-1002490575006").split()]  # 🔰 FSub Channels
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "https://envs.sh/n9o.jpg")  # 🔰 Welcome Image URL
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "20"))  # 🔰 Auto-delete time in seconds
VIDEO_LIMIT = "10"  # 🔰 Maximum videos per user in 6 hours
SPAM_TIMEOUT = "60"  # 🔰 Mute spam users for 1 minute

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]
users_db = db["users"]

# 🔰 Function to check if user is subscribed
async def is_subscribed(client, user_id):
    for channel in AUTH_CHANNEL:
        try:
            await client.get_chat_member(channel, user_id)
        except UserNotParticipant:
            chat = await client.get_chat(channel)
            return False, chat.invite_link
    return True, None

# 🔰 Anti-Spam System
user_requests = {}

async def check_spam(user_id):
    now = time.time()
    if user_id in user_requests:
        last_request, count = user_requests[user_id]
        if now - last_request < 5:  # 🔰 5 seconds between requests
            count += 1
            if count >= 5:  # 🔰 More than 5 requests in short time
                user_requests[user_id] = (now, count)
                return True  # 🔰 User is spamming
        else:
            count = 1  # 🔰 Reset count if enough time has passed
        user_requests[user_id] = (now, count)
    else:
        user_requests[user_id] = (now, 1)
    return False

# 🔰 User Quota System (6-Hour Limit)
async def check_quota(user_id):
    user_data = users_db.find_one({"user_id": user_id})
    current_time = time.time()
    
    if user_data:
        last_reset = user_data["last_reset"]
        if current_time - last_reset >= 21600:  # 🔰 6 hours (21600 seconds)
            users_db.update_one({"user_id": user_id}, {"$set": {"quota": VIDEO_LIMIT, "last_reset": current_time}})
            return VIDEO_LIMIT
        return user_data["quota"]
    else:
        users_db.insert_one({"user_id": user_id, "quota": VIDEO_LIMIT, "last_reset": current_time})
        return VIDEO_LIMIT

async def update_quota(user_id):
    users_db.update_one({"user_id": user_id}, {"$inc": {"quota": -1}})

# 🔰 Send Random Video Function
async def send_random_video(client, chat_id, user_id):
    if await check_spam(user_id):
        await client.send_message(chat_id, "🚫 You're sending too many requests! Muted for 1 minute.")
        await bot.restrict_chat_member(chat_id, user_id, until_date=int(time.time()) + SPAM_TIMEOUT)
        return

    quota_left = await check_quota(user_id)
    if quota_left <= 0:
        await client.send_message(chat_id, "⚠ Your video limit is exhausted! Try again later.")
        return

    video_docs = list(collection.find())
    if not video_docs:
        await client.send_message(chat_id, "⚠ No videos available. Use /index first!")
        return

    random_video = random.choice(video_docs)
    try:
        message = await client.get_messages(CHANNEL_ID, random_video["message_id"])
        if message and message.video:
            sent_msg = await client.send_video(
                chat_id=chat_id,
                video=message.video.file_id,
                caption="Thanks 😊"
            )
            await update_quota(user_id)

            # 🔰 Auto-delete feature
            await asyncio.sleep(AUTO_DELETE_TIME)
            await sent_msg.delete()
        else:
            await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")
    except FloodWait as e:
        logger.warning(f"FloodWait triggered: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
        await send_random_video(client, chat_id, user_id)
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")

# 🔰 Start Command
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
        [InlineKeyboardButton("🎥 Get Random Video", callback_data=f"get_random_video_{user_id}")],
    ])
    await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome to the Video Bot!", reply_markup=keyboard)

# 🔰 Callback for Getting Random Video
@bot.on_callback_query(filters.regex(r"get_random_video_(\d+)"))
async def random_video_callback(client, callback_query: CallbackQuery):
    user_id = int(callback_query.matches[0].group(1))
    await send_random_video(client, callback_query.message.chat.id, user_id)
    await callback_query.answer()

# 🔰 Run the Bot
if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    bot.run()
