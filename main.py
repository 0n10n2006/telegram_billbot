# ============================================================
# ELECTRICITY BILL ANALYZER – TELEGRAM BOT
# Render-ready | EasyOCR | Cohere AI | Solar ROI
# ============================================================

import os
import re
import asyncio
import easyocr
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
# 1. LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

if not TELEGRAM_BOT_TOKEN or not COHERE_API_KEY:
    raise RuntimeError("Missing environment variables")

# ============================================================
# 2. AI + OCR SETUP
# ============================================================
import easyocr

_easyocr_reader = None

def get_ocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        print("🔄 Initializing EasyOCR (first run only)...")
        _easyocr_reader = easyocr.Reader(["en"], gpu=False)
    return _easyocr_reader


# Cohere client
co = cohere.Client(COHERE_API_KEY)
COHERE_MODEL = "command-r-08-2024"

# ============================================================
# 3. OFFICIAL ELECTRICITY PAYMENT PORTALS
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
# 4. USER TEXT (SIMPLE & CLEAN)
# ============================================================

TEXT = {
    "welcome": (
        "👋 *Electricity Bill Analyzer*\n\n"
        "📸 Send a clear photo of your electricity bill.\n\n"
        "I will:\n"
        "• Explain charges\n"
        "• Detect high usage ⚠️\n"
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
}

# ============================================================
# 5. HELPER FUNCTIONS
# ============================================================

def escape_md(text: str) -> str:
    for c in "_*[]()~`>#+-=|{}.!":
        text = text.replace(c, "\\" + c)
    return text

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

def perform_ocr(image_path: str) -> str:
    results = reader.readtext(image_path)
    return " ".join([r[1] for r in results])

# ============================================================
# 6. FORMAT OUTPUT (SOLAR SAFE)
# ============================================================

def format_analysis(raw: str) -> str:
    titles = {
        "BILL_SUMMARY": "📄 ELECTRICITY BILL SUMMARY",
        "USAGE_ANALYSIS": "📊 USAGE ANALYSIS",
        "SOLAR_SAVINGS": "☀️ SOLAR SAVINGS ESTIMATE",
        "SAVING_TIPS": "💡 SMART SAVING TIPS",
    }

    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("SECTION:"):
            key = line.replace("SECTION:", "").strip()
            out.append(f"\n{titles.get(key, key)}")
            out.append("━━━━━━━━━━━━━━━━━━━━━━")
        else:
            out.append(f"• {line}")

    return "\n".join(out)

# ============================================================
# 7. TELEGRAM HANDLERS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        TEXT["welcome"],
        parse_mode="Markdown",
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEXT["analyzing"])

    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_path = f"bill_{update.effective_user.id}.jpg"
    await file.download_to_drive(image_path)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, analyze_bill, image_path
    )

    await update.message.reply_text(
        result["text"],
        reply_markup=result["buttons"],
        parse_mode="Markdown",
    )

    os.remove(image_path)

def analyze_bill(image_path: str):
    ocr_text = perform_ocr(image_path)

    if len(ocr_text.strip()) < 40:
        return {"text": TEXT["ocr_fail"], "buttons": None}

    discom = detect_discom(ocr_text)
    consumer = extract_consumer_number(ocr_text)

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

    analysis = escape_md(format_analysis(response.text.strip()))

    buttons = []

    if consumer:
        buttons.append([
            InlineKeyboardButton(
                TEXT["copy_btn"],
                callback_data=f"copy_{consumer}",
            )
        ])

    if discom:
        buttons.append([
            InlineKeyboardButton(
                TEXT["pay_btn"],
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
            TEXT["copied"].format(consumer),
            parse_mode="Markdown",
        )

# ============================================================
# 8. MAIN ENTRY POINT
# ============================================================

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Electricity Bill Analyzer Bot running on Render")
    app.run_polling()

if __name__ == "__main__":
    main()
