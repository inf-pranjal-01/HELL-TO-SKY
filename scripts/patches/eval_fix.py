import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_str = 
new_str = 
content = content.replace(old_str, new_str)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
