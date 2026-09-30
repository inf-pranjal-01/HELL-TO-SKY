import re
with open('model/state.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_record = 
new_record = 
content = content.replace(old_record, new_record)
with open('model/state.py', 'w', encoding='utf-8') as f:
    f.write(content)
