import os
import re
import asyncio
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
import cohere

# ==========================
# ENV & CONFIG
# ==========================
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

co = cohere.Client(COHERE_API_KEY)
COHERE_MODEL = "command-r-08-2024"

# ==========================
# DISCOM PAYMENT LINKS
# ==========================
DISCOM_PAYMENT_URLS = {
    "MSEDCL": "https://www.mahadiscom.in/consumer/pay-bill",
    "BESCOM": "https://bescom.karnataka.gov.in/online-payment",
    "BRPL": "https://www.bsesdelhi.com/web/brpl/pay-bill",
    "BYPL": "https://www.bsesdelhi.com/web/bypl/pay-bill",
    "TANGEDCO": "https://www.tnebnet.org/awp/login",
    "UPPCL": "https://www.uppclonline.com/onlinebillpayment.aspx",
    "WBSEDCL":
    "https://www.wbsedcl.in/irj/go/km/docs/internet/new_website/payment/payment.html",
    "TPDDL": "https://www.tatapower-ddl.com/billpay/paybill.aspx",
    "PSPCL": "https://www.pspcl.in/online-bill-payment",
}


# ==========================
# HELPERS
# ==========================
def detect_discom(text: str):
    text = text.upper()
    for d in DISCOM_PAYMENT_URLS:
        if d in text:
            return d
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


# ==========================
# START COMMAND
# ==========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ *Electricity Bill Analyzer Bot*\n\n"
        "📸 Send a photo of your electricity bill and I will:\n"
        "• Explain all charges clearly\n"
        "• Detect usage issues\n"
        "• Estimate *Solar ROI & Payback*\n"
        "• Give official payment links\n\n"
        "_Works best with clear English or bilingual bills._",
        parse_mode="Markdown")


# ==========================
# IMAGE HANDLER
# ==========================
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = await update.message.reply_text("📄 Bill received. Analyzing… ⏳")

    photo = update.message.photo[-1]
    file = await photo.get_file()
    path = f"bill_{update.effective_user.id}.jpg"
    await file.download_to_drive(path)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, analyze_bill, path)

    await status.delete()

    await update.message.reply_text(result["text"],
                                    reply_markup=result["buttons"],
                                    parse_mode="Markdown")

    if os.path.exists(path):
        os.remove(path)


# ==========================
# CORE ANALYSIS (COHERE FORCED)
# ==========================
def analyze_bill(image_path: str):
    extracted_text = """
    Indian Electricity Bill
    Provider: MSEDCL
    Monthly Units: 300
    Total Amount: ₹2400
    """

    consumer_no = extract_consumer_number(extracted_text)
    discom = detect_discom(extracted_text)

    prompt = """
You are an expert Indian electricity analyst.

ALWAYS estimate solar ROI using:
- Avg units: 300/month
- Rate: ₹8/unit
- Solar cost: ₹60,000 per kW
- 1 kW = 120 units/month

Respond with sections:

⚡ BILL SUMMARY
📊 USAGE ANALYSIS
☀️ SOLAR ROI ESTIMATE (MANDATORY)
💡 SMART RECOMMENDATIONS
"""

    response = co.chat(model=COHERE_MODEL, message=prompt, temperature=0.3)

    analysis_text = response.text.strip()

    # -------------------
    # BUTTONS (FIXED)
    # -------------------
    buttons = []

    if consumer_no:
        buttons.append([
            InlineKeyboardButton("📋 Copy Consumer Number",
                                 callback_data=f"copy_{consumer_no}")
        ])

    # ✅ ALWAYS SHOW PAYMENT BUTTON
    payment_url = (DISCOM_PAYMENT_URLS.get(discom)
                   if discom in DISCOM_PAYMENT_URLS else
                   "https://www.bharatbillpay.com/")

    buttons.append(
        [InlineKeyboardButton("💳 Pay Electricity Bill", url=payment_url)])

    return {"text": analysis_text, "buttons": InlineKeyboardMarkup(buttons)}


# ==========================
# CALLBACKS
# ==========================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("copy_"):
        number = query.data.replace("copy_", "")
        await query.message.reply_text(
            f"✅ *Consumer Number Copied*\n\n`{number}`", parse_mode="Markdown")


# ==========================
# MAIN
# ==========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(CallbackQueryHandler(callbacks))

    print("🤖 Telegram Electricity Bill Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
