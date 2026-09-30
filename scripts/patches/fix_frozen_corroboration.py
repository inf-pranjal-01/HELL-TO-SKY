import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_frozen_corroboration = 
new_frozen_corroboration = 
content = content.replace(old_frozen_corroboration, new_frozen_corroboration)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
