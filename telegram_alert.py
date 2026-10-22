import os
import requests
from dotenv import load_dotenv
from utils.logger import logger

load_dotenv()

TOKEN    = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


def send(text: str):
    if not TOKEN or not CHAT_ID:
        return
    try:
        requests.post(BASE_URL, json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=5)
    except Exception as e:
        logger.error(f"[Telegram] send error: {e}")


def alert_bot_started(symbols, timeframe):
    msg = (
        f"🚀 <b>BYBIT BOT STARTED</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🪙 Symbols   : <b>{', '.join(symbols)}</b>\n"
        f"⏱ Timeframe : <b>{timeframe}m</b>\n"
        f"🔄 Mode      : <b>DEMO Trading</b>\n"
        f"📊 Strategy  : <b>EMA + RSI + MACD</b>\n"
        f"───────────────\n"
        f"🤖 Bybit Demo Bot"
    )
    send(msg)


def alert_order_placed(symbol, side, price, qty, sl, tp, order_id=""):
    emoji  = "🟢" if side == "Buy" else "🔴"
    s_text = "BUY  📈" if side == "Buy" else "SELL 📉"
    risk   = round(abs(price - sl) * qty, 4)
    reward = round(abs(tp - price) * qty, 4)
    msg = (
        f"{emoji} <b>BYBIT ENTRY CONFIRMED</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 Pair     : <b>{symbol}</b>\n"
        f"📊 Side     : <b>{s_text}</b>\n"
        f"📦 Quantity : <code>{qty:.4f}</code>\n"
        f"💵 Entry    : <code>${price:,.4f}</code>\n"
        f"🛑 Stop Loss: <code>${sl:,.4f}</code>\n"
        f"🎯 Take Prof: <code>${tp:,.4f}</code>\n"
        f"───────────────\n"
        f"⚠️ Risk     : <code>${risk}</code>\n"
        f"💰 Reward   : <code>${reward}</code>\n"
        f"🔑 Order ID : <code>{order_id}</code>\n"
        f"───────────────\n"
        f"🤖 Bybit Demo Bot"
    )
    send(msg)


def alert_trade_closed(symbol, side, entry, exit_price, qty, pnl, fees=0.0):
    status     = "PROFIT ✅" if pnl > 0 else "LOSS ❌"
    emoji      = "✅" if pnl > 0 else "❌"
    pnl_text   = f"+{pnl:.6f}" if pnl > 0 else f"{pnl:.6f}"
    close_side = "Buy" if side == "Sell" else "Sell"
    msg = (
        f"{emoji} <b>BYBIT EXIT CONFIRMED</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 Pair       : <b>{symbol}</b>\n"
        f"🔎 Status     : <b>{status}</b>\n"
        f"📊 Closed side: <b>{close_side}</b>\n"
        f"📦 Quantity   : <code>{qty:.4f}</code>\n"
        f"💵 Avg entry  : <code>{entry:,.4f}</code>\n"
        f"🏁 Avg exit   : <code>{exit_price:,.4f}</code>\n"
        f"💰 Net P&L    : <b>{pnl_text} USDT</b>\n"
        f"🧾 Est. Fees  : <code>{fees:.6f} USDT</code>\n"
        f"───────────────\n"
        f"➡️ Recorded in Journal\n"
        f"🤖 Bybit Demo Bot"
    )
    send(msg)


def alert_signal(symbol, side, price, sl, tp, rsi, macd):
    emoji  = "🟢" if side == "Buy" else "🔴"
    s_text = "BUY 📈" if side == "Buy" else "SELL 📉"
    msg = (
        f"{emoji} <b>SIGNAL: {s_text}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🪙 Symbol : <b>{symbol}</b>\n"
        f"💰 Price  : <code>${price:,.4f}</code>\n"
        f"🛑 SL     : <code>${sl:,.4f}</code>\n"
        f"🎯 TP     : <code>${tp:,.4f}</code>\n"
        f"───────────────\n"
        f"📊 RSI    : <code>{rsi:.2f}</code>\n"
        f"📉 MACD   : <code>{macd:.4f}</code>\n"
        f"🤖 Bybit Demo Bot"
    )
    send(msg)


def alert_error(symbol, error):
    msg = (
        f"⚠️ <b>BOT ERROR!</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🪙 Symbol : <b>{symbol}</b>\n"
        f"❌ Error  : <code>{str(error)[:200]}</code>\n"
        f"🤖 Bybit Demo Bot"
    )
    send(msg)