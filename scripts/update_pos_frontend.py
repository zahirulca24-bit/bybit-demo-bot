import pathlib

file_path = pathlib.Path('dashboard/static/index.html')
content = file_path.read_text(encoding='utf-8')

# ১. চার্টের ভেতরে ওভারলে ডিভ যোগ করা
chart_old = '<div id="tv-c"></div>'
chart_new = '''<div style="position:relative;flex:1;min-height:400px;display:flex;flex-direction:column;">
      <div id="pos-overlay" style="position:absolute;top:0;left:0;right:0;bottom:0;pointer-events:none;z-index:10;display:none;">
         <div id="line-tp" style="position:absolute;width:100%;border-top:1px dashed var(--g);color:var(--g);font-size:10px;text-align:right;padding-right:10px;font-family:monospace;">TP</div>
         <div id="line-entry" style="position:absolute;width:100%;border-top:1px solid var(--b);color:var(--b);font-size:10px;text-align:right;padding-right:10px;font-family:monospace;">ENTRY</div>
         <div id="line-sl" style="position:absolute;width:100%;border-top:1px dashed var(--r);color:var(--r);font-size:10px;text-align:right;padding-right:10px;font-family:monospace;">SL</div>
      </div>
      <div id="tv-c" style="flex:1;"></div>
    </div>'''
if 'pos-overlay' not in content:
    content = content.replace(chart_old, chart_new)

# ২. পজিশন লাইন লোড করার জাভাস্ক্রিপ্ট
js_new = '''
let currentPos = null;

async function fetchPosition(sym) {
  try {
    const d = await(await fetch(`/api/position/${sym}`)).json();
    const ov = document.getElementById('pos-overlay');
    if (d.has_position) {
      currentPos = d;
      ov.style.display = 'block';

      document.getElementById('line-tp').innerHTML = `TP: $${d.tp.toFixed(4)}`;
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
      }
    } else {
      currentPos = null;
      ov.style.display = 'none';
    }
  } catch(e) { console.error(e); }
}
'''

if 'async function fetchPosition' not in content:
    content = content.replace('async function fetchS(){', js_new + '\nasync function fetchS(){')

# ৩. চার্ট চেঞ্জ হলে পজিশন কল করা
lc_old = "new TradingView.widget({container_id:'tv',autosize:true,"
lc_new = "fetchPosition(sym);\n  new TradingView.widget({container_id:'tv',autosize:true,"
if 'fetchPosition(sym);' not in content:
    content = content.replace(lc_old, lc_new)

# ৪. প্রতি ৫ সেকেন্ডে পজিশন আপডেট করা
if 'setInterval(() => { if(cur) fetchPosition(cur); }, 5000);' not in content:
    content = content.replace('setInterval(fetchS,5000);', 'setInterval(fetchS,5000);\nsetInterval(() => { if(cur) fetchPosition(cur); }, 5000);')

file_path.write_text(content, encoding='utf-8')
print('\n[SUCCESS] Frontend updated with Position Overlay!\n')
