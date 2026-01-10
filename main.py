import os
import re
import cv2
import asyncio
import easyocr
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

# ================== ENV ==================
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

co = cohere.Client(COHERE_API_KEY)

# ================== EASY OCR (LAZY LOAD) ==================
_easyocr_reader = None

def get_ocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        print("🔄 Loading EasyOCR model (first run only)...")
        _easyocr_reader = easyocr.Reader(["en"], gpu=False)
    return _easyocr_reader

# ================== USER PREFS ==================
user_lang = {}

def lang(uid):
    return user_lang.get(uid, "en")

# ================== TRANSLATIONS ==================
T = {
    "en": {
        "start": (
            "⚡ *Electricity Bill Analyzer*\n\n"
            "📸 Send a photo of your electricity bill and I will:\n"
            "• Explain all charges\n"
            "• Detect usage spikes\n"
            "• Estimate solar ROI ☀️\n"
            "• Give official payment link 💳"
        ),
        "analyzing": "📄 *Bill received*\n🔍 Analyzing… please wait ⏳",
        "ocr_fail": "❌ Could not read the bill clearly.\nPlease send a sharper photo.",
        "copy": "📋 Copy Consumer Number",
        "pay": "💳 Pay Bill on Official Portal",
        "lang_set": "✅ Language set to English",
    },
    "hi": {
        "start": (
            "⚡ *बिजली बिल विश्लेषक*\n\n"
            "📸 अपना बिजली बिल भेजें और मैं:\n"
            "• सभी शुल्क समझाऊंगा\n"
            "• अधिक उपयोग बताऊंगा\n"
            "• सोलर ROI बताऊंगा ☀️\n"
            "• भुगतान लिंक दूँगा 💳"
        ),
        "analyzing": "📄 *बिल प्राप्त हुआ*\n🔍 विश्लेषण किया जा रहा है ⏳",
        "ocr_fail": "❌ बिल स्पष्ट नहीं पढ़ पाया।\nकृपया साफ फोटो भेजें।",
        "copy": "📋 उपभोक्ता संख्या कॉपी करें",
        "pay": "💳 आधिकारिक पोर्टल पर भुगतान करें",
        "lang_set": "✅ भाषा हिंदी में सेट की गई",
    },
}

# ================== PAYMENT LINKS ==================
PAYMENT_LINKS = {
    "MSEDCL": "https://www.mahadiscom.in/consumer/pay-bill",
    "BESCOM": "https://bescom.karnataka.gov.in/online-payment",
    "BSES": "https://www.bsesdelhi.com/web/brpl/pay-bill",
    "TANGEDCO": "https://www.tnebnet.org/awp/login",
}

# ================== HELPERS ==================
def extract_consumer(text):
    m = re.search(r"(Consumer|Account|CA)\s*No[:\s]*([A-Z0-9]{6,20})", text, re.I)
    return m.group(2) if m else None

def detect_board(text):
    for b in PAYMENT_LINKS:
        if b in text.upper():
            return b
    return None

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"),
         InlineKeyboardButton("हिंदी 🇮🇳", callback_data="lang_hi")]
    ]
    await update.message.reply_text(
        T[lang(update.effective_user.id)]["start"],
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )

# ================== IMAGE HANDLER ==================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = await update.message.reply_text(T[lang(uid)]["analyzing"], parse_mode="Markdown")

    file = await update.message.photo[-1].get_file()
    path = f"bill_{uid}.jpg"
    await file.download_to_drive(path)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, analyze_bill, path, uid)

    await msg.delete()
    await update.message.reply_text(
        result["text"],
        reply_markup=result["buttons"],
        parse_mode="Markdown",
    )

    os.remove(path)

# ================== BILL ANALYSIS ==================
def analyze_bill(image_path, uid):
    reader = get_ocr_reader()
    ocr = reader.readtext(image_path, detail=0)
    text = "\n".join(ocr)

    if len(text) < 40:
        return {"text": T[lang(uid)]["ocr_fail"], "buttons": None}

    consumer = extract_consumer(text)
    board = detect_board(text)

    prompt = f"""
You are an expert Indian electricity bill analyst.

OCR TEXT:
{text}

Produce a CLEAN, EASY-TO-READ report with emojis.

MANDATORY sections:
1️⃣ BILL SUMMARY
2️⃣ UNITS & COST EXPLANATION
3️⃣ SPIKE / ISSUE DETECTION
4️⃣ ☀️ SOLAR SAVINGS ESTIMATE (IMPORTANT)
   - ₹60,000 per kW
   - 120 units/month per kW
   - Show monthly saving
   - Show payback period in years
5️⃣ MONEY SAVING TIPS (5 points)

Keep language SIMPLE.
"""

    ai = co.chat(
        model="command-r-08-2024",
        message=prompt,
        temperature=0.3,
    )

    buttons = []
    if consumer:
        buttons.append([InlineKeyboardButton(T[lang(uid)]["copy"], callback_data=f"copy_{consumer}")])
    if board:
        buttons.append([InlineKeyboardButton(T[lang(uid)]["pay"], url=PAYMENT_LINKS[board])])

    return {
        "text": ai.text,
        "buttons": InlineKeyboardMarkup(buttons) if buttons else None,
    }

# ================== CALLBACKS ==================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data.startswith("lang_"):
        user_lang[uid] = q.data.split("_")[1]
        await q.edit_message_text(T[user_lang[uid]]["lang_set"])

    elif q.data.startswith("copy_"):
        await q.message.reply_text(f"`{q.data[5:]}`", parse_mode="Markdown")

# ================== MAIN ==================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(callbacks))
    print("🤖 Bot running on Railway")
    app.run_polling()

if __name__ == "__main__":
    main()
