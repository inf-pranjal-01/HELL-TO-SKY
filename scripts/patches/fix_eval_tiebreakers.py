import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_mv = 
new_mv = 
content = content.replace(old_mv, new_mv)
old_frozen = 
new_frozen = 
content = content.replace(old_frozen, new_frozen)
old_drift = 
new_drift = 
content = content.replace(old_drift, new_drift)
old_spike = 
new_spike = 
content = content.replace(old_spike, new_spike)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
