import json
import os
import logging
from uuid import uuid4
from dotenv import load_dotenv
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, MessageHandler, InlineQueryHandler, filters, ContextTypes

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
        "Kinolar ro'yxatini /movies buyrug'i bilan oling.\n"
        "Yoki istalgan chatda @sizning_bot_username kino_nomi deb qidiring."
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
        try:
            await update.message.reply_video(video=file_id, caption=f"🎬 {title}")
        except Exception as e:
            logger.error(f"Video yuborishda xatolik: {e}")
            await update.message.reply_text("❌ Kino yuborishda xatolik. Iltimos, adminga murojaat qiling.")
    else:
        await update.message.reply_text("❌ Bunday raqamli kino yo'q.")

# === Inline qidiruv (xatoliksiz) ===
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip().lower()
    movies = load_movies()
    results = []

    if not movies:
        await update.inline_query.answer([], switch_pm_text="Kinolar ro'yxati", switch_pm_parameter="movies")
        return

    # Kinolarni nomiga qarab saralaymiz
    matched_titles = []
    for title in movies.keys():
        if query in title.lower():
            matched_titles.append(title)

    # Agar so'rov bo'sh bo'lsa yoki mos keluvchi topilmasa, dastlabki 10 ta kinoni ko'rsatamiz
    if not query or not matched_titles:
        matched_titles = list(movies.keys())[:10]

    for idx, title in enumerate(matched_titles):
        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"🎬 {title}",
                description="Kino yuborish uchun tanlang",
                input_message_content=InputTextMessageContent(
                    message_text=f"/get_{title}"  # maxsus buyruq orqali yuboramiz
                )
            )
        )

    await update.inline_query.answer(results, cache_time=5)

# === Inline orqali kino yuborish uchun handler ===
async def get_movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline tanlanganda yuboriladigan maxfiy buyruq."""
    if not update.message or not update.message.text:
        return
    cmd = update.message.text.strip()
    if not cmd.startswith("/get_"):
        return

    title = cmd[5:]  # "/get_" ni olib tashlaymiz
    movies = load_movies()
    if title in movies:
        file_id = movies[title]
        try:
            await update.message.reply_video(video=file_id, caption=f"🎬 {title}")
        except Exception as e:
            logger.error(f"Video yuborishda xatolik: {e}")
            await update.message.reply_text("❌ Kino yuborishda xatolik.")
    else:
        await update.message.reply_text("❌ Kino topilmadi.")

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
    app.add_handler(CommandHandler("get", get_movie_command))  # maxsus buyruq
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number))
    app.add_handler(InlineQueryHandler(inline_query))

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
