"""Bybit Demo Bot Telegram alerts.

No trading actions. Telegram delivery failures do not raise into trading code.
"""
import html
import os
import threading
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from utils.logger import logger

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

_lock = threading.Lock()
_sent = {}
DEDUP_SECONDS = 600


def esc(value):
    return html.escape(str(value), quote=True)


def money(value, digits=4):
    return f"{float(value):,.{digits}f}"


def send(text, event_key=None):
    """Return True only when Telegram confirms success.

    Duplicate suppression is per-process, not durable across restarts.
    """
    if not TOKEN or not CHAT_ID:
        logger.warning("[Telegram] Token or chat ID not configured")
        return False

    with _lock:
        now = time.monotonic()
        for key, timestamp in list(_sent.items()):
            if now - timestamp > DEDUP_SECONDS:
                del _sent[key]

        if event_key and event_key in _sent:
            logger.info("[Telegram] Duplicate alert suppressed")
            return True

        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        for attempt in range(2):
            try:
                response = requests.post(
                    BASE_URL,
                    json=payload,
                    timeout=(3, 7),
                )

                if response.status_code == 429 and attempt == 0:
                    try:
                        retry_after = int(
                            response.json()
                            .get("parameters", {})
                            .get("retry_after", 1)
                        )
                    except (ValueError, TypeError, KeyError):
                        retry_after = 1

                    time.sleep(min(max(retry_after, 1), 5))
                    continue

                response.raise_for_status()
                result = response.json()

                if result.get("ok") is not True:
                    logger.error(
                        "[Telegram] API rejected message"
                    )
                    return False

                if event_key:
                    _sent[event_key] = time.monotonic()

                return True

            except (requests.RequestException, ValueError) as exc:
                # Never blindly retry ambiguous network failures:
                # Telegram may already have delivered the message.
                logger.error(
                    "[Telegram] Delivery unconfirmed: %s",
                    type(exc).__name__,
                )
                return False

        return False


def alert_bot_started(symbols, timeframe):
    pairs = ", ".join(map(str, symbols))

    msg = (
        "🚀 <b>BYBIT DEMO BOT STARTED</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🪙 Symbols: <b>{esc(pairs)}</b>\n"
        f"⏱ Timeframe: <b>{esc(timeframe)}m</b>\n"
        "🔄 Mode: <b>DEMO Trading</b>\n"
        "📊 Strategy: EMA + RSI + MACD\n"
        "🤖 Bybit Demo Bot"
    )

    return send(msg, event_key="bot-start")


def alert_order_placed(symbol, side, price, qty, sl, tp, order_id=""):
    risk = abs(float(price) - float(sl)) * float(qty)
    reward = abs(float(tp) - float(price)) * float(qty)

    indicator = "🟢" if side == "Buy" else "🔴"

    msg = (
        f"{indicator} <b>ORDER FILLED</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📌 Symbol: <b>{esc(symbol)}</b>\n"
        f"📊 Side: <b>{esc(side)}</b>\n"
        f"📦 Filled Qty: <code>{money(qty, 8)}</code>\n"
        f"💵 Avg Entry: <code>${money(price)}</code>\n"
        f"🛑 Stop Loss: <code>${money(sl)}</code>\n"
        f"🎯 Take Profit: <code>${money(tp)}</code>\n"
        f"⚠️ Est. Risk: <code>${money(risk, 2)}</code>\n"
        f"💰 Est. Reward: <code>${money(reward, 2)}</code>\n"
        f"🔑 Order ID: <code>{esc(order_id)}</code>\n"
        "🤖 Bybit Demo Bot"
    )

    key = f"order:{order_id}" if order_id else None
    return send(msg, event_key=key)


