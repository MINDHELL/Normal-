import os
import logging
import asyncio
import threading
import time
import re
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

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]

# ✅ Rate Limiting Setup
user_last_request = {}  
video_request_semaphore = asyncio.Semaphore(900)  # Allow 2 concurrent requests

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

# ✅ **Fetch & Send Random Video (Optimized)**
async def send_random_video(client, chat_id):
    async with video_request_semaphore:  
        video_list = list(collection.aggregate([{"$sample": {"size": 10}}]))

        if not video_list:
            await client.send_message(chat_id, "⚠ No videos available. Use /index first!")
            return

        video = video_list[0]
        try:
            message = await client.get_messages(CHANNEL_ID, video["message_id"])
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

# ✅ **Callback for Getting Random Video (Rate Limited)**
@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    current_time = time.time()

    # User cooldown (1 second per request)
    if user_id in user_last_request and current_time - user_last_request[user_id] < 1:
        await callback_query.answer("❌ Please wait before requesting another video!", show_alert=True)
        return

    # Update last request time
    user_last_request[user_id] = current_time

    try:
        await callback_query.answer()
        await send_random_video(client, callback_query.message.chat.id)
    except QueryIdInvalid:
        logger.warning("Ignoring invalid query ID error.")
    except Exception as e:
        logger.error(f"Error in callback: {e}")

# ✅ **Start Command (Welcome & FSub Check)**
@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id

    if AUTH_CHANNEL:
        try:
            btn = await is_subscribed(client, message, AUTH_CHANNEL)
            if btn:
                username = (await client.get_me()).username
                btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start=true")])
                await message.reply_text(f"<b>👋 Hello {message.from_user.mention},\n\nPlease join the channel then click the try again button. 😇</b>", reply_markup=InlineKeyboardMarkup(btn))
                return
        except Exception as e:
            logger.error(e)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 Get Random Video", callback_data="get_random_video")],
    ])
    await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome to the Video Bot!", reply_markup=keyboard)

# ✅ **Index Videos (Optimized)**
@bot.on_message(filters.command("index") & filters.user(OWNER_ID))
async def index_videos(client, message):
    await message.reply_text("🔄 Indexing videos... Please wait.")

    last_indexed = collection.find_one(sort=[("message_id", -1)])
    last_message_id = last_indexed["message_id"] if last_indexed else 1
    indexed_count = 0

    while True:
        try:
            messages = await client.get_messages(CHANNEL_ID, list(range(last_message_id, last_message_id + 100)))
            video_entries = [{"message_id": msg.id} for msg in messages if msg and msg.video]

            if video_entries:
                collection.insert_many(video_entries, ordered=False)
                indexed_count += len(video_entries)

            last_message_id += 100
            if not video_entries:
                break
        except Exception as e:
            logger.error(f"Indexing error: {e}")
            break

    response = f"✅ Indexed {indexed_count} new videos!" if indexed_count else "⚠ No new videos found!"
    await message.reply_text(response)

# ✅ **Check Total Indexed Files (Owner Only)**
@bot.on_message(filters.command("files") & filters.user(OWNER_ID))
async def check_files(client, message):
    total_videos = collection.count_documents({})
    await message.reply_text(f"📂 Total Indexed Videos: {total_videos}")

# ✅ **About Command**
@bot.on_message(filters.command("about"))
async def about(client, message):
    await message.reply_text(
        "🤖 **Bot Name:** Random Video Bot\n"
        "👑 **Owner:** @YourUsername\n"
        "🔧 **Version:** 2.2 (Optimized)\n"
        "💾 **Database:** MongoDB\n"
        "🚀 **Hosted On:** Koyeb",
        disable_web_page_preview=True
    )

# ✅ **Run the Bot**
if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    bot.run() 

