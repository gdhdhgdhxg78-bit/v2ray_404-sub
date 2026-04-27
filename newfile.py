import asyncio
import aiosqlite
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from pyrogram.enums import ParseMode, ChatMemberStatus
import logging
import re
from datetime import datetime
import random
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID

# ------------------ Logging ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ Bot ------------------
app = Client("v2ray_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ------------------ Configuration ------------------
REQUIRED_CHANNEL = "@Foot_GOAL_RUSH"
REQUIRED_CHANNEL_ID = None

# ------------------ Database ------------------
DB_PATH = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                join_date INTEGER,
                referrer_id INTEGER,
                invite_link TEXT,
                referral_count INTEGER DEFAULT 0,
                free_config_received BOOLEAN DEFAULT 0,
                is_blocked BOOLEAN DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_text TEXT NOT NULL,
                type TEXT NOT NULL,
                item_id INTEGER,
                used BOOLEAN DEFAULT 0,
                used_by INTEGER,
                assigned_date INTEGER,
                FOREIGN KEY (item_id) REFERENCES price_items(id)
            );
            
            CREATE TABLE IF NOT EXISTS price_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price INTEGER NOT NULL,
                card_number TEXT,
                card_holder TEXT
            );
            
            CREATE TABLE IF NOT EXISTS pending_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                receipt_photo_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (item_id) REFERENCES price_items(id)
            );
            
            CREATE TABLE IF NOT EXISTS user_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                config_text TEXT NOT NULL,
                item_name TEXT,
                purchase_date INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_date INTEGER,
                FOREIGN KEY (added_by) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS broadcast_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                message_text TEXT NOT NULL,
                recipients_count INTEGER DEFAULT 0,
                sent_date INTEGER,
                FOREIGN KEY (admin_id) REFERENCES users(user_id)
            );
            
            CREATE TABLE IF NOT EXISTS lottery_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                username TEXT,
                first_name TEXT,
                joined_at INTEGER,
                is_winner BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            
            CREATE TABLE IF NOT EXISTS lottery_winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                config_text TEXT,
                win_date INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)
        
        # Handle migration for existing databases
        try:
            await db.execute("ALTER TABLE admins ADD COLUMN added_by INTEGER")
        except:
            pass
        try:
            await db.execute("ALTER TABLE admins ADD COLUMN added_date INTEGER")
        except:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT 0")
        except:
            pass
        
        # Insert owner admin
        await db.execute("INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, strftime('%s','now'))", (ADMIN_ID, ADMIN_ID))
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sales_open', '1')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('lottery_active', '0')")
        await db.commit()

# ------------------ Helper Functions ------------------
async def is_sales_open() -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key='sales_open'") as cursor:
            row = await cursor.fetchone()
            return row[0] == '1' if row else True

async def set_sales_open(open: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('sales_open', ?)",
                         ('1' if open else '0',))
        await db.commit()

async def is_lottery_active() -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key='lottery_active'") as cursor:
            row = await cursor.fetchone()
            return row[0] == '1' if row else False

async def set_lottery_active(active: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('lottery_active', ?)",
                         ('1' if active else '0',))
        await db.commit()
# ------------------ Configuration ------------------
REQUIRED_CHANNEL = "@Foot_GOAL_RUSH"
REQUIRED_CHANNEL_ID = None
REQUIRED_CHANNEL_2 = "@RUSH_PROXY"
REQUIRED_CHANNEL_ID_2 = None

# ------------------ Helper Functions ------------------
async def check_channel_subscription(user_id: int) -> bool:
    global REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_ID_2
    
    try:
        # Check first channel
        if REQUIRED_CHANNEL_ID is None:
            chat = await app.get_chat(REQUIRED_CHANNEL)
            REQUIRED_CHANNEL_ID = chat.id
        
        member = await app.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
        if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
            return False
        
        # Check second channel
        if REQUIRED_CHANNEL_ID_2 is None:
            chat2 = await app.get_chat(REQUIRED_CHANNEL_2)
            REQUIRED_CHANNEL_ID_2 = chat2.id
        
        member2 = await app.get_chat_member(REQUIRED_CHANNEL_ID_2, user_id)
        if member2.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def add_user(user_id: int, username: str, first_name: str, referrer_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, join_date, referrer_id)
            VALUES (?, ?, ?, strftime('%s','now'), ?)
        """, (user_id, username, first_name, referrer_id))
        await db.commit()
        if referrer_id and referrer_id != user_id:
            await db.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (referrer_id,))
            await db.commit()
            await check_referral_reward(referrer_id)

async def check_referral_reward(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT referral_count, free_config_received FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] >= 25 and not row[1]:
                async with db.execute("""
                    SELECT id, config_text FROM configs 
                    WHERE type='referral' AND used=0 
                    ORDER BY id LIMIT 1
                """) as conf_cursor:
                    conf_row = await conf_cursor.fetchone()
                    if conf_row:
                        config_id, config_text = conf_row
                        await db.execute("UPDATE configs SET used=1, used_by=?, assigned_date=strftime('%s','now') WHERE id=?", (user_id, config_id))
                        await db.execute("UPDATE users SET free_config_received=1 WHERE user_id=?", (user_id,))
                        
                        await db.execute("""
                            INSERT INTO user_configs (user_id, config_text, item_name, purchase_date)
                            VALUES (?, ?, ?, strftime('%s','now'))
                        """, (user_id, config_text, "🎁 کانفیگ رایگان (جایزه دعوت)"))
                        
                        await db.commit()
                        try:
                            await app.send_message(user_id, f"🎉 تبریک! شما با موفقیت ۲۵ نفر را دعوت کردید.\n🔐 کانفیگ رایگان شما:\n\n`{config_text}`")
                        except:
                            pass
                    else:
                        try:
                            await app.send_message(ADMIN_ID, f"⚠️ کاربر {user_id} ۲۵ دعوت انجام داده اما کانفیگ رایگان موجود نیست.")
                        except:
                            pass

async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def is_owner(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def get_available_config_for_item(item_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, config_text FROM configs 
            WHERE type='item' AND item_id=? AND used=0 
            ORDER BY id LIMIT 1
        """, (item_id,)) as cursor:
            return await cursor.fetchone()

