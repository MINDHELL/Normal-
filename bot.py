import os
import logging
import random
import threading
import asyncio
import time
import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from pyrogram.errors import UserNotParticipant, FloodWait, MessageIdInvalid

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
VIDEO_LIMIT = "10"  # 🔰 Videos per user per 6 hours
SPAM_TIMEOUT = "3"  # 🔰 Prevent spam (3 seconds delay)

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]
users_db = db["users"]

# 🔰 Spam Control
user_last_action = {}

# 🔰 Function to check subscription
async def is_subscribed(client, user_id):
    for channel in AUTH_CHANNEL:
        try:
            await client.get_chat_member(channel, user_id)
        except UserNotParticipant:
            chat = await client.get_chat(channel)
            return False, chat.invite_link
    return True, None

# 🔰 User Quota System
async def get_user_quota(user_id):
    user = users_db.find_one({"user_id": user_id})
    current_time = time.time()

    if user:
        last_reset = user["last_reset"]
        if current_time - last_reset >= 21600:  # 🔰 6 hours
            users_db.update_one({"user_id": user_id}, {"$set": {"quota": VIDEO_LIMIT, "last_reset": current_time}})
            return VIDEO_LIMIT
        return user["quota"]
    else:
        users_db.insert_one({"user_id": user_id, "quota": VIDEO_LIMIT, "last_reset": current_time})
        return VIDEO_LIMIT

async def update_user_quota(user_id):
    users_db.update_one({"user_id": user_id}, {"$inc": {"quota": -1}})

# 🔰 Send Random Video
async def send_random_video(client, chat_id, user_id):
    global user_last_action

    # 🔰 Spam Protection
    current_time = time.time()
    if user_id in user_last_action and current_time - user_last_action[user_id] < SPAM_TIMEOUT:
        await client.send_message(chat_id, "⚠ Please wait before requesting again!")
        return
    user_last_action[user_id] = current_time  # Update last action time

    # 🔰 Quota Check
    if user_id != OWNER_ID:
        quota_left = await get_user_quota(user_id)
        if int(quota_left) <= 0:
            await client.send_message(chat_id, "⚠ Your video limit is exhausted! Reset in 6 hours.")
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

            if user_id != OWNER_ID:
                await update_user_quota(user_id)

            # 🔰 Auto-delete
            await asyncio.sleep(AUTO_DELETE_TIME)
            await sent_msg.delete()
        else:
            await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")
    except FloodWait as e:
        logger.warning(f"FloodWait: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
        await send_random_video(client, chat_id, user_id)
    except MessageIdInvalid:
        await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")

# 🔰 Index Videos
@bot.on_message(filters.command("index") & filters.user(OWNER_ID))
async def index_videos(client, message):
    all_messages = []
    async for msg in client.get_chat_history(CHANNEL_ID, limit=500):
        if msg.video:
            all_messages.append({"message_id": msg.message_id})

    if all_messages:
        collection.insert_many(all_messages, ordered=False)
        await message.reply_text(f"✅ Indexed {len(all_messages)} videos successfully!")
    else:
        await message.reply_text("⚠ No videos found in the channel.")

# 🔰 /start Command
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
        [InlineKeyboardButton("📊 My Plan", callback_data=f"myplan_{user_id}")],
    ])
    await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome to the Video Bot!", reply_markup=keyboard)

# 🔰 /myplan Command
@bot.on_callback_query(filters.regex(r"myplan_(\d+)"))
async def myplan_callback(client, callback_query: CallbackQuery):
    user_id = int(callback_query.matches[0].group(1))

    if user_id == OWNER_ID:
        await callback_query.message.edit_text("🛠 Owner Mode: Unlimited Quota 🚀")
        return

    user = users_db.find_one({"user_id": user_id})
    if not user:
        quota_left = VIDEO_LIMIT
        reset_time = "6 hours from now"
    else:
        quota_left = user["quota"]
        reset_time = datetime.datetime.utcfromtimestamp(user["last_reset"] + 21600).strftime("%Y-%m-%d %H:%M:%S UTC")

    await callback_query.message.edit_text(
        f"📊 **Your Plan:**\n"
        f"🎥 Videos Left: `{quota_left}`\n"
        f"🔄 Reset Time: `{reset_time}`\n"
        "Upgrade to premium for more access!"
    )

# 🔰 /get_random_video Callback
@bot.on_callback_query(filters.regex(r"get_random_video_(\d+)"))
async def random_video_callback(client, callback_query: CallbackQuery):
    user_id = int(callback_query.matches[0].group(1))
    await send_random_video(client, callback_query.message.chat.id, user_id)
    await callback_query.answer()

# 🔰 Run the Bot
if __name__ == "__main__":
    bot.run()
