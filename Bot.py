import asyncio
import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import API_ID, API_HASH, BOT_TOKEN, MONGO_URI, DB_NAME, CHANNEL_ID, OWNER_ID, FORCE_SUB_CHANNEL, DAILY_LIMIT, AUTO_DELETE_TIME, WELCOME_IMAGE_URL, WELCOME_MESSAGE

bot = Client("RandomVideoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client[DB_NAME]
users_collection = db["users"]
videos_collection = db["videos"]

async def is_owner(user_id):
    return user_id == OWNER_ID

async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

async def update_user_limit(user_id):
    today = datetime.datetime.utcnow().date()
    user = await users_collection.find_one({"user_id": user_id})
    if not user:
        await users_collection.insert_one({"user_id": user_id, "date": today.isoformat(), "requests": 1})
        return True

    if user["date"] != today.isoformat():
        await users_collection.update_one({"user_id": user_id}, {"$set": {"date": today.isoformat(), "requests": 1}})
        return True

    if user["requests"] < DAILY_LIMIT or await is_owner(user_id):
        await users_collection.update_one({"user_id": user_id}, {"$inc": {"requests": 1}})
        return True

    return False

@bot.on_message(filters.command("start"))
async def start(bot, message):
    user_id = message.from_user.id
    while not await is_subscribed(user_id):  
        await message.reply(
            "❌ *You must join our channel to use this bot!*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL[1:]}")]])
        )
        await asyncio.sleep(5)
        return  

    await message.reply_photo(
        photo=WELCOME_IMAGE_URL,
        caption=WELCOME_MESSAGE,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Get Random Video", callback_data="get_video")]])
    )

@bot.on_callback_query(filters.regex("get_video"))
async def get_random_video(bot, query):
    user_id = query.from_user.id

    while not await is_subscribed(user_id):  
        await query.message.reply(
            "❌ *You must join our channel to use this bot!*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL[1:]}")]])
        )
        await asyncio.sleep(5)
        return  

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

@bot.on_message(filters.command("files"))
async def total_files(bot, message):
    total = await videos_collection.count_documents({})
    await message.reply(f"📂 Total Indexed Videos: {total}")

@bot.on_message(filters.command("index"))
async def index_command(bot, message):
    if not await is_owner(message.from_user.id):
        return await message.reply("❌ Only the owner can use this command!")

    await message.reply("🔄 Indexing videos...")
    count = 0
    async for msg in bot.get_chat_history(CHANNEL_ID, limit=5000):
        if msg.video:
            await videos_collection.update_one(
                {"file_id": msg.video.file_id},
                {"$set": {"file_id": msg.video.file_id}},
                upsert=True
            )
            count += 1

    await message.reply(f"✅ Indexed {count} videos!")

@bot.on_message(filters.command("set_limit"))
async def set_limit(bot, message):
    if not await is_owner(message.from_user.id):
        return await message.reply("❌ Only the owner can set limits!")
    
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        return await message.reply("⚠️ Usage: `/set_limit <number>`")

    global DAILY_LIMIT
    DAILY_LIMIT = int(args[1])
    await message.reply(f"✅ Daily limit updated to {DAILY_LIMIT} videos per user.")

bot.run()
