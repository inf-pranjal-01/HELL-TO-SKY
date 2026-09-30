import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_tp = 
new_tp = 
content = content.replace(old_tp, new_tp)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
