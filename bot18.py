import logging
import sqlite3
import os
import json
import re
import io
import base64
import tempfile
import subprocess
import shutil
import urllib.parse
from datetime import datetime, date

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, FSInputFile
import asyncio

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

try:
    from mutagen.id3 import ID3, TIT2, TPE1
    from mutagen.mp3 import MP3
except ImportError:
    ID3 = TIT2 = TPE1 = MP3 = None

try:
    from aiogram.enums import ButtonStyle as _RealButtonStyle
    class ButtonStyle:
        PRIMARY = _RealButtonStyle.PRIMARY
        DANGER  = _RealButtonStyle.DANGER
        SUCCESS = _RealButtonStyle.SUCCESS
        DEFAULT = None
except Exception:
    class ButtonStyle:
        PRIMARY = "primary"
        DANGER  = "danger"
        SUCCESS = "success"
        DEFAULT = None
    _orig_ikb_init = InlineKeyboardButton.__init__
    def _patched_ikb_init(self, **kwargs):
        kwargs.pop("style", None)
        _orig_ikb_init(self, **kwargs)
    InlineKeyboardButton.__init__ = _patched_ikb_init

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== تنظیمات ====================
BOT_TOKEN        = "8673188458:AAHz79xyhX0v3R-ckUNMw-dGK-HawrUB0LQ"
SUPER_ADMIN_IDS  = [8478999016, 6189730344]   # ادمین‌های اصلی - دسترسی کامل
COINS_PER_REFERRAL  = 1
COINS_TO_GET_CONFIG = 3
GEMINI_API_KEY   = "AIzaSyCyyipjH2hBzXMakEwCcMaTfeIOF14aawk"
GEMINI_TEXT_MODEL  = "gemini-2.5-flash"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image-preview"

_BASE_DIR   = "/storage/emulated/0/coinsfil" if os.path.exists("/storage/emulated/0") else os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(_BASE_DIR, "bot.db")
STATUS_FILE = os.path.join(_BASE_DIR, "bot_status.json")

ALL_PERMS = ["toggle_bot", "stats", "users", "add_config", "broadcast", "coins", "channels", "support_id", "texts", "buttons", "colors"]
PERM_NAMES = {
    "toggle_bot": "🔴🟢 خاموش/روشن ربات",
    "stats":      "📊 آمار کلی",
    "users":      "👥 لیست کاربران",
    "add_config": "➕ افزودن کانفیگ",
    "broadcast":  "📢 ارسال همگانی",
    "coins":      "💰 مدیریت سکه",
    "channels":   "📡 مدیریت چنل‌ها",
    "support_id": "🛟 تنظیم پشتیبانی",
    "texts":      "✏️ مدیریت متن‌ها",
    "buttons":    "🔘 مدیریت دکمه‌ها",
    "colors":     "🎨 تنظیم رنگ دکمه‌ها",
}

# ==================== کانفیگ ====================
DEFAULT_TEXTS = {
    "start": "🔐 با هر بار دعوت یه دوست = 1 سکه 🪙\n🎁 با 3 سکه → یه اتصال رایگان دریافت کن!\n━━━━━━━━━━━━━━━\n\nاز منوی پایین شروع کن 👇",
    "join_required": "❌ برای استفاده از ربات باید در کانال ما عضو بشی:",
    "join_required_short": "❌ برای استفاده باید عضو کانال باشی:",
    "not_joined": "❌ هنوز عضو نشدی!",
    "help": "⚠️ راهنمای استفاده از ربات\n━━━━━━━━━━━━━━━\n\n1️⃣ لینک دعوت خودتو از بخش «لینک دعوت» بگیر\n2️⃣ لینکتو برای دوستات بفرست\n3️⃣ به ازای هر دوست = 1 سکه 🪙 می‌گیری\n4️⃣ با 3 سکه → یه اتصال رایگان دریافت کن!",
    "support": "🟢 پشتیبانی\n━━━━━━━━━━━━━━━\n\n📌 در چه مواردی کمک می‌کنیم:\n• مشکل در دریافت کانفیگ\n• مشکل در لینک دعوت\n• اشکال در عملکرد ربات\n\n❌ موارد پشتیبانی نمی‌شه:\n• درخواست کانفیگ رایگان بدون سکه\n• مشکلات اینترنت شخصی\n\n━━━━━━━━━━━━━━━\nنوع درخواست:",
    "sponsor_prompt": "💼 درخواست اسپانسر\n━━━━━━━━━━━━━━━\n\nپیام خود را برای اسپانسر شدن بنویسید:\n\n💡 لطفاً ذکر کنید:\n• معرفی کانال/گروه\n• تعداد اعضا\n• نوع همکاری\n\nپیام خود را ارسال کنید 👇",
    "support_question_prompt": "❓ سوال / مشکل\n━━━━━━━━━━━━━━━\n\nسوال یا مشکل خود را بنویسید 👇",
}

TEXT_NAMES = {
    "start": "متن شروع / منوی اصلی",
    "join_required": "متن الزام عضویت",
    "join_required_short": "متن الزام عضویت کوتاه",
    "not_joined": "متن هنوز عضو نشدی",
    "help": "متن راهنما",
    "support": "متن پشتیبانی",
    "sponsor_prompt": "متن درخواست اسپانسر",
    "support_question_prompt": "متن سوال / مشکل",
}

DEFAULT_BUTTONS = {
    "main_get_config": "اتصال رایگان 🤩",
    "main_my_configs": "کانفیگ‌های من 📦",
    "main_account": "حساب من 👤",
    "main_referral": "لینک دعوت 🔗",
    "main_support": "پشتیبانی 🟢",
    "main_help": "راهنما 📖",
    "main_admin": "🛠 پنل مدیریت",
    "admin_toggle_on": "🟢 ربات روشن | خاموش کن",
    "admin_toggle_off": "🔴 ربات خاموش | روشن کن",
    "admin_support": "🛟 پشتیبانی:",
    "admin_stats": "📊 آمار کلی",
    "admin_users": "👥 لیست کاربران",
    "admin_add_config": "➕ افزودن کانفیگ",
    "admin_broadcast": "📢 ارسال همگانی",
    "admin_addcoins": "💰 انتقال سکه",
    "admin_subcoins": "➖ کسر سکه",
    "admin_channels": "📡 مدیریت چنل‌ها",
    "admin_texts": "✏️ مدیریت متن‌ها",
    "admin_buttons": "🔘 مدیریت دکمه‌ها",
    "admin_manage_admins": "👤 مدیریت ادمین‌ها",
    "admin_ban_direct": "🚫 بن کاربر",
    "admin_unban_direct": "🔓 آنبن کاربر",
    "admin_banlist": "📋 لیست بن‌ها",
    "back_main": "🔙 بازگشت",
    "back_panel": "🔙 بازگشت به پنل",
    "cancel": "❌ لغو",
    "cancel_action": "❌ انصراف",
    "check_join": "✅ عضو شدم",
    "join_channel": "عضویت در",
    "ban_user": "🚫 بن کاربر",
    "unban_user": "🔓 آنبن کاربر",
    "msg_user": "✉️ پیام به کاربر",
    "send_coin_user": "➕ فرستادن سکه",
    "sub_coin_user": "➖ کسر سکه",
    "delete_admin": "🗑 حذف این ادمین",
    "get_referral": "🔗 دریافت لینک رفرال",
    "support_sponsor": "💼 اسپانسر",
    "support_question": "❓ سوالات غیر اسپانسری",
    "bot_off": "🔴 خاموش",
    "bot_on": "🟢 روشن",
    "prev_page": "◀️ قبلی",
    "next_page": "بعدی ▶️",
    "add_channel": "➕ اضافه کردن چنل",
    "delete_channel": "🗑 حذف",
    "add_admin": "➕ اضافه کردن ادمین",
    "broadcast_pin": "📌 ارسال + پین",
    "broadcast_send": "📤 فقط ارسال",
    "confirm_unban": "✅ تایید آنبن",
    "main_special": "✨ امکانات ویژه",
    "sf_like_maker": "👍 لایک ساز",
    "sf_ai": "🤖 هوش مصنوعی",
    "sf_downloader": "📥 دانلودر ویدیو",
    "sf_music": "🎵 موسیقی MP3",
    "sf_logo_maker": "🎨 ساخت لوگو",
    "sf_voice_to_mp3": "🎙 ویس به MP3",
    "dl_tiktok": "🎵 تیک تاک",
    "dl_instagram": "📸 اینستاگرام",
    "dl_youtube": "▶️ یوتوب",
    "dl_twitter": "🐦 توییتر / X",
    "like_btn": "♥️",
    "admin_colors": "🎨 تنظیم رنگ دکمه‌ها",
    "color_red": "🔴 قرمز",
    "color_green": "🟢 سبز",
    "color_blue": "🔵 آبی",
    "color_default": "⚪ معمولی (شیشه‌ای)",
}

BUTTON_NAMES = {
    "main_get_config": "دکمه اتصال رایگان",
    "main_my_configs": "دکمه کانفیگ‌های من",
    "main_account": "دکمه حساب من",
    "main_referral": "دکمه لینک دعوت",
    "main_support": "دکمه پشتیبانی",
    "main_help": "دکمه راهنما",
    "main_admin": "دکمه پنل مدیریت",
    "admin_toggle_on": "دکمه وضعیت ربات وقتی روشن است",
    "admin_toggle_off": "دکمه وضعیت ربات وقتی خاموش است",
    "admin_support": "دکمه تنظیم پشتیبانی",
    "admin_stats": "دکمه آمار کلی",
    "admin_users": "دکمه لیست کاربران",
    "admin_add_config": "دکمه افزودن کانفیگ",
    "admin_broadcast": "دکمه ارسال همگانی",
    "admin_addcoins": "دکمه انتقال سکه",
    "admin_subcoins": "دکمه کسر سکه",
    "admin_channels": "دکمه مدیریت چنل‌ها",
    "admin_texts": "دکمه مدیریت متن‌ها",
    "admin_buttons": "دکمه مدیریت دکمه‌ها",
    "admin_manage_admins": "دکمه مدیریت ادمین‌ها",
    "admin_ban_direct": "دکمه بن کاربر در پنل",
    "admin_unban_direct": "دکمه آنبن کاربر در پنل",
    "admin_banlist": "دکمه لیست بن‌ها",
    "back_main": "دکمه بازگشت",
    "back_panel": "دکمه بازگشت به پنل",
    "cancel": "دکمه لغو",
    "cancel_action": "دکمه انصراف",
    "check_join": "دکمه عضو شدم",
    "join_channel": "دکمه عضویت در کانال",
    "ban_user": "دکمه بن کاربر",
    "unban_user": "دکمه آنبن کاربر",
    "msg_user": "دکمه پیام به کاربر",
    "send_coin_user": "دکمه فرستادن سکه",
    "sub_coin_user": "دکمه کسر سکه از کاربر",
    "delete_admin": "دکمه حذف ادمین",
    "get_referral": "دکمه دریافت لینک رفرال",
    "support_sponsor": "دکمه اسپانسر",
    "support_question": "دکمه سوالات غیر اسپانسری",
    "bot_off": "دکمه خاموش کردن",
    "bot_on": "دکمه روشن کردن",
    "prev_page": "دکمه صفحه قبلی",
    "next_page": "دکمه صفحه بعدی",
    "add_channel": "دکمه اضافه کردن چنل",
    "delete_channel": "دکمه حذف چنل",
    "add_admin": "دکمه اضافه کردن ادمین",
    "broadcast_pin": "دکمه ارسال همگانی + پین",
    "broadcast_send": "دکمه ارسال همگانی بدون پین",
    "confirm_unban": "دکمه تایید آنبن",
    "main_special": "دکمه امکانات ویژه",
    "sf_like_maker": "دکمه لایک ساز",
    "sf_ai": "دکمه هوش مصنوعی",
    "sf_downloader": "دکمه دانلودر ویدیو",
    "sf_music": "دکمه موسیقی MP3",
    "sf_logo_maker": "دکمه ساخت لوگو",
    "sf_voice_to_mp3": "دکمه ویس به MP3",
    "dl_tiktok": "دکمه دانلود تیک تاک",
    "dl_instagram": "دکمه دانلود اینستاگرام",
    "dl_youtube": "دکمه دانلود یوتوب",
    "dl_twitter": "دکمه دانلود توییتر",
    "like_btn": "دکمه لایک پست",
    "admin_colors": "دکمه تنظیم رنگ دکمه‌ها در پنل",
}

