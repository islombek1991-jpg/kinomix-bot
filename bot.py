import os
import sqlite3
import logging
from typing import List, Tuple, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =======================
# LOG
# =======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("kinomix-bot")

# =======================
# ENV (faqat BOT_TOKEN shart)
# =======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "data.db").strip()

# Adminlar (ixtiyoriy) "5491302235,123456789"
ADMIN_IDS: List[int] = []
_raw_admins = os.getenv("ADMIN_IDS", "").strip()
if _raw_admins:
    for x in _raw_admins.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.append(int(x))

# Majburiy obuna kanallari (ixtiyoriy) "@kanal1,@kanal2"
FORCE_CHANNELS: List[str] = []
_raw_channels = os.getenv("FORCE_CHANNELS", "").strip()
if _raw_channels:
    for ch in _raw_channels.split(","):
        ch = ch.strip()
        if ch:
            # @ bo'lmasa qo'shib yuboramiz
            FORCE_CHANNELS.append(ch if ch.startswith("@") else f"@{ch}")

# Instagram (faqat tugma, tekshirmaydi)
IG_URL = os.getenv("IG_URL", "https://www.instagram.com/kino.isboysbot").strip()

CHANNEL_URL = os.getenv("CHANNEL_URL", "").strip()  # ixtiyoriy: kanal linki tugma uchun (https://t.me/...)
BOT_NAME = os.getenv("BOT_NAME", "KinoMix TV").strip()

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN yo'q. Railway Variables ga BOT_TOKEN qo'ying.")

# =======================
# DB
# =======================
def db_conn():
    return sqlite3.connect(DB_PATH)

def db_init():
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url   TEXT NOT NULL,
                views INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.commit()

def db_add_movie(code: str, title: str, url: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO movies(code,title,url,views) VALUES(?,?,?,COALESCE((SELECT views FROM movies WHERE code=?),0))",
            (code, title, url, code),
        )
        con.commit()

