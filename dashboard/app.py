from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os,time
from dashboard.state import bot_state
from database import get_all_trades,get_journal_stats,get_symbol_stats
app=FastAPI(title="Bybit Demo Bot")
from dashboard.legacy_metrics import router as metrics_router
app.include_router(metrics_router)
from dashboard.live import router as live_router
app.include_router(live_router)
static_dir=os.path.join(os.path.dirname(__file__),"static")
app.mount("/static",StaticFiles(directory=static_dir),name="static")
@app.get("/")
def root():return FileResponse(os.path.join(static_dir,"index.html"))
@app.get("/api/status")
def status():
    syms={}
    for sym,s in bot_state.symbols.items():
        syms[sym]={"symbol":s.symbol,"price":s.price,"price_change_pct":round(s.price_change_pct,2),
            "ema_fast":round(s.ema_fast,4),"ema_slow":round(s.ema_slow,4),"rsi":round(s.rsi,2),
            "signal":s.signal,"has_position":s.has_position,"position_side":s.position_side,
            "position_size":s.position_size,"unrealized_pnl":s.unrealized_pnl,
            "macd":round(s.macd,4),"macd_signal":round(s.macd_signal,4),"macd_hist":round(s.macd_hist,4)}
    balance = round(bot_state.balance_usdt, 2)
    trades = bot_state.trade_log[:20]
    data_errors = {}

    if not bot_state.running:
        # Dashboard-only mode: fetch the balance from Bybit.
        # Never mistake an API failure for a zero balance.
        try:
            from dashboard.legacy_metrics import real_balance
            balance = real_balance()["balance"]
        except Exception as exc:
            balance = None
            data_errors["balance"] = str(exc)

        # Restore recent trade rows from Neon after restart.
        try:
            rows = get_all_trades(limit=20)
            trades = [
                {
                    "time": str(t["time"])[:19],
                    "symbol": t["symbol"],
                    "side": t["side"],
                    "price": float(t["entry_price"]),
                    "qty": float(t["qty"]),
                    "sl": float(t["stop_loss"] or 0),
                    "tp": float(t["take_profit"] or 0),
                    "status": t["status"],
                }
                for t in rows
            ]
        except Exception as exc:
            data_errors["trades"] = str(exc)

    from dashboard.account_snapshot import get_account_snapshot
    live_account_data, live_account_error = get_account_snapshot()

    return {
        "live_account": live_account_data,
        "live_account_error": live_account_error,
        "running": bot_state.running,
        "uptime": int(time.time() - bot_state.started_at)
                  if bot_state.running else 0,
        "balance_usdt": balance,
        "symbols": syms,
        "trade_log": trades,
        "signal_history": bot_state.signal_history[:50],
        "data_errors": data_errors,
    }
@app.get("/api/scan")
def get_scan():return bot_state.last_scan or{"scanned_at":"","total_scanned":0,"selected":0,"results":[]}
@app.post("/api/scan/run")
def run_scan():
    from scanner import MarketScanner
    result=MarketScanner().run(limit=20)
    bot_state.last_scan=result
    return result
@app.get("/api/journal")
def journal():
    stats=get_journal_stats()
    wr=round(stats["wins"]/stats["total_trades"]*100,1) if stats.get("total_trades",0)>0 else 0
    return{"stats":{**{k:float(v) if k not in("total_trades","wins","losses") else int(v)
                       for k,v in stats.items()},"win_rate":wr},
           "symbol_stats":get_symbol_stats(),
           "trades":[{"id":t["id"],"time":str(t["time"])[:19],"symbol":t["symbol"],"side":t["side"],
               "entry_price":float(t["entry_price"]),"qty":float(t["qty"]),
               "exit_price":float(t["exit_price"]) if t["exit_price"] else None,
               "pnl":float(t["pnl"]) if t["pnl"] else None,"status":t["status"]}
               for t in get_all_trades(limit=100)]}
@app.get("/api/settings")
def settings():
    import os
    from config.settings import SYMBOLS,TIMEFRAME,TRADE_USDT,MAX_OPEN_TRADES,STOP_LOSS_PCT,TAKE_PROFIT_PCT
    return{"symbols":SYMBOLS,"timeframe":TIMEFRAME,"trade_usdt":TRADE_USDT,
           "max_open_trades":MAX_OPEN_TRADES,"stop_loss_pct":STOP_LOSS_PCT,
           "take_profit_pct":TAKE_PROFIT_PCT,
           "api_key_set":bool(os.getenv("BYBIT_API_KEY")),
           "db_set":bool(os.getenv("DATABASE_URL")),
           "telegram_set":bool(os.getenv("TELEGRAM_TOKEN"))}
@app.post("/api/test/connection")
def test_conn():
    from pybit.unified_trading import HTTP
    from config.settings import API_KEY,API_SECRET,DEMO_MODE,TESTNET
    results={}
    try:
        s=HTTP(testnet=TESTNET,demo=DEMO_MODE,api_key=API_KEY,api_secret=API_SECRET)
        r=s.get_wallet_balance(accountType="UNIFIED")
        results["bybit"]={"ok":r["retCode"]==0,"msg":r.get("retMsg","")}
    except Exception as e:results["bybit"]={"ok":False,"msg":str(e)}
    try:
        from database import get_conn
        with get_conn() as c:
            with c.cursor() as cur:cur.execute("SELECT 1")
        results["database"]={"ok":True,"msg":"Connected"}
    except Exception as e:results["database"]={"ok":False,"msg":str(e)}
    try:
        import os,requests
        token=os.getenv("TELEGRAM_TOKEN","")
        if token:
            r=requests.get(f"https://api.telegram.org/bot{token}/getMe",timeout=5)
            results["telegram"]={"ok":r.status_code==200,"msg":r.json().get("result",{}).get("username","")}
        else:results["telegram"]={"ok":False,"msg":"Token not set"}
    except Exception as e:results["telegram"]={"ok":False,"msg":str(e)}
    return results



@app.get("/api/position/{symbol}")
def get_position(symbol: str):
    from pybit.unified_trading import HTTP
    from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET
    try:
        s = HTTP(testnet=TESTNET, demo=DEMO_MODE, api_key=API_KEY, api_secret=API_SECRET)
        r = s.get_positions(category="linear", symbol=symbol)
        if r.get("retCode") != 0:
            raise RuntimeError("Bybit position request failed")
        pos_list = r.get("result", {}).get("list", [])
        
        if pos_list and float(pos_list[0].get("size", 0)) > 0:
            p = pos_list[0]
            return {
                "has_position": True, 
                "side": p.get("side"), 
                "entry": float(p.get("avgPrice", 0)), 
                "sl": float(p.get("stopLoss", 0)) if p.get("stopLoss") else 0.0, 
                "tp": float(p.get("takeProfit", 0)) if p.get("takeProfit") else 0.0,
                "pnl": float(p.get("unrealisedPnl", 0))
            }
        return {"has_position": False}
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Bybit position data unavailable"
        )


