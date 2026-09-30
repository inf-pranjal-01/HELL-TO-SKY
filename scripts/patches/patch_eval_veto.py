import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_helper = 
new_helper = 
content = content.replace(old_helper, new_helper)
old_pred = 
new_pred = 
content = content.replace(old_pred, new_pred)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
