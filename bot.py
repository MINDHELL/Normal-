import os
import logging
import asyncio
import threading
import time
import re
import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid
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
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "30"))
VIDEO_LIMIT = int(os.getenv("VIDEO_LIMIT", "20"))  # Set video limit per user
QUOTA_RESET_TIME = 0 * 3 * 60  # Quota reset every 24 hours

# ✅ Force Subscribe Setup
id_pattern = re.compile(r'^.\d+$')
AUTH_CHANNEL = [int(ch) if id_pattern.search(ch) else ch for ch in os.getenv("AUTH_CHANNEL", "-1002490575006").split()]

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot"]
collection = db["videos"]
users_collection = db["users"]
settings_collection = db["settings"]

# ✅ **Cache Optimization**
video_cache = []
last_cache_time = 0
CACHE_EXPIRY = 300  # Refresh cache every 5 minutes

async def refresh_video_cache():
    global video_cache, last_cache_time
    if time.time() - last_cache_time > CACHE_EXPIRY:
        video_cache = list(collection.aggregate([{"$sample": {"size": 500}}]))  
        last_cache_time = time.time()

# ✅ **Fetch Protection Setting**
def is_protection_enabled():
    setting = settings_collection.find_one({"_id": "content_protection"})
    return setting and setting.get("enabled", False)

# ✅ **User Management**
async def add_user(user_id):
    user = users_collection.find_one({"id": user_id})
    if not user:
        # Initialize user with default values
        users_collection.insert_one({
            "id": user_id,
            "joined": datetime.datetime.utcnow(),
            "videos_sent": 0,  # Initialize videos_sent field
            "quota_reset_time": time.time() + QUOTA_RESET_TIME  # Set the reset time for quota
        })
    else:
        # Ensure "videos_sent" and "quota_reset_time" exist
        if "videos_sent" not in user:
            users_collection.update_one({"id": user_id}, {"$set": {"videos_sent": 0}})
        if "quota_reset_time" not in user:
            users_collection.update_one({"id": user_id}, {"$set": {"quota_reset_time": time.time() + QUOTA_RESET_TIME}})

# ✅ **/users Command – Get Total Users**
@bot.on_message(filters.command("users") & filters.user(OWNER_ID))
async def get_users_count(client, message):
    total_users = users_collection.count_documents({})
    await message.reply_text(f"📊 **Total Users:** `{total_users}`")

# ✅ **Broadcast System**
async def broadcast_messages(user_id, message):
    try:
        await message.copy(chat_id=user_id)
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message)
    except (InputUserDeactivated, UserIsBlocked, PeerIdInvalid):
        users_collection.delete_one({"id": user_id})
        return False, "Removed"
    except Exception:
        return False, "Error"

@bot.on_message(filters.command("broadcast") & filters.user(OWNER_ID) & filters.reply)
async def broadcast(client, message):
    users = users_collection.find()
    b_msg = message.reply_to_message
    total_users = users_collection.count_documents({})
    done, blocked, deleted, failed, success = 0, 0, 0, 0, 0

    status_msg = await message.reply_text(f"📢 **Broadcasting...**\nTotal Users: `{total_users}`")
    start_time = time.time()

    for user in users:
        user_id = user.get("id")
        if not user_id:
            continue
            
        result, reason = await broadcast_messages(user_id, b_msg)
        if result:
            success += 1
        else:
            if reason == "Removed":
                deleted += 1
            failed += 1
        done += 1

        if done % 20 == 0:
            try:
                await status_msg.edit(f"📢 **Broadcasting...**\nTotal Users: `{total_users}`\nProcessed: `{done}`\n✅ Success: `{success}`\n❌ Failed: `{failed}`\n🚫 Deleted: `{deleted}`")
            except:
                pass

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await status_msg.edit(f"✅ **Broadcast Completed in {time_taken}!**\nTotal Users: `{total_users}`\nProcessed: `{done}`\n✅ Success: `{success}`\n❌ Failed: `{failed}`\n🚫 Deleted: `{deleted}`")

