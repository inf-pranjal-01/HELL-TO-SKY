import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    content = f.read()
target1 = 
replace1 = 
target2 = 
replace2 = 
target3 = 
replace3 = 
content = content.replace(target1, replace1)
content = content.replace(target2, replace2)
content = content.replace(target3, replace3)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
