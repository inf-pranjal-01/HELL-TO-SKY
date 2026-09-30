import re
with open('config.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_allowance = 
new_allowance = 
content = content.replace(old_allowance, new_allowance)
with open('config.py', 'w', encoding='utf-8') as f:
    f.write(content)
