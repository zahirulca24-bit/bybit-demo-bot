import time
import threading
import uvicorn

from config.settings import SYMBOLS, TIMEFRAME, MAX_OPEN_TRADES
from core.market_data import MarketData
from core.strategy import Strategy
from core.risk_manager import RiskManager
from core.order_executor import OrderExecutor
from dashboard.app import app
from dashboard.state import bot_state
from database import init_db, insert_trade, close_trade, get_all_trades
from telegram_alert import alert_bot_started, alert_order_placed, alert_trade_closed, alert_error
from utils.logger import logger

# Symbol → open trade tracking
open_trades: dict = {}


def check_position_closed(symbol, executor, current_pos):
    """আগে Position ছিল, এখন নেই → Trade Close হয়েছে।"""
    if symbol not in open_trades:
        return
    if current_pos is not None:
        return

    trade = open_trades.pop(symbol)
    try:
        # Trade History থেকে Exit Price ও PnL নেওয়া
        history = executor.session.get_closed_pnl(
            category="linear", symbol=symbol, limit=1
        )
        if history["retCode"] == 0 and history["result"]["list"]:
            h = history["result"]["list"][0]
            exit_price = float(h.get("avgExitPrice", 0))
            pnl        = float(h.get("closedPnl", 0))
            qty        = float(h.get("qty", trade.get("qty", 0)))
            fees       = abs(pnl) * 0.00055 * 2  # est. taker fee
        else:
            exit_price = 0.0
            pnl        = 0.0
            qty        = trade.get("qty", 0)
            fees       = 0.0

        # DB Update
        if trade.get("db_id"):
            close_trade(trade["db_id"], exit_price, pnl)

        # Telegram Exit Alert
        alert_trade_closed(
            symbol=symbol,
            side=trade["side"],
            entry=trade["entry_price"],
            exit_price=exit_price,
            qty=qty,
            pnl=pnl,
            fees=fees,
        )
        logger.info(f"[{symbol}] Position closed | PnL={pnl}")
    except Exception as e:
        logger.error(f"[{symbol}] check_position_closed error: {e}")


def process_symbol(symbol, market, executor, strategy, risk, last_candle):
    df = market.get_candles()
    if df is None or df.empty:
        return

    price = market.get_current_price() or 0.0
    pos   = executor.get_open_position()

    # Exit Detection
    check_position_closed(symbol, executor, pos)

    closed_time = df.iloc[-1]["timestamp"]
    same_candle = closed_time == last_candle.get(symbol)

    df_ind = strategy.calculate_indicators(df).dropna()
    if not df_ind.empty:
        curr = df_ind.iloc[-1]
        bot_state.update_symbol(symbol,
            price=price,
            ema_fast=curr["ema_fast"],
            ema_slow=curr["ema_slow"],
            rsi=curr["rsi"],
            macd=round(curr.get("macd", 0), 4),
            macd_signal=round(curr.get("macd_signal", 0), 4),
            macd_hist=round(curr.get("macd_hist", 0), 4),
            has_position=pos is not None,
            position_side=pos["side"] if pos else "",
            position_size=float(pos["size"]) if pos else 0.0,
            unrealized_pnl=float(pos.get("unrealisedPnl", 0)) if pos else 0.0,
        )

    if same_candle:
        return

    last_candle[symbol] = closed_time
    logger.info(f"[{symbol}] New closed candle: {closed_time}")

    if not df_ind.empty:
        curr   = df_ind.iloc[-1]
        signal = strategy.get_signal(df, symbol)
        bot_state.update_symbol(symbol, signal=signal)

        if signal == "HOLD":
            return
        if pos is not None:
            logger.info(f"[{symbol}] Signal {signal} ignored: position open")
            return

        open_count = executor.count_open_positions()
        if open_count is None or not risk.can_trade(open_count):
            return

        side   = "Buy" if signal == "BUY" else "Sell"
        levels = risk.calculate_levels(price, side)
        result = executor.place_market_order(levels)

        if result:
            order_id = result.get("orderId", "")

            # DB Insert
            db_id = insert_trade(
                symbol=symbol, side=side,
                entry_price=price, qty=levels["quantity"],
                stop_loss=levels["stop_loss"],
                take_profit=levels["take_profit"],
                order_id=order_id,
            )

            # Track করো
            open_trades[symbol] = {
                "db_id":       db_id,
                "side":        side,
                "entry_price": price,
                "qty":         levels["quantity"],
            }

            # In-memory
            bot_state.add_trade(
                symbol, side, price,
                levels["quantity"],
                levels["stop_loss"],
                levels["take_profit"],
            )

            # Telegram Entry Alert
            alert_order_placed(
                symbol=symbol, side=side, price=price,
                qty=levels["quantity"],
                sl=levels["stop_loss"],
                tp=levels["take_profit"],
                order_id=order_id,
            )


def bot_loop():
    init_db()

    strategy = Strategy()
    risk     = RiskManager()
    markets, executors = {}, {}

    for symbol in SYMBOLS:
        ex = OrderExecutor(symbol)
        if not ex.ready:
            continue
        markets[symbol]   = MarketData(symbol)
        executors[symbol] = ex

    if not executors:
        logger.error("No valid symbols")
        return

    active = list(executors.keys())
    bot_state.running    = True
    bot_state.started_at = time.time()

    # DB থেকে আগের Trade Load
    try:
        db_trades = get_all_trades(limit=50)
        for t in reversed(db_trades):
            bot_state.trade_log.insert(0, {
                "time":   str(t["time"])[:19],
                "symbol": t["symbol"],
                "side":   t["side"],
                "price":  float(t["entry_price"]),
                "qty":    float(t["qty"]),
                "sl":     float(t["stop_loss"] or 0),
                "tp":     float(t["take_profit"] or 0),
                "status": t["status"],
                "pnl":    float(t["pnl"]) if t["pnl"] else None,
            })
        logger.info(f"Loaded {len(db_trades)} trades from DB")
    except Exception as e:
        logger.error(f"Trade load error: {e}")

    # Telegram Start Alert
    alert_bot_started(active, TIMEFRAME)
    logger.info(f"Bot started | {', '.join(active)} | {TIMEFRAME}m | DEMO")

    last_candle = {}
    while True:
        try:
            for symbol in active:
                try:
                    process_symbol(
                        symbol, markets[symbol],
                        executors[symbol],
                        strategy, risk, last_candle,
                    )
                except Exception as e:
                    logger.error(f"[{symbol}] Error: {e}")
                    alert_error(symbol, e)
                time.sleep(0.5)
            time.sleep(15)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(30)

    bot_state.running = False


if __name__ == "__main__":
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")