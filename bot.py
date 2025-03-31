import os
import logging
import asyncio
import threading
import time
import re
import requests
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
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
OWNER_ID = int(os.getenv("OWNER_ID", "6860316927"))
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "https://envs.sh/n9o.jpg")
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "20"))

# ✅ Force Subscribe Setup
id_pattern = re.compile(r'^.\d+$')
AUTH_CHANNEL = [int(ch) if id_pattern.search(ch) else ch for ch in os.getenv("AUTH_CHANNEL", "-1002490575006").split()]

# ✅ Token & Shortener API
SHORTENER_API_URL = os.getenv("SHORTENER_API_URL", "https://instantearn.in")
SHORTENER_API_KEY = os.getenv("SHORTENER_API_KEY", "e753b45153becd850d3142dbdfce442891a7b1d0")

# ✅ Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]
users_collection = db["users"]
settings_collection = db["settings"]

# ✅ Free Video Limit
FREE_VIDEO_LIMIT = 5

# ✅ **MongoDB Caching**
video_cache = []
last_cache_time = 0
CACHE_EXPIRY = 300  # Refresh cache every 5 minutes

async def refresh_video_cache():
    global video_cache, last_cache_time
    if time.time() - last_cache_time > CACHE_EXPIRY:
        video_cache = list(collection.aggregate([{"$sample": {"size": 500}}]))
        last_cache_time = time.time()

# ✅ **Check Subscription Type**
def get_user_subscription(user_id):
    user = users_collection.find_one({"user_id": user_id})
    return user["subscription"] if user else "free"

def reduce_free_videos(user_id):
    user = users_collection.find_one({"user_id": user_id})
    if user and "free_videos" in user and user["free_videos"] > 0:
        users_collection.update_one({"user_id": user_id}, {"$inc": {"free_videos": -1}})
        return user["free_videos"] - 1
    return 0

def set_free_videos(user_id):
    users_collection.update_one({"user_id": user_id}, {"$setOnInsert": {"free_videos": FREE_VIDEO_LIMIT}}, upsert=True)

# ✅ **Shortener API Verification**
def verify_token(user_id):
    user = users_collection.find_one({"user_id": user_id})
    if user and "verified" in user and user["verified"]:
        return True

    response = requests.get(f"{SHORTENER_API_URL}/verify?api_key={SHORTENER_API_KEY}&user_id={user_id}")
    if response.status_code == 200 and response.json().get("status") == "success":
        users_collection.update_one({"user_id": user_id}, {"$set": {"verified": True}}, upsert=True)
        return True
    return False

# ✅ **Force Subscribe Check**
async def is_subscribed(bot, query, channel):
    btn = []
    for id in channel:
        try:
            chat = await bot.get_chat(int(id))
            await bot.get_chat_member(id, query.from_user.id)
        except UserNotParticipant:
            btn.append([InlineKeyboardButton(f'Join {chat.title}', url=chat.invite_link)])
        except Exception:
            pass
    return btn

# 🔰 **Fetch & Send Random Video**
async def send_random_video(client, chat_id, user_id):
    await refresh_video_cache()

    if not video_cache:
        await client.send_message(chat_id, "⚠ No videos available. Use /index first!")
        return

    user_sub = get_user_subscription(user_id)
    
    if user_sub == "free":
        remaining_videos = reduce_free_videos(user_id)
        if remaining_videos < 0:
            await client.send_message(chat_id, "🚫 You've used all your free videos! Verify via shortener to continue.")
            return
    elif user_sub == "verified" and not verify_token(user_id):
        await client.send_message(chat_id, "⚠ Your verification expired! Please verify again via the shortener.")
        return

    video = video_cache.pop()
    try:
        message = await client.get_messages(CHANNEL_ID, video["message_id"])
        if message and message.video:
            sent_msg = await client.send_video(
                chat_id, 
                video=message.video.file_id, 
                caption="Thanks 😊"
            )

            if AUTO_DELETE_TIME > 0:
                await asyncio.sleep(AUTO_DELETE_TIME)
                await sent_msg.delete()

    except FloodWait as e:
        await asyncio.sleep(e.value)
        await send_random_video(client, chat_id, user_id)
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")

# ✅ **Callback for Getting Random Video**
@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    try:
        await callback_query.answer()
        asyncio.create_task(send_random_video(client, callback_query.message.chat.id, callback_query.from_user.id))
    except QueryIdInvalid:
        logger.warning("Ignoring invalid query ID error.")
    except Exception as e:
        logger.error(f"Error in callback: {e}")

# ✅ **Start Command**
@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    set_free_videos(user_id)

    if AUTH_CHANNEL:
        try:
            btn = await is_subscribed(client, message, AUTH_CHANNEL)
            if btn:
                username = (await client.get_me()).username
                btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start=true")])
                await message.reply_text("👋 Hello! Please join the channel then click Try Again.", reply_markup=InlineKeyboardMarkup(btn))
                return
        except Exception as e:
            logger.error(e)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 Get Random Video", callback_data="get_random_video")],
        [InlineKeyboardButton("✅ Verify & Get More Videos", callback_data="verify_tutorial")]
    ])
    await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome! Enjoy free videos.", reply_markup=keyboard)

# ✅ **Verify Tutorial**
@bot.on_callback_query(filters.regex("verify_tutorial"))
async def verify_tutorial(client, callback_query: CallbackQuery):
    short_url = f"{SHORTENER_API_URL}/get?api_key={SHORTENER_API_KEY}&user_id={callback_query.from_user.id}"
    await callback_query.message.reply_text(f"📌 **Verification Steps:**\n\n1️⃣ Click the link below.\n2️⃣ Complete the verification.\n3️⃣ Enjoy more videos!\n\n🔗 [Verify Now]({short_url})", disable_web_page_preview=True)

# ✅ **Run the Bot**
if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    bot.run()
