#!/usr/bin/env python3
"""Run: python update_frontend.py"""
import pathlib

def w(path, txt):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt.strip(), encoding='utf-8')
    print(f'  OK  {path}')

print('Updating all files...\n')

w('dashboard/state.py', """
from dataclasses import dataclass, field
from typing import Dict, List
import time, json, os

TRADE_LOG_FILE = "logs/trade_log.json"

def _load_trades():
    try:
        if os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_trades(trades):
    try:
        os.makedirs("logs", exist_ok=True)
        with open(TRADE_LOG_FILE, "w") as f:
            json.dump(trades, f, indent=2)
    except Exception:
        pass

@dataclass
class SymbolState:
    symbol: str = ""
    price: float = 0.0
    price_change_pct: float = 0.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    rsi: float = 0.0
    signal: str = "HOLD"
    has_position: bool = False
    position_side: str = ""
    position_size: float = 0.0
    unrealized_pnl: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    updated_at: float = 0.0

@dataclass
class BotState:
    running: bool = False
    started_at: float = 0.0
    balance_usdt: float = 0.0
    symbols: Dict[str, SymbolState] = field(default_factory=dict)
    trade_log: List[dict] = field(default_factory=_load_trades)
    signal_history: List[dict] = field(default_factory=list)

    def update_symbol(self, symbol, **kwargs):
        if symbol not in self.symbols:
            self.symbols[symbol] = SymbolState(symbol=symbol)
        s = self.symbols[symbol]
        for k, v in kwargs.items():
            if hasattr(s, k):
                setattr(s, k, v)
        s.updated_at = time.time()

    def add_trade(self, symbol, side, price, qty, sl, tp):
        self.trade_log.insert(0, {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol, "side": side,
            "price": price, "qty": qty, "sl": sl, "tp": tp,
        })
        if len(self.trade_log) > 100:
            self.trade_log.pop()
        _save_trades(self.trade_log)

    def add_signal(self, symbol, signal, price, rsi, macd):
        self.signal_history.insert(0, {
            "time": time.strftime("%H:%M:%S"),
            "symbol": symbol, "signal": signal,
            "price": price, "rsi": round(rsi, 2), "macd": round(macd, 4),
        })
        if len(self.signal_history) > 100:
            self.signal_history.pop()

bot_state = BotState()
""")

w('core/market_data.py', """
import pandas as pd
from pybit.unified_trading import HTTP
from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET, SYMBOL, TIMEFRAME
from utils.logger import logger

class MarketData:
    def __init__(self, symbol: str = SYMBOL):
        self.session = HTTP(testnet=TESTNET, demo=DEMO_MODE,
                            api_key=API_KEY, api_secret=API_SECRET)
        self.symbol = symbol
        self.timeframe = TIMEFRAME

    def get_candles(self, limit=100):
        try:
            r = self.session.get_kline(category="linear", symbol=self.symbol,
                                       interval=self.timeframe, limit=limit)
            if r["retCode"] != 0:
                logger.error(f"Candle error: {r['retMsg']}")
                return None
            df = pd.DataFrame(r["result"]["list"],
                              columns=["timestamp","open","high","low","close","volume","turnover"])
            df = df.astype({"timestamp":"int64","open":"float64","high":"float64",
                            "low":"float64","close":"float64","volume":"float64"})
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df.sort_values("timestamp").reset_index(drop=True)
        except Exception as e:
            logger.error(f"get_candles: {e}")
            return None

    def get_current_price(self):
        try:
            t = self.session.get_tickers(category="linear", symbol=self.symbol)
            return float(t["result"]["list"][0]["lastPrice"])
        except Exception as e:
            logger.error(f"get_current_price: {e}")
            return None

    def get_ticker_24h(self):
        try:
            t = self.session.get_tickers(category="linear", symbol=self.symbol)
            d = t["result"]["list"][0]
            return {
                "price": float(d["lastPrice"]),
                "change_pct": round(float(d.get("price24hPcnt", 0)) * 100, 2),
            }
        except Exception as e:
            logger.error(f"get_ticker_24h: {e}")
            return {"price": 0.0, "change_pct": 0.0}

    def get_balance(self):
        try:
            r = self.session.get_wallet_balance(accountType="UNIFIED")
            if r["retCode"] == 0:
                for c in r["result"]["list"][0]["coin"]:
                    if c["coin"] == "USDT":
                        return float(c["walletBalance"])
            return 0.0
        except Exception as e:
            logger.error(f"get_balance: {e}")
            return 0.0
""")

