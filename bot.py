import os
import logging
import random
import asyncio
import threading
import re
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
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL", "YOUR_MONGO_URL")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002465297334"))
OWNER_ID = int(os.getenv("OWNER_ID", "6860316927"))
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "https://envs.sh/n9o.jpg")
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "20"))

# ✅ FSub Setup (🔹 Don't Remove Credit: @VJ_Botz 🔹)
id_pattern = re.compile(r'^.\d+$')
AUTH_CHANNEL = [int(ch) if id_pattern.search(ch) else ch for ch in os.getenv("AUTH_CHANNEL", "-1002490575006").split()]

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]

# 🔥 **Cache for Fast Video Retrieval**
recent_videos = []

# ✅ **Force Subscribe Function**
async def is_subscribed(bot, query, channel):
    btn = []
    for id in channel:
        chat = await bot.get_chat(int(id))
        try:
            await bot.get_chat_member(id, query.from_user.id)
        except UserNotParticipant:
            btn.append([InlineKeyboardButton(f'Join {chat.title}', url=chat.invite_link)])
        except Exception as e:
            pass
    return btn

# 🔰 **Fetch & Send Random Video**
async def send_random_video(client, chat_id):
    global recent_videos

    if not recent_videos:
        recent_videos = list(collection.aggregate([{"$sample": {"size": 10}}]))

    if not recent_videos:
        await client.send_message(chat_id, "⚠ No videos available. Use /index first!")
        return
    
    random_video = recent_videos.pop()
    try:
        message = await client.get_messages(CHANNEL_ID, random_video["message_id"])
        if message and message.video:
            sent_msg = await client.send_video(
                chat_id=chat_id,
                video=message.video.file_id,
                caption="Thanks 😊"
            )
            await asyncio.sleep(AUTO_DELETE_TIME)
            await sent_msg.delete()

        if len(recent_videos) < 3:
            asyncio.create_task(prefetch_videos())

    except FloodWait as e:
        logger.warning(f"FloodWait detected: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
        await send_random_video(client, chat_id)
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")

# 🔥 **Pre-fetch Next Set of Videos**
async def prefetch_videos():
    global recent_videos
    if len(recent_videos) < 5:
        recent_videos.extend(list(collection.aggregate([{"$sample": {"size": 10}}])))

# 🔰 **Index Videos (Owner Only)**
@bot.on_message(filters.command("index") & filters.user(OWNER_ID))
async def index_videos(client, message):
    await message.reply_text("🔄 Indexing videos... Please wait.")
    
    indexed_count = 0
    last_indexed = collection.find_one(sort=[("message_id", -1)])
    last_message_id = last_indexed["message_id"] if last_indexed else 1
    batch_size = 100

    while True:
        try:
            message_ids = list(range(last_message_id, last_message_id + batch_size))
            messages = await client.get_messages(CHANNEL_ID, message_ids)

            video_entries = [
                {"message_id": msg.id}
                for msg in messages if msg and msg.video and not collection.find_one({"message_id": msg.id})
            ]

            if video_entries:
                collection.insert_many(video_entries)
                indexed_count += len(video_entries)

            last_message_id += batch_size
            if not video_entries:
                break
        except Exception as e:
            logger.error(f"Indexing error: {e}")
            break

    if indexed_count:
        await message.reply_text(f"✅ Indexed {indexed_count} new videos!")
    else:
        await message.reply_text("⚠ No new videos found!")

# 🔰 **Check Total Indexed Files (Owner Only)**
@bot.on_message(filters.command("files") & filters.user(OWNER_ID))
async def check_files(client, message):
    total_videos = collection.count_documents({})
    await message.reply_text(f"📂 Total Indexed Videos: {total_videos}")

# 🔰 **Start Command (Welcome & FSub Check)**
@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id

    if AUTH_CHANNEL:
        try:
            btn = await is_subscribed(client, message, AUTH_CHANNEL)
            if btn:
                username = (await client.get_me()).username
                if message.command[1]:
                    btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start={message.command[1]}")])
                else:
                    btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start=true")])
                await message.reply_text(text=f"<b>👋 Hello {message.from_user.mention},\n\nPlease join the channel then click on try again button. 😇</b>", reply_markup=InlineKeyboardMarkup(btn))
                return
        except Exception as e:
            print(e)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 Get Random Video", callback_data="get_random_video")],
    ])
    await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome to the Video Bot!", reply_markup=keyboard)

# 🔰 **Callback for Getting Random Video**
@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    await send_random_video(client, callback_query.message.chat.id)
    await callback_query.answer()

# 🔰 **About Command**
@bot.on_message(filters.command("about"))
async def about(client, message):
    await message.reply_text(
        "🤖 **Bot Name:** Random Video Bot\n"
        "👑 **Owner:** @YourUsername\n"
        "🔧 **Version:** 2.1 (Optimized)\n"
        "💾 **Database:** MongoDB\n"
        "🚀 **Hosted On:** Koyeb",
        disable_web_page_preview=True
    )

# 🔰 **Run the Bot**
if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    bot.run()
