import re
with open('model/features.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_block = 
new_block = 
content = content.replace(old_block, new_block)
with open('model/features.py', 'w', encoding='utf-8') as f:
    f.write(content)
