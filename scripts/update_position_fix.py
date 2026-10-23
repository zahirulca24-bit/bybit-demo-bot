import pathlib

# ১. ব্যাকএন্ড আপডেট (Bybit API থেকে সরাসরি পজিশন নেওয়া)
app_path = pathlib.Path('dashboard/app.py')
app_content = app_path.read_text(encoding='utf-8')

new_pos_func = '''
@app.get("/api/position/{symbol}")
def get_position(symbol: str):
    from pybit.unified_trading import HTTP
    from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET
    try:
        s = HTTP(testnet=TESTNET, demo=DEMO_MODE, api_key=API_KEY, api_secret=API_SECRET)
        # Bybit API থেকে ওপেন পজিশন চেক করা
        r = s.get_positions(category="linear", symbol=symbol)
        pos_list = r.get("result", {}).get("list", [])

        if pos_list and float(pos_list[0].get("size", 0)) > 0:
            p = pos_list[0]
            return {
                "has_position": True,
                "side": p.get("side"),
                "entry": float(p.get("avgPrice", 0)),
                "sl": float(p.get("stopLoss", 0)) if p.get("stopLoss") else 0.0,
                "tp": float(p.get("takeProfit", 0)) if p.get("takeProfit") else 0.0
            }
        return {"has_position": False}
    except Exception as e:
        return {"has_position": False, "error": str(e)}
'''

# পুরনো ফাংশনটি রিপ্লেস করা
import re
app_content = re.sub(r'@app\.get\("/api/position/\{symbol\}"\).*?(?=@app|$)', new_pos_func + '\n', app_content, flags=re.DOTALL)
app_path.write_text(app_content, encoding='utf-8')
print('[SUCCESS] Backend updated to fetch live position from Bybit!')

# ২. ফ্রন্টএন্ড আপডেট (লাইন পজিশনিং আরও নিখুঁত করা)
html_path = pathlib.Path('dashboard/static/index.html')
html_content = html_path.read_text(encoding='utf-8')

# যদি SL বা TP 0.0 থাকে, তবে লাইনটি হাইড করার লজিক
old_js = """      document.getElementById('line-tp').innerHTML = `TP: $${d.tp.toFixed(4)}`;
      document.getElementById('line-entry').innerHTML = `ENTRY: $${d.entry.toFixed(4)} (${d.side})`;
      document.getElementById('line-sl').innerHTML = `SL: $${d.sl.toFixed(4)}`;

      // লাইনের পজিশন ক্যালকুলেশন (উপর থেকে নিচে)
      const maxP = Math.max(d.tp, d.entry, d.sl);
      const minP = Math.min(d.tp, d.entry, d.sl);
      const range = maxP - minP;

      if (range > 0) {
        // চার্টের ওপরের অংশ ১০% থেকে নিচের অংশ ৯০% পর্যন্ত লাইনগুলো ছড়াবে
        document.getElementById('line-tp').style.top = `${10 + ((maxP - d.tp) / range) * 80}%`;
        document.getElementById('line-entry').style.top = `${10 + ((maxP - d.entry) / range) * 80}%`;
        document.getElementById('line-sl').style.top = `${10 + ((maxP - d.sl) / range) * 80}%`;
      }"""

new_js = """      const lineTp = document.getElementById('line-tp');
      const lineSl = document.getElementById('line-sl');

      if (d.tp > 0) { lineTp.style.display = 'block'; lineTp.innerHTML = `TP: $${d.tp.toFixed(4)}`; }
      else { lineTp.style.display = 'none'; }

      if (d.sl > 0) { lineSl.style.display = 'block'; lineSl.innerHTML = `SL: $${d.sl.toFixed(4)}`; }
      else { lineSl.style.display = 'none'; }

      document.getElementById('line-entry').innerHTML = `ENTRY: $${d.entry.toFixed(4)} (${d.side})`;

      // লাইনের পজিশন ক্যালকুলেশন
      const prices = [d.entry];
      if (d.tp > 0) prices.push(d.tp);
      if (d.sl > 0) prices.push(d.sl);

      const maxP = Math.max(...prices);
      const minP = Math.min(...prices);
      const range = maxP - minP;

      if (range > 0) {
        if (d.tp > 0) lineTp.style.top = `${10 + ((maxP - d.tp) / range) * 80}%`;
        document.getElementById('line-entry').style.top = `${10 + ((maxP - d.entry) / range) * 80}%`;
        if (d.sl > 0) lineSl.style.top = `${10 + ((maxP - d.sl) / range) * 80}%`;
      }"""

html_content = html_content.replace(old_js, new_js)
html_path.write_text(html_content, encoding='utf-8')
print('[SUCCESS] Frontend overlay logic updated!')
