
"""Read-only Bybit and Neon live dashboard."""

from contextlib import closing
from decimal import Decimal
from html import escape
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from config.settings import (
    API_KEY, API_SECRET, DEMO_MODE, TESTNET,
)
from database import get_conn
from dashboard.state import bot_state

router = APIRouter()


def number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def live_account():
    from pybit.unified_trading import HTTP

    session = HTTP(
        testnet=TESTNET,
        demo=DEMO_MODE,
        api_key=API_KEY,
        api_secret=API_SECRET,
    )

    wallet = session.get_wallet_balance(accountType="UNIFIED")
    if wallet.get("retCode") != 0:
        raise RuntimeError(
            "Bybit wallet error: " + str(wallet.get("retMsg"))
        )

    accounts = wallet.get("result", {}).get("list", [])
    if not accounts:
        raise RuntimeError("Bybit wallet response has no accounts")

    account = accounts[0]
    coins = account.get("coin", [])
    usdt = next(
        (coin for coin in coins if coin.get("coin") == "USDT"),
        {},
    )

    positions = session.get_positions(
        category="linear",
        settleCoin="USDT",
        limit=200,
    )
    if positions.get("retCode") != 0:
        raise RuntimeError(
            "Bybit position error: " + str(positions.get("retMsg"))
        )

    result = positions.get("result", {})
    position_list = result.get("list", [])

    active = []
    for p in position_list:
        if number(p.get("size")) <= 0:
            continue

        active.append({
            "symbol": p.get("symbol"),
            "side": p.get("side"),
            "qty": number(p.get("size")),
            "entry": number(p.get("avgPrice")),
            "mark_price": number(p.get("markPrice")),
            "unrealized_pnl": number(p.get("unrealisedPnl")),
            "stop_loss": number(p.get("stopLoss")),
            "take_profit": number(p.get("takeProfit")),
        })

    return {
        "equity_usd": number(account.get("totalEquity")),
        "available_usd": number(
            account.get("totalAvailableBalance")
        ),
        "wallet_usdt": number(usdt.get("walletBalance")),
        "unrealized_pnl": sum(
            p["unrealized_pnl"] for p in active
        ),
        "open_count": len(active),
        "positions": active,
        "more_positions_possible": bool(result.get("nextPageCursor")),
    }


def live_trades():
    with closing(get_conn()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, time, symbol, side,
                       entry_price, qty, exit_price,
                       pnl, status
                FROM trades
                ORDER BY time DESC, id DESC
                LIMIT 50
            """)
            rows = cur.fetchall()

    trades = []
    for t in rows:
        trades.append({
            "id": t["id"],
            "time": str(t["time"])[:19],
            "symbol": t["symbol"],
            "side": t["side"],
            "entry_price": number(t["entry_price"]),
            "qty": number(t["qty"]),
            "exit_price": (
                number(t["exit_price"])
                if t["exit_price"] is not None else None
            ),
            "pnl": (
                number(t["pnl"])
                if t["pnl"] is not None else None
            ),
            "status": t["status"],
        })

    with closing(get_conn()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE status = 'OPEN'
                    ) AS db_open,
                    COUNT(*) FILTER (
                        WHERE status IN ('WIN', 'LOSS')
                    ) AS closed_count,
                    COALESCE(
                        SUM(pnl) FILTER (
                            WHERE status IN ('WIN', 'LOSS')
                        ), 0
                    ) AS realized_pnl
                FROM trades
            """)
            stats = dict(cur.fetchone())

    return {
        "db_open": int(stats["db_open"]),
        "closed_count": int(stats["closed_count"]),
        "realized_pnl": number(stats["realized_pnl"]),
        "trades": trades,
    }


