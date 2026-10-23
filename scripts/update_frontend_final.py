import pathlib

file_path = pathlib.Path('dashboard/static/index.html')
content = file_path.read_text(encoding='utf-8')

# ১. সাইডবার টগল বাটন যুক্ত করা
if 'id="toggle-rp"' not in content:
    content = content.replace(
        '<div class="rp">',
        '<button id="toggle-rp" onclick="toggleSidebar()" style="position:absolute;right:240px;top:100px;z-index:99;background:var(--bg3);border:1px solid var(--bd2);color:var(--t);cursor:pointer;padding:5px;border-radius:4px;">▶</button>\n<div class="rp" id="right-panel">'
    )

# ২. ডেইলি স্ট্যাটস সেকশন যুক্ত করা (Journal ট্যাবে)
daily_html = '''
<div class="jg" style="margin-bottom:20px; border-bottom:1px solid var(--bd); padding-bottom:20px;">
  <div class="jc"><div class="jcl">Today Net PnL</div><div class="jcv" id="d-net">$0.00</div></div>
  <div class="jc"><div class="jcl">Total Trades</div><div class="jcv b" id="d-total">0</div></div>
  <div class="jc"><div class="jcl">Buys / Sells</div><div class="jcv"><span class="g" id="d-buy">0</span> / <span class="r" id="d-sell">0</span></div></div>
  <div class="jc"><div class="jcl">Wins / Losses</div><div class="jcv"><span class="g" id="d-win">0</span> / <span class="r" id="d-loss">0</span></div></div>
</div>
'''
if 'd-net' not in content:
    content = content.replace('<div class="jg">', daily_html + '<div class="jg">', 1)

# ৩. Click to Chart ফাংশন যোগ করা
js_new = '''
function toggleSidebar() {
  const rp = document.getElementById('right-panel');
  const btn = document.getElementById('toggle-rp');
  if (rp.style.display === 'none') {
    rp.style.display = 'flex';
    btn.innerHTML = '▶';
    btn.style.right = '240px';
  } else {
    rp.style.display = 'none';
    btn.innerHTML = '◀';
    btn.style.right = '0px';
  }
}

function openChart(sym) {
  if (tab !== 'chart') {
    st('chart', document.getElementById('t-chart'));
  }
  lc(sym);
}

async function fetchRealBalance() {
  try {
    const d = await(await fetch('/api/real_balance')).json();
    if (d.balance !== undefined) {
      document.getElementById('hbal').textContent = '$' + Number(d.balance).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
  } catch(e) {}
}

async function fetchDailyStats() {
  try {
    const d = await(await fetch('/api/daily_stats')).json();
    document.getElementById('d-net').textContent = (d.net_pnl >= 0 ? '+' : '') + '$' + Number(d.net_pnl).toFixed(2);
    document.getElementById('d-net').className = 'jcv ' + (d.net_pnl >= 0 ? 'g' : 'r');
    document.getElementById('d-total').textContent = d.total;
    document.getElementById('d-buy').textContent = d.buys;
    document.getElementById('d-sell').textContent = d.sells;
    document.getElementById('d-win').textContent = d.wins;
    document.getElementById('d-loss').textContent = d.losses;
  } catch(e) {}
}
'''

if 'function toggleSidebar' not in content:
    content = content.replace('async function fetchS(){', js_new + '\nasync function fetchS(){')

# ৪. Scanner-এ row click যোগ করা
scanner_js_old = "tb.innerHTML=d.results.map((r,i)=>`<tr>"
scanner_js_new = "tb.innerHTML=d.results.map((r,i)=>`<tr style='cursor:pointer' onclick=\"openChart('${r.symbol}')\">"
if 'openChart(' not in content[content.find('async function fetchScan'):]:
    content = content.replace(scanner_js_old, scanner_js_new)

# ৫. Math Predict-এ row click যোগ করা
math_js_old = "tb.innerHTML = d.results.map((r, i) => `\n      <tr>"
math_js_new = "tb.innerHTML = d.results.map((r, i) => `\n      <tr style='cursor:pointer' onclick=\"openChart('${r.symbol}')\">"
if 'openChart(' not in content[content.find('async function fetchMath'):]:
    content = content.replace(math_js_old, math_js_new)

# ৬. ফাংশনগুলো কল করা
if 'fetchRealBalance();' not in content:
    content = content.replace("lc('BTCUSDT');fetchS();", "lc('BTCUSDT');fetchS();fetchRealBalance();")
if 'fetchDailyStats();' not in content:
    content = content.replace('setInterval(fetchS,5000);', 'setInterval(fetchS,5000);\nsetInterval(fetchRealBalance, 60000);\nsetInterval(fetchDailyStats, 15000);\nfetchDailyStats();')

# ৭. TradingView ড্রয়িং টুলস এনাবল করা
content = content.replace("enable_publishing:false,save_image:false,", "enable_publishing:false,save_image:false,withdateranges:true,hide_side_toolbar:false,allow_symbol_change:true,")

file_path.write_text(content, encoding='utf-8')
print('\n[SUCCESS] Frontend updated with all requested features!\n')
