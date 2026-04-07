from telegram import InlineQueryResultCachedVideo
import json
import os
import logging
import re
from uuid import uuid4
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    InlineQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

# === Muhit o'zgaruvchilari ===
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi!")

admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()]

DB_FILE = "movies.json"

# === Logging ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Ma'lumotlar bazasi ===
def load_movies():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Baza o'qishda xatolik: {e}")
        return {}

def save_movies(movies):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(movies, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Baza saqlashda xatolik: {e}")
        return False

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# === Foydalanuvchi buyruqlari ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Kino Botiga xush kelibsiz!*\n\n"
        "Kinolar ro'yxatini ko'rish uchun /movies buyrug'ini bosing.\n"
        "Yoki istalgan chatda `@sizning_bot_username kino` deb yozib qidiring.\n\n"
        "👨‍💻 Adminlar kino qo'shishlari mumkin: /adminhelp",
        parse_mode=ParseMode.MARKDOWN
    )

async def movies_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movies = load_movies()
    if not movies:
        await update.message.reply_text("📭 Hozircha kino mavjud emas.")
        return

    keyboard = []
    for title, file_id in movies.items():
        keyboard.append([InlineKeyboardButton(f"🎬 {title}", callback_data=f"get_{file_id}")])

    await update.message.reply_text(
        "📋 *Mavjud kinolar:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("get_"):
        file_id = data[4:]
        try:
            await context.bot.send_video(
                chat_id=query.message.chat_id,
                video=file_id,
                caption="✅ Kino tayyor!",
                protect_content=True  # forward qilishni cheklash (ixtiyoriy)
            )
            await query.edit_message_text("✅ Kino yuborildi!")
        except Exception as e:
            logger.error(f"Video yuborishda xatolik: {e}")
            await query.edit_message_text("❌ Kechirasiz, video yuborishda xatolik.")

# === Inline qidiruv ===
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    movies = load_movies()
    results = []

    if not query:
        # Bo'sh so'rov bo'lsa, bir nechta kinoni ko'rsatamiz
        for title, file_id in list(movies.items())[:10]:
            results.append(
                InlineQueryResultCachedVideo(
                    id=str(uuid4()),
                    video_file_id=file_id,
                    title=title,
                    caption=f"🎬 {title}",
                )
            )
    else:
        # Qidiruv so'zi bo'lsa, nomga qarab filtrlaymiz
        for title, file_id in movies.items():
            if query.lower() in title.lower():
                results.append(
                    InlineQueryResultCachedVideo(
                        id=str(uuid4()),
                        video_file_id=file_id,
                        title=title,
                        caption=f"🎬 {title}",
                    )
                )

    await update.inline_query.answer(results, cache_time=5)

# === Admin funksiyalari ===
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    text = (
        "👨‍💻 *Admin buyruqlari:*\n"
        "/addmovie - Yangi kino qo'shish (video forward yoki link)\n"
        "/delete `nomi` - Kino o'chirish\n"
        "/list - Barcha kinolar ro'yxati\n"
        "/cancel - Kino qo'shishni bekor qilish\n"
        "/adminhelp - Ushbu yordam"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def clear_all_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    save_movies({})  # bo'sh lug'at saqlaydi
    await update.message.reply_text("🗑 Barcha kinolar o'chirildi!")

async def add_movie_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return

    await update.message.reply_text(
        "📤 Iltimos, quyidagilardan birini yuboring:\n"
        "1️⃣ Kanalda joylangan video xabarini *forward* qiling.\n"
        "2️⃣ Kanal posti linkini yuboring (masalan: https://t.me/kanal/123).\n\n"
        "Xabar izohiga (caption) kino nomini yozing.\n"
        "❌ Bekor qilish uchun /cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data["awaiting_movie"] = True

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_movie"):
        context.user_data["awaiting_movie"] = False
        await update.message.reply_text("✅ Bekor qilindi.")
    else:
        await update.message.reply_text("ℹ️ Bekor qilinadigan jarayon yo'q.")

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin forward yoki link yuborganida ishlaydi."""
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get("awaiting_movie"):
        return

    message = update.message
    file_id = None
    title = message.caption or message.text

    # 1. Forward qilingan video
    if message.forward_from_chat and (message.video or message.document):
        if message.video:
            file_id = message.video.file_id
        elif message.document:
            file_id = message.document.file_id
        if not title:
            await message.reply_text("❌ Kino nomini izohga yozing.")
            return

    # 2. Kanal linki
    elif message.text and "t.me/" in message.text:
        match = re.search(r"t\.me/([^/]+)/(\d+)", message.text)
        if match:
            channel = match.group(1)
            msg_id = int(match.group(2))
            try:
                forwarded = await context.bot.forward_message(
                    chat_id=message.chat_id,
                    from_chat_id=f"@{channel}",
                    message_id=msg_id
                )
                if forwarded.video:
                    file_id = forwarded.video.file_id
                elif forwarded.document:
                    file_id = forwarded.document.file_id
                else:
                    await message.reply_text("❌ Bu postda video topilmadi.")
                    return
                await forwarded.delete()
                if not title:
                    await message.reply_text("❌ Kino nomini xabar matniga yozing.")
                    return
            except Exception as e:
                await message.reply_text(f"❌ Linkdan video olib bo'lmadi. Bot kanal a'zosimi?\nXatolik: {e}")
                return
        else:
            await message.reply_text("❌ Noto'g'ri link formati.")
            return
    else:
        await message.reply_text("❌ Iltimos, video forward qiling yoki kanal linkini yuboring.")
        return

    if not file_id:
        await message.reply_text("❌ Video topilmadi.")
        return

    title = title.strip()
    movies = load_movies()
    if title in movies:
        await message.reply_text(f"⚠️ '{title}' allaqachon mavjud.")
        return

    movies[title] = file_id
    if save_movies(movies):
        await message.reply_text(f"✅ '{title}' kinosi qo'shildi!")
        logger.info(f"Admin {update.effective_user.id} yangi kino: {title}")
    else:
        await message.reply_text("❌ Saqlashda xatolik.")

    context.user_data["awaiting_movie"] = False

async def delete_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    if not context.args:
        await update.message.reply_text("❌ Nom kiriting: /delete Nom")
        return
    title = " ".join(context.args).strip()
    movies = load_movies()
    if title in movies:
        del movies[title]
        if save_movies(movies):
            await update.message.reply_text(f"🗑 '{title}' o'chirildi.")
        else:
            await update.message.reply_text("❌ Saqlashda xatolik.")
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
        await update.message.reply_text(f"📋 *Kinolar:*\n{text}", parse_mode=ParseMode.MARKDOWN)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Xatolik:", exc_info=context.error)

# === Asosiy ===
def main():
    app = Application.builder().token(TOKEN).build()

    # Foydalanuvchi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("movies", movies_list))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(InlineQueryHandler(inline_query))

    # Admin
    app.add_handler(CommandHandler("addmovie", add_movie_start))
    app.add_handler(CommandHandler("delete", delete_movie))
    app.add_handler(CommandHandler("list", list_admin))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("adminhelp", admin_help))

    # Forward/link uchun
    app.add_handler(MessageHandler(
        filters.TEXT | filters.FORWARDED | filters.VIDEO | filters.Document.ALL,
        handle_admin_message
    ))

    app.add_error_handler(error_handler)

    logger.info("Bot ishga tushmoqda...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