w('dashboard/app.py', """
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os, time

from dashboard.state import bot_state
from database import get_all_trades, get_journal_stats, get_symbol_stats

app = FastAPI(title="Bybit Demo Bot")
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/api/status")
def get_status():
    syms = {}
    for sym, s in bot_state.symbols.items():
        syms[sym] = {
            "symbol": s.symbol, "price": s.price,
            "price_change_pct": round(s.price_change_pct, 2),
            "ema_fast": round(s.ema_fast, 4), "ema_slow": round(s.ema_slow, 4),
            "rsi": round(s.rsi, 2), "signal": s.signal,
            "has_position": s.has_position, "position_side": s.position_side,
            "position_size": s.position_size, "unrealized_pnl": s.unrealized_pnl,
            "macd": round(s.macd, 4), "macd_signal": round(s.macd_signal, 4),
            "macd_hist": round(s.macd_hist, 4),
        }
    return {
        "running": bot_state.running,
        "uptime": int(time.time() - bot_state.started_at) if bot_state.running else 0,
        "balance_usdt": round(bot_state.balance_usdt, 2),
        "symbols": syms,
        "trade_log": bot_state.trade_log[:20],
        "signal_history": bot_state.signal_history[:50],
    }

@app.get("/api/journal")
def get_journal():
    stats = get_journal_stats()
    win_rate = 0
    if stats.get("total_trades", 0) > 0:
        win_rate = round(stats["wins"] / stats["total_trades"] * 100, 1)
    return {
        "stats": {
            "total_trades": stats.get("total_trades", 0),
            "wins": stats.get("wins", 0), "losses": stats.get("losses", 0),
            "win_rate": win_rate, "total_pnl": float(stats.get("total_pnl", 0)),
            "best_trade": float(stats.get("best_trade", 0)),
            "worst_trade": float(stats.get("worst_trade", 0)),
            "avg_pnl": float(stats.get("avg_pnl", 0)),
        },
        "symbol_stats": get_symbol_stats(),
        "trades": [{
            "id": t["id"], "time": str(t["time"])[:19],
            "symbol": t["symbol"], "side": t["side"],
            "entry_price": float(t["entry_price"]), "qty": float(t["qty"]),
            "sl": float(t["stop_loss"] or 0), "tp": float(t["take_profit"] or 0),
            "exit_price": float(t["exit_price"]) if t["exit_price"] else None,
            "pnl": float(t["pnl"]) if t["pnl"] else None,
            "status": t["status"],
        } for t in get_all_trades(limit=100)],
    }
""")

