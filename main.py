import time, threading, os
from typing import Any, cast
from decimal import Decimal
import uvicorn
from config.settings import SYMBOLS, TIMEFRAME, MAX_OPEN_TRADES
from core.market_data import MarketData
from core.strategy import Strategy
from core.risk_manager import RiskManager
from core.order_executor import OrderExecutor
from dashboard.app import app
from dashboard.state import bot_state
from database import init_db, insert_trade, get_all_trades, get_conn
from telegram_alert import alert_bot_started, alert_order_placed, alert_trade_closed, alert_error
from utils.logger import logger
from scanner import MarketScanner
from core.trading_guard import (
    acquire_bot_lock,
    assert_bot_lock,
    initialize_intents,
    reserve_order,
    mark_order,
    pending_symbols,
)


open_trades = {}
blocked_symbols = set()
trading_lock = None


def preflight_trade(symbol):
    # Fail closed if startup lock is missing or its DB session is lost.
    assert_bot_lock(trading_lock)

    # Never place a new order for an existing Neon OPEN trade.
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''
                SELECT id FROM trades
                WHERE symbol = %s AND status = 'OPEN'
                LIMIT 1
                ''',
                (symbol,),
            )
            if cur.fetchone() is not None:
                raise RuntimeError(
                    f"{symbol}: OPEN Neon trade already exists"
                )

    # Include persistent unresolved order intents.
    if symbol in pending_symbols():
        raise RuntimeError(
            f"{symbol}: unresolved order intent exists"
        )

    return True


def recover_open_trades():
    """Read all OPEN trade records from Neon, without changing them."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, time, symbol, side, entry_price, qty
                FROM trades
                WHERE status = 'OPEN'
                ORDER BY time DESC, id DESC
            """)
            rows = [dict(r) for r in cur.fetchall()]

    recovered = {}
    for row in rows:
        symbol = row["symbol"]

        if symbol in recovered:
            blocked_symbols.add(symbol)
            logger.error(
                f"[{symbol}] Multiple OPEN database trades. "
                "Trading blocked pending manual reconciliation."
            )
            continue

        recovered[symbol] = {
            "db_id": row["id"],
            "side": row["side"],
            "entry_price": float(row["entry_price"]),
            "qty": float(row["qty"]),
            "opened_at": row["time"],
        }

    logger.info(f"Recovered {len(recovered)} OPEN trades from Neon")
    return recovered


def confirmed_fill(executor, order_id, side):
    """Return confirmed (qty, avg_price) or None; never guess a fill."""
    for attempt in range(8):
        if attempt:
            time.sleep(1)

        try:
            response = executor.session.get_order_history(
                category="linear",
                symbol=executor.symbol,
                orderId=order_id,
            )

            if response.get("retCode") != 0:
                logger.warning(
                    f"[{executor.symbol}] Fill lookup failed: "
                    f"{response.get('retMsg')}"
                )
                continue

            orders = [
                order
                for order in response.get("result", {}).get("list", [])
                if order.get("orderId") == order_id
            ]

            if len(orders) != 1:
                continue

            order = orders[0]

            if (
                order.get("symbol") != executor.symbol
                or order.get("side") != side
            ):
                raise RuntimeError("Opening order identity mismatch")

            if order.get("orderStatus") != "Filled":
                continue

            qty = Decimal(str(order.get("cumExecQty", "0")))
            avg = Decimal(str(order.get("avgPrice") or "0"))

            if (
                qty.is_finite() and qty > 0
                and avg.is_finite() and avg > 0
            ):
                return float(qty), float(avg)

        except Exception as exc:
            logger.error(
                f"[{executor.symbol}] Fill verification: {exc}"
            )

    return None


def check_closed(symbol, executor, pos):
    """Close a DB row only on a uniquely matched Bybit closed-PnL record."""
    if symbol not in open_trades or pos is not None:
        return

    trade = open_trades[symbol]

    try:
        # Bybit closed-PnL may include older or partial closes.
        # A symbol-only latest-record lookup is not safe.
        response = executor.session.get_closed_pnl(
            category="linear",
            symbol=symbol,
            limit=50,
        )

        if response.get("retCode") != 0:
            raise RuntimeError(response.get("retMsg"))

        matches = []

        opened_ms = int(
            trade["opened_at"].timestamp() * 1000
        ) if trade.get("opened_at") else 0

        for rec in response.get("result", {}).get("list", []):
            try:
                created_ms = int(rec.get("createdTime", 0))
                closed_qty = Decimal(
                    str(rec.get("closedSize", "0"))
                )
                entry = Decimal(
                    str(rec.get("avgEntryPrice", "0"))
                )
                actual_entry = Decimal(
                    str(trade["entry_price"])
                )
                expected_qty = Decimal(str(trade["qty"]))

                if created_ms < opened_ms:
                    continue

                if abs(closed_qty - expected_qty) > Decimal("0.00000001"):
                    continue

                if actual_entry <= 0:
                    continue

                # Protect against unrelated closes of same symbol.
                if abs(entry - actual_entry) / actual_entry > Decimal("0.001"):
                    continue

                if rec.get("side") != trade["side"]:
                    continue

                exit_price = Decimal(
                    str(rec.get("avgExitPrice", "0"))
                )
                pnl = Decimal(str(rec.get("closedPnl", "NaN")))

                if not (
                    exit_price.is_finite() and exit_price > 0
                    and pnl.is_finite()
                ):
                    continue

                matches.append((rec, exit_price, pnl))
            except (ValueError, TypeError, ArithmeticError):
                continue

        if len(matches) != 1:
            blocked_symbols.add(symbol)
            logger.warning(
                f"[{symbol}] Flat on Bybit but {len(matches)} "
                "matching close records. DB left OPEN; "
                "manual reconciliation required."
            )
            return

        rec, exit_price, pnl = matches[0]

        # Guard against concurrent changes to this trade.
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE trades
                    SET exit_price = %s,
                        pnl = %s,
                        status = %s
                    WHERE id = %s
                      AND symbol = %s
                      AND status = 'OPEN'
                      AND qty = %s
                    RETURNING id
                """, (
                    exit_price,
                    pnl,
                    "WIN" if pnl > 0 else "LOSS",
                    trade["db_id"],
                    symbol,
                    trade["qty"],
                ))
                updated = cur.fetchone()

                if updated is None:
                    raise RuntimeError(
                        "Trade changed concurrently; not closing"
                    )

            conn.commit()

        open_trades.pop(symbol, None)
        blocked_symbols.discard(symbol)

        alert_trade_closed(
            symbol=symbol,
            side=trade["side"],
            entry=trade["entry_price"],
            exit_price=float(exit_price),
            qty=trade["qty"],
            pnl=float(pnl),
            fees=0,
        )

        logger.info(
            f"[{symbol}] Verified close: "
            f"trade_id={trade['db_id']} pnl={pnl}"
        )

    except Exception as exc:
        blocked_symbols.add(symbol)
        logger.error(f"[{symbol}] Close verification: {exc}")

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
        if symbol in blocked_symbols or symbol in open_trades:
            bot_state.add_signal(
                symbol, signal, price, rsi_v, macd_v,
                traded=False,
                reason="Existing trade or unresolved order"
            )
            return

        # Database outages must not allow new orders.
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
        except Exception as exc:
            logger.error(f"[{symbol}] DB unavailable: {exc}")
            return
        open_count = executor.count_open_positions()

        if open_count is None:
            logger.error(
                f"[{symbol}] Position count unavailable. "
                "Skipping trade for safety."
            )
            bot_state.add_signal(
                symbol, signal, price, rsi_v, macd_v,
                traded=False,
                reason="Bybit position count unavailable"
            )
            return

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
        try:
            preflight_trade(symbol)
            intent_id = reserve_order(symbol, side)
        except Exception as exc:
            blocked_symbols.add(symbol)
            logger.error(
                f"[{symbol}] Order reservation failed: {exc}"
            )
            return

        # If API submission times out, the intent remains pending.
        # This prevents automatic duplicate submission.
        blocked_symbols.add(symbol)
        try:
            # One final lock check immediately before submission.
            assert_bot_lock(trading_lock)
            result = executor.place_market_order(
                levels, order_link_id=intent_id
            )
        except Exception as exc:
            logger.critical(
                f"[{symbol}] Order state uncertain: {exc}"
            )
            result = None

        if result is None:
            # API errors/timeouts cannot prove non-execution.
            # Keep the symbol blocked until reconciliation.
            try:
                mark_order(intent_id, "UNCERTAIN")
            except Exception as exc:
                logger.critical(
                    f"[{symbol}] Could not update intent: {exc}"
                )

        if result:
            mark_order(
                intent_id,
                "ACKNOWLEDGED",
                result.get("orderId"),
            )
            order_id = result.get("orderId", "")
            blocked_symbols.add(symbol)

            if not order_id:
                logger.error(
                    f"[{symbol}] Order accepted without orderId. "
                    "Trading blocked."
                )
                return

            fill = confirmed_fill(executor, order_id, side)

            if fill is None:
                logger.error(
                    f"[{symbol}] Order {order_id} not yet confirmed. "
                    "Trading blocked; investigate before restarting."
                )
                bot_state.add_signal(
                    symbol, signal, price, rsi_v, macd_v,
                    traded=False,
                    reason="Order accepted; fill unconfirmed"
                )
                return

            filled_qty, filled_price = fill

            mark_order(
                intent_id,
                "FILLED_UNSAVED",
                order_id,
            )

            db_id = insert_trade(
                symbol=symbol,
                side=side,
                entry_price=filled_price,
                qty=filled_qty,
                stop_loss=levels["stop_loss"],
                take_profit=levels["take_profit"],
                order_id=order_id,
            )

            if db_id is None:
                logger.critical(
                    f"[{symbol}] ORDER FILLED but DB insert failed! "
                    f"orderId={order_id}; manual recovery required."
                )
                return

            # Store UTC-naive time consistently with database NOW().
            from datetime import datetime, timezone
            opened_at = datetime.now(timezone.utc).replace(tzinfo=None)

            open_trades[symbol] = {
                "db_id": db_id,
                "side": side,
                "entry_price": filled_price,
                "qty": filled_qty,
                "opened_at": opened_at,
            }

            mark_order(
                intent_id,
                "RECORDED",
                order_id,
            )
            blocked_symbols.discard(symbol)

            bot_state.add_trade(
                symbol, side, filled_price, filled_qty,
                levels["stop_loss"], levels["take_profit"]
            )
            bot_state.add_signal(
                symbol, signal, price, rsi_v, macd_v,
                traded=True,
                reason=f"Filled order: {order_id}"
            )
            alert_order_placed(
                symbol=symbol,
                side=side,
                price=filled_price,
                qty=filled_qty,
                sl=levels["stop_loss"],
                tp=levels["take_profit"],
                order_id=order_id,
            )
        else:
            bot_state.add_signal(symbol, signal, price, rsi_v, macd_v, traded=False, reason="Order placement failed")

def bot_loop():
    global trading_lock
    try:
        trading_lock = acquire_bot_lock()
        if trading_lock is None:
            logger.critical(
                "Another bot instance holds the Neon trading lock. "
                "Trading disabled in this instance."
            )
            return

        initialize_intents()
        from core.pending_order_recovery import recover_recorded_intents
        recover_recorded_intents()
        blocked_symbols.update(pending_symbols())

        if blocked_symbols:
            logger.warning(
                f"Unresolved order intents: {blocked_symbols}. "
                "Those symbols are blocked from new trades."
            )

    except Exception as exc:
        logger.critical(f"Trading startup blocked: {exc}")
        return

    init_db()

    # A DB failure must stop startup, not permit blind trading.
    try:
        recovered = recover_open_trades()
    except Exception as exc:
        logger.critical(f"Startup recovery failed: {exc}")
        bot_state.running = False
        return

    open_trades.update(recovered)
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
            trade = cast(dict[str, Any], t)
            bot_state.trade_log.insert(0, {"time": str(trade["time"])[:19], "symbol": trade["symbol"], "side": trade["side"], "price": float(trade["entry_price"]), "qty": float(trade["qty"]), "sl": float(trade["stop_loss"] or 0), "tp": float(trade["take_profit"] or 0), "status": trade["status"], "pnl": float(trade["pnl"]) if trade["pnl"] else None})
    except Exception as e: logger.error(f"Trade load: {e}")
    alert_bot_started(list(executors.keys()), TIMEFRAME)
    logger.info(f"Bot started | {TIMEFRAME}m | DEMO")
    
    # Include recovered trade symbols, even if scanner excludes them.
    for sym in open_trades:
        if sym not in executors:
            ex = OrderExecutor(sym)
            if ex.ready:
                executors[sym] = ex
                markets[sym] = MarketData(sym)
            else:
                blocked_symbols.add(sym)
                logger.error(
                    f"[{sym}] Recovered trade lacks ready executor"
                )

    scanner = MarketScanner()
    last_candle = {}
    loop = 0
    dynamic_symbols = list(SYMBOLS)
    
    while True:
        try:
            assert_bot_lock(trading_lock)
        except Exception as exc:
            logger.critical(
                f"Trading lock lost. Stopping bot: {exc}"
            )
            bot_state.running = False
            return

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
            
            # Monitor existing trades even after scanner deselects them.
            for sym in list(open_trades):
                if sym not in executors:
                    continue
                if sym in dynamic_symbols:
                    continue
                try:
                    ex = executors[sym]
                    pos = ex.get_open_position()
                    check_closed(sym, ex, pos)
                    bot_state.update_symbol(
                        sym,
                        has_position=pos is not None,
                        position_side=pos["side"] if pos else "",
                        position_size=float(pos["size"]) if pos else 0.0,
                        unrealized_pnl=float(
                            pos.get("unrealisedPnl", 0)
                        ) if pos else 0.0,
                    )
                except Exception as exc:
                    logger.error(
                        f"[{sym}] Recovered position monitor: {exc}"
                    )

            active_to_trade = [
                s for s in dynamic_symbols if s in executors
            ]
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
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8001")), log_level="warning")