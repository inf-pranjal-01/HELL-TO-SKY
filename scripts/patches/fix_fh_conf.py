import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_fh = 
new_fh = 
content = content.replace(old_fh, new_fh)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    eval_content = f.read()
old_eval_fh = 
new_eval_fh = 
eval_content = eval_content.replace(old_eval_fh, new_eval_fh)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(eval_content)