# ==================== رنگ پیش‌فرض دکمه‌ها ====================
DEFAULT_BUTTON_COLORS = {
    "main_get_config": "primary",
    "main_account": "danger",
    "main_referral": "danger",
    "main_my_configs": "primary",
    "main_special": "primary",
    "main_support": "success",
    "main_help": "success",
    "main_admin": "default",
    "sf_like_maker": "primary",
    "sf_ai": "primary",
    "sf_downloader": "danger",
    "sf_music": "danger",
    "sf_logo_maker": "success",
    "sf_voice_to_mp3": "success",
    "dl_tiktok": "default",
    "dl_instagram": "default",
    "dl_youtube": "default",
    "dl_twitter": "default",
    "like_btn": "success",
    "support_sponsor": "primary",
    "support_question": "success",
    "delete_admin": "danger",
    "delete_channel": "danger",
    "add_channel": "success",
    "add_admin": "success",
    "broadcast_pin": "primary",
    "broadcast_send": "success",
    "confirm_unban": "danger",
    "join_channel": "danger",
    "check_join": "success",
}

def load_config() -> dict:
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["texts"] = {**DEFAULT_TEXTS, **data.get("texts", {})}
                data["buttons"] = {**DEFAULT_BUTTONS, **data.get("buttons", {})}
                data["colors"] = {**DEFAULT_BUTTON_COLORS, **data.get("colors", {})}
                data.setdefault("like_posts", {})
                return data
    except:
        pass
    return {"enabled": True, "support_id": "", "channels": ["@v2ray_404"], "sub_admins": {},
            "texts": DEFAULT_TEXTS.copy(), "buttons": DEFAULT_BUTTONS.copy(),
            "colors": DEFAULT_BUTTON_COLORS.copy(), "like_posts": {}}

def save_config(data: dict):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except:
        pass

_config      = load_config()
BOT_ENABLED  = _config.get("enabled", True)
SUPPORT_ID   = _config.get("support_id", "")
CHANNEL_IDS: list = _config.get("channels", ["@v2ray_404"])
SUB_ADMINS: dict  = _config.get("sub_admins", {})
BOT_TEXTS: dict    = {**DEFAULT_TEXTS, **_config.get("texts", {})}
BOT_BUTTONS: dict  = {**DEFAULT_BUTTONS, **_config.get("buttons", {})}
BOT_COLORS: dict   = {**DEFAULT_BUTTON_COLORS, **_config.get("colors", {})}
LIKE_POSTS: dict   = _config.get("like_posts", {})

_COLOR_TO_STYLE = {
    "primary": ButtonStyle.PRIMARY,
    "danger":  ButtonStyle.DANGER,
    "success": ButtonStyle.SUCCESS,
    "default": ButtonStyle.DEFAULT,
}

def get_btn_color(key: str) -> str:
    return BOT_COLORS.get(key, DEFAULT_BUTTON_COLORS.get(key, "default"))

def style_of(key: str):
    return _COLOR_TO_STYLE.get(get_btn_color(key), ButtonStyle.DEFAULT)

def save_btn_color(key: str, color: str):
    BOT_COLORS[key] = color
    cfg = load_config(); cfg["colors"] = BOT_COLORS; save_config(cfg)

def save_like_posts():
    cfg = load_config(); cfg["like_posts"] = LIKE_POSTS; save_config(cfg)

def get_bot_text(key: str) -> str:
    return BOT_TEXTS.get(key, DEFAULT_TEXTS.get(key, ""))

def save_bot_text(key: str, value: str):
    BOT_TEXTS[key] = value
    cfg = load_config()
    cfg["texts"] = BOT_TEXTS
    save_config(cfg)

def get_button_text(key: str) -> str:
    return BOT_BUTTONS.get(key, DEFAULT_BUTTONS.get(key, ""))

def save_button_text(key: str, value: str):
    BOT_BUTTONS[key] = value
    cfg = load_config()
    cfg["buttons"] = BOT_BUTTONS
    save_config(cfg)

# ==================== توابع دسترسی ====================
def is_any_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS or str(user_id) in SUB_ADMINS

def is_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS

def has_perm(user_id: int, perm: str) -> bool:
    if user_id in SUPER_ADMIN_IDS:
        return True
    perms = SUB_ADMINS.get(str(user_id), {})
    return perms.get(perm, False)

# ==================== FSM States ====================
class AdminStates(StatesGroup):
    waiting_config_count = State()
    waiting_config_item  = State()
    broadcast            = State()
    broadcast_choose_pin = State()
    add_coins_id         = State()
    add_coins_amount     = State()
    sub_coins_id         = State()
    sub_coins_amount     = State()
    msg_user_text        = State()
    set_support_id       = State()
    add_channel          = State()
    add_admin_id         = State()
    edit_bot_text        = State()
    edit_button_text     = State()
    ban_direct_id        = State()
    unban_direct_id      = State()

class SpecialStates(StatesGroup):
    like_link            = State()
    like_name            = State()
    ai_chat              = State()
    dl_link              = State()
    music_query          = State()
    logo_name            = State()
    voice_title          = State()

class UserStates(StatesGroup):
    sponsor_msg  = State()
    support_msg  = State()

# ==================== دیتابیس ====================
def init_db():
    if os.path.dirname(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        coins INTEGER DEFAULT 0, referred_by INTEGER DEFAULT NULL,
        join_date TEXT, is_banned INTEGER DEFAULT 0, configs_received INTEGER DEFAULT 0,
        referral_credited INTEGER DEFAULT 0)""")
    try:
        c.execute("ALTER TABLE users ADD COLUMN referral_credited INTEGER DEFAULT 0")
    except:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL,
        is_used INTEGER DEFAULT 0, used_by INTEGER DEFAULT NULL, used_at TEXT DEFAULT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER DEFAULT 0)""")
    for key in ("total_users", "configs_given", "total_referrals"):
        c.execute("INSERT OR IGNORE INTO stats (key, value) VALUES (?, 0)", (key,))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone(); conn.close(); return row

def add_user(user_id, username, full_name, referred_by=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO users
        (user_id, username, full_name, coins, referred_by, join_date, is_banned, configs_received)
        VALUES (?, ?, ?, 0, ?, ?, 0, 0)""",
        (user_id, username, full_name, referred_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    inserted = c.rowcount; conn.commit(); conn.close(); return inserted == 1

def get_all_users_paginated(page, per_page=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, full_name, coins, is_banned, configs_received FROM users LIMIT ? OFFSET ?",
              (per_page, page * per_page))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]; conn.close(); return rows, total

def get_banned_users_paginated(page, per_page=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, full_name, coins FROM users WHERE is_banned = 1 LIMIT ? OFFSET ?",
              (per_page, page * per_page))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    total = c.fetchone()[0]; conn.close(); return rows, total

def get_user_detail(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT user_id, username, full_name, coins, is_banned, configs_received,
               (SELECT COUNT(*) FROM users WHERE referred_by = ?) FROM users WHERE user_id = ?""",
               (user_id, user_id))
    row = c.fetchone(); conn.close(); return row

def get_user_configs(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, content, used_at FROM configs WHERE used_by = ? ORDER BY id DESC", (user_id,))
    rows = c.fetchall(); conn.close(); return rows

def update_coins(user_id, delta):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET coins = MAX(0, coins + ?) WHERE user_id = ?", (delta, user_id))
    conn.commit(); conn.close()

def db_ban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
    affected = c.rowcount
    conn.commit(); conn.close()
    return affected

def db_unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
    affected = c.rowcount
    conn.commit(); conn.close()
    return affected

def get_stat(key):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM stats WHERE key = ?", (key,))
    row = c.fetchone(); conn.close(); return row[0] if row else 0

def increment_stat(key, amount=1):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO stats (key, value) VALUES (?, 0)", (key,))
    c.execute("UPDATE stats SET value = value + ? WHERE key = ?", (amount, key))
    conn.commit(); conn.close()

def get_free_config():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, content FROM configs WHERE is_used = 0 LIMIT 1")
    row = c.fetchone(); conn.close(); return row

def mark_config_used(config_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE configs SET is_used=1, used_by=?, used_at=? WHERE id=?",
              (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), config_id))
    c.execute("UPDATE users SET configs_received=configs_received+1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()

def add_config(content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO configs (content) VALUES (?)", (content.strip(),))
    conn.commit(); conn.close()

def get_referral_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
    count = c.fetchone()[0]; conn.close(); return count

def credit_referral(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT referred_by, referral_credited FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row or not row[0] or row[1]:
        conn.close()
        return None
    referred_by = row[0]
    ref_user_row = c.execute("SELECT is_banned FROM users WHERE user_id = ?", (referred_by,)).fetchone()
    if not ref_user_row or ref_user_row[0]:
        conn.close()
        return None
    c.execute("UPDATE users SET referral_credited = 1 WHERE user_id = ?", (user_id,))
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (COINS_PER_REFERRAL, referred_by))
    conn.commit()
    conn.close()
    increment_stat("total_referrals")
    return referred_by

def get_configs_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM configs WHERE is_used = 0")
    free = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM configs")
    total = c.fetchone()[0]; conn.close(); return free, total

def get_today_stats():
    today = date.today().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE join_date LIKE ?", (today + "%",))
    new_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM configs WHERE used_at LIKE ?", (today + "%",))
    configs_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM configs WHERE is_used = 1")
    total_used = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE coins < ? AND is_banned = 0", (COINS_TO_GET_CONFIG,))
    waiting = c.fetchone()[0]; conn.close()
    return new_today, configs_today, total_used, waiting

# ==================== بررسی عضویت ====================
async def check_membership(user_id: int, bot: Bot) -> bool:
    for channel in CHANNEL_IDS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception as e:
            logger.warning(f"خطا در بررسی عضویت {channel}: {e}")
            return False
    return True

# ==================== کیبوردها ====================
def main_keyboard(show_admin_btn: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=get_button_text("main_get_config"), callback_data="get_config", style=style_of("main_get_config"))],
        [
            InlineKeyboardButton(text=get_button_text("main_account"), callback_data="my_account", style=style_of("main_account")),
            InlineKeyboardButton(text=get_button_text("main_referral"), callback_data="referral", style=style_of("main_referral")),
        ],
        [InlineKeyboardButton(text=get_button_text("main_my_configs"), callback_data="my_configs", style=style_of("main_my_configs"))],
        [InlineKeyboardButton(text=get_button_text("main_special"), callback_data="special_menu", style=style_of("main_special"))],
        [
            InlineKeyboardButton(text=get_button_text("main_support"), callback_data="support", style=style_of("main_support")),
            InlineKeyboardButton(text=get_button_text("main_help"), callback_data="help", style=style_of("main_help")),
        ],
    ]
    if show_admin_btn:
        rows.append([InlineKeyboardButton(text=get_button_text("main_admin"), callback_data="open_admin_panel", style=style_of("main_admin"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def special_features_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_button_text("sf_like_maker"), callback_data="sf_like", style=style_of("sf_like_maker")),
            InlineKeyboardButton(text=get_button_text("sf_ai"),         callback_data="sf_ai",   style=style_of("sf_ai")),
        ],
        [
            InlineKeyboardButton(text=get_button_text("sf_downloader"), callback_data="sf_dl",    style=style_of("sf_downloader")),
            InlineKeyboardButton(text=get_button_text("sf_music"),      callback_data="sf_music", style=style_of("sf_music")),
        ],
        [
            InlineKeyboardButton(text=get_button_text("sf_logo_maker"),    callback_data="sf_logo",  style=style_of("sf_logo_maker")),
            InlineKeyboardButton(text=get_button_text("sf_voice_to_mp3"),  callback_data="sf_voice", style=style_of("sf_voice_to_mp3")),
        ],
        [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main", style=style_of("back_main"))],
    ])

def downloader_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_button_text("dl_tiktok"),    callback_data="dl_tiktok",    style=style_of("dl_tiktok")),
            InlineKeyboardButton(text=get_button_text("dl_instagram"), callback_data="dl_instagram", style=style_of("dl_instagram")),
        ],
        [
            InlineKeyboardButton(text=get_button_text("dl_youtube"), callback_data="dl_youtube", style=style_of("dl_youtube")),
            InlineKeyboardButton(text=get_button_text("dl_twitter"), callback_data="dl_twitter", style=style_of("dl_twitter")),
        ],
        [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="special_menu", style=style_of("back_main"))],
    ])

def admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    if has_perm(user_id, "toggle_bot"):
        status_text = get_button_text("admin_toggle_on") if BOT_ENABLED else get_button_text("admin_toggle_off")
        rows.append([InlineKeyboardButton(text=status_text, callback_data="admin_toggle_bot")])
    sup = SUPPORT_ID if SUPPORT_ID else "تنظیم نشده"
    if has_perm(user_id, "support_id"):
        rows.append([InlineKeyboardButton(text=f"{get_button_text('admin_support')} {sup}", callback_data="admin_set_support")])
    if has_perm(user_id, "stats"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_stats"), callback_data="admin_stats")])
    if has_perm(user_id, "users"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_users"), callback_data="admin_users_0")])
    if has_perm(user_id, "users"):
        rows.append([
            InlineKeyboardButton(text=get_button_text("admin_ban_direct"), callback_data="admin_ban_direct"),
            InlineKeyboardButton(text=get_button_text("admin_unban_direct"), callback_data="admin_unban_direct"),
        ])
        rows.append([InlineKeyboardButton(text=get_button_text("admin_banlist"), callback_data="admin_banlist_0")])
    row2 = []
    if has_perm(user_id, "add_config"):
        row2.append(InlineKeyboardButton(text=get_button_text("admin_add_config"), callback_data="admin_add_config"))
    if has_perm(user_id, "broadcast"):
        row2.append(InlineKeyboardButton(text=get_button_text("admin_broadcast"), callback_data="admin_broadcast"))
    if row2:
        rows.append(row2)
    row3 = []
    if has_perm(user_id, "coins"):
        row3.append(InlineKeyboardButton(text=get_button_text("admin_addcoins"), callback_data="admin_addcoins"))
        row3.append(InlineKeyboardButton(text=get_button_text("admin_subcoins"), callback_data="admin_subcoins"))
    if row3:
        rows.append(row3)
    if has_perm(user_id, "channels"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_channels"), callback_data="admin_channels")])
    if has_perm(user_id, "texts"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_texts"), callback_data="admin_texts")])
    if has_perm(user_id, "buttons"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_buttons"), callback_data="admin_buttons_0")])
    if has_perm(user_id, "colors"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_colors"), callback_data="admin_colors_0")])
    if is_super_admin(user_id):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_manage_admins"), callback_data="admin_manage_admins")])
    rows.append([InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def bot_texts_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, name in TEXT_NAMES.items():
        rows.append([InlineKeyboardButton(text=name, callback_data=f"admin_edittext_{key}")])
    rows.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def bot_buttons_keyboard(page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    items = list(BUTTON_NAMES.items())
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    rows = []
    for key, name in items[start:start + per_page]:
        rows.append([InlineKeyboardButton(text=name, callback_data=f"admin_editbutton_{key}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=get_button_text("prev_page"), callback_data=f"admin_buttons_{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text=get_button_text("next_page"), callback_data=f"admin_buttons_{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def join_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for ch in CHANNEL_IDS:
        buttons.append([InlineKeyboardButton(text=f"{get_button_text('join_channel')} {ch}", url=f"https://t.me/{ch.lstrip('@')}", style=ButtonStyle.DANGER)])
    buttons.append([InlineKeyboardButton(text=get_button_text("check_join"), callback_data="check_join", style=ButtonStyle.SUCCESS)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def user_detail_keyboard(uid, is_banned) -> InlineKeyboardMarkup:
    ban_btn = (InlineKeyboardButton(text=get_button_text("unban_user"), callback_data=f"admin_unban_{uid}")
               if is_banned else InlineKeyboardButton(text=get_button_text("ban_user"), callback_data=f"admin_ban_{uid}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        [ban_btn],
        [InlineKeyboardButton(text=get_button_text("msg_user"), callback_data=f"admin_msguser_{uid}")],
        [InlineKeyboardButton(text=get_button_text("send_coin_user"), callback_data=f"admin_addcoin_{uid}"),
         InlineKeyboardButton(text=get_button_text("sub_coin_user"), callback_data=f"admin_subcoin_{uid}")],
        [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="admin_users_0")],
    ])

def support_action_keyboard(uid, is_banned) -> InlineKeyboardMarkup:
    ban_btn = (InlineKeyboardButton(text=get_button_text("unban_user"), callback_data=f"admin_unban_{uid}")
               if is_banned else InlineKeyboardButton(text=get_button_text("ban_user"), callback_data=f"admin_ban_{uid}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        [ban_btn],
        [InlineKeyboardButton(text=get_button_text("msg_user"), callback_data=f"admin_msguser_{uid}")],
        [InlineKeyboardButton(text=get_button_text("send_coin_user"), callback_data=f"admin_addcoin_{uid}"),
         InlineKeyboardButton(text=get_button_text("sub_coin_user"), callback_data=f"admin_subcoin_{uid}")],
    ])

def sub_admin_perms_keyboard(target_id: int) -> InlineKeyboardMarkup:
    perms = SUB_ADMINS.get(str(target_id), {})
    rows = []
    for perm, name in PERM_NAMES.items():
        has = perms.get(perm, False)
        icon = "✅" if has else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {name}",
            callback_data=f"admin_toggleperm_{target_id}_{perm}"
        )])
    rows.append([InlineKeyboardButton(text=get_button_text("delete_admin"), callback_data=f"admin_removeadmin_{target_id}", style=ButtonStyle.DANGER)])
    rows.append([InlineKeyboardButton(text=get_button_text("back_main"), callback_data="admin_manage_admins")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

dp  = Dispatcher(storage=MemoryStorage())
bot: Bot = None

# ==================== /start ====================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referred_by = int(args[1].split("_")[1])
            if referred_by == user.id: referred_by = None
        except: pass

    is_new = add_user(user.id, user.username, user.full_name, referred_by)
    if is_new: increment_stat("total_users")

    if not BOT_ENABLED and not is_any_admin(user.id):
        await message.answer("🔴 ربات درحال بروزرسانی هست\nبزودی روشن می‌شود 🙏"); return

    is_member = await check_membership(user.id, bot)
    if not is_member:
        await message.answer(get_bot_text("join_required"), reply_markup=join_keyboard()); return

    db_user = get_user(user.id)
    if db_user and db_user[6]:
        await message.answer("⛔️ حساب شما مسدود شده است."); return

    referred_by_credited = credit_referral(user.id)
    if referred_by_credited:
        try:
            await bot.send_message(referred_by_credited,
                f"🎉 یه نفر با لینک دعوت تو وارد ربات شد و عضو کانال شد!\n+{COINS_PER_REFERRAL} سکه به حسابت اضافه شد 🪙")
        except: pass

    await message.answer(get_bot_text("start"), reply_markup=main_keyboard(show_admin_btn=is_any_admin(user.id)))

# ==================== باز کردن پنل ادمین ====================
@dp.callback_query(F.data == "open_admin_panel")
async def cb_open_admin_panel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    if not is_any_admin(call.from_user.id):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.message.edit_text("👑 پنل مدیریت", reply_markup=admin_keyboard(call.from_user.id))

# ==================== check_join ====================
@dp.callback_query(F.data == "check_join")
async def cb_check_join(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not BOT_ENABLED and not is_any_admin(call.from_user.id):
        await call.message.edit_text("🔴 ربات درحال بروزرسانی هست\nبزودی روشن می‌شود 🙏"); return
    is_member = await check_membership(call.from_user.id, bot)
    if not is_member:
        await call.message.edit_text(get_bot_text("not_joined"), reply_markup=join_keyboard()); return
    db_user = get_user(call.from_user.id)
    if db_user and db_user[6]:
        await call.message.edit_text("⛔️ حساب شما مسدود شده است."); return

    referred_by = credit_referral(call.from_user.id)
    if referred_by:
        try:
            await bot.send_message(referred_by,
                f"🎉 یه نفر با لینک دعوت تو وارد ربات شد و عضو کانال شد!\n+{COINS_PER_REFERRAL} سکه به حسابت اضافه شد 🪙")
        except: pass

    await call.message.edit_text(get_bot_text("start"), reply_markup=main_keyboard(show_admin_btn=is_any_admin(call.from_user.id)))

# ==================== back_main ====================
@dp.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text(get_bot_text("start"), reply_markup=main_keyboard(show_admin_btn=is_any_admin(call.from_user.id)))

# ==================== get_config ====================
@dp.callback_query(F.data == "get_config")
async def cb_get_config(call: CallbackQuery):
    await call.answer()
    user = call.from_user
    if not BOT_ENABLED and not is_any_admin(user.id):
        await call.message.edit_text("🔴 ربات درحال بروزرسانی هست\nبزودی روشن می‌شود 🙏"); return
    is_member = await check_membership(user.id, bot)
    if not is_member:
        await call.message.edit_text(get_bot_text("join_required_short"), reply_markup=join_keyboard()); return
    db_user = get_user(user.id)
    if not db_user:
        await call.answer("ابتدا /start بزن.", show_alert=True); return
    if db_user[6]:
        await call.answer("⛔️ حساب شما مسدود است.", show_alert=True); return
    coins = db_user[3]
    if coins < COINS_TO_GET_CONFIG:
        needed = COINS_TO_GET_CONFIG - coins
        await call.message.edit_text(
            f"❌ سکه کافی نداری رفیق!\n\n🪙 سکه فعلی تو: {coins}\n🎯 نیاز داری: {COINS_TO_GET_CONFIG} سکه\n📉 کمبود داری: {needed} سکه\n\n👥 دوستاتو دعوت کن!\nهر دعوت = {COINS_PER_REFERRAL} سکه 🪙",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("get_referral"), callback_data="referral", style=ButtonStyle.PRIMARY)],
                [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")],
            ])); return
    config = get_free_config()
    if not config:
        await call.message.edit_text("😔 متأسفانه در حال حاضر کانفیگ موجود نیست.\nکمی صبر کن!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]])); return
    update_coins(user.id, -COINS_TO_GET_CONFIG)
    mark_config_used(config[0], user.id)
    increment_stat("configs_given")
    await call.message.edit_text(
        f"✅ اتصال رایگان تو اینه رفیق!\n\n<code>{config[1]}</code>\n\n🪙 {COINS_TO_GET_CONFIG} سکه از حسابت کسر شد.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== کانفیگ‌های من ====================
@dp.callback_query(F.data == "my_configs")
async def cb_my_configs(call: CallbackQuery):
    await call.answer()
    user = call.from_user
    db_user = get_user(user.id)
    if not db_user:
        await call.answer("ابتدا /start بزن.", show_alert=True); return
    configs = get_user_configs(user.id)
    if not configs:
        await call.message.edit_text(
            "📦 کانفیگ‌های من\n━━━━━━━━━━━━━━━\n\n"
            "هنوز هیچ کانفیگی دریافت نکردی!\n"
            "از منوی اصلی روی «اتصال رایگان» بزن تا اولین کانفیگتو بگیری 🎁",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))
        return
    await call.message.edit_text(
        f"📦 کانفیگ‌های من\n━━━━━━━━━━━━━━━\n\n"
        f"تعداد کل کانفیگ‌های دریافتی: {len(configs)}\n\n"
        f"در حال ارسال کانفیگ‌ها برای شما... 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))
    for idx, (cid, content, used_at) in enumerate(configs, start=1):
        try:
            await bot.send_message(
                user.id,
                f"📦 کانفیگ #{idx}\n📅 تاریخ دریافت: {used_at or '-'}\n\n<code>{content}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.warning(f"خطا در ارسال کانفیگ به کاربر {user.id}: {e}")

# ==================== referral ====================
@dp.callback_query(F.data == "referral")
async def cb_referral(call: CallbackQuery):
    await call.answer()
    db_user = get_user(call.from_user.id)
    if not db_user:
        await call.answer("ابتدا /start بزن.", show_alert=True); return
    ref_count = get_referral_count(call.from_user.id)
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{call.from_user.id}"
    await call.message.edit_text(
        f"🔗 لینک دعوت تو:\n\n<code>{ref_link}</code>\n\n━━━━━━━━━━━━━━━\n"
        f"👥 تعداد دعوت‌شده‌ها: {ref_count} نفر\n🪙 سکه‌های فعلی: {db_user[3]}\n"
        f"🎯 نیاز داری: {COINS_TO_GET_CONFIG} سکه\n━━━━━━━━━━━━━━━\n\n"
        f"هر دعوت = {COINS_PER_REFERRAL} سکه 🪙\nلینکتو برای دوستات بفرست!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== my_account ====================
@dp.callback_query(F.data == "my_account")
async def cb_my_account(call: CallbackQuery):
    await call.answer()
    db_user = get_user(call.from_user.id)
    if not db_user:
        await call.answer("ابتدا /start بزن.", show_alert=True); return
    ref_count = get_referral_count(call.from_user.id)
    status = "🚫 مسدود" if db_user[6] else "✅ فعال"
    await call.message.edit_text(
        f"👤 حساب من\n━━━━━━━━━━━━━━━\n🆔 آیدی: <code>{db_user[0]}</code>\n📛 نام: {db_user[2]}\n"
        f"🪙 سکه: {db_user[3]}\n👥 زیرمجموعه: {ref_count} نفر\n"
        f"📉 سکه مصرف‌شده: {db_user[7]*COINS_TO_GET_CONFIG}\n🎁 اتصال دریافت‌شده: {db_user[7]}\n"
        f"📌 وضعیت: {status}\n━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== help ====================
@dp.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        get_bot_text("help"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== پشتیبانی ====================
@dp.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        get_bot_text("support"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("support_sponsor"), callback_data="support_sponsor", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton(text=get_button_text("support_question"), callback_data="support_question", style=ButtonStyle.SUCCESS)],
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")],
        ]))

@dp.callback_query(F.data == "support_sponsor")
async def cb_support_sponsor(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(UserStates.sponsor_msg)
    await call.message.edit_text(
        get_bot_text("sponsor_prompt"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="back_main")]]))

@dp.message(UserStates.sponsor_msg)
async def hdl_sponsor_msg(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    db_user = get_user(user.id)
    coins = db_user[3] if db_user else 0
    is_banned = db_user[6] if db_user else 0
    username = f"@{user.username}" if user.username else "ندارد"
    admin_text = (f"💼 درخواست اسپانسر جدید\n━━━━━━━━━━━━━━━\n\n"
                  f"👤 نام: {user.full_name}\n📛 یوزرنیم: {username}\n"
                  f"🆔 آیدی: <code>{user.id}</code>\n🪙 سکه: {coins}\n"
                  f"━━━━━━━━━━━━━━━\n\n📝 پیام اسپانسر:\n{message.text}")
    for aid in SUPER_ADMIN_IDS:
        try: await bot.send_message(aid, admin_text, parse_mode=ParseMode.HTML, reply_markup=support_action_keyboard(user.id, is_banned))
        except: pass
    await message.answer("✅ درخواست اسپانسر شما ارسال شد!\nبه زودی با شما تماس می‌گیریم 🙏",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

@dp.callback_query(F.data == "support_question")
async def cb_support_question(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(UserStates.support_msg)
    await call.message.edit_text(get_bot_text("support_question_prompt"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="back_main")]]))

@dp.message(UserStates.support_msg)
async def hdl_support_msg(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    db_user = get_user(user.id)
    coins = db_user[3] if db_user else 0
    is_banned = db_user[6] if db_user else 0
    username = f"@{user.username}" if user.username else "ندارد"
    admin_text = (f"❓ سوال / مشکل جدید\n━━━━━━━━━━━━━━━\n\n"
                  f"👤 نام: {user.full_name}\n📛 یوزرنیم: {username}\n"
                  f"🆔 آیدی: <code>{user.id}</code>\n🪙 سکه: {coins}\n"
                  f"━━━━━━━━━━━━━━━\n\n📝 پیام:\n{message.text}")
    for aid in SUPER_ADMIN_IDS:
        try: await bot.send_message(aid, admin_text, parse_mode=ParseMode.HTML, reply_markup=support_action_keyboard(user.id, is_banned))
        except: pass
    await message.answer("✅ پیام شما ارسال شد!\nبه زودی پاسخ می‌گیرید 🙏",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== خاموش/روشن ====================
@dp.callback_query(F.data == "admin_toggle_bot")
async def cb_toggle_bot(call: CallbackQuery):
    if not has_perm(call.from_user.id, "toggle_bot"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    status_text = "🟢 روشن" if BOT_ENABLED else "🔴 خاموش"
    await call.message.edit_text(f"⚙️ وضعیت ربات\n\nوضعیت فعلی: {status_text}\n\nیکی رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("bot_off"), callback_data="admin_bot_off")],
            [InlineKeyboardButton(text=get_button_text("bot_on"), callback_data="admin_bot_on")],
            [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")],
        ]))

@dp.callback_query(F.data == "admin_bot_on")
async def cb_bot_on(call: CallbackQuery):
    global BOT_ENABLED
    if not has_perm(call.from_user.id, "toggle_bot"): return
    await call.answer()
    BOT_ENABLED = True
    cfg = load_config(); cfg["enabled"] = True; save_config(cfg)
    await call.message.edit_text("✅ ربات روشن شد!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]]))

@dp.callback_query(F.data == "admin_bot_off")
async def cb_bot_off(call: CallbackQuery):
    global BOT_ENABLED
    if not has_perm(call.from_user.id, "toggle_bot"): return
    await call.answer()
    BOT_ENABLED = False
    cfg = load_config(); cfg["enabled"] = False; save_config(cfg)
    await call.message.edit_text("🔴 ربات خاموش شد!\nکاربران پیام «درحال بروزرسانی» می‌بینن.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]]))

# ==================== آمار ====================
@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    if not has_perm(call.from_user.id, "stats"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    total_users = get_stat("total_users")
    free_configs, _ = get_configs_count()
    new_today, configs_today, total_used, waiting = get_today_stats()
    bot_status = "🟢 روشن" if BOT_ENABLED else "🔴 خاموش"
    sup = SUPPORT_ID if SUPPORT_ID else "تنظیم نشده"
    await call.message.edit_text(
        f"وضعیت ربات: {bot_status}\nآیدی پشتیبانی فعلی: {sup}\n\n📊 آمار کلی:\n"
        f"👥 تعداد کل کاربران: {total_users}\n🔥 کاربران فعال امروز: {new_today}\n"
        f"🌱 ورودی‌های جدید امروز: {new_today}\n\n✅ کانفیگ های موجود فعلی: {free_configs}\n"
        f"🟢 کانفیگ‌های مصرف‌شده امروز: {configs_today}\n🔴 کل کانفیگ‌های منقضی/مصرف‌شده: {total_used}\n\n"
        f"⏳ کاربران در انتظار کانفیگ: {waiting}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]]))

# ==================== مدیریت متن‌ها ====================
@dp.callback_query(F.data == "admin_texts")
async def cb_admin_texts(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not has_perm(call.from_user.id, "texts"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    await call.message.edit_text(
        "✏️ مدیریت متن‌ها\n\nیکی از متن‌ها را انتخاب کن تا متن فعلی را ببینی و متن جدید بفرستی:",
        reply_markup=bot_texts_keyboard())

@dp.callback_query(F.data.startswith("admin_edittext_"))
async def cb_admin_edit_text(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "texts"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    key = call.data.replace("admin_edittext_", "")
    if key not in TEXT_NAMES:
        await call.answer("این متن پیدا نشد.", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.edit_bot_text)
    await state.update_data(text_key=key)
    await call.message.edit_text(
        f"✏️ تغییر {TEXT_NAMES[key]}\n\nمتن فعلی:\n\n{get_bot_text(key)}\n\n━━━━━━━━━━━━━━━\nمتن جدید را همینجا بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="admin_texts")]]))

@dp.message(AdminStates.edit_bot_text)
async def hdl_admin_edit_text(message: Message, state: FSMContext):
    if not has_perm(message.from_user.id, "texts"):
        await state.clear()
        return
    data = await state.get_data()
    key = data.get("text_key")
    if key not in TEXT_NAMES:
        await state.clear()
        await message.answer("❌ خطا در انتخاب متن.", reply_markup=admin_keyboard(message.from_user.id))
        return
    new_text = (message.text or "").strip()
    if not new_text:
        await message.answer("❌ متن خالی قابل ذخیره نیست. متن جدید را بفرست:")
        return
    save_bot_text(key, new_text)
    await state.clear()
    await message.answer(
        f"✅ {TEXT_NAMES[key]} ذخیره شد.\n\nمتن جدید:\n\n{new_text}",
        reply_markup=bot_texts_keyboard())

# ==================== مدیریت دکمه‌ها ====================
@dp.callback_query(F.data.startswith("admin_buttons_"))
async def cb_admin_buttons(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not has_perm(call.from_user.id, "buttons"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    try:
        page = int(call.data.split("_")[-1])
    except:
        page = 0
    await call.message.edit_text(
        "🔘 مدیریت دکمه‌های شیشه‌ای\n\nیکی از دکمه‌ها را انتخاب کن تا اسم فعلی را ببینی و اسم جدید بفرستی:",
        reply_markup=bot_buttons_keyboard(page))

@dp.callback_query(F.data.startswith("admin_editbutton_"))
async def cb_admin_edit_button(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "buttons"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    key = call.data.replace("admin_editbutton_", "")
    if key not in BUTTON_NAMES:
        await call.answer("این دکمه پیدا نشد.", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.edit_button_text)
    await state.update_data(button_key=key)
    await call.message.edit_text(
        f"🔘 تغییر {BUTTON_NAMES[key]}\n\nاسم فعلی:\n\n{get_button_text(key)}\n\n━━━━━━━━━━━━━━━\nاسم جدید دکمه را بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="admin_buttons_0")]]))

@dp.message(AdminStates.edit_button_text)
async def hdl_admin_edit_button(message: Message, state: FSMContext):
    if not has_perm(message.from_user.id, "buttons"):
        await state.clear()
        return
    data = await state.get_data()
    key = data.get("button_key")
    if key not in BUTTON_NAMES:
        await state.clear()
        await message.answer("❌ خطا در انتخاب دکمه.", reply_markup=admin_keyboard(message.from_user.id))
        return
    new_text = (message.text or "").strip()
    if not new_text:
        await message.answer("❌ اسم خالی قابل ذخیره نیست. اسم جدید دکمه را بفرست:")
        return
    save_button_text(key, new_text)
    await state.clear()
    await message.answer(
        f"✅ {BUTTON_NAMES[key]} ذخیره شد.\n\nاسم جدید:\n\n{new_text}",
        reply_markup=bot_buttons_keyboard())

# ==================== لیست کاربران ====================
@dp.callback_query(F.data.startswith("admin_users_"))
async def cb_admin_users(call: CallbackQuery):
    if not has_perm(call.from_user.id, "users"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    page = int(call.data.split("_")[-1])
    users, total = get_all_users_paginated(page, 20)
    if not users:
        await call.message.edit_text("هیچ کاربری یافت نشد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]])); return
    buttons = []
    for u in users:
        banned = "🚫" if u[3] else ""
        buttons.append([InlineKeyboardButton(text=f"{banned}{u[1]} | 🪙{u[2]}", callback_data=f"admin_userdetail_{u[0]}")])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text=get_button_text("prev_page"), callback_data=f"admin_users_{page-1}"))
    if (page+1)*20 < total: nav.append(InlineKeyboardButton(text=get_button_text("next_page"), callback_data=f"admin_users_{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    await call.message.edit_text(f"👥 لیست کاربران (صفحه {page+1})\nکل: {total} کاربر",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("admin_userdetail_"))
async def cb_user_detail_view(call: CallbackQuery):
    if not is_any_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.split("_")[-1])
    u = get_user_detail(target_id)
    if not u:
        await call.answer("کاربر یافت نشد.", show_alert=True); return
    status = "🚫 مسدود" if u[4] else "✅ فعال"
    await call.message.edit_text(
        f"👤 جزئیات کاربر\n━━━━━━━━━━━━━━━\n🆔 آیدی: <code>{u[0]}</code>\n"
        f"📛 یوزرنیم: @{u[1] or 'ندارد'}\n👤 نام: {u[2]}\n🪙 سکه: {u[3]}\n"
        f"📌 وضعیت: {status}\n🎁 کانفیگ دریافتی: {u[5]}\n👥 زیرمجموعه: {u[6]}\n━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML, reply_markup=user_detail_keyboard(u[0], u[4]))

@dp.callback_query(F.data.startswith("admin_ban_") & ~F.data.startswith("admin_ban_direct") & ~F.data.startswith("admin_banlist"))
async def cb_ban(call: CallbackQuery):
    if not is_any_admin(call.from_user.id): return
    target_id = int(call.data.split("_")[-1])
    db_ban_user(target_id)
    await call.answer(f"✅ کاربر {target_id} بن شد.", show_alert=True)
    u = get_user_detail(target_id)
    if u:
        try: await call.message.edit_reply_markup(reply_markup=user_detail_keyboard(u[0], u[4]))
        except:
            try: await call.message.edit_reply_markup(reply_markup=support_action_keyboard(u[0], u[4]))
            except: pass

@dp.callback_query(F.data.startswith("admin_unban_") & ~F.data.startswith("admin_unban_direct"))
async def cb_unban(call: CallbackQuery):
    if not is_any_admin(call.from_user.id): return
    target_id = int(call.data.split("_")[-1])
    db_unban_user(target_id)
    await call.answer(f"✅ کاربر {target_id} آنبن شد.", show_alert=True)
    u = get_user_detail(target_id)
    if u:
        try: await call.message.edit_reply_markup(reply_markup=user_detail_keyboard(u[0], u[4]))
        except:
            try: await call.message.edit_reply_markup(reply_markup=support_action_keyboard(u[0], u[4]))
            except: pass

# ==================== بن مستقیم از پنل (با آیدی عددی) ====================
@dp.callback_query(F.data == "admin_ban_direct")
async def cb_admin_ban_direct(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "users"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.ban_direct_id)
    await call.message.edit_text(
        "🚫 بن کردن کاربر\n\nآیدی عددی کاربری که می‌خوای بن بشه رو بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.message(AdminStates.ban_direct_id)
async def hdl_admin_ban_direct(message: Message, state: FSMContext):
    if not has_perm(message.from_user.id, "users"):
        await state.clear(); return
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("❌ آیدی عددی معتبر بفرست:"); return
    target_id = int(txt)
    u = get_user(target_id)
    if not u:
        await message.answer("❌ کاربری با این آیدی در ربات یافت نشد. آیدی دیگه‌ای بفرست یا لغو کن:"); return
    db_ban_user(target_id)
    await state.clear()
    await message.answer(
        f"✅ کاربر <code>{target_id}</code> با موفقیت بن شد.\n👤 نام: {u[2]}",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(message.from_user.id))

@dp.callback_query(F.data == "admin_unban_direct")
async def cb_admin_unban_direct(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "users"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.unban_direct_id)
    await call.message.edit_text(
        "🔓 آنبن کردن کاربر\n\nآیدی عددی کاربری که می‌خوای آنبن بشه رو بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.message(AdminStates.unban_direct_id)
async def hdl_admin_unban_direct(message: Message, state: FSMContext):
    if not has_perm(message.from_user.id, "users"):
        await state.clear(); return
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("❌ آیدی عددی معتبر بفرست:"); return
    target_id = int(txt)
    u = get_user(target_id)
    if not u:
        await message.answer("❌ کاربری با این آیدی در ربات یافت نشد. آیدی دیگه‌ای بفرست یا لغو کن:"); return
    db_unban_user(target_id)
    await state.clear()
    await message.answer(
        f"✅ کاربر <code>{target_id}</code> با موفقیت آنبن شد.\n👤 نام: {u[2]}",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(message.from_user.id))

# ==================== لیست بن‌ها ====================
@dp.callback_query(F.data.startswith("admin_banlist_"))
async def cb_admin_banlist(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not has_perm(call.from_user.id, "users"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    try:
        page = int(call.data.split("_")[-1])
    except:
        page = 0
    users, total = get_banned_users_paginated(page, 20)
    if total == 0:
        await call.message.edit_text(
            "📋 لیست بن‌ها\n━━━━━━━━━━━━━━━\n\nهیچ کاربر بن‌شده‌ای وجود نداره ✅",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]]))
        return
    buttons = []
    for u in users:
        buttons.append([InlineKeyboardButton(
            text=f"🚫 {u[1]} | 🆔 {u[0]}",
            callback_data=f"admin_bannedview_{u[0]}"
        )])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text=get_button_text("prev_page"), callback_data=f"admin_banlist_{page-1}"))
    if (page+1)*20 < total: nav.append(InlineKeyboardButton(text=get_button_text("next_page"), callback_data=f"admin_banlist_{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    await call.message.edit_text(
        f"📋 لیست بن‌ها (صفحه {page+1})\nکل کاربران بن‌شده: {total}\n\nروی کاربر بزن تا آنبن بشه:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("admin_bannedview_"))
async def cb_admin_banned_view(call: CallbackQuery):
    if not has_perm(call.from_user.id, "users"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    target_id = int(call.data.split("_")[-1])
    u = get_user_detail(target_id)
    if not u:
        await call.answer("کاربر یافت نشد.", show_alert=True); return
    await call.message.edit_text(
        f"👤 کاربر بن‌شده\n━━━━━━━━━━━━━━━\n"
        f"🆔 آیدی: <code>{u[0]}</code>\n"
        f"📛 یوزرنیم: @{u[1] or 'ندارد'}\n"
        f"👤 نام: {u[2]}\n"
        f"🪙 سکه: {u[3]}\n"
        f"🎁 کانفیگ دریافتی: {u[5]}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"این کاربر آنبن شود؟",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("confirm_unban"), callback_data=f"admin_confirmunban_{target_id}")],
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="admin_banlist_0")],
        ]))

@dp.callback_query(F.data.startswith("admin_confirmunban_"))
async def cb_admin_confirm_unban(call: CallbackQuery):
    if not has_perm(call.from_user.id, "users"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    target_id = int(call.data.split("_")[-1])
    db_unban_user(target_id)
    await call.answer(f"✅ کاربر {target_id} آنبن شد.", show_alert=True)
    users, total = get_banned_users_paginated(0, 20)
    if total == 0:
        await call.message.edit_text(
            "📋 لیست بن‌ها\n━━━━━━━━━━━━━━━\n\nهیچ کاربر بن‌شده‌ای وجود نداره ✅",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]]))
        return
    buttons = []
    for u in users:
        buttons.append([InlineKeyboardButton(
            text=f"🚫 {u[1]} | 🆔 {u[0]}",
            callback_data=f"admin_bannedview_{u[0]}"
        )])
    if total > 20:
        buttons.append([InlineKeyboardButton(text=get_button_text("next_page"), callback_data=f"admin_banlist_1")])
    buttons.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    await call.message.edit_text(
        f"✅ کاربر {target_id} آنبن شد.\n\n📋 لیست بن‌ها (صفحه 1)\nکل کاربران بن‌شده: {total}\n\nروی کاربر بزن تا آنبن بشه:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# ==================== افزودن کانفیگ ====================
@dp.callback_query(F.data == "admin_add_config")
async def cb_add_config(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "add_config"): return
    await call.answer()
    await state.set_state(AdminStates.waiting_config_count)
    await call.message.edit_text("➕ افزودن کانفیگ\n\nچند تا کانفیگ می‌خوای اضافه کنی؟\nعدد بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.message(AdminStates.waiting_config_count)
async def hdl_config_count(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❌ عدد معتبر بفرست:"); return
    count = int(message.text.strip())
    await state.update_data(config_count=count, config_received=0)
    await state.set_state(AdminStates.waiting_config_item)
    await message.answer(f"✅ {count} تا کانفیگ ثبت می‌کنیم.\n\nکانفیگ شماره 1 رو بفرست:")

@dp.message(AdminStates.waiting_config_item)
async def hdl_config_item(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    data = await state.get_data()
    add_config(message.text.strip())
    received = data["config_received"] + 1
    await state.update_data(config_received=received)
    if received >= data["config_count"]:
        await state.clear()
        await message.answer(f"✅ همه {data['config_count']} کانفیگ اضافه شدن!", reply_markup=admin_keyboard(message.from_user.id)); return
    await message.answer(f"✅ کانفیگ {received} ثبت شد.\n\nکانفیگ شماره {received+1} رو بفرست:")

# ==================== سکه ====================
@dp.callback_query(F.data == "admin_addcoins")
async def cb_add_coins(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "coins"): return
    await call.answer()
    await state.set_state(AdminStates.add_coins_id)
    await call.message.edit_text("💰 انتقال سکه\n\nآیدی عددی کاربر رو بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.callback_query(F.data.startswith("admin_addcoin_"))
async def cb_add_coin_direct(call: CallbackQuery, state: FSMContext):
    if not is_any_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.split("_")[-1])
    await state.update_data(add_coins_target=target_id)
    await state.set_state(AdminStates.add_coins_amount)
    await call.message.edit_text(f"💰 چند سکه به کاربر {target_id} اضافه کنم?\nعدد بفرست:")

@dp.message(AdminStates.add_coins_id)
async def hdl_add_coins_id(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit():
        await message.answer("❌ آیدی عددی معتبر بفرست:"); return
    u = get_user(int(message.text.strip()))
    if not u:
        await message.answer("❌ کاربر یافت نشد:"); return
    await state.update_data(add_coins_target=int(message.text.strip()))
    await state.set_state(AdminStates.add_coins_amount)
    await message.answer(f"✅ کاربر: {u[2]}\n🪙 سکه فعلی: {u[3]}\n\nچند سکه اضافه کنم?")

@dp.message(AdminStates.add_coins_amount)
async def hdl_add_coins_amount(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❌ عدد معتبر بفرست:"); return
    data = await state.get_data()
    update_coins(data["add_coins_target"], int(message.text.strip()))
    u = get_user(data["add_coins_target"])
    await state.clear()
    await message.answer(f"✅ {message.text.strip()} سکه به {data['add_coins_target']} اضافه شد.\n🪙 سکه جدید: {u[3]}",
        reply_markup=admin_keyboard(message.from_user.id))

@dp.callback_query(F.data == "admin_subcoins")
async def cb_sub_coins(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "coins"): return
    await call.answer()
    await state.set_state(AdminStates.sub_coins_id)
    await call.message.edit_text("➖ کسر سکه\n\nآیدی عددی کاربر رو بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.callback_query(F.data.startswith("admin_subcoin_"))
async def cb_sub_coin_direct(call: CallbackQuery, state: FSMContext):
    if not is_any_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.split("_")[-1])
    await state.update_data(sub_coins_target=target_id)
    await state.set_state(AdminStates.sub_coins_amount)
    await call.message.edit_text(f"➖ چند سکه از کاربر {target_id} کسر کنم?\nعدد بفرست:")

@dp.message(AdminStates.sub_coins_id)
async def hdl_sub_coins_id(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit():
        await message.answer("❌ آیدی عددی معتبر بفرست:"); return
    u = get_user(int(message.text.strip()))
    if not u:
        await message.answer("❌ کاربر یافت نشد:"); return
    await state.update_data(sub_coins_target=int(message.text.strip()))
    await state.set_state(AdminStates.sub_coins_amount)
    await message.answer(f"✅ کاربر: {u[2]}\n🪙 سکه فعلی: {u[3]}\n\nچند سکه کسر کنم?")

@dp.message(AdminStates.sub_coins_amount)
async def hdl_sub_coins_amount(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❌ عدد معتبر بفرست:"); return
    data = await state.get_data()
    update_coins(data["sub_coins_target"], -int(message.text.strip()))
    u = get_user(data["sub_coins_target"])
    await state.clear()
    await message.answer(f"✅ {message.text.strip()} سکه از {data['sub_coins_target']} کسر شد.\n🪙 سکه جدید: {u[3]}",
        reply_markup=admin_keyboard(message.from_user.id))

# ==================== پیام به کاربر ====================
@dp.callback_query(F.data.startswith("admin_msguser_"))
async def cb_msg_user(call: CallbackQuery, state: FSMContext):
    if not is_any_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.split("_")[-1])
    await state.update_data(msg_user_target=target_id)
    await state.set_state(AdminStates.msg_user_text)
    await call.message.edit_text(f"✉️ پیام به کاربر {target_id}\n\nمتن پیام رو بفرست:")

@dp.message(AdminStates.msg_user_text)
async def hdl_msg_user_text(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    data = await state.get_data()
    try:
        await bot.send_message(data["msg_user_target"], f"📩 پیام از ادمین:\n\n{message.text}")
        await message.answer("✅ پیام ارسال شد.", reply_markup=admin_keyboard(message.from_user.id))
    except Exception as e:
        await message.answer(f"❌ ارسال ناموفق: {e}", reply_markup=admin_keyboard(message.from_user.id))
    await state.clear()

# ==================== ارسال همگانی (با گزینه پین) ====================
@dp.callback_query(F.data == "admin_broadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "broadcast"): return
    await call.answer()
    await state.set_state(AdminStates.broadcast)
    await call.message.edit_text("📢 ارسال همگانی\n\nمتن پیام رو بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.message(AdminStates.broadcast)
async def hdl_broadcast(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ متن خالی قابل ارسال نیست. متن پیام رو بفرست:"); return
    await state.update_data(broadcast_text=text)
    await state.set_state(AdminStates.broadcast_choose_pin)
    await message.answer(
        f"📢 پیش‌نمایش پیام همگانی:\n━━━━━━━━━━━━━━━\n\n{text}\n\n━━━━━━━━━━━━━━━\n\n"
        f"می‌خوای پیام بعد از ارسال، در چت کاربران پین هم بشه؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("broadcast_pin"), callback_data="admin_broadcast_pin")],
            [InlineKeyboardButton(text=get_button_text("broadcast_send"), callback_data="admin_broadcast_send")],
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")],
        ]))

async def _do_broadcast(call: CallbackQuery, state: FSMContext, pin: bool):
    data = await state.get_data()
    text = data.get("broadcast_text", "").strip()
    await state.clear()
    if not text:
        await call.message.edit_text("❌ متنی برای ارسال پیدا نشد.", reply_markup=admin_keyboard(call.from_user.id))
        return
    await call.message.edit_text("⏳ در حال ارسال همگانی...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_banned = 0")
    users = c.fetchall(); conn.close()
    sent = failed = pinned = pin_failed = 0
    for (uid,) in users:
        try:
            sent_msg = await bot.send_message(uid, text)
            sent += 1
            if pin:
                try:
                    await bot.pin_chat_message(uid, sent_msg.message_id, disable_notification=True)
                    pinned += 1
                except Exception as e:
                    pin_failed += 1
                    logger.warning(f"خطا در پین برای {uid}: {e}")
        except:
            failed += 1
    summary = f"✅ ارسال همگانی تموم شد.\n📤 ارسال‌شده: {sent}\n❌ ناموفق: {failed}"
    if pin:
        summary += f"\n📌 پین‌شده: {pinned}\n📌❌ پین ناموفق: {pin_failed}"
    await bot.send_message(call.from_user.id, summary, reply_markup=admin_keyboard(call.from_user.id))

@dp.callback_query(F.data == "admin_broadcast_pin")
async def cb_broadcast_pin(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "broadcast"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    await _do_broadcast(call, state, pin=True)

@dp.callback_query(F.data == "admin_broadcast_send")
async def cb_broadcast_send(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "broadcast"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    await _do_broadcast(call, state, pin=False)

# ==================== تنظیم ایدی پشتیبانی ====================
@dp.callback_query(F.data == "admin_set_support")
async def cb_set_support(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "support_id"): return
    await call.answer()
    await state.set_state(AdminStates.set_support_id)
    await call.message.edit_text(
        f"🛟 تنظیم ایدی پشتیبانی\n\nایدی فعلی: {SUPPORT_ID or 'تنظیم نشده'}\n\nایدی جدید رو بفرست (مثلاً @username):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.message(AdminStates.set_support_id)
async def hdl_set_support_id(message: Message, state: FSMContext):
    global SUPPORT_ID
    if not is_any_admin(message.from_user.id): return
    new_id = message.text.strip()
    if not new_id.startswith("@"): new_id = "@" + new_id
    SUPPORT_ID = new_id
    cfg = load_config(); cfg["support_id"] = new_id; save_config(cfg)
    await state.clear()
    await message.answer(f"✅ ایدی پشتیبانی به {new_id} تغییر کرد!", reply_markup=admin_keyboard(message.from_user.id))

# ==================== مدیریت چنل‌ها ====================
def channels_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for ch in CHANNEL_IDS:
        buttons.append([InlineKeyboardButton(text=f"{get_button_text('delete_channel')} {ch}", callback_data=f"admin_delchannel_{ch.lstrip('@')}", style=ButtonStyle.DANGER)])
    buttons.append([InlineKeyboardButton(text=get_button_text("add_channel"), callback_data="admin_addchannel", style=ButtonStyle.SUCCESS)])
    buttons.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.callback_query(F.data == "admin_channels")
async def cb_admin_channels(call: CallbackQuery):
    if not has_perm(call.from_user.id, "channels"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    ch_list = "\n".join([f"• {ch}" for ch in CHANNEL_IDS]) if CHANNEL_IDS else "هیچ چنلی ثبت نشده"
    await call.message.edit_text(
        f"📡 مدیریت چنل‌های عضویت اجباری\n━━━━━━━━━━━━━━━\n\nچنل‌های فعلی:\n{ch_list}\n\n"
        f"برای حذف روی چنل بزن:", reply_markup=channels_keyboard())

@dp.callback_query(F.data == "admin_addchannel")
async def cb_add_channel(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "channels"): return
    await call.answer()
    await state.set_state(AdminStates.add_channel)
    await call.message.edit_text("➕ اضافه کردن چنل\n\nیوزرنیم چنل رو با @ بفرست:\nمثال: @mychannel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_channels")]]))

@dp.message(AdminStates.add_channel)
async def hdl_add_channel(message: Message, state: FSMContext):
    global CHANNEL_IDS
    if not is_any_admin(message.from_user.id): return
    ch = message.text.strip()
    if not ch.startswith("@"): ch = "@" + ch
    if ch not in CHANNEL_IDS:
        CHANNEL_IDS.append(ch)
        cfg = load_config(); cfg["channels"] = CHANNEL_IDS; save_config(cfg)
        await message.answer(f"✅ چنل {ch} اضافه شد!", reply_markup=channels_keyboard())
    else:
        await message.answer(f"⚠️ چنل {ch} قبلاً ثبت شده!", reply_markup=channels_keyboard())
    await state.clear()

@dp.callback_query(F.data.startswith("admin_delchannel_"))
async def cb_del_channel(call: CallbackQuery):
    global CHANNEL_IDS
    if not has_perm(call.from_user.id, "channels"): return
    await call.answer()
    ch = "@" + call.data.replace("admin_delchannel_", "")
    if ch in CHANNEL_IDS:
        CHANNEL_IDS.remove(ch)
        cfg = load_config(); cfg["channels"] = CHANNEL_IDS; save_config(cfg)
    ch_list = "\n".join([f"• {c}" for c in CHANNEL_IDS]) if CHANNEL_IDS else "هیچ چنلی ثبت نشده"
    await call.message.edit_text(f"✅ چنل {ch} حذف شد!\n\n📡 چنل‌های فعلی:\n{ch_list}\n\nبرای حذف روی چنل بزن:",
        reply_markup=channels_keyboard())

# ==================== مدیریت ادمین‌ها ====================
@dp.callback_query(F.data == "admin_manage_admins")
async def cb_manage_admins(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        await call.answer("❌ فقط ادمین اصلی دسترسی دارد.", show_alert=True); return
    await call.answer()
    rows = []
    for uid_str, perms in SUB_ADMINS.items():
        active = sum(1 for v in perms.values() if v)
        rows.append([InlineKeyboardButton(text=f"👤 {uid_str} | {active}/{len(ALL_PERMS)} دسترسی",
            callback_data=f"admin_editadmin_{uid_str}")])
    rows.append([InlineKeyboardButton(text=get_button_text("add_admin"), callback_data="admin_addadmin", style=ButtonStyle.SUCCESS)])
    rows.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    count = len(SUB_ADMINS)
    await call.message.edit_text(
        f"👤 مدیریت ادمین‌ها\n━━━━━━━━━━━━━━━\n\nادمین‌های فعلی: {count} نفر\n\nروی ادمین بزن تا دسترسی‌هاشو تنظیم کنی:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data == "admin_addadmin")
async def cb_add_admin(call: CallbackQuery, state: FSMContext):
    if not is_super_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AdminStates.add_admin_id)
    await call.message.edit_text(
        "➕ اضافه کردن ادمین جدید\n\nآیدی عددی یا یوزرنیم @ کاربر رو بفرست:\nمثال: 123456789 یا @username",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_manage_admins")]]))

@dp.message(AdminStates.add_admin_id)
async def hdl_add_admin_id(message: Message, state: FSMContext):
    global SUB_ADMINS
    if not is_super_admin(message.from_user.id): return
    text = message.text.strip().lstrip("@")
    if not text.isdigit():
        await message.answer("❌ لطفاً آیدی عددی بفرست (نه یوزرنیم):"); return
    uid_str = text
    if uid_str not in SUB_ADMINS:
        SUB_ADMINS[uid_str] = {p: False for p in ALL_PERMS}
        cfg = load_config(); cfg["sub_admins"] = SUB_ADMINS; save_config(cfg)
    await state.clear()
    await message.answer(
        f"✅ ادمین {uid_str} اضافه شد!\nالان دسترسی‌هاشو تنظیم کن:",
        reply_markup=sub_admin_perms_keyboard(int(uid_str)))

@dp.callback_query(F.data.startswith("admin_editadmin_"))
async def cb_edit_admin(call: CallbackQuery):
    if not is_super_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.replace("admin_editadmin_", ""))
    perms = SUB_ADMINS.get(str(target_id), {})
    active = sum(1 for v in perms.values() if v)
    await call.message.edit_text(
        f"👤 ادمین: {target_id}\n━━━━━━━━━━━━━━━\n"
        f"دسترسی‌های فعال: {active}/{len(ALL_PERMS)}\n\nروی هر گزینه بزن تا آن/آف بشه:",
        reply_markup=sub_admin_perms_keyboard(target_id))

@dp.callback_query(F.data.startswith("admin_toggleperm_"))
async def cb_toggle_perm(call: CallbackQuery):
    global SUB_ADMINS
    if not is_super_admin(call.from_user.id): return
    await call.answer()
    parts = call.data.replace("admin_toggleperm_", "").split("_", 1)
    target_id = parts[0]
    perm = parts[1]
    if target_id not in SUB_ADMINS:
        SUB_ADMINS[target_id] = {p: False for p in ALL_PERMS}
    current = SUB_ADMINS[target_id].get(perm, False)
    SUB_ADMINS[target_id][perm] = not current
    cfg = load_config(); cfg["sub_admins"] = SUB_ADMINS; save_config(cfg)
    active = sum(1 for v in SUB_ADMINS[target_id].values() if v)
    await call.message.edit_text(
        f"👤 ادمین: {target_id}\n━━━━━━━━━━━━━━━\n"
        f"دسترسی‌های فعال: {active}/{len(ALL_PERMS)}\n\nروی هر گزینه بزن تا آن/آف بشه:",
        reply_markup=sub_admin_perms_keyboard(int(target_id)))

@dp.callback_query(F.data.startswith("admin_removeadmin_"))
async def cb_remove_admin(call: CallbackQuery):
    global SUB_ADMINS
    if not is_super_admin(call.from_user.id): return
    await call.answer()
    target_id = call.data.replace("admin_removeadmin_", "")
    SUB_ADMINS.pop(target_id, None)
    cfg = load_config(); cfg["sub_admins"] = SUB_ADMINS; save_config(cfg)
    rows = []
    for uid_str, perms in SUB_ADMINS.items():
        active = sum(1 for v in perms.values() if v)
        rows.append([InlineKeyboardButton(text=f"👤 {uid_str} | {active}/{len(ALL_PERMS)} دسترسی",
            callback_data=f"admin_editadmin_{uid_str}")])
    rows.append([InlineKeyboardButton(text=get_button_text("add_admin"), callback_data="admin_addadmin", style=ButtonStyle.SUCCESS)])
    rows.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    await call.message.edit_text(
        f"✅ ادمین {target_id} حذف شد!\n\n👤 مدیریت ادمین‌ها\nادمین‌های فعلی: {len(SUB_ADMINS)} نفر",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

# ==================== لغو ====================
@dp.callback_query(F.data == "admin_cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text("❌ عملیات لغو شد.", reply_markup=admin_keyboard(call.from_user.id))

# ==================== ابزارهای امکانات ویژه ====================
GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]

async def _gemini_call(model: str, contents: list) -> tuple[str | None, str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": contents}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(url, json=payload) as r:
            data = await r.json()
            if "candidates" in data:
                parts = data["candidates"][0].get("content", {}).get("parts", [])
                texts = [p.get("text", "") for p in parts if p.get("text")]
                return "\n".join(texts).strip() or None, "ok"
            err = data.get("error", {}).get("message", "نامشخص")
            return None, err

async def gemini_text(prompt: str, history: list | None = None) -> str:
    if aiohttp is None:
        return "❌ کتابخانه aiohttp نصب نیست."
    contents = []
    if history:
        for h in history[-10:]:
            contents.append({"role": h["role"], "parts": [{"text": h["text"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    last_err = "خطای ناشناخته"
    for model in GEMINI_FALLBACK_MODELS:
        for attempt in range(2):
            try:
                ans, err = await _gemini_call(model, contents)
                if ans:
                    return ans
                last_err = err
                low = err.lower()
                if any(k in low for k in ["overload", "high demand", "unavailable", "rate", "quota", "429", "503"]):
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                break
            except Exception as e:
                last_err = str(e)
                await asyncio.sleep(1.0)
    return f"❌ خطا: {last_err}\n\nلطفاً چند ثانیه بعد دوباره امتحان کن."

async def gemini_image(prompt: str) -> bytes | None:
    if aiohttp is None:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}
    try:
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(url, json=payload) as r:
                data = await r.json()
                if "candidates" not in data:
                    return None
                for p in data["candidates"][0].get("content", {}).get("parts", []):
                    inline = p.get("inlineData") or p.get("inline_data")
                    if inline and inline.get("data"):
                        return base64.b64decode(inline["data"])
        return None
    except Exception as e:
        logger.warning(f"gemini_image error: {e}")
        return None

def make_text_logo(name: str) -> bytes:
    if Image is None:
        return b""
    import random
    W, H = 1024, 1024
    palettes = [((20, 30, 80), (250, 200, 80)), ((10, 60, 50), (255, 255, 255)),
                ((100, 0, 80), (255, 220, 240)), ((0, 60, 100), (255, 255, 200)),
                ((80, 0, 0), (255, 200, 100))]
    bg, fg = random.choice(palettes)
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 180)
    except:
        try: font = ImageFont.truetype("DejaVuSans-Bold.ttf", 180)
        except: font = ImageFont.load_default()
    text = name[:18]
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) / 2 - bbox[0]
    y = (H - th) / 2 - bbox[1]
    d.rectangle([60, 60, W - 60, H - 60], outline=fg, width=8)
    d.text((x, y), text, fill=fg, font=font)
    out = io.BytesIO(); img.save(out, "PNG"); return out.getvalue()

PLATFORM_INFO = {
    "tiktok":    ("تیک تاک",   ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"]),
    "instagram": ("اینستاگرام", ["instagram.com", "instagr.am"]),
    "youtube":   ("یوتوب",      ["youtube.com", "youtu.be", "m.youtube.com"]),
    "twitter":   ("توییتر / X", ["twitter.com", "x.com", "mobile.twitter.com"]),
}

def url_belongs_to(url: str, platform: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except:
        return False
    return any(d in host for d in PLATFORM_INFO[platform][1])

def detect_platform(url: str) -> str | None:
    for p in PLATFORM_INFO:
        if url_belongs_to(url, p):
            return p
    return None

async def yt_dlp_download(url: str, audio_only: bool = False, max_mb: int = 49) -> tuple[str | None, str]:
    if not shutil.which("yt-dlp"):
        return None, "❌ ابزار yt-dlp نصب نیست. روی VPS بزن:\npip install yt-dlp"
    tmpdir = tempfile.mkdtemp(prefix="dl_")
    out_tpl = os.path.join(tmpdir, "%(title).80s.%(ext)s")
    common = [
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "--add-header", "Accept-Language:en-US,en;q=0.9",
        "--retries", "5", "--fragment-retries", "5",
        "--retry-sleep", "exp=2:30",
        "--sleep-requests", "1", "--sleep-interval", "1", "--max-sleep-interval", "5",
        "--no-warnings", "--no-check-certificate",
    ]
    if audio_only:
        cmd = ["yt-dlp", *common, "-x", "--audio-format", "mp3", "--audio-quality", "5",
               "-o", out_tpl, "--no-playlist", "--max-filesize", f"{max_mb}M", url]
    else:
        cmd = ["yt-dlp", *common, "-f", f"best[filesize<{max_mb}M]/best[height<=720]/best",
               "-o", out_tpl, "--no-playlist", "--max-filesize", f"{max_mb}M",
               "--merge-output-format", "mp4", url]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=180)
        except asyncio.TimeoutError:
            proc.kill(); return None, "⏱ زمان دانلود تموم شد."
        files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
        if not files:
            msg = (err.decode(errors="ignore")[-400:] if err else "نامشخص")
            return None, f"❌ دانلود ناموفق:\n{msg}"
        return max(files, key=os.path.getsize), tmpdir
    except Exception as e:
        return None, f"❌ خطا: {e}"

async def yt_dlp_search_audio(query: str, max_mb: int = 49) -> tuple[str | None, str]:
    if not shutil.which("yt-dlp"):
        return None, "❌ ابزار yt-dlp نصب نیست."
    return await yt_dlp_download(f"ytsearch1:{query}", audio_only=True, max_mb=max_mb)

# ==================== منوی امکانات ویژه ====================
@dp.callback_query(F.data == "special_menu")
async def cb_special_menu(call: CallbackQuery, state: FSMContext):
    await state.clear(); await call.answer()
    await call.message.edit_text(
        "✨ امکانات ویژه\n━━━━━━━━━━━━━━━\n\nیکی از قابلیت‌ها رو انتخاب کن 👇",
        reply_markup=special_features_keyboard())

# ==================== لایک ساز ====================
@dp.callback_query(F.data == "sf_like")
async def cb_sf_like(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(SpecialStates.like_link)
    me = await bot.get_me()
    await call.message.edit_text(
        f"👍 لایک ساز\n━━━━━━━━━━━━━━━\n\n"
        f"۱) ربات (@{me.username}) رو توی چنل خودت ادمین کن (دسترسی ارسال پست بده)\n"
        f"۲) لینک یا یوزرنیم چنلت رو بفرست (مثل @mychannel)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="special_menu")]]))

@dp.message(SpecialStates.like_link)
async def hdl_like_link(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    m = re.search(r"(?:t\.me/|@)([A-Za-z0-9_]+)", raw)
    if m:
        username = "@" + m.group(1)
    elif raw.startswith("@"):
        username = raw
    elif raw.lstrip("-").isdigit():
        username = raw
    else:
        await message.answer("❌ لینک یا یوزرنیم معتبر بفرست (مثل @mychannel)."); return
    try:
        chat = await bot.get_chat(username)
    except Exception as e:
        await message.answer(f"❌ نتونستم چنل رو پیدا کنم. مطمئن شو ربات داخل چنل ادمینه.\n\nخطا: {e}"); return
    try:
        admins = await bot.get_chat_administrators(chat.id)
    except Exception as e:
        await message.answer(f"❌ ربات داخل چنل ادمین نیست. اول ادمینش کن.\n\nخطا: {e}"); return
    me = await bot.get_me()
    is_owner = any(a.user.id == message.from_user.id and a.status == "creator" for a in admins)
    bot_is_admin = any(a.user.id == me.id for a in admins)
    if not bot_is_admin:
        await message.answer("❌ ربات هنوز ادمین چنل نیست."); return
    if not is_owner:
        await message.answer("❌ فقط مالک (سازنده) چنل می‌تونه از این قابلیت استفاده کنه."); return
    await state.update_data(like_chat_id=chat.id, like_chat_username=chat.username or "", like_chat_title=chat.title)
    await state.set_state(SpecialStates.like_name)
    await message.answer(
        f"✅ مالکیت چنل «{chat.title}» تایید شد.\n\n"
        f"حالا اسم/متن لایک رو بفرست (مثلاً: «بهترین آهنگ ۱۴۰۳»):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="special_menu")]]))

@dp.message(SpecialStates.like_name)
async def hdl_like_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ متن خالی نمی‌شه."); return
    data = await state.get_data()
    chat_id = data["like_chat_id"]
    ch_username = data.get("like_chat_username", "")
    placeholder_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{get_button_text('like_btn')} 0", callback_data="like_pending", style=style_of("like_btn"))
    ]])
    try:
        sent = await bot.send_message(chat_id, f"👍 {name}", reply_markup=placeholder_kb)
    except Exception as e:
        await state.clear()
        await message.answer(f"❌ ارسال پست ناموفق: {e}"); return
    key = f"{chat_id}:{sent.message_id}"
    LIKE_POSTS[key] = {"name": name, "owner": message.from_user.id,
                       "channel_username": ch_username, "channel_id": chat_id, "likers": []}
    real_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{get_button_text('like_btn')} 0", callback_data=f"like_{chat_id}_{sent.message_id}", style=style_of("like_btn"))
    ]])
    try:
        await bot.edit_message_reply_markup(chat_id, sent.message_id, reply_markup=real_kb)
    except: pass
    save_like_posts()
    await state.clear()
    link = f"https://t.me/{ch_username}/{sent.message_id}" if ch_username else "(چنل خصوصی)"
    await message.answer(f"✅ پست لایک ساخته شد!\n📍 لینک پست: {link}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

@dp.callback_query(F.data.startswith("like_"))
async def cb_like_press(call: CallbackQuery):
    if call.data == "like_pending":
        await call.answer("⏳ لطفاً چند لحظه بعد دوباره امتحان کن.", show_alert=True); return
    try:
        parts = call.data.split("_", 2)
        chat_id = int(parts[1]); msg_id = int(parts[2])
    except Exception as e:
        logger.warning(f"like parse err: {e} data={call.data}")
        await call.answer("❌ خطای داخلی.", show_alert=True); return
    key = f"{chat_id}:{msg_id}"
    post = LIKE_POSTS.get(key)
    if not post:
        await call.answer("❌ این پست منقضی شده.", show_alert=True); return
    user_id = call.from_user.id
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        status = str(getattr(member, "status", "") or "").lower()
        if any(x in status for x in ("left", "kicked", "banned")):
            ch = post.get("channel_username", "")
            link = f"@{ch}" if ch else "چنل"
            await call.answer(f"❌ اول باید عضو {link} بشی!", show_alert=True); return
    except Exception as e:
        logger.info(f"like membership check skipped: {e}")
    likers = post.setdefault("likers", [])
    if user_id in likers:
        await call.answer("✅ قبلاً لایک کردی.", show_alert=True); return
    likers.append(user_id)
    save_like_posts()
    cnt = len(likers)
    btn_text = f"{get_button_text('like_btn')} {cnt}".strip()
    new_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=btn_text, callback_data=f"like_{chat_id}_{msg_id}", style=style_of("like_btn"))
    ]])
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=new_kb)
    except Exception as e:
        logger.warning(f"like edit_markup err: {e}")
    await call.answer("♥️ لایکت ثبت شد!")

# ==================== هوش مصنوعی ====================
AI_CHAT_HISTORY: dict[int, list] = {}

def _ai_stop_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛔️ توقف چت", callback_data="ai_stop", style=ButtonStyle.DEFAULT)]])

@dp.callback_query(F.data == "sf_ai")
async def cb_sf_ai(call: CallbackQuery, state: FSMContext):
    await call.answer()
    AI_CHAT_HISTORY[call.from_user.id] = []
    await state.set_state(SpecialStates.ai_chat)
    await call.message.edit_text(
        "🤖 هوش مصنوعی\n━━━━━━━━━━━━━━━\n\n"
        "حالا تا وقتی که دکمه «توقف چت» رو نزنی، هر پیامی بفرستی پاسخ می‌دم و\n"
        "تاریخچه گفتگو رو هم به‌خاطر می‌سپرم.\n\nسؤالت رو بفرست 👇",
        reply_markup=_ai_stop_kb())

@dp.callback_query(F.data == "ai_stop", SpecialStates.ai_chat)
async def cb_ai_stop(call: CallbackQuery, state: FSMContext):
    AI_CHAT_HISTORY.pop(call.from_user.id, None)
    await state.clear()
    await call.answer("چت بسته شد")
    try: await call.message.edit_reply_markup(reply_markup=None)
    except: pass
    await call.message.answer("✅ چت هوش مصنوعی بسته شد.", reply_markup=special_features_keyboard())

@dp.message(SpecialStates.ai_chat)
async def hdl_ai_chat(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt:
        await message.answer("❌ متن بفرست.", reply_markup=_ai_stop_kb()); return
    uid = message.from_user.id
    history = AI_CHAT_HISTORY.setdefault(uid, [])
    wait = await message.answer("🤖 در حال فکر کردن...")
    answer = await gemini_text(txt, history=history)
    try: await wait.delete()
    except: pass
    if not answer.startswith("❌"):
        history.append({"role": "user",  "text": txt})
        history.append({"role": "model", "text": answer})
        if len(history) > 20:
            del history[:len(history) - 20]
    chunks = [answer[i:i+4000] for i in range(0, len(answer), 4000)] or [answer]
    for i, chunk in enumerate(chunks):
        kb = _ai_stop_kb() if i == len(chunks) - 1 else None
        await message.answer(chunk, reply_markup=kb)

# ==================== دانلودر ویدیو ====================
@dp.callback_query(F.data == "sf_dl")
async def cb_sf_dl(call: CallbackQuery, state: FSMContext):
    await state.clear(); await call.answer()
    await call.message.edit_text(
        "📥 دانلودر ویدیو\n━━━━━━━━━━━━━━━\n\nاز کدوم پلتفرم می‌خوای دانلود کنی؟",
        reply_markup=downloader_keyboard())

@dp.callback_query(F.data.in_({"dl_tiktok", "dl_instagram", "dl_youtube", "dl_twitter"}))
async def cb_dl_choose(call: CallbackQuery, state: FSMContext):
    await call.answer()
    platform = call.data.replace("dl_", "")
    name = PLATFORM_INFO[platform][0]
    await state.update_data(dl_platform=platform)
    await state.set_state(SpecialStates.dl_link)
    await call.message.edit_text(
        f"📥 دانلود از {name}\n\nلینک پست/ویدیو رو بفرست 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="sf_dl")]]))

@dp.message(SpecialStates.dl_link)
async def hdl_dl_link(message: Message, state: FSMContext):
    data = await state.get_data()
    platform = data.get("dl_platform")
    txt = (message.text or "").strip()
    m = re.search(r"https?://\S+", txt)
    if not m:
        await message.answer("❌ لینک معتبر بفرست (با http یا https)."); return
    url = m.group(0)
    if not url_belongs_to(url, platform):
        actual = detect_platform(url)
        actual_name = PLATFORM_INFO[actual][0] if actual else "نامشخص"
        await message.answer(
            f"❌ این لینک برای {PLATFORM_INFO[platform][0]} نیست!\n"
            f"این لینک متعلق به: {actual_name}\n\nلطفاً لینک درست بفرست یا از منوی دانلودر پلتفرم درست رو بزن.",
            reply_markup=downloader_keyboard())
        await state.clear(); return
    wait = await message.answer("⏳ در حال دانلود... (تا چند ثانیه)")
    path, info = await yt_dlp_download(url, audio_only=False)
    await state.clear()
    try: await wait.delete()
    except: pass
    if not path:
        await message.answer(info, reply_markup=special_features_keyboard()); return
    try:
        await bot.send_video(message.chat.id, FSInputFile(path),
            caption=f"✅ از {PLATFORM_INFO[platform][0]} دانلود شد.")
    except Exception as e:
        try:
            await bot.send_document(message.chat.id, FSInputFile(path), caption="✅ دانلود شد")
        except Exception as e2:
            await message.answer(f"❌ ارسال ناموفق: {e2}")
    finally:
        try: shutil.rmtree(info)
        except: pass
    await message.answer("✨ یه چیز دیگه؟", reply_markup=special_features_keyboard())

# ==================== موسیقی MP3 ====================
@dp.callback_query(F.data == "sf_music")
async def cb_sf_music(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(SpecialStates.music_query)
    await call.message.edit_text(
        "🎵 موسیقی MP3\n━━━━━━━━━━━━━━━\n\nاسم آهنگ یا خواننده رو بفرست تا پیدا کنم 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="special_menu")]]))

@dp.message(SpecialStates.music_query)
async def hdl_music_query(message: Message, state: FSMContext):
    q = (message.text or "").strip()
    if not q:
        await message.answer("❌ اسم آهنگ بفرست."); return
    wait = await message.answer(f"🔎 در حال جستجو و دانلود «{q}»...")
    path, info = await yt_dlp_search_audio(q)
    await state.clear()
    try: await wait.delete()
    except: pass
    if not path:
        await message.answer(info, reply_markup=special_features_keyboard()); return
    try:
        await bot.send_audio(message.chat.id, FSInputFile(path), title=q[:60], caption=f"🎵 {q}")
    except Exception as e:
        await message.answer(f"❌ ارسال ناموفق: {e}")
    finally:
        try: shutil.rmtree(info)
        except: pass
    await message.answer("✨ یه چیز دیگه؟", reply_markup=special_features_keyboard())

# ==================== ساخت لوگو ====================
@dp.callback_query(F.data == "sf_logo")
async def cb_sf_logo(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(SpecialStates.logo_name)
    await call.message.edit_text(
        "🎨 ساخت لوگو\n━━━━━━━━━━━━━━━\n\nاسم/متنی که می‌خوای روی لوگو باشه رو بفرست 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="special_menu")]]))

@dp.message(SpecialStates.logo_name)
async def hdl_logo_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ یک اسم بفرست."); return
    wait = await message.answer("🎨 در حال ساخت لوگو...")
    prompt = (f"Create a clean modern minimalist logo with the text \"{name}\" prominently displayed, "
              f"high quality, vector style, square 1:1, professional branding, vibrant colors, transparent or simple background.")
    img_bytes = await gemini_image(prompt)
    if not img_bytes:
        img_bytes = make_text_logo(name)
    await state.clear()
    try: await wait.delete()
    except: pass
    if not img_bytes:
        await message.answer("❌ ساخت لوگو ممکن نشد.", reply_markup=special_features_keyboard()); return
    await bot.send_photo(message.chat.id, BufferedInputFile(img_bytes, filename=f"logo_{name[:20]}.png"),
                         caption=f"🎨 لوگوی «{name}»")
    await message.answer("✨ یه چیز دیگه؟", reply_markup=special_features_keyboard())

# ==================== ویس به MP3 ====================
@dp.callback_query(F.data == "sf_voice")
async def cb_sf_voice(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(SpecialStates.voice_title)
    await state.update_data(voice_file_id=None)
    await call.message.edit_text(
        "🎙 ویس به MP3\n━━━━━━━━━━━━━━━\n\nاول یک ویس بفرست 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="special_menu")]]))

@dp.message(SpecialStates.voice_title, F.voice | F.audio)
async def hdl_voice_received(message: Message, state: FSMContext):
    file_id = message.voice.file_id if message.voice else message.audio.file_id
    await state.update_data(voice_file_id=file_id)
    await message.answer("✅ ویس دریافت شد.\nحالا اسمی که روی آهنگ بشینه رو بفرست (مثلاً: bad boy):")

@dp.message(SpecialStates.voice_title, F.text)
async def hdl_voice_title(message: Message, state: FSMContext):
    data = await state.get_data()
    file_id = data.get("voice_file_id")
    if not file_id:
        await message.answer("❌ اول یک ویس بفرست."); return
    title = (message.text or "").strip()
    if not title:
        await message.answer("❌ اسم بفرست."); return
    if not shutil.which("ffmpeg"):
        await state.clear()
        await message.answer("❌ ابزار ffmpeg نصب نیست. روی VPS بزن:\napt install ffmpeg",
                             reply_markup=special_features_keyboard()); return
    wait = await message.answer("⏳ در حال تبدیل...")
    tmpdir = tempfile.mkdtemp(prefix="v2m_")
    try:
        ogg_path = os.path.join(tmpdir, "in.ogg")
        mp3_path = os.path.join(tmpdir, f"{re.sub(r'[^A-Za-z0-9_-]+','_', title)[:40] or 'song'}.mp3")
        f = await bot.get_file(file_id)
        await bot.download_file(f.file_path, destination=ogg_path)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", ogg_path, "-vn", "-ab", "192k", "-ar", "44100", mp3_path,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc.wait()
        if not os.path.exists(mp3_path):
            raise RuntimeError("ffmpeg failed")
        if MP3 is not None and ID3 is not None:
            try:
                tags = ID3()
                tags.add(TIT2(encoding=3, text=title))
                tags.add(TPE1(encoding=3, text=title))
                tags.save(mp3_path)
            except Exception as e:
                logger.warning(f"id3 tag error: {e}")
        await state.clear()
        try: await wait.delete()
        except: pass
        await bot.send_audio(message.chat.id, FSInputFile(mp3_path), title=title, performer=title)
        await message.answer("✨ یه چیز دیگه؟", reply_markup=special_features_keyboard())
    except Exception as e:
        await state.clear()
        try: await wait.delete()
        except: pass
        await message.answer(f"❌ خطا در تبدیل: {e}", reply_markup=special_features_keyboard())
    finally:
        try: shutil.rmtree(tmpdir)
        except: pass

# ==================== تنظیم رنگ دکمه‌ها ====================
def colors_list_keyboard(page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    items = list(BUTTON_NAMES.items())
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    rows = []
    color_emoji = {"primary": "🔵", "danger": "🔴", "success": "🟢", "default": "⚪"}
    for key, name in items[start:start + per_page]:
        cur = get_btn_color(key)
        rows.append([InlineKeyboardButton(text=f"{color_emoji.get(cur,'⚪')} {name}",
                                          callback_data=f"admin_colorpick_{key}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=get_button_text("prev_page"), callback_data=f"admin_colors_{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text=get_button_text("next_page"), callback_data=f"admin_colors_{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.callback_query(F.data.startswith("admin_colors_"))
async def cb_admin_colors(call: CallbackQuery):
    if not has_perm(call.from_user.id, "colors"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    try: page = int(call.data.replace("admin_colors_", ""))
    except: page = 0
    await call.message.edit_text(
        "🎨 تنظیم رنگ دکمه‌ها\n━━━━━━━━━━━━━━━\n\n"
        "روی دکمه‌ای که می‌خوای رنگش رو عوض کنی بزن:\n"
        "🔵 آبی | 🔴 قرمز | 🟢 سبز | ⚪ معمولی (شیشه‌ای)",
        reply_markup=colors_list_keyboard(page))

@dp.callback_query(F.data.startswith("admin_colorpick_"))
async def cb_admin_color_pick(call: CallbackQuery):
    if not has_perm(call.from_user.id, "colors"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    key = call.data.replace("admin_colorpick_", "")
    name = BUTTON_NAMES.get(key, key)
    cur = get_btn_color(key)
    color_fa = {"primary": "🔵 آبی", "danger": "🔴 قرمز", "success": "🟢 سبز", "default": "⚪ معمولی"}
    rows = [
        [InlineKeyboardButton(text=get_button_text("color_red"),     callback_data=f"admin_setcolor_{key}_danger",  style=ButtonStyle.DANGER)],
        [InlineKeyboardButton(text=get_button_text("color_green"),   callback_data=f"admin_setcolor_{key}_success", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton(text=get_button_text("color_blue"),    callback_data=f"admin_setcolor_{key}_primary", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton(text=get_button_text("color_default"), callback_data=f"admin_setcolor_{key}_default", style=ButtonStyle.DEFAULT)],
        [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="admin_colors_0")],
    ]
    await call.message.edit_text(
        f"🎨 تغییر رنگ\n━━━━━━━━━━━━━━━\n\n"
        f"دکمه: {name}\nرنگ فعلی: {color_fa.get(cur,'⚪ معمولی')}\n\nرنگ جدید رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data.startswith("admin_setcolor_"))
async def cb_admin_set_color(call: CallbackQuery):
    if not has_perm(call.from_user.id, "colors"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    rest = call.data.replace("admin_setcolor_", "")
    last = rest.rfind("_")
    if last == -1:
        await call.answer(); return
    key, color = rest[:last], rest[last+1:]
    if color not in _COLOR_TO_STYLE:
        await call.answer("❌ رنگ نامعتبر.", show_alert=True); return
    save_btn_color(key, color)
    await call.answer("✅ رنگ ذخیره شد.")
    await call.message.edit_text(
        "🎨 تنظیم رنگ دکمه‌ها\n━━━━━━━━━━━━━━━\n\n✅ رنگ با موفقیت تغییر کرد.\n\n"
        "روی دکمه دیگری بزن یا برگرد:",
        reply_markup=colors_list_keyboard(0))

# ==================== main ====================
async def main():
    global bot
    init_db()
    bot = Bot(token=BOT_TOKEN)
    print("✅ ربات شروع به کار کرد...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
