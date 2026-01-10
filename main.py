import os
import re
import cv2
import pytesseract
import cohere
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================= ENV =================
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

co = cohere.Client(COHERE_API_KEY)

# Tesseract path (Render auto-detects)
pytesseract.pytesseract.tesseract_cmd = "tesseract"

# ================= CONSTANTS =================
PAYMENT_PORTALS = {
    "MSEDCL": "https://www.mahadiscom.in/consumer/pay-bill",
    "BESCOM": "https://bescom.karnataka.gov.in/online-payment",
    "BSES": "https://www.bsesdelhi.com/web/brpl/pay-bill",
    "TANGEDCO": "https://www.tnebnet.org/awp/login",
}

# ================= HELPERS =================
def extract_consumer(text):
    m = re.search(r"(Consumer|Account|CA)\s*No[:\s]*([A-Z0-9]{6,20})", text, re.I)
    return m.group(2) if m else None

def detect_board(text):
    for b in PAYMENT_PORTALS:
        if b in text.upper():
            return b
    return None

def preprocess(img_path):
    img = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return pytesseract.image_to_string(gray)

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ *Electricity Bill Analyzer*\n\n"
        "📸 Send a photo of your electricity bill.\n\n"
        "I will:\n"
        "• Explain charges\n"
        "• Detect issues\n"
        "• Estimate solar ROI ☀️\n"
        "• Provide payment link 💳",
        parse_mode="Markdown"
    )

# ================= IMAGE HANDLER =================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📄 Bill received. Analyzing… ⏳")

    file = await update.message.photo[-1].get_file()
    path = f"bill_{update.effective_user.id}.jpg"
    await file.download_to_drive(path)

    text = preprocess(path)
    os.remove(path)

    if len(text) < 40:
        await msg.edit_text("❌ Image unclear. Please send a clearer bill photo.")
        return

    consumer = extract_consumer(text)
    board = detect_board(text)

    prompt = f"""
You are an Indian electricity bill expert.

OCR TEXT:
{text}

Create a CLEAR, EASY report with emojis.

MANDATORY:
1️⃣ Bill Summary
2️⃣ Units & Charges Explained
3️⃣ Usage Spike / Issues
4️⃣ ☀️ Solar ROI
   - ₹60,000 per kW
   - 120 units/month per kW
   - Monthly savings
   - Payback period
5️⃣ Money-saving tips (5)
"""

    response = co.chat(
        model="command-r-08-2024",
        message=prompt,
        temperature=0.3,
    )

    buttons = []
    if consumer:
        buttons.append([
            InlineKeyboardButton("📋 Copy Consumer Number", callback_data=f"copy_{consumer}")
        ])
    if board:
        buttons.append([
            InlineKeyboardButton("💳 Pay Bill", url=PAYMENT_PORTALS[board])
        ])

    await msg.delete()
    await update.message.reply_text(
        response.text,
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        parse_mode="Markdown"
    )

# ================= CALLBACK =================
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("copy_"):
        await q.message.reply_text(f"`{q.data[5:]}`", parse_mode="Markdown")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(callback))
    print("🤖 Bot running on Render")
    app.run_polling()

if __name__ == "__main__":
    main()
