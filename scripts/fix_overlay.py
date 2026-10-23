import pathlib

html_path = pathlib.Path('dashboard/static/index.html')
content = html_path.read_text(encoding='utf-8')

# ওভারলে স্টাইল ফিক্স (লাইনগুলো ডান পাশে আনতে)
old_overlay = '''<div id="pos-overlay" style="position:absolute;top:0;left:0;right:0;bottom:0;pointer-events:none;z-index:10;display:none;">
         <div id="line-tp" style="position:absolute;width:100%;border-top:1px dashed var(--g);color:var(--g);font-size:10px;text-align:right;padding-right:10px;font-family:monospace;">TP</div>
         <div id="line-entry" style="position:absolute;width:100%;border-top:1px solid var(--b);color:var(--b);font-size:10px;text-align:right;padding-right:10px;font-family:monospace;">ENTRY</div>
         <div id="line-sl" style="position:absolute;width:100%;border-top:1px dashed var(--r);color:var(--r);font-size:10px;text-align:right;padding-right:10px;font-family:monospace;">SL</div>
      </div>'''

new_overlay = '''<div id="pos-overlay" style="position:absolute;top:0;left:0;right:60px;bottom:0;pointer-events:none;z-index:10;display:none;">
         <div id="line-tp" style="position:absolute;width:100%;border-top:1px dashed var(--g);color:var(--g);font-size:10px;text-align:right;padding-right:5px;font-family:monospace;">TP</div>
         <div id="line-entry" style="position:absolute;width:100%;border-top:1px solid var(--b);color:var(--b);font-size:10px;text-align:right;padding-right:5px;font-family:monospace;">ENTRY</div>
         <div id="line-sl" style="position:absolute;width:100%;border-top:1px dashed var(--r);color:var(--r);font-size:10px;text-align:right;padding-right:5px;font-family:monospace;">SL</div>
      </div>'''

content = content.replace(old_overlay, new_overlay)

# জাভাস্ক্রিপ্ট লজিক আপডেট (যদি পজিশন ক্লোজ হয়ে যায় তবে লাইন হাইড করা)
old_js = """      if (range > 0) {
        if (d.tp > 0) lineTp.style.top = `${10 + ((maxP - d.tp) / range) * 80}%`;
        document.getElementById('line-entry').style.top = `${10 + ((maxP - d.entry) / range) * 80}%`;
        if (d.sl > 0) lineSl.style.top = `${10 + ((maxP - d.sl) / range) * 80}%`;
      }"""

new_js = """      if (range > 0) {
        if (d.tp > 0) lineTp.style.top = `${10 + ((maxP - d.tp) / range) * 80}%`;
        document.getElementById('line-entry').style.top = `${10 + ((maxP - d.entry) / range) * 80}%`;
        if (d.sl > 0) lineSl.style.top = `${10 + ((maxP - d.sl) / range) * 80}%`;
      } else {
        // যদি সব প্রাইস সমান হয়
        document.getElementById('line-entry').style.top = '50%';
      }"""

content = content.replace(old_js, new_js)

html_path.write_text(content, encoding='utf-8')
print('\n[SUCCESS] Overlay lines fixed to the right side!\n')
