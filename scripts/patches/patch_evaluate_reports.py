import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
metric_code = 
old_loop = 
content = content.replace(old_loop, metric_code)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
