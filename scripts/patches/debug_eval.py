import sys
import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace(
    ,
)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