@router.get("/api/live")
def live_data():
    result = {
        "bot_running": bot_state.running,
        "account": None,
        "trading_history": None,
        "errors": {},
    }

    try:
        result["account"] = live_account()
    except Exception as exc:
        result["errors"]["bybit"] = (
            f"{type(exc).__name__}: {exc}"
        )

    try:
        result["trading_history"] = live_trades()
    except Exception as exc:
        result["errors"]["neon"] = (
            f"{type(exc).__name__}: {exc}"
        )

    return result


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bybit Demo Bot — Live Monitor</title>
<style>
:root {color-scheme:dark}
body{margin:0;background:#0b1120;color:#e2e8f0;
font:14px system-ui,Segoe UI,sans-serif}
main{max-width:1220px;margin:auto;padding:28px}
header{display:flex;justify-content:space-between;
align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:24px;margin:0}
a{color:#93c5fd;text-decoration:none}
small,.muted{color:#94a3b8}
.cards{display:grid;grid-template-columns:
repeat(auto-fit,minmax(175px,1fr));gap:14px;margin:24px 0}
.card,.panel{background:#151f31;border:1px solid #29354b;
border-radius:14px;padding:18px}
.value{font-size:24px;font-weight:700;margin-top:10px}
.panel{margin-top:20px;overflow-x:auto}
h2{font-size:17px;margin:0 0 16px}
table{border-collapse:collapse;width:100%;min-width:650px}
td,th{padding:12px;text-align:left;border-bottom:
1px solid #29354b;white-space:nowrap}
th{color:#94a3b8;font-weight:500}
.positive{color:#4ade80}
.negative{color:#fb7185}
.error{color:#fca5a5;white-space:pre-wrap}
button{background:#2563eb;border:0;border-radius:8px;
padding:10px 16px;color:white;cursor:pointer}
</style>
</head>
<body>
<main>
<header>
<div><h1>Bybit Demo Bot — Live Monitor</h1>
<small>Read-only · Bybit Demo + Neon PostgreSQL</small></div>
<div><a href="/">Original Dashboard</a> &nbsp;
<button onclick="refresh()">Refresh Now</button></div>
</header>
<p id="status" class="muted">Loading live data...</p>
<div id="errors" class="error"></div>

<section class="cards">
<div class="card">Account Equity<div id="equity" class="value">—</div></div>
<div class="card">Available Balance<div id="available" class="value">—</div></div>
<div class="card">Wallet USDT<div id="wallet" class="value">—</div></div>
<div class="card">Unrealized PnL<div id="unrealized" class="value">—</div></div>
<div class="card">Realized PnL<div id="realized" class="value">—</div></div>
<div class="card">Open Positions<div id="open" class="value">—</div></div>
</section>

<section class="panel"><h2>Live Bybit Positions</h2>
<table><thead><tr>
<th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th>
<th>Mark</th><th>Unrealized PnL</th><th>SL</th><th>TP</th>
</tr></thead><tbody id="positions"></tbody></table></section>

<section class="panel"><h2>Neon Trade History — Latest 50</h2>
<table><thead><tr>
<th>ID</th><th>Time</th><th>Symbol</th><th>Side</th>
<th>Entry</th><th>Qty</th><th>Exit</th><th>PnL</th><th>Status</th>
</tr></thead><tbody id="trades"></tbody></table></section>
</main>
<script>
const $ = id => document.getElementById(id);
const fmt = (v, digits=2) => v == null ? "—" :
  Number(v).toLocaleString(undefined,{maximumFractionDigits:digits});
function value(id,v,digits=2){
  $(id).textContent=v==null?"—":fmt(v,digits);
}
function renderRows(id,rows,fields,pnlIndex){
  const body=$(id);
  body.replaceChildren();
  if(!rows.length){
    const tr=document.createElement("tr");
    const td=document.createElement("td");
    td.colSpan=fields.length;
    td.textContent="No records";
    tr.appendChild(td);body.appendChild(tr);return;
  }
  for(const item of rows){
    const tr=document.createElement("tr");
    fields.forEach((field,i)=>{
      const td=document.createElement("td");
      let v=item[field];
      td.textContent=typeof v==="number" ? fmt(v,8) : (v??"—");
      if(i===pnlIndex && v!=null){
        td.className=Number(v)>=0?"positive":"negative";
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  }
}
let loading=false;
async function refresh(){
  if(loading)return;
  loading=true;
  try{
    const r=await fetch("/api/live",{cache:"no-store"});
    if(!r.ok)throw new Error("Dashboard API HTTP "+r.status);
    const d=await r.json();
    const a=d.account;
    const h=d.trading_history;
    const errors=Object.entries(d.errors||{})
      .map(([key,msg])=>key.toUpperCase()+": "+msg);
    $("errors").textContent=errors.join("\\n");
    $("status").textContent=
      "Bot: "+(d.bot_running?"RUNNING":"NOT RUNNING")+
      " · Updated "+new Date().toLocaleTimeString()+
      (errors.length?" · PARTIAL DATA":" · Connected");
    value("equity",a?.equity_usd);
    value("available",a?.available_usd);
    value("wallet",a?.wallet_usdt);
    value("unrealized",a?.unrealized_pnl);
    value("realized",h?.realized_pnl);
    value("open",a?.open_count,0);
    renderRows("positions",a?.positions||[],
      ["symbol","side","qty","entry","mark_price",
       "unrealized_pnl","stop_loss","take_profit"],5);
    renderRows("trades",h?.trades||[],
      ["id","time","symbol","side","entry_price","qty",
       "exit_price","pnl","status"],7);
    if(a?.more_positions_possible){
      $("errors").textContent+="\\nMore positions may exist beyond API page 1.";
    }
  }catch(e){
    $("status").textContent="Dashboard connection error";
    $("errors").textContent=String(e);
  }finally{loading=false}
}
refresh();
setInterval(refresh,15000);
</script></body></html>
"""


@router.get("/live", response_class=HTMLResponse)
def live_page():
    return HTMLResponse(PAGE)
