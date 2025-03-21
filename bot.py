import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import *

bot = Client("RandomVideoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["random_video_bot"]
videos_collection = db["videos"]
users_collection = db["users"]

async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        print(f"Force Sub Error: {e}")
    return False

async def update_user_limit(user_id):
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        await users_collection.insert_one({"_id": user_id, "videos_sent": 1})
        return True
    if user["videos_sent"] < DAILY_LIMIT:
        await users_collection.update_one({"_id": user_id}, {"$inc": {"videos_sent": 1}})
        return True
    return False

@bot.on_message(filters.command("start"))
async def start(bot, message):
    user_id = message.from_user.id

    if not await is_subscribed(user_id):
        return await message.reply(
            "❌ *You must join our channel to use this bot!*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL[1:]}")]])
        )

    await message.reply_photo(
        photo=WELCOME_IMAGE_URL,
        caption=WELCOME_MESSAGE,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Get Random Video", callback_data="get_video")]])
    )

@bot.on_callback_query(filters.regex("get_video"))
async def get_random_video(bot, query):
    user_id = query.from_user.id

    if not await is_subscribed(user_id):
        return await query.answer("❌ *You must join our channel to use this bot!*", show_alert=True)

    if not await update_user_limit(user_id):
        return await query.answer("⚠️ Daily limit reached! Try again tomorrow.", show_alert=True)

    video = await videos_collection.aggregate([{"$sample": {"size": 1}}]).to_list(length=1)
    if not video:
        return await query.answer("❌ No videos available! Run `/index` first.", show_alert=True)

    sent_message = await bot.send_video(
        chat_id=user_id,
        video=video[0]["file_id"],
        caption="🎥 Here's a random video for you!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Get Another", callback_data="get_video")]])
    )

    await asyncio.sleep(AUTO_DELETE_TIME)
    await bot.delete_messages(user_id, sent_message.message_id)

@bot.on_message(filters.command("index") & filters.user("your_owner_id"))
async def index_videos(bot, message):
    channel_id = message.chat.id
    async for msg in bot.get_chat_history(channel_id):
        if msg.video:
            await videos_collection.insert_one({"file_id": msg.video.file_id})
    await message.reply("✅ Indexing Completed!")

@bot.on_message(filters.command("files"))
async def show_file_count(bot, message):
    count = await videos_collection.count_documents({})
    await message.reply(f"📂 Total Indexed Videos: {count}")

bot.run()
