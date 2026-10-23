import pathlib

file_path = pathlib.Path('scanner.py')
content = file_path.read_text(encoding='utf-8')

# স্ক্যানারের সিলেকশন লজিক কঠোর করা (শুধু Tech এবং Math মিললেই Selected হবে)
old_logic = '"selected": score >= 5 or (sig != "HOLD" and math_sig == sig)}'
new_logic = '"selected": (sig != "HOLD" and math_sig == sig)}'

if old_logic in content:
    content = content.replace(old_logic, new_logic)
    print('\n[SUCCESS] Logic fixed strictly!')
elif '"selected": score >= 5 or sig != "HOLD"}' in content:
    content = content.replace('"selected": score >= 5 or sig != "HOLD"}', '"selected": (sig != "HOLD" and math_sig == sig)}')
    print('\n[SUCCESS] Logic fixed strictly!')
else:
    # যদি সরাসরি ম্যাচ না করে, তবে রেগুলার এক্সপ্রেশন দিয়ে ঠিক করা
    import re
    content = re.sub(r'"selected":\s*[^}]+', '"selected": (sig != "HOLD" and math_sig == sig)', content)
    print('\n[SUCCESS] Logic fixed via regex!')

file_path.write_text(content, encoding='utf-8')
