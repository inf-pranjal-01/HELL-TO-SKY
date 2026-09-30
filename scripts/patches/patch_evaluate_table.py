import sys
import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
target_block_start = '        print("\\nPerformance by fault type (Recall & Precision):")'
target_block_end = '        print("\\n  [EPISODE-LEVEL AUDIT FOR CONTINUOUS FAULTS]")'
if target_block_start in content and target_block_end in content:
    s_idx = content.find(target_block_start)
    e_idx = content.find(target_block_end)
    new_block = r
    content = content[:s_idx] + new_block + content[e_idx:]
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Successfully patched evaluate table.")