def db_get_movie(code: str) -> Optional[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT title, url, views FROM movies WHERE code=?", (code,))
        return cur.fetchone()

def db_inc_view(code: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("UPDATE movies SET views = views + 1 WHERE code=?", (code,))
        con.commit()

def db_list_movies(limit: int = 50) -> List[Tuple[str, str]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title FROM movies ORDER BY rowid DESC LIMIT ?", (limit,))
        return cur.fetchall()

def db_top_movies(limit: int = 10) -> List[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title, views FROM movies ORDER BY views DESC LIMIT ?", (limit,))
        return cur.fetchall()

# =======================
# UI (tugmalar)
# =======================
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎬 Kino kodi yuborish")],
            [KeyboardButton("📃 Ro‘yxat"), KeyboardButton("⭐ TOP")],
            [KeyboardButton("📢 Kanal"), KeyboardButton("📸 Instagram")],
            [KeyboardButton("🆘 Yordam")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def sub_keyboard(not_joined: List[str]) -> InlineKeyboardMarkup:
    btns = []
    for ch in not_joined:
        # kanalga link: @kanal -> https://t.me/kanal
        link = f"https://t.me/{ch.lstrip('@')}"
        btns.append([InlineKeyboardButton(f"➕ {ch}", url=link)])
    btns.append([InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data="check_sub")])
    if IG_URL:
        btns.append([InlineKeyboardButton("📸 Instagram", url=IG_URL)])
    return InlineKeyboardMarkup(btns)

def links_keyboard() -> InlineKeyboardMarkup:
    btns = []
    if CHANNEL_URL:
        btns.append([InlineKeyboardButton("📢 Kanalga o‘tish", url=CHANNEL_URL)])
    if IG_URL:
        btns.append([InlineKeyboardButton("📸 Instagram", url=IG_URL)])
    return InlineKeyboardMarkup(btns) if btns else InlineKeyboardMarkup(
        [[InlineKeyboardButton("📸 Instagram", url=IG_URL)]]
    )

# =======================
# Helpers
# =======================
def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return True  # xohlasang: False qilib qo'yamiz
    return user_id in ADMIN_IDS

async def safe_send(update: Update, text: str, reply_markup=None):
    """
    Hech qanaqa parse_mode ishlatmaymiz.
    Shu sabab BadRequest (parse entities) bo'lmaydi.
    """
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup, disable_web_page_preview=True)

async def get_not_joined(update: Update, context: ContextTypes.DEFAULT_TYPE) -> List[str]:
    if not FORCE_CHANNELS:
        return []
    user = update.effective_user
    if not user:
        return FORCE_CHANNELS[:]  # xavfsiz
    not_joined = []
    for ch in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(ch, user.id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            # bot kanalga admin bo'lmasa ham bu yerga tushishi mumkin
            not_joined.append(ch)
    return not_joined

async def require_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    not_joined = await get_not_joined(update, context)
    if not not_joined:
        return True
    txt = (
        "🔒 Botdan foydalanish uchun kanalga obuna bo‘ling.\n\n"
        "1) Pastdagi kanal(lar)ga kiring\n"
        "2) Obuna bo‘ling\n"
        "3) ✅ Obuna bo‘ldim tugmasini bosing"
    )
    await safe_send(update, txt, reply_markup=sub_keyboard(not_joined))
    return False

# =======================
# Handlers
# =======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = await require_sub(update, context)
    if not ok:
        return
    txt = (
        f"🎬 {BOT_NAME} botga xush kelibsiz!\n\n"
        "✅ Kino yoki serial kodini yuboring (masalan: 101)\n"
        "📌 Tugmalar orqali ham ishlaydi.\n"
    )
    await safe_send(update, txt, reply_markup=main_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🆘 Yordam\n\n"
        "🎬 Kino ko‘rish: shunchaki KOD yuborasiz (101)\n"
        "📃 Ro‘yxat: 50 ta oxirgi qo‘shilgan\n"
        "⭐ TOP: eng ko‘p ko‘rilganlar\n\n"
        "👑 Admin uchun kino qo‘shish:\n"
        "/add KOD | NOMI | LINK\n"
        "Misol:\n"
        "/add 02 | Troll | https://t.me/IsboySkinolar_olami/4\n"
    )
    await safe_send(update, txt, reply_markup=main_keyboard())

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = await require_sub(update, context)
    if not ok:
        return
    rows = db_list_movies(50)
    if not rows:
        await safe_send(update, "Hozircha kino yo‘q. Admin /add bilan qo‘shadi.", reply_markup=main_keyboard())
        return
    text = "📃 Oxirgi qo‘shilgan kinolar:\n\n" + "\n".join([f"{c} — {t}" for c, t in rows])
    await safe_send(update, text, reply_markup=main_keyboard())

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = await require_sub(update, context)
    if not ok:
        return
    rows = db_top_movies(10)
    if not rows:
        await safe_send(update, "TOP hozircha yo‘q. Avval kino qo‘shing.", reply_markup=main_keyboard())
        return
    lines = []
    n = 1
    for code, title, views in rows:
        lines.append(f"{n}) {code} — {title} ({views} ta ko‘rildi)")
        n += 1
    await safe_send(update, "⭐ TOP kinolar:\n\n" + "\n".join(lines), reply_markup=main_keyboard())

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return

    raw = (msg.text or "").replace("/add", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await msg.reply_text(
            "❌ Format xato.\n"
            "To‘g‘risi: /add KOD | NOMI | LINK\n"
            "Misol: /add 02 | Troll | https://t.me/kanal/123"
        )
        return

    code, title, url = parts
    if not code:
        await msg.reply_text("❌ KOD bo‘sh bo‘lmasin.")
        return
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/")):
        await msg.reply_text("❌ LINK noto‘g‘ri. https://... bo‘lsin.")
        return

    db_add_movie(code, title, url)
    await msg.reply_text(f"✅ Qo‘shildi: {code} — {title}")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    text = (msg.text or "").strip()

    # Tugma matnlari
    if text == "📃 Ro‘yxat":
        await list_cmd(update, context); return
    if text == "⭐ TOP":
        await top_cmd(update, context); return
    if text == "🆘 Yordam":
        await help_cmd(update, context); return
    if text == "📢 Kanal":
        await safe_send(update, "📢 Kanal va sahifalar:", reply_markup=links_keyboard()); return
    if text == "📸 Instagram":
        await safe_send(update, "📸 Instagram:", reply_markup=links_keyboard()); return
    if text == "🎬 Kino kodi yuborish":
        await safe_send(update, "Kino/serial kodini yuboring (masalan: 101).", reply_markup=main_keyboard()); return

    # Oddiy kod qabul
    ok = await require_sub(update, context)
    if not ok:
        return

    if text.startswith("/"):
        return

    row = db_get_movie(text)
    if not row:
        await safe_send(update, "❌ Bunday kod topilmadi. (Kodni tekshirib qayta yuboring)", reply_markup=main_keyboard())
        return

    title, url, views = row
    db_inc_view(text)
    await safe_send(update, f"🎬 {title}\n🔗 {url}", reply_markup=main_keyboard())

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    if q.data == "check_sub":
        ok = await require_sub(update, context)
        if ok:
            await safe_send(update, "✅ Rahmat! Endi kino kodini yuboring.", reply_markup=main_keyboard())

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("ERROR: %s", context.error)

def main():
    db_init()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("add", add_cmd))

    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.add_error_handler(error_handler)

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
