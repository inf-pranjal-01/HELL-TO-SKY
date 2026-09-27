import re

with open('scripts/compile_judge_facing_docs.py', encoding='utf-8') as f:
    code = f.read()

lines = code.splitlines()

for idx, line in enumerate(lines):
    # Search for single { that isn't {{
    matches = re.findall(r'(?<!\{)\{(?!\{)', line)
    if matches:
        # Check if line is inside an f-string function
        if any(kw in line for kw in ['\text', '\delta', '_{\text', 'h_{\text']):
            print(f"Line {idx+1}: {line}")
