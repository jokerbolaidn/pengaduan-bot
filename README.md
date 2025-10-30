# Pengaduan JokerBola Bot

Bot Telegram untuk menerima laporan keluhan user dan menyimpan ke Google Sheet.

## Deploy Railway

1. Push repo ke GitHub.
2. Buat project baru di Railway → Deploy from GitHub.
3. Set Environment Variables:
   - BOT_TOKEN → token Telegram bot
   - GOOGLE_CREDENTIALS → isi file `credentials.json` seluruhnya (paste satu baris)
4. Railway otomatis build & jalankan bot.