async def get_price_item(item_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM price_items WHERE id=?", (item_id,)) as cursor:
            return await cursor.fetchone()

async def get_available_referral_config():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, config_text FROM configs 
            WHERE type='referral' AND used=0 
            ORDER BY id LIMIT 1
        """) as cursor:
            return await cursor.fetchone()

# ------------------ Temp Storage ------------------
temp_purchases = {}
waiting_for_price_input = set()
waiting_for_config_input = {}
waiting_for_broadcast = {}
waiting_for_add_admin = set()
waiting_for_remove_admin = set()

# ------------------ Keyboard Functions ------------------
def get_main_keyboard(is_admin_user: bool = False):
    buttons = [
        [KeyboardButton("🛒 خرید کانفیگ")],
        [KeyboardButton("📊 آمار دعوت من"), KeyboardButton("🔐 کانفیگ‌های من")],
        [KeyboardButton("🔗 لینک دعوت من"), KeyboardButton("📞 پشتیبانی")]
    ]
    buttons.append([KeyboardButton("🎰 قرعه‌کشی")])  # Always show, check on click
    if is_admin_user:
        buttons.append([KeyboardButton("⚙️ پنل مدیریت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ------------------ Handlers ------------------
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check channel subscription first
    if not await check_channel_subscription(user_id) and user_id != ADMIN_ID:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 عضویت در کانال ۱", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
            [InlineKeyboardButton("📢 عضویت در کانال ۲", url=f"https://t.me/{REQUIRED_CHANNEL_2[1:]}")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_subscription")]
        ])
        
        await message.reply(
            f"⚠️ **برای استفاده از ربات ابتدا باید عضو کانال‌های زیر شوید:**\n\n"
            f"📢 ۱. {REQUIRED_CHANNEL}\n"
            f"📢 ۲. {REQUIRED_CHANNEL_2}\n\n"
            "پس از عضویت در هر دو کانال، روی دکمه «عضو شدم» کلیک کنید.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1][3:])
        except:
            pass
    
    await add_user(user_id, username, first_name, referrer_id)
    
    bot_username = (await client.get_me()).username
    invite_link = f"https://t.me/{bot_username}?start=ref{user_id}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET invite_link=? WHERE user_id=?", (invite_link, user_id))
        await db.commit()
    
    welcome_text = (
        "🌟 **به کانفیگ فروشی رافو خوش آمدید!** 🌟\n\n"
        "➕ با دعوت ۲۵ نفر یک کانفیگ رایگان دریافت کنید.\n\n"
        "🎰 در قرعه‌کشی شرکت کنید و برنده شوید!\n\n"
        "از منوی زیر برای استفاده از ربات استفاده کنید:"
    )
    
    is_admin_user = await is_admin(user_id)
    await message.reply(welcome_text, reply_markup=get_main_keyboard(is_admin_user))
@app.on_callback_query(filters.regex("check_subscription"))
async def check_subscription_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if await check_channel_subscription(user_id):
        await callback_query.answer("✅ عضویت شما تایید شد!", show_alert=True)
        await callback_query.message.delete()
        fake_message = callback_query.message
        fake_message.from_user = callback_query.from_user
        fake_message.text = "/start"
        await start_command(client, fake_message)
    else:
        await callback_query.answer("❌ شما هنوز عضو کانال نشده‌اید!", show_alert=True)

@app.on_message(filters.private & filters.text)
async def handle_text_messages(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text
    
    if not await check_channel_subscription(user_id) and user_id != ADMIN_ID:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 عضویت در کانال ۱", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
            [InlineKeyboardButton("📢 عضویت در کانال ۲", url=f"https://t.me/{REQUIRED_CHANNEL_2[1:]}")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_subscription")]
        ])
        await message.reply(
            f"⚠️ برای استفاده از ربات باید عضو هر دو کانال زیر باشید:\n\n"
            f"📢 ۱. {REQUIRED_CHANNEL}\n"
            f"📢 ۲. {REQUIRED_CHANNEL_2}",
            reply_markup=keyboard
        )
        return
    # ... 
    
    is_admin_user = await is_admin(user_id)
    
    # Handle special input states
    if user_id in waiting_for_price_input:
        await handle_price_input(client, message)
        return
    elif user_id in waiting_for_config_input:
        await handle_config_input(client, message)
        return
    elif user_id in waiting_for_broadcast:
        await handle_broadcast_input(client, message)
        return
    elif user_id in waiting_for_add_admin:
        await handle_add_admin_input(client, message)
        return
    elif user_id in waiting_for_remove_admin:
        await handle_remove_admin_input(client, message)
        return
    
    if text == "🛒 خرید کانفیگ":
        await show_price_list_message(client, message)
    elif text == "📊 آمار دعوت من":
        await show_user_stats_message(client, message)
    elif text == "🔐 کانفیگ‌های من":
        await show_user_configs(client, message)
    elif text == "🔗 لینک دعوت من":
        await show_invite_link(client, message)
    elif text == "📞 پشتیبانی":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 ارتباط با پشتیبانی", url="https://t.me/ErfanFoo")]
        ])
        await message.reply(
            "📞 **پشتیبانی کانفیگ فروشی رافو**\n\n"
            "برای ارتباط با پشتیبانی روی دکمه زیر کلیک کنید:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    elif text == "🎰 قرعه‌کشی":
        await handle_lottery_user(client, message)
    elif text == "⚙️ پنل مدیریت" and is_admin_user:
        await show_admin_panel(client, message)
    elif text in ["🚫 بستن فروش", "✅ باز کردن فروش"] and is_admin_user:
        await toggle_sales(client, message)
    elif text in ["🎰 فعال کردن قرعه‌کشی", "🎰 غیرفعال کردن قرعه‌کشی"] and is_admin_user:
        await toggle_lottery(client, message)
    elif text == "📊 آمار کلی" and is_admin_user:
        await admin_stats_message(client, message)
    elif text == "💰 مدیریت قیمت‌ها" and is_admin_user:
        await manage_prices_message(client, message)
    elif text == "🔐 مدیریت کانفیگ‌ها" and is_admin_user:
        await manage_configs_message(client, message)
    elif text == "🧾 درخواست‌های خرید" and is_admin_user:
        await show_pending_purchases_message(client, message)
    elif text == "👥 لیست کاربران" and is_admin_user:
        await show_users_list_message(client, message)
    elif text == "📢 ارسال پیام همگانی" and is_admin_user:
        await start_broadcast(client, message)
    elif text == "🎰 مدیریت قرعه‌کشی" and is_admin_user:
        await manage_lottery_message(client, message)
    elif text == "👨‍💼 مدیریت ادمین‌ها" and is_admin_user and await is_owner(user_id):
        await manage_admins_message(client, message)
    elif text == "🔙 بازگشت به منوی اصلی":
        await message.reply("🏠 منوی اصلی", reply_markup=get_main_keyboard(is_admin_user))
    else:
        await message.reply("❌ دستور نامعتبر. لطفاً از منو استفاده کنید.")

# ------------------ Lottery System ------------------
async def handle_lottery_user(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not await is_lottery_active():
        await message.reply("🎰 قرعه‌کشی در حال حاضر فعال نیست. منتظر قرعه‌کشی بعدی باشید!")
        return
    
    # Check if already participated
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM lottery_participants WHERE user_id=?", (user_id,)) as cursor:
            if await cursor.fetchone():
                await message.reply("✅ شما قبلاً در این قرعه‌کشی شرکت کرده‌اید. منتظر نتایج باشید!")
                return
        
        # Add participant
        user = message.from_user
        await db.execute("""
            INSERT INTO lottery_participants (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, strftime('%s','now'))
        """, (user_id, user.username or "", user.first_name or ""))
        await db.commit()
        
        # Get participant count
        async with db.execute("SELECT COUNT(*) FROM lottery_participants") as cursor:
            count = (await cursor.fetchone())[0]
    
    await message.reply(
        f"🎉 **با موفقیت در قرعه‌کشی شرکت کردید!**\n\n"
        f"👥 تعداد شرکت‌کنندگان تا الان: {count}\n"
        f"🍀 موفق باشید!",
        parse_mode=ParseMode.MARKDOWN
    )

async def toggle_lottery(client: Client, message: Message):
    current = await is_lottery_active()
    new_status = not current
    await set_lottery_active(new_status)
    
    if new_status:
        # Clear previous participants when starting new lottery
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM lottery_participants")
            await db.commit()
    
    await show_admin_panel(client, message)
    await message.reply(f"🎰 قرعه‌کشی {'فعال' if new_status else 'غیرفعال'} شد.")

async def manage_lottery_message(client: Client, message: Message):
    is_active = await is_lottery_active()
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM lottery_participants") as cursor:
            count = (await cursor.fetchone())[0]
    
    status_text = "✅ فعال" if is_active else "❌ غیرفعال"
    
    text = (
        f"🎰 **مدیریت قرعه‌کشی**\n\n"
        f"وضعیت: {status_text}\n"
        f"👥 تعداد شرکت‌کنندگان: {count}\n\n"
        "عملیات مورد نظر را انتخاب کنید:"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 انتخاب برنده", callback_data="lottery_pick_winner")],
        [InlineKeyboardButton("👥 مشاهده شرکت‌کنندگان", callback_data="lottery_view_participants")],
        [InlineKeyboardButton("🗑 پاک کردن لیست", callback_data="lottery_clear")],
        [InlineKeyboardButton("📜 تاریخچه برندگان", callback_data="lottery_winners_history")],
    ])
    
    await message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

# ------------------ Admin Panel ------------------
async def show_admin_panel(client: Client, message: Message):
    user_id = message.from_user.id
    is_owner_user = await is_owner(user_id)
    sales_open = await is_sales_open()
    lottery_active = await is_lottery_active()
    
    sales_toggle = "🚫 بستن فروش" if sales_open else "✅ باز کردن فروش"
    lottery_toggle = "🎰 غیرفعال کردن قرعه‌کشی" if lottery_active else "🎰 فعال کردن قرعه‌کشی"
    
    keyboard = [
        [KeyboardButton("📊 آمار کلی"), KeyboardButton("💰 مدیریت قیمت‌ها")],
        [KeyboardButton("🔐 مدیریت کانفیگ‌ها"), KeyboardButton("🧾 درخواست‌های خرید")],
        [KeyboardButton("👥 لیست کاربران"), KeyboardButton("📢 ارسال پیام همگانی")],
        [KeyboardButton("🎰 مدیریت قرعه‌کشی")],
    ]
    
    if is_owner_user:
        keyboard.append([KeyboardButton("👨‍💼 مدیریت ادمین‌ها")])
    
    keyboard.append([KeyboardButton(sales_toggle)])
    keyboard.append([KeyboardButton(lottery_toggle)])
    keyboard.append([KeyboardButton("🔙 بازگشت به منوی اصلی")])
    
    await message.reply(
        "🔧 **پنل مدیریت**",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )

async def toggle_sales(client: Client, message: Message):
    current = await is_sales_open()
    new_status = not current
    await set_sales_open(new_status)
    await show_admin_panel(client, message)
    await message.reply(f"✅ فروش {'باز' if new_status else 'بسته'} شد.")

# ------------------ Broadcast System (unchanged) ------------------
async def start_broadcast(client: Client, message: Message):
    user_id = message.from_user.id
    waiting_for_broadcast[user_id] = True
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ لغو", callback_data="cancel_broadcast")]
    ])
    
    await message.reply(
        "📢 **ارسال پیام همگانی**\n\n"
        "لطفاً پیام خود را ارسال کنید:\n\n"
        "⚠️ *نکته: پیام می‌تواند شامل متن، عکس، ویدیو و ... باشد.*\n"
        "برای لغو روی دکمه زیر کلیک کنید.",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_broadcast_input(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in waiting_for_broadcast:
        return
    
    waiting_for_broadcast.pop(user_id)
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_blocked=0") as cursor:
            users = await cursor.fetchall()
    
    total_users = len(users)
    success = 0
    failed = 0
    
    progress_msg = await message.reply(f"📤 در حال ارسال به {total_users} کاربر...")
    
    for (user_id,) in users:
        try:
            if message.text:
                await client.send_message(user_id, message.text)
            elif message.photo:
                await client.send_photo(user_id, message.photo.file_id, caption=message.caption or "")
            elif message.video:
                await client.send_video(user_id, message.video.file_id, caption=message.caption or "")
            elif message.document:
                await client.send_document(user_id, message.document.file_id, caption=message.caption or "")
            elif message.voice:
                await client.send_voice(user_id, message.voice.file_id, caption=message.caption or "")
            else:
                await client.forward_messages(user_id, message.chat.id, message.id)
            success += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
            failed += 1
        
        if (success + failed) % 20 == 0:
            try:
                await progress_msg.edit_text(f"📤 ارسال: {success + failed} از {total_users}")
            except:
                pass
        await asyncio.sleep(0.05)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO broadcast_history (admin_id, message_text, recipients_count, sent_date)
            VALUES (?, ?, ?, strftime('%s','now'))
        """, (user_id, message.text[:200] if message.text else message.caption[:200] if message.caption else "Media", success))
        await db.commit()
    
    await progress_msg.edit_text(
        f"✅ **ارسال پیام همگانی به پایان رسید**\n\n"
        f"👥 کل کاربران: {total_users}\n"
        f"✅ موفق: {success}\n"
        f"❌ ناموفق: {failed}",
        parse_mode=ParseMode.MARKDOWN
    )

