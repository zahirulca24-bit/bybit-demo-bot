from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os,time
from dashboard.state import bot_state
from database import get_all_trades,get_journal_stats,get_symbol_stats
app=FastAPI(title="Bybit Demo Bot")
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
    return{"running":bot_state.running,
           "uptime":int(time.time()-bot_state.started_at) if bot_state.running else 0,
           "balance_usdt":round(bot_state.balance_usdt,2),
           "symbols":syms,"trade_log":bot_state.trade_log[:20],
           "signal_history":bot_state.signal_history[:50]}
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