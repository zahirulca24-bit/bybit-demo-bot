#!/usr/bin/env python3
"""Run: python update_v2.py"""
import pathlib
def w(p,t):
    pp=pathlib.Path(p);pp.parent.mkdir(parents=True,exist_ok=True)
    pp.write_text(t.strip(),encoding='utf-8');print(f'  OK  {p}')
print('Updating all files...\n')

w('scanner.py',r"""
import time as _t
import pandas as pd
from pybit.unified_trading import HTTP
from config.settings import API_KEY,API_SECRET,DEMO_MODE,TESTNET,TIMEFRAME
from core.strategy import Strategy
from utils.logger import logger

class MarketScanner:
    TOP_N=30
    def __init__(self):
        self.session=HTTP(testnet=TESTNET,demo=DEMO_MODE,api_key=API_KEY,api_secret=API_SECRET)
        self.strategy=Strategy()
    def _top_syms(self):
        try:
            r=self.session.get_tickers(category="linear")
            rows=[t for t in r["result"]["list"] if t["symbol"].endswith("USDT") and float(t.get("volume24h",0))>0]
            rows.sort(key=lambda x:float(x["volume24h"]),reverse=True)
            return [t["symbol"] for t in rows[:self.TOP_N]]
        except Exception as e:logger.error(f"[Scan] top_syms:{e}");return[]
    def _candles(self,sym):
        try:
            r=self.session.get_kline(category="linear",symbol=sym,interval=TIMEFRAME,limit=100)
            if r["retCode"]!=0:return None
            df=pd.DataFrame(r["result"]["list"],columns=["timestamp","open","high","low","close","volume","turnover"])
            df=df.astype({"timestamp":"int64","open":"float64","high":"float64","low":"float64","close":"float64","volume":"float64"})
            df["timestamp"]=pd.to_datetime(df["timestamp"],unit="ms")
            return df.sort_values("timestamp").reset_index(drop=True)
        except:return None
    def scan_one(self,sym):
        try:
            df=self._candles(sym)
            if df is None:return None
            td=self.session.get_tickers(category="linear",symbol=sym)["result"]["list"][0]
            price=float(td["lastPrice"]);chg=round(float(td.get("price24hPcnt",0))*100,2)
            vol=float(td.get("volume24h",0))
            di=self.strategy.calculate_indicators(df).dropna()
            if di.empty:return None
            c=di.iloc[-1];sig=self.strategy.get_signal(df,sym)
            score,reasons=0,[]
            rsi=float(c["rsi"]);macd=float(c.get("macd",0));ms=float(c.get("macd_signal",0))
            if rsi<=30:score+=3;reasons.append(f"RSI Oversold {rsi:.1f}")
            elif rsi>=70:score+=3;reasons.append(f"RSI Overbought {rsi:.1f}")
            elif rsi<=40:score+=1;reasons.append(f"RSI Low {rsi:.1f}")
            elif rsi>=60:score+=1;reasons.append(f"RSI High {rsi:.1f}")
            if macd>ms:score+=2;reasons.append("MACD Bullish")
            else:score+=1;reasons.append("MACD Bearish")
            if c["ema_fast"]>c["ema_slow"]:score+=1;reasons.append("EMA Bull Align")
            else:reasons.append("EMA Bear Align")
            if sig!="HOLD":score+=5;reasons.append(f"Signal:{sig}")
            return{"symbol":sym,"price":price,"change_pct":chg,"volume_24h":round(vol,0),
                   "rsi":round(rsi,2),"macd":round(macd,4),
                   "ema_fast":round(float(c["ema_fast"]),4),"ema_slow":round(float(c["ema_slow"]),4),
                   "signal":sig,"score":score,"reasons":", ".join(reasons),
                   "selected":score>=5 or sig!="HOLD"}
        except Exception as e:logger.error(f"[Scan] {sym}:{e}");return None
    def run(self,limit=20):
        t0=_t.time();syms=self._top_syms()[:limit]
        logger.info(f"[Scan] Scanning {len(syms)} symbols...")
        results=[]
        for sym in syms:
            r=self.scan_one(sym)
            if r:results.append(r)
            _t.sleep(0.15)
        results.sort(key=lambda x:x["score"],reverse=True)
        sel=[r for r in results if r["selected"]];dur=round(_t.time()-t0,1)
        logger.info(f"[Scan] Done {dur}s | {len(sel)}/{len(results)} selected")
        return{"scanned_at":_t.strftime("%Y-%m-%d %H:%M:%S"),"total_scanned":len(results),
               "selected":len(sel),"duration_sec":dur,"results":results}
""")

w('dashboard/state.py',r"""
from dataclasses import dataclass,field
from typing import Dict,List
import time,json,os
TRADE_LOG_FILE="logs/trade_log.json"
def _load():
    try:
        if os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE) as f:return json.load(f)
    except:pass
    return[]
def _save(t):
    try:
        os.makedirs("logs",exist_ok=True)
        with open(TRADE_LOG_FILE,"w") as f:json.dump(t,f,indent=2)
    except:pass
@dataclass
class SymbolState:
    symbol:str="";price:float=0.0;price_change_pct:float=0.0
    ema_fast:float=0.0;ema_slow:float=0.0;rsi:float=0.0;signal:str="HOLD"
    has_position:bool=False;position_side:str="";position_size:float=0.0
    unrealized_pnl:float=0.0;macd:float=0.0;macd_signal:float=0.0
    macd_hist:float=0.0;updated_at:float=0.0
@dataclass
class BotState:
    running:bool=False;started_at:float=0.0;balance_usdt:float=0.0
    symbols:Dict[str,SymbolState]=field(default_factory=dict)
    trade_log:List[dict]=field(default_factory=_load)
    signal_history:List[dict]=field(default_factory=list)
    last_scan:dict=field(default_factory=dict)
    def update_symbol(self,symbol,**kw):
        if symbol not in self.symbols:self.symbols[symbol]=SymbolState(symbol=symbol)
        s=self.symbols[symbol]
        for k,v in kw.items():
            if hasattr(s,k):setattr(s,k,v)
        s.updated_at=time.time()
    def add_trade(self,symbol,side,price,qty,sl,tp):
        self.trade_log.insert(0,{"time":time.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol":symbol,"side":side,"price":price,"qty":qty,"sl":sl,"tp":tp})
        if len(self.trade_log)>100:self.trade_log.pop()
        _save(self.trade_log)
    def add_signal(self,symbol,signal,price,rsi,macd,traded=False,reason=""):
        self.signal_history.insert(0,{"time":time.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol":symbol,"signal":signal,"price":price,
            "rsi":round(rsi,2),"macd":round(macd,4),"traded":traded,"reason":reason})
        if len(self.signal_history)>200:self.signal_history.pop()
bot_state=BotState()
""")

