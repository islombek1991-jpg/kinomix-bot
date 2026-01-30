import os
import re
import sqlite3
import random
from datetime import time as dtime
from typing import Optional, List, Tuple

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# =======================
# ENV (faqat BOT_TOKEN shart)
# =======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "data.db").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()     # "5491302235,123..."
IG_LINK = os.getenv("IG_LINK", "").strip()            # instagram link (faqat ko'rsatadi)

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN yo‘q. Railway Variables ga BOT_TOKEN qo‘ying.")

ADMIN_IDS = set()
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.add(int(x))

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# =======================
# DB
# =======================
def db_conn():
    return sqlite3.connect(DB_PATH)

def db_init():
    with db_conn() as con:
        cur = con.cursor()
        # movies: kod, nom, link, qo'shilgan vaqt
        cur.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url   TEXT NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s','now'))
            )
        """)
        # stats: ko'rilish
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                code TEXT PRIMARY KEY,
                views INTEGER NOT NULL DEFAULT 0
            )
        """)
        # settings: force channels, post channel, autopost times (comma), autopost enabled
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL
            )
        """)
        con.commit()

def set_setting(k: str, v: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)", (k, v))
        con.commit()

def get_setting(k: str, default: str = "") -> str:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT v FROM settings WHERE k=?", (k,))
        row = cur.fetchone()
        return row[0] if row else default

def db_add_movie(code: str, title: str, url: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("INSERT OR REPLACE INTO movies(code,title,url) VALUES(?,?,?)", (code, title, url))
        cur.execute("INSERT OR IGNORE INTO stats(code,views) VALUES(?,0)", (code,))
        con.commit()

def db_del_movie(code: str) -> bool:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM movies WHERE code=?", (code,))
        cur.execute("DELETE FROM stats WHERE code=?", (code,))
        con.commit()
        return cur.rowcount > 0

def db_get_movie(code: str) -> Optional[Tuple[str, str]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT title, url FROM movies WHERE code=?", (code,))
        return cur.fetchone()

def db_list_movies(limit: int = 50) -> List[Tuple[str, str]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title FROM movies ORDER BY created_at DESC LIMIT ?", (limit,))
        return cur.fetchall()

def db_inc_view(code: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO stats(code,views) VALUES(?,0)", (code,))
        cur.execute("UPDATE stats SET views = views + 1 WHERE code=?", (code,))
        con.commit()

def db_top(limit: int = 10) -> List[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT m.code, m.title, s.views
            FROM movies m
            JOIN stats s ON s.code = m.code
            ORDER BY s.views DESC, m.created_at DESC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()

def db_random_movie() -> Optional[Tuple[str, str, str]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title, url FROM movies ORDER BY RANDOM() LIMIT 1")
        return cur.fetchone()

# =======================
# Force subscribe (kuchaytirilgan)
# =======================
def parse_channels(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    raw = raw.replace(" ", "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts

def get_force_channels() -> List[str]:
    return parse_channels(get_setting("FORCE_CHANNELS", ""))

def set_force_channels(chs: List[str]):
    set_setting("FORCE_CHANNELS", ",".join(chs))

async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """True=ruxsat, False=blok. Bot kanal(lar)da ADMIN bo‘lishi shart."""
    if not update.effective_user or not update.message:
        return False

    channels = get_force_channels()
    if not channels:
        return True

    user_id = update.effective_user.id
    not_joined = []

    for ch in channels:
        try:
            member = await context.bot.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            # Bot admin emas / kanal topilmadi -> hamma "join" bo'lmaydi deb chiqadi
            not_joined.append(ch)

    if not_joined:
        # Kuchaytirilgan xabar + tugmalar
        join_buttons = [[InlineKeyboardButton(f"📢 {c}", url=f"https://t.me/{c.lstrip('@')}")] for c in not_joined]
        extra = []
        if IG_LINK:
            extra.append([InlineKeyboardButton("📸 Instagram", url=IG_LINK)])
        extra.append([InlineKeyboardButton("✅ Tekshirish", callback_data="recheck_sub")])

        text = (
            "🔒 <b>Davom etish uchun obuna shart!</b>\n\n"
            "1) Pastdagi kanal(lar)ga kiring\n"
            "2) Obuna bo‘ling\n"
            "3) <b>✅ Tekshirish</b> ni bosing\n\n"
            "⏳ 5 soniya ketadi, keyin bot ochiladi."
        )
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(join_buttons + extra),
            disable_web_page_preview=True,
        )
        return False

    return True

async def recheck_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    fake_update = Update(update.update_id, message=q.message)
    fake_update.effective_user = q.from_user  # type: ignore
    # check again
    ok = await check_force_sub(fake_update, context)
    if ok:
        await q.message.reply_text("✅ Obuna tasdiqlandi. Endi kod yuboring (masalan: 4).")

# =======================
# Auto-post (kanalga)
# =======================
def get_post_channel() -> str:
    return get_setting("POST_CHANNEL", "").strip()

def set_post_channel(v: str):
    set_setting("POST_CHANNEL", v.strip())

def get_autopost_enabled() -> bool:
    return get_setting("AUTOPOST_ON", "0") == "1"

def set_autopost_enabled(on: bool):
    set_setting("AUTOPOST_ON", "1" if on else "0")

def get_autopost_times() -> List[str]:
    # "09:00,18:00,21:00"
    raw = get_setting("AUTOPOST_TIMES", "09:00,18:00,21:00")
    raw = raw.replace(" ", "")
    times = [t for t in raw.split(",") if re.fullmatch(r"\d{2}:\d{2}", t)]
    return times if times else ["09:00", "18:00", "21:00"]

def set_autopost_times(times: str):
    set_setting("AUTOPOST_TIMES", times.replace(" ", ""))

async def autopost_job(context: ContextTypes.DEFAULT_TYPE):
    if not get_autopost_enabled():
        return

    ch = get_post_channel()
    if not ch:
        return

    item = db_random_movie()
    if not item:
        return

    code, title, url = item
    text = (
        "🎬 <b>BUGUNGI TAVSIYA</b>\n\n"
        f"🎞 <b>{title}</b>\n"
        f"🔢 Kod: <code>{code}</code>\n"
        f"🔗 {url}\n\n"
        "✅ Kodni botga yozing — darhol chiqadi!"
    )

    try:
        await context.bot.send_message(chat_id=ch, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
    except Exception:
        # Bot kanalga yozolmasa: bot admin emas yoki channel id xato
        return

def schedule_autopost(app: Application):
    # avval eski schedule'larni tozalaymiz
    jq = app.job_queue
    for job in jq.jobs():
        if job.name and job.name.startswith("autopost_"):
            job.schedule_removal()

    # default timezone (Railway odatda UTC). Foydalanuvchi +0900 bo‘lsa ham,
    # eng oson: vaqtni UTC bo‘yicha qo‘ying yoki keyin sozlaymiz.
    for t in get_autopost_times():
        hh, mm = map(int, t.split(":"))
        jq.run_daily(autopost_job, time=dtime(hour=hh, minute=mm), name=f"autopost_{t}")

# =======================
# Texts
# =======================
def start_text() -> str:
    chs = get_force_channels()
    ch_txt = "\n".join([f"• {c}" for c in chs]) if chs else "• (yo‘q)"
    post_ch = get_post_channel() or "(yo‘q)"
    ig = f"\n📸 Instagram: {IG_LINK}" if IG_LINK else ""
    return (
        "🎬 <b>KinoMixBot</b> ga xush kelibsiz!\n\n"
        "🔎 <b>Kino/serial kodini yuboring</b> (masalan: <code>4</code>)\n"
        "📌 Ro‘yxat: /list\n"
        "⭐ Top: /top\n"
        "🎲 Random: /random\n"
        f"{ig}\n\n"
        "<b>Majburiy obuna kanallari:</b>\n"
        f"{ch_txt}\n\n"
        f"<b>Avto-post kanali:</b> {post_ch}"
    )

HELP_TEXT = (
    "📌 Buyruqlar:\n"
    "/start — boshlash\n"
    "/help — yordam\n"
    "/list — oxirgi 50 ta kino\n"
    "/top — TOP kinolar (ko‘rilish bo‘yicha)\n"
    "/random — tasodifiy kino\n\n"
    "🛠 Admin:\n"
    "/add <kod> | <nom> | <link>\n"
    "/del <kod>\n\n"
    "🔒 Majburiy obuna (admin):\n"
    "/channel_list\n"
    "/channel_add @kanal\n"
    "/channel_del @kanal\n"
    "/channel_set @k1,@k2,@k3\n\n"
    "🤖 Avto-post (admin):\n"
    "/set_post_channel @kanal  (yoki -100... ID)\n"
    "/autopost_times 09:00,18:00,21:00\n"
    "/autopost_on\n"
    "/autopost_off"
)

# =======================
# Handlers
# =======================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and not await check_force_sub(update, context):
        return
    await update.message.reply_text(start_text(), parse_mode=ParseMode.HTML)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and not await check_force_sub(update, context):
        return
    rows = db_list_movies(50)
    if not rows:
        await update.message.reply_text("Hozircha kino yo‘q. Admin /add bilan qo‘shadi.")
        return
    text = "📃 Oxirgi kinolar:\n" + "\n".join([f"{c} — {t}" for c, t in rows])
    await update.message.reply_text(text)

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and not await check_force_sub(update, context):
        return
    rows = db_top(10)
    if not rows:
        await update.message.reply_text("Hozircha reyting yo‘q.")
        return
    text = "⭐ TOP kinolar:\n" + "\n".join([f"{i+1}) {c} — {t}  (👀 {v})" for i, (c, t, v) in enumerate(rows)])
    await update.message.reply_text(text)

async def random_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and not await check_force_sub(update, context):
        return
    item = db_random_movie()
    if not item:
        await update.message.reply_text("Hozircha kino yo‘q.")
        return
    code, title, url = item
    await update.message.reply_text(
        f"🎲 Random:\n🎬 <b>{title}</b>\n🔢 Kod: <code>{code}</code>\n🔗 {url}",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz. ADMIN_IDS ni Railway Variables ga qo‘ying.")
        return

    raw = (msg.text or "").replace("/add", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await msg.reply_text(
            "❌ Format xato.\n"
            "To‘g‘risi: /add <kod> | <nom> | <link>\n"
            "Misol: /add 4 | Troll | https://t.me/IsboySkinolar_olami/4"
        )
        return

    code, title, url = parts
    if not code:
        await msg.reply_text("❌ Kod bo‘sh bo‘lmasin.")
        return
    if not (url.startswith("https://") or url.startswith("http://") or "t.me/" in url):
        await msg.reply_text("❌ Link xato. https://... yoki t.me/... bo‘lsin.")
        return

    db_add_movie(code, title, url)
    await msg.reply_text(f"✅ Qo‘shildi: {code} — {title}")

async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return
    raw = (msg.text or "").replace("/del", "", 1).strip()
    if not raw:
        await msg.reply_text("❌ Misol: /del 4")
        return
    ok = db_del_movie(raw)
    await msg.reply_text("✅ O‘chirildi." if ok else "❌ Bunday kod topilmadi.")

# ---- Channels manage
async def channel_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return
    chs = get_force_channels()
    if not chs:
        await msg.reply_text("📢 Hozir majburiy obuna kanali yo‘q.\n/channel_add @kanal")
        return
    await msg.reply_text("📢 Majburiy obuna kanallari:\n" + "\n".join([f"• {c}" for c in chs]))

async def channel_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return
    raw = (msg.text or "").replace("/channel_set", "", 1).strip().replace(" ", "")
    chs = parse_channels(raw)
    set_force_channels(chs)
    await msg.reply_text("✅ Saqlandi:\n" + ("\n".join([f"• {c}" for c in chs]) if chs else "(bo‘sh)"))

async def channel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return
    ch = (msg.text or "").replace("/channel_add", "", 1).strip()
    if not ch:
        await msg.reply_text("❌ Misol: /channel_add @KinoMixTV")
        return
    chs = get_force_channels()
    if ch not in chs:
        chs.append(ch)
    set_force_channels(chs)
    await msg.reply_text("✅ Qo‘shildi:\n" + "\n".join([f"• {c}" for c in chs]))

async def channel_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return
    ch = (msg.text or "").replace("/channel_del", "", 1).strip()
    if not ch:
        await msg.reply_text("❌ Misol: /channel_del @KinoMixTV")
        return
    chs = [c for c in get_force_channels() if c != ch]
    set_force_channels(chs)
    await msg.reply_text("✅ O‘chirildi:\n" + ("\n".join([f"• {c}" for c in chs]) if chs else "(bo‘sh)"))

# ---- Autopost manage
async def set_post_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return
    raw = (msg.text or "").replace("/set_post_channel", "", 1).strip()
    if not raw:
        await msg.reply_text("❌ Misol: /set_post_channel @KinoMixTV  (yoki -100123...)")
        return
    set_post_channel(raw)
    await msg.reply_text(f"✅ Avto-post kanali saqlandi: {raw}\n\n⚠️ Bot o‘sha kanalda ADMIN bo‘lsin!")

async def autopost_times_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return
    raw = (msg.text or "").replace("/autopost_times", "", 1).strip()
    if not raw:
        await msg.reply_text("❌ Misol: /autopost_times 09:00,18:00,21:00")
        return
    # validate
    raw = raw.replace(" ", "")
    times = [t for t in raw.split(",") if re.fullmatch(r"\d{2}:\d{2}", t)]
    if not times:
        await msg.reply_text("❌ Vaqt formati xato. Misol: 09:00,18:00,21:00")
        return
    set_autopost_times(",".join(times))
    schedule_autopost(context.application)
    await msg.reply_text("✅ Avto-post vaqtlar saqlandi: " + ",".join(times))

async def autopost_on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return
    if not get_post_channel():
        await msg.reply_text("❌ Avto-post kanali yo‘q. Avval: /set_post_channel @kanal")
        return
    set_autopost_enabled(True)
    schedule_autopost(context.application)
    await msg.reply_text("✅ Avto-post yoqildi.")

async def autopost_off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return
    set_autopost_enabled(False)
    await msg.reply_text("⛔ Avto-post o‘chirildi.")

# ---- Code message
async def code_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    if not await check_force_sub(update, context):
        return

    text = (msg.text or "").strip()
    if not text or text.startswith("/"):
        return

    row = db_get_movie(text)
    if not row:
        await msg.reply_text("❌ Bunday kod topilmadi.\n/list dan tekshirib ko‘ring.")
        return

    title, url = row
    db_inc_view(text)
    await msg.reply_text(
        f"🎬 <b>{title}</b>\n🔗 {url}",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )

def main():
    db_init()

    app = Application.builder().token(BOT_TOKEN).build()

    # schedule autopost at startup
    schedule_autopost(app)

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("random", random_cmd))

    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("del", del_cmd))

    app.add_handler(CommandHandler("channel_list", channel_list))
    app.add_handler(CommandHandler("channel_set", channel_set))
    app.add_handler(CommandHandler("channel_add", channel_add))
    app.add_handler(CommandHandler("channel_del", channel_del))

    app.add_handler(CommandHandler("set_post_channel", set_post_channel_cmd))
    app.add_handler(CommandHandler("autopost_times", autopost_times_cmd))
    app.add_handler(CommandHandler("autopost_on", autopost_on_cmd))
    app.add_handler(CommandHandler("autopost_off", autopost_off_cmd))

    app.add_handler(CallbackQueryHandler(recheck_callback, pattern="^recheck_sub$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, code_message))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