w('main.py', """
import time, threading
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

open_trades: dict = {}

def check_position_closed(symbol, executor, current_pos):
    if symbol not in open_trades or current_pos is not None:
        return
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
        if trade.get("db_id"):
            close_trade(trade["db_id"], exit_price, pnl)
        alert_trade_closed(symbol=symbol, side=trade["side"],
                           entry=trade["entry_price"], exit_price=exit_price,
                           qty=qty, pnl=pnl, fees=abs(pnl)*0.00055*2)
        logger.info(f"[{symbol}] Closed | PnL={pnl}")
    except Exception as e:
        logger.error(f"[{symbol}] close check error: {e}")

def process_symbol(symbol, market, executor, strategy, risk, last_candle):
    ticker = market.get_ticker_24h()
    price  = ticker["price"]
    chg    = ticker["change_pct"]
    pos    = executor.get_open_position()

    check_position_closed(symbol, executor, pos)

    df = market.get_candles()
    if df is None or df.empty:
        return

    closed_time = df.iloc[-1]["timestamp"]
    same_candle = closed_time == last_candle.get(symbol)

    df_ind = strategy.calculate_indicators(df).dropna()
    if not df_ind.empty:
        curr = df_ind.iloc[-1]
        bot_state.update_symbol(symbol,
            price=price, price_change_pct=chg,
            ema_fast=curr["ema_fast"], ema_slow=curr["ema_slow"], rsi=curr["rsi"],
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
    logger.info(f"[{symbol}] New candle: {closed_time}")

    if df_ind.empty:
        return

    curr   = df_ind.iloc[-1]
    signal = strategy.get_signal(df, symbol)
    bot_state.update_symbol(symbol, signal=signal)

    if signal != "HOLD":
        bot_state.add_signal(symbol, signal, price, curr["rsi"], curr.get("macd", 0))

    if signal == "HOLD" or pos is not None:
        return

    open_count = executor.count_open_positions()
    if open_count is None or not risk.can_trade(open_count):
        return

    side   = "Buy" if signal == "BUY" else "Sell"
    levels = risk.calculate_levels(price, side)
    result = executor.place_market_order(levels)

    if result:
        order_id = result.get("orderId", "")
        db_id = insert_trade(symbol=symbol, side=side, entry_price=price,
                             qty=levels["quantity"], stop_loss=levels["stop_loss"],
                             take_profit=levels["take_profit"], order_id=order_id)
        open_trades[symbol] = {"db_id": db_id, "side": side,
                               "entry_price": price, "qty": levels["quantity"]}
        bot_state.add_trade(symbol, side, price,
                            levels["quantity"], levels["stop_loss"], levels["take_profit"])
        alert_order_placed(symbol=symbol, side=side, price=price,
                           qty=levels["quantity"], sl=levels["stop_loss"],
                           tp=levels["take_profit"], order_id=order_id)

def bot_loop():
    init_db()
    strategy = Strategy()
    risk = RiskManager()
    markets, executors = {}, {}

    for symbol in SYMBOLS:
        ex = OrderExecutor(symbol)
        if not ex.ready:
            continue
        markets[symbol] = MarketData(symbol)
        executors[symbol] = ex

    if not executors:
        logger.error("No valid symbols")
        return

    active = list(executors.keys())
    bot_state.running    = True
    bot_state.started_at = time.time()

    try:
        bot_state.balance_usdt = list(markets.values())[0].get_balance()
        logger.info(f"Balance: {bot_state.balance_usdt} USDT")
    except Exception:
        pass

    try:
        for t in reversed(get_all_trades(limit=50)):
            bot_state.trade_log.insert(0, {
                "time": str(t["time"])[:19], "symbol": t["symbol"],
                "side": t["side"], "price": float(t["entry_price"]),
                "qty": float(t["qty"]), "sl": float(t["stop_loss"] or 0),
                "tp": float(t["take_profit"] or 0), "status": t["status"],
                "pnl": float(t["pnl"]) if t["pnl"] else None,
            })
    except Exception as e:
        logger.error(f"Trade load: {e}")

    alert_bot_started(active, TIMEFRAME)
    logger.info(f"Bot started | {', '.join(active)} | {TIMEFRAME}m | DEMO")

    last_candle, loop = {}, 0
    while True:
        try:
            for symbol in active:
                try:
                    process_symbol(symbol, markets[symbol], executors[symbol],
                                   strategy, risk, last_candle)
                except Exception as e:
                    logger.error(f"[{symbol}] Error: {e}")
                    alert_error(symbol, e)
                time.sleep(0.5)
            loop += 1
            if loop % 10 == 0:
                try:
                    bot_state.balance_usdt = list(markets.values())[0].get_balance()
                except Exception:
                    pass
            time.sleep(15)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Main loop: {e}")
            time.sleep(30)
    bot_state.running = False

if __name__ == "__main__":
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
""")

