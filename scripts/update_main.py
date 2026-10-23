import pathlib

code = '''import time, threading
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
from scanner import MarketScanner

open_trades = {}

def check_closed(symbol, executor, pos):
    if symbol not in open_trades or pos is not None: return
    trade = open_trades.pop(symbol)
    try:
        h = executor.session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
        if h["retCode"] == 0 and h["result"]["list"]:
            rec = h["result"]["list"][0]
            exit_price = float(rec.get("avgExitPrice", 0))
            pnl = float(rec.get("closedPnl", 0))
            qty = float(rec.get("qty", trade.get("qty", 0)))
        else:
            exit_price = pnl = 0.0
            qty = trade.get("qty", 0)
        if trade.get("db_id"): close_trade(trade["db_id"], exit_price, pnl)
        alert_trade_closed(symbol=symbol, side=trade["side"], entry=trade["entry_price"], exit_price=exit_price, qty=qty, pnl=pnl, fees=abs(pnl)*0.00055*2)
        logger.info(f"[{symbol}] Closed PnL={pnl}")
    except Exception as e: logger.error(f"[{symbol}] close_check:{e}")

def process_symbol(symbol, market, executor, strategy, risk, last_candle):
    ticker = market.get_ticker_24h()
    price = ticker["price"]
    chg = ticker["change_pct"]
    pos = executor.get_open_position()
    check_closed(symbol, executor, pos)
    df = market.get_candles()
    if df is None or df.empty: return
    closed_time = df.iloc[-1]["timestamp"]
    same = closed_time == last_candle.get(symbol)
    df_ind = strategy.calculate_indicators(df).dropna()
    if not df_ind.empty:
        curr = df_ind.iloc[-1]
        bot_state.update_symbol(symbol, price=price, price_change_pct=chg, ema_fast=curr["ema_fast"], ema_slow=curr["ema_slow"], rsi=curr["rsi"], macd=round(float(curr.get("macd", 0)), 4), macd_signal=round(float(curr.get("macd_signal", 0)), 4), macd_hist=round(float(curr.get("macd_hist", 0)), 4), has_position=pos is not None, position_side=pos["side"] if pos else "", position_size=float(pos["size"]) if pos else 0.0, unrealized_pnl=float(pos.get("unrealisedPnl", 0)) if pos else 0.0)
    if same: return
    last_candle[symbol] = closed_time
    logger.info(f"[{symbol}] New candle: {closed_time}")
    if df_ind.empty: return
    curr = df_ind.iloc[-1]
    signal = strategy.get_signal(df, symbol)
    bot_state.update_symbol(symbol, signal=signal)
    rsi_v = float(curr["rsi"])
    macd_v = float(curr.get("macd", 0))
    if signal != "HOLD":
        open_count = executor.count_open_positions() or 0
        has_pos = pos is not None
        if has_pos:
            reason = "Already has open position"
            bot_state.add_signal(symbol, signal, price, rsi_v, macd_v, traded=False, reason=reason)
            return
        if not risk.can_trade(open_count):
            reason = f"Max open trades reached ({open_count}/{MAX_OPEN_TRADES})"
            bot_state.add_signal(symbol, signal, price, rsi_v, macd_v, traded=False, reason=reason)
            return
        side = "Buy" if signal == "BUY" else "Sell"
        levels = risk.calculate_levels(price, side)
        result = executor.place_market_order(levels)
        if result:
            order_id = result.get("orderId", "")
            db_id = insert_trade(symbol=symbol, side=side, entry_price=price, qty=levels["quantity"], stop_loss=levels["stop_loss"], take_profit=levels["take_profit"], order_id=order_id)
            open_trades[symbol] = {"db_id": db_id, "side": side, "entry_price": price, "qty": levels["quantity"]}
            bot_state.add_trade(symbol, side, price, levels["quantity"], levels["stop_loss"], levels["take_profit"])
            bot_state.add_signal(symbol, signal, price, rsi_v, macd_v, traded=True, reason=f"Order placed: {order_id}")
            alert_order_placed(symbol=symbol, side=side, price=price, qty=levels["quantity"], sl=levels["stop_loss"], tp=levels["take_profit"], order_id=order_id)
        else:
            bot_state.add_signal(symbol, signal, price, rsi_v, macd_v, traded=False, reason="Order placement failed")

def bot_loop():
    init_db()
    strategy = Strategy()
    risk = RiskManager()
    markets, executors = {}, {}
    for sym in SYMBOLS:
        ex = OrderExecutor(sym)
        if not ex.ready: continue
        markets[sym] = MarketData(sym)
        executors[sym] = ex
    if not executors:
        logger.error("No valid symbols found.")
        return
    bot_state.running = True
    bot_state.started_at = time.time()
    try: bot_state.balance_usdt = list(markets.values())[0].get_balance()
    except: pass
    try:
        for t in reversed(get_all_trades(limit=50)):
            bot_state.trade_log.insert(0, {"time": str(t["time"])[:19], "symbol": t["symbol"], "side": t["side"], "price": float(t["entry_price"]), "qty": float(t["qty"]), "sl": float(t["stop_loss"] or 0), "tp": float(t["take_profit"] or 0), "status": t["status"], "pnl": float(t["pnl"]) if t["pnl"] else None})
    except Exception as e: logger.error(f"Trade load: {e}")
    alert_bot_started(list(executors.keys()), TIMEFRAME)
    logger.info(f"Bot started | {TIMEFRAME}m | DEMO")

    scanner = MarketScanner()
    last_candle = {}
    loop = 0
    dynamic_symbols = list(SYMBOLS)

    while True:
        try:
            current_time = int(time.time())
            candle_time = (current_time // (15 * 60)) * (15 * 60)
            if loop == 0 or candle_time != last_candle.get("_scan_time"):
                last_candle["_scan_time"] = candle_time
                logger.info("Running Auto-Scanner (every 15m)...")
                try:
                    scan_result = scanner.run(limit=20)
                    bot_state.last_scan = scan_result
                    top_symbols = [r["symbol"] for r in scan_result["results"] if r["selected"]]
                    if top_symbols:
                        dynamic_symbols = top_symbols[:5]
                        logger.info(f"Auto-Scanner selected: {dynamic_symbols}")
                        for sym in dynamic_symbols:
                            if sym not in executors:
                                ex = OrderExecutor(sym)
                                if ex.ready:
                                    markets[sym] = MarketData(sym)
                                    executors[sym] = ex
                    else:
                        logger.info("No best symbols found. Waiting for next candle...")
                except Exception as e:
                    logger.error(f"Auto-Scan Error: {e}")

            active_to_trade = [s for s in dynamic_symbols if s in executors]
            for sym in active_to_trade:
                try: process_symbol(sym, markets[sym], executors[sym], strategy, risk, last_candle)
                except Exception as e:
                    logger.error(f"[{sym}] Error: {e}")
                    alert_error(sym, e)
                time.sleep(0.5)
            loop += 1
            if loop % 10 == 0:
                try: bot_state.balance_usdt = list(markets.values())[0].get_balance()
                except: pass
            time.sleep(15)
        except KeyboardInterrupt: break
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(30)
    bot_state.running = False

if __name__ == "__main__":
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
'''

pathlib.Path('main.py').write_text(code.strip(), encoding='utf-8')
print('\n[SUCCESS] main.py updated successfully! Now stop the bot and run: python main.py\n')
