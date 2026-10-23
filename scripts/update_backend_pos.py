import pathlib
import re

app_path = pathlib.Path('dashboard/app.py')
content = app_path.read_text(encoding='utf-8')

new_func = '''
@app.get("/api/position/{symbol}")
def get_position(symbol: str):
    from pybit.unified_trading import HTTP
    from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET
    try:
        s = HTTP(testnet=TESTNET, demo=DEMO_MODE, api_key=API_KEY, api_secret=API_SECRET)
        r = s.get_positions(category="linear", symbol=symbol)
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
    except Exception as e:
        return {"has_position": False, "error": str(e)}
'''
content = re.sub(r'@app\.get\("/api/position/\{symbol\}"\).*?(?=@app|$)', new_func + '\n', content, flags=re.DOTALL)
app_path.write_text(content, encoding='utf-8')
print('[SUCCESS] Backend updated with PnL.')
