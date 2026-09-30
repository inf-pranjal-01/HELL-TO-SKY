import re
with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_def = 
new_def = 
content = content.replace(old_def, new_def)
old_return = 
new_return = 
content = content.replace(old_return, new_return)
old_call = 
new_call = 
content = content.replace(old_call, new_call)
with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
