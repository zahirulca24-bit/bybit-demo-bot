import pathlib
import re

html_path = pathlib.Path('dashboard/static/index.html')
content = html_path.read_text(encoding='utf-8')

# ১. চার্টের উপরে নতুন প্যানেল ডিজাইন যোগ করা
old_chdr = '<div id="tv-c" style="flex:1;height:100%;"></div>'
new_chdr = '''
    <!-- Position Info Overlay -->
    <div id="pos-panel" style="position:absolute; top:10px; left:10px; z-index:100; background:rgba(13, 17, 23, 0.9); border:1px solid var(--bd2); border-radius:6px; padding:10px 15px; display:none; box-shadow:0 4px 6px rgba(0,0,0,0.3); backdrop-filter:blur(4px);">
      <div style="font-size:11px; font-weight:600; margin-bottom:5px; color:var(--t);" id="pos-title">POSITION</div>
      <div style="display:flex; gap:15px; font-size:11px; font-family:monospace;">
         <div><span style="color:var(--t3)">Entry:</span> <span id="pos-entry" style="color:var(--b); font-weight:bold;">-</span></div>
         <div><span style="color:var(--t3)">SL:</span> <span id="pos-sl" style="color:var(--r); font-weight:bold;">-</span></div>
         <div><span style="color:var(--t3)">TP:</span> <span id="pos-tp" style="color:var(--g); font-weight:bold;">-</span></div>
         <div><span style="color:var(--t3)">PnL:</span> <span id="pos-pnl" style="font-weight:bold;">-</span></div>
      </div>
    </div>
    <div id="tv-c" style="flex:1;height:100%;"></div>'''

content = content.replace('<div id="tv-c" style="flex:1;height:100%;"></div>', new_chdr)
# রিলেটিভ পজিশন নিশ্চিত করা চার্ট কন্টেইনারের
content = content.replace('<div style="position:relative;flex:1;min-height:400px;display:flex;flex-direction:column;">', '<div style="position:relative;flex:1;min-height:400px;display:flex;flex-direction:column; overflow:hidden;">')


# ২. নতুন জাভাস্ক্রিপ্ট লজিক বসানো
new_js = '''
let currentPos = null;

async function fetchPosition(sym) {
  try {
    const d = await(await fetch(`/api/position/${sym}`)).json();
    const panel = document.getElementById('pos-panel');

    if (d.has_position) {
      panel.style.display = 'block';
      const sideColor = d.side === 'Buy' ? 'var(--g)' : 'var(--r)';
      document.getElementById('pos-title').innerHTML = `<span style="color:${sideColor}">●</span> ${d.side.toUpperCase()} ${sym}`;

      document.getElementById('pos-entry').textContent = '$' + d.entry.toFixed(4);
      document.getElementById('pos-sl').textContent = d.sl > 0 ? '$' + d.sl.toFixed(4) : 'None';
      document.getElementById('pos-tp').textContent = d.tp > 0 ? '$' + d.tp.toFixed(4) : 'None';

      const pnlEl = document.getElementById('pos-pnl');
      pnlEl.textContent = (d.pnl >= 0 ? '+' : '') + '$' + d.pnl.toFixed(2);
      pnlEl.style.color = d.pnl >= 0 ? 'var(--g)' : 'var(--r)';
    } else {
      panel.style.display = 'none';
    }
  } catch(e) { console.error(e); }
}
'''

# পুরনো fetchPosition ফাংশনটি খুঁজে বের করে রিপ্লেস করা
content = re.sub(r'let currentPos = null;.*?async function fetchS\(\)', new_js + '\nasync function fetchS()', content, flags=re.DOTALL)

# চার্ট পরিবর্তন হলে প্যানেল আপডেট করা
if 'fetchPosition(sym);' not in content:
    content = content.replace("new TradingView.widget({container_id:'tv',autosize:true,", "fetchPosition(sym);\n  new TradingView.widget({container_id:'tv',autosize:true,")

# প্রতি ৩ সেকেন্ডে PnL আপডেট করা
content = content.replace("setInterval(() => { if(cur) fetchPosition(cur); }, 5000);", "setInterval(() => { if(cur) fetchPosition(cur); }, 3000);")

html_path.write_text(content, encoding='utf-8')
print('\\n[SUCCESS] Frontend Position Panel integrated!\\n')