w('dashboard/app.py',r"""
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
""")

w('main.py',r"""
import time,threading
import uvicorn
from config.settings import SYMBOLS,TIMEFRAME,MAX_OPEN_TRADES
from core.market_data import MarketData
from core.strategy import Strategy
from core.risk_manager import RiskManager
from core.order_executor import OrderExecutor
from dashboard.app import app
from dashboard.state import bot_state
from database import init_db,insert_trade,close_trade,get_all_trades
from telegram_alert import alert_bot_started,alert_order_placed,alert_trade_closed,alert_error
from utils.logger import logger

open_trades:dict={}
_scan_counter=0

def check_closed(symbol,executor,pos):
    if symbol not in open_trades or pos is not None:return
    trade=open_trades.pop(symbol)
    try:
        h=executor.session.get_closed_pnl(category="linear",symbol=symbol,limit=1)
        if h["retCode"]==0 and h["result"]["list"]:
            rec=h["result"]["list"][0]
            exit_price=float(rec.get("avgExitPrice",0));pnl=float(rec.get("closedPnl",0))
            qty=float(rec.get("qty",trade.get("qty",0)))
        else:exit_price=pnl=0.0;qty=trade.get("qty",0)
        if trade.get("db_id"):close_trade(trade["db_id"],exit_price,pnl)
        alert_trade_closed(symbol=symbol,side=trade["side"],entry=trade["entry_price"],
                           exit_price=exit_price,qty=qty,pnl=pnl,fees=abs(pnl)*0.00055*2)
        logger.info(f"[{symbol}] Closed PnL={pnl}")
    except Exception as e:logger.error(f"[{symbol}] close_check:{e}")

def process_symbol(symbol,market,executor,strategy,risk,last_candle):
    ticker=market.get_ticker_24h();price=ticker["price"];chg=ticker["change_pct"]
    pos=executor.get_open_position()
    check_closed(symbol,executor,pos)
    df=market.get_candles()
    if df is None or df.empty:return
    closed_time=df.iloc[-1]["timestamp"];same=closed_time==last_candle.get(symbol)
    df_ind=strategy.calculate_indicators(df).dropna()
    if not df_ind.empty:
        curr=df_ind.iloc[-1]
        bot_state.update_symbol(symbol,price=price,price_change_pct=chg,
            ema_fast=curr["ema_fast"],ema_slow=curr["ema_slow"],rsi=curr["rsi"],
            macd=round(float(curr.get("macd",0)),4),
            macd_signal=round(float(curr.get("macd_signal",0)),4),
            macd_hist=round(float(curr.get("macd_hist",0)),4),
            has_position=pos is not None,
            position_side=pos["side"] if pos else "",
            position_size=float(pos["size"]) if pos else 0.0,
            unrealized_pnl=float(pos.get("unrealisedPnl",0)) if pos else 0.0)
    if same:return
    last_candle[symbol]=closed_time
    logger.info(f"[{symbol}] New candle:{closed_time}")
    if df_ind.empty:return
    curr=df_ind.iloc[-1];signal=strategy.get_signal(df,symbol)
    bot_state.update_symbol(symbol,signal=signal)
    rsi_v=float(curr["rsi"]);macd_v=float(curr.get("macd",0))
    if signal!="HOLD":
        open_count=executor.count_open_positions() or 0
        has_pos=pos is not None
        if has_pos:
            reason="Already has open position"
            bot_state.add_signal(symbol,signal,price,rsi_v,macd_v,traded=False,reason=reason)
            logger.info(f"[{symbol}] Signal {signal} skipped: {reason}")
            return
        if not risk.can_trade(open_count):
            reason=f"Max open trades reached ({open_count}/{MAX_OPEN_TRADES})"
            bot_state.add_signal(symbol,signal,price,rsi_v,macd_v,traded=False,reason=reason)
            logger.info(f"[{symbol}] Signal {signal} skipped: {reason}")
            return
        side="Buy" if signal=="BUY" else "Sell"
        levels=risk.calculate_levels(price,side)
        result=executor.place_market_order(levels)
        if result:
            order_id=result.get("orderId","")
            db_id=insert_trade(symbol=symbol,side=side,entry_price=price,qty=levels["quantity"],
                               stop_loss=levels["stop_loss"],take_profit=levels["take_profit"],order_id=order_id)
            open_trades[symbol]={"db_id":db_id,"side":side,"entry_price":price,"qty":levels["quantity"]}
            bot_state.add_trade(symbol,side,price,levels["quantity"],levels["stop_loss"],levels["take_profit"])
            bot_state.add_signal(symbol,signal,price,rsi_v,macd_v,traded=True,reason=f"Order placed: {order_id}")
            alert_order_placed(symbol=symbol,side=side,price=price,qty=levels["quantity"],
                               sl=levels["stop_loss"],tp=levels["take_profit"],order_id=order_id)
        else:
            bot_state.add_signal(symbol,signal,price,rsi_v,macd_v,traded=False,reason="Order placement failed")

def bot_loop():
    global _scan_counter
    init_db();strategy=Strategy();risk=RiskManager();markets,executors={},{}
    for sym in SYMBOLS:
        ex=OrderExecutor(sym)
        if not ex.ready:continue
        markets[sym]=MarketData(sym);executors[sym]=ex
    if not executors:logger.error("No valid symbols");return
    active=list(executors.keys())
    bot_state.running=True;bot_state.started_at=time.time()
    try:bot_state.balance_usdt=list(markets.values())[0].get_balance()
    except:pass
    try:
        for t in reversed(get_all_trades(limit=50)):
            bot_state.trade_log.insert(0,{"time":str(t["time"])[:19],"symbol":t["symbol"],
                "side":t["side"],"price":float(t["entry_price"]),"qty":float(t["qty"]),
                "sl":float(t["stop_loss"] or 0),"tp":float(t["take_profit"] or 0),"status":t["status"],
                "pnl":float(t["pnl"]) if t["pnl"] else None})
    except Exception as e:logger.error(f"Trade load:{e}")
    alert_bot_started(active,TIMEFRAME)
    logger.info(f"Bot started | {', '.join(active)} | {TIMEFRAME}m | DEMO")
    # Initial scan
    try:
        from scanner import MarketScanner
        bot_state.last_scan=MarketScanner().run(limit=20)
    except Exception as e:logger.error(f"Initial scan:{e}")
    last_candle={};loop=0
    while True:
        try:
            for sym in active:
                try:process_symbol(sym,markets[sym],executors[sym],strategy,risk,last_candle)
                except Exception as e:logger.error(f"[{sym}] Error:{e}");alert_error(sym,e)
                time.sleep(0.5)
            loop+=1
            if loop%10==0:
                try:bot_state.balance_usdt=list(markets.values())[0].get_balance()
                except:pass
            # Auto-scan every 20 loops (~5 minutes)
            if loop%20==0:
                try:
                    from scanner import MarketScanner
                    bot_state.last_scan=MarketScanner().run(limit=20)
                except Exception as e:logger.error(f"Auto-scan:{e}")
            time.sleep(15)
        except KeyboardInterrupt:break
        except Exception as e:logger.error(f"Main loop:{e}");time.sleep(30)
    bot_state.running=False

if __name__=="__main__":
    t=threading.Thread(target=bot_loop,daemon=True);t.start()
    uvicorn.run(app,host="0.0.0.0",port=8000,log_level="warning")
""")

