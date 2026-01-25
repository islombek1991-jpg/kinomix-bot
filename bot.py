import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN yo‘q. Railway Variables ga BOT_TOKEN qo‘ying.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 KinoMix TV botiga xush kelibsiz!\n\n"
        "📌 Kino yoki serial kodini yuboring.\n"
        "🔥 Eng yangi kinolar faqat bizda!"
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()
