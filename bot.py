
from telegram import InlineQueryResultCachedVideo
import json
import os
import logging
import re
from uuid import uuid4
import httpx
from dotenv import load_dotenv
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    InlineQueryResultCachedVideo
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    InlineQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode, ChatMemberStatus

# === Muhit o'zgaruvchilari ===
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi!")

admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()]

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID", "").strip()

# GitHub Gist sozlamalari (agar ishlatilsa)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GIST_ID = os.getenv("GIST_ID", "").strip()

# Agar Volume ishlatilsa, DB_FILE shu yo'lda
DB_FILE = os.getenv("DB_FILE", "/app/data/movies.json")  # yoki oddiy "movies.json"

# === Logging ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Ma'lumotlar bazasi funksiyalari (GitHub Gist yoki mahalliy fayl) ===
# Agar GITHUB_TOKEN bo'lsa, Gist ishlatiladi, aks holda mahalliy fayl
USE_GIST = bool(GITHUB_TOKEN)

if USE_GIST:
    async def load_movies_async():
        if not GITHUB_TOKEN:
            return {}
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        async with httpx.AsyncClient() as client:
            if not GIST_ID:
                data = {
                    "description": "Kino bot ma'lumotlari",
                    "public": False,
                    "files": {"movies.json": {"content": json.dumps({})}}
                }
                resp = await client.post("https://api.github.com/gists", headers=headers, json=data)
                if resp.status_code == 201:
                    gist_id = resp.json()["id"]
                    logger.info(f"Yangi Gist yaratildi: {gist_id}")
                    global GIST_ID
                    GIST_ID = gist_id
                    return {}
                else:
                    logger.error(f"Gist yaratishda xatolik: {resp.text}")
                    return {}
            else:
                resp = await client.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers)
                if resp.status_code == 200:
                    gist = resp.json()
                    content = gist["files"]["movies.json"]["content"]
                    return json.loads(content) if content.strip() else {}
                else:
                    logger.error(f"Gist o'qishda xatolik: {resp.text}")
                    return {}

    async def save_movies_async(movies):
        if not GITHUB_TOKEN or not GIST_ID:
            return False
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        data = {"files": {"movies.json": {"content": json.dumps(movies, ensure_ascii=False, indent=2)}}}
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=data)
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"Gist yozishda xatolik: {resp.text}")
                return False

    import asyncio
    import nest_asyncio
    nest_asyncio.apply()

    def load_movies():
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return loop.run_until_complete(load_movies_async())
            else:
                return asyncio.run(load_movies_async())
        except RuntimeError:
            return asyncio.run(load_movies_async())

    def save_movies(movies):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return loop.run_until_complete(save_movies_async(movies))
            else:
                return asyncio.run(save_movies_async(movies))
        except RuntimeError:
            return asyncio.run(save_movies_async(movies))
