import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
target = 
replace = 
content = content.replace(target, replace)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