# ------------------ Admin Management ------------------
async def manage_admins_message(client: Client, message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT a.user_id, u.first_name, u.username, a.added_date 
            FROM admins a
            LEFT JOIN users u ON a.user_id = u.user_id
            ORDER BY a.added_date
        """) as cursor:
            admins = await cursor.fetchall()
    
    text = "👨‍💼 **مدیریت ادمین‌ها**\n\n"
    for admin in admins:
        uid, first_name, username, added_date = admin
        username_str = f"@{username}" if username else "بدون یوزرنیم"
        name = first_name or "ناشناس"
        dt = datetime.fromtimestamp(added_date)
        owner_badge = " 👑" if uid == ADMIN_ID else ""
        text += f"• {name} ({username_str}){owner_badge}\n  🆔 `{uid}` | 📅 {dt.strftime('%Y/%m/%d')}\n\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن ادمین", callback_data="admin_add_admin")],
        [InlineKeyboardButton("➖ حذف ادمین", callback_data="admin_remove_admin")],
    ])
    
    await message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

async def handle_add_admin_input(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in waiting_for_add_admin:
        return
    
    waiting_for_add_admin.remove(user_id)
    
    try:
        new_admin_id = int(message.text.strip())
    except:
        await message.reply("❌ شناسه کاربری نامعتبر است. لطفاً یک عدد وارد کنید.")
        return
    
    if await is_admin(new_admin_id):
        await message.reply("⚠️ این کاربر در حال حاضر ادمین است.")
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, strftime('%s','now'))",
                        (new_admin_id, user_id))
        await db.commit()
    
    await message.reply(f"✅ کاربر `{new_admin_id}` با موفقیت به ادمین‌ها اضافه شد.", parse_mode=ParseMode.MARKDOWN)
    
    try:
        await client.send_message(
            new_admin_id,
            "🎉 **تبریک!** شما به عنوان ادمین ربات منصوب شدید.\n\n"
            "از منوی اصلی گزینه «⚙️ پنل مدیریت» را انتخاب کنید.",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass

async def handle_remove_admin_input(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in waiting_for_remove_admin:
        return
    
    waiting_for_remove_admin.remove(user_id)
    
    try:
        remove_admin_id = int(message.text.strip())
    except:
        await message.reply("❌ شناسه کاربری نامعتبر است. لطفاً یک عدد وارد کنید.")
        return
    
    if remove_admin_id == ADMIN_ID:
        await message.reply("❌ نمی‌توانید ادمین اصلی (مالک) را حذف کنید.")
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id=? AND user_id != ?", (remove_admin_id, ADMIN_ID))
        await db.commit()
    
    await message.reply(f"✅ کاربر `{remove_admin_id}` از ادمین‌ها حذف شد.", parse_mode=ParseMode.MARKDOWN)
    
    try:
        await client.send_message(
            remove_admin_id,
            "⚠️ شما از مدیریت ربات حذف شدید.",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass

# ------------------ Show Functions ------------------
async def show_price_list_message(client: Client, message: Message):
    if not await is_sales_open():
        await message.reply("🛑 فروش در حال حاضر بسته است. لطفاً بعداً امتحان کنید.")
        return
        
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, description, price FROM price_items ORDER BY id") as cursor:
            items = await cursor.fetchall()
    
    if not items:
        await message.reply("😕 در حال حاضر آیتمی برای فروش تعریف نشده است.")
        return
    
    buttons = []
    text = "📋 **لیست کانفیگ‌های موجود:**\n\n"
    for item in items:
        item_id, name, desc, price = item
        text += f"• {name} - {price:,} تومان\n"
        buttons.append([InlineKeyboardButton(f"خرید {name}", callback_data=f"buy_item_{item_id}")])
    
    await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

async def show_user_stats_message(client: Client, message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT referral_count, free_config_received, invite_link FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
    
    if row:
        count, received, link = row
        remaining = 25 - count
        if remaining < 0:
            remaining = 0
        text = (
            f"📊 **آمار دعوت شما:**\n\n"
            f"👥 تعداد دعوت شده: {count}\n"
            f"🎁 کانفیگ رایگان دریافت شده: {'✅ بله' if received else '❌ خیر'}\n"
            f"🎯 نیاز به {remaining} دعوت دیگر برای کانفیگ رایگان\n\n"
            f"🔗 لینک دعوت شما:\n`{link}`"
        )
    else:
        text = "اطلاعات یافت نشد."
    
    await message.reply(text, parse_mode=ParseMode.MARKDOWN)

async def show_invite_link(client: Client, message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT invite_link FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
    
    if row and row[0]:
        await message.reply(f"🔗 **لینک دعوت اختصاصی شما:**\n\n`{row[0]}`\n\n📤 این لینک را برای دوستان خود ارسال کنید.", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.reply("خطا در دریافت لینک. لطفاً /start را بزنید.")

async def show_user_configs(client: Client, message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT config_text, item_name, purchase_date FROM user_configs 
            WHERE user_id=? ORDER BY purchase_date DESC
        """, (user_id,)) as cursor:
            configs = await cursor.fetchall()
    
    if not configs:
        await message.reply("📭 شما هنوز هیچ کانفیگی خریداری یا دریافت نکرده‌اید.")
        return
    
    text = "🔐 **کانفیگ‌های شما:**\n\n"
    for i, (config, item_name, date) in enumerate(configs, 1):
        dt = datetime.fromtimestamp(date)
        text += f"**{i}. {item_name}**\n📅 تاریخ: {dt.strftime('%Y/%m/%d')}\n`{config}`\n\n{'─'*30}\n\n"
    
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.reply(part, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.reply(text, parse_mode=ParseMode.MARKDOWN)

# ------------------ Callback Handler ------------------
@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if not await check_channel_subscription(user_id) and user_id != ADMIN_ID:
        await callback_query.answer("⚠️ ابتدا عضو کانال شوید!", show_alert=True)
        return
    
    # Lottery callbacks
    if data == "lottery_pick_winner":
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        await pick_lottery_winner(client, callback_query)
    elif data == "lottery_view_participants":
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        await view_lottery_participants(client, callback_query)
    elif data == "lottery_clear":
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        await clear_lottery(client, callback_query)
    elif data == "lottery_winners_history":
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        await view_lottery_winners_history(client, callback_query)
    elif data.startswith("buy_item_"):
        if not await is_sales_open():
            await callback_query.answer("🛑 فروش بسته است.", show_alert=True)
            return
        item_id = int(data.split("_")[2])
        await start_purchase_process(client, callback_query, item_id)
    elif data.startswith("send_receipt_"):
        match = re.search(r"send_receipt_(\d+)", data)
        if match:
            item_id = int(match.group(1))
            await prompt_receipt(client, callback_query, item_id)
    elif data == "cancel_purchase":
        user_id = callback_query.from_user.id
        temp_purchases.pop(user_id, None)
        await callback_query.edit_message_text("❌ عملیات لغو شد.")
    elif data == "cancel_broadcast":
        if user_id in waiting_for_broadcast:
            waiting_for_broadcast.pop(user_id)
        await callback_query.edit_message_text("❌ ارسال پیام همگانی لغو شد.")
    elif data.startswith("confirm_"):
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        purchase_id = int(data.split("_")[1])
        await confirm_purchase(client, callback_query, purchase_id)
    elif data.startswith("reject_"):
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        purchase_id = int(data.split("_")[1])
        await reject_purchase(client, callback_query, purchase_id)
    elif data.startswith("admin_config_"):
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        action = data.split("_")[2]
        if action == "referral":
            await start_add_config_admin(client, callback_query, "referral")
        elif action == "item":
            await start_add_config_for_item(client, callback_query)
        elif action == "view":
            await view_configs(client, callback_query)
    elif data.startswith("config_for_item_"):
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        item_id = int(data.split("_")[3])
        await start_add_config_admin(client, callback_query, "item", item_id)
    elif data.startswith("delete_config_"):
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        config_id = int(data.split("_")[2])
        await delete_config(client, callback_query, config_id)
    elif data.startswith("admin_price_"):
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        action = data.split("_")[2]
        if action == "view":
            await view_prices(client, callback_query)
        elif action == "delete":
            price_id = int(data.split("_")[3])
            await delete_price(client, callback_query, price_id)
    elif data == "cancel_config_input":
        if user_id in waiting_for_config_input:
            waiting_for_config_input.pop(user_id, None)
        await callback_query.message.delete()
        await callback_query.answer("❌ عملیات لغو شد.", show_alert=False)
    elif data == "admin_add_price":
        if not await is_admin(user_id):
            await callback_query.answer("⛔️ دسترسی غیرمجاز", show_alert=True)
            return
        waiting_for_price_input.add(user_id)
        await callback_query.edit_message_text(
            "📝 لطفاً مشخصات آیتم جدید را به صورت زیر ارسال کنید:\n\n"
            "`نام | توضیحات | قیمت (تومان) | شماره کارت | نام صاحب کارت`\n\n"
            "مثال:\n"
            "`کانفیگ ۳۰ روزه | حجم ۵۰ گیگ | ۱۵۰۰۰۰ | 6037991234567890 | علی رضایی`",
            parse_mode=ParseMode.MARKDOWN
        )
    elif data == "admin_add_admin":
        if not await is_owner(user_id):
            await callback_query.answer("⛔️ فقط مالک ربات می‌تواند ادمین اضافه کند.", show_alert=True)
            return
        waiting_for_add_admin.add(user_id)
        await callback_query.edit_message_text(
            "➕ **افزودن ادمین جدید**\n\n"
            "لطفاً شناسه عددی (ID) کاربر را ارسال کنید:\n\n"
            "مثال: `123456789`",
            parse_mode=ParseMode.MARKDOWN
        )
    elif data == "admin_remove_admin":
        if not await is_owner(user_id):
            await callback_query.answer("⛔️ فقط مالک ربات می‌تواند ادمین حذف کند.", show_alert=True)
            return
        waiting_for_remove_admin.add(user_id)
        await callback_query.edit_message_text(
            "➖ **حذف ادمین**\n\n"
            "لطفاً شناسه عددی (ID) ادمین را ارسال کنید:\n\n"
            "مثال: `123456789`\n\n"
            "⚠️ توجه: مالک اصلی قابل حذف نیست.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await callback_query.answer()

# ------------------ Lottery Admin Functions ------------------
async def pick_lottery_winner(client: Client, callback_query: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        # Get all participants
        async with db.execute("SELECT user_id, first_name, username FROM lottery_participants") as cursor:
            participants = await cursor.fetchall()
        
        if not participants:
            await callback_query.answer("❌ هیچ شرکت‌کننده‌ای وجود ندارد!", show_alert=True)
            return
        
        # Pick random winner
        winner = random.choice(participants)
        winner_id, winner_name, winner_username = winner
        
        # Get available config
        config = await get_available_referral_config()
        
        if not config:
            await callback_query.answer("⚠️ کانفیگ رایگان موجود نیست!", show_alert=True)
            return
        
        config_id, config_text = config
        
        # Mark config as used
        await db.execute("UPDATE configs SET used=1, used_by=?, assigned_date=strftime('%s','now') WHERE id=?", (winner_id, config_id))
        
        # Save to user_configs
        await db.execute("""
            INSERT INTO user_configs (user_id, config_text, item_name, purchase_date)
            VALUES (?, ?, ?, strftime('%s','now'))
        """, (winner_id, config_text, "🎰 جایزه قرعه‌کشی"))
        
        # Mark winner in participants
        await db.execute("UPDATE lottery_participants SET is_winner=1 WHERE user_id=?", (winner_id,))
        
        # Save to winners history
        await db.execute("""
            INSERT INTO lottery_winners (user_id, config_text, win_date)
            VALUES (?, ?, strftime('%s','now'))
        """, (winner_id, config_text))
        
        await db.commit()
    
    winner_username_str = f"@{winner_username}" if winner_username else "بدون یوزرنیم"
    
    # Announce winner
    announcement = (
        f"🎉 **برنده قرعه‌کشی مشخص شد!** 🎉\n\n"
        f"👤 برنده: {winner_name} ({winner_username_str})\n"
        f"🆔 شناسه: `{winner_id}`\n\n"
        f"🎁 کانفیگ رایگان به برنده ارسال شد.\n"
        f"🙏 از همه شرکت‌کنندگان متشکریم!"
    )
    
    # Notify all admins
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM admins") as cursor:
            admins = await cursor.fetchall()
    
    for (admin_id,) in admins:
        try:
            await client.send_message(admin_id, announcement, parse_mode=ParseMode.MARKDOWN)
        except:
            pass
    
    # Notify winner
    try:
        await client.send_message(winner_id, f"🎉 **تبریک! شما برنده قرعه‌کشی شدید!**\n\n🔐 کانفیگ رایگان شما:\n\n`{config_text}`", parse_mode=ParseMode.MARKDOWN)
    except:
        pass
    
    await callback_query.answer("✅ برنده انتخاب و کانفیگ ارسال شد!", show_alert=True)

async def view_lottery_participants(client: Client, callback_query: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id, first_name, username, joined_at, is_winner 
            FROM lottery_participants 
            ORDER BY joined_at
        """) as cursor:
            participants = await cursor.fetchall()
    
    if not participants:
        await callback_query.edit_message_text("📭 هیچ شرکت‌کننده‌ای در قرعه‌کشی وجود ندارد.")
        return
    
    text = f"👥 **شرکت‌کنندگان قرعه‌کشی** ({len(participants)} نفر)\n\n"
    for p in participants[:50]:  # Show first 50
        uid, name, username, joined, is_winner = p
        username_str = f"@{username}" if username else "ندارد"
        winner_badge = " 🏆" if is_winner else ""
        dt = datetime.fromtimestamp(joined)
        text += f"• {name} ({username_str}){winner_badge}\n  🆔 `{uid}` | {dt.strftime('%H:%M')}\n"
    
    if len(participants) > 50:
        text += f"\n... و {len(participants) - 50} نفر دیگر"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="lottery_view_participants")]
    ])
    
    await callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def clear_lottery(client: Client, callback_query: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM lottery_participants")
        await db.commit()
    
    await callback_query.answer("✅ لیست شرکت‌کنندگان پاک شد.", show_alert=True)
    await callback_query.edit_message_text("🗑 لیست شرکت‌کنندگان قرعه‌کشی پاک شد.")

async def view_lottery_winners_history(client: Client, callback_query: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT lw.user_id, lw.config_text, lw.win_date, u.first_name, u.username
            FROM lottery_winners lw
            LEFT JOIN users u ON lw.user_id = u.user_id
            ORDER BY lw.win_date DESC
            LIMIT 20
        """) as cursor:
            winners = await cursor.fetchall()
    
    if not winners:
        await callback_query.edit_message_text("📜 هنوز برنده‌ای در قرعه‌کشی نداشته‌ایم.")
        return
    
    text = "📜 **تاریخچه برندگان قرعه‌کشی**\n\n"
    for w in winners:
        uid, config, date, name, username = w
        username_str = f"@{username}" if username else "ندارد"
        name_str = name or "ناشناس"
        dt = datetime.fromtimestamp(date)
        short_config = (config[:40] + "...") if len(config) > 40 else config
        text += f"🏆 {name_str} ({username_str})\n  🆔 `{uid}` | 📅 {dt.strftime('%Y/%m/%d')}\n  🔐 `{short_config}`\n\n"
    
    await callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

# ------------------ Purchase Process ------------------
async def start_purchase_process(client: Client, callback_query: CallbackQuery, item_id: int):
    user_id = callback_query.from_user.id
    item = await get_price_item(item_id)
    
    if not item:
        await callback_query.answer("آیتم نامعتبر", show_alert=True)
        return
    
    name, price, card_number, card_holder = item[1], item[3], item[4], item[5]
    temp_purchases[user_id] = item_id
    
    payment_text = (
        f"💰 **خرید {name}**\n\n"
        f"💳 **شماره کارت:** `{card_number}`\n"
        f"👤 **به نام:** {card_holder}\n"
        f"💵 **مبلغ:** {price:,} تومان\n\n"
        "📸 لطفاً عکس رسید را ارسال کنید.\n"
        "⏳ پس از تایید ادمین، کانفیگ ارسال خواهد شد."
    )
    
    await callback_query.message.delete()
    await client.send_message(
        user_id,
        payment_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 ارسال رسید", callback_data=f"send_receipt_{item_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data="cancel_purchase")]
        ])
    )

