"""
Fintel Short Interest Telegram Bot — Render.com uchun moslashtirilgan
======================================================================

Foydalanuvchi "#TICKER" yozsa (masalan #BIYA, #TNXP), bot javob beradi:

#TICKER

📉 Short Interest: XX.X%
💰 Borrow Fee (CTB): XX.X%
📦 Shares Available: XXX,XXX
🔥 Short Squeeze Score: XX/100

RENDER.COM'DA ISHGA TUSHIRISH:
    Build command:  pip install -r requirements.txt
    Start command:  python main.py
    Environment variable: BOT_TOKEN = <sizning bot tokeningiz>

Render bepul tarifi 15 daqiqa faoliyatsizlikdan keyin xizmatni "uyqiga"
yuboradi. Buning oldini olish uchun bu fayl kichik Flask veb-serverini ham
ishga tushiradi (health-check uchun) — Render bergan URL'ni UptimeRobot
kabi xizmat orqali har 5 daqiqada "ping" qilib turing, shunda bot doim
faol qoladi.

FINTEL_SELECTORS lug'atini haqiqiy sahifa HTML'iga qarab moslashtirish
kerak bo'lishi mumkin (Fintel ba'zi ma'lumotlarni faqat login qilganlarga
ko'rsatishi mumkin).
"""

import os
import re
import threading
import logging

import requests
from bs4 import BeautifulSoup
from flask import Flask

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", 10000))  # Render avtomatik PORT beradi

FINTEL_URL_TEMPLATE = "https://fintel.io/ss/us/{ticker}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# --- Haqiqiy Fintel sahifasiga qarab moslang (Inspect Element) ---
FINTEL_SELECTORS = {
    "short_interest": "td#short-interest-percent",
    "borrow_fee": "td#borrow-fee",
    "shares_available": "td#shares-available",
    "squeeze_score": "div#squeeze-score",
}

TICKER_PATTERN = re.compile(r"^#([A-Za-z]{1,6})$")


# ---------------------------------------------------------------------
# Fintel'dan ma'lumot olish
# ---------------------------------------------------------------------

def fetch_fintel_data(ticker: str) -> dict | None:
    url = FINTEL_URL_TEMPLATE.format(ticker=ticker.upper())
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
    except requests.RequestException as e:
        logger.error("So'rov xatoligi (%s): %s", ticker, e)
        return None

    if resp.status_code != 200:
        logger.warning("Fintel %s uchun status %s qaytardi", ticker, resp.status_code)
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    data = {}
    for key, selector in FINTEL_SELECTORS.items():
        el = soup.select_one(selector)
        data[key] = el.get_text(strip=True) if el else None

    if all(v is None for v in data.values()):
        return None
    return data


def format_reply(ticker: str, data: dict) -> str:
    def val(key):
        return data.get(key) or "Ma'lumot topilmadi"

    return (
        f"#{ticker.upper()}\n\n"
        f"📉 Short Interest: {val('short_interest')}\n"
        f"💰 Borrow Fee (CTB): {val('borrow_fee')}\n"
        f"📦 Shares Available: {val('shares_available')}\n"
        f"🔥 Short Squeeze Score: {val('squeeze_score')}"
    )


# ---------------------------------------------------------------------
# Telegram handler
# ---------------------------------------------------------------------

async def handle_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    match = TICKER_PATTERN.match(text)
    if not match:
        return

    ticker = match.group(1).upper()
    await update.message.reply_text(f"⏳ {ticker} tekshirilmoqda...")

    data = fetch_fintel_data(ticker)
    if data is None:
        await update.message.reply_text(
            f"❌ #{ticker} uchun ma'lumot topilmadi. Ticker noto'g'ri bo'lishi "
            f"yoki Fintel sahifasi login talab qilishi mumkin."
        )
        return

    await update.message.reply_text(format_reply(ticker, data))


def run_bot():
    """Telegram botni alohida thread'da uzluksiz ishga tushiradi."""
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticker))
    logger.info("Telegram bot ishga tushdi (polling)...")
    app.run_polling(stop_signals=None)


# ---------------------------------------------------------------------
# Flask — Render'ni "uyg'oq" ushlab turish uchun health-check server
# ---------------------------------------------------------------------

flask_app = Flask(__name__)


@flask_app.route("/")
def health_check():
    return "Fintel short interest bot ishlayapti ✅"


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN muhit o'zgaruvchisi topilmadi.")

    # Telegram botni alohida thread'da ishga tushiramiz,
    # asosiy thread esa Flask serverni ishga tushiradi (Render shuni kutadi).
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    logger.info("Flask server %s portda ishga tushdi...", PORT)
    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
