import re
with open('model/engine.py', 'r', encoding='utf-8') as f:
    content = f.read()
target1 = 
replace1 = 
target2 = 
replace2 = 
content = content.replace(target1, replace1)
content = content.replace(target2, replace2)
with open('model/engine.py', 'w', encoding='utf-8') as f:
    f.write(content)
