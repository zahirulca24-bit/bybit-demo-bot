import pathlib
import re

html_path = pathlib.Path('dashboard/static/index.html')
content = html_path.read_text(encoding='utf-8')

# ১. পুরনো HTML ওভারলে রিমুভ করা
old_chart_div = '<div style="position:relative;flex:1;min-height:400px;display:flex;flex-direction:column;">'
new_chart_div = '<div style="position:relative;flex:1;min-height:400px;display:flex;flex-direction:column;">'
# শুধু tv-c রেখে বাকি ওভারলে মুছে ফেলা
content = re.sub(r'<div id="pos-overlay".*?</div>\s*<div id="tv-c"', '<div id="tv-c"', content, flags=re.DOTALL)
content = content.replace('<div id="tv-c" style="flex:1;"></div>', '<div id="tv-c" style="flex:1;height:100%;"></div>')

# ২. TradingView Widget তৈরি করার সময় global variable এ সেভ করা
old_lc = "new TradingView.widget({container_id:'tv',autosize:true,"
new_lc = "window.tvWidget = new TradingView.widget({container_id:'tv',autosize:true,"
content = content.replace(old_lc, new_lc)

# ৩. নতুন জাভাস্ক্রিপ্ট লজিক বসানো (TradingView Shape API)
old_js = "let currentPos = null;\n\nasync function fetchPosition(sym) {"
new_js = '''
let currentPos = null;

async function fetchPosition(sym) {
  try {
    const d = await(await fetch(`/api/position/${sym}`)).json();
    if (window.tvWidget && window.tvWidget.chart) {
      const chart = window.tvWidget.chart();
      chart.removeAllShapes(); // আগের লাইনগুলো মুছে ফেলা

      if (d.has_position) {
        // Entry Line (Blue)
        chart.createShape({ time: Math.floor(Date.now() / 1000) }, {
          shape: 'horizontal_line',
          text: 'ENTRY: $' + d.entry.toFixed(4),
          lock: true,
          disableSelection: true,
          overrides: { lineStyle: 0, lineColor: '#58a6ff', lineWidth: 2, showLabel: true, textColor: '#58a6ff' }
        });

        // TP Line (Green)
        if (d.tp > 0) {
          chart.createShape({ time: Math.floor(Date.now() / 1000) }, {
            shape: 'horizontal_line',
            text: 'TP: $' + d.tp.toFixed(4),
            lock: true,
            disableSelection: true,
            overrides: { lineStyle: 2, lineColor: '#3fb950', lineWidth: 1, showLabel: true, textColor: '#3fb950' }
          });
        }

        // SL Line (Red)
        if (d.sl > 0) {
          chart.createShape({ time: Math.floor(Date.now() / 1000) }, {
            shape: 'horizontal_line',
            text: 'SL: $' + d.sl.toFixed(4),
            lock: true,
            disableSelection: true,
            overrides: { lineStyle: 2, lineColor: '#f85149', lineWidth: 1, showLabel: true, textColor: '#f85149' }
          });
        }
      }
    }
  } catch(e) { console.error(e); }
}
'''

# পুরনো fetchPosition ফাংশন রিপ্লেস করা
content = re.sub(r'let currentPos = null;.*?async function fetchS\(\)', new_js + '\nasync function fetchS()', content, flags=re.DOTALL)

html_path.write_text(content, encoding='utf-8')
print('\\n[SUCCESS] TradingView Shapes integrated successfully!\\n')
