import os
import shutil
import signal
import subprocess
import psutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "abcde")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")
OWNER_ID = int(os.environ.get("OWNER_ID", 12345))
MONGO_URL = os.environ.get("MONGO_URL", "")

# --- SETUP ---
app = Client("ProHoster", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB Connection
if MONGO_URL:
    mongo = AsyncIOMotorClient(MONGO_URL)
    db = mongo.hosting_bot
    bots_collection = db.bots
else:
    print("❌ MONGO_URL missing! Bot database save nahi karega.")

# Work Directory
WORKDIR = "hosted_bots"
if not os.path.exists(WORKDIR):
    os.mkdir(WORKDIR)

# --- HELPER FUNCTIONS ---
async def is_owner(user_id):
    return user_id == OWNER_ID

def kill_process(pid):
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
        return True
    except:
        return False

# --- COMMANDS ---

@app.on_message(filters.command("start"))
async def start(client, message):
    txt = (
        "👋 **Pro Hosting Bot Live!**\n\n"
        "**Commands:**\n"
        "⚡ `/deploy link | token | mongo` - Naya bot banayein\n"
        "🛑 `/stop user_id` - Bot rokein\n"
        "📊 `/mybots` - Running bots dekhein\n"
        "📝 `/logs user_id` - Logs mangwayein\n"
        "🗑 `/delete user_id` - Bot delete karein"
    )
    await message.reply(txt)

@app.on_message(filters.command("deploy") & filters.user(OWNER_ID))
async def deploy(client, message):
    try:
        # Format: /deploy link | token | mongo
        _, args = message.text.split(" ", 1)
        repo, token, mongo = args.split(" | ")
    except:
        return await message.reply("❌ **Format:** `/deploy link | token | mongo`")

    # Target User (Filhal Owner hi deploy kar raha hai apne liye ya client ke liye)
    # Agar aap client ke liye host kar rahe hain toh command aise use karein:
    # /deploy link | token | mongo (Message mein target user ID mention kar sakte hain logic badha kar)
    
    # Simple logic: Har User ka ek hi bot hoga
    user_id = message.from_user.id 
    path = f"{WORKDIR}/{user_id}"

    msg = await message.reply("⚙️ **System Check...**")

    # Check if already running
    old_bot = await bots_collection.find_one({"user_id": user_id})
    if old_bot:
        await msg.edit("⚠️ **Purana bot delete kiya ja raha hai...**")
        if old_bot.get("pid"):
            kill_process(old_bot["pid"])
        if os.path.exists(path):
            shutil.rmtree(path)
        await bots_collection.delete_one({"user_id": user_id})

    # Cloning
    await msg.edit("📥 **Cloning Repo...**")
    os.system(f"git clone {repo} {path}")

    # Create .env
    with open(f"{path}/.env", "w") as f:
        f.write(f"API_ID={API_ID}\nAPI_HASH={API_HASH}\nBOT_TOKEN={token}\nDATABASE_URL={mongo}")

    # Install Requirements
    await msg.edit("📦 **Installing Requirements...**")
    subprocess.run(f"pip install -r {path}/requirements.txt", shell=True)

    # Start Bot
    await msg.edit("🚀 **Starting Bot...**")
    log_file = open(f"{path}/log.txt", "w")
    
    # Bot start command (Assuming repo has 'bot' folder or 'main.py')
    # Link-Share-Bot specific: python3 -m bot
    process = subprocess.Popen(
        ["python3", "-m", "bot"], 
        cwd=path, 
        stdout=log_file, 
        stderr=log_file
    )

    # Save to DB
    bot_data = {
        "user_id": user_id,
        "repo": repo,
        "token": token,
        "pid": process.pid,
        "status": "Running"
    }
    await bots_collection.insert_one(bot_data)

    await msg.edit(f"✅ **Bot Deployed Successfully!**\nPID: `{process.pid}`\n\nLogs ke liye `/logs` use karein.")

@app.on_message(filters.command("stop") & filters.user(OWNER_ID))
async def stop_bot(client, message):
    try:
        target = int(message.text.split()[1])
    except:
        target = message.from_user.id
        
    bot = await bots_collection.find_one({"user_id": target})
    if not bot:
        return await message.reply("❌ Koi bot nahi mila.")

    if kill_process(bot["pid"]):
        await bots_collection.update_one({"user_id": target}, {"$set": {"status": "Stopped", "pid": None}})
        await message.reply("✅ Bot rok diya gaya hai.")
    else:
        await message.reply("⚠️ Bot pehle hi band hai ya PID nahi mili.")

@app.on_message(filters.command("logs") & filters.user(OWNER_ID))
async def get_logs(client, message):
    try:
        target = int(message.text.split()[1])
    except:
        target = message.from_user.id

    path = f"{WORKDIR}/{target}/log.txt"
    if os.path.exists(path):
        await message.reply_document(path, caption=f"📜 Logs for User: `{target}`")
    else:
        await message.reply("❌ Log file nahi mili.")

@app.on_message(filters.command("mybots") & filters.user(OWNER_ID))
async def list_bots(client, message):
    bots = bots_collection.find()
    text = "📊 **Active Bots:**\n\n"
    async for bot in bots:
        text += f"👤 User: `{bot['user_id']}`\n🤖 Status: {bot['status']}\n🆔 PID: `{bot.get('pid')}`\n\n"
    await message.reply(text)

print("🔥 Advanced Manager Bot Started!")
app.run()
