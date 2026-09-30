import sys
import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
pattern = re.compile(r'def _score_and_report.*?return \{"precision".*?\}', re.DOTALL)
new_score = r
content = pattern.sub(lambda m: new_score, content)
start_idx = content.find('print("EMPIRICAL COMPARISON: BEFORE VS AFTER SPATIAL CORROBORATION & GRADUATED CONFIDENCE")')
if start_idx != -1:
    end_idx = content.find('print("=" * 90)', start_idx + 100)
    if end_idx != -1:
        content = content[:start_idx-8] + content[end_idx+16:]
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Successfully replaced _score_and_report via regex.")
