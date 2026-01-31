import os
import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()  # majburiy
DB_PATH = os.getenv("DB_PATH", "data.db").strip()  # ixtiyoriy

# Adminlar: "5491302235,123456789" (ixtiyoriy)
ADMIN_IDS: List[int] = []
_raw_admins = os.getenv("ADMIN_IDS", "").strip()
if _raw_admins:
    for x in _raw_admins.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.append(int(x))

# Majburiy obuna kanallari: "@KinoMixTv91,@IsboySkinolar_olami"
FORCE_CHANNELS: List[str] = []
_raw_channels = os.getenv("FORCE_CHANNELS", "").strip()
if _raw_channels:
    for ch in _raw_channels.split(","):
        ch = ch.strip()
        if ch:
            FORCE_CHANNELS.append(ch)

# Kanal linki (button uchun)
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/KinoMixTv91").strip()

# Instagram link (tekshirilmaydi, faqat ko'rsatish)
INSTA_URL = os.getenv("INSTA_URL", "https://www.instagram.com/kino.isboysbot").strip()

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN yo‘q. Railway Variables ga BOT_TOKEN qo‘ying.")

# =========================
# DB
# =========================
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
                views INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        con.commit()

def db_add_movie(code: str, title: str, url: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO movies(code,title,url,views,created_at) VALUES(?,?,?,?,?)",
            (code, title, url, 0, datetime.utcnow().isoformat()),
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

def db_list_movies(limit: int = 30) -> List[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title, views FROM movies ORDER BY created_at DESC LIMIT ?", (limit,))
        return cur.fetchall()

def db_top_movies(limit: int = 10) -> List[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title, views FROM movies ORDER BY views DESC, created_at DESC LIMIT ?", (limit,))
        return cur.fetchall()

# =========================
# UI (Buttons)
# =========================
def main_menu_keyboard(is_admin_user: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🔥 TOP kinolar", callback_data="menu_top"),
            InlineKeyboardButton("🆕 Oxirgi kinolar", callback_data="menu_list"),
        ],
        [
            InlineKeyboardButton("📢 Kanal", url=CHANNEL_URL),
            InlineKeyboardButton("📸 Instagram", url=INSTA_URL),
        ],
        [
            InlineKeyboardButton("🔄 Obunani tekshir", callback_data="recheck_sub"),
        ],
    ]
    if is_admin_user:
        rows.insert(0, [InlineKeyboardButton("➕ Kino qo‘shish", callback_data="menu_add")])
    return InlineKeyboardMarkup(rows)

def force_sub_keyboard(first_channel_username: str) -> InlineKeyboardMarkup:
    # first_channel_username: "@KinoMixTv91" kabi
    ch_url = f"https://t.me/{first_channel_username.lstrip('@')}"
    rows = [
        [InlineKeyboardButton("✅ Kanalga obuna bo‘lish", url=ch_url)],
        [InlineKeyboardButton("📸 Instagram", url=INSTA_URL)],
        [InlineKeyboardButton("🔄 Obuna bo‘ldim / Tekshir", callback_data="recheck_sub")],
    ]
    return InlineKeyboardMarkup(rows)

# =========================
# Helpers
# =========================
def is_admin(user_id: int) -> bool:
    # ADMIN_IDS bo'sh bo'lsa /add hamma uchun ochiq bo'ladi
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS

async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not FORCE_CHANNELS:
        return True

    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return False

    not_joined = []
    for ch in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(ch, user.id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)

    if not_joined:
        text = (
            "🔒 Botdan foydalanish uchun avval kanalga obuna bo‘ling:\n\n"
            + "\n".join([f"👉 {c}" for c in not_joined])
            + "\n\n✅ Obuna bo‘lgach **Tekshir** ni bosing."
        )
        await msg.reply_text(
            text,
            reply_markup=force_sub_keyboard(not_joined[0]),
            disable_web_page_preview=True,
            parse_mode="Markdown",
        )
        return False

    return True

# =========================
# Handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message and not await check_force_sub(update, context):
        return

    user = update.effective_user
    is_admin_user = bool(user and is_admin(user.id))

    await update.effective_message.reply_text(
        "🎬 *KinoMix Bot* ga xush kelibsiz!\n\n"
        "📌 Kino/serial kodini yuboring (masalan: `101`)\n"
        "yoki pastdagi tugmalardan foydalaning 👇",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin_user),
        disable_web_page_preview=True,
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🧠 *Yordam*\n\n"
        "✅ Kino ko‘rish:\n"
        "— kod yuborasiz (masalan: `101`)\n\n"
        "🛠 Admin uchun kino qo‘shish:\n"
        "`/add <kod> | <nom> | <link>`\n"
        "Misol:\n"
        "`/add 101 | Troll | https://t.me/IsboySkinolar_olami/4`\n\n"
        "📌 /list — oxirgi qo‘shilganlar\n"
        "⭐ /top — eng ko‘p ko‘rilganlar",
        parse_mode="Markdown"
    )

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message and not await check_force_sub(update, context):
        return
    rows = db_list_movies(30)
    if not rows:
        await update.effective_message.reply_text("Hozircha kino yo‘q. /add bilan qo‘shiladi.")
        return
    text = "🆕 *Oxirgi qo‘shilgan kinolar:*\n\n" + "\n".join([f"`{c}` — {t}  (👁 {v})" for c, t, v in rows])
    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message and not await check_force_sub(update, context):
        return
    rows = db_top_movies(10)
    if not rows:
        await update.effective_message.reply_text("Hozircha TOP yo‘q. Kino qo‘shing.")
        return
    text = "🔥 *TOP 10 kinolar:*\n\n" + "\n".join([f"{i+1}) `{c}` — {t}  (👁 {v})" for i, (c, t, v) in enumerate(rows)])
    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    if not is_admin(user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return

    raw = (msg.text or "").replace("/add", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await msg.reply_text(
            "❌ Format xato.\n"
            "To‘g‘risi: /add <kod> | <nom> | <link>\n"
            "Misol: /add 101 | Troll | https://t.me/kanal/123"
        )
        return

    code, title, url = parts
    if not code:
        await msg.reply_text("❌ Kod bo‘sh bo‘lmasin.")
        return
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/")):
        await msg.reply_text("❌ Link xato. https://... yoki t.me/... bo‘lsin.")
        return

    db_add_movie(code, title, url)
    await msg.reply_text(f"✅ Qo‘shildi: `{code}` — {title}", parse_mode="Markdown")

async def code_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    if not await check_force_sub(update, context):
        return

    text = (msg.text or "").strip()
    if not text or text.startswith("/"):
        return

    row = db_get_movie(text)
    if not row:
        await msg.reply_text("❌ Bunday kod topilmadi.\n\n👇 Tugmalar:", reply_markup=main_menu_keyboard(is_admin(update.effective_user.id)))
        return

    title, url, views = row
    db_inc_view(text)
    await msg.reply_text(
        f"🎬 *{title}*\n👁 Ko‘rildi: {views+1}\n🔗 {url}",
        parse_mode="Markdown",
        disable_web_page_preview=False,
        reply_markup=main_menu_keyboard(is_admin(update.effective_user.id)),
    )

# =========================
# Callbacks (Buttons)
# =========================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    user = update.effective_user
    is_admin_user = bool(user and is_admin(user.id))

    # majburiy obuna tekshir
    if q.data == "recheck_sub":
        ok = await check_force_sub(update, context)
        if ok:
            await q.message.reply_text("✅ Obuna tasdiqlandi! Endi kod yuboring (masalan: 101).", reply_markup=main_menu_keyboard(is_admin_user))
        return

    # menu actions
    if q.data == "menu_top":
        rows = db_top_movies(10)
        if not rows:
            await q.message.reply_text("Hozircha TOP yo‘q.", reply_markup=main_menu_keyboard(is_admin_user))
            return
        text = "🔥 *TOP 10 kinolar:*\n\n" + "\n".join([f"{i+1}) `{c}` — {t} (👁 {v})" for i, (c, t, v) in enumerate(rows)])
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard(is_admin_user))
        return

    if q.data == "menu_list":
        rows = db_list_movies(30)
        if not rows:
            await q.message.reply_text("Hozircha kino yo‘q.", reply_markup=main_menu_keyboard(is_admin_user))
            return
        text = "🆕 *Oxirgi qo‘shilgan kinolar:*\n\n" + "\n".join([f"`{c}` — {t} (👁 {v})" for c, t, v in rows])
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard(is_admin_user))
        return

    if q.data == "menu_add":
        if not is_admin_user:
            await q.message.reply_text("⛔ Admin emassiz.", reply_markup=main_menu_keyboard(False))
            return
        await q.message.reply_text(
            "➕ Kino qo‘shish formati:\n\n"
            "`/add 101 | Troll | https://t.me/IsboySkinolar_olami/4`",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(True),
        )
        return

# =========================
# Main
# =========================
def main():
    db_init()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("add", add_cmd))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, code_message))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