async def prompt_receipt(client: Client, callback_query: CallbackQuery, item_id: int):
    user_id = callback_query.from_user.id
    temp_purchases[user_id] = item_id
    
    await callback_query.edit_message_text(
        "📸 لطفاً عکس رسید پرداخت را ارسال کنید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ انصراف", callback_data="cancel_purchase")]
        ])
    )

@app.on_message(filters.private & filters.photo)
async def handle_receipt_photo(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not await check_channel_subscription(user_id) and user_id != ADMIN_ID:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 عضویت در کانال ۱", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
            [InlineKeyboardButton("📢 عضویت در کانال ۲", url=f"https://t.me/{REQUIRED_CHANNEL_2[1:]}")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_subscription")]
        ])
        await message.reply(
            f"⚠️ برای استفاده از ربات باید عضو هر دو کانال زیر باشید:\n\n"
            f"📢 ۱. {REQUIRED_CHANNEL}\n"
            f"📢 ۲. {REQUIRED_CHANNEL_2}",
            reply_markup=keyboard
        )
        return
    
    if not await is_sales_open():
        await message.reply("🛑 فروش در حال حاضر بسته است. رسید شما ثبت نشد.")
        return
    
    if user_id in waiting_for_price_input or user_id in waiting_for_config_input or user_id in waiting_for_broadcast:
        return
    
    if user_id not in temp_purchases:
        await message.reply("⚠️ درخواست فعالی برای خرید ندارید. لطفاً دوباره اقدام کنید.")
        return
    
    item_id = temp_purchases[user_id]
    photo_id = message.photo.file_id
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO pending_purchases (user_id, item_id, receipt_photo_id, status, created_at)
            VALUES (?, ?, ?, 'pending', strftime('%s','now'))
        """, (user_id, item_id, photo_id))
        await db.commit()
        purchase_id = await db.execute("SELECT last_insert_rowid()")
        purchase_id = (await purchase_id.fetchone())[0]
    
    user_info = await get_user(user_id)
    username = f"@{user_info[1]}" if user_info[1] else "بدون نام کاربری"
    item = await get_price_item(item_id)
    
    admin_text = (
        f"🛒 **درخواست خرید جدید**\n\n"
        f"👤 کاربر: [{user_info[2]}](tg://user?id={user_id}) ({username})\n"
        f"🆔 شناسه: `{user_id}`\n"
        f"📦 آیتم: {item[1]}\n"
        f"💵 مبلغ: {item[3]:,} تومان\n\n"
        "✅ تایید میکنید؟"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید", callback_data=f"confirm_{purchase_id}")],
        [InlineKeyboardButton("❌ رد", callback_data=f"reject_{purchase_id}")]
    ])
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM admins") as cursor:
            admins = await cursor.fetchall()
        for (admin_id,) in admins:
            try:
                await client.send_photo(
                    admin_id,
                    photo_id,
                    caption=admin_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    await message.reply(
        "📨 رسید شما دریافت شد. پس از تایید ادمین، کانفیگ ارسال خواهد شد."
    )
    
    del temp_purchases[user_id]

# ------------------ Admin Message Handlers ------------------
async def admin_stats_message(client: Client, message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        total_users = await db.execute("SELECT COUNT(*) FROM users")
        total_users = (await total_users.fetchone())[0]
        
        total_configs_referral = await db.execute("SELECT COUNT(*) FROM configs WHERE type='referral' AND used=0")
        total_configs_referral = (await total_configs_referral.fetchone())[0]
        
        total_configs_item = await db.execute("SELECT COUNT(*) FROM configs WHERE type='item' AND used=0")
        total_configs_item = (await total_configs_item.fetchone())[0]
        
        total_sold = await db.execute("SELECT COUNT(*) FROM pending_purchases WHERE status='confirmed'")
        total_sold = (await total_sold.fetchone())[0]
        
        total_admins = await db.execute("SELECT COUNT(*) FROM admins")
        total_admins = (await total_admins.fetchone())[0]
        
        lottery_participants = await db.execute("SELECT COUNT(*) FROM lottery_participants")
        lottery_participants = (await lottery_participants.fetchone())[0]
        
        text = (
            f"📊 **آمار ربات**\n\n"
            f"👥 تعداد کاربران: {total_users}\n"
            f"👨‍💼 تعداد ادمین‌ها: {total_admins}\n"
            f"🎁 کانفیگ‌های رایگان موجود: {total_configs_referral}\n"
            f"💰 کانفیگ‌های فروشی موجود: {total_configs_item}\n"
            f"✅ فروش موفق: {total_sold}\n"
            f"🎰 شرکت‌کنندگان قرعه‌کشی: {lottery_participants}\n"
        )
    
    await message.reply(text, parse_mode=ParseMode.MARKDOWN)

async def manage_prices_message(client: Client, message: Message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن آیتم جدید", callback_data="admin_add_price")],
        [InlineKeyboardButton("📋 مشاهده قیمت‌ها", callback_data="admin_price_view")],
    ])
    
    await message.reply(
        "💰 **مدیریت قیمت‌ها**\n\nعملیات مورد نظر را انتخاب کنید:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def manage_configs_message(client: Client, message: Message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن کانفیگ رایگان", callback_data="admin_config_referral")],
        [InlineKeyboardButton("➕ افزودن کانفیگ فروشی", callback_data="admin_config_item")],
        [InlineKeyboardButton("📋 مشاهده کانفیگ‌ها", callback_data="admin_config_view")],
    ])
    
    await message.reply(
        "🔐 **مدیریت کانفیگ‌ها**\n\nنوع عملیات را انتخاب کنید:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def show_pending_purchases_message(client: Client, message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT pp.id, u.first_name, u.user_id, pi.name, pi.price 
            FROM pending_purchases pp
            JOIN users u ON pp.user_id = u.user_id
            JOIN price_items pi ON pp.item_id = pi.id
            WHERE pp.status = 'pending'
        """) as cursor:
            pendings = await cursor.fetchall()
    
    if not pendings:
        await message.reply("📭 درخواست در انتظاری وجود ندارد.")
        return
    
    text = "🧾 **درخواست‌های در انتظار:**\n\n"
    for p in pendings:
        text += f"🆔 خرید {p[0]} - {p[1]} ({p[2]}) - {p[3]} - {p[4]:,} تومان\n"
    text += "\n👆 برای تایید/رد به پیام مربوطه مراجعه کنید."
    
    await message.reply(text, parse_mode=ParseMode.MARKDOWN)

