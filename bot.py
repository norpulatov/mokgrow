from telegram import InlineQueryResultCachedVideo
import json
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi!")

ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
DB_FILE = "movies.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def load_movies():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_movies(movies):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# === Foydalanuvchi ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Assalomu alaykum! Kino botiga xush kelibsiz.\n"
        "Kinolar ro'yxatini /movies buyrug'i bilan oling."
    )

async def movies_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movies = load_movies()
    if not movies:
        await update.message.reply_text("📭 Hozircha kino mavjud emas.")
        return

    titles = list(movies.keys())
    text = "📋 *Mavjud kinolar:*\n"
    for i, title in enumerate(titles, 1):
        text += f"{i}. {title}\n"
    text += "\nKerakli kino raqamini yuboring."
    await update.message.reply_text(text)

async def handle_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi faqat raqam yuborsa ishlaydi."""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if not text.isdigit():
        return

    movies = load_movies()
    if not movies:
        await update.message.reply_text("📭 Hozircha kino yo'q.")
        return

    titles = list(movies.keys())
    idx = int(text) - 1
    if 0 <= idx < len(titles):
        title = titles[idx]
        file_id = movies[title]
        await update.message.reply_video(video=file_id, caption=f"🎬 {title}")
    else:
        await update.message.reply_text("❌ Bunday raqamli kino yo'q.")

# === Admin ===
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "/addmovie - Yangi kino qo'shish\n"
        "/delete nom - Kinoni o'chirish\n"
        "/list - Kinolar ro'yxati (admin)"
    )

async def add_movie_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    await update.message.reply_text("📤 Video faylni yuboring va izohga kino nomini yozing.")
    context.user_data["awaiting_movie"] = True

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin video yuborganda."""
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get("awaiting_movie"):
        return

    video = update.message.video
    document = update.message.document
    if not video and not document:
        await update.message.reply_text("❌ Iltimos, video fayl yuboring.")
        return

    file_id = video.file_id if video else document.file_id
    title = update.message.caption
    if not title:
        await update.message.reply_text("❌ Iltimos, izohga kino nomini yozing.")
        return

    title = title.strip()
    movies = load_movies()
    if title in movies:
        await update.message.reply_text(f"⚠️ '{title}' allaqachon mavjud.")
        return

    movies[title] = file_id
    save_movies(movies)
    await update.message.reply_text(f"✅ '{title}' kinosi qo'shildi!")
    logger.info(f"Admin {update.effective_user.id} yangi kino: {title}")
    context.user_data["awaiting_movie"] = False

async def delete_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    if not context.args:
        await update.message.reply_text("❌ O'chirish uchun nom kiriting: /delete Nom")
        return
    title = " ".join(context.args).strip()
    movies = load_movies()
    if title in movies:
        del movies[title]
        save_movies(movies)
        await update.message.reply_text(f"🗑 '{title}' o'chirildi.")
    else:
        await update.message.reply_text("❌ Bunday kino topilmadi.")

async def list_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    movies = load_movies()
    if not movies:
        await update.message.reply_text("📭 Kino yo'q.")
    else:
        text = "\n".join([f"• {t}" for t in movies.keys()])
        await update.message.reply_text(f"📋 Kinolar:\n{text}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if context.user_data.get("awaiting_movie"):
        context.user_data["awaiting_movie"] = False
        await update.message.reply_text("✅ Bekor qilindi.")
    else:
        await update.message.reply_text("ℹ️ Bekor qilinadigan jarayon yo'q.")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("movies", movies_list))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number))

    app.add_handler(CommandHandler("addmovie", add_movie_start))
    app.add_handler(CommandHandler("delete", delete_movie))
    app.add_handler(CommandHandler("list", list_admin))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("adminhelp", admin_help))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.ALL, handle_video))

    logger.info("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