w('dashboard/static/index.html', """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Bybit Demo Bot</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{--bg:#070b0f;--bg2:#0d1117;--bg3:#161b22;--bg4:#1c2128;--border:#21262d;--border2:#30363d;
  --text:#e6edf3;--text2:#8b949e;--text3:#6e7681;--green:#3fb950;--gbg:#0d2e1a;--gborder:#1a4731;
  --red:#f85149;--rbg:#2d1117;--rborder:#4a1c1c;--blue:#58a6ff;--bbg:#0d1f36;--yellow:#d29922;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden;}
header{background:var(--bg2);border-bottom:1px solid var(--border2);padding:0 16px;height:52px;
  display:flex;align-items:center;gap:12px;flex-shrink:0;}
.logo{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:700;flex-shrink:0;}
.logo-icon{width:26px;height:26px;background:linear-gradient(135deg,#f7a11a,#e8440f);border-radius:6px;
  display:flex;align-items:center;justify-content:center;font-size:13px;}
.badge{padding:2px 8px;border-radius:20px;font-size:10px;font-weight:600;letter-spacing:.4px;text-transform:uppercase;}
.bdemo{background:var(--bbg);color:var(--blue);border:1px solid #1a3a5c;}
.blive{background:var(--gbg);color:var(--green);border:1px solid var(--gborder);}
.boff{background:var(--rbg);color:var(--red);border:1px solid var(--rborder);}
.pulse{width:6px;height:6px;background:var(--green);border-radius:50%;display:inline-block;margin-right:4px;animation:p 1.5s infinite;}
@keyframes p{0%,100%{opacity:1;}50%{opacity:.3;}}
.hstats{margin-left:auto;display:flex;gap:16px;align-items:center;}
.hs{text-align:right;}
.hs-l{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.7px;}
.hs-v{font-size:12px;font-weight:600;font-family:'JetBrains Mono',monospace;}
.tab-bar{background:var(--bg2);border-bottom:1px solid var(--border2);display:flex;flex-shrink:0;}
.tab{padding:9px 18px;font-size:12px;font-weight:500;color:var(--text3);cursor:pointer;
  border-bottom:2px solid transparent;transition:all .2s;white-space:nowrap;}
.tab:hover{color:var(--text2);}
.tab.active{color:var(--blue);border-bottom-color:var(--blue);}
.body-wrap{display:flex;flex:1;overflow:hidden;}
.left{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0;}
.right{width:248px;flex-shrink:0;background:var(--bg2);border-left:1px solid var(--border2);display:flex;flex-direction:column;overflow:hidden;}
.phdr{padding:9px 12px;border-bottom:1px solid var(--border);font-size:10px;text-transform:uppercase;letter-spacing:.7px;color:var(--text3);font-weight:600;flex-shrink:0;}
.slist{flex:1;overflow-y:auto;padding:7px;}
.tc{display:none;flex:1;flex-direction:column;overflow:hidden;}
.tc.active{display:flex;}
.chdr{padding:9px 14px;border-bottom:1px solid var(--border);background:var(--bg2);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.ctitle{font-size:12px;font-weight:600;display:flex;align-items:center;gap:6px;}
.dot{width:5px;height:5px;background:var(--blue);border-radius:50%;}
.csym{color:var(--blue);font-weight:700;font-family:'JetBrains Mono',monospace;}
.chint{font-size:10px;color:var(--text3);}
#tv-c{flex:1;overflow:hidden;}
.tstrip{height:168px;flex-shrink:0;border-top:1px solid var(--border2);background:var(--bg2);display:flex;flex-direction:column;}
.shdr{padding:7px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.st{font-size:11px;font-weight:600;display:flex;align-items:center;gap:6px;}
.cb{font-size:10px;background:var(--bg4);color:var(--text2);padding:2px 7px;border-radius:8px;border:1px solid var(--border2);}
.sbody{flex:1;overflow-y:auto;}
.sigwrap,.jwrap{flex:1;overflow-y:auto;padding:12px;}
.sig-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;}
.ssc{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center;}
.ssv{font-size:20px;font-weight:700;font-family:'JetBrains Mono',monospace;}
.ssl{font-size:10px;color:var(--text3);margin-top:4px;}
.jgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px;}
.jc{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:12px;}
.jcl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.7px;margin-bottom:5px;}
.jcv{font-size:20px;font-weight:700;font-family:'JetBrains Mono',monospace;}
.jcs{font-size:10px;color:var(--text3);margin-top:3px;}
.wrc{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:12px;}
.wrh{display:flex;justify-content:space-between;margin-bottom:8px;}
.wrht{font-size:12px;font-weight:600;}
.wrp{font-size:14px;font-weight:700;font-family:'JetBrains Mono',monospace;color:var(--green);}
.wrt{height:6px;background:var(--border);border-radius:3px;overflow:hidden;margin-bottom:8px;}
.wrf{height:100%;background:linear-gradient(90deg,var(--green),#2ea043);border-radius:3px;transition:width .5s;}
.wrr{display:flex;justify-content:space-between;}
.wri{text-align:center;}
.wril{font-size:9px;color:var(--text3);}
.wriv{font-size:13px;font-weight:600;font-family:'JetBrains Mono',monospace;}
.sc{background:var(--bg3);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:12px;}
.sch{padding:10px 14px;border-bottom:1px solid var(--border);font-size:11px;font-weight:600;display:flex;align-items:center;gap:6px;}
table{width:100%;border-collapse:collapse;}
th{text-align:left;padding:7px 12px;font-size:9px;text-transform:uppercase;letter-spacing:.7px;color:var(--text3);font-weight:500;background:var(--bg2);border-bottom:1px solid var(--border);}
td{padding:8px 12px;font-size:11px;border-bottom:1px solid var(--border);vertical-align:middle;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:var(--bg4);}
.mn{font-family:'JetBrains Mono',monospace;}
.dt{color:var(--text3);font-size:10px;}
.dsym{font-weight:600;}
.dbuy{color:var(--green);font-weight:700;}
.dsell{color:var(--red);font-weight:700;}
.dsl{color:var(--red);}
.dtp{color:var(--green);}
.dwin{color:var(--green);font-weight:600;}
.dloss{color:var(--red);font-weight:600;}
.dopn{color:var(--yellow);font-weight:600;}
.emp{text-align:center;color:var(--text3);font-size:12px;padding:20px !important;}
.symc{background:var(--bg3);border:1px solid var(--border);border-radius:9px;padding:11px;margin-bottom:7px;
  cursor:pointer;transition:all .15s;position:relative;overflow:hidden;}
.symc::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--border2);}
.symc.hbuy::before{background:var(--green);}
.symc.hsell::before{background:var(--red);}
.symc.sel{border-color:var(--blue);}
.symc:hover{background:var(--bg4);}
.ctop{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;}
.sname{font-size:11px;font-weight:700;}
.sigb{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:700;}
.sBUY{background:var(--gbg);color:var(--green);border:1px solid var(--gborder);}
.sSELL{background:var(--rbg);color:var(--red);border:1px solid var(--rborder);}
.sHOLD{background:var(--bg4);color:var(--text3);border:1px solid var(--border);}
.prow{display:flex;align-items:baseline;gap:6px;margin-bottom:7px;}
.sprice{font-size:15px;font-weight:700;font-family:'JetBrains Mono',monospace;}
.chgb{font-size:10px;font-weight:600;padding:1px 5px;border-radius:3px;}
.cp{background:var(--gbg);color:var(--green);}
.cn{background:var(--rbg);color:var(--red);}
.igrid{display:grid;grid-template-columns:1fr 1fr;gap:3px 6px;margin-bottom:5px;}
.ir{display:flex;justify-content:space-between;}
.il{font-size:9px;color:var(--text3);text-transform:uppercase;}
.iv{font-size:10px;font-weight:500;font-family:'JetBrains Mono',monospace;color:var(--text2);}
.iv.bull{color:var(--green);}
.iv.bear{color:var(--red);}
.rsiw{margin-bottom:5px;}
.rsir{display:flex;justify-content:space-between;margin-bottom:2px;}
.rsit{height:2px;background:var(--border);border-radius:1px;overflow:hidden;}
.rsif{height:100%;border-radius:1px;transition:width .4s;}
.posr{display:flex;justify-content:space-between;align-items:center;padding-top:5px;border-top:1px solid var(--border);}
.posl{font-size:9px;color:var(--text3);}
.posv{font-size:10px;font-weight:600;}
.posv.long{color:var(--green);}
.posv.short{color:var(--red);}
.posv.none{color:var(--text3);}
.pnl{font-size:10px;font-family:'JetBrains Mono',monospace;}
.pp{color:var(--green);}
.pn{color:var(--red);}
.g{color:var(--green);}.r{color:var(--red);}.b{color:var(--blue);}
.footer{padding:4px 14px;font-size:10px;color:var(--text3);background:var(--bg2);border-top:1px solid var(--border);flex-shrink:0;}
@media(max-width:900px){.right{width:200px;}}
@media(max-width:680px){
  .right{display:none;}
  .hstats .hs:nth-child(n+4){display:none;}
  .jgrid{grid-template-columns:1fr 1fr;}
  .sig-stats{grid-template-columns:1fr 1fr;}
  .chint{display:none;}
}
@media(max-width:420px){.tab{padding:9px 10px;font-size:11px;}}
::-webkit-scrollbar{width:3px;}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px;}
</style>
</head>
<body>
<header>
  <div class="logo"><div class="logo-icon">⚡</div>Bybit Bot</div>
  <span class="badge bdemo">Demo</span>
  <span class="badge blive" id="sbadge"><span class="pulse"></span>Live</span>
  <div class="hstats">
    <div class="hs"><div class="hs-l">Balance</div><div class="hs-v" id="hbal">—</div></div>
    <div class="hs"><div class="hs-l">Open PnL</div><div class="hs-v" id="hpnl" style="color:var(--green)">$0.00</div></div>
    <div class="hs"><div class="hs-l">Uptime</div><div class="hs-v" id="hup">00:00:00</div></div>
    <div class="hs"><div class="hs-l">Positions</div><div class="hs-v" id="hpos">0</div></div>
    <div class="hs"><div class="hs-l">Updated</div><div class="hs-v" id="hupd">—</div></div>
  </div>
</header>
<div class="tab-bar">
  <div class="tab active" id="t-chart" onclick="st('chart',this)">📈 Live Chart</div>
  <div class="tab" id="t-signals" onclick="st('signals',this)">🔔 Signals</div>
  <div class="tab" id="t-journal" onclick="st('journal',this)">📒 Journal</div>
</div>
<div class="body-wrap">
<div class="left">
  <div class="tc active" id="tc-chart">
    <div class="chdr">
      <div class="ctitle"><span class="dot"></span>Live Chart — <span class="csym" id="csym">BTCUSDT</span></div>
      <span class="chint">Card click → chart · 15m · RSI + MACD</span>
    </div>
    <div id="tv-c"></div>
    <div class="tstrip">
      <div class="shdr">
        <div class="st"><span class="dot"></span>Recent Trades</div>
        <span class="cb" id="tcnt">0 trades</span>
      </div>
      <div class="sbody">
        <table>
          <thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Price</th><th>Qty</th><th>SL</th><th>TP</th></tr></thead>
          <tbody id="tlog"><tr><td class="emp" colspan="7">No trades yet...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>
  <div class="tc" id="tc-signals">
    <div class="sigwrap">
      <div class="sig-stats">
        <div class="ssc"><div class="ssv b" id="s-tot">0</div><div class="ssl">Total Signals</div></div>
        <div class="ssc"><div class="ssv g" id="s-buy">0</div><div class="ssl">BUY Signals</div></div>
        <div class="ssc"><div class="ssv r" id="s-sell">0</div><div class="ssl">SELL Signals</div></div>
      </div>
      <div class="sc">
        <div class="sch"><span class="dot"></span>Signal History</div>
        <table>
          <thead><tr><th>Time</th><th>Symbol</th><th>Signal</th><th>Price</th><th>RSI</th><th>MACD</th></tr></thead>
          <tbody id="sigh"><tr><td class="emp" colspan="6">No signals yet...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>
  <div class="tc" id="tc-journal">
    <div class="jwrap">
      <div class="jgrid">
        <div class="jc"><div class="jcl">Total PnL</div><div class="jcv" id="jpnl">$0.00</div><div class="jcs">All closed</div></div>
        <div class="jc"><div class="jcl">Trades</div><div class="jcv b" id="jtot">0</div><div class="jcs" id="jopen">0 open</div></div>
        <div class="jc"><div class="jcl">Best Trade</div><div class="jcv g" id="jbest">$0.00</div><div class="jcs">Max gain</div></div>
        <div class="jc"><div class="jcl">Worst Trade</div><div class="jcv r" id="jworst">$0.00</div><div class="jcs">Max loss</div></div>
      </div>
      <div class="wrc">
        <div class="wrh"><span class="wrht">Win Rate</span><span class="wrp" id="jwr">0%</span></div>
        <div class="wrt"><div class="wrf" id="jwrbar" style="width:0%"></div></div>
        <div class="wrr">
          <div class="wri"><div class="wril">Wins</div><div class="wriv g" id="jwins">0</div></div>
          <div class="wri"><div class="wril">Losses</div><div class="wriv r" id="jlosses">0</div></div>
          <div class="wri"><div class="wril">Avg PnL</div><div class="wriv" id="javg">$0.00</div></div>
        </div>
      </div>
      <div class="sc">
        <div class="sch"><span class="dot"></span>Symbol Breakdown</div>
        <table>
          <thead><tr><th>Symbol</th><th>Trades</th><th>Wins</th><th>PnL</th></tr></thead>
          <tbody id="jsym"><tr><td class="emp" colspan="4">No data</td></tr></tbody>
        </table>
      </div>
      <div class="sc">
        <div class="sch"><span class="dot"></span>Trade History (Neon DB)</div>
        <table>
          <thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th><th>PnL</th><th>Status</th></tr></thead>
          <tbody id="jtrades"><tr><td class="emp" colspan="7">No trades</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>
</div>
<div class="right">
  <div class="phdr">📊 Markets</div>
  <div class="slist" id="symlist"></div>
</div>
</div>
<div class="footer" id="footer">Auto-refresh every 5s</div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>
let cur='BTCUSDT',tab='chart';
function st(t,el){
  tab=t;
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tc').forEach(x=>x.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tc-'+t).classList.add('active');
  if(t==='journal')fetchJ();
}
function lc(sym){
  cur=sym;document.getElementById('csym').textContent=sym;
  const c=document.getElementById('tv-c');c.innerHTML='';
  const el=document.createElement('div');el.id='tv';el.style.cssText='height:100%;width:100%;';
  c.appendChild(el);
  new TradingView.widget({container_id:'tv',autosize:true,
    symbol:'BYBIT:'+sym.replace('USDT','USDT.P'),
    interval:'15',timezone:'Asia/Dhaka',theme:'dark',style:'1',locale:'en',
    backgroundColor:'#0d1117',enable_publishing:false,save_image:false,
    studies:['RSI@tv-basicstudies','MACD@tv-basicstudies']});
}
function fu(s){return[Math.floor(s/3600),Math.floor((s%3600)/60),s%60].map(v=>String(v).padStart(2,'0')).join(':');}
function rc(r){return r>=70?'#f85149':r<=30?'#3fb950':'#58a6ff';}
function mc(v){return v>0?'bull':v<0?'bear':'';}
function fp(v){
  if(v===null||v===undefined)return '<span style="color:var(--text3)">—</span>';
  return '<span class="'+(v>=0?'pp':'pn')+'">'+(v>=0?'+':'')+'$'+Number(v).toFixed(2)+'</span>';
}
async function fetchS(){
  try{
    const d=await(await fetch('/api/status')).json();
    document.getElementById('hup').textContent=fu(d.uptime);
    document.getElementById('hbal').textContent='$'+Number(d.balance_usdt||0).toLocaleString('en-US',{maximumFractionDigits:0});
    document.getElementById('hupd').textContent=new Date().toLocaleTimeString('en-US',{hour12:false});
    const b=document.getElementById('sbadge');b.className='badge blive';b.innerHTML='<span class="pulse"></span>Live';
    let pos=0,pnl=0;
    for(const s of Object.values(d.symbols)){if(s.has_position){pos++;pnl+=s.unrealized_pnl;}}
    document.getElementById('hpos').textContent=pos;
    const pe=document.getElementById('hpnl');
    pe.textContent=(pnl>=0?'+':'')+'$'+pnl.toFixed(2);
    pe.style.color=pnl>=0?'var(--green)':'var(--red)';
    document.getElementById('tcnt').textContent=d.trade_log.length+' trades';
    const list=document.getElementById('symlist');list.innerHTML='';
    for(const[sym,s]of Object.entries(d.symbols)){
      const pc=s.has_position?(s.position_side==='Buy'?'long':'short'):'none';
      const pt=s.has_position?s.position_side+' '+s.position_size:'No Position';
      const cc=s.price_change_pct>=0?'cp':'cn';
      const ct=(s.price_change_pct>=0?'+':'')+s.price_change_pct.toFixed(2)+'%';
      const rsi=s.rsi||0;
      const ph=s.has_position?'<span class="pnl '+(s.unrealized_pnl>=0?'pp':'pn')+'">$'+Number(s.unrealized_pnl).toFixed(2)+'</span>':'';
      const card=document.createElement('div');
      card.className=['symc',s.has_position?(s.position_side==='Buy'?'hbuy':'hsell'):'',sym===cur?'sel':''].filter(Boolean).join(' ');
      card.innerHTML=`<div class="ctop"><span class="sname">${sym}</span><span class="sigb s${s.signal}">${s.signal}</span></div>
        <div class="prow"><span class="sprice">$${Number(s.price).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:4})}</span>
        <span class="chgb ${cc}">${ct}</span></div>
        <div class="igrid">
          <div class="ir"><span class="il">EMA F</span><span class="iv">${Number(s.ema_fast).toFixed(2)}</span></div>
          <div class="ir"><span class="il">EMA S</span><span class="iv">${Number(s.ema_slow).toFixed(2)}</span></div>
          <div class="ir"><span class="il">MACD</span><span class="iv ${mc(s.macd)}">${Number(s.macd||0).toFixed(4)}</span></div>
          <div class="ir"><span class="il">Sig</span><span class="iv ${mc(s.macd_signal)}">${Number(s.macd_signal||0).toFixed(4)}</span></div>
        </div>
        <div class="rsiw">
          <div class="rsir"><span class="il">RSI</span><span class="iv" style="color:${rc(rsi)}">${rsi.toFixed(1)}</span></div>
          <div class="rsit"><div class="rsif" style="width:${Math.min(100,rsi)}%;background:${rc(rsi)}"></div></div>
        </div>
        <div class="posr"><span class="posl">Position</span>
          <div style="text-align:right"><div class="posv ${pc}">${pt}</div>${ph}</div></div>`;
      card.addEventListener('click',()=>{
        document.querySelectorAll('.symc').forEach(c=>c.classList.remove('sel'));
        card.classList.add('sel');
        if(sym!==cur)lc(sym);
        if(tab!=='chart'){
          tab='chart';
          document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
          document.querySelectorAll('.tc').forEach(t=>t.classList.remove('active'));
          document.getElementById('t-chart').classList.add('active');
          document.getElementById('tc-chart').classList.add('active');
        }
      });
      list.appendChild(card);
    }
    const tb=document.getElementById('tlog');
    if(!d.trade_log||!d.trade_log.length){tb.innerHTML='<tr><td class="emp" colspan="7">No trades yet...</td></tr>';}
    else{tb.innerHTML=d.trade_log.map(t=>`<tr>
      <td class="dt mn">${t.time}</td><td class="dsym">${t.symbol}</td>
      <td class="${t.side==='Buy'?'dbuy':'dsell'}">${t.side==='Buy'?'▲ BUY':'▼ SELL'}</td>
      <td class="mn">$${Number(t.price).toFixed(2)}</td>
      <td class="mn">${Number(t.qty).toFixed(4)}</td>
      <td class="dsl mn">$${Number(t.sl).toFixed(4)}</td>
      <td class="dtp mn">$${Number(t.tp).toFixed(4)}</td></tr>`).join('');}
    if(d.signal_history){
      const sigs=d.signal_history;
      document.getElementById('s-tot').textContent=sigs.length;
      document.getElementById('s-buy').textContent=sigs.filter(s=>s.signal==='BUY').length;
      document.getElementById('s-sell').textContent=sigs.filter(s=>s.signal==='SELL').length;
      const sh=document.getElementById('sigh');
      if(!sigs.length){sh.innerHTML='<tr><td class="emp" colspan="6">No signals yet...</td></tr>';}
      else{sh.innerHTML=sigs.map(s=>`<tr>
        <td class="dt mn">${s.time}</td><td class="dsym">${s.symbol}</td>
        <td class="${s.signal==='BUY'?'dbuy':'dsell'}">${s.signal==='BUY'?'▲ BUY':'▼ SELL'}</td>
        <td class="mn">$${Number(s.price).toFixed(4)}</td>
        <td class="mn" style="color:${rc(s.rsi)}">${s.rsi}</td>
        <td class="mn ${mc(s.macd)}">${s.macd}</td></tr>`).join('');}
    }
    document.getElementById('footer').textContent='Last updated: '+new Date().toLocaleTimeString()+' · Auto-refresh every 5s';
  }catch(e){
    const b=document.getElementById('sbadge');b.className='badge boff';b.innerHTML='● Offline';
  }
}
async function fetchJ(){
  try{
    const d=await(await fetch('/api/journal')).json();
    const s=d.stats;
    const pe=document.getElementById('jpnl');
    pe.textContent=(s.total_pnl>=0?'+':'')+'$'+Number(s.total_pnl).toFixed(2);
    pe.className='jcv '+(s.total_pnl>=0?'g':'r');
    document.getElementById('jtot').textContent=s.total_trades;
    document.getElementById('jbest').textContent='$'+Number(s.best_trade).toFixed(2);
    document.getElementById('jworst').textContent='$'+Number(s.worst_trade).toFixed(2);
    document.getElementById('jwr').textContent=s.win_rate+'%';
    document.getElementById('jwrbar').style.width=s.win_rate+'%';
    document.getElementById('jwins').textContent=s.wins;
    document.getElementById('jlosses').textContent=s.losses;
    document.getElementById('javg').textContent='$'+Number(s.avg_pnl).toFixed(2);
    const sb=document.getElementById('jsym');
    if(!d.symbol_stats||!d.symbol_stats.length){sb.innerHTML='<tr><td class="emp" colspan="4">No data</td></tr>';}
    else{sb.innerHTML=d.symbol_stats.map(r=>`<tr>
      <td class="dsym">${r.symbol}</td><td class="mn">${r.trades}</td>
      <td class="mn g">${r.wins}</td>
      <td class="mn ${r.total_pnl>=0?'g':'r'}">${r.total_pnl>=0?'+':''}$${Number(r.total_pnl).toFixed(2)}</td></tr>`).join('');}
    const jt=document.getElementById('jtrades');
    if(!d.trades||!d.trades.length){jt.innerHTML='<tr><td class="emp" colspan="7">No trades</td></tr>';}
    else{jt.innerHTML=d.trades.map(t=>`<tr>
      <td class="dt mn">${t.time}</td><td class="dsym">${t.symbol}</td>
      <td class="${t.side==='Buy'?'dbuy':'dsell'}">${t.side==='Buy'?'▲':'▼'} ${t.side}</td>
      <td class="mn">$${Number(t.entry_price).toFixed(4)}</td>
      <td class="mn">${t.exit_price?'$'+Number(t.exit_price).toFixed(4):'—'}</td>
      <td>${fp(t.pnl)}</td>
      <td class="${t.status==='WIN'?'dwin':t.status==='LOSS'?'dloss':'dopn'}">${t.status}</td></tr>`).join('');}
  }catch(e){console.error(e);}
}
lc('BTCUSDT');fetchS();
setInterval(fetchS,5000);
setInterval(()=>{if(tab==='journal')fetchJ();},15000);
</script>
</body>
</html>""")

print('\n All done!')
print(' PowerShell commands:')
print('   python main.py')
print('   git add . && git commit -m "update: balance, 24h change, signals tab, mobile" && git push')