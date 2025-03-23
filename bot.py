import os
import logging
import random
import asyncio
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from pyrogram.errors import UserNotParticipant
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
AUTH_CHANNEL = [int(ch) for ch in os.getenv("AUTH_CHANNEL", "-1002490575006").split()]  # 🔰 FSub Channels
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "https://envs.sh/n9o.jpg")  # 🔰 Welcome Image URL
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "20"))  # 🔰 Auto-delete time in seconds

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]

# 🔰 Function to check if user is subscribed
async def is_subscribed(client, user_id):
    for channel in AUTH_CHANNEL:
        try:
            await client.get_chat_member(channel, user_id)
        except UserNotParticipant:
            chat = await client.get_chat(channel)
            return False, chat.invite_link
    return True, None

# 🔰 Send Random Video Function
async def send_random_video(client, chat_id):
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
            # 🔰 Auto-delete feature
            await asyncio.sleep(AUTO_DELETE_TIME)
            await sent_msg.delete()
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await client.send_message(chat_id, "⚠ Error fetching video. Try again later.")

# 🔰 Index Videos Command (Owner Only)
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
                break  # 🔰 Stop if no new videos found
        except Exception as e:
            logger.error(f"Indexing error: {e}")
            break

    if indexed_count:
        await message.reply_text(f"✅ Indexed {indexed_count} new videos!")
    else:
        await message.reply_text("⚠ No new videos found!")

# 🔰 Command to Check Total Indexed Files (Owner Only)
@bot.on_message(filters.command("files") & filters.user(OWNER_ID))
async def check_files(client, message):
    total_videos = collection.count_documents({})
    await message.reply_text(f"📂 Total Indexed Videos: {total_videos}")

# 🔰 Start Command (Welcome Message & FSub Check)
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

# 🔰 Callback for Getting Random Video
@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    await send_random_video(client, callback_query.message.chat.id)
    await callback_query.answer()

# 🔰 About Command
@bot.on_message(filters.command("about"))
async def about(client, message):
    await message.reply_text(
        "🤖 **Bot Name:** Random Video Bot\n"
        "👑 **Owner:** @cosmoms6t\n"
        "🔧 **Version:** 2.0\n"
        "💾 **Database:** MongoDB\n"
        "🚀 **Hosted On:** Koyeb",
        disable_web_page_preview=True
    )

# 🔰 Run the Bot
if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    bot.run()import os
import logging
import random
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from pyrogram.errors import UserNotParticipant, FloodWait

# 🔰 Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔰 Environment Variables
API_ID = int(os.getenv("API_ID", "27788368"))
API_HASH = os.getenv("API_HASH", "9df7e9ef3d7e4145270045e5e43e1081")
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MONGO_URL = os.getenv("MONGO_URL", "YOUR_MONGO_URL_HERE")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002465297334"))
OWNER_ID = int(os.getenv("OWNER_ID", "6860316927"))
AUTH_CHANNEL = [int(ch) for ch in os.getenv("AUTH_CHANNEL", "-1002490575006").split()]
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "https://envs.sh/n9o.jpg")
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "10"))  # ⏳ Faster deletion
RATE_LIMIT_DELAY = 1  # ⏳ Delay to prevent FloodWait

# 🔰 Initialize Bot & Database
bot = Client("fast_video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL, maxPoolSize=50)  # 🚀 Connection Pooling
db = mongo["VideoBot"]
collection = db["videos"]

# ✅ **Force Subscription Checker**
async def is_subscribed(client, user_id):
    for channel in AUTH_CHANNEL:
        try:
            await client.get_chat_member(channel, user_id)
        except UserNotParticipant:
            chat = await client.get_chat(channel)
            return False, chat.invite_link
    return True, None

# ✅ **Send Random Video Faster with Task Queues**
async def send_random_video(client, chat_id):
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
            # 🔰 Auto-delete after `AUTO_DELETE_TIME`
            asyncio.create_task(delete_after_delay(sent_msg))
    except FloodWait as e:
        logger.warning(f"FloodWait: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error(f"Error sending video: {e}")

# ✅ **Auto-delete messages faster**
async def delete_after_delay(message):
    await asyncio.sleep(AUTO_DELETE_TIME)
    await message.delete()

# ✅ **Owner-Only Command to Index Videos**
@bot.on_message(filters.command("index") & filters.user(OWNER_ID))
async def index_videos(client, message):
    await message.reply_text("🔄 Indexing videos... Please wait.")
    
    indexed_count = 0
    last_indexed = collection.find_one(sort=[("message_id", -1)])
    last_message_id = last_indexed["message_id"] if last_indexed else 1
    batch_size = 50  # 🚀 Smaller batch size for faster processing

    while True:
        try:
            messages = await client.get_messages(CHANNEL_ID, range(last_message_id, last_message_id + batch_size))
            video_entries = [{"message_id": msg.id} for msg in messages if msg and msg.video]

            if video_entries:
                collection.insert_many(video_entries, ordered=False)
                indexed_count += len(video_entries)

            last_message_id += batch_size
            if not video_entries:
                break  # 🔰 Stop if no new videos found
        except Exception as e:
            logger.error(f"Indexing error: {e}")
            break

    await message.reply_text(f"✅ Indexed {indexed_count} new videos!" if indexed_count else "⚠ No new videos found!")

# ✅ **Check Total Indexed Files**
@bot.on_message(filters.command("files") & filters.user(OWNER_ID))
async def check_files(client, message):
    total_videos = collection.count_documents({})
    await message.reply_text(f"📂 Total Indexed Videos: {total_videos}")

# ✅ **Start Command with Faster FSub Check**
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
    await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome to the Fast Video Bot!", reply_markup=keyboard)

# ✅ **Callback for Fast Random Video Sending**
@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    asyncio.create_task(send_random_video(client, callback_query.message.chat.id))  # 🚀 Run as async task
    await callback_query.answer()

# ✅ **About Command**
@bot.on_message(filters.command("about"))
async def about(client, message):
    await message.reply_text(
        "🤖 **Bot Name:** Fast Video Bot\n"
        "👑 **Owner:** @cosmos6t\n"
        "🔧 **Version:** 2.1 Optimized\n"
        "💾 **Database:** MongoDB (Fast Querying)\n"
        "🚀 **Hosted On:** Koyeb (Scalable)",
        disable_web_page_preview=True
    )

# ✅ **Run the Bot Efficiently**
if __name__ == "__main__":
    bot.start()  # 🚀 Start without blocking
    asyncio.get_event_loop().run_forever()

