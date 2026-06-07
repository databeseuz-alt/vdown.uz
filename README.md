# 🎬 VDown.uz — Telegram Video Yuklab Olish Boti

Foydalanuvchi havola yuboradi → Bot saytdan videoni topadi → HLS segmentlarni yuklab oladi → MKV qilib birlashtiradi → Telegramga yuboradi.

## ✨ Imkoniyatlar

- ✅ **1000+ sayt** qo'llab-quvvatlanadi (YouTube, AsilMedia, va boshqalar)
- ✅ **HLS/m3u8** segmentlarni avtomatik yuklab olish va birlashtirish
- ✅ **MKV** formatda chiqish
- ✅ **Sifat tanlash** (360p, 480p, 720p, 1080p)
- ✅ **Progress bar** — yuklab olish jarayonini kuzatish
- ✅ **Avtomatik siqish** — katta fayllar uchun
- ✅ **O'zbek tilida** interfeys

## 📋 Talablar

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/download.html) o'rnatilgan bo'lishi kerak
- Telegram Bot Token ([@BotFather](https://t.me/BotFather) dan olinadi)

## 🚀 O'rnatish

### 1. Repositoryni klonlash
```bash
git clone https://github.com/yourusername/vdown.uz.git
cd vdown.uz
```

### 2. Virtual environment yaratish
```bash
python -m venv venv
venv\Scripts\activate   # Windows
# yoki
source venv/bin/activate  # Linux/Mac
```

### 3. Kutubxonalarni o'rnatish
```bash
pip install -r requirements.txt
```

### 4. ffmpeg o'rnatish

**Windows:**
```bash
# winget orqali
winget install Gyan.FFmpeg

# yoki chocolatey orqali
choco install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg
```

### 5. Sozlamalar (.env fayl)
```bash
copy .env.example .env
```

`.env` faylni oching va `BOT_TOKEN` ni o'z tokeningiz bilan almashtiring:
```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 6. Botni ishga tushirish
```bash
python bot.py
```

## 📖 Foydalanish

1. Telegramda botingizni oching
2. `/start` buyrug'ini yuboring
3. Video havolasini yuboring (masalan: `https://asilmedia.org/...`)
4. Sifatni tanlang (tugmalar orqali)
5. Video yuklab olinadi va MKV sifatida yuboriladi! 🎉

## 📁 Loyiha tuzilmasi

```
vdown.uz/
├── bot.py           # Asosiy bot logikasi
├── downloader.py    # Video yuklab olish moduli (yt-dlp + ffmpeg)
├── config.py        # Sozlamalar
├── .env             # Maxfiy sozlamalar (token)
├── .env.example     # Namuna sozlamalar
├── requirements.txt # Python kutubxonalar
├── downloads/       # Vaqtinchalik yuklab olish papkasi
└── README.md        # Ushbu fayl
```

## ⚙️ Qanday ishlaydi?

```
Havola → yt-dlp (video topish) → HLS segmentlar yuklanadi
→ ffmpeg (birlashtirish) → MKV fayl → Telegram yuborish → Tozalash
```

1. **URL qabul qilish** — Foydalanuvchi havola yuboradi
2. **Video aniqlash** — `yt-dlp` saytdan video stream'ni topadi
3. **Segmentlar yuklab olish** — HLS (.ts) bo'laklarni parallel yuklab olish
4. **Birlashtirish** — `ffmpeg` orqali barcha segmentlar bitta MKV faylga birlashtiriladi
5. **Hajm tekshirish** — Agar 50 MB dan katta bo'lsa, avtomatik siqiladi
6. **Yuborish** — MKV fayl Telegram orqali foydalanuvchiga yuboriladi
7. **Tozalash** — Vaqtinchalik fayllar o'chiriladi

## ⚠️ Eslatmalar

- Telegram Bot API orqali maksimal **50 MB** fayl yuboriladi
- Kattaroq videolar avtomatik siqiladi (sifat bir oz pasayishi mumkin)
- `ffmpeg` o'rnatilmagan bo'lsa, birlashtirish ishlamaydi
- Vaqtinchalik fayllar `downloads/` papkasida saqlanadi va yuborilgandan so'ng o'chiriladi

## 📄 Litsenziya

MIT