else:
    # Mahalliy fayl rejimi
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
            os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(movies, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Baza saqlashda xatolik: {e}")
            return False

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# === Obuna tekshirish ===
async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not REQUIRED_CHANNEL and not REQUIRED_CHANNEL_ID:
        return True
    chat_id = REQUIRED_CHANNEL_ID if REQUIRED_CHANNEL_ID else f"@{REQUIRED_CHANNEL}"
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
            return False
        return True
    except Exception as e:
        logger.error(f"Obuna tekshirishda xatolik: {e}")
        return True  # Xatolikda ruxsat beramiz

async def require_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not REQUIRED_CHANNEL and not REQUIRED_CHANNEL_ID:
        return True
    user_id = update.effective_user.id
    try:
        if await check_subscription(user_id, context):
            return True
    except Exception:
        return True

    keyboard = []
    if REQUIRED_CHANNEL:
        keyboard.append([InlineKeyboardButton("📢 Kanalga o'tish", url=f"https://t.me/{REQUIRED_CHANNEL}")])
    keyboard.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = "⛔ Botdan foydalanish uchun kanalimizga obuna bo'ling!\n\nObuna bo'lgach \"✅ Tekshirish\" tugmasini bosing."

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.inline_query:
        await update.inline_query.answer([], switch_pm_text="Botdan foydalanish uchun kanalga obuna bo'ling", switch_pm_parameter="subscribe")
    return False

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if await check_subscription(user_id, context):
        await query.edit_message_text("✅ Rahmat! Endi botdan foydalanishingiz mumkin.\nBoshlash uchun /start")
    else:
        await query.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

# === Foydalanuvchi handlerlari ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_subscription(update, context):
        return
    user = update.effective_user
    first_name = user.first_name if user.first_name else "foydalanuvchi"
    await update.message.reply_text(
        f"👋 Assalomu alaykum, {first_name}, botimizga xush kelibsiz\n\n"
        "🎥 Bot orqali siz sevimli filmlar, seriallar va multfilmlarni sifatli formatda ko'rishingiz mumkin\n"
        "Kinolar ro'yxatini /movies buyrug'i bilan oling."
    )

async def movies_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_subscription(update, context):
        return
    movies = load_movies()
    if not movies:
        await update.message.reply_text("📭 Hozircha kino mavjud emas.")
        return

    # Kinolarni raqamlab chiqamiz
    movie_titles = list(movies.keys())
    text = "📋 *Mavjud kinolar:*\n"
    for idx, title in enumerate(movie_titles, 1):
        text += f"{idx}. {title}\n"
    text += "\nKerakli kino raqamini yuboring."
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def handle_number_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi raqam yuborsa, shu raqamdagi kinoni yuboradi."""
    # Admin kino qo'shayotgan bo'lsa, aralashmaymiz
    if context.user_data.get("awaiting_movie"):
        return

    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if not text.isdigit():
        return

    if not await require_subscription(update, context):
        return

    movies = load_movies()
    if not movies:
        await update.message.reply_text("📭 Hozircha kino mavjud emas.")
        return

    movie_titles = list(movies.keys())
    try:
        index = int(text) - 1
        if 0 <= index < len(movie_titles):
            title = movie_titles[index]
            file_id = movies[title]
            await update.message.reply_video(video=file_id, caption=f"🎬 {title}")
        else:
            await update.message.reply_text("❌ Bunday raqamli kino yo'q.")
    except Exception as e:
        logger.error(f"Raqamli xabarda xatolik: {e}")

# Inline qidiruv (ixtiyoriy)
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_subscription(update, context):
        return
    query = update.inline_query.query.strip()
    movies = load_movies()
    results = []

    if not query:
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
        "/addmovie - Yangi kino qo'shish\n"
        "/delete nomi - Kino o'chirish\n"
        "/list - Barcha kinolar ro'yxati\n"
        "/cancel - Bekor qilish"
    )
    await update.message.reply_text(text)

async def add_movie_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    await update.message.reply_text(
        "📤 Video xabarini forward qiling yoki kanal posti linkini yuboring.\n"
        "Xabar izohiga kino nomini yozing.\n"
        "❌ Bekor qilish uchun /cancel"
    )
    context.user_data["awaiting_movie"] = True

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if context.user_data.get("awaiting_movie"):
        context.user_data["awaiting_movie"] = False
        await update.message.reply_text("✅ Bekor qilindi.")
    else:
        await update.message.reply_text("ℹ️ Bekor qilinadigan jarayon yo'q.")

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get("awaiting_movie"):
        return

    message = update.message
    file_id = None
    title = message.caption or message.text

    if message.forward_from_chat and (message.video or message.document):
        if message.video:
            file_id = message.video.file_id
        elif message.document:
            file_id = message.document.file_id
        if not title:
            await message.reply_text("❌ Kino nomini izohga yozing.")
            return

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
        await update.message.reply_text(f"📋 Kinolar:\n{text}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Xatolik:", exc_info=context.error)

def main():
    app = Application.builder().token(TOKEN).build()

    # Callback handlerlar
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"))
    
    # Foydalanuvchi buyruqlari
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("movies", movies_list))
    app.add_handler(InlineQueryHandler(inline_query))
    
    # Raqamli xabarlar (admin jarayonida bo'lmasa)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number_message))
    
    # Admin handlerlari
    app.add_handler(CommandHandler("addmovie", add_movie_start))
    app.add_handler(CommandHandler("delete", delete_movie))
    app.add_handler(CommandHandler("list", list_admin))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("adminhelp", admin_help))
    app.add_handler(MessageHandler(
        filters.TEXT | filters.FORWARDED | filters.VIDEO | filters.Document.ALL,
        handle_admin_message
    ))
    
    app.add_error_handler(error_handler)

    logger.info("Bot ishga tushmoqda...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
