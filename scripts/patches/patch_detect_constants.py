import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = re.sub(r'# independent check.*?PHYSICAL_BOUNDS = \{.*?\}\n', '', content, flags=re.DOTALL)
content = re.sub(r'(from config import .*)', r'\1, PHYSICAL_BOUNDS', content)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
