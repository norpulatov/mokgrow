import json
import os
import logging
import re
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)

# Muhit o'zgaruvchilarini yuklash (Railway da avtomatik)
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN muhit o'zgaruvchisi topilmadi!")

# Admin ID lar vergul bilan ajratilgan string
admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()]

DB_FILE = "movies.json"

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Ma'lumotlar bazasi funksiyalari ===
def load_movies():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Bazani o'qishda xatolik: {e}")
        return {}

def save_movies(movies):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(movies, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Bazani saqlashda xatolik: {e}")
        return False

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# === Foydalanuvchi buyruqlari ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 Assalomu alaykum! Kino botga xush kelibsiz.\n"
        "Mavjud kinolarni ko'rish uchun /movies buyrug'ini bosing."
    )

async def movies_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movies = load_movies()
    if not movies:
        await update.message.reply_text("📭 Hozircha hech qanday kino mavjud emas.")
        return

    keyboard = []
    for title, file_id in movies.items():
        keyboard.append([InlineKeyboardButton(f"🎬 {title}", callback_data=f"get_{file_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 Mavjud kinolar ro'yxati:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("get_"):
        return

    file_id = data[4:]  # "get_" ni olib tashlash
    try:
        await context.bot.send_video(
            chat_id=query.message.chat_id,
            video=file_id,
            caption="✅ Kino tayyor!"
        )
        await query.edit_message_text("✅ Kino muvaffaqiyatli yuborildi!")
    except Exception as e:
        logger.error(f"Video yuborishda xatolik: {e}")
        await query.edit_message_text("❌ Kechirasiz, video yuborishda xatolik yuz berdi.")

# === Admin funksiyalari (KANAL USULI) ===
async def add_movie_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return

    await update.message.reply_text(
        "📤 Iltimos, quyidagilardan birini yuboring:\n"
        "1️⃣ Kanalda joylangan video xabarini menga *forward* qiling.\n"
        "2️⃣ Kanal posti linkini yuboring (masalan: https://t.me/kanal/123).\n\n"
        "Xabar izohiga (caption) kino nomini yozing.\n"
        "❌ Bekor qilish uchun /cancel"
    )
    context.user_data["awaiting_movie"] = True

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_movie"):
        context.user_data["awaiting_movie"] = False
        await update.message.reply_text("✅ Kino qo'shish bekor qilindi.")
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

    # 1. Forward qilingan video xabar
    if message.forward_from_chat and (message.video or message.document):
        if message.video:
            file_id = message.video.file_id
        elif message.document:
            file_id = message.document.file_id
        if not title:
            await message.reply_text("❌ Iltimos, kino nomini xabar izohiga yozing.")
            return

    # 2. Kanal posti linki
    elif message.text and "t.me/" in message.text:
        match = re.search(r"t\.me/([^/]+)/(\d+)", message.text)
        if match:
            channel = match.group(1)
            msg_id = int(match.group(2))
            try:
                # Bot kanal a'zosi bo'lishi kerak
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
                # Forward qilingan xabarni o'chiramiz (ixtiyoriy)
                await forwarded.delete()
                if not title:
                    await message.reply_text("❌ Kino nomini xabar matniga yozing (caption emas).")
                    return
            except Exception as e:
                await message.reply_text(f"❌ Linkdan video olib bo'lmadi. Bot kanal a'zosimi?\nXatolik: {e}")
                return
        else:
            await message.reply_text("❌ Noto'g'ri link formati.")
            return
    else:
        await message.reply_text("❌ Iltimos, video forward qiling yoki kanal posti linkini yuboring.")
        return

    if not file_id:
        await message.reply_text("❌ Video fayl topilmadi.")
        return

    title = title.strip()
    movies = load_movies()
    if title in movies:
        await message.reply_text(f"⚠️ '{title}' nomli kino allaqachon mavjud.")
        return

    movies[title] = file_id
    if save_movies(movies):
        await message.reply_text(f"✅ '{title}' kinosi muvaffaqiyatli qo'shildi!")
        logger.info(f"Admin yangi kino qo'shdi: {title}")
    else:
        await message.reply_text("❌ Bazaga saqlashda xatolik yuz berdi.")

    context.user_data["awaiting_movie"] = False

async def delete_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    if not context.args:
        await update.message.reply_text("❌ O'chiriladigan kino nomini kiriting: /delete Nom")
        return

    title = " ".join(context.args).strip()
    movies = load_movies()
    if title in movies:
        del movies[title]
        if save_movies(movies):
            await update.message.reply_text(f"🗑 '{title}' kinosi o'chirildi.")
            logger.info(f"Admin {update.effective_user.id} kinoni o'chirdi: {title}")
        else:
            await update.message.reply_text("❌ Bazaga saqlashda xatolik.")
    else:
        await update.message.reply_text("❌ Bunday kino topilmadi.")

async def list_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    movies = load_movies()
    if not movies:
        await update.message.reply_text("📭 Hozircha kino yo'q.")
    else:
        text = "\n".join([f"• {t}" for t in movies.keys()])
        await update.message.reply_text(f"📋 Kinolar ro'yxati:\n{text}")

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = (
        "👨‍💻 *Admin buyruqlari:*\n"
        "/addmovie - Yangi kino qo'shish\n"
        "/delete `nomi` - Kino o'chirish\n"
        "/list - Barcha kinolar ro'yxati\n"
        "/cancel - Kino qo'shishni bekor qilish\n"
        "/adminhelp - Ushbu yordam"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Xatolik yuz berdi:", exc_info=context.error)

# === Asosiy dastur ===
def main():
    if not TOKEN:
        logger.error("BOT_TOKEN topilmadi!")
        return

    app = Application.builder().token(TOKEN).build()

    # Handlerlarni qo'shish
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("movies", movies_list))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(CommandHandler("addmovie", add_movie_start))
    app.add_handler(CommandHandler("delete", delete_movie))
    app.add_handler(CommandHandler("list", list_admin))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("adminhelp", admin_help))

    # Admin tomonidan forward/link yuborish uchun
    app.add_handler(MessageHandler(
        filters.TEXT | filters.FORWARDED | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        handle_admin_message
    ))

    app.add_error_handler(error_handler)

    logger.info("Bot ishga tushmoqda...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()