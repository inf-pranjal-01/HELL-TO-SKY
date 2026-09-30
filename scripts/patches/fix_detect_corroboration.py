import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_frozen_detect = 
new_frozen_detect = 
content = content.replace(old_frozen_detect, new_frozen_detect)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
