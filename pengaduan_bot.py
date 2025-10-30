import logging
import os
import json
from datetime import datetime
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Logging ---
logging.basicConfig(level=logging.INFO)

# --- Tahapan Form ---
NAMA, USERNAME, KELUHAN, BUKTI = range(4)

# --- Ambil dari ENV ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

if not BOT_TOKEN or not GOOGLE_CREDENTIALS:
    raise ValueError("BOT_TOKEN atau GOOGLE_CREDENTIALS tidak ditemukan di environment variables!")

# --- Multi Admin ---
ADMIN_IDS = [5704050846, 987654321]  # Ganti sesuai chat_id admin

# --- Koneksi Google Sheet ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

creds_dict = json.loads(GOOGLE_CREDENTIALS)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Pengaduan JokerBola").sheet1  # nama sheet

# --- Fungsi nomor tiket otomatis ---
def generate_ticket_number():
    today = datetime.now().strftime("%Y%m%d")
    records = sheet.get_all_records()
    count_today = sum(1 for row in records if str(row["Timestamp"]).startswith(datetime.now().strftime("%Y-%m-%d")))
    return f"JB-{today}-{count_today+1:03d}"

# --- Escape karakter MarkdownV2 ---
def escape_markdown(text: str) -> str:
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f"\\{c}" if c in escape_chars else c for c in text)

# --- Start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Halo! Selamat datang di *Layanan Pengaduan JokerBola*.\n\n"
        "Silakan isi data berikut untuk melaporkan keluhan Anda.\n\n"
        "📝 Nama lengkap:",
        parse_mode="Markdown"
    )
    return NAMA

# --- Nama ---
async def nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nama"] = update.message.text
    context.user_data["user_id"] = update.message.from_user.id
    context.user_data["username_tg"] = update.message.from_user.username or "-"
    await update.message.reply_text("🆔 Masukkan ID / Username akun JokerBola Anda:")
    return USERNAME

# --- Username ---
async def username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["username"] = update.message.text
    await update.message.reply_text("📋 Jelaskan keluhan Anda:")
    return KELUHAN

# --- Keluhan ---
async def keluhan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["keluhan"] = update.message.text
    await update.message.reply_text(
        "📸 Kirimkan foto bukti (opsional). Jika tidak ada, ketik *skip*.",
        parse_mode="Markdown"
    )
    return BUKTI

# --- Bukti ---
async def bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        context.user_data["bukti"] = file.file_id
        context.user_data["bukti_url"] = file.file_path  # link file Telegram
    else:
        context.user_data["bukti"] = "Tidak ada"
        context.user_data["bukti_url"] = "Tidak ada"
    await kirim_ringkasan(update, context)
    return ConversationHandler.END

async def skip_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["bukti"] = "Tidak ada"
    context.user_data["bukti_url"] = "Tidak ada"
    await kirim_ringkasan(update, context)
    return ConversationHandler.END

# --- Kirim ringkasan ke admin + Google Sheet + feedback ke user ---
async def kirim_ringkasan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ticket_id = generate_ticket_number()

    # Escape semua text
    nama_esc = escape_markdown(data['nama'])
    username_esc = escape_markdown(data['username'])
    keluhan_esc = escape_markdown(data['keluhan'])
    username_tg_esc = escape_markdown(data['username_tg'])
    tiket_esc = escape_markdown(ticket_id)
    bukti_text = "Terlampir" if data["bukti"] != "Tidak ada" else "Tidak ada"

    # Balasan ke user
    reply_text = (
        f"✅ Terima kasih, {nama_esc}!\n"
        f"Laporan Anda telah diterima.\n\n"
        f"Nomor tiket Anda: *{tiket_esc}*\n"
        f"Gunakan perintah /cek {tiket_esc} untuk memantau status laporan Anda."
    )
    try:
        await update.message.reply_text(reply_text, parse_mode="MarkdownV2", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        logging.error(f"❌ Gagal kirim balasan ke user: {e}")

    # Ringkasan untuk admin
    ringkasan = (
        f"🎟️ *TIKET PENGADUAN BARU*\n\n"
        f"🧾 Nomor Tiket: `{tiket_esc}`\n"
        f"📅 Waktu: {timestamp}\n\n"
        f"👤 Nama: {nama_esc}\n"
        f"🆔 Username Akun: {username_esc}\n"
        f"💬 Keluhan: {keluhan_esc}\n"
        f"📎 Bukti: {bukti_text}\n\n"
        f"👤 Telegram: [t.me/{username_tg_esc}](https://t.me/{username_tg_esc}) (ID: {data['user_id']})"
    )

    # Kirim ke admin
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, ringkasan, parse_mode="MarkdownV2", disable_web_page_preview=True)
            if data["bukti"] != "Tidak ada":
                await context.bot.send_photo(admin_id, data["bukti"], caption=f"Tiket: {ticket_id}")
            logging.info(f"📩 Notifikasi terkirim ke admin {admin_id}")
        except Exception as e:
            logging.warning(f"⚠️ Gagal kirim notifikasi ke admin {admin_id}: {e}")

    # Simpan ke Google Sheet
    try:
        sheet.append_row([
            timestamp,
            ticket_id,
            data["nama"],
            data["username"],
            data["keluhan"],
            data["bukti_url"],  # simpan link file
            f"t.me/{data['username_tg']}",
            data["user_id"],
            "Sedang diproses"
        ])
        logging.info(f"✅ Data berhasil dikirim ke Google Sheet: {ticket_id}")
    except Exception as e:
        logging.error(f"❌ Gagal menulis ke Google Sheet: {e}")

# --- /cek ---
async def cek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("❗Gunakan format: /cek [nomor_tiket]\nContoh: /cek JB-20251030-001")
        return
    ticket = context.args[0].strip()
    records = sheet.get_all_records()
    for row in records:
        if row["Ticket ID"] == ticket:
            msg = (
                f"📋 *Status Pengaduan Anda*\n\n"
                f"🎟️ Nomor Tiket: `{escape_markdown(ticket)}`\n"
                f"👤 Nama: {escape_markdown(row['Nama'])}\n"
                f"🆔 Username: {escape_markdown(row['Username'])}\n"
                f"💬 Keluhan: {escape_markdown(row['Keluhan'])}\n"
                f"📅 Waktu: {row['Timestamp']}\n"
                f"📊 Status: *{escape_markdown(row['Status'])}*"
            )
            await update.message.reply_text(msg, parse_mode="MarkdownV2")
            return
    await update.message.reply_text("⚠️ Nomor tiket tidak ditemukan. Pastikan format benar.")

# --- Cancel ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Formulir dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- Jalankan Bot ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, nama)],
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, username)],
            KELUHAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, keluhan)],
            BUKTI: [
                MessageHandler(filters.PHOTO, bukti),
                MessageHandler(filters.Regex("^(skip|Skip|SKIP)$"), skip_bukti),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("cek", cek))
    app.run_polling()

if __name__ == "__main__":
    main()