w('dashboard/static/index.html',"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Bybit Demo Bot</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{--bg:#070b0f;--bg2:#0d1117;--bg3:#161b22;--bg4:#1c2128;--bd:#21262d;--bd2:#30363d;
  --t:#e6edf3;--t2:#8b949e;--t3:#6e7681;--g:#3fb950;--gbg:#0d2e1a;--gbr:#1a4731;
  --r:#f85149;--rbg:#2d1117;--rbr:#4a1c1c;--b:#58a6ff;--bbg:#0d1f36;--y:#d29922;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--t);font-family:'Inter',sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden;}
/* Header */
header{background:var(--bg2);border-bottom:1px solid var(--bd2);padding:0 14px;height:50px;
  display:flex;align-items:center;gap:10px;flex-shrink:0;}
.logo{display:flex;align-items:center;gap:7px;font-size:14px;font-weight:700;flex-shrink:0;}
.li{width:26px;height:26px;background:linear-gradient(135deg,#f7a11a,#e8440f);border-radius:6px;
  display:flex;align-items:center;justify-content:center;font-size:13px;}
.badge{padding:2px 8px;border-radius:20px;font-size:10px;font-weight:600;letter-spacing:.4px;text-transform:uppercase;}
.bdemo{background:var(--bbg);color:var(--b);border:1px solid #1a3a5c;}
.blive{background:var(--gbg);color:var(--g);border:1px solid var(--gbr);}
.boff{background:var(--rbg);color:var(--r);border:1px solid var(--rbr);}
.pulse{width:6px;height:6px;background:var(--g);border-radius:50%;display:inline-block;margin-right:4px;animation:p 1.5s infinite;}
@keyframes p{0%,100%{opacity:1}50%{opacity:.3}}
.hs{margin-left:auto;display:flex;gap:14px;align-items:center;}
.hsi{text-align:right;}
.hsl{font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;}
.hsv{font-size:12px;font-weight:600;font-family:'JetBrains Mono',monospace;}
/* Tabs */
.tbar{background:var(--bg2);border-bottom:1px solid var(--bd2);display:flex;flex-shrink:0;overflow-x:auto;}
.tbar::-webkit-scrollbar{height:0;}
.tab{padding:9px 16px;font-size:12px;font-weight:500;color:var(--t3);cursor:pointer;
  border-bottom:2px solid transparent;transition:all .2s;white-space:nowrap;flex-shrink:0;}
.tab:hover{color:var(--t2);}
.tab.active{color:var(--b);border-bottom-color:var(--b);}
/* Layout */
.wrap{display:flex;flex:1;overflow:hidden;}
.lp{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0;}
.rp{width:240px;flex-shrink:0;background:var(--bg2);border-left:1px solid var(--bd2);display:flex;flex-direction:column;overflow:hidden;}
.rph{padding:8px 12px;border-bottom:1px solid var(--bd);font-size:10px;text-transform:uppercase;letter-spacing:.7px;color:var(--t3);font-weight:600;flex-shrink:0;display:flex;align-items:center;justify-content:space-between;}
.rph span{font-size:10px;color:var(--b);cursor:pointer;}
.rtable-wrap{flex:1;overflow-y:auto;}
.rtable-wrap::-webkit-scrollbar{width:3px;}
.rtable-wrap::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:2px;}
.rt{width:100%;border-collapse:collapse;}
.rt th{padding:6px 8px;font-size:9px;text-transform:uppercase;letter-spacing:.6px;color:var(--t3);font-weight:500;background:var(--bg3);border-bottom:1px solid var(--bd);position:sticky;top:0;}
.rt td{padding:7px 8px;font-size:11px;border-bottom:1px solid var(--bd);}
.rt tr:last-child td{border-bottom:none;}
.rt tr:hover td{background:var(--bg4);cursor:pointer;}
.rt tr.sel td{background:var(--bbg);}
/* Tab Content */
.tc{display:none;flex:1;flex-direction:column;overflow:hidden;}
.tc.active{display:flex;}
/* Chart */
.chdr{padding:9px 14px;border-bottom:1px solid var(--bd);background:var(--bg2);
  display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.ctit{font-size:12px;font-weight:600;display:flex;align-items:center;gap:6px;}
.dot{width:5px;height:5px;background:var(--b);border-radius:50%;}
.csym{color:var(--b);font-weight:700;font-family:'JetBrains Mono',monospace;}
.cmeta{display:flex;align-items:center;gap:12px;}
.countdown-box{background:var(--bg4);border:1px solid var(--bd2);border-radius:6px;
  padding:3px 10px;font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600;}
.cd-label{font-size:9px;color:var(--t3);margin-right:4px;}
.chint{font-size:10px;color:var(--t3);}
#tv-c{flex:1;overflow:hidden;}
.tstrip{height:165px;flex-shrink:0;border-top:1px solid var(--bd2);background:var(--bg2);display:flex;flex-direction:column;}
.shdr{padding:7px 14px;border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.st{font-size:11px;font-weight:600;display:flex;align-items:center;gap:5px;}
.cnt{font-size:10px;background:var(--bg4);color:var(--t2);padding:2px 7px;border-radius:8px;border:1px solid var(--bd2);}
.sbody{flex:1;overflow-y:auto;}
/* Scanner */
.scan-wrap{flex:1;overflow-y:auto;padding:12px;}
.scan-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px;}
.ssc{background:var(--bg3);border:1px solid var(--bd);border-radius:8px;padding:12px;text-align:center;}
.ssv{font-size:20px;font-weight:700;font-family:'JetBrains Mono',monospace;}
.ssl{font-size:10px;color:var(--t3);margin-top:3px;}
.scan-btn{padding:7px 18px;background:var(--b);color:#fff;border:none;border-radius:6px;
  font-size:12px;font-weight:600;cursor:pointer;transition:opacity .2s;}
.scan-btn:hover{opacity:.8;}
.scan-btn:disabled{opacity:.4;cursor:not-allowed;}
.tbl-wrap{background:var(--bg3);border:1px solid var(--bd);border-radius:8px;overflow:hidden;}
.tbl-head{padding:10px 14px;border-bottom:1px solid var(--bd);font-size:11px;font-weight:600;
  display:flex;align-items:center;justify-content:space-between;}
/* Signal */
.sig-wrap{flex:1;overflow-y:auto;padding:12px;}
.sig-top{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;}
/* Journal */
.jwrap{flex:1;overflow-y:auto;padding:12px;}
.jg{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px;}
.jc{background:var(--bg3);border:1px solid var(--bd);border-radius:8px;padding:12px;}
.jcl{font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:5px;}
.jcv{font-size:20px;font-weight:700;font-family:'JetBrains Mono',monospace;}
.wrc{background:var(--bg3);border:1px solid var(--bd);border-radius:8px;padding:12px;margin-bottom:12px;}
.wrh{display:flex;justify-content:space-between;margin-bottom:8px;}
.wrt{height:6px;background:var(--bd);border-radius:3px;overflow:hidden;margin-bottom:8px;}
.wrf{height:100%;background:linear-gradient(90deg,var(--g),#2ea043);border-radius:3px;transition:width .5s;}
.wrr{display:flex;justify-content:space-between;}
.wri{text-align:center;}
.wril{font-size:9px;color:var(--t3);}
.wriv{font-size:13px;font-weight:600;font-family:'JetBrains Mono',monospace;}
/* Settings */
.swrap{flex:1;overflow-y:auto;padding:12px;}
.cfg-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;}
.cfg-c{background:var(--bg3);border:1px solid var(--bd);border-radius:8px;padding:12px;}
.cfg-t{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px;font-weight:600;}
.cfg-r{display:flex;justify-content:space-between;margin-bottom:5px;}
.cfg-k{font-size:11px;color:var(--t2);}
.cfg-v{font-size:11px;font-weight:600;font-family:'JetBrains Mono',monospace;}
.test-btn{padding:8px 20px;background:var(--bg4);border:1px solid var(--bd2);border-radius:6px;
  color:var(--t);font-size:12px;font-weight:600;cursor:pointer;transition:all .2s;margin-bottom:12px;}
.test-btn:hover{border-color:var(--b);color:var(--b);}
.conn-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;}
.conn-c{background:var(--bg3);border:1px solid var(--bd);border-radius:8px;padding:14px;text-align:center;}
.conn-icon{font-size:24px;margin-bottom:6px;}
.conn-name{font-size:11px;font-weight:600;margin-bottom:4px;}
.conn-status{font-size:10px;padding:2px 8px;border-radius:10px;display:inline-block;}
.cs-ok{background:var(--gbg);color:var(--g);border:1px solid var(--gbr);}
.cs-err{background:var(--rbg);color:var(--r);border:1px solid var(--rbr);}
.cs-idle{background:var(--bg4);color:var(--t3);border:1px solid var(--bd);}
.conn-msg{font-size:10px;color:var(--t3);margin-top:4px;word-break:break-all;}
/* Common */
table{width:100%;border-collapse:collapse;}
th{text-align:left;padding:7px 10px;font-size:9px;text-transform:uppercase;letter-spacing:.6px;
  color:var(--t3);font-weight:500;background:var(--bg2);border-bottom:1px solid var(--bd);}
td{padding:7px 10px;font-size:11px;border-bottom:1px solid var(--bd);vertical-align:middle;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:var(--bg4);}
.mn{font-family:'JetBrains Mono',monospace;}
.dt{color:var(--t3);font-size:10px;}
.dsym{font-weight:700;}
.dbuy{color:var(--g);font-weight:700;}
.dsell{color:var(--r);font-weight:700;}
.dwin{color:var(--g);font-weight:600;}
.dloss{color:var(--r);font-weight:600;}
.dopn{color:var(--y);font-weight:600;}
.sc{background:var(--bg3);border:1px solid var(--bd);border-radius:8px;overflow:hidden;margin-bottom:10px;}
.sch{padding:9px 14px;border-bottom:1px solid var(--bd);font-size:11px;font-weight:600;
  display:flex;align-items:center;gap:5px;}
.emp{text-align:center;color:var(--t3);font-size:12px;padding:20px !important;}
.sigb{padding:2px 7px;border-radius:4px;font-size:9px;font-weight:700;}
.sBUY{background:var(--gbg);color:var(--g);border:1px solid var(--gbr);}
.sSELL{background:var(--rbg);color:var(--r);border:1px solid var(--rbr);}
.sHOLD{background:var(--bg4);color:var(--t3);border:1px solid var(--bd);}
.chgp{color:var(--g);font-size:10px;}
.chgn{color:var(--r);font-size:10px;}
.g{color:var(--g);}.r{color:var(--r);}.b{color:var(--b);}.y{color:var(--y);}
.scored-yes{color:var(--g);font-weight:600;}
.scored-no{color:var(--t3);}
.footer{padding:4px 14px;font-size:10px;color:var(--t3);background:var(--bg2);border-top:1px solid var(--bd);flex-shrink:0;}
@media(max-width:900px){.rp{width:190px;}}
@media(max-width:680px){.rp{display:none;}.jg{grid-template-columns:1fr 1fr;}.scan-stats{grid-template-columns:1fr 1fr;}}
::-webkit-scrollbar{width:3px;}
::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:2px;}
</style>
</head>
<body>
<header>
  <div class="logo"><div class="li">⚡</div>Bybit Bot</div>
  <span class="badge bdemo">Demo</span>
  <span class="badge blive" id="sbadge"><span class="pulse"></span>Live</span>
  <div class="hs">
    <div class="hsi"><div class="hsl">Balance</div><div class="hsv" id="hbal">—</div></div>
    <div class="hsi"><div class="hsl">Open PnL</div><div class="hsv" id="hpnl" style="color:var(--g)">$0.00</div></div>
    <div class="hsi"><div class="hsl">Uptime</div><div class="hsv" id="hup">00:00:00</div></div>
    <div class="hsi"><div class="hsl">Pos</div><div class="hsv" id="hpos">0</div></div>
    <div class="hsi"><div class="hsl">Updated</div><div class="hsv" id="hupd">—</div></div>
  </div>
</header>
<div class="tbar">
  <div class="tab active" id="t-chart" onclick="st('chart',this)">📈 Chart</div>
  <div class="tab" id="t-scanner" onclick="st('scanner',this)">🔍 Scanner</div>
  <div class="tab" id="t-signals" onclick="st('signals',this)">🔔 Signals</div>
  <div class="tab" id="t-journal" onclick="st('journal',this)">📒 Journal</div>
  <div class="tab" id="t-settings" onclick="st('settings',this)">⚙️ Settings</div>
</div>
<div class="wrap">
<div class="lp">
  <!-- Chart Tab -->
  <div class="tc active" id="tc-chart">
    <div class="chdr">
      <div class="ctit"><span class="dot"></span>Chart — <span class="csym" id="csym">BTCUSDT</span></div>
      <div class="cmeta">
        <div class="countdown-box"><span class="cd-label">CLOSE</span><span id="countdown">--:--</span></div>
        <span class="chint">15m · RSI + MACD · Click card → chart</span>
      </div>
    </div>
    <div id="tv-c"></div>
    <div class="tstrip">
      <div class="shdr"><div class="st"><span class="dot"></span>Recent Trades</div><span class="cnt" id="tcnt">0</span></div>
      <div class="sbody">
        <table><thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Price</th><th>Qty</th><th>SL</th><th>TP</th></tr></thead>
        <tbody id="tlog"><tr><td class="emp" colspan="7">No trades yet...</td></tr></tbody></table>
      </div>
    </div>
  </div>
  <!-- Scanner Tab -->
  <div class="tc" id="tc-scanner">
    <div class="scan-wrap">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
        <div>
          <div style="font-size:14px;font-weight:700;margin-bottom:2px;">Market Scanner</div>
          <div style="font-size:11px;color:var(--t3)" id="scan-time">Never scanned</div>
        </div>
        <button class="scan-btn" id="scan-btn" onclick="runScan()">🔍 Scan Now</button>
      </div>
      <div class="scan-stats">
        <div class="ssc"><div class="ssv b" id="sc-total">0</div><div class="ssl">Scanned</div></div>
        <div class="ssc"><div class="ssv g" id="sc-sel">0</div><div class="ssl">Selected</div></div>
        <div class="ssc"><div class="ssv y" id="sc-sig">0</div><div class="ssl">With Signal</div></div>
        <div class="ssc"><div class="ssv" id="sc-dur">0s</div><div class="ssl">Duration</div></div>
      </div>
      <div class="tbl-wrap">
        <div class="tbl-head">
          <span>Scan Results (Top 20 by Volume)</span>
          <span style="font-size:10px;color:var(--t3)">Auto-scan every ~5 min</span>
        </div>
        <table>
          <thead><tr><th>#</th><th>Symbol</th><th>Price</th><th>Chg%</th><th>RSI</th><th>MACD</th><th>Signal</th><th>Score</th><th>Selected</th><th>Reasons</th></tr></thead>
          <tbody id="scan-table"><tr><td class="emp" colspan="10">Click Scan Now to start...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>
  <!-- Signals Tab -->
  <div class="tc" id="tc-signals">
    <div class="sig-wrap">
      <div class="sig-top">
        <div class="ssc"><div class="ssv b" id="sg-tot">0</div><div class="ssl">Total</div></div>
        <div class="ssc"><div class="ssv g" id="sg-buy">0</div><div class="ssl">BUY</div></div>
        <div class="ssc"><div class="ssv r" id="sg-sell">0</div><div class="ssl">SELL</div></div>
      </div>
      <div class="sc">
        <div class="sch"><span class="dot"></span>Signal History — Trade taken/skipped & reason</div>
        <table>
          <thead><tr><th>Time</th><th>Symbol</th><th>Signal</th><th>Price</th><th>RSI</th><th>MACD</th><th>Traded</th><th>Reason</th></tr></thead>
          <tbody id="sigh"><tr><td class="emp" colspan="8">No signals yet...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>
  <!-- Journal Tab -->
  <div class="tc" id="tc-journal">
    <div class="jwrap">
      <div class="jg">
        <div class="jc"><div class="jcl">Total PnL</div><div class="jcv" id="jpnl">$0.00</div><div style="font-size:10px;color:var(--t3)">All closed</div></div>
        <div class="jc"><div class="jcl">Trades</div><div class="jcv b" id="jtot">0</div><div style="font-size:10px;color:var(--t3)" id="jopen">0 open</div></div>
        <div class="jc"><div class="jcl">Best Trade</div><div class="jcv g" id="jbest">$0.00</div></div>
        <div class="jc"><div class="jcl">Worst</div><div class="jcv r" id="jworst">$0.00</div></div>
      </div>
      <div class="wrc">
        <div class="wrh"><span style="font-size:12px;font-weight:600;">Win Rate</span><span style="font-size:14px;font-weight:700;color:var(--g)" id="jwr">0%</span></div>
        <div class="wrt"><div class="wrf" id="jwrbar" style="width:0%"></div></div>
        <div class="wrr">
          <div class="wri"><div class="wril">Wins</div><div class="wriv g" id="jwins">0</div></div>
          <div class="wri"><div class="wril">Losses</div><div class="wriv r" id="jlosses">0</div></div>
          <div class="wri"><div class="wril">Avg PnL</div><div class="wriv" id="javg">$0.00</div></div>
        </div>
      </div>
      <div class="sc" style="margin-bottom:10px;">
        <div class="sch"><span class="dot"></span>Symbol Breakdown</div>
        <table><thead><tr><th>Symbol</th><th>Trades</th><th>Wins</th><th>PnL</th></tr></thead>
        <tbody id="jsym"><tr><td class="emp" colspan="4">No data</td></tr></tbody></table>
      </div>
      <div class="sc">
        <div class="sch"><span class="dot"></span>Trade History — Entry, Exit, PnL (Neon DB)</div>
        <table>
          <thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th><th>PnL</th><th>Status</th></tr></thead>
          <tbody id="jtrades"><tr><td class="emp" colspan="7">No trades</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>
  <!-- Settings Tab -->
  <div class="tc" id="tc-settings">
    <div class="swrap">
      <div style="margin-bottom:12px;">
        <button class="test-btn" onclick="testConn()">🔌 Test All Connections</button>
      </div>
      <div class="conn-grid">
        <div class="conn-c" id="conn-bybit"><div class="conn-icon">🔑</div><div class="conn-name">Bybit API</div><div class="conn-status cs-idle" id="cs-bybit">Untested</div><div class="conn-msg" id="cm-bybit"></div></div>
        <div class="conn-c" id="conn-db"><div class="conn-icon">🗄️</div><div class="conn-name">Neon Database</div><div class="conn-status cs-idle" id="cs-db">Untested</div><div class="conn-msg" id="cm-db"></div></div>
        <div class="conn-c" id="conn-tg"><div class="conn-icon">📱</div><div class="conn-name">Telegram</div><div class="conn-status cs-idle" id="cs-tg">Untested</div><div class="conn-msg" id="cm-tg"></div></div>
      </div>
      <div class="cfg-grid">
        <div class="cfg-c">
          <div class="cfg-t">Trading Config</div>
          <div id="cfg-trading"></div>
        </div>
        <div class="cfg-c">
          <div class="cfg-t">Risk Config</div>
          <div id="cfg-risk"></div>
        </div>
      </div>
      <div class="cfg-c" style="margin-bottom:10px;">
        <div class="cfg-t">Monitored Symbols</div>
        <div id="cfg-symbols" style="display:flex;flex-wrap:wrap;gap:6px;padding-top:4px;"></div>
      </div>
    </div>
  </div>
</div>
<!-- Right Panel: Compact Table -->
<div class="rp">
  <div class="rph">📊 Markets<span onclick="fetchS()">↻</span></div>
  <div class="rtable-wrap">
    <table class="rt">
      <thead><tr><th>Symbol</th><th>Price</th><th>Chg</th><th>Sig</th></tr></thead>
      <tbody id="rtbody"></tbody>
    </table>
  </div>
</div>
</div>
<div class="footer" id="footer">Auto-refresh every 5s</div>

<script src="https://s3.tradingview.com/tv.js"></script>
<script>
let cur='BTCUSDT',tab='chart';

// Countdown timer
function updateCountdown(){
  const now=new Date(),ms=now.getTime(),iv=15*60*1000;
  const nc=Math.ceil(ms/iv)*iv,rem=Math.floor((nc-ms)/1000);
  const m=Math.floor(rem/60),s=rem%60;
  const el=document.getElementById('countdown');
  if(el){
    const pct=rem/(15*60);
    el.textContent=String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
    el.style.color=rem<60?'var(--r)':rem<180?'var(--y)':'var(--g)';
  }
}
setInterval(updateCountdown,1000);updateCountdown();

function st(t,el){
  tab=t;
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tc').forEach(x=>x.classList.remove('active'));
  el.classList.add('active');document.getElementById('tc-'+t).classList.add('active');
  if(t==='journal')fetchJ();
  if(t==='scanner')fetchScan();
  if(t==='settings')fetchSettings();
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
function rc(r){return r>=70?'var(--r)':r<=30?'var(--g)':'var(--b)';}
function mc(v){return v>0?'class="g"':v<0?'class="r"':'';}
function fp(v){
  if(v===null||v===undefined)return'<span style="color:var(--t3)">—</span>';
  return'<span class="'+(v>=0?'g':'r')+'">'+(v>=0?'+':'')+'$'+Number(v).toFixed(2)+'</span>';
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
    pe.style.color=pnl>=0?'var(--g)':'var(--r)';
    document.getElementById('tcnt').textContent=d.trade_log.length;
    // Right panel table
    const rb=document.getElementById('rtbody');rb.innerHTML='';
    for(const[sym,s]of Object.entries(d.symbols)){
      const chgCls=s.price_change_pct>=0?'chgp':'chgn';
      const chgTxt=(s.price_change_pct>=0?'+':'')+s.price_change_pct.toFixed(2)+'%';
      const tr=document.createElement('tr');
      if(sym===cur)tr.className='sel';
      tr.innerHTML=`<td class="dsym">${sym.replace('USDT','')}<br><span style="font-size:9px;color:var(--t3)">${s.has_position?'●'+s.position_side:''}</span></td>
        <td class="mn" style="font-size:10px;">$${Number(s.price).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:4})}</td>
        <td class="${chgCls}">${chgTxt}</td>
        <td><span class="sigb s${s.signal}">${s.signal}</span></td>`;
      tr.addEventListener('click',()=>{
        document.querySelectorAll('#rtbody tr').forEach(r=>r.classList.remove('sel'));
        tr.classList.add('sel');
        if(sym!==cur)lc(sym);
        if(tab!=='chart'){st('chart',document.getElementById('t-chart'));}
      });
      rb.appendChild(tr);
    }
    // Trade log
    const tb=document.getElementById('tlog');
    if(!d.trade_log||!d.trade_log.length){tb.innerHTML='<tr><td class="emp" colspan="7">No trades yet...</td></tr>';}
    else{tb.innerHTML=d.trade_log.map(t=>`<tr>
      <td class="dt mn">${t.time}</td><td class="dsym">${t.symbol}</td>
      <td class="${t.side==='Buy'?'dbuy':'dsell'}">${t.side==='Buy'?'▲BUY':'▼SELL'}</td>
      <td class="mn">$${Number(t.price).toFixed(2)}</td>
      <td class="mn">${Number(t.qty).toFixed(4)}</td>
      <td class="mn r">$${Number(t.sl).toFixed(4)}</td>
      <td class="mn g">$${Number(t.tp).toFixed(4)}</td></tr>`).join('');}
    // Signal history
    if(d.signal_history){
      const sigs=d.signal_history;
      document.getElementById('sg-tot').textContent=sigs.length;
      document.getElementById('sg-buy').textContent=sigs.filter(s=>s.signal==='BUY').length;
      document.getElementById('sg-sell').textContent=sigs.filter(s=>s.signal==='SELL').length;
      const sh=document.getElementById('sigh');
      if(!sigs.length){sh.innerHTML='<tr><td class="emp" colspan="8">No signals yet...</td></tr>';}
      else{sh.innerHTML=sigs.map(s=>`<tr>
        <td class="dt mn">${s.time}</td><td class="dsym">${s.symbol}</td>
        <td><span class="sigb s${s.signal}">${s.signal==='BUY'?'▲BUY':'▼SELL'}</span></td>
        <td class="mn">$${Number(s.price).toFixed(4)}</td>
        <td class="mn" style="color:${rc(s.rsi)}">${s.rsi}</td>
        <td class="mn ${s.macd>0?'g':'r'}">${s.macd}</td>
        <td>${s.traded?'<span class="g">✅ Yes</span>':'<span class="r">❌ No</span>'}</td>
        <td style="font-size:10px;color:var(--t3)">${s.reason||'—'}</td></tr>`).join('');}
    }
    document.getElementById('footer').textContent='Last updated: '+new Date().toLocaleTimeString()+' · Auto-refresh 5s';
  }catch(e){
    const b=document.getElementById('sbadge');b.className='badge boff';b.innerHTML='● Offline';
  }
}

async function fetchScan(){
  try{
    const d=await(await fetch('/api/scan')).json();
    if(!d.scanned_at)return;
    document.getElementById('scan-time').textContent='Last scan: '+d.scanned_at+' ('+d.duration_sec+'s)';
    document.getElementById('sc-total').textContent=d.total_scanned;
    document.getElementById('sc-sel').textContent=d.selected;
    const hasSig=d.results?d.results.filter(r=>r.signal!=='HOLD').length:0;
    document.getElementById('sc-sig').textContent=hasSig;
    document.getElementById('sc-dur').textContent=d.duration_sec+'s';
    const tb=document.getElementById('scan-table');
    if(!d.results||!d.results.length){tb.innerHTML='<tr><td class="emp" colspan="10">No results</td></tr>';return;}
    tb.innerHTML=d.results.map((r,i)=>`<tr>
      <td class="mn t3">${i+1}</td>
      <td class="dsym">${r.symbol}</td>
      <td class="mn">$${Number(r.price).toFixed(4)}</td>
      <td class="${r.change_pct>=0?'g':'r'} mn">${r.change_pct>=0?'+':''}${r.change_pct}%</td>
      <td class="mn" style="color:${rc(r.rsi)}">${r.rsi}</td>
      <td class="mn ${r.macd>0?'g':'r'}">${r.macd}</td>
      <td><span class="sigb s${r.signal}">${r.signal}</span></td>
      <td class="mn ${r.score>=5?'g':r.score>=3?'y':'t3'}">${r.score}</td>
      <td class="${r.selected?'scored-yes':'scored-no'}">${r.selected?'✅ Yes':'—'}</td>
      <td style="font-size:10px;color:var(--t3);max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${r.reasons}</td>
    </tr>`).join('');
  }catch(e){console.error(e);}
}

async function runScan(){
  const btn=document.getElementById('scan-btn');
  btn.disabled=true;btn.textContent='⏳ Scanning...';
  try{
    await fetch('/api/scan/run',{method:'POST'});
    await fetchScan();
  }catch(e){console.error(e);}
  btn.disabled=false;btn.textContent='🔍 Scan Now';
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
    if(!d.trades||!d.trades.length){jt.innerHTML='<tr><td class="emp" colspan="7">No trades yet</td></tr>';}
    else{jt.innerHTML=d.trades.map(t=>`<tr>
      <td class="dt mn">${t.time}</td><td class="dsym">${t.symbol}</td>
      <td class="${t.side==='Buy'?'dbuy':'dsell'}">${t.side==='Buy'?'▲':'▼'} ${t.side}</td>
      <td class="mn">$${Number(t.entry_price).toFixed(4)}</td>
      <td class="mn">${t.exit_price?'$'+Number(t.exit_price).toFixed(4):'<span style="color:var(--y)">OPEN</span>'}</td>
      <td>${fp(t.pnl)}</td>
      <td class="${t.status==='WIN'?'dwin':t.status==='LOSS'?'dloss':'dopn'}">${t.status}</td></tr>`).join('');}
  }catch(e){console.error(e);}
}

async function fetchSettings(){
  try{
    const d=await(await fetch('/api/settings')).json();
    const cr=k=>`<div class="cfg-r"><span class="cfg-k">${k[0]}</span><span class="cfg-v">${k[1]}</span></div>`;
    document.getElementById('cfg-trading').innerHTML=
      [['Timeframe',d.timeframe+'m'],['Trade USDT','$'+d.trade_usdt],
       ['Max Open Trades',d.max_open_trades]].map(cr).join('');
    document.getElementById('cfg-risk').innerHTML=
      [['Stop Loss',((d.stop_loss_pct||0)*100).toFixed(1)+'%'],
       ['Take Profit',((d.take_profit_pct||0)*100).toFixed(1)+'%']].map(cr).join('');
    const sc=document.getElementById('cfg-symbols');
    sc.innerHTML=(d.symbols||[]).map(s=>`<span style="background:var(--bbg);color:var(--b);
      border:1px solid #1a3a5c;padding:3px 8px;border-radius:4px;font-size:11px;font-weight:600;">${s}</span>`).join('');
    document.getElementById('cs-bybit').className='conn-status '+(d.api_key_set?'cs-ok':'cs-err');
    document.getElementById('cs-bybit').textContent=d.api_key_set?'Key Set':'Not Set';
    document.getElementById('cs-db').className='conn-status '+(d.db_set?'cs-ok':'cs-err');
    document.getElementById('cs-db').textContent=d.db_set?'URL Set':'Not Set';
    document.getElementById('cs-tg').className='conn-status '+(d.telegram_set?'cs-ok':'cs-err');
    document.getElementById('cs-tg').textContent=d.telegram_set?'Token Set':'Not Set';
  }catch(e){console.error(e);}
}

async function testConn(){
  ['bybit','db','tg'].forEach(k=>{
    document.getElementById('cs-'+k).className='conn-status cs-idle';
    document.getElementById('cs-'+k).textContent='Testing...';
    document.getElementById('cm-'+k).textContent='';
  });
  try{
    const d=await(await fetch('/api/test/connection',{method:'POST'})).json();
    const map={bybit:'bybit',database:'db',telegram:'tg'};
    for(const[key,res]of Object.entries(d)){
      const k=map[key];if(!k)continue;
      document.getElementById('cs-'+k).className='conn-status '+(res.ok?'cs-ok':'cs-err');
      document.getElementById('cs-'+k).textContent=res.ok?'✅ Connected':'❌ Failed';
      document.getElementById('cm-'+k).textContent=res.msg||'';
    }
  }catch(e){console.error(e);}
}

lc('BTCUSDT');fetchS();
setInterval(fetchS,5000);
setInterval(()=>{if(tab==='journal')fetchJ();if(tab==='scanner')fetchScan();},15000);
</script>
</body>
</html>""")

print('\n✅ All files updated!')
print('\nPowerShell commands:')
print('  python update_v2.py')
print('  python main.py')
print('  git add .')
print('  git commit -m "v2: scanner, signals, countdown, table watchlist, journal, settings"')
print('  git push')