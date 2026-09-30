import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_fuse = 
new_fuse = 
content = content.replace(old_fuse, new_fuse)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    eval_content = f.read()
old_eval_fuse = 
new_eval_fuse = 
eval_content = eval_content.replace(old_eval_fuse, new_eval_fuse)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(eval_content)
