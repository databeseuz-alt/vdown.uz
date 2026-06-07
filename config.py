"""
VDown.uz Bot — Sozlamalar moduli
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env fayldan sozlamalarni o'qish
load_dotenv()

# ─── Telegram Bot ──────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ─── Yuklab olish sozlamalari ──────────────────────────
# Telegram Bot API maksimal fayl hajmi (50 MB)
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 50 * 1024 * 1024))

# Vaqtinchalik yuklab olish papkasi
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "./downloads"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─── yt-dlp sozlamalari ───────────────────────────────
YTDLP_OPTIONS = {
    # Eng yaxshi sifatni tanlash
    "format": "bestvideo+bestaudio/best",
    # Chiqish formati — MKV
    "merge_output_format": "mkv",
    # Fayl nomi shabloni
    "outtmpl": str(DOWNLOAD_DIR / "%(id)s_%(title).50s.%(ext)s"),
    # Hech qanday banner/reklama chiqarmaslik
    "quiet": True,
    "no_warnings": True,
    # HTTP so'rov headerlari (ba'zi saytlar uchun kerak)
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "uz,ru;q=0.9,en;q=0.8",
    },
    # Segmentlarni parallella yuklab olish (tezroq)
    "concurrent_fragment_downloads": 5,
    # Qayta urinish
    "retries": 3,
    "fragment_retries": 5,
}

# ─── Sifat variantlari ────────────────────────────────
QUALITY_OPTIONS = {
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "best": "bestvideo+bestaudio/best",
}

# ─── Xabarlar (O'zbek tilida) ─────────────────────────
MESSAGES = {
    "start": (
        "🎬 <b>VDown Bot</b> — Video Yuklab Olish Boti\n\n"
        "📎 Menga video havolasini yuboring va men sizga "
        "videoni <b>MKV</b> formatda yuklab beraman!\n\n"
        "✅ 1000+ sayt qo'llab-quvvatlanadi\n"
        "✅ HLS/m3u8 segmentlar avtomatik birlashtiriladi\n"
        "✅ Sifat tanlash imkoniyati\n\n"
        "💡 Havola yuboring — boshlaymiz!"
    ),
    "help": (
        "📖 <b>Yordam</b>\n\n"
        "1️⃣ Video havolasini yuboring\n"
        "2️⃣ Sifatni tanlang (yoki avtomatik eng yaxshisi)\n"
        "3️⃣ Videoni yuklab oling!\n\n"
        "📌 <b>Buyruqlar:</b>\n"
        "/start — Botni boshlash\n"
        "/help — Yordam\n\n"
        "⚠️ Maksimal fayl hajmi: 50 MB\n"
        "Kattaroq videolar avtomatik siqiladi."
    ),
    "invalid_url": "❌ Iltimos, to'g'ri havola yuboring.",
    "analyzing": "🔍 Havola tahlil qilinmoqda...",
    "downloading": "⬇️ Yuklab olinmoqda... {progress}%",
    "merging": "🔄 Segmentlar birlashtirilmoqda...",
    "compressing": "🗜 Fayl siqilmoqda (hajmi katta)...",
    "uploading": "📤 Telegramga yuborilmoqda...",
    "done": "✅ Tayyor! Yoqimli tomosha! 🎬",
    "error": "❌ Xatolik yuz berdi: {error}",
    "no_video": "❌ Bu havolada video topilmadi.",
    "too_large": (
        "⚠️ Video hajmi juda katta ({size} MB).\n"
        "Siqib ko'rilmoqda..."
    ),
    "choose_quality": "🎚 Sifatni tanlang:",
}
