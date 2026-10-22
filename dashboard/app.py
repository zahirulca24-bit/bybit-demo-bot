from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from dashboard.state import bot_state
from database import get_all_trades, get_journal_stats, get_symbol_stats

app = FastAPI(title="Bybit Demo Bot Dashboard")

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/api/status")
def get_status():
    import time
    symbols_data = {}
    for sym, s in bot_state.symbols.items():
        symbols_data[sym] = {
            "symbol": s.symbol,
            "price": s.price,
            "ema_fast": round(s.ema_fast, 4),
            "ema_slow": round(s.ema_slow, 4),
            "rsi": round(s.rsi, 2),
            "signal": s.signal,
            "has_position": s.has_position,
            "position_side": s.position_side,
            "position_size": s.position_size,
            "unrealized_pnl": s.unrealized_pnl,
            "macd": round(s.macd, 4),
            "macd_signal": round(s.macd_signal, 4),
            "macd_hist": round(s.macd_hist, 4),
        }
    return {
        "running": bot_state.running,
        "uptime": int(time.time() - bot_state.started_at) if bot_state.running else 0,
        "symbols": symbols_data,
        "trade_log": bot_state.trade_log[:20],
    }

@app.get("/api/journal")
def get_journal():
    stats = get_journal_stats()
    symbol_stats = get_symbol_stats()
    trades = get_all_trades(limit=100)
    trade_list = []
    for t in trades:
        trade_list.append({
            "id": t["id"],
            "time": str(t["time"])[:19],
            "symbol": t["symbol"],
            "side": t["side"],
            "entry_price": float(t["entry_price"]),
            "qty": float(t["qty"]),
            "sl": float(t["stop_loss"] or 0),
            "tp": float(t["take_profit"] or 0),
            "exit_price": float(t["exit_price"]) if t["exit_price"] else None,
            "pnl": float(t["pnl"]) if t["pnl"] else None,
            "status": t["status"],
        })
    win_rate = 0
    if stats.get("total_trades", 0) > 0:
        win_rate = round(stats["wins"] / stats["total_trades"] * 100, 1)
    return {
        "stats": {
            "total_trades": stats.get("total_trades", 0),
            "wins": stats.get("wins", 0),
            "losses": stats.get("losses", 0),
            "win_rate": win_rate,
            "total_pnl": float(stats.get("total_pnl", 0)),
            "best_trade": float(stats.get("best_trade", 0)),
            "worst_trade": float(stats.get("worst_trade", 0)),
            "avg_pnl": float(stats.get("avg_pnl", 0)),
        },
        "symbol_stats": symbol_stats,
        "trades": trade_list,
    }