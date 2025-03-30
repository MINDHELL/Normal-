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
settings_collection = db["settings"]

# ✅ **MongoDB Caching**
video_cache = []  # Cache for indexed videos
last_cache_time = 0
CACHE_EXPIRY = 300  # Refresh cache every 5 minutes

async def refresh_video_cache():
    global video_cache, last_cache_time
    if time.time() - last_cache_time > CACHE_EXPIRY:
        video_cache = list(collection.aggregate([{"$sample": {"size": 500}}]))  # Increased cache size
        last_cache_time = time.time()

# ✅ **Fetch Protection Setting**
def is_protection_enabled():
    setting = settings_collection.find_one({"_id": "content_protection"})
    return setting and setting.get("enabled", False)

# ✅ **Set Protection On/Off**
@bot.on_message(filters.command("protect") & filters.user(OWNER_ID))
async def toggle_protection(client, message):
    if len(message.command) < 2:
        await message.reply_text("⚙ Usage: `/protect on` or `/protect off`")
        return
    
    status = message.command[1].lower()
    if status in ["on", "off"]:
        settings_collection.update_one({"_id": "content_protection"}, {"$set": {"enabled": status == "on"}}, upsert=True)
        await message.reply_text(f"✅ **Content Protection is now {'ENABLED' if status == 'on' else 'DISABLED'}**")
    else:
        await message.reply_text("⚙ Invalid option! Use `/protect on` or `/protect off`.")

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

# 🔰 **Fetch & Send Random Video (With Protection)**
async def send_random_video(client, chat_id):
    await refresh_video_cache()  # Refresh cache if needed

    if not video_cache:
        await client.send_message(chat_id, "⚠ No videos available. Use /index first!")
        return

    video = video_cache.pop()
    try:
        message = await client.get_messages(CHANNEL_ID, video["message_id"])
        if message and message.video:
            sent_msg = await client.send_video(
                chat_id, 
                video=message.video.file_id, 
                caption="Thanks 😊", 
                protect_content=is_protection_enabled()  # Enable protection if set
            )

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
    try:
        await callback_query.answer()
        asyncio.create_task(send_random_video(client, callback_query.message.chat.id))
    except QueryIdInvalid:
        logger.warning("Ignoring invalid query ID error.")
    except Exception as e:
        logger.error(f"Error in callback: {e}")

# 🔰 **Start Command (Welcome & FSub Check)**
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

# 🔰 **Index Videos (Owner Only)**
@bot.on_message(filters.command("index") & filters.user(OWNER_ID))
async def index_videos(client, message):
    await message.reply_text("🔄 Indexing videos... Please wait.")

    last_indexed = collection.find_one(sort=[("message_id", -1)])
    last_message_id = last_indexed["message_id"] if last_indexed else 1
    batch_size = 100
    indexed_count = 0

    while True:
        try:
            messages = await client.get_messages(CHANNEL_ID, list(range(last_message_id, last_message_id + batch_size)))
            video_entries = [{"message_id": msg.id} for msg in messages if msg and msg.video and not collection.find_one({"message_id": msg.id})]

            if video_entries:
                collection.insert_many(video_entries)
                indexed_count += len(video_entries)

            last_message_id += batch_size
            if not video_entries:
                break
        except Exception as e:
            logger.error(f"Indexing error: {e}")
            break

    await refresh_video_cache()
    response = f"✅ Indexed {indexed_count} new videos!" if indexed_count else "⚠ No new videos found!"
    await message.reply_text(response)

# 🔰 **Check Total Indexed Files (Owner Only)**
@bot.on_message(filters.command("files") & filters.user(OWNER_ID))
async def check_files(client, message):
    total_videos = collection.count_documents({})
    await message.reply_text(f"📂 Total Indexed Videos: {total_videos}")
    
# 🔰 **About Command**
@bot.on_message(filters.command("about"))
async def about(client, message):
    about_text = f"""
🤖 **Bot Name:** Random Video Bot  
👨‍💻 **Owner:** [Your Username](tg://user?id={OWNER_ID})  
🛠 **Version:** 2.1  
📡 **Hosted On:** Koyeb  
💾 **Database:** MongoDB  
⚙ **Framework:** Pyrogram  
📢 **Support Channel:** [Join Here](https://t.me/YOUR_CHANNEL)  

⚡ **Description:** This bot fetches random videos from an indexed database and sends them to users on request.  
"""
    await message.reply_text(about_text, disable_web_page_preview=True)
    
    # 🔰 **Run the Bot**
    if __name__ == "__main__":
        
        threading.Thread(target=start_health_check, daemon=True).start()
        bot.run()