def alert_trade_closed(
    symbol, side, entry, exit_price, qty, pnl, fees=0.0
):
    pnl_value = float(pnl)
    if pnl_value > 0:
        status = "✅ PROFIT"
    elif pnl_value < 0:
        status = "❌ LOSS"
    else:
        status = "➖ BREAKEVEN"

    msg = (
        f"🏁 <b>TRADE CLOSED — {status}</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📌 Symbol: <b>{esc(symbol)}</b>\n"
        f"📊 Entry Side: <b>{esc(side)}</b>\n"
        f"📦 Closed Qty: <code>{money(qty, 8)}</code>\n"
        f"💵 Avg Entry: <code>${money(entry)}</code>\n"
        f"💵 Avg Exit: <code>${money(exit_price)}</code>\n"
        f"💰 Bybit PnL: <b>{pnl_value:+.4f} USDT</b>\n"
        f"🧾 Fee Estimate Supplied: "
        f"<code>{money(fees, 6)} USDT</code>\n"
        "🤖 Bybit Demo Bot"
    )

    # Keep legitimate repeated trades; without a unique closing
    # execution ID, persistent deduplication would be unsafe.
    return send(msg)


def alert_signal(symbol, side, price, sl, tp, rsi, macd):
    indicator = "🟢" if side == "Buy" else "🔴"

    msg = (
        f"{indicator} <b>TRADING SIGNAL</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📌 Symbol: <b>{esc(symbol)}</b>\n"
        f"📊 Side: <b>{esc(side)}</b>\n"
        f"💵 Price: <code>${money(price)}</code>\n"
        f"🛑 SL: <code>${money(sl)}</code>\n"
        f"🎯 TP: <code>${money(tp)}</code>\n"
        f"📈 RSI: <code>{float(rsi):.2f}</code>\n"
        f"📉 MACD: <code>{float(macd):.4f}</code>"
    )

    return send(msg)


def alert_error(symbol, error):
    msg = (
        "🚨 <b>BOT ERROR</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📌 Symbol: <b>{esc(symbol)}</b>\n"
        f"⚠️ Error: <code>{esc(str(error)[:500])}</code>\n"
        "🤖 Bybit Demo Bot"
    )

    # Suppress bursts of the same error for ten minutes.
    # Do not include secret-bearing exception details in event keys.
    key = f"error:{symbol}:{type(error).__name__}"
    return send(msg, event_key=key)


def get_daily_summary():
    """Statistics grouped by trade ENTRY date (database timezone)."""
    from database import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    CURRENT_DATE AS day,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE side = 'Buy') AS buys,
                    COUNT(*) FILTER (WHERE side = 'Sell') AS sells,
                    COUNT(*) FILTER (WHERE status = 'WIN') AS wins,
                    COUNT(*) FILTER (WHERE status = 'LOSS') AS losses,
                    COALESCE(
                        SUM(pnl) FILTER (
                            WHERE status IN ('WIN', 'LOSS')
                        ), 0
                    ) AS pnl
                FROM trades
                WHERE time >= CURRENT_DATE
                  AND time < CURRENT_DATE + INTERVAL '1 day'
            """)
            return dict(cur.fetchone())


def alert_daily_summary():
    try:
        stats = get_daily_summary()
        day = str(stats["day"])

        msg = (
            "📊 <b>BYBIT DAILY SUMMARY</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            f"📅 Date: <b>{esc(day)}</b>\n"
            f"📦 Trades Entered: <b>{stats['total']}</b>\n"
            f"🟢 Buy: <b>{stats['buys']}</b>\n"
            f"🔴 Sell: <b>{stats['sells']}</b>\n"
            f"✅ Wins: <b>{stats['wins']}</b>\n"
            f"❌ Losses: <b>{stats['losses']}</b>\n"
            f"💰 PnL: <b>{float(stats['pnl']):+.4f} USDT</b>\n"
            "ℹ️ Based on today's trade entry date.\n"
            "🤖 Bybit Demo Bot"
        )

        return send(msg, event_key=f"summary:{day}")

    except Exception as exc:
        logger.error(
            "[Telegram] Daily summary unavailable: %s",
            type(exc).__name__,
        )
        return False


if __name__ == "__main__":
    print("Telegram alerts module loaded successfully")
    print("Configured:", bool(TOKEN and CHAT_ID))
    print("No message sent")
