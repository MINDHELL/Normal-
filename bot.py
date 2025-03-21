import asyncio
import threading
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import API_ID, API_HASH, BOT_TOKEN, MONGO_URL, OWNER_ID, FORCE_SUB_CHANNEL, DAILY_LIMIT, AUTO_DELETE_TIME, WELCOME_IMAGE

# Initialize Bot
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Connect to MongoDB
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["video_bot"]
users_db = db["users"]
videos_db = db["videos"]

# Flask Web Server for Koyeb TCP Health Check Fix
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

# Force Subscription Function
async def is_subscribed(client, user_id):
    if user_id == OWNER_ID:
        return True  # Owner bypasses force sub
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# Welcome Message
@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    if not await is_subscribed(client, user_id):
        return await message.reply_text(
            "🔴 You must join our channel first!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL}")]])
        )

    await message.reply_photo(
        WELCOME_IMAGE,
        caption="👋 Welcome to the bot!\nEnjoy random videos.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Get Video 🎥", callback_data="get_video")]])
    )

# Video Sending Function
@bot.on_callback_query(filters.regex("get_video"))
async def send_video(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_subscribed(client, user_id):
        return await callback_query.answer("🔴 You must join our channel first!", show_alert=True)

    user = await users_db.find_one({"user_id": user_id})
    if not user:
        await users_db.insert_one({"user_id": user_id, "daily_videos": 0})

    user = await users_db.find_one({"user_id": user_id})
    if int(user["daily_videos"]) >= int(DAILY_LIMIT):
        return await callback_query.answer("⚠️ Daily limit reached! Try again tomorrow.", show_alert=True)

    video = await videos_db.find_one({}, sort=[("timestamp", -1)])
    if video:
        sent_msg = await bot.send_video(callback_query.message.chat.id, video["file_id"], caption="Enjoy! 🎥")
        await users_db.update_one({"user_id": user_id}, {"$inc": {"daily_videos": 1}})
        
        # Auto-delete after set time
        await asyncio.sleep(AUTO_DELETE_TIME)
        await sent_msg.delete()

# Reset Daily Limit
async def reset_limits():
    while True:
        await asyncio.sleep(86400)  # 24 hours
        await users_db.update_many({}, {"$set": {"daily_videos": 0}})

@bot.on_message(filters.command("files") & filters.user(OWNER_ID))
async def count_files(client, message):
    total_files = await videos_db.count_documents({})
    await message.reply_text(f"📁 Total indexed videos: {total_files}")

# Start Flask Web Server for Koyeb Health Check
threading.Thread(target=run_web).start()

# Start Limit Reset Task
bot.loop.create_task(reset_limits())

# Run the Bot
bot.run()