async def show_users_list_message(client: Client, message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id, first_name, username, referral_count, free_config_received, is_blocked
            FROM users ORDER BY join_date DESC LIMIT 20
        """) as cursor:
            users = await cursor.fetchall()
    
    text = "👥 **آخرین کاربران:**\n\n"
    for u in users:
        username = f"@{u[2]}" if u[2] else "ندارد"
        free_config = "✅" if u[4] else "❌"
        blocked = " 🚫" if u[5] else ""
        text += f"🆔 `{u[0]}` - {u[1]} ({username}){blocked}\n   👥 دعوت: {u[3]} | 🎁 رایگان: {free_config}\n"
    
    await message.reply(text, parse_mode=ParseMode.MARKDOWN)

# ------------------ View / Delete Configs ------------------
async def view_configs(client: Client, callback_query: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT c.id, c.type, c.item_id, c.used, 
                   CASE WHEN c.type='item' THEN pi.name ELSE 'رایگان' END as item_name,
                   c.config_text
            FROM configs c
            LEFT JOIN price_items pi ON c.item_id = pi.id
            ORDER BY c.id
        """) as cursor:
            configs = await cursor.fetchall()
    
    if not configs:
        await callback_query.edit_message_text("📭 هیچ کانفیگی ذخیره نشده است.")
        return
    
    text = "📋 **کانفیگ‌های موجود:**\n\n"
    buttons = []
    for conf in configs:
        cid, ctype, item_id, used, item_name, config_text = conf
        used_icon = "✅" if used else "❌"
        short_config = (config_text[:30] + "...") if len(config_text) > 30 else config_text
        text += f"🆔 `{cid}` | {used_icon} | {ctype} | {item_name}\n`{short_config}`\n\n"
        buttons.append([InlineKeyboardButton(f"🗑 حذف {cid} - {item_name}", callback_data=f"delete_config_{cid}")])
    
    buttons.append([InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_config_view")])
    
    if len(text) > 4000:
        await callback_query.edit_message_text(text[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))

async def delete_config(client: Client, callback_query: CallbackQuery, config_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM configs WHERE id=?", (config_id,))
        await db.commit()
    await callback_query.answer("✅ کانفیگ حذف شد.", show_alert=True)
    await view_configs(client, callback_query)

# ------------------ View / Delete Prices ------------------
async def view_prices(client: Client, callback_query: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, description, price, card_number, card_holder FROM price_items ORDER BY id") as cursor:
            items = await cursor.fetchall()
    
    if not items:
        await callback_query.edit_message_text("💰 هیچ آیتم قیمتی تعریف نشده است.")
        return
    
    text = "💰 **آیتم‌های قیمتی:**\n\n"
    buttons = []
    for item in items:
        pid, name, desc, price, card, holder = item
        text += f"🆔 `{pid}` | {name} | {price:,} تومان\n   💳 {card} ({holder})\n\n"
        buttons.append([InlineKeyboardButton(f"🗑 حذف {pid} - {name}", callback_data=f"admin_price_delete_{pid}")])
    
    buttons.append([InlineKeyboardButton("➕ افزودن آیتم جدید", callback_data="admin_add_price")])
    buttons.append([InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_price_view")])
    
    await callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))

async def delete_price(client: Client, callback_query: CallbackQuery, price_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM configs WHERE item_id=?", (price_id,))
        await db.execute("DELETE FROM price_items WHERE id=?", (price_id,))
        await db.commit()
    await callback_query.answer("✅ آیتم و کانفیگ‌های مرتبط حذف شد.", show_alert=True)
    await view_prices(client, callback_query)

# ------------------ Config Management ------------------
async def start_add_config_admin(client: Client, callback_query: CallbackQuery, config_type: str, item_id: int = None):
    user_id = callback_query.from_user.id
    waiting_for_config_input[user_id] = {"type": config_type, "item_id": item_id}
    
    if config_type == "item":
        item = await get_price_item(item_id)
        text = f"🔐 لطفاً کانفیگ مربوط به **{item[1]}** را ارسال کنید:\n\n`(متن کانفیگ V2Ray)`"
    else:
        text = "🎁 لطفاً کانفیگ رایگان (جایزه دعوت) را ارسال کنید:\n\n`(متن کانفیگ V2Ray)`"
    
    await callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    await callback_query.message.reply(
        text + "\n\n⚠️ پیام بعدی شما به عنوان کانفیگ ثبت خواهد شد.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ لغو", callback_data="cancel_config_input")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

async def start_add_config_for_item(client: Client, callback_query: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name FROM price_items") as cursor:
            items = await cursor.fetchall()
    
    if not items:
        await callback_query.answer("ابتدا باید آیتم قیمت تعریف کنید!", show_alert=True)
        return
    
    buttons = []
    for item in items:
        buttons.append([InlineKeyboardButton(f"📦 {item[1]}", callback_data=f"config_for_item_{item[0]}")])
    
    await callback_query.edit_message_text(
        "📦 **برای کدام آیتم کانفیگ اضافه می‌کنید؟**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_price_input(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in waiting_for_price_input:
        return
    
    waiting_for_price_input.remove(user_id)
    
    parts = message.text.split("|")
    if len(parts) != 5:
        await message.reply("❌ فرمت اشتباه! دوباره تلاش کنید.\nفرمت صحیح: `نام | توضیحات | قیمت (تومان) | شماره کارت | نام صاحب کارت`", parse_mode=ParseMode.MARKDOWN)
        return
    name, desc, price_str, card, holder = [p.strip() for p in parts]
    try:
        price = int(price_str.replace(",", "").replace("،", ""))
    except:
        await message.reply("❌ مبلغ باید عدد باشد.")
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO price_items (name, description, price, card_number, card_holder)
            VALUES (?, ?, ?, ?, ?)
        """, (name, desc, price, card, holder))
        await db.commit()
    
    await message.reply("✅ آیتم جدید با موفقیت اضافه شد.")

async def handle_config_input(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in waiting_for_config_input:
        return
    
    config_info = waiting_for_config_input.pop(user_id)
    config_text = message.text.strip()
    
    async with aiosqlite.connect(DB_PATH) as db:
        if config_info["type"] == "referral":
            await db.execute("INSERT INTO configs (config_text, type, used) VALUES (?, 'referral', 0)", (config_text,))
        else:
            await db.execute("INSERT INTO configs (config_text, type, item_id, used) VALUES (?, 'item', ?, 0)", 
                           (config_text, config_info["item_id"]))
        await db.commit()
    
    await message.reply("✅ کانفیگ جدید با موفقیت اضافه شد.")

# ------------------ Confirm/Reject Purchase ------------------
async def confirm_purchase(client: Client, callback_query: CallbackQuery, purchase_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id, item_id, receipt_photo_id FROM pending_purchases WHERE id=?
        """, (purchase_id,)) as cursor:
            purchase = await cursor.fetchone()
        if not purchase:
            await callback_query.answer("درخواست یافت نشد", show_alert=True)
            return
        user_id, item_id, photo_id = purchase
        
        config = await get_available_config_for_item(item_id)
        if config:
            config_id, config_text = config
            item = await get_price_item(item_id)
            
            await db.execute("UPDATE configs SET used=1, used_by=?, assigned_date=strftime('%s','now') WHERE id=?", (user_id, config_id))
            await db.execute("UPDATE pending_purchases SET status='confirmed' WHERE id=?", (purchase_id,))
            
            await db.execute("""
                INSERT INTO user_configs (user_id, config_text, item_name, purchase_date)
                VALUES (?, ?, ?, strftime('%s','now'))
            """, (user_id, config_text, item[1]))
            
            await db.commit()
            
            try:
                await client.send_message(user_id, f"✅ پرداخت شما تایید شد.\n🔐 کانفیگ خریداری شده:\n\n`{config_text}`")
            except:
                pass
            await callback_query.edit_message_caption(
                caption=callback_query.message.caption + "\n\n✅ **تایید شد و کانفیگ ارسال گردید.**",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback_query.answer("⚠️ کانفیگی برای این آیتم موجود نیست!", show_alert=True)
            await callback_query.edit_message_caption(
                caption=callback_query.message.caption + "\n\n⚠️ **هشدار:** کانفیگ موجود نیست.",
                parse_mode=ParseMode.MARKDOWN
            )

async def reject_purchase(client: Client, callback_query: CallbackQuery, purchase_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM pending_purchases WHERE id=?", (purchase_id,)) as cursor:
            row = await cursor.fetchone()
            user_id = row[0] if row else None
        await db.execute("UPDATE pending_purchases SET status='rejected' WHERE id=?", (purchase_id,))
        await db.commit()
    
    if user_id:
        try:
            await client.send_message(user_id, "❌ متاسفانه پرداخت شما تایید نشد. در صورت نیاز با پشتیبانی تماس بگیرید.")
        except:
            pass
    await callback_query.edit_message_caption(
        caption=callback_query.message.caption + "\n\n❌ **رد شد.**",
        parse_mode=ParseMode.MARKDOWN
    )

# ------------------ Run ------------------
async def main():
    await init_db()
    await app.start()
    logger.info("Bot started...")
    logger.info("Welcome to کانفیگ فروشی رافو!")
    logger.info(f"Owner ID: {ADMIN_ID}")
    logger.info("Features: Sales, Lottery, Broadcast, Multiple Admins")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())