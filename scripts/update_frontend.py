import pathlib

html_path = pathlib.Path('dashboard/static/index.html')
content = html_path.read_text(encoding='utf-8')

# ১. Tab Menu-তে নতুন পেজ যুক্ত করা
tab_old = '<div class="tab" id="t-journal" onclick="st(\'journal\',this)">📒 Journal</div>'
tab_new = tab_old + '\\n  <div class="tab" id="t-math" onclick="st(\'math\',this)">🧮 Math Predict</div>'
if tab_old in content and 't-math' not in content:
    content = content.replace(tab_old, tab_new)

# ২. নতুন পেজের HTML ব্লক যুক্ত করা (Journal-এর পরে)
html_old = '<!-- Settings Tab -->'
html_new = '''<!-- Math Predict Tab -->
  <div class="tc" id="tc-math">
    <div class="jwrap">
      <div class="jg">
        <div class="jc"><div class="jcl">Total Scanned</div><div class="jcv b" id="m-total">0</div></div>
        <div class="jc"><div class="jcl">Math Trend UP</div><div class="jcv g" id="m-up">0</div></div>
        <div class="jc"><div class="jcl">Math Trend DOWN</div><div class="jcv r" id="m-down">0</div></div>
        <div class="jc"><div class="jcl">Last Updated</div><div class="jcv" id="m-time" style="font-size:14px">--:--</div></div>
      </div>
      <div class="sc">
        <div class="sch"><span class="dot"></span>Mathematical Prediction (Linear Regression - Past 20 Candles)</div>
        <table>
          <thead><tr><th>#</th><th>Symbol</th><th>Price</th><th>Math Trend</th><th>Predicted Change</th><th>Tech Signal</th><th>Status</th></tr></thead>
          <tbody id="math-table"><tr><td class="emp" colspan="7">Click Scan Now in Scanner tab to get Math Predictions...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>
  <!-- Settings Tab -->'''
if html_old in content and 'tc-math' not in content:
    content = content.replace(html_old, html_new)

# ৩. Javascript-এ ডেটা পপুলেট করার লজিক যুক্ত করা
js_old = "async function fetchSettings(){"
js_new = '''async function fetchMath() {
  try {
    const d = await(await fetch('/api/scan')).json();
    if(!d.results) return;

    document.getElementById('m-total').textContent = d.total_scanned;
    document.getElementById('m-up').textContent = d.results.filter(r => r.math_signal === 'BUY').length;
    document.getElementById('m-down').textContent = d.results.filter(r => r.math_signal === 'SELL').length;
    document.getElementById('m-time').textContent = d.scanned_at.split(' ')[1] || '--:--';

    const tb = document.getElementById('math-table');
    tb.innerHTML = d.results.map((r, i) => `
      <tr>
        <td class="mn t3">${i+1}</td>
        <td class="dsym">${r.symbol}</td>
        <td class="mn">$${Number(r.price).toFixed(4)}</td>
        <td><span class="sigb s${r.math_signal}">${r.math_signal}</span></td>
        <td class="mn ${r.math_pct > 0 ? 'g' : r.math_pct < 0 ? 'r' : 't3'}">${r.math_pct > 0 ? '+' : ''}${r.math_pct}%</td>
        <td><span class="sigb s${r.signal}">${r.signal}</span></td>
        <td>${r.selected ? '<span class="scored-yes">✅ Trade Ready</span>' : '<span class="scored-no">Skipped</span>'}</td>
      </tr>
    `).join('');
  } catch(e) { console.error(e); }
}

async function fetchSettings(){'''
if js_old in content and 'fetchMath' not in content:
    content = content.replace(js_old, js_new)

# ৪. পেজ চেঞ্জের সময় fetchMath কল করা
st_old = "if(t==='settings')fetchSettings();"
st_new = "if(t==='settings')fetchSettings();\\n  if(t==='math')fetchMath();"
if st_old in content and "if(t==='math')fetchMath();" not in content:
    content = content.replace(st_old, st_new)

# সেভ করা
html_path.write_text(content, encoding='utf-8')
print('\\n[SUCCESS] index.html updated with Math Predict Tab!\\n')
