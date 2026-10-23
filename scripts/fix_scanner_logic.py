import pathlib

file_path = pathlib.Path('scanner.py')
content = file_path.read_text(encoding='utf-8')

# স্ক্যানারের সিলেকশন লজিক ঠিক করা (যাতে HOLD থাকলে সিলেক্ট না হয়)
old_logic = '"selected": score >= 5 or sig != "HOLD"}'
new_logic = '"selected": (sig != "HOLD" and math_sig == sig)}'

if old_logic in content:
    content = content.replace(old_logic, new_logic)
    file_path.write_text(content, encoding='utf-8')
    print('\n[SUCCESS] Scanner selection logic fixed! (HOLD will not be selected)\n')
else:
    print('\n[INFO] Could not find the exact logic string. Checking for variations...\n')
    # Alternative fix if spacing is different
    if '"selected": score >= 5 or (sig != "HOLD" and math_sig == sig)' in content:
         print('[OK] Logic seems already correct or previously fixed.\n')
