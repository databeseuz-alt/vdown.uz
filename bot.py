"""
VDown.uz — Telegram Video Yuklab Olish Boti

Foydalanuvchi havola yuboradi → Bot videoni yuklab oladi →
HLS segmentlarni birlashtiradi → MKV sifatida yuboradi.
"""
import asyncio
import logging
import re
import os
from pathlib import Path
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatAction, ParseMode

from config import BOT_TOKEN, MESSAGES, MAX_FILE_SIZE
from downloader import (
    get_video_info,
    download_video,
    compress_video,
    get_file_size_mb,
    cleanup_file,
    DownloadError,
    VideoInfo,
)

# ─── Logging sozlash ──────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("vdown_bot")

# URL regex pattern
URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+",
    re.IGNORECASE,
)

# Foydalanuvchi holatlari (davom etayotgan yuklab olishlar)
active_downloads: dict[int, bool] = {}


# ─── Command Handlers ─────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start buyrug'i"""
    await update.message.reply_text(
        MESSAGES["start"],
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help buyrug'i"""
    await update.message.reply_text(
        MESSAGES["help"],
        parse_mode=ParseMode.HTML,
    )


# ─── URL Handler ──────────────────────────────────────

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Foydalanuvchi yuborgan URL ni qayta ishlash"""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()

    # URL ni ajratib olish
    match = URL_PATTERN.search(message_text)
    if not match:
        await update.message.reply_text(MESSAGES["invalid_url"])
        return

    url = match.group(0)

    # Agar allaqachon yuklab olish davom etayotgan bo'lsa
    if active_downloads.get(user_id):
        await update.message.reply_text(
            "⏳ Avvalgi yuklab olish davom etmoqda. Iltimos, kuting..."
        )
        return

    # Tahlil bosqichi
    status_msg = await update.message.reply_text(MESSAGES["analyzing"])

    try:
        # Video ma'lumotlarini olish
        await update.message.chat.send_action(ChatAction.TYPING)
        video_info = await get_video_info(url)

        # Sifat tanlash tugmalarini ko'rsatish
        qualities = video_info.available_qualities
        if len(qualities) > 1:
            keyboard = []
            row = []
            for q in qualities:
                emoji = {"360p": "📱", "480p": "📺", "720p": "💻", "1080p": "🖥", "best": "⭐"}.get(q, "▶️")
                row.append(
                    InlineKeyboardButton(
                        f"{emoji} {q.upper()}",
                        callback_data=f"quality:{q}:{url}",
                    )
                )
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)

            info_text = (
                f"🎬 <b>{_escape_html(video_info.title)}</b>\n"
                f"⏱ Davomiyligi: {video_info.duration_str}\n\n"
                f"{MESSAGES['choose_quality']}"
            )

            await status_msg.edit_text(
                info_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            # Faqat bitta sifat — darhol yuklab olish
            await status_msg.edit_text(
                f"🎬 <b>{_escape_html(video_info.title)}</b>\n"
                f"⏱ Davomiyligi: {video_info.duration_str}\n\n"
                f"⬇️ Yuklab olinmoqda...",
                parse_mode=ParseMode.HTML,
            )
            await _process_download(update, context, url, "best", status_msg)

    except DownloadError as e:
        await status_msg.edit_text(f"❌ {e}")
    except Exception as e:
        logger.error(f"URL handling xatosi: {e}", exc_info=True)
        await status_msg.edit_text(MESSAGES["error"].format(error=str(e)))


# ─── Callback (Sifat tanlash) ─────────────────────────

async def handle_quality_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Sifat tugmasi bosilganda"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("quality:"):
        return

    parts = data.split(":", 2)
    if len(parts) != 3:
        return

    _, quality, url = parts

    status_msg = query.message
    await status_msg.edit_text(
        f"⬇️ <b>{quality.upper()}</b> sifatda yuklab olinmoqda...",
        parse_mode=ParseMode.HTML,
    )

    await _process_download(update, context, url, quality, status_msg)


# ─── Download Processing ──────────────────────────────

async def _process_download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    quality: str,
    status_msg,
) -> None:
    """Videoni yuklab olish va yuborish jarayoni"""
    user_id = update.effective_user.id
    active_downloads[user_id] = True
    downloaded_path = None
    compressed_path = None

    try:
        chat = update.effective_chat

        # Progress callback
        last_update_time = [0]

        async def progress_callback(percent: float, status: str):
            now = asyncio.get_event_loop().time()
            # Har 3 sekundda yangilash (flood limitni oldini olish)
            if now - last_update_time[0] < 3:
                return
            last_update_time[0] = now

            if status == "downloading":
                progress_bar = _make_progress_bar(percent)
                text = f"⬇️ Yuklab olinmoqda...\n{progress_bar} {percent}%"
            elif status == "merging":
                text = MESSAGES["merging"]
            else:
                text = f"⏳ {status}..."

            try:
                await status_msg.edit_text(text)
            except Exception:
                pass

        # Yuklab olish
        await chat.send_action(ChatAction.UPLOAD_VIDEO)
        downloaded_path = await download_video(url, quality, progress_callback)
        logger.info(f"Yuklab olindi: {downloaded_path}")

        # Fayl hajmini tekshirish
        file_size_mb = get_file_size_mb(downloaded_path)
        logger.info(f"Fayl hajmi: {file_size_mb:.1f} MB")

        send_path = downloaded_path

        if downloaded_path.stat().st_size > MAX_FILE_SIZE:
            # Siqish kerak
            await status_msg.edit_text(
                MESSAGES["too_large"].format(size=f"{file_size_mb:.0f}")
            )
            compressed_path = await compress_video(downloaded_path)
            send_path = compressed_path

            # Siqilgandan keyin ham katta bo'lsa
            if send_path.stat().st_size > MAX_FILE_SIZE:
                await status_msg.edit_text(
                    "❌ Video juda katta (siqilgandan keyin ham 50 MB dan oshadi).\n"
                    "Pastroq sifatni tanlang yoki qisqaroq video yuboring."
                )
                return

        # Telegramga yuborish
        await status_msg.edit_text(MESSAGES["uploading"])
        await chat.send_action(ChatAction.UPLOAD_VIDEO)

        with open(send_path, "rb") as video_file:
            await chat.send_video(
                video=video_file,
                caption=f"🎬 VDown Bot orqali yuklab olindi\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300,
                connect_timeout=60,
            )

        await status_msg.edit_text(MESSAGES["done"])
        logger.info(f"Video yuborildi: user={user_id}")

    except DownloadError as e:
        logger.error(f"Download xatosi: {e}")
        await status_msg.edit_text(MESSAGES["error"].format(error=str(e)))
    except Exception as e:
        logger.error(f"Kutilmagan xato: {e}", exc_info=True)
        await status_msg.edit_text(
            MESSAGES["error"].format(error="Ichki xato yuz berdi. Qayta urinib ko'ring.")
        )
    finally:
        # Tozalash
        active_downloads.pop(user_id, None)
        if downloaded_path:
            cleanup_file(downloaded_path)
        if compressed_path:
            cleanup_file(compressed_path)


# ─── Yordamchi funksiyalar ─────────────────────────────

def _make_progress_bar(percent: int, length: int = 20) -> str:
    """Progress bar yasash: ████████░░░░"""
    filled = int(length * percent / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}]"


def _escape_html(text: str) -> str:
    """HTML belgilarni escape qilish"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ─── Error Handler ────────────────────────────────────

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global xatolarni ushlash"""
    logger.error(f"Xatolik: {context.error}", exc_info=context.error)

    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Kutilmagan xato yuz berdi. Iltimos, qayta urinib ko'ring."
            )
        except Exception:
            pass


# ─── Main ──────────────────────────────────────────────

def main():
    """Botni ishga tushirish"""
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN topilmadi!")
        print("1. @BotFather dan bot yarating va token oling")
        print("2. .env faylga yozing: BOT_TOKEN=your_token_here")
        print("3. Qayta ishga tushiring")
        return

    print("🚀 VDown Bot ishga tushmoqda...")

    # Application yaratish
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(handle_quality_callback, pattern=r"^quality:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    # Error handler
    app.add_error_handler(error_handler)

    print("✅ Bot tayyor! Ctrl+C bilan to'xtatish mumkin.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
