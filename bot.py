# ============================================================
# ELECTRICITY BILL ANALYZER – TELEGRAM BOT
# OCR + COHERE AI + PAYMENT LINKS + SOLAR ROI
# CLEAN • STABLE • BEGINNER FRIENDLY
# ============================================================

import os
import re
import cv2
import asyncio
import pytesseract
import cohere
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
# 1. ENVIRONMENT SETUP
# ============================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Tesseract OCR path (Windows)
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Cohere client (stable model)
co = cohere.Client(COHERE_API_KEY)
COHERE_MODEL = "command-r-08-2024"

# ============================================================
# 2. OFFICIAL DISCOM PAYMENT LINKS
# ============================================================

DISCOM_PAYMENT_URLS = {
    "MSEDCL": "https://www.mahadiscom.in/consumer/pay-bill",
    "MAHADISCOM": "https://www.mahadiscom.in/consumer/pay-bill",
    "BESCOM": "https://bescom.karnataka.gov.in/online-payment",
    "BRPL": "https://www.bsesdelhi.com/web/brpl/pay-bill",
    "BYPL": "https://www.bsesdelhi.com/web/bypl/pay-bill",
    "TANGEDCO": "https://www.tnebnet.org/awp/login",
    "TNEB": "https://www.tnebnet.org/awp/login",
    "UPPCL": "https://www.uppclonline.com/onlinebillpayment.aspx",
    "WBSEDCL": "https://www.wbsedcl.in/irj/go/km/docs/internet/new_website/payment/payment.html",
}

# ============================================================
# 3. MULTI-LANGUAGE TEXT (SIMPLE)
# ============================================================

TEXT = {
    "en": {
        "welcome": (
            "👋 *Electricity Bill Analyzer*\n\n"
            "📸 Send a clear photo of your electricity bill.\n\n"
            "I will:\n"
            "• Explain charges\n"
            "• Detect usage issues ⚠️\n"
            "• Estimate solar ROI ☀️\n"
            "• Give official payment link 💳"
        ),
        "analyzing": "📄 Bill received. Analyzing… ⏳",
        "ocr_fail": (
            "❌ *Could not read the bill clearly*\n\n"
            "Tips:\n"
            "• Use good lighting\n"
            "• Capture full bill\n"
            "• Avoid blur"
        ),
        "copy_btn": "📋 Copy Consumer Number",
        "pay_btn": "💳 Pay on Official Website",
        "copied": (
            "✅ *Consumer Number*\n\n"
            "`{}`\n\n"
            "_Long-press to copy_"
        ),
    },
}

USER_LANG = {}

def t(user_id: int, key: str) -> str:
    return TEXT["en"].get(key, "")

# ============================================================
# 4. HELPER FUNCTIONS
# ============================================================

def detect_discom(text: str):
    text = text.upper()
    for board in DISCOM_PAYMENT_URLS:
        if board in text:
            return board
    return None

def extract_consumer_number(text: str):
    patterns = [
        r"Consumer\s*No[:\s]*([A-Z0-9\-]{6,20})",
        r"CA\s*No[:\s]*([0-9]{6,20})",
        r"Account\s*No[:\s]*([0-9]{6,20})",
        r"Service\s*No[:\s]*([A-Z0-9]{6,20})",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def enhance_ocr(image_path: str) -> str:
    img = cv2.imread(image_path)
    if img is None:
        return ""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return pytesseract.image_to_string(gray)

def escape_md(text: str) -> str:
    for c in "_*[]()~`>#+-=|{}.!":
        text = text.replace(c, "\\" + c)
    return text

# ============================================================
# 5. CLEAN SECTION-BASED FORMATTER (SOLAR SAFE)
# ============================================================

def format_analysis(raw_text: str) -> str:
    sections = {
        "BILL_SUMMARY": "📄 ELECTRICITY BILL SUMMARY",
        "USAGE_ANALYSIS": "📊 USAGE ANALYSIS",
        "SOLAR_SAVINGS": "☀️ SOLAR SAVINGS ESTIMATE",
        "SAVING_TIPS": "💡 SMART SAVING TIPS",
    }

    output = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("SECTION:"):
            key = line.replace("SECTION:", "").strip()
            title = sections.get(key, key)
            output.append(f"\n{title}")
            output.append("━━━━━━━━━━━━━━━━━━━━━━")
        else:
            output.append(f"• {line}")

    return "\n".join(output)

# ============================================================
# 6. TELEGRAM HANDLERS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    USER_LANG[update.effective_user.id] = "en"
    await update.message.reply_text(
        t(update.effective_user.id, "welcome"),
        parse_mode="Markdown",
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(t(user_id, "analyzing"))

    photo = update.message.photo[-1]
    file = await photo.get_file()

    image_path = f"bill_{user_id}.jpg"
    await file.download_to_drive(image_path)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, analyze_bill, image_path, user_id
    )

    await update.message.reply_text(
        result["text"],
        reply_markup=result["buttons"],
        parse_mode="Markdown",
    )

    os.remove(image_path)

def analyze_bill(image_path: str, user_id: int):
    ocr_text = enhance_ocr(image_path)

    if len(ocr_text.strip()) < 40:
        return {"text": t(user_id, "ocr_fail"), "buttons": None}

    discom = detect_discom(ocr_text)
    consumer = extract_consumer_number(ocr_text)

    # 🔒 SOLAR IS FORCED — NEVER SKIPPED
    prompt = f"""
You are an Indian electricity bill expert.

OCR TEXT:
{ocr_text}

Respond EXACTLY in this structure:

SECTION: BILL_SUMMARY
Electricity Board
Billing Period
Units Consumed
Total Amount Payable

SECTION: USAGE_ANALYSIS
Is usage normal or high?
Any spikes?
Possible reasons

SECTION: SOLAR_SAVINGS
Assumptions:
- ₹60,000 per kW
- 1 kW = 120 units/month
- ₹7 per unit

Calculate:
Recommended solar size
Monthly savings
Payback period in years

SECTION: SAVING_TIPS
Give 5 practical tips.
"""

    response = co.chat(
        model=COHERE_MODEL,
        message=prompt,
        temperature=0.3,
    )

    analysis = escape_md(
        format_analysis(response.text.strip())
    )

    buttons = []

    if consumer:
        buttons.append([
            InlineKeyboardButton(
                t(user_id, "copy_btn"),
                callback_data=f"copy_{consumer}",
            )
        ])

    if discom:
        buttons.append([
            InlineKeyboardButton(
                t(user_id, "pay_btn"),
                url=DISCOM_PAYMENT_URLS[discom],
            )
        ])

    return {
        "text": analysis,
        "buttons": InlineKeyboardMarkup(buttons),
    }

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("copy_"):
        consumer = query.data.split("_", 1)[1]
        await query.message.reply_text(
            t(update.effective_user.id, "copied").format(consumer),
            parse_mode="Markdown",
        )

# ============================================================
# 7. MAIN
# ============================================================

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Electricity Bill Analyzer Bot running (SOLAR GUARANTEED)")
    app.run_polling()

if __name__ == "__main__":
    main()