# ✅ **Start Command**
@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    await add_user(user_id)

    if AUTH_CHANNEL:
        try:
            btn = []
            for id in AUTH_CHANNEL:
                chat = await client.get_chat(int(id))
                await client.get_chat_member(id, user_id)
        except UserNotParticipant:
            btn.append([InlineKeyboardButton(f'Join {chat.title}', url=chat.invite_link)])
            btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{client.me.username}?start=true")])
            await message.reply_text(f"👋 **Hello {message.from_user.mention},**\n\nJoin the channel and click 'Try Again'.", reply_markup=InlineKeyboardMarkup(btn))
            return
        except Exception:
            pass

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Get Random Video", callback_data="get_random_video")]])
    await message.reply_photo(WELCOME_IMAGE, caption="🎉 Welcome to the Video Bot!", reply_markup=keyboard)

# ✅ **Get Random Video**
async def send_random_video(client, chat_id):
    await refresh_video_cache()

    if not video_cache:
        await client.send_message(chat_id, "⚠ No videos available. Use /index first!")
        return

    user = users_collection.find_one({"id": chat_id})
    if user["videos_sent"] >= VIDEO_LIMIT and time.time() < user["quota_reset_time"]:
        reset_time = datetime.datetime.fromtimestamp(user["quota_reset_time"]).strftime("%Y-%m-%d %H:%M:%S")
        await client.send_message(chat_id, f"⚠️ You have reached your video limit of {VIDEO_LIMIT} videos. Your quota will reset at {reset_time}.")
        return

    video = video_cache.pop()
    try:
        message = await client.get_messages(CHANNEL_ID, video["message_id"])
        if message and message.video:
            sent_msg = await client.send_video(chat_id, video=message.video.file_id, caption="Thanks 😊", protect_content=is_protection_enabled())

            # Update user's videos_sent count
            users_collection.update_one({"id": chat_id}, {"$inc": {"videos_sent": 1}})

            if AUTO_DELETE_TIME > 0:
                await asyncio.sleep(AUTO_DELETE_TIME)
                await sent_msg.delete()

    except FloodWait as e:
        await asyncio.sleep(e.value)
        await send_random_video(client, chat_id)

@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    await callback_query.answer()
    asyncio.create_task(send_random_video(client, callback_query.message.chat.id))

# ✅ **Quota Status**
@bot.on_message(filters.command("quota"))
async def quota_status(client, message):
    user_id = message.from_user.id
    user = users_collection.find_one({"id": user_id})

    if user:
        videos_left = max(0, VIDEO_LIMIT - user["videos_sent"])
        time_left = user["quota_reset_time"] - time.time()
        reset_time = datetime.datetime.fromtimestamp(user["quota_reset_time"]).strftime("%Y-%m-%d %H:%M:%S")

        await message.reply_text(f"📊 **Your Quota Status:**\n"
                                 f"📅 Quota Reset Time: {reset_time}\n"
                                 f"🎥 Videos Sent: {user['videos_sent']}/{VIDEO_LIMIT}\n"
                                 f"⏳ Time Until Reset: {str(datetime.timedelta(seconds=int(time_left)))}\n"
                                 f"🕒 Videos Left: {videos_left}")
    else:
        await message.reply_text("⚠️ User not found! Please start the bot first.")

# ✅ **Index Videos**
@bot.on_message(filters.command("index") & filters.user(OWNER_ID))
async def index_videos(client, message):
    await message.reply_text("🔄 Indexing videos...")

    last_indexed = collection.find_one(sort=[("message_id", -1)])
    last_message_id = last_indexed["message_id"] if last_indexed else 1
    indexed_count = 0

    while True:
        try:
            messages = await client.get_messages(CHANNEL_ID, list(range(last_message_id, last_message_id + 100)))
            video_entries = [{"message_id": msg.id} for msg in messages if msg and msg.video and not collection.find_one({"message_id": msg.id})]

            if video_entries:
                collection.insert_many(video_entries)
                indexed_count += len(video_entries)

            last_message_id += 100
            if not video_entries:
                break
        except Exception:
            break

    await refresh_video_cache()
    await message.reply_text(f"✅ Indexed {indexed_count} new videos!" if indexed_count else "⚠ No new videos found!")

@bot.on_message(filters.command("files") & filters.user(OWNER_ID))
async def total_files(client, message):
    total_files = collection.count_documents({})
    await message.reply_text(f"📂 **Total Indexed Files:** `{total_files}`")

# ✅ **Run the Bot**
if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    bot.run()